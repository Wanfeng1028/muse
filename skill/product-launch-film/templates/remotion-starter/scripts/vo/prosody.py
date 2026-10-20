#!/usr/bin/env python3
"""Objective prosody numbers for narration takes, for when nobody can listen yet.

  python3 scripts/vo/prosody.py vo-takes/take1 vo-takes/take2 [--script src/vo-script.json]

For each take dir (OUT of vo.py) prints: median F0, pitch SD and 5-95% range in semitones (expressiveness;
SD < ~2 st sounds flat/read), loudness SD in dB (movement), words per second (aim ~2.3-2.7).
Needs numpy and ffmpeg on PATH. Numbers support a pick; they don't replace listening.
"""
import argparse, glob, json, os, re, subprocess
import numpy as np


def load(path, sr=16000):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32), sr


def f0_track(x, sr, fmin=70, fmax=400, win=0.04, hop=0.01):
    n, h = int(win * sr), int(hop * sr)
    lo, hi = int(sr / fmax), int(sr / fmin)
    out, rms = [], []
    for i in range(0, len(x) - n, h):
        f = x[i:i + n] * np.hanning(n)
        e = float(np.sqrt((f ** 2).mean())); rms.append(e)
        if e < 0.01:
            out.append(np.nan); continue
        ac = np.correlate(f, f, "full")[n - 1:]
        ac /= ac[0] + 1e-9
        k = lo + int(np.argmax(ac[lo:hi]))
        out.append(sr / k if ac[k] > 0.45 else np.nan)
    return np.array(out), np.array(rms)


def stats(paths, words):
    f0s, rmss, dur = [], [], 0.0
    for p in paths:
        x, sr = load(p); dur += len(x) / sr
        f0, rms = f0_track(x, sr); f0s.append(f0); rmss.append(rms)
    f0 = np.concatenate(f0s); f0 = f0[~np.isnan(f0)]
    st = 12 * np.log2(f0 / np.median(f0))
    rms = np.concatenate(rmss); db = 20 * np.log10(rms[rms > 0.01])
    return {"f0_median_hz": round(float(np.median(f0)), 1), "pitch_sd_st": round(float(st.std()), 2),
            "pitch_range_st": round(float(np.percentile(st, 95) - np.percentile(st, 5)), 2),
            "loud_sd_db": round(float(db.std()), 2), "wps": round(words / dur, 2), "sec": round(dur, 2)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--script", default="src/vo-script.json")
    a = ap.parse_args()
    text = {l["id"]: re.sub(r"\[[^\]]*\]\s*", "", l["text"]) for l in json.load(open(a.script))["lines"]}
    for d in a.dirs:
        files = sorted(glob.glob(os.path.join(d, "*.mp3")))
        ids = [os.path.splitext(os.path.basename(f))[0] for f in files]
        words = sum(len(text.get(i, "").split()) for i in ids)
        print(os.path.basename(os.path.normpath(d)).ljust(16), stats(files, words))
