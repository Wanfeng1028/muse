#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2"]
# ///
"""Audio QA for mixes, VO takes and finished videos: loudness, true peak, clipping, envelopes, speech spans, silences.

Inputs: one or more audio or video files (WAV, MP3, MP4...). Loudness comes from ffmpeg loudnorm's measuring pass
(EBU R128 integrated LUFS, true peak, LRA). Measure the encoded MP4 too, not only the WAV: AAC can raise the true peak.
Output: report on stdout and in out/review/qa/<name>.audio.txt (+ .audio.json with --json). Exit 1 when a target fails.
Examples:
  audio_qa.py out/mix.wav out/final/film-16x9.mp4
  audio_qa.py out/mix.wav --envelope 19.8 21.2 0.05 --check-silence 4.85,10.2
  audio_qa.py public/audio/vo-final/*.wav --spans --target-lufs -16 --report-only
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ENVELOPE_RATE = 22050
PEAK_MEASUREMENT_SLACK = 0.05


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--target-lufs", type=float, default=-14.0, help="integrated loudness target (default -14)")
    parser.add_argument("--lufs-tolerance", type=float, default=1.0, help="allowed LU either side (default 1.0)")
    parser.add_argument("--max-true-peak", type=float, default=-1.0, help="dBTP ceiling (default -1.0)")
    parser.add_argument("--clip-level", type=float, default=0.999, help="sample magnitude counted as clipped")
    parser.add_argument("--max-clipped", type=int, default=0, help="clipped samples allowed (default 0)")
    parser.add_argument("--report-only", action="store_true", help="measure and print, never fail on targets")
    parser.add_argument("--envelope", nargs="+", type=float, metavar="S", help="START END [STEP]: RMS bars per step")
    parser.add_argument("--spans", action="store_true", help="where speech (non-silence) starts and ends")
    parser.add_argument("--check-silence", help="times in seconds that must sit in silence, comma separated")
    parser.add_argument("--silence-db", type=float, default=-42.0, help="silence threshold dBFS (default -42)")
    parser.add_argument("--silence-window", type=float, default=0.03, help="± seconds measured per check (default 0.03)")
    parser.add_argument("--report-dir", type=Path, default=Path("out/review/qa"))
    parser.add_argument("--json", action="store_true", help="also write a JSON report per file")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def resolve_binary(name: str, verbose: bool) -> str:
    candidate = os.environ.get(name.upper()) or shutil.which(name)
    if not candidate:
        sys.exit(f"{name} not found: set ${name.upper()} or install ffmpeg (brew install ffmpeg / apt install ffmpeg)")
    if verbose:
        print(f"using {name}: {candidate}", file=sys.stderr)
    return candidate


def probe_audio(ffprobe: str, path: Path) -> dict[str, object]:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name,sample_rate,channels:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    if result.returncode != 0 or not streams:
        sys.exit(f"no audio stream in {path}")
    stream = streams[0]
    return {
        "codec": stream.get("codec_name"),
        "sample_rate": int(stream.get("sample_rate", 0)),
        "channels": int(stream.get("channels", 1)),
        "duration": float(data.get("format", {}).get("duration", 0)),
    }


def measure_loudness(ffmpeg: str, path: Path, target: float, true_peak: float) -> dict[str, float]:
    command = [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
               f"loudnorm=I={target}:TP={true_peak}:LRA=11:print_format=json", "-f", "null", "-"]
    log = subprocess.run(command, capture_output=True, text=True).stderr
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", log)
    if not match:
        sys.exit(f"loudnorm measurement failed for {path}:\n{log[-800:]}")
    values = json.loads(match.group(0))
    return {key: float(values[f"input_{key}"]) for key in ("i", "tp", "lra", "thresh")}


def decode(ffmpeg: str, path: Path, rate: int | None, mono: bool) -> np.ndarray:
    command = [ffmpeg, "-v", "error", "-i", str(path), "-vn", "-f", "f32le", "-acodec", "pcm_f32le"]
    if rate:
        command += ["-ar", str(rate)]
    if mono:
        command += ["-ac", "1"]
    result = subprocess.run(command + ["-"], capture_output=True)
    if result.returncode != 0:
        sys.exit(f"could not decode {path}: {result.stderr.decode()[-500:]}")
    return np.frombuffer(result.stdout, np.float32)


def decibels(value: float) -> float:
    return float(20 * np.log10(value + 1e-9))


def envelope_lines(samples: np.ndarray, start: float, end: float, step: float) -> list[str]:
    lines = []
    time = start
    while time < end - 1e-9:
        window = samples[int(time * ENVELOPE_RATE):int((time + step) * ENVELOPE_RATE)]
        level = decibels(float(np.sqrt(np.mean(window ** 2)))) if len(window) else -180.0
        lines.append(f"{time:8.2f}  {level:6.1f} dB  {'#' * max(0, int((level + 60) / 2))}")
        time += step
    return lines


def speech_span(ffmpeg: str, path: Path, silence_db: float, duration: float) -> tuple[float, float, int]:
    command = [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
               f"silencedetect=n={silence_db}dB:d=0.06", "-f", "null", "-"]
    log = subprocess.run(command, capture_output=True, text=True).stderr
    starts = [float(value) for value in re.findall(r"silence_start: (-?[0-9.]+)", log)]
    ends = [float(value) for value in re.findall(r"silence_end: ([0-9.]+)", log)]
    speech_start = ends[0] if starts and starts[0] < 0.02 and ends else 0.0
    speech_end = starts[-1] if starts and (not ends or starts[-1] > ends[-1]) else duration
    inner_pauses = sum(speech_start < start < speech_end for start in starts)
    return speech_start, speech_end, inner_pauses


def silence_checks(samples: np.ndarray, times: list[float], window: float, threshold: float) -> list[tuple[float, float, bool]]:
    results = []
    for time in times:
        chunk = samples[max(0, int((time - window) * ENVELOPE_RATE)):int((time + window) * ENVELOPE_RATE)]
        level = decibels(float(np.sqrt(np.mean(chunk ** 2)))) if len(chunk) else -180.0
        results.append((time, level, bool(level <= threshold)))
    return results


def verdict(passed: bool, report_only: bool) -> str:
    if report_only:
        return "INFO"
    return "PASS" if passed else "FAIL"


def analyse(path: Path, arguments: argparse.Namespace, ffmpeg: str, ffprobe: str) -> tuple[list[str], dict[str, object], bool]:
    info = probe_audio(ffprobe, path)
    loudness = measure_loudness(ffmpeg, path, arguments.target_lufs, arguments.max_true_peak)
    native = decode(ffmpeg, path, None, mono=False)
    clipped = int(np.count_nonzero(np.abs(native) >= arguments.clip_level))
    sample_peak = decibels(float(np.abs(native).max())) if len(native) else -180.0
    loudness_ok = abs(loudness["i"] - arguments.target_lufs) <= arguments.lufs_tolerance
    peak_ok = loudness["tp"] <= arguments.max_true_peak + PEAK_MEASUREMENT_SLACK
    clip_ok = clipped <= arguments.max_clipped
    lines = [
        f"AUDIO {path}",
        f"  {info['codec']}, {info['sample_rate']} Hz, {info['channels']} ch, {info['duration']:.3f} s",
        f"  [{verdict(loudness_ok, arguments.report_only)}] integrated {loudness['i']:.2f} LUFS (target {arguments.target_lufs:g} ± {arguments.lufs_tolerance:g})",
        f"  [{verdict(peak_ok, arguments.report_only)}] true peak {loudness['tp']:.2f} dBTP (max {arguments.max_true_peak:g}); sample peak {sample_peak:.2f} dBFS",
        f"  [INFO] LRA {loudness['lra']:.1f} LU, gating threshold {loudness['thresh']:.1f} LUFS",
        f"  [{verdict(clip_ok, arguments.report_only)}] clipped samples {clipped} (|s| >= {arguments.clip_level:g}, allowed {arguments.max_clipped})",
    ]
    report: dict[str, object] = {"file": str(path), **info, "lufs": loudness["i"], "true_peak": loudness["tp"],
                                 "lra": loudness["lra"], "sample_peak": sample_peak, "clipped": clipped}
    passed = loudness_ok and peak_ok and clip_ok
    needs_mono = arguments.envelope or arguments.check_silence
    mono = decode(ffmpeg, path, ENVELOPE_RATE, mono=True) if needs_mono else np.zeros(0, np.float32)
    if arguments.envelope:
        start, end = arguments.envelope[0], arguments.envelope[1]
        step = arguments.envelope[2] if len(arguments.envelope) > 2 else 0.1
        lines.append(f"  envelope {start:g}-{end:g} s, step {step:g} s (RMS dBFS):")
        lines += [f"  {line}" for line in envelope_lines(mono, start, end, step)]
    if arguments.spans:
        speech_start, speech_end, pauses = speech_span(ffmpeg, path, arguments.silence_db, info["duration"])
        lines.append(f"  [INFO] speech {speech_start:.2f}-{speech_end:.2f} s (len {speech_end - speech_start:.2f}, "
                     f"lead {speech_start:.2f}, tail {info['duration'] - speech_end:.2f}, inner pauses {pauses})")
        report["speech"] = {"start": speech_start, "end": speech_end, "inner_pauses": pauses}
    if arguments.check_silence:
        times = [float(value) for value in arguments.check_silence.split(",") if value.strip()]
        results = silence_checks(mono, times, arguments.silence_window, arguments.silence_db)
        for time, level, silent in results:
            lines.append(f"  [{verdict(silent, arguments.report_only)}] silence at {time:.3f} s: {level:.1f} dBFS (threshold {arguments.silence_db:g})")
        passed = passed and all(silent for _, _, silent in results)
        report["silence_checks"] = [{"time": time, "level": level, "silent": silent} for time, level, silent in results]
    passed = passed or arguments.report_only
    report["passed"] = passed
    return lines, report, passed


def write_reports(path: Path, lines: list[str], report: dict[str, object], arguments: argparse.Namespace) -> None:
    arguments.report_dir.mkdir(parents=True, exist_ok=True)
    text_path = arguments.report_dir / f"{path.stem}.audio.txt"
    text_path.write_text("\n".join(lines) + "\n")
    print(f"wrote {text_path}")
    if arguments.json:
        json_path = arguments.report_dir / f"{path.stem}.audio.json"
        json_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {json_path}")


def main() -> None:
    arguments = parse_arguments()
    if arguments.envelope and len(arguments.envelope) not in (2, 3):
        sys.exit("--envelope takes START END [STEP]")
    ffmpeg = resolve_binary("ffmpeg", arguments.verbose)
    ffprobe = resolve_binary("ffprobe", arguments.verbose)
    failures = []
    for path in arguments.files:
        if not path.is_file():
            sys.exit(f"file not found: {path}")
        lines, report, passed = analyse(path, arguments, ffmpeg, ffprobe)
        print("\n".join(lines))
        write_reports(path, lines, report, arguments)
        if not passed:
            failures.append(path.name)
    print(f"FAIL: {', '.join(failures)}" if failures else f"PASS: {len(arguments.files)} file(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
