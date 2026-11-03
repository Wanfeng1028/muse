"""fusion-hand-throw sound: under the real voice, each word pops out of the hand, is thrown (whoosh
scaled by how hard the hand flicked) and slaps onto the wall. Beats come from the page's timing(),
which reads them off the Vision hand track. Registered at run time: `tag_stick` (a paper tag
slapped onto a wall)."""
import numpy as np

from xlaudio import sfx as S
from xlaudio.dsp import SR, smp, noise, bpf, lp, fade_edges, get_ir, convolve_st


def _stick(rng, seed, pitch=0.0, bright=0.5):
    n = smp(0.3)
    t = np.arange(n) / SR
    k = 2 ** (pitch / 12)
    slap = bpf(noise(n, seed + 1), 350 * k, 2600 * k * (0.7 + 0.6 * bright)) * np.exp(-t / 0.012)
    body = np.sin(2 * np.pi * 180 * k * t) * np.exp(-t / 0.02)
    tape = bpf(noise(n, seed + 2), 3000, 9000) * np.exp(-np.maximum(t - 0.015, 0) / 0.01) * (t > 0.015) * 0.25
    y = 1.0 * slap + 0.4 * body + tape
    y = fade_edges(np.vstack([y, y]), 0.0005, 0.01)
    return y + convolve_st(y * 0.12, get_ir('room'), n)


def setup():
    if 'tag_stick' not in S.REGISTRY:
        S.register(S.SfxSpec('tag_stick', _stick, '纸签贴到墙上', '与贴住同帧', 'start', ('tp', -14.0),
                             {'pitch': (0.0, -12.0, 12.0, 'semitones'), 'bright': (0.5, 0.0, 1.0, '')}))


def cues(shot):
    T = shot['T']
    out = []
    top = max(T['speeds']) or 1
    for k, (ta, tr, tl, spd) in enumerate(zip(T['appear'], T['releases'], T['land'], T['speeds'])):
        hard = max(0.0, spd / top)
        out += [
            {'id': 'pop_soft', 'at': ta + 0.1, 'gain_db': -9, 'pan': 0.5, 'params': {'pitch': [0, 2, 4, 7][k % 4]}},
            {'id': 'whoosh_fast', 'at': tr, 'align': 'motion', 'gain_db': -14 + 6 * hard, 'pan': [0.5, 0.75],
             'params': {'dur': 0.42, 'pitch': 2 + 2 * hard, 'bright': 0.5 + 0.3 * hard, 'travel': 0.3}},
            {'id': 'tag_stick', 'at': tl, 'gain_db': -4 + 3 * hard, 'pan': 0.7, 'params': {'pitch': [0, -2, 1, -1][k % 4]}},
        ]
    return out
