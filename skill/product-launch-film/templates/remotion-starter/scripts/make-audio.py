#!/usr/bin/env python3
"""Original music bed + UI SFX, synthesized from scratch (numpy only; no samples, no third-party audio).

    python3 scripts/make-audio.py            # needs: pip install numpy
      -> public/audio/music.wav              (48 kHz stereo, length = timeline TOTAL)
      -> public/audio/sfx/{tick,tick-low,deny,allow,thread,bloom,air}.wav
      -> src/audio.json                      (tells Sound.tsx what exists)

Scene cuts come from src/timeline.ts, and the chord changes on each cut. Edit CHORDS per scene:
keep it light under the problem, fullest at the core moment, held back under the proof, and resolve on the close.
This is deliberately simple; swap in a licensed track if you have one (and credit it).
"""
import json, pathlib, re, wave
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
SR = 48000
rng = np.random.default_rng(7)

tl = (ROOT / "src/timeline.ts").read_text()
FPS = int(re.search(r"FPS\s*=\s*(\d+)", tl).group(1))
scenes = [(int(a), int(b)) for a, b in re.findall(r"from:\s*(\d+),\s*dur:\s*(\d+)", tl)]
TOTAL = max(a + b for a, b in scenes) / FPS
CUTS = [a / FPS for a, _ in scenes] + [TOTAL]
BPM = 100
BEAT = 60 / BPM
# MIDI chords, cycled over scenes (D major family). Replace per scene.
CHORDS = [[50, 57, 62, 64, 66], [43, 50, 55, 59, 62, 66], [47, 54, 59, 61, 62], [45, 52, 57, 61, 64], [38, 45, 50, 54, 57, 64]]
hz = lambda m: 440 * 2 ** ((m - 69) / 12)


def lp_fft(x, fc):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / np.sqrt(1 + (f / fc) ** 4)
    return np.fft.irfft(X, len(x))


def reverb(x, seconds=1.8, mix=0.22):
    n = int(seconds * SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (SR * seconds / 6))
    ir = lp_fft(ir, 5000)
    ir /= np.sqrt((ir ** 2).sum())
    wet = np.fft.irfft(np.fft.rfft(x, len(x) + n) * np.fft.rfft(ir, len(x) + n))[: len(x)]
    return (1 - mix) * x + mix * wet


def bell(freq, seconds):
    t = np.arange(int(seconds * SR)) / SR
    mod = np.sin(2 * np.pi * freq * 2 * t) * 1.1 * np.exp(-t / 0.35)
    return np.sin(2 * np.pi * freq * t + mod) * np.minimum(1, t / 0.006) * np.exp(-t / 1.6)


def music():
    n = int(TOTAL * SR)
    out = np.zeros((n, 2))
    for si in range(len(CUTS) - 1):
        a, b = CUTS[si], CUTS[si + 1]
        notes = CHORDS[si % len(CHORDS)]
        t = a
        k = 0
        while t < b - 0.05:  # soft chord strikes every 2 beats, one note voice spread L/R
            for j, m in enumerate(notes):
                s = bell(hz(m), min(3.0, b - t + 0.6)) * (0.05 if j else 0.07)
                i0 = int(t * SR)
                seg = s[: max(0, min(len(s), n - i0))]
                pan = 0.5 + 0.35 * np.sin(j * 1.7 + k)
                out[i0 : i0 + len(seg), 0] += seg * (1 - pan)
                out[i0 : i0 + len(seg), 1] += seg * pan
            t += 2 * BEAT
            k += 1
    for ch in range(2):
        out[:, ch] = reverb(out[:, ch], 2.2, 0.3)
    fade = np.minimum(1, np.arange(n) / (0.4 * SR)) * np.minimum(1, (n - np.arange(n)) / (1.5 * SR))
    out *= fade[:, None]
    return out / (np.abs(out).max() + 1e-9) * 0.5


def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(1, t / attack) * np.exp(-t / decay)


def sfx():
    d = {}
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    d["tick"] = np.sin(2 * np.pi * 2400 * t) * env(n, 0.0008, 0.012) * 0.8
    d["tick-low"] = np.sin(2 * np.pi * 1300 * t) * env(n, 0.0008, 0.018) * 0.8
    n = int(0.6 * SR); t = np.arange(n) / SR
    d["deny"] = (np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 233 * t)) * env(n, 0.004, 0.12) * 0.6
    d["allow"] = (np.sin(2 * np.pi * 660 * t) * env(n, 0.003, 0.18) + np.sin(2 * np.pi * 990 * np.maximum(0, t - 0.07)) * env(n, 0.003, 0.22) * (t > 0.07)) * 0.5
    n = int(0.9 * SR); t = np.arange(n) / SR
    d["thread"] = np.sin(2 * np.pi * (880 + 440 * t) * t) * env(n, 0.02, 0.25) * 0.35
    n = int(3.0 * SR)
    d["bloom"] = sum(bell(hz(m), 3.0) for m in (62, 66, 69, 74)) * 0.25
    noise = rng.standard_normal(int(1.2 * SR))
    d["air"] = lp_fft(noise, 2500) * np.sin(np.linspace(0, np.pi, len(noise))) ** 2 * 0.12
    return {k: reverb(v, 0.8, 0.15) for k, v in d.items()}


def write(path, x):
    x = np.asarray(x)
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    write(ROOT / "public/audio/music.wav", music())
    names = []
    for k, v in sfx().items():
        write(ROOT / f"public/audio/sfx/{k}.wav", v / (np.abs(v).max() + 1e-9) * 0.7)
        names.append(k)
    (ROOT / "src/audio.json").write_text(json.dumps({"note": "Written by scripts/make-audio.py.", "music": "audio/music.wav", "sfx": names}, indent=1) + "\n")
    print(f"music {TOTAL:.2f}s, {len(names)} sfx -> public/audio/")
