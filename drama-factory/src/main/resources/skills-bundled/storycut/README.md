# StoryCut — Claude Code Skill

A free, local-first Claude Skill that turns a spoken video, podcast, or timestamped transcript into an ordered, source-verified editorial cut list.

## Install

1. Copy this entire `storycut` directory to one of these locations:
   - A Claude Code project: `.claude/skills/storycut/`
   - Personal skills: `~/.claude/skills/storycut/`
2. Requirements: Python 3.10+; for **video/audio input**, install `ffmpeg` and run `python3 -m pip install faster-whisper` in the Python environment used by Claude Code. The first transcription may download a model (internet required). Timed `.srt`/`.vtt` inputs do **not** need these extra dependencies.
3. Start a Claude Code session and ask: `Use StoryCut on /absolute/path/to/interview.mp4. Make a 90-second founder story for LinkedIn.`

## How it works

```text
local video/audio ──FFmpeg + faster-whisper──> verified transcript
timestamped SRT/VTT ────────────────────────> verified transcript
verified transcript ──Claude story editing──> draft clip IDs
draft clip IDs ──Python validator/exporter──> cutlist.md / .csv / .json
```

Claude supplies editorial choices. The Python code computes timecodes from the transcription rather than trusting model-invented numbers.

## Manual CLI demo (no AI key required)

```bash
python3 scripts/storycut.py doctor
python3 scripts/storycut.py prepare tests/fixtures/interview.srt --out /tmp/storycut-demo
python3 scripts/storycut.py validate /tmp/storycut-demo/transcript.json tests/fixtures/cutlist_draft.json --out /tmp/storycut-demo
```

The fixture proves that parsing, source traceability, and export work. It is **not** a test of AI editorial quality or the transcription backend.

## What V1 does and does not do

- ✅ Local media transcription with an optional installed faster-whisper backend
- ✅ Import SRT/VTT/timestamped TXT
- ✅ Claude-driven story selection, ordering, reasons, and narrative notes
- ✅ Timestamp and quotation verification, downloadable JSON/CSV/Markdown cut lists
- ❌ Does not render a finished video, auto-caption, publish, or guarantee frame-perfect edit points
- ❌ Doesn't make the Claude model itself free; users must have Claude Code access

## Cost and privacy

The scripts are free and require no paid API. Local transcription uses your CPU/GPU and may require a model download. Claude usage depends on your Claude plan/API arrangements. Local media and transcripts stay on the machine unless the user deliberately shares them; text that Claude reads is processed according to the user's Claude environment.

## License

MIT; see `LICENSE`.

