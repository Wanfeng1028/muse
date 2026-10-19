#!/usr/bin/env python3
"""Generate bottom-positioned caption PNGs from voice-over lines.

One caption card per VO line, styled smaller and lower than the title cards so the
two don't collide. Same Pillow → PNG → ffmpeg-overlay toolchain as generate_titles.py
(this ffmpeg build lacks libass, so burned .srt subtitles aren't an option).

Input is a JSON array of objects with the line text and its on-screen window:
    [
      {"text": "One prompt. Zero clicks from me.", "start": 0.3, "end": 4.8},
      {"text": "It drives a real browser.",        "start": 5.3, "end": 8.8}
    ]
The start/end come from the shot list's per-segment timing in the FINAL video.

Usage:
    uv run --with pillow python generate_captions.py --lines captions.json --out captions/
Emits captions/caption_NN.png and prints an ffmpeg overlay snippet (with the enable
windows) ready to paste into add_voiceover.sh.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

CANVAS_W = 1080
MAX_TEXT_W = 980
FONT_SIZE = 42          # smaller than titles' 52
SCRIM = (10, 12, 20, 190)
TEXT = (255, 255, 255, 255)
RADIUS = 18
PAD_X, PAD_Y = 30, 18
LINE_SPACING = 10


def find_font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise FileNotFoundError("No font found; edit FONT_CANDIDATES")


def wrap(draw, text, font):
    """Greedy wrap to keep each line within MAX_TEXT_W."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= MAX_TEXT_W:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def make_caption(text):
    probe = ImageDraw.Draw(Image.new("RGBA", (CANVAS_W, 400)))
    font = find_font(FONT_SIZE)
    wrapped = wrap(probe, text, font)
    bbox = probe.multiline_textbbox((0, 0), wrapped, font=font, spacing=LINE_SPACING, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    h = th + 2 * PAD_Y
    img = Image.new("RGBA", (CANVAS_W, h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bx0 = (CANVAS_W - tw) / 2 - PAD_X
    d.rounded_rectangle([bx0, 4, bx0 + tw + 2 * PAD_X, 4 + h], RADIUS, fill=SCRIM)
    d.multiline_text((CANVAS_W / 2, 4 + h / 2), wrapped, font=font, spacing=LINE_SPACING,
                     align="center", anchor="mm", fill=TEXT)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", required=True, help="JSON array of {text,start,end}")
    ap.add_argument("--out", default="captions")
    ap.add_argument("--bottom-margin", type=int, default=210,
                    help="px from the bottom edge of a 1920-tall frame")
    ap.add_argument("--frame-h", type=int, default=1920)
    args = ap.parse_args()

    lines = json.loads(Path(args.lines).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    snippets = []
    for i, item in enumerate(lines, 1):
        img = make_caption(item["text"])
        path = out / f"caption_{i:02d}.png"
        img.save(path)
        y = args.frame_h - img.height - args.bottom_margin
        snippets.append((i, item["start"], item["end"], y, path))
        print(f"  {path}  {img.size}  y={y}  ({item['start']}-{item['end']}s)")

    # Print a ready-to-paste overlay chain (caption inputs come after title inputs).
    print("\n# overlay chain (adjust input indices to your ffmpeg -i order):")
    for i, s, e, y, _ in snippets:
        print(f"[vN][IN]overlay=0:{y}:enable='between(t,{s},{e})'[vN+1];")


if __name__ == "__main__":
    main()
