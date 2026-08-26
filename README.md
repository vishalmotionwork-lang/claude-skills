# claude-skills

A small collection of [Claude Code Skills](https://docs.claude.com/en/docs/claude-code/skills).
Each subfolder is a self-contained skill — copy the one you want into your
`~/.claude/skills/` (user-level) or `.claude/skills/` (project-level) directory.

| Skill | What it does | License |
|-------|--------------|---------|
| [`chatgpt-transcript`](./chatgpt-transcript) | Transcribe local audio/video with **ChatGPT's own voice-to-text** (`gpt-4o-transcribe`) via your logged-in **browser session** — no API key or cost. Chunks long audio, recovers ASR loops, resumes on rate-limit. Strong on Hindi/Gujarati/Hinglish. | MIT |
| [`skill-creator`](./skill-creator) | Anthropic's official skill for **creating, editing, evaluating, and benchmarking** skills. Redistributed unmodified — see its [ATTRIBUTION](./skill-creator/ATTRIBUTION.md). | Apache-2.0 |
| [`creator-reverse-engineer`](https://github.com/vishalmotionwork-lang/creator-reverse-engineer) **↗ own repo** | Reverse-engineer any public Instagram creator into **one HTML document**: every post fetched, every reel transcribed and scene-cut, all their platforms torn down, the content formula and money machine decoded — ending in a replication plan. Ships a complete worked example. | MIT |

## Install a single skill

```bash
# user-level (available in every project)
git clone https://github.com/vishalmotionwork-lang/claude-skills.git /tmp/claude-skills
cp -R /tmp/claude-skills/chatgpt-transcript ~/.claude/skills/chatgpt-transcript
cp -R /tmp/claude-skills/skill-creator      ~/.claude/skills/skill-creator
```

Then in Claude Code the skills are available by name, e.g.:

```
/chatgpt-transcript /path/to/audio.m4a
```

## chatgpt-transcript — quick notes

- Reuses your existing **ChatGPT browser login** (Brave → Chrome → Edge →
  Firefox); reads `chatgpt.com` cookies locally, stores nothing.
- Needs **ffmpeg** and **python3**; the first run auto-creates a venv beside the
  scripts and installs `browser_cookie3` + `curl_cffi`.
- On macOS, the first run pops a **Keychain** prompt — click **Allow** so the
  cookies can be decrypted.
- Uses an undocumented internal endpoint on **your own** account — a ToS gray
  area for personal use. Don't run high-volume batches.

See [`chatgpt-transcript/README.md`](./chatgpt-transcript/README.md) for full
details, flags, and how auth works.

## skill-creator — quick notes

Anthropic's skill for building and improving skills (draft → eval → benchmark →
iterate). Redistributed here unmodified under Apache-2.0. Upstream:
https://github.com/anthropics/skills/tree/main/skills/skill-creator
