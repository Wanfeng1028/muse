#!/usr/bin/env python3
"""
Compare the tonal balance of a score against a professionally mixed reference, per octave band,
and suggest master-EQ moves (for audio/score.json "master_eq" or compose.py's master chain).

  band-match.py reference.wav score.wav [--ref-range 20 100] [--ours-range 12 52]

Both files are reduced to mono; each band's energy is expressed relative to the file's total energy (dB),
so overall loudness differences don't matter. Aim for every band within about ±4 dB in the groove sections.
Typical finding for synthesized scores: +6..+10 dB too much 1–10 kHz, −4..−8 dB too little 80–320 Hz.
"""
import argparse
import json

import numpy as np
import soundfile as sf

EDGES = [20, 40, 80, 160, 320, 640, 1280, 2560, 5120, 10240, 20000]


def bands(path, rng):
    x, sr = sf.read(path, always_2d=True)
    x = x.mean(1)
    if rng:
        x = x[int(rng[0] * sr):int(rng[1] * sr)]
    n = 8192
    win = np.hanning(n)
    acc, k = np.zeros(n // 2 + 1), 0
    for i in range(0, max(1, len(x) - n), n // 2):
        seg = x[i:i + n]
        if len(seg) < n:
            break
        acc += np.abs(np.fft.rfft(seg * win)) ** 2
        k += 1
    if k == 0:
        raise SystemExit(f'{path}: range too short')
    f = np.fft.rfftfreq(n, 1 / sr)
    e = np.array([acc[(f >= a) & (f < b)].sum() for a, b in zip(EDGES[:-1], EDGES[1:])])
    return 10 * np.log10(e / e.sum() + 1e-20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('reference')
    ap.add_argument('ours')
    ap.add_argument('--ref-range', nargs=2, type=float)
    ap.add_argument('--ours-range', nargs=2, type=float)
    a = ap.parse_args()
    r, o = bands(a.reference, a.ref_range), bands(a.ours, a.ours_range)
    d = o - r
    print(f"{'band (Hz)':>14} {'ref dB':>8} {'ours dB':>8} {'diff':>7}")
    for i in range(len(r)):
        flag = '  <-- ' + ('too much' if d[i] > 0 else 'too little') if abs(d[i]) > 4 else ''
        print(f'{EDGES[i]:>6}-{EDGES[i + 1]:<7} {r[i]:8.1f} {o[i]:8.1f} {d[i]:+7.1f}{flag}')
    # suggestions: one corrective move per region whose average deviation exceeds 2 dB (both directions)
    regions = [  # (band indices, filter, centre Hz, q)
        ((0, 1), 'lowshelf', 60, 0.7),     # sub 20-80 Hz
        ((2, 3), 'peak', 230, 0.8),        # low-mids 80-320 Hz (warmth / body)
        ((4, 5), 'peak', 700, 0.9),        # mids 320-1280 Hz (boxiness)
        ((6, 7), 'highshelf', 1600, 0.6),  # presence 1.3-5 kHz (harshness)
        ((8, 9), 'highshelf', 7000, 0.7),  # air 5-20 kHz
    ]
    sug = []
    for idx, kind, hz, q in regions:
        dev = float(np.mean([d[i] for i in idx]))
        if abs(dev) > 2:
            sug.append({'type': kind, 'hz': hz, 'db': round(float(np.clip(-0.7 * dev, -6, 6)), 1), 'q': q})
    print('\nsuggested master_eq moves (add to the chain, re-render, re-run until every band is within ±4 dB):')
    print(json.dumps(sug) if sug else 'balance already within tolerance')


if __name__ == '__main__':
    main()
