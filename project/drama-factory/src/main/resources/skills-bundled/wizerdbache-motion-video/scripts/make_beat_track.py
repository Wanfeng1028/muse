"""Synthesize a drum track with a known beat grid (no licensing, exact ground truth).

Kick on every beat, snare on beats 2 and 4 of each bar, closed hi-hat on every
eighth note, a crash on the first downbeat. Beat 1 is at t = offset.

Usage:
    python -X utf8 scripts/make_beat_track.py --bpm 120 --bars 7 --out build/beat120.wav
Writes the WAV and a sidecar JSON with every beat time.
"""
import argparse
import json
import wave
from pathlib import Path

import numpy as np

SR = 48000


def kick(sr):
    t = np.arange(int(0.25 * sr)) / sr
    f = 50 + 70 * np.exp(-t / 0.03)
    return np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.09)


def snare(sr, rng):
    t = np.arange(int(0.18 * sr)) / sr
    return (0.7 * rng.standard_normal(len(t)) + 0.4 * np.sin(2 * np.pi * 190 * t)) * np.exp(-t / 0.05)


def hat(sr, rng):
    t = np.arange(int(0.05 * sr)) / sr
    n = rng.standard_normal(len(t))
    n = np.diff(np.concatenate([[0], n]))  # crude high-pass
    return n * np.exp(-t / 0.012)


def crash(sr, rng):
    t = np.arange(int(1.2 * sr)) / sr
    n = np.diff(np.concatenate([[0], rng.standard_normal(len(t))]))
    return n * np.exp(-t / 0.35)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bpm", type=float, default=120)
    ap.add_argument("--bars", type=int, default=7)
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rng = np.random.default_rng(7)
    period = 60 / a.bpm
    n_beats = a.bars * 4
    dur = a.offset + n_beats * period
    y = np.zeros(int(dur * SR) + SR)
    beats = [a.offset + i * period for i in range(n_beats)]

    def add(sig, t, gain):
        i = int(round(t * SR))
        seg = sig[: max(0, len(y) - i)]
        y[i:i + len(seg)] += gain * seg

    k, s, h, c = kick(SR), snare(SR, rng), hat(SR, rng), crash(SR, rng)
    for i, b in enumerate(beats):
        add(k, b, 0.9)
        if i % 4 in (1, 3):
            add(s, b, 0.45)
        add(h, b, 0.12)
        add(h, b + period / 2, 0.08)
    add(c, beats[0], 0.25)
    y = y[: int(dur * SR)]
    y = 0.9 * y / np.max(np.abs(y))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((y * 32767).astype(np.int16).tobytes())
    meta = {"bpm": a.bpm, "bars": a.bars, "beats_per_bar": 4, "duration_s": dur, "offset_s": a.offset,
            "beat_times_s": [round(b, 6) for b in beats],
            "pattern": "kick every beat, snare on beats 2 and 4, hi-hat every eighth, crash on beat 1"}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"{out}: {dur:.3f}s, {n_beats} beats at {a.bpm} BPM")


if __name__ == "__main__":
    main()
