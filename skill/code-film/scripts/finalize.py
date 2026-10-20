"""交付前的最后一步：两遍响度标准化（默认 -14 LUFS、真峰值 -1 dBTP），音频转 AAC，加 faststart。
视频流直接复制，不重新编码。需要 ffmpeg。

用法：
  python finalize.py out/film.mp4 out/final.mp4
  python finalize.py out/film.mp4 out/final.mp4 --lufs -16 --tp -1.5
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
    ap = argparse.ArgumentParser(description="响度标准化并输出交付文件")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--tp", type=float, default=-1.0)
    ap.add_argument("--lra", type=float, default=11.0)
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("需要 ffmpeg")
    if args.input == args.output:
        sys.exit("输出路径不能和输入相同")

    probe = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", args.input])
    has_audio = bool(probe.stdout.strip())

    if not has_audio:
        out = run(["ffmpeg", "-v", "error", "-y", "-i", args.input, "-c", "copy", "-movflags", "+faststart", args.output])
        if out.returncode != 0:
            sys.exit(out.stderr)
        print(f"[OK] 没有音轨，只加了 faststart：{args.output}")
        return

    target = f"I={args.lufs}:TP={args.tp}:LRA={args.lra}"
    first = run(["ffmpeg", "-hide_banner", "-nostats", "-i", args.input, "-vn",
                 "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", first.stderr, re.S)
    if not m:
        sys.exit(f"第一遍测量失败：\n{first.stderr[-2000:]}")
    meas = json.loads(m.group(0))
    print(f"测量：整体 {meas['input_i']} LUFS，真峰值 {meas['input_tp']} dBTP，动态范围 {meas['input_lra']} LU")

    af = (f"loudnorm={target}:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}"
          f":measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}"
          f":offset={meas['target_offset']}:linear=true,aresample=48000")
    second = run(["ffmpeg", "-v", "error", "-y", "-i", args.input, "-map", "0:v:0?", "-map", "0:a:0",
                  "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
                  "-movflags", "+faststart", args.output])
    if second.returncode != 0:
        sys.exit(f"第二遍处理失败：\n{second.stderr[-2000:]}")

    check = run(["ffmpeg", "-hide_banner", "-nostats", "-i", args.output, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    mi = re.search(r"Integrated loudness:\s*\n\s*I:\s*([-\d.]+) LUFS", check.stderr)
    mt = re.search(r"True peak:\s*\n\s*Peak:\s*([-\d.]+) dBFS", check.stderr)
    print(f"[OK] {args.output}  整体 {mi.group(1) if mi else '?'} LUFS，真峰值 {mt.group(1) if mt else '?'} dBTP")


if __name__ == "__main__":
    main()
