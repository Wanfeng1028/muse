"""card-frame-tunnel sound: a low swell under the push, one air rush per frame passing the lens,
a warm landing and a gold shimmer as the title appears. Beats come from the page's timing()."""
import numpy as np

from xlaudio.dsp import SR, smp, noise, lp, hp


def cues(shot):
    T = shot['T']
    out = [
        {'id': 'riser', 'at': T['arrive'], 'align': 'end', 'gain_db': -12, 'params': {'dur': T['arrive'] - T['push'] + 0.1, 'octaves': 0.7, 'bright': 0.35, 'pitch': -5}},
        {'id': 'whoosh_slow', 'at': T['push'] + 0.1, 'gain_db': -14, 'params': {'dur': 1.6, 'pitch': -6, 'travel': 0.0}},
    ]
    for i, tp in enumerate(T['passes']):
        out.append({'id': 'whoosh_fast', 'at': tp, 'align': 'peak', 'gain_db': -9 - 2 * (i % 2),
                    'pan': [(-0.5 if i % 2 else 0.5), (0.5 if i % 2 else -0.5)], 'params': {'dur': 0.34, 'pitch': -4 + (i % 3), 'bright': 0.4}})
    out += [
        {'id': 'impact_soft', 'at': T['arrive'], 'gain_db': -6, 'params': {'pitch': -3, 'bright': 0.35, 'dur': 0.8}},
        {'id': 'bell', 'at': T['arrive'] + 0.02, 'gain_db': -10, 'params': {'note': 'D5', 'space': 0.5, 'bright': 0.4, 'dur': 3.0}},
        {'id': 'shimmer', 'at': T['title'], 'gain_db': -10, 'params': {'dur': 1.2, 'density': 0.45, 'root': 'D', 'bright': 0.5}},
    ]
    return out


def bed(shot, dur):
    """velvet room: a low D/A drone that swells with the push and settles on arrival"""
    n = smp(dur)
    t = np.arange(n) / SR
    T = shot['T']
    sw = np.clip((t - T['push']) / (T['arrive'] - T['push']), 0, 1)
    amp = 0.004 + 0.007 * np.sin(np.pi * np.clip(sw * 1.05, 0, 1)) ** 1.5 + 0.004 * (t > T['arrive'])
    d = sum(a * np.sin(2 * np.pi * f * t + 0.4 * np.sin(2 * np.pi * 0.17 * t + f)) for f, a in ((73.42, 1.0), (110.0, 0.6), (146.83, 0.3), (220.0, 0.15)))
    y = lp(d, 700, 2) * amp * np.clip(t / 0.5, 0, 1) * np.clip((dur - t) / 0.3, 0, 1)
    air = hp(lp(noise(n, 12), 3000, 2), 200, 2) * 0.004 * np.clip(t / 0.5, 0, 1)
    return np.vstack([y + air, y + 0.95 * air])
