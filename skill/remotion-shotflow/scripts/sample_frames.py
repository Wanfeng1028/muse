#!/usr/bin/env python3
"""Sample local video by nearest decoded PTS; create labelled contact sheets."""
from __future__ import annotations

import argparse
import bisect
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class SamplingError(Exception):
    pass


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip()[-2400:]
        raise SamplingError(f"{Path(command[0]).name} failed ({result.returncode}): {detail}")
    return result.stdout


def finite(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be finite")
    return number


def integer_between(low: int, high: int):
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("must be an integer") from exc
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number
    return parse


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path, help="existing local media file")
    p.add_argument("--out", required=True, type=Path, help="new output directory; never overwrite")
    p.add_argument("--times", help="comma-separated seconds relative to container format.start_time")
    p.add_argument("--start", type=finite, help="range start, inclusive (seconds)")
    p.add_argument("--end", type=finite, help="range end, inclusive if it falls on a step")
    p.add_argument("--step", type=finite, help="positive interval (seconds)")
    p.add_argument("--max-samples", type=integer_between(1, 5000), default=240)
    p.add_argument("--per-page", type=integer_between(1, 100), default=24)
    p.add_argument("--columns", type=integer_between(1, 12), default=4)
    p.add_argument("--frame-width", type=integer_between(64, 4096), default=960)
    p.add_argument("--thumb-width", type=integer_between(120, 1000), default=320)
    p.add_argument("--thumb-height", type=integer_between(80, 1000), default=200)
    p.add_argument("--font", type=Path, help="optional TTF/OTF font for contact-sheet labels")
    return p


def targets_from_args(args, p) -> list[float]:
    ranges = (args.start, args.end, args.step)
    if args.times is not None:
        if any(v is not None for v in ranges):
            p.error("--times is mutually exclusive with --start/--end/--step")
        try:
            targets = [finite(token.strip()) for token in args.times.split(",")]
        except argparse.ArgumentTypeError as exc:
            p.error(f"invalid --times: {exc}")
    else:
        if any(v is None for v in ranges):
            p.error("provide --times OR all three of --start, --end, --step")
        if args.step <= 0:
            p.error("--step must be positive")
        if args.end < args.start:
            p.error("--end must be greater than or equal to --start")
        count = (args.end - args.start) / args.step
        if not math.isfinite(count) or count >= args.max_samples:
            p.error(f"range exceeds --max-samples {args.max_samples}; narrow it or raise the limit")
        targets = [args.start + i * args.step for i in range(math.floor(count + 1e-9) + 1)]
    if len(targets) > args.max_samples:
        p.error(f"{len(targets)} targets exceed --max-samples {args.max_samples}")
    if any(t < 0 for t in targets):
        p.error("sample times must be non-negative")
    return targets


def probe(source: Path) -> tuple[dict, list[float], dict, str]:
    raw = run([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-select_streams", "v:0", "-show_streams", "-show_frames", "-show_format",
        "-show_entries",
        "stream=index,codec_name,width,height,time_base,start_time,duration,r_frame_rate,avg_frame_rate:"
        "frame=best_effort_timestamp_time:format=start_time,duration", "-of", "json", str(source),
    ])
    data = json.loads(raw)
    if not data.get("streams"):
        raise SamplingError("input has no video stream")
    decoded = data.get("frames", [])
    if not decoded:
        raise SamplingError("video stream contains no decodable frames")
    times = []
    for index, frame in enumerate(decoded):
        try:
            pts = float(frame["best_effort_timestamp_time"])
        except (KeyError, ValueError, TypeError) as exc:
            raise SamplingError(f"decoded frame {index} has no usable best_effort_timestamp_time") from exc
        if not math.isfinite(pts):
            raise SamplingError(f"decoded frame {index} has a non-finite timestamp")
        if times and pts < times[-1]:
            raise SamplingError("decoded timestamps are not monotonic; cannot safely map frame indices")
        times.append(pts)
    return data["streams"][0], times, data.get("format", {}), raw


def nearest_index(times: list[float], pts: float) -> int:
    right = bisect.bisect_left(times, pts)
    candidates = {max(0, right - 1), min(len(times) - 1, right)}
    # Earlier decoded frame wins exact halfway ties.
    return min(candidates, key=lambda i: (abs(times[i] - pts), i))


def load_font(ImageFont, path: Path | None):
    if path is not None:
        try:
            return ImageFont.truetype(str(path), 16)
        except OSError as exc:
            raise SamplingError(f"cannot load --font {path}: {exc}") from exc
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, 16)
        except OSError:
            pass
    return ImageFont.load_default()


def make_sheets(stage: Path, samples: list[dict], args, Image, ImageDraw, ImageFont) -> list[str]:
    font = load_font(ImageFont, args.font)
    sheets = []
    label_height, pad = 48, 8
    cols = min(args.columns, args.per_page)
    tile_w, tile_h = args.thumb_width, args.thumb_height + label_height
    for offset in range(0, len(samples), args.per_page):
        page = samples[offset:offset + args.per_page]
        sheet = Image.new("RGB", (cols * tile_w, math.ceil(len(page) / cols) * tile_h), "#20242c")
        draw = ImageDraw.Draw(sheet)
        for position, sample in enumerate(page):
            x, y = (position % cols) * tile_w, (position // cols) * tile_h
            with Image.open(stage / sample["image"]) as frame:
                thumbnail = frame.convert("RGB")
                thumbnail.thumbnail((tile_w - 2 * pad, args.thumb_height - 2 * pad), Image.Resampling.LANCZOS)
                sheet.paste(thumbnail, (x + (tile_w - thumbnail.width) // 2,
                                       y + label_height + (args.thumb_height - thumbnail.height) // 2))
            draw.text((x + pad, y + 5), f"#{sample['sample_index_1']} target {sample['target_time_s']:.3f}s", font=font, fill="white")
            draw.text((x + pad, y + 25), f"PTS {sample['actual_pts_s']:.3f}s  n={sample['frame_index_0']}", font=font, fill="#a9c8e8")
        relative = f"contact-{offset // args.per_page + 1:03d}.jpg"
        sheet.save(stage / relative, quality=92)
        sheets.append(relative)
    return sheets


def sample(args, targets: list[float]) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise SamplingError("Pillow is unavailable in this Python runtime; choose an existing runtime with Pillow") from exc
    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            raise SamplingError(f"{binary} is not on PATH; no dependencies are installed automatically")
    source, destination = args.input.expanduser().resolve(), args.out.expanduser().resolve()
    if not source.is_file():
        raise SamplingError(f"input is not an existing local file: {source}")
    if destination.exists():
        raise SamplingError(f"output already exists; choose a new --out directory: {destination}")
    if args.font:
        args.font = args.font.expanduser().resolve()
    stream, timestamps, container, probe_json = probe(source)
    first_pts, last_pts = timestamps[0], timestamps[-1]
    try:
        origin = float(container["start_time"])
        if not math.isfinite(origin):
            raise ValueError("non-finite container start")
        origin_policy = "format.start_time"
    except (KeyError, ValueError, TypeError):
        origin, origin_policy = 0.0, "fallback_zero_missing_format_start_time"
    min_time, max_time = first_pts - origin, last_pts - origin
    if any(t < min_time - 1e-6 or t > max_time + 1e-6 for t in targets):
        bad = next(t for t in targets if t < min_time - 1e-6 or t > max_time + 1e-6)
        raise SamplingError(f"target {bad:g}s is outside the decoded video frame span [{min_time:.6f}, {max_time:.6f}]s; "
                            "the final frame PTS can precede container duration")
    selections = [nearest_index(timestamps, origin + t) for t in targets]
    unique = sorted(set(selections))
    files = {index: f"frames/frame-{index:08d}.jpg" for index in unique}
    samples = [{
        "sample_index_1": position + 1,
        "target_time_s": target,
        "target_pts_s": origin + target,
        "actual_pts_s": timestamps[index],
        "actual_time_s": timestamps[index] - origin,
        "error_s": timestamps[index] - origin - target,
        "frame_index_0": index,
        "image": files[index],
    } for position, (target, index) in enumerate(zip(targets, selections))]
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        (stage / "frames").mkdir()
        expression = "+".join(f"eq(n\\,{index})" for index in unique)
        # No input seeking or FPS conversion: n maps to ffprobe's decoded frame order.
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-protocol_whitelist", "file,pipe", "-i", str(source),
             "-map", "0:v:0", "-an", "-sn", "-dn", "-vf",
             f"select={expression},scale={args.frame_width}:-1",
             "-fps_mode", "passthrough", "-q:v", "2", str(stage / "frames" / "extract-%08d.jpg")])
        extracted = sorted((stage / "frames").glob("extract-*.jpg"))
        if len(extracted) != len(unique):
            raise SamplingError(f"decoded {len(extracted)} output frames, expected {len(unique)}; no manifest written")
        for index, extracted_file in zip(unique, extracted):
            with Image.open(extracted_file) as im:
                im.verify()
            extracted_file.rename(stage / files[index])
        sheets = make_sheets(stage, samples, args, Image, ImageDraw, ImageFont)
        manifest = {
            "schema_version": 1,
            "source": str(source),
            "stream": stream,
            "timestamp_basis": "target_time_s and actual_time_s are container-origin-relative; actual_pts_s is source best_effort_timestamp_time",
            "container": container,
            "timeline_origin_pts_s": origin,
            "origin_policy": origin_policy,
            "timing": {
                "time_origin": "seconds from container presentation start",
                "origin_basis": origin_policy,
                "presentation_start_pts_s": origin,
                "first_decoded_video_frame_pts_s": first_pts,
                "video_offset_s": first_pts - origin,
                "origin_verified": origin_policy == "format.start_time",
            },
            "selection": "nearest decoded frame, ties choose earlier frame; repeated selections share an image",
            "first_video_pts_s": first_pts,
            "last_video_pts_s": last_pts,
            "first_video_time_s": min_time,
            "last_video_time_s": max_time,
            "decoded_frame_count": len(timestamps),
            "sample_count": len(samples),
            "unique_frame_count": len(unique),
            "frame_width": args.frame_width,
            "samples": samples,
            "contact_sheets": sheets,
        }
        (stage / "probe.json").write_text(probe_json, encoding="utf-8")
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if destination.exists():
            raise SamplingError("output appeared during processing; refusing to replace it")
        stage.rename(destination)
        return destination / "manifest.json"
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> int:
    p = parser()
    args = p.parse_args()
    targets = targets_from_args(args, p)
    try:
        manifest = sample(args, targets)
    except (SamplingError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Created {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
