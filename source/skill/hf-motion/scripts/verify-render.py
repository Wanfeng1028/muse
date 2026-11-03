#!/usr/bin/env python3
"""Post-render gate for a hf-motion MP4: container, audio peak, kick grid.

    python3 verify-render.py renders/video.mp4 --duration 15 --bpm 120
    python3 verify-render.py renders/video.mp4 --duration 6 --width 1080 --height 830

Pass exactly the scaffold's `verify-render args:` line. Without --bpm (a
recipe with no music bed) only check 1 runs, minus the audio stream.

Checks (each prints [OK] / [FAIL]; exit 1 on any FAIL):
  1. ffprobe: one h264 video stream WxH (default 1920x1080) @ 30 fps, one aac audio stream,
     container duration == --duration (+-0.05 s).
  2. audio peak: max sample between -6 dBFS and -0.1 dBFS (not silent, not clipped).
  3. kick grid: low-band (<150 Hz) onset on at least 80 % of beats k*60/bpm
     (the recipe drops one kick before the finale on purpose).
Needs ffmpeg/ffprobe and numpy.
"""
import argparse
import json
import subprocess
import sys

import numpy as np

SR = 22050


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mp4")
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--bpm", type=float, help="omit for a recipe with no music bed")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", default="30/1")
    a = ap.parse_args()
    fails = 0

    def report(ok, msg):
        nonlocal fails
        print(("[OK]   " if ok else "[FAIL] ") + msg)
        fails += 0 if ok else 1

    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", a.mp4],
        check=True, capture_output=True, text=True).stdout)
    v = [s for s in probe["streams"] if s["codec_type"] == "video"]
    au = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    dur = float(probe["format"]["duration"])
    report(len(v) == 1 and v[0]["codec_name"] == "h264" and v[0]["width"] == a.width
           and v[0]["height"] == a.height and v[0]["r_frame_rate"] == a.fps,
           f"video {v[0]['codec_name'] if v else '-'} {v[0].get('width') if v else '-'}x"
           f"{v[0].get('height') if v else '-'} @ {v[0].get('r_frame_rate') if v else '-'}")
    report(abs(dur - a.duration) <= 0.05, f"duration {dur:.3f}s (want {a.duration}s)")
    if a.bpm is None:
        print("[SKIP] audio: no --bpm, recipe has no music bed")
        sys.exit(1 if fails else 0)
    report(len(au) == 1 and au[0]["codec_name"] == "aac", f"audio {au[0]['codec_name'] if au else 'missing'}")

    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", a.mp4, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        check=True, capture_output=True).stdout
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768
    peak_db = 20 * np.log10(max(np.max(np.abs(x)), 1e-9))
    report(-6.0 <= peak_db <= -0.1, f"audio peak {peak_db:.1f} dBFS (want -6..-0.1)")

    # one-pole low-pass at 150 Hz via exponential smoothing, then onset ratio per beat
    alpha = 1 - np.exp(-2 * np.pi * 150 / SR)
    lp = np.empty_like(x)
    acc = 0.0
    for i, s in enumerate(x):
        acc += alpha * (s - acc)
        lp[i] = acc
    w = int(0.03 * SR)
    beat = 60 / a.bpm

    def onset_median(offset):  # median low-band energy jump at (k + offset) beats
        r = []
        for k in range(int(a.duration / beat)):
            c = int(round((k + offset) * beat * SR))
            if w <= c <= len(lp) - w:
                r.append(np.sqrt(np.mean(lp[c:c + w] ** 2)) / (np.sqrt(np.mean(lp[c - w:c] ** 2)) + 1e-9))
        return float(np.median(r)) if r else 0.0

    # Measured on the reference renders: on-beat median ~45-50, half-beat (bass 8ths) ~1.4-2.
    on, half = onset_median(0), onset_median(0.5)
    report(on >= 10 and on >= 5 * half,
           f"kick grid: on-beat onset median {on:.1f} vs half-beat {half:.1f} (want >=10 and >=5x)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
