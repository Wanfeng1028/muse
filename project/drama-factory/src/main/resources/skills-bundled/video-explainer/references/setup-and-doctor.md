# Setup and doctor

Use this reference for a new machine or a blocked doctor result.

## Supported fast path

- Node.js 20 or newer
- Python 3.10 or newer
- `ffmpeg` and `ffprobe`
- Installed dependencies under `remotion/node_modules`
- A writable output directory
- One TTS path:
  - macOS `say` for a clearly labeled demo-quality result; or
  - an already configured Fish Audio environment for publication-oriented narration

Run:

```bash
node scripts/video-explainer.mjs doctor --json --output <output-directory>
```

Doctor is read-only. It checks whether credentials are present but never prints, copies, validates remotely, or writes them.

## Recovery actions

- Missing Node: install Node 20+.
- Missing Python: install Python 3.10+.
- Missing `ffmpeg` or `ffprobe`: install ffmpeg and rerun doctor.
- Missing Remotion: run `npm install` inside `remotion/`, then rerun doctor.
- No TTS path: use the macOS demo path or configure a supported provider outside this skill.
- Output not writable: choose a different directory; do not weaken filesystem permissions broadly.

Do not start dependency installation, account signup, API-key creation, or a paid TTS call unless the user has authorized that separate action.
