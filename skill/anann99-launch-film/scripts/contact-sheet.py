#!/usr/bin/env python3
"""
Labelled contact sheet of images (e.g. all product captures), so agents can see everything in one Read.

  contact-sheet.py video/public/shots capture/shots_sheet.jpg [--cols 3] [--width 640]
"""
import argparse
import glob
import os

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src', help='directory (all png/jpg) or glob pattern')
    ap.add_argument('out')
    ap.add_argument('--cols', type=int, default=3)
    ap.add_argument('--width', type=int, default=640)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.src, '*.png')) + glob.glob(os.path.join(a.src, '*.jpg'))) if os.path.isdir(a.src) else sorted(glob.glob(a.src))
    if not files:
        raise SystemExit('no images found')
    w = a.width
    h = int(w * 9 / 16)
    label = 20
    rows = -(-len(files) // a.cols)
    sheet = Image.new('RGB', (w * a.cols, (h + label) * rows), 'white')
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        im = Image.open(f).convert('RGB')
        im.thumbnail((w, h))
        x, y = (i % a.cols) * w, (i // a.cols) * (h + label)
        sheet.paste(im, (x, y + label))
        d.text((x + 4, y + 4), os.path.basename(f), fill='black')
    sheet.save(a.out, quality=85)
    print(f'{a.out}: {len(files)} images, {a.cols} cols')


if __name__ == '__main__':
    main()
