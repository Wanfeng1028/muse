#!/usr/bin/env python3
"""
make_beat_grid.py — 从 BGM 生成「真实脉冲」节拍网格（通用版）

为什么单独做成工具：自动 BPM 检测会在真值、2 倍、以及与鼓点无关的候选之间飘
（同一首曲子，librosa.feature.tempo 可能给 143.55，自相关给 69.84）。
把「人工确认过的那条网格」冻结成 JSON，渲染才是确定性的。

本工具的做法：
  1. 用自相关在指定 BPM 区间内找基频（默认 55–110，避开 2 倍频陷阱）
  2. 由此推出 beat / bar；再用 onset 能量在预测位置附近微调相位
  3. 输出带 downbeats / beats 的 JSON，供 index.html 的 onBeat() 使用

用法：
    python3 scripts/make_beat_grid.py assets/bgm-v3.mp3 -o assets/beat-grid-v3.json \\
        --bpm-range 55 110 --trim 0.0 --duration 60
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def analyse(path: Path, bpm_range: tuple[float, float], sr: int = 22050,
            align_to: float | None = None) -> dict:
    import librosa
    y, sr = librosa.load(str(path), sr=sr, mono=True)
    oe = librosa.onset.onset_strength(y=y, sr=sr)
    hop = 512
    frame_s = hop / sr

    # --- 1) 自相关找基频 ---
    x = oe - oe.mean()
    ac = np.correlate(x, x, "full")[len(x) - 1:]
    ac = ac / (ac[0] + 1e-9)
    lo = max(1, int(round((60 / bpm_range[1]) / frame_s)))
    hi = max(lo + 1, int(round((60 / bpm_range[0]) / frame_s)))
    hi = min(hi, len(ac) - 1)
    lag = lo + int(np.argmax(ac[lo:hi]))
    period = lag * frame_s
    bpm = 60.0 / period

    # --- 2) 相位微调：在 ±半个 beat 内找 onset 能量最大的位移 ---
    times = librosa.times_like(oe, sr=sr, hop_length=hop)
    dur = len(y) / sr
    phase_best, score_best = 0.0, -1.0
    for ph in np.arange(0, period, 0.02):
        grid = np.arange(ph, dur, period)
        idx = np.clip(np.searchsorted(times, grid), 0, len(oe) - 1)
        s = float(oe[idx].mean())
        if s > score_best:
            score_best, phase_best = s, float(ph)

    # 微调后的 beat 相位
    phase_best = float(np.arange(0, period, 0.02)[
        int(np.argmax([float(oe[np.clip(np.searchsorted(times, np.arange(ph, dur, period)), 0, len(oe) - 1)].mean())
                       for ph in np.arange(0, period, 0.02)]))])

    # --- 3) 下拍：每 4 拍取一个，相位对齐到能量最高的一拍 ---
    # 注意：4 个候选相位之间存在「哪一拍是真正的小节头」的固有歧义，
    # 需要用 align_to 显式指定（或留空由能量最大者决定）。这是踩坑卡片 #2 的根因之一。
    beats = list(np.arange(phase_best, dur, period))
    if align_to is None:
        bar_phase, score_best = 0.0, -1.0
        for k in range(4):
            g = np.array(beats[k::4])
            if not len(g):
                continue
            idx = np.clip(np.searchsorted(times, g), 0, len(oe) - 1)
            sc = float(oe[idx].mean())
            if sc > score_best:
                score_best, bar_phase = sc, float(g[0])
    else:
        # 选与原参考下拍最接近的那个候选相位
        cands = [float(g[0]) for k in range(4) if len(g := np.array(beats[k::4]))]
        bar_phase = min(cands, key=lambda t: abs(((t - align_to + period / 2) % (period * 4)) - period / 2))
    # 精修：在 ±0.15s 内平移整组下拍，使其落在 onset 峰上
    best_off, best_score = 0.0, -1.0
    for off in np.arange(-0.15, 0.1501, 0.005):
        g = np.arange(bar_phase + off, dur, period * 4)
        if not len(g):
            continue
        idx = np.clip(np.searchsorted(times, g), 0, len(oe) - 1)
        sc = float(oe[idx].mean())
        if sc > best_score:
            best_score, best_off = sc, float(off)
    bar_phase += best_off
    downbeats = list(np.arange(bar_phase, dur, period * 4))

    return {
        "tempo": round(bpm, 5),
        "beat": round(period, 5),
        "bar": round(period * 4, 5),
        "duration": round(dur, 3),
        "downbeats": [round(float(t), 4) for t in downbeats],
        "beats": [round(float(t), 4) for t in beats],
        "phase": round(phase_best, 4),
        "source": path.name,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bgm", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--bpm-range", type=float, nargs=2, default=[55.0, 110.0],
                    help="搜索区间，默认 55–110（避开 2 倍频陷阱）")
    ap.add_argument("--source-note", default="", help="写进 JSON 的来源说明")
    ap.add_argument("--align-to", type=float, default=None,
                    help="把下拍相位对齐到与 T 秒最接近的候选（解决 4 倍相位歧义）")
    args = ap.parse_args()

    grid = analyse(args.bgm, tuple(args.bpm_range), align_to=args.align_to)
    if args.source_note:
        grid["source"] = args.source_note
    args.out.write_text(json.dumps(grid, ensure_ascii=False, indent=1))
    print(f"[ok] {args.out}")
    print(f"     tempo={grid['tempo']} BPM  beat={grid['beat']}s  bar={grid['bar']}s")
    print(f"     beats={len(grid['beats'])}  downbeats={len(grid['downbeats'])}")
    print(f"     first downbeats: {grid['downbeats'][:5]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
