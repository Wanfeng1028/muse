"""card-flow-nodes sound: a pentatonic blip as each node lights, a thin zip as each link draws,
packet chatter while data streams stage by stage, a riser into the result node and a clear
completion (bell + shimmer). Beats come from the page's timing()."""
import numpy as np

from xlaudio.dsp import SR, smp, noise, bpf, lp, hp

PENTA = [0, 2, 4, 7, 9, 12, 14, 16]


def cues(shot):
    T = shot['T']
    out = []
    for i, tb in enumerate(T['blips']):
        out.append({'id': 'blip', 'at': tb, 'gain_db': -5, 'pan': 0.4 * np.sin(i * 2.1), 'params': {'pitch': PENTA[i % len(PENTA)] - 5}})
    for k, L in enumerate(T['link']):
        out.append({'id': 'laser_zip', 'at': L['t0'], 'gain_db': -17, 'pan': 0.3 * (1 if k % 2 else -1), 'params': {'dur': max(0.05, min(0.25, L['t1'] - L['t0'])), 'pitch': -7}})
    for L in range(T['maxL']):                          # one soft push per stage of data
        out.append({'id': 'whoosh_fast', 'at': T['flow0'] + L * T['stage'], 'gain_db': -18, 'params': {'dur': 0.4, 'pitch': 4 + 2 * L, 'bright': 0.7, 'travel': 0.0}})
        out.append({'id': 'pop_soft', 'at': T['flow0'] + (L + 1) * T['stage'] - 0.03, 'gain_db': -12, 'params': {'pitch': 2 * L}})
    done = T['done']
    out += [
        {'id': 'riser', 'at': done, 'align': 'end', 'gain_db': -13, 'params': {'dur': 0.9, 'octaves': 1.0, 'bright': 0.5}},
        {'id': 'impact_soft', 'at': done, 'gain_db': -12, 'params': {'pitch': -5, 'bright': 0.35, 'dur': 0.6}},
        {'id': 'bell', 'at': done + 0.01, 'gain_db': -8, 'params': {'note': 'D6', 'space': 0.45, 'bright': 0.5, 'dur': 3.0}},
        {'id': 'shimmer', 'at': done, 'gain_db': -11, 'params': {'dur': 1.4, 'density': 0.5, 'root': 'D', 'bright': 0.6}},
    ]
    return out


def bed(shot, dur):
    """packet chatter: short high grains while data is moving, over a faint cold air"""
    T = shot['T']
    n = smp(dur)
    t = np.arange(n) / SR
    rng = np.random.default_rng(3)
    y = np.zeros((2, n))
    g = smp(0.004)
    e = np.hanning(g)
    a0, a1 = T['flow0'], T['flow0'] + T['maxL'] * T['stage']
    tt = a0
    while tt < a1:
        tt += rng.exponential(1 / 70)
        i = smp(tt)
        if i + g >= n:
            break
        f = rng.uniform(3500, 8500)
        c = np.sin(2 * np.pi * f * np.arange(g) / SR) * e * rng.uniform(0.3, 1.0)
        pan = rng.uniform(-0.7, 0.7)
        y[0, i:i + g] += c * (1 - pan) * 0.5
        y[1, i:i + g] += c * (1 + pan) * 0.5
    y *= 0.02
    air = hp(lp(noise(n, 17), 2500, 2), 300, 2) * 0.0025 * np.clip(t / 0.4, 0, 1)
    return y + np.vstack([air, 0.96 * air])
