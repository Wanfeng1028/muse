#!/usr/bin/env python3
"""Procedural soundtrack for the 75s Droid film.

Deterministic (seed 20261004). numpy + scipy only.
Writes audio/score_raw.wav, loudness-normalizes to public/score.wav,
and writes audio/cues_report.txt.

Run from the project root:
    python audio/build.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy import signal

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
TIMELINE = ROOT / "public" / "timeline.json"
RAW_WAV = ROOT / "audio" / "score_raw.wav"
OUT_WAV = ROOT / "public" / "score.wav"
REPORT = ROOT / "audio" / "cues_report.txt"

SR = 48000
SEED = 20261004
N_CH = 2

# Musical reference. A4 = 440.
A4 = 440.0


def midi_hz(m: float) -> float:
    return A4 * (2.0 ** ((m - 69.0) / 12.0))


# Pitch classes (MIDI).
D3, E3, A3, D4, E4, FS4, G4, A4M, BB4, B4, C5 = 50, 52, 57, 62, 64, 66, 67, 69, 70, 71, 72
D5, E5, FS5, G5, A5, B5, CS6, D6, E6 = 74, 76, 78, 79, 81, 83, 85, 86, 88

# Scene chords as (midi, gain) partial lists. Fundamental-ish voicings,
# low enough to sit under foley, voice-led so adjacent scenes share tones.
CHORDS = {
    "S1": [],  # cream world: dry, no bed
    "S2": [(50, 0.55), (57, 0.42), (65, 0.38), (69, 0.30), (72, 0.22)],  # Dm9  D3 A3 F4 A4 C5
    "S3": [(46, 0.50), (58, 0.40), (65, 0.36), (69, 0.32), (70, 0.22)],  # Bbmaj7 Bb2 Bb3 F4 A4 Bb4
    "S4": [(45, 0.42), (57, 0.48), (64, 0.36), (69, 0.30), (72, 0.20)],  # F/A   A2 A3 E4 A4 C5
    "S5": [(43, 0.40), (55, 0.46), (62, 0.38), (67, 0.28), (74, 0.16)],  # Gsus2 G2 G3 D4 G4 D5
    "S6": [(52, 0.38), (57, 0.34), (64, 0.42), (66, 0.36), (71, 0.30), (76, 0.22)],  # lifted Esus2/D
    "S7a": [(43, 0.36), (55, 0.40), (60, 0.28), (65, 0.32), (67, 0.22)],  # Gsus4
    "S7b": [(50, 0.42), (57, 0.40), (62, 0.34), (66, 0.28), (69, 0.18)],  # D
    "S8": [(74, 0.55), (86, 0.28)],  # sparse D5 + D6
}


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def load_timeline():
    with TIMELINE.open("r", encoding="utf-8") as f:
        tl = json.load(f)
    fps = int(tl["fps"])
    total = int(tl["total"])
    scenes = {s["id"]: s for s in tl["scenes"]}
    cues = tl["cues"]
    return fps, total, scenes, cues


def abs_time(scenes, fps, sid, local_frame):
    return (scenes[sid]["from"] + local_frame) / fps


# ---------------------------------------------------------------------------
# Mix bus
# ---------------------------------------------------------------------------

class Mix:
    def __init__(self, n):
        self.dry = np.zeros((n, 2), dtype=np.float64)
        self.room = np.zeros((n, 2), dtype=np.float64)   # small room send
        self.plate = np.zeros((n, 2), dtype=np.float64)  # plate send
        self.n = n

    def add(self, start, mono, pan=0.0, gain=1.0, send_room=0.0, send_plate=0.0):
        """Place a mono buffer. pan in [-1, 1]. Sends are pre-pan wet copies."""
        if mono is None or gain == 0.0:
            return
        mono = declick(np.asarray(mono, dtype=np.float64).reshape(-1).copy())
        if mono.size == 0:
            return
        i0 = int(start)
        if i0 >= self.n:
            return
        if i0 < 0:
            cut = -i0
            if cut >= mono.size:
                return
            mono = mono[cut:]
            i0 = 0
        n = min(mono.size, self.n - i0)
        if n <= 0:
            return
        x = mono[:n] * gain
        # Constant-power pan.
        ang = (pan + 1.0) * 0.25 * np.pi  # 0..pi/2
        l = np.cos(ang)
        r = np.sin(ang)
        sl = slice(i0, i0 + n)
        self.dry[sl, 0] += x * l
        self.dry[sl, 1] += x * r
        if send_room:
            self.room[sl, 0] += x * l * send_room
            self.room[sl, 1] += x * r * send_room
        if send_plate:
            self.plate[sl, 0] += x * l * send_plate
            self.plate[sl, 1] += x * r * send_plate

    def add_stereo(self, start, stereo, gain=1.0):
        st = declick(np.asarray(stereo, dtype=np.float64).copy())
        if st.ndim == 1:
            st = np.column_stack([st, st])
        i0 = int(start)
        if i0 >= self.n:
            return
        if i0 < 0:
            cut = -i0
            if cut >= st.shape[0]:
                return
            st = st[cut:]
            i0 = 0
        n = min(st.shape[0], self.n - i0)
        if n <= 0:
            return
        self.dry[i0:i0 + n] += st[:n] * gain


# ---------------------------------------------------------------------------
# Envelopes / noise / filters
# ---------------------------------------------------------------------------

def env_ar(n, a, r, sr=SR, curve=1.0):
    """Attack/release envelope, peak 1. a, r in seconds."""
    a_n = max(1, int(a * sr))
    r_n = max(1, int(r * sr))
    e = np.zeros(n, dtype=np.float64)
    aa = min(a_n, n)
    e[:aa] = np.linspace(0.0, 1.0, aa, endpoint=False) ** curve
    rest = n - aa
    if rest > 0:
        rr = min(r_n, rest)
        e[aa:aa + rr] = np.linspace(1.0, 0.0, rr, endpoint=False)
    return e


def env_exp(n, tau, sr=SR):
    t = np.arange(n, dtype=np.float64) / sr
    return np.exp(-t / max(tau, 1e-4))


def declick(x, ms=1.5, sr=SR):
    """Force a 1.5 ms zero-crossing fade on both ends. Voices are placed
    by sample-slicing, so an edge that isn't zero becomes a step and a
    true-peak overshoot once loudnorm raises the gain."""
    n = x.shape[0]
    k = min(int(ms * 1e-3 * sr), n // 2)
    if k < 2:
        return x
    ramp = np.linspace(0.0, 1.0, k)
    if x.ndim == 1:
        x[:k] *= ramp
        x[-k:] *= ramp[::-1]
    else:
        x[:k] *= ramp[:, None]
        x[-k:] *= ramp[::-1, None]
    return x


def noise(n, rng):
    return rng.standard_normal(n)


def pinkish(n, rng):
    """Cheap 1/f-ish noise via cascaded one-pole smoothing of white."""
    w = rng.standard_normal(n)
    out = np.zeros(n, dtype=np.float64)
    acc = 0.0
    # Three leaky integrators at different rates, summed.
    a1, a2, a3 = 0.985, 0.94, 0.7
    s1 = s2 = s3 = 0.0
    for i in range(n):
        x = w[i]
        s1 = a1 * s1 + (1 - a1) * x
        s2 = a2 * s2 + (1 - a2) * x
        s3 = a3 * s3 + (1 - a3) * x
        out[i] = s1 * 0.7 + s2 * 0.45 + s3 * 0.3
    peak = np.max(np.abs(out)) + 1e-12
    return out / peak


def bp_reson(x, f0, q, sr=SR):
    f0 = float(np.clip(f0, 40.0, sr * 0.45))
    q = max(q, 0.5)
    b, a = signal.butter(2, [max(f0 / q, 20.0), min(f0 * q, sr * 0.49)], btype="band", fs=sr)
    # Use sos for stability on narrow bands.
    sos = signal.butter(2, [max(f0 * (1 - 0.5 / q), 20.0), min(f0 * (1 + 0.5 / q), sr * 0.49)],
                        btype="band", output="sos", fs=sr)
    return signal.sosfilt(sos, x)


def hp(x, f0, sr=SR, order=2):
    f0 = float(np.clip(f0, 20.0, sr * 0.45))
    sos = signal.butter(order, f0, btype="highpass", output="sos", fs=sr)
    return signal.sosfilt(sos, x)


def lp(x, f0, sr=SR, order=2):
    f0 = float(np.clip(f0, 40.0, sr * 0.45))
    sos = signal.butter(order, f0, btype="lowpass", output="sos", fs=sr)
    return signal.sosfilt(sos, x)


def bp_sweep(x, f_start, f_end, q, sr=SR):
    """Time-varying bandpass via STFT-free sample-wise biquad (RBJ)."""
    n = x.size
    f = np.geomspace(max(f_start, 30.0), max(f_end, 31.0), n)
    y = np.zeros(n, dtype=np.float64)
    # Direct-form I, coefficients updated per sample. q constant.
    x1 = x2 = y1 = y2 = 0.0
    for i in range(n):
        w0 = 2.0 * np.pi * f[i] / sr
        alpha = np.sin(w0) / (2.0 * q)
        cosw = np.cos(w0)
        b0 = alpha
        b1 = 0.0
        b2 = -alpha
        a0 = 1.0 + alpha
        a1 = -2.0 * cosw
        a2 = 1.0 - alpha
        # normalize
        ib0, ib1, ib2 = b0 / a0, b1 / a0, b2 / a0
        ia1, ia2 = a1 / a0, a2 / a0
        yi = ib0 * x[i] + ib1 * x1 + ib2 * x2 - ia1 * y1 - ia2 * y2
        x2, x1 = x1, x[i]
        y2, y1 = y1, yi
        y[i] = yi
    return y


def norm(x, peak=1.0):
    m = np.max(np.abs(x))
    if m < 1e-12:
        return x
    return x * (peak / m)


def soften(x, n=8):
    """Tiny fade in/out so placed events don't click at the buffer edge."""
    if x.size < n * 2:
        return x
    w = np.ones(x.size, dtype=np.float64)
    ramp = np.linspace(0.0, 1.0, n)
    w[:n] *= ramp
    w[-n:] *= ramp[::-1]
    return x * w


# ---------------------------------------------------------------------------
# Synthesis voices
# ---------------------------------------------------------------------------

def keystroke(rng, enter=False, world="paper"):
    """Low-profile mechanical key: noise burst through 2-3 body modes,
    plus a bottom-out thock ~8 ms later."""
    dur = 0.085 if not enter else 0.14
    n = int(dur * SR)
    # Click: very short noise, band-passed into body resonances.
    click_n = int((0.0045 if not enter else 0.007) * SR)
    burst = np.zeros(n)
    burst[:click_n] = rng.standard_normal(click_n)
    # Slightly shaped excitation.
    burst[:click_n] *= np.linspace(1.0, 0.15, click_n)

    modes = [1800.0, 3400.0, 6000.0]
    qs = [7.5, 6.0, 4.5]
    gains = [1.0, 0.62, 0.34]
    if world == "terminal":
        # Tighter, less air, a touch more plastic.
        modes = [2100.0, 3900.0, 6400.0]
        qs = [9.0, 7.0, 5.0]
        gains = [0.9, 0.5, 0.22]
    body = np.zeros(n)
    for f0, q, g in zip(modes, qs, gains):
        # Per-key resonance wander, ±4% on the top mode only would be pitch;
        # body modes wander a little so keys don't clone.
        f = f0 * (1.0 + rng.uniform(-0.025, 0.025))
        body += g * bp_reson(burst, f, q)
    body = hp(body, 900.0)
    # Very short decay already implied by narrow excitation; add a touch of ring.
    body *= env_exp(n, 0.018 if not enter else 0.028)

    # Bottom-out thock: damped sine 180-260 Hz, ~8 ms later.
    thock_f = rng.uniform(185.0, 255.0)
    if enter:
        thock_f *= 0.72
    delay = int(0.008 * SR)
    thock_n = n - delay
    t = np.arange(thock_n) / SR
    tau = 0.022 if not enter else 0.045
    thock = np.sin(2 * np.pi * thock_f * t) * np.exp(-t / tau)
    # A little second partial, inharmonic, for the housing.
    thock += 0.28 * np.sin(2 * np.pi * thock_f * 2.37 * t) * np.exp(-t / (tau * 0.45))
    y = body * 0.85
    y[delay:] += thock * (0.55 if not enter else 0.85)
    if enter:
        # Heavier: extra low housing knock.
        y[delay:] += 0.35 * np.sin(2 * np.pi * 95.0 * t) * np.exp(-t / 0.05)
    y = soften(y, 6)
    peak = 0.9 if not enter else 1.0
    return norm(y, peak)


def string_friction(rng, dur=0.16):
    """Barely-audible high filtered string scrape. Very quiet by design."""
    n = int(dur * SR)
    x = noise(n, rng)
    x = hp(x, 4000.0)
    x = lp(x, 9000.0)
    # Slow amplitude flutter, like fiber drag.
    t = np.arange(n) / SR
    flutter = 0.65 + 0.35 * np.sin(2 * np.pi * rng.uniform(28, 46) * t + rng.uniform(0, 6))
    e = env_ar(n, 0.03, 0.10)
    return soften(x * flutter * e, 8) * 0.35


def modal_bar(freq, rng, dur=0.55, strike=1.0):
    """Wooden / marimba bar. Inharmonic ratios 1 : 3.93 : 9.5, short decay."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    ratios = [(1.0, 1.0, 0.18), (3.93, 0.42, 0.055), (9.5, 0.16, 0.022)]
    y = np.zeros(n)
    # Stiff excitation: a few samples of noise into the modes (already closed form).
    for ratio, g, tau in ratios:
        f = freq * ratio * (1.0 + rng.uniform(-0.002, 0.002))
        y += g * np.sin(2 * np.pi * f * t + rng.uniform(0, 0.4)) * np.exp(-t / tau)
    # A dry click at the strike so it reads as wood, not a pure tone.
    click_n = int(0.003 * SR)
    click = rng.standard_normal(click_n) * np.linspace(1.0, 0.0, click_n)
    click = bp_reson(np.pad(click, (0, n - click_n)), min(freq * 6.5, 7000), 3.5)
    y += 0.22 * click * strike
    y *= strike
    return soften(norm(y, 0.95), 4)


def fm_bell(freq, ratio=1.4, dur=2.8, index=2.4, tau=1.1):
    """Single FM bell. Logo signature is D3, ratio 1:1.4."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    # Index decays so the strike is bright and the tail is pure.
    ind = index * np.exp(-t / 0.35)
    mod = np.sin(2 * np.pi * freq * ratio * t)
    car = np.sin(2 * np.pi * freq * t + ind * mod)
    # A quiet second carrier an octave up, very short, for the "tick" of the strike.
    car += 0.18 * np.sin(2 * np.pi * freq * 2.0 * t + 0.6 * ind * mod) * np.exp(-t / 0.12)
    y = car * np.exp(-t / tau)
    # Soft attack so it doesn't spike.
    a = int(0.004 * SR)
    y[:a] *= np.linspace(0.0, 1.0, a)
    return soften(y * 0.8, 8)


def click_into_place(rng):
    """Soft mechanical click: two close transients, metal-on-detent."""
    n = int(0.09 * SR)
    y = np.zeros(n)
    for delay_ms, f, tau, g in ((0.0, 2400, 0.012, 0.7), (7.5, 1680, 0.018, 1.0), (14.0, 620, 0.02, 0.45)):
        d = int(delay_ms * 1e-3 * SR)
        m = n - d
        tt = np.arange(m) / SR
        y[d:] += g * np.sin(2 * np.pi * f * tt) * np.exp(-tt / tau)
    # Noise tick on the first transient.
    k = int(0.0015 * SR)
    y[:k] += rng.standard_normal(k) * 0.4 * np.linspace(1, 0, k)
    return soften(norm(y, 0.8), 4)


def rotor_air(dur, rng):
    """Rotating blades: filtered noise AM at blade-pass 4 -> 40 Hz, doppler pan.
    Returns stereo (n, 2)."""
    n = int(dur * SR)
    # A bit of pink so it isn't a hiss.
    src = pinkish(n, rng)
    src = bp_reson(np.pad(src, (0, 0)), 900, 1.6)
    # Narrower: band-limit the air to a whoosh-but-not-whoosh band.
    src = bp_reson(src, 1400, 1.3)
    t = np.arange(n) / SR
    # Blade-pass frequency rises 4 -> 40 Hz, ease-in (slow start, gathers).
    u = t / max(dur, 1e-6)
    u = u ** 1.6
    bpf = 4.0 + (40.0 - 4.0) * u
    phase = 2 * np.pi * np.cumsum(bpf) / SR
    # Three blades: fundamental + a weaker 2nd harmonic of the pass.
    am = 0.42 + 0.58 * (0.5 + 0.5 * np.sin(phase)) ** 1.4
    am *= 0.85 + 0.15 * np.sin(2 * phase)
    air = src * am
    # Level gathers with speed, then eases off into the shutter.
    level = np.clip(u * 1.3, 0, 1) ** 0.8
    level *= np.linspace(1.0, 0.55, n)
    air *= level
    # Doppler pan: a slow rotation, accelerating with bpf.
    pan_phase = phase / 3.0  # one pan cycle per 3 blade passes ~ one revolution if 3 blades
    pan = 0.55 * np.sin(pan_phase)
    ang = (pan + 1.0) * 0.25 * np.pi
    stereo = np.column_stack([air * np.cos(ang), air * np.sin(ang)])
    return stereo * 0.55


def shutter_thump(rng):
    """Dark shutter-close when the frame goes black."""
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * 58.0 * t) * np.exp(-t / 0.06)
    y += 0.45 * np.sin(2 * np.pi * 112.0 * t) * np.exp(-t / 0.035)
    y += 0.18 * np.sin(2 * np.pi * 240.0 * t) * np.exp(-t / 0.018)
    slap_n = int(0.008 * SR)
    slap = lp(noise(n, rng), 1800)
    slap *= 0
    slap = np.zeros(n)
    slap[:slap_n] = rng.standard_normal(slap_n) * np.linspace(1, 0, slap_n)
    slap = lp(slap, 2200)
    y += 0.35 * slap
    return soften(norm(y, 0.9), 4)


def granular_ticks(dur, rate0, rate1, rng, pan_center=0.0):
    """Soft ticks whose density rises. Returns list of (offset_samples, mono, pan)."""
    events = []
    t = 0.0
    while t < dur:
        u = t / max(dur, 1e-6)
        rate = rate0 + (rate1 - rate0) * (u ** 1.35)
        # jitter
        step = 1.0 / max(rate, 0.5) * rng.uniform(0.75, 1.25)
        n = int(rng.uniform(0.004, 0.011) * SR)
        f = rng.uniform(1400, 3200)
        tt = np.arange(n) / SR
        tick = np.sin(2 * np.pi * f * tt) * np.exp(-tt / rng.uniform(0.003, 0.008))
        tick += 0.25 * rng.standard_normal(n) * np.exp(-tt / 0.002)
        tick = soften(tick, 3)
        pan = np.clip(pan_center + rng.uniform(-0.35, 0.35), -0.8, 0.8)
        events.append((int(t * SR), tick * rng.uniform(0.35, 0.7), pan))
        t += step
    return events


def sine_glide(f0, f1, dur, tau_tail=0.35):
    """Rising sine that arrives at f1 and rings a little past `dur`."""
    tail = 0.55
    n = int((dur + tail) * SR)
    t = np.arange(n) / SR
    # Glide over `dur`, then hold.
    u = np.clip(t / max(dur, 1e-6), 0, 1)
    u = u ** 1.15
    f = f0 + (f1 - f0) * u
    phase = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(phase)
    e = np.ones(n)
    a = int(0.04 * SR)
    e[:a] = np.linspace(0, 1, a)
    # After arrival, decay.
    hold_end = int(dur * SR)
    if hold_end < n:
        tt = np.arange(n - hold_end) / SR
        e[hold_end:] *= np.exp(-tt / tau_tail)
    # Gentle level rise during the glide so it doesn't shout early.
    e[:hold_end] *= np.linspace(0.35, 1.0, hold_end)
    return y * e * 0.55


def fifth_chord(root_hz, dur=1.6):
    """Root + fifth + octave, soft, on raceWin."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    tones = [(1.0, 1.0, 0.7), (1.5, 0.62, 0.55), (2.0, 0.38, 0.4)]
    y = np.zeros(n)
    for ratio, g, tau in tones:
        y += g * np.sin(2 * np.pi * root_hz * ratio * t) * np.exp(-t / tau)
    a = int(0.012 * SR)
    y[:a] *= np.linspace(0, 1, a)
    return soften(y * 0.7, 8)


def latch_click(rng):
    """Two-transient counter lock."""
    n = int(0.07 * SR)
    y = np.zeros(n)
    for d_ms, f, tau, g in ((0.0, 3100, 0.006, 0.8), (11.0, 1900, 0.014, 1.0)):
        d = int(d_ms * 1e-3 * SR)
        m = n - d
        tt = np.arange(m) / SR
        y[d:] += g * np.sin(2 * np.pi * f * tt) * np.exp(-tt / tau)
        k = int(0.0012 * SR)
        y[d:d + k] += rng.standard_normal(k) * 0.35 * np.linspace(1, 0, k)
    return soften(norm(y, 0.85), 3)


def airy_expand(dur=0.45, rng=None):
    """Lowpassed noise opening — the bar growing into a terminal. Short."""
    n = int(dur * SR)
    x = pinkish(n, rng)
    # Opening filter: cutoff rises 180 -> 900 Hz.
    y = np.zeros(n)
    # Block-wise lowpass to keep it cheap and smooth.
    block = 256
    cuts = np.geomspace(180, 900, int(np.ceil(n / block)))
    pos = 0
    for c in cuts:
        b = min(block, n - pos)
        seg = x[pos:pos + b]
        # one-pole
        a = np.exp(-2 * np.pi * c / SR)
        acc = 0.0
        out = np.empty(b)
        for i in range(b):
            acc = a * acc + (1 - a) * seg[i]
            out[i] = acc
        y[pos:pos + b] = out
        pos += b
    e = env_ar(n, 0.05, dur * 0.7)
    return soften(y * e, 8)


def karplus(freq, dur=0.45, rng=None, brightness=0.5):
    """Karplus-Strong pizzicato pluck."""
    n = int(dur * SR)
    period = max(2, int(SR / freq))
    # Burst excitation.
    buf = rng.standard_normal(period) * np.hanning(period)
    y = np.zeros(n)
    # Feedback with a one-pole lowpass (the string loss).
    a = 0.5 + 0.45 * brightness  # averaging coefficient toward DC loss
    # Standard KS: y[n] = 0.5 * (y[n-P] + y[n-P-1]) * decay
    decay = 0.996
    # We'll run a delay line.
    line = np.zeros(period + 2)
    line[:period] = buf
    idx = 0
    prev = 0.0
    for i in range(n):
        s = line[idx]
        # lowpass in the loop
        avg = (1 - a) * s + a * prev
        prev = avg
        y[i] = s
        line[idx] = avg * decay
        idx = (idx + 1) % period
    # Tiny pick noise at the front.
    k = int(0.002 * SR)
    y[:k] += rng.standard_normal(k) * 0.15 * np.linspace(1, 0, k)
    return soften(norm(y, 0.8), 4)


def glass_ping(freq, dur=2.4):
    """Sine + 3rd harmonic, 3 ms attack, long tail."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * freq * t)
    y += 0.28 * np.sin(2 * np.pi * freq * 3.0 * t) * np.exp(-t / 0.35)
    y *= np.exp(-t / 1.15)
    a = int(0.003 * SR)
    y[:a] *= np.linspace(0, 1, a) ** 0.7
    return soften(y * 0.62, 6)


def chord_collapse_tail(freqs, dur=1.1, rng=None):
    """Reverse-swelled tail of a chord, used into the merge thud.
    Built forward then reversed so it swells into the thud."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for i, f in enumerate(freqs):
        y += (0.5 ** i) * np.sin(2 * np.pi * f * t) * np.exp(-t / 0.55)
    y = y[::-1]  # reverse swell
    # Fade the start (which is the old tail) so it doesn't pop in.
    a = int(0.08 * SR)
    y[:a] *= np.linspace(0, 1, a)
    y *= 0.45
    return soften(y, 8)


def tight_thud(rng):
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * 78.0 * t) * np.exp(-t / 0.045)
    y += 0.4 * np.sin(2 * np.pi * 156.0 * t) * np.exp(-t / 0.025)
    k = int(0.004 * SR)
    slap = np.zeros(n)
    slap[:k] = rng.standard_normal(k) * np.linspace(1, 0, k)
    y += 0.3 * lp(slap, 2500)
    return soften(norm(y, 0.9), 4)


def felt_piano(freq, rng, dur=0.7):
    """Additive thump, fast HF decay — felt-muted piano."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    partials = [(1.0, 1.0, 0.28), (2.0, 0.45, 0.08), (3.0, 0.22, 0.035),
                (4.01, 0.10, 0.018), (5.2, 0.05, 0.01)]
    y = np.zeros(n)
    for ratio, g, tau in partials:
        f = freq * ratio * (1 + rng.uniform(-0.0015, 0.0015))
        y += g * np.sin(2 * np.pi * f * t + rng.uniform(0, 0.5)) * np.exp(-t / tau)
    # Hammer noise, very short, lowpassed.
    k = int(0.006 * SR)
    hammer = np.zeros(n)
    hammer[:k] = rng.standard_normal(k) * np.linspace(1, 0, k) ** 0.5
    y += 0.18 * lp(hammer, 1800)
    a = int(0.004 * SR)
    y[:a] *= np.linspace(0, 1, a)
    return soften(norm(y, 0.85), 4)


def clock_tick(rng, pitch=2400.0):
    n = int(0.025 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * pitch * t) * np.exp(-t / 0.006)
    y += 0.3 * np.sin(2 * np.pi * pitch * 2.1 * t) * np.exp(-t / 0.003)
    k = min(n, int(0.001 * SR))
    y[:k] += rng.standard_normal(k) * 0.2
    return soften(y, 2)


def dry_clack(rng):
    n = int(0.04 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * 980 * t) * np.exp(-t / 0.008)
    y += 0.5 * np.sin(2 * np.pi * 2100 * t) * np.exp(-t / 0.004)
    return soften(norm(y, 0.7), 2)


def page_turn(rng, dur=0.55):
    """Band-limited noise, swept bandpass, flutter AM 8-14 Hz, soft landing."""
    n = int(dur * SR)
    x = noise(n, rng)
    # Sweep a bandpass from ~400 Hz up to ~3 kHz and back down — the page arc.
    u = np.linspace(0, 1, n)
    # Center frequency curve: rise then fall.
    fc = 500 + 2600 * np.sin(np.pi * u) ** 1.1
    y = np.zeros(n)
    # Sample-wise RBJ bandpass, moderate Q.
    x1 = x2 = y1 = y2 = 0.0
    q = 1.6
    for i in range(n):
        w0 = 2 * np.pi * fc[i] / SR
        alpha = np.sin(w0) / (2 * q)
        cosw = np.cos(w0)
        b0 = alpha
        b2 = -alpha
        a0 = 1 + alpha
        a1 = -2 * cosw
        a2 = 1 - alpha
        yi = (b0 / a0) * x[i] + (b2 / a0) * x2 - (a1 / a0) * y1 - (a2 / a0) * y2
        x2, x1 = x1, x[i]
        y2, y1 = y1, yi
        y[i] = yi
    t = np.arange(n) / SR
    flutter_f = 8 + 6 * u  # 8 -> 14 Hz
    flutter = 0.55 + 0.45 * np.sin(2 * np.pi * np.cumsum(flutter_f) / SR)
    e = np.sin(np.pi * u) ** 0.8
    y = y * flutter * e
    # Soft landing: a low muted tap at the end.
    land_n = int(0.06 * SR)
    land_at = n - int(0.07 * SR)
    tt = np.arange(land_n) / SR
    land = np.sin(2 * np.pi * 140 * tt) * np.exp(-tt / 0.02)
    land += 0.3 * np.sin(2 * np.pi * 90 * tt) * np.exp(-tt / 0.03)
    y[land_at:land_at + land_n] += land * 0.8
    return soften(norm(y, 0.75), 10)


def sub_swell(f=48.0, dur=2.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * f * t)
    # Slow attack, long body, gentle release.
    a = int(0.55 * SR)
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a) ** 1.4
    rel = int(0.7 * SR)
    e[-rel:] *= np.linspace(1, 0, rel)
    return y * e * 0.7


def wooden_drop(freq, rng, glass=False):
    """Small drop: short modal wood, or a glassier variant on even pours."""
    if glass:
        n = int(0.38 * SR)
        t = np.arange(n) / SR
        y = np.sin(2 * np.pi * freq * t) * np.exp(-t / 0.12)
        y += 0.35 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t / 0.05)
        y += 0.12 * np.sin(2 * np.pi * freq * 5.4 * t) * np.exp(-t / 0.02)
        a = int(0.002 * SR)
        y[:a] *= np.linspace(0, 1, a)
        return soften(y * 0.7, 3)
    return modal_bar(freq, rng, dur=0.32, strike=0.7) * 0.75


def paper_slide(rng, dur=0.28):
    n = int(dur * SR)
    x = noise(n, rng)
    x = bp_reson(x, 1800, 1.4)
    x = hp(x, 700)
    u = np.linspace(0, 1, n)
    e = np.sin(np.pi * u) ** 1.2
    return soften(x * e * 0.4, 6)


def descending_wood(freq, rng):
    return modal_bar(freq, rng, dur=0.42, strike=0.65) * 0.7


def inhale(dur=0.8, rng=None):
    """Spectral filtered-noise inhale, ~0.8s, then we cut it."""
    n = int(dur * SR)
    x = pinkish(n, rng)
    # Rising band: air being drawn in. Center climbs 200 -> 1800.
    fc = np.geomspace(220, 1600, n)
    y = np.zeros(n)
    x1 = x2 = y1 = y2 = 0.0
    q = 1.1
    for i in range(n):
        w0 = 2 * np.pi * min(fc[i], SR * 0.4) / SR
        alpha = np.sin(w0) / (2 * q)
        cosw = np.cos(w0)
        a0 = 1 + alpha
        yi = (alpha / a0) * x[i] + ((-alpha) / a0) * x2 - ((-2 * cosw) / a0) * y1 - ((1 - alpha) / a0) * y2
        x2, x1 = x1, x[i]
        y2, y1 = y1, yi
        y[i] = yi
    u = np.linspace(0, 1, n)
    e = u ** 1.3  # inhale builds
    # Cut hard at the end (the brief says cut to silence). A 4 ms fade only,
    # so it doesn't tick but still reads as a cut.
    fade = int(0.004 * SR)
    e[-fade:] *= np.linspace(1, 0, fade)
    return soften(y * e, 4) * 0.8


def stepper_burst(rng, dur=0.09, rate=50.0):
    """Thermal-printer line advance: 40-60 Hz stepper pulses + HF crackle."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    # Pulse train.
    phase = 2 * np.pi * rate * t
    pulse = (np.sin(phase) > 0.55).astype(np.float64)
    # Each pulse is a short damped click, not a square.
    click_len = int(0.0035 * SR)
    click = np.sin(2 * np.pi * 1800 * np.arange(click_len) / SR) * np.exp(-np.arange(click_len) / (0.0012 * SR))
    click += 0.4 * np.sin(2 * np.pi * 420 * np.arange(click_len) / SR) * np.exp(-np.arange(click_len) / (0.0016 * SR))
    y = np.zeros(n)
    onsets = np.where(np.diff(pulse, prepend=0) > 0)[0]
    for o in onsets:
        m = min(click_len, n - o)
        y[o:o + m] += click[:m]
    # HF crackle, gated loosely to the burst. Band-limited to 9 kHz:
    # unfiltered crackle above ~12 kHz is what pushes the intersample
    # true-peak meter over the ceiling after loudnorm, and a thermal head
    # doesn't put meaningful energy up there anyway.
    crack = hp(noise(n, rng), 4000)
    crack = lp(crack, 9000)
    y += crack * 0.18 * (0.4 + 0.6 * np.clip(np.abs(y) * 4, 0, 1))
    y = lp(y, 10000)
    e = env_ar(n, 0.004, dur * 0.45)
    return soften(y * e, 3)


def printer_idle(rng, dur=0.55, rate=46.0):
    """Quieter continuous feed between line bursts."""
    return stepper_burst(rng, dur=dur, rate=rate) * 0.28


def rubber_stamp(rng):
    """Dense rubber thump: low-mid damped body + short noise slap."""
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * 145 * t) * np.exp(-t / 0.04)
    y += 0.55 * np.sin(2 * np.pi * 230 * t) * np.exp(-t / 0.025)
    y += 0.25 * np.sin(2 * np.pi * 410 * t) * np.exp(-t / 0.014)
    y += 0.12 * np.sin(2 * np.pi * 90 * t) * np.exp(-t / 0.05)
    slap_n = int(0.009 * SR)
    slap = np.zeros(n)
    slap[:slap_n] = rng.standard_normal(slap_n) * np.linspace(1, 0, slap_n)
    slap = bp_reson(slap, 1600, 1.5)
    y += 0.55 * slap
    return soften(norm(y, 0.95), 4)


def paper_tear(rng, dur=0.35):
    """Crackly tear: noise with random micro-transients, sweeping highpass."""
    n = int(dur * SR)
    x = noise(n, rng)
    # Sweeping highpass 400 -> 5000.
    fc = np.geomspace(400, 5200, n)
    y = np.zeros(n)
    # One-pole highpass, cutoff per sample.
    prev_x = 0.0
    prev_y = 0.0
    for i in range(n):
        a = np.exp(-2 * np.pi * min(fc[i], SR * 0.45) / SR)
        # y[n] = a*(y[n-1] + x[n] - x[n-1])
        prev_y = a * (prev_y + x[i] - prev_x)
        prev_x = x[i]
        y[i] = prev_y
    # Micro-transients: irregular fiber snaps. Kept under 6 kHz so the
    # tear reads as paper, not as a true-peak spike.
    n_snaps = int(rng.integers(18, 28))
    for _ in range(n_snaps):
        at = int(rng.uniform(0.01, 0.92) * n)
        ln = int(rng.uniform(0.001, 0.004) * SR)
        ln = min(ln, n - at)
        f = rng.uniform(1400, 5500)
        tt = np.arange(ln) / SR
        snap = np.sin(2 * np.pi * f * tt) * np.exp(-tt / rng.uniform(0.001, 0.003))
        y[at:at + ln] += snap * rng.uniform(0.25, 0.7)
    u = np.linspace(0, 1, n)
    e = np.sin(np.pi * np.clip(u * 1.05, 0, 1)) ** 0.6
    e *= np.linspace(0.7, 1.0, n)
    return soften(norm(y * e, 0.8), 6)


# ---------------------------------------------------------------------------
# Drone bed
# ---------------------------------------------------------------------------

def render_drone(n, scenes, fps, silence_span):
    """Additive detuned partials, scene-chord changes with ~1s voice-led
    crossfades. Wow ±3 cents at 0.3 Hz. Soft tanh. Very low level.

    silence_span: (start_sample, end_sample) forced to exact zero, including
    a short fade into it so the cut is musical rather than a tick — the
    window itself is digital zero.
    """
    # Build a list of (start_s, end_s, chord_key) regions.
    order = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]
    regions = []
    for sid in order:
        s = scenes[sid]
        t0 = s["from"] / fps
        t1 = (s["from"] + s["dur"]) / fps
        if sid == "S7":
            # Gsus4 until the fallaway begins, then resolve toward D.
            # fallaway[0] is scene-local 110.
            mid = (s["from"] + 110) / fps
            regions.append((t0, mid, "S7a"))
            regions.append((mid, t1, "S7b"))
        else:
            regions.append((t0, t1, sid))

    # Collect every midi we might voice, so the crossfade is per-partial.
    all_midis = sorted({m for key in CHORDS for m, _g in CHORDS[key]})
    # Target gain per partial over time, block-wise (control rate 200 Hz).
    ctrl = 200
    n_ctrl = int(np.ceil(n / (SR / ctrl))) + 2
    gains = {m: np.zeros(n_ctrl) for m in all_midis}
    xfade = 1.0  # seconds

    def chord_gain_map(key):
        return {m: g for m, g in CHORDS[key]}

    for t0, t1, key in regions:
        gmap = chord_gain_map(key)
        # Crossfade in from previous over `xfade` seconds, except S1 (silent)
        # and the hard silence (handled later).
        c0 = int(t0 * ctrl)
        c1 = int(t1 * ctrl)
        c0 = max(0, min(c0, n_ctrl))
        c1 = max(0, min(c1, n_ctrl))
        for m in all_midis:
            target = gmap.get(m, 0.0)
            gains[m][c0:c1] = target
        # Smooth the boundary by ramping the first xfade seconds.
        ramp_n = int(xfade * ctrl)
        if c0 > 0 and ramp_n > 0:
            a = max(0, c0 - ramp_n // 2)
            b = min(n_ctrl, c0 + ramp_n // 2)
            if b > a:
                # Already set; we'll lowpass the whole gain curve below.
                pass

    # Lowpass gain curves so chord changes are ~1s voice-leading, not steps.
    # One-pole at ~1.2 Hz.
    alpha = np.exp(-2 * np.pi * 1.2 / ctrl)
    for m in all_midis:
        g = gains[m]
        acc = 0.0
        for i in range(g.size):
            acc = alpha * acc + (1 - alpha) * g[i]
            g[i] = acc

    # Render per partial. Each partial is a sine with slow beating (two
    # detuned copies) and a 0.3 Hz wow of ±3 cents.
    t = np.arange(n) / SR
    wow = np.sin(2 * np.pi * 0.3 * t)  # ±1
    cents = 3.0
    wow_ratio = 2.0 ** (wow * cents / 1200.0)  # multiplicative

    bed = np.zeros(n, dtype=np.float64)
    # Stereo: odd partials lean left a hair, even right, plus a decorrelated copy.
    bed_l = np.zeros(n)
    bed_r = np.zeros(n)

    for i, m in enumerate(all_midis):
        g = gains[m]
        if np.max(g) < 1e-4:
            continue
        # Upsample gain to audio rate (linear, control blocks).
        gi = np.interp(np.arange(n), np.arange(g.size) * (SR / ctrl), g)
        f0 = midi_hz(m)
        # Two detuned oscillators for beating. Detune fixed per partial, ±4-9 cents.
        detune_cents = 4.0 + (i % 5) * 1.1
        r_up = 2.0 ** (detune_cents / 1200.0)
        r_dn = 2.0 ** (-detune_cents / 1200.0)
        # Phase with wow: integrate instantaneous frequency.
        inst = f0 * wow_ratio
        phase = 2 * np.pi * np.cumsum(inst) / SR
        osc = 0.5 * np.sin(phase * r_up) + 0.5 * np.sin(phase * r_dn)
        # Very slow amplitude beating already comes from the detune.
        sig = osc * gi
        # Pan: spread the voicing a little, never wide.
        pan = -0.25 + 0.5 * (i / max(1, len(all_midis) - 1))
        ang = (pan + 1.0) * 0.25 * np.pi
        bed_l += sig * np.cos(ang)
        bed_r += sig * np.sin(ang)

    # Level: around -28 dBFS relative to a full-scale sine. A sine at gain 1
    # is 0 dBFS peak; -28 dBFS is 10^(-28/20) ≈ 0.04. The chord sums several
    # partials, so scale the whole bed to land near that.
    peak = np.max(np.abs(np.column_stack([bed_l, bed_r]))) + 1e-12
    target = 10 ** (-28.0 / 20.0)  # ~0.0398
    # Leave a little room: the summed chord should peak near -28, not each partial.
    scale = target / peak
    bed_l *= scale
    bed_r *= scale

    # Soft tape saturation.
    drive = 1.6
    bed_l = np.tanh(bed_l * drive) / np.tanh(drive)
    bed_r = np.tanh(bed_r * drive) / np.tanh(drive)

    # Hard silence window: fade 30 ms into it, exact zero inside, fade 40 ms out.
    if silence_span is not None:
        a, b = silence_span
        a = int(np.clip(a, 0, n))
        b = int(np.clip(b, 0, n))
        fade_in = int(0.03 * SR)
        fade_out = int(0.04 * SR)
        if a - fade_in > 0:
            ramp = np.linspace(1, 0, fade_in)
            bed_l[a - fade_in:a] *= ramp
            bed_r[a - fade_in:a] *= ramp
        bed_l[a:b] = 0.0
        bed_r[a:b] = 0.0
        if b + fade_out < n:
            ramp = np.linspace(0, 1, fade_out)
            bed_l[b:b + fade_out] *= ramp
            bed_r[b:b + fade_out] *= ramp

    return np.column_stack([bed_l, bed_r])


# ---------------------------------------------------------------------------
# Schroeder / FDN reverb (small, written here, no external impulse)
# ---------------------------------------------------------------------------

def schroeder(x, sr, comb_ms, ap_ms, comb_g, ap_g, predelay_ms=8):
    """Mono Schroeder: parallel combs -> series allpasses. x is 1-D."""
    n = x.size
    y = np.zeros(n)
    # Predelay.
    pre = int(predelay_ms * 1e-3 * sr)
    src = np.zeros(n)
    if pre < n:
        src[pre:] = x[:n - pre]
    else:
        src = x.copy()
    for ms, g in zip(comb_ms, comb_g):
        d = int(ms * 1e-3 * sr)
        buf = np.zeros(d)
        idx = 0
        acc = np.zeros(n)
        for i in range(n):
            delayed = buf[idx]
            acc[i] = delayed
            buf[idx] = src[i] + g * delayed
            idx += 1
            if idx >= d:
                idx = 0
        y += acc
    y *= 1.0 / max(len(comb_ms), 1)
    for ms, g in zip(ap_ms, ap_g):
        d = max(1, int(ms * 1e-3 * sr))
        buf = np.zeros(d)
        idx = 0
        out = np.zeros(n)
        for i in range(n):
            delayed = buf[idx]
            v = y[i] - g * delayed
            out[i] = g * v + delayed
            buf[idx] = v
            idx += 1
            if idx >= d:
                idx = 0
        y = out
    return y


def fdn_stereo(send, kind, sr):
    """Decorrelated stereo reverb. `kind` is 'room' or 'plate'.
    send is (n, 2); we sum to mono excitation then decorrelate the returns
    with different delay sets per channel, and a touch of crossfeed.
    """
    n = send.shape[0]
    exc = send[:, 0] * 0.7 + send[:, 1] * 0.7
    if kind == "room":
        # Small room: short combs, modest feedback. Foley.
        combs_l = [23.1, 29.7, 37.3, 43.9]
        combs_r = [25.3, 31.1, 39.7, 47.3]
        gl = [0.62, 0.66, 0.70, 0.64]
        gr = [0.64, 0.68, 0.69, 0.63]
        ap = [5.1, 7.7]
        apg = [0.55, 0.45]
        pre = 6
        wet = 0.55
    else:
        # Larger plate: longer, brighter feedback, for bells and glass.
        combs_l = [41.3, 53.7, 67.9, 79.1]
        combs_r = [43.9, 57.1, 71.3, 83.7]
        gl = [0.78, 0.80, 0.82, 0.76]
        gr = [0.79, 0.81, 0.80, 0.77]
        ap = [8.3, 12.7, 17.1]
        apg = [0.62, 0.55, 0.48]
        pre = 14
        wet = 0.7
    l = schroeder(exc, sr, combs_l, ap, gl, apg, predelay_ms=pre)
    r = schroeder(exc, sr, combs_r, ap, gr, apg, predelay_ms=pre + 3)
    # A little damping so the plate doesn't ring forever as white noise.
    l = lp(l, 6500 if kind == "plate" else 5000)
    r = lp(r, 6500 if kind == "plate" else 5000)
    # Crossfeed for width without a hole in the middle.
    ll = l * 0.85 + r * 0.15
    rr = r * 0.85 + l * 0.15
    return np.column_stack([ll, rr]) * wet


# ---------------------------------------------------------------------------
# WAV writer (24-bit PCM, no extra deps)
# ---------------------------------------------------------------------------

def write_wav_24(path, audio, sr):
    """audio: (n, 2) float in roughly [-1, 1]."""
    audio = np.clip(audio, -1.0, 1.0)
    pcm = np.round(audio * (2 ** 23 - 1)).astype(np.int32)
    # Pack 24-bit little-endian.
    pcm_bytes = bytearray()
    # Vectorized pack.
    interleaved = pcm.reshape(-1)
    b = np.empty(interleaved.size * 3, dtype=np.uint8)
    v = interleaved.astype(np.uint32)
    # two's complement already in the low 24 of int32 when we mask after
    # converting via view. int32 negative: low 24 bits are the two's complement.
    u = interleaved.view(np.uint32)
    b[0::3] = (u & 0xFF).astype(np.uint8)
    b[1::3] = ((u >> 8) & 0xFF).astype(np.uint8)
    b[2::3] = ((u >> 16) & 0xFF).astype(np.uint8)
    data = b.tobytes()
    n_samples = audio.shape[0]
    channels = 2
    bits = 24
    block_align = channels * bits // 8
    byte_rate = sr * block_align
    data_size = len(data)
    import struct
    header = b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
    fmt = struct.pack("<HHIIHH", 1, channels, sr, byte_rate, block_align, bits)
    header += b"fmt " + struct.pack("<I", 16) + fmt
    header += b"data" + struct.pack("<I", data_size)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(header)
        f.write(data)


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

def build():
    fps, total_frames, scenes, cues = load_timeline()
    duration = total_frames / fps
    n = int(round(duration * SR))
    assert abs(n / SR - 75.0) < 1e-9 or abs(duration - 75.0) < 1e-9
    n = int(round(75.0 * SR))  # exactly 75.000 s at 48 kHz

    rng = np.random.default_rng(SEED)
    mix = Mix(n)
    report = []

    def t_of(sid, frame):
        return abs_time(scenes, fps, sid, frame)

    def s_of(sid, frame):
        return int(round(t_of(sid, frame) * SR))

    def note(sid, key, idx, frame, sounds):
        tt = t_of(sid, frame)
        label = f"{sid}.{key}" if idx is None else f"{sid}.{key}[{idx}]"
        report.append((tt, label, frame, sounds))

    # ----- S1 cream world: dry, close, no bed -----
    s1 = cues["S1"]
    for i, fr in enumerate(s1["keystrokes"]):
        y = keystroke(rng, enter=False, world="paper")
        # Per-key pitch is already inside the voice via resonance wander;
        # level ±2 dB, slight pan.
        db = rng.uniform(-2.0, 2.0)
        g = 0.42 * (10 ** (db / 20.0))
        pan = rng.uniform(-0.12, 0.12)
        mix.add(s_of("S1", fr), y, pan=pan, gain=g, send_room=0.08)
        note("S1", "keystrokes", i, fr, "paper keystroke (body modes 1.8/3.4/6k + thock)")

    y = keystroke(rng, enter=True, world="paper")
    mix.add(s_of("S1", s1["enter"]), y, pan=0.0, gain=0.55, send_room=0.1)
    note("S1", "enter", None, s1["enter"], "heavier enter key (lower thock, longer)")

    # rotorForm: click-into-place + logo bell D3
    click = click_into_place(rng)
    mix.add(s_of("S1", s1["rotorForm"]), click, pan=0.0, gain=0.5, send_room=0.18)
    bell = fm_bell(midi_hz(D3), ratio=1.4, dur=2.6, index=2.2, tau=1.15)
    mix.add(s_of("S1", s1["rotorForm"]) + int(0.02 * SR), bell, pan=0.0, gain=0.34, send_plate=0.55)
    note("S1", "rotorForm", None, s1["rotorForm"], "detent click + FM bell D3 ratio 1:1.4 (logo)")

    # rotorSpin: air, accelerating blade-pass, until shutter.
    # Spin runs from rotorSpin to scene end (frame goes black by +40 of the
    # spin, i.e. local 172, scene ends 180). Shutter lands as the frame closes.
    spin_start = s1["rotorSpin"]
    shutter_frame = s1["rotorSpin"] + 40  # brief: blades sweep to black by +40
    spin_dur = (shutter_frame - spin_start) / fps
    air = rotor_air(spin_dur, rng)
    mix.add_stereo(s_of("S1", spin_start), air * 0.55)
    # A little room on the air so it isn't bone-dry, but it's mostly dry/moving.
    mix.room[s_of("S1", spin_start):s_of("S1", spin_start) + air.shape[0]] += air * 0.12
    note("S1", "rotorSpin", None, spin_start,
         f"blade-pass air 4->40 Hz, doppler pan, {spin_dur:.2f}s")

    thump = shutter_thump(rng)
    mix.add(s_of("S1", shutter_frame), thump, pan=0.0, gain=0.62, send_room=0.22)
    note("S1", "rotorSpin+40", None, shutter_frame, "shutter-close thump (frame to black)")

    # ----- S2 dark: chips, threads, lanes -----
    s2 = cues["S2"]
    # Headline: a single quiet low tone, not a whoosh. Just marks the cut.
    mix.add(s_of("S2", s2["headline"]), fm_bell(midi_hz(A3), ratio=1.0, dur=1.4, index=0.8, tau=0.7),
            pan=0.0, gain=0.08, send_plate=0.3)
    note("S2", "headline", None, s2["headline"], "quiet A3 tone (no whoosh)")

    chip_notes = [D4, E4, FS4, A4M, B4]  # D major pentatonic
    for i, fr in enumerate(s2["chipLand"]):
        # Thread friction just before the land.
        fric = string_friction(rng, dur=0.18)
        mix.add(s_of("S2", fr) - int(0.14 * SR), fric, pan=rng.uniform(-0.2, 0.2),
                gain=0.045, send_room=0.05)
        bar = modal_bar(midi_hz(chip_notes[i]), rng, dur=0.6, strike=1.0)
        pan = -0.35 + 0.7 * (i / 4)
        mix.add(s_of("S2", fr), bar, pan=pan, gain=0.38, send_room=0.16, send_plate=0.08)
        note("S2", "chipLand", i, fr,
             f"thread friction + wooden bar {['D4','E4','F#4','A4','B4'][i]}")

    # Lanes draw in: five quiet dry ticks, left to right, like a pen.
    lane_t = s_of("S2", s2["lanes"])
    for i in range(5):
        tick = clock_tick(rng, pitch=1600 + i * 180)
        mix.add(lane_t + int(i * 0.045 * SR), tick, pan=-0.4 + i * 0.2, gain=0.12, send_room=0.06)
    note("S2", "lanes", None, s2["lanes"], "5 dry pen-ticks L->R as lanes draw")

    # ----- S3 bar race -----
    s3 = cues["S3"]
    mix.add(s_of("S3", s3["headline"]),
            fm_bell(midi_hz(BB4), ratio=1.0, dur=1.2, index=0.6, tau=0.55),
            pan=0.0, gain=0.07, send_plate=0.25)
    note("S3", "headline", None, s3["headline"], "quiet Bb4 tone")

    race_dur = (s3["raceWin"] - s3["raceStart"]) / fps
    # Granular ticks, density rising. Three loose streams (the other bars)
    # plus the Droid glide.
    for stream, pan_c, r0, r1 in (
        (0, -0.45, 3.5, 14.0),
        (1, 0.15, 2.5, 9.0),
        (2, 0.5, 2.0, 7.0),
    ):
        events = granular_ticks(race_dur, r0, r1, rng, pan_center=pan_c)
        base = s_of("S3", s3["raceStart"])
        for off, tick, pan in events:
            mix.add(base + off, tick, pan=pan, gain=0.07, send_room=0.05)
    # Droid bar: rising sine D4 -> A4 (a fifth), resolves on raceWin.
    glide = sine_glide(midi_hz(D4), midi_hz(A4M), race_dur, tau_tail=0.5)
    mix.add(s_of("S3", s3["raceStart"]), glide, pan=0.05, gain=0.16, send_plate=0.12)
    note("S3", "raceStart", None, s3["raceStart"],
         f"granular ticks x3 streams + D4->A4 glide over {race_dur:.2f}s")

    chord = fifth_chord(midi_hz(D4), dur=1.5)
    mix.add(s_of("S3", s3["raceWin"]), chord, pan=0.0, gain=0.22, send_plate=0.35)
    latch = latch_click(rng)
    mix.add(s_of("S3", s3["raceWin"]), latch, pan=0.02, gain=0.55, send_room=0.1)
    note("S3", "raceWin", None, s3["raceWin"], "fifth chord (D4+A4+D5) + two-transient latch click")

    expand = airy_expand(0.42, rng)
    mix.add(s_of("S3", s3["growToTerminal"]), expand, pan=0.0, gain=0.2, send_room=0.15)
    note("S3", "growToTerminal", None, s3["growToTerminal"], "short lowpassed-noise opening")

    # ----- S4 terminal -----
    s4 = cues["S4"]
    for i, fr in enumerate(s4["keystrokes"]):
        y = keystroke(rng, enter=False, world="terminal")
        db = rng.uniform(-2.0, 2.0)
        g = 0.30 * (10 ** (db / 20.0))
        pan = rng.uniform(-0.06, 0.06)  # tighter image inside the terminal
        mix.add(s_of("S4", fr), y, pan=pan, gain=g, send_room=0.05)
        note("S4", "keystrokes", i, fr, "terminal keystroke (tighter body, less room)")

    # specOk: a small affirmative — glass ping on D5, dry.
    ping = glass_ping(midi_hz(D5), dur=1.1)
    mix.add(s_of("S4", s4["specOk"]), ping, pan=0.0, gain=0.28, send_plate=0.3)
    ok_click = latch_click(rng)
    mix.add(s_of("S4", s4["specOk"]), ok_click, pan=0.0, gain=0.28, send_room=0.06)
    note("S4", "specOk", None, s4["specOk"], "D5 glass ping + small latch")

    # fanOut: 5 KS plucks, L->R, a quick ascending pick.
    fan_notes = [D4, E4, FS4, A4M, B4]
    for i, m in enumerate(fan_notes):
        pluck = karplus(midi_hz(m + 12), dur=0.5, rng=rng, brightness=0.45)  # an octave up, tiny
        delay = int(i * 0.035 * SR)
        pan = -0.6 + 1.2 * (i / 4)
        mix.add(s_of("S4", s4["fanOut"]) + delay, pluck, pan=pan, gain=0.32, send_room=0.1)
    note("S4", "fanOut", None, s4["fanOut"], "5 Karplus plucks D5-B5 panned L->R, 35ms apart")

    # checks: Dmaj9 stack D5 F#5 A5 C#6 E6
    check_notes = [D5, FS5, A5, CS6, E6]
    check_names = ["D5", "F#5", "A5", "C#6", "E6"]
    for i, (fr, m) in enumerate(zip(s4["checks"], check_notes)):
        gping = glass_ping(midi_hz(m), dur=2.6)
        pan = -0.4 + 0.8 * (i / 4)
        mix.add(s_of("S4", fr), gping, pan=pan, gain=0.26, send_plate=0.45)
        note("S4", "checks", i, fr, f"glass ping {check_names[i]} (Dmaj9 stack)")

    # merge: reverse swell of the chord into a thud.
    # Place the swell so it crests AT the merge frame.
    swell_dur = 0.9
    swell = chord_collapse_tail([midi_hz(m) for m in check_notes], dur=swell_dur, rng=rng)
    mix.add(s_of("S4", s4["merge"]) - int(swell_dur * SR), swell, pan=0.0, gain=0.3, send_plate=0.2)
    thud = tight_thud(rng)
    mix.add(s_of("S4", s4["merge"]), thud, pan=0.0, gain=0.55, send_room=0.18)
    note("S4", "merge", None, s4["merge"], "reverse-swelled Dmaj9 tail collapsing into a tight thud")

    # ----- S5 plans, meters, silence, page -----
    s5 = cues["S5"]
    card_notes = [G4, A4M, D5]  # rising
    card_names = ["G4", "A4", "D5"]
    for i, fr in enumerate(s5["cards"]):
        th = felt_piano(midi_hz(card_notes[i]), rng, dur=0.8)
        pan = -0.3 + 0.3 * i
        mix.add(s_of("S5", fr), th, pan=pan, gain=0.36, send_room=0.14)
        note("S5", "cards", i, fr, f"felt-muted piano thump {card_names[i]}")

    # Three clock rings at different rates, from meterFill to meterFull.
    fill_t = t_of("S5", s5["meterFill"])
    full_t = t_of("S5", s5["meterFull"])
    fill_dur = full_t - fill_t
    # 5h / 7d / 30d — three rates, all accelerating, none frantic.
    # Start sparse, end near 8-14 Hz so it reads as a clock running out.
    clocks = [
        ("5h", 2.0, 11.0, 0.22, 2100.0),
        ("7d", 1.2, 7.5, -0.28, 1600.0),
        ("30d", 0.7, 4.5, 0.0, 1100.0),
    ]
    for name, r0, r1, pan, pitch in clocks:
        tt = 0.0
        k = 0
        while tt < fill_dur - 0.02:
            u = tt / fill_dur
            rate = r0 + (r1 - r0) * (u ** 1.5)
            step = 1.0 / rate
            tick = clock_tick(rng, pitch=pitch * (1 + rng.uniform(-0.01, 0.01)))
            # Ticks get slightly louder as the ring fills.
            g = 0.055 + 0.06 * u
            mix.add(int(round((fill_t + tt) * SR)), tick, pan=pan, gain=g, send_room=0.04)
            tt += step * rng.uniform(0.92, 1.08)
            k += 1
        note("S5", "meterFill", None, s5["meterFill"],
             f"clock '{name}' {r0:.1f}->{r1:.1f} Hz ({k} ticks) [listed once]")
    # The note() above fires 3 times with the same timestamp; that's fine,
    # the report shows the three rings. But it says meterFill three times
    # which is what we want (one line per ring). Good.

    # meterFull: one dry clack, then HARD SILENCE until pageFlip.
    clack = dry_clack(rng)
    mix.add(s_of("S5", s5["meterFull"]), clack, pan=0.0, gain=0.4, send_room=0.0)
    note("S5", "meterFull", None, s5["meterFull"], "dry clack, then HARD SILENCE until pageFlip")

    silence_a = s_of("S5", s5["meterFull"]) + int(0.05 * SR)  # clack is ~40ms; zero after it
    # The brief says silence from meterFull to pageFlip. The clack IS the
    # meterFull sound, so the zero window starts just after the clack dies
    # and runs to the pageFlip sample. We also zero the drone across the
    # whole span including a fade before meterFull.
    silence_b = s_of("S5", s5["pageFlip"])
    # Drone silence starts a little before meterFull so nothing sustains in.
    drone_silence = (s_of("S5", s5["meterFull"]) - int(0.02 * SR), silence_b)

    flip = page_turn(rng, dur=0.62)
    mix.add(s_of("S5", s5["pageFlip"]), flip, pan=0.04, gain=0.5, send_room=0.2)
    note("S5", "pageFlip", None, s5["pageFlip"], "paper page-turn (swept bandpass + flutter AM + landing)")

    # ----- S6 Droid Core: the warm lift -----
    s6 = cues["S6"]
    swell = sub_swell(f=46.0, dur=2.4)
    mix.add(s_of("S6", s6["coreRise"]), swell, pan=0.0, gain=0.45, send_room=0.0)
    # A quiet rising fifth inside the swell, not a riser — one tone.
    lift = sine_glide(midi_hz(D3), midi_hz(E3), 1.6, tau_tail=0.8)
    mix.add(s_of("S6", s6["coreRise"]) + int(0.15 * SR), lift, pan=0.0, gain=0.1, send_plate=0.2)
    note("S6", "coreRise", None, s6["coreRise"], "sub swell ~46 Hz + quiet D3->E3 (whole-step lift)")

    pour_notes = [D4, E4, FS4, A4M, B4, D5, E5, FS5]
    pour_names = ["D4", "E4", "F#4", "A4", "B4", "D5", "E5", "F#5"]
    for i, fr in enumerate(s6["modelsPour"]):
        glass = (i % 2 == 1)
        drop = wooden_drop(midi_hz(pour_notes[i]), rng, glass=glass)
        pan = -0.45 if i % 2 == 0 else 0.45
        mix.add(s_of("S6", fr), drop, pan=pan, gain=0.26,
                send_room=0.1, send_plate=0.18 if glass else 0.05)
        kind = "glass drop" if glass else "wooden drop"
        note("S6", "modelsPour", i, fr, f"{kind} {pour_names[i]} pan {'R' if i % 2 else 'L'}")

    # Caption: one quiet low bell, or nothing. One bell.
    cap = fm_bell(midi_hz(D3), ratio=1.4, dur=1.8, index=1.2, tau=0.9)
    mix.add(s_of("S6", s6["caption"]), cap, pan=0.0, gain=0.1, send_plate=0.35)
    note("S6", "caption", None, s6["caption"], "quiet logo bell D3 (under the line, not a sting)")

    # merge ⊕: two latching clicks + logo bell.
    for i, delay_ms in enumerate((0.0, 70.0)):
        c = latch_click(rng)
        mix.add(s_of("S6", s6["merge"]) + int(delay_ms * 1e-3 * SR), c,
                pan=-0.15 if i == 0 else 0.15, gain=0.42, send_room=0.08)
    bell = fm_bell(midi_hz(D3), ratio=1.4, dur=2.2, index=2.0, tau=1.0)
    mix.add(s_of("S6", s6["merge"]) + int(0.04 * SR), bell, pan=0.0, gain=0.3, send_plate=0.5)
    note("S6", "merge", None, s6["merge"], "two latch clicks (one per bar) + logo bell D3")

    # ----- S7 thesis -----
    s7 = cues["S7"]
    # line1: a single soft key-thock.
    thock = keystroke(rng, enter=False, world="paper")
    mix.add(s_of("S7", s7["line1"]), thock, pan=0.0, gain=0.28, send_room=0.06)
    note("S7", "line1", None, s7["line1"], "single soft key-thock")

    # line2: no new gesture — the line is read, not announced. A barely-there
    # second thock would nag. Leave it silent; the bed carries the sentence.
    note("S7", "line2", None, s7["line2"], "(no sound — the sentence is read, not scored)")

    fall_notes = [A4M, FS4, D4]  # descending
    fall_names = ["A4", "F#4", "D4"]
    for i, fr in enumerate(s7["fallaway"]):
        wood = descending_wood(midi_hz(fall_notes[i]), rng)
        slide = paper_slide(rng, dur=0.32)
        pan = -0.3 + 0.3 * i
        mix.add(s_of("S7", fr), wood, pan=pan, gain=0.3, send_room=0.12)
        mix.add(s_of("S7", fr) + int(0.02 * SR), slide, pan=pan * 0.5, gain=0.16, send_room=0.08)
        note("S7", "fallaway", i, fr, f"descending muted wood {fall_names[i]} + paper slide")

    # zoom: inhale from the zoom cue, cut to silence exactly when the picture
    # goes black. S7 holds cream until scene-local frame 230, then a solid
    # ink frame (see src/scenes/S7.tsx: `if (frame >= 230) return <Fill bg={C.ink} />`).
    # 230 is not a timeline cue, so it is read as picture, not invented timing.
    black_frame = 230
    breath_dur = (black_frame - s7["zoom"]) / fps  # 34 frames, 1.133s
    breath = inhale(breath_dur, rng)
    mix.add(s_of("S7", s7["zoom"]), breath, pan=0.0, gain=0.28, send_room=0.08)
    note("S7", "zoom", None, s7["zoom"],
         f"filtered-noise inhale {breath_dur:.3f}s, hard cut at frame {black_frame} (screen black)")

    # ----- S8 receipt -----
    s8 = cues["S8"]
    # printStart: motor comes up, a short spin-up of the stepper before line 1.
    spinup = stepper_burst(rng, dur=0.16, rate=36.0)
    mix.add(s_of("S8", s8["printStart"]), spinup, pan=0.0, gain=0.34, send_room=0.08)
    note("S8", "printStart", None, s8["printStart"], "stepper motor spin-up")

    line_gaps = []
    frames = s8["printLines"]
    for i, fr in enumerate(frames):
        if i + 1 < len(frames):
            gap = (frames[i + 1] - fr) / fps
        else:
            gap = 0.34
        line_gaps.append(gap)
        rate = rng.uniform(44.0, 58.0)
        burst = stepper_burst(rng, dur=min(0.16, gap * 0.55), rate=rate)
        mix.add(s_of("S8", fr), burst, pan=rng.uniform(-0.08, 0.08), gain=0.4, send_room=0.07)
        # Quiet feed in the gap so the printer doesn't teleport.
        if gap > 0.18:
            idle = printer_idle(rng, dur=gap * 0.45, rate=rate * 0.85)
            mix.add(s_of("S8", fr) + int(0.12 * SR), idle, pan=0.0, gain=0.22, send_room=0.04)
        note("S8", "printLines", i, fr, f"stepper burst {rate:.0f} Hz + crackle")

    stamp = rubber_stamp(rng)
    mix.add(s_of("S8", s8["stamp"]), stamp, pan=0.0, gain=0.7, send_room=0.2)
    note("S8", "stamp", None, s8["stamp"], "rubber stamp thump (damped body + noise slap)")

    tear = paper_tear(rng, dur=0.35)
    mix.add(s_of("S8", s8["tear"]), tear, pan=0.05, gain=0.48, send_room=0.12)
    note("S8", "tear", None, s8["tear"], "paper tear 0.35s (swept highpass + fiber snaps)")

    # Logo bell rings out after the tear, into silence at 75s.
    end_bell = fm_bell(midi_hz(D3), ratio=1.4, dur=1.05, index=1.8, tau=0.42)
    mix.add(s_of("S8", s8["tear"]) + int(0.28 * SR), end_bell, pan=0.0, gain=0.26, send_plate=0.4)
    report.append((t_of("S8", s8["tear"]) + 0.28, "S8.outro", s8["tear"],
                   "logo bell D3 rings out, faded before 75.0s"))

    # ----- Drone -----
    print("rendering drone...", flush=True)
    drone = render_drone(n, scenes, fps, drone_silence)
    mix.add_stereo(0, drone, gain=1.0)

    # ----- Reverb -----
    print("rendering reverb...", flush=True)
    room = fdn_stereo(mix.room, "room", SR)
    plate = fdn_stereo(mix.plate, "plate", SR)

    # Force reverb to zero across the silence window too (sends may have
    # tails from the clack — clack has no send, but the drone fade and any
    # earlier event tails must not leak). Zero room+plate from silence_a
    # to silence_b, with a short fade so the cut into silence isn't a tick
    # from the reverb and the return isn't either.
    def zero_window(buf, a, b, fade=int(0.012 * SR)):
        a = int(np.clip(a, 0, buf.shape[0]))
        b = int(np.clip(b, 0, buf.shape[0]))
        if a - fade > 0:
            ramp = np.linspace(1, 0, fade)[:, None]
            buf[a - fade:a] *= ramp
        buf[a:b] = 0.0
        return buf

    zero_window(room, silence_a, silence_b)
    zero_window(plate, silence_a, silence_b)
    # Also zero anything already in dry across the true-zero window.
    # The clack ends well before silence_a (40 ms voice, silence_a is +50 ms).
    mix.dry[silence_a:silence_b] = 0.0

    # ----- Bus -----
    bus = mix.dry + room * 0.85 + plate * 0.9
    # Gentle bus tanh. Drive low so transients stay crisp.
    drive = 1.15
    bus = np.tanh(bus * drive) / np.tanh(drive)

    # Fade the very end to exact zero so the file ends in silence, and a
    # 5 ms fade-in so sample 0 isn't a step (it should already be near zero).
    end_fade = int(0.15 * SR)
    bus[-end_fade:] *= np.linspace(1, 0, end_fade)[:, None]
    in_fade = int(0.01 * SR)
    bus[:in_fade] *= np.linspace(0, 1, in_fade)[:, None]

    # Round off the handful of steepest sample-to-sample steps. These are
    # what loudnorm's 4x oversampled true-peak meter hears as overs even
    # when the sample peak is at -6 dBFS. A 3-point smoother triggered only
    # above a steepness threshold leaves ordinary transients alone.
    d = np.diff(bus, axis=0, prepend=bus[:1])
    steep = np.max(np.abs(d), axis=1) > 0.04
    if np.any(steep):
        kernel = np.array([0.25, 0.5, 0.25])
        for ch in range(2):
            smoothed = np.convolve(bus[:, ch], kernel, mode="same")
            bus[steep, ch] = smoothed[steep]
        # Second pass: the neighbours of a fixed sample can now be the steep ones.
        d = np.diff(bus, axis=0, prepend=bus[:1])
        steep = np.max(np.abs(d), axis=1) > 0.04
        if np.any(steep):
            for ch in range(2):
                smoothed = np.convolve(bus[:, ch], kernel, mode="same")
                bus[steep, ch] = smoothed[steep]

    # Headroom before loudnorm. Sample peak at -8 dBFS; with the steps
    # rounded, intersample peaks stay inside the -1 dBTP ceiling after the
    # ~+10 dB linear gain loudnorm applies to reach -14 LUFS.
    peak = np.max(np.abs(bus))
    if peak > 0:
        bus *= min(1.0, (10 ** (-8.0 / 20.0)) / peak)

    # Re-assert the silence window AFTER gain, so it is exact digital zero.
    bus[silence_a:silence_b] = 0.0

    print(f"peak before write: {np.max(np.abs(bus)):.4f}", flush=True)
    print(f"silence window samples {silence_a}:{silence_b} "
          f"({silence_a / SR:.4f}s .. {silence_b / SR:.4f}s) "
          f"maxabs={np.max(np.abs(bus[silence_a:silence_b])):.3e}", flush=True)

    write_wav_24(RAW_WAV, bus, SR)
    print(f"wrote {RAW_WAV}", flush=True)

    # ----- Report -----
    lines = []
    lines.append("Droid film — cue report")
    lines.append(f"sr={SR} duration={n / SR:.3f}s seed={SEED}")
    lines.append(f"silence window: {silence_a / SR:.4f}s .. {silence_b / SR:.4f}s "
                 f"(samples {silence_a}:{silence_b}) "
                 f"maxabs={np.max(np.abs(bus[silence_a:silence_b])):.3e}")
    lines.append("")
    lines.append(f"{'time':>8}  {'cue':<22} {'local':>6}  sounds")
    for tt, label, frame, sounds in sorted(report, key=lambda r: (r[0], r[1])):
        lines.append(f"{tt:8.4f}  {label:<22} {frame:6d}  {sounds}")
    lines.append("")
    lines.append("Scene bed:")
    lines.append("  S1  none (cream, dry)")
    lines.append("  S2  Dm9")
    lines.append("  S3  Bbmaj7")
    lines.append("  S4  F/A")
    lines.append("  S5  Gsus2, hard-cut at meterFull")
    lines.append("  S6  Esus2/D, brighter, whole step up")
    lines.append("  S7  Gsus4 -> D at fallaway")
    lines.append("  S8  sparse D5, fading")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {REPORT}", flush=True)

    # ----- Loudness normalize -----
    loudnorm(RAW_WAV, OUT_WAV, silence_a, silence_b)
    return silence_a, silence_b


def loudnorm(src, dst, silence_a, silence_b):
    """Two-pass ffmpeg loudnorm, I=-14, TP=-1.0, linear if the measured
    range allows it."""
    print("loudnorm pass 1...", flush=True)
    p1 = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-y", "-i", str(src),
            "-af", "loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    text = p1.stderr
    # The JSON block is at the end of stderr.
    start = text.rfind("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        print(text[-2000:], file=sys.stderr)
        raise RuntimeError("loudnorm pass 1 did not return JSON")
    measured = json.loads(text[start:end + 1])
    print("measured:", json.dumps(measured), flush=True)

    def fget(k):
        return str(measured[k])

    # linear=true keeps the limiter off when the material fits.
    afilter = (
        "loudnorm=I=-14:TP=-1.0:LRA=11:"
        f"measured_I={fget('input_i')}:"
        f"measured_TP={fget('input_tp')}:"
        f"measured_LRA={fget('input_lra')}:"
        f"measured_thresh={fget('input_thresh')}:"
        f"offset={fget('target_offset')}:"
        "linear=true:print_format=summary"
    )
    print("loudnorm pass 2...", flush=True)
    p2 = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-y", "-i", str(src),
            "-af", afilter,
            "-ar", "48000", "-c:a", "pcm_s24le",
            str(dst),
        ],
        capture_output=True, text=True,
    )
    if p2.returncode != 0:
        print(p2.stderr[-2000:], file=sys.stderr)
        raise RuntimeError("loudnorm pass 2 failed")
    # Show the summary.
    for line in p2.stderr.splitlines():
        if any(k in line for k in ("Input Integrated", "Output Integrated",
                                   "Input True Peak", "Output True Peak",
                                   "Normalization", "loudnorm")):
            print(line, flush=True)
    print(f"wrote {dst}", flush=True)

    # linear=true can leave the silence window non-zero if ffmpeg resamples
    # or the limiter trims — it shouldn't, pcm in/out same rate. Verify and,
    # if a denormal snuck in, re-zero. We re-read via ffmpeg to raw f32.
    verify_and_rezero(dst, silence_a, silence_b)


def verify_and_rezero(path, silence_a, silence_b):
    """Read the normalized wav back, confirm the silence window, re-zero if
    loudnorm dithered it (it shouldn't with linear=true, but check)."""
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path),
         "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
        capture_output=True,
    )
    if raw.returncode != 0:
        print(raw.stderr.decode("utf-8", "replace")[-1000:], file=sys.stderr)
        raise RuntimeError("failed to read back normalized wav")
    audio = np.frombuffer(raw.stdout, dtype=np.float32).reshape(-1, 2).astype(np.float64)
    if audio.shape[0] < silence_b:
        print(f"WARNING: readback length {audio.shape[0]} < silence_b {silence_b}")
        return
    window = audio[silence_a:silence_b]
    maxabs = float(np.max(np.abs(window)))
    print(f"post-loudnorm silence maxabs = {maxabs:.3e}", flush=True)
    if maxabs > 0.0:
        # loudnorm's DC blocker / limiter can leak a denormal-scale value.
        # Re-zero and rewrite so the contract (digital zero) holds. Gain is
        # already applied; zeroing a silent window does not change LUFS
        # in any measurable way (the window is ~0.75s of nothing).
        audio[silence_a:silence_b] = 0.0
        write_wav_24(path, audio, SR)
        print("re-zeroed silence window in normalized file", flush=True)


if __name__ == "__main__":
    build()
