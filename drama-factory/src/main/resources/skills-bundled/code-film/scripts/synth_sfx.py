"""用纯代码合成一套常用音效，并生成 manifest.json（记录每个音效的时长和峰值时间）。

用法：
  python synth_sfx.py --out public/sfx                  生成全部音效
  python synth_sfx.py --out public/sfx --only whoosh,hit --seed 3
  python synth_sfx.py --measure my_sound.wav other.mp3  测量外部音效的时长和峰值，输出可以贴进 manifest 的条目
"""
import argparse
import json
from pathlib import Path

from _dsp import (
    bandpass_gain, decode_audio, fade, fft_filter, highpass_gain, lowpass_gain,
    normalize, np, peak_time, reverb, setup_stdout, stft_filter, sweep_sine, to_stereo, trim_tail,
    write_wav,
)

SR = 48000


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _pan(x, pos):
    """pos 可以是常数或逐采样数组，0 为最左，1 为最右（等功率声像）。"""
    ang = np.asarray(pos) * np.pi / 2
    return np.stack([x * np.cos(ang), x * np.sin(ang)], axis=1)


def whoosh(rng, dur=1.2, peak_pos=0.55, f_lo=250.0, f_hi=3200.0):
    n = int(dur * SR)
    p_of = lambda tt: np.clip(tt / dur, 0, 1)

    def gain(freqs, tt):
        shape = np.exp(-((p_of(tt) - peak_pos) / 0.28) ** 2)
        return bandpass_gain(freqs, f_lo * (f_hi / f_lo) ** shape, 1.1)

    y = stft_filter(rng.standard_normal(n), SR, gain, n_fft=1024, hop=256)
    p = np.arange(n) / n
    env = np.where(p < peak_pos, (p / peak_pos) ** 2.2, ((1 - p) / (1 - peak_pos)) ** 1.6)
    y = y * env
    return reverb(_pan(y, 0.15 + 0.7 * p), SR, 0.8, 0.15, seed=11)


def hit(rng, dur=0.9):
    t = _t(dur)
    body = sweep_sine(45 + 110 * np.exp(-t * 28), SR) * np.exp(-t * 9)
    nz = fft_filter(rng.standard_normal(len(t)), SR, lambda f: bandpass_gain(f, 2200, 1.3))
    nz = nz / (np.max(np.abs(nz)) + 1e-9)
    y = np.tanh((body * 0.9 + nz * np.exp(-t * 60) * 0.7) * 1.5)
    return reverb(y, SR, 1.0, 0.18, seed=12)


def boom(rng, dur=3.5):
    t = _t(dur)
    body = sweep_sine(30 + 28 * np.exp(-t * 2.5), SR) * np.exp(-t * 1.4)
    rumble = fft_filter(rng.standard_normal(len(t)), SR, lambda f: lowpass_gain(f, 180, 2))
    rumble = rumble / (np.max(np.abs(rumble)) + 1e-9) * np.exp(-t * 2.2) * 0.5
    trans = fft_filter(rng.standard_normal(len(t)), SR, lambda f: bandpass_gain(f, 900, 1.5))
    trans = trans / (np.max(np.abs(trans)) + 1e-9) * np.exp(-t * 40) * 0.4
    y = np.tanh((body + rumble + trans) * 1.6)
    return reverb(y, SR, 2.5, 0.25, seed=13)


def sub_drop(rng, dur=2.0):
    t = _t(dur)
    y = sweep_sine(30 + 60 * np.exp(-t * 3), SR) * np.exp(-t * 1.2)
    return to_stereo(np.tanh(y * 1.3))


def riser(rng, dur=2.5):
    n = int(dur * SR)
    t = np.arange(n) / SR
    p = t / dur

    def gain(freqs, tt):
        q = np.clip(tt / dur, 0, 1)
        return bandpass_gain(freqs, 200 * (6000 / 200) ** (q ** 1.5), 0.9)

    left = stft_filter(rng.standard_normal(n), SR, gain, n_fft=1024, hop=256)
    right = stft_filter(rng.standard_normal(n), SR, gain, n_fft=1024, hop=256)
    tone = sweep_sine(110 * (8 ** p), SR) * p ** 3 * 0.25
    amp = p ** 2.5
    y = np.stack([left * amp + tone, right * amp + tone], axis=1)
    return fade(y, SR, 0.01, 0.015)


def reverse_swell(rng, dur=1.6):
    t = _t(dur)
    src = fft_filter(rng.standard_normal(len(t)), SR, lambda f: bandpass_gain(f, 1500, 1.4))
    src = src / (np.max(np.abs(src)) + 1e-9) * np.exp(-t * 6)
    src += np.sin(2 * np.pi * 220 * t) * np.exp(-t * 4) * 0.4
    wet = reverb(src, SR, 2.0, 0.55, seed=14)[: len(t)]
    return fade(wet[::-1].copy(), SR, 0.02, 0.006)


def tick(rng, dur=0.06):
    t = _t(dur)
    y = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120)
    y += rng.standard_normal(len(t)) * np.exp(-t * 400) * 0.15
    return to_stereo(fade(y, SR, 0.0005, 0.005))


def click(rng, dur=0.04):
    t = _t(dur)
    y = fft_filter(rng.standard_normal(len(t)), SR, lambda f: highpass_gain(f, 3000, 2))
    return to_stereo(fade(y * np.exp(-t * 250), SR, 0.0003, 0.004))


def pop(rng, dur=0.18):
    t = _t(dur)
    y = sweep_sine(280 + 520 * np.exp(-t * 35), SR) * np.exp(-t * 22)
    y += rng.standard_normal(len(t)) * np.exp(-t * 200) * 0.08
    return to_stereo(fade(y, SR, 0.001, 0.01))


def glitch(rng, dur=0.45):
    n = int(dur * SR)
    y = np.zeros((n, 2))
    pos = 0
    while pos < n:
        seg = int(rng.uniform(0.01, 0.04) * SR)
        end = min(n, pos + seg)
        m = end - pos
        tt = np.arange(m) / SR
        kind = rng.integers(0, 3)
        if kind == 0:
            s = np.sign(np.sin(2 * np.pi * rng.uniform(200, 2000) * tt)) * 0.6
        elif kind == 1:
            hold = int(rng.integers(4, 16))
            s = np.repeat(rng.standard_normal(m // hold + 1), hold)[:m]
            s = np.round(s * 3) / 3 * 0.5
        else:
            s = np.zeros(m)
        y[pos:end] = _pan(fade(s, SR, 0.0005, 0.0005), rng.uniform(0.2, 0.8))
        pos = end
    return y


def shimmer(rng, dur=2.2):
    n = int(dur * SR)
    y = np.zeros(n)
    for _ in range(24):
        start = int(rng.uniform(0, 1.2) * SR)
        length = int(rng.uniform(0.3, 0.8) * SR)
        end = min(n, start + length)
        tt = np.arange(end - start) / SR
        partial = np.sin(2 * np.pi * rng.uniform(2000, 7000) * tt) * np.exp(-tt * rng.uniform(4, 9))
        y[start:end] += fade(partial, SR, 0.005, 0.01) * rng.uniform(0.3, 1.0)
    wet = reverb(y, SR, 2.5, 0.4, seed=15)[:n]
    return fade(wet, SR, 0.01, 0.3)


def drone(rng, dur=8.0):
    xf = 1.0
    total = dur + xf
    t = _t(total)
    y = np.zeros(len(t))
    for hz in (55.0, 82.41, 110.0):
        for cents in (-6, 0, 6):
            f = hz * 2 ** (cents / 1200)
            y += 2 * ((f * t + rng.uniform()) % 1.0) - 1
    y = fft_filter(y, SR, lambda f: lowpass_gain(f, 400, 2))
    y *= 0.8 + 0.2 * np.sin(2 * np.pi * t / 4.0)
    n, k = int(dur * SR), int(xf * SR)
    out = y[:n].copy()
    ramp = np.linspace(0, 1, k)
    out[:k] = y[:k] * ramp + y[n:n + k] * (1 - ramp)
    return to_stereo(out)


# 名字：(生成函数, 峰值电平 dBFS, 推荐的对齐方式)
SOUNDS = {
    "whoosh": (lambda r: whoosh(r), -1.0, "peak"),
    "whoosh_fast": (lambda r: whoosh(r, 0.55, 0.45, 400.0, 4500.0), -1.0, "peak"),
    "hit": (hit, -1.0, "peak"),
    "boom": (boom, -1.0, "start"),
    "sub_drop": (sub_drop, -1.0, "start"),
    "riser": (riser, -1.0, "end"),
    "reverse_swell": (reverse_swell, -1.0, "end"),
    "tick": (tick, -8.0, "peak"),
    "click": (click, -10.0, "peak"),
    "pop": (pop, -6.0, "peak"),
    "glitch": (glitch, -4.0, "start"),
    "shimmer": (shimmer, -6.0, "start"),
    "drone": (drone, -6.0, "start"),
}


def measure(paths):
    entries = {}
    for p in paths:
        x = decode_audio(p, SR)
        entries[Path(p).stem] = {
            "file": f"sfx/{Path(p).name}",
            "duration": round(len(x) / SR, 4),
            "peak": round(peak_time(x, SR), 4),
            "align": "peak",
        }
    print(json.dumps(entries, ensure_ascii=False, indent=2))


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="合成音效库")
    ap.add_argument("--out", default="public/sfx", help="输出目录")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", default="", help="只生成这些，逗号分隔")
    ap.add_argument("--prefix", default="sfx/", help="manifest 里的文件路径前缀（相对 public/）")
    ap.add_argument("--measure", nargs="+", help="测量外部音效文件，不生成")
    args = ap.parse_args()

    if args.measure:
        measure(args.measure)
        return

    names = [s for s in args.only.split(",") if s] or list(SOUNDS)
    unknown = [s for s in names if s not in SOUNDS]
    if unknown:
        raise SystemExit(f"未知音效：{unknown}。可选：{list(SOUNDS)}")

    out = Path(args.out)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    for i, name in enumerate(names):
        fn, level, align = SOUNDS[name]
        rng = np.random.default_rng(args.seed * 1000 + i)
        y = normalize(to_stereo(fn(rng)), level)
        if name != "drone" and align != "end":
            y = trim_tail(y, SR)
        write_wav(out / f"{name}.wav", y, SR)
        manifest[name] = {
            "file": f"{args.prefix}{name}.wav",
            "duration": round(len(y) / SR, 4),
            "peak": round(peak_time(y, SR), 4),
            "align": align,
        }
        print(f"[OK] {name:14s} {manifest[name]['duration']:.2f}s  峰值 {manifest[name]['peak']:.3f}s  默认对齐 {align}")

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"manifest 已写入 {manifest_path}")


if __name__ == "__main__":
    main()
