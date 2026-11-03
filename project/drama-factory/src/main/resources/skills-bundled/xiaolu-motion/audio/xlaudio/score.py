"""Parametric music bed ("配乐预设").

    res = render_score('coldlight_ambient', duration=30, bpm=120, key='D minor',
                       energy=[(0, 0.3), (8, 0.6), (16, 0.9), (24, 0.4)],
                       sections={'drums_in': 8, 'drop': 16, 'breakdown': 24},
                       loop=False, seed=0)
    res.audio   # (2, n) float64, 48 kHz, mastered (default -14 LUFS, <= -1.3 dBTP)
    res.meta    # bpm, key, bar grid (time / sample / frame / chord / state), snapped sections, loop points

Inputs
* duration  seconds (exact output length; loop=True rounds to whole progression cycles)
* bpm, key  tempo and key ("D minor", "F# major", "Bb", "Am" ...); defaults per preset
* energy    breakpoints [(t, 0..1)], a constant, or None (preset default). Energy drives
            layer density (arp 8ths -> 16ths, bass pulses, hats 16ths, claps), filter
            brightness, width and velocities.
* sections  {'drums_in': t, 'build': t, 'drop': t, 'breakdown': t} in seconds (snapped to the
            nearest bar line) or 'bar:N' (0-based). Without markers, drums follow energy >= 0.55.
            A drop without an explicit build gets a 2-bar riser + snare roll into it.
* loop      True -> seamless loop: whole cycles, a pre-roll cycle is rendered and discarded so
            reverb / delay / pad tails wrap around, pad notes re-attack at the cycle start, all
            randomness is keyed by the bar inside the cycle, mastering sees a post-roll bar.

Only one preset ships ("coldlight_ambient", 冷光氛围电子: the pad / crystal-pluck / sub /
soft-drum palette of "在我开口之前"). Presets are plain dicts in PRESETS; BGM for regular
videos comes from the Jianying library (see README), this bed is for own-IP pieces.
"""
import re
import zlib
from dataclasses import dataclass

import numpy as np

from . import instruments as ins
from . import meter
from .dsp import (SR, smp, hz, rc_ramp, stereo, add_at, apply_eq, db2lin, hp, lp, get_ir,
                  convolve_st, pingpong, compressor, softclip_os, limiter, mono_lows, noise)
from .grid import BeatGrid

# -----------------------------------------------------------------------------
# harmony
# -----------------------------------------------------------------------------
_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
QUAL = {'maj': [0, 4, 7], 'm': [0, 3, 7], 'm(add9)': [0, 3, 7, 14], 'add9': [0, 4, 7, 14],
        'maj7': [0, 4, 7, 11], 'maj9': [0, 4, 7, 11, 14], 'm7': [0, 3, 7, 10], 'm9': [0, 3, 7, 10, 14],
        'sus2': [0, 2, 7], 'sus4': [0, 5, 7], '7sus4': [0, 5, 7, 10], '6/9': [0, 4, 7, 9, 14]}


def parse_key(key):
    """'D minor' / 'Dm' / 'F# major' / 'Bb' -> (tonic pitch class, 'minor'|'major')."""
    s = key.strip()
    m = re.match(r'^([A-Ga-g])([#b]?)\s*(.*)$', s)
    if not m:
        raise ValueError('bad key %r' % key)
    pc = (_PC[m.group(1).upper()] + (1 if m.group(2) == '#' else -1 if m.group(2) == 'b' else 0)) % 12
    rest = m.group(3).lower()
    mode = 'minor' if rest in ('m', 'min', 'minor', 'aeolian') else 'major'
    return pc, mode


def _voice(root_pc, ivs, prev_upper, lo=52, hi=76, bass_lo=43):
    """root in [bass_lo, bass_lo+11] + upper chord tones voice-led inside [lo, hi]."""
    root = bass_lo + (root_pc - bass_lo) % 12
    pcs = sorted({(root_pc + i) % 12 for i in ivs if i % 12 != 0} | ({(root_pc + 14) % 12} if 14 in ivs else set()))
    center = [62.0] if not prev_upper else prev_upper
    upper = []
    for pc in pcs:
        cands = [m for m in range(lo, hi + 1) if m % 12 == pc]
        best = min(cands, key=lambda m: min(abs(m - c) for c in center) + 0.01 * abs(m - 64))
        while best in upper:
            best += 12
        upper.append(best)
    return root, sorted(upper)


# -----------------------------------------------------------------------------
# presets
# -----------------------------------------------------------------------------
PRESETS = {
    'coldlight_ambient': dict(
        title='冷光氛围电子 cold-light ambient electronic',
        bpm=120, key='D minor', beats_per_bar=4,
        prog={'minor': [(0, 'm(add9)', 2), (8, 'maj9', 2), (5, 'm9', 2), (7, 'sus4', 2)],
              'major': [(0, 'add9', 2), (9, 'm9', 2), (5, 'maj9', 2), (7, 'sus4', 2)]},
        final={'minor': (0, 'm(add9)'), 'major': (0, 'maj9')},
        energy=0.4,
        # bus loudness when active, LU relative to the pad (auto fader calibration)
        balance=dict(pad=0.0, arp=-2.0, bass=-2.5, kick=-0.5, hats=-12.0, perc=-8.0, shimmer=-11.0, fx=-3.0,
                     bell=-5.0),
        sidechain_db=dict(pad=-4.0, bass=-6.0, arp=-2.0, shimmer=-2.0),
        sends=dict(pad=(0.20, 0.0, 0.0), arp=(0.30, 0.0, 0.26), shimmer=(0.60, 0.0, 0.10), bell=(0.42, 0.0, 0.12),
                   fx=(0.25, 0.05, 0.0), perc=(0.05, 0.22, 0.0), hats=(0.05, 0.2, 0.0), bass=(0, 0, 0),
                   kick=(0, 0, 0)),
        eq=dict(pad=[('hp', 45), ('peak', 2800.0, 0.7, 1.0)], arp=[('hp', 170), ('lp', 12000), ('peak', 2800.0, 0.7, 1.0)],
                bell=[('hp', 140), ('lp', 14000)], shimmer=[('hp', 650), ('lp', 12000)], bass=[('lp', 260)],
                perc=[('hp', 110)], hats=[('hp', 110)], fx=[('hp', 28)]),
        pad_cutoff=(650.0, 3400.0), pad_blend=(0.30, 0.62),
    ),
}


# -----------------------------------------------------------------------------
# result
# -----------------------------------------------------------------------------
@dataclass
class ScoreResult:
    audio: np.ndarray
    meta: dict
    sr: int = SR

    def save(self, wav_path, bits=24):
        import json
        from .wavio import write_wav
        write_wav(wav_path, self.audio, bits=bits)
        with open(wav_path.rsplit('.', 1)[0] + '.json', 'w', encoding='utf-8') as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=1)
        return wav_path

    def cut(self, bar_from, bar_to, fade_ms=10.0):
        """trim to [bar_from, bar_to) on exact bar lines (0-based), short fades."""
        bars = self.meta['bars']
        a = bars[bar_from]['sample']
        b = bars[bar_to]['sample'] if bar_to < len(bars) else self.audio.shape[1]
        y = self.audio[:, a:b].copy()
        nf = smp(fade_ms / 1000.0)
        y[:, :nf] *= rc_ramp(nf)
        y[:, -nf:] *= rc_ramp(nf)[::-1]
        return y


# -----------------------------------------------------------------------------
# rendering
# -----------------------------------------------------------------------------
def _energy_fn(energy, default, period=None):
    if energy is None:
        energy = default
    if np.isscalar(energy):
        v = float(energy)
        return lambda t: np.full(np.shape(t), v) if np.ndim(t) else v
    if callable(energy):
        f = energy
    else:
        pts = sorted((float(a), float(b)) for a, b in energy)
        xs = np.array([p[0] for p in pts])
        ys = np.clip(np.array([p[1] for p in pts]), 0, 1)
        f = lambda t: np.interp(t, xs, ys)  # noqa: E731
    if period:
        return lambda t: f(np.mod(t, period))
    return f


def _marker_bar(v, grid):
    if isinstance(v, str) and v.startswith('bar:'):
        return int(v[4:])
    return int(round((float(v) - grid.offset) / grid.bar_s))


def _rng(*key):
    return np.random.default_rng(zlib.crc32('|'.join(str(k) for k in key).encode()))


class _Bus:
    def __init__(self, n):
        self.y = np.zeros((2, n))

    def add(self, sig, t, pan=0.0, gain=1.0):
        st = stereo(sig, pan) if sig.ndim == 1 else sig
        k = min(12, st.shape[1])
        st = st.copy()
        st[:, :k] *= rc_ramp(k)
        add_at(self.y, st * gain, smp(t))


def render_score(preset='coldlight_ambient', duration=30.0, bpm=None, key=None, energy=None, sections=None,
                 loop=False, seed=0, target_lufs=-14.0, ceiling_db=-1.3, offset=0.0, fps=30.0, ring=2.4):
    P = PRESETS[preset]
    bpm = float(bpm or P['bpm'])
    tonic, mode = parse_key(key or P['key'])
    bpb = P['beats_per_bar']
    grid = BeatGrid(bpm, bpb, offset, fps)
    prog = P['prog'][mode]
    cyc = sum(b for _, _, b in prog)
    chord_of_bar = []
    for i, (ofs, q, nb) in enumerate(prog):
        chord_of_bar += [i] * nb
    bar_s = grid.bar_s

    if loop:
        n_cyc = max(1, int(round((duration - offset) / (cyc * bar_s))))
        loop_bars = n_cyc * cyc
        L = loop_bars * bar_s
        first_bar, last_bar = -cyc, loop_bars           # render [-cyc, loop_bars] (+1 post bar)
        pre_s = cyc * bar_s
        total = pre_s + L + bar_s + 5.0
        efn = _energy_fn(energy, P['energy'], period=L)
        n_music = loop_bars
    else:
        n_music = max(1, int(np.floor((duration - offset - ring) / bar_s)))
        first_bar, last_bar = 0, n_music - 1
        pre_s = offset
        total = duration
        efn = _energy_fn(energy, P['energy'])
        L = duration
    N = smp(total)

    def T(b, beat=0.0):                     # bar (+beat) -> seconds in the render buffer
        return (pre_s if loop else offset) + (b * bpb + beat) * grid.beat_s

    marks = {k: _marker_bar(v, grid) for k, v in (sections or {}).items()}
    if 'drop' in marks and 'build' not in marks:
        marks['build'] = max(0, marks['drop'] - 2)

    # ---- per-bar plan --------------------------------------------------------
    plan = []
    drums_state = False
    for b in range(first_bar, last_bar + 1):
        bk = b % cyc if loop else b                    # key for randomness / periodicity
        bl = b % n_music if loop else b                 # bar inside the loop for markers / energy
        e = float(efn((bl + 0.5) * bar_s))
        if marks:
            if bl == marks.get('drums_in', -1) or bl == marks.get('drop', -1):
                drums_state = True
            if bl == marks.get('breakdown', -1):
                drums_state = False
            if loop and bl == 0:
                drums_state = any(marks.get(k, 10 ** 9) <= 0 for k in ('drums_in', 'drop')) and \
                    not marks.get('breakdown', 10 ** 9) <= 0
            drums = drums_state or ('drums_in' not in marks and 'drop' not in marks and e >= 0.55)
        else:
            drums = e >= 0.55
        building = 'drop' in marks and marks['build'] <= bl < marks['drop']
        plan.append(dict(b=b, bk=bk, bl=bl, t=T(b), e=e, chord=chord_of_bar[bl % cyc], drums=drums,
                         build=building, drop=(bl == marks.get('drop', -1)),
                         breakdown=('breakdown' in marks and bl >= marks['breakdown'] and
                                    not (marks.get('drop', -1) > marks['breakdown'] and bl >= marks['drop']))))
    if loop:                                          # periodic drums state: copy cycle-local state
        for p in plan:
            ref = [q for q in plan if q['bl'] == p['bl'] and q['b'] >= 0]
            if ref:
                p['drums'] = ref[0]['drums']

    B = {k: _Bus(N) for k in ('pad', 'arp', 'bass', 'shimmer', 'kick', 'hats', 'perc', 'fx', 'bell')}
    kicks = []

    # ---- chord spans + pad -----------------------------------------------------
    spans = []
    for p in plan:
        new = (not spans or spans[-1]['chord'] != p['chord'] or p['drop'] or (loop and p['bl'] % cyc == 0
                                                                                  and spans[-1]['b1'] != p['b']))
        if new:
            spans.append(dict(chord=p['chord'], b0=p['b'], b1=p['b'] + 1, drop=p['drop'], bk=p['bk'],
                              cycle_start=(p['bl'] % cyc == 0)))
        else:
            spans[-1]['b1'] = p['b'] + 1
    prev = None
    for s in spans:
        ofs, q, _ = prog[s['chord']]
        root, upper = _voice((tonic + ofs) % 12, QUAL[q], prev)
        s['root'], s['upper'] = root, upper
        prev = upper
    lo_fc, hi_fc = P['pad_cutoff']
    lo_bl, hi_bl = P['pad_blend']

    def fc_at(t_abs):
        e = efn(np.maximum(t_abs - (pre_s if loop else offset), 0.0))
        return lo_fc * (hi_fc / lo_fc) ** e

    notes = []                                        # (midi, t0, t1, att, key)
    active = {}
    for i, s in enumerate(spans):
        ms = [s['root']] + s['upper']
        force = s['drop'] or (loop and s['cycle_start']) or i == 0
        for m in list(active):
            if force or m not in ms:
                t0, att, k = active.pop(m)
                notes.append((m, t0, T(s['b0']), att, k))
        for m in ms:
            if m not in active:
                att = 0.10 if s['drop'] else (1.4 if (i == 0 and not loop) else 0.8)
                active[m] = (T(s['b0']), att, (s['bk'], m))
    end_t = T(last_bar + 1)
    for m, (t0, att, k) in active.items():
        notes.append((m, t0, end_t, att, k))
    for (m, t0, t1, att, k) in notes:
        rng = _rng('pad', seed, *k)
        hold = t1 - t0
        fl = float(np.clip(4.0 * np.max(fc_at(np.linspace(t0, t1, 16))), 3000.0, 9000.0))
        y = ins.pad_note(m, hold, att, 2.0, lambda tr, t0=t0: fc_at(t0 + tr),
                         lambda tr, t0=t0: lo_bl + (hi_bl - lo_bl) * efn(np.maximum(t0 + tr - (pre_s if loop else offset), 0)),
                         rng, width=0.55 + 0.3 * float(efn(max(0.0, t0 - (pre_s if loop else offset)))), flimit=fl)
        B['pad'].add(y, t0)

    # ---- bass ------------------------------------------------------------------
    for s in spans:
        pl = [p for p in plan if s['b0'] <= p['b'] < s['b1']]
        root_b = s['root'] - 12 if s['root'] - 12 >= 31 else s['root']
        pulse = [p for p in pl if p['drums'] and p['e'] >= 0.6]
        if pulse and len(pulse) == len(pl):
            for p in pl:
                for k8 in range(bpb * 2):
                    m = root_b + (12 if k8 % 4 == 3 else 0)
                    v = (0.80 if k8 % 2 == 0 else 0.66) * (0.85 + 0.15 * p['e'])
                    B['bass'].add(ins.sub_bass(m, grid.beat_s * 0.38, v, att=0.006, rel=0.05), T(p['b'], k8 * 0.5))
        elif max(p['e'] for p in pl) >= 0.2:
            d = (s['b1'] - s['b0']) * bar_s
            B['bass'].add(ins.sub_bass(root_b, d - 0.05, 0.55 + 0.3 * pl[0]['e'], att=0.25, rel=0.5), T(s['b0']))

    # ---- arp (crystal pluck) ----------------------------------------------------
    for s in spans:
        ofs, q, _ = prog[s['chord']]
        pcs = {(tonic + ofs + i) % 12 for i in QUAL[q]}
        pool = [m for m in range(62, 87) if m % 12 in pcs]
        seq = pool + pool[-2:0:-1]
        idx = 0
        for p in [p for p in plan if s['b0'] <= p['b'] < s['b1']]:
            e = p['e']
            if p['breakdown'] and e < 0.5:
                div = 1.0
            elif e >= 0.65:
                div = 0.25
            elif e >= 0.3:
                div = 0.5
            else:
                continue
            rng = _rng('arp', seed, p['bk'])
            for k in range(int(round(bpb / div))):
                beat = k * div
                acc = abs(beat - round(beat)) < 1e-9
                v = (0.26 + 0.24 * e + (0.08 if acc else 0.0)) * (1 + rng.uniform(-0.05, 0.05))
                br = 0.75 + 0.45 * e + (0.35 if p['build'] else 0.0) * (beat / bpb)
                y = ins.crystal_pluck(seq[idx % len(seq)], v, dur=1.3, ratio=2.0, bright=br,
                                      seed=int(rng.integers(1 << 20)), decay=0.34)
                B['arp'].add(y, T(p['b'], beat), pan=0.22 * (1 if k % 2 else -1))
                idx += 1

    # ---- shimmer sprinkles at chord changes, clouds at drops ----------------------
    for s in spans:
        p0 = [p for p in plan if p['b'] == s['b0']][0]
        rng = _rng('shim', seed, s['bk'])
        ofs, q, _ = prog[s['chord']]
        tones = [m for m in range(86, 101) if m % 12 in {(tonic + ofs + i) % 12 for i in QUAL[q]}]
        cnt = int(3 + 8 * p0['e'] + (14 if s['drop'] else 0))
        for j in range(cnt):
            tg = p0['t'] + (0.75 if not s['drop'] else 2.0) * (j / max(1, cnt)) ** 1.3 + rng.uniform(0, 0.02)
            g = ins.grain(hz(tones[int(rng.integers(len(tones)))]), float(rng.uniform(0.05, 0.16)),
                          0.12 * float(rng.uniform(0.5, 1.0)) * (1.0 if not s['drop'] else 1.6))
            B['shimmer'].add(g, tg, pan=float(rng.uniform(-0.8, 0.8)))

    # ---- drums -------------------------------------------------------------------
    for p in plan:
        if not p['drums']:
            continue
        e = p['e']
        rng = _rng('drums', seed, p['bk'])
        kbeats = range(bpb) if e >= 0.75 or p['drop'] else [0, 2]
        for kb in kbeats:
            tk = T(p['b'], kb)
            B['kick'].add(ins.kick(0.95 + 0.05 * e, seed=int(rng.integers(1 << 20))), tk)
            kicks.append(tk)
        div = 0.25 if e >= 0.8 else 0.5
        for k in range(int(bpb / div)):
            beat = k * div
            acc = 1.0 if abs(beat - round(beat)) < 1e-9 else (0.7 if abs(beat * 2 - round(beat * 2)) < 1e-9 else 0.45)
            B['hats'].add(ins.hat(False, 0.6 * acc * (1 + rng.uniform(-0.1, 0.1)), seed=int(rng.integers(1 << 30))),
                          T(p['b'], beat), pan=0.18)
        if e >= 0.7:
            for kb in range(bpb):
                B['hats'].add(ins.hat(True, 0.25, seed=int(rng.integers(1 << 30))), T(p['b'], kb + 0.5), pan=-0.2)
        if e >= 0.65:
            for kb in (1, 3):
                B['perc'].add(ins.clap(0.5, seed=int(rng.integers(1 << 30))), T(p['b'], kb))

    # ---- build / drop ---------------------------------------------------------------
    if 'drop' in marks:
        for cyc_ofs in ([0] if not loop else [-n_music, 0]):
            db_ = marks['drop'] + cyc_ofs
            bb = marks['build'] + cyc_ofs
            if db_ < first_bar or db_ > last_bar + 1:
                continue
            t_drop = T(db_)
            if db_ > bb:
                d = t_drop - T(bb)
                B['fx'].add(ins.riser(d, 110.0 * 2 ** (((tonic - 9) % 12) / 12.0), seed=seed + 60, vel=0.5), T(bb))
                rb = db_ - 1
                roll = [bpb * 0 + 0.25 * k for k in range(int(bpb / 0.25 / 2))] + \
                       [bpb / 2 + 0.125 * k for k in range(int(bpb / 2 / 0.125))]
                for k, beat in enumerate(roll):
                    u = k / (len(roll) - 1)
                    B['perc'].add(ins.snare(0.16 + 0.34 * u ** 1.4, body_hz=190 + 90 * u, seed=seed * 100 + k),
                                  T(rb, beat), pan=0.08)
            B['fx'].add(ins.hit(0.8, seed=seed + 320), t_drop)
            crash = hp(noise(smp(1.6), seed + 321), 3500, 2)
            crash = lp(crash, 9500, 2) * np.exp(-np.arange(smp(1.6)) / SR / 0.35) * 0.08
            crash[:12] *= rc_ramp(12)
            B['fx'].add(np.vstack([crash, np.roll(crash, 240)]), t_drop)

    # ---- ending ------------------------------------------------------------------------
    if not loop:
        t_end = T(n_music)
        ofs, q = P['final'][mode]
        root, upper = _voice((tonic + ofs) % 12, QUAL[q], prev)
        hold = max(0.5, duration - t_end - 0.4)
        for m in [root] + upper:
            y = ins.pad_note(m, hold, 0.35, 1.2, lambda tr: np.full(np.shape(tr), 1400.0),
                             lambda tr: np.full(np.shape(tr), lo_bl + 0.2), _rng('endpad', seed, m), width=0.8)
            B['pad'].add(y, t_end)
        strum = [m for m in range(62, 90) if m % 12 in {(tonic + ofs + i) % 12 for i in QUAL[q]}][:6]
        for k, m in enumerate(strum):
            B['arp'].add(ins.crystal_pluck(m, 0.42, 2.2, 2.0, 0.8, seed=seed + 410 + k, decay=0.6), t_end + 0.045 * k,
                         pan=-0.5 + 0.2 * k)
        B['bell'].add(ins.bell(72 + (tonic + ofs + 7) % 12, 0.8, 4.0), t_end)      # the fifth, octave 5 (MIDI)
        B['bass'].add(ins.sub_bass(root - 12 if root - 12 >= 31 else root, hold, 0.5, att=0.02, rel=0.8), t_end)
        rng = _rng('endshim', seed)
        tones = [m for m in range(86, 101) if m % 12 in {(tonic + ofs + i) % 12 for i in QUAL[q]}]
        for j in range(16):
            tg = t_end + 2.5 * (j / 16) ** 1.4
            B['shimmer'].add(ins.grain(hz(tones[int(rng.integers(len(tones)))]), float(rng.uniform(0.06, 0.18)),
                                       0.14 * np.exp(-(tg - t_end) / 1.5)), tg, pan=float(rng.uniform(-0.8, 0.8)))

    # ---- mix -------------------------------------------------------------------------
    mix, info = _mix(P, B, kicks, N)
    # ---- master ----------------------------------------------------------------------
    if loop:
        s0 = smp(pre_s)
        region = (s0, s0 + smp(L))
    else:
        region = (0, N)
    y, minfo = _master(mix, target_lufs, ceiling_db, region, loop, duration if not loop else None)
    audio = y[:, region[0]:region[1]] if loop else y
    info.update(minfo)

    # ---- meta ------------------------------------------------------------------------
    bars = []
    for p in plan:
        if loop and not (0 <= p['b'] < n_music):
            continue
        t_out = p['t'] - (pre_s if loop else 0.0)
        ofs, q, _ = prog[p['chord']]
        names = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
        bars.append(dict(bar=p['b'], t=round(t_out, 6), sample=smp(t_out), frame=int(round(t_out * fps)),
                         chord=names[(tonic + ofs) % 12] + q, energy=round(p['e'], 3), drums=p['drums'],
                         build=p['build'], drop=p['drop'], breakdown=p['breakdown']))
    if not loop:
        bars.append(dict(bar=n_music, t=round(T(n_music), 6), sample=smp(T(n_music)),
                         frame=int(round(T(n_music) * fps)), chord='ending', energy=None))
    meta = dict(preset=preset, title=P['title'], bpm=bpm, key=key or P['key'], mode=mode,
                beats_per_bar=bpb, bar_s=bar_s, beat_s=grid.beat_s, duration=audio.shape[1] / SR, sr=SR, fps=fps,
                frame_error_ms=grid.frame_error_ms(), seed=seed,
                sections={k: dict(bar=v, t=round(v * bar_s + (0 if loop else offset), 6)) for k, v in marks.items()},
                loop=dict(start=0.0, end=audio.shape[1] / SR, bars=n_music) if loop else None,
                kicks=[round(t - (pre_s if loop else 0.0), 6) for t in sorted(kicks)
                       if (not loop) or (pre_s <= t < pre_s + L)],
                bars=bars, mix=info)
    return ScoreResult(audio=audio, meta=meta)


def _sidechain_env(kicks, depth_db, n, tau=0.12, att=0.004):
    g = np.zeros(n)
    for tk in kicks:
        s0 = smp(tk)
        s1 = min(n, s0 + smp(0.7))
        if s1 <= s0:
            continue
        tt = np.arange(s1 - s0) / SR
        dip = depth_db * np.exp(-np.maximum(tt - att, 0) / tau)
        na = min(len(dip), smp(att))
        dip[:na] *= rc_ramp(na)
        g[s0:s1] = np.minimum(g[s0:s1], dip)
    return 10 ** (g / 20.0)


def _mix(P, B, kicks, N):
    stems = {}
    for name, bus in B.items():
        x = apply_eq(bus.y, P['eq'].get(name, []))
        if kicks and P['sidechain_db'].get(name):
            x = x * _sidechain_env(kicks, P['sidechain_db'][name], N)
        stems[name] = x
    ref = meter.integrated(stems['pad'])
    faders = {}
    for name, x in stems.items():
        I = meter.integrated(x)
        if not np.isfinite(I):
            faders[name] = None
            continue
        g = ref + P['balance'].get(name, -6.0) - I
        faders[name] = round(float(g), 2)
        stems[name] = x * db2lin(g)
    dry = sum(stems.values())
    sends = {'hall': np.zeros((2, N)), 'room': np.zeros((2, N)), 'delay': np.zeros((2, N))}
    for name, x in stems.items():
        h, r, d = P['sends'].get(name, (0, 0, 0))
        if h:
            sends['hall'] += x * h
        if r:
            sends['room'] += x * r
        if d:
            sends['delay'] += x * d
    wet = convolve_st(lp(hp(sends['hall'], 200, 2), 9000, 2), get_ir('hall'), N)
    wet += convolve_st(lp(hp(sends['room'], 250, 2), 10000, 2), get_ir('room'), N)
    m = hp(0.5 * (sends['delay'][0] + sends['delay'][1]), 300, 2)
    bpm_delay = 0.375 * (120.0 / P['bpm'])
    wet += pingpong(m, bpm_delay, fb=0.36, damp_hz=4200, hp_hz=300)
    if kicks:
        wet = wet * _sidechain_env(kicks, -1.5, N)
    out = mono_lows(dry + wet)
    return out, dict(faders_db=faders, pad_lufs=ref)


def _master(x, target, ceiling, region, loop, duration):
    a, b = region
    x = hp(x, 25.0, 2)
    I0 = meter.integrated(x[:, a:b])
    ref = -17.0
    x = x * 10 ** ((ref - I0) / 20)
    xc, gcomp = compressor(x, -13.0, ratio=2.0, knee_db=6.0, att=0.010, rel=0.150)
    G = target - ref
    n = x.shape[1]
    fade = np.ones(n)
    if not loop:
        ni = smp(0.005)
        fade[:ni] = rc_ramp(ni)
        nf = smp(min(2.0, 0.4 * duration))
        u = np.linspace(0, 1, nf)
        fade[n - nf:] = np.cos(0.5 * np.pi * u) ** 2
        fade[-1] = 0.0
    y = xc
    glim = np.ones(n)
    for _ in range(6):
        y = xc * 10 ** (G / 20)
        y = softclip_os(y, thresh=0.80 * 10 ** (ceiling / 20))
        y, glim = limiter(y, ceiling, look=0.005, rel=0.08)
        y = y * fade
        I = meter.integrated(y[:, a:b])
        if abs(I - target) < 0.03:
            break
        G += target - I
    return y, dict(comp_gr_db_max=float(-20 * np.log10(gcomp.min())),
                   lim_gr_db_max=float(-20 * np.log10(glim.min())),
                   lim_gr_db_p99=float(np.percentile(-20 * np.log10(glim), 99)), makeup_db=float(G))
