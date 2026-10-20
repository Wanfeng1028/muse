"""旁白按窗口贴轨 + BGM ducking → 混成母带（「密度流 + 旁白」形态的第 2 步）。

用法：
    python mix_audio.py --timing audio/timing.json --bgm assets/bgm.wav \
        --total 60 --out film/assets/mix.wav

设计：
- 旁白按 timing.json 的窗口起点 + 段内居中偏移落位（避免贴脸开头，也避免溢出窗口）。
- 旁白轨单独存 `--vo-out`（默认 assets/vo.wav），供验收探针检验"人声确实存在"。
- 母带 `--out` = BGM(ducking) + VO，交渲染用。
- BGM 在有旁白处自动压低（ducking），旁白间隙回到基准电平；用平滑包络避免硬切。

踩坑：
- **edge-tts 输出 24kHz 单声道 mp3**，与 BGM 的 44.1kHz 不同，必须重采样（本脚本内置线性重采样）。
- **时长必须显式传入**：不要靠"读 BGM 长度"推断片长，否则 BGM 比片子短时旁白会被截断。
- **削波检查必须有**：VO + BGM 叠加很容易过 1.0，峰值超 0.97 会自动整体归一。
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import soundfile as sf

SR = 44100
VO_GAIN = 1.0
BGM_BASE = 0.42          # 无人声时 BGM 电平
BGM_DUCK = 0.16          # 有人声时压到的电平（相对 BGM_BASE 约 -8.4dB）
DUCK_FADE = 0.28         # ducking 淡入淡出时长


def load_audio(path, stereo=False):
    """读 wav/mp3，统一重采样到 SR、float32、二维。"""
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    if sr != SR:
        # 线性重采样（音质足够：只做人声贴轨）
        n = int(round(len(y) * SR / sr))
        idx = np.arange(n) * (sr / SR)
        i0 = np.floor(idx).astype(np.int64)
        i1 = np.minimum(i0 + 1, len(y) - 1)
        frac = (idx - i0)[:, None]
        y = (y[i0] * (1 - frac) + y[i1] * frac).astype(np.float32)
    if stereo and y.shape[1] == 1:
        y = np.repeat(y, 2, axis=1)
    return y


def smooth_env(voiced, n):
    """人声包络平滑（两次 box filter ≈ 三角核），避免 ducking 硬切。"""
    fade = max(1, int(DUCK_FADE * SR))
    ker = np.ones(fade, dtype=np.float32) / fade
    env = np.convolve(voiced, ker, mode="same")
    env = np.convolve(env, ker, mode="same")
    return np.clip(env * 2.2, 0, 1)[:n]


def main():
    ap = argparse.ArgumentParser(description="旁白贴轨 + BGM ducking 混音")
    ap.add_argument("--timing", default="audio/timing.json")
    ap.add_argument("--bgm", default="assets/bgm.wav")
    ap.add_argument("--total", type=float, default=None,
                    help="片长（秒）。不给则读 timing.json 的 total")
    ap.add_argument("--out", default="film/assets/mix.wav", help="母带输出")
    ap.add_argument("--vo-out", default="assets/vo.wav", help="旁白轨输出（探针用）")
    ap.add_argument("--bgm-base", type=float, default=BGM_BASE)
    ap.add_argument("--bgm-duck", type=float, default=BGM_DUCK)
    ap.add_argument("--vo-gain", type=float, default=VO_GAIN)
    a = ap.parse_args()

    t = json.load(open(a.timing, encoding="utf-8"))
    segs = t["segments"]
    dur = a.total if a.total is not None else float(t.get("total", 60.0))
    n = int(dur * SR)

    vo_mono = np.zeros(n, dtype=np.float32)
    voiced = np.zeros(n, dtype=np.float32)

    print(f"片长 {dur}s / 旁白 {len(segs)} 段")
    print(f"{'镜':<5}{'VO起':<9}{'VO止':<9}{'段内偏移':<10}")
    print("-" * 36)
    for sid, v in segs.items():
        w0, w1 = v["window"]
        d = v["vo_dur"]
        lead = (w1 - w0 - d) / 2.0
        lead = max(0.12, min(lead, 1.2))     # 贴脸也留 0.12s 起音
        start = w0 + lead
        start = min(start, w1 - d)           # 不许溢出窗口

        y = load_audio(v["vo_file"])[:, 0] * a.vo_gain
        i0 = int(start * SR)
        i1 = min(n, i0 + len(y))
        if i1 > i0:
            vo_mono[i0:i1] += y[: i1 - i0]
            voiced[i0:i1] = 1.0
        print(f"{sid:<5}{start:<9.2f}{start+d:<9.2f}{lead:<10.2f}")

    env = smooth_env(voiced, n)
    gain = a.bgm_base * (1 - env) + a.bgm_duck * env

    bgm = load_audio(a.bgm, stereo=True)
    m = min(len(bgm), n)
    bgm = bgm[:m]
    if m < n:
        bgm = np.vstack([bgm, np.zeros((n - m, bgm.shape[1]), dtype=np.float32)])
    bgm = bgm * gain[:, None]

    d1 = os.path.dirname(os.path.abspath(a.vo_out))
    if d1:
        os.makedirs(d1, exist_ok=True)
    sf.write(a.vo_out, vo_mono, SR, subtype="PCM_16")

    mix = bgm.copy()
    mix[:, 0] += vo_mono
    if mix.shape[1] > 1:
        mix[:, 1] += vo_mono
    peak = float(np.max(np.abs(mix)))
    if peak > 0.97:
        mix *= 0.97 / peak
        print(f"\n母线峰值 {peak:.3f} 偏高，已整体归一到 0.97")

    d2 = os.path.dirname(os.path.abspath(a.out))
    if d2:
        os.makedirs(d2, exist_ok=True)
    sf.write(a.out, mix, SR, subtype="PCM_16")

    clipped = float(np.mean(np.abs(mix) >= 0.999))
    duck_db = 20 * math.log10(a.bgm_base / a.bgm_duck) if a.bgm_duck > 0 else 0
    print(f"\n旁白轨 -> {a.vo_out}（峰值 {np.max(np.abs(vo_mono)):.3f}）")
    print(f"母带   -> {a.out}（峰值 {np.max(np.abs(mix)):.3f}，削波率 {clipped:.5f}）")
    print(f"BGM 电平：无人声 {a.bgm_base} / 有人声 {a.bgm_duck}（ducking {duck_db:.1f}dB）")
    if clipped > 0.0001:
        print("警告：削波率偏高，降 --bgm-base 或 --vo-gain。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
