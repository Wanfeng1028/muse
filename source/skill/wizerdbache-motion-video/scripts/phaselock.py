"""Phase-locking of event times to a beat grid (circular statistics).

Nearest-beat offsets cannot tell "on the beat" from "locked to the beat with a
constant delay". This maps every event onto the beat cycle and reports:
  - mean_phase_ms: circular mean position inside the beat (0 = on the beat)
  - R: resultant length, 1 = every event at the same phase, ~0 = unrelated
  - spread_ms: circular standard deviation in ms
It can also search the tempo that best locks the events (--search), which is how
a video cut on its own grid is told apart from one cut to its audio.

Usage:
    python -X utf8 scripts/phaselock.py --grid <outdir>/beat/beatgrid.json --events a,b,c [--search 100:140]
    python -X utf8 scripts/phaselock.py --selftest
"""
import argparse
import json
import sys

import numpy as np


def lock(times, period, phase):
    ang = 2 * np.pi * ((np.asarray(times) - phase) / period)
    z = np.exp(1j * ang).mean()
    R = float(abs(z))
    mean = float(np.angle(z)) / (2 * np.pi) * period
    spread = float(np.sqrt(-2 * np.log(max(R, 1e-9)))) / (2 * np.pi) * period
    return {"n": len(times), "R": round(R, 3), "mean_phase_ms": round(mean * 1000, 1),
            "spread_ms": round(spread * 1000, 1), "period_s": period, "bpm": round(60 / period, 2)}


def search(times, lo, hi):
    best = None
    for bpm in np.arange(lo, hi + 1e-9, 0.05):
        r = lock(times, 60 / bpm, 0.0)
        if best is None or r["R"] > best["R"]:
            best = r
    return best


def selftest():
    rng = np.random.default_rng(1)
    period = 0.5
    locked = 0.075 + period * np.array([1, 2, 4, 7, 9, 12, 15, 20]) + 0.18 + rng.normal(0, 0.01, 8)
    unrelated = rng.uniform(0, 14, 8)
    a = lock(locked, period, 0.075)
    b = lock(unrelated, period, 0.075)
    s = search(0.042 + (60 / 129) * np.array([1, 3, 5, 9, 11, 13, 21, 25, 29]), 100, 140)
    ok = a["R"] > 0.9 and abs(a["mean_phase_ms"] - 180) < 15 and b["R"] < 0.6 and abs(s["bpm"] - 129) <= 0.1
    print(f"locked +180ms: R {a['R']} mean {a['mean_phase_ms']} ms; unrelated: R {b['R']}; "
          f"search on a 129 BPM cut list -> {s['bpm']} BPM (R {s['R']})")
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid")
    ap.add_argument("--events", help="comma-separated seconds")
    ap.add_argument("--search", help="lo:hi BPM")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    g = json.load(open(a.grid, encoding="utf-8"))["grid"]
    times = [float(x) for x in a.events.split(",")]
    out = {"audio_grid": lock(times, g["period_s"], g["phase_s"])}
    if a.search:
        lo, hi = map(float, a.search.split(":"))
        out["best_own_grid"] = search(times, lo, hi)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
