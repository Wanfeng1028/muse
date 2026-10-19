#!/usr/bin/env python3
"""Onset-locked cutter v2 — cut on EVERY moment the song enables.

Differences from a marker/priority-based builder:
  - Cut grid = librosa onset grid (every audible hit/transient), not just
    beat-tracker beats filtered by priority. Nothing is skipped.
  - Cuts NEVER land off-grid: sparse passages hold; busy passages burst
    (floor 0.13s ~= 4 frames, keep-the-stronger merge below that).
  - All boundaries quantized to exact 30fps frame indices (zero drift).
  - Top-quartile onsets get a punch-in accent (subtle zoom) on the new shot.
  - Segment picking rotates a footage pool, avoiding the same source
    back-to-back, optionally restricted to accepted shots from a
    shot_map.json produced by scan_shot_quality.py (recommended — needs
    ~60+ usable shots for a dense high-energy window).

Usage:
  build_onset_cut.py --config job.json [--shot-map assets/sourced_footage/shot_map.json]

job.json:
  {
    "slug": "my_edit_01",
    "audio": "path/to/song.wav",
    "window": [81.92, 103.92],
    "hook_lines": ["line one", "line two"],
    "title": "song title",
    "artist": "artist name",
    "footage_files": ["path/to/clip1.mp4", "path/to/clip2.mp4", ...],
    "out_dir": "outputs/my_edit",
    "footage_credit": "optional footage credit line",
    "album_line": "optional album/context line"
  }

Needs a deep footage pool (60+ usable shots) for dense high-energy windows —
a shallow pool makes the rotation repeat visibly. Run scan_shot_quality.py
first to build the shot_map.json; without --shot-map, every file in
footage_files is treated as fully usable and random offsets are picked.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
from pathlib import Path

import numpy as np

FONT = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"

FPS = 30
FRAME = 1.0 / FPS
W, H, WIN, WIN_X, WIN_Y = 1080, 1920, 1000, 40, 470
MIN_GAP = 0.13            # perceptual floor between cuts (~4 frames)
ONSET_DELTA = 0.02        # librosa onset sensitivity (low = catch everything)


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def onset_grid(audio: Path, a: float, b: float):
    import librosa
    y, sr = librosa.load(str(audio), sr=22050, mono=True)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    tt = librosa.times_like(env, sr=sr, hop_length=512)
    onsets = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=512,
                                        backtrack=False, delta=ONSET_DELTA, units="time")
    pts = [(t, float(np.interp(t, tt, env))) for t in onsets if a <= t <= b]
    # merge under the perceptual floor, keeping the stronger onset
    kept = []
    for t, s in pts:
        if kept and t - kept[-1][0] < MIN_GAP:
            if s > kept[-1][1]:
                kept[-1] = (t, s)
        else:
            kept.append((t, s))
    # quantize to frame indices relative to window start; dedupe
    frames = sorted({int(round((t - a) / FRAME)) for t, _ in kept if t - a >= 0})
    if not frames or frames[0] != 0:
        frames.insert(0, 0)
    strengths = {}
    for t, s in kept:
        strengths[int(round((t - a) / FRAME))] = s
    total_frames = int(round((b - a) / FRAME))
    frames = [f for f in frames if f < total_frames - 2]
    bounds = frames + [total_frames]
    segs = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    thr = np.percentile(list(strengths.values()), 75) if strengths else 0
    return segs, strengths, thr


def shot_pool(files, shots):
    pool = []
    for f in files:
        info = shots.get(str(f))
        if info and info.get("accepted"):
            for s in info["accepted"]:
                if s["end"] - s["start"] >= 0.45:
                    pool.append((Path(f), s))
        else:
            pool.append((Path(f), None))   # unscanned: random offsets
    return pool


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--shot-map", type=Path, default=None,
                    help="shot_map.json from scan_shot_quality.py (optional)")
    args = ap.parse_args()
    job = json.loads(args.config.read_text())
    a, b = job["window"]
    out_dir = Path(job["out_dir"])
    work = out_dir / "work_onset" / job["slug"]
    segdir = work / "segments"
    segdir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(job["slug"] + "-onset-v2")

    shots = json.loads(args.shot_map.read_text()) if args.shot_map else {}

    segs, strengths, thr = onset_grid(Path(job["audio"]), a, b)
    print(f"{len(segs)} segments, avg {np.mean([ (e-s)*FRAME for s,e in segs]):.3f}s")

    pool = shot_pool(job["footage_files"], shots)
    if len(pool) < 4:
        raise SystemExit("pool too shallow for rapid cutting")
    rng.shuffle(pool)
    pi = 0
    last_file = None
    timeline = []
    for i, (f0, f1) in enumerate(segs):
        dur = (f1 - f0) * FRAME
        # rotate pool; avoid same file back-to-back when possible
        for attempt in range(len(pool)):
            cand_file, cand_shot = pool[(pi + attempt) % len(pool)]
            if cand_file != last_file or len(pool) == 1:
                pi = (pi + attempt + 1) % len(pool)
                break
        clip, shot = cand_file, cand_shot
        last_file = clip
        if shot:
            smax = max(shot["start"], shot["end"] - dur - 0.1)
            start = rng.uniform(shot["start"], smax) if smax > shot["start"] else shot["start"]
        else:
            start = rng.uniform(1.0, 30.0)
        accent = strengths.get(f0, 0) >= thr
        zoom = "scale=1100:1100,crop=1000:1000" if accent else f"scale={WIN}:{WIN}"
        vf = (f"crop='min(iw,ih)':'min(iw,ih)',{zoom},"
              f"eq=contrast=1.07:saturation=1.12:brightness=0.004,fps={FPS},setsar=1")
        seg = segdir / f"seg_{i:03d}.mp4"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-ss", f"{start:.3f}", "-t", f"{dur + 0.5:.3f}", "-i", str(clip), "-an",
             "-vf", vf + ",setpts=PTS-STARTPTS", "-frames:v", str(f1 - f0),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-threads", "2", str(seg)])
        timeline.append({"i": i, "t": round(f0 * FRAME, 3), "dur": round(dur, 3),
                         "src": clip.name, "accent": bool(accent)})

    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{(segdir / f'seg_{i:03d}.mp4').resolve()}'\n"
                              for i in range(len(segs))))
    silent = work / "silent.mp4"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(concat), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", str(silent)])
    aud = work / "audio.wav"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", job["audio"],
         "-af", f"afade=t=in:st=0:d=0.05,afade=t=out:st={b - a - 0.25:.3f}:d=0.25", str(aud)])

    draw = [f"pad={W}:{H}:{WIN_X}:{WIN_Y}:color=black"]
    hook = job["hook_lines"]
    hs = 52
    first_y = (WIN_Y - len(hook) * (hs + 18)) // 2 + 40
    specs = [(l, hs, "white", first_y + i * (hs + 18)) for i, l in enumerate(hook)]
    cy = WIN_Y + WIN + 60
    artist = job.get("artist", "artist")
    specs.append((f"song | {artist} ~ {job['title']}", 30, "white@0.85", cy))
    if job.get("album_line"):
        specs.append((job["album_line"], 26, "white@0.55", cy + 48))
    if job.get("footage_credit"):
        specs.append((job["footage_credit"], 22, "white@0.40", cy + 92))
    for ti, (line, size, color, y) in enumerate(specs):
        tf = work / f"t{ti}.txt"
        tf.write_text(line)
        draw.append(f"drawtext=fontfile='{FONT}':textfile='{tf}':fontsize={size}:"
                    f"fontcolor={color}:x=(w-text_w)/2:y={y}")
    final = out_dir / f"{job['slug']}_1080x1920.mp4"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(silent),
         "-i", str(aud), "-vf", ",".join(draw), "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(final)])
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(final),
         "-vf", "fps=2,scale=270:-1,tile=6x5", "-frames:v", "1",
         str(out_dir / f"{job['slug']}_contact.jpg")])
    (work / "timeline.json").write_text(json.dumps(timeline, indent=1))
    print(f"BUILT {final} ({len(segs)} cuts)")


if __name__ == "__main__":
    main()
