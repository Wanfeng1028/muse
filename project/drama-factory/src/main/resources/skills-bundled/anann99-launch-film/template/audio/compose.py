#!/usr/bin/env python3
"""
Launch-film score: arranger + sound design + master + verification, driven by audio/score.json.

  .venv/bin/python audio/compose.py            # renders <project>/<score.json "out"> (default video/public/audio/score.wav)

score.json (see references/audio.md):
  duration, bpm, out, music (bool), lufs (-14), true_peak (-1),
  sections: [{start, end, energy: intro|groove|peak|breakdown|outro, chords: ["Am","F","C","G"]}]  (one chord per bar, cycling)
  silence:  [[a, b], ...]   true digital silence windows (e.g. the pre-drop breath)
  hits:     [{t, kind, note}]  kinds: tick soft-tick tick-rise type-hit swish whoosh click stamp thunk bell impact
                                       drop logo-sting riser-start snare-fill (+ structural: section pad-in pluck-in
                                       drums-out silence fade — no sound, documentation only)
  master_eq: optional list of {type: lowshelf|highshelf|peak|highpass, hz, db, q}
This is a strong STARTING POINT: the composer agent is expected to extend the arrangement for the film.
Every hit is placed sample-exactly; the report shows placement (always 0.00 ms) and detected-onset error.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
import pedalboard as pb  # noqa: E402
import pyloudnorm as pyln  # noqa: E402
import soundfile as sf  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from scipy import signal  # noqa: E402
from scipy.ndimage import maximum_filter1d, minimum_filter1d, uniform_filter1d  # noqa: E402

from synth import (F32, SR, bell, blip, clap, crash, db, edge, hat, heartbeat, hp, impact, keys,  # noqa: E402
                   kick, ladder, lp, mouse_click, n_, pan_st, pluck, reverse_cymbal, riser, shimmer,
                   sidechain_env, snare, stamp, sub_bass, supersaw, thunk, tick, whoosh)

CFG = json.load(open(os.path.join(HERE, 'score.json')))
DUR = float(CFG['duration'])
BPM = float(CFG.get('bpm', 120))
BEAT = 60.0 / BPM
BAR = 4 * BEAT
N = n_(DUR)
OUT = os.path.join(ROOT, CFG.get('out', 'video/public/audio/score.wav'))
VIZ = os.path.join(HERE, 'score_viz.png')
TARGET_LUFS = float(CFG.get('lufs', -14.0))
TP_MAX = float(CFG.get('true_peak', -1.0))
MUSIC = bool(CFG.get('music', True))
SECTIONS = CFG.get('sections', [])
SILENCE = [tuple(w) for w in CFG.get('silence', [])]
HITS = sorted(CFG.get('hits', []), key=lambda h: h['t'])
DEFAULT_EQ = [  # gentle low-mid warmth; re-tune per film with scripts/band-match.py against a pro-mixed reference
    {'type': 'highpass', 'hz': 28},
    {'type': 'lowshelf', 'hz': 320, 'db': 2.0, 'q': 0.7},
    {'type': 'peak', 'hz': 230, 'db': 3.0, 'q': 0.8},
]
EQ = CFG.get('master_eq', DEFAULT_EQ)
PLACED: list[tuple[float, str]] = []

# ------------------------------------------------------------------ harmony
NOTE = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7,
        'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
QUAL = {'': [0, 4, 7], 'm': [0, 3, 7], '7': [0, 4, 7, 10], 'maj7': [0, 4, 7, 11], 'm7': [0, 3, 7, 10],
        'm9': [0, 3, 7, 10, 14], '9': [0, 4, 7, 10, 14], 'maj9': [0, 4, 7, 11, 14], 'add9': [0, 4, 7, 14],
        'sus2': [0, 2, 7], 'sus4': [0, 5, 7], 'dim': [0, 3, 6], '6': [0, 4, 7, 9], 'm6': [0, 3, 7, 9]}


def chord(name: str):
    m = re.match(r'^([A-G][#b]?)(.*)$', name.strip())
    if not m or m.group(2) not in QUAL:
        raise ValueError(f'unknown chord {name!r}; qualities: {sorted(QUAL)}')
    pc = NOTE[m.group(1)]
    root = 52 + ((pc - 52) % 12)  # pad root in E3..D#4
    ivs = QUAL[m.group(2)]
    pad = [root + i for i in ivs[:4]]
    if len(pad) == 3:
        pad.append(root + 12)
    bass = 28 + ((pc - 28) % 12)  # E1..D#2
    arp = sorted(set(pad + [pad[1] + 12]))
    return {'pad': pad, 'bass': bass, 'arp': arp}


def bars_of(sec):
    t, k = sec['start'], 0
    while t < sec['end'] - 1e-9:
        yield t, min(BAR, sec['end'] - t), chord(sec['chords'][k % len(sec['chords'])])
        t += BAR
        k += 1


# ------------------------------------------------------------------ buses
class Bus:
    def __init__(self):
        self.x = np.zeros((N, 2), F32)

    def add(self, s: np.ndarray, at: float, gain: float = 1.0, pan: float = 0.0):
        if s.ndim == 1:
            s = pan_st(s, pan)
        i = int(round(at * SR))
        if i < 0:
            s, i = s[-i:], 0
        if i >= N:
            return
        j = min(N, i + len(s))
        self.x[i:j] += s[: j - i] * gain


BUSES = {k: Bus() for k in ('kick', 'drums', 'bass', 'pad', 'arp', 'bell', 'sfx', 'fx')}
KICKS: list[float] = []


def mark(t: float, what: str):
    PLACED.append((round(t, 4), what))


# ------------------------------------------------------------------ arrangement
def arrange():
    for si, sec in enumerate(SECTIONS):
        e = sec.get('energy', 'groove')
        for bi, (t0, blen, ch) in enumerate(bars_of(sec)):
            seed = int(t0 * 100) + si * 7
            # pad (every section)
            bright = {'intro': 0.25, 'groove': 0.5, 'peak': 0.7, 'breakdown': 0.4, 'outro': 0.55}.get(e, 0.5)
            p = supersaw(ch['pad'], blen + 1.0, seed=seed, attack=0.4 if e != 'intro' else 1.2, release=1.0)
            p = ladder(p, 500 + 3200 * bright, res=0.1, mode='lpf24')
            BUSES['pad'].add(p, t0, 0.42 if e != 'outro' else 0.5)
            if e == 'outro':
                for k, m in enumerate(ch['pad']):
                    BUSES['bell'].add(keys(m + 12, blen + 1.0, vel=0.6, seed=seed + k), t0 + 0.02 * k, 0.16, pan=-0.3 + 0.2 * k)
            if e == 'intro':
                BUSES['bass'].add(heartbeat(ch['bass'] + 12, 0.7, seed=seed), t0, 0.5)
            # drums
            if e in ('groove', 'peak'):
                for b in range(int(round(blen / BEAT))):
                    tb = t0 + b * BEAT
                    if tb >= sec['end'] - 1e-9:
                        break
                    BUSES['kick'].add(kick(seed=1), tb, 0.9)
                    KICKS.append(tb)
                    if b % 2 == 1:
                        BUSES['drums'].add(clap(seed=3), tb, 0.45)
                    BUSES['drums'].add(hat(seed=4 + b, open_=True), tb + BEAT / 2, 0.16, pan=0.2)
                    if e == 'peak':
                        for q in range(4):
                            BUSES['drums'].add(hat(seed=40 + b * 4 + q), tb + q * BEAT / 4, 0.10 if q % 2 else 0.14, pan=-0.25)
                # bass: 8ths on the root
                for q in range(int(round(blen / (BEAT / 2)))):
                    BUSES['bass'].add(sub_bass(ch['bass'], BEAT / 2 * 0.9), t0 + q * BEAT / 2, 0.55)
            # arp: 16ths (groove/peak/breakdown), 8ths in the intro's second half, bells in the outro
            if e in ('groove', 'peak', 'breakdown'):
                step = BEAT / 4
                for q in range(int(round(blen / step))):
                    m = ch['arp'][q % len(ch['arp'])] + (12 if e == 'peak' and q % 8 >= 4 else 0)
                    BUSES['arp'].add(pluck(m, 0.4, bright=0.35 + 0.3 * bright, seed=seed + q), t0 + q * step,
                                     0.13 if q % 4 else 0.18, pan=-0.35 + 0.7 * ((q % 4) / 3))
            elif e == 'intro' and t0 >= sec['start'] + (sec['end'] - sec['start']) / 2:
                for q in range(int(round(blen / (BEAT / 2)))):
                    BUSES['arp'].add(pluck(ch['arp'][q % len(ch['arp'])] - 12, 0.5, bright=0.25, seed=seed + q),
                                     t0 + q * BEAT / 2, 0.14)
            if e == 'peak' and bi % 2 == 0:
                BUSES['bell'].add(bell(ch['pad'][-1] + 12, 2.0, seed=seed), t0, 0.12, pan=0.3)
            if e == 'outro':
                for q, m in enumerate(ch['arp']):
                    BUSES['bell'].add(bell(m + 12, 2.0, ratio=2.0, seed=seed + q), t0 + q * BEAT / 2, 0.1, pan=-0.4 + 0.25 * q)


def chord_at(t: float):
    for sec in SECTIONS:
        if sec['start'] <= t < sec['end']:
            k = int((t - sec['start']) // BAR)
            return chord(sec['chords'][k % len(sec['chords'])])
    return chord(SECTIONS[-1]['chords'][-1]) if SECTIONS else chord('C')


def sound_design():
    sfx, fx = BUSES['sfx'], BUSES['fx']
    rise_n = 0
    for i, h in enumerate(HITS):
        t, k = float(h['t']), h['kind']
        s = 1000 + i
        if k == 'tick':
            sfx.add(tick(2600, seed=s), t, 0.35)
        elif k == 'soft-tick':
            sfx.add(tick(3300, 0.04, seed=s, tau=0.004, noise=0.6), t, 0.2)
        elif k == 'tick-rise':
            sfx.add(blip(84 + 2 * rise_n, 0.2, drop=0.0, seed=s), t, 0.22)
            rise_n += 1
        elif k == 'type-hit':
            sfx.add(blip(79, 0.25, seed=s), t, 0.3)
            sfx.add(tick(2200, seed=s + 1), t, 0.25)
        elif k in ('swish', 'whoosh'):
            w, pk = whoosh(rise=0.18 if k == 'swish' else 0.35, fall=0.2 if k == 'swish' else 0.3, seed=s)
            fx.add(w, t - pk, 0.3 if k == 'swish' else 0.42)
        elif k == 'click':
            sfx.add(mouse_click(seed=s), t, 0.55)
        elif k == 'stamp':
            sfx.add(stamp(seed=s), t, 0.45)
        elif k == 'thunk':
            sfx.add(thunk(98, seed=s), t, 0.5)
        elif k == 'bell':
            for j, m in enumerate(chord_at(t)['pad'][-3:]):
                BUSES['bell'].add(bell(m + 12, 3.0, seed=s + j), t, 0.2, pan=(-0.3, 0.3, 0.0)[j])
        elif k == 'impact':
            fx.add(impact(seed=s, dur=2.5, size=0.8), t, 0.55)
            BUSES['bell'].add(bell(chord_at(t)['pad'][-1] + 12, 2.5, seed=s), t, 0.18)
        elif k == 'drop':
            fx.add(impact(seed=s, dur=3.0, size=1.0), t, 0.75)
            fx.add(crash(seed=s), t, 0.35)
            rc = reverse_cymbal(0.9, seed=s)
            fx.add(rc, t - len(rc) / SR, 0.28)
            for j, m in enumerate(chord_at(t)['pad']):
                BUSES['bell'].add(bell(m + 12, 3.5, seed=s + j), t, 0.16)
        elif k == 'logo-sting':
            notes = [m + 12 for m in chord_at(t)['pad']]
            BUSES['bell'].add(shimmer(notes, 4.0, seed=s), t, 0.35)
            for j, m in enumerate(notes):
                BUSES['bell'].add(bell(m, 4.0, ratio=2.0, seed=s + j), t, 0.18, pan=-0.3 + 0.2 * j)
            fx.add(impact(seed=s, dur=3.5, size=0.7, crack=0.2), t, 0.45)
        elif k == 'riser-start':
            nxt = next((float(x['t']) for x in HITS[i + 1:] if x['kind'] in ('drop', 'silence')), t + 2 * BEAT * 2)
            dur = max(0.5, nxt - t)
            r = riser(dur, seed=s)
            fx.add(edge(r, 0.01, 0.03), t, 0.35)
        elif k == 'snare-fill':
            steps = int(round(BAR / (BEAT / 4)))
            for q in range(steps):
                BUSES['drums'].add(snare(seed=s + q), t + q * BEAT / 4, 0.12 + 0.3 * q / steps)
        else:
            continue  # structural kinds: documentation only
        mark(t, k)


# ------------------------------------------------------------------ mix + master
def to_pb(x):
    return np.ascontiguousarray(x.T.astype(F32))


def from_pb(y):
    return np.ascontiguousarray(y.T.astype(F32))


def reverb(x, size=0.85):
    return from_pb(pb.Reverb(room_size=size, damping=0.5, wet_level=1.0, dry_level=0.0, width=1.0)(to_pb(lp(hp(x, 250), 8500)), SR))


def mix():
    duck = sidechain_env(N, KICKS, depth=0.55, release=0.22)[:, None] if KICKS else 1.0
    b = {k: v.x.copy() for k, v in BUSES.items()}
    for k in ('pad', 'arp', 'bell', 'sfx', 'fx', 'drums'):
        b[k] = hp(b[k], 120 if k != 'drums' else 90)
    b['pad'] = b['pad'] * duck
    b['bass'] = lp(b['bass'], 900) * duck
    b['arp'] = b['arp'] * (0.6 + 0.4 * duck if KICKS else 1.0)
    send = b['pad'] * 0.35 + b['arp'] * 0.25 + b['bell'] * 0.5 + b['drums'] * 0.12 + b['sfx'] * 0.12
    out = sum(b.values()) + reverb(send) * 0.35
    if not MUSIC:  # sfx-only mode (to layer over a licensed track)
        out = b['sfx'] + b['fx'] + reverb(b['sfx'] * 0.2) * 0.3
    return out.astype(F32)


def true_peak_db(x):
    return db(float(np.max(np.abs(signal.resample_poly(x.astype(np.float64), 4, 1, axis=0)))))


def limiter(x, ceiling_db=-1.3, lookahead=0.004, release=0.09):
    c = 10 ** (ceiling_db / 20)
    pk = np.max(np.abs(x), axis=1)
    g_req = np.minimum(1.0, c / np.maximum(pk, 1e-12))
    L = max(2, n_(lookahead))
    g_min = minimum_filter1d(g_req, size=2 * L + 1, mode='nearest')
    g_box = uniform_filter1d(g_min, size=L + 1, mode='nearest')
    blk = 32
    nb = -(-len(x) // blk)
    gb = np.pad(g_min, (0, nb * blk - len(x)), mode='edge').reshape(nb, blk).min(1)
    a = np.exp(-blk / (release * SR))
    out, g = np.empty(nb), 1.0
    for i in range(nb):
        v = gb[i]
        g = v if v < g else v - (v - g) * a
        out[i] = g
    gain = np.minimum(uniform_filter1d(np.repeat(out, blk)[:len(x)], size=L, mode='nearest'), g_box)
    return (x * gain[:, None]).astype(F32)


def eq_chain():
    fx = []
    for e in EQ:
        t = e['type']
        if t == 'highpass':
            fx.append(pb.HighpassFilter(cutoff_frequency_hz=e['hz']))
        elif t == 'lowshelf':
            fx.append(pb.LowShelfFilter(cutoff_frequency_hz=e['hz'], gain_db=e['db'], q=e.get('q', 0.7)))
        elif t == 'highshelf':
            fx.append(pb.HighShelfFilter(cutoff_frequency_hz=e['hz'], gain_db=e['db'], q=e.get('q', 0.7)))
        elif t == 'peak':
            fx.append(pb.PeakFilter(cutoff_frequency_hz=e['hz'], gain_db=e['db'], q=e.get('q', 1.0)))
    return pb.Pedalboard(fx)


def master(x):
    m = (x[:, 0] + x[:, 1]) / 2
    s = hp((x[:, 0] - x[:, 1]) / 2, 140, 2)
    x = np.stack([m + s, m - s], 1).astype(F32)
    x = from_pb(eq_chain()(to_pb(x), SR))
    meter = pyln.Meter(SR)
    x = x * 10 ** ((-20.0 - meter.integrated_loudness(x)) / 20)
    x = from_pb(pb.Compressor(threshold_db=-15.0, ratio=1.6, attack_ms=30.0, release_ms=200.0)(to_pb(x), SR))
    gate = np.ones(N, F32)
    for a, b in SILENCE:  # true digital silence (a drop's reverse cymbal may 'inhale' into b)
        inhale = 0.14 if any(h['kind'] == 'drop' and abs(float(h['t']) - b) < 1e-6 for h in HITS) else 0.0
        gate[n_(a):n_(b - inhale)] = 0.0
    fade0 = n_(DUR - 0.5)
    gate[fade0:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, N - fade0))).astype(F32)
    g_db, ceiling = 0.0, -1.3
    for _ in range(12):
        y = limiter(x * 10 ** (g_db / 20), ceiling) * gate[:, None]
        L, tp = meter.integrated_loudness(y), true_peak_db(y)
        if tp > TP_MAX - 0.05:
            ceiling -= tp - (TP_MAX - 0.1)
        if abs(L - TARGET_LUFS) < 0.05 and tp <= TP_MAX - 0.05:
            break
        g_db += TARGET_LUFS - L
    return y.astype(F32)


# ------------------------------------------------------------------ verification + viz
def onsets(x, win=512, hop=96, lag=3):
    mono = x.mean(1).astype(np.float64)
    pad = np.concatenate([np.zeros(win), mono, np.zeros(win)])
    S = np.abs(np.fft.rfft(np.lib.stride_tricks.sliding_window_view(pad, win)[::hop] * np.hanning(win), axis=1))
    S = np.log1p(100 * S / (S.max() + 1e-12))
    ref = maximum_filter1d(S, size=3, axis=1)
    flux = np.zeros(len(S))
    flux[lag:] = np.maximum(0.0, S[lag:] - ref[:-lag]).sum(1)
    times = (np.arange(len(S)) * hop + win / 2 - win) / SR
    w = max(1, int(0.03 * SR / hop))
    peaks = np.where((flux == maximum_filter1d(flux, size=2 * w + 1)) &
                     (flux > (uniform_filter1d(flux, size=int(0.25 * SR / hop)) + 0.02 * flux.max()) * 1.3))[0]
    return times[peaks]


def verify(y):
    meter = pyln.Meter(SR)
    print(f'file: {OUT}\n  {len(y)} samples = {len(y) / SR:.6f} s (target {DUR} s)')
    print(f'  integrated loudness {meter.integrated_loudness(y):.2f} LUFS (target {TARGET_LUFS}) | '
          f'sample peak {db(float(np.max(np.abs(y)))):.2f} dBFS | true peak {true_peak_db(y):.2f} dBTP (max {TP_MAX})')
    for sec in SECTIONS:
        a, b = sec['start'], sec['end']
        if b - a >= 0.5:
            print(f'  section {a:g}-{b:g} [{sec.get("energy")}]: {meter.integrated_loudness(y[n_(a):n_(b)]):.1f} LUFS')
    pk = onsets(y)
    ok = 0
    for t, k in sorted(PLACED):
        err = (pk[np.argmin(np.abs(pk - t))] - t) * 1000 if len(pk) else float('nan')
        flag = 'OK ' if abs(err) <= 10 else 'masked?'
        ok += abs(err) <= 10
        print(f'  {t:7.3f} {k:12s} placed +0.00 ms | detected {err:+6.1f} ms  {flag}')
    print(f'=> {ok}/{len(PLACED)} hits detected within ±10 ms (placement is exact; "masked?" = soft hit inside a dense mix)')


def viz(y, path):
    W, H = 2400, 900
    img = Image.new('RGB', (W, H), (14, 15, 12))
    d = ImageDraw.Draw(img)
    mono = y.mean(1)
    cols = np.array_split(np.abs(mono), W - 100)
    for i, c in enumerate(cols):  # waveform
        v = float(c.max()) if len(c) else 0
        d.line([(50 + i, 160 - v * 110), (50 + i, 160 + v * 110)], fill=(150, 184, 116))
    f, t, Z = signal.stft(mono, SR, nperseg=2048, noverlap=1536)
    Z = 20 * np.log10(np.abs(Z) + 1e-9)
    fb = np.geomspace(30, 16000, 300)
    idx = np.clip(np.searchsorted(f, fb), 0, len(f) - 1)
    spec = Z[idx][::-1]
    spec = np.clip((spec - (spec.max() - 80)) / 80, 0, 1)
    rgb = (np.stack([spec ** 0.7 * 255, spec ** 1.6 * 200, (1 - spec) * spec * 255], -1)).astype(np.uint8)
    img.paste(Image.fromarray(rgb).resize((W - 100, 500)), (50, 320))
    for sec in SECTIONS:
        x = 50 + sec['start'] / DUR * (W - 100)
        d.line([(x, 290), (x, 820)], fill=(221, 229, 182))
        d.text((x + 4, 295), f"{sec['start']:g}s {sec.get('energy', '')}", fill=(221, 229, 182))
    for tt, k in PLACED:
        x = 50 + tt / DUR * (W - 100)
        d.line([(x, 300), (x, 318)], fill=(199, 43, 125))
    d.text((50, 20), f'score: {DUR}s @ {BPM:g} BPM  (waveform / log-frequency spectrogram 30 Hz-16 kHz / section + hit markers)', fill=(253, 254, 251))
    img.save(path)
    print(f'viz: {path}')


def main():
    if MUSIC:
        arrange()
    sound_design()
    y = master(mix())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    sf.write(OUT, y, SR, subtype='PCM_24')
    verify(y)
    viz(y, VIZ)


if __name__ == '__main__':
    main()
