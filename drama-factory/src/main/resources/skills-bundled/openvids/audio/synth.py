"""Tactile synthesis primitives. numpy + scipy only.

Every voice returns a float64 array at SR, mono (n,) or stereo (n, 2),
peaking near 1. Placement, buses, and loudness live in render.py.

Voices that need noise take `rng`. Pass the same numpy Generator through a
score and the render is deterministic. Voices with no noise ignore it.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

SR = 48000
A4 = 440.0

_NOTE_PC = {
    "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11,
}


def note_hz(note) -> float:
    """'D4', 'F#5', 'Bb3', 'C#6', or a number already in Hz."""
    if isinstance(note, (int, float)):
        return float(note)
    name = str(note).strip()
    i = 1
    pc = _NOTE_PC[name[0].upper()]
    if i < len(name) and name[i] == "#":
        pc += 1
        i += 1
    elif i < len(name) and name[i] == "b":
        pc -= 1
        i += 1
    octave = int(name[i:])
    return A4 * (2.0 ** ((pc + 12 * (octave + 1) - 69) / 12.0))


def midi_hz(m: float) -> float:
    return A4 * (2.0 ** ((m - 69.0) / 12.0))


def db(v: float) -> float:
    return 10.0 ** (v / 20.0)


def pan_gains(pan: float):
    """Constant-power stereo gains. pan is -1..1."""
    ang = (float(pan) + 1.0) * 0.25 * np.pi
    return float(np.cos(ang)), float(np.sin(ang))


def place(buf, start, audio, gain: float = 1.0, pan: float = 0.0):
    """Add `audio` into a stereo buffer at sample `start`.

    Mono audio is panned. Stereo audio ignores pan. Samples that fall
    outside the buffer are dropped. `start` may be negative.
    """
    if audio is None or gain == 0.0:
        return
    x = declick(np.asarray(audio, dtype=np.float64).copy())
    if x.size == 0:
        return
    if x.ndim == 1:
        l, r = pan_gains(pan)
        x = np.column_stack([x * l, x * r])
    i0 = int(start)
    if i0 >= buf.shape[0]:
        return
    if i0 < 0:
        cut = -i0
        if cut >= x.shape[0]:
            return
        x = x[cut:]
        i0 = 0
    n = min(x.shape[0], buf.shape[0] - i0)
    if n <= 0:
        return
    buf[i0:i0 + n] += x[:n] * gain


def declick(x, ms: float = 1.5, sr: int = SR):
    """Fade both ends to zero. A voice sliced into a buffer clicks otherwise,
    and that step becomes a true-peak over after loudnorm."""
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


def env_ar(n, a, r, sr=SR):
    a_n = max(1, int(a * sr))
    r_n = max(1, int(r * sr))
    e = np.zeros(n, dtype=np.float64)
    aa = min(a_n, n)
    e[:aa] = np.linspace(0.0, 1.0, aa, endpoint=False)
    rest = n - aa
    if rest > 0:
        rr = min(r_n, rest)
        e[aa:aa + rr] = np.linspace(1.0, 0.0, rr, endpoint=False)
    return e


def env_exp(n, tau, sr=SR):
    t = np.arange(n, dtype=np.float64) / sr
    return np.exp(-t / max(tau, 1e-4))


def noise(n, rng):
    return rng.standard_normal(n)


def pinkish(n, rng):
    """1/f-ish noise from three leaky integrators. Peak-normalized."""
    w = rng.standard_normal(n)
    out = np.empty(n, dtype=np.float64)
    a1, a2, a3 = 0.985, 0.94, 0.7
    s1 = s2 = s3 = 0.0
    for i in range(n):
        x = w[i]
        s1 = a1 * s1 + (1 - a1) * x
        s2 = a2 * s2 + (1 - a2) * x
        s3 = a3 * s3 + (1 - a3) * x
        out[i] = s1 * 0.7 + s2 * 0.45 + s3 * 0.3
    return out / (np.max(np.abs(out)) + 1e-12)


def bp_reson(x, f0, q, sr=SR):
    f0 = float(np.clip(f0, 40.0, sr * 0.45))
    q = max(q, 0.5)
    lo = max(f0 * (1 - 0.5 / q), 20.0)
    hi = min(f0 * (1 + 0.5 / q), sr * 0.49)
    if lo >= hi:
        lo, hi = hi * 0.5, hi
    sos = signal.butter(2, [lo, hi], btype="band", output="sos", fs=sr)
    return signal.sosfilt(sos, x)


def hp(x, f0, sr=SR, order=2):
    f0 = float(np.clip(f0, 20.0, sr * 0.45))
    sos = signal.butter(order, f0, btype="highpass", output="sos", fs=sr)
    return signal.sosfilt(sos, x)


def lp(x, f0, sr=SR, order=2):
    f0 = float(np.clip(f0, 40.0, sr * 0.45))
    sos = signal.butter(order, f0, btype="lowpass", output="sos", fs=sr)
    return signal.sosfilt(sos, x)


def _rbj_bandpass(x, fc, q, sr=SR):
    """Sample-wise RBJ bandpass. `fc` is a scalar or a per-sample array."""
    n = x.size
    if np.isscalar(fc):
        fc = np.full(n, float(fc))
    y = np.empty(n, dtype=np.float64)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(n):
        w0 = 2.0 * np.pi * min(float(fc[i]), sr * 0.45) / sr
        alpha = np.sin(w0) / (2.0 * q)
        cosw = np.cos(w0)
        a0 = 1.0 + alpha
        yi = (alpha / a0) * x[i] + (-alpha / a0) * x2 - (-2.0 * cosw / a0) * y1 - ((1.0 - alpha) / a0) * y2
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
    if x.size < n * 2:
        return x
    ramp = np.linspace(0.0, 1.0, n)
    x = x.copy()
    x[:n] *= ramp
    x[-n:] *= ramp[::-1]
    return x


def tape(x, drive=1.4):
    """Soft tanh saturation, normalized so a full-scale sine stays near unity."""
    return np.tanh(x * drive) / np.tanh(drive)


def keystroke(kind="paper", rng=None):
    """Low-profile key. Noise burst through body modes, plus a thock ~8 ms later.

    kind: paper (open, wooden desk), terminal (tighter, plastic), enter (heavier).
    """
    if rng is None:
        rng = np.random.default_rng(0)
    enter = kind == "enter"
    dur = 0.14 if enter else 0.085
    n = int(dur * SR)
    click_n = int((0.007 if enter else 0.0045) * SR)
    burst = np.zeros(n)
    burst[:click_n] = rng.standard_normal(click_n) * np.linspace(1.0, 0.15, click_n)

    if kind == "terminal":
        modes, qs, gains = [2100.0, 3900.0, 6400.0], [9.0, 7.0, 5.0], [0.9, 0.5, 0.22]
    else:
        modes, qs, gains = [1800.0, 3400.0, 6000.0], [7.5, 6.0, 4.5], [1.0, 0.62, 0.34]
    body = np.zeros(n)
    for f0, q, g in zip(modes, qs, gains):
        body += g * bp_reson(burst, f0 * (1.0 + rng.uniform(-0.025, 0.025)), q)
    body = hp(body, 900.0) * env_exp(n, 0.028 if enter else 0.018)

    thock_f = rng.uniform(185.0, 255.0) * (0.72 if enter else 1.0)
    delay = int(0.008 * SR)
    t = np.arange(n - delay) / SR
    tau = 0.045 if enter else 0.022
    thock = np.sin(2 * np.pi * thock_f * t) * np.exp(-t / tau)
    thock += 0.28 * np.sin(2 * np.pi * thock_f * 2.37 * t) * np.exp(-t / (tau * 0.45))
    y = body * 0.85
    y[delay:] += thock * (0.85 if enter else 0.55)
    if enter:
        y[delay:] += 0.35 * np.sin(2 * np.pi * 95.0 * t) * np.exp(-t / 0.05)
    return soften(norm(y, 1.0 if enter else 0.9), 6)


def modal_bar(note, rng=None, dur=0.55, strike=1.0):
    """Wooden bar. Inharmonic ratios 1 : 3.93 : 9.5, short decay, dry click."""
    if rng is None:
        rng = np.random.default_rng(0)
    freq = note_hz(note)
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for ratio, g, tau in ((1.0, 1.0, 0.18), (3.93, 0.42, 0.055), (9.5, 0.16, 0.022)):
        f = freq * ratio * (1.0 + rng.uniform(-0.002, 0.002))
        y += g * np.sin(2 * np.pi * f * t + rng.uniform(0, 0.4)) * np.exp(-t / tau)
    click_n = int(0.003 * SR)
    click = np.zeros(n)
    click[:click_n] = rng.standard_normal(click_n) * np.linspace(1.0, 0.0, click_n)
    y += 0.22 * bp_reson(click, min(freq * 6.5, 7000), 3.5) * strike
    return soften(norm(y * strike, 0.95), 4)


def fm_bell(note, ratio=1.4, dur=2.8, index=2.4, tau=1.1):
    """FM bell. The logo tone is D3 at ratio 1.4."""
    freq = note_hz(note)
    n = int(dur * SR)
    t = np.arange(n) / SR
    ind = index * np.exp(-t / 0.35)
    mod = np.sin(2 * np.pi * freq * ratio * t)
    car = np.sin(2 * np.pi * freq * t + ind * mod)
    car += 0.18 * np.sin(2 * np.pi * freq * 2.0 * t + 0.6 * ind * mod) * np.exp(-t / 0.12)
    y = car * np.exp(-t / tau)
    a = int(0.004 * SR)
    y[:a] *= np.linspace(0.0, 1.0, a)
    return soften(y * 0.8, 8)


def glass_ping(note, dur=2.4):
    """Sine plus a short 3rd harmonic. 3 ms attack, long tail."""
    freq = note_hz(note)
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * freq * t)
    y += 0.28 * np.sin(2 * np.pi * freq * 3.0 * t) * np.exp(-t / 0.35)
    y *= np.exp(-t / 1.15)
    a = int(0.003 * SR)
    y[:a] *= np.linspace(0, 1, a) ** 0.7
    return soften(y * 0.62, 6)


def pluck(note, rng=None, dur=0.45, brightness=0.5):
    """Karplus-Strong. brightness 0..1 is the loop lowpass, brighter = longer."""
    if rng is None:
        rng = np.random.default_rng(0)
    freq = note_hz(note)
    n = int(dur * SR)
    period = max(2, int(SR / freq))
    buf = rng.standard_normal(period) * np.hanning(period)
    a = 0.5 + 0.45 * float(np.clip(brightness, 0.0, 1.0))
    decay = 0.996
    line = np.zeros(period + 2)
    line[:period] = buf
    y = np.empty(n)
    idx = 0
    prev = 0.0
    for i in range(n):
        s = line[idx]
        avg = (1 - a) * s + a * prev
        prev = avg
        y[i] = s
        line[idx] = avg * decay
        idx = (idx + 1) % period
    k = int(0.002 * SR)
    y[:k] += rng.standard_normal(k) * 0.15 * np.linspace(1, 0, k)
    return soften(norm(y, 0.8), 4)


def felt_thump(note, rng=None, dur=0.7):
    """Felt-muted piano. Additive partials, fast high-frequency decay, short hammer."""
    if rng is None:
        rng = np.random.default_rng(0)
    freq = note_hz(note)
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for ratio, g, tau in ((1.0, 1.0, 0.28), (2.0, 0.45, 0.08), (3.0, 0.22, 0.035),
                          (4.01, 0.10, 0.018), (5.2, 0.05, 0.01)):
        f = freq * ratio * (1 + rng.uniform(-0.0015, 0.0015))
        y += g * np.sin(2 * np.pi * f * t + rng.uniform(0, 0.5)) * np.exp(-t / tau)
    k = int(0.006 * SR)
    hammer = np.zeros(n)
    hammer[:k] = rng.standard_normal(k) * np.linspace(1, 0, k) ** 0.5
    y += 0.18 * lp(hammer, 1800)
    a = int(0.004 * SR)
    y[:a] *= np.linspace(0, 1, a)
    return soften(norm(y, 0.85), 4)


def paper_turn(dur=0.55, rng=None):
    """Page turn. Swept bandpass, flutter AM 8-14 Hz, muted landing."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(dur * SR)
    u = np.linspace(0, 1, n)
    fc = 500 + 2600 * np.sin(np.pi * u) ** 1.1
    y = _rbj_bandpass(noise(n, rng), fc, 1.6)
    flutter_f = 8 + 6 * u
    flutter = 0.55 + 0.45 * np.sin(2 * np.pi * np.cumsum(flutter_f) / SR)
    y = y * flutter * np.sin(np.pi * u) ** 0.8
    land_n = int(0.06 * SR)
    land_at = n - int(0.07 * SR)
    tt = np.arange(land_n) / SR
    land = np.sin(2 * np.pi * 140 * tt) * np.exp(-tt / 0.02)
    land += 0.3 * np.sin(2 * np.pi * 90 * tt) * np.exp(-tt / 0.03)
    y[land_at:land_at + land_n] += land * 0.8
    return soften(norm(y, 0.75), 10)


def paper_tear(dur=0.35, rng=None):
    """Tear. Sweeping highpass plus irregular fiber snaps, kept under 6 kHz."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(dur * SR)
    x = noise(n, rng)
    fc = np.geomspace(400, 5200, n)
    y = np.empty(n)
    prev_x = prev_y = 0.0
    for i in range(n):
        a = np.exp(-2 * np.pi * min(fc[i], SR * 0.45) / SR)
        prev_y = a * (prev_y + x[i] - prev_x)
        prev_x = x[i]
        y[i] = prev_y
    for _ in range(int(rng.integers(18, 28))):
        at = int(rng.uniform(0.01, 0.92) * n)
        ln = min(int(rng.uniform(0.001, 0.004) * SR), n - at)
        tt = np.arange(ln) / SR
        snap = np.sin(2 * np.pi * rng.uniform(1400, 5500) * tt) * np.exp(-tt / rng.uniform(0.001, 0.003))
        y[at:at + ln] += snap * rng.uniform(0.25, 0.7)
    u = np.linspace(0, 1, n)
    e = np.sin(np.pi * np.clip(u * 1.05, 0, 1)) ** 0.6 * np.linspace(0.7, 1.0, n)
    return soften(norm(y * e, 0.8), 6)


def printer_burst(dur=0.09, rate=50.0, rng=None, level=1.0):
    """Thermal-printer advance. Stepper clicks at `rate` Hz plus band-limited crackle."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(dur * SR)
    t = np.arange(n) / SR
    pulse = (np.sin(2 * np.pi * rate * t) > 0.55).astype(np.float64)
    click_len = int(0.0035 * SR)
    ct = np.arange(click_len) / SR
    click = np.sin(2 * np.pi * 1800 * ct) * np.exp(-ct / 0.0012)
    click += 0.4 * np.sin(2 * np.pi * 420 * ct) * np.exp(-ct / 0.0016)
    y = np.zeros(n)
    for o in np.where(np.diff(pulse, prepend=0) > 0)[0]:
        m = min(click_len, n - int(o))
        y[int(o):int(o) + m] += click[:m]
    crack = lp(hp(noise(n, rng), 4000), 9000)
    y += crack * 0.18 * (0.4 + 0.6 * np.clip(np.abs(y) * 4, 0, 1))
    y = lp(y, 10000) * env_ar(n, 0.004, dur * 0.45)
    return soften(y, 3) * level


def stamp(rng=None):
    """Rubber stamp. Damped low-mid body plus a short noise slap."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * 145 * t) * np.exp(-t / 0.04)
    y += 0.55 * np.sin(2 * np.pi * 230 * t) * np.exp(-t / 0.025)
    y += 0.25 * np.sin(2 * np.pi * 410 * t) * np.exp(-t / 0.014)
    y += 0.12 * np.sin(2 * np.pi * 90 * t) * np.exp(-t / 0.05)
    slap_n = int(0.009 * SR)
    slap = np.zeros(n)
    slap[:slap_n] = rng.standard_normal(slap_n) * np.linspace(1, 0, slap_n)
    y += 0.55 * bp_reson(slap, 1600, 1.5)
    return soften(norm(y, 0.95), 4)


def latch_click(rng=None):
    """Two-transient counter lock, 11 ms apart."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(0.07 * SR)
    y = np.zeros(n)
    for d_ms, f, tau, g in ((0.0, 3100, 0.006, 0.8), (11.0, 1900, 0.014, 1.0)):
        d = int(d_ms * 1e-3 * SR)
        tt = np.arange(n - d) / SR
        y[d:] += g * np.sin(2 * np.pi * f * tt) * np.exp(-tt / tau)
        k = int(0.0012 * SR)
        y[d:d + k] += rng.standard_normal(k) * 0.35 * np.linspace(1, 0, k)
    return soften(norm(y, 0.85), 3)


def detent(rng=None):
    """Softer metal-on-detent click. Three close partials, used under a logo bell."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(0.09 * SR)
    y = np.zeros(n)
    for delay_ms, f, tau, g in ((0.0, 2400, 0.012, 0.7), (7.5, 1680, 0.018, 1.0), (14.0, 620, 0.02, 0.45)):
        d = int(delay_ms * 1e-3 * SR)
        tt = np.arange(n - d) / SR
        y[d:] += g * np.sin(2 * np.pi * f * tt) * np.exp(-tt / tau)
    k = int(0.0015 * SR)
    y[:k] += rng.standard_normal(k) * 0.4 * np.linspace(1, 0, k)
    return soften(norm(y, 0.8), 4)


def air_spin(dur, start_hz=4.0, end_hz=40.0, rng=None):
    """Rotating blades. Filtered noise, amplitude-modulated at blade-pass
    frequency, with a slow doppler pan. Returns stereo (n, 2)."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(dur * SR)
    src = bp_reson(bp_reson(pinkish(n, rng), 900, 1.6), 1400, 1.3)
    t = np.arange(n) / SR
    u = (t / max(dur, 1e-6)) ** 1.6
    bpf = start_hz + (end_hz - start_hz) * u
    phase = 2 * np.pi * np.cumsum(bpf) / SR
    am = (0.42 + 0.58 * (0.5 + 0.5 * np.sin(phase)) ** 1.4) * (0.85 + 0.15 * np.sin(2 * phase))
    level = np.clip(u * 1.3, 0, 1) ** 0.8 * np.linspace(1.0, 0.55, n)
    air = src * am * level
    ang = (0.55 * np.sin(phase / 3.0) + 1.0) * 0.25 * np.pi
    return np.column_stack([air * np.cos(ang), air * np.sin(ang)]) * 0.55


def sub_swell(dur, f=48.0):
    """Slow sub sine. Long attack, no pitch movement. Not a riser."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    a = min(n, int(0.55 * SR))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a) ** 1.4
    rel = min(n, int(0.7 * SR))
    e[-rel:] *= np.linspace(1, 0, rel)
    return np.sin(2 * np.pi * f * t) * e * 0.7


def inhale(dur, rng=None):
    """Filtered-noise breath that builds and cuts. The picture goes black at the end."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(max(dur, 0.02) * SR)
    y = _rbj_bandpass(pinkish(n, rng), np.geomspace(220, 1600, n), 1.1)
    e = np.linspace(0, 1, n) ** 1.3
    fade = min(n, int(0.004 * SR))
    e[-fade:] *= np.linspace(1, 0, fade)
    return soften(y * e, 4) * 0.8


def _partials(chords):
    midis = set()
    for notes in chords.values():
        for item in notes:
            midis.add(item[0] if isinstance(item, tuple) else _as_midi(item))
    return sorted(midis)


def note_name(note) -> str:
    """A name stays a name. A MIDI number becomes one, so a report can print either."""
    if isinstance(note, str):
        return note
    if isinstance(note, tuple):
        return note_name(note[0])
    m = int(round(float(note)))
    names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    return f"{names[m % 12]}{(m // 12) - 1}"


def _as_midi(note) -> float:
    if isinstance(note, (int, float)) and not isinstance(note, bool):
        v = float(note)
        if v < 20.0 or float(v).is_integer() and 12 <= v <= 127:
            return v
    return 69.0 + 12.0 * np.log2(note_hz(note) / A4)


def _chord_gains(notes):
    """notes: ['D3', 'A3'] (equal) or [(midi_or_note, gain), ...]."""
    out = {}
    if not notes:
        return out
    weighted = isinstance(notes[0], tuple)
    for item in notes:
        if weighted:
            note, g = item
        else:
            note, g = item, 1.0
        out[_as_midi(note)] = float(g)
    return out


def drone(chords, spans, n, sr=SR, level_db=-28.0, xfade=1.0, wow_hz=0.3, cents=3.0):
    """Additive bed. `chords` maps a name to note lists. `spans` is
    [(start_sample, end_sample, chord_name), ...] in order.

    Adjacent chords crossfade over `xfade` seconds by smoothing every
    partial's gain, so shared tones hold and new ones enter. A 0.3 Hz wow
    of ±3 cents, then soft tape. Stereo, narrow. Empty chord = silence.
    """
    spans = [(int(a), int(b), name) for a, b, name in spans]
    all_midis = _partials(chords)
    if not all_midis or n <= 0:
        return np.zeros((n, 2))

    ctrl = 200
    step = sr / ctrl
    n_ctrl = int(np.ceil(n / step)) + 2
    gains = {m: np.zeros(n_ctrl) for m in all_midis}
    for a, b, name in spans:
        gmap = _chord_gains(chords.get(name, []))
        c0 = max(0, min(int(round(a / step)), n_ctrl))
        c1 = max(0, min(int(round(b / step)), n_ctrl))
        for m in all_midis:
            gains[m][c0:c1] = gmap.get(m, 0.0)

    alpha = np.exp(-2 * np.pi * (1.0 / max(xfade, 0.05)) / ctrl)
    for m in all_midis:
        g = gains[m]
        acc = 0.0
        for i in range(g.size):
            acc = alpha * acc + (1 - alpha) * g[i]
            g[i] = acc

    t = np.arange(n) / sr
    wow_ratio = 2.0 ** (np.sin(2 * np.pi * wow_hz * t) * cents / 1200.0)
    bed_l = np.zeros(n)
    bed_r = np.zeros(n)
    voiced = [m for m in all_midis if np.max(gains[m]) >= 1e-4]
    for i, m in enumerate(voiced):
        gi = np.interp(np.arange(n), np.arange(n_ctrl) * step, gains[m])
        detune = 4.0 + (i % 5) * 1.1
        r_up = 2.0 ** (detune / 1200.0)
        r_dn = 2.0 ** (-detune / 1200.0)
        phase = 2 * np.pi * np.cumsum(midi_hz(m) * wow_ratio) / sr
        sig = (0.5 * np.sin(phase * r_up) + 0.5 * np.sin(phase * r_dn)) * gi
        pan_pos = -0.25 + (0.5 * i / max(1, len(voiced) - 1))
        ang = (pan_pos + 1.0) * 0.25 * np.pi
        bed_l += sig * np.cos(ang)
        bed_r += sig * np.sin(ang)

    peak = np.max(np.abs(np.column_stack([bed_l, bed_r]))) + 1e-12
    scale = db(level_db) / peak
    stereo = tape(np.column_stack([bed_l * scale, bed_r * scale]), drive=1.6)
    return stereo


def _schroeder(x, sr, comb_ms, ap_ms, comb_g, ap_g, predelay_ms):
    n = x.size
    pre = int(predelay_ms * 1e-3 * sr)
    src = np.zeros(n)
    if pre < n:
        src[pre:] = x[:n - pre]
    y = np.zeros(n)
    for ms, g in zip(comb_ms, comb_g):
        d = max(1, int(ms * 1e-3 * sr))
        buf = np.zeros(d)
        idx = 0
        acc = np.zeros(n)
        for i in range(n):
            delayed = buf[idx]
            acc[i] = delayed
            buf[idx] = src[i] + g * delayed
            idx = idx + 1 if idx + 1 < d else 0
        y += acc
    y *= 1.0 / max(len(comb_ms), 1)
    for ms, g in zip(ap_ms, ap_g):
        d = max(1, int(ms * 1e-3 * sr))
        buf = np.zeros(d)
        idx = 0
        out = np.empty(n)
        for i in range(n):
            delayed = buf[idx]
            v = y[i] - g * delayed
            out[i] = g * v + delayed
            buf[idx] = v
            idx = idx + 1 if idx + 1 < d else 0
        y = out
    return y


_ROOMS = {
    "room": dict(
        combs_l=[23.1, 29.7, 37.3, 43.9], combs_r=[25.3, 31.1, 39.7, 47.3],
        gl=[0.62, 0.66, 0.70, 0.64], gr=[0.64, 0.68, 0.69, 0.63],
        ap=[5.1, 7.7], apg=[0.55, 0.45], pre=6, wet=0.55, damp=5000,
    ),
    "plate": dict(
        combs_l=[41.3, 53.7, 67.9, 79.1], combs_r=[43.9, 57.1, 71.3, 83.7],
        gl=[0.78, 0.80, 0.82, 0.76], gr=[0.79, 0.81, 0.80, 0.77],
        ap=[8.3, 12.7, 17.1], apg=[0.62, 0.55, 0.48], pre=14, wet=0.7, damp=6500,
    ),
}


def reverb(send, kind="room", sr=SR):
    """Schroeder room or plate. `send` is mono (n,) or stereo (n, 2).
    Returns stereo (n, 2), already scaled by the kind's wet gain."""
    x = np.asarray(send, dtype=np.float64)
    exc = x if x.ndim == 1 else x[:, 0] * 0.7 + x[:, 1] * 0.7
    p = _ROOMS[kind]
    l = lp(_schroeder(exc, sr, p["combs_l"], p["ap"], p["gl"], p["apg"], p["pre"]), p["damp"], sr=sr)
    r = lp(_schroeder(exc, sr, p["combs_r"], p["ap"], p["gr"], p["apg"], p["pre"] + 3), p["damp"], sr=sr)
    return np.column_stack([l * 0.85 + r * 0.15, r * 0.85 + l * 0.15]) * p["wet"]


def rest():
    """Nothing. Use it on a cue the picture carries alone, so the report lists the choice."""
    return None


def tone(note, dur=1.2, index=0.7, tau=0.6):
    """Quiet pure-ish bell for a scene entrance. Not a whoosh."""
    return fm_bell(note, ratio=1.0, dur=dur, index=index, tau=tau)


def friction(dur=0.16, rng=None):
    """Barely-there string scrape. Meant to sit under a landing, very quiet."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(dur * SR)
    x = lp(hp(noise(n, rng), 4000.0), 9000.0)
    t = np.arange(n) / SR
    flutter = 0.65 + 0.35 * np.sin(2 * np.pi * rng.uniform(28, 46) * t + rng.uniform(0, 6))
    return soften(x * flutter * env_ar(n, 0.03, 0.10), 8) * 0.35


def pen_tick(pitch=1800.0, rng=None):
    """Dry tick, like a pen hitting paper."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(0.025 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * pitch * t) * np.exp(-t / 0.006)
    y += 0.3 * np.sin(2 * np.pi * pitch * 2.1 * t) * np.exp(-t / 0.003)
    k = min(n, int(0.001 * SR))
    y[:k] += rng.standard_normal(k) * 0.2
    return soften(y, 2)


def ticks(dur, rate0, rate1, rng=None, pitch=2400.0, jitter=0.16):
    """Accelerating ticks. Returns [(offset_samples, mono), ...].

    rate0/rate1 are Hz at the start and end. Pitch may be a range (lo, hi)
    to pick a fresh pitch per tick.
    """
    if rng is None:
        rng = np.random.default_rng(0)
    events = []
    t = 0.0
    while t < dur - 1.0 / max(rate1, 0.5):
        u = t / max(dur, 1e-6)
        rate = rate0 + (rate1 - rate0) * (u ** 1.4)
        if isinstance(pitch, tuple):
            f = rng.uniform(pitch[0], pitch[1])
        else:
            f = pitch * (1 + rng.uniform(-0.01, 0.01))
        n = int(rng.uniform(0.004, 0.012) * SR)
        tt = np.arange(n) / SR
        tick = np.sin(2 * np.pi * f * tt) * np.exp(-tt / rng.uniform(0.003, 0.008))
        tick += 0.25 * rng.standard_normal(n) * np.exp(-tt / 0.002)
        events.append((int(t * SR), soften(tick, 3) * rng.uniform(0.4, 0.75)))
        t += (1.0 / max(rate, 0.5)) * rng.uniform(1 - jitter, 1 + jitter)
    return events


def glide(f0, f1, dur, tau_tail=0.4):
    """Sine that rises from f0 to f1 over `dur` and rings briefly. Notes or Hz."""
    f0, f1 = note_hz(f0), note_hz(f1)
    tail = 0.55
    n = int((dur + tail) * SR)
    t = np.arange(n) / SR
    u = np.clip(t / max(dur, 1e-6), 0, 1) ** 1.15
    phase = 2 * np.pi * np.cumsum(f0 + (f1 - f0) * u) / SR
    e = np.ones(n)
    a = min(n, int(0.04 * SR))
    e[:a] = np.linspace(0, 1, a)
    hold = min(n, int(dur * SR))
    e[:hold] *= np.linspace(0.35, 1.0, hold)
    if hold < n:
        e[hold:] *= np.exp(-(np.arange(n - hold) / SR) / tau_tail)
    return np.sin(phase) * e * 0.55


def fifth(note, dur=1.6):
    """Root, fifth, octave. A resolution, not a pad."""
    root = note_hz(note)
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for ratio, g, tau in ((1.0, 1.0, 0.7), (1.5, 0.62, 0.55), (2.0, 0.38, 0.4)):
        y += g * np.sin(2 * np.pi * root * ratio * t) * np.exp(-t / tau)
    a = int(0.012 * SR)
    y[:a] *= np.linspace(0, 1, a)
    return soften(y * 0.7, 8)


def glass_drop(note, dur=0.38):
    """Short glassy strike. Inharmonic, faster than a wooden bar."""
    freq = note_hz(note)
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * freq * t) * np.exp(-t / 0.12)
    y += 0.35 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t / 0.05)
    y += 0.12 * np.sin(2 * np.pi * freq * 5.4 * t) * np.exp(-t / 0.02)
    a = int(0.002 * SR)
    y[:a] *= np.linspace(0, 1, a)
    return soften(y * 0.7, 3)


def thud(rng=None, f=78.0):
    """Tight low thud. Two partials plus a short slap."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.045)
    y += 0.4 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t / 0.025)
    k = int(0.004 * SR)
    slap = np.zeros(n)
    slap[:k] = rng.standard_normal(k) * np.linspace(1, 0, k)
    y += 0.3 * lp(slap, 2500)
    return soften(norm(y, 0.9), 4)


def clack(rng=None):
    """Dry clack. No sustain, so a silence window can open just after it."""
    n = int(0.04 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * 980 * t) * np.exp(-t / 0.008)
    y += 0.5 * np.sin(2 * np.pi * 2100 * t) * np.exp(-t / 0.004)
    return soften(norm(y, 0.7), 2)


def paper_slide(dur=0.28, rng=None):
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(dur * SR)
    x = hp(bp_reson(noise(n, rng), 1800, 1.4), 700)
    e = np.sin(np.pi * np.linspace(0, 1, n)) ** 1.2
    return soften(x * e * 0.4, 6)


def swell_in(notes, dur=0.9):
    """A chord tail reversed, so it swells into the sample where you place its end.

    Place it at (cue_sample - len). The crest is the last sample.
    """
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for i, note in enumerate(notes):
        y += (0.5 ** i) * np.sin(2 * np.pi * note_hz(note) * t) * np.exp(-t / 0.55)
    y = y[::-1]
    a = int(0.08 * SR)
    y[:a] *= np.linspace(0, 1, a)
    return soften(y * 0.45, 8)


def shutter(rng=None):
    """Dark shutter-close. Low partials plus a short slap, for a frame going black."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * 58.0 * t) * np.exp(-t / 0.06)
    y += 0.45 * np.sin(2 * np.pi * 112.0 * t) * np.exp(-t / 0.035)
    y += 0.18 * np.sin(2 * np.pi * 240.0 * t) * np.exp(-t / 0.018)
    slap_n = int(0.008 * SR)
    slap = np.zeros(n)
    slap[:slap_n] = rng.standard_normal(slap_n) * np.linspace(1, 0, slap_n)
    y += 0.35 * lp(slap, 2200)
    return soften(norm(y, 0.9), 4)


def clock_run(dur, rate0, rate1, rng=None, pitch=1800.0, accel=1.5, pan=0.0, gain0=0.55, gain1=1.0):
    """One stereo buffer of accelerating ticks over `dur` seconds.

    gain0..gain1 is the level at the start and end, so a filling meter can
    get slightly louder without the score placing each tick.
    """
    n = int(dur * SR) + int(0.03 * SR)
    buf = np.zeros((n, 2))
    for off, tick, u in clock(dur, rate0, rate1, rng=rng, pitch=pitch, accel=accel):
        place(buf, off, tick, gain=gain0 + (gain1 - gain0) * u, pan=pan)
    return buf


def granular(dur, rate0, rate1, rng=None, pan=0.0, pitch=(1400.0, 3200.0), gain=0.55):
    """Rising density of soft ticks, one stereo buffer. The losing bars in a race."""
    n = int(dur * SR) + int(0.02 * SR)
    buf = np.zeros((n, 2))
    for off, tick in ticks(dur, rate0, rate1, rng=rng, pitch=pitch, jitter=0.25):
        place(buf, off, tick, gain=gain, pan=float(np.clip(pan + rng.uniform(-0.3, 0.3), -0.85, 0.85)))
    return buf


def clock(dur, rate0, rate1, rng=None, pitch=1800.0, accel=1.5):
    """Meter ticks. Same idea as ticks(), with a steeper accel so a filling
    meter reads as running out rather than as a steady clock."""
    if rng is None:
        rng = np.random.default_rng(0)
    events = []
    t = 0.0
    while t < dur - 0.02:
        u = t / max(dur, 1e-6)
        rate = rate0 + (rate1 - rate0) * (u ** accel)
        f = pitch * (1 + rng.uniform(-0.01, 0.01))
        n = int(0.02 * SR)
        tt = np.arange(n) / SR
        y = np.sin(2 * np.pi * f * tt) * np.exp(-tt / 0.006)
        y += 0.3 * np.sin(2 * np.pi * f * 2.1 * tt) * np.exp(-tt / 0.003)
        k = min(n, int(0.001 * SR))
        y[:k] += rng.standard_normal(k) * 0.2
        events.append((int(round(t * SR)), soften(y, 2), u))
        t += (1.0 / max(rate, 0.4)) * rng.uniform(0.92, 1.08)
    return events


def opening(dur=0.42, rng=None):
    """Lowpassed noise whose cutoff opens 180 -> 900 Hz. A shape growing, not a whoosh."""
    if rng is None:
        rng = np.random.default_rng(0)
    n = int(dur * SR)
    x = pinkish(n, rng)
    y = np.empty(n)
    block = 256
    cuts = np.geomspace(180, 900, int(np.ceil(n / block)))
    pos = 0
    for c in cuts:
        b = min(block, n - pos)
        a = np.exp(-2 * np.pi * c / SR)
        acc = 0.0
        for i in range(b):
            acc = a * acc + (1 - a) * x[pos + i]
            y[pos + i] = acc
        pos += b
    return soften(y * env_ar(n, 0.05, dur * 0.7), 8)
