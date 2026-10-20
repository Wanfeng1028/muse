"""用纯代码合成一首有段落结构的配乐，同时输出段落时间图（JSON）。

用法：
  python synth_music.py --mood melancholic --bpm 72 \
      --structure "intro:4,build:8,peak:8,break:2,peak:8,outro:4" \
      --out public/music/bgm.wav --fps 30

段落名决定编配密度：
  intro  只有铺底和零星的拨弦
  build  加入琶音，滤波器逐渐打开，后半段加入镲
  peak   全部乐器：铺底、琶音、低音、鼓
  break  只剩很轻的铺底
  outro  铺底和零星拨弦，逐渐淡出到 0

情绪（--mood）：calm / hopeful / melancholic / tense / epic / tech
"""
import argparse
import json
from pathlib import Path

from _dsp import (
    bandpass_gain, fft_convolve, fft_filter, highpass_gain, lowpass_gain, midi_hz,
    normalize, np, setup_stdout, stft_filter, sweep_sine, write_wav,
)

SR = 44100

# 和弦用相对 C4（MIDI 60）的半音列表表示，root 是低音的音级
MOODS = {
    "calm": dict(bpm=80, bars_per_chord=2, drums="soft", bass="hold", chords=[
        (0, [0, 4, 7, 11]), (9, [-3, 0, 4, 7]), (5, [-7, -3, 0, 4]), (7, [-5, -1, 2, 4])]),
    "hopeful": dict(bpm=96, bars_per_chord=1, drums="full", bass="hold", chords=[
        (0, [0, 4, 7]), (7, [-5, -1, 2]), (9, [-3, 0, 4]), (5, [-7, -3, 0])]),
    "melancholic": dict(bpm=72, bars_per_chord=1, drums="soft", bass="hold", chords=[
        (9, [-3, 0, 4]), (5, [-7, -3, 0]), (0, [-5, 0, 4]), (7, [-5, -1, 2])]),
    "tense": dict(bpm=110, bars_per_chord=1, drums="full", bass="pulse", chords=[
        (9, [-3, 0, 4]), (10, [-2, 2, 5]), (9, [-3, 0, 4]), (4, [-8, -4, -1])]),
    "epic": dict(bpm=120, bars_per_chord=1, drums="full", bass="pulse", chords=[
        (9, [-3, 0, 4]), (5, [-7, -3, 0]), (0, [-5, 0, 4]), (7, [-5, -1, 2])]),
    "tech": dict(bpm=124, bars_per_chord=1, drums="four", bass="pulse", chords=[
        (4, [-8, -5, -1]), (0, [-5, 0, 4]), (7, [-5, -1, 2]), (2, [-10, -6, -3])]),
}

SECTION_NAMES = ("intro", "build", "peak", "break", "outro")


def parse_structure(text):
    out = []
    for part in text.split(","):
        name, _, bars = part.strip().partition(":")
        name = name.strip().lower()
        if name not in SECTION_NAMES:
            raise SystemExit(f"未知段落名 {name!r}，可选：{SECTION_NAMES}")
        if not bars.strip().isdigit() or int(bars) <= 0:
            raise SystemExit(f"段落 {part!r} 的小节数必须是正整数")
        out.append((name, int(bars)))
    return out


def pluck(freq, dur, bright=1.0):
    t = np.arange(int(dur * SR)) / SR
    y = np.zeros(len(t))
    for k in range(1, 9):
        y += np.sin(2 * np.pi * freq * k * (1 + 0.0004 * k * k) * t) / k ** 1.3 * np.exp(-t * (2.5 + 1.2 * k / bright))
    y *= np.minimum(1.0, t / 0.002)
    return y


def kick():
    t = np.arange(int(0.45 * SR)) / SR
    y = sweep_sine(45 + 95 * np.exp(-t * 30), SR) * np.exp(-t * 7)
    y[: int(0.005 * SR)] += np.random.default_rng(1).standard_normal(int(0.005 * SR)) * 0.3
    return np.tanh(y * 1.4)


def snare(rng):
    t = np.arange(int(0.3 * SR)) / SR
    nz = fft_filter(rng.standard_normal(len(t)), SR, lambda f: bandpass_gain(f, 1800, 1.2))
    nz /= np.max(np.abs(nz)) + 1e-9
    return nz * np.exp(-t * 18) * 0.8 + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25) * 0.5


def hat(rng):
    t = np.arange(int(0.12 * SR)) / SR
    nz = fft_filter(rng.standard_normal(len(t)), SR, lambda f: highpass_gain(f, 7000, 2))
    nz /= np.max(np.abs(nz)) + 1e-9
    return nz * np.exp(-t * 45)


def place(buf, sample, at, gain=1.0, pan=0.5):
    i = max(0, int(round(at * SR)))
    if i >= len(buf):
        return
    s = sample[: len(buf) - i] * gain
    buf[i:i + len(s), 0] += s * np.cos(pan * np.pi / 2) * 1.414
    buf[i:i + len(s), 1] += s * np.sin(pan * np.pi / 2) * 1.414


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="合成配乐")
    ap.add_argument("--mood", default="calm", choices=list(MOODS))
    ap.add_argument("--bpm", type=float, default=None, help="默认按情绪取值")
    ap.add_argument("--structure", default="intro:4,build:8,peak:8,outro:4")
    ap.add_argument("--out", default="public/music/bgm.wav")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    mood = MOODS[args.mood]
    bpm = args.bpm or mood["bpm"]
    beat = 60.0 / bpm
    bar = 4 * beat
    sections = parse_structure(args.structure)
    total_bars = sum(b for _, b in sections)
    total = total_bars * bar
    n = int(round(total * SR))
    rng = np.random.default_rng(args.seed)

    # 每个小节所属的段落，以及段落内的进度
    bar_info = []
    for name, bars in sections:
        for i in range(bars):
            bar_info.append((name, i / max(1, bars - 1) if bars > 1 else 1.0, i, bars))

    def energy_at(t):
        b = min(total_bars - 1, int(t / bar))
        name, prog, _, _ = bar_info[b]
        return {"intro": 0.25, "build": 0.35 + 0.45 * prog, "peak": 1.0,
                "break": 0.1, "outro": 0.6 - 0.45 * prog}[name]

    chords = mood["chords"]
    bpc = mood["bars_per_chord"]
    chord_of_bar = lambda b: chords[(b // bpc) % len(chords)]

    # 铺底：失谐锯齿波，按和弦段生成，再做随能量变化的低通
    pad = np.zeros((n, 2))
    t_all = np.arange(n) / SR
    b = 0
    while b < total_bars:
        span_bars = min(bpc - (b % bpc), total_bars - b)
        start, dur = b * bar, span_bars * bar
        rel = min(0.8, bar * 0.5)
        i0, i1 = int(start * SR), min(n, int((start + dur + rel) * SR))
        tt = np.arange(i1 - i0) / SR
        att = min(1.2, dur * 0.25)
        env = np.minimum(1.0, tt / att) * np.where(tt > dur, np.exp(-(tt - dur) / (rel / 3)), 1.0)
        _, notes = chord_of_bar(b)
        for ch, cents in ((0, -7), (1, 7)):
            voice = np.zeros(len(tt))
            for m in notes:
                f = midi_hz(60 + m) * 2 ** (cents / 1200)
                voice += 2 * ((f * tt + rng.uniform()) % 1.0) - 1
                voice += 0.5 * np.sin(2 * np.pi * f / 2 * tt)
            pad[i0:i1, ch] += voice * env * 0.12
        b += span_bars
    for ch in range(2):
        pad[:, ch] = stft_filter(pad[:, ch], SR, lambda f, t: lowpass_gain(f, 450 + 3200 * energy_at(max(0.0, t)) ** 1.5, 2))
    pad_level = np.array([0.5 if bar_info[min(total_bars - 1, int(t / bar))][0] == "break" else 1.0
                          for t in np.arange(0, n, 512) / SR])
    pad *= np.repeat(pad_level, 512)[:n, None]

    arp = np.zeros((n, 2))
    bass = np.zeros((n, 2))
    drums = np.zeros((n, 2))
    k_s, sn_s, h_s = kick(), snare(rng), hat(rng)
    pattern = [0, 1, 2, 3, 4, 3, 2, 1]
    kick_times = []

    for b, (name, prog, idx, bars) in enumerate(bar_info):
        t0 = b * bar
        root, notes = chord_of_bar(b)
        tones = sorted(notes) + [m + 12 for m in sorted(notes)]
        second_half = idx >= bars / 2

        if name in ("intro", "outro", "break"):
            if name != "break" or idx == 0:
                place(arp, pluck(midi_hz(72 + root % 12), 2.0, 0.8), t0, 0.35 if name != "break" else 0.2, 0.45)
        if name in ("build", "peak"):
            vel = 0.3 + 0.5 * prog if name == "build" else 0.85
            for s in range(8):
                m = tones[pattern[s] % len(tones)]
                jitter = rng.uniform(-0.003, 0.003)
                place(arp, pluck(midi_hz(72 + m), 1.2), t0 + s * beat / 2 + jitter,
                      vel * rng.uniform(0.9, 1.1) * 0.35, 0.35 if s % 2 else 0.65)
        if name == "peak" and idx % 2 == 0:
            m = tones[int(rng.integers(0, len(tones)))] + 12
            place(arp, pluck(midi_hz(72 + m), 1.5, 1.5), t0, 0.15, rng.uniform(0.2, 0.8))

        if name == "peak" or (name == "build" and second_half and mood["bass"] == "pulse"):
            bf = midi_hz(36 + root % 12)
            if mood["bass"] == "hold":
                tt = np.arange(int(bar * SR)) / SR
                tone = (np.sin(2 * np.pi * bf * tt) + 0.3 * np.sin(4 * np.pi * bf * tt)) * np.minimum(1, tt / 0.02) * np.exp(-tt * 0.4)
                place(bass, tone, t0, 0.45)
            else:
                tt = np.arange(int(beat / 2 * SR)) / SR
                tone = (np.sin(2 * np.pi * bf * tt) + 0.3 * np.sin(4 * np.pi * bf * tt)) * np.minimum(1, tt / 0.005) * np.exp(-tt * 6)
                for s in range(8):
                    place(bass, tone, t0 + s * beat / 2, 0.4)

        style = mood["drums"]
        if name == "peak" and style != "none":
            beats_with_kick = range(4) if style == "four" else (0, 2)
            for s in beats_with_kick:
                place(drums, k_s, t0 + s * beat, 0.8)
                kick_times.append(t0 + s * beat)
            if style in ("full", "four"):
                for s in (1, 3):
                    place(drums, sn_s, t0 + s * beat, 0.45, 0.52)
            for s in range(8):
                if style == "soft" and s % 2 == 0:
                    continue
                place(drums, h_s, t0 + s * beat / 2, 0.12 if s % 2 else 0.07, 0.62)
        if name == "build" and second_half:
            for s in range(1, 8, 2):
                place(drums, h_s, t0 + s * beat / 2, 0.04 + 0.08 * prog, 0.62)

    if mood["drums"] == "four" and kick_times:
        duck = np.ones(n)
        for kt in kick_times:
            i = int(kt * SR)
            seg = np.arange(min(int(beat * SR), n - i)) / SR
            duck[i:i + len(seg)] = np.minimum(duck[i:i + len(seg)], 1 - 0.35 * np.exp(-seg * 12))
        pad *= duck[:, None]

    # 混响只给铺底和琶音
    send = pad * 0.5 + arp * 0.8
    ir_len = int(2.8 * SR)
    t_ir = np.arange(ir_len) / SR
    wet = np.zeros((n, 2))
    for ch in range(2):
        ir = np.random.default_rng(50 + ch).standard_normal(ir_len) * np.exp(-6.9 * t_ir / 2.8)
        ir = fft_filter(ir, SR, lambda f: lowpass_gain(f, 5000, 1))
        ir /= np.sqrt(np.sum(ir ** 2)) + 1e-12
        wet[:, ch] = fft_convolve(send[:, ch], ir)[:n]

    mix = pad * 0.9 + arp * 0.8 + bass * 0.9 + drums * 0.9 + wet * 0.35

    # 总音量：outro 段逐渐淡出到 0，开头 50ms 淡入
    gain = np.ones(n)
    start_bar = 0
    for name, bars in sections:
        if name == "outro":
            i0, i1 = int(start_bar * bar * SR), int((start_bar + bars) * bar * SR)
            gain[i0:min(n, i1)] = np.linspace(1, 0, min(n, i1) - i0) ** 1.5
        start_bar += bars
    gain[: int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))
    gain[-int(0.05 * SR):] *= np.linspace(1, 0, int(0.05 * SR))
    mix *= gain[:, None]
    mix = np.tanh(mix * 1.2) / np.tanh(1.2)
    mix = normalize(mix, -1.0)

    out = Path(args.out)
    write_wav(out, mix, SR)

    fps = args.fps
    sec_list, cursor = [], 0
    for name, bars in sections:
        s, e = cursor * bar, (cursor + bars) * bar
        sec_list.append({"name": name, "startBar": cursor + 1, "bars": bars,
                         "startSec": round(s, 3), "endSec": round(e, 3),
                         "startFrame": int(round(s * fps)), "endFrame": int(round(e * fps))})
        cursor += bars
    info = {"file": out.name, "mood": args.mood, "bpm": bpm, "fps": fps,
            "framesPerBeat": round(fps * beat, 4), "barFrames": round(fps * bar, 4),
            "durationSec": round(total, 3), "durationInFrames": int(round(total * fps)),
            "sections": sec_list}
    out.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] {out}  {total:.2f}s  {bpm} BPM  每拍 {fps * beat:.2f} 帧  共 {info['durationInFrames']} 帧")
    for s in sec_list:
        print(f"     {s['name']:6s} 第 {s['startBar']:>3} 小节起  {s['startSec']:7.2f}s 到 {s['endSec']:7.2f}s  帧 {s['startFrame']} 到 {s['endFrame']}")
    print(f"段落时间图：{out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
