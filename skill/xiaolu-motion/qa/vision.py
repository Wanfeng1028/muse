"""Python wrapper around qa/vision_probe.swift (Apple Vision, on-device).

analyze(video, frames, faces=True, text=False, rects=False) -> {"size", "fps", "frames": [...]}
face_track(video, frames) -> {n: [{"box":{x,y,w,h}, "mouth":{...}|None}]} in video pixels
"""
import json
import subprocess
from pathlib import Path

from render.common import CACHE

SRC = Path(__file__).with_name("vision_probe.swift")
BIN = CACHE / "bin" / "vision_probe"


def build():
    if BIN.exists() and BIN.stat().st_mtime >= SRC.stat().st_mtime:
        return BIN
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["swiftc", "-O", "-o", str(BIN), str(SRC)], check=True, capture_output=True)
    return BIN


def analyze(video, frames, faces=True, text=False, rects=False, dump=None, chunk=400):
    exe = build()
    frames = sorted(set(int(f) for f in frames))
    out = None
    for k in range(0, len(frames), chunk):   # keep the command line short
        part = frames[k:k + chunk]
        cmd = [str(exe), str(video), "--frames", ",".join(map(str, part))]
        if faces:
            cmd.append("--faces")
        if text:
            cmd.append("--text")
        if rects:
            cmd.append("--rects")
        if dump:
            Path(dump).mkdir(parents=True, exist_ok=True)
            cmd += ["--dump", str(dump)]
        r = subprocess.run(cmd, check=True, capture_output=True)
        d = json.loads(r.stdout)
        if out is None:
            out = d
        else:
            out["frames"] += d["frames"]
    return out
