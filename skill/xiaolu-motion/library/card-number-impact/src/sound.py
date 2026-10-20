"""card-number-impact sound: a ticking count that speeds into a riser, then a layered hit (boom,
sub drop, crack, crystal) exactly on the slam, and a hot ember tail. Beats come from timing()."""
import numpy as np

from xlaudio.dsp import SR, smp, noise, lp, hp, bpf


def cues(shot):
    T = shot['T']
    hit = T['hit']
    out = []
    n = len(T['ticks'])
    for i, t in enumerate(T['ticks']):                    # quieter and brighter as they blur together
        out.append({'id': 'tick', 'at': t, 'gain_db': -8 - 6 * (i / max(1, n - 1)), 'pan': 0.15 * np.sin(i * 1.7),
                    'params': {'pitch': 2 * (i / max(1, n - 1)) * 6, 'bright': 0.5 + 0.4 * i / max(1, n - 1)}})
    out += [
        {'id': 'riser', 'at': hit, 'align': 'end', 'gain_db': -9, 'params': {'dur': hit - T['count'] + 0.1, 'octaves': 1.2, 'bright': 0.6}},
        {'id': 'reverse_whoosh', 'at': hit, 'align': 'end', 'gain_db': -8, 'params': {'dur': 0.5, 'bright': 0.6}},
        {'id': 'impact_big', 'at': hit, 'gain_db': 0, 'params': {'bright': 0.7, 'tail': 0.6}},
        {'id': 'sub_drop', 'at': hit, 'gain_db': -3, 'params': {'bright': 0.7}},
        {'id': 'hit', 'at': hit, 'gain_db': -4},
        {'id': 'glitch', 'at': hit, 'gain_db': -14, 'params': {'dur': 0.12, 'density': 0.4}},
        {'id': 'shimmer', 'at': hit + 0.15, 'gain_db': -14, 'params': {'dur': 1.8, 'density': 0.3, 'root': 'D', 'bright': 0.4}},
        {'id': 'pop_soft', 'at': T['label'] + 0.05, 'gain_db': -9, 'params': {'pitch': -2}},
    ]
    return out


def bed(shot, dur):
    """low rumble that tightens during the count and a crackle tail after the hit"""
    n = smp(dur)
    t = np.arange(n) / SR
    T = shot['T']
    rum = lp(noise(n, 41), 120, 2) * (0.010 + 0.02 * np.clip((t - T['count']) / (T['hit'] - T['count']), 0, 1) ** 2 * (t < T['hit']))
    rng = np.random.default_rng(7)
    crk = np.zeros(n)
    for _ in range(90):                                   # embers crackling after the hit
        tt = T['hit'] + 0.1 + rng.exponential(0.6)
        i = smp(tt)
        if i + 200 < n:
            crk[i:i + 200] += rng.uniform(0.2, 1) * np.exp(-np.arange(200) / 25)
    crk = hp(crk * rng.standard_normal(n) * 0.6 + crk * 0.2, 2500, 2) * 0.02
    y = rum + crk
    return np.vstack([y, 0.96 * y])
