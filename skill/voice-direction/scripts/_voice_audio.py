"""Audio measurement helpers shared by voice_qa.py, vo_record.py and vo_build.py (ffmpeg + numpy)."""
import functools
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ANALYSIS_RATE = 44100
FRAME_SIZE = 1024
HOP_SIZE = 512
SILENCE_BELOW_PEAK_DB = 35.0
MIN_MEASURABLE_SECONDS = 0.6
CLIP_LEVEL = 0.999
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"}


@functools.cache
def binary(name: str, verbose: bool = False) -> str:
    candidate = os.environ.get(name.upper()) or shutil.which(name)
    if not candidate:
        raise SystemExit(f"error: {name} not found: set ${name.upper()} or install ffmpeg on PATH (brew install ffmpeg)")
    if verbose:
        print(f"[{name}] {candidate}")
    return candidate


def decode_mono(path: Path, rate: int = ANALYSIS_RATE, filters: str | None = None, via_pipe: bool = False) -> np.ndarray:
    """via_pipe feeds the file on stdin, so ffmpeg keeps the MP3 encoder-delay samples (no gapless trim). The noise-floor
    thresholds were calibrated that way; reading by path measures up to ~3 dB higher on sub-second clips."""
    command = [binary("ffmpeg"), "-v", "error", "-i", "pipe:0" if via_pipe else str(path)]
    if filters:
        command += ["-af", filters]
    command += ["-f", "f32le", "-ac", "1", "-ar", str(rate), "pipe:1"]
    if not Path(path).is_file():
        raise SystemExit(f"error: audio file not found: {path}")
    stdin = Path(path).read_bytes() if via_pipe else None
    result = subprocess.run(command, input=stdin, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"error: ffmpeg could not decode {path}: {result.stderr.decode(errors='replace')[-400:]}")
    return np.frombuffer(result.stdout, dtype=np.float32).copy()


def probe_seconds(path: Path) -> float:
    command = [binary("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    output = subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()
    return float(output)


def frame_levels_db(samples: np.ndarray) -> np.ndarray:
    if len(samples) < FRAME_SIZE:
        return np.empty(0)
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(FRAME_SIZE) / (FRAME_SIZE - 1))
    count = (len(samples) - FRAME_SIZE) // HOP_SIZE + 1
    frames = np.lib.stride_tricks.sliding_window_view(samples.astype(np.float64), FRAME_SIZE)[::HOP_SIZE][:count]
    energy = ((frames * window) ** 2).mean(axis=1)
    return 20 * np.log10(np.sqrt(energy) + 1e-10)


@dataclass(frozen=True)
class NoiseFloor:
    floor_db: float | None
    silence_fraction: float
    quiet_centroid_hz: float | None = None


def spectral_centroid(samples: np.ndarray, frame_indices: np.ndarray) -> float | None:
    """Mean spectral centroid of the given frames: hiss is broadband (kHz), soft speech and breaths sit low (~1 kHz)."""
    if not len(frame_indices):
        return None
    window = np.hanning(FRAME_SIZE)
    power = np.mean([np.abs(np.fft.rfft(samples[i * HOP_SIZE : i * HOP_SIZE + FRAME_SIZE] * window)) ** 2 for i in frame_indices], axis=0)
    frequencies = np.fft.rfftfreq(FRAME_SIZE, 1 / ANALYSIS_RATE)
    return round(float((frequencies * power).sum() / max(power.sum(), 1e-20)))


def noise_floor(samples: np.ndarray, percentile: float = 10.0) -> NoiseFloor:
    """Quietest `percentile`% of frames minus the loudest frame (same index method as the TS checker it was calibrated on)."""
    levels = frame_levels_db(samples)
    if not len(levels):
        return NoiseFloor(None, 0.0)
    ordered = np.sort(levels)
    loudest = ordered[-1]
    silence_fraction = float(np.mean(levels < loudest - SILENCE_BELOW_PEAK_DB))
    quiet = ordered[int(np.floor(len(ordered) * percentile / 100))]
    centroid = spectral_centroid(samples, np.where(np.abs(levels - quiet) <= 2)[0])
    return NoiseFloor(round(float(quiet - loudest), 1), round(silence_fraction, 3), centroid)


def clipped_samples(samples: np.ndarray) -> int:
    return int(np.count_nonzero(np.abs(samples) >= CLIP_LEVEL))


@dataclass(frozen=True)
class Loudness:
    lufs: float | None
    true_peak: float | None


def measure_loudness(path: Path, seconds: float | None = None) -> Loudness:
    """EBU R128 integrated loudness and true peak; clips under 0.6 s are looped 3x (R128 gates need 400 ms)."""
    seconds = probe_seconds(path) if seconds is None else seconds
    loops = ["-stream_loop", "2"] if seconds < MIN_MEASURABLE_SECONDS else []
    command = [binary("ffmpeg"), "-hide_banner", "-nostats", *loops, "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"]
    log = subprocess.run(command, capture_output=True, text=True, check=False).stderr
    summary = log[log.rfind("Summary:") :] if "Summary:" in log else ""
    integrated = re.search(r"I:\s+(-?[0-9.]+|-inf) LUFS", summary)
    peak = re.search(r"Peak:\s+(-?[0-9.]+|-inf) dBFS", summary)
    lufs = float(integrated.group(1)) if integrated and integrated.group(1) != "-inf" else None
    true_peak = float(peak.group(1)) if peak and peak.group(1) != "-inf" else None
    if lufs is not None and lufs <= -70:
        lufs = None
    return Loudness(lufs, true_peak)
