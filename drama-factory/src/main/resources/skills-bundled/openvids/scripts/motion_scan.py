import argparse
from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Find near-static runs using 480x270 grayscale frames and a codec-noise threshold.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--max-static", type=int, default=12)
    parser.add_argument("--allow", default="", help="Inclusive absolute-frame ranges, for example 1369-1391,1429-1444.")
    args = parser.parse_args()
    if args.max_static < 0:
        parser.error("max-static must be nonnegative.")
    allowed = []
    for item in filter(None, args.allow.split(",")):
        try:
            first, last = map(int, item.split("-"))
            if first < 0 or last < first:
                raise ValueError()
            allowed.append((first, last))
        except ValueError:
            parser.error(f"Invalid allow range: {item}")
    if not args.video.is_file():
        parser.error(f"Video not found: {args.video}")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate",
         "-of", "default=noprint_wrappers=1:nokey=1", str(args.video)],
        capture_output=True, text=True, check=True,
    )
    fps = float(Fraction(probe.stdout.strip()))
    if fps <= 0:
        raise RuntimeError("Video has no positive average frame rate.")
    runs = []
    start = None
    previous = None
    count = 0
    size = 480 * 270
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-i", str(args.video), "-map", "0:v:0", "-vf", "scale=480:270",
             "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            stdout=subprocess.PIPE, stderr=errors,
        )
        try:
            while raw := process.stdout.read(size):
                if len(raw) != size:
                    raise RuntimeError("ffmpeg returned an incomplete frame.")
                current = np.frombuffer(raw, np.uint8).astype(np.int16)
                if previous is not None:
                    changed = int(np.count_nonzero(np.abs(current - previous) > 6))
                    if changed < 40:
                        if start is None:
                            start = count
                    elif start is not None:
                        runs.append((start, count - 1))
                        start = None
                previous = current
                count += 1
            if start is not None:
                runs.append((start, count - 1))
            if process.wait() != 0:
                errors.seek(0)
                raise RuntimeError(errors.read().decode(errors="replace").strip())
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait()
    if count < 2:
        raise RuntimeError("The video needs at least two decoded frames.")
    failures = 0
    print(f"{count} frames at {fps:g} fps; static means fewer than 40 pixels changing by more than 6/255")
    for first, last in runs:
        length = last - first + 1
        if length <= args.max_static:
            continue
        permitted = all(any(a <= frame <= b for a, b in allowed) for frame in range(first, last + 1))
        failures += not permitted
        print(f"frames {first}-{last}  {first / fps:.3f}s..{last / fps:.3f}s  ({length})  {'allowed' if permitted else 'FAIL'}")
    print(f"{failures} unallowed runs longer than {args.max_static} frames")
    return int(failures > 0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
