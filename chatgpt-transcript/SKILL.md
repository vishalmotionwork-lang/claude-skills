---
name: chatgpt-transcript
description: Transcribe a local audio/video file using ChatGPT's own voice-to-text (gpt-4o-transcribe) via your logged-in browser session — no API key or cost. Chunks long audio, auto-recovers ASR decoder loops, resumes on rate-limit, and saves a timestamped .txt + .json next to the file. Use when the user wants ChatGPT-quality transcription of a local file, especially Hindi/Gujarati/Hinglish code-switching. For transcribing from URLs (YouTube/Instagram/TikTok), use a Whisper-based tool instead.
---

# ChatGPT Transcript

Transcribe a local audio/video file with **ChatGPT's transcription model**
(`gpt-4o-transcribe`, the model behind ChatGPT voice) — using the user's
logged-in ChatGPT **browser session**, so there is no API key or payment.
Best when the user wants ChatGPT-quality transcription, including
Hindi/Gujarati/Hinglish code-switching in native script.

For transcribing from URLs (YouTube/Instagram/TikTok) via Whisper instead, use a
Whisper-based URL transcriber.

## Prerequisites

- **Logged into ChatGPT** in a supported browser (Brave → Chrome → Edge →
  Firefox, auto-detected). The skill reads that browser's `chatgpt.com` cookies
  to authenticate — see [Browser cookies](#browser-cookies-how-auth-works) below.
- **`ffmpeg`** on PATH (`brew install ffmpeg` / `apt install ffmpeg`). Used to
  transcode and chunk audio.
- **`python3`** on PATH. First run auto-creates a venv beside the scripts and
  installs `browser_cookie3` + `curl_cffi` — no manual pip needed.

## Usage

```
/chatgpt-transcript <path-to-audio-or-video> [more files…]
```

If no path is given, ask the user for the file path(s).

## Workflow

1. **Parse args** — collect file path(s) from the arguments. Strip surrounding
   quotes. Skip anything that isn't an existing file (warn, continue).

2. **Run the helper, one file at a time** (serial — never parallel, to stay well
   under ChatGPT rate limits):

   ```bash
   "$SKILL_DIR/scripts/chatgpt_transcribe.sh" "/abs/path/to/file.m4a"
   ```

   where `$SKILL_DIR` is the directory containing this `SKILL.md`. The helper
   handles everything: browser-session auth (auto-detects Brave → Chrome → Edge
   → Firefox), 3-min chunking, the ChatGPT transcribe endpoint, decoder-loop
   collapse, adaptive 1-min re-split of any looped/empty chunk, resume-on-429,
   and writes `<name>.chatgpt.txt` (timestamped sections) + `<name>.chatgpt.json`
   next to the input. The transcript is also printed to stdout.

3. **Long files run in the background** — a 30-min file is ~10+ requests over
   several minutes. Launch it in the background, then wait for completion (e.g. an
   `until grep -q "\[saved:" <logfile>` wait), and report when done. Don't block
   the session polling.

4. **Surface results** — show the saved path(s) and a short content summary.
   Output is in the **native script** ChatGPT returns (Devanagari/Gujarati for
   Hindi/Gujarati; Latin for English). To romanize to Latin Hinglish, offer a
   Groq/llama romanizer as a follow-up (it does not add ChatGPT requests).

## Options (pass through to the helper)

| flag | default | meaning |
|------|---------|---------|
| `--minutes N` | `3` | chunk length. ≤10 (endpoint max), but 10 loops — keep ≤3. |
| `--browser B` | `auto` | `brave`\|`chrome`\|`edge`\|`firefox`\|`auto` |
| `--delay S` | `4` | base seconds between requests (jitter added) |
| `--out DIR` | next to input | output directory |

## Browser cookies (how auth works)

This skill does **not** use the ChatGPT API. It reuses your existing browser
login:

1. It reads `chatgpt.com` cookies straight from your local browser profile via
   `browser_cookie3` (Brave → Chrome → Edge → Firefox, in that order for
   `--browser auto`).
2. It exchanges those cookies at `chatgpt.com/api/auth/session` for a short-lived
   `accessToken`, and grabs `cf_clearance` for Cloudflare.
3. It calls the internal `chatgpt.com/backend-api/transcribe` endpoint,
   impersonating Chrome (`curl_cffi`) so Cloudflare accepts the request.

**First run on macOS pops a Keychain prompt** ("… wants to use Brave/Chrome Safe
Storage") — click **Allow** so the cookies can be decrypted. Nothing is stored by
this skill; the token lives only in memory for the run.

## Notes / gotchas

- **Requires being logged into ChatGPT** in a supported browser. If auth fails,
  log in at chatgpt.com and retry (and grant the Keychain prompt).
- The endpoint accepts **mp3 only** — the helper transcodes for you; m4a/long
  chunks are handled internally.
- `gpt-4o-transcribe` **hallucinates repeat-loops** on long/multi-speaker audio;
  the helper detects the chars/sec spike and re-transcribes those windows at 60s.
- **Rate-safe by design**: serial requests, jittered delays, one reused token,
  hard stop on HTTP 429. On a 429 it saves progress and exits 75 — re-run the
  **same** command after the cooldown to resume from where it stopped.
- This uses an undocumented internal endpoint on the user's **own** account — a
  ToS gray area for personal use. Don't run high-volume batches.
- First invocation auto-creates a venv at `scripts/.chatgpt-transcript-venv`
  (deps: `browser_cookie3`, `curl_cffi`); system deps: `ffmpeg`.
