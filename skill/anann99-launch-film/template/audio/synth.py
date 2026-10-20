"""
Deterministic synth toolkit for launch-film scores.

Every generator takes an explicit `seed` (no shared global RNG), so a note
renders identically no matter the call order. All functions return float32
numpy arrays at SR: mono (n,) unless noted, stereo as (n, 2).

Requirements: numpy, scipy, pedalboard, soundfile, pyloudnorm, pillow
(e.g. python3 -m venv .venv && .venv/bin/pip install numpy scipy pedalboard soundfile pyloudnorm pillow).
BPM/BEAT/BAR below are defaults only; compose.py passes timing explicitly from score.json.
"""
from __future__ import annotations

import numpy as np
from scipy import signal
import pedalboard as pb

SR = 48000
BPM = 120
BEAT = 60.0 / BPM  # 0.5 s
BAR = BEAT * 4  # 2.0 s
TAU = 2 * np.pi
F32 = np.float32


def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(int(seed) & 0xFFFFFFFF)


def n_(dur: float) -> int:
    return int(round(dur * SR))


def t_(dur: float) -> np.ndarray:
    return np.arange(n_(dur)) / SR


def midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


NOTE = {n: i for i, n in enumerate(['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'])}


def n2m(name: str) -> int:
    """'A3' -> 57"""
    pitch, octv = name[:-1], int(name[-1])
    return 12 * (octv + 1) + NOTE[pitch]


def db(x: float) -> float:
    return 20 * np.log10(max(abs(x), 1e-12))


def undb(d: float) -> float:
    return 10 ** (d / 20)


# ---------------------------------------------------------------- envelopes / edges
def adsr(n: int, a=0.005, d=0.1, s=0.7, r=0.2, sus_len: float | None = None) -> np.ndarray:
    a_n, d_n, r_n = max(1, int(a * SR)), max(1, int(d * SR)), max(1, int(r * SR))
    s_n = max(0, n - a_n - d_n - r_n) if sus_len is None else int(sus_len * SR)
    env = np.concatenate([
        0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a_n, endpoint=False)),  # smooth attack
        np.linspace(1, s, d_n, endpoint=False),
        np.full(s_n, s),
        s * (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r_n))),  # smooth release to exactly 0
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n].astype(F32)


def exp_decay(n: int, tau: float) -> np.ndarray:
    return np.exp(-np.arange(n) / (tau * SR)).astype(F32)


def edge(x: np.ndarray, fi: float = 0.0005, fo: float = 0.006) -> np.ndarray:
    """Short raised-cosine fade-in/out so no one-shot starts or ends on a step."""
    x = np.array(x, dtype=F32, copy=True)
    n = len(x)
    if n == 0:
        return x
    a = min(n, max(1, int(fi * SR))) if fi > 0 else 0
    b = min(n, max(1, int(fo * SR))) if fo > 0 else 0
    if a:
        ra = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a, endpoint=False))).astype(F32)
        x[:a] *= ra[:, None] if x.ndim == 2 else ra
    if b:
        rb = (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, b))).astype(F32)
        x[-b:] *= rb[:, None] if x.ndim == 2 else rb
    return x


def norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = float(np.max(np.abs(x))) if len(x) else 0.0
    return (x * (peak / m)).astype(F32) if m > 0 else x.astype(F32)


def pan_st(x: np.ndarray, pan: float | np.ndarray = 0.0) -> np.ndarray:
    """Equal-power pan, unity at centre. pan may be per-sample."""
    p = np.clip(pan, -1, 1)
    l, r = np.cos((p + 1) * np.pi / 4) * np.sqrt(2), np.sin((p + 1) * np.pi / 4) * np.sqrt(2)
    return np.stack([x * l, x * r], 1).astype(F32)


# ---------------------------------------------------------------- oscillators
def phase(freq, n: int, ph0: float = 0.0) -> np.ndarray:
    """Phase in cycles (unwrapped), float64; freq scalar or per-sample."""
    f = np.broadcast_to(np.asarray(freq, np.float64), (n,))
    return ph0 + np.concatenate([[0.0], np.cumsum(f[:-1])]) / SR


def sine(freq, n: int, ph0: float = 0.0) -> np.ndarray:
    return np.sin(TAU * phase(freq, n, ph0)).astype(F32)


def blsaw(freq, n: int, ph0: float = 0.0) -> np.ndarray:
    """PolyBLEP band-limited sawtooth."""
    f = np.broadcast_to(np.asarray(freq, np.float64), (n,))
    dt = f / SR
    ph = phase(f, n, ph0) % 1.0
    y = 2.0 * ph - 1.0
    m = ph < dt
    tt = ph[m] / dt[m]
    y[m] -= tt + tt - tt * tt - 1.0
    m = ph > 1.0 - dt
    tt = (ph[m] - 1.0) / dt[m]
    y[m] -= tt * tt + tt + tt + 1.0
    return y.astype(F32)


# ---------------------------------------------------------------- filters
def _sos(kind, f, order):
    if kind == 'band':
        lo, hi = f
        return signal.butter(order, [lo, min(hi, SR * 0.45)], 'band', fs=SR, output='sos')
    return signal.butter(order, min(f, SR * 0.45), kind, fs=SR, output='sos')


def lp(x, fc, order=2):
    return signal.sosfilt(_sos('low', fc, order), x, axis=0).astype(F32)


def hp(x, fc, order=2):
    return signal.sosfilt(_sos('high', fc, order), x, axis=0).astype(F32)


def bp(x, lo, hi, order=2):
    return signal.sosfilt(_sos('band', (lo, hi), order), x, axis=0).astype(F32)


_LMODE = {'lpf24': pb.LadderFilter.Mode.LPF24, 'lpf12': pb.LadderFilter.Mode.LPF12,
          'bpf12': pb.LadderFilter.Mode.BPF12, 'hpf12': pb.LadderFilter.Mode.HPF12,
          'bpf24': pb.LadderFilter.Mode.BPF24, 'hpf24': pb.LadderFilter.Mode.HPF24}


def ladder(x: np.ndarray, cutoff, res: float = 0.1, drive: float = 1.0, mode: str = 'lpf24',
           chunk: int = 256) -> np.ndarray:
    """Moog-style ladder filter (pedalboard). `cutoff` = Hz scalar or per-sample array
    (time-varying: block-updated with filter state carried across blocks)."""
    st = x.ndim == 2
    data = np.ascontiguousarray((x.T if st else x[None, :]).astype(F32))
    n = data.shape[1]
    lf = pb.LadderFilter(mode=_LMODE[mode], cutoff_hz=200.0, resonance=res, drive=drive)
    if np.isscalar(cutoff):
        lf.cutoff_hz = float(np.clip(cutoff, 20, SR * 0.45))
        out = lf.process(data, SR)
    else:
        cut = np.asarray(cutoff, np.float64)
        out = np.zeros_like(data)
        for i in range(0, n, chunk):
            lf.cutoff_hz = float(np.clip(cut[min(i + chunk // 2, n - 1)], 20, SR * 0.45))
            out[:, i:i + chunk] = lf.process(data[:, i:i + chunk], SR, reset=(i == 0))
    out = out.astype(F32)
    return out.T.copy() if st else out[0].copy()


def exp_curve(n: int, a: float, b: float, shape: float = 1.0) -> np.ndarray:
    """Exponential glide a->b over n samples (shape>1 = late, <1 = early)."""
    u = np.linspace(0, 1, n) ** shape
    return a * (b / a) ** u


# ---------------------------------------------------------------- tonal instruments
def supersaw(notes, dur, seed=0, detune=0.14, voices=6, attack=0.6, decay=0.3, sustain=0.9,
             release=1.2, width=0.8, drift=0.0012) -> np.ndarray:
    """Detuned band-limited saw stack, voices spread across the stereo field. Unfiltered,
    (n, 2). Filter with `ladder` afterwards."""
    n = n_(dur)
    r = rng(seed)
    t = np.arange(n) / SR
    L = np.zeros(n, np.float64)
    R = np.zeros(n, np.float64)
    for m in notes:
        for v in range(voices):
            x = (v / (voices - 1)) * 2 - 1 if voices > 1 else 0.0
            f0 = midi_hz(m + x * detune)
            f = f0 * (1 + drift * np.sin(TAU * (0.07 + 0.25 * r.random()) * t + TAU * r.random()))
            s = blsaw(f, n, r.random())
            p = x * width
            L += s * np.cos((p + 1) * np.pi / 4)
            R += s * np.sin((p + 1) * np.pi / 4)
    env = adsr(n, a=attack, d=decay, s=sustain, r=release)
    g = np.sqrt(2) / np.sqrt(len(notes) * voices)
    return (np.stack([L, R], 1) * env[:, None] * g).astype(F32)


_CACHE: dict = {}


def pluck(midi, dur=0.5, bright=0.5, decay=0.4, seed=0) -> np.ndarray:
    """Additive pluck: harmonic partials whose decay grows with frequency (a filter-envelope
    pluck without aliasing). Peak-normalised, mono."""
    key = ('pluck', midi, round(dur, 3), round(bright, 3), round(decay, 3))
    if key in _CACHE:
        return _CACHE[key]
    f = midi_hz(midi)
    n = n_(dur)
    t = np.arange(n) / SR
    fmax = min(15000.0, 900 + 8000 * bright ** 1.4)
    K = max(1, int(fmax // f))
    tilt = 1.0 + (1.0 - bright) * 0.8
    y = np.zeros(n)
    for k in range(1, K + 1):
        fk = f * k
        a = (1.0 / k ** tilt) / (1 + (fk / fmax) ** 4)
        dk = 1.0 / decay + (fk / 1000.0) * (1.5 + 9.0 * (1.0 - bright))
        m = min(n, int(9.0 / dk * SR) + 1)
        y[:m] += a * np.sin(TAU * fk * t[:m]) * np.exp(-dk * t[:m])
    y = edge(norm(y), 0.0015, 0.01)
    _CACHE[key] = y
    return y


def bell(midi, dur=2.5, ratio=3.5, index=1.3, idx_decay=0.15, decay=0.9, partial2=0.12, seed=0) -> np.ndarray:
    """2-op FM bell. ratio 3.5 = glassy/inharmonic, 2.0 = soft mallet."""
    key = ('bell', midi, round(dur, 3), ratio, index, idx_decay, decay, partial2)
    if key in _CACHE:
        return _CACHE[key]
    f = midi_hz(midi)
    n = n_(dur)
    t = np.arange(n) / SR
    I = index * np.exp(-t / idx_decay)
    x = np.sin(TAU * f * t + I * np.sin(TAU * f * ratio * t)) * np.exp(-t / decay)
    x += partial2 * np.sin(TAU * f * 2.0 * 1.0013 * t) * np.exp(-t / (decay * 0.35))
    y = edge(norm(x), 0.0012, 0.02)
    _CACHE[key] = y
    return y


def keys(midi, dur=2.0, vel=0.8, seed=0) -> np.ndarray:
    """FM electric-piano tone (warm body + short tine)."""
    key = ('keys', midi, round(dur, 3), round(vel, 2))
    if key in _CACHE:
        return _CACHE[key]
    f = midi_hz(midi)
    n = n_(dur)
    t = np.arange(n) / SR
    dec = 1.9 * (261.6 / f) ** 0.35
    I = (0.5 + 1.2 * vel) * np.exp(-t / 0.3) + 0.2
    body = np.sin(TAU * f * t + I * np.sin(TAU * f * t)) * np.exp(-t / dec)
    tr = min(14.0, 8000.0 / f)
    tine = np.sin(TAU * f * t + 1.6 * np.exp(-t / 0.012) * np.sin(TAU * f * tr * t)) * np.exp(-t / 0.14) * 0.22 * vel
    x = body + tine
    x *= adsr(n, a=0.003, d=0.05, s=1.0, r=min(0.4, dur * 0.3))
    y = edge(norm(x), 0.001, 0.01)
    _CACHE[key] = y
    return y


def sub_bass(midi, dur, drive=1.3, harm=0.18, attack=0.006, release=0.06) -> np.ndarray:
    f = midi_hz(midi)
    n = n_(dur)
    x = sine(f, n) + harm * sine(2 * f, n, 0.12)
    x = np.tanh(drive * x) / np.tanh(drive)
    return (x * adsr(n, a=attack, d=0.1, s=0.92, r=release)).astype(F32)


def heartbeat(midi=33, dur=0.7, seed=0) -> np.ndarray:
    f = midi_hz(midi)
    n = n_(dur)
    t = np.arange(n) / SR
    fi = f * (1 + 0.9 * np.exp(-t / 0.025))
    x = np.sin(TAU * phase(fi, n)) * np.where(t < 0.025, 1.0, np.exp(-(t - 0.025) / 0.16))
    x += 0.25 * np.sin(TAU * phase(2 * fi, n)) * np.exp(-t / 0.06)
    x = np.tanh(1.6 * x) / np.tanh(1.6)
    return edge(lp(x, 400, 2), 0.001, 0.03)


# ---------------------------------------------------------------- drums
HAT_F = np.array([205.3, 304.4, 369.6, 522.7, 540.0, 800.0])


def _metal(n, seed, mult=1.0):
    r = rng(seed)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f in HAT_F * mult * (1 + 0.01 * r.standard_normal(6)):
        x += np.sign(np.sin(TAU * f * t + TAU * r.random()))
    return x / 6


def kick(seed=1, f0=150, f1=46, pitch_tau=0.03, decay=0.22, hold=0.025, click=0.3, dur=0.42, drive=1.7):
    n = n_(dur)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / pitch_tau)
    env = np.where(t < hold, 1.0, np.exp(-(t - hold) / decay))
    body = np.sin(TAU * phase(f, n)) * env
    nz = bp(rng(seed).standard_normal(n), 1800, 9000) * np.exp(-t / 0.0022) * click
    beater = np.sin(TAU * 1100 * t) * np.exp(-t / 0.005) * 0.12
    x = np.tanh(drive * (body + nz + beater)) / np.tanh(drive)
    return edge(x, 0.0, 0.012)


def snare(seed=2, tone=190, dur=0.32, snappy=1.0, body=0.6):
    n = n_(dur)
    t = np.arange(n) / SR
    r = rng(seed)
    fi = tone * (1 + 0.6 * np.exp(-t / 0.008))
    b = (np.sin(TAU * phase(fi, n)) * np.exp(-t / 0.045) + 0.5 * np.sin(TAU * phase(fi * 1.62, n)) * np.exp(-t / 0.03))
    nz = bp(r.standard_normal(n), 1500, 9500) * np.exp(-t / 0.085) * snappy
    x = np.tanh(1.3 * (body * b + nz))
    return edge(norm(x), 0.0003, 0.02)


def clap(seed=3, dur=0.38):
    n = n_(dur)
    r = rng(seed)
    noise = r.standard_normal(n)
    env = np.zeros(n)
    for k, off in enumerate([0.0, 0.010, 0.021]):
        i = int(off * SR)
        env[i:] += np.exp(-np.arange(n - i) / ((0.0055 if k < 2 else 0.075) * SR)) * (0.75 if k < 2 else 1.0)
    x = bp(noise * env, 850, 6500)
    t = np.arange(n) / SR
    x += 0.25 * np.sin(TAU * 230 * t) * np.exp(-t / 0.03)  # a touch of body
    return edge(norm(x), 0.0003, 0.02)


def hat(seed=4, open_=False, dur=None):
    dur = dur or (0.24 if open_ else 0.07)
    n = n_(dur)
    t = np.arange(n) / SR
    m = _metal(n, seed, 1.0)
    x = bp(m, 7000, 13000, 2) * 0.8 + hp(rng(seed + 99).standard_normal(n), 8500, 2) * 0.35
    x *= np.exp(-t / (0.085 if open_ else 0.016))
    return edge(norm(x), 0.0002, 0.012)


def crash(seed=5, dur=2.6, decay=0.85):
    n = n_(dur)
    t = np.arange(n) / SR
    chans = []
    for c in range(2):
        m = _metal(n, seed * 7 + c, 2.15)
        nz = rng(seed * 13 + c).standard_normal(n)
        x = bp(m * 0.55 + nz * 0.6, 3800, 15000, 2)
        x *= np.where(t < 0.002, t / 0.002, 1.0) * (0.55 * np.exp(-t / decay) + 0.45 * np.exp(-t / 0.12))
        chans.append(x)
    return edge(norm(np.stack(chans, 1)), 0.0002, 0.05)


def reverse_cymbal(dur=1.0, seed=6):
    c = crash(seed, dur=max(dur, 0.1) + 0.05, decay=dur * 0.45)[: n_(dur)][::-1]
    return edge(np.ascontiguousarray(c), 0.01, 0.0015)


# ---------------------------------------------------------------- UI / sound design
def tick(freq=2600, dur=0.05, seed=0, tau=0.009, noise=0.35):
    n = n_(dur)
    t = np.arange(n) / SR
    x = np.sin(TAU * freq * t) * np.exp(-t / tau) + 0.45 * np.sin(TAU * freq * 1.51 * t) * np.exp(-t / (tau * 0.45))
    x += noise * hp(rng(seed).standard_normal(n), 5000) * np.exp(-t / 0.0012)
    return edge(norm(x), 0.0002, 0.008)


def blip(midi, dur=0.22, drop=0.6, tau=0.055, seed=0):
    f = midi_hz(midi)
    n = n_(dur)
    t = np.arange(n) / SR
    fi = f * (1 + drop * np.exp(-t / 0.006))
    x = np.sin(TAU * phase(fi, n)) * np.exp(-t / tau) + 0.22 * np.sin(TAU * phase(2 * fi, n)) * np.exp(-t / (tau * 0.4))
    return edge(norm(x), 0.0004, 0.012)


def mouse_click(seed=0):
    n = n_(0.11)
    t = np.arange(n) / SR
    r = rng(seed)
    x = np.zeros(n)
    for off, g, fr in ((0.0, 1.0, 3200), (0.046, 0.45, 3900)):
        i = int(off * SR)
        tt = t[: n - i]
        x[i:] += g * (bp(r.standard_normal(n - i), 1800, 8000)[: n - i] * np.exp(-tt / 0.0011)
                      + 0.5 * np.sin(TAU * fr * tt) * np.exp(-tt / 0.0025))
    return edge(norm(x), 0.0001, 0.01)


def stamp(seed=0, dur=0.5):
    n = n_(dur)
    t = np.arange(n) / SR
    r = rng(seed)
    fi = 65 + 110 * np.exp(-t / 0.014)
    thump = np.sin(TAU * phase(fi, n)) * np.exp(-t / 0.085)
    slap = bp(r.standard_normal(n), 300, 2600) * np.exp(-t / 0.018) * 0.8
    crisp = hp(r.standard_normal(n), 3000) * np.exp(-t / 0.0035) * 0.35
    x = np.tanh(1.5 * (thump + slap + crisp))
    return edge(norm(x), 0.0002, 0.03)


def thunk(f0=98, dur=0.3, seed=0):
    n = n_(dur)
    t = np.arange(n) / SR
    fi = f0 * (1 + 0.8 * np.exp(-t / 0.018))
    x = np.sin(TAU * phase(fi, n)) * np.exp(-t / 0.085)
    x += lp(rng(seed).standard_normal(n), 900) * np.exp(-t / 0.014) * 0.5
    x = lp(np.tanh(1.4 * x), 1400, 2)
    return edge(norm(x), 0.0004, 0.03)


def whoosh(rise=0.35, fall=0.3, f_lo=350, f_hi=6000, seed=0, pan_from=-0.6, pan_to=0.6, res=0.3,
           accent=0.5):
    """Band-swept noise whoosh whose peak (plus a tiny transient accent) sits exactly `rise` seconds
    in. Returns ((n,2) stereo, peak_offset_seconds)."""
    n = n_(rise + fall)
    pk = n_(rise)
    t = np.arange(n) / SR
    r = rng(seed)
    noise = r.standard_normal(n).astype(F32)
    cut = np.concatenate([exp_curve(pk, f_lo, f_hi, 1.3), exp_curve(n - pk, f_hi, f_lo * 1.5, 0.6)])
    y = ladder(noise, cut, res=res, mode='bpf12') * 1.0 + ladder(noise, cut * 1.7, res=0.0, mode='lpf12') * 0.35
    env = np.where(t < rise, (t / rise) ** 2.4, np.exp(-(t - rise) / (fall * 0.3)))
    y = y * env
    acc = np.zeros(n)
    acc[pk:] = hp(r.standard_normal(n - pk), 2500) * np.exp(-(t[pk:] - rise) / 0.0035)
    y = norm(y) + accent * norm(acc)
    p = np.interp(t, [0, rise, rise + fall], [pan_from, (pan_from + pan_to) / 2, pan_to])
    return edge(pan_st(norm(y), p), 0.002, 0.01), pk / SR


def downlifter(dur=1.6, seed=0, f0=9000, f1=180):
    n = n_(dur)
    t = np.arange(n) / SR
    chans = []
    for c in range(2):
        nz = rng(seed * 3 + c).standard_normal(n).astype(F32)
        y = ladder(nz, exp_curve(n, f0, f1, 0.5), res=0.25, mode='lpf24')
        chans.append(y * np.exp(-t / (dur * 0.3)))
    return edge(norm(np.stack(chans, 1)), 0.0005, 0.05)


def riser(dur=1.75, seed=0, f0=250, f1=9500, pitch0=45, pitch1=69):
    """Noise sweep + gliding filtered saw. Stereo; ends at full level (caller cuts)."""
    n = n_(dur)
    t = np.arange(n) / SR
    cut = exp_curve(n, f0, f1, 1.2)
    chans = []
    for c in range(2):
        nz = rng(seed * 5 + c).standard_normal(n).astype(F32)
        chans.append(ladder(nz, cut, res=0.35, mode='lpf24'))
    st = np.stack(chans, 1)
    fglide = midi_hz(pitch0) * 2 ** ((pitch1 - pitch0) / 12 * (t / dur) ** 1.3)
    tone = ladder(blsaw(fglide, n) + blsaw(fglide * 1.006, n, 0.3), cut * 0.6, res=0.2, mode='lpf24')
    st = norm(st) + 0.35 * pan_st(norm(tone))[:, :]
    env = (t / dur) ** 2.2
    return edge(norm(st * env[:, None]), 0.003, 0.003)


def impact(seed=0, dur=3.0, size=1.0, f_hi=115, f_lo=33, crack=0.6):
    n = n_(dur)
    t = np.arange(n) / SR
    fi = f_lo + (f_hi - f_lo) * np.exp(-t / 0.07)
    boom = np.sin(TAU * phase(fi, n)) * np.exp(-t / (0.6 * size))
    body = bp(rng(seed).standard_normal(n), 70, 450) * np.exp(-t / (0.22 * size)) * 0.45
    low = np.tanh(1.4 * (boom + body)) / np.tanh(1.4)
    chans = []
    for c in range(2):
        cr = lp(rng(seed * 11 + c).standard_normal(n), 5500) * np.exp(-t / 0.032) * crack
        chans.append(low + cr)
    return edge(norm(np.stack(chans, 1)), 0.0003, 0.05)


def shimmer(notes, dur=4.0, seed=0):
    """High FM-bell cluster + airy noise, stereo."""
    n = n_(dur)
    t = np.arange(n) / SR
    L = np.zeros(n)
    R = np.zeros(n)
    for i, m in enumerate(notes):
        b = bell(m, dur, ratio=3.5, index=0.9, idx_decay=0.4, decay=dur * 0.45, partial2=0.05)
        trem = 1 + 0.25 * np.sin(TAU * (4.5 + i) * t + i)
        p = -0.7 + 1.4 * i / max(1, len(notes) - 1)
        L += b * trem * np.cos((p + 1) * np.pi / 4)
        R += b * trem * np.sin((p + 1) * np.pi / 4)
    air = np.stack([hp(rng(seed + c).standard_normal(n), 7000, 2) for c in range(2)], 1)
    air *= (np.minimum(t / 0.03, 1) * np.exp(-t / (dur * 0.3)))[:, None] * 0.25
    st = np.stack([L, R], 1)
    return edge(norm(norm(st) + air), 0.001, 0.08)


# ---------------------------------------------------------------- legacy names (v1 kit)
def fm_bell(midi, dur=2.5, ratio=3.5, index=2.2):
    return bell(midi, dur, ratio=ratio, index=index)


def sidechain_env(n_total: int, hits, depth=0.6, release=0.22, attack=0.003) -> np.ndarray:
    """Kick-ducking gain curve: a short raised-cosine dip (no step -> no click) that recovers
    over `release` seconds."""
    env = np.ones(n_total, F32)
    a = max(1, int(attack * SR))
    rel = int(release * SR)
    down = 1 - depth * (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a)))
    u = np.linspace(0, 1, rel)
    up = 1 - depth * (1 - u) ** 2.2
    curve = np.concatenate([down, up]).astype(F32)
    for h in hits:
        i = int(round(h * SR)) - a + 1
        j = min(n_total, i + len(curve))
        if i < 0:
            continue
        env[i:j] = np.minimum(env[i:j], curve[: j - i])
    return env


class Track:
    """Stereo accumulation buffer with time-based placement (sample-accurate)."""

    def __init__(self, dur: float):
        self.buf = np.zeros((n_(dur), 2), F32)

    def add(self, x: np.ndarray, at: float, gain: float = 1.0, pan: float = 0.0):
        i = int(round(at * SR))
        if x.ndim == 1:
            x = pan_st(x, pan)
        if i < 0:
            x, i = x[-i:], 0
        if i >= len(self.buf):
            return
        j = min(len(self.buf), i + len(x))
        self.buf[i:j] += x[: j - i] * gain
