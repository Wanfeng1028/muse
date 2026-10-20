#!/usr/bin/env python3
"""
teardown_video.py — 宣传片「多维度」拆解器（对标用）

目的：不是看一遍下结论，而是把一支片子拆成 6 个可量化的维度，输出可对比的 JSON。
用于把「参考片 vs 我们的片子」的差异定位到具体维度，而不是笼统说「动效差点意思」。

六维：
  A 结构   —— 场景/镜头切分、时长分布、节奏曲线
  B 运动   —— 全局运动(运镜) vs 局部运动(元素动) 分解；运动覆盖率；死角占比
  C 文字   —— OCR 出屏上文字、出现节奏、字数密度、信息层级
  D 声音   —— 音量轨迹、段落结构、重音位置、语音vs音乐
  E 卡点   —— 用「重音」而不是「拍」衡量切点对齐（关键修正）
  F 配色   —— 主色、饱和度、色彩丰富度、明度分布

用法：
    python3 teardown_video.py <video> --out out.json [--label 名字]
"""
from __future__ import annotations

import argparse, json, subprocess, sys, warnings
from pathlib import Path
import numpy as np
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------- 基础解码
def decode(f: Path, fps: float, w: int, h: int, pix="gray") -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-i", str(f), "-vf", f"fps={fps},scale={w}:{h}",
           "-pix_fmt", pix, "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    ch = 1 if pix == "gray" else 3
    n = len(raw) // (w * h * ch)
    return np.frombuffer(raw, np.uint8)[: n * w * h * ch].reshape(n, h, w, ch)


def audio(f: Path, sr=22050) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def probe(f: Path) -> dict:
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration,bit_rate:stream=codec_type,codec_name,width,height,r_frame_rate",
                        "-of", "json", str(f)], capture_output=True, text=True).stdout
    d = json.loads(o)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    num, den = v["r_frame_rate"].split("/")
    return dict(width=v["width"], height=v["height"], fps=round(float(num)/float(den), 3),
                duration=round(float(d["format"]["duration"]), 3),
                vcodec=v["codec_name"], bitrate_kbps=round(int(d["format"].get("bit_rate", 0))/1000))


# ---------------------------------------------------------------- A 结构
def cuts(frame_diff: np.ndarray, fps: float) -> list[int]:
    """镜头切点（帧索引）。用自适应阈值 + 非极大值抑制。"""
    t = max(frame_diff.mean() + 2.5 * frame_diff.std(), 0.06)
    idx = np.where(frame_diff > t)[0]
    # 抑制相邻（一个切镜可能连续 2 帧超阈）
    out = []
    for i in idx:
        if not out or (i - out[-1]) > fps * 0.15:
            out.append(int(i))
    return out


def dim_structure(frames: np.ndarray, fps: float) -> dict:
    d = np.abs(np.diff(frames[..., 0].astype(np.int16), axis=0)).mean(axis=(1, 2))
    c = cuts(d, fps)
    bounds = [0] + [i + 1 for i in c] + [len(frames)]
    lens = [(b - a) / fps for a, b in zip(bounds[:-1], bounds[1:])]
    lens = [x for x in lens if x >= 0.2]
    lens_a = np.array(lens) if lens else np.array([len(frames)/fps])
    # 节奏曲线：每 5 秒的镜头数
    dur = len(frames) / fps
    bins = np.zeros(int(np.ceil(dur / 5)) + 1)
    for t in [i / fps for i in c]:
        bins[int(t // 5)] += 1
    return dict(
        n_cuts=len(c), n_shots=len(lens),
        avg_shot_s=round(float(lens_a.mean()), 2),
        median_shot_s=round(float(np.median(lens_a)), 2),
        min_shot_s=round(float(lens_a.min()), 2),
        max_shot_s=round(float(lens_a.max()), 2),
        shot_std_s=round(float(lens_a.std()), 2),
        cuts_per_sec=round(len(c) / dur, 3),
        tempo_curve_cuts_per_5s=[int(x) for x in bins],
        _bounds=bounds, _cut_times=[round(i / fps, 2) for i in c],
    )


# ---------------------------------------------------------------- B 运动
def dim_motion(f: Path, fps: float = 12, w: int = 320, h: int = 180) -> dict:
    """全局运动(运镜) 与 局部运动(元素动) 分解。

    用 ffmpeg 解码（OpenCV 对 AV1/HEVC 支持不全，会拿不到帧）→ 再算光流。
    """
    import cv2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-vf",
                          f"fps={fps},scale={w}:{h}", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    n = len(raw) // (w * h)
    if n < 3:
        return {"error": "too few frames decoded", "decoded": n}
    fr = [np.frombuffer(raw, np.uint8)[i * w * h:(i + 1) * w * h].reshape(h, w) for i in range(n)]

    glob, loc, cover, per_pair = [], [], [], []
    for a, b in zip(fr[:-1], fr[1:]):
        flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        # 全局 = 光场中位向量（相机平移/推拉主导）
        med = np.median(flow.reshape(-1, 2), axis=0)
        resid = flow - med
        rmag = np.sqrt((resid ** 2).sum(-1))
        mag = np.sqrt((flow ** 2).sum(-1))
        glob.append(float(np.sqrt((med ** 2).sum())))
        loc.append(float(rmag.mean()))
        # 运动覆盖率：光流幅值显著高的像素占比
        cover.append(float((mag > 0.5).mean()))
        per_pair.append((float(np.abs(b.astype(np.int16) - a.astype(np.int16)).mean()),
                         float(np.sqrt((med ** 2).sum())), float(rmag.mean())))
    p = np.array(per_pair)
    # 死角：帧间差很小的帧对
    dead = (p[:, 0] < 0.15).mean()
    return dict(
        frames_analyzed=len(fr),
        global_motion_mean=round(float(np.mean(glob)), 4),      # 运镜强度
        local_motion_mean=round(float(np.mean(loc)), 4),        # 元素动效强度
        motion_coverage_mean=round(float(np.mean(cover)), 4),   # 有多少画面在动
        dead_pair_ratio=round(float(dead), 4),                  # 近似静止的帧对占比
        local_over_global=round(float(np.mean(loc) / (np.mean(glob) + 1e-6)), 2),
        pixel_diff_mean=round(float(p[:, 0].mean()), 4),
    )


# ---------------------------------------------------------------- C 文字
def dim_text(f: Path, fps: float = 1.0, w: int = 1920) -> dict:
    """OCR 出屏上文字；统计出现节奏与文字量。"""
    import cv2
    tmp = Path("/tmp/_teardown_frames"); tmp.mkdir(exist_ok=True)
    for p in tmp.glob("*.png"):
        p.unlink()
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-vf", f"fps={fps},scale={w}:-1",
                    str(tmp / "f%05d.png")], capture_output=True)
    imgs = sorted(tmp.glob("*.png"))
    texts = []
    for im in imgs:
        t = subprocess.run(["tesseract", str(im), "stdout", "--psm", "6"],
                           capture_output=True, text=True).stdout
        t = " ".join(t.split())
        texts.append(t)
    # 逐秒字数
    wc = [len(t.replace(" ", "")) for t in texts]
    nonempty = [i for i, t in enumerate(texts) if len(t.strip()) >= 3]
    uniq = []
    for t in texts:
        if t and t not in uniq:
            uniq.append(t)
    return dict(
        sampled_seconds=len(texts),
        total_chars=sum(wc),
        char_density_mean=round(float(np.mean(wc)), 1),
        text_coverage_ratio=round(len(nonempty) / max(len(texts), 1), 3),  # 多少比例的时间有字
        text_lines_top=uniq[:25],
    )


# ---------------------------------------------------------------- D 声音
def dim_sound(f: Path, sr: int = 22050) -> dict:
    y = audio(f, sr)
    if not len(y):
        return {"error": "no audio"}
    dur = len(y) / sr
    # 每 0.5s RMS
    win = int(0.5 * sr)
    rms = np.array([float(np.sqrt((y[i:i+win] ** 2).mean())) for i in range(0, len(y) - win, win)])
    db = 20 * np.log10(rms + 1e-6)
    # 用量化动态范围看是否有「音乐段落」起伏
    return dict(
        duration_s=round(dur, 2),
        rms_mean=round(float(np.sqrt((y ** 2).mean())), 4),
        rms_std=round(float(np.std(rms)), 4),
        dynamic_range_db=round(float(np.percentile(db, 95) - np.percentile(db, 5)), 1),
        quiet_ratio=round(float((rms < 0.01).mean()), 3),          # 近乎无声的时间占比
        loud_ratio=round(float((rms > 0.2).mean()), 3),
        rms_curve=[round(float(x), 4) for x in rms[:120]],
        peak=round(float(np.abs(y).max()), 3),
    )


# ---------------------------------------------------------------- E 卡点（关键修正）
def dim_beats(f: Path, cut_times: list[float], sr: int = 22050) -> dict:
    """切点 vs 音乐重音/强拍的偏移。

    修正上一版的问题：不能只看「到最近拍」——拍间距小时任何切点都近乎贴上。
    这里同时给三组参照：
      1) 到「重音(onset 峰)」的距离
      2) 到「强拍(downbeat, 每小节头)」的距离
      3) 归一化：偏移 / 拍间隔
    """
    import librosa
    y = audio(f, sr)
    if not len(y):
        return {"error": "no audio"}
    oenv = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.times_like(oenv, sr=sr)
    # onset 峰（真正的重音事件）
    peaks = librosa.util.peak_pick(oenv, pre_max=3, post_max=3, pre_avg=3, post_avg=5,
                                   delta=0.15, wait=5)
    onset_t = times[peaks]
    # 拍 + 小节头
    tempo, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, units='time')
    tempo = float(np.atleast_1d(tempo)[0])
    period = 60.0 / tempo if tempo > 0 else 0.5
    # downbeats：每 4 拍
    downbeats = beats[::4] if len(beats) >= 4 else beats

    dur = len(y) / sr

    def dists(ref):
        if len(ref) == 0:
            return []
        return [float(min(abs(t - r) for r in ref)) for t in cut_times]

    def chance(n_ref, th):
        """随机基线：参考点每秒 n_ref/dur 个时，随机切点落在 ±th 内的期望概率（近似 2·th·密度）。"""
        if n_ref == 0:
            return None
        return float(min(1.0, 2.0 * th * (n_ref / dur)))

    def stats(ref, th=0.06):
        d = np.array(dists(ref))
        if not len(d):
            return dict(n_ref=0)
        obs = float((d <= th).mean())
        ch = chance(len(ref), th)
        return dict(
            n_ref=len(ref),
            median_dist_s=round(float(np.median(d)), 3),
            ratio_within_th=round(obs, 3),
            chance_baseline=round(ch, 3) if ch is not None else None,
            lift_over_chance=round(obs / ch, 2) if ch and ch > 0 else None,
        )

    return dict(
        tempo_bpm=round(tempo, 1), beat_period_s=round(period, 3),
        duration_s=round(dur, 2), n_cuts_compared=len(cut_times),
        threshold_s=0.06,
        # 三组参照，各自带「随机基线」和「超出基线的倍数」
        vs_onset_accent=stats(onset_t),
        vs_downbeat=stats(downbeats),
        vs_beat=stats(beats),
        beat_offset_over_period=round(float(np.median(np.array(dists(beats))) / period), 3)
            if len(beats) and period else None,
    )


# ---------------------------------------------------------------- F 配色
def dim_color(f: Path, fps: float = 2.0, w: int = 480, h: int = 270) -> dict:
    fr = decode(f, fps, w, h, pix="rgb24")
    if not len(fr):
        return {"error": "no frames"}
    px = fr.reshape(-1, 3).astype(np.float32)
    # 饱和度/明度（HSV）
    mx = px.max(1); mn = px.min(1)
    sat = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0)
    val = mx / 255.0
    # 主色：粗略量化到 4bit/通道后取 top
    q = (px // 32).astype(np.int16)
    key = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    vals, cnts = np.unique(key, return_counts=True)
    order = np.argsort(cnts)[::-1][:6]
    top = []
    for o in order:
        k = int(vals[o]); r, g, b = (k // 64) * 32 + 16, ((k // 8) % 8) * 32 + 16, (k % 8) * 32 + 16
        top.append({"rgb": [r, g, b], "pct": round(float(cnts[o]) / len(key) * 100, 1)})
    # 色彩丰富度：不同量化色的数量占比
    richness = float(len(vals)) / 512.0
    # 逐帧亮度波动（是否所有画面同一个明度）
    lum = fr.mean(axis=(1, 2, 3))
    return dict(
        sat_mean=round(float(sat.mean()), 3), sat_std=round(float(sat.std()), 3),
        val_mean=round(float(val.mean()), 3), val_std=round(float(val.std()), 3),
        color_richness=round(richness, 3),
        lum_frame_std=round(float(lum.std()), 2),
        top_colors=top,
        dominant_pct=top[0]["pct"] if top else None,
    )


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--fps-struct", type=float, default=12)
    ap.add_argument("--skip", default="", help="跳过的维度，逗号分隔：A,B,C,D,E,F")
    args = ap.parse_args()
    skip = set(x.strip().upper() for x in args.skip.split(",") if x.strip())
    f = args.video
    if not f.exists():
        print(f"[fatal] not found: {f}", file=sys.stderr); return 2

    rep = {"file": str(f), "label": args.label or f.stem, "probe": probe(f)}
    # A 需要解码灰度帧
    frames = decode(f, args.fps_struct, 192, 108)
    if "A" not in skip:
        rep["A_structure"] = dim_structure(frames, args.fps_struct)
    if "B" not in skip:
        rep["B_motion"] = dim_motion(f)
    if "C" not in skip:
        rep["C_text"] = dim_text(f)
    if "D" not in skip:
        rep["D_sound"] = dim_sound(f)
    if "E" not in skip:
        ct = rep.get("A_structure", {}).get("_cut_times", [])
        rep["E_beat"] = dim_beats(f, ct)
    if "F" not in skip:
        rep["F_color"] = dim_color(f)

    txt = json.dumps(rep, ensure_ascii=False, indent=1)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(txt); print(f"[written] {args.out}", file=sys.stderr)
    else:
        print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
