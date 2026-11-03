#!/usr/bin/env python3
"""Generate a circular alpha mask (+ optional ring) for the facecam bubble.

The mask is a white circle on black — used by ffmpeg's alphamerge as the alpha
channel (white = opaque, black = transparent), turning a square webcam crop into
a round bubble. Optionally emits a separate ring PNG to overlay as a border.

Usage:
    uv run --with pillow python make_circle_mask.py --size 320 --out mask.png
    # with a ring border:
    uv run --with pillow python make_circle_mask.py --size 320 --out mask.png \
        --ring ring.png --ring-width 6 --ring-color "255,255,255"
"""
import argparse
from PIL import Image, ImageDraw

# 4× supersample then downscale for smooth anti-aliased edges.
SS = 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=320, help="Bubble diameter in px")
    ap.add_argument("--out", required=True, help="Output mask PNG (white circle on black)")
    ap.add_argument("--ring", help="Optional ring PNG (transparent with a colored stroke)")
    ap.add_argument("--ring-width", type=int, default=6)
    ap.add_argument("--ring-color", default="255,255,255")
    args = ap.parse_args()

    d = args.size * SS

    # Alpha mask: white filled circle on black.
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, d - 1, d - 1], fill=255)
    mask.resize((args.size, args.size), Image.LANCZOS).save(args.out)
    print(f"  mask  -> {args.out}  ({args.size}x{args.size})")

    if args.ring:
        color = tuple(int(x) for x in args.ring_color.split(","))
        w = args.ring_width * SS
        ring = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse(
            [w // 2, w // 2, d - 1 - w // 2, d - 1 - w // 2],
            outline=(*color, 255), width=w,
        )
        ring.resize((args.size, args.size), Image.LANCZOS).save(args.ring)
        print(f"  ring  -> {args.ring}  ({args.size}x{args.size}, {args.ring_width}px)")


if __name__ == "__main__":
    main()
