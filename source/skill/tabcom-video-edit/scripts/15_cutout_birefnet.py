# -*- coding: utf-8 -*-
"""Per-frame birefnet cutout for the single split window (highest quality)."""
import os, glob
from PIL import Image, ImageFilter
from rembg import remove, new_session

ROOT = os.path.dirname(os.path.abspath(__file__))
dst = os.path.join(ROOT, "cut_q1b")
os.makedirs(dst, exist_ok=True)
files = sorted(glob.glob(os.path.join(ROOT, "raw_q1", "*.png")))
s = new_session("birefnet-portrait")
for i, f in enumerate(files):
    o = os.path.join(dst, os.path.basename(f))
    if os.path.exists(o):
        continue
    cut = remove(Image.open(f), session=s)
    r, g, b, a = cut.split()
    a = a.point(lambda v: 0 if v < 120 else v).filter(ImageFilter.GaussianBlur(0.8))
    Image.merge("RGBA", (r, g, b, a)).save(o)
    if i % 10 == 0:
        print(f"biref q1 {i}/{len(files)}", flush=True)
print("BIREF Q1 DONE", flush=True)
