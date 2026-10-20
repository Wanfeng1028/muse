"""Fast self-checks (python3 -m pytest tests -q). No listening involved: these
check determinism, levels, sample-accurate placement, grid maths and the
mixer's loudness / true-peak / ducking behaviour on synthetic signals."""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xlaudio as xa  # noqa: E402
from xlaudio import meter  # noqa: E402
from xlaudio.dsp import SR, smp  # noqa: E402

ALL = xa.list_sfx()


@pytest.mark.parametrize('sid', ALL)
def test_sfx_renders_clean_and_deterministic(sid):
    y = xa.render_sfx(sid, seed=3)
    assert y.ndim == 2 and y.shape[0] == 2 and y.shape[1] > smp(0.005)
    assert np.isfinite(y).all()
    assert np.max(np.abs(y[:, 0])) < 1e-6 and np.max(np.abs(y[:, -1])) < 1e-6
    assert np.array_equal(y, xa.render_sfx(sid, seed=3))
    spec = xa.get_spec(sid)
    kind, target = spec.ref
    lvl = meter.true_peak_db(y) if kind == 'tp' else meter.max_momentary(y)
    tol = spec.humanize_db + 0.15
    assert abs(lvl - target) <= tol, (sid, lvl, target)
    assert np.max(np.abs(np.mean(y, axis=1))) < 1e-3


def test_required_catalogue_present():
    need = {'whoosh_fast', 'whoosh_mid', 'whoosh_slow', 'reverse_whoosh', 'tick', 'tock', 'ui_click', 'typing_key',
            'pop_soft', 'pluck', 'bell', 'impact_soft', 'impact_big', 'riser', 'sub_drop', 'glitch', 'stamp', 'shimmer',
            'enter', 'land', 'push', 'reveal', 'hit'}
    assert need <= set(ALL)
    assert len(xa.list_sfx('ident')) == 6


def test_params_validation():
    with pytest.raises(TypeError):
        xa.render_sfx('tick', pitchh=2)
    with pytest.warns(UserWarning):
        xa.render_sfx('tick', bright=3.0)
    a = xa.render_sfx('whoosh_mid', pitch=-5, seed=1)
    b = xa.render_sfx('whoosh_mid', pitch=5, seed=1)
    assert a.shape == b.shape and not np.allclose(a, b)


def test_cues_placement_is_sample_accurate():
    cues = [dict(id='land', at=1.0), dict(id='riser', at=4.0, align='end', params=dict(dur=1.0)),
            dict(id='enter', at=6.0, align='motion'), dict(id='reveal', at=8.0, align='anchor')]
    y, log = xa.render_cues(cues, 10.0, return_log=True)
    assert y.shape == (2, smp(10.0))
    nz = np.nonzero(np.any(y != 0, axis=0))[0]
    assert abs(nz[0] - smp(1.0)) <= 1
    riser = [c for c in log if c['id'] == 'riser'][0]
    assert abs(riser['start_s'] + riser['len_s'] - 4.0) < 1.0 / SR + 1e-9
    enter = [c for c in log if c['id'] == 'enter'][0]
    assert abs((6.0 - enter['start_s']) * 30.0 - 3.5) < 0.05
    reveal = [c for c in log if c['id'] == 'reveal'][0]
    assert abs(reveal['start_s'] - (8.0 - 0.35)) < 1.0 / SR + 1e-9


def test_cues_storyboard_compat(tmp_path):
    p = tmp_path / 'sb.json'
    p.write_text(json.dumps({'sfx': [{'kind': 'whoosh_fast', 't': 0.5, 'dur': 0.3, 'pan': [-0.5, 0.5], 'gain_db': -3},
                                     {'id': 'tick', 'frame': 45, 'fps': 30}]}))
    y, log = xa.render_cues(str(p), 3.0, return_log=True)
    assert log[0]['params']['travel'] == 0.5 and log[0]['params']['dur'] == 0.3
    assert abs(log[1]['at'] - 1.5) < 1e-9
    # default seed is derived from (id, at): inserting another cue does not change this one
    y2, log2 = xa.render_cues([{'id': 'pop_soft', 'at': 0.1}] + json.loads(p.read_text())['sfx'], 3.0,
                              return_log=True)
    assert log2[1]['seed'] == log[0]['seed']


def test_grid():
    g = xa.BeatGrid(120, 4, fps=30)
    assert g.bar_time(2) == 4.0 and g.bbt(3, 1) == 4.0 and g.beat_time(3) == 1.5
    assert g.bar_beat(5.25) == (2, 2.5)
    assert g.snap(1.1) == 1.0 and g.snap(1.1, division=4) == 2.0 and g.snap(0.9, division=4) == 0.0
    assert g.frame(g.beat_time(7)) == 7 * 15 and g.frame_error_ms() == 0.0
    assert any(abs(x['bpm'] - 100.0) < 1e-9 for x in xa.frame_locked_bpms(30))
    assert xa.BeatGrid(96, fps=30).frame_error_ms() > 1.0


def test_jianying_beat_loader(tmp_path):
    p = tmp_path / 'x.beat'
    p.write_text(json.dumps({'time': [100, 580, 1050, 1510, 1990], 'value': [1, 2, 3, 4, 1], 'energy': [0] * 5}))
    bm = xa.load_jianying_beat(str(p))
    assert bm.downbeats(0, 3) == [0.1, 1.99]
    assert abs(bm.tempo() - 60 / 0.47) < 2


def _speechlike(dur=8.0, seed=0):
    """glottal pulse train through 3 formant resonators, syllable envelope with pauses."""
    from scipy import signal
    rng = np.random.default_rng(seed)
    n = smp(dur)
    t = np.arange(n) / SR
    f0 = 120 * (1 + 0.08 * np.sin(2 * np.pi * 0.7 * t))
    ph = np.cumsum(f0) / SR
    src = (np.diff(np.floor(ph), prepend=0) > 0).astype(float)
    y = np.zeros(n)
    for fc, bw in ((700, 90), (1200, 120), (2600, 180)):
        b, a = signal.iirpeak(fc, fc / bw, fs=SR)
        y += signal.lfilter(b, a, src)
    env = np.zeros(n)
    tt = 0.3
    while tt < dur - 0.5:
        d = rng.uniform(0.15, 0.35)
        s0, s1 = smp(tt), smp(tt + d)
        env[s0:s1] = np.hanning(s1 - s0)
        tt += d + (rng.uniform(0.6, 1.0) if rng.random() < 0.2 else 0.02)
    y = y * env + 1e-4 * rng.standard_normal(n)
    return np.vstack([y, y]) * 0.05


def test_mix_with_voice_levels_and_ducking():
    v = _speechlike()
    rng = np.random.default_rng(1)
    bgm = np.vstack([np.convolve(rng.standard_normal(v.shape[1] + 2000), np.ones(8) / 8, 'same')[:v.shape[1]]
                     for _ in range(2)]) * 0.3
    sfx = xa.render_cues([{'id': 'hit', 'at': 2.0}, {'id': 'enter', 'at': 5.0, 'align': 'motion'}], v.shape[1] / SR)
    rep = xa.mix_with_voice(v, bgm, sfx, None, duck_db=-8.0)
    o = rep['output']
    assert abs(o['own_I_LUFS'] + 14.0) < 0.1
    assert o['own_TP_dBTP'] <= -1.0
    d = rep['ducking']
    assert 0.2 < d['ducked_time_frac'] < 1.0
    assert d['voice_minus_bgm_in_speech_LU'] > 10.0
    assert rep['master']['limiter_gr_db_max'] < 6.0


def test_score_loop_is_seamless():
    from xlaudio.score import render_score
    r = render_score('coldlight_ambient', duration=16.0, energy=0.7, loop=True, seed=1)
    y = r.audio
    assert y.shape[1] == smp(16.0)
    step_seam = np.max(np.abs(y[:, 0] - y[:, -1]))
    typical = np.percentile(np.abs(np.diff(y, axis=1)), 99.9)
    assert step_seam < typical
    assert abs(meter.integrated(y) + 14.0) < 0.2 and meter.true_peak_db(y) <= -1.0
