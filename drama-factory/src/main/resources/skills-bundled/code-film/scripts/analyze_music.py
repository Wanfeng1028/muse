"""分析一首音乐：BPM、节拍、强拍、段落、能量曲线、重音、空拍。需要 numpy 和 ffmpeg。

用法：
  python analyze_music.py public/music/bgm.mp3 --fps 30 --out docs/music.json
  python analyze_music.py song.wav --bpm 128        已知速度时手动指定，只让脚本找拍子位置

输出 JSON 字段：
  bpm, framesPerBeat, beatOffsetFrames（第一个强拍所在帧）
  beats:    [{t, frame, bar, beat}]    bar 从 1 开始，bar=0 表示强拍之前的弱起
  sections: [{name, level, startSec, endSec, startFrame, endFrame, startBar, bars, energy}]
  energy:   每 0.5 秒一个 0 到 1 的能量值
  accents:  最突出的重音点 [{t, frame, strength}]
  breaks:   能量骤降的小节 [{bar, t, frame}]
强拍（bar 的划分）和段落名称都是估算，重要判断请让用户用耳朵确认。
"""
import argparse
import json
from pathlib import Path

from _dsp import decode_audio, np, setup_stdout

SR = 22050
N_FFT = 2048
HOP = 512


def stft_features(x):
    pad = np.concatenate([np.zeros(N_FFT // 2), x, np.zeros(N_FFT // 2)])
    n_frames = 1 + (len(pad) - N_FFT) // HOP
    win = np.hanning(N_FFT).astype(np.float32)
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / SR)
    low = freqs < 150
    flux, low_flux, rms, centroid = (np.zeros(n_frames) for _ in range(4))
    prev = None
    chunk = 512
    for c0 in range(0, n_frames, chunk):
        idx = np.arange(c0, min(n_frames, c0 + chunk))
        frames = np.stack([pad[i * HOP:i * HOP + N_FFT] for i in idx]).astype(np.float32)
        rms[idx] = np.sqrt(np.mean(frames ** 2, axis=1))
        mag = np.abs(np.fft.rfft(frames * win, axis=1))
        centroid[idx] = (mag * freqs).sum(1) / (mag.sum(1) + 1e-9)
        logm = np.log1p(100 * mag)
        first = logm[:1] if prev is None else prev
        d = np.maximum(0, np.diff(np.vstack([first, logm]), axis=0))
        flux[idx] = d.sum(1)
        low_flux[idx] = d[:, low].sum(1)
        prev = logm[-1:]
    return flux, low_flux, rms, centroid


def moving_avg(x, w):
    w = max(1, int(w))
    return np.convolve(x, np.ones(w) / w, mode="same")


def onset_envelope(flux, fr):
    env = np.maximum(0, flux - moving_avg(flux, 0.4 * fr))
    return env / (np.std(env) + 1e-9)


def estimate_tempo(env, fr):
    e = env - env.mean()
    n = len(e)
    spec = np.fft.rfft(e, 2 * n)
    ac = np.fft.irfft(spec * np.conj(spec))[:n]
    lo, hi = int(60 * fr / 200), int(60 * fr / 60)
    best, best_score = lo, -np.inf
    for lag in range(max(1, lo), min(hi, n - 1) + 1):
        bpm = 60 * fr / lag
        w = np.exp(-0.5 * (np.log2(bpm / 120) / 0.9) ** 2)
        score = ac[lag] * w
        if 2 * lag < n:
            score += 0.5 * ac[2 * lag] * w
        if score > best_score:
            best, best_score = lag, score
    if 1 <= best < n - 1:
        a, b, c = ac[best - 1], ac[best], ac[best + 1]
        denom = a - 2 * b + c
        shift = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
        lag = best + float(np.clip(shift, -0.5, 0.5))
    else:
        lag = float(best)
    return 60 * fr / lag


def track_beats(env, fr, bpm, tightness=100.0):
    period = 60 * fr / bpm
    n = len(env)
    score = env.copy()
    back = -np.ones(n, dtype=int)
    for t in range(n):
        hi = int(round(t - period / 2))
        if hi < 0:
            continue
        lo = max(0, int(round(t - 2 * period)))
        prev = np.arange(lo, hi + 1)
        cand = score[prev] - tightness * np.log((t - prev) / period) ** 2
        i = int(np.argmax(cand))
        if cand[i] > 0:
            score[t] = env[t] + cand[i]
            back[t] = prev[i]
    tail = max(0, n - int(round(period)))
    t = tail + int(np.argmax(score[tail:]))
    beats = [t]
    while back[t] >= 0:
        t = back[t]
        beats.append(t)
    return np.array(beats[::-1])


def segment_bars(Z, penalty=4.0):
    """最优分段：让每段内部的特征尽量一致，每多一段付出一次惩罚。Z 为逐小节的标准化特征。"""
    n = len(Z)
    cs = np.vstack([np.zeros(Z.shape[1]), np.cumsum(Z, 0)])
    cs2 = np.vstack([np.zeros(Z.shape[1]), np.cumsum(Z ** 2, 0)])
    best = np.full(n + 1, np.inf)
    best[0] = 0.0
    arg = np.zeros(n + 1, dtype=int)
    for b in range(1, n + 1):
        for a in range(b):
            m = b - a
            s = cs[b] - cs[a]
            cost = (cs2[b] - cs2[a] - s * s / m).sum()
            v = best[a] + cost + penalty
            if v < best[b]:
                best[b], arg[b] = v, a
    bounds, b = [], n
    while b > 0:
        bounds.append(b)
        b = arg[b]
    return [0] + [int(v) for v in bounds[::-1]]


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="分析音乐结构")
    ap.add_argument("audio")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--bpm", type=float, default=None, help="手动指定速度")
    ap.add_argument("--out", default=None, help="输出 JSON 路径，默认与音频同名")
    ap.add_argument("--penalty", type=float, default=3.0, help="段落切分的惩罚系数：越小切得越细，越大段落越少")
    args = ap.parse_args()

    x = decode_audio(args.audio, SR)
    if len(x) < SR * 2:
        raise SystemExit("音频太短（少于 2 秒）")
    duration = len(x) / SR
    fr = SR / HOP
    fps = args.fps

    flux, low_flux, rms, centroid = stft_features(x)
    env = onset_envelope(flux, fr)
    low_env = onset_envelope(low_flux, fr)

    bpm = args.bpm or estimate_tempo(env, fr)
    beat_idx = track_beats(env, fr, bpm)
    beat_t = beat_idx * HOP / SR
    if len(beat_t) > 8:
        bpm_refined = 60.0 / np.median(np.diff(beat_t))
        if args.bpm is None and abs(bpm_refined - bpm) / bpm < 0.04:
            bpm = bpm_refined

    phase_scores = []
    for k in range(4):
        sel = beat_idx[k::4]
        phase_scores.append(low_env[sel].mean() + 0.3 * env[sel].mean() if len(sel) else -1)
    phase = int(np.argmax(phase_scores))

    beats = []
    for i, t in enumerate(beat_t):
        if i < phase:
            bar, pos = 0, 4 - phase + i + 1
        else:
            bar, pos = (i - phase) // 4 + 1, (i - phase) % 4 + 1
        beats.append({"t": round(float(t), 3), "frame": int(round(t * fps)), "bar": bar, "beat": pos})

    rms_db = 20 * np.log10(rms + 1e-9)
    lo_db, hi_db = np.percentile(rms_db, 5), np.percentile(rms_db, 95)
    energy_frame = np.clip((rms_db - lo_db) / (hi_db - lo_db + 1e-9), 0, 1)
    step = max(1, int(round(0.5 * fr)))
    energy_curve = [round(float(v), 3) for v in moving_avg(energy_frame, step)[::step]]

    downbeats = [b for b in beats if b["beat"] == 1 and b["bar"] >= 1]
    bar_starts = [int(round(b["t"] * fr)) for b in downbeats] + [len(env)]
    rows = []
    for a, b in zip(bar_starts[:-1], bar_starts[1:]):
        b = max(b, a + 1)
        rows.append([rms_db[a:b].mean(), centroid[a:b].mean(), env[a:b].mean(), low_env[a:b].mean()])
    nb = len(rows)
    F = np.array(rows) if rows else np.zeros((0, 4))
    bar_energy = []
    if nb:
        d_lo, d_hi = np.percentile(F[:, 0], 5), np.percentile(F[:, 0], 95)
        bar_energy = [float(v) for v in np.clip((F[:, 0] - d_lo) / (d_hi - d_lo + 1e-9), 0, 1)]

    sections = []
    if nb >= 4:
        Z = (F - F.mean(0)) / (F.std(0) + 1e-9)
        bounds = segment_bars(Z, args.penalty)
        for a, b in zip(bounds[:-1], bounds[1:]):
            sections.append({"startBar": a + 1, "bars": b - a, "energy": round(float(np.mean(bar_energy[a:b])), 3)})
        bar_len = np.diff([d["t"] for d in downbeats] + [duration])
        if len(sections) > 1 and sections[-1]["bars"] == 1 and bar_len[-1] < 0.5 * np.median(bar_len):
            sections[-2]["bars"] += 1
            sections.pop()
        es = [s["energy"] for s in sections]
        emax = max(es) or 1.0
        is_peak = [e >= 0.9 * emax for e in es]
        last_peak = max((i for i, p in enumerate(is_peak) if p), default=-1)
        for i, s in enumerate(sections):
            e = s["energy"]
            s["level"] = "high" if is_peak[i] else ("mid" if e >= 0.55 * emax else "low")
            prev_e = es[i - 1] if i > 0 else None
            next_e = es[i + 1] if i + 1 < len(es) else None
            leads_to_peak = any(
                is_peak[j] and all(es[k] < e for k in range(i + 1, j))
                for j in range(i + 1, min(len(es), i + 3))
            )
            if is_peak[i]:
                name = "peak"
            elif i == 0:
                name = "intro"
            elif i > last_peak and all(es[j] <= es[j - 1] + 0.05 for j in range(i, len(es))):
                name = "outro"
            elif prev_e is not None and next_e is not None and min(prev_e, next_e) > e + 0.1:
                name = "break"
            elif leads_to_peak:
                name = "build"
            else:
                name = "verse"
            s["name"] = name
        merged = []
        for s in sections:
            if merged and merged[-1]["name"] == s["name"]:
                m = merged[-1]
                total_bars = m["bars"] + s["bars"]
                m["energy"] = round((m["energy"] * m["bars"] + s["energy"] * s["bars"]) / total_bars, 3)
                m["bars"] = total_bars
            else:
                merged.append(dict(s))
        sections = merged
        for k, s in enumerate(sections):
            a = s["startBar"] - 1
            b = a + s["bars"]
            st = 0.0 if k == 0 else downbeats[a]["t"]
            en = duration if k == len(sections) - 1 else downbeats[b]["t"]
            s.update({"startSec": round(st, 3), "endSec": round(en, 3),
                      "startFrame": int(round(st * fps)), "endFrame": int(round(en * fps))})
        sections = [{k: s[k] for k in ("name", "level", "startSec", "endSec", "startFrame", "endFrame", "startBar", "bars", "energy")} for s in sections]

    win = int(0.25 * fr)
    peaks = [i for i in range(len(env)) if env[i] > 0 and env[i] == env[max(0, i - win):i + win + 1].max()]
    peaks.sort(key=lambda i: -env[i])
    n_acc = max(4, int(round(duration / 60 * 10)))
    chosen = []
    for i in peaks:
        if all(abs(i - j) >= 0.5 * fr for j in chosen):
            chosen.append(i)
        if len(chosen) >= n_acc:
            break
    top = env[chosen].max() if chosen else 1.0
    accents = [{"t": round(i * HOP / SR, 3), "frame": int(round(i * HOP / SR * fps)),
                "strength": round(float(env[i] / top), 3)} for i in sorted(chosen)]

    breaks = []
    for b in range(1, nb):
        if bar_energy[b] < 0.2 and bar_energy[b - 1] - bar_energy[b] > 0.25:
            breaks.append({"bar": b + 1, "t": downbeats[b]["t"], "frame": downbeats[b]["frame"]})

    result = {
        "file": Path(args.audio).name,
        "durationSec": round(duration, 3),
        "durationInFrames": int(round(duration * fps)),
        "fps": fps,
        "bpm": round(float(bpm), 2),
        "bpmAlternatives": [round(float(bpm) / 2, 2), round(float(bpm) * 2, 2)],
        "framesPerBeat": round(fps * 60 / bpm, 4),
        "beatOffsetFrames": downbeats[0]["frame"] if downbeats else 0,
        "beats": beats,
        "sections": sections,
        "energy": energy_curve,
        "energyStepSec": 0.5,
        "accents": accents,
        "breaks": breaks,
        "note": "强拍和段落名称为估算，重要判断请用户试听确认",
    }
    out = Path(args.out) if args.out else Path(args.audio).with_suffix(".analysis.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")

    print(f"[OK] {result['file']}  时长 {duration:.2f}s  BPM {result['bpm']}  每拍 {result['framesPerBeat']} 帧")
    print(f"     提示：速度容易被误判成一半或两倍。如果听感上的拍子是 {bpm / 2:.1f} 或 {bpm * 2:.1f}，请加 --bpm 重新分析")
    print(f"     节拍 {len(beats)} 个，第一个强拍在 {downbeats[0]['t'] if downbeats else 0:.3f}s（帧 {result['beatOffsetFrames']}）")
    for s in sections:
        bar_line = "#" * int(round(s["energy"] * 20))
        print(f"     {s['name']:6s} {s['level']:4s} {s['startSec']:7.2f}s 到 {s['endSec']:7.2f}s  第 {s['startBar']:>3} 小节起 {s['bars']:>3} 小节  {bar_line}")
    if accents:
        print("     重音：" + "  ".join(f"{a['t']:.2f}s" for a in accents[:12]))
    if breaks:
        print("     空拍：" + "  ".join(f"第 {b['bar']} 小节 {b['t']:.2f}s" for b in breaks))
    print(f"结果已写入 {out}")


if __name__ == "__main__":
    main()
