"""card-hanzi-proof sound: rain of type on paper that slows to a hush, brush on xuan paper, a seal.

Registered at run time (the audio package is not modified): `pen_scratch` (a brush / pen stroke on
paper, length = the stroke's duration). The rain bed follows the same rain clock as the picture
(fast ticks -> near silence while the proofreader works -> a light drizzle).
"""
import numpy as np

from xlaudio import sfx as S
from xlaudio.dsp import SR, smp, noise, bpf, lp, hp, fade_edges, get_ir, convolve_st


def _scratch(rng, seed, pitch=0.0, bright=0.5, dur=0.3):
    """brush on paper: band noise with fibre grain (AM 40-90 Hz), pressure envelope over the stroke"""
    n = smp(dur + 0.08)
    t = np.arange(n) / SR
    k = 2 ** (pitch / 12)
    base = bpf(noise(n, seed + 1), 900 * k, 5200 * k * (0.7 + 0.6 * bright))
    grain = np.zeros(n)
    pos = 0
    while pos < n:                                   # fibre grain: short random bursts
        L = int(SR / rng.uniform(40, 95))
        grain[pos:pos + L] = rng.uniform(0.35, 1.0)
        pos += L
    grain = lp(grain, 260, 1)
    u = np.clip(t / dur, 0, 1)
    press = np.sin(np.pi * u) ** 0.6 * (t < dur) + (t >= dur) * np.exp(-(t - dur) / 0.012)
    press *= np.clip(t / 0.006, 0, 1)
    y = base * grain * press
    y += 0.25 * hp(noise(n, seed + 2), 6000, 2) * press * bright
    y = fade_edges(np.vstack([y, 0.94 * y]), 0.001, 0.01)
    return y + convolve_st(y * 0.08, get_ir('room'), n)


def setup():
    if 'pen_scratch' in S.REGISTRY:
        return
    S.register(S.SfxSpec('pen_scratch', _scratch, '毛笔 / 钢笔在纸上划过', '与笔画开始同帧，dur = 笔画时长', 'start', ('mmax', -27.0),
                         {'pitch': (0.0, -12.0, 12.0, 'semitones'), 'bright': (0.5, 0.0, 1.0, ''), 'dur': (0.3, 0.05, 1.5, 's')}))


def timing(p):
    s = p['t_settle']
    return {'settle': s, 'circle': s + 0.2, 'strike': s + 0.62, 'write': s + 0.86, 'drop': s + 1.3, 'fly': s + 1.42,
            'land': s + 1.95, 'seal': s + 2.3, 'resume': s + 2.1}


def _speed(p, t):
    """same rain clock as the picture: 1 -> 0.06 around settle, drifting back to 0.3 after resume"""
    T = timing(p)

    def seg(x, a, b):
        return np.clip((x - a) / (b - a), 0, 1)

    def cio(x):
        return np.where(x < 0.5, 4 * x ** 3, 1 - (-2 * x + 2) ** 3 / 2)
    slow = cio(seg(t, T['settle'] - 0.55, T['settle'] + 0.1))
    back = 0.5 - 0.5 * np.cos(np.pi * seg(t, T['resume'], T['resume'] + 1.2))
    return (1 - slow) * 1 + slow * 0.06 + (0.3 - 0.06) * back


def cues(shot):
    T = shot.get('T') or timing(shot['params'])
    return [
        {'id': 'reverse_whoosh', 'at': T['settle'], 'align': 'end', 'gain_db': -12, 'params': {'dur': 0.9, 'bright': 0.35}},
        {'id': 'impact_soft', 'at': T['settle'], 'gain_db': -14, 'params': {'pitch': -3, 'bright': 0.25, 'dur': 0.5}},
        {'id': 'pen_scratch', 'at': T['circle'], 'gain_db': 0, 'pan': 0.05, 'params': {'dur': 0.38, 'bright': 0.55}},
        {'id': 'pen_scratch', 'at': T['strike'], 'gain_db': 1, 'pan': 0.05, 'params': {'dur': 0.16, 'bright': 0.75, 'pitch': 2}},
        {'id': 'pen_scratch', 'at': T['write'] - 0.12, 'gain_db': -4, 'pan': 0.2, 'params': {'dur': 0.22, 'bright': 0.4, 'pitch': -1}},
        {'id': 'pen_scratch', 'at': T['write'], 'gain_db': -1, 'pan': 0.3, 'params': {'dur': 0.4, 'bright': 0.5, 'pitch': 1}},
        {'id': 'whoosh_mid', 'at': T['drop'], 'align': 'motion', 'gain_db': -13, 'pan': 0.1, 'params': {'pitch': -5, 'travel': 0.3, 'dur': 0.5}},
        {'id': 'enter', 'at': T['fly'], 'align': 'motion', 'gain_db': -7, 'pan': 0.2, 'params': {'dur': 0.55, 'travel': -0.3, 'bright': 0.45}},
        {'id': 'land', 'at': T['land'], 'gain_db': -4},
        {'id': 'pluck', 'at': T['land'] + 0.02, 'gain_db': -11, 'params': {'note': 'D6', 'space': 0.35, 'bright': 0.45}},
        {'id': 'pen_scratch', 'at': T['land'] + 0.12, 'gain_db': -3, 'pan': 0.15, 'params': {'dur': 0.18, 'bright': 0.6, 'pitch': 3}},
        {'id': 'stamp', 'at': T['seal'], 'gain_db': -1, 'pan': 0.25},
    ]


def bed(shot, dur):
    """type rain on paper: ticks whose rate and level follow the rain clock, plus a soft paper hiss"""
    p = shot['params']
    n = smp(dur)
    t = np.arange(n) / SR
    sp = _speed(p, t)
    rng = np.random.default_rng(2024)
    y = np.zeros((2, n))
    tick_n = smp(0.006)
    tt = np.arange(tick_n) / SR
    env = np.exp(-tt / 0.0012)
    k = 0.0
    while k < dur:
        rate = 55 * float(np.interp(k, t[::480], sp[::480])) + 1.5
        k += rng.exponential(1 / rate)
        i = smp(k)
        if i + tick_n >= n:
            break
        c = bpf(rng.standard_normal(tick_n), 1800 + 5000 * rng.random(), 9000) * env * rng.uniform(0.2, 1.0) ** 2
        pan = rng.uniform(-0.8, 0.8)
        y[0, i:i + tick_n] += c * (1 - pan) * 0.5
        y[1, i:i + tick_n] += c * (1 + pan) * 0.5
    y *= 0.05
    hiss = lp(hp(noise(n, 99), 600, 2), 5200, 2) * 0.004 * (0.25 + 0.75 * sp)
    y += np.vstack([hiss, 0.95 * hiss])
    y *= np.clip(t / 0.3, 0, 1)
    return y
