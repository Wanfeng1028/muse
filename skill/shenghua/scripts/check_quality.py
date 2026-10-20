#!/usr/bin/env python3
"""Gate an encoded output on VMAF against the source video it was built from.

  check_quality.py <source-video> <output-mp4> [--min 95] [--sample-every 10]

Presenter and bookends modes re-encode the speaker's footage, so a silent quality loss
(wrong bitrate, wrong preset) would ship unnoticed; this compares the output against the
source frame-for-frame and fails below --min. A resolution mismatch is handled by scaling
the reference down to the output's size inside the filter graph (VMAF needs matching dims).
An ffmpeg build without libvmaf skips the gate instead of failing it.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

VMAF_SCORE = re.compile(r"VMAF score:\s*([0-9]+(?:\.[0-9]+)?)")


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "ffprobe failed")
    info = json.loads(out.stdout)
    stream = info["streams"][0]
    num, den = stream["r_frame_rate"].split("/")
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": float(num) / float(den),
        "duration": float(info["format"]["duration"]),
    }


def parse_vmaf_score(log_text):
    scores = VMAF_SCORE.findall(log_text)
    return float(scores[-1]) if scores else None


def needs_scaling(source, output):
    return (source["width"], source["height"]) != (output["width"], output["height"])


def passes(score, minimum):
    return score >= minimum


def has_libvmaf():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return "libvmaf" in out.stdout


def build_filter(source, output, sample_every):
    def chain(label_in, label_out, scale_to=None):
        steps = []
        if scale_to:
            steps.append(f"scale={scale_to[0]}:{scale_to[1]}")
        if sample_every > 1:
            steps.append(f"select=not(mod(n\\,{sample_every}))")
            steps.append("setpts=N/FRAME_RATE/TB")
        body = ",".join(steps) if steps else "null"
        return f"[{label_in}]{body}[{label_out}]"

    # libvmaf takes the distorted video first, the reference second
    dist = chain("0:v", "dist")
    ref = chain("1:v", "ref", scale_to=(output["width"], output["height"]) if needs_scaling(source, output) else None)
    return f"{dist};{ref};[dist][ref]libvmaf"


def fmt_fps(fps):
    return str(int(fps)) if fps == int(fps) else f"{fps:.2f}"


def describe(meta):
    return f"{meta['width']}x{meta['height']}@{fmt_fps(meta['fps'])}"


def main():
    parser = argparse.ArgumentParser(description="VMAF quality gate: output mp4 against its source video")
    parser.add_argument("source", help="the video the output was built from (reference)")
    parser.add_argument("output", help="the encoded output mp4 (distorted)")
    parser.add_argument("--min", type=float, default=95, help="minimum VMAF score (default 95)")
    parser.add_argument("--sample-every", type=int, default=10,
                        help="score every Nth frame for speed (default 10)")
    args = parser.parse_args()

    if args.sample_every < 1:
        print("--sample-every must be 1 or more", file=sys.stderr)
        print("Next: pass --sample-every 10, or 1 to score every frame", file=sys.stderr)
        return 1
    for label, path in (("source", args.source), ("output", args.output)):
        if not Path(path).is_file():
            print(f"No such {label} video: {path}", file=sys.stderr)
            print(f"Next: pass the {label} file as the {'first' if label == 'source' else 'second'} argument", file=sys.stderr)
            return 1

    if not has_libvmaf():
        print("VMAF unavailable: this ffmpeg build has no libvmaf; skipped")
        print("Next: install an ffmpeg build with libvmaf to gate encode quality, or ship unchecked")
        return 0

    try:
        source = probe(args.source)
        output = probe(args.output)
    except RuntimeError as exc:
        print(f"Could not probe a video: {exc}", file=sys.stderr)
        print("Next: check both files play with ffprobe, then re-run", file=sys.stderr)
        return 1

    run = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", args.output, "-i", args.source,
         "-lavfi", build_filter(source, output, args.sample_every), "-f", "null", "-"],
        capture_output=True, text=True)
    score = parse_vmaf_score(run.stderr)
    if score is None:
        print("ffmpeg produced no VMAF score", file=sys.stderr)
        tail = run.stderr.strip().splitlines()[-1] if run.stderr.strip() else "(no output)"
        print(f"Next: fix the ffmpeg error above ({tail}), then re-run", file=sys.stderr)
        return 1

    dims = f"source {describe(source)} → output {describe(output)} · {output['duration']:.1f}s"
    if passes(score, args.min):
        print(f"quality {score:.1f} VMAF (min {args.min:g}) · {dims}")
        print("Next: deliver.sh packages the master — the encode keeps the source's detail")
        return 0
    print(f"quality {score:.1f} VMAF is below the {args.min:g} minimum · {dims}", file=sys.stderr)
    print("Next: re-encode with a higher bitrate (lower CRF or raise -maxrate in mix-encode.sh), then re-check", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
