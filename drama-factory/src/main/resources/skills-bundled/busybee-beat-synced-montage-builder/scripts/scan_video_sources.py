#!/usr/bin/env python3
"""Create a lightweight motion/glow inventory for video source selection."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

try:
    import numpy as np
except ImportError as exc:
    raise SystemExit("This script requires numpy. Install it or use the workspace Python bundle if available.") from exc


VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def run_text(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def probe_duration(path: Path) -> float:
    out = run_text([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nk=1:nw=1",
        str(path),
    ])
    return float(out)


def scan_motion(path: Path, scan_fps: float, width: int, height: int, max_duration: float | None) -> list[dict]:
    cmd = ["ffmpeg", "-v", "error"]
    if max_duration:
        cmd += ["-t", f"{max_duration:.3f}"]
    cmd += [
        "-i",
        str(path),
        "-vf",
        f"fps={scan_fps},scale={width}:{height},format=rgb24",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    raw = subprocess.check_output(cmd)
    frame_size = width * height * 3
    n = len(raw) // frame_size
    if n < 2:
        return []

    frames = np.frombuffer(raw[: n * frame_size], dtype=np.uint8).reshape(n, height, width, 3).astype(np.float32)
    diff = np.mean(np.abs(np.diff(frames, axis=0)), axis=(1, 2, 3))
    current = frames[1:]
    brightness = np.mean(current, axis=(1, 2, 3))
    saturation = np.mean(np.max(current, axis=3) - np.min(current, axis=3), axis=(1, 2))
    valid = (brightness > 18) & (brightness < 222) & (saturation > 7)
    motion = np.where(valid, diff + 0.030 * saturation, (diff + 0.030 * saturation) * 0.12)
    glow = np.where(brightness > 25, diff + 0.065 * saturation + 0.012 * brightness, motion * 0.5)

    win = max(1, int(scan_fps * 1.25))
    kernel = np.ones(win) / win
    motion_smooth = np.convolve(motion, kernel, mode="same")
    glow_smooth = np.convolve(glow, kernel, mode="same")

    rows = []
    for i in range(len(motion_smooth)):
        rows.append({
            "time": round((i + 1) / scan_fps, 3),
            "motion_score": float(motion_smooth[i]),
            "glow_score": float(glow_smooth[i]),
            "brightness": float(brightness[min(i, len(brightness) - 1)]),
            "saturation": float(saturation[min(i, len(saturation) - 1)]),
        })
    return rows


def choose_starts(rows: list[dict], key: str, max_count: int, min_gap: float) -> list[dict]:
    ranked = sorted(rows, key=lambda r: r[key], reverse=True)
    chosen: list[dict] = []
    for row in ranked:
        if row["time"] < 0.6:
            continue
        if row["brightness"] > 224 or row["brightness"] < 14 or row["saturation"] < 7:
            continue
        if all(abs(row["time"] - old["time"]) >= min_gap for old in chosen):
            chosen.append(row)
        if len(chosen) >= max_count:
            break
    return chosen


def iter_videos(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(p for p in sorted(path.rglob("*")) if p.suffix.lower() in VIDEO_EXTS)
        elif path.suffix.lower() in VIDEO_EXTS:
            found.append(path)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Score video files for beat-synced montage source selection.")
    parser.add_argument("paths", nargs="+", type=Path, help="Video files or folders to scan")
    parser.add_argument("--out", type=Path, required=True, help="Output prefix or CSV path")
    parser.add_argument("--scan-fps", type=float, default=3.0)
    parser.add_argument("--width", type=int, default=160)
    parser.add_argument("--height", type=int, default=90)
    parser.add_argument("--max-duration", type=float, default=180.0)
    parser.add_argument("--starts", type=int, default=20)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    inventory = []
    for path in iter_videos(args.paths):
        rows = scan_motion(path, args.scan_fps, args.width, args.height, args.max_duration)
        motion_starts = choose_starts(rows, "motion_score", args.starts, 1.5)
        glow_starts = choose_starts(rows, "glow_score", args.starts, 1.2)
        inventory.append({
            "path": str(path),
            "duration": round(probe_duration(path), 3),
            "max_motion_score": round(max((r["motion_score"] for r in rows), default=0.0), 3),
            "max_glow_score": round(max((r["glow_score"] for r in rows), default=0.0), 3),
            "motion_starts": [r["time"] for r in motion_starts],
            "glow_starts": [r["time"] for r in glow_starts],
        })

    csv_path = args.out if args.out.suffix == ".csv" else args.out.with_suffix(".csv")
    json_path = args.out.with_suffix(".json")
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "duration", "max_motion_score", "max_glow_score", "motion_starts", "glow_starts"])
        writer.writeheader()
        for row in inventory:
            writer.writerow({**row, "motion_starts": "|".join(map(str, row["motion_starts"])), "glow_starts": "|".join(map(str, row["glow_starts"]))})
    json_path.write_text(json.dumps({"videos": inventory}, indent=2))
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
