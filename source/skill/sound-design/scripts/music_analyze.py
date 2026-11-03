#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["numpy>=2", "scipy>=1.11", "librosa>=0.11", "soundfile>=0.12"]
# ///
"""Analyze a music track: tempo, beats, bars, energy, key, onsets, drop candidates; refine onsets near guesses."""
import argparse
import json
import sys
from pathlib import Path

import librosa
import numpy as np
from scipy.signal import butter, find_peaks, sosfilt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_audio import media  # noqa: E402

RATE = 22050
FINE_HOP = 64
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
GRID_WARNING = "Auto beat grids can be off by whole beats (one licensed track's grid was 2 beats off): confirm the downbeat and drop by ear or with --around before snapping cuts."


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tempo, beats, bars, per-second and per-bar energy (low + full band), Krumhansl key, onset strength and drop candidates.",
        epilog=(
            "Outputs <out-dir>/<track>.beats.json and <track>.summary.txt.\n"
            "beats.json keys: tempo, tempo_candidates, duration, grid, beats, beats_tracked, tracked_agreement, bars, downbeat_phase,\n"
            "energy_per_second, energy_db_per_second,"
            " low_db_per_second, bar_energy, onset_mean, onset_strength_per_beat, key, drops[{time, coarse, jump_db, low_jump_db, nearest_bar, bar_offset}], around, warnings.\n"
            "Example: uv run music_analyze.py public/audio/music/track.mp3 --around 30.2 61.0 --downbeat 0.23"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("track", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--around", type=float, nargs="*", default=[], help="guesses (s) to refine to the exact onset")
    parser.add_argument("--window", type=float, default=0.15, help="search half-window for --around (s)")
    parser.add_argument("--beats-per-bar", type=int, default=4)
    parser.add_argument("--grid", choices=("steady", "tracked"), default="steady", help="steady = constant-tempo grid fitted to onsets (default); tracked = librosa beats, for drifting tempo")
    parser.add_argument("--snap-ms", type=float, default=50.0, help="snap tracked beats to the onset peak within this window (0 = off)")
    parser.add_argument("--downbeat", type=float, default=None, help="a known downbeat time; fixes the bar phase")
    parser.add_argument("--drops", type=int, default=5, help="max drop candidates")
    parser.add_argument("--drop-threshold", type=float, default=3.0, help="min energy jump (dB) for a drop candidate")
    parser.add_argument("--low-hz", type=float, default=150.0, help="low band cutoff for kick/bass energy")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def to_db(power: np.ndarray) -> np.ndarray:
    return 10 * np.log10(np.maximum(power, 1e-12))


def frame_power(signal: np.ndarray, frame: int, hop: int) -> np.ndarray:
    frames = librosa.util.frame(np.pad(signal, (frame // 2, frame // 2)), frame_length=frame, hop_length=hop)
    return (frames.astype(np.float64) ** 2).mean(axis=0)


def tempo_and_beats(samples: np.ndarray) -> tuple[float, np.ndarray, list[float], float]:
    onset = librosa.onset.onset_strength(y=samples, sr=RATE, hop_length=256)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=RATE, hop_length=256, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    centred = onset - onset.mean()
    correlation = np.correlate(centred, centred, "full")[len(centred) - 1 :]
    lags = np.arange(len(correlation)) * 256 / RATE
    valid = (lags > 60 / 200) & (lags < 60 / 55)
    autocorrelation_bpm = 60 / lags[valid][np.argmax(correlation[valid])]
    candidates = sorted({round(value, 2) for value in (tempo, tempo / 2, tempo * 2, autocorrelation_bpm) if 50 <= value <= 220})
    return tempo, np.asarray(beats), candidates, float(autocorrelation_bpm)


def snap_beats(beats: np.ndarray, fine_onset: np.ndarray, window: float) -> np.ndarray:
    """Move each tracked beat to the clear onset peak within +-window (the tracker runs ~20-40 ms late)."""
    if window <= 0:
        return beats
    times = np.arange(len(fine_onset)) * FINE_HOP / RATE
    snapped = beats.copy()
    for index, beat in enumerate(beats):
        mask = (times > beat - window) & (times < beat + window)
        if mask.any() and fine_onset[mask].max() > 2 * fine_onset[mask].mean():
            snapped[index] = times[mask][np.argmax(fine_onset[mask])]
    return snapped


def _best_grid(fine_onset: np.ndarray, duration: float, periods: np.ndarray) -> tuple[float, float, float]:
    times = np.arange(len(fine_onset)) * FINE_HOP / RATE
    best = (-1.0, float(periods[0]), 0.0)
    for period in periods:
        phases = np.arange(0, period, 0.002)
        grid = phases[:, None] + np.arange(int(duration / period) + 1)[None, :] * period
        valid = grid < duration - 0.01
        score = (np.interp(grid, times, fine_onset) * valid).sum(axis=1) / valid.sum(axis=1)
        index = int(np.argmax(score))
        if score[index] > best[0]:
            best = (float(score[index]), float(period), float(phases[index]))
    return best


def steady_grid(fine_onset: np.ndarray, tracked: np.ndarray, tempo: float, duration: float) -> tuple[np.ndarray, float, float]:
    """Constant-tempo grid that best lines up with the onset envelope (tempo within 2% of the tracker's).
    Returns grid, period and the share of tracked beats within 50 ms of it."""
    period = 60 / tempo
    _, coarse, _ = _best_grid(fine_onset, duration, np.arange(period * 0.98, period * 1.02, 0.0002))
    _, period, phase = _best_grid(fine_onset, duration, np.arange(coarse - 0.0003, coarse + 0.0003, 0.00002))
    grid = phase + np.arange(int((duration - phase) / period) + 1) * period
    agreement = float(np.mean([np.min(np.abs(grid - beat)) < 0.05 for beat in tracked])) if len(tracked) else 0.0
    return grid[grid < duration], period, agreement


def downbeat_phase(beats: np.ndarray, low_power: np.ndarray, chroma: np.ndarray, hop: int, per_bar: int, known: float | None) -> int:
    if known is not None:
        return int(np.argmin(np.abs(beats - known))) % per_bar
    frames = np.clip((beats * RATE / hop).astype(int), 1, chroma.shape[1] - 1)
    novelty = np.r_[0, np.linalg.norm(np.diff(chroma, axis=1), axis=0)][frames]
    low = low_power[np.clip((beats * RATE / FINE_HOP).astype(int), 0, len(low_power) - 1)]
    score = novelty / (novelty.mean() or 1) + low / (low.mean() or 1)
    return int(np.argmax([score[phase::per_bar].mean() for phase in range(per_bar)]))


def estimate_key(chroma: np.ndarray) -> list[dict[str, float | str]]:
    profile = chroma.mean(axis=1)
    scores = []
    for tonic in range(12):
        scores.append((float(np.corrcoef(np.roll(MAJOR, tonic), profile)[0, 1]), f"{NAMES[tonic]} major"))
        scores.append((float(np.corrcoef(np.roll(MINOR, tonic), profile)[0, 1]), f"{NAMES[tonic]} minor"))
    return [{"name": name, "score": round(score, 3)} for score, name in sorted(scores, reverse=True)[:4]]


def per_second_db(power: np.ndarray, hop: int, duration: float) -> list[float]:
    per_second = RATE // hop
    return [round(float(to_db(power[s * per_second : (s + 1) * per_second].mean())), 1) for s in range(int(duration))]


def jump_curve(power: np.ndarray, hop: int, seconds: float) -> np.ndarray:
    span = int(seconds * RATE / hop)
    cumulative = np.r_[0, np.cumsum(power)]
    index = np.arange(len(power))
    before = (cumulative[index] - cumulative[np.maximum(index - span, 0)]) / np.maximum(index - np.maximum(index - span, 0), 1)
    after = (cumulative[np.minimum(index + span, len(power))] - cumulative[index]) / np.maximum(np.minimum(index + span, len(power)) - index, 1)
    curve = to_db(after) - to_db(before)
    curve[: span // 2] = 0
    curve[-span // 2 :] = 0
    return curve


def strongest_onset(fine_onset: np.ndarray, around: float, window: float) -> float:
    times = np.arange(len(fine_onset)) * FINE_HOP / RATE
    mask = (times > around - window) & (times < around + window)
    if not mask.any():
        return around
    return float(times[mask][np.argmax(fine_onset[mask])])


def find_drops(full: np.ndarray, low: np.ndarray, fine_onset: np.ndarray, bars: np.ndarray, arguments: argparse.Namespace) -> list[dict[str, float]]:
    full_jump, low_jump = jump_curve(full, FINE_HOP, 2.0), jump_curve(low, FINE_HOP, 2.0)
    combined = 0.6 * low_jump + 0.4 * full_jump
    peaks, _ = find_peaks(combined, height=arguments.drop_threshold, distance=int(4 * RATE / FINE_HOP))
    peaks = sorted(peaks, key=lambda index: combined[index], reverse=True)[: arguments.drops]
    drops = []
    for index in sorted(peaks):
        coarse = index * FINE_HOP / RATE
        refined = strongest_onset(fine_onset, coarse, 0.3)
        nearest = float(bars[np.argmin(np.abs(bars - refined))]) if len(bars) else refined
        drops.append({
            "time": round(refined, 3), "coarse": round(coarse, 3), "jump_db": round(float(full_jump[index]), 1),
            "low_jump_db": round(float(low_jump[index]), 1), "nearest_bar": round(nearest, 3), "bar_offset": round(refined - nearest, 3),
        })
    return drops


def chord(chroma: np.ndarray, hop: int, start: float, end: float) -> str:
    first, last = int(max(start, 0) * RATE / hop), max(int(end * RATE / hop), int(max(start, 0) * RATE / hop) + 1)
    profile = chroma[:, first:last].mean(axis=1)
    return "/".join(NAMES[i] for i in np.argsort(profile)[::-1][:3])


def summary_lines(result: dict, track: Path) -> list[str]:
    lines = [f"{track.name}: {result['duration']:.2f}s, tempo {result['tempo']:.2f} BPM (candidates {result['tempo_candidates']}),",
             f"  {len(result['beats'])} beats, {len(result['bars'])} bars (downbeat phase {result['downbeat_phase']}, first bar {result['bars'][0] if result['bars'] else '-'})",
             "  key: " + ", ".join(f"{k['name']} ({k['score']})" for k in result["key"]["candidates"])]
    lines += [f"  drop {d['time']:.3f}s (coarse {d['coarse']:.2f}, +{d['jump_db']} dB full, +{d['low_jump_db']} dB low, bar offset {d['bar_offset'] * 1000:+.0f} ms)" for d in result["drops"]]
    lines += [f"  around {a['guess']}: onset {a['onset']:.3f}s, chord before {a['chord_before']}, after {a['chord_after']}" for a in result["around"]]
    seconds = result["energy_db_per_second"]
    lines.append("  energy dB per second (full/low):")
    lines += ["    " + "  ".join(f"{s:3d}:{seconds[s]:5.1f}/{result['low_db_per_second'][s]:5.1f}" for s in range(row, min(row + 6, len(seconds)))) for row in range(0, len(seconds), 6)]
    return lines + [f"  warning: {w}" for w in result["warnings"]]


def main() -> None:
    arguments = parse_arguments()
    media.set_verbose(arguments.verbose)
    samples = media.decode(arguments.track, RATE, 1)[:, 0]
    duration = len(samples) / RATE
    low_signal = sosfilt(butter(4, arguments.low_hz / (RATE / 2), output="sos"), samples).astype(np.float32)
    full_power, low_power = frame_power(samples, 1024, FINE_HOP), frame_power(low_signal, 1024, FINE_HOP)
    fine_onset = librosa.onset.onset_strength(y=samples, sr=RATE, hop_length=FINE_HOP, n_fft=512)
    chroma_hop = 512
    chroma = librosa.feature.chroma_cqt(y=samples, sr=RATE, hop_length=chroma_hop)
    tempo, beats, candidates, autocorrelation_bpm = tempo_and_beats(samples)
    tracked = snap_beats(beats, fine_onset, arguments.snap_ms / 1000)
    grid, period, inliers = steady_grid(fine_onset, tracked, tempo, duration)
    use_steady = arguments.grid == "steady"
    beats = grid if use_steady else tracked
    if use_steady:
        tempo = 60 / period
    phase = downbeat_phase(beats, low_power, chroma, chroma_hop, arguments.beats_per_bar, arguments.downbeat) if len(beats) else 0
    bars = beats[phase :: arguments.beats_per_bar]
    onset_hop = librosa.onset.onset_strength(y=samples, sr=RATE, hop_length=512)

    warnings = [GRID_WARNING]
    if inliers < 0.5:
        warnings.append(f"only {inliers:.0%} of tracked beats sit within 50 ms of the steady grid: tempo may drift (try --grid tracked), or voice/SFX over the music confuse the tracker (analyze the clean track)")
    if not any(abs(autocorrelation_bpm / tempo - ratio) < 0.04 * ratio for ratio in (0.5, 1, 2)):
        warnings.append(f"beat tracker ({tempo:.1f}) and autocorrelation ({autocorrelation_bpm:.1f}) disagree on tempo; check by ear")
    if arguments.downbeat is None:
        warnings.append("bar phase is a heuristic (chord change + low energy); pass --downbeat t once you know a real downbeat")
    key_candidates = estimate_key(chroma)
    bar_edges = np.r_[bars, duration]
    result = {
        "file": str(arguments.track), "tempo": round(tempo, 3), "tempo_candidates": candidates, "duration": round(duration, 3),
        "beats_per_bar": arguments.beats_per_bar, "downbeat_phase": phase,
        "grid": "steady" if use_steady else "tracked", "tracked_agreement": round(inliers, 2), "beats_tracked": [round(float(b), 3) for b in tracked],
        "beats": [round(float(b), 3) for b in beats], "bars": [round(float(b), 3) for b in bars],
        "energy_per_second": [round(float(np.sqrt(full_power[s * (RATE // FINE_HOP) : (s + 1) * (RATE // FINE_HOP)].mean())), 3) for s in range(int(duration))],
        "energy_db_per_second": per_second_db(full_power, FINE_HOP, duration), "low_db_per_second": per_second_db(low_power, FINE_HOP, duration),
        "bar_energy": [{"start": round(float(a), 3), "full_db": round(float(to_db(full_power[int(a * RATE / FINE_HOP) : int(b * RATE / FINE_HOP) + 1].mean())), 1),
                        "low_db": round(float(to_db(low_power[int(a * RATE / FINE_HOP) : int(b * RATE / FINE_HOP) + 1].mean())), 1)} for a, b in zip(bar_edges, bar_edges[1:])],
        "onset_mean": round(float(onset_hop.mean()), 3),
        "onset_strength_per_beat": [round(float(onset_hop[min(int(b * RATE / 512), len(onset_hop) - 1)]), 2) for b in beats],
        "key": {"best": key_candidates[0]["name"], "candidates": key_candidates},
        "drops": find_drops(full_power, low_power, fine_onset, bars, arguments),
        "around": [{"guess": guess, "onset": round(onset, 3), "chord_before": chord(chroma, chroma_hop, onset - 1.2, onset - 0.05), "chord_after": chord(chroma, chroma_hop, onset + 0.05, onset + 0.8)}
                   for guess in arguments.around for onset in [strongest_onset(fine_onset, guess, arguments.window)]],
        "warnings": warnings,
    }
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    beats_path = arguments.out_dir / f"{arguments.track.stem}.beats.json"
    summary_path = arguments.out_dir / f"{arguments.track.stem}.summary.txt"
    beats_path.write_text(json.dumps(result) + "\n")
    lines = summary_lines(result, arguments.track)
    summary_path.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(beats_path)
    print(summary_path)


if __name__ == "__main__":
    main()
