"""Measure the audio viewers actually hear: decode a finished video or audio file and report levels.

Usage: python audio_check.py FILE [--ceiling -0.5] [--project film/]
Prints peak dBFS, RMS dBFS, samples at or over 0 dBFS, and RMS per second.
Exits with code 1 when the decoded peak is above the ceiling.
"""
import argparse, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _media import decode_audio, set_project  # noqa: E402


def db(x):
    return 20 * np.log10(max(float(x), 1e-12))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--ceiling", type=float, default=-0.5)
    ap.add_argument("--project", default=None)
    a = ap.parse_args()
    set_project(a.project)
    sr = 48000
    x = decode_audio(a.file, sr, 2)
    if not len(x):
        sys.exit("no audio stream")
    peak = np.abs(x).max()
    rms = np.sqrt((x ** 2).mean())
    over = int((np.abs(x) >= 0.99997).sum())
    print(f"duration {len(x) / sr:.2f}s  peak {db(peak):.2f} dBFS  rms {db(rms):.1f} dBFS  samples>=0dBFS {over}")
    per = [db(np.sqrt((x[i:i + sr] ** 2).mean())) for i in range(0, len(x), sr)]
    print("rms per second:", " ".join(f"{v:.0f}" for v in per))
    if db(peak) > a.ceiling:
        print(f"FAIL: peak above {a.ceiling} dBFS. Master the source WAV to -4 dBFS and remux.")
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()

