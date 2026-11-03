import argparse
import math
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Tile sampled video frames into PNG contact sheets without drawtext.")
    parser.add_argument("video", type=Path)
    parser.add_argument("outDir", type=Path)
    parser.add_argument("--fps", type=float, default=2)
    parser.add_argument("--cols", type=int, default=6)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--width", type=int, default=480)
    args = parser.parse_args()
    if args.fps <= 0 or not math.isfinite(args.fps) or min(args.cols, args.rows, args.width) <= 0:
        parser.error("fps, cols, rows, and width must be positive.")
    if not args.video.is_file():
        parser.error(f"Video not found: {args.video}")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(args.video)], capture_output=True, text=True, check=True,
    )
    source_w, source_h = map(int, probe.stdout.strip().split(",")[:2])
    height = max(1, round(args.width * source_h / source_w))
    size = args.width * height * 3
    args.outDir.mkdir(parents=True, exist_ok=True)
    count = 0
    sheets = 0
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-i", str(args.video), "-map", "0:v:0", "-vf",
             f"fps={args.fps},scale={args.width}:{height}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, stderr=errors,
        )
        try:
            while True:
                canvas = np.zeros((height * args.rows, args.width * args.cols, 3), dtype=np.uint8)
                first = count
                for tile in range(args.cols * args.rows):
                    raw = process.stdout.read(size)
                    if not raw:
                        break
                    if len(raw) != size:
                        raise RuntimeError("ffmpeg returned an incomplete frame.")
                    row, col = divmod(tile, args.cols)
                    canvas[row * height:(row + 1) * height, col * args.width:(col + 1) * args.width] = \
                        np.frombuffer(raw, np.uint8).reshape(height, args.width, 3)
                    count += 1
                if count == first:
                    break
                sheets += 1
                output = args.outDir / f"sheet-{sheets:03d}.png"
                subprocess.run(
                    ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                     f"{args.width * args.cols}x{height * args.rows}", "-i", "-", "-frames:v", "1", str(output)],
                    input=canvas.tobytes(), capture_output=True, check=True,
                )
                print(f"{output.resolve()}  {first / args.fps:.3f}s..{(count - 1) / args.fps:.3f}s  ({count - first} frames)")
            if process.wait() != 0:
                errors.seek(0)
                raise RuntimeError(errors.read().decode(errors="replace").strip())
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait()
    if not count:
        raise RuntimeError("The video decoded no frames.")
    print(f"{count} sampled frames, {sheets} sheets")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
