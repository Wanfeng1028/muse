"""Beat-alignment instrument: audio beat grid vs visual event times.

Audio: spectral-flux onset envelope -> tempo (autocorrelation, 70-180 BPM, then a
fine period/phase comb search) -> beat grid. Visual: per-frame mean absolute
difference on a downscaled gray video -> motion bursts (onset frame + peak frame),
plus hard cuts from ffmpeg scdet. Each event is paired with its nearest beat.

Limits (stated in every output): onset hop = 256 samples at 22.05 kHz (11.6 ms);
visual time resolution = 1 frame; tempo is prior-free inside 70-180 BPM, so a
true tempo outside that range reads as its octave.

Usage:
    python -X utf8 scripts/beatgrid.py <video> --out <outdir>/beat [--min-gap 0.2] [--k 6]
    python -X utf8 scripts/beatgrid.py --selftest
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import load_audio, load_gray_frames, probe  # noqa: E402

HOP = 256
NFFT = 1024


def onset_envelope(y, sr):
    n = 1 + (len(y) - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    frames = y[idx] * np.hanning(NFFT)[None, :]
    mag = np.log1p(1000 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")  # remove slow loudness trend
    flux = np.maximum(flux, 0)
    env_t = (np.arange(n) * HOP + NFFT / 2) / sr
    return flux / (flux.max() or 1), env_t


def comb_score(env, env_t, period, phase):
    beats = np.arange(phase, env_t[-1], period)
    return np.interp(beats, env_t, env).mean() if len(beats) else 0.0


def estimate_grid(env, env_t, bpm_lo=70, bpm_hi=180):
    dt = env_t[1] - env_t[0]
    ac = np.correlate(env - env.mean(), env - env.mean(), mode="full")[len(env) - 1:]
    lags = np.arange(len(ac)) * dt
    ok = (lags >= 60 / bpm_hi) & (lags <= 60 / bpm_lo)
    cand_idx = np.where(ok)[0][np.argsort(ac[ok])[::-1]]
    candidates = []
    for i in cand_idx:
        bpm = 60 / lags[i]
        if all(abs(bpm - c) > 3 for c in candidates):
            candidates.append(round(float(bpm), 2))
        if len(candidates) == 3:
            break
    coarse = 60 / candidates[0]
    best = (-1, coarse, 0.0)
    for period in np.linspace(coarse * 0.97, coarse * 1.03, 121):
        for phase in np.arange(0, period, dt / 2):
            s = comb_score(env, env_t, period, phase)
            if s > best[0]:
                best = (s, period, phase)
    score, period, phase = best
    return {"bpm": float(60 / period), "period_s": float(period), "phase_s": float(phase),
            "comb_score": float(score), "autocorr_candidates_bpm": candidates}


def motion_events(frames, fps, k=6.0, min_gap=0.2):
    f = frames.astype(np.float32)
    diff = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    diff = np.concatenate([[0.0], diff])
    med = np.median(diff)
    mad = np.median(np.abs(diff - med)) or 1e-6
    thr = med + k * 1.4826 * mad
    active = diff > thr
    events, i, n = [], 0, len(diff)
    while i < n:
        if active[i]:
            j = i
            while j + 1 < n and active[j + 1]:
                j += 1
            peak = i + int(np.argmax(diff[i:j + 1]))
            if not events or (i - events[-1]["end_frame"]) / fps >= min_gap:
                events.append({"onset_frame": i, "peak_frame": peak, "end_frame": j})
            else:
                events[-1]["end_frame"] = j
            i = j + 1
        else:
            i += 1
    return events, diff, float(thr)


def scdet_cuts(path, threshold=12):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", f"scdet=threshold={threshold}",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    times = [float(t) for t in re.findall(r"lavfi\.scd\.time: ([0-9.]+)", r.stderr)]
    merged = []
    for t in times:  # scdet often fires on 2 consecutive frames of one cut
        if not merged or t - merged[-1] > 0.1:
            merged.append(t)
    return merged


def pair(times, grid, fps):
    out = []
    for t in times:
        k = round((t - grid["phase_s"]) / grid["period_s"])
        bt = grid["phase_s"] + k * grid["period_s"]
        off = t - bt
        out.append({"t": round(t, 4), "beat_index": int(k), "beat_t": round(bt, 4),
                    "offset_ms": round(off * 1000, 1), "offset_frames": round(off * fps, 2)})
    return out


def summarize(pairs, fps):
    if not pairs:
        return {}
    o = np.array([p["offset_ms"] for p in pairs])
    frame_ms = 1000 / fps
    return {"n": len(o), "median_ms": float(np.median(o)), "median_abs_ms": float(np.median(np.abs(o))),
            "within_1_frame": float(np.mean(np.abs(o) <= frame_ms + 1e-6)),
            "within_50ms": float(np.mean(np.abs(o) <= 50))}


def analyse(path, k=6.0, min_gap=0.2, width=240):
    info = probe(path)
    y, sr = load_audio(path)
    env, env_t = onset_envelope(y, sr)
    env_t = env_t + info["audio_start"] - info["video_start"]  # put audio on the video clock
    grid = estimate_grid(env, env_t)
    frames, fps = load_gray_frames(path, width=width)
    evs, diff, thr = motion_events(frames, fps, k=k, min_gap=min_gap)
    cuts = scdet_cuts(path)
    res = {
        "video": str(path), "fps": fps, "duration_s": info["duration"],
        "stream_start": {"audio": info["audio_start"], "video": info["video_start"]},
        "grid": grid,
        "motion_onsets": pair([e["onset_frame"] / fps for e in evs], grid, fps),
        "motion_peaks": pair([e["peak_frame"] / fps for e in evs], grid, fps),
        "cuts": pair(cuts, grid, fps),
        "limits": "onset hop 11.6 ms; visual resolution 1 frame; tempo range 70-180 BPM prior-free; "
                  "motion onset = first frame whose frame-difference exceeds median + k * median absolute deviation",
        "params": {"k": k, "min_gap_s": min_gap, "downscale_width": width, "diff_threshold": thr},
    }
    for key in ("motion_onsets", "motion_peaks", "cuts"):
        res[key + "_summary"] = summarize(res[key], fps)
    return res, (env, env_t, diff)


def plot(res, series, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    env, env_t, diff = series
    fps, g = res["fps"], res["grid"]
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [2, 2, 1.4]})
    beats = np.arange(g["phase_s"], res["duration_s"], g["period_s"])
    a1.plot(env_t, env, lw=0.7, color="#555")
    a1.set_ylabel("audio onset")
    t = np.arange(len(diff)) / fps
    a2.plot(t, diff / (diff.max() or 1), lw=0.8, color="#1f5fa8")
    a2.set_ylabel("frame diff")
    for ax in (a1, a2):
        for b in beats:
            ax.axvline(b, color="#d33", lw=0.5, alpha=0.6)
        ax.set_xlim(0, res["duration_s"])
    for e in res["motion_onsets"]:
        a2.plot(e["t"], 1.02, "v", color="#1f5fa8", ms=5)
    for c in res["cuts"]:
        a2.axvline(c["t"], color="#111", lw=1.2, ls="--")
    a1.set_title(f"{Path(res['video']).name}: {g['bpm']:.2f} BPM (red = beat grid; black dashed = cuts; "
                 f"triangles = motion onsets)", fontsize=10)
    offs = [e["offset_ms"] for e in res["motion_onsets"]] + [c["offset_ms"] for c in res["cuts"]]
    half = g["period_s"] * 500
    a3.hist(offs, bins=np.linspace(-half, half, 41), color="#1f5fa8")
    a3.axvline(0, color="#d33")
    a3.set_xlabel("event offset from nearest beat (ms); negative = early")
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


# ---------- calibration ----------
def synth(path, bpm, visual_shift_s, dur=12.0, fps=30, sr=22050, seed=0):
    rng = np.random.default_rng(seed)
    period = 60 / bpm
    beats = np.arange(0.25, dur, period)
    y = 0.02 * rng.standard_normal(int(dur * sr)).astype(np.float32)
    click = np.sin(2 * np.pi * 1000 * np.arange(int(0.03 * sr)) / sr) * np.exp(-np.arange(int(0.03 * sr)) / (0.006 * sr))
    for b in beats:
        i = int(b * sr)
        y[i:i + len(click)] += 0.8 * click[: len(y) - i]
    w, h = 320, 180
    n = int(dur * fps)
    vid = np.full((n, h, w), 60, np.uint8)
    for b in beats:  # a white block appears on the beat and holds 4 frames
        f0 = int(np.ceil((b + visual_shift_s) * fps - 1e-9))
        vid[f0:f0 + 4, 40:140, 60:260] = 230
    with tempfile.TemporaryDirectory() as td:
        wav, raw = Path(td) / "a.f32", Path(td) / "v.raw"
        wav.write_bytes(y.astype(np.float32).tobytes())
        raw.write_bytes(vid.tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                        "-r", str(fps), "-i", str(raw), "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", str(wav),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", str(path)], check=True)
    return beats


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        cases = [("pos120", 120, 0.0), ("neg120_+100ms", 120, 0.1), ("pos129", 129, 0.0)]
        for name, bpm, shift in cases:
            p = Path(td) / f"{name}.mp4"
            synth(p, bpm, shift)
            res, _ = analyse(p)
            g = res["grid"]
            s = res["motion_onsets_summary"]
            bpm_ok = abs(g["bpm"] - bpm) <= 1.0
            # the visual block appears on the first frame at/after beat+shift: expected offset in [shift, shift+1 frame]
            exp_lo, exp_hi = shift * 1000 - 40, shift * 1000 + 1000 / 30 + 40
            off_ok = exp_lo <= s["median_ms"] <= exp_hi
            n_ok = s["n"] >= int(11.5 / (60 / bpm)) - 1
            print(f"{name}: bpm {g['bpm']:.2f} (want {bpm}) {'ok' if bpm_ok else 'FAIL'}; "
                  f"median offset {s['median_ms']:.1f} ms (want {exp_lo:.0f}..{exp_hi:.0f}) {'ok' if off_ok else 'FAIL'}; "
                  f"events {s['n']} {'ok' if n_ok else 'FAIL'}")
            ok &= bpm_ok and off_ok and n_ok
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--k", type=float, default=6.0)
    ap.add_argument("--min-gap", type=float, default=0.2)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    res, series = analyse(a.video, k=a.k, min_gap=a.min_gap)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "beatgrid.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    plot(res, series, out / "beatgrid.png")
    g = res["grid"]
    print(f"{g['bpm']:.2f} BPM (candidates {g['autocorr_candidates_bpm']}), phase {g['phase_s']:.3f}s")
    for key in ("motion_onsets", "motion_peaks", "cuts"):
        print(key, res[key + "_summary"])


if __name__ == "__main__":
    main()
