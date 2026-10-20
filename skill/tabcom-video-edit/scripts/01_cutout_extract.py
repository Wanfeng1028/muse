# -*- coding: utf-8 -*-
"""Extract person frames for split windows and remove background with rembg."""
import os
import subprocess
import glob
from PIL import Image
from rembg import remove, new_session

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import tabcom_paths as P
ROOT = P.work()
SRC = P.src()

WINDOWS = [
    ("w1", 12.60, 18.18),
    ("w2", 45.52, 51.34),
    ("w3", 68.62, 75.00),
]

for name, s, e in WINDOWS:
    raw = os.path.join(ROOT, f"frames_{name}_raw")
    out = os.path.join(ROOT, f"frames_{name}_cut")
    os.makedirs(raw, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(s), "-t", str(round(e - s, 2)),
                    "-i", SRC, "-vf", "crop=920:1020:80:230,fps=25", os.path.join(raw, "%04d.png")], check=True)
    print(name, "extracted", len(os.listdir(raw)), "frames", flush=True)

session = new_session("u2net_human_seg")
print("session ready", flush=True)

for name, s, e in WINDOWS:
    raw = os.path.join(ROOT, f"frames_{name}_raw")
    out = os.path.join(ROOT, f"frames_{name}_cut")
    files = sorted(glob.glob(os.path.join(raw, "*.png")))
    for i, f in enumerate(files):
        dst = os.path.join(out, os.path.basename(f))
        if os.path.exists(dst):
            continue
        img = Image.open(f)
        cut = remove(img, session=session)
        cut.save(dst)
        if i % 25 == 0:
            print(f"{name}: {i}/{len(files)}", flush=True)
    print(name, "DONE", len(files), flush=True)
print("ALL CUTOUT DONE", flush=True)
