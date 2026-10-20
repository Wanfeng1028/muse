"""Synthesize the ui-morph music bed (deterministic, numpy only).

Grid: beat k starts at sample k*BEAT (44.1 kHz, BEAT = round(SR*60/bpm)).
Bar = 4 beats. Writes <out>.wav, then encodes <out>.m4a with ffmpeg.

  - kick on every beat, closed hat on every off-beat
  - a soft sine pad, one chord per bar (A minor, F, C, G), above 200 Hz
  - a quiet UI tap (short high blip) on each --taps beat: the clicks, the
    drag grabs and releases, the toggle tick, the key presses, the toast pop
  - no fade: the video loops, so every tail that runs past the end is folded
    back onto the start and the bed loops seamlessly with the picture

Defaults reproduce the original 14 s / 120 BPM bed byte-for-byte (seed 719).

    python3 scripts/make_music.py --bpm 120 --duration 14 \
        --taps 0,3,6,8,9,11,13,15,17,18,21,22,23,26 --seed 719 --out assets/music.wav
"""
import argparse
import os
import subprocess
import wave

import numpy as np

SR = 44100
TAPS = "0,3,6,8,9,11,13,15,17,18,21,22,23,26"


def synth(bpm, dur, taps, seed):
    beat = int(round(SR * 60 / bpm))
    n_total = int(round(SR * dur))
    tail = SR  # 1 s of room for tails, folded back onto the start
    rng = np.random.default_rng(seed)
    buf = np.zeros((n_total + tail, 2))

    def add(sig, start, gain=1.0, pan=0.0):
        s = int(start)
        e = min(len(buf), s + len(sig))
        a = (pan + 1) * np.pi / 4
        buf[s:e, 0] += sig[: e - s] * gain * np.cos(a)
        buf[s:e, 1] += sig[: e - s] * gain * np.sin(a)

    def kick():
        n = int(SR * 0.32)
        t = np.arange(n) / SR
        f = 48 + 110 * np.exp(-t * 30)  # 158 -> 48 Hz sweep
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 10)
        click = rng.standard_normal(n) * np.exp(-t * 700) * 0.25
        return np.tanh((body + click) * 1.5)

    def hat():
        n = int(SR * 0.05)
        t = np.arange(n) / SR
        x = rng.standard_normal(n)
        x = np.diff(np.concatenate([[0.0], x]))  # first difference = crude high-pass
        return x * np.exp(-t * 90)

    def tap():
        n = int(SR * 0.09)
        t = np.arange(n) / SR
        tone = np.sin(2 * np.pi * 1760 * t) + 0.4 * np.sin(2 * np.pi * 2640 * t)
        return tone * np.exp(-t * 60) * np.minimum(1, t / 0.0015)

    def pad(midis, n):
        t = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * 440.0 * 2 ** ((m - 69) / 12) * t) for m in midis)
        env = np.minimum(1, t / 0.25) * np.minimum(1, (n - np.arange(n)) / (0.3 * SR))
        return x * env / len(midis)

    total_beats = int(round(dur * bpm / 60))
    for k in range(total_beats):
        add(kick(), k * beat, 0.95)
        add(hat(), k * beat + beat // 2, 0.12, pan=0.25)
    chords = [(57, 60, 64), (53, 57, 60), (55, 60, 64), (55, 59, 62)]  # Am F C G (inversions)
    for bar in range((total_beats + 3) // 4):
        add(pad(chords[bar % 4], 4 * beat + beat // 2), bar * 4 * beat, 0.10)
    for b in taps:
        add(tap(), int(round(b * beat)), 0.16, pan=0.15)

    buf[: tail] += buf[n_total:]  # wrap the tails: the bed loops like the picture
    mix = buf[:n_total]
    mix *= 10 ** (-1 / 20) / np.max(np.abs(mix))  # normalise to -1 dBFS
    assert np.max(np.abs(mix)) < 1.0
    return (mix * 32767).astype(np.int16)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bpm", type=float, default=120)
    ap.add_argument("--duration", type=float, default=14)
    ap.add_argument("--taps", default=TAPS, help="comma-separated beat numbers")
    ap.add_argument("--seed", type=int, default=719)
    ap.add_argument("--out", default="assets/music.wav")
    ap.add_argument("--no-encode", action="store_true", help="write the .wav only")
    a = ap.parse_args()
    taps = [float(x) for x in a.taps.split(",") if x.strip()]
    if not all(0 <= b < a.duration * a.bpm / 60 for b in taps):
        ap.error("every tap must be a beat inside the duration")

    pcm = synth(a.bpm, a.duration, taps, a.seed)
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
