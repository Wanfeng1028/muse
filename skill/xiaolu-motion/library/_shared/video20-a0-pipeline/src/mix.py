"""Programme mix (48 kHz stereo, v2 timeline 4857 frames = 7,771,200 samples).

Stems: voice master (03_locked_master/voice_master_48k.wav, -16 LUFS), the three inserts' own audio (each levelled to
-16.5 LUFS over its span, see locked_review.py), BGM bed (Jianying cache, read-only), SFX track (xlaudio render_cues).
BGM rules (task + SOP stage 5):
  * the bed sits BGM_REL_LU under the voice's integrated loudness, measured on the bed itself (no fixed gain number);
  * ducking is keyed ONLY from the presenter's voice stem (never from the inserts, whose own tracks carry voice + music):
    DUCK_DB with a 300 Hz-4 kHz pocket, 80 ms look-ahead, 60 ms attack, 250 ms hold, 600 ms release (xlaudio);
  * during the three inserts the bed fades out (0.30 s, ending on the cut into the insert) and fades back in
    (0.60 s from the cut back to the presenter), so the demos' own sound has the room;
  * 0.25 s fade-in at 0, 1.6 s fade-out ending at the last frame.
Master: sum -> 25 Hz high-pass -> gain -> band-limited soft clip (-3 dBFS, xlaudio) -> true-peak look-ahead limiter
(ceiling -1.3 dBTP) iterated to -14.0 LUFS; checked with ffmpeg ebur128 (TP must read <= -1.0 dBTP, else lower the
ceiling and redo).
usage:
  python3 mix.py auditions            -> 06_audio/bgm_candidates/bgm{1,2,3}_*_audition_30s.wav (+ report)
  python3 mix.py programme SFX.json   -> 06_audio/mix_v2_bgm1.wav, mix_v2_nobgm.wav, stems/, mix_report.json
"""
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
os.environ.setdefault('NUMBA_CACHE_DIR', str(__import__('pathlib').Path(__file__).resolve().parent.parent / 'work/numba_cache'))
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from a0common import *  # noqa
sys.path.insert(0, str(XM / 'audio'))
import numpy as np  # noqa: E402
from scipy import signal  # noqa: E402
import xlaudio as xa  # noqa: E402
from xlaudio import meter  # noqa: E402
from xlaudio.dsp import hp, lp0, limiter, softclip_os, upsample, db2lin, rc_ramp  # noqa: E402
from xlaudio.mix import duck_envelope  # noqa: E402

JY = Path(os.environ.get("XM_BGM_LIBRARY_DIR", "path/to/your_bgm_library"))  # any folder of BGM you have the rights to use
N = TOTAL * SPF
VOICE_REF = -16.0
BGM_REL_LU = -9.0
DUCK_DB = -7.0
POCKET_DB = -3.0
INSERT_TARGET = -16.5
TARGET = -14.0
CEIL = -1.0
LIMIT_CEIL = -2.0          # limiter ceiling on the WAV master: AAC encoding adds ~0.7 dB true peak (measured on draft v1)

# candidates in rank order: file (relative to JY above), start (a bar line -- from Jianying's .beat
# analysis if you have one, see xlaudio/grid.py:load_jianying_beat, or just where you want the bed
# to start), splices [(A, B)]: at song time A jump back to song time B (both bar lines, B = A - 16
# bars in the source project) with a 60ms equal-power crossfade, to loop a track under a longer
# programme without an audible seam. The 3 rows below are placeholders standing in for the source
# project's 3 real candidate tracks (each licensed for that project's own use via a Jianying
# membership, hence identified there by Jianying's own content-hash filename) -- replace with your
# own BGM's filenames/timings; the `style`/`tempo_bpm`/`key` fields are analysis notes for picking
# between candidates, not required by the code.
BGM = [
    dict(n=1, file='your_bgm_1.mp3', start=0.04, splices=[],
         style='e.g. upbeat synth + electric piano, steady groove, no drop-outs', tempo_bpm=115.4, key='e.g. B major-ish'),
    dict(n=2, file='your_bgm_2.mp3', start=30.73, splices=[],
         style='e.g. bright plucked-synth pop, techy feel', tempo_bpm=125.0, key='e.g. D major'),
    dict(n=3, file='your_bgm_3.mp3', start=0.26, splices=[(100.27, 68.27)],
         style='e.g. warm plucked guitar + light percussion, loops via the splice above', tempo_bpm=120.0, key='e.g. D major'),
]


def ebur(path):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(path), '-filter_complex', 'ebur128=peak=true',
                        '-f', 'null', '-'], capture_output=True, text=True)
    t = r.stderr[r.stderr.rfind('Summary:'):]
    g = lambda k: float(re.search(k + r':\s*(-?[\d.]+)', t).group(1))
    return dict(I_LUFS=g('I'), LRA_LU=g('LRA'), TP_dBTP=g('Peak'))


def load(path, ch=2):
    return read_audio(path, SR, ch=ch).T


def voice_and_inserts():
    v = load(LOCKED / 'voice_master_48k.wav')
    ins = load(LOCKED / 'inserts_audio_48k.wav')
    assert v.shape[1] == N and ins.shape[1] == N
    gains = {}
    out = np.zeros_like(ins)
    for key, (v0, v1, f, df0) in insert_frames().items():
        a, b = v0 * SPF, v1 * SPF
        g = INSERT_TARGET - meter.ungated(ins[:, a:b])
        out[:, a:b] = ins[:, a:b] * db2lin(g)
        gains[key] = round(float(g), 2)
    return v, out, gains


def bgm_bed(plan):
    song = load(JY / plan['file'])
    s = int(round(plan['start'] * SR))
    parts, pos = [], s
    xf = int(0.06 * SR)
    for A, B in plan['splices']:
        a = int(round(A * SR))
        parts.append(song[:, pos:a + xf // 2])
        pos = int(round(B * SR)) - xf // 2
    parts.append(song[:, pos:])
    bed = parts[0]
    for p in parts[1:]:
        r = np.sqrt(rc_ramp(xf))
        bed = np.hstack([bed[:, :-xf], bed[:, -xf:] * r[::-1] + p[:, :xf] * r, p[:, xf:]])
    assert bed.shape[1] >= N, ('bed too short', bed.shape[1] / SR)
    bed = bed[:, :N].copy()
    return bed


def insert_mask():
    """1 outside the inserts, 0 inside; 0.30 s fade out before each insert, 0.60 s fade in after"""
    m = np.ones(N)
    fo, fi = int(0.30 * SR), int(0.60 * SR)
    for key, (v0, v1, f, df0) in insert_frames().items():
        a, b = v0 * SPF, v1 * SPF
        m[a - fo:a] = np.minimum(m[a - fo:a], rc_ramp(fo)[::-1])
        m[a:b] = 0
        m[b:b + fi] = np.minimum(m[b:b + fi], rc_ramp(fi))
    return m


def place_bgm(bed, v):
    g = VOICE_REF + BGM_REL_LU - meter.integrated(bed)
    b = bed * db2lin(g)
    env, dinfo = duck_envelope(v, VOICE_REF, -22.0, 60.0, 250.0, 600.0, 80.0)
    sos = signal.butter(2, [300.0, 4000.0], 'band', fs=SR, output='sos')
    band = signal.sosfiltfilt(sos, b, axis=-1)
    b = (b + (db2lin(POCKET_DB * env) - 1.0) * band) * db2lin(DUCK_DB * env)
    m = insert_mask()
    fi, fo = int(0.25 * SR), int(1.6 * SR)
    m[:fi] *= rc_ramp(fi)
    m[-fo:] *= rc_ramp(fo)[::-1]
    b = b * m
    act = env > 0.5
    info = dict(stage_gain_db=float(g), bed_I_LUFS_before=float(meter.integrated(bed)), unducked_rel_lu=BGM_REL_LU,
                duck_db=DUCK_DB, pocket_db=POCKET_DB, ducked_time_frac=float(np.mean(act)),
                voice_minus_bgm_in_speech_LU=float(meter.ungated(v[:, act]) - meter.ungated(b[:, act])) if act.any() else None)
    return b, info


def _chunked(fn, x, block=10 * SR, ov=SR):
    """apply a (look-ahead / oversampling) stage block by block with 1 s overlap on both sides: same result as the
    whole-array call for these short-memory stages, at a fraction of the memory (4x oversampling of 162 s is ~2 GB)"""
    n = x.shape[1]
    y = np.empty_like(x)
    g_all = None
    for s0 in range(0, n, block):
        a, b = max(0, s0 - ov), min(n, s0 + block + ov)
        r = fn(x[:, a:b])
        yb, gb = r if isinstance(r, tuple) else (r, None)
        e = min(n, s0 + block)
        y[:, s0:e] = yb[:, s0 - a:e - a]
        if gb is not None:
            if g_all is None:
                g_all = np.empty(n)
            g_all[s0:e] = gb[s0 - a:e - a]
    return (y, g_all) if g_all is not None else y


def master(pre, out_path):
    pre = hp(pre, 25.0, 2)
    ceiling = LIMIT_CEIL
    G = TARGET - meter.integrated(pre)
    thr = 10 ** (-3.0 / 20)
    fade = np.ones(pre.shape[1])
    ni, no = int(0.003 * SR), int(0.05 * SR)
    fade[:ni] = rc_ramp(ni)
    fade[-no:] = rc_ramp(no)[::-1]
    for attempt in range(4):
        for _ in range(10):
            x = pre * db2lin(G)
            x = _chunked(lambda c: c + lp0(softclip_os(c, thresh=thr) - c, 8000.0, 4), x)
            y, gl = _chunked(lambda c: limiter(c, ceiling, look=0.005, rel=0.06), x)
            y = y * fade
            I = meter.integrated(y)
            if abs(I - TARGET) < 0.02:
                break
            G += TARGET - I
        part = str(out_path).replace('.wav', '.partial.wav')
        xa.write_wav(part, y, bits=24)
        eb = ebur(part)
        if eb['TP_dBTP'] <= CEIL and abs(eb['I_LUFS'] - TARGET) <= 0.3:
            break
        ceiling -= max(0.1, eb['TP_dBTP'] - CEIL + 0.1)
    d = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', part],
                             capture_output=True, text=True, check=True).stdout)
    assert abs(d - N / SR) < 1e-3, d
    os.replace(part, out_path)
    grl = -20 * np.log10(gl)
    return y, dict(makeup_db=float(G), limiter_ceiling_dbtp=float(ceiling), limiter_gr_db_max=float(grl.max()),
                   limiter_ms_over_1db=float(np.sum(grl > 1) / SR * 1000), ffmpeg=eb)


def auditions():
    v, ins, gains = voice_and_inserts()
    outdir = AUDIO / 'bgm_candidates'
    outdir.mkdir(parents=True, exist_ok=True)
    rep = []
    for plan in BGM:
        bed = bgm_bed(plan)
        b, info = place_bgm(bed, v)
        full = WORK / f'aud_full_{plan["n"]}.wav'
        y, minfo = master(v + ins + b, full)
        n30 = 30 * SR
        seg = y[:, :n30].copy()
        seg[:, -int(0.5 * SR):] *= rc_ramp(int(0.5 * SR))[::-1]
        out = outdir / f'bgm{plan["n"]}_{plan["file"][:8]}_audition_30s.wav'
        xa.write_wav(str(out), seg, bits=24)
        full.unlink()
        rep.append(dict(**plan, audition=str(out), bgm=info, master=minfo,
                        note='v2 0:00-0:30：真人人声母带 + 三段插入成片原声 + 本曲（无音效），与全片同一混音参数，整片母带到 -14 LUFS 后截取前 30 s'))
        print(plan['n'], plan['file'][:8], 'voice-bgm in speech %.1f LU' % info['voice_minus_bgm_in_speech_LU'], minfo['ffmpeg'])
    save_json(outdir / 'auditions_report.json', dict(insert_gain_db=gains, params=dict(
        voice_ref_lufs=VOICE_REF, bgm_rel_lu=BGM_REL_LU, duck_db=DUCK_DB, pocket_db=POCKET_DB, target_lufs=TARGET,
        ceiling_dbtp=CEIL), candidates=rep))


def render_sfx(cues_path):
    cues = load_json(cues_path)
    items = []
    for c in cues:
        d = dict(id=c['id'], at=float(c['t']), gain_db=float(c.get('gain_db', 0.0)))
        prm = dict(c.get('params') or {})
        if c.get('pitch') not in (None, 0):
            prm['pitch'] = float(c['pitch'])
        for k in ('dur', 'bright'):                       # top-level 'note' is a human note, never a pitch name
            if k in c:
                prm[k] = c[k]
        if prm:
            d['params'] = prm
        if c.get('align'):
            d['align'] = c['align']
        d['fps'] = FPS
        items.append(d)
    trk, log = xa.render_cues(items, duration=N / SR, return_log=True)
    return trk, log


def programme(sfx_path=None):
    v, ins, gains = voice_and_inserts()
    plan = BGM[0]
    b, info = place_bgm(bgm_bed(plan), v)
    sfx = np.zeros_like(v)
    slog = None
    if sfx_path:
        sfx, slog = render_sfx(sfx_path)
        sfx = sfx[:, :N]
        # xlaudio SFX reference levels assume the voice at -16 LUFS: our voice stem is exactly there
    (AUDIO / 'stems').mkdir(parents=True, exist_ok=True)
    y1, m1 = master(v + ins + b + sfx, AUDIO / 'mix_v2_bgm1.wav')
    y0, m0 = master(v + ins + sfx, AUDIO / 'mix_v2_nobgm.wav')
    xa.write_wav(str(AUDIO / 'stems/bgm1_used_bed.wav'), b, bits='float')
    xa.write_wav(str(AUDIO / 'stems/sfx.wav'), sfx, bits='float')
    save_json(AUDIO / 'mix_report.json', dict(bgm=dict(plan, **info), insert_gain_db=gains, with_bgm=m1, no_bgm=m0,
                                              voice=ebur(LOCKED / 'voice_master_48k.wav'),
                                              sfx_cues=str(sfx_path) if sfx_path else None,
                                              sfx_count=(len(load_json(sfx_path)) if sfx_path else 0)))
    print('with BGM', m1['ffmpeg'], '| no BGM', m0['ffmpeg'])


if __name__ == '__main__':
    if sys.argv[1] == 'auditions':
        auditions()
    else:
        programme(sys.argv[2] if len(sys.argv) > 2 else None)
