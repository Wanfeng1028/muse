"""Line processing for vo_build.py: high-pass, silence trims, fades, and loudness matching with a limiter loop."""
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import _voice_audio as audio

RATE = 48000
LOUDNESS_TOLERANCE = 0.3
MAX_PASSES = 6


@dataclass(frozen=True)
class Processing:
    highpass: float = 80.0
    trim: bool = True
    lead_threshold_db: float = -50.0
    tail_threshold_db: float = -40.0
    lead_keep: float = 0.04
    tail_keep: float = 0.08
    target_lufs: float | None = -16.0
    true_peak: float = -1.5
    limiter_ceiling: float = -2.5
    max_limiting: float = 8.0


def base_filters(tempo: float, settings: Processing) -> list[str]:
    filters = [f"atempo={tempo}"] if tempo != 1.0 else []
    if settings.highpass > 0:
        filters.append(f"highpass=f={settings.highpass:g}")
    return filters


def trim_bounds(source: Path, tempo: float, start: float, end: float, speech: tuple[float, float], settings: Processing) -> tuple[float, float]:
    """Narrow [start, end] to the audio above the lead/tail thresholds (sample peak). Guards: never start after the first
    aligned word's start (unless the alignment pins it at 0) and never end before the last word's start + 0.15 s
    (ElevenLabs alignment often stretches the last character to the end of the file, so its end is not trusted)."""
    if not settings.trim:
        return start, end
    filters = ",".join(base_filters(tempo, settings)) or None
    samples = audio.decode_mono(source, rate=RATE, filters=filters)[int(start * RATE) : int(end * RATE)]
    lead = np.flatnonzero(np.abs(samples) >= 10 ** (settings.lead_threshold_db / 20))
    tail = np.flatnonzero(np.abs(samples) >= 10 ** (settings.tail_threshold_db / 20))
    if not len(lead) or not len(tail):
        return start, end
    trimmed_start = start + max(0.0, lead[0] / RATE - settings.lead_keep)
    trimmed_end = start + min(len(samples) / RATE, tail[-1] / RATE + settings.tail_keep)
    first_word_start, last_word_start = speech
    if first_word_start > start:
        trimmed_start = min(trimmed_start, max(start, first_word_start - 0.02))
    return trimmed_start, max(trimmed_end, min(end, last_word_start + 0.15))


def render(source: Path, target: Path, tempo: float, start: float, end: float, settings: Processing) -> None:
    length = end - start
    filters = base_filters(tempo, settings) + [
        f"atrim=start={start:.3f}:end={end:.3f}",
        "asetpts=PTS-STARTPTS",
        "afade=t=in:st=0:d=0.02",
        f"afade=t=out:st={max(0.0, length - 0.04):.3f}:d=0.04",
    ]
    command = [audio.binary("ffmpeg"), "-v", "error", "-y", "-i", str(source), "-af", ",".join(filters), "-ar", str(RATE), "-ac", "1", str(target)]
    subprocess.run(command, check=True)


def _apply_gain(source: Path, target: Path, gain_db: float, ceiling_db: float) -> None:
    limit = f"{10 ** (ceiling_db / 20):.4f}"
    chain = f"volume={gain_db:.2f}dB,alimiter=limit={limit}:level=false:latency=true:attack=3:release=15"
    command = [audio.binary("ffmpeg"), "-v", "error", "-y", "-i", str(source), "-af", chain]
    command += ["-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(target)]
    subprocess.run(command, check=True)


@dataclass
class LoudnessResult:
    input_lufs: float | None
    input_true_peak: float | None
    gain_db: float = 0.0
    ceiling_db: float = 0.0
    output_lufs: float | None = None
    output_true_peak: float | None = None
    passes: int = 0


def match_loudness(source: Path, target: Path, settings: Processing) -> LoudnessResult:
    """Linear gain plus a 3 ms / 15 ms sample-peak limiter (at most max_limiting dB of reduction), re-measured until the
    output sits within 0.3 LU of the target with a true peak at or below the ceiling (clips under 0.6 s measured looped)."""
    measured = audio.measure_loudness(source)
    result = LoudnessResult(measured.lufs, measured.true_peak)
    if settings.target_lufs is None or measured.lufs is None or measured.true_peak is None:
        shutil.copyfile(source, target)
        output = audio.measure_loudness(target)
        result.output_lufs, result.output_true_peak = output.lufs, output.true_peak
        return result
    target_lufs = settings.target_lufs

    def capped(wanted: float, ceiling: float) -> float:
        return min(wanted, ceiling + settings.max_limiting - float(measured.true_peak))

    ceiling = settings.limiter_ceiling
    gain = capped(target_lufs - measured.lufs, ceiling)
    for attempt in range(1, MAX_PASSES + 1):
        _apply_gain(source, target, gain, ceiling)
        output = audio.measure_loudness(target)
        result.passes, result.output_lufs, result.output_true_peak = attempt, output.lufs, output.true_peak
        if output.lufs is None or output.true_peak is None:
            break
        next_gain = capped(gain + target_lufs - output.lufs, ceiling)
        settled = abs(output.lufs - target_lufs) <= LOUDNESS_TOLERANCE or abs(next_gain - gain) < 0.1
        peak_ok = output.true_peak <= settings.true_peak
        if settled and peak_ok:
            break
        if not peak_ok:
            ceiling -= output.true_peak - settings.true_peak + 0.2
        gain = next_gain if peak_ok else capped(gain, ceiling)
    result.gain_db, result.ceiling_db = round(gain, 2), round(ceiling, 2)
    return result
