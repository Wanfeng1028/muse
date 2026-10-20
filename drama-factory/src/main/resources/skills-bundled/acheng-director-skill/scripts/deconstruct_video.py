#!/usr/bin/env python3
"""Extract timestamp-grounded frames; does not invent visual or audio observations."""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def extract(video, output, start, end, sample_fps=3, every_frame=False):
    video, output = Path(video).resolve(), Path(output)
    if not video.is_file():
        raise ValueError("Input video does not exist")
    if not 0 <= start < end or sample_fps <= 0 or end - start > 600:
        raise ValueError("Require 0 <= start < end, positive sample rate, and a bounded interval <=600s")
    if output.exists():
        raise ValueError("Output exists; use a fresh evidence directory")
    for tool in ("ffprobe", "ffmpeg"):
        if not shutil.which(tool):
            raise ValueError(f"Missing required tool: {tool}")
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_format", "-show_frames", "-show_entries", "frame=best_effort_timestamp_time,key_frame:stream=width,height,r_frame_rate,avg_frame_rate,time_base:format=duration", "-of", "json", str(video)]
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
    probe = json.loads(result.stdout)
    duration = float(probe["format"]["duration"])
    if end > duration + 0.001:
        raise ValueError(f"Requested end {end} exceeds media duration {duration}")
    frames = [(i, float(f["best_effort_timestamp_time"])) for i, f in enumerate(probe["frames"]) if "best_effort_timestamp_time" in f]
    available = [(i, t) for i, t in frames if start <= t < end]
    if not available:
        raise ValueError("No frames in requested interval")
    if every_frame:
        chosen = available
    else:
        times = [t for _, t in available]
        indices = set()
        count = int((end - start) * sample_fps + 0.999999)
        for step in range(count):
            target = start + step / sample_fps
            pos = bisect.bisect_left(times, target)
            candidates = [x for x in (pos - 1, pos) if 0 <= x < len(times)]
            indices.add(min(candidates, key=lambda x: abs(times[x] - target)))
        chosen = [available[i] for i in sorted(indices)]
    if len(chosen) > 18000:
        raise ValueError("Too many frames; narrow the interval")
    output.mkdir(parents=True)
    # Select exact decoded frame indices, not rounded seek timestamps.
    selection = "+".join(f"eq(n\\,{i})" for i, _ in chosen)
    filter_file = output / "selection.txt"
    filter_file.write_text(f"select='{selection}'", encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-filter_script:v", str(filter_file),
                    "-fps_mode", "vfr", str(output / "frame-%06d.png")], check=True, timeout=240)
    paths = sorted(output.glob("frame-*.png"))
    if len(paths) != len(chosen):
        raise ValueError("Extracted frame count differs from selected source indices")
    records = [{"source_frame_index": index, "pts_seconds": t, "file": path.name,
                "observation": None, "inference": None} for (index, t), path in zip(chosen, paths)]
    with video.open("rb") as handle:
        source_hash = hashlib.file_digest(handle, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(handle.read()).hexdigest()
    evidence = {"source": str(video), "source_sha256": source_hash, "interval": [start, end],
                "sampling": "every-frame" if every_frame else sample_fps,
                "streams": probe["streams"], "frames": records, "audio_observed": False,
                "precision_note": "PTS/source-frame precision; sampling does not imply microsecond visual resolution"}
    (output / "frames.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--sample-fps", type=float, default=3)
    parser.add_argument("--every-frame", action="store_true")
    args = parser.parse_args()
    try:
        report = extract(args.video, args.out, args.start, args.end, args.sample_fps, args.every_frame)
        print(f"Extracted {len(report['frames'])} source-grounded frames; visual/audio interpretation remains unverified.")
        return 0
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
