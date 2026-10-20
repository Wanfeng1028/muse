"""Which property of the music do the cuts follow? Cut times vs several music event streams.

The audio is decoded mono at 22.05 kHz. Event streams (all from the mix; no source separation):

    beat       beat grid from beatgrid.py (spectral-flux onset envelope, autocorrelation tempo 70-180 BPM,
               comb phase search)
    accent     strong onsets: peaks of the same onset envelope above its 90th percentile, >= 0.25 s apart
    energy     loudness change: RMS in dB per 50 ms, |mean(next 1 s) - mean(previous 1 s)|, peaks above
               the 90th percentile, >= 1.5 s apart
    structure  section boundaries: Foote (2000) checkerboard novelty on the cosine self-similarity of
               chroma + 12 cepstral coefficients at 0.25 s hop, kernel half-width 4 s (Gaussian taper),
               peaks above the 75th percentile, >= 4 s apart
    harmonic   harmonic change: Harte et al. (2006) HCDF, distance between successive tonal-centroid
               vectors (6-D, from chroma, Gaussian-smoothed sigma 0.4 s) at 0.1 s hop, peaks above the
               80th percentile, >= 0.5 s apart
    lines      line starts of a transcript .srt (lyric or dialogue lines), when given with --srt, or line
               start times from a JSON list with --lines

For each stream: dt = (cut - lag) - nearest stream event; statistic = the smallest median |dt| over a
constant lag in -0.15..+0.15 s (a detector's latency is unknown but fixed: beatgrid's grid sat 0.11 s
after the synthetic kicks, which hid a true beat lock in the first selftest run); control = the same
cuts each shifted by an independent uniform offset in +-3 s (1000 repetitions, fixed seed), with the
same lag search, p = share of shifted sets with a statistic at least as small (narrlock.py's control,
which absorbs stream density). Also
the share of cuts within +-0.25 s, the null's mean share, and the median signed dt of those close cuts
(negative = the cut comes before the music event). With six streams, `locked` means p < 0.05 / 6.

Calibration (selftest, a 64 s synthetic song: eight 8 s sections with different chords and timbres,
kick on every beat at 120 BPM, a loudness jump inside one section, a sine melody whose phrase starts sit
at a random phase of the beat; the phrase starts are given as --lines. A first version put every
phrase start half a beat off the grid: a constant phase IS beat-locked, and the tool said so): cuts at phrase starts (+-80 ms) must
lock to lines and not to beat; cuts on random beats must lock to beat and not to lines; cuts at the
seven section boundaries must lock to structure; uniformly random cuts must lock to nothing in at
least 4 of 5 seeds.

Real positive control (2026-10-04): C31's 21 scene boundaries are defined in its source code as "the last
beat at or before the first word of the anchor lyric line" (measurements/C31/code_boundaries.json, with
the 46 code lyric line starts as --lines) -> beat locked (median |dt| 7 ms after lag), accent locked,
lines locked (close cuts 0.085 s before the line start), energy and harmonic not; structure p 0.009
(just above 0.05/6). File: measurements/C31/cutdrivers_code.json.

The lines stream returns no p when it has no event within 20 s of at least 80 % of the cuts (a
transcript covering part of the song). Detector streams are computed over the whole film, so a sparse
one (few loudness changes) is still tested.

What it cannot determine: the streams are not independent (a section boundary is also a beat and
often an energy jump), so a cut set can lock to several; read the tightest p together with the
close-share. Melody and vocal phrases are NOT extracted from the mix (no separation): the lines stream
needs a transcript, and machine transcripts of singing are often empty or late (C33, C34). A stream
event is a detector's peak, not a musician's label. Lyric content (what a line says) is outside it.

Usage:
    python -X utf8 scripts/cutdrivers.py <video|audio> --events t1,t2,..|--segments seg.json
        [--srt lines.srt | --lines lines.json] [--skip-before S] --out <file.json>
    python -X utf8 scripts/cutdrivers.py --selftest
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.fft import dct
from scipy.ndimage import gaussian_filter1d

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import load_audio  # noqa: E402
from beatgrid import estimate_grid, onset_envelope  # noqa: E402
from narrlock import srt_starts  # noqa: E402

SR = 22050
SHIFT, REPS, CLOSE = 3.0, 1000, 0.25
COVER_S, COVER_MIN = 20.0, 0.8  # lines only: C32's 12-line transcript gave median |dt| 67 s; the guard
                                # first applied to every stream and silenced the sparse energy stream
LAGS = np.round(np.arange(-0.15, 0.151, 0.01), 2)
STREAMS = ("beat", "accent", "energy", "structure", "harmonic", "lines")


def peaks(x, t, pct, min_gap):
    thr = np.percentile(x, pct)
    cand = [i for i in range(1, len(x) - 1) if x[i] >= thr and x[i] >= x[i - 1] and x[i] > x[i + 1]]
    cand.sort(key=lambda i: -x[i])
    keep = []
    for i in cand:
        if all(abs(t[i] - t[j]) >= min_gap for j in keep):
            keep.append(i)
    return sorted(float(t[i]) for i in keep)


def spectrogram(y, nfft, hop):
    n = 1 + (len(y) - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(n)[:, None]
    mag = np.abs(np.fft.rfft(y[idx] * np.hanning(nfft)[None, :], axis=1))
    t = (np.arange(n) * hop + nfft / 2) / SR
    return mag, t


def chroma_of(mag, nfft):
    f = np.fft.rfftfreq(nfft, 1 / SR)
    ok = (f >= 55) & (f <= 2000)
    pc = (np.round(12 * np.log2(f[ok] / 440.0) + 69).astype(int)) % 12
    C = np.zeros((mag.shape[0], 12))
    for k in range(12):
        C[:, k] = (mag[:, ok][:, pc == k] ** 2).sum(axis=1)
    return C / (C.sum(axis=1, keepdims=True) + 1e-12)


def cepstrum_of(mag, nfft, n_mels=40, n_c=13):
    f = np.fft.rfftfreq(nfft, 1 / SR)
    mel = lambda x: 2595 * np.log10(1 + x / 700)  # noqa: E731
    edges = 700 * (10 ** (np.linspace(mel(40), mel(8000), n_mels + 2) / 2595) - 1)
    fb = np.zeros((n_mels, len(f)))
    for m in range(n_mels):
        lo, ce, hi = edges[m], edges[m + 1], edges[m + 2]
        fb[m] = np.clip(np.minimum((f - lo) / (ce - lo), (hi - f) / (hi - ce)), 0, None)
    logmel = np.log(mag ** 2 @ fb.T + 1e-10)
    return dct(logmel, type=2, norm="ortho", axis=1)[:, 1:n_c]


def tonal_centroid(C):
    """Harte et al. 2006: chroma -> 6-D tonal centroid (fifths, minor thirds, major thirds circles)."""
    l = np.arange(12)
    phi = np.stack([np.sin(l * 7 * np.pi / 6), np.cos(l * 7 * np.pi / 6),
                    np.sin(l * 3 * np.pi / 2), np.cos(l * 3 * np.pi / 2),
                    0.5 * np.sin(l * 2 * np.pi / 3), 0.5 * np.cos(l * 2 * np.pi / 3)])
    return C @ phi.T


def foote_novelty(F, half):
    F = F / (np.linalg.norm(F, axis=1, keepdims=True) + 1e-12)
    S = F @ F.T
    g = np.exp(-0.5 * (np.linspace(-2, 2, 2 * half)) ** 2)
    K = np.outer(g, g) * np.outer(np.r_[-np.ones(half), np.ones(half)], np.r_[-np.ones(half), np.ones(half)])
    n = len(F)
    nov = np.zeros(n)
    for i in range(half, n - half):
        nov[i] = (S[i - half:i + half, i - half:i + half] * K).sum()
    return np.maximum(nov, 0)


def music_streams(y, duration=None):
    out = {}
    env, env_t = onset_envelope(y, SR)
    grid = estimate_grid(env, env_t)
    out["beat"] = [float(t) for t in np.arange(grid["phase_s"], env_t[-1], grid["period_s"])]
    out["accent"] = peaks(env, env_t, 90, 0.25)
    hop = int(0.05 * SR)
    n = len(y) // hop
    rms = np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)
    L = 20 * np.log10(rms)
    tl = (np.arange(n) + 0.5) * hop / SR
    w = 20
    nov = np.zeros(n)
    for i in range(w, n - w):
        nov[i] = abs(L[i:i + w].mean() - L[i - w:i].mean())
    out["energy"] = peaks(nov, tl, 90, 1.5)
    mag, tt = spectrogram(y, 4096, int(0.1 * SR))
    C = chroma_of(mag, 4096)
    cep = cepstrum_of(mag, 4096)
    # structure at 0.25 s: average pairs of 0.1 s frames into 0.25 s blocks
    blk = 5
    m = len(C) // blk * blk
    Cb = C[:m].reshape(-1, blk, 12).mean(axis=1)
    Eb = cep[:m].reshape(-1, blk, cep.shape[1]).mean(axis=1)
    Eb = (Eb - Eb.mean(axis=0)) / (Eb.std(axis=0) + 1e-9)
    tb = tt[:m].reshape(-1, blk).mean(axis=1)
    feat = np.hstack([Cb * 3.4, Eb / np.sqrt(Eb.shape[1])])  # chroma and timbre at similar weight
    out["structure"] = peaks(foote_novelty(feat, int(4 / 0.5)), tb, 75, 4.0)
    T = gaussian_filter1d(tonal_centroid(C), 4, axis=0)
    hcdf = np.r_[0, np.linalg.norm(T[2:] - T[:-2], axis=1), 0]
    out["harmonic"] = peaks(hcdf, tt, 80, 0.5)
    return out, grid


def lock_test(cuts, stream, seed=0, guard=False):
    cuts = np.asarray(cuts, float)
    s = np.asarray(sorted(stream), float)
    if len(cuts) < 3 or len(s) < 2:
        return {"n": int(len(cuts)), "n_stream": int(len(s)), "p": None, "why": "too few events"}
    cover = float(np.mean(np.min(np.abs(cuts[:, None] - s[None, :]), axis=1) <= COVER_S))
    if guard and cover < COVER_MIN:
        return {"n": int(len(cuts)), "n_stream": int(len(s)), "p": None, "coverage": round(cover, 3),
                "why": f"stream covers only {cover:.0%} of the cuts (an event within {COVER_S:.0f} s); "
                       "a partial transcript cannot test the rest"}

    def nearest(c):
        k = np.clip(np.searchsorted(s, c), 1, len(s) - 1)
        left, right = s[k - 1], s[k]
        return np.where(np.abs(c - left) <= np.abs(c - right), c - left, c - right)

    def stat(c):
        """min over a constant lag of median |dt|: detector latency is unknown but fixed."""
        best, lag = np.inf, 0.0
        for g in LAGS:
            m = np.median(np.abs(nearest(c - g)))
            if m < best:
                best, lag = m, g
        return best, lag

    obs, lag = stat(cuts)
    dt = nearest(cuts - lag)
    rng = np.random.default_rng(seed)
    null = np.empty(REPS)
    close_null = np.empty(REPS)
    for r in range(REPS):
        sh = cuts + rng.uniform(-SHIFT, SHIFT, len(cuts))
        null[r], lg = stat(sh)
        close_null[r] = (np.abs(nearest(sh - lg)) <= CLOSE).mean()
    p = float((np.sum(null <= obs) + 1) / (REPS + 1))
    close = np.abs(dt) <= CLOSE
    return {"n": int(len(cuts)), "n_stream": int(len(s)), "median_abs_dt": round(float(obs), 3),
            "lag_s": round(float(lag), 2),
            "null_mean": round(float(null.mean()), 3), "p": round(p, 4),
            "close_share": round(float(close.mean()), 3), "close_share_null": round(float(close_null.mean()), 3),
            "close_signed_median": round(float(np.median(dt[close])), 3) if close.any() else None,
            "locked": bool(p < 0.05 / len(STREAMS))}


def analyse(media, cuts, lines=None, skip_before=0.0):
    y, sr = load_audio(media, sr=SR)
    streams, grid = music_streams(y)
    if lines is not None:
        streams["lines"] = sorted(lines)
    cuts = [c for c in cuts if c >= skip_before]
    tests = {k: lock_test(cuts, v, guard=(k == "lines")) for k, v in streams.items()}
    return {"media": str(media), "n_cuts": len(cuts), "bpm": round(grid["bpm"], 2),
            "stream_sizes": {k: len(v) for k, v in streams.items()},
            "tests": tests, "streams": {k: [round(t, 3) for t in v] for k, v in streams.items()},
            "limits": "streams from the mix, not independent; lines only from a transcript; "
                      "locked = p < 0.05/6 (shifted-cut control, +-3 s)"}


# ---------------------------------------------------------------- selftest

def synth_song(seed=0):
    rng = np.random.default_rng(seed)
    dur, bpm = 64.0, 120.0
    t = np.arange(int(dur * SR)) / SR
    y = np.zeros_like(t)
    roots = [220.0, 174.6, 261.6, 196.0, 233.1, 164.8, 293.7, 207.7]
    for s in range(8):
        a, b = s * 8.0, (s + 1) * 8.0
        m = (t >= a) & (t < b)
        amp = 0.12 * (1.6 if s == 5 else 1.0)
        for ratio in (1.0, 1.26, 1.5):
            f = roots[s] * ratio
            harm = (1,) if s % 2 == 0 else (1, 2, 3, 4)
            for h in harm:
                y[m] += amp / h * np.sin(2 * np.pi * f * h * t[m])
        if s == 2:  # loudness jump inside section 2 at 20 s
            y[(t >= 20.0) & (t < 24.0)] *= 2.2
    beat = 60 / bpm
    kick_t = np.arange(0, 0.12, 1 / SR)
    kick = np.sin(2 * np.pi * 60 * kick_t) * np.exp(-kick_t * 30) * 0.5
    for bt in np.arange(0, dur, beat):
        i = int(bt * SR)
        y[i:i + len(kick)] += kick[:len(y) - i]
    phrase_starts = []
    tcur = 1.31
    while tcur < dur - 3:
        phrase_starts.append(tcur)
        for k in range(4):  # one note per beat from the phrase start, soft attack
            a = tcur + k * beat
            m = (t >= a) & (t < a + 0.4)
            env = np.minimum(1, (t[m] - a) / 0.03)
            y[m] += 0.08 * env * np.sin(2 * np.pi * (440 * 2 ** (rng.integers(0, 7) / 12)) * t[m])
        nxt = beat * (int((tcur + beat * int(rng.integers(5, 9))) / beat))
        tcur = nxt + float(rng.uniform(0.1, beat - 0.1))  # phrase starts at a random phase of the beat
    return y.astype(np.float32), [round(p, 3) for p in phrase_starts], list(np.arange(0, dur, beat)), \
        [8.0 * k for k in range(1, 8)]


def selftest():
    ok = True
    y, lines, beats, bounds = synth_song()
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "s.wav"
        raw = Path(td) / "s.f32"
        raw.write_bytes(y.tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", str(raw),
                        str(wav)], check=True)
        yy, _ = load_audio(wav, sr=SR)
    streams, grid = music_streams(yy)
    streams["lines"] = lines
    print(f"synthetic song: bpm read {grid['bpm']:.1f} (truth 120); structure peaks "
          f"{[round(x, 1) for x in streams['structure']]} (truth {bounds})")
    rng = np.random.default_rng(1)

    def run(name, cuts, must, must_not):
        nonlocal ok
        res = {k: lock_test(cuts, v) for k, v in streams.items()}
        good = all(res[k].get("locked") for k in must) and not any(res[k].get("locked") for k in must_not)
        print(f"{name:34s} " + "  ".join(f"{k} p={res[k].get('p')}" for k in STREAMS)
              + f"  -> want locked {must}, not {must_not}: {'ok' if good else 'FAIL'}")
        ok &= good

    cut_lines = [l + rng.normal(0, 0.08) for l in lines]
    run("known-true cuts at phrase starts", cut_lines, ["lines"], ["beat"])
    cut_beats = sorted(rng.choice(beats[4:-4], 16, replace=False) + rng.normal(0, 0.02, 16))
    run("known-true cuts on random beats", cut_beats, ["beat"], ["lines"])
    run("known-true cuts at section bounds", [b + rng.normal(0, 0.1) for b in bounds], ["structure"], [])
    part = [l for l in lines if l < 16]
    r = lock_test(cut_lines, part, guard=True)
    good = r.get("p") is None and "covers" in r.get("why", "")
    print(f"known-false partial transcript (lines < 16 s only): p {r.get('p')} ({r.get('why')}) "
          f"-> want no p: {'ok' if good else 'FAIL'}")
    ok &= good
    fails = 0
    for seed in range(5):
        r2 = np.random.default_rng(100 + seed)
        cuts = sorted(r2.uniform(2, 62, 16))
        res = {k: lock_test(cuts, v, seed=seed) for k, v in streams.items()}
        anyl = [k for k in STREAMS if res[k].get("locked")]
        fails += bool(anyl)
        print(f"known-false random cuts seed {seed}: locked streams {anyl or 'none'}")
    good = fails <= 1
    print(f"random cuts lock to nothing in {5 - fails}/5 seeds (want >= 4) -> {'ok' if good else 'FAIL'}")
    ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media", nargs="?")
    ap.add_argument("--events")
    ap.add_argument("--segments")
    ap.add_argument("--srt")
    ap.add_argument("--lines")
    ap.add_argument("--skip-before", type=float, default=0.0)
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.events:
        cuts = [float(x) for x in a.events.split(",") if x.strip()]
    elif a.segments:
        seg = json.loads(Path(a.segments).read_text(encoding="utf-8"))
        cuts = [e["t"] if isinstance(e, dict) else float(e) for e in seg["events"]]
    else:
        ap.error("give --events or --segments")
    lines = None
    if a.srt:
        lines = srt_starts(Path(a.srt).read_text(encoding="utf-8", errors="replace"))
    elif a.lines:
        lines = json.loads(Path(a.lines).read_text(encoding="utf-8"))
    res = analyse(a.media, cuts, lines, a.skip_before)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"n cuts {res['n_cuts']}  bpm {res['bpm']}  streams {res['stream_sizes']}")
    for k, r in res["tests"].items():
        print(f"  {k:9s} p={r.get('p')} median|dt|={r.get('median_abs_dt')} (null {r.get('null_mean')}) "
              f"close {r.get('close_share')} (null {r.get('close_share_null')}) signed {r.get('close_signed_median')}"
              f"{'  LOCKED' if r.get('locked') else ''}")


if __name__ == "__main__":
    main()
