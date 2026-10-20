#!/usr/bin/env python3
"""Contact sheet: 30 evenly spaced frames of a video in one image, to look at it at a glance.

Usage: python3 hoja.py video.mp4 [salida.jpg]
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comun import duration, ffmpeg, require_ffmpeg

require_ffmpeg()
video = Path(sys.argv[1])
out = Path(sys.argv[2]) if len(sys.argv) > 2 else video.with_suffix(".hoja.jpg")

w, h = map(int, subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
     "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=False).stdout.strip().split(","))
cols, rows, scale = (6, 5, "400:-2") if w >= h else (10, 3, "-2:420")

d = duration(video)
n = cols * rows
ffmpeg("-i", video, "-vf", f"fps={n / d},scale={scale},tile={cols}x{rows}:padding=4",
       "-frames:v", 1, out)
print(f"{out}  (un cuadro cada {d / n:.1f} s, de izquierda a derecha y de arriba abajo)")
