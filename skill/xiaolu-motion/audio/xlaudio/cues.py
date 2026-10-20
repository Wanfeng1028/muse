"""Cue sheet rendering: ``render_cues(cues, duration, sr=48000) -> (2, n)``.

A cue is a dict compatible with the storyboard JSON ``sfx`` field::

    {"id": "whoosh_mid", "at": 3.20, "gain_db": -2, "pan": 0.3,
     "params": {"pitch": 2, "bright": 0.7}, "seed": 4, "align": "start"}

* ``id``      sfx / ident id (alias ``kind``)
* ``at``      seconds on the video timeline (alias ``t``); ``frame`` + ``fps`` also accepted
* ``gain_db`` relative to the class reference level (default 0)
* ``pan``     -1..1 constant-power balance applied to the rendered stereo effect
* ``params``  effect parameters (pitch / bright / dur / ...); a top-level ``dur`` is moved here
* ``seed``    optional; default is derived from (id, at) so inserting cues never changes others
* ``align``   'start' (default: the sound starts at ``at``), 'end' (sound ends at ``at``),
              'peak' (loudest 10 ms at ``at``), 'anchor' (the effect's own sync point:
              whoosh peak, riser / reverse_whoosh end, ident main hit, else start),
              'motion' (``at`` = frame where the visual action starts; the sound starts the
              class's lead_frames earlier, e.g. whoosh-type enter/push 3-4 frames, impacts 0)
* ``fps``     frame rate for ``frame`` and align='motion' (default 30)
"""
import json
import zlib

import numpy as np
from scipy import signal

from .dsp import SR, smp, pan_st, add_at
from .sfx import render_sfx, get_spec, anchor_offset
from . import ident, motion  # noqa: F401  (register the ident + motion families)

_SKIP = {'id', 'kind', 'at', 't', 'frame', 'fps', 'gain_db', 'pan', 'params', 'seed', 'align', 'note', 'comment',
         'label', 'name'}


def load_cues(src):
    """list of cues | {"sfx": [...]} | path to such a JSON file -> list of cues."""
    if isinstance(src, (str, bytes)) or hasattr(src, '__fspath__'):
        with open(src, encoding='utf-8') as f:
            src = json.load(f)
    if isinstance(src, dict):
        src = src.get('sfx', src.get('cues', []))
    return list(src)


def _norm_cue(c, fps_default=30.0):
    sid = c.get('id', c.get('kind'))
    if sid is None:
        raise ValueError('cue without id: %r' % (c,))
    if 'at' in c:
        at = float(c['at'])
    elif 't' in c:
        at = float(c['t'])
    elif 'frame' in c:
        at = float(c['frame']) / float(c.get('fps', fps_default))
    else:
        raise ValueError('cue without at/t/frame: %r' % (c,))
    params = dict(c.get('params') or {})
    if 'dur' in c and 'dur' not in params:
        params['dur'] = c['dur']
    pan = c.get('pan', 0.0)
    if isinstance(pan, (list, tuple)):            # [from, to] -> whoosh travel
        spec = get_spec(sid)
        if 'travel' in spec.params and 'travel' not in params:
            params['travel'] = float(pan[1] - pan[0]) / 2.0
        pan = float(pan[0] + pan[1]) / 2.0
    seed = c.get('seed')
    if seed is None:
        seed = zlib.crc32(('%s|%d' % (sid, smp(at))).encode()) & 0x7FFFFFFF
    return dict(id=sid, at=at, gain_db=float(c.get('gain_db', 0.0)), pan=float(pan), params=params,
                seed=int(seed), align=c.get('align', 'start'), fps=float(c.get('fps', fps_default)))


def render_cues(cues, duration, sr=SR, out_path=None, bits='float', return_log=False):
    """Render a cue list to a stereo effects track of exactly round(duration*sr)
    samples. Cues outside the timeline are truncated (logged)."""
    cues = load_cues(cues)
    N = smp(duration)
    out = np.zeros((2, N))
    log = []
    for c in cues:
        q = _norm_cue(c)
        y = render_sfx(q['id'], seed=q['seed'], gain_db=q['gain_db'], **q['params'])
        y = pan_st(y, q['pan'])
        a = q['align']
        if a == 'start':
            off = 0
        elif a == 'end':
            off = y.shape[1]
        elif a == 'peak':
            off = anchor_offset(q['id'], y, mode='peak', **q['params'])
        elif a == 'anchor':
            off = anchor_offset(q['id'], y, **q['params'])
        elif a == 'motion':                   # at = frame the visual action starts; apply the class lead
            off = smp(get_spec(q['id']).lead_frames / q['fps'])
        else:
            raise ValueError('align must be start/end/peak/anchor/motion, got %r' % a)
        start = smp(q['at']) - off
        add_at(out, y, start)
        log.append(dict(id=q['id'], at=q['at'], align=a, start_s=start / SR, sync_sample=smp(q['at']),
                        len_s=y.shape[1] / SR, seed=q['seed'], gain_db=q['gain_db'], pan=q['pan'],
                        params=q['params'], truncated=bool(start < 0 or start + y.shape[1] > N)))
    if sr != SR:
        g = np.gcd(int(sr), SR)
        out = signal.resample_poly(out, int(sr) // g, SR // g, axis=-1)
    if out_path:
        from .wavio import write_wav
        write_wav(out_path, out, bits=bits, sr=int(sr))
    return (out, log) if return_log else out
