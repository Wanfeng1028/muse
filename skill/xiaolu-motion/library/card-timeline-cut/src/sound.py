"""card-timeline-cut sound: scrub, two scissor snips, the segment lifting away, the ripple slide and a
latch click, the length readout ticking down.

Registered at run time (the audio package is not modified): `scissor_snip` (two steel blades
closing: a rising scrape and the closing 'shk') and `latch_click` (a clasp / buckle snapping shut).
"""
import numpy as np

from xlaudio import sfx as S
from xlaudio.dsp import SR, smp, noise, bpf, lp, hp, svf, fade_edges, get_ir, convolve_st


def _snip(rng, seed, pitch=0.0, bright=0.5):
    n = smp(0.4)
    t = np.arange(n) / SR
    k = 2 ** (pitch / 12)
    close = 0.085                                        # blades meet here
    u = np.clip(t / close, 0, 1)
    fc = (2200 + 4200 * u ** 1.5) * k                    # scrape rises as the pivot closes
    scrape = svf(noise(n, seed + 1), fc, 5.0, 'bp') * (u ** 1.2) * (t < close)
    scrape += 0.4 * hp(noise(n, seed + 2), 5000, 2) * (u ** 2) * (t < close)
    tt = np.maximum(t - close, 0)
    on = t >= close
    shk = bpf(noise(n, seed + 3), 2500 * k, 11000) * np.exp(-tt / 0.004) * on
    ring = sum(a * np.sin(2 * np.pi * f * k * tt) * np.exp(-tt / d) for f, a, d in ((3150, 0.5, 0.03), (4870, 0.3, 0.02), (7400, 0.15, 0.012))) * on
    thud = np.sin(2 * np.pi * 260 * tt) * np.exp(-tt / 0.012) * on
    y = 0.55 * scrape + 1.0 * shk + 0.35 * ring + 0.25 * thud
    y = fade_edges(np.vstack([y, 0.95 * y]), 0.002, 0.01)
    return y + convolve_st(y * 0.08, get_ir('room'), n)


def _latch(rng, seed, pitch=0.0, bright=0.5):
    n = smp(0.35)
    t = np.arange(n) / SR
    k = 2 ** (pitch / 12)
    y = np.zeros(n)
    for j, (d, a) in enumerate(((0.0, 0.8), (0.018, 1.0))):     # engage + seat
        tt = np.maximum(t - d, 0)
        on = t >= d
        y += a * bpf(noise(n, seed + 5 + j), 1500 * k, 7500 * k) * np.exp(-tt / 0.0022) * on
        y += 0.5 * a * np.sin(2 * np.pi * (1850 + 400 * j) * k * tt) * np.exp(-tt / 0.009) * on
    tt = np.maximum(t - 0.018, 0)
    y += 0.7 * np.sin(2 * np.pi * 150 * tt * (1 + 0.3 * np.exp(-tt / 0.006))) * np.exp(-tt / 0.03) * (t >= 0.018)
    y = fade_edges(np.vstack([y, y]), 0.0005, 0.01)
    return y + convolve_st(y * 0.1, get_ir('room'), n)


def setup():
    if 'scissor_snip' in S.REGISTRY:
        return
    S.register(S.SfxSpec('scissor_snip', _snip, '剪刀剪断（刀刃合拢）', 'mark 0.085 s = 刀刃合拢 / 切开那一帧', 'mark', ('tp', -10.0),
                         {'pitch': (0.0, -12.0, 12.0, 'semitones'), 'bright': (0.5, 0.0, 1.0, '')}, mark_s=lambda p: 0.085))
    S.register(S.SfxSpec('latch_click', _latch, '卡扣扣上', 'mark 0.018 s = 扣到位', 'mark', ('tp', -11.0),
                         {'pitch': (0.0, -12.0, 12.0, 'semitones'), 'bright': (0.5, 0.0, 1.0, '')}, mark_s=lambda p: 0.018))


def cues(shot):
    T = shot['T']
    p = shot['params']
    out = [
        {'id': 'whoosh_slow', 'at': 0.15, 'align': 'start', 'gain_db': -20, 'params': {'dur': 0.9, 'pitch': -3, 'travel': 0.4}},
        {'id': 'scissor_snip', 'at': T['cut1'], 'align': 'anchor', 'gain_db': 0, 'pan': -0.2},
        {'id': 'tick', 'at': T['move'], 'gain_db': -6},
        {'id': 'whoosh_fast', 'at': T['move'], 'align': 'motion', 'gain_db': -18, 'params': {'dur': 0.3, 'travel': 0.5}},
        {'id': 'scissor_snip', 'at': T['cut2'], 'align': 'anchor', 'gain_db': 0, 'pan': 0.2, 'params': {'pitch': 1}},
        {'id': 'pop_soft', 'at': T['lift'] + 0.08, 'gain_db': -8, 'params': {'pitch': -4}},
        {'id': 'whoosh_mid', 'at': T['lift'] + 0.18, 'align': 'motion', 'gain_db': -13, 'params': {'dur': 0.45, 'pitch': -6, 'travel': 0.2}},
        {'id': 'whoosh_fast', 'at': T['slide'], 'align': 'motion', 'gain_db': -12, 'params': {'dur': 0.42, 'travel': -0.6, 'pitch': 2}},
        {'id': 'latch_click', 'at': T['latch'], 'align': 'anchor', 'gain_db': 0},
        {'id': 'impact_soft', 'at': T['latch'], 'gain_db': -14, 'params': {'pitch': -2, 'dur': 0.4, 'bright': 0.3}},
    ]
    n = int(p['removed'])
    for i in range(n):                                    # readout ticks, one per second removed
        out.append({'id': 'tick', 'at': T['roll'] + (T['rollEnd'] - T['roll']) * (i + 0.5) / n, 'gain_db': -9, 'params': {'pitch': 2 + i % 2}})
    out.append({'id': 'tock', 'at': T['rollEnd'] + 0.02, 'gain_db': -6})
    return out


def bed(shot, dur):
    """edit-bay room tone: low air, a faint machine hum"""
    n = smp(dur)
    t = np.arange(n) / SR
    y = lp(noise(n, 31), 250, 2) * 0.008 + 0.0015 * np.sin(2 * np.pi * 60 * t) + 0.0008 * np.sin(2 * np.pi * 120 * t)
    y *= np.clip(t / 0.3, 0, 1)
    return np.vstack([y, 0.97 * y])
