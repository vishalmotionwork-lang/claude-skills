"""chatgpt_transcript.py — audio/video -> transcript via ChatGPT's own voice-to-text.

Uses your logged-in browser session (cookies) to call ChatGPT's internal
transcription endpoint (gpt-4o-transcribe), the same model behind ChatGPT voice.

Self-contained: cookie auth + Cloudflare-capable client + chunking + loop recovery.

Endpoint: POST https://chatgpt.com/backend-api/transcribe
  multipart field "file", mp3/audio-mpeg only -> {"text": "...", ...}

Rate-safe: serial requests, jittered delays, one reused token, stop on HTTP 429.
gpt-4o-transcribe loops on long/meeting audio, so we chunk (default 3 min), collapse
decoder loops, and adaptively re-split any looped/near-empty chunk down to ~60s.

Usage:
  chatgpt_transcript.py <file> [--minutes 3] [--browser auto] [--delay 4] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from difflib import SequenceMatcher

import browser_cookie3
from curl_cffi import CurlMime
from curl_cffi import requests as creq

BASE = "https://chatgpt.com"
TRANSCRIBE_EP = BASE + "/backend-api/transcribe"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
SAMPLE_RATE = 16000
LOOP_CPS = 28  # chars/sec above this over a span = probable ASR decoder loop

_LOOP_RE = re.compile(r"(.{4,80}?)(?:\s*\1){3,}", re.DOTALL)
_SENT_SPLIT = re.compile(r"(?<=[।.?!])\s+")


# ---------------- session / auth ----------------
_BROWSERS = {"brave": browser_cookie3.brave, "chrome": browser_cookie3.chrome,
             "edge": browser_cookie3.edge, "firefox": browser_cookie3.firefox}


def _session_for(browser: str):
    cj = _BROWSERS[browser](domain_name="chatgpt.com")
    cookies = {c.name: c.value for c in cj}
    if not cookies:
        return None
    s = creq.Session(impersonate="chrome131")
    for k, v in cookies.items():
        s.cookies.set(k, v, domain=".chatgpt.com")
    s.headers.update({"User-Agent": UA, "Accept": "*/*",
                      "Origin": BASE, "Referer": BASE + "/"})
    r = s.get(BASE + "/api/auth/session", timeout=30)
    if r.status_code != 200:
        return None
    try:
        token = r.json().get("accessToken")
    except Exception:  # noqa: BLE001
        return None
    if not token:
        return None
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def get_session(browser: str, log):
    order = [browser] if browser != "auto" else ["brave", "chrome", "edge", "firefox"]
    for b in order:
        try:
            s = _session_for(b)
        except Exception as e:  # noqa: BLE001
            log(f"  ({b}: {type(e).__name__})")
            s = None
        if s:
            log(f"[chatgpt] authenticated via {b} session")
            return s
    raise SystemExit(
        "Could not authenticate. Log into chatgpt.com in Brave/Chrome, then retry "
        "(grant the Keychain prompt so cookies can be decrypted).")


# ---------------- audio ----------------
def probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def chunk_audio(path: str, seconds: int) -> list[dict]:
    out_dir = tempfile.mkdtemp(prefix="cgpt_")
    duration = probe_duration(path)
    pattern = os.path.join(out_dir, "chunk_%03d.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SAMPLE_RATE),
         "-b:a", "64k", "-f", "segment", "-segment_time", str(seconds),
         "-reset_timestamps", "1", pattern], check=True)
    files = sorted(f for f in os.listdir(out_dir) if f.startswith("chunk_"))
    chunks = []
    for i, f in enumerate(files):
        start = i * seconds
        end = min((i + 1) * seconds, int(duration)) if duration else (i + 1) * seconds
        chunks.append({"index": i, "path": os.path.join(out_dir, f),
                       "start": start, "end": end})
    return chunks


# ---------------- loop collapse ----------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\wऀ-ॿ઀-૿]+", " ", s.lower())).strip()


def collapse_repeats(text: str) -> str:
    prev, out = None, text
    for _ in range(5):
        if out == prev:
            break
        prev = out
        out = _LOOP_RE.sub(lambda m: m.group(1) + " " + m.group(1), out)
    parts = _SENT_SPLIT.split(out)
    kept, window, W = [], [], 12
    for p in parts:
        k = _norm(p)
        if not k:
            continue
        if len(k) > 15:
            if any(k == w or SequenceMatcher(None, k, w).ratio() > 0.9 for w in window):
                continue
            window.append(k)
            window[:] = window[-W:]
        kept.append(p.strip())
    deduped, last = [], None
    for p in kept:
        k = _norm(p)
        if k and k == last:
            continue
        last = k
        deduped.append(p)
    return re.sub(r"\s{2,}", " ", " ".join(deduped)).strip()


# ---------------- transcription ----------------
class RateLimited(BaseException):
    """ChatGPT 429. Subclasses BaseException (not Exception) so per-chunk
    `except Exception` handlers won't swallow it — a rate-limit must propagate
    and hard-stop the run to protect the account, then resume later."""


def transcribe_one(session, path: str, retries: int = 3) -> str:
    audio = open(path, "rb").read()
    last = None
    for attempt in range(retries + 1):
        mp = CurlMime()
        mp.addpart(name="file", filename=os.path.basename(path),
                   content_type="audio/mpeg", data=audio)
        try:
            r = session.post(TRANSCRIBE_EP, multipart=mp, timeout=300)
        except Exception as e:  # network/timeout/connection — transient, retry
            last = f"network: {type(e).__name__}: {e}"
            if attempt < retries:
                time.sleep(5 + attempt * 5)
                continue
            raise RuntimeError(f"failed after {retries + 1} tries — {last}")
        if r.status_code == 200:
            return (r.json().get("text") or "").strip()
        if r.status_code == 429:
            raise RateLimited("429 rate-limited by ChatGPT — stopping to keep the account safe.")
        last = f"HTTP {r.status_code}: {r.text[:200]}"
        if attempt < retries:
            time.sleep(3 + attempt * 4)
            continue
        raise RuntimeError(str(last))
    return ""


def _fmt(s: int) -> str:
    return f"{s // 60:02d}:{s % 60:02d}"


def _load_cached(prog_path):
    """Return {index: result} of previously-completed (non-failed) chunks."""
    if not prog_path or not os.path.isfile(prog_path):
        return {}
    try:
        data = json.load(open(prog_path))
    except Exception:  # noqa: BLE001 — a corrupt sidecar just means start fresh
        return {}
    return {r["index"]: r for r in data.get("chunks", [])
            if r.get("text") and not r.get("failed")}


def _save_progress(prog_path, file, duration, results):
    """Atomically persist progress so a 429/crash never loses completed chunks."""
    if not prog_path:
        return
    tmp = prog_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"file": file, "duration_sec": int(duration),
                   "chunks": results}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, prog_path)


def transcribe_file(path: str, minutes: float, browser: str, delay: float, log,
                    prog_path=None) -> dict:
    secs = int(minutes * 60)
    duration = probe_duration(path)
    chunks = chunk_audio(path, secs)
    cached = _load_cached(prog_path)
    fname = os.path.basename(path)
    log(f"[chatgpt] {fname} · {duration/60:.1f} min -> "
        f"{len(chunks)} chunk(s) of {minutes:g} min · serial, ~{delay}s gap"
        + (f" · resuming ({len(cached)} cached)" if cached else ""))
    session = None  # created lazily — a fully-cached resume needs no auth

    def window(p: str, span: int, depth: int) -> str:
        text = collapse_repeats(transcribe_one(session, p))
        cps = len(text) / max(1, span)
        looped, dropped = cps > LOOP_CPS, (len(text) < 5 and span > 90)
        if (looped or dropped) and span > 70 and depth < 2:
            log(f"      ↳ {'loop' if looped else 'near-empty'} "
                f"({cps:.0f} chars/s) — re-splitting {span}s into ~60s")
            subs = chunk_audio(p, 60)
            pieces = []
            try:
                for j, sub in enumerate(subs):
                    try:
                        pieces.append(window(sub["path"], sub["end"] - sub["start"], depth + 1))
                    except Exception as e:  # noqa: BLE001 — one bad sub-chunk must not drop the parent window
                        log(f"      ↳ sub-chunk failed, skipping — {e}")
                    if j < len(subs) - 1:
                        time.sleep(delay + random.uniform(0, 2.0))
            finally:
                for sub in subs:
                    try:
                        os.unlink(sub["path"])
                    except OSError:
                        pass
            return collapse_repeats(" ".join(x for x in pieces if x))
        return text

    results = []
    try:
        for c in chunks:
            if c["index"] in cached:
                results.append(cached[c["index"]])
                log(f"  [{_fmt(c['start'])}–{_fmt(c['end'])}] cached ✓")
                continue
            if session is None:
                session = get_session(browser, log)
            t0 = time.time()
            span = max(1, c["end"] - c["start"])
            failed = False
            try:
                text = window(c["path"], span, 0)
            except Exception as e:  # noqa: BLE001 — transient endpoint failure must not kill the whole job
                text, failed = "", True
                log(f"  [{_fmt(c['start'])}–{_fmt(c['end'])}] FAILED, left blank — {e}")
            results.append({"index": c["index"], "start": c["start"],
                            "end": c["end"], "text": text, "failed": failed})
            _save_progress(prog_path, fname, duration, results)
            if not failed:
                log(f"  [{_fmt(c['start'])}–{_fmt(c['end'])}] {len(text)} chars "
                    f"({time.time()-t0:.1f}s)")
            if c is not chunks[-1]:
                time.sleep(delay + random.uniform(0, 2.0))
        # second pass: retry chunks that failed outright (temp files still on disk)
        retry_idx = [i for i, r in enumerate(results) if r["failed"]]
        if retry_idx:
            log(f"[chatgpt] second pass — retrying {len(retry_idx)} failed chunk(s)")
            for i in retry_idx:
                c = chunks[i]
                span = max(1, c["end"] - c["start"])
                if session is None:
                    session = get_session(browser, log)
                time.sleep(delay + random.uniform(0, 2.0))
                try:
                    text = window(c["path"], span, 0)
                    results[i]["text"], results[i]["failed"] = text, False
                    log(f"  [retry {_fmt(c['start'])}–{_fmt(c['end'])}] {len(text)} chars")
                except Exception as e:  # noqa: BLE001 — leave blank, keep the rest
                    log(f"  [retry {_fmt(c['start'])}–{_fmt(c['end'])}] still failing — {e}")
                _save_progress(prog_path, fname, duration, results)
    finally:
        for c in chunks:
            try:
                os.unlink(c["path"])
            except OSError:
                pass
    combined = "\n".join(r["text"] for r in results if r["text"]).strip()
    return {"file": os.path.basename(path), "model": "chatgpt-web (gpt-4o-transcribe)",
            "duration_sec": int(duration), "chunks": results, "text": combined}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Transcribe audio via ChatGPT (browser session).")
    ap.add_argument("input", help="audio/video file")
    ap.add_argument("--minutes", type=float, default=3.0, help="chunk length (default 3)")
    ap.add_argument("--browser", default="auto", help="brave|chrome|edge|firefox|auto")
    ap.add_argument("--delay", type=float, default=4.0, help="base seconds between requests")
    ap.add_argument("--out", default=None, help="output dir (default: next to input)")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        raise SystemExit(f"not a file: {args.input}")
    log = lambda m: print(m, file=sys.stderr, flush=True)  # noqa: E731

    out_dir = args.out or os.path.dirname(os.path.abspath(args.input))
    base = os.path.join(out_dir, os.path.splitext(os.path.basename(args.input))[0])
    prog_path = base + ".chatgpt.progress.json"

    try:
        out = transcribe_file(args.input, args.minutes, args.browser, args.delay,
                              log, prog_path)
    except RateLimited as e:
        log(f"\n{e}")
        log("[resume] progress saved — re-run the SAME command after the cooldown "
            "to continue from where it stopped (exit 75).")
        return 75

    with open(base + ".chatgpt.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open(base + ".chatgpt.txt", "w") as f:
        f.write(f"# {out['file']} — via {out['model']}\n\n")
        for c in out["chunks"]:
            mark = "  ⚠️ WINDOW FAILED — re-run this range" if c.get("failed") else ""
            f.write(f"[{_fmt(c['start'])}–{_fmt(c['end'])}]{mark}\n{c['text']}\n\n")
    print(out["text"])
    failed = [c for c in out["chunks"] if c.get("failed")]
    if failed:
        ranges = ", ".join(f"{_fmt(c['start'])}–{_fmt(c['end'])}" for c in failed)
        log(f"[warn] {len(failed)} window(s) could not be transcribed: {ranges}")
    else:
        try:  # complete + clean — drop the resume sidecar
            os.remove(prog_path)
        except OSError:
            pass
    log(f"\n[saved: {base}.chatgpt.txt  +  .json]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
