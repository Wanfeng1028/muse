import os, glob, subprocess
import numpy as np
from scipy import ndimage
from PIL import Image, ImageFilter
from rembg import remove, new_session

ROOT = os.getcwd()
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import tabcom_paths as P
SRC = P.src()
WINDOWS = [("q1", 47.25, 3.60), ("q2", 58.00, 8.70)]

for name, s, d in WINDOWS:
    raw = os.path.join(ROOT, f"raw_{name}")
    os.makedirs(raw, exist_ok=True)
    if not glob.glob(os.path.join(raw, "*.png")):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(s), "-t", str(d), "-i", SRC,
                        "-vf", "crop=940:1040:70:340,fps=25", os.path.join(raw, "%04d.png")], check=True)
    print(name, "frames", len(os.listdir(raw)), flush=True)

import gc

# phase 1: gates with birefnet (loaded alone)
biref = new_session("birefnet-portrait")
for name, s, d in WINDOWS:
    raw = sorted(glob.glob(os.path.join(ROOT, f"raw_{name}", "*.png")))
    gate_p = os.path.join(ROOT, f"gate_{name}.npy")
    if not os.path.exists(gate_p):
        gate = None
        for f in raw[::18] + [raw[-1]]:
            m = np.array(remove(Image.open(f), session=biref, only_mask=True)) > 128
            gate = m if gate is None else (gate | m)
        np.save(gate_p, ndimage.binary_dilation(gate, iterations=22))
        print("gate", name, "built", flush=True)
del biref
gc.collect()

# phase 2: per-frame fast model
fast = new_session("isnet-general-use")

for name, s, d in WINDOWS:
    raw = sorted(glob.glob(os.path.join(ROOT, f"raw_{name}", "*.png")))
    gate = np.load(os.path.join(ROOT, f"gate_{name}.npy"))
    dst = os.path.join(ROOT, f"cut_{name}")
    os.makedirs(dst, exist_ok=True)
    for i, f in enumerate(raw):
        o = os.path.join(dst, os.path.basename(f))
        if os.path.exists(o):
            continue
        for attempt in range(4):
            try:
                cut = remove(Image.open(f), session=fast)
                break
            except MemoryError:
                gc.collect()
                import time as _t; _t.sleep(4)
        else:
            raise RuntimeError("OOM on " + f)
        arr = np.array(cut).astype(np.int16)
        a = arr[..., 3]
        hard = (a > 140) & gate
        op = ndimage.binary_opening(hard, iterations=6)
        lab, n = ndimage.label(op)
        if n >= 1:
            sizes = ndimage.sum(op, lab, range(1, n + 1))
            seed = lab == (np.argmax(sizes) + 1)
            recon = ndimage.binary_propagation(seed, mask=hard)
        else:
            recon = hard
        a2 = np.where(recon, a, 0)
        rows = np.where(a2.sum(axis=1) > 0)[0]
        if len(rows):
            t0 = rows[0]
            zone = np.zeros_like(recon); zone[t0:t0 + 115, :] = True
            bright = np.maximum.reduce([arr[..., 0], arr[..., 1], arr[..., 2]]) > 68
            bad = ndimage.binary_dilation(bright & zone & recon, iterations=1)
            for c, v in zip(range(3), (28, 24, 22)):
                arr[..., c] = np.where(bad, v, arr[..., c])
        im2 = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        im2.putalpha(Image.fromarray(a2.astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)))
        im2.save(o)
        if i % 40 == 0:
            print(f"{name} {i}/{len(raw)}", flush=True)
    print(name, "CUT DONE", flush=True)
print("ALL CUTOUT DONE", flush=True)
