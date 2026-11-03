"""声音标识 (sonic identity): a two-note motif, three candidates.

Each candidate is ONE two-note motif (short pickup -> long landing) in its own
timbre, rendered in two cuts that share the notes, the interval and the timbre:

* ``ident_<name>``        片头 / 落版: pickup + landing + bloom tail, ~2.4-2.8 s,
                          reference M-max -17 LUFS
* ``ident_<name>_trans``  转场签名: the same two notes tighter (90 ms apart) over a short
                          air swish, ~0.9 s, reference M-max -21 LUFS

Candidates (key D by default; ``pitch`` transposes):

* crystal 晶光  A5 -> E6, rising fifth (open, cool, "sus9" colour over D). Crystal FM
                pluck, bell layer on the landing, shimmer, sub. Cold-light family,
                closest to the approved "在我开口之前" palette.
* warm    暖光  A5 -> F#6, rising major sixth (sweet, friendly). Celesta + FM
                e-piano body, soft bell, plate.
* hop     小鹿跳 A5 -> D6, rising fourth with a pitch glide into the landing (the
                "leap"), wooden mallet + bubble pop, delay echo of the landing note.

Registered in the sfx registry (family='ident'); ``anchor='mark'`` = the landing
note, so ``align='anchor'`` puts the landing exactly on ``at``.
"""
import numpy as np

from . import instruments as ins
from .dsp import SR, TWOPI, smp, hz, midi, semis, noise, bpf, stereo, rc_ramp, add_at, att_curve as _att
from .sfx import SfxSpec, register, render_sfx, _space


def mallet(note, vel=1.0, dur=0.9, glide_from=None, glide_t=0.07, bright=0.5, seed=0):
    """wooden mallet (marimba-like): fundamental + 3.93x partial (fast decay) +
    9.2x partial (very fast), optional exponential pitch glide from glide_from."""
    f = hz(note)
    n = smp(dur)
    t = np.arange(n) / SR
    if glide_from is not None:
        ft = f * (hz(glide_from) / f) ** np.exp(-t / (glide_t / 3.0))
    else:
        ft = np.full(n, f)
    ph = TWOPI * np.cumsum(ft) / SR
    y = (np.sin(ph) * np.exp(-t / (0.28 * dur))
         + 0.35 * np.sin(3.93 * ph) * np.exp(-t / 0.05)
         + 0.08 * (0.5 + bright) * np.sin(9.2 * ph) * np.exp(-t / 0.015))
    y *= _att(t, 0.001)
    nn = smp(0.002)
    y[:nn] += 0.12 * bright * bpf(noise(nn, 900 + seed), 2000, 6000) * np.hanning(nn)
    y[-smp(0.01):] *= rc_ramp(smp(0.01))[::-1]
    return y * vel


class _Tl:
    def __init__(self, total):
        self.out = np.zeros((2, smp(total)))

    def add(self, sig, t, pan=0.0, gain=1.0):
        st = stereo(sig, pan) if sig.ndim == 1 else sig
        add_at(self.out, st * gain, smp(t))

    def done(self, space, ir, fade):
        y = _space(self.out, space, ir, tail=0.0)[:, : self.out.shape[1]]
        nf = smp(fade)
        y[:, -nf:] *= rc_ramp(nf)[::-1]
        return y


def _grains(tl, rng, t0, dur, root_midi, vel=0.05, rate=16.0):
    notes = [root_midi + o + 12 * k for k in (0, 1) for o in (0, 2, 4, 7, 9)]
    t = t0
    while True:
        t += float(rng.exponential(1.0 / (rate * np.exp(-(t - t0) / (0.5 * dur)) + 2.0)))
        if t >= t0 + dur:
            break
        g = ins.grain(hz(notes[int(rng.integers(len(notes)))]), float(rng.uniform(0.05, 0.15)),
                      vel * float(rng.uniform(0.5, 1.0)) * np.exp(-(t - t0) / (0.6 * dur)))
        tl.add(g, t, pan=float(rng.uniform(-0.8, 0.8)))


def _swish(tl, seed, p, bright, t0, dur=0.26, gain=0.18):
    sw = ins.whoosh(dur, 700 * semis(p), min(3400 * semis(p) * 2 ** (bright - 0.5), 12000), 'swell', q=1.2,
                    pan0=-0.6, pan1=0.6, seed=seed, peak=0.75, air=0.2 * bright)
    tl.add(sw * gain, t0)


# ----------------------------------------------------------------------------
# voices of each candidate (note 1 = pickup, note 2 = landing)
# ----------------------------------------------------------------------------
def _crystal_notes(tl, rng, seed, p, bright, T1, T2, long=True):
    b = 0.7 + 0.6 * bright
    tl.add(ins.crystal_pluck(midi('A5') + p, 0.62, 1.2, 2.0, b, seed=seed + 1, decay=0.3), T1, pan=-0.2)
    tl.add(ins.crystal_pluck(midi('E6') + p, 0.80, 2.0 if long else 1.0, 2.0, b, seed=seed + 2,
                             decay=0.6 if long else 0.35), T2, pan=0.15)
    tl.add(ins.bell(midi('E6') + p, 0.55 if long else 0.3, 2.4 if long else 1.0, index=1.4 + 1.6 * bright,
                    decay=0.5 if long else 0.25), T2)
    if long:
        tl.add(ins.sub_bass(midi('D2') + p, 0.5, 0.26, att=0.004, rel=0.6), T2)
        tl.add(ins.boom(62 * semis(p), 44 * semis(p), 0.8, 0.14, glide_tau=0.12, decay=0.22), T2)
        _grains(tl, rng, T2 + 0.03, 1.2, midi('D6') + p, vel=0.04 + 0.04 * bright)


def _warm_notes(tl, rng, seed, p, bright, T1, T2, long=True):
    tl.add(ins.celesta(midi('A5') + p, 0.55, 1.2, seed=seed + 1), T1, pan=-0.15)
    tl.add(ins.epiano(midi('A5') + p, 0.35, 0.12, seed=seed + 2), T1, pan=-0.15)
    tl.add(ins.celesta(midi('F#6') + p, 0.75, 2.2 if long else 1.0, seed=seed + 3), T2, pan=0.12)
    tl.add(ins.epiano(midi('F#5') + p, 0.40 + 0.1 * bright, 1.2 if long else 0.3, seed=seed + 4), T2, pan=0.0)
    if long:
        tl.add(ins.epiano(midi('D4') + p, 0.30, 1.4, seed=seed + 5), T2, pan=-0.1)
        tl.add(ins.bell(midi('F#6') + p, 0.15 + 0.1 * bright, 2.2, index=1.2, decay=0.45), T2 + 0.01, pan=0.2)
        tl.add(ins.sub_bass(midi('D2') + p, 0.9, 0.18, att=0.02, rel=0.7), T2)


def _hop_notes(tl, rng, seed, p, bright, T1, T2, long=True):
    tl.add(mallet(midi('A5') + p, 0.55, 0.3, glide_from=midi('F#5') + p, glide_t=0.04, bright=bright, seed=seed),
           T1, pan=-0.15)
    tl.add(mallet(midi('D6') + p, 1.0, 1.0 if long else 0.6, glide_from=midi('A5') + p, glide_t=0.06,
                  bright=bright, seed=seed + 1), T2, pan=0.05)
    pop = render_sfx('pop_soft', seed=seed, normalize=False, pitch=p + 5, bright=bright, dur=0.1)
    tl.add(pop * 0.2, T2 - 0.01)
    tl.add(ins.tock(520.0 * semis(p), 0.15, index=1.2, decay=0.012), T2)
    if long:
        for k, (dt, g, pan) in enumerate(((0.375, 0.30, 0.55), (0.75, 0.14, -0.55))):   # dotted-8th echoes
            tl.add(mallet(midi('D6') + p, g, 0.6, bright=bright * 0.7, seed=seed + 2 + k), T2 + dt, pan=pan)
        tl.add(ins.celesta(midi('D7') + p, 0.08 + 0.08 * bright, 1.2, seed=seed + 5), T2 + 0.02, pan=0.3)


_CANDS = {
    'crystal': dict(fn=_crystal_notes, gap=0.16, space=(0.35, 'hall'), total=2.8, title='晶光',
                    notes='A5 → E6 上行纯五度（开阔、冷静、科技感），crystal FM 拨弦 + 落点钟声 + 高音颗粒 + 次低频。'),
    'warm': dict(fn=_warm_notes, gap=0.18, space=(0.35, 'plate'), total=2.8, title='暖光',
                 notes='A5 → F#6 上行大六度（甜、友好、温暖），celesta + FM 电钢底 + 轻钟 + 板式混响。'),
    'hop': dict(fn=_hop_notes, gap=0.20, space=(0.25, 'plate'), total=2.4, title='小鹿跳',
                notes='A5 → D6 上行纯四度，滑音跳上落点（“起跳”），木槌 + 泡泡 pop + 附点八分回声。'),
}
INTRO_MARK = 0.45           # landing note in the intro cut
TRANS_MARK = 0.20           # landing note in the transition cut
TRANS_GAP = 0.09


def _make(name, trans):
    c = _CANDS[name]

    def fn(rng, seed, pitch=0.0, bright=0.5, space=None):
        sp = c['space'][0] if space is None else space
        if not trans:
            tl = _Tl(c['total'])
            T2 = INTRO_MARK
            c['fn'](tl, rng, seed, pitch, bright, T2 - c['gap'], T2, long=True)
            return tl.done(sp, c['space'][1], fade=0.5)
        tl = _Tl(0.95)
        T2 = TRANS_MARK
        _swish(tl, seed * 7 + 91, pitch, bright, T2 - 0.2)
        c['fn'](tl, rng, seed, pitch, bright, T2 - TRANS_GAP, T2, long=False)
        return tl.done(sp * 0.8, c['space'][1], fade=0.3)
    return fn


_P = {'pitch': (0.0, -7.0, 7.0, 'semitones (default key D)'), 'bright': (0.5, 0.0, 1.0, '0 dark .. 1 bright'),
      'space': (None, None, None, 'reverb amount 0..1 (default per candidate)')}

for _name, _c in _CANDS.items():
    register(SfxSpec(
        id='ident_' + _name, fn=_make(_name, False), family='ident', anchor='mark',
        mark_s=lambda prm: INTRO_MARK, ref=('mmax', -17.0), params=dict(_P),
        purpose='候选「%s」片头 / 落版标识音（两音动机完整版）' % _c['title'],
        sync='落点（第二个音）在 %.2f s：align=anchor 对准 Logo / 标题落定那一帧；第一个音提前 %.2f s' % (
            INTRO_MARK, _c['gap']),
        notes=_c['notes']))
    register(SfxSpec(
        id='ident_%s_trans' % _name, fn=_make(_name, True), family='ident', anchor='mark',
        mark_s=lambda prm: TRANS_MARK, ref=('mmax', -21.0), params=dict(_P),
        purpose='候选「%s」转场签名（同一两音动机缩短版）' % _c['title'],
        sync='落点在 %.2f s：align=anchor 对准剪辑点；两音间隔 %d ms，下方快 whoosh 掠过' % (
            TRANS_MARK, int(TRANS_GAP * 1000)),
        notes='同一两音动机，间隔收紧到 90 ms，尾巴缩到约 0.7 s，加快速空气声。'))


def list_idents():
    from .sfx import list_sfx
    return list_sfx('ident')
