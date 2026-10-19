#!/usr/bin/env python3
"""Audit a rendered video edit and optional timeline CSV."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
from collections import Counter
from pathlib import Path


def run_json(cmd: list[str]) -> dict:
    return json.loads(subprocess.check_output(cmd, text=True))


def probe(path: Path) -> dict:
    data = run_json([
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ])
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), {})
    audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), {})
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    num, den = [float(x) for x in rate.split("/")]
    fps = num / den if den else 0.0
    return {
        "duration": float(data.get("format", {}).get("duration", 0.0)),
        "format": data.get("format", {}).get("format_name", ""),
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "fps": fps,
        "video_codec": video.get("codec_name", ""),
        "has_audio": bool(audio),
        "audio_codec": audio.get("codec_name", ""),
    }


def read_timeline(path: Path) -> dict:
    rows = list(csv.DictReader(path.open()))
    durations = [float(r["duration"]) for r in rows if r.get("duration")]
    source_key = "source_tag" if rows and "source_tag" in rows[0] else "source"
    kind_key = "kind" if rows and "kind" in rows[0] else "category"
    return {
        "segments": len(rows),
        "avg_segment_duration": statistics.mean(durations) if durations else 0.0,
        "min_segment_duration": min(durations) if durations else 0.0,
        "max_segment_duration": max(durations) if durations else 0.0,
        "source_mix": dict(Counter(r.get(source_key, "") for r in rows if r.get(source_key))),
        "kind_mix": dict(Counter(r.get(kind_key, "") for r in rows if r.get(kind_key))),
    }


def make_contact_sheet(video: Path, out: Path, vertical: bool) -> None:
    scale = "270:480" if vertical else "480:270"
    tile = "4x4"
    subprocess.run([
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(video),
        "-vf",
        f"fps=1/4,scale={scale},tile={tile}",
        "-frames:v",
        "1",
        str(out),
    ], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="QA a final video edit.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--timeline", type=Path)
    parser.add_argument("--contact-sheet", type=Path)
    parser.add_argument("--make-contact-sheet", action="store_true")
    parser.add_argument("--out", type=Path, required=True, help="Output prefix")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    specs = probe(args.video)
    vertical = specs["height"] > specs["width"]
    contact_sheet = args.contact_sheet
    if args.make_contact_sheet and not contact_sheet:
        contact_sheet = args.out.with_name(args.out.name + "_contact_sheet.jpg")
        make_contact_sheet(args.video, contact_sheet, vertical)

    timeline = read_timeline(args.timeline) if args.timeline else None
    flags = []
    if not specs["has_audio"]:
        flags.append("No audio stream found.")
    if specs["fps"] < 29.0:
        flags.append("Frame rate is below 30fps target.")
    if vertical and (specs["width"], specs["height"]) != (1080, 1920):
        flags.append("Vertical render is not 1080x1920.")
    if not vertical and (specs["width"], specs["height"]) != (1920, 1080):
        flags.append("Landscape render is not 1920x1080.")
    if timeline and specs["duration"] >= 30 and timeline["avg_segment_duration"] > 0.75:
        flags.append("Average segment duration is loose for a dense high-energy montage.")

    report = {
        "video": str(args.video),
        "specs": specs,
        "timeline": timeline,
        "contact_sheet": str(contact_sheet) if contact_sheet else None,
        "flags": flags,
    }
    json_path = args.out.with_suffix(".json")
    md_path = args.out.with_suffix(".md")
    json_path.write_text(json.dumps(report, indent=2))
    lines = [
        "# Video Edit QA",
        "",
        f"- Video: `{args.video}`",
        f"- Duration: `{specs['duration']:.2f}s`",
        f"- Size/FPS: `{specs['width']}x{specs['height']} @ {specs['fps']:.2f}fps`",
        f"- Video codec: `{specs['video_codec']}`",
        f"- Audio: `{'yes' if specs['has_audio'] else 'no'}` {specs['audio_codec']}",
    ]
    if timeline:
        lines += [
            f"- Segments: `{timeline['segments']}`",
            f"- Average segment: `{timeline['avg_segment_duration']:.3f}s`",
            f"- Source mix: `{timeline['source_mix']}`",
            f"- Kind mix: `{timeline['kind_mix']}`",
        ]
    if contact_sheet:
        lines.append(f"- Contact sheet: `{contact_sheet}`")
    lines += ["", "## Flags"]
    lines += [f"- {flag}" for flag in flags] if flags else ["- No automated flags. Still review the contact sheet or final render by eye."]
    md_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
