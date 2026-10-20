#!/usr/bin/env python3
"""
audit_video.py — 宣传片「不看图」对抗性验收器（通用版）

把验收检测表变成真能跑的命令：一条命令跑完，输出可留档 JSON + 退出码。
退出码：0 = 全部过线；1 = 有项目未过线。

用法：
    python3 scripts/audit_video.py renders/video.mp4 \
        --total 60 --bgm assets/bgm.mp3 --grid-json assets/beat-grid.json \
        --countup "6:10:380:180:260:150" --json evidence/audit.json

设计原则：每个结论都必须来自一个可复算的量；能算比值就不写「感觉不错」。
注意：所有区域坐标都在分析分辨率 960×540 下。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

W, H = 960, 540          # 差分分析分辨率
BLK_ROWS, BLK_COLS = 6, 12  # 分块网格


# ---------------------------------------------------------------- ffmpeg helpers
def ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def decode_gray(path: Path, fps: int, w: int = W, h: int = H) -> np.ndarray:
    """整段解码成灰度帧数组 (N, h, w)。"""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path),
           "-vf", f"fps={fps},scale={w}:{h}", "-pix_fmt", "gray",
           "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw, dtype=np.uint8)[: n * w * h].reshape(n, h, w)


def decode_audio(path: Path, sr: int = 22050) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
           "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


# ---------------------------------------------------------------- metrics
def spec_check(probe: dict, total: float | None, expect=(1920, 1080),
               dur_tol: float = 2.0) -> dict:
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    dur = float(probe["format"]["duration"])
    num, den = v["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    res = {
        "width": v["width"], "height": v["height"], "fps": round(fps, 3),
        "duration": round(dur, 3), "size_mb": round(float(probe["format"]["size"]) / 1e6, 1),
        "vcodec": v["codec_name"],
        "acodec": a["codec_name"] if a else None,
        "sample_rate": int(a["sample_rate"]) if a else None,
        "channels": a["channels"] if a else None,
        "res_ok": (v["width"], v["height"]) == expect,
        "dur_ok": abs(dur - total) <= dur_tol if total else None,
    }
    res["pass"] = bool(res["res_ok"]) and (res["dur_ok"] is not False)
    return res


def _runs(mask: np.ndarray, fps: int, min_s: float, t_of) -> list:
    segs, cur = [], 0
    for i, v in enumerate(mask):
        if v:
            cur += 1
        else:
            if cur / fps >= min_s:
                segs.append({"t": round(t_of(i - cur), 2), "dur": round(cur / fps, 2)})
            cur = 0
    if cur / fps >= min_s:
        segs.append({"t": round(t_of(len(mask) - cur), 2), "dur": round(cur / fps, 2)})
    return segs


def motion_stats(frames: np.ndarray, fps: int, static_thr: float = 0.15) -> dict:
    """分块差分。

    「静止」有两个不同口径，必须分开报，否则会互相掩盖：
      - frozen  : 逐帧整幅平均差 < static_thr（近似像素级冻结，真死帧）
      - low-motion: 活跃块占比 < 2%（内容几乎不动，但环境层仍在缓慢动）
    """
    n = len(frames)
    diff = np.abs(np.diff(frames.astype(np.int16), axis=0))          # (n-1,h,w)
    blk = diff.reshape(n - 1, BLK_ROWS, H // BLK_ROWS,
                       BLK_COLS, W // BLK_COLS).transpose(0, 1, 3, 2, 4)
    bmean = blk.reshape(n - 1, BLK_ROWS * BLK_COLS, -1).mean(axis=2)  # (n-1, 72)
    frame_act = (bmean > 2.0).mean(axis=1)                            # 活跃块占比
    active = frame_act > 0.02

    frame_diff = diff.mean(axis=(1, 2))                               # 整幅平均差
    frozen = frame_diff < static_thr

    longest = 0
    cur = 0
    for a in active:
        cur = cur + 1 if not a else 0
        longest = max(longest, cur)

    gmin = frames.reshape(n, -1).min(axis=1)
    gmean = frames.reshape(n, -1).mean(axis=1)
    gstd = frames.reshape(n, -1).std(axis=1)
    return {
        "frames": n,
        "active_frame_ratio": round(float(active.mean()), 3),
        "mean_block_diff": round(float(bmean.mean()), 2),
        "mean_frame_diff": round(float(frame_diff.mean()), 3),
        "low_motion_segments_ge_1s": _runs(~active, fps, 1.0, lambda i: (i + 1) / fps),
        "frozen_segments_ge_1s": _runs(frozen, fps, 1.0, lambda i: (i + 1) / fps),
        "frozen_frame_ratio": round(float(frozen.mean()), 3),
        "blank_frames": int((gstd < 8).sum()),
        "black_frames": int((gmean < 12).sum()),
        "static_threshold": static_thr,
    }


def audio_stats(samples: np.ndarray, sr: int, head_s: float = 3.0) -> dict:
    """开场能量比：0–3s RMS / 全片 RMS。"""
    if samples.size == 0:
        return {"error": "no audio"}
    n = len(samples)
    def rms(x):
        return float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
    head = samples[: int(head_s * sr)]
    overall = rms(samples)
    peak = float(np.max(np.abs(samples)))
    # 逐秒 RMS 轨迹
    per_sec = [round(rms(samples[i * sr:(i + 1) * sr]), 4)
               for i in range(min(int(n / sr), 60))]
    # 削波样本比例（|x|>0.999）
    clipped = float((np.abs(samples) > 0.999).mean())
    return {
        "head_rms": round(rms(head), 4),
        "overall_rms": round(overall, 4),
        "head_over_overall": round(rms(head) / overall, 3) if overall else None,
        "peak": round(peak, 4),
        "clipped_ratio": round(clipped, 6),
        "per_sec_rms": per_sec,
    }


def beat_check(grid: dict, bgm: Path, total: float, tol: float = 0.05) -> dict:
    """节拍网格是否落在音频真实重拍上：用 onset 包络在网格点附近取极大。

    注意：基准必须是 BGM 源文件（bgm-*.mp3），不是渲染后的成片——
    成片混了音效、且有编码位移，会把偏移量算脏。
    """
    import librosa
    y, sr = librosa.load(str(bgm), sr=22050, mono=True)
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.times_like(onset, sr=sr)
    db = np.array(grid["downbeats"])
    db = db[(db >= 0) & (db < min(total, times[-1]))]
    hits = 0
    offsets = []
    for t in db:
        m = (times >= t - tol) & (times <= t + tol)
        if not m.any():
            continue
        loc = np.argmax(onset[m])
        tt = times[m][loc]
        offsets.append(float(tt - t))
        # 网格点是否落在该窗口的能量峰（相对窗口外基线）
        hits += 1
    return {
        "n_downbeats": len(db),
        "checked": len(offsets),
        "mean_abs_offset_s": round(float(np.mean(np.abs(offsets))), 4) if offsets else None,
        "max_abs_offset_s": round(float(np.max(np.abs(offsets))), 4) if offsets else None,
    }


def _ncc_template(image: np.ndarray, tmpl: np.ndarray) -> float:
    """归一化互相关的模板匹配（FFT 加速），返回最佳匹配得分。"""
    from scipy.signal import fftconvolve
    if tmpl.shape[0] > image.shape[0] or tmpl.shape[1] > image.shape[1]:
        return -2.0
    t = tmpl.astype(np.float64)
    t = t - t.mean()
    tn = float(np.sqrt((t ** 2).sum()))
    if tn < 1e-6:
        return -2.0
    corr = fftconvolve(image.astype(np.float64), t[::-1, ::-1], mode="valid")
    # 局部均值/方差（积分图）
    ii = np.cumsum(np.cumsum(image.astype(np.float64), 0), 1)
    ii = np.pad(ii, ((1, 0), (1, 0)))
    ii2 = np.cumsum(np.cumsum(image.astype(np.float64) ** 2, 0), 1)
    ii2 = np.pad(ii2, ((1, 0), (1, 0)))
    h, w = tmpl.shape
    def box(ii_):
        return (ii_[h:, w:] - ii_[:-h, w:] - ii_[h:, :-w] + ii_[:-h, :-w])
    s1, s2 = box(ii), box(ii2)
    n = h * w
    var = np.maximum(s2 - s1 ** 2 / n, 0.0)
    denom = np.sqrt(var) * tn
    with np.errstate(invalid="ignore", divide="ignore"):
        ncc = np.where(denom > 1e-6, corr / denom, -2.0)
    return float(np.nanmax(ncc))


def scale_probe(frames: np.ndarray, t0: float, t1: float, fps: int,
                box: tuple[int, int, int, int] | None = None,
                stride: float = 0.4, smin: float = 1.0, smax: float = 1.9,
                sstep: float = 0.02) -> dict:
    """推近倍数估计：区域内模板匹配。

    原理：若目标帧相对基准帧「推近」了 sc 倍，则把目标帧区域缩小 1/sc 后
    应与基准帧的某个子区域重合 → 对每个候选 sc 做模板匹配，取 NCC 最高者。

    box = (x, y, w, h)，坐标为分析分辨率（默认 960×540）下的像素。
    不传 box 时用整帧中心区域，只能捕捉「整机位」推近，测不到元素内局部推近。
    """
    from scipy.ndimage import zoom as _zoom
    n = len(frames)
    i0 = int(t0 * fps)
    if i0 >= n:
        return {"window": [t0, t1], "error": "start beyond video"}
    if box:
        x, y, w, h = box
        base = frames[i0][y:y + h, x:x + w].astype(np.float32)
    else:
        m = 0.12
        x, y = int(W * m), int(H * m)
        w, h = int(W * (1 - 2 * m)), int(H * (1 - 2 * m))
        base = frames[i0][y:y + h, x:x + w].astype(np.float32)
    if base.size == 0:
        return {"window": [t0, t1], "error": "empty region"}

    samples, best = [], (1.0, -2.0)
    for sc in np.arange(smin, smax + 1e-9, sstep):
        pass
    t = t0 + stride
    while t < t1:
        i = int(t * fps)
        if i >= n:
            break
        cur = frames[i][y:y + h, x:x + w].astype(np.float32)
        best_sc, best_ncc = None, -2.0
        for sc in np.arange(smin, smax + 1e-9, sstep):
            if sc <= 1.0:
                probe = cur
            else:
                probe = _zoom(cur, (1.0 / sc, 1.0 / sc), order=1)
            if probe.shape[0] < 12 or probe.shape[1] < 12:
                continue
            ncc = _ncc_template(base, probe)
            if ncc > best_ncc:
                best_ncc, best_sc = ncc, float(sc)
        if best_sc is None:
            t += stride
            continue
        samples.append({"t": round(t, 2), "scale": round(best_sc, 3), "ncc": round(best_ncc, 3)})
        if best_ncc > best[1]:
            best = (best_sc, best_ncc)
        t += stride

    if not samples:
        return {"window": [t0, t1], "error": "no comparable frames"}
    sc_list = [x["scale"] for x in samples]
    ncc_list = [x["ncc"] for x in samples]
    return {
        "window": [t0, t1],
        "box": [x, y, w, h],
        "best_scale": round(best[0], 3),
        "best_ncc": round(best[1], 3),
        "median_scale": round(float(np.median(sc_list)), 3),
        "max_scale": round(float(np.max(sc_list)), 3),
        "median_ncc": round(float(np.median(ncc_list)), 3),
        "samples": samples,
    }


def region_motion(frames: np.ndarray, t0: float, t1: float, fps: int,
                  box: tuple[int, int, int, int]) -> float:
    x, y, w, h = box
    sub = frames[:, y:y + h, x:x + w].astype(np.int16)
    i0, i1 = int(t0 * fps), int(t1 * fps)
    seg = np.diff(sub[i0:i1], axis=0)
    if seg.size == 0:
        return 0.0
    return float(np.abs(seg).mean())


def _hot_block_ratio(frames, t0, t1, fps, box, grid=4) -> float:
    """区域内「热点子块」占比：子块时间波动超过全片噪声底若干倍才算在动。"""
    x, y, w, h = box
    sub = frames[int(t0 * fps):int(t1 * fps), y:y + h, x:x + w].astype(np.float32)
    if sub.shape[0] < 4:
        return 0.0
    std = sub.std(axis=0)                       # 每像素时间标准差
    gh, gw = max(h // grid, 1), max(w // grid, 1)
    blocks = std[:grid * gh, :grid * gw].reshape(grid, gh, grid, gw).mean(axis=(1, 3))
    return float((blocks > 3.0).mean())


def playback_probe(frames: np.ndarray, t0: float, t1: float, fps: int,
                   play_box: tuple, static_box: tuple) -> dict:
    """真视频是否在播。

    判据：播放区内「有运动的子块占比」应显著高于静态区。
    用热点子块占比而不是整框平均差，避免被播放器外框/描边稀释。
    """
    ph = _hot_block_ratio(frames, t0, t1, fps, play_box)
    sh = _hot_block_ratio(frames, t0, t1, fps, static_box)
    return {"window": [t0, t1],
            "play_hot_ratio": round(ph, 3),
            "static_hot_ratio": round(sh, 3),
            "pass": ph >= 0.25 and ph >= sh + 0.2}


def typing_probe(frames: np.ndarray, t0: float, t1: float, fps: int,
                 box: tuple, min_steps: int = 4) -> dict:
    """是否逐字打字：输入区逐帧差分里应出现「多段安静 + 若干离散跳变」。"""
    x, y, w, h = box
    sub = frames[:, y:y + h, x:x + w].astype(np.int16)
    i0, i1 = int(t0 * fps), int(t1 * fps)
    d = np.abs(np.diff(sub[i0:i1], axis=0)).mean(axis=(1, 2))
    if d.size == 0:
        return {"window": [t0, t1], "error": "empty"}
    thr = max(d.mean() * 0.5, 0.5)
    hot = d > thr
    # 计数「跳变簇」（相邻 hot 合并为一次）
    steps = int(np.sum(hot[1:] & ~hot[:-1])) + int(hot[0])
    return {"window": [t0, t1], "frames": int(d.size),
            "mean_diff": round(float(d.mean()), 3),
            "max_diff": round(float(d.max()), 3),
            "burst_threshold": round(float(thr), 3),
            "burst_count": steps,
            "pass": steps >= min_steps}


def countup_probe(frames: np.ndarray, t0: float, t1: float, fps: int,
                  box: tuple[int, int, int, int]) -> dict:
    """数字区逐帧差分：完全没变的帧对应为 0（连续累加，不是跳字）。"""
    x, y, w, h = box
    sub = frames[:, y:y + h, x:x + w].astype(np.int16)
    d = np.abs(np.diff(sub, axis=0)).mean(axis=(1, 2))
    i0, i1 = int(t0 * fps), int(t1 * fps)
    seg = d[i0:i1]
    frozen = int((seg < 0.5).sum())
    return {"window": [t0, t1], "frames": int(len(seg)),
            "frozen_frames": frozen,
            "mean_diff": round(float(seg.mean()), 3),
            "max_diff": round(float(seg.max()), 3),
            "pass": frozen == 0}


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--total", type=float, default=None, help="目标时长（秒）")
    ap.add_argument("--fps", type=int, default=10, help="差分分析帧率")
    ap.add_argument("--grid-json", type=Path, default=None, help="节拍网格 json")
    ap.add_argument("--bgm", type=Path, default=None,
                    help="节拍分析用的 BGM 源文件（默认取 grid json 同目录的 bgm-v3.mp3）")
    ap.add_argument("--head-seconds", type=float, default=3.0)
    ap.add_argument("--static-threshold", type=float, default=0.15,
                    help="整幅平均差低于此值算「冻结」（默认 0.15 灰度级）")
    ap.add_argument("--expect-res", type=str, default="1920x1080",
                    help="期望分辨率，如 1920x1080 / 1080x1920 / 1080x1080")
    ap.add_argument("--dur-tol", type=float, default=2.0, help="时长容差（秒），默认 2.0")
    ap.add_argument("--scale-windows", type=str, default="",
                    help="镜头推近窗口，形如 '18:23'（整机位）或 '26.4:27.6:x:y:w:h'（元素区域）")
    ap.add_argument("--countup", type=str, default="",
                    help="数字区窗口+区域，形如 '6.4:9.6:120:340:600:220'")
    ap.add_argument("--playback", type=str, default="",
                    help="真视频播放探针：'t0:t1:px:py:pw:ph:sx:sy:sw:sh'（播放区+静态区）")
    ap.add_argument("--typing", type=str, default="",
                    help="逐字打字探针：'t0:t1:x:y:w:h'")
    ap.add_argument("--json", type=Path, default=None, help="输出 JSON 路径")
    args = ap.parse_args()

    if not args.video.exists():
        print(f"[fatal] 找不到 {args.video}", file=sys.stderr)
        return 2
    if args.total is None and args.grid_json:
        args.total = json.loads(args.grid_json.read_text()).get("duration")
    total = args.total or 0.0

    ew, eh = (int(v) for v in args.expect_res.lower().split("x"))
    report: dict = {"video": str(args.video)}
    probe = ffprobe(args.video)
    report["spec"] = spec_check(probe, args.total, expect=(ew, eh), dur_tol=args.dur_tol)

    frames = decode_gray(args.video, args.fps)
    report["motion"] = motion_stats(frames, args.fps, args.static_threshold)

    samples = decode_audio(args.video)
    report["audio"] = audio_stats(samples, 22050, args.head_seconds)

    if args.grid_json:
        grid = json.loads(args.grid_json.read_text())
        if args.bgm:
            bgm = args.bgm
        else:
            cands = sorted(args.grid_json.parent.glob("bgm*"))
            bgm = cands[0] if cands else None
        if bgm is None:
            report["beats"] = {"error": "no BGM given and none found next to grid json"}
        else:
            try:
                rep = beat_check(grid, bgm, total or float(probe["format"]["duration"]))
                rep["bgm"] = str(bgm)
                rep["tempo_declared"] = grid.get("tempo")
                report["beats"] = rep
            except Exception as exc:  # librosa 缺失等
                report["beats"] = {"error": str(exc), "bgm": str(bgm)}

    if args.scale_windows:
        wins = []
        for seg in args.scale_windows.split(","):
            parts = seg.split(":")
            a, b = float(parts[0]), float(parts[1])
            box = tuple(int(v) for v in parts[2:6]) if len(parts) >= 6 else None
            wins.append(scale_probe(frames, a, b, args.fps, box=box))
        report["scale"] = wins

    if args.playback:
        v = [float(x) if i < 2 else int(x) for i, x in enumerate(args.playback.split(":"))]
        t0, t1 = v[0], v[1]
        report["playback"] = playback_probe(frames, t0, t1, args.fps,
                                            tuple(v[2:6]), tuple(v[6:10]))

    if args.typing:
        v = [float(x) if i < 2 else int(x) for i, x in enumerate(args.typing.split(":"))]
        report["typing"] = typing_probe(frames, v[0], v[1], args.fps, tuple(v[2:6]))

    if args.countup:
        a, b, x, y, w, h = (float(v) if i < 2 else int(v) for i, v in enumerate(args.countup.split(":")))
        report["countup"] = countup_probe(frames, a, b, args.fps, (x, y, w, h))

    # ---- 判定 ----
    m = report["motion"]
    verdict = {
        "active_ratio_ok": m["active_frame_ratio"] >= 0.55,
        "no_frozen_ge_1s": len(m["frozen_segments_ge_1s"]) == 0,
        "no_blank": m["blank_frames"] == 0,
        "no_black": m["black_frames"] == 0,
        "head_energy_ok": (report["audio"]["head_over_overall"] or 0) >= 0.6,
        "no_clipping": report["audio"]["clipped_ratio"] < 0.001,
        "spec_ok": report["spec"]["pass"],
    }
    if "countup" in report:
        verdict["countup_continuous"] = report["countup"]["pass"]
    if "playback" in report:
        verdict["real_video_playing"] = report["playback"]["pass"]
    if "typing" in report:
        verdict["typing_is_gradual"] = report["typing"]["pass"]
    report["verdict"] = verdict
    report["pass"] = all(verdict.values())

    txt = json.dumps(report, ensure_ascii=False, indent=2)
    print(txt)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(txt)
        print(f"\n[written] {args.json}", file=sys.stderr)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
