"""Objective checks and plots for rendered audio (we cannot listen, so every
product gets measured and drawn):

* ffmpeg ebur128 (authoritative I / LRA / true peak + 100 ms M/S frame log)
* clipping, DC, first/last sample, non-finite values
* click / discontinuity scan: block LPC residual (whitens predictable music)
  -> outliers vs the local residual RMS, confirmed by a broadband 16-24 kHz
  burst; intended transient onsets (given by the caller) are reported apart
* spectrogram figure (log-frequency spectrogram with labelled marks, linear
  8-24 kHz alias check, long-term spectrum vs pink reference)
* level figure (waveform min/max/RMS, momentary + short-term loudness,
  optional extra curves such as the ducking gain)
Ported from the "在我开口之前" analysis.py and generalised.
"""
import json
import re
import subprocess

import numpy as np
from scipy import signal

from .dsp import SR, smp
from . import meter


# -----------------------------------------------------------------------------
# ffmpeg
# -----------------------------------------------------------------------------
def ffmpeg_ebur128(path):
    cmd = ['ffmpeg', '-hide_banner', '-nostats', '-v', 'verbose', '-i', str(path), '-filter_complex',
           'ebur128=peak=true:framelog=verbose', '-f', 'null', '-']
    p = subprocess.run(cmd, capture_output=True, text=True)
    err = p.stderr
    frames = []
    rx = re.compile(r't:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+|-inf|nan)\s+S:\s*(-?[\d.]+|-inf|nan)\s+'
                    r'I:\s*(-?[\d.]+|-inf|nan)\s+LUFS\s+LRA:\s*([\d.]+)')
    for line in err.splitlines():
        m = rx.search(line)
        if m:
            frames.append([float(v) if v not in ('-inf', 'nan') else -120.0 for v in m.groups()])
    summ = err[err.rfind('Summary:'):]
    I = float(re.search(r'I:\s*(-?[\d.]+|-inf)\s*LUFS', summ).group(1).replace('-inf', '-120'))
    LRA = float(re.search(r'LRA:\s*([\d.]+)\s*LU', summ).group(1))
    tp = re.search(r'Peak:\s*(-?[\d.]+|-inf)\s*dBFS', summ)
    TP = float(tp.group(1)) if tp and tp.group(1) != '-inf' else None
    summary = '\n'.join(l for l in summ.splitlines() if not l.startswith('[out#') and not l.startswith('size='))
    return dict(I=I, LRA=LRA, TP=TP, frames=np.array(frames), summary=summary.strip())


def ffprobe(path):
    p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                        'stream=codec_name,sample_rate,channels,bits_per_sample,duration_ts,duration',
                        '-of', 'json', str(path)], capture_output=True, text=True)
    return json.loads(p.stdout)['streams'][0]


# -----------------------------------------------------------------------------
# checks
# -----------------------------------------------------------------------------
def basic_checks(y):
    r = {}
    r['finite'] = bool(np.isfinite(y).all())
    r['peak_sample_dbfs'] = float(20 * np.log10(np.max(np.abs(y)) + 1e-20))
    r['clipped_samples'] = int(np.sum(np.abs(y) >= 0.99999))
    dc = [float(np.mean(y[0])), float(np.mean(y[1]))]
    r['dc'] = dc
    r['dc_dbfs'] = float(20 * np.log10(max(abs(dc[0]), abs(dc[1])) + 1e-20))
    den = np.sqrt(np.sum(y[0] ** 2) * np.sum(y[1] ** 2))
    r['lr_corr'] = float(np.sum(y[0] * y[1]) / den) if den > 0 else 1.0
    r['first_sample'] = [float(y[0, 0]), float(y[1, 0])]
    r['last_sample'] = [float(y[0, -1]), float(y[1, -1])]
    return r


def lpc_residual(x, order=24, block=2048):
    """block-wise LPC (autocorrelation method) prediction error; the central
    half of each block is kept (hop = block/2)."""
    from scipy.linalg import solve_toeplitz
    n = len(x)
    hop = block // 2
    res = np.zeros(n)
    win = np.hanning(block)
    for s0 in range(-hop // 2, n, hop):
        a0, a1 = max(0, s0), min(n, s0 + block)
        xb = np.zeros(block)
        xb[a0 - s0:a1 - s0] = x[a0:a1]
        F = np.fft.rfft(xb * win, 2 * block)
        r = np.fft.irfft(np.abs(F) ** 2)[:order + 1]
        if r[0] < 1e-14:
            continue
        r[0] *= 1.0 + 1e-6
        try:
            coef = solve_toeplitz(r[:order], r[1:order + 1])
        except Exception:
            continue
        pred = signal.lfilter(np.concatenate([[0.0], coef]), [1.0], xb)
        e = xb - pred
        c0, c1 = s0 + hop // 2, s0 + hop // 2 + hop
        k0, k1 = max(c0, 0), min(c1, n)
        if k1 > k0:
            res[k0:k1] = e[k0 - s0:k1 - s0]
    return res


_HF_SOS = signal.butter(8, 16000, 'high', fs=SR, output='sos')


def hf_burst(x, t):
    """peak of the 16-24 kHz band within +-1 ms (dBFS) and its ratio to the local
    16-24 kHz RMS (+-5..40 ms). A real discontinuity is broadband; a steep but
    band-limited waveform edge is not."""
    c = smp(t)
    a0, a1 = max(0, c - 4800), min(len(x), c + 4800)
    h = signal.sosfiltfilt(_HF_SOS, x[a0:a1])
    k = c - a0
    peak = np.max(np.abs(h[max(0, k - 48):k + 48]))
    bg_parts = np.concatenate([h[max(0, k - 1920):max(0, k - 240)], h[k + 240:k + 1920]])
    bg = np.sqrt(np.mean(bg_parts ** 2)) if len(bg_parts) else 0.0
    return float(20 * np.log10(peak + 1e-15)), float(20 * np.log10((peak + 1e-15) / (bg + 1e-15)))


def click_scan(y, transient_times=(), ratio_thr=9.0, abs_thr=4e-4, guard=3, abs_db=-90.0, rel_db=20.0,
               pre=0.002, post=0.030):
    """-> dict(confirmed=[...], at_transients=[...], band_limited=[...]); each entry
    (t, ch, |residual|, ratio, hf_peak_db, hf_rel_db). Only 'confirmed' entries
    outside the intended transient windows [t-pre, t+post] count as clicks."""
    n = y.shape[1]
    ex = np.zeros(n, bool)
    for t in transient_times:                    # float onset or (t0, t1) span
        if isinstance(t, (tuple, list)):
            a, b = max(0, smp(t[0] - pre)), min(n, smp(t[1] + post))
        else:
            a, b = max(0, smp(t - pre)), min(n, smp(t + post))
        ex[a:b] = True
    w = smp(0.005)
    flags = []
    for ch in range(2):
        e = lpc_residual(y[ch])
        c = np.concatenate([[0.0], np.cumsum(e * e)])
        idx = np.arange(n)
        lo, hi = np.maximum(idx - w, 0), np.minimum(idx + w + 1, n)
        glo, ghi = np.maximum(idx - guard, 0), np.minimum(idx + guard + 1, n)
        tot = (c[hi] - c[lo]) - (c[ghi] - c[glo])
        cnt = (hi - lo) - (ghi - glo)
        loc = np.sqrt(np.maximum(tot, 0) / np.maximum(cnt, 1))
        cand = np.nonzero((np.abs(e) > abs_thr) & (np.abs(e) > ratio_thr * (loc + 1e-12)))[0]
        for i in cand:
            flags.append((i / SR, ch, float(abs(e[i])), float(abs(e[i]) / (loc[i] + 1e-12)), bool(ex[i])))
    flags.sort()
    merged = []
    for f in flags:
        if merged and f[0] - merged[-1][0] < 0.005:
            continue
        merged.append(f)
    out = dict(confirmed=[], at_transients=[], band_limited=[])
    for f in merged:
        pk, rel = hf_burst(y[f[1]], f[0])
        row = (round(f[0], 5), f[1], f[2], f[3], pk, rel)
        if f[4]:
            out['at_transients'].append(row)
        elif pk > abs_db and rel >= rel_db:
            out['confirmed'].append(row)
        else:
            out['band_limited'].append(row)
    return out


def band_levels(y):
    """long-term band energies (dB re the 200-2000 Hz band), mid signal."""
    m = 0.5 * (y[0] + y[1])
    f, P = signal.welch(m, SR, nperseg=8192)

    def band(a, b):
        k = (f >= a) & (f < b)
        return float(10 * np.log10(np.sum(P[k]) + 1e-30))
    ref = band(200, 2000)
    return {'20-60': band(20, 60) - ref, '60-200': band(60, 200) - ref, '2k-5k': band(2000, 5000) - ref,
            '5k-10k': band(5000, 10000) - ref, '10k-16k': band(10000, 16000) - ref,
            '16k-20k': band(16000, 20000) - ref, '20k-24k': band(20000, 24000) - ref}


# -----------------------------------------------------------------------------
# plots
# -----------------------------------------------------------------------------
def _plt():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


def plot_spectrogram(y, path, title='', marks=(), spans=()):
    """marks: [(t, label)], spans: [(t0, t1, label)]."""
    plt = _plt()
    m = 0.5 * (y[0] + y[1])
    dur = len(m) / SR
    nfft = 4096 if dur > 8 else 2048
    hop = max(128, int(nfft / 8 if dur < 20 else nfft / 4))
    f, tt, Z = signal.stft(m, SR, nperseg=nfft, noverlap=nfft - hop, window='hann', boundary=None, padded=False)
    S = 20 * np.log10(np.abs(Z) + 1e-9)
    S -= S.max()
    fig = plt.figure(figsize=(18, 12), dpi=90)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.45, 0.9, 0.8], hspace=0.34)
    ax = fig.add_subplot(gs[0])
    fl = np.geomspace(20, 24000, 420)
    Sl = np.empty((len(fl), S.shape[1]))
    for j in range(S.shape[1]):
        Sl[:, j] = np.interp(fl, f, S[:, j])
    ax.pcolormesh(tt, fl, Sl, shading='auto', cmap='magma', vmin=-100, vmax=0, rasterized=True)
    ax.set_yscale('log')
    ax.set_ylim(20, 24000)
    ax.set_xlim(0, dur)
    ax.set_ylabel('Hz')
    ax.set_title((title + '  |  ' if title else '') + 'spectrogram (mid, log f, dB re max)')
    for i, (t, lab) in enumerate(marks):
        ax.axvline(t, color='w', lw=0.6, ls='--', alpha=0.6)
        if lab:
            ax.text(t, 24000 * (0.62 if i % 2 else 0.36), lab, color='w', fontsize=7, rotation=90, va='top',
                    ha='right')
    for (a, b, lab) in spans:
        ax.axvspan(a, b, color='c', alpha=0.08)
        ax.text((a + b) / 2, 30, lab, color='c', fontsize=8, ha='center')
    ax2 = fig.add_subplot(gs[1])
    im = ax2.imshow(S[f >= 8000], origin='lower', aspect='auto', cmap='magma', vmin=-110, vmax=-20,
                    extent=[tt[0], tt[-1], 8000, 24000], interpolation='nearest')
    ax2.set_xlim(0, dur)
    ax2.set_title('linear 8-24 kHz (alias check: mirrored / descending lines = aliasing)')
    ax2.set_ylabel('Hz')
    ax2.set_xlabel('time (s)')
    for t, _ in marks:
        ax2.axvline(t, color='w', lw=0.5, ls='--', alpha=0.4)
    fig.colorbar(im, ax=ax2, pad=0.01, fraction=0.02)
    ax3 = fig.add_subplot(gs[2])
    fw, P = signal.welch(m, SR, nperseg=8192)
    k = fw > 15
    L = 10 * np.log10(P[k] + 1e-30)
    L -= np.interp(1000, fw[k], L)
    ax3.semilogx(fw[k], L, color='#9db8d3', lw=0.8, label='long-term spectrum (mid)')
    fc3 = 1000 * 2 ** (np.arange(-17, 15) / 3)
    sm = []
    for fc in fc3:
        kk = (fw >= fc * 2 ** (-1 / 6)) & (fw < fc * 2 ** (1 / 6))
        sm.append(10 * np.log10(np.mean(P[kk]) + 1e-30) if np.any(kk) else np.nan)
    sm = np.array(sm)
    sm -= sm[np.argmin(np.abs(fc3 - 1000))]
    ax3.semilogx(fc3, sm, color='#1f4e79', lw=2.0, marker='o', ms=3, label='1/3-octave smoothed')
    ax3.semilogx(fw[k], -3.0 * np.log2(fw[k] / 1000), color='#999', ls='--', lw=1, label='pink (-3 dB/oct)')
    ax3.axvspan(2000, 5000, color='orange', alpha=0.08, label='2-5 kHz (harshness / speech presence)')
    ax3.set_xlim(20, 24000)
    ax3.set_ylim(-80, 25)
    ax3.grid(True, which='both', alpha=0.25)
    ax3.set_xlabel('Hz')
    ax3.set_ylabel('dB re 1 kHz')
    ax3.legend(loc='lower left', fontsize=8)
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)


def plot_levels(y, frames, path, title='', marks=(), curves=None, ref_lines=((-14, 'g', '-14 LUFS'),)):
    """waveform (min/max + RMS) and ebur128 M/S curves; curves = {label: (t, values_db)}."""
    plt = _plt()
    n = y.shape[1]
    dur = n / SR
    fig, axes = plt.subplots(3, 1, figsize=(18, 9), dpi=90, sharex=True,
                             gridspec_kw=dict(height_ratios=[1, 1, 1.3]))
    px = min(3000, n)
    step = max(1, n // px)
    t = np.arange(px) * step / SR
    for ch, ax in enumerate(axes[:2]):
        x = y[ch, :px * step].reshape(px, step)
        ax.fill_between(t, x.min(axis=1), x.max(axis=1), color='#2b5d8a', lw=0)
        r = np.sqrt(np.mean(x ** 2, axis=1))
        ax.fill_between(t, -r, r, color='#8cc0e8', lw=0)
        ax.set_ylim(-1, 1)
        ax.set_ylabel('L' if ch == 0 else 'R')
        ax.axhline(10 ** (-1 / 20), color='r', lw=0.5, ls=':')
        ax.axhline(-10 ** (-1 / 20), color='r', lw=0.5, ls=':')
        for tm, lab in marks:
            ax.axvline(tm, color='#d62728', lw=0.6, ls='--', alpha=0.6)
        ax.grid(True, axis='x', alpha=0.25)
    axes[0].set_title((title + '  |  ' if title else '') + 'waveform (min/max + RMS), red dotted = -1 dBFS')
    ax = axes[2]
    if frames is not None and len(frames):
        ft, M, S = frames[:, 0], frames[:, 1].copy(), frames[:, 2].copy()
        M[M < -70] = np.nan
        S[(S < -70) | (ft < 3.0)] = np.nan
        ax.plot(ft, M, color='#aaaaaa', lw=0.8, label='momentary 400 ms (ffmpeg)')
        ax.plot(ft, S, color='#1f4e79', lw=1.8, label='short-term 3 s (ffmpeg)')
    for lvl, col, lab in ref_lines:
        ax.axhline(lvl, color=col, lw=0.8, ls=':', label=lab)
    if curves:
        ax2 = ax.twinx()
        for i, (lab, (ct, cv)) in enumerate(curves.items()):
            ax2.plot(ct, cv, lw=1.2, color=['#c55a11', '#6a3d9a', '#33a02c'][i % 3], label=lab)
        ax2.set_ylabel('dB (curves)')
        ax2.legend(loc='lower right', fontsize=8)
    for tm, lab in marks:
        ax.axvline(tm, color='#888', lw=0.6, ls=':')
    ax.set_xlim(0, dur)
    ax.set_ylim(-60, -4)
    ax.grid(True, alpha=0.25)
    ax.set_xlabel('time (s)')
    ax.set_ylabel('LUFS')
    ax.legend(loc='lower left', fontsize=8, ncol=3)
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)


# -----------------------------------------------------------------------------
# one-call product analysis
# -----------------------------------------------------------------------------
def analyze(wav_path, prefix, title='', marks=(), spans=(), transients=(), curves=None, extra=None):
    """ebur128 + checks + plots for a written WAV. Writes <prefix>.ebur128.txt,
    <prefix>.spectrogram.png, <prefix>.levels.png, <prefix>.report.json."""
    from .wavio import read_audio
    y = read_audio(wav_path)
    eb = ffmpeg_ebur128(wav_path)
    probe = ffprobe(wav_path)
    basic = basic_checks(y)
    clicks = click_scan(y, transients)
    res = dict(file=str(wav_path), title=title, format=probe, duration_s=y.shape[1] / SR,
               ffmpeg=dict(I_LUFS=eb['I'], LRA_LU=eb['LRA'], TP_dBTP=eb['TP']),
               own_meter=dict(I_LUFS=meter.integrated(y), TP_dBTP=meter.true_peak_db(y), LRA_LU=meter.lra(y)),
               checks=basic, bands_db_re_200_2k=band_levels(y),
               clicks=dict(confirmed=len(clicks['confirmed']), at_intended_transients=len(clicks['at_transients']),
                           band_limited_edges=len(clicks['band_limited']), confirmed_list=clicks['confirmed'][:20]))
    res['pass'] = dict(no_clipping=basic['clipped_samples'] == 0,
                       tp_le_minus1=eb['TP'] is not None and eb['TP'] <= -1.0,
                       dc_below_minus80dbfs=basic['dc_dbfs'] < -80.0,
                       no_confirmed_clicks=len(clicks['confirmed']) == 0,
                       starts_ends_at_zero=max(abs(v) for v in basic['first_sample'] + basic['last_sample']) < 1e-4,
                       finite=basic['finite'])
    if extra:
        res.update(extra)
    with open(prefix + '.ebur128.txt', 'w', encoding='utf-8') as f:
        f.write('ffmpeg -i %s -filter_complex ebur128=peak=true -f null -\n\n' % wav_path)
        f.write(eb['summary'] + '\n')
    plot_spectrogram(y, prefix + '.spectrogram.png', title, marks, spans)
    plot_levels(y, eb['frames'], prefix + '.levels.png', title, marks, curves)
    with open(prefix + '.report.json', 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=float)
    return res
