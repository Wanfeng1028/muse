"""Instrument voices and raw sound-effect voices.

Each function returns a float64 array (mono (n,) or stereo (2, n)) that starts
from silence and ends at silence. Everything is generated from oscillators, FM
operators, additive banks, filtered noise and envelopes (see dsp.py).

Ported from the "在我开口之前" score (instruments.py); film-specific placement
was removed, a few voices got extra parameters (kick/hat/pad_note/rim/boom).
The catalogue-level API with pitch/brightness/duration parameters, seeds and
loudness normalisation lives in sfx.py.
"""
import numpy as np

from .dsp import (SR, TWOPI, smp, hz, rc_ramp, noise, env_perc, env_asr, lp, hp, bpf, svf,
                  fm2, pan_gains, additive, att_curve as _att)


def _tail(y, sec=0.008):
    n = min(y.shape[-1], max(1, smp(sec)))
    y[..., -n:] *= rc_ramp(n)[::-1]
    return y


# =============================================================================
# pitched instruments
# =============================================================================
def crystal_pluck(note, vel=1.0, dur=1.8, ratio=2.0, bright=1.0, seed=0, decay=0.4):
    """FM pluck, carrier:mod 1:ratio, index 4 -> 0 in ~80 ms, amp tau ~decay,
    plus a very short band-passed noise transient."""
    f = hz(note)
    kt = float(np.clip((600.0 / f) ** 0.35, 0.55, 1.2))
    I0 = 4.0 * bright * kt
    Is = 0.22 * bright * kt
    y = fm2(dur, f, ratio,
            lambda t: I0 * np.exp(-t / 0.022) + Is * np.exp(-t / 0.5),
            lambda t: _att(t, 0.0012) * np.exp(-t / decay), os=2)
    nn = smp(0.004)
    tr = bpf(noise(nn, 1000 + seed), 2500, 7500) * env_perc(nn, 0.0003, 0.0012, tail=0.001)
    y[:nn] += 0.10 * bright * tr
    return _tail(y * vel, 0.05)


def celesta(note, vel=1.0, dur=2.4, seed=0):
    """FM 1:1 pluck body + faint 1:3.5 bell shimmer."""
    f = hz(note)
    kt = float(np.clip((700.0 / f) ** 0.3, 0.6, 1.15))
    body = fm2(dur, f, 1.0, lambda t: 2.6 * kt * np.exp(-t / 0.035) + 0.3 * np.exp(-t / 0.6),
               lambda t: _att(t, 0.0012) * np.exp(-t / 0.42), os=2)
    shim = fm2(dur, f, 3.5, lambda t: 1.4 * np.exp(-t / 0.25),
               lambda t: _att(t, 0.002) * np.exp(-t / 0.9), os=2)
    nn = smp(0.003)
    tr = bpf(noise(nn, 2000 + seed), 3000, 8000) * env_perc(nn, 0.0002, 0.0008, tail=0.001)
    y = 0.8 * body + 0.22 * shim
    y[:nn] += 0.22 * tr
    return _tail(y * vel, 0.08)


def bell(note, vel=1.0, dur=4.2, index=3.0, decay=0.75):
    """Soft FM bell, carrier:mod 1:3.5 (inharmonic), index -> 0 over ~1.5 s,
    ~3 s decay, plus a warm fundamental layer with slow beating and a hum tone."""
    f = hz(note)
    main = fm2(dur, f, 3.5, lambda t: index * np.exp(-t / 0.42),
               lambda t: _att(t, 0.0015) * np.exp(-t / decay), os=2)
    t = np.arange(len(main)) / SR
    body = (np.sin(TWOPI * f * t) + 0.6 * np.sin(TWOPI * (f + 0.9) * t)) * _att(t, 0.003) * np.exp(-t / (decay * 1.47))
    hum = np.sin(TWOPI * 0.5 * f * t) * _att(t, 0.01) * np.exp(-t / (decay * 1.87))
    y = 0.62 * main + 0.26 * body + 0.10 * hum
    return _tail(y * vel, 0.3)


def ping(note, vel=1.0, dur=1.2):
    """high 'star' ping: near-sine FM (1:1, small index)."""
    f = hz(note)
    y = fm2(dur, f, 1.0, lambda t: 0.7 * np.exp(-t / 0.03),
            lambda t: _att(t, 0.002) * np.exp(-t / 0.28), os=2)
    return _tail(y * vel, 0.05)


def epiano(note, vel=0.7, dur=1.0, seed=0, rel_tau=0.28):
    """FM electric piano (Rhodes-like): 1:1 body (index 1.5 -> 0.3) + 1:14 tine
    layer with a very short decay at low level; `dur` = key-down time."""
    f = hz(note)
    v = vel
    total = dur + 1.6
    kt = float(np.clip((440.0 / f) ** 0.25, 0.7, 1.2))

    def amp(t):
        a = _att(t, 0.0025) * np.exp(-t / 1.9)
        rel = np.where(t > dur, np.exp(-(t - dur) / rel_tau), 1.0)
        return a * rel

    body = fm2(total, f, 1.0,
               lambda t: (0.3 + 1.2 * v * np.exp(-t / 0.35)) * kt, amp, os=2)
    tine_i = 0.9 if f < 900 else 0.5
    tine = fm2(total, f, 14.0, lambda t: tine_i * np.exp(-t / 0.010),
               lambda t: _att(t, 0.0008) * np.exp(-t / 0.018), os=4)
    y = body + 0.10 * v * tine
    t = np.arange(len(y)) / SR
    y += 0.06 * v * np.sin(TWOPI * 2 * f * t) * amp(t) * np.exp(-t / 0.4)
    return _tail(y * v, 0.05)


def sub_bass(note, dur, vel=1.0, att=0.008, rel=0.06, sat=1.4, h2=0.12):
    """sine + a little 2nd harmonic -> tanh soft saturation."""
    f = hz(note)
    n = smp(dur + rel + 0.02)
    t = np.arange(n) / SR
    x = np.sin(TWOPI * f * t) + h2 * np.sin(2 * TWOPI * f * t)
    x = np.tanh(sat * x) / np.tanh(sat)
    e = env_asr(n, att, dur, rel_tau=rel / 2.5, rel_len=rel + 0.015)
    return x * e * vel


def pad_note(note, hold, att, rel, fc_fn, blend_fn, rng, width=0.6, flimit=9000.0,
             detune=(0.0, -6.0, 6.0, -12.0, 12.0), lfo_cents=3.0):
    """one pad note: additive band-limited saw/triangle blend, 5 detuned voices
    (0 / +-6 / +-12 cents) spread across the stereo field, slow pitch LFO,
    per-partial 12 dB/oct 'filter' following fc_fn(t_rel) (Hz) and wave blend
    blend_fn(t_rel) (0 tri .. 1 saw), both sampled at control rate.
    Returns (2, n) with n = hold + rel."""
    f = hz(note)
    V = len(detune)
    block = 32
    n = smp(hold + rel)
    nb = n // block + 2
    tb = np.arange(nb) * block / SR
    ctl_fc = np.asarray(fc_fn(tb), dtype=np.float64)
    ctl_bl = np.asarray(blend_fn(tb), dtype=np.float64)
    pans = np.linspace(-1.0, 1.0, V)[np.argsort(np.argsort(detune))] if V > 1 else np.zeros(1)
    voices = additive(np.full(n, f), np.array(detune, float), rng.uniform(0.06, 0.22, V), np.full(V, lfo_cents),
                      rng.uniform(0, TWOPI, V), rng.uniform(0, TWOPI, V), ctl_fc, ctl_bl,
                      block=block, flimit=flimit, order=2)
    env = env_asr(n, att, hold, rel_tau=rel * 0.28, rel_len=rel)
    reg = 1.0
    if f < 90:
        reg = 0.55
    elif f < 130:
        reg = 0.7
    elif f > 300:
        reg = 0.85
    out = np.zeros((2, n))
    for v in range(V):
        gl, gr = pan_gains(pans[v] * width)
        out[0] += voices[v] * gl
        out[1] += voices[v] * gr
    out *= env * reg / np.sqrt(V)
    return out


# =============================================================================
# drums
# =============================================================================
def kick(vel=1.0, seed=0, f_lo=45.0, f_hi=110.0, tau=0.35, click=0.22, length=0.50):
    """sine sweep f(t)=f_lo+f_hi e^(-t/0.03), amp e^(-t/tau), 2 ms click."""
    n = smp(length)
    t = np.arange(n) / SR
    ph = TWOPI * (f_lo * t + f_hi * 0.03 * (1.0 - np.exp(-t / 0.03)))
    body = np.sin(ph) * np.exp(-t / tau)
    k0, k1 = smp(length * 0.64), n
    body[k0:k1] *= rc_ramp(k1 - k0)[::-1]
    body[:12] *= rc_ramp(12)
    body = np.tanh(1.25 * body) / np.tanh(1.25)
    nc = smp(0.002)
    ck = bpf(noise(nc, 7000 + seed), 1500, 6000) * np.hanning(nc)
    body[:nc] += click * ck
    return body * vel


def hat(open_=False, vel=1.0, seed=0, soft=False):
    """white noise -> HP 7 kHz (-> LP 13.5 kHz), closed ~9 ms / open ~55 ms decay.
    soft=True: brush-like (5-10 kHz band, 2 ms attack, longer decay)."""
    dur = 0.26 if open_ else (0.09 if soft else 0.05)
    tau = 0.055 if open_ else (0.022 if soft else 0.0085)
    n = smp(dur)
    x = noise(n, seed)
    if soft:
        x = bpf(x, 5000, 10000, 2)
        e = env_perc(n, 0.002, tau, tail=0.01)
    else:
        x = hp(x, 7000, 4)
        x = lp(x, 13500, 2)
        e = env_perc(n, 0.0004, tau, tail=0.01 if open_ else 0.004)
    return x * e * vel * 0.5


def clap(vel=1.0, seed=0):
    """4 noise bursts 10 ms apart, 1.2 kHz band-pass, 120 ms decay."""
    n = smp(0.26)
    t = np.arange(n) / SR
    x = noise(n, seed)
    e = np.zeros(n)
    for k in range(4):
        t0 = 0.010 * k
        tau = 0.004 if k < 3 else 0.045
        tt = np.maximum(t - t0, 0.0)
        e += np.where(t >= t0, _att(tt, 0.0003) * np.exp(-tt / tau), 0.0) * (0.75 if k < 3 else 1.0)
    e *= np.clip(1.0 - t / 0.26, 0, 1)
    y = svf(x * e, 1200.0, 1.3, 'bp') + 0.35 * svf(x * e, 2400.0, 2.0, 'bp')
    y[:24] *= rc_ramp(24)
    return _tail(y * vel, 0.02)


def rim(vel=1.0, seed=0, f=1700.0):
    """soft rim / wood snap: short FM knock (1:1.47) + band-passed noise."""
    y = fm2(0.08, f, 1.47, lambda t: 1.8 * np.exp(-t / 0.004),
            lambda t: _att(t, 0.0004) * np.exp(-t / 0.012), os=2)
    t = np.arange(len(y)) / SR
    nz = bpf(noise(len(y), seed), 1500, 6000) * _att(t, 0.0003) * np.exp(-t / 0.006)
    y = 0.8 * y + 0.35 * nz + 0.25 * np.sin(TWOPI * 420.0 * t) * _att(t, 0.001) * np.exp(-t / 0.02)
    return _tail(y * vel, 0.006)


def snare(vel=1.0, body_hz=190.0, seed=0, tau=0.06):
    """noise + ~190 Hz drum body (roll element)."""
    n = smp(0.18)
    t = np.arange(n) / SR
    nz = bpf(noise(n, seed), 900, 8000) * env_perc(n, 0.0005, tau * 0.8)
    ph = TWOPI * np.cumsum(body_hz * (1 + 0.25 * np.exp(-t / 0.01))) / SR
    body = np.sin(ph) * env_perc(n, 0.0008, 0.045)
    y = 0.55 * nz + 0.6 * body
    return _tail(y * vel, 0.01)


def tom(f0=110.0, vel=1.0, seed=0):
    n = smp(0.35)
    t = np.arange(n) / SR
    f = f0 * (1 + 0.5 * np.exp(-t / 0.02))
    body = np.sin(TWOPI * np.cumsum(f) / SR) * env_perc(n, 0.001, 0.11)
    nz = bpf(noise(n, seed), 400, 3000) * env_perc(n, 0.0005, 0.02)
    return _tail((body + 0.25 * nz) * vel, 0.02)


# =============================================================================
# raw sound-effect voices (sfx.py wraps these with parameters + normalisation)
# =============================================================================
def wood_tick(f=1200.0, ratio=1.5, index=2.0, dur=0.025, vel=1.0):
    """short wooden FM tick: ratio 1.5, index -> 0 in ~10 ms."""
    y = fm2(dur + 0.01, f, ratio, lambda t: index * np.clip(1 - t / 0.010, 0, 1) ** 2,
            lambda t: _att(t, 0.0004) * np.exp(-t / (dur / 4.0)), os=2)
    return _tail(y * vel, 0.004)


def tock(f=640.0, vel=1.0, index=2.4, decay=0.014):
    y = fm2(max(0.07, decay * 5.0), f, 1.5, lambda t: index * np.exp(-t / 0.008),
            lambda t: _att(t, 0.0005) * np.exp(-t / decay), os=2)
    t = np.arange(len(y)) / SR
    y += 0.5 * np.sin(TWOPI * 0.5 * f * t) * _att(t, 0.001) * np.exp(-t / (decay * 0.86))
    return _tail(y * vel, 0.006)


def blip(f, vel=1.0, index=1.2, decay=0.06):
    """start-up blip: FM near-sine (ratio 2 -> odd partials) with a tiny upward glide."""
    y = fm2(max(0.12, decay * 3.6), f, 2.0, lambda t: index * np.exp(-t / 0.012),
            lambda t: _att(t, 0.0015) * np.exp(-t / decay), os=2,
            pm_fn=lambda t: 2 ** ((-40 * np.exp(-t / 0.012)) / 1200))
    return _tail(y * vel, 0.01)


def key_click(rng, heavy=False, vel=1.0, pitch=1.0, bright=1.0):
    """typing key: 3-8 ms 2-4 kHz band noise + faint 1.5 kHz pitch; heavy (commit/space)
    adds a 5 ms click and a 100 Hz / 30 ms body."""
    lvl = vel * (1.0 + rng.uniform(-0.15, 0.15))
    pit = pitch * (1.0 + rng.uniform(-0.05, 0.05))
    dur = rng.uniform(0.003, 0.008) if not heavy else 0.008
    n = smp(0.07 if heavy else 0.02)
    t = np.arange(n) / SR
    nz = bpf(noise(n, int(rng.integers(1 << 30))), 2000 * pit, min(4000 * pit * (0.7 + 0.6 * bright), 20000), order=2)
    e = _att(t, 0.0003) * np.exp(-t / (dur / 3.0))
    y = nz * e
    y += 0.10 * np.sin(TWOPI * 1500 * pit * t) * _att(t, 0.0005) * np.exp(-t / 0.004)
    if heavy:
        nc = smp(0.005)
        c = bpf(noise(nc, int(rng.integers(1 << 30))), 1200, 5000) * np.hanning(nc)
        y[:nc] += 0.8 * c
        y += 0.9 * np.sin(TWOPI * 100 * pit * t) * _att(t, 0.0015) * np.exp(-t / 0.010)
    return _tail(y * lvl, 0.004)


def laser_zip(vel=1.0, f0=5000.0, f1=1800.0, dur=0.05, seed=0):
    """f0 -> f1 sine sweep in dur + a little tracking noise."""
    n = smp(dur + 0.03)
    t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** np.clip(t / dur, 0, 1)
    ph = TWOPI * np.cumsum(f) / SR
    e = _att(t, 0.001) * np.clip(1 - t / (dur + 0.03), 0, 1) ** 2.2
    y = np.sin(ph) * e
    nz = svf(noise(n, seed), f, 4.0, 'bp') * e
    y = y + 0.35 * nz
    y = lp(y, 9000, 2)
    return _tail(y * vel, 0.006)


def _shape(kind, u, att=None, peak=0.6):
    """normalised amplitude shapes on u in [0,1]."""
    if kind == 'swell':        # rise then fall, peak at `peak`
        k = np.log(0.5) / np.log(max(1e-3, min(0.999, peak)))
        return np.sin(np.pi * np.clip(u, 0, 1) ** k) ** 1.5
    if kind == 'reverse':      # exponential rise to an abrupt end
        return (np.exp(4.0 * u) - 1) / (np.e ** 4 - 1)
    if kind == 'decay':        # fast attack, smooth decay
        a = 0.06 if att is None else att
        return _att(u, a) * np.exp(-u * 4.0) * (1 - u)
    if kind == 'pass':         # quick rise to 15 %, decay
        return np.where(u < 0.15, np.sin(0.5 * np.pi * u / 0.15) ** 2,
                        np.exp(-(u - 0.15) * 5.0)) * np.clip((1 - u) * 8, 0, 1)
    raise ValueError(kind)


def whoosh(dur, f0, f1, shape='swell', q=1.4, pan0=0.0, pan1=0.0, seed=0, vel=1.0,
           lowmix=0.35, fade_out=0.006, att=None, peak=0.6, fc_curve=None, air=0.0):
    """band-passed noise with swept centre frequency, amplitude shape and pan
    motion. fc_curve(u) (0..1 -> 0..1) overrides the plain exponential sweep
    from f0 to f1; air adds a high-passed (> 6 kHz) noise layer."""
    n = smp(dur)
    u = np.arange(n) / n
    w = u if fc_curve is None else fc_curve(u)
    fc = f0 * (f1 / f0) ** w
    x = noise(n, seed)
    a = svf(x, fc, q, 'bp')
    b = svf(noise(n, seed + 1), fc * 0.5, 0.9, 'bp')
    y = lp(a + lowmix * b, 9500, 2)
    if air > 0:
        y = y + air * lp(svf(hp(noise(n, seed + 2), 6000, 2), np.minimum(fc * 3.0, 12000), 0.7, 'bp'), 13000, 2)
    y *= _shape(shape, u, None if att is None else att / dur, peak)
    y[:24] *= rc_ramp(24)
    nf = smp(fade_out)
    y[-nf:] *= rc_ramp(nf)[::-1]
    p = pan0 + (pan1 - pan0) * (0.5 - 0.5 * np.cos(np.pi * u))
    gl, gr = pan_gains(p)
    return np.vstack([y * gl, y * gr]) * vel


def riser(dur=3.78, f0=110.0, seed=0, vel=1.0, octaves=1.0, fc_end=9000.0):
    """noise + saw rising `octaves` + opening filter, stereo, exponential crescendo."""
    n = smp(dur)
    u = np.arange(n) / n
    f = f0 * 2.0 ** (octaves * u)
    out = np.zeros((2, n))
    for ch, det in enumerate((-7.0, 7.0)):
        ph = TWOPI * np.cumsum(f * 2 ** (det / 1200)) / SR + ch
        saw = np.zeros(n)
        for k in range(1, 40):
            fk = f * k
            m = np.clip((12000 - fk) / 3000, 0, 1)
            if not np.any(m):
                break
            saw += np.sin(k * ph) / k * m
        fc = 300.0 * (fc_end / 300.0) ** (u ** 1.3)
        s1 = svf(saw, fc, 0.9, 'lp')
        nz = svf(noise(n, seed + ch), fc * 1.2, 0.8, 'lp')
        out[ch] = 0.55 * s1 + 0.35 * nz
    amp = (np.exp(3.2 * u) - 1) / (np.exp(3.2) - 1)
    out *= amp
    nf = smp(0.02)
    out[:, -nf:] *= rc_ramp(nf)[::-1]
    return out * vel


def boom(f_hi=50.0, f_lo=35.0, dur=1.5, vel=1.0, glide_tau=0.35, decay=0.45, sat=1.2):
    """low sine boom f_hi -> f_lo with long decay."""
    n = smp(dur)
    t = np.arange(n) / SR
    f = f_lo + (f_hi - f_lo) * np.exp(-t / glide_tau)
    y = np.sin(TWOPI * np.cumsum(f) / SR) * _att(t, 0.003) * np.exp(-t / decay)
    y = np.tanh(sat * y) / np.tanh(sat)
    return _tail(y * vel, min(0.2, dur * 0.2))


def hit(vel=1.0, seed=0, warm=False):
    """cinematic hit: boom + low drum body + low-passed noise burst (stereo)."""
    b = boom(50, 35, 1.5, 1.0)
    n = len(b)
    t = np.arange(n) / SR
    body = np.sin(TWOPI * np.cumsum(95 * (1 + 0.6 * np.exp(-t / 0.015))) / SR) * _att(t, 0.001) * np.exp(-t / 0.16)
    out = np.zeros((2, n))
    for ch in range(2):
        nz = noise(n, seed + ch)
        nz = lp(nz, 1400 if warm else 2200, 2)
        nz *= _att(t, 0.0008) * np.exp(-t / (0.22 if warm else 0.16))
        out[ch] = 0.9 * b + 0.55 * body + 0.32 * nz
    out[:, :24] *= rc_ramp(24)
    return _tail(out * vel, 0.2)


def stamp(vel=1.0, seed=0, f=70.0, paper=0.35):
    """70 Hz / 80 ms thump + 30 ms paper noise."""
    n = smp(0.16)
    t = np.arange(n) / SR
    ff = f * (1 + 0.4 * np.exp(-t / 0.01))
    th = np.sin(TWOPI * np.cumsum(ff) / SR) * _att(t, 0.001) * np.exp(-t / 0.03) * np.clip(1 - t / 0.12, 0, 1)
    pn = bpf(noise(n, seed), 700, 3500) * _att(t, 0.0005) * np.exp(-t / 0.008) * np.clip(1 - t / 0.035, 0, 1)
    return _tail((th + paper * pn) * vel, 0.01)


def clack(vel=1.0, seed=0, f=900.0):
    """lock: sharp plastic/wood clack."""
    n = smp(0.035)
    t = np.arange(n) / SR
    nz = bpf(noise(n, seed), 1800, 6000) * _att(t, 0.0003) * np.exp(-t / 0.0025)
    tk = fm2(0.035, f, 2.3, lambda tt: 2.5 * np.exp(-tt / 0.004),
             lambda tt: _att(tt, 0.0004) * np.exp(-tt / 0.006), os=2)[:n]
    body = np.sin(TWOPI * 160 * (f / 900.0) * t) * _att(t, 0.0008) * np.exp(-t / 0.007)
    return _tail((0.6 * nz + 0.7 * tk + 0.5 * body) * vel, 0.004)


def zap(vel=1.0, f0=1600.0, f1=150.0):
    """descending FM zap f0 -> f1 in 40 ms."""
    dur = 0.045
    n = smp(dur)
    t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / dur)
    ph = TWOPI * np.cumsum(f) / SR
    phm = TWOPI * np.cumsum(f * 3.7) / SR
    y = np.sin(ph + 1.3 * np.exp(-t / 0.01) * np.sin(phm)) * _att(t, 0.0008) * np.exp(-t / 0.011)
    return _tail(y * vel, 0.004)


def heartbeat(vel=1.0):
    """lub-dub low thump pair (0.42 s)."""
    n = smp(0.42)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for t0, f0, a in ((0.0, 58.0, 1.0), (0.17, 64.0, 0.7)):
        tt = t - t0
        m = tt >= 0
        f = f0 * (1 + 0.3 * np.exp(-np.maximum(tt, 0) / 0.015))
        ph = TWOPI * np.cumsum(np.where(m, f, 0.0)) / SR
        y += a * np.sin(ph) * _att(np.maximum(tt, 0), 0.004) * np.exp(-np.maximum(tt, 0) / 0.045) * m
    y = lp(y, 300, 2)
    return _tail(y * vel, 0.02)


def grain(freq, dur=0.08, vel=1.0, glide=1.0, arc=0.0, h2=0.12):
    """Hann-windowed sine grain; glide = end/start frequency ratio; arc =
    semitone bend up-and-back."""
    n = max(16, smp(dur))
    u = np.arange(n) / n
    f = freq * glide ** u * 2 ** (arc * np.sin(np.pi * u) / 12.0)
    ph = TWOPI * np.cumsum(f) / SR
    y = (np.sin(ph) + h2 * np.sin(2 * ph)) * np.hanning(n)
    return y * vel
