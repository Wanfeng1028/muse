#!/usr/bin/env python3
"""Generate title-card overlay PNGs for social video edits.

This ffmpeg build often lacks libfreetype (no drawtext filter), so overlays are
rendered as transparent PNGs with Pillow and composited later with the overlay filter.

Usage:
    uv run --with pillow python generate_titles.py \
        --titles titles.json \
        --out titles/ \
        --style dark-pill

titles.json is a JSON array of strings, one per card. Use "\n" to force a 2-line split
(recommended — keep each line under ~40 chars for phone legibility). If a line has no
"\n", the script keeps it single-line but shrinks the font to fit within the frame.

Styles: dark-pill (default), light-pill, bottom-bar, accent-pill.
For accent-pill, also pass --accent-color "R,G,B".
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Style presets: (scrim_rgba, text_rgba, radius, pad_x, pad_y, font_size)
STYLES = {
    "dark-pill":   ((10, 12, 20, 165),  (255, 255, 255, 255), 26, 44, 30, 52),
    "light-pill":  ((255, 255, 255, 200), (10, 12, 20, 255),  26, 44, 30, 52),
    "bottom-bar":  ((10, 12, 20, 200),  (255, 255, 255, 255),  0, 60, 36, 48),
    "accent-pill": (None,               (255, 255, 255, 255), 26, 44, 30, 52),  # scrim from --accent-color
}

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

CANVAS_W = 1080
MAX_TEXT_W = 1016  # 1080 − 2×32 safety margin
LINE_SPACING = 14


def find_font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise FileNotFoundError("No bold font found; edit FONT_CANDIDATES in generate_titles.py")


def fit_font(draw, text, base_size):
    """Shrink font until the widest line fits MAX_TEXT_W (min 24pt)."""
    size = base_size
    while size > 24:
        font = find_font(size)
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=LINE_SPACING, align="center")
        if bbox[2] - bbox[0] <= MAX_TEXT_W:
            return font, bbox
        size -= 2
    font = find_font(24)
    return font, draw.multiline_textbbox((0, 0), text, font=font, spacing=LINE_SPACING, align="center")


def make_card(text, style, accent):
    scrim, text_color, radius, pad_x, pad_y, font_size = STYLES[style]
    if style == "accent-pill":
        scrim = (*accent, 180)

    probe = ImageDraw.Draw(Image.new("RGBA", (CANVAS_W, 600)))
    font, bbox = fit_font(probe, text, font_size)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    h = th + 2 * pad_y

    img = Image.new("RGBA", (CANVAS_W, h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if style == "bottom-bar":
        # full-width bar, no rounding
        d.rectangle([0, 4, CANVAS_W, 4 + h], fill=scrim)
    else:
        bx0 = (CANVAS_W - tw) / 2 - pad_x
        d.rounded_rectangle([bx0, 4, bx0 + tw + 2 * pad_x, 4 + h], radius, fill=scrim)

    d.multiline_text((CANVAS_W / 2, 4 + h / 2), text, font=font, spacing=LINE_SPACING,
                     align="center", anchor="mm", fill=text_color)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--titles", required=True, help="JSON array of title strings")
    ap.add_argument("--out", default="titles", help="Output directory")
    ap.add_argument("--style", default="dark-pill", choices=list(STYLES))
    ap.add_argument("--accent-color", default="66,99,235", help="R,G,B for accent-pill")
    args = ap.parse_args()

    accent = tuple(int(x) for x in args.accent_color.split(","))
    titles = json.loads(Path(args.titles).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for i, text in enumerate(titles, 1):
        img = make_card(text, args.style, accent)
        path = out / f"title_{i:02d}.png"
        img.save(path)
        print(f"  {path}  {img.size}")
    print(f"Done — {len(titles)} cards ({args.style}).")


if __name__ == "__main__":
    main()
