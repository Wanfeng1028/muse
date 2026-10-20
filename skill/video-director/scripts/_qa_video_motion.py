"""Helper module for qa_video.py (not a CLI): frame-difference scans for pops, flashes, freezes, black frames, loop seam.

Pop and flash math follows the howseen-ai motion-design render_template.py scan: frames at 180x180 grey,
mean absolute difference between neighbours on a 0-255 scale.
"""
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from _qa_video_spec import Check

SIZE = 180
CHUNK = 256


@dataclass
class MotionSettings:
    fps: float
    cut_frames: set[int]
    beat_frames: set[int]
    beat_tolerance: int
    ignored_frames: set[int]
    final_hold: float
    freeze_threshold: float
    min_freeze: float
    pop_ratio: float
    pop_floor: float
    black_level: float
    loop: bool


def decode_gray_frames(ffmpeg: str, video: Path) -> np.ndarray:
    result = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(video), "-an", "-vf", f"scale={SIZE}:{SIZE}:flags=area,format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True,
    )
    if result.returncode != 0:
        sys.exit(f"ffmpeg could not decode {video}: {result.stderr.decode()[-800:]}")
    return np.frombuffer(result.stdout, np.uint8).reshape(-1, SIZE, SIZE)


def mean_abs_diff(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    return np.abs(first.astype(np.int16) - second.astype(np.int16)).mean(axis=(-2, -1))


def neighbour_diffs(frames: np.ndarray, gap: int) -> np.ndarray:
    limit = len(frames) - gap
    parts = [mean_abs_diff(frames[start:min(start + CHUNK, limit)], frames[start + gap:min(start + CHUNK, limit) + gap])
             for start in range(0, limit, CHUNK)]
    return np.concatenate(parts) if parts else np.zeros(0)


def classify(frame: int, settings: MotionSettings) -> str:
    if frame in settings.ignored_frames or frame - 1 in settings.ignored_frames:
        return "ignored"
    if any(abs(frame - cut) <= 1 for cut in settings.cut_frames):
        return "expected cut"
    if any(abs(frame - beat) <= settings.beat_tolerance for beat in settings.beat_frames):
        return "on beat"
    return "unexplained"


def event_check(name: str, events: list[tuple[int, str]], settings: MotionSettings) -> Check:
    labelled = [(frame, text, classify(frame, settings)) for frame, text in events]
    unexplained = sum(label == "unexplained" for _, _, label in labelled)
    details = [f"frame {frame} t {frame / settings.fps:.3f} {text} [{label}]" for frame, text, label in labelled]
    summary = f"{len(labelled)} found, {unexplained} unexplained"
    if unexplained:
        summary += " (inspect each with: sheets.sh around <video> <out.png> <t>)"
    return Check(name, "FAIL" if unexplained else "PASS", summary, details)


def find_pops(diffs: np.ndarray, settings: MotionSettings) -> list[tuple[int, str]]:
    events = []
    for index, value in enumerate(diffs):
        left = diffs[index - 1] if index > 0 else 0.0
        right = diffs[index + 1] if index + 1 < len(diffs) else 0.0
        neighbours = max(left, right, 0.3)
        if value > settings.pop_ratio * neighbours and value > settings.pop_floor:
            events.append((index + 1, f"diff {value:.2f} neighbours {neighbours:.2f}"))
    return events


def find_flashes(frames: np.ndarray, diffs: np.ndarray, settings: MotionSettings) -> list[tuple[int, str]]:
    events = []
    for frame in range(1, len(frames) - 1):
        smaller = min(diffs[frame - 1], diffs[frame])
        if smaller <= settings.pop_floor:
            continue
        skip = float(mean_abs_diff(frames[frame - 1], frames[frame + 1]))
        if skip < 0.35 * smaller:
            events.append((frame, f"diff {smaller:.2f}, n-1 vs n+1 {skip:.2f}"))
    return events


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    spans, start = [], None
    for index, flagged in enumerate(mask):
        if flagged and start is None:
            start = index
        if not flagged and start is not None:
            spans.append((start, index - 1))
            start = None
    if start is not None:
        spans.append((start, len(mask) - 1))
    return spans


def freeze_check(diffs: np.ndarray, settings: MotionSettings) -> Check:
    details, failures = [], 0
    for first, last in runs(diffs < settings.freeze_threshold):
        seconds = (last - first + 2) / settings.fps
        if seconds < settings.min_freeze:
            continue
        reaches_end = last == len(diffs) - 1
        if first in settings.ignored_frames:
            label = "ignored"
        elif reaches_end and settings.final_hold and seconds <= settings.final_hold + 1 / settings.fps:
            label = "declared final hold"
        elif reaches_end and settings.final_hold:
            label = f"final freeze longer than declared hold {settings.final_hold:g} s"
        else:
            label = "unexplained"
        failures += label not in {"ignored", "declared final hold"}
        details.append(f"frames {first}-{last + 1} t {first / settings.fps:.2f}-{(last + 1) / settings.fps:.2f} ({seconds:.2f} s) [{label}]")
    summary = f"{len(details)} spans >= {settings.min_freeze:g} s, {failures} unexplained"
    return Check("frozen spans", "FAIL" if failures else "PASS", summary, details)


def black_check(frames: np.ndarray, settings: MotionSettings) -> Check:
    means = frames.reshape(len(frames), -1).mean(axis=1)
    spreads = frames.reshape(len(frames), -1).std(axis=1)
    details, failures = [], 0
    for first, last in runs((means < settings.black_level) & (spreads < 6)):
        ignored = all(frame in settings.ignored_frames for frame in range(first, last + 1))
        failures += not ignored
        label = "ignored" if ignored else "unexplained"
        details.append(f"frames {first}-{last} t {first / settings.fps:.2f}-{last / settings.fps:.2f} [{label}]")
    return Check("black frames", "FAIL" if failures else "PASS", f"{len(details)} spans, {failures} unexplained", details)


def loop_check(frames: np.ndarray, diffs: np.ndarray) -> Check:
    median_step = float(np.median(diffs)) or 0.3
    seam = float(mean_abs_diff(frames[-1], frames[0]))
    velocity_in = float(mean_abs_diff(frames[-1], frames[-2]))
    velocity_out = float(mean_abs_diff(frames[1], frames[0]))
    position_ok = seam <= 2 * median_step
    velocity_ok = abs(velocity_in - velocity_out) <= max(1.0, 0.5 * max(velocity_in, velocity_out))
    details = [
        f"position: seam diff {seam:.2f} vs median step {median_step:.2f} -> {'OK' if position_ok else 'JUMP: fix positions at t=0/T'}",
        f"velocity: in {velocity_in:.2f} / out {velocity_out:.2f} -> {'OK' if velocity_ok else 'SPEED BREAK at the seam'}",
    ]
    level = "PASS" if position_ok and velocity_ok else "FAIL"
    return Check("loop seam", level, "position and velocity match" if level == "PASS" else "seam visible", details)


def motion_checks(frames: np.ndarray, settings: MotionSettings) -> list[Check]:
    if len(frames) < 3:
        return [Check("motion scan", "WARN", f"only {len(frames)} frames decoded")]
    diffs = neighbour_diffs(frames, 1)
    checks = [
        event_check("pops", find_pops(diffs, settings), settings),
        event_check("one-frame flashes", find_flashes(frames, diffs, settings), settings),
        freeze_check(diffs, settings),
        black_check(frames, settings),
        Check("motion stats", "INFO", f"{len(frames)} frames, median step {float(np.median(diffs)):.3f}, max {float(diffs.max()):.2f}"),
    ]
    if settings.loop:
        checks.append(loop_check(frames, diffs))
    return checks
