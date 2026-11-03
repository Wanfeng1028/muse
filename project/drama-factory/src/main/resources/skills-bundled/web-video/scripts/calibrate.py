#!/usr/bin/env python3
"""Measure the offset between the event-log clock and the video clock (sync flash).

USAGE
  calibrate.py RUN_DIR            # find the magenta sync flash in raw.webm, write events.json video_offset
  calibrate.py RUN_DIR --set 0.2  # set the offset by hand (seconds, video time = event time + offset)
  calibrate.py RUN_DIR --show     # print the current offset

record.py shows a full-screen magenta frame and logs a 'flash' event before the first step,
then calls this automatically. Every other script reads video_offset from events.json only
(Hard rule 4: one clock, one offset, applied in one place).
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import load_json, run_paths, save_json  # noqa: E402

SAMPLE_FPS = 100  # 10 ms resolution
W, H = 16, 9


def flash_video_time(video: pathlib.Path, search_s: float = 8.0) -> float | None:
    """Time (s) of the first mostly-magenta frame in the first search_s seconds, or None."""
    cmd = ["ffmpeg", "-v", "error", "-t", str(search_s), "-i", str(video),
           "-vf", f"fps={SAMPLE_FPS},scale={W}:{H}:flags=area,format=rgb24", "-f", "rawvideo", "-"]
    data = subprocess.run(cmd, capture_output=True, check=True).stdout
    fsz = W * H * 3
    for idx in range(len(data) // fsz):
        px = data[idx * fsz:(idx + 1) * fsz]
        n = W * H
        r = sum(px[0::3]) / n
        g = sum(px[1::3]) / n
        b = sum(px[2::3]) / n
        if r > 180 and b > 180 and g < 90:
            return idx / SAMPLE_FPS
    return None


def measure(run: pathlib.Path) -> tuple[float, str]:
    p = run_paths(run)
    ev = load_json(p["events"])
    flash = next((e for e in ev["events"] if e["kind"] == "flash"), None)
    if not flash:
        return 0.0, "none (no flash event; recorded with --no-flash)"
    vt = flash_video_time(p["raw"])
    if vt is None:
        return 0.0, "none (flash not found in video)"
    return round(vt - flash["t"], 3), f"flash (video {vt:.2f}s, event {flash['t']:.2f}s)"


def write(run: pathlib.Path, offset: float, method: str):
    p = run_paths(run)
    ev = load_json(p["events"])
    ev["video_offset"] = offset
    ev["offset_method"] = method
    save_json(p["events"], ev)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=pathlib.Path)
    ap.add_argument("--set", type=float, help="set offset manually (seconds)")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    if a.show:
        ev = load_json(run_paths(a.run)["events"])
        print(f"video_offset={ev.get('video_offset')} method={ev.get('offset_method')}")
        return
    if a.set is not None:
        write(a.run, a.set, "manual")
        print(f"video_offset={a.set} (manual)")
        return
    off, method = measure(a.run)
    write(a.run, off, method)
    print(f"video_offset={off} method={method}")
    if method.startswith("none"):
        print("warning: offset unknown; zoom and cuts may be off by ~0.2 s. "
              "Check a click frame in verify/ and use --set.", file=sys.stderr)


if __name__ == "__main__":
    main()
