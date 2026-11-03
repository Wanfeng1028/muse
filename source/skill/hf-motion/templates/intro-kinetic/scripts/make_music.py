"""Synthesize the intro-kinetic music bed (deterministic, numpy only).

Grid: beat k starts at sample k*BEAT (44.1 kHz, BEAT = round(SR*60/bpm)).
Bar = 4 beats. Writes <out>.wav, then encodes <out>.m4a with ffmpeg.

Structure follows the composition's scene plan:
  - kick on every beat, boom kicks on beat 0 and on --finale-beat
  - the beat before --finale-beat drops kick/clap/bass for contrast
  - plucked stabs everywhere except the flash scene [--flash-beat, --finale-beat)
  - noise riser across the flash scene, stab chord on the finale impact
  - 0.5 s fade-out at the end

Defaults reproduce the original 15 s / 120 BPM bed byte-for-byte (seed 719).

    python3 scripts/make_music.py --bpm 120 --duration 15 --flash-beat 18 \
        --finale-beat 22 --seed 719 --out assets/music.wav
"""
import argparse
import os
import subprocess
import wave

import numpy as np

SR = 44100


def synth(bpm, dur, flash_beat, finale_beat, seed):
    beat = int(round(SR * 60 / bpm))
    n_total = int(SR * dur)
    rng = np.random.default_rng(seed)
    left = np.zeros(n_total)
    right = np.zeros(n_total)

    def add(sig, start, gain=1.0, pan=0.0):
        """Mix mono sig at sample `start`; pan -1..1 (equal-power)."""
        s = int(start)
        e = min(n_total, s + len(sig))
        if e <= s:
            return
        a = (pan + 1) * np.pi / 4
        left[s:e] += sig[: e - s] * gain * np.cos(a)
        right[s:e] += sig[: e - s] * gain * np.sin(a)

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

    def kick(boom=False):
        n = int(SR * (0.9 if boom else 0.35))
        t = np.arange(n) / SR
        f = 45 + 105 * np.exp(-t * 28)  # 150 -> 45 Hz sweep
        ph = 2 * np.pi * np.cumsum(f) / SR
        body = np.sin(ph) * np.exp(-t * (3.0 if boom else 9.0))
        click = rng.standard_normal(n) * np.exp(-t * 600) * 0.35
        out = np.tanh((body + click) * 1.6)
        if boom:  # extra sub tail
            out += 0.6 * np.sin(2 * np.pi * 40 * t) * np.exp(-t * 2.2)
        return out

    def hat():
        n = int(SR * 0.06)
        t = np.arange(n) / SR
        return hp(rng.standard_normal(n), 7000) * np.exp(-t * 70)

    def clap():
        n = int(SR * 0.25)
        t = np.arange(n) / SR
        noise = hp(rng.standard_normal(n), 900)
        env = np.exp(-t * 22)
        for d in (0.0, 0.011, 0.022):  # 3 quick flams = clap
            k = int(d * SR)
            env[k:] += 0.6 * np.exp(-(t[: n - k]) * 140)
        tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * 0.4
        return noise * env * 0.7 + tone

    def saw(freq, n):
        t = np.arange(n) / SR
        return 2 * ((t * freq) % 1.0) - 1

    def bass(freq):
        n = int(SR * 0.22)
        t = np.arange(n) / SR
        x = saw(freq, n) + 0.5 * saw(freq * 1.005, n)
        x = onepole_lp(onepole_lp(x, 380), 380)
        env = np.minimum(1, t / 0.004) * np.exp(-t * 11)
        return np.tanh(x * 2.2) * env

    def pluck(freq):
        n = int(SR * 0.4)
        t = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * freq * h * t) / h for h in (1, 2, 3, 4))
        x += 0.5 * sum(np.sin(2 * np.pi * freq * 1.5 * h * t) / h for h in (1, 2))  # fifth
        return x * np.exp(-t * 9) * np.minimum(1, t / 0.003)

    def hz(midi):
        return 440.0 * 2 ** ((midi - 69) / 12)

    a1, e2, g1, c2 = hz(33), hz(40), hz(31), hz(36)
    bassline = [a1, a1, a1, e2, a1, a1, g1, c2]  # per 8th within a bar (one bar loop)
    stabs = {0: hz(69), 3: hz(72), 6: hz(76), 10: hz(74), 13: hz(72)}  # 16th index in 2-bar loop

    total_beats = int(round(dur * bpm / 60))
    gap_beat = finale_beat - 1  # kick dropped for contrast before the finale impact
    flash_sec = flash_beat * 60 / bpm
    finale_sec = finale_beat * 60 / bpm
    for k in range(total_beats):
        s = k * beat
        boom = k in (0, finale_beat)
        if k != gap_beat:
            add(kick(boom=boom), s, 1.1 if boom else 0.95)
        add(hat(), s + beat // 2, 0.22, pan=0.25)  # offbeat closed hat
        if k % 4 in (1, 3) and k != gap_beat:  # beats 2 and 4
            add(clap(), s, 0.45, pan=-0.05)
        if k != gap_beat:  # bass on 8ths (skip during gap)
            for e in range(2):
                idx = (k % 4) * 2 + e
                add(bass(bassline[idx]), s + e * beat // 2, 0.42)

    # sparse minor stabs (16th grid, 2-bar pattern = 32 sixteenths), silent in the flash scene
    s16 = beat // 4
    for i in range(total_beats * 4):
        t_sec = i * s16 / SR
        if flash_sec <= t_sec < finale_sec:
            continue
        j = i % 32
        if j in stabs:
            add(pluck(stabs[j]), i * s16, 0.16, pan=0.35 if j % 2 else -0.35)

    # riser across the flash scene: noise through a rising lowpass, swelling gain
    rs, re_ = int(flash_sec * SR), int(finale_sec * SR)
    n = re_ - rs
    prog = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    y = np.empty(n)
    acc = 0.0
    for i in range(n):
        fc = 300 + 9000 * prog[i] ** 2
        a = np.exp(-2 * np.pi * fc / SR)
        acc = (1 - a) * noise[i] + a * acc
        y[i] = acc
    y = hp(y, 200) * prog**2 * 0.9
    add(y, rs, 1.0)

    # finale stab chord on the impact
    t = np.arange(int(SR * 1.2)) / SR
    chord = sum(np.sin(2 * np.pi * hz(m) * t) for m in (57, 60, 64, 69)) * np.exp(-t * 3)
    add(chord, finale_beat * beat, 0.12)

    # fade over the last 0.5 s
    fade = np.ones(n_total)
    fs = int((dur - 0.5) * SR)
    fade[fs:] = np.linspace(1, 0, n_total - fs) ** 2
    left *= fade
    right *= fade

    mix = np.stack([left, right], axis=1)
    mix *= 10 ** (-1 / 20) / np.max(np.abs(mix))  # normalise to -1 dBFS
    assert np.max(np.abs(mix)) < 1.0
    pcm = (mix * 32767).astype(np.int16)
    assert pcm.shape[0] == n_total
    return pcm


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bpm", type=float, default=120)
    ap.add_argument("--duration", type=float, default=15)
    ap.add_argument("--flash-beat", type=int, default=18)
    ap.add_argument("--finale-beat", type=int, default=22)
    ap.add_argument("--seed", type=int, default=719)
    ap.add_argument("--out", default="assets/music.wav")
    ap.add_argument("--no-encode", action="store_true", help="write the .wav only")
    a = ap.parse_args()
    if not 0 < a.flash_beat < a.finale_beat < a.duration * a.bpm / 60:
        ap.error("need 0 < flash-beat < finale-beat < total beats")

    pcm = synth(a.bpm, a.duration, a.flash_beat, a.finale_beat, a.seed)
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
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", a.out, "-c:a", "aac", "-b:a", "256k", m4a],
        check=True,
    )
    print("wrote", a.out, "and", m4a)


if __name__ == "__main__":
    main()
