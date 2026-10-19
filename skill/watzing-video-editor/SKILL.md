---
name: watzing-video-editor
description: A collaborative video cutting pipeline for clips dropped into source/. Transcribes speech with word timings, proposes an edit plan alongside the user, and renders trimmed results. Trigger when a fresh clip lands in source/ or the user asks to cut, trim, clean up, or edit a video.
version: "1.0.0"
author: playhouse
license: MIT
---

# Collaborative video trimming

Take a raw clip, turn its audio into a timed transcript, work out with the user which spans to keep, then produce a rendered cut.

## Workspace layout

Everything lives under a fixed set of directories:

```
source/   input clips live here
output/   finished renders land here as <basename>_final.mp4 (work-in-progress as <basename>_draft.mp4)
tmp/      scratch space: extracted audio, transcript JSON, cut lists; wiped once finished
editor/   generated HTML pages (one per clip) for adjusting cuts visually
```

Filename rule: a clip named `source/demo.mp4` produces `output/demo_final.mp4`. Keep the original stem, add the `_final` suffix (or `_draft` while iterating), always write into `output/`. The source file is never modified.

Create any missing directory with `mkdir -p`.

## Dependencies

- `ffmpeg` plus `ffprobe`
- `whisper` — the OpenAI CLI, installed via `pip install openai-whisper`
- `python3` for reading transcript JSON

## Workflow

### 1. Find the input clip

Run `ls source/`. If more than one file is present, ask the user which to work on. Grab its length:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 source/<video>
```

### 2. Pull out the audio track

Whisper expects 16 kHz mono PCM:

```bash
ffmpeg -y -i source/<video> -vn -acodec pcm_s16le -ar 16000 -ac 1 tmp/audio.wav
```

### 3. Run Whisper with word timings

`base.en` gives a good speed/accuracy balance for English screencasts. Enable `--word_timestamps True` so that later cuts can be snapped to individual word edges.

Note: Whisper's CLI keeps only the last `--output_format` value, so pass it once. Use `json` and print the readable text yourself later:

```bash
whisper tmp/audio.wav --model base.en --output_format json --word_timestamps True --output_dir tmp
```

If quality matters more than wall-clock time, bump to `small.en` or `medium`.

### 4. Show the transcript and propose an edit

Print each segment with `[mm:ss.xx → mm:ss.xx]` markers. Read carefully — narrators frequently describe their own edits aloud ("take that out", "no, keep this bit", "skip ahead"), so treat those remarks as candidate cuts.

Things to look for:
- **Spoken removal cues** — "no", "scratch that", "redo", "start over"
- **Repeat takes** — the same line said twice; usually the later take is better, but confirm the earlier one doesn't carry screen action that must stay in sync
- **False starts and stumbles** — "so you, so you click", "the — the button"
- **Long silent stretches** (>5 s) — often dead air worth removing, but sometimes it's a demo (loading, AI thinking); surface these instead of silently cutting
- **Whisper mishears on jargon** — a term like "paste button" may be transcribed as "pause button"; trust what you hear over the transcript's spelling

Present two views: a table of proposed cuts, and the inverse — the kept windows plus the concatenated transcript as one continuous script. Users want to sanity-check both before committing. Call out judgment calls (which take wins, how hard to trim silence) rather than deciding silently.

### 5. Derive exact cut points from word data

Read the JSON to find word boundaries near each cut, then pad:
- roughly 0.1 s before the first word of a kept span
- roughly 0.2–0.3 s past the last word so the final syllable isn't clipped

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

**One continuous keep window** — re-encode so the cut lands on a clean frame:

```bash
ffmpeg -y -ss <start> -to <end> -i source/<video> \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart output/<name>_final.mp4
```

**Several keep windows** — cut each piece, then join. Re-encode all pieces with matching settings, then concatenate with a stream copy:

```bash
SRC="source/<video>"
OUT="output/<name>_final.mp4"
# zsh array of "start end" strings
PAIRS=("4.10 9.16" "27.43 41.49" ...)
# When reading from a saved cuts JSON (post-editor save):
# PAIRS=("${(@f)$(python3 -c "
# import json
# for s in json.load(open('tmp/<name>_cuts.json'))['segments']:
#     print(f\"{s['start']} {s['end']}\")
# ")}")

# Clear stale intermediates (find avoids zsh "no matches" errors)
find tmp -maxdepth 1 -name 'seg_*.mp4' -delete 2>/dev/null
rm -f tmp/concat.txt

i=0
for pair in "${PAIRS[@]}"; do
  start="${pair%% *}"
  end="${pair##* }"
  # -nostdin prevents ffmpeg from swallowing the loop's stdin
  ffmpeg -nostdin -y -ss "$start" -to "$end" -i "$SRC" \
    -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
    -c:a aac -b:a 192k "tmp/seg_${i}.mp4" 2>&1 | tail -1
  echo "file 'seg_${i}.mp4'" >> tmp/concat.txt
  i=$((i+1))
done

ffmpeg -nostdin -y -f concat -safe 0 -i tmp/concat.txt -c copy tmp/_concat.mp4

# Loudness normalize; video is copied untouched.
# I=-16 LUFS / TP=-1.5 dBTP matches YouTube/Spotify/Apple Podcasts targets
# so platforms won't re-level the upload. LRA=11 preserves natural dynamics.
ffmpeg -nostdin -y -i tmp/_concat.mp4 \
  -c:v copy \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  "$OUT"
rm -f tmp/_concat.mp4
```

For a single-window render, fold `loudnorm` into the same call:

```bash
ffmpeg -nostdin -y -ss <start> -to <end> -i source/<video> \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  -c:a aac -b:a 192k -movflags +faststart "$OUT"
```

Alternative loudness targets if the user asks:
- **-14 LUFS** — Spotify/Tidal preference (a touch hotter, popular for music-heavy shows)
- **-16 LUFS** — YouTube/Apple Podcasts baseline (safest for voice)
- **-23 LUFS** — EBU broadcast spec (quieter, used in TV)

**Shell pitfalls this avoids:**
- `echo "$pairs" | while read start end; do ffmpeg ...` — the `while` runs in a subshell and ffmpeg without `-nostdin` drains the pipe, so later iterations vanish. Always iterate an array and pass `-nostdin`.
- `mapfile` is a bash builtin, absent in zsh. Use `("${(@f)$(...)}")` to capture lines in zsh.

CRF 18 is the default (near-lossless). Raise to 23 for smaller files on request.

### 7. Draft mode and the visual editor loop

When the user wants to preview before locking cuts — phrases like "make a draft", "show me first", or any uncertainty — render to `output/<name>_draft.mp4` and leave `tmp/` in place. Then offer the visual editor.

The editor is an HTML page served by a small local Python server. It loads the source clip, draws kept spans as draggable bands on a zoomable timeline, and posts edits back to `tmp/<name>_cuts.json` via `POST /api/save`.

```bash
# 1. Persist the current proposed cuts
cat > tmp/cuts.json <<'EOF'
[
  {"start": 80.50, "end": 89.20},
  ...
]
EOF

# 2. Generate the editor page (embeds video, transcript, cuts, save path into editor/<name>.html)
python3 build_editor.py \
  source/<video> tmp/audio.json tmp/cuts.json editor/<name>.html

# 3. Launch the server in the background
python3 serve_editor.py &
# Tell the user to open http://localhost:8765/editor/<name>.html
```

Editor capabilities:
- Scrub, click empty timeline space to seek, click a green band to select it
- **Drag a band** to shift it; **drag either edge** to resize
- **Zoom** via +/− buttons or `Cmd`+scroll; horizontal scrolling for long clips
- Numeric `start` / `end` fields per span; a "Play" button that auto-pauses at span end
- "Preview Final" plays all kept spans back-to-back
- Add or remove spans
- **Undo** (button or `Cmd+Z`) with full history, last 100 states
- Transcript pane with click-to-seek; green inside a kept window, dimmed elsewhere
- Keys: `Space` play/pause, `←`/`→` seek 1 s (Shift = 0.1 s), `I` or `Cmd+<` set selected start, `O` or `Cmd+>` set selected end, `Cmd+S` save, `Cmd+Z` undo
- **Save** (button or `Cmd+S`) posts to `tmp/<name>_cuts.json` via the server
- "Export" remains available as a fallback download when the server is off

After the user says they've saved, read `tmp/<name>_cuts.json` and re-render:

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

Iterate until the user approves, then produce `output/<name>_final.mp4` and clean up.

### 8. Cleanup and report

After final approval, remove everything in `tmp/` and the editor page:

```bash
find tmp -maxdepth 1 -type f ! -name '.gitkeep' -delete
rm -f editor/<name>.html
```

Report the output filename, duration, and size. Done.

## Notes

- Source clips are the user's input — never overwrite or delete them.
- If `output/<name>_final.mp4` exists, ask before replacing it.
- For "cut the long pause" requests that don't show in the transcript, use silence detection: `ffmpeg -i tmp/audio.wav -af silencedetect=n=-30dB:d=0.5 -f null - 2>&1 | grep silence`.
- The first Whisper run downloads the model (~140 MB for `base.en`); later runs use the cache.
- zsh quirk: a bare `rm tmp/seg_*.mp4` fails with "no matches found" when nothing matches. Prefer `find tmp -maxdepth 1 -name 'seg_*.mp4' -delete`.

## 来源说明

功能参考自 https://github.com/watzing/claude-video-editor。本文档及随附脚本为独立重写，未复制原始文本。
