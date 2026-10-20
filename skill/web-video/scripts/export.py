#!/usr/bin/env python3
"""Size-targeted final encode (H.264 yuv420p + AAC, faststart), optional GIF.

USAGE
  export.py IN.mp4 OUT.mp4 [--max-mb 9] [--height 720] [--gif OUT.gif] [--gif-width 800]

Encodes with CRF 26; if the file is over --max-mb, re-encodes 2-pass at the bitrate that fits (floor 150 kb/s).
GitHub allows 10 MB (free) / 100 MB (paid) videos, so the default target is 9 MB.
GIF only when asked: it is 2-5x larger than the MP4.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import die, need, probe_summary, run_ffmpeg  # noqa: E402

MB = 1024 * 1024


def encode(inp: pathlib.Path, out: pathlib.Path, max_mb: float, height: int) -> int:
    vf = f"scale=-2:'min({height},ih)':flags=lanczos,format=yuv420p"
    has_audio = bool(probe_summary(inp)["audio_codec"])
    audio = ["-c:a", "aac", "-b:a", "128k"] if has_audio else ["-an"]
    run_ffmpeg(["-i", str(inp), "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "26",
                "-pix_fmt", "yuv420p", *audio, "-movflags", "+faststart", str(out)])
    size = out.stat().st_size
    if size > max_mb * MB:
        dur = probe_summary(inp)["duration"]
        abr = 96 if has_audio else 0
        vbr = max(150, int(max_mb * 8192 * 0.93 / dur) - abr)
        print(f"CRF 26 gave {size / MB:.2f} MB > {max_mb} MB; 2-pass at {vbr}k video", file=sys.stderr)
        audio = ["-c:a", "aac", "-b:a", "96k"] if has_audio else ["-an"]
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "pass")
            run_ffmpeg(["-i", str(inp), "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-b:v", f"{vbr}k",
                        "-pass", "1", "-passlogfile", log, "-an", "-f", "mp4", os.devnull])
            run_ffmpeg(["-i", str(inp), "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-b:v", f"{vbr}k",
                        "-pass", "2", "-passlogfile", log, "-pix_fmt", "yuv420p", *audio,
                        "-movflags", "+faststart", str(out)])
        size = out.stat().st_size
    print(f"{out}: {size / MB:.2f} MB (target <= {max_mb} MB)")
    if size > max_mb * MB:
        print("warning: still over the target. Use --height 540, shorten the video, or upload elsewhere "
              "and link it.", file=sys.stderr)
    return size


def gif(src: pathlib.Path, out: pathlib.Path, width: int):
    run_ffmpeg(["-i", str(src), "-filter_complex",
                f"fps=10,scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];"
                "[b][p]paletteuse=dither=bayer:bayer_scale=4", str(out)])
    print(f"{out}: {out.stat().st_size / MB:.2f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inp", type=pathlib.Path)
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--max-mb", type=float, default=9)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--gif", type=pathlib.Path)
    ap.add_argument("--gif-width", type=int, default=800)
    a = ap.parse_args()
    need("ffmpeg")
    if not a.inp.exists():
        die(f"no such file: {a.inp}")
    encode(a.inp, a.out, a.max_mb, a.height)
    if a.gif:
        gif(a.out, a.gif, a.gif_width)


if __name__ == "__main__":
    main()
