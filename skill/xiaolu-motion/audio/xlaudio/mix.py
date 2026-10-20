"""人声混音: ``mix_with_voice(voice, bgm, sfx, out_path=...) -> report dict``.

* voice  talking-head master (any ffmpeg-readable file or (2, n) array); defines the timeline
* bgm    ANY external music file -- by default a Jianying library track (their cache files are
         AAC-in-MP4 with an .mp3 extension; ffmpeg decodes them regardless) -- or our own bed.
         Its loudness is measured and re-staged, so heavily mastered commercial tracks are fine.
* sfx    effects track from render_cues (reference levels assume the voice at -16 LUFS)

Chain
1. voice: measure (ffmpeg ebur128 I / TP / LRA) -> 70 Hz high-pass -> phase rotator (5 all-pass
   sections 120-500 Hz: makes peaky glottal pulses symmetric, -4 dB peak-to-loudness on the test
   voice, spectrum unchanged) -> gain to voice_ref_lufs -> compressor (3:1 above ref+4 dB,
   2 ms / 80 ms) -> re-stage to voice_ref_lufs
2. bgm: pick [bgm_start, bgm_start + len(voice)], fade in when starting mid-song, fade out at
   the end (or loop with a crossfade when bgm_fit='loop'), gain so its integrated loudness is
   voice_ref + bgm_rel_lu
3. ducking: voice activity = 10 ms RMS of the 150-4000 Hz voice band above ref + vad_rel_db;
   dilated by hold_ms, started lookahead_ms early, smoothed with attack_ms / release_ms;
   BGM gain = duck_db * a(t), plus an extra "voice pocket" dip (pocket_db) in 300 Hz-4 kHz
4. master: sum -> 25 Hz high-pass -> static gain -> band-limited clipper (4x oversampled soft
   clip above master_clip_dbfs; only the < 8 kHz part of the correction is applied, so it adds
   no HF distortion bursts; only the sharpest glottal peaks reach it) -> look-ahead true-peak limiter,
   iterated until integrated loudness = target_lufs; ceiling ceiling_dbtp - 0.3 dB margin,
   verified with ffmpeg (re-run with a lower ceiling if ffmpeg reads above ceiling_dbtp)
"""
import json
import os
import tempfile

import numpy as np
from scipy import signal

from . import meter
from .dsp import SR, TWOPI, smp, hp, lp0, rc_ramp, compressor, limiter, db2lin, upsample, softclip_os
from .wavio import as_audio, write_wav


def phase_rotate(x, freqs=(120.0, 180.0, 260.0, 360.0, 500.0), q=0.6):
    """cascade of 2nd-order all-pass sections: flat magnitude, dispersed phase.
    Reduces the crest factor of asymmetric speech waveforms (broadcast 'phase rotator')."""
    for f in freqs:
        w0 = TWOPI * f / SR
        al = np.sin(w0) / (2 * q)
        c = np.cos(w0)
        a0 = 1 + al
        x = signal.lfilter(np.array([1 - al, -2 * c, 1 + al]) / a0, np.array([1 + al, -2 * c, 1 - al]) / a0, x,
                           axis=-1)
    return x


def _fit_bgm(bgm, n, start, fit, fade_in, fade_out, xfade=2.0):
    s0 = smp(start)
    src = bgm[:, s0:]
    info = dict(source_len_s=bgm.shape[1] / SR, start_s=start, fit=fit)
    if src.shape[1] >= n:
        y = src[:, :n].copy()
        info['ends_naturally'] = False
    elif fit == 'loop' and src.shape[1] > smp(2 * xfade + 1):
        xf = smp(xfade)
        y = src.copy()
        while y.shape[1] < n:
            a = np.sqrt(rc_ramp(xf))
            y[:, -xf:] = y[:, -xf:] * a[::-1] + src[:, :xf] * a
            y = np.hstack([y, src[:, xf:]])
        y = y[:, :n]
        info['ends_naturally'] = False
        info['looped'] = True
    else:
        y = np.hstack([src, np.zeros((2, n - src.shape[1]))])
        info['ends_naturally'] = True
        info['warning'] = 'BGM shorter than the voice: %.1f s of silence at the end' % ((n - src.shape[1]) / SR)
    fi = smp(fade_in if fade_in is not None else (0.4 if start > 0 else 0.005))
    y[:, :fi] *= rc_ramp(fi)
    if not info['ends_naturally']:
        fo = smp(fade_out)
        y[:, -fo:] *= rc_ramp(fo)[::-1]
    info['used_len_s'] = y.shape[1] / SR
    return y, info


def duck_envelope(voice, ref_lufs, vad_rel_db=-22.0, attack_ms=60.0, hold_ms=250.0, release_ms=600.0,
                  lookahead_ms=80.0, hop_ms=10.0):
    """-> (a(t) per sample in [0, 1], frame info). a = 1 means fully ducked."""
    n = voice.shape[1]
    m = 0.5 * (voice[0] + voice[1])
    sos = signal.butter(2, [150.0, 4000.0], 'band', fs=SR, output='sos')
    b = signal.sosfilt(sos, m)
    h = smp(hop_ms / 1000.0)
    nf = n // h
    rms = np.sqrt(np.mean(b[: nf * h].reshape(nf, h) ** 2, axis=1) + 1e-20)
    lvl = 20 * np.log10(rms)
    thr = ref_lufs + vad_rel_db
    act = lvl > thr
    # hold: stay active hold_ms after the last active frame; lookahead: start early
    k_hold = int(round(hold_ms / hop_ms))
    k_look = int(round(lookahead_ms / hop_ms))
    tgt = np.zeros(nf)
    idx = np.nonzero(act)[0]
    for i in idx:
        tgt[max(0, i - k_look):min(nf, i + k_hold + 1)] = 1.0
    # asymmetric one-pole smoothing at frame rate
    aa = np.exp(-hop_ms / max(attack_ms, 1e-3))
    ar = np.exp(-hop_ms / max(release_ms, 1e-3))
    a = np.zeros(nf)
    cur = 0.0
    for i in range(nf):
        c = aa if tgt[i] > cur else ar
        cur = tgt[i] + (cur - tgt[i]) * c
        a[i] = cur
    tf = (np.arange(nf) + 0.5) * h
    env = np.interp(np.arange(n), tf, a)
    return env, dict(threshold_dbfs=thr, active_frac=float(np.mean(act)), frames_level_db=lvl, frames_t=tf / SR,
                     frames_a=a)


def _ffmpeg_eb(path):
    from .analysis import ffmpeg_ebur128
    e = ffmpeg_ebur128(path)
    return dict(I_LUFS=e['I'], TP_dBTP=e['TP'], LRA_LU=e['LRA'])


def _measure(y, path=None):
    d = dict(own_I_LUFS=meter.integrated(y), own_TP_dBTP=meter.true_peak_db(y), own_LRA_LU=meter.lra(y))
    if path is not None:
        d.update(_ffmpeg_eb(path))
    return d


def mix_with_voice(voice, bgm=None, sfx=None, out_path=None, *, target_lufs=-14.0, ceiling_dbtp=-1.0,
                   voice_ref_lufs=-16.0, voice_hp_hz=70.0, voice_phase_rotate=True, voice_comp=True,
                   master_clip_dbfs=-3.0,
                   bgm_rel_lu=-6.0, bgm_start=0.0, bgm_fit='trim', bgm_fade_in=None, bgm_fade_out=1.5,
                   duck_db=-6.0, attack_ms=60.0, hold_ms=250.0, release_ms=600.0, lookahead_ms=80.0,
                   vad_rel_db=-22.0, pocket_db=-3.0, sfx_gain_db=0.0, stems_dir=None, report_path=None):
    rep = dict(params=dict(target_lufs=target_lufs, ceiling_dbtp=ceiling_dbtp, voice_ref_lufs=voice_ref_lufs,
                           voice_hp_hz=voice_hp_hz, voice_phase_rotate=voice_phase_rotate, voice_comp=voice_comp,
                           master_clip_dbfs=master_clip_dbfs, bgm_rel_lu=bgm_rel_lu,
                           bgm_start=bgm_start, bgm_fit=bgm_fit, duck_db=duck_db, attack_ms=attack_ms,
                           hold_ms=hold_ms, release_ms=release_ms, lookahead_ms=lookahead_ms,
                           vad_rel_db=vad_rel_db, pocket_db=pocket_db, sfx_gain_db=sfx_gain_db))
    # ---- 1. voice ----------------------------------------------------------------
    v = as_audio(voice)
    n = v.shape[1]
    rep['voice_in'] = dict(file=None if isinstance(voice, np.ndarray) else str(voice), duration_s=n / SR,
                           **_measure(v, None if isinstance(voice, np.ndarray) else voice))
    rep['voice_in']['PLR_dB'] = rep['voice_in']['own_TP_dBTP'] - rep['voice_in']['own_I_LUFS']
    if voice_hp_hz:
        v = hp(v, voice_hp_hz, 2)
    vinfo = {}
    if voice_phase_rotate:
        plr0 = meter.true_peak_db(v) - meter.integrated(v)
        v = phase_rotate(v)
        vinfo['phase_rotate_PLR_change_dB'] = (meter.true_peak_db(v) - meter.integrated(v)) - plr0
    g0 = voice_ref_lufs - meter.integrated(v)
    v = v * db2lin(g0)
    vinfo['stage_gain_db'] = g0
    if voice_comp:
        v, gc = compressor(v, voice_ref_lufs + 4.0, ratio=3.0, knee_db=6.0, att=0.002, rel=0.08)
        grd = -20 * np.log10(gc)
        vinfo.update(comp_threshold_dbfs=voice_ref_lufs + 4.0, comp_gr_db_max=float(grd.max()),
                     comp_gr_db_p99=float(np.percentile(grd, 99)), comp_active_frac=float(np.mean(grd > 0.5)))
        g1 = voice_ref_lufs - meter.integrated(v)
        v = v * db2lin(g1)
        vinfo['restage_gain_db'] = g1
    rep['voice_chain'] = vinfo

    # ---- 2. bgm --------------------------------------------------------------------
    if bgm is not None:
        b_raw = as_audio(bgm)
        b, binfo = _fit_bgm(b_raw, n, bgm_start, bgm_fit, bgm_fade_in, bgm_fade_out)
        binfo['file'] = None if isinstance(bgm, np.ndarray) else str(bgm)
        I_b = meter.integrated(b)
        binfo['used_part_I_LUFS'] = I_b
        binfo['used_part_TP_dBTP'] = meter.true_peak_db(b)
        gb = (voice_ref_lufs + bgm_rel_lu) - I_b
        b = b * db2lin(gb)
        binfo['stage_gain_db'] = gb
        binfo['unducked_I_LUFS'] = voice_ref_lufs + bgm_rel_lu
        # ---- 3. ducking ----------------------------------------------------------------
        env, dinfo = duck_envelope(v, voice_ref_lufs, vad_rel_db, attack_ms, hold_ms, release_ms, lookahead_ms)
        gd = db2lin(duck_db * env)
        if pocket_db:
            sos = signal.butter(2, [300.0, 4000.0], 'band', fs=SR, output='sos')
            band = signal.sosfiltfilt(sos, b, axis=-1)
            b_d = (b + (db2lin(pocket_db * env) - 1.0) * band) * gd
        else:
            b_d = b * gd
        act = env > 0.5
        dinfo_out = dict(threshold_dbfs=dinfo['threshold_dbfs'], voice_active_frames=dinfo['active_frac'],
                         ducked_time_frac=float(np.mean(act)),
                         mean_duck_db_while_ducked=float(np.mean(duck_db * env[act])) if np.any(act) else 0.0)
        # speech-to-music ratio while the voice is active (ungated energy means)
        if np.any(act):
            vs = meter.ungated(v[:, act])
            bs = meter.ungated(b_d[:, act])
            dinfo_out['voice_minus_bgm_in_speech_LU'] = vs - bs
        if np.any(~act):
            dinfo_out['bgm_level_in_gaps_LUFS_ungated'] = meter.ungated(b_d[:, ~act])
        rep['bgm'] = binfo
        rep['ducking'] = dinfo_out
    else:
        b_d = np.zeros_like(v)
        env = np.zeros(n)
        rep['bgm'] = None
    # ---- sfx ---------------------------------------------------------------------------
    if sfx is not None:
        s = as_audio(sfx)
        s = s[:, :n] if s.shape[1] >= n else np.hstack([s, np.zeros((2, n - s.shape[1]))])
        s = s * db2lin(sfx_gain_db + (voice_ref_lufs + 16.0))
        rep['sfx'] = dict(file=None if isinstance(sfx, np.ndarray) else str(sfx), peak_dbfs=meter.sample_peak_db(s),
                          gain_db=sfx_gain_db + voice_ref_lufs + 16.0)
    else:
        s = np.zeros_like(v)
        rep['sfx'] = None

    # ---- 4. master -------------------------------------------------------------------
    pre = hp(v + b_d + s, 25.0, 2)
    fade = np.ones(n)
    ni, no = smp(0.003), smp(0.05)
    fade[:ni] = rc_ramp(ni)
    fade[-no:] = rc_ramp(no)[::-1]
    ceiling = ceiling_dbtp - 0.3
    G = target_lufs - meter.integrated(pre)
    clip_thr = None if master_clip_dbfs is None else 10 ** (master_clip_dbfs / 20.0)
    for attempt in range(3):
        for _ in range(8):
            x = pre * db2lin(G)
            if clip_thr is not None:
                x = x + lp0(softclip_os(x, thresh=clip_thr) - x, 8000.0, 4)
            y, gl = limiter(x, ceiling, look=0.005, rel=0.06)
            y = y * fade
            I = meter.integrated(y)
            if abs(I - target_lufs) < 0.02:
                break
            G += target_lufs - I
        if out_path is None:
            break
        write_wav(out_path, y, bits=24)
        eb = _ffmpeg_eb(out_path)
        if eb['TP_dBTP'] is not None and eb['TP_dBTP'] <= ceiling_dbtp:
            break
        ceiling -= (eb['TP_dBTP'] - ceiling_dbtp) + 0.1
    grl = -20 * np.log10(gl)
    clip_info = {}
    if clip_thr is not None:
        x = pre * db2lin(G)
        xc = x + lp0(softclip_os(x, thresh=clip_thr) - x, 8000.0, 4)
        up = np.max(np.abs(upsample(x, 4)), axis=0)
        clip_info = dict(clip_threshold_dbfs=master_clip_dbfs,
                         clip_ms_active=float(np.sum(up > clip_thr) / (4 * SR) * 1000),
                         clip_tp_reduction_db=meter.true_peak_db(x) - meter.true_peak_db(xc))
    rep['master'] = dict(makeup_db=G, **clip_info, limiter_ceiling_dbtp=ceiling, limiter_gr_db_max=float(grl.max()),
                         limiter_gr_db_p99=float(np.percentile(grl, 99)),
                         limiter_ms_over_1db=float(np.sum(grl > 1.0) / SR * 1000.0),
                         limiter_ms_over_3db=float(np.sum(grl > 3.0) / SR * 1000.0))
    rep['output'] = dict(file=out_path, **_measure(y, out_path))
    rep['output']['pass_target'] = (abs(rep['output'].get('I_LUFS', rep['output']['own_I_LUFS']) - target_lufs) <= 0.5
                                    and (rep['output'].get('TP_dBTP') or rep['output']['own_TP_dBTP']) <= ceiling_dbtp)
    if stems_dir:
        os.makedirs(stems_dir, exist_ok=True)
        gm = db2lin(G)
        write_wav(os.path.join(stems_dir, 'voice_processed.wav'), v * gm, bits='float')
        write_wav(os.path.join(stems_dir, 'bgm_ducked.wav'), b_d * gm, bits='float')
        write_wav(os.path.join(stems_dir, 'sfx.wav'), s * gm, bits='float')
        t = np.arange(0, n, smp(0.01))
        with open(os.path.join(stems_dir, 'duck_gain.json'), 'w') as f:
            json.dump(dict(hop_s=0.01, duck_db=[round(float(duck_db * env[i] + (0 if not pocket_db else 0)), 3)
                                                 for i in t]), f)
    rep['_curves'] = dict(t=np.arange(n)[::smp(0.01)] / SR, duck_db=duck_db * env[::smp(0.01)])
    if report_path:
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({k: v_ for k, v_ in rep.items() if not k.startswith('_')}, f, ensure_ascii=False, indent=1,
                      default=float)
    return rep


def measure_file(path):
    """ffmpeg ebur128 + own meter for any file (decoded to 48 kHz stereo)."""
    y = as_audio(path)
    if not str(path).lower().endswith('.wav'):
        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        write_wav(tmp, y, bits='float')
        d = _measure(y, tmp)
        os.unlink(tmp)
        return d
    return _measure(y, path)
