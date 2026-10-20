"""生成 60s+ 长片用的合成音轨（无版权、无采样、纯 stdlib 可复现）。

拆书 / 知识长片的默认 BGM。六镜结构驱动段落密度，音乐随叙事呼吸：

  hook       钩子：kick 每拍 + hat 每半拍 + 拨弦（密度最高）
  expert     定义/专长：撤 hat，留 kick + bass（进入解释）
  leverage   机制/杠杆：重新加 hat + 拨弦（密度回升）
  compound   策略/复利：kick 每拍 + bass 每 2 拍（稳定推进）
  happiness  结论/幸福：hat 减半（安静下来）
  close      收尾主张：撤 hat、kick 每 2 拍（让主张落地）

**SECTIONS 表要跟着你的镜窗改**，否则节奏和画面讲不到一起。

只用 Python stdlib（wave/math/random），可复现。blip 音色是刻意的"知识感"点状织体。

用法：
    python generate_bgm_longform.py --dur 60 --bpm 100 --out assets/bgm.wav
"""
import argparse
import math
import os
import random
import struct
import wave

SR = 44100
random.seed(29)


def kick(t):
    """Decaying 52 Hz sine, 0.30 s."""
    if t < 0 or t > 0.30:
        return 0.0
    return math.sin(2 * math.pi * 52 * t) * math.exp(-9 * t)


def hat(t):
    """Short noise burst, 0.032 s."""
    if t < 0 or t > 0.032:
        return 0.0
    return (random.random() * 2 - 1) * math.exp(-62 * t)


def bass(t):
    """Low pulse 104 Hz, 0.44 s, softer."""
    if t < 0 or t > 0.44:
        return 0.0
    return math.sin(2 * math.pi * 104 * t) * math.exp(-7 * t) * 0.5


def pluck(t):
    """Bright arpeggio tick 392 Hz, 0.22 s —— 给密集段加一层"知识感"点状织体。"""
    if t < 0 or t > 0.22:
        return 0.0
    return math.sin(2 * math.pi * 392 * t) * math.exp(-16 * t) * 0.28


# 段落表：(名字, 起点, 终点) —— 改片时同步改这里，与镜窗对齐
SECTIONS = [
    ("hook", 0.0, 8.0),
    ("expert", 8.0, 18.0),
    ("leverage", 18.0, 30.0),
    ("compound", 30.0, 40.0),
    ("happiness", 40.0, 52.0),
    ("close", 52.0, 999.0),
]


def section_of(t):
    for name, a, b in SECTIONS:
        if a <= t < b:
            return name
    return SECTIONS[-1][0]


def sample(t, beat):
    beat_pos = t / beat
    bi = int(beat_pos)
    sec = section_of(t)

    v = 0.0
    # 底鼓：默认每拍；收尾段降到每 2 拍（给结尾留呼吸）
    if sec == "close":
        if bi % 2 == 0:
            v += kick(t - bi * beat) * 0.88
    else:
        v += kick(t - bi * beat) * 0.95

    # 低音：偶数拍
    if bi % 2 == 0:
        gain = 0.48 if sec in ("expert", "happiness", "close") else 0.56
        v += bass(t - bi * beat) * gain

    # 踩镲：只在需要密度的段落
    if sec in ("hook", "leverage", "compound"):
        half = int(beat_pos * 2)
        v += hat(t - half * (beat / 2)) * 0.20

    # 点状拨弦：信息密度最高的两段（钩子 / 杠杆），每半拍一记
    if sec in ("hook", "leverage"):
        half = int(beat_pos * 2)
        note = (half % 4)
        v += pluck(t - half * (beat / 2)) * (1.0 - 0.12 * note)

    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dur", type=float, default=60.0)
    ap.add_argument("--bpm", type=float, default=104.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--gain", type=float, default=0.84,
                    help="总线增益，留 headroom 防削波")
    args = ap.parse_args()

    dur, bpm = args.dur, args.bpm
    beat = 60.0 / bpm
    n = int(SR * dur)

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "assets", "bgm.wav")
    out = os.path.abspath(out)

    left = bytearray()
    right = bytearray()
    for i in range(n):
        t = i / SR
        s = sample(t, beat) * args.gain
        s_r = sample(t + 0.0009, beat) * args.gain
        left += struct.pack('<h', int(max(-1.0, min(1.0, s)) * 32767))
        right += struct.pack('<h', int(max(-1.0, min(1.0, s_r)) * 32767))

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with wave.open(out, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(left + right))
    print(f'wrote {out}  ({dur}s, {bpm} BPM, stereo, gain={args.gain})')


if __name__ == "__main__":
    main()
