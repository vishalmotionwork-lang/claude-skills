# chatgpt-transcript

A [Claude Code Skill](https://docs.claude.com/en/docs/claude-code/skills) that
transcribes local audio/video with **ChatGPT's own voice-to-text**
(`gpt-4o-transcribe`) through your **logged-in browser session** — no API key, no
per-minute cost.

It's especially good at **Hindi / Gujarati / Hinglish code-switching**, returning
text in native script.

## What it does

- Reuses your existing **ChatGPT browser login** (Brave → Chrome → Edge →
  Firefox) — reads `chatgpt.com` cookies locally, no credentials stored.
- **Chunks** long audio (default 3 min) and transcribes serially with jittered
  delays so you stay under rate limits.
- **Collapses ASR decoder loops** and adaptively **re-splits** looped or empty
  windows down to ~60s.
- **Resumes on rate-limit**: on HTTP 429 it saves progress and exits — re-run the
  same command to continue.
- Saves `<name>.chatgpt.txt` (timestamped sections) + `<name>.chatgpt.json` next
  to the input, and prints the transcript to stdout.

## Install

Drop the folder into your Claude Code skills directory:

```bash
# user-level
git clone https://github.com/<owner>/chatgpt-transcript.git \
  ~/.claude/skills/chatgpt-transcript

# or project-level
git clone https://github.com/<owner>/chatgpt-transcript.git \
  .claude/skills/chatgpt-transcript
```

Then in Claude Code:

```
/chatgpt-transcript /path/to/audio.m4a
```

## Requirements

- Logged into **ChatGPT** in a supported browser
- **ffmpeg** on PATH (`brew install ffmpeg` / `apt install ffmpeg`)
- **python3** — the first run auto-creates a venv beside the scripts and installs
  `browser_cookie3` + `curl_cffi`

On macOS, the first run pops a **Keychain** prompt so the browser cookies can be
decrypted — click **Allow**.

## Direct use (without Claude Code)

```bash
scripts/chatgpt_transcribe.sh /path/to/file.m4a --minutes 3 --browser auto
```

| flag | default | meaning |
|------|---------|---------|
| `--minutes N` | `3` | chunk length (≤10; keep ≤3, longer loops) |
| `--browser B` | `auto` | `brave`\|`chrome`\|`edge`\|`firefox`\|`auto` |
| `--delay S` | `4` | base seconds between requests (jitter added) |
| `--out DIR` | next to input | output directory |

## How it works

1. Read `chatgpt.com` cookies from your browser profile (`browser_cookie3`).
2. Exchange them at `chatgpt.com/api/auth/session` for a short-lived
   `accessToken` (+ `cf_clearance` for Cloudflare).
3. `POST chatgpt.com/backend-api/transcribe` per chunk, impersonating Chrome via
   `curl_cffi` so Cloudflare accepts it.

## Caveats

- Uses an **undocumented internal endpoint** on **your own** ChatGPT account — a
  ToS gray area intended for personal use. Don't run high-volume batches.
- The endpoint accepts **mp3 only**; the helper transcodes for you.
- `gpt-4o-transcribe` can hallucinate repeat-loops on long/multi-speaker audio —
  handled via loop-collapse + re-split, but very long single chunks are worse, so
  keep `--minutes ≤ 3`.

## License

MIT — see [LICENSE](LICENSE).
