#!/usr/bin/env bash
# chatgpt_transcribe.sh — wrapper for /chatgpt-transcript.
# Transcribes an audio/video file via ChatGPT's voice-to-text (browser session).
# Bootstraps a dedicated venv on first run so the skill is self-contained.
#
# Usage: chatgpt_transcribe.sh <file> [--minutes 3] [--browser auto] [--delay 4] [--out DIR]

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$DIR/chatgpt_transcript.py"
VENV="$DIR/.chatgpt-transcript-venv"

for cmd in ffmpeg ffprobe python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing dep: $cmd (try: brew install $cmd)" >&2; exit 69; }
done

if [ ! -x "$VENV/bin/python" ]; then
  echo "[setup] creating venv + installing deps (one time)…" >&2
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip >/dev/null
  "$VENV/bin/pip" install -q browser_cookie3 curl_cffi >&2
fi

exec "$VENV/bin/python" "$SCRIPT" "$@"
