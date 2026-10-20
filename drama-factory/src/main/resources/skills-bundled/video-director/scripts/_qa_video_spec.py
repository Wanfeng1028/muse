"""Helper module for qa_video.py (not a CLI): ffprobe spec checks, faststart detection, shared Check type."""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Check:
    name: str
    level: str
    summary: str
    details: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_binary(name: str, verbose: bool) -> str:
    candidate = os.environ.get(name.upper()) or shutil.which(name)
    if not candidate:
        sys.exit(f"{name} not found: set ${name.upper()} or install ffmpeg (brew install ffmpeg / apt install ffmpeg)")
    if verbose:
        print(f"using {name}: {candidate}", file=sys.stderr)
    return candidate


def probe(ffprobe: str, video: Path) -> dict[str, object]:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"ffprobe failed on {video}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def top_level_atoms(video: Path) -> list[str]:
    atoms: list[str] = []
    with video.open("rb") as handle:
        while len(atoms) < 64:
            header = handle.read(8)
            if len(header) < 8:
                break
            size, kind = struct.unpack(">I4s", header)
            if size == 1:
                size = struct.unpack(">Q", handle.read(8))[0]
                handle.seek(size - 16, 1)
            elif size == 0:
                atoms.append(kind.decode("latin-1"))
                break
            else:
                handle.seek(size - 8, 1)
            atoms.append(kind.decode("latin-1"))
    return atoms


def frame_rate(stream: dict[str, object]) -> float:
    numerator, _, denominator = str(stream.get("avg_frame_rate", "0/1")).partition("/")
    return float(numerator) / float(denominator or 1) if float(denominator or 1) else 0.0


def match_check(name: str, actual: object, expected: str, level_on_mismatch: str = "FAIL") -> Check:
    level = "PASS" if str(actual) == expected else level_on_mismatch
    return Check(name, level, f"{actual} (expected {expected})")


def video_checks(stream: dict[str, object], arguments: argparse.Namespace) -> list[Check]:
    checks = [
        match_check("video codec", stream.get("codec_name"), arguments.expect_codec),
        Check("profile", "INFO", f"{stream.get('profile')} level {stream.get('level')}, {stream.get('width')}x{stream.get('height')}"),
        match_check("pixel format", stream.get("pix_fmt"), arguments.expect_pix_fmt),
    ]
    if arguments.expect_color != "none":
        tags = {key: stream.get(key, "unset") for key in ("color_space", "color_primaries", "color_transfer")}
        wrong = {key: value for key, value in tags.items() if value != arguments.expect_color}
        summary = ", ".join(f"{key}={value}" for key, value in tags.items())
        checks.append(Check("colour tags", "FAIL" if wrong else "PASS", f"{summary} (expected {arguments.expect_color})"))
        checks.append(match_check("colour range", stream.get("color_range", "unset"), "tv", "WARN"))
    return checks


def fps_check(actual: float, expected: float | None) -> Check:
    if expected is None:
        return Check("fps", "INFO", f"{actual:.3f}")
    level = "PASS" if abs(actual - expected) < 0.01 else "FAIL"
    return Check("fps", level, f"{actual:.3f} (expected {expected:g})")


def duration_check(duration: float, fps: float, arguments: argparse.Namespace) -> Check:
    if arguments.expect_duration is None:
        return Check("duration", "INFO", f"{duration:.3f} s")
    tolerance = arguments.duration_tolerance if arguments.duration_tolerance is not None else 1 / max(fps, 1) + 0.05
    off = duration - arguments.expect_duration
    level = "PASS" if abs(off) <= tolerance else "FAIL"
    return Check("duration", level, f"{duration:.3f} s (expected {arguments.expect_duration:g}, off {off:+.3f}, tolerance {tolerance:.3f})")


def audio_checks(stream: dict[str, object] | None, video_duration: float, arguments: argparse.Namespace) -> list[Check]:
    if stream is None:
        return [Check("audio", "FAIL" if arguments.expect_audio else "WARN", "no audio stream")]
    rate = int(str(stream.get("sample_rate", "0")))
    checks = [
        match_check("audio codec", stream.get("codec_name"), arguments.expect_audio_codec),
        Check("sample rate", "PASS" if rate == arguments.expect_sample_rate else "WARN",
              f"{rate} Hz, {stream.get('channels')} ch, {int(str(stream.get('bit_rate', '0'))) // 1000} kb/s (expected {arguments.expect_sample_rate})"),
    ]
    audio_duration = float(str(stream.get("duration", video_duration)))
    gap = audio_duration - video_duration
    checks.append(Check("audio length", "PASS" if abs(gap) <= 0.1 else "WARN", f"{audio_duration:.3f} s vs video {video_duration:.3f} s ({gap:+.3f})"))
    return checks


def faststart_check(video: Path) -> Check:
    if video.suffix.lower() not in {".mp4", ".mov", ".m4v"}:
        return Check("faststart", "INFO", "not an MP4/MOV container")
    atoms = top_level_atoms(video)
    if "moov" in atoms and "mdat" in atoms and atoms.index("moov") < atoms.index("mdat"):
        return Check("faststart", "PASS", "moov before mdat")
    fix = f"ffmpeg -i {video} -c copy -movflags +faststart fixed.mp4"
    return Check("faststart", "WARN", f"moov after mdat (atoms {' '.join(atoms[:6])})", [f"fix: {fix}"])


def spec_checks(arguments: argparse.Namespace, ffprobe: str) -> tuple[list[Check], float]:
    data = probe(ffprobe, arguments.video)
    streams = data.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video_stream is None:
        sys.exit(f"no video stream in {arguments.video}")
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    fps = frame_rate(video_stream)
    duration = float(str(video_stream.get("duration") or data.get("format", {}).get("duration", 0)))
    checks = video_checks(video_stream, arguments)
    checks.append(fps_check(fps, arguments.fps))
    checks.append(duration_check(duration, fps, arguments))
    checks += audio_checks(audio_stream, duration, arguments)
    checks.append(faststart_check(arguments.video))
    return checks, fps
