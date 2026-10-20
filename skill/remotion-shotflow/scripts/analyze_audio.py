#!/usr/bin/env python3
"""Measure a local soundtrack for cue review; never identify/confirm sounds or beats.

Reads the first audio stream in full. No downloads, uploads, dependency installation,
source mutation, or compressed-stream seeking. Python 3, NumPy, SciPy, ffmpeg/ffprobe.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SR, NFFT, HOP = 22050, 1024, 220
DT = HOP / SR
METHOD_VERSION = 2


def run(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"{command[0]} failed: {result.stderr.decode(errors='replace')[-1800:]}")
    return result.stdout


def probe(path, *options):
    return json.loads(run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                           *options, "-of", "json", str(path)]))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def number(value, default=None):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def r(value, digits=5):
    return round(float(value), digits)


def db(value):
    return 20 * np.log10(np.maximum(value, 1e-8))


def levels(samples):
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    rms = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0.0
    return {"sample_count": len(samples), "sample_peak_linear": peak,
            "sample_peak_dbfs": r(20 * np.log10(peak), 2) if peak else None,
            "rms_linear": rms, "rms_dbfs": r(20 * np.log10(rms), 2) if rms else None,
            "all_samples_exactly_zero": not bool(np.any(samples))}


def low_spans(mask, times, end):
    changes = np.diff(np.r_[False, mask, False].astype(np.int8))
    result = []
    for a, b in zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)):
        start = float(times[a])
        stop = min(float(times[0] + b * DT), end)
        if stop - start >= 0.1:
            result.append({"start_s": r(start, 6), "end_s": r(stop, 6),
                           "duration_s": r(stop - start, 6)})
    return result


def tempo_candidates(envelope, count=6):
    """Normalized autocorrelation maxima: repetition hypotheses, not beat detection."""
    if len(envelope) * DT < 5 or np.max(envelope, initial=0) < 1e-7:
        return []
    x = envelope - np.mean(envelope)
    ac = signal.correlate(x, x, mode="full", method="fft")[len(x) - 1:]
    squares = np.r_[0.0, np.cumsum(x * x)]
    lags = np.arange(len(x))
    # Cancellation can leave tiny negative values in cumulative-sum differences.
    products = np.maximum(squares[len(x) - lags], 0) * np.maximum(squares[-1] - squares[lags], 0)
    ac = ac / np.maximum(np.sqrt(products), 1e-12)
    lo, hi = int(np.floor(60 / 220 / DT)), min(int(np.ceil(60 / 45 / DT)), len(ac) - 2)
    if hi <= lo + 2:
        return []
    peaks, _ = signal.find_peaks(ac[lo:hi + 1], distance=3, prominence=0.005)
    result = []
    for k in sorted(peaks + lo, key=lambda k: ac[k], reverse=True)[:count]:
        if ac[k] <= 0:
            continue
        divisor = ac[k - 1] - 2 * ac[k] + ac[k + 1]
        delta = np.clip(0.5 * (ac[k - 1] - ac[k + 1]) / divisor, -0.5, 0.5) if abs(divisor) > 1e-10 else 0
        period = (k + delta) * DT
        bpm = 60 / period
        if not 45 <= bpm <= 220:
            continue
        result.append({"bpm_equivalent": r(bpm, 2), "period_s": r(period, 4),
                       "normalized_autocorrelation_score": r(np.clip(ac[k], -1, 1), 4),
                       "half_bpm_interpretation": r(bpm / 2, 2),
                       "double_bpm_interpretation": r(bpm * 2, 2)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Single local video or audio file")
    parser.add_argument("--out", type=Path, required=True, help="New output directory; never overwrite existing results")
    parser.add_argument("--plot", action="store_true", help="Also write overview.png; requires matplotlib")
    args = parser.parse_args()
    path, out = args.input.expanduser().resolve(), args.out.expanduser().resolve()
    if not path.is_file():
        parser.error(f"Local input file does not exist: {path}")
    if out.exists():
        parser.error(f"Output already exists; choose a new --out directory: {out}")
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    modules = {}
    for name in ("numpy", "scipy", *(('matplotlib',) if args.plot else ())):
        try:
            modules[name] = importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing:
        parser.error("Missing dependencies: " + ", ".join(missing) + ". Use a prepared local environment; this script does not install packages.")
    global np, signal, ndimage
    np = modules["numpy"]
    from scipy import ndimage, signal
    out.parent.mkdir(parents=True, exist_ok=True)
    # Work beside the final destination so success can be committed with one rename.
    # Exceptions, decode failure and plot failure remove the temporary directory.
    with tempfile.TemporaryDirectory(prefix=f".{out.name}-", dir=out.parent) as stage:
        analyze(args, path, Path(stage), out, modules)


def analyze(args, path, out, destination, modules):
    metadata = probe(path, "-show_streams", "-show_format")
    streams = metadata.get("streams", [])
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    base = {"schema_version": 1, "method_version": METHOD_VERSION,
            "source": {"path": str(path), "sha256": digest, "bytes": path.stat().st_size},
            "audio_stream_count": len(audio),
            "runtime": {"python": sys.version.split()[0], "numpy": np.__version__,
                        "scipy": modules["scipy"].__version__,
                        "ffmpeg": run(["ffmpeg", "-version"]).decode().splitlines()[0],
                        "ffprobe": run(["ffprobe", "-version"]).decode().splitlines()[0]},
            "limitations": [
                "No listening, sound-effect classification, stem separation, musical beat confirmation, or visual synchronization validation.",
                "Spectral onset candidates and autocorrelation periods are review hypotheses; scores are not probabilities.",
                "Only the first audio stream is measured; other streams are counted but not mixed or analyzed.",
                "10 ms sampling step is not onset accuracy; the 46 ms STFT window spreads transients over tens of milliseconds.",
                "RMS is not LUFS; sample peak is not true peak; float decode/resampling can exceed 0 dBFS without proving source clipping."
            ], "artifacts": ["analysis.json", "probe.json"],
            "onset_candidates": [], "global_repetition_candidates": [], "local_repetition_windows": []}
    dump(out / "probe.json", metadata)

    def finish(status):
        base["status"] = status
        dump(out / "analysis.json", base)
        if destination.exists():
            raise RuntimeError("Output appeared during processing; refusing to replace it")
        out.rename(destination)
        print(json.dumps({"status": status, "analysis": str(destination / "analysis.json"),
                          "onset_candidate_count": len(base["onset_candidates"]),
                          "repetition_candidate_count": len(base["global_repetition_candidates"])}))

    if not audio:
        finish("no_audio_stream")
        return
    a = audio[0]
    base["audio_stream"] = {key: a.get(key) for key in
                            ("index", "codec_name", "sample_rate", "channels", "channel_layout", "start_time", "duration")}
    channels, native_sr = int(a["channels"]), int(a["sample_rate"])
    frame_info = probe(path, "-select_streams", "a:0", "-show_frames", "-show_entries",
                       "frame=pts_time,best_effort_timestamp_time,nb_samples")
    packet_info = probe(path, "-select_streams", "a:0", "-read_intervals", "%+0.1",
                        "-show_packets", "-show_entries", "packet=pts_time,side_data_list")
    frames = frame_info.get("frames", [])
    first_frame = frames[0] if frames else {}
    first_packet = next(iter(packet_info.get("packets", [])), {})
    frame_pts = [number(frame.get("pts_time", frame.get("best_effort_timestamp_time"))) for frame in frames]
    decoded_start = frame_pts[0] if frame_pts else None
    gaps = []
    for index in range(1, len(frames)):
        previous, current = frame_pts[index - 1:index + 1]
        samples = number(frames[index - 1].get("nb_samples"))
        if previous is None or current is None or samples is None:
            continue
        difference = current - (previous + samples / native_sr)
        if abs(difference) > max(0.002, 2 / native_sr):
            gaps.append({"frame_index": index, "difference_s": r(difference, 6)})
    format_start = number(metadata.get("format", {}).get("start_time"))
    if format_start is not None:
        presentation_start, origin_basis = format_start, "format.start_time"
    else:
        presentation_start, origin_basis = 0.0, "fallback_zero_missing_format_start_time"
    offset = decoded_start - presentation_start if decoded_start is not None else 0.0
    base["timing"] = {"time_origin": "seconds from container presentation start",
                      "presentation_start_pts_s": presentation_start, "origin_basis": origin_basis,
                      "origin_verified": format_start is not None,
                      "first_decoded_audio_frame_pts_s": decoded_start,
                      "first_audio_packet_pts_s": number(first_packet.get("pts_time")),
                      "first_audio_packet_side_data": first_packet.get("side_data_list", []),
                      "audio_offset_s": r(offset, 6), "timestamp_discontinuities": gaps[:20],
                      "timestamp_discontinuity_count": len(gaps),
                      "codec_delay": "FFmpeg applies codec metadata while decoding; no manual AAC/MP3 delay is added."}
    dump(out / "timing-probe.json", {"first_frame": first_frame, "first_packet": first_packet,
                                     "frame_count": len(frames), "timestamp_discontinuities": gaps})
    base["artifacts"].append("timing-probe.json")
    native_raw = run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
                      "-i", str(path), "-map", "0:a:0", "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"])
    native = np.frombuffer(native_raw, dtype="<f4").reshape(-1, channels).astype(np.float64)
    if not np.isfinite(native).all():
        finish("invalid_nonfinite_decoded_samples")
        return
    stereo_opposites = channels == 2 and bool(np.any(native)) and np.array_equal(native[:, 0], -native[:, 1])
    base["original_channels"] = {"sample_rate_hz": native_sr,
                                 "domain": "decoded original channel count and sample rate, before downmix/resampling",
                                 "channels": [{"channel_index": c, **levels(native[:, c])} for c in range(channels)],
                                 "all_channels_exactly_zero": not bool(np.any(native)),
                                 "stereo_channels_exact_opposites": stereo_opposites,
                                 "zero_dbfs_note": "null is digital zero (-infinity), not missing measurement"}
    if not len(native):
        finish("empty_decoded_audio")
        return
    del native_raw
    native_zero = not bool(np.any(native))
    strongest_native_rms = max(channel["rms_linear"] for channel in base["original_channels"]["channels"])
    del native
    if decoded_start is None or any(pts is None for pts in frame_pts):
        finish("timing_unavailable")
        return
    if gaps:
        finish("timestamp_discontinuity_unsupported")
        return
    raw = run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
               "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(SR),
               "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"])
    y = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    if not len(y):
        finish("too_short_for_resampling")
        return
    if not np.isfinite(y).all():
        finish("invalid_nonfinite_decoded_samples")
        return
    end = offset + len(y) / SR
    base["timing"].update({"decoded_audio_duration_s": r(len(y) / SR, 6), "audio_end_s": r(end, 6)})
    base["analysis_levels"] = {"domain": "22050 Hz mono downmix", **levels(y)}
    mono_rms = base["analysis_levels"]["rms_linear"]
    if not native_zero and (not np.any(y) or (stereo_opposites and mono_rms / strongest_native_rms < 1e-4)):
        base["analysis_levels"]["cancellation_note"] = "Original channels are nonzero; mono cancels to zero or floating-point residuals. This is not source silence."
        finish("mono_downmix_cancellation")
        return
    if strongest_native_rms and mono_rms / strongest_native_rms < 0.01:
        base["warnings"] = ["Mono RMS is >40 dB below the strongest original channel: substantial cancellation may hide events. Inspect channels separately before choosing cues."]
    # Pad extremely short media to the analysis window, but clamp all outputs to real duration.
    y_stft = np.pad(y, (0, max(0, NFFT - len(y))))
    freq, tt, z = signal.stft(y_stft, fs=SR, window="hann", nperseg=NFFT,
                             noverlap=NFFT - HOP, nfft=NFFT, boundary="zeros", padded=True)
    usable = tt <= len(y) / SR
    tt, z = tt[usable], z[:, usable]
    magnitude = np.abs(z)
    comp = np.log1p(100 * magnitude[(freq >= 80) & (freq <= 10000)])
    flux = np.r_[0.0, np.mean(np.maximum(np.diff(comp, axis=1), 0), axis=0)]
    novelty = np.maximum(flux - ndimage.median_filter(flux, size=61, mode="nearest"), 0)
    scale = float(np.percentile(novelty, 95))
    normalization = "95th percentile of novelty"
    if scale <= 1e-12:
        scale = float(np.max(novelty, initial=0))
        normalization = "maximum novelty fallback because p95 is zero/negligible (sparse signal)"
    strength = novelty / max(scale, 1e-12)
    padded = np.pad(y, (NFFT // 2, NFFT // 2 + HOP))
    windows = np.lib.stride_tricks.sliding_window_view(padded, NFFT)[::HOP][:len(tt)]
    rms = np.sqrt(np.mean(windows * windows, axis=1))
    rmsdb, times = db(rms), tt + offset
    p95 = float(np.percentile(rmsdb, 95))
    low_threshold = -40.0 if native_zero else min(-40.0, p95 - 25.0)
    # Relative threshold preserves dynamic range; absolute floor avoids amplifying numerical noise.
    analysis_threshold = max(low_threshold, -80.0)
    below_level = rms < 10 ** (analysis_threshold / 20)
    base["analysis_levels"].update({"rms_envelope_p95_dbfs": r(p95, 2),
                                    "low_energy_threshold_dbfs": r(low_threshold, 2),
                                    "candidate_gate_dbfs": r(analysis_threshold, 2),
                                    "low_energy_segments": low_spans(rms < 10 ** (low_threshold / 20), times, end)})
    peak_idx, props = signal.find_peaks(strength, distance=max(1, int(0.12 / DT)), prominence=0.35, height=0.5)
    for j, i in enumerate(peak_idx):
        if below_level[i] or times[i] < 0 or times[i] > end:
            continue
        base["onset_candidates"].append({"time_s": r(times[i], 6), "review_status": "unreviewed",
                                         "strength_vs_normalizer": r(strength[i], 3),
                                         "strength_vs_clip_max": r(novelty[i] / max(float(novelty.max()), 1e-12), 4),
                                         "prominence_vs_normalizer": r(props["prominences"][j], 3),
                                         "local_rms_dbfs": r(rmsdb[i], 2)})
    rhythm = np.minimum(strength, 3.0)
    rhythm[below_level] = 0
    base["global_repetition_candidates"] = tempo_candidates(rhythm)
    for start in np.arange(0, max(0.0, len(y) / SR - 8.0) + 0.001, 4.0):
        left, right = int(start / DT), int((start + 8.0) / DT)
        if right > len(rhythm) or start + 8.0 > len(y) / SR:
            break
        low_fraction = float(np.mean(below_level[left:right]))
        base["local_repetition_windows"].append({"start_s": r(start + offset, 6), "end_s": r(start + 8 + offset, 6),
                                                 "below_gate_fraction": r(low_fraction, 4),
                                                 "status": "skipped_low_energy" if low_fraction >= 0.8 else "computed",
                                                 "candidates": [] if low_fraction >= 0.8 else tempo_candidates(rhythm[left:right], 3)})
    base["method"] = {"sample_rate_hz": SR, "analysis_channels": 1, "stft_size_samples": NFFT,
                      "hop_samples": HOP, "hop_s": r(DT, 6), "window_duration_s": r(NFFT / SR, 6),
                      "stft": "Hann, centered timestamps, zero boundary, padded; results clamped to decoded duration",
                      "novelty": "mean positive diff(log1p(100*abs(STFT))) over 80-10000 Hz; subtract 61-frame local median; clamp >=0",
                      "normalization": normalization, "normalizer_linear": scale,
                      "onset_min_distance_s": 0.12, "onset_min_height": 0.5, "onset_min_prominence": 0.35,
                      "low_energy_rule": "RMS < min(-40 dBFS, clip RMS envelope p95 - 25 dB), continuously >=100 ms; all-zero clip uses -40 dBFS",
                      "candidate_gate": "For onsets and all ACF, zero frames below max(low-energy threshold, -80 dBFS); skip local ACF windows >=80% below gate",
                      "repetition": "mean-removed normalized autocorrelation of normalized novelty clipped at 3; local maxima, parabolic lag refinement",
                      "tempo_search_bpm_range": [45, 220], "min_tempo_duration_s": 5,
                      "local_tempo_window_s": 8, "local_tempo_step_s": 4,
                      "score_meaning": "normalized autocorrelation at candidate period, not probability/confidence",
                      "level_display_floor_dbfs": -160}
    dump(out / "envelope.json", {"time_s": np.round(times[::5], 6).tolist(),
                                 "rms_dbfs": np.round(rmsdb[::5], 2).tolist(),
                                 "novelty_vs_normalizer": np.round(strength[::5], 3).tolist(),
                                 "note": "Every fifth analysis frame (~50 ms); use onset_candidates for review timestamps; -160 dBFS is a zero display floor."})
    base["artifacts"].append("envelope.json")
    if args.plot:
        modules["matplotlib"].use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 1, figsize=(12, 5), sharex=True)
        axes[0].plot(times, rmsdb, linewidth=0.7)
        axes[0].axhline(analysis_threshold, color="gray", linestyle=":")
        axes[0].set_ylabel("Mono RMS dBFS")
        axes[1].plot(times, strength, linewidth=0.7)
        for cue in base["onset_candidates"]:
            axes[1].axvline(cue["time_s"], color="orange", alpha=0.3, linewidth=0.5)
        axes[1].set_ylabel("Spectral novelty / normalizer")
        axes[1].set_xlabel("Seconds from presentation start; orange = unreviewed candidates")
        fig.suptitle(path.name)
        fig.tight_layout()
        fig.savefig(out / "overview.png", dpi=140)
        plt.close(fig)
        base["artifacts"].append("overview.png")
    finish("digital_silence" if native_zero else "measured")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
