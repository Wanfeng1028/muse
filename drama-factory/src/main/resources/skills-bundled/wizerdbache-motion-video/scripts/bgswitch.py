"""Background ground colour: how often a film changes its ground, and how many distinct grounds it uses.

Question it serves (user review of r10, 2026-09-29): "the background keeps switching between beige, black and orange;
lock the theme colour". This tool counts ground switches; whether a switch hurts is the user's call.

Method. Frames are decoded at --fps (default 4) and scaled to --width (default 64). For each frame the ground is read
from the border ring (--ring px wide, default 2, about 3 % of the width on each side):
    - border pixels are binned at 16 levels per channel; the most common bin is the candidate ground;
    - if that bin (plus pixels within --dist of its mean) holds at least --share (0.6) of the ring, the ground is the
      mean colour of those pixels; otherwise the frame is `mixed` (a photo, gradient or content across the edge).
Ground runs: the current ground is an anchor colour. A frame farther than --dist (RGB Euclidean, default 40) from the
anchor starts a candidate; the candidate is confirmed as a switch once the following frames stay within --dist of it
for --hold s (default 0.5). Mixed frames neither break nor confirm a run. A fast fade (every intermediate colour lasts
< --hold) is one switch; a slow fade ends as one switch because each new candidate replaces the last unconfirmed one.
Distinct grounds: confirmed run colours merged within --dist.

Reported: n_switches, n_grounds (with hex colour and seconds each), dominant_share (seconds on the most-used ground /
seconds on any ground), mixed_share, the run list.

Calibration (--selftest, synthetic frames): a locked beige ground with moving content and a 0.25 s edge touch -> 0
switches, 1 ground; hard cuts beige/black/orange/beige 3 s each -> 3 switches, 3 grounds; a 2 s beige->black fade ->
1 switch, 2 grounds; a 3 s full-bleed noise block between beige -> 0 switches, mixed share > 0. The selftest also
runs one synthetic clip through ffmpeg encode/decode to check the decoding path.
Real controls (run before trusting numbers, see references/evidence-and-instruments.md): r11 S2 and S3 keep one cream ground (read on the 5 fps
sheets) and must read 0-1 switches; r11 O1 alternates cream / red / dark and must read >= 4.

What it cannot determine: a ground change that happens only in the centre (a card grows over a constant border)
is not a switch; a full-bleed photo section reads as mixed, not as a ground; whether the switching is tiring.

Usage:
    python -X utf8 scripts/bgswitch.py <video> [--out f.json]
    python -X utf8 scripts/bgswitch.py --selftest
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


def probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout
    w, h = (int(x) for x in out.strip().split(",")[:2])
    return w, h


def decode(video, fps, width):
    w, h = probe(video)
    height = max(2, int(round(h * width / w / 2)) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={width}:{height}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, height, width, 3).astype(np.float32)


def ground(frame, ring=2, dist=40.0, share=0.6):
    """Ground colour of one frame (RGB float array) from its border ring, or None if mixed."""
    edge = np.concatenate([frame[:ring].reshape(-1, 3), frame[-ring:].reshape(-1, 3),
                           frame[ring:-ring, :ring].reshape(-1, 3), frame[ring:-ring, -ring:].reshape(-1, 3)])
    bins = (edge // 16).astype(np.int32)
    keys = bins[:, 0] * 256 + bins[:, 1] * 16 + bins[:, 2]
    vals, counts = np.unique(keys, return_counts=True)
    top = edge[keys == vals[counts.argmax()]].mean(axis=0)
    near = np.linalg.norm(edge - top, axis=1) <= dist
    if near.mean() < share:
        return None
    return edge[near].mean(axis=0)


def runs_from_grounds(grounds, fps, dist=40.0, hold=0.5):
    need = max(1, int(round(hold * fps)))
    runs, anchor, start = [], None, 0
    cand, cand_start, cand_n = None, 0, 0
    for i, g in enumerate(grounds):
        if g is None:
            continue
        if anchor is None:
            anchor, start = g, i
            continue
        if np.linalg.norm(g - anchor) <= dist:
            cand, cand_n = None, 0
            continue
        if cand is None or np.linalg.norm(g - cand) > dist:
            cand, cand_start, cand_n = g, i, 1
        else:
            cand_n += 1
        if cand_n >= need:
            runs.append({"start_s": round(start / fps, 2), "end_s": round(cand_start / fps, 2), "rgb": anchor})
            anchor, start, cand, cand_n = cand, cand_start, None, 0
    if anchor is not None:
        runs.append({"start_s": round(start / fps, 2), "end_s": round(len(grounds) / fps, 2), "rgb": anchor})
    return runs


def summarise(grounds, fps, dist=40.0, hold=0.5):
    runs = runs_from_grounds(grounds, fps, dist, hold)
    distinct = []
    for r in runs:
        for d in distinct:
            if np.linalg.norm(r["rgb"] - d["rgb"]) <= dist:
                d["seconds"] += r["end_s"] - r["start_s"]
                break
        else:
            distinct.append({"rgb": r["rgb"], "seconds": r["end_s"] - r["start_s"]})
    hexc = lambda c: "#%02x%02x%02x" % tuple(int(round(v)) for v in c)
    total = sum(d["seconds"] for d in distinct)
    return {"n_switches": max(0, len(runs) - 1), "n_grounds": len(distinct),
            "dominant_share": round(max((d["seconds"] for d in distinct), default=0) / total, 3) if total else None,
            "grounds": [{"hex": hexc(d["rgb"]), "seconds": round(d["seconds"], 2)} for d in distinct],
            "mixed_share": round(sum(g is None for g in grounds) / max(1, len(grounds)), 3),
            "runs": [{"start_s": r["start_s"], "end_s": r["end_s"], "hex": hexc(r["rgb"])} for r in runs]}


def measure(video, fps=4, width=64, ring=2, dist=40.0, share=0.6, hold=0.5):
    frames = decode(video, fps, width)
    res = summarise([ground(f, ring, dist, share) for f in frames], fps, dist, hold)
    res.update({"video": str(video), "fps": fps, "width": width})
    return res


# ---------- selftest ----------
BEIGE, BLACK, ORANGE = (240, 232, 218), (30, 30, 32), (200, 80, 40)


def synth(blocks, fps=4, h=114, w=64, seed=0):
    """blocks: list of (seconds, kind, arg). kind 'solid' arg=rgb; 'fade' arg=(rgb0, rgb1); 'noise'."""
    rng = np.random.default_rng(seed)
    frames = []
    for sec, kind, arg in blocks:
        n = int(round(sec * fps))
        for k in range(n):
            if kind == "solid":
                f = np.empty((h, w, 3), np.float32); f[:] = arg
            elif kind == "fade":
                a = k / max(1, n - 1)
                f = np.empty((h, w, 3), np.float32); f[:] = (1 - a) * np.array(arg[0]) + a * np.array(arg[1])
            else:
                f = rng.uniform(0, 255, (h, w, 3)).astype(np.float32)
            if kind != "noise":  # moving content in the middle, never touching the ring
                y = 20 + (len(frames) * 3) % 60
                f[y:y + 20, 16:48] = (20, 20, 20) if kind == "solid" and arg == BEIGE else (250, 250, 250)
            frames.append(f)
    return frames


def selftest():
    fps, ok = 4, True
    cases = []
    locked = synth([(6, "solid", BEIGE)])
    for i in (8,):  # one frame (0.25 s) where content crosses the whole edge
        locked[i][:, :, :] = (20, 20, 20)
    cases.append(("locked beige, moving content, 0.25 s edge touch", locked, lambda r: r["n_switches"] == 0 and r["n_grounds"] == 1))
    cuts = synth([(3, "solid", BEIGE), (3, "solid", BLACK), (3, "solid", ORANGE), (3, "solid", BEIGE)])
    cases.append(("hard cuts beige/black/orange/beige", cuts, lambda r: r["n_switches"] == 3 and r["n_grounds"] == 3))
    fade = synth([(2, "solid", BEIGE), (2, "fade", (BEIGE, BLACK)), (2, "solid", BLACK)])
    cases.append(("2 s beige->black fade", fade, lambda r: r["n_switches"] == 1 and r["n_grounds"] == 2))
    photo = synth([(3, "solid", BEIGE), (3, "noise", None), (3, "solid", BEIGE)])
    cases.append(("full-bleed noise between beige", photo, lambda r: r["n_switches"] == 0 and r["mixed_share"] > 0.2))
    for name, frames, want in cases:
        r = summarise([ground(f) for f in frames], fps)
        good = want(r)
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {name}: switches {r['n_switches']}, grounds {r['n_grounds']}, mixed {r['mixed_share']}")
    with tempfile.TemporaryDirectory() as td:  # decoding path: encode the hard-cut clip, read it back
        clip = Path(td) / "cuts.mp4"
        data = np.stack([np.repeat(np.repeat(f, 4, 0), 4, 1) for f in cuts]).astype(np.uint8)
        p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                            f"{data.shape[2]}x{data.shape[1]}", "-r", str(fps), "-i", "-", "-pix_fmt", "yuv420p",
                            str(clip)], input=data.tobytes(), capture_output=True)
        r = measure(clip) if p.returncode == 0 else {"n_switches": None, "n_grounds": None}
        good = r["n_switches"] == 3 and r["n_grounds"] == 3
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} encoded hard-cut clip via ffmpeg: switches {r['n_switches']}, grounds {r['n_grounds']}")
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--fps", type=float, default=4)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    r = measure(a.video, fps=a.fps)
    print(json.dumps({k: v for k, v in r.items() if k != "runs"}, ensure_ascii=False))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
