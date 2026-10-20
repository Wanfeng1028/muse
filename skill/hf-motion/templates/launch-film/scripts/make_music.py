"""Synthesize the launch-film music bed + UI sounds (deterministic, numpy only).

Grid: beat k starts at sample k*BEAT (44.1 kHz, BEAT = round(SR*60/bpm)); the
piece is 54 beats and loops (no fade: the last beat brings the bed back so
beat 0 follows naturally).

  - kick on every beat (soft in the open, full from the drop, quiet in the
    wall breakdown, full again on the last beat)
  - DROP on beat 12 (the bento zoom lands): boom kick, sub, bass and claps
  - quiet breakdown across the wall scene (beats 48-52): pad, no bass/claps
  - UI sounds synthesized and placed on the beats where the cursor acts
    (clicks, pops, ticks, whooshes, floods); see CUES

Normalised to -1 dBFS peak (verify-render wants -6..-0.1 dBFS after AAC).

    python3 scripts/make_music.py --bpm 120 --glass-letters 5 --digits 4 \\
        --seed 719 --out assets/music.wav
"""
import argparse
import os
import subprocess
import wave

import numpy as np

SR = 44100
BEATS = 54
DROP, BREAK_AT, BREAK_END = 12, 48, 53

# UI cues in beats (the template's beat map; kept in step with index.html)
CUES = [
    ("click", [3, 11, 16, 38, 39, 40, 41, 48, 50.5, 51.5, 51.9]),
    ("grab", [18, 25, 27, 31, 35]),
    ("thud", [21, 34]),
    ("whoosh", [11.2, 21.1, 23, 26, 28, 32, 33, 40.05]),
    ("tick", [31.2, 31.4, 31.6, 35.1, 35.25, 35.4]),
    ("pop", [0.9, 1.9, 5, 15.35, 15.47, 15.59, 15.71, 26.3, 37.2, 37.3, 37.4, 37.5, 37.6, 37.7]),
    ("chime", [42.15, 47.15]),
    ("flood", [48, 51.9]),
]


def synth(bpm, seed, glass_letters, digits):
    beat = int(round(SR * 60 / bpm))
    n_total = int(round(SR * BEATS * 60 / bpm))
    rng = np.random.default_rng(seed)
    left = np.zeros(n_total)
    right = np.zeros(n_total)

    def add(sig, start, gain=1.0, pan=0.0):
        s = int(start)
        e = min(n_total, s + len(sig))
        if e <= s:
            return
        a = (pan + 1) * np.pi / 4
        left[s:e] += sig[: e - s] * gain * np.cos(a)
        right[s:e] += sig[: e - s] * gain * np.sin(a)

    def at(b):  # beat (may be fractional) -> sample
        return int(round(b * beat))

    def onepole_lp(x, fc):
        a = np.exp(-2 * np.pi * fc / SR)
        y = np.empty_like(x)
        acc = 0.0
        for i, v in enumerate(x):
            acc = (1 - a) * v + a * acc
            y[i] = acc
        return y

    def hp(x, fc):
        return x - onepole_lp(x, fc)

    def env(n, decay, attack=0.002):
        t = np.arange(n) / SR
        return np.minimum(1, t / attack) * np.exp(-t * decay)

    def kick(boom=False):
        n = int(SR * (0.9 if boom else 0.32))
        t = np.arange(n) / SR
        f = 45 + 110 * np.exp(-t * 30)
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * (3.0 if boom else 9.5))
        click = rng.standard_normal(n) * np.exp(-t * 600) * 0.3
        out = np.tanh((body + click) * 1.6)
        if boom:
            out += 0.6 * np.sin(2 * np.pi * 41 * t) * np.exp(-t * 2.4)
        return out

    def hat():
        n = int(SR * 0.05)
        return hp(rng.standard_normal(n), 7000) * env(n, 80, 0.0005)

    def clap():
        n = int(SR * 0.22)
        t = np.arange(n) / SR
        e = np.exp(-t * 24)
        for d in (0.0, 0.011, 0.021):
            k = int(d * SR)
            e[k:] += 0.6 * np.exp(-t[: n - k] * 140)
        return hp(rng.standard_normal(n), 900) * e * 0.7

    def tone(freqs, n, decay, harm=(1,), attack=0.003):
        t = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * f * h * t) / h for f in freqs for h in harm)
        return x * env(n, decay, attack)

    def bass(freq):
        n = int(SR * 0.22)
        t = np.arange(n) / SR
        x = 2 * ((t * freq) % 1.0) - 1
        return np.tanh(onepole_lp(onepole_lp(x, 360), 360) * 2.2) * env(n, 10, 0.004)

    def hz(m):
        return 440.0 * 2 ** ((m - 69) / 12)

    # ---- UI sounds
    def ui(kind):
        if kind == "click":
            n = int(SR * 0.05)
            return hp(rng.standard_normal(n), 2500) * env(n, 160, 0.0005) * 0.6 + tone([2100], n, 90) * 0.5
        if kind == "grab":
            n = int(SR * 0.07)
            return hp(rng.standard_normal(n), 1200) * env(n, 90, 0.0008) * 0.4 + tone([900], n, 60) * 0.5
        if kind == "tick":
            n = int(SR * 0.02)
            return tone([3200], n, 220) * 0.45
        if kind == "pop":
            n = int(SR * 0.09)
            t = np.arange(n) / SR
            f = 380 + 700 * (1 - np.exp(-t * 60))
            return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 45, 0.001) * 0.6
        if kind == "thud":
            n = int(SR * 0.2)
            t = np.arange(n) / SR
            f = 60 + 90 * np.exp(-t * 35)
            return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 18, 0.001)
        if kind == "whoosh":
            n = int(SR * 0.4)
            t = np.arange(n) / SR
            x = hp(onepole_lp(rng.standard_normal(n), 2600), 500)
            return x * np.sin(np.pi * t / t[-1]) ** 2 * 0.5
        if kind == "chime":
            n = int(SR * 0.7)
            return tone([hz(88), hz(95)], n, 6, harm=(1, 2)) * 0.25
        if kind == "flood":
            n = int(SR * 0.9)
            t = np.arange(n) / SR
            f = 70 * np.exp(-t * 1.5) + 34
            sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 3.2, 0.01)
            air = hp(onepole_lp(rng.standard_normal(n), 900), 120) * env(n, 7, 0.02) * 0.3
            return sub + air
        raise ValueError(kind)

    a1, e2, g1, c2, d2 = hz(33), hz(40), hz(31), hz(36), hz(38)
    bassline = [a1, a1, a1, e2, a1, a1, g1, c2]
    stabs = {0: hz(69), 3: hz(72), 6: hz(76), 10: hz(74), 13: hz(72)}

    for k in range(BEATS):
        s = k * beat
        full = DROP <= k < BREAK_AT or k == BREAK_END
        gain = 0.95 if full else (0.6 if k < DROP else 0.4)
        add(kick(boom=k in (DROP, BREAK_END)), s, 1.1 if k == DROP else gain)
        if k >= 4 and (k < BREAK_AT or k == BREAK_END):
            add(hat(), s + beat // 2, 0.2, pan=0.25)
        if full and k % 2 == 1:
            add(clap(), s, 0.42, pan=-0.05)
        if full:
            for e in range(2):
                add(bass(bassline[(k % 4) * 2 + e]), s + e * beat // 2, 0.4)
    # plucked stabs: sparse in the open, full in the body, gone in the breakdown
    s16 = beat // 4
    for i in range(BEATS * 4):
        b = i / 4
        if BREAK_AT <= b < BREAK_END:
            continue
        j = i % 32
        if j in stabs and (b >= DROP or j in (0, 6)):
            add(tone([stabs[j], stabs[j] * 1.5], int(SR * 0.4), 9, harm=(1, 2, 3)), i * s16, 0.11, pan=0.35 if j % 2 else -0.35)
    # riser into the drop
    n = at(DROP) - at(DROP - 2)
    prog = np.linspace(0, 1, n)
    y = hp(onepole_lp(rng.standard_normal(n), 3000), 300) * prog ** 2 * 0.35
    add(y, at(DROP - 2))
    # breakdown pad (the wall)
    n = at(BREAK_END) - at(BREAK_AT)
    t = np.arange(n) / SR
    pad = sum(np.sin(2 * np.pi * hz(m) * t) for m in (57, 60, 64, 67)) * np.minimum(1, t / 0.3) * np.minimum(1, (t[-1] - t) / 0.2)
    add(pad * 0.05, at(BREAK_AT))
    # UI cues; per-letter pops follow the parameters
    cues = dict(CUES)
    cues["pop"] = cues["pop"] + [13 + i * 0.8 / glass_letters for i in range(glass_letters)] + [24 + i * 0.12 for i in range(digits)]
    for kind, beats in cues.items():
        for b in beats:
            add(ui(kind), at(b), 0.55 if kind != "flood" else 0.9, pan=0.1)

    mix = np.stack([left, right], axis=1)
    ramp = int(0.004 * SR)  # no click at the loop point
    mix[-ramp:] *= np.linspace(1, 0, ramp)[:, None]
    mix *= 10 ** (-1 / 20) / np.max(np.abs(mix))
    pcm = (mix * 32767).astype(np.int16)
    assert pcm.shape[0] == n_total
    return pcm


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bpm", type=float, default=120)
    ap.add_argument("--glass-letters", type=int, default=5)
    ap.add_argument("--digits", type=int, default=4)
    ap.add_argument("--seed", type=int, default=719)
    ap.add_argument("--out", default="assets/music.wav")
    ap.add_argument("--no-encode", action="store_true", help="write the .wav only")
    a = ap.parse_args()
    if not 90 <= a.bpm <= 150:
        ap.error("bpm must be 90..150")
    pcm = synth(a.bpm, a.seed, max(1, a.glass_letters), max(1, a.digits))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with wave.open(a.out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    if a.no_encode:
        print("wrote", a.out)
        return
    m4a = os.path.splitext(a.out)[0] + ".m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.out, "-c:a", "aac", "-b:a", "256k", m4a], check=True)
    print("wrote", a.out, "and", m4a)


if __name__ == "__main__":
    main()
