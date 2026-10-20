"""card-movable-type sound: metal sorts clinking into a steel rail, the quoin lock, a light sweep.

Two effects are synthesised here and registered into xlaudio at run time (the audio package itself
is not modified): `type_clink` (a small lead-alloy block landing on steel) and `type_lock` (the
quoin tightening the row). Everything else comes from the xlaudio catalogue.
"""
import numpy as np

import xlaudio as xa
from xlaudio import sfx as S
from xlaudio.dsp import SR, smp, noise, bpf, lp, hp, env_perc, pan_st, get_ir, convolve_st, fade_edges


def _modes(n, f0, ratios, decays, amps, t0=0.0):
    t = np.arange(n) / SR - t0
    on = t >= 0
    tt = np.maximum(t, 0)
    y = np.zeros(n)
    for r, d, a in zip(ratios, decays, amps):
        y += a * np.sin(2 * np.pi * f0 * r * tt) * np.exp(-tt / d)
    return y * on


def _clink(rng, seed, pitch=0.0, bright=0.5):
    """lead-alloy sort on a steel rail: free-bar modes (1, 2.76, 5.40, 8.93) + click + rail thunk + one rattle"""
    n = smp(0.5)
    f0 = 2350.0 * 2 ** (pitch / 12) * (1 + rng.uniform(-0.02, 0.02))
    ratios, decays = (1.0, 2.756, 5.404, 8.933), (0.085, 0.045, 0.022, 0.012)
    amps = (1.0, 0.55 * (0.6 + bright), 0.28 * (0.5 + bright), 0.12 * bright)
    y = _modes(n, f0, ratios, decays, amps)
    y += 0.35 * _modes(n, f0 * 1.07, ratios, [d * 0.6 for d in decays], amps, t0=rng.uniform(0.018, 0.028))   # rattle
    t = np.arange(n) / SR
    click = bpf(noise(n, seed + 11), 2500, 9500) * np.exp(-t / 0.0016)
    thunk = np.sin(2 * np.pi * 185 * t * (1 + 0.25 * np.exp(-t / 0.006))) * np.exp(-t / 0.022)
    y = 0.55 * y + 0.9 * click + 0.7 * thunk
    y = fade_edges(np.vstack([y, y]), 0.0002, 0.01)
    wet = convolve_st(y * 0.16, get_ir('room'), n)
    return y + wet


def _lock(rng, seed, pitch=0.0, bright=0.5):
    """quoin lock: a heavier, lower steel 'chunk' + ratchet double click + low body"""
    n = smp(0.9)
    t = np.arange(n) / SR
    f0 = 940.0 * 2 ** (pitch / 12)
    ring = _modes(n, f0, (1.0, 2.756, 5.404), (0.18, 0.08, 0.035), (1.0, 0.45, 0.2))
    body = np.sin(2 * np.pi * 96 * t * (1 + 0.4 * np.exp(-t / 0.01))) * np.exp(-t / 0.06)
    clicks = np.zeros(n)
    for k, t0 in enumerate((0.0, 0.034)):
        m = smp(0.006)
        s0 = smp(t0)
        clicks[s0:s0 + m] += bpf(noise(m, seed + 3 + k), 1800, 7000) * np.hanning(m) * (1.0 if k == 0 else 0.6)
    y = 0.45 * ring + 0.9 * body + 1.0 * clicks
    y = fade_edges(np.vstack([y, y]), 0.0002, 0.02)
    return y + convolve_st(y * 0.22, get_ir('plate'), n)


def setup():
    if 'type_clink' in S.REGISTRY:
        return
    S.register(S.SfxSpec('type_clink', _clink, '金属活字落进钢排字槽', '与活字落定同帧', 'start', ('tp', -11.0),
                         {'pitch': (0.0, -12.0, 12.0, 'semitones'), 'bright': (0.5, 0.0, 1.0, '')}, humanize_db=0.8))
    S.register(S.SfxSpec('type_lock', _lock, '锁版：楔子把整行活字挤紧', '与锁版同帧', 'start', ('tp', -9.0),
                         {'pitch': (0.0, -12.0, 12.0, 'semitones'), 'bright': (0.5, 0.0, 1.0, '')}))


def timing(p):
    n = len(p['text'])
    launch = [p['t0'] + i * p['stagger'] for i in range(n)]
    land = [a + p['rise'] + p['fall'] for a in launch]
    lock = land[-1] + p['lock_gap']
    return {'n': n, 'launch': launch, 'land': land, 'lock': lock, 'sweep': lock + 0.22, 'sub': lock + 0.55}


def cues(shot):
    T = shot.get('T') or timing(shot['params'])
    n = T['n']
    out = []
    for i in range(n):
        pan = (i - (n - 1) / 2) / max(1, n - 1) * 0.7
        out.append({'id': 'whoosh_fast', 'at': T['launch'][i] + 0.18, 'align': 'motion', 'gain_db': -15, 'pan': pan,
                    'params': {'dur': 0.34, 'pitch': -3 + 1.5 * (i % 3), 'bright': 0.35, 'travel': -0.2}})
        out.append({'id': 'type_clink', 'at': T['land'][i], 'gain_db': -1.5 if i < n - 1 else 0.0, 'pan': pan,
                    'params': {'pitch': [0, 2, -1, 3, 1, -2, 2][i % 7], 'bright': 0.55}})
    out += [
        {'id': 'type_lock', 'at': T['lock'], 'gain_db': 0.0},
        {'id': 'impact_soft', 'at': T['lock'], 'gain_db': -9.0, 'params': {'pitch': -5, 'bright': 0.3, 'dur': 0.5}},
        {'id': 'shimmer', 'at': T['sweep'], 'gain_db': -9.0, 'params': {'dur': 1.0, 'density': 0.35, 'bright': 0.55, 'root': 'D'}},
        {'id': 'pluck', 'at': T['sub'] + 0.05, 'gain_db': -13.0, 'params': {'note': 'A5', 'space': 0.45, 'bright': 0.4}},
    ]
    return out


def bed(shot, dur):
    """warm room tone + a low D drone that opens up at the lock (quiet: about -40 LUFS)"""
    n = smp(dur)
    t = np.arange(n) / SR
    T = shot.get('T') or timing(shot['params'])
    room = lp(noise(n, 77), 420, 2) + 0.25 * hp(lp(noise(n, 78), 6000, 2), 2500, 2)
    room *= 0.010 * np.clip(t / 0.4, 0, 1)
    drone = np.zeros(n)
    for f, a in ((73.42, 1.0), (110.0, 0.55), (146.83, 0.35), (220.0, 0.12)):
        drone += a * np.sin(2 * np.pi * f * t + 0.3 * np.sin(2 * np.pi * 0.21 * t))
    swell = 0.35 + 0.65 * np.clip((t - T['lock'] + 0.4) / 1.2, 0, 1)
    drone = lp(drone, 900, 2) * 0.0065 * swell * np.clip(t / 0.8, 0, 1) * np.clip((dur - t) / 0.3, 0, 1)
    y = np.vstack([room + drone, 0.97 * room + drone])
    return y
