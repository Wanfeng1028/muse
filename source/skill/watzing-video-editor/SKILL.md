---
name: video-editor
description: Transcribe-and-trim workflow for videos in this folder. Use when the user drops a video file into source/ and wants it edited, trimmed, or "cleaned up" — including phrases like "edit this video", "trim this", "cut this down", or just "clean it up" when a new video appears in source/.
---

# Video editor workflow

Transcribe a video, decide cuts collaboratively with the user, then render the trimmed result.

## Folder layout

This project uses a fixed structure:

```
source/   <-- input videos go here
output/   <-- rendered finals land here as <name>_final.mp4 (drafts as <name>_draft.mp4)
tmp/      <-- intermediate audio + transcript + cuts.json; auto-cleaned at the end
editor/   <-- generated HTML editor pages (one per video) for visual cut adjustment
```

Naming: `source/checklist.mp4` → `output/checklist_final.mp4`. Preserve the original basename, append `_final` (or `_draft` while iterating), output to `output/`. Never overwrite the source.

If any of these dirs don't exist, create them with `mkdir -p`.

## Tools required

- `ffmpeg` (and `ffprobe`)
- `whisper` (OpenAI Whisper CLI — `pip install openai-whisper`)
- `python3` for parsing the JSON transcript

## Steps

### 1. Locate the video

`ls source/`. If multiple videos exist, ask which one. Note duration with `ffprobe`:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 source/<video>
```

### 2. Extract audio

16kHz mono WAV is what Whisper wants:

```bash
ffmpeg -y -i source/<video> -vn -acodec pcm_s16le -ar 16000 -ac 1 tmp/audio.wav
```

### 3. Transcribe with word-level timestamps

`base.en` is fast and accurate enough for English screen recordings. Always use `--word_timestamps True` so cuts can land on word boundaries.

**Important:** pass `--output_format` only once. Whisper's CLI does not accumulate multiple `--output_format` flags — the last one wins. Use `json` (we'll print the text view ourselves from the JSON):

```bash
whisper tmp/audio.wav --model base.en --output_format json --word_timestamps True --output_dir tmp
```

If accuracy matters more than speed, escalate to `small.en` or `medium`.

### 4. Present the transcript and propose cuts

Show the segment-level transcript with `[mm:ss.xx → mm:ss.xx]` timestamps. Read the content carefully — the user often narrates their own editing instructions inside the video itself ("remove this part", "no, grab that", "skip the next bit"). Surface those instructions as your proposed cut plan.

Watch for:
- **Explicit removal cues** in narration ("no", "scratch that", "grab that", "let me re-do")
- **Re-takes** — the speaker says roughly the same thing twice; usually the second take is the keeper, but check whether the first take has on-screen action that needs to stay synced
- **Stutters and false starts** — "click, click", "from here you can either, from here you can…"
- **Long silences** (>5s) — likely dead time worth trimming, but may also be a visual demo (loading, AI processing); flag these to the user rather than cutting silently
- **Mistakes you should leave alone** — domain terms Whisper mishears ("pause button" might really be "paste button"); trust the audio over Whisper's spelling

Propose a table of cuts AND show the inverse — the keep windows + the final transcript reading as one continuous script. The user wants to verify both views before rendering. Flag judgment calls (which take to keep, how aggressively to trim silence) explicitly rather than guessing.

### 5. Pick precise cut points from word timestamps

Use the JSON to find word-level boundaries near each cut. Pad cuts slightly so words don't get clipped:

- ~0.1s before the first word of a kept segment
- ~0.2–0.3s after the last word (let the final word finish naturally)

```bash
python3 << 'EOF'
import json
with open('tmp/audio.json') as f:
    data = json.load(f)
for seg in data['segments']:
    print(f"[{seg['start']:.2f} -> {seg['end']:.2f}] {seg['text']}")
    for w in seg.get('words', []):
        print(f"   {w['start']:.2f}-{w['end']:.2f}: '{w['word'].strip()}'")
EOF
```

### 6. Render

**Single contiguous keep window** — re-encode for clean (non-keyframe) cuts:

```bash
ffmpeg -y -ss <start> -to <end> -i source/<video> \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart output/<name>_final.mp4
```

**Multiple keep windows** — extract each segment, then concat. Re-encode the segments (so all share codec params), then stream-copy concat:

```bash
SRC="source/<video>"
OUT="output/<name>_final.mp4"
# zsh-compatible: array of "start end" strings
PAIRS=("4.10 9.16" "27.43 41.49" ...)
# Or, when reading from a saved cuts JSON (after a visual-editor save):
# PAIRS=("${(@f)$(python3 -c "
# import json
# for s in json.load(open('tmp/<name>_cuts.json'))['segments']:
#     print(f\"{s['start']} {s['end']}\")
# ")}")

# Clean any prior intermediates (zsh-safe — avoid bare globs)
find tmp -maxdepth 1 -name 'seg_*.mp4' -delete 2>/dev/null
rm -f tmp/concat.txt

i=0
for pair in "${PAIRS[@]}"; do
  start="${pair%% *}"
  end="${pair##* }"
  # IMPORTANT: -nostdin so ffmpeg doesn't eat the for-loop's stdin
  ffmpeg -nostdin -y -ss "$start" -to "$end" -i "$SRC" \
    -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
    -c:a aac -b:a 192k "tmp/seg_${i}.mp4" 2>&1 | tail -1
  echo "file 'seg_${i}.mp4'" >> tmp/concat.txt
  i=$((i+1))
done

ffmpeg -nostdin -y -f concat -safe 0 -i tmp/concat.txt -c copy tmp/_concat.mp4

# Final pass: normalize audio loudness while copying video stream.
# I=-16 LUFS / TP=-1.5 dBTP matches what YouTube/Spotify/Apple Podcasts target,
# so the upload won't be re-leveled. LRA=11 keeps reasonable dynamic range.
ffmpeg -nostdin -y -i tmp/_concat.mp4 \
  -c:v copy \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  "$OUT"
rm -f tmp/_concat.mp4
```

For a single-window render (no concat), apply `loudnorm` directly in the same ffmpeg call:

```bash
ffmpeg -nostdin -y -ss <start> -to <end> -i source/<video> \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  -c:a aac -b:a 192k -movflags +faststart "$OUT"
```

If the user wants different loudness targets:
- **-14 LUFS** — Spotify/Tidal recommended (slightly louder, common for music podcasts)
- **-16 LUFS** — YouTube/Apple Podcasts default (the safe pick for spoken content)
- **-23 LUFS** — EBU broadcast standard (quieter, used in TV)

**Bash gotchas this protects against:**
- `echo "$pairs" | while read start end; do ffmpeg ...` — the `while` runs in a subshell AND ffmpeg without `-nostdin` consumes the pipe, dropping subsequent iterations. Always loop over an array, and always pass `-nostdin` to ffmpeg inside the loop.
- `mapfile` is a bash builtin and does not exist in zsh. Use `("${(@f)$(...)}")` for line-by-line capture in zsh.

CRF 18 is the default (visually lossless-ish). Raise to 23 for smaller files if asked.

### 7. Draft vs. final, and the visual editor loop

When the user wants to review before locking in cuts (which is the default — phrases like "make a draft", "let me see it first", or any uncertainty about the cut plan), render to `output/<name>_draft.mp4` and **don't** clean up `tmp/` yet. Then offer the visual editor.

The visual editor is an HTML page served by a tiny local Python server. It loads the source video, displays kept segments as draggable bands on a zoomable timeline, and saves edited cuts directly back to `tmp/<name>_cuts.json` over a `POST /api/save` endpoint.

```bash
# 1. Save current proposed cuts to tmp/cuts.json first
cat > tmp/cuts.json <<'EOF'
[
  {"start": 80.50, "end": 89.20},
  ...
]
EOF

# 2. Build the editor (writes editor/<name>.html with video, transcript, cuts, and save_path embedded)
python3 build_editor.py \
  source/<video> tmp/audio.json tmp/cuts.json editor/<name>.html

# 3. Start the server (background — will keep running until killed)
python3 serve_editor.py &
# Then tell the user: open http://localhost:8765/editor/<name>.html
```

Features in the editor:
- Scrub video, click empty timeline area to seek, click a green band to select that segment
- **Drag a band** to move it; **drag its left/right edge** to resize start/end
- **Zoom** with the +/− buttons or `Cmd`+scroll on the timeline; horizontal scroll for long videos
- Per-segment numeric `start` / `end` inputs, "Play" button (auto-pauses at segment end)
- "Preview Final" plays all kept segments in sequence
- Add/Delete segments
- **Undo** (button or `Cmd+Z`) — full history, last 100 states
- Transcript view with click-to-jump; green if inside a keep window, dim if cut
- Keyboard: `Space` play/pause, `←`/`→` seek 1s (Shift = 0.1s), `I` or `Cmd+<` set selected start, `O` or `Cmd+>` set selected end, `Cmd+S` save, `Cmd+Z` undo
- **Save** (button or `Cmd+S`) writes to `tmp/<name>_cuts.json` via the local server
- "Export" still available as a fallback download if the server isn't running

When the user reports they've saved, read `tmp/<name>_cuts.json` directly and re-render:

```bash
python3 -c "
import json
cuts = json.load(open('tmp/cuts.json'))
segs = cuts.get('segments', cuts) if isinstance(cuts, dict) else cuts
for s in segs:
    print(f\"{s['start']} {s['end']}\")
" | while read start end; do
  # ... same multi-segment render loop as above
done
```

Iterate until the user is happy, then render the final to `output/<name>_final.mp4` and clean up.

### 8. Clean up and report

Once the user confirms the final is good, delete everything in `tmp/` and the editor page:

```bash
find tmp -maxdepth 1 -type f ! -name '.gitkeep' -delete
rm -f editor/<name>.html
```

Report: final filename, duration, size. Done.

## Notes

- Source videos are the user's input — never overwrite or delete them.
- If `output/<name>_final.mp4` already exists, ask before overwriting.
- For "remove the long pause" requests not visible in the transcript, use silence detection: `ffmpeg -i tmp/audio.wav -af silencedetect=n=-30dB:d=0.5 -f null - 2>&1 | grep silence`.
- Whisper's first run downloads the model (~140MB for `base.en`); subsequent runs are cached.
- zsh quirk: bare `rm tmp/seg_*.mp4` errors with "no matches found" when no files exist. Use `find tmp -maxdepth 1 -name 'seg_*.mp4' -delete` instead.
