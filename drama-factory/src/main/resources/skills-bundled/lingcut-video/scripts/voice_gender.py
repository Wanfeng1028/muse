"""判断一段人声是男声还是女声——自相关法估基频 F0。

参考区间（说话声）：
  成年男声 ≈ 85–155 Hz      成年女声 ≈ 165–255 Hz
  儿童   ≈ 250–400 Hz       老年男声偏低端，老年女声偏中端

用法: python voice_gender.py <wav1> [wav2 ...]
（WAV 用 ffmpeg 预先抽出：-vn -ac 1 -ar 16000）
"""
import sys, os, wave
import numpy as np

FMIN, FMAX = 70, 420


def f0_track(x, sr):
    win = int(0.040 * sr)
    hop = int(0.010 * sr)
    lo, hi = int(sr / FMAX), int(sr / FMIN)
    out = []
    for i in range(0, max(1, len(x) - win), hop):
        seg = x[i:i + win]
        if seg.size < win:
            break
        rms = float(np.sqrt(np.mean(seg ** 2)))
        if rms < 0.01:                      # 静音段跳过
            continue
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, mode='full')[win - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        seg_r = ac[lo:hi]
        if seg_r.size == 0:
            continue
        k = int(np.argmax(seg_r))
        if seg_r[k] < 0.35:                 # 周期性不足（噪声/清音）
            continue
        out.append((sr / (lo + k), rms))
    return out


def report(path):
    with wave.open(path, 'rb') as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    tr = f0_track(x, sr)
    if not tr:
        return {"file": os.path.basename(path), "error": "未检出浊音帧"}
    f0 = np.array([t[0] for t in tr])
    rms = np.array([t[1] for t in tr])
    # 取能量最高的 60% 帧，避开弱辅音
    keep = rms >= np.percentile(rms, 40)
    f0k = f0[keep]
    med = float(np.median(f0k))
    if med < 150:
        guess = "男声"
    elif med < 175:
        guess = "偏中性/青年男声"
    elif med < 260:
        guess = "女声"
    else:
        guess = "儿童/偏高女声"
    # 语调起伏：半音域（播报腔的典型特征就是起伏小）
    lo, hi = float(np.percentile(f0k, 5)), float(np.percentile(f0k, 95))
    semitones = 12 * np.log2(hi / lo) if lo > 0 else 0.0
    if semitones >= 9:
        prosody = "起伏大，接近自然口语"
    elif semitones >= 6:
        prosody = "起伏中等"
    else:
        prosody = "起伏小，偏播报/朗读腔"
    return {
        "file": os.path.basename(path),
        "duration_s": round(len(x) / sr, 2),
        "voiced_frames": len(tr),
        "F0_median_Hz": round(med, 1),
        "F0_p25_p75": [round(float(np.percentile(f0k, 25)), 1), round(float(np.percentile(f0k, 75)), 1)],
        "F0_range": [round(float(f0k.min()), 1), round(float(f0k.max()), 1)],
        "F0_std_Hz": round(float(f0k.std()), 1),
        "音域_半音": round(float(semitones), 1),
        "语调": prosody,
        "判断": guess,
    }


for p in sys.argv[1:]:
    print(report(p))
