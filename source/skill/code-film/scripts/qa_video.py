"""成片体检：编码参数、黑帧、冻帧（拖沓嫌疑）、静音、响度。需要 ffmpeg 和 ffprobe。

用法：
  python qa_video.py out/film.mp4
  python qa_video.py out/film.mp4 --expect-fps 30 --expect-duration 90 --freeze 1.5 --lufs -14

冻帧和静音不一定是错误：刻意的留白和黑场也会被报出来，逐条核对即可。
退出码：有错误时为 1。
"""
import argparse
import json
import re
import shutil
import subprocess
import sys


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="成片体检")
    ap.add_argument("video")
    ap.add_argument("--expect-fps", type=float, default=None)
    ap.add_argument("--expect-duration", type=float, default=None, help="期望时长（秒），误差超过 0.5 秒报警告")
    ap.add_argument("--freeze", type=float, default=1.5, help="画面静止超过多少秒算冻帧")
    ap.add_argument("--silence", type=float, default=1.0, help="无声超过多少秒报告")
    ap.add_argument("--lufs", type=float, default=-14.0, help="目标整体响度")
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"需要 {tool}")

    errors, warns, infos = [], [], []

    probe = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", args.video])
    if probe.returncode != 0:
        sys.exit(f"无法读取视频：{probe.stderr}")
    meta = json.loads(probe.stdout)
    vstreams = [s for s in meta["streams"] if s["codec_type"] == "video"]
    astreams = [s for s in meta["streams"] if s["codec_type"] == "audio"]
    duration = float(meta["format"].get("duration", 0))

    if not vstreams:
        errors.append("没有视频流")
    else:
        v = vstreams[0]
        w, h = v.get("width"), v.get("height")
        num, den = (v.get("avg_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0
        infos.append(f"视频：{v.get('codec_name')} {w}x{h} {fps:.3f}fps {v.get('pix_fmt')}  时长 {duration:.2f}s")
        if v.get("codec_name") != "h264":
            warns.append(f"编码器是 {v.get('codec_name')}，交付给手机和社交平台建议用 h264")
        if v.get("pix_fmt") != "yuv420p":
            errors.append(f"像素格式是 {v.get('pix_fmt')}，部分播放器（包括微信）会黑屏，交付请用 yuv420p")
        if (w or 0) % 2 or (h or 0) % 2:
            errors.append(f"宽高 {w}x{h} 不是偶数")
        if args.expect_fps and abs(fps - args.expect_fps) > 0.01:
            errors.append(f"帧率 {fps:.3f}，期望 {args.expect_fps}")
    if args.expect_duration and abs(duration - args.expect_duration) > 0.5:
        warns.append(f"时长 {duration:.2f}s，期望 {args.expect_duration}s")

    if astreams:
        a = astreams[0]
        infos.append(f"音频：{a.get('codec_name')} {a.get('sample_rate')}Hz {a.get('channels')} 声道")
    else:
        warns.append("没有音轨。如果是刻意的无声片，可以忽略")

    filters_v = f"blackdetect=d=0.1:pix_th=0.10,freezedetect=n=0.003:d={args.freeze}"
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", args.video, "-vf", filters_v]
    if astreams:
        cmd += ["-af", f"silencedetect=n=-50dB:d={args.silence},ebur128=peak=true"]
    cmd += ["-f", "null", "-"]
    log = run(cmd).stderr

    for s, e in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", log):
        s, e = float(s), float(e)
        warns.append(f"黑帧：{s:.2f}s 到 {e:.2f}s（{e - s:.2f}s）")

    fs = re.findall(r"freeze_start:\s*([\d.]+)", log)
    fe = re.findall(r"freeze_end:\s*([\d.]+)", log)
    for i, s in enumerate(fs):
        s = float(s)
        e = float(fe[i]) if i < len(fe) else duration
        warns.append(f"冻帧：{s:.2f}s 到 {e:.2f}s（{e - s:.2f}s 画面完全不变）。不是刻意留白的话，这里可能拖沓")

    ss = re.findall(r"silence_start:\s*([-\d.]+)", log)
    se = re.findall(r"silence_end:\s*([\d.]+)", log)
    for i, s in enumerate(ss):
        s = max(0.0, float(s))
        e = float(se[i]) if i < len(se) else duration
        warns.append(f"静音：{s:.2f}s 到 {e:.2f}s（{e - s:.2f}s）")

    if astreams:
        m_i = re.search(r"Integrated loudness:\s*\n\s*I:\s*([-\d.]+) LUFS", log)
        m_tp = re.search(r"True peak:\s*\n\s*Peak:\s*([-\d.]+) dBFS", log)
        if m_i:
            lufs = float(m_i.group(1))
            infos.append(f"整体响度 {lufs:.1f} LUFS（目标 {args.lufs}）")
            if abs(lufs - args.lufs) > 1.5:
                warns.append(f"整体响度 {lufs:.1f} LUFS，偏离目标 {args.lufs} 超过 1.5，交付前跑 finalize.py")
        if m_tp:
            tp = float(m_tp.group(1))
            infos.append(f"真峰值 {tp:.1f} dBTP")
            if tp > -1.0:
                warns.append(f"真峰值 {tp:.1f} dBTP 高于 -1，可能削波，交付前跑 finalize.py")

    for m in infos:
        print(f"[INFO] {m}")
    for m in warns:
        print(f"[WARN] {m}")
    for m in errors:
        print(f"[ERR ] {m}")
    print(f"结果：{len(errors)} 个错误，{len(warns)} 个警告")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
