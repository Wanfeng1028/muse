#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2"]
# ///
"""Automatic scan of a rendered video: pops, one-frame flashes, frozen spans, black frames, loop seam, plus a spec report.

Inputs: a video file. Output: a text report on stdout and in out/review/qa/<name>.qa.txt (+ .qa.json with --json).
Exit code 1 when any check fails (warnings fail too with --strict). Intentional hard cuts flag as pops: pass them
with --cuts so they are listed as expected. A poster on frame 0 flags too: pass --ignore 0.
Example: qa_video.py out/final/film-16x9.mp4 --ignore 0 --cuts 12.4,30.0 --expect-duration 73 --final-hold 1.5 --json
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from _qa_video_spec import Check, resolve_binary, spec_checks
from _qa_video_motion import MotionSettings, decode_gray_frames, motion_checks


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--fps", type=float, help="expected fps (default: read from the file, checked if given)")
    parser.add_argument("--cuts", default="", help="intentional hard cuts in seconds, comma separated (±1 frame)")
    parser.add_argument("--beats", help="BPM:OFFSET beat grid; events near a beat are labelled 'on beat'")
    parser.add_argument("--beat-tolerance", type=int, default=2, help="frames either side of a beat (default 2)")
    parser.add_argument("--ignore", default="", help="frames or frame ranges to whitelist, e.g. 0,120-150")
    parser.add_argument("--expect-duration", type=float, help="expected duration in seconds")
    parser.add_argument("--duration-tolerance", type=float, help="seconds (default: one frame + 0.05)")
    parser.add_argument("--final-hold", type=float, default=0.0, help="seconds of declared frozen hold at the end")
    parser.add_argument("--freeze-threshold", type=float, default=0.02, help="mean abs diff counted as frozen")
    parser.add_argument("--min-freeze", type=float, default=1.0, help="seconds of no change that count as a freeze")
    parser.add_argument("--pop-ratio", type=float, default=3.0, help="spike must exceed this times both neighbours")
    parser.add_argument("--pop-floor", type=float, default=2.0, help="minimum diff (0-255 grey) for pops and flashes")
    parser.add_argument("--black-level", type=float, default=24.0, help="mean grey below this with low spread is black")
    parser.add_argument("--loop", action="store_true", help="check the loop seam (last frame into frame 0)")
    parser.add_argument("--expect-codec", default="h264")
    parser.add_argument("--expect-pix-fmt", default="yuv420p")
    parser.add_argument("--expect-color", default="bt709", help="matrix/primaries/transfer tag; 'none' skips")
    parser.add_argument("--expect-audio", action="store_true", help="fail when there is no audio stream")
    parser.add_argument("--expect-audio-codec", default="aac")
    parser.add_argument("--expect-sample-rate", type=int, default=48000)
    parser.add_argument("--skip-motion", action="store_true", help="spec report only (fast)")
    parser.add_argument("--report-dir", type=Path, default=Path("out/review/qa"))
    parser.add_argument("--json", action="store_true", help="also write a JSON report")
    parser.add_argument("--strict", action="store_true", help="warnings also fail")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def parse_times(text: str) -> list[float]:
    return [float(value) for value in text.split(",") if value.strip()]


def beat_frames(text: str | None, fps: float, frame_count: int) -> set[int]:
    if not text:
        return set()
    bpm, _, offset = text.partition(":")
    period = 60 / float(bpm)
    time = float(offset or 0) % period
    frames = set()
    while time * fps < frame_count:
        frames.add(round(time * fps))
        time += period
    return frames


def parse_frame_set(text: str) -> set[int]:
    frames: set[int] = set()
    for token in (value.strip() for value in text.split(",")):
        if not token:
            continue
        if "-" in token:
            first, last = token.split("-", 1)
            frames.update(range(int(first), int(last) + 1))
        else:
            frames.add(int(token))
    return frames


def render_report(video: Path, checks: list[Check], strict: bool) -> tuple[str, bool]:
    failing_levels = {"FAIL", "WARN"} if strict else {"FAIL"}
    failed = any(check.level in failing_levels for check in checks)
    lines = [f"QA {video}"]
    for check in checks:
        lines.append(f"  [{check.level}] {check.name}: {check.summary}")
        lines.extend(f"      {detail}" for detail in check.details[:40])
        if len(check.details) > 40:
            lines.append(f"      ... {len(check.details) - 40} more")
    counts = {level: sum(check.level == level for check in checks) for level in ("PASS", "WARN", "FAIL", "INFO")}
    verdict = "FAIL" if failed else "PASS"
    lines.append(f"{verdict}: {counts['PASS']} pass, {counts['WARN']} warn, {counts['FAIL']} fail")
    return "\n".join(lines), failed


def write_reports(arguments: argparse.Namespace, text: str, checks: list[Check], failed: bool) -> None:
    arguments.report_dir.mkdir(parents=True, exist_ok=True)
    text_path = arguments.report_dir / f"{arguments.video.stem}.qa.txt"
    text_path.write_text(text + "\n")
    print(f"wrote {text_path}")
    if not arguments.json:
        return
    json_path = arguments.report_dir / f"{arguments.video.stem}.qa.json"
    payload = {"video": str(arguments.video), "passed": not failed, "checks": [check.as_dict() for check in checks]}
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {json_path}")


def main() -> None:
    arguments = parse_arguments()
    if not arguments.video.is_file():
        sys.exit(f"video not found: {arguments.video}")
    ffmpeg = resolve_binary("ffmpeg", arguments.verbose)
    ffprobe = resolve_binary("ffprobe", arguments.verbose)
    checks, probed_fps = spec_checks(arguments, ffprobe)
    if not arguments.skip_motion:
        fps = arguments.fps or probed_fps
        frames = decode_gray_frames(ffmpeg, arguments.video)
        settings = MotionSettings(
            fps=fps,
            cut_frames={round(time * fps) for time in parse_times(arguments.cuts)},
            beat_frames=beat_frames(arguments.beats, fps, len(frames)),
            beat_tolerance=arguments.beat_tolerance,
            ignored_frames=parse_frame_set(arguments.ignore),
            final_hold=arguments.final_hold,
            freeze_threshold=arguments.freeze_threshold,
            min_freeze=arguments.min_freeze,
            pop_ratio=arguments.pop_ratio,
            pop_floor=arguments.pop_floor,
            black_level=arguments.black_level,
            loop=arguments.loop,
        )
        checks += motion_checks(frames, settings)
    text, failed = render_report(arguments.video, checks, arguments.strict)
    print(text)
    write_reports(arguments, text, checks, failed)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
