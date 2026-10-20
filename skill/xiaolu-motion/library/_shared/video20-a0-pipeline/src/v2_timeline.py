"""v2 candidates built on top of the v2 programme (4857 frames) with the pause cut list
(05_visual/build/a0/cuts/pause_cut_list_v2.json):
  v2p     pause-cut programme: the v2 frames outside every removed span, same picture, same sound samples
  v2p110  v2p at 1.1x: output frame k shows v2p frame round(k * 1.1) (drops 1 frame in 11, no interpolation);
          dialogue (voice + inserts) time-stretched with rubberband (pitch kept), SFX re-placed at t / 1.1,
          BGM laid again at its own speed.
usage: python3 v2_timeline.py frames | audio | captions | all
Outputs: a0/cuts/frames_v2p.json, frames_v2p110.json; 06_audio/mix_v2p_*.wav, mix_v2p110_*.wav;
         04_captions/captions_v2p_burn.srt/.ass, captions_v2p110_burn.srt/.ass
"""
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
os.environ.setdefault('NUMBA_CACHE_DIR', str(__import__('pathlib').Path(__file__).resolve().parent.parent / 'work/numba_cache'))
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from a0common import *  # noqa
import numpy as np  # noqa: E402

CUTS = A0 / 'cuts'
SPEED = 1.1
XF_MS = 12.0


def cut_list():
    return load_json(CUTS / 'pause_cut_list_v2.json')


def kept_frames():
    rm = set()
    for c in cut_list()['cuts']:
        rm.update(range(*c['frames']))
    return [f for f in range(TOTAL) if f not in rm]


def map_time(t, cuts):
    """v2 seconds -> v2p seconds (a time inside a removed span maps to the cut point)"""
    out = t
    for c in cuts:
        a, b = c['frames'][0] / FPS, c['frames'][1] / FPS
        if t >= b:
            out -= b - a
        elif t > a:
            out -= t - a
    return out


def frames():
    keep = kept_frames()
    n110 = int(len(keep) / SPEED)
    sel = [keep[min(len(keep) - 1, int(round(k * SPEED)))] for k in range(n110)]
    save_json(CUTS / 'frames_v2p.json', dict(timeline='v2p', fps=FPS, n=len(keep), duration_s=round(len(keep) / FPS, 3), v2_frames=keep))
    save_json(CUTS / 'frames_v2p110.json', dict(timeline='v2p110', fps=FPS, speed=SPEED, n=len(sel), duration_s=round(len(sel) / FPS, 3),
                                                note='frame k = v2p frame round(k*1.1)', v2_frames=sel))
    print('v2p', len(keep), 'frames', round(len(keep) / FPS, 3), 's | v2p110', len(sel), 'frames', round(len(sel) / FPS, 3), 's')


def cut_audio(y, cuts, sr=SR, spf=SPF):
    """remove the cut spans (frame boundaries) with an equal-power crossfade of XF_MS centred on every join"""
    h = int(round(XF_MS / 2000 * sr))
    t = (np.arange(2 * h) + 0.5) / (2 * h)
    fin, fout = np.sin(0.5 * np.pi * t), np.cos(0.5 * np.pi * t)
    spans = sorted((c['frames'][0] * spf, c['frames'][1] * spf) for c in cuts)
    pieces, pos = [], 0
    for a, b in spans:
        pieces.append((pos, a))
        pos = b
    pieces.append((pos, y.shape[1]))
    out = np.concatenate([y[:, a:b] for a, b in pieces], axis=1)
    x = 0
    for (a0, b0), (a1, b1) in zip(pieces, pieces[1:]):
        x += b0 - a0
        A = y[:, b0 - h:b0 + h]
        B = y[:, a1 - h:a1 + h]
        out[:, x - h:x + h] = A * fout + B * fin
    return out


def stretch(y, speed):
    """rubberband (pitch kept) through ffmpeg; atempo fallback"""
    tmp_in, tmp_out = WORK / 'st_in.wav', WORK / 'st_out.wav'
    write_wav(tmp_in, y.T, SR)
    try:
        sh(['ffmpeg', '-v', 'error', '-y', '-i', tmp_in, '-af', f'rubberband=tempo={speed}:pitch=1:transients=crisp:detector=compound:'
            f'phase=laminar:window=standard:smoothing=off:formant=preserved:pitchq=quality:channels=together',
            '-c:a', 'pcm_f32le', tmp_out])
        how = 'rubberband'
    except subprocess.CalledProcessError:
        sh(['ffmpeg', '-v', 'error', '-y', '-i', tmp_in, '-af', f'atempo={speed}', '-c:a', 'pcm_f32le', tmp_out])
        how = 'atempo'
    z = read_audio(tmp_out, SR, ch=2).T
    tmp_in.unlink()
    tmp_out.unlink()
    return z, how


def audio():
    import mix as M
    cl = cut_list()
    cuts = cl['cuts']
    v, ins, gains = M.voice_and_inserts()
    vc, ic = cut_audio(v, cuts), cut_audio(ins, cuts)
    n = vc.shape[1]
    assert n == len(kept_frames()) * SPF, (n, len(kept_frames()) * SPF)
    cues = load_json(A0 / 'work/sfx_merged_cand_v1.json')
    inside = [c for c in cues if any(cc['frames'][0] / FPS < float(c['t']) < cc['frames'][1] / FPS for cc in cuts)]
    ins_map = {}
    for key, (v0, v1, f, df0) in insert_frames().items():
        ins_map[key] = (int(round(map_time(v0 / FPS, cuts) * FPS)), int(round(map_time(v1 / FPS, cuts) * FPS)))
    rep = dict(cuts=len(cuts), removed_s=cl['removed_s'], sfx_inside_cut_spans=[(c['id'], c['t'], c.get('source')) for c in inside],
               insert_frames_v2p=ins_map, insert_gain_db=gains)
    for tag, speed in (('v2p', 1.0), ('v2p110', SPEED)):
        cues_t = [dict(c, t=round(map_time(float(c['t']), cuts) / speed, 4)) for c in cues]
        p = WORK / f'sfx_{tag}.json'
        save_json(p, cues_t)
        dia = vc + ic
        voice_key = vc
        how = None
        if speed != 1.0:
            dia, how = stretch(dia, speed)
            voice_key, _ = stretch(vc, speed)
            target = int(len(kept_frames()) / speed) * SPF          # exactly the 1.1x picture's frame count
            fit = lambda z: z[:, :target] if z.shape[1] >= target else np.hstack([z, np.zeros((2, target - z.shape[1]))])
            rep.setdefault('stretch_len_before_fit', {})[tag] = [int(dia.shape[1]), int(target)]
            dia, voice_key = fit(dia), fit(voice_key)
        N_ = dia.shape[1]
        M.N = N_                                              # the mix helpers work on the current programme length
        sfx, _ = M.render_sfx(p)
        sfx = sfx[:, :N_] if sfx.shape[1] >= N_ else np.hstack([sfx, np.zeros((2, N_ - sfx.shape[1]))])
        # BGM #1 at its own speed; ducking keyed by the presenter's voice only; bed silent during the (moved) inserts
        bed = M.bgm_bed(M.BGM[0])[:, :N_] if True else None
        M.insert_frames_override = {k: (int(round(a / speed)), int(round(b / speed))) for k, (a, b) in ins_map.items()}
        b, binfo = place_bgm_cut(M, bed, voice_key, M.insert_frames_override)
        y1, m1 = M.master(dia + b + sfx, AUDIO / f'mix_{tag}_bgm1.wav')
        y0, m0 = M.master(dia + sfx, AUDIO / f'mix_{tag}_nobgm.wav')
        rep[tag] = dict(samples=N_, duration_s=round(N_ / SR, 3), stretch=how, bgm=binfo, with_bgm=m1, no_bgm=m0)
        print(tag, N_ / SR, 's', 'stretch', how, m1['ffmpeg'], m0['ffmpeg'], flush=True)
    save_json(AUDIO / 'mix_v2_timelines_report.json', rep)


def place_bgm_cut(M, bed, v, ins):
    """mix.place_bgm with the insert ranges of the new timeline"""
    from xlaudio import meter
    from xlaudio.dsp import db2lin, rc_ramp
    from xlaudio.mix import duck_envelope
    from scipy import signal
    N_ = bed.shape[1]
    g = M.VOICE_REF + M.BGM_REL_LU - meter.integrated(bed)
    b = bed * db2lin(g)
    env, _ = duck_envelope(v, M.VOICE_REF, -22.0, 60.0, 250.0, 600.0, 80.0)
    sos = signal.butter(2, [300.0, 4000.0], 'band', fs=SR, output='sos')
    band = signal.sosfiltfilt(sos, b, axis=-1)
    b = (b + (db2lin(M.POCKET_DB * env) - 1.0) * band) * db2lin(M.DUCK_DB * env)
    m = np.ones(N_)
    fo, fi = int(0.30 * SR), int(0.60 * SR)
    for key, (v0, v1) in ins.items():
        a, c = v0 * SPF, v1 * SPF
        m[a - fo:a] = np.minimum(m[a - fo:a], rc_ramp(fo)[::-1])
        m[a:c] = 0
        m[c:c + fi] = np.minimum(m[c:c + fi], rc_ramp(fi))
    fi2, fo2 = int(0.25 * SR), int(1.6 * SR)
    m[:fi2] *= rc_ramp(fi2)
    m[-fo2:] *= rc_ramp(fo2)[::-1]
    b = b * m
    act = env > 0.5
    return b, dict(stage_gain_db=float(g), ducked_time_frac=float(np.mean(act)),
                   voice_minus_bgm_in_speech_LU=float(meter.ungated(v[:, act]) - meter.ungated(b[:, act])))


def captions():
    cl = cut_list()
    cuts = cl['cuts']
    C = load_json(CAPS / 'captions_v2.json')
    import captions as CP
    for tag, speed in (('v2p', 1.0), ('v2p110', SPEED)):
        rows = []
        for r in C['strips']:
            if not r['burn']:
                continue
            a = map_time(r['f0'] / FPS, cuts) / speed
            b = map_time(r['f1'] / FPS, cuts) / speed
            if b - a < 0.2:
                continue
            rows.append(dict(r, t0=a, t1=b))
        srt = []
        for n, r in enumerate(rows, 1):
            srt.append(f"{n}\n{CP.srt_time(r['t0'])} --> {CP.srt_time(r['t1'])}\n{r['text']}\n")
        (CAPS / f'captions_{tag}_burn.srt').write_text('\n'.join(srt), encoding='utf-8')
        ass = (CAPS / 'captions_v2_burn.ass').read_text(encoding='utf-8')
        head = ass[:ass.index('[Events]')]
        ev = ['[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
        for r in rows:
            txt = re.sub(r'\[([^\]]+)\]', r'{\\fnSource Han Sans SC Heavy\\3c&H0AD6FF&}\1{\\fnSource Han Sans SC Medium\\3c&HFFFFFF&}', r['markup'])
            ev.append(f"Dialogue: 0,{CP.ass_time(r['t0'])},{CP.ass_time(r['t1'])},C,,0,0,0,,{txt}")
        (CAPS / f'captions_{tag}_burn.ass').write_text(head + '\n'.join(ev) + '\n', encoding='utf-8')
        print(tag, len(rows), 'lines')


if __name__ == '__main__':
    step = sys.argv[1]
    for s in (['frames', 'audio', 'captions'] if step == 'all' else [step]):
        {'frames': frames, 'audio': audio, 'captions': captions}[s]()
