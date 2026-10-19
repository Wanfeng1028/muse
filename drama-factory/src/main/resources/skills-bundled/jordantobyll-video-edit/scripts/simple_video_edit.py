#!/usr/bin/env python3
"""Lightweight FFmpeg front-end for basic video edits.

Supported operations:
  trim         - keep only [start, end]
  concat       - join multiple files end-to-end
  speed        - change playback rate (video + audio)
  trim-concat  - trim several spans out of one file and join them

No machine-learning decisions are made here; the tool is intentionally
procedural so it can be driven from a script or from a higher-level skill.
"""

import argparse
import json
import os
import subprocess
import sys


def _video_encoder_flags():
    if sys.platform == "darwin":
        return ["-c:v", "h264_videotoolbox", "-b:v", "8M"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]


def _audio_flags():
    return ["-c:a", "aac", "-b:a", "320k"]


def _run(cmd, tolerate_hw_failure=True):
    """Run an FFmpeg command, retrying with software encoder if needed."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return

    if tolerate_hw_failure and "h264_videotoolbox" in cmd:
        print("hardware encoder failed; retrying with libx264", file=sys.stderr)
        # Swap the hardware codec for libx264, drop -b:v, add -crf 18
        new_cmd = []
        skip_next = False
        for tok in cmd:
            if skip_next:
                skip_next = False
                continue
            if tok == "h264_videotoolbox":
                new_cmd += ["libx264", "-preset", "fast", "-crf", "18"]
            elif tok == "-b:v":
                skip_next = True
            else:
                new_cmd.append(tok)
        proc = subprocess.run(new_cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            return

    print(proc.stderr[-2000:], file=sys.stderr)
    raise RuntimeError("ffmpeg failed")


def _probe_duration(path):
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", path,
        ],
        capture_output=True, text=True,
    )
    return float(json.loads(proc.stdout)["format"]["duration"])


def op_trim(input_path, output_path, start, end):
    cmd = (
        ["ffmpeg", "-y", "-ss", str(start), "-i", input_path,
         "-t", str(end - start)]
        + _video_encoder_flags()
        + _audio_flags()
        + ["-loglevel", "error", output_path]
    )
    _run(cmd)


def op_concat(inputs, output_path):
    """Concat via the demuxer when possible, re-encoding otherwise."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        for p in inputs:
            fh.write(f"file '{os.path.abspath(p)}'\n")
        list_path = fh.name

    try:
        # First try stream-copy; if the inputs are heterogeneous, fall back.
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_path, "-c", "copy",
            "-loglevel", "error", output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            return

        # Fallback: filter-based re-encode
        n = len(inputs)
        filter_parts = []
        for i in range(n):
            filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")
            filter_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
        joined = "".join(f"[v{i}][a{i}]" for i in range(n))
        graph = ";".join(filter_parts) + f";{joined}concat=n={n}:v=1:a=1[outv][outa]"

        cmd = ["ffmpeg", "-y"]
        for p in inputs:
            cmd += ["-i", p]
        cmd += [
            "-filter_complex", graph,
            "-map", "[outv]", "-map", "[outa]",
        ] + _video_encoder_flags() + _audio_flags() + [
            "-loglevel", "error", output_path,
        ]
        _run(cmd)
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)


def op_speed(input_path, output_path, rate):
    if rate <= 0:
        raise ValueError("--rate must be positive")
    # atempo only handles 0.5–2.0; chain as needed.
    atempo = []
    remaining = rate
    while remaining > 2.0:
        atempo.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        atempo.append("atempo=0.5")
        remaining /= 0.5
    atempo.append(f"atempo={remaining:.6f}")

    graph = (
        f"[0:v]setpts=PTS/{rate}[outv];"
        f"[0:a]{','.join(atempo)}[outa]"
    )
    cmd = (
        ["ffmpeg", "-y", "-i", input_path,
         "-filter_complex", graph,
         "-map", "[outv]", "-map", "[outa]"]
        + _video_encoder_flags()
        + _audio_flags()
        + ["-loglevel", "error", output_path]
    )
    _run(cmd)


def op_trim_concat(input_path, output_path, segments):
    """segments is a list of [start, end] pairs (seconds)."""
    n = len(segments)
    if n == 0:
        raise ValueError("no segments provided")

    parts = []
    for i, (s, e) in enumerate(segments):
        parts.append(
            f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]"
        )
    for i, (s, e) in enumerate(segments):
        parts.append(
            f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]"
        )
    joined = "".join(f"[v{i}][a{i}]" for i in range(n))
    parts.append(f"{joined}concat=n={n}:v=1:a=1[outv][outa]")
    graph = ";".join(parts)

    cmd = (
        ["ffmpeg", "-y", "-i", input_path,
         "-filter_complex", graph,
         "-map", "[outv]", "-map", "[outa]"]
        + _video_encoder_flags()
        + _audio_flags()
        + ["-loglevel", "error", output_path]
    )
    _run(cmd)


def main():
    ap = argparse.ArgumentParser(description="Simple FFmpeg edit helper")
    ap.add_argument("--op", required=True,
                    choices=["trim", "concat", "speed", "trim-concat"])
    ap.add_argument("--input", action="append", default=[],
                    help="Input file(s). Repeat for concat.")
    ap.add_argument("--output", required=True)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--segments", type=str, default=None,
                    help="JSON list of [start, end] pairs for trim-concat")
    args = ap.parse_args()

    if args.op == "trim":
        if not args.input:
            raise SystemExit("--input required")
        end = args.end if args.end is not None else _probe_duration(args.input[0])
        op_trim(args.input[0], args.output, args.start, end)

    elif args.op == "concat":
        if len(args.input) < 2:
            raise SystemExit("--input must be given at least twice for concat")
        op_concat(args.input, args.output)

    elif args.op == "speed":
        if not args.input:
            raise SystemExit("--input required")
        op_speed(args.input[0], args.output, args.rate)

    elif args.op == "trim-concat":
        if not args.input:
            raise SystemExit("--input required")
        if not args.segments:
            raise SystemExit("--segments required for trim-concat")
        segments = json.loads(args.segments)
        op_trim_concat(args.input[0], args.output, segments)


if __name__ == "__main__":
    main()
