"""card-prompt-box sound: keys, Enter, three generation blips, three flights, soft drops into a
cardboard box, one beat of near-silence, the lid shutting, a check.

Registered at run time (the audio package is not modified): `box_drop` (a light piece landing in a
box) and `box_close` (a lid shutting with trapped air). Beats come from the page's timing().
"""
import numpy as np

from xlaudio import sfx as S
from xlaudio.dsp import SR, smp, noise, bpf, lp, hp, fade_edges, get_ir, convolve_st


def _drop(rng, seed, pitch=0.0, bright=0.5):
    n = smp(0.35)
    t = np.arange(n) / SR
    k = 2 ** (pitch / 12)
    body = np.sin(2 * np.pi * 150 * k * t * (1 + 0.3 * np.exp(-t / 0.008))) * np.exp(-t / 0.035)
    tap = bpf(noise(n, seed + 1), 500 * k, 3500 * k * (0.7 + 0.6 * bright)) * np.exp(-t / 0.006)
    rustle = bpf(noise(n, seed + 2), 2000, 8000) * np.exp(-np.maximum(t - 0.01, 0) / 0.03) * (t > 0.008) * 0.25
    y = 0.8 * body + 0.9 * tap + rustle
    y = fade_edges(np.vstack([y, y]), 0.0003, 0.01)
    return y + convolve_st(y * 0.1, get_ir('room'), n)


def _close(rng, seed, pitch=0.0, bright=0.5):
    n = smp(1.0)
    t = np.arange(n) / SR
    pre = smp(0.12)                                   # trapped air rushing out just before contact
    y = np.zeros(n)
    air = lp(noise(n, seed + 3), 900, 2)
    env = np.zeros(n)
    env[:pre] = np.linspace(0, 1, pre) ** 2.5
    y += 0.5 * air * env
    tt = np.maximum(t - pre / SR, 0)
    on = t >= pre / SR
    body = np.sin(2 * np.pi * 82 * tt * (1 + 0.5 * np.exp(-tt / 0.01))) * np.exp(-tt / 0.07) * on
    pap = bpf(noise(n, seed + 4), 280, 1600) * np.exp(-tt / 0.018) * on
    y += 1.0 * body + 0.8 * pap
    for k, d in enumerate((0.045, 0.07, 0.11)):      # the pieces inside settle
        m = t >= pre / SR + d
        y += 0.12 * bpf(noise(n, seed + 10 + k), 1500, 6000) * np.exp(-np.maximum(t - pre / SR - d, 0) / 0.004) * m
    y = fade_edges(np.vstack([y, y]), 0.001, 0.02)
    return y + convolve_st(y * 0.14, get_ir('room'), n)


def setup():
    if 'box_drop' in S.REGISTRY:
        return
    S.register(S.SfxSpec('box_drop', _drop, '轻物落进纸盒', '与落入同帧', 'start', ('tp', -15.0),
                         {'pitch': (0.0, -12.0, 12.0, 'semitones'), 'bright': (0.5, 0.0, 1.0, '')}))
    S.register(S.SfxSpec('box_close', _close, '纸盒合盖（带挤出的空气）', 'mark 0.12 s = 盖子碰上盒口', 'mark', ('tp', -10.0),
                         {'pitch': (0.0, -12.0, 12.0, 'semitones'), 'bright': (0.5, 0.0, 1.0, '')}, mark_s=lambda p: 0.12))


def cues(shot):
    T = shot['T']
    out = []
    for i, t in enumerate(T['keys']):
        out.append({'id': 'typing_key', 'at': t, 'gain_db': -2, 'pan': 0.1 * np.sin(i), 'params': {'pitch': ((i * 5) % 3) - 1}})
    out += [
        {'id': 'typing_key', 'at': T['enter'], 'gain_db': 1, 'params': {'heavy': 1}},
        {'id': 'ui_click', 'at': T['enter'] + 0.01, 'gain_db': -4, 'pan': 0.35},
        {'id': 'shimmer', 'at': T['gen'][0], 'gain_db': -13, 'params': {'dur': 0.7, 'density': 0.4, 'root': 'D'}},
    ]
    for k in range(3):
        out.append({'id': 'blip', 'at': T['gen'][k], 'gain_db': -6, 'pan': (k - 1) * 0.5, 'params': {'pitch': [0, 4, 7][k]}})
        out.append({'id': 'whoosh_mid', 'at': T['launch'][k], 'align': 'motion', 'gain_db': -11, 'pan': [(k - 1) * 0.6, 0],
                    'params': {'dur': 0.75, 'pitch': [-2, 0, 2][k], 'bright': 0.45}})
        out.append({'id': 'box_drop', 'at': T['land'][k], 'gain_db': -1 - k, 'pan': (k - 1) * 0.25, 'params': {'pitch': [0, 2, -1][k]}})
    out += [
        {'id': 'reverse_whoosh', 'at': T['closed'], 'align': 'end', 'gain_db': -16, 'params': {'dur': 0.45, 'bright': 0.3}},
        {'id': 'box_close', 'at': T['closed'], 'align': 'anchor', 'gain_db': 0},
        {'id': 'pop_soft', 'at': T['check'] + 0.1, 'gain_db': -5, 'params': {'pitch': 3}},
        {'id': 'pluck', 'at': T['check'] + 0.24, 'gain_db': -12, 'params': {'note': 'A5', 'space': 0.35}},
    ]
    return out


def bed(shot, dur):
    """a quiet daylight room: low air + a very soft high hiss"""
    n = smp(dur)
    t = np.arange(n) / SR
    y = lp(noise(n, 5), 300, 2) * 0.006 + hp(lp(noise(n, 6), 7000, 2), 3000, 2) * 0.0012
    y *= np.clip(t / 0.3, 0, 1)
    return np.vstack([y, 0.96 * y])
