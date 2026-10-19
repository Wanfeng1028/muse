---
name: auto-subtitles
version: 1.0.0
description: Auto-generate styled hardcoded subtitles from speech for any video. Whisper (large-v3) transcribes audio with word-level timestamps, splits into semantic chunks of 2-5 words, burns into video with a custom font and configurable colored plate. Works for any language Whisper supports. Use when the user wants automatic subtitles, voice-to-text caption burn-in, hardcoded subs for social media (TikTok, Reels, Shorts), brand-styled captions, automatic transcription with timing. Triggers — "auto subtitles", "burn subtitles", "voice to subtitles", "hardcoded captions", "вшить субтитры", "автотитры", "субтитры по голосу", "распознай речь и сделай титры", "субтитры с таймингом", "TikTok subtitles", "Reels captions".
---

# Auto-Subtitles — voice-driven hardcoded captions

End-to-end pipeline: video file → Whisper transcription with word timestamps → smart semantic chunking → ASS subtitle styling → ffmpeg burn-in.

## When to use

- TikTok / Reels / Shorts captions (most viewers watch muted)
- YouTube hardcoded subs for translation
- Brand video content where editor (CapCut) doesn't preserve subtitle styles
- Course/lecture recordings — auto-captions in any language

## Required from user

Ask for these before generating anything:

1. **Path to video file(s)** — `.mp4`, `.mov`, `.mkv`, etc.
2. **Language** — `ru`, `en`, `es`, `fr`, `de`, `zh`, `auto`, etc.
3. **Font** — path to a `.otf` / `.ttf` file. If user doesn't have one, suggest free options: Inter, Roboto, Montserrat, Bebas Neue. Drop in any local font file path.
4. **Frame size** — usually `1080×1920` (vertical / 9:16), `1920×1080` (horizontal), `1080×1080` (square)
5. **Plate position** — top or bottom. Default: top (doesn't cover faces if speaker is centered)
6. **Brand colors** (optional) — text color, plate color, accent color. Default: white text on `rgba(0,0,0,0.55)` plate
7. **Glossary** (optional but recommended) — list of names, brands, technical terms to seed Whisper for better accuracy

## Tech stack

- **mlx-whisper** for Apple Silicon (`pip install mlx-whisper`) — 5-10× faster than vanilla whisper
- **openai-whisper** fallback for non-Mac (`pip install openai-whisper`)
- **ffmpeg** with libass — `brew install ffmpeg` / `apt install ffmpeg`
- **Python 3.9+**

## Step 1 — Transcription with word timestamps

```bash
# Apple Silicon (fast)
mlx_whisper --model mlx-community/whisper-large-v3-mlx \
  --language ru \
  --output-format json \
  --word-timestamps True \
  --initial-prompt "BrandName ProductName customTerm1 customTerm2" \
  --output-dir transcripts/ \
  video.mp4

# Cross-platform
whisper video.mp4 --model large-v3 --language ru \
  --output_format json --word_timestamps True \
  --initial_prompt "..." --output_dir transcripts/
```

**Word-level timestamps are critical** — without them subtitles drift 0.5-1 sec from speech.

## Step 2 — Smart chunking + burn-in

```python
"""
burn-subs.py — voice-driven subtitle burn-in.
Usage:
  python3 burn-subs.py <video> <whisper.json> [output.mp4]

Config: edit constants at top of file.
"""
import sys, re, json, subprocess
from pathlib import Path

# ─── CONFIG (edit these) ───
FONT_NAME    = "Inter"                          # font family (must match what's in FONTS_DIR)
FONT_SIZE    = 60                                # 60pt good for 1080×1920; scale proportionally for other sizes
FONTS_DIR    = "/path/to/your/fonts"            # folder containing .otf/.ttf files
VIDEO_W      = 1080
VIDEO_H      = 1920
STRIP_Y      = 140                               # plate top edge (px from video top)
STRIP_H      = 140                               # plate height
PLATE_COLOR  = "black@0.55"                      # ffmpeg color/alpha
TEXT_COLOR   = "&H00FFFFFF"                      # ASS color (BGR hex, &H + alpha + BBGGRR). FFFFFF = white
OUTLINE_COLOR = "&H00000000"                     # black outline for legibility
OUTLINE_WIDTH = 2

MIN_WORDS, MAX_WORDS, MAX_CHARS = 2, 5, 32
PAUSE_THRESHOLD = 0.40                           # break on pauses ≥ 400ms
PUNCT_HARD = ".!?…"                              # hard break after
PUNCT_SOFT = ",;:—–"                             # soft break if ≥ MIN_WORDS

# Whisper hallucinations to skip (common training-data artifacts)
HALLUCINATIONS = re.compile(
    r'(?i)(subtitles\s+by|субтитры\s+(?:созда|подготов|сделал)|dimatorzok|'
    r'thank\s+you\s+for\s+watching|please\s+subscribe|продолжение\s+следует)'
)

def ms_to_ass(ms):
    h = ms // 3600000; ms %= 3600000
    m = ms // 60000; ms %= 60000
    s = ms // 1000; cs = (ms % 1000) // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def smart_chunks(data):
    words = []
    for seg in data.get("segments", []):
        if HALLUCINATIONS.search(seg.get("text", "")):
            continue
        for w in seg.get("words", []):
            tok = w.get("word", "").strip()
            if tok:
                words.append({"text": tok, "start": w["start"], "end": w["end"]})
    chunks, cur, cur_chars = [], [], 0
    def flush():
        nonlocal cur, cur_chars
        if not cur: return
        chunks.append({
            "start": int(cur[0]["start"]*1000),
            "end":   int(cur[-1]["end"]*1000),
            "text":  " ".join(w["text"] for w in cur)
        })
        cur, cur_chars = [], 0
    for i, w in enumerate(words):
        cur.append(w); cur_chars += len(w["text"]) + (1 if len(cur) > 1 else 0)
        last = w["text"][-1] if w["text"] else ""
        nxt = words[i+1] if i+1 < len(words) else None
        pause = (nxt["start"] - w["end"]) if nxt else 999
        force = False
        if len(cur) >= MAX_WORDS: force = True
        elif cur_chars >= MAX_CHARS and len(cur) >= MIN_WORDS: force = True
        elif last in PUNCT_HARD: force = True
        elif last in PUNCT_SOFT and len(cur) >= MIN_WORDS: force = True
        elif pause >= PAUSE_THRESHOLD and len(cur) >= MIN_WORDS: force = True
        elif nxt is None: force = True
        if force: flush()
    return chunks

def write_ass(cues, path):
    plate_center = STRIP_Y + STRIP_H // 2
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_W}
PlayResY: {VIDEO_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},{FONT_SIZE},{TEXT_COLOR},&H000000FF,{OUTLINE_COLOR},&H80000000,-1,0,0,0,100,100,0,0,1,{OUTLINE_WIDTH},0,5,30,30,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for c in cues:
        txt = f"{{\\pos({VIDEO_W//2},{plate_center})}}" + c["text"]
        lines.append(f"Dialogue: 0,{ms_to_ass(c['start'])},{ms_to_ass(c['end'])},Default,,0,0,0,,{txt}")
    path.write_text(header + "\n".join(lines), encoding="utf-8")

def burn(video, ass, out):
    vf = (f"drawbox=x=0:y={STRIP_Y}:w=iw:h={STRIP_H}:color={PLATE_COLOR}:t=fill,"
          f"subtitles={ass}:fontsdir={FONTS_DIR}")
    subprocess.check_call([
        "ffmpeg","-y","-loglevel","error","-stats",
        "-i", str(video), "-vf", vf,
        "-c:v","libx264","-preset","fast","-crf","20",
        "-c:a","copy","-movflags","+faststart", str(out)
    ])

def main():
    video = Path(sys.argv[1])
    js    = Path(sys.argv[2])
    out   = Path(sys.argv[3]) if len(sys.argv) > 3 else video.with_name(video.stem + "_subs.mp4")
    ass   = video.with_suffix(".ass")
    cues  = smart_chunks(json.loads(js.read_text(encoding="utf-8")))
    print(f"chunks: {len(cues)}")
    write_ass(cues, ass)
    burn(video, ass, out)
    ass.unlink()
    print(f"done: {out}")

if __name__ == "__main__":
    main()
```

## Step 3 — Batch processing

```bash
for v in *.mp4; do
  mlx_whisper --model mlx-community/whisper-large-v3-mlx \
    --language ru --output-format json --word-timestamps True \
    --output-dir transcripts/ "$v"
  python3 burn-subs.py "$v" "transcripts/${v%.mp4}.json" "out/${v%.mp4}_subs.mp4"
done
```

## Defaults by aspect ratio

| Frame | Font size | Plate y | Plate h | Max chars |
|---|---|---|---|---|
| 1080×1920 (9:16) | 60 | 140 | 140 | 32 |
| 1920×1080 (16:9) | 56 | 880 | 130 | 50 |
| 1080×1080 (1:1) | 56 | 80 | 130 | 36 |

## Best practices

1. **Always use word-level timestamps** — without them, subtitles drift 0.5-1s from speech
2. **Smart chunks beat fixed N-words** — break on punctuation + pauses, not arbitrary word count
3. **Filter hallucinations** — Whisper invents "Subtitles by X" / "thank you for watching" in silence
4. **Glossary helps** — pass `--initial-prompt` with brand names, jargon, person names
5. **Plate height ≤ 15% of video height** — keeps the subject visible
6. **Font size = 5-7% of video width** — readable on phones without dominating
7. **Outline at least 2px** — works on any background even without plate
8. **Test on 1 video first** — adjust position/size before batch processing all files

## Output format options

Beyond burn-in MP4:

| Format | When | How |
|---|---|---|
| Burned-in MP4 (default) | Final upload, CapCut won't strip style | as above |
| Standalone .srt next to video | User wants to edit in CapCut/Premiere | mlx_whisper `--output-format srt` |
| ProRes 4444 .mov overlay with alpha | Drag-n-drop over edited video | render frames separately, encode with `-c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le` |
| ASS file separately | Advanced editing in Aegisub | save .ass without burning |

## Pre-delivery checklist

- [ ] Font loaded correctly (not falling back to Arial)
- [ ] No hallucinations in output (search for trained phrases)
- [ ] Subtitles sync with voice (check first/last word in a few cues)
- [ ] Text doesn't overflow video width
- [ ] Plate position doesn't cover key visual elements
- [ ] Audio preserved (`-c:a copy` keeps original quality)
