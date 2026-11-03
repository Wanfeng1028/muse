#!/usr/bin/env python3
"""
Soundtrack for the scene: a synthesized bed on the scene's tempo, plus one UI
sound per cue, each placed so its *measured peak* lands on the cue time.

Reads audio/meta.json and audio/cues.json (written by preview.mjs from the
scene's window.META and window.CUES). Writes audio/bed.wav.

  python3 audio.py                         synthesized bed
  python3 audio.py --music track.wav       the user's track instead of the bed
                                           (its tempo is measured and printed:
                                           set the scene's bpm to it and start on
                                           its downbeat, given by --offset)
  python3 audio.py --music track.mp3 --offset 1.84
  python3 audio.py --voice anna.mp4:10.5:2.0:6.0     footage sound: file:at:start:dur,
                                                      repeatable; the bed ducks under it

Any format ffmpeg reads works for --music and --voice. A loop wraps every tail
back into bar 1 so the seam is continuous. A one-shot (META.endT, required)
stops the drums on the end card and lets a chord ring out.
"""
import argparse, json, subprocess, wave
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--music"); ap.add_argument("--offset", type=float, default=0.0)
ap.add_argument("--voice", action="append", default=[])
ap.add_argument("--out", default="audio/bed.wav")
args = ap.parse_args()
META = json.load(open("audio/meta.json")); CUES = json.load(open("audio/cues.json"))
if not META["loop"] and META.get("endT") is None:
    raise SystemExit("a one-shot needs META.endT (when the end card lands) in the scene")

SR = 48000
BEAT = 60.0 / META["bpm"]
DUR = META["dur"]
N = int(round(DUR * SR))
LOOP = bool(META["loop"])
END_T = META.get("endT")
rng = np.random.default_rng(7)

# ---------------------------------------------------------------- primitives
def env_exp(n, a=0.002, d=0.2, floor=1e-4):
    """Percussive envelope: short linear attack, exponential decay."""
    t = np.arange(n) / SR
    at = np.clip(t / max(a, 1e-6), 0, 1)
    de = np.exp(np.log(floor) * np.clip((t - a) / max(d, 1e-6), 0, None))
    return at * de


def env_ad(n, a, r, curve=2.0):
    t = np.linspace(0, 1, n)
    ap = max(a, 1e-6)
    e = np.where(t < ap, (t / ap), ((1 - t) / (1 - ap)) ** curve)
    return np.clip(e, 0, 1)


def noise(n):
    return rng.standard_normal(n)


def lowpass_fast(x, cutoff, order=2):
    """Frequency-domain version of the same shape, for long buffers."""
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    H = 1.0 / (1.0 + (f / max(cutoff, 1.0)) ** 2) ** (order / 2.0)
    return np.fft.irfft(X * H, n)


def highpass_fast(x, cutoff, order=2):
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    r = (f / max(cutoff, 1.0))
    H = (r ** order) / np.sqrt(1.0 + r ** (2 * order))
    return np.fft.irfft(X * H, n)


def sine(freq, n, phase=0.0):
    t = np.arange(n) / SR
    if np.isscalar(freq):
        return np.sin(2 * np.pi * freq * t + phase)
    ph = np.cumsum(2 * np.pi * np.asarray(freq) / SR)
    return np.sin(ph + phase)


def tri(freq, n):
    t = np.arange(n) / SR
    return 2 * np.abs(2 * ((freq * t) % 1.0) - 1) - 1


# ---------------------------------------------------------------- bed voices
def kick(gain=1.0):
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    f = 46 + 130 * np.exp(-t / 0.016)          # pitch drop into the sub
    body = sine(f, n) * env_exp(n, 0.0008, 0.26)
    click = lowpass_fast(noise(int(0.012 * SR)), 5200, 2) * env_exp(int(0.012 * SR), 0.0002, 0.006)
    out = body
    out[:len(click)] += click * 0.35
    return out * gain


def hat(gain=1.0, open_=False):
    d = 0.09 if open_ else 0.035
    n = int(d * SR)
    x = highpass_fast(noise(n), 7000, 3)
    return x * env_exp(n, 0.0004, d * 0.45) * gain


def pluck(freq, gain=1.0, d=0.26):
    """Muted pluck: two detuned triangles through a falling lowpass."""
    n = int(d * SR)
    x = tri(freq, n) * 0.6 + tri(freq * 1.005, n) * 0.4
    x += tri(freq * 2.0, n) * 0.12
    x = lowpass_fast(x, 1500, 2)
    return x * env_exp(n, 0.0025, d * 0.42) * gain


def subbass(freq, dur, gain=1.0):
    n = int(dur * SR)
    x = sine(freq, n) * 0.85 + sine(freq * 2, n) * 0.12
    return x * env_ad(n, 0.02, 0.5, 1.4) * gain


def pad(freq, dur, gain=1.0):
    n = int(dur * SR)
    x = np.zeros(n)
    for k, amp in ((1, 1.0), (2, 0.28), (3, 0.14), (5, 0.06)):
        x += sine(freq * k * (1 + 0.0012 * k), n) * amp
    x = lowpass_fast(x, 900, 2)
    return x * env_ad(n, 0.45, 0.5, 1.2) * gain


# ---------------------------------------------------------------- UI sounds
def ui_click_down():
    n = int(0.035 * SR)
    x = lowpass_fast(noise(n), 3800, 2) * env_exp(n, 0.0003, 0.007)
    x += sine(480, n) * env_exp(n, 0.0003, 0.010) * 0.5
    return x


def ui_click_up():
    n = int(0.030 * SR)
    x = lowpass_fast(noise(n), 5200, 2) * env_exp(n, 0.0002, 0.005)
    x += sine(760, n) * env_exp(n, 0.0002, 0.008) * 0.4
    return x


def ui_whoosh(d=0.24, lo=400, hi=2600, rev=False):
    n = int(d * SR)
    x = noise(n)
    f = np.linspace(lo, hi, n) if not rev else np.linspace(hi, lo, n)
    # sweeping band via ring-mod of filtered noise, cheap but reads right
    x = lowpass_fast(x, 4000, 2)
    x = x * np.sin(2 * np.pi * np.cumsum(f) / SR)
    return x * env_ad(n, 0.28, 0.5, 1.6)


def ui_tick(freq=1800, d=0.018):
    n = int(d * SR)
    return (sine(freq, n) + 0.4 * sine(freq * 2.01, n)) * env_exp(n, 0.0002, d * 0.3)


def ui_confirm():
    """Two-note up. The peak is in note one; placement uses that."""
    n = int(0.42 * SR)
    x = np.zeros(n)
    for i, f in enumerate((784.0, 1174.7)):     # G5 -> D6
        off = int(i * 0.085 * SR)
        m = int(0.30 * SR)
        v = (sine(f, m) * 0.7 + sine(f * 2, m) * 0.18) * env_exp(m, 0.003, 0.11)
        x[off:off + m] += v * (1.0 if i == 0 else 0.85)
    return x


def ui_thunk():
    n = int(0.10 * SR)
    x = sine(np.linspace(220, 110, n), n) * env_exp(n, 0.001, 0.035)
    x += lowpass_fast(noise(n), 900, 2) * env_exp(n, 0.0006, 0.012) * 0.6
    return x


def ui_rubber(d=0.46):
    """Rising strain: pitch and brightness climb while the track stretches."""
    n = int(d * SR)
    f = np.linspace(300, 1250, n)
    x = sine(f, n) * 0.55 + sine(f * 1.5, n) * 0.2
    x += highpass_fast(noise(n), 2500, 2) * 0.25
    return x * env_ad(n, 0.75, 0.22, 1.0) * np.linspace(0.35, 1.0, n)


def ui_snap():
    n = int(0.13 * SR)
    x = sine(np.linspace(1500, 420, n), n) * env_exp(n, 0.0004, 0.030)
    x += highpass_fast(noise(n), 3000, 2) * env_exp(n, 0.0002, 0.008) * 0.7
    return x


def ui_toggle():
    n = int(0.055 * SR)
    x = lowpass_fast(noise(n), 6500, 2) * env_exp(n, 0.0002, 0.0045)
    x += sine(1100, n) * env_exp(n, 0.0002, 0.009) * 0.55
    x += sine(620, n) * env_exp(n, 0.0008, 0.020) * 0.30
    return x


def ui_key():
    n = int(0.024 * SR)
    x = lowpass_fast(noise(n), 4200, 2) * env_exp(n, 0.0002, 0.0045)
    x += sine(1500 + rng.uniform(-160, 160), n) * env_exp(n, 0.0002, 0.006) * 0.35
    return x


def ui_pop():
    n = int(0.09 * SR)
    x = sine(np.linspace(620, 1500, n), n) * env_exp(n, 0.0012, 0.022)
    return x


def ui_draw(d=0.48):
    """The chart stroking in: a quiet rising shimmer, no transient."""
    n = int(d * SR)
    x = highpass_fast(noise(n), 4500, 2) * 0.5
    x += sine(np.linspace(900, 2400, n), n) * 0.25
    return x * env_ad(n, 0.5, 0.45, 1.3) * np.linspace(0.3, 1.0, n)


def ui_toast():
    n = int(0.62 * SR)
    x = np.zeros(n)
    for i, f in enumerate((659.3, 987.8, 1318.5)):   # E5 B5 E6
        off = int(i * 0.070 * SR)
        m = int(0.40 * SR)
        v = (sine(f, m) * 0.6 + sine(f * 2, m) * 0.12) * env_exp(m, 0.004, 0.14)
        x[off:off + m] += v * (0.9, 1.0, 0.7)[i]
    return x


def ui_enter():
    n = int(0.07 * SR)
    x = lowpass_fast(noise(n), 3000, 2) * env_exp(n, 0.0004, 0.010)
    x += sine(330, n) * env_exp(n, 0.0006, 0.024) * 0.7
    return x


# ---------------------------------------------------------------- verify grid
def onset_envelope(x, sr=SR, hop=256, win=1024, band=None):
    """Spectral flux, returned with the time of each value in seconds.

    Frame k spans [k*hop, k*hop+win). flux[k] is the rise from frame k to k+1,
    so the onset it reports sits at the start of frame k+1 -> (k+1)*hop.
    """
    frames = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(frames)[:, None]
    S = np.abs(np.fft.rfft(x[idx] * np.hanning(win), axis=1))
    if band is not None:
        f = np.fft.rfftfreq(win, 1 / sr)
        S = S[:, (f >= band[0]) & (f < band[1])]
    flux = np.maximum(0, np.diff(S, axis=0)).sum(axis=1)
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    t = (np.arange(len(flux)) + 1) * hop / sr
    return t, flux


def comb_phase(t, flux, period, n_phase=400):
    """Best continuous phase of a period-spaced comb against the envelope."""
    phases = np.linspace(0, period, n_phase, endpoint=False)
    best, best_p = -1e18, 0.0
    for p in phases:
        hits = np.arange(p, t[-1], period)
        # nearest-neighbour sample, tolerant to the hop resolution
        s = flux[np.clip(np.searchsorted(t, hits), 0, len(flux) - 1)].sum()
        if s > best:
            best, best_p = s, p
    return best_p, best


def detect_grid(x, sr=SR):
    """Tempo by flux autocorrelation, beat phase and downbeat by comb fit.

    Beats are read from the full-band flux; the downbeat is read from the
    sub-band (<90 Hz) envelope, where only the bar-one bass note moves.
    """
    hop = 256
    fps = sr / hop
    t, flux = onset_envelope(x, sr, hop)

    ac = np.correlate(flux, flux, "full")[len(flux) - 1:]
    lo, hi = int(fps * 60 / 200), int(fps * 60 / 70)
    lag = lo + int(np.argmax(ac[lo:hi]))
    bpm = 60 * fps / lag
    beat = 60.0 / bpm

    beat_phase, _ = comb_phase(t, flux, beat)

    # downbeat: test the 4 candidate bar phases against the sub-band envelope
    tb, fb = onset_envelope(x, sr, hop, band=(20, 90))
    bar = beat * 4
    cands = [(beat_phase + k * beat) % bar for k in range(4)]
    scores = []
    for p in cands:
        hits = np.arange(p, tb[-1], bar)
        scores.append(fb[np.clip(np.searchsorted(tb, hits), 0, len(fb) - 1)].sum())
    downbeat = cands[int(np.argmax(scores))]
    if bar - downbeat < downbeat:                  # a phase just under a full bar is ~0
        downbeat -= bar
    return bpm, beat_phase, downbeat


# ---------------------------------------------------------------- mixing
def add(buf, x, start, gain=1.0):
    """Loops fold a tail past the end back into bar 1; one-shots drop it."""
    s0 = int(start)
    if LOOP:
        np.add.at(buf, (np.arange(len(x)) + s0) % len(buf), x * gain)
        return
    a, c = max(0, s0), min(len(buf), s0 + len(x))
    if c > a:
        buf[a:c] += x[a - s0:c - s0] * gain


def at_peak(buf, x, t, gain):
    pk = int(np.argmax(np.abs(x)))
    add(buf, x, round(t * SR) - pk, gain)
    return pk / SR


def bt(bar, beat, six=0.0):
    return ((bar - 1) * 4 + (beat - 1) + six * 0.25) * BEAT


SOUNDS = {
    "click": ui_click_down, "release": ui_click_up, "tick": ui_tick, "key": ui_key,
    "whoosh": lambda: ui_whoosh(0.28, 400, 2000), "whoosh_rev": lambda: ui_whoosh(0.26, 2000, 500, rev=True),
    "confirm": ui_confirm, "toggle": ui_toggle, "thunk": ui_thunk, "snap": ui_snap,
    "pop": ui_pop, "draw": ui_draw, "toast": ui_toast, "rubber": ui_rubber, "enter": ui_enter,
}

def decode(path, start=0.0, dur=None, channels=2):
    """Any file ffmpeg reads, as float samples at SR, shape (n, channels)."""
    cmd = ["ffmpeg", "-v", "error", "-ss", str(max(0.0, start))] + (["-t", str(dur)] if dur else []) + \
          ["-i", path, "-vn", "-ac", str(channels), "-ar", str(SR), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<i2").reshape(-1, channels) / 32768.0


# ---------------------------------------------------------------- the bed
bed = np.zeros(N)
music = None                                       # the person's track, kept in stereo
if args.music:
    full = decode(args.music)
    bpm_m, _, down_m = detect_grid(full.mean(1))
    print(f"track tempo {bpm_m:.2f} BPM, first downbeat near {down_m:.3f}s (scene bpm is {META['bpm']})")
    # a negative offset starts the track that much after the video's first frame
    lead_in = int(max(0.0, -args.offset) * SR)
    seg = full[int(max(0.0, args.offset) * SR):][:max(0, N - lead_in)]
    music = np.zeros((N, 2))
    music[lead_in:lead_in + len(seg)] = seg / (np.abs(seg).max() + 1e-9) * 0.9
    if not LOOP:                                   # fade the track out under the end card
        f0 = min(N, int((END_T + 0.3) * SR))
        music[f0:] *= (np.linspace(1, 0, N - f0) ** 2)[:, None]
else:
    bars = int(np.ceil(DUR / (4 * BEAT)))
    stop = END_T if (END_T and not LOOP) else DUR + 1
    ROOTS = [55.00, 55.00, 61.74, 55.00, 49.00, 65.41, 55.00, 43.65]   # an A-minor walk
    for i in range(bars):
        t0 = bt(i + 1, 1)
        if t0 >= stop:
            break
        f = ROOTS[i % len(ROOTS)]
        add(bed, subbass(f, min(BEAT * 4 * 1.04, stop - t0 + .05)), t0 * SR, 0.34)
        if 2 <= i < bars - 1:
            add(bed, pad(f * 4, BEAT * 4 * 1.03), t0 * SR, 0.055)
        for beat in range(1, 5):
            for six, g in ((0, .10), (2, .16)):
                th = bt(i + 1, beat, six)
                if th < stop - 1e-6:
                    add(bed, hat(open_=(six == 2 and beat == 4 and i % 2)), th * SR, g)
            tb = bt(i + 1, beat)
            if tb >= stop - 1e-6:
                continue
            if beat in (1, 3):
                add(bed, kick(), tb * SR, 0.92 if beat == 1 else 0.8)
            else:
                add(bed, pluck(440.0 if beat == 2 else 329.6), tb * SR, 0.17)
    if LOOP:
        sw = int(0.55 * SR)                        # a swell that carries the seam
        add(bed, highpass_fast(noise(sw), 1800, 2) * np.linspace(0, 1, sw) ** 2.4, (DUR - 0.55) * SR, 0.085)
    else:                                          # resolve on the end card and ring out
        ring = DUR - END_T + .2
        for f, g in ((220.0, .060), (261.63, .045), (329.63, .045), (493.88, .030)):
            add(bed, pad(f, ring) * env_exp(int(ring * SR), .02, 2.6, 1e-3), (END_T - .02) * SR, g)
        tail = int((DUR - END_T) * SR)
        add(bed, (sine(55.0, tail) * .85 + sine(110.0, tail) * .12) * env_exp(tail, .01, (DUR - END_T) * .9, 1e-3), END_T * SR, .36)
        add(bed, kick(), END_T * SR, 0.95)
        sw = int(0.55 * SR)
        add(bed, highpass_fast(noise(sw), 1800, 2) * np.linspace(0, 1, sw) ** 2.4, (END_T - 0.55) * SR, 0.085)

# ---------------------------------------------------------------- the cues
sfx = np.zeros(N)
unknown = sorted({c["sound"] for c in CUES} - set(SOUNDS))
if unknown:
    raise SystemExit(f"unknown sound(s) {unknown}; available: {sorted(SOUNDS)}")
for c in CUES:
    at_peak(sfx, SOUNDS[c["sound"]](), c["t"], c.get("gain", 0.5))

# ---------------------------------------------------------------- footage sound
voice = np.zeros(N); duck = np.ones(N)
for v in args.voice:
    path, at, start, dur = v.rsplit(":", 3)
    at, start, dur = float(at), float(start), float(dur)
    clip = decode(path, start, dur, channels=1)[:, 0]
    a = int(at * SR); clip = clip[:max(0, N - a)]
    voice[a:a + len(clip)] += clip / (np.abs(clip).max() + 1e-9) * 0.8
    r = min(int(0.15 * SR), len(clip) // 2)        # the bed steps back under speech, then returns
    env = np.zeros(len(clip))                      # 0 = fully ducked
    if r:
        env[:r] = np.linspace(1, 0, r); env[-r:] = np.linspace(0, 1, r)
    duck[a:a + len(clip)] = np.minimum(duck[a:a + len(clip)], 0.4 + 0.6 * env)

# ---------------------------------------------------------------- check, mix, write
if not args.music:
    bpm_m, _, down_m = detect_grid(bed)
    print(f"bed measured {bpm_m:.2f} BPM (target {META['bpm']}), downbeat {down_m * 1000:+.0f} ms")
x = bed * 0.8 + sfx
worst = max((abs((np.argmax(np.abs(x[max(0, int(c['t'] * SR) - 576):int(c['t'] * SR) + 576])) +
                  max(0, int(c['t'] * SR) - 576)) / SR - c['t']) for c in CUES), default=0)
print(f"{len(CUES)} cues placed by measured peak; worst offset {worst * 1000:.1f} ms "
      "(a neighbouring louder cue inside 12 ms can read as an offset)")
base = music if music is not None else np.stack([bed, bed], 1)
st = base * 0.8 * duck[:, None] + np.stack([sfx, np.roll(sfx, 3)], 1) + voice[:, None]   # a few samples of width on the cues
st = np.tanh(st * 1.25) / np.tanh(1.25)
st *= 0.89 / (np.abs(st).max() + 1e-9)
with wave.open(args.out, "w") as f:
    f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR)
    f.writeframes((np.clip(st, -1, 1) * 32767).astype("<i2").tobytes())
print(f"wrote {args.out}  {DUR:.2f}s  {'loop' if LOOP else 'one-shot'}")
