"""DSP primitives.

Every sound in xlaudio is computed from math: oscillators, FM operators,
additive oscillator banks, filtered noise, envelopes and synthetic impulse
responses. No samples, sound fonts, MIDI sound sources, downloaded audio or AI
audio services are used anywhere in the package.

Ported from the "在我开口之前 / BEFORE I SPEAK" score synthesiser (dsp.py) and
made reusable: nothing in here knows about a particular film.

Conventions
-----------
* sample rate: 48 kHz (``SR``), float64 internally
* stereo buffers are channel-first, shape ``(2, n)``; mono buffers are ``(n,)``
* time arguments are seconds, frequencies Hz, levels dB unless stated otherwise
"""
from functools import lru_cache

import numpy as np
from numba import njit, prange
from scipy import signal

SR = 48000
TWOPI = 2.0 * np.pi


# ----------------------------------------------------------------------------
# time / pitch helpers
# ----------------------------------------------------------------------------
def smp(t, sr=SR):
    """seconds -> sample index (rounded)."""
    return int(round(t * sr))


_NOTE_OFS = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def midi(name):
    """'A5', 'Bb2', 'C#6', 'F#3' -> MIDI number (C4 = 60). Ints pass through."""
    if isinstance(name, (int, np.integer)):
        return int(name)
    if isinstance(name, (float, np.floating)):
        return float(name)
    letter = name[0].upper()
    i = 1
    acc = 0
    while i < len(name) and name[i] in '#b':
        acc += 1 if name[i] == '#' else -1
        i += 1
    octave = int(name[i:])
    return 12 * (octave + 1) + _NOTE_OFS[letter] + acc


def hz(m):
    """note name or MIDI number (float allowed) -> Hz (A4 = 440)."""
    mm = midi(m)
    if not -24 <= mm <= 135:
        raise ValueError('MIDI note %r out of range -- a frequency passed where a note was expected?' % (m,))
    return 440.0 * 2.0 ** ((mm - 69) / 12.0)


def semis(x):
    """frequency ratio for x semitones."""
    return 2.0 ** (x / 12.0)


def pan_gains(p):
    """constant-power pan, p in [-1, 1] (scalar or array); centre = -3 dB."""
    p = np.clip(p, -1.0, 1.0)
    th = (p + 1.0) * np.pi / 4.0
    return np.cos(th), np.sin(th)


def stereo(x, pan=0.0):
    """mono -> stereo with the constant-power law (centre = -3 dB per side)."""
    gl, gr = pan_gains(pan)
    return np.vstack([x * gl, x * gr])


def dual_mono(x):
    """mono -> stereo, both channels = x (unity at centre)."""
    return np.vstack([x, x])


def pan_st(y, p):
    """constant-power pan/balance of a stereo buffer, unity at p = 0.

    Gains are sqrt(2)*cos / sqrt(2)*sin of (p+1)*pi/4, so the summed power of a
    dual-mono source is the same at every position (hard side = +3 dB on one
    channel, 0 on the other)."""
    if np.isscalar(p) and p == 0:
        return y
    gl, gr = pan_gains(p)
    return np.vstack([y[0] * gl * np.sqrt(2.0), y[1] * gr * np.sqrt(2.0)])


def rc_ramp(n):
    """raised-cosine ramp 0 -> 1 over n samples (length n)."""
    if n <= 0:
        return np.ones(0)
    return 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)


def fade_edges(y, fade_in=0.0005, fade_out=0.004, sr=SR):
    """raised-cosine fade in / out (in place on a copy); last sample becomes 0."""
    y = np.array(y, dtype=np.float64, copy=True)
    n = y.shape[-1]
    ni = min(n, max(1, int(round(fade_in * sr))))
    no = min(n, max(1, int(round(fade_out * sr))))
    y[..., :ni] *= rc_ramp(ni)
    y[..., n - no:] *= rc_ramp(no)[::-1]
    y[..., -1] = 0.0
    return y


def noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def db2lin(db):
    return 10.0 ** (np.asarray(db) / 20.0)


def lin2db(x):
    return 20.0 * np.log10(np.maximum(np.abs(x), 1e-12))


# ----------------------------------------------------------------------------
# envelopes
# ----------------------------------------------------------------------------
def env_perc(n, att, tau, tail=0.006, sr=SR):
    """raised-cosine attack (att s), exponential decay (tau s), faded tail."""
    t = np.arange(n) / sr
    e = np.exp(-np.maximum(t - att, 0.0) / tau)
    na = max(1, int(att * sr))
    e[:na] *= rc_ramp(na)
    nt = min(n, max(1, int(tail * sr)))
    e[n - nt:] *= rc_ramp(nt)[::-1]
    return e


def env_asr(n, att, rel_start, rel_tau, rel_len, sr=SR):
    """attack -> hold 1 -> release starting at rel_start (s): exp(tau) x taper."""
    t = np.arange(n) / sr
    e = np.ones(n)
    na = min(n, max(1, int(att * sr)))
    e[:na] = rc_ramp(na)
    rs = int(rel_start * sr)
    if rs < n:
        tr = t[rs:] - t[rs]
        taper = np.clip(1.0 - tr / rel_len, 0.0, 1.0)
        taper = 0.5 - 0.5 * np.cos(np.pi * taper)
        e[rs:] *= np.exp(-tr / rel_tau) * taper
    return e


def att_curve(t, a):
    """raised-cosine attack factor as a function of a time array t."""
    if a <= 0:
        return np.ones_like(t)
    return np.where(t < a, 0.5 - 0.5 * np.cos(np.pi * np.clip(t / a, 0, 1)), 1.0)


def bp_curve(points, tgrid, log=False):
    """piecewise-linear breakpoint curve sampled on tgrid; log=True interpolates
    in the log domain (for frequencies)."""
    pts = np.array(points, dtype=float)
    xs, ys = pts[:, 0], pts[:, 1]
    if log:
        return np.exp(np.interp(tgrid, xs, np.log(ys)))
    return np.interp(tgrid, xs, ys)


# ----------------------------------------------------------------------------
# static filters (scipy, sos)
# ----------------------------------------------------------------------------
def lp(x, fc, order=2, sr=SR):
    sos = signal.butter(order, min(fc, 0.45 * sr), 'low', fs=sr, output='sos')
    return signal.sosfilt(sos, x, axis=-1)


def hp(x, fc, order=2, sr=SR):
    sos = signal.butter(order, fc, 'high', fs=sr, output='sos')
    return signal.sosfilt(sos, x, axis=-1)


def bpf(x, f_lo, f_hi, order=2, sr=SR):
    sos = signal.butter(order, [f_lo, min(f_hi, 0.45 * sr)], 'band', fs=sr, output='sos')
    return signal.sosfilt(sos, x, axis=-1)


def lp0(x, fc, order=2, sr=SR):
    """zero-phase lowpass."""
    sos = signal.butter(order, fc, 'low', fs=sr, output='sos')
    return signal.sosfiltfilt(sos, x, axis=-1)


def hp0(x, fc, order=2, sr=SR):
    """zero-phase highpass."""
    sos = signal.butter(order, fc, 'high', fs=sr, output='sos')
    return signal.sosfiltfilt(sos, x, axis=-1)


def dc_block(x, fc=12.0):
    """causal 2nd-order 12 Hz high-pass: removes DC without touching the attack."""
    return hp(x, fc, 2)


def rbj(kind, f0, q=0.707, gain_db=0.0, sr=SR):
    """RBJ cookbook biquad -> (b, a)."""
    A = 10 ** (gain_db / 40.0)
    w0 = TWOPI * f0 / sr
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2 * q)
    if kind == 'peak':
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == 'lowshelf':
        sa = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + sa), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sa)]
        a = [(A + 1) + (A - 1) * cw + sa, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sa]
    elif kind == 'highshelf':
        sa = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + sa), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sa)]
        a = [(A + 1) - (A - 1) * cw + sa, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sa]
    elif kind == 'bp':
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    else:
        raise ValueError(kind)
    b = np.array(b) / a[0]
    a = np.array(a) / a[0]
    return b, a


def eq(x, kind, f0, q=0.707, gain_db=0.0):
    b, a = rbj(kind, f0, q, gain_db)
    return signal.lfilter(b, a, x, axis=-1)


def apply_eq(x, chain):
    """chain items: ('hp', f) ('lp', f) ('peak', f, q, dB) ('hs', f, q, dB) ('ls', f, q, dB)."""
    for item in chain:
        kind, f = item[0], item[1]
        if kind == 'hp':
            x = hp(x, f, 2)
        elif kind == 'lp':
            x = lp(x, f, 2)
        elif kind == 'peak':
            x = eq(x, 'peak', f, item[2], item[3])
        elif kind == 'hs':
            x = eq(x, 'highshelf', f, item[2], item[3])
        elif kind == 'ls':
            x = eq(x, 'lowshelf', f, item[2], item[3])
        else:
            raise ValueError(kind)
    return x


# ----------------------------------------------------------------------------
# time-varying state-variable filter (TPT / Zavalishin), numba
# ----------------------------------------------------------------------------
@njit(cache=True)
def _svf_tv(x, fc, q, mode, sr):
    n = x.shape[0]
    y = np.zeros(n)
    ic1 = 0.0
    ic2 = 0.0
    k = 1.0 / q
    for i in range(n):
        f = fc[i]
        if f > 0.45 * sr:
            f = 0.45 * sr
        g = np.tan(np.pi * f / sr)
        a1 = 1.0 / (1.0 + g * (g + k))
        a2 = g * a1
        a3 = g * a2
        v3 = x[i] - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        if mode == 0:
            y[i] = v2                      # lowpass
        elif mode == 1:
            y[i] = k * v1                  # bandpass, unity peak
        else:
            y[i] = x[i] - k * v1 - v2      # highpass
    return y


def svf(x, fc, q=0.707, mode='lp'):
    """time-varying SVF; fc may be a scalar or a per-sample array."""
    m = {'lp': 0, 'bp': 1, 'hp': 2}[mode]
    fc = np.broadcast_to(np.asarray(fc, dtype=np.float64), x.shape).copy()
    return _svf_tv(np.ascontiguousarray(x, dtype=np.float64), fc, float(q), m, float(SR))


# ----------------------------------------------------------------------------
# oversampled FM operators (alias-safe)
# ----------------------------------------------------------------------------
_FIR = {}


def _decim_fir(os):
    """linear-phase anti-alias FIR for decimation by os (passband to 20 kHz,
    stopband from ~26 kHz, > 90 dB)."""
    if os not in _FIR:
        ntap = {2: 159, 4: 319}[os]
        fs_os = SR * os
        _FIR[os] = signal.firwin(ntap, 22000.0, window=('kaiser', 9.0), fs=fs_os)
    return _FIR[os]


def decimate(y, os):
    if os == 1:
        return y
    return signal.resample_poly(y, 1, os, window=_decim_fir(os), axis=-1)


def upsample(y, os):
    if os == 1:
        return y
    return signal.resample_poly(y, os, 1, window=_decim_fir(os), axis=-1)


def fm2(dur, fc, ratio, I_fn, A_fn, os=2, mod_fixed=None, pm_fn=None, phase=0.0):
    """two-operator FM: A(t) * sin(2pi fc t + I(t) sin(2pi fm t)).
    fm = fc*ratio (or mod_fixed Hz). Rendered at os x SR then decimated.
    pm_fn optional pitch multiplier curve (vibrato/glide) as callable(t)."""
    n_os = int(round(dur * SR * os))
    t = np.arange(n_os) / (SR * os)
    fm = mod_fixed if mod_fixed is not None else fc * ratio
    if pm_fn is None:
        ph_c = TWOPI * fc * t + phase
        ph_m = TWOPI * fm * t
    else:
        mult = pm_fn(t)
        ph_c = TWOPI * np.cumsum(fc * mult) / (SR * os) + phase
        ph_m = TWOPI * np.cumsum(fm * mult) / (SR * os)
    y = A_fn(t) * np.sin(ph_c + I_fn(t) * np.sin(ph_m))
    return decimate(y, os)


# ----------------------------------------------------------------------------
# additive band-limited oscillator bank (pads / leads) -- numba, parallel
# ----------------------------------------------------------------------------
@njit(parallel=True, cache=True)
def _additive(f0, detune, lfo_rate, lfo_depth, lfo_phase, ph0,
              ctl_fc, ctl_blend, block, kmax, flimit, order, sr):
    """Render V detuned voices of a band-limited saw/triangle blend.

    f0      : per-sample base frequency (n,)
    ctl_fc  : control-rate lowpass cutoff (nb,) where nb = n//block + 2
    ctl_blend: control-rate blend 0 (triangle-ish, odd 1/k^2) .. 1 (saw 1/k)
    The "filter" is a magnitude response applied per partial:
        H(f) = 1/sqrt(1 + (f/fc)^(2*order))
    Partials above flimit are tapered to zero -> no aliasing by construction.
    """
    V = detune.shape[0]
    n = f0.shape[0]
    out = np.zeros((V, n))
    nb = ctl_fc.shape[0]
    for v in prange(V):
        ph = ph0[v]
        amp_a = np.zeros(kmax)
        amp_b = np.zeros(kmax)
        for b in range(nb - 1):
            i0 = b * block
            if i0 >= n:
                break
            for side in range(2):
                bi = b + side
                ii = bi * block
                if ii >= n:
                    ii = n - 1
                fb = f0[ii] * 2.0 ** (detune[v] / 1200.0)
                fcut = ctl_fc[bi]
                bl = ctl_blend[bi]
                for k in range(kmax):
                    kk = k + 1
                    fk = fb * kk
                    saw = 1.0 / kk
                    tri = 0.0
                    if kk % 2 == 1:
                        tri = 1.0 / (kk * kk)
                    w = bl * saw + (1.0 - bl) * tri
                    h = 1.0 / np.sqrt(1.0 + (fk / fcut) ** (2 * order))
                    x = (fk - 0.75 * flimit) / (0.25 * flimit)
                    if x >= 1.0:
                        tap = 0.0
                    elif x <= 0.0:
                        tap = 1.0
                    else:
                        tap = 0.5 + 0.5 * np.cos(np.pi * x)
                    if side == 0:
                        amp_a[k] = w * h * tap
                    else:
                        amp_b[k] = w * h * tap
            for j in range(block):
                i = i0 + j
                if i >= n:
                    break
                fr = j / block
                cents = detune[v] + lfo_depth[v] * np.sin(TWOPI * lfo_rate[v] * i / sr + lfo_phase[v])
                f = f0[i] * 2.0 ** (cents / 1200.0)
                ph += TWOPI * f / sr
                if ph > TWOPI:
                    ph -= TWOPI
                c = np.cos(ph)
                s = np.sin(ph)
                ck = c
                sk = s
                acc = 0.0
                for k in range(kmax):
                    a = amp_a[k] + (amp_b[k] - amp_a[k]) * fr
                    acc += a * sk
                    t_ = ck * c - sk * s
                    sk = sk * c + ck * s
                    ck = t_
                out[v, i] = acc
    return out


def additive(f0_arr, detune_c, lfo_rate, lfo_depth, lfo_phase, ph0, ctl_fc, ctl_blend,
             block=32, flimit=9000.0, order=2):
    f0_arr = np.ascontiguousarray(f0_arr, dtype=np.float64)
    fmin = float(np.min(f0_arr)) * 2 ** (-20 / 1200)
    kmax = int(max(1, min(96, np.floor(flimit / fmin))))
    return _additive(f0_arr, np.asarray(detune_c, float), np.asarray(lfo_rate, float),
                     np.asarray(lfo_depth, float), np.asarray(lfo_phase, float),
                     np.asarray(ph0, float), np.ascontiguousarray(ctl_fc, dtype=np.float64),
                     np.ascontiguousarray(ctl_blend, dtype=np.float64), int(block), kmax,
                     float(flimit), int(order), float(SR))


# ----------------------------------------------------------------------------
# ping-pong delay (numba)
# ----------------------------------------------------------------------------
@njit(cache=True)
def _pingpong(x, d, fb, lp_coef, hp_coef):
    n = x.shape[0]
    bufL = np.zeros(d)
    bufR = np.zeros(d)
    yL = np.zeros(n)
    yR = np.zeros(n)
    idx = 0
    lps = 0.0
    hps = 0.0
    lps2 = 0.0
    for i in range(n):
        oL = bufL[idx]
        oR = bufR[idx]
        yL[i] = oL
        yR[i] = oR
        lps += lp_coef * (oR - lps)
        hps += hp_coef * (lps - hps)
        fbv = lps - hps
        lps2 += lp_coef * (oL - lps2)
        bufL[idx] = x[i] + fb * fbv
        bufR[idx] = lps2
        idx += 1
        if idx >= d:
            idx = 0
    return yL, yR


def pingpong(x, delay_s, fb=0.38, damp_hz=4500.0, hp_hz=250.0):
    d = max(1, smp(delay_s))
    lpc = 1.0 - np.exp(-TWOPI * damp_hz / SR)
    hpc = 1.0 - np.exp(-TWOPI * hp_hz / SR)
    yL, yR = _pingpong(np.ascontiguousarray(x, dtype=np.float64), d, fb, lpc, hpc)
    return np.vstack([yL, yR])


# ----------------------------------------------------------------------------
# synthetic reverb impulse responses
# ----------------------------------------------------------------------------
def make_ir(seed, length, rt60_pts, predelay=0.020, onset=0.012, er_n=10, er_span=0.07,
            lp_hz=10000.0, width=1.0):
    """Stereo IR: decorrelated noise, per-octave exponential decay (frequency
    dependent RT60), early reflections, predelay, energy-normalised."""
    n = smp(length)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    centers = np.array([63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000], float)
    u = np.log2(np.maximum(freqs, 1.0) / centers[0])
    rt_c = np.exp(np.interp(np.log(centers), np.log(np.array([p[0] for p in rt60_pts], float)),
                            np.log(np.array([p[1] for p in rt60_pts], float))))
    ir = np.zeros((2, n))
    for ch in range(2):
        X = np.fft.rfft(rng.standard_normal(n))
        y = np.zeros(n)
        for b in range(len(centers)):
            d = u - b
            w = np.where(np.abs(d) < 1.0, np.cos(0.5 * np.pi * d) ** 2, 0.0)
            if b == 0:
                w = np.where(d <= 0, 1.0, w)
            if b == len(centers) - 1:
                w = np.where(d >= 0, 1.0, w)
            xb = np.fft.irfft(X * w, n)
            y += xb * np.exp(-6.9078 * t / rt_c[b])
        no = smp(onset)
        y[:no] *= rc_ramp(no)
        for _ in range(er_n):
            tt = rng.uniform(0.004, er_span)
            g = rng.uniform(0.3, 1.0) * np.exp(-tt / 0.05) * rng.choice([-1, 1])
            k = smp(tt)
            y[k] += g * 6.0
        y = lp(y, lp_hz, 2)
        ir[ch] = y
    if width != 1.0:
        m = 0.5 * (ir[0] + ir[1])
        s_ = 0.5 * (ir[0] - ir[1]) * width
        ir = np.vstack([m + s_, m - s_])
    pd = smp(predelay)
    ir = np.hstack([np.zeros((2, pd)), ir])
    nf = smp(0.3)
    ir[:, -nf:] *= rc_ramp(nf)[::-1]
    ir /= np.sqrt(np.sum(ir ** 2, axis=1, keepdims=True))
    return ir


HALL_RT = [(63, 3.7), (250, 3.6), (500, 3.5), (1000, 3.3), (2000, 2.8), (4000, 2.1), (8000, 1.4), (16000, 0.8)]
ROOM_RT = [(63, 1.0), (500, 0.95), (2000, 0.8), (4000, 0.6), (8000, 0.45), (16000, 0.3)]
PLATE_RT = [(63, 1.6), (500, 1.8), (2000, 1.6), (4000, 1.3), (8000, 1.0), (16000, 0.6)]


@lru_cache(maxsize=8)
def get_ir(name):
    """cached synthetic IRs: 'hall' (RT60 ~3.5 s), 'room' (~0.9 s), 'plate' (~1.7 s)."""
    if name == 'hall':
        return make_ir(1, 4.6, HALL_RT, predelay=0.020, onset=0.015, er_n=12, er_span=0.08, lp_hz=9500)
    if name == 'room':
        return make_ir(2, 1.3, ROOM_RT, predelay=0.008, onset=0.004, er_n=8, er_span=0.03, lp_hz=11000)
    if name == 'plate':
        return make_ir(3, 2.4, PLATE_RT, predelay=0.012, onset=0.006, er_n=6, er_span=0.04, lp_hz=10000)
    raise ValueError(name)


def convolve_st(x, ir, n_out):
    """x (2,n) send -> stereo reverb via 70/30 cross feed into IR L/R."""
    inL = 0.7 * x[0] + 0.3 * x[1]
    inR = 0.3 * x[0] + 0.7 * x[1]
    yL = signal.fftconvolve(inL, ir[0])[:n_out]
    yR = signal.fftconvolve(inR, ir[1])[:n_out]
    if yL.shape[0] < n_out:
        yL = np.pad(yL, (0, n_out - yL.shape[0]))
        yR = np.pad(yR, (0, n_out - yR.shape[0]))
    return np.vstack([yL, yR])


# ----------------------------------------------------------------------------
# dynamics (numba)
# ----------------------------------------------------------------------------
@njit(cache=True)
def _compressor(xL, xR, thr, ratio, knee, att, rel, sr):
    n = xL.shape[0]
    g = np.ones(n)
    aa = np.exp(-1.0 / (att * sr))
    ar = np.exp(-1.0 / (rel * sr))
    gs = 0.0
    slope = 1.0 / ratio - 1.0
    for i in range(n):
        lv = max(abs(xL[i]), abs(xR[i]))
        ld = 20.0 * np.log10(lv + 1e-12)
        ov = ld - thr
        if 2.0 * ov < -knee:
            gr = 0.0
        elif 2.0 * abs(ov) <= knee:
            gr = slope * (ov + knee / 2.0) ** 2 / (2.0 * knee)
        else:
            gr = slope * ov
        if gr < gs:
            gs = aa * gs + (1.0 - aa) * gr
        else:
            gs = ar * gs + (1.0 - ar) * gr
        g[i] = 10.0 ** (gs / 20.0)
    return g


def compressor(x, thr_db, ratio=2.0, knee_db=6.0, att=0.010, rel=0.150):
    """feed-forward peak compressor on a stereo buffer (linked). Returns (y, gain)."""
    g = _compressor(np.ascontiguousarray(x[0]), np.ascontiguousarray(x[1]), float(thr_db), float(ratio),
                    float(knee_db), float(att), float(rel), float(SR))
    return x * g, g


@njit(cache=True)
def _fwd_min(g, L):
    """h[n] = min(g[n : n+L])  (monotonic deque, O(n))."""
    n = g.shape[0]
    h = np.empty(n)
    dq = np.empty(n, dtype=np.int64)
    head = 0
    tail = 0
    for i in range(n - 1, -1, -1):
        while tail > head and g[dq[tail - 1]] >= g[i]:
            tail -= 1
        dq[tail] = i
        tail += 1
        while dq[head] >= i + L:
            head += 1
        h[i] = g[dq[head]]
    return h


@njit(cache=True)
def _release(h, ar):
    n = h.shape[0]
    r = np.empty(n)
    cur = 1.0
    for i in range(n):
        if h[i] < cur:
            cur = h[i]
        else:
            cur = h[i] + (cur - h[i]) * ar
        r[i] = cur
    return r


def true_peak_env(x, os=4):
    """per-sample true-peak estimate (max over channels of 4x upsampled |x|)."""
    up = upsample(x, os)
    a = np.max(np.abs(up), axis=0)
    n = x.shape[1]
    a = a[: n * os].reshape(n, os).max(axis=1)
    a = np.maximum(a, np.concatenate([a[1:], a[-1:]]))
    return a


def limiter(x, ceiling_db=-1.3, look=0.005, rel=0.08):
    """look-ahead, true-peak-aware brickwall limiter (offline). Returns (y, gain)."""
    ceil = 10 ** (ceiling_db / 20.0)
    tp = true_peak_env(x)
    greq = np.minimum(1.0, ceil / np.maximum(tp, 1e-12))
    L = max(1, smp(look))
    h = _fwd_min(greq, L)
    r = _release(h, np.exp(-1.0 / (rel * SR)))
    c = np.cumsum(np.concatenate([np.full(L, r[0]), r]))
    g = (c[L:] - c[:-L]) / L
    return x * g, g


def softclip_os(x, thresh=0.85, os=4):
    """oversampled soft knee: linear below thresh, tanh above."""
    up = upsample(x, os)
    a = np.abs(up)
    over = a > thresh
    y = up.copy()
    k = 1.0 - thresh
    y[over] = np.sign(up[over]) * (thresh + k * np.tanh((a[over] - thresh) / k))
    return decimate_2d(y, os, x.shape[1])


def decimate_2d(y, os, n):
    out = np.vstack([decimate(y[0], os), decimate(y[1], os)])
    return out[:, :n]


def mono_lows(x, f_lo=95.0, f_hi=120.0):
    """keep the low end mono: remove the side channel below f_lo with a
    zero-phase FFT crossover (raised-cosine transition f_lo -> f_hi)."""
    m = 0.5 * (x[0] + x[1])
    s = 0.5 * (x[0] - x[1])
    n = s.shape[-1]
    pad = SR
    sp = np.concatenate([np.zeros(pad), s, np.zeros(pad)])
    S = np.fft.rfft(sp)
    f = np.fft.rfftfreq(len(sp), 1.0 / SR)
    H = np.clip((f - f_lo) / (f_hi - f_lo), 0.0, 1.0)
    H = 0.5 - 0.5 * np.cos(np.pi * H)
    s = np.fft.irfft(S * H, len(sp))[pad:pad + n]
    return np.vstack([m + s, m - s])


def add_at(dst, src, start):
    """mix src (2, m) into dst (2, N) starting at sample `start` (may be < 0 or
    run past the end; out-of-range parts are dropped)."""
    n = dst.shape[1]
    m = src.shape[1]
    s0, s1 = max(0, start), min(n, start + m)
    if s1 > s0:
        dst[:, s0:s1] += src[:, s0 - start:s1 - start]
    return dst
