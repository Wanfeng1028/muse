#!/usr/bin/env python3
"""Motion Video sound + delivery CLI.

Run with the venv made by setup.sh:  .motion/venv/bin/python <skill>/scripts/motion.py <command> ...

Commands:
  beats  TRACK                                  beat grid of a music track as JSON on stdout
                                                (needs librosa: setup.sh --beats)
  sfx    EVENTS.json DUR WORK [--music calm|energetic|none] [--samples DIR]
                                                synthesize an SFX track (+ optional music bed)
                                                -> WORK/sfx.wav, WORK/music.wav
  mix    RENDER.mp4 OUT.mp4 [--music M] [--sfx S] [--voice V] [--fade SEC]
                                                music-led mix (music -20, SFX -22, voice on top
                                                with the music ducked), two-pass loudnorm -14,
                                                video re-encoded to yuv420p bt709
  sheet  VIDEO OUT.png [--fps 2] [--width 270] [--cols 6]
                                                contact sheet of the whole video
  strip  VIDEO T OUT.png [--n 12] [--width 320] N consecutive frames from time T (fast action)
  qa     VIDEO                                  duration, size, pixel format, loudness, peak

SFX types: pop, click, shutter, whoosh, swipe, fuwa, wind, bell (synthesized); cash, money and
anything else need a real sample named <type>.wav in --samples DIR (it also overrides a synth).
"""
import argparse, json, os, re, subprocess, sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 48000


def sh(cmd, capture=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd[:6])}...\n{r.stderr[-2000:]}")
    return (r.stdout + r.stderr) if capture else None


def ffmpeg(*args):
    sh(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args])


def probe(path, entries, stream=None):
    cmd = ['ffprobe', '-v', 'error']
    if stream:
        cmd += ['-select_streams', stream]
    out = sh(cmd + ['-show_entries', entries, '-of', 'default=nw=1', path], True)
    return dict(line.split('=', 1) for line in out.strip().splitlines() if '=' in line)


def duration(path):
    return float(probe(path, 'format=duration')['duration'])


def lufs(path):
    out = sh(['ffmpeg', '-hide_banner', '-i', path, '-af', 'ebur128=peak=true:framelog=quiet', '-f', 'null', '-'], True)
    i = re.findall(r'I:\s+(-?[\d.]+) LUFS', out)
    p = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', out)
    return float(i[-1]) if i else None, float(p[-1]) if p else None


def read_mono(path):
    sr, a = wavfile.read(path)
    a = a.astype(np.float64)
    if a.ndim > 1:
        a = a.mean(1)
    peak = np.abs(a).max()
    return sr, a / peak if peak > 1.5 else a


# ---------------------------------------------------------------- beats
def cmd_beats(a):
    try:
        import librosa
    except ImportError:
        sys.exit('librosa is not installed: run setup.sh --beats (or .motion/venv/bin/pip install librosa)')
    y, sr = librosa.load(a.track, sr=None, mono=True)
    tempo, frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
    beats = librosa.frames_to_time(frames, sr=sr).round(3).tolist()
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    peaks = librosa.util.peak_pick(onset, pre_max=3, post_max=3, pre_avg=3, post_avg=5, delta=0.5, wait=10)
    json.dump({
        'bpm': float(np.atleast_1d(tempo)[0]),
        'beats': beats,
        'downbeats': beats[::4],
        'hits': librosa.frames_to_time(peaks, sr=sr).round(3).tolist(),
    }, sys.stdout, indent=1)
    print()


# ---------------------------------------------------------------- sound synthesis
def _lp(x, f, o=2): return sosfilt(butter(o, f, 'low', fs=SR, output='sos'), x)
def _hp(x, f, o=2): return sosfilt(butter(o, f, 'high', fs=SR, output='sos'), x)
def _bp(x, lo, hi, o=2): return sosfilt(butter(o, [lo, hi], 'band', fs=SR, output='sos'), x)
def _env(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(t / a, 1) * np.exp(-t / d)


def synth(kind, rng):
    n = lambda s: int(s * SR)
    noise = lambda s: rng.standard_normal(n(s))
    if kind == 'pop':
        N = n(0.09); t = np.arange(N) / SR; f = 900 * np.exp(-t / 0.03) + 260
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(N, 0.001, 0.025) + _hp(noise(0.09), 3000) * _env(N, 0.0005, 0.003) * 0.25
    if kind == 'click':
        N = n(0.04); return _hp(noise(0.04), 2500) * _env(N, 0.0003, 0.004) * 0.8 + np.sin(2 * np.pi * 3200 * np.arange(N) / SR) * _env(N, 0.0005, 0.006) * 0.3
    if kind == 'shutter':
        a_ = _bp(noise(0.05), 1500, 9000) * _env(n(0.05), 0.0005, 0.008)
        out = np.zeros(n(0.16)); out[:len(a_)] += a_; out[n(0.07):n(0.07) + len(a_)] += a_ * 0.8
        return out
    if kind in ('whoosh', 'swipe', 'fuwa', 'wind'):
        dur = {'whoosh': 0.5, 'swipe': 0.25, 'fuwa': 0.42, 'wind': 1.3}[kind]
        lo, hi = {'whoosh': (300, 3000), 'swipe': (1500, 9000), 'fuwa': (250, 1800), 'wind': (150, 1200)}[kind]
        N = n(dur); t = np.arange(N) / SR
        shape = np.sin(np.pi * t / dur) ** (1.5 if kind != 'swipe' else 0.8)
        x = _bp(noise(dur), lo, hi)
        if kind in ('fuwa', 'wind'):  # slow gusty wobble
            x *= 1 + 0.35 * np.sin(2 * np.pi * (3 if kind == 'fuwa' else 1.3) * t)
        return x * shape * 0.5
    if kind == 'bell':
        N = n(1.2); t = np.arange(N) / SR
        return sum(g * np.sin(2 * np.pi * f * t) * np.exp(-t / d) for f, g, d in
                   [(1760, 1, 0.5), (2640, 0.5, 0.35), (3520, 0.3, 0.2), (5280, 0.15, 0.1)]) * np.minimum(t / 0.002, 1) * 0.4
    return None  # cash, money, ...: need real samples


def music(dur, mood):
    N = int(SR * dur); rng = np.random.default_rng(3)
    bpm = 84 if mood == 'calm' else 112; beat = 60 / bpm
    note = lambda m: 440 * 2 ** ((m - 69) / 12)
    prog = [[50, 53, 57, 60, 64], [46, 50, 53, 57, 62], [41, 48, 53, 57, 60], [48, 52, 55, 62, 64]]
    out = np.zeros(N)

    def add(x, t, g):
        i = int(t * SR); j = min(N, i + len(x))
        if i < N: out[i:j] += x[:j - i] * g
    for b in range(int(np.ceil(dur / (4 * beat)))):
        ch = prog[b % 4]; t0 = b * 4 * beat; n = int(4 * beat * SR); t = np.arange(n) / SR
        pad = sum(np.sin(2 * np.pi * note(m) * t + 0.3 * np.sin(2 * np.pi * 0.3 * t)) for m in ch)
        add(_lp(pad, 1400 if mood == 'calm' else 1800) * np.minimum(t / 0.4, 1) * np.minimum((4 * beat - t) / 0.3, 1), t0, 0.07)
        steps = [0, 2, 3, 4] if mood == 'calm' else [0, 2, 3, 4, 3, 2, 4, 1]
        for k, idx in enumerate(steps):
            nn = int(0.6 * SR); tt = np.arange(nn) / SR
            add(np.sin(2 * np.pi * note(ch[idx] + 12) * tt) * _env(nn, 0.004, 0.25 if mood == 'calm' else 0.12),
                t0 + k * (4 * beat / len(steps)), 0.08)
        nn = int(2 * beat * SR); tt = np.arange(nn) / SR
        add(np.sin(2 * np.pi * note(ch[0] - 12) * tt) * _env(nn, 0.02, 0.8), t0, 0.15)
        if mood != 'calm':
            for k in range(4):
                if k % 2 == 0:
                    nn = int(0.3 * SR); tt = np.arange(nn) / SR; f = 50 + 90 * np.exp(-tt / 0.04)
                    add(np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(nn, 0.002, 0.12), t0 + k * beat, 0.5)
                else:
                    add(_hp(_lp(rng.standard_normal(int(0.2 * SR)), 4000), 900) * _env(int(0.2 * SR), 0.001, 0.05), t0 + k * beat, 0.2)
    out *= np.clip(np.minimum(np.arange(N) / SR / 1.0, (dur - np.arange(N) / SR) / 0.8), 0, 1)
    return out / (np.abs(out).max() + 1e-9) * 0.9


def cmd_sfx(a):
    os.makedirs(a.work, exist_ok=True)
    events = json.load(open(a.events))  # [{"t":0.0,"type":"whoosh","gain":1.0}, ...]
    dur = float(a.dur); N = int(dur * SR); rng = np.random.default_rng(7)
    track = np.zeros(N); skipped = []
    for ev in events:
        kind = ev['type']; x = None
        if a.samples:
            for ext in ('.wav', '.mp3', '.m4a', '.aiff'):
                p = os.path.join(a.samples, kind + ext)
                if os.path.exists(p):
                    tmp = os.path.join(a.work, f'_s_{kind}.wav')
                    ffmpeg('-i', p, '-ac', '1', '-ar', str(SR), tmp); _, x = read_mono(tmp); os.remove(tmp); break
        if x is None:
            x = synth(kind, rng)
        if x is None:
            skipped.append(kind); continue
        x = x / (np.abs(x).max() + 1e-9) * ev.get('gain', 1.0)
        i = int(max(0, ev['t'] - 0.01) * SR); j = min(N, i + len(x))
        if i < N: track[i:j] += x[:j - i]
    track /= (np.abs(track).max() + 1e-9) * 1.05
    wavfile.write(os.path.join(a.work, 'sfx.wav'), SR, np.stack([track, track], 1).astype(np.float32))
    print('wrote sfx.wav' + (f"; no sample for {sorted(set(skipped))} (add <type>.wav files to a --samples dir)" if skipped else ''))
    if a.music != 'none':
        wavfile.write(os.path.join(a.work, 'music.wav'), SR, np.stack([music(dur, a.music)] * 2, 1).astype(np.float32))
        print(f'wrote music.wav ({a.music})')


# ---------------------------------------------------------------- mix + deliver
def cmd_mix(a):
    if not (a.music or a.sfx or a.voice):
        sys.exit('mix needs at least one of --music, --sfx, --voice')
    dur = duration(a.render)
    inputs = ['-i', a.render]; parts = []; mixin = []

    def add(path):
        inputs.extend(['-i', path]); return len(inputs) // 2 - 1
    if a.voice:
        v = add(a.voice)
        parts.append(f'[{v}:a]loudnorm=I=-16:TP=-2,aformat=channel_layouts=stereo,asplit=2[v][vk]')
        mixin.append('[v]')
    if a.music:
        m = add(a.music)
        parts.append(f'[{m}:a]loudnorm=I={-26 if a.voice else -20}:TP=-4,aformat=channel_layouts=stereo[m0]')
        if a.voice:
            parts.append('[m0][vk]sidechaincompress=threshold=0.04:ratio=4:attack=20:release=350[m]')
        else:
            parts.append('[m0]anull[m]')
        mixin.append('[m]')
    elif a.voice:
        parts.append('[vk]anullsink')
    if a.sfx:
        s = add(a.sfx)
        parts.append(f'[{s}:a]loudnorm=I=-22:TP=-3,aformat=channel_layouts=stereo[s]'); mixin.append('[s]')
    fade = f',afade=t=out:st={max(0, dur - a.fade):.3f}:d={a.fade}' if a.fade > 0 else ''
    graph = ';'.join(parts) + ';' + ''.join(mixin) + \
        f'amix=inputs={len(mixin)}:normalize=0:duration=longest,apad,atrim=0:{dur:.3f}{fade}[mx]'
    work = os.path.dirname(os.path.abspath(a.out)); os.makedirs(work, exist_ok=True)
    p1 = os.path.join(work, '_mix1.txt'); open(p1, 'w').write(graph + ';[mx]loudnorm=I=-14:TP=-1.5:LRA=9:print_format=json')
    out = sh(['ffmpeg', '-hide_banner', *inputs, '-filter_complex_script', p1, '-f', 'null', '-'], True)
    d = json.loads(re.findall(r'\{[^{}]*"input_i"[^{}]*\}', out)[-1])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=9:measured_I={d['input_i']}:measured_TP={d['input_tp']}:"
          f"measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}:offset={d['target_offset']}:linear=true")
    p2 = os.path.join(work, '_mix2.txt'); open(p2, 'w').write(graph + f';[mx]{ln}[out]')
    # Remotion writes full-range yuvj420p; players expect limited-range yuv420p tagged bt709.
    ffmpeg(*inputs, '-filter_complex_script', p2, '-map', '0:v', '-map', '[out]',
           '-vf', 'scale=in_range=full:out_range=tv,format=yuv420p',
           '-c:v', 'libx264', '-crf', '17', '-preset', 'slow', '-pix_fmt', 'yuv420p',
           '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
           '-c:a', 'aac', '-b:a', '192k', '-ar', str(SR), '-movflags', '+faststart', '-shortest', a.out)
    os.remove(p1); os.remove(p2)
    i, p = lufs(a.out)
    print(f'wrote {a.out}: {i} LUFS, peak {p} dBFS')


def cmd_sheet(a):
    d = duration(a.video)
    n = max(1, int(d * a.fps)); rows = int(np.ceil(n / a.cols))
    ffmpeg('-i', a.video, '-vf', f'fps={a.fps},scale={a.width}:-2,tile={a.cols}x{rows}', '-frames:v', '1', a.out)
    print(f'wrote {a.out} ({n} frames, {1 / a.fps:.2f}s apart, left→right, top→bottom)')


def cmd_strip(a):
    ffmpeg('-ss', str(a.t), '-i', a.video, '-vf', f'scale={a.width}:-2,tile={a.n}x1', '-frames:v', '1', a.out)
    print(f'wrote {a.out} ({a.n} consecutive frames from {a.t}s)')


def cmd_qa(a):
    v = probe(a.video, 'stream=width,height,pix_fmt,r_frame_rate,color_space', 'v:0')
    d = duration(a.video)
    i, p = lufs(a.video)
    print(f"{a.video}: {v.get('width')}x{v.get('height')} @ {v.get('r_frame_rate')} fps, {d:.2f}s")
    print(f"pixel format {v.get('pix_fmt')} / {v.get('color_space')} (want yuv420p / bt709)")
    print(f"loudness {i} LUFS (target -14 ±1), peak {p} dBFS (want ≤ -1)")


def main():
    P = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    S = P.add_subparsers(dest='cmd', required=True)
    s = S.add_parser('beats'); s.add_argument('track'); s.set_defaults(f=cmd_beats)
    s = S.add_parser('sfx'); s.add_argument('events'); s.add_argument('dur'); s.add_argument('work')
    s.add_argument('--music', default='none', choices=['none', 'calm', 'energetic']); s.add_argument('--samples', default=''); s.set_defaults(f=cmd_sfx)
    s = S.add_parser('mix'); s.add_argument('render'); s.add_argument('out'); s.add_argument('--music'); s.add_argument('--sfx'); s.add_argument('--voice')
    s.add_argument('--fade', type=float, default=0.8); s.set_defaults(f=cmd_mix)
    s = S.add_parser('sheet'); s.add_argument('video'); s.add_argument('out'); s.add_argument('--fps', type=float, default=2)
    s.add_argument('--width', type=int, default=270); s.add_argument('--cols', type=int, default=6); s.set_defaults(f=cmd_sheet)
    s = S.add_parser('strip'); s.add_argument('video'); s.add_argument('t', type=float); s.add_argument('out')
    s.add_argument('--n', type=int, default=12); s.add_argument('--width', type=int, default=320); s.set_defaults(f=cmd_strip)
    s = S.add_parser('qa'); s.add_argument('video'); s.set_defaults(f=cmd_qa)
    a = P.parse_args(); a.f(a)


if __name__ == '__main__':
    main()
