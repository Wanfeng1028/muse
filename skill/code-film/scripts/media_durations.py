"""读取一批音频（通常是逐句生成的配音）的时长，排出逐句时间轴。需要 ffprobe。

用法：
  python media_durations.py public/vo --fps 30 --gap 0.5 --lead 0.3 --out docs/vo_timeline.json

每句的建议镜头长度 = lead（镜头切入后多久开口）+ 这句的时长 + gap（句后气口）。
文件按文件名排序，建议命名为 vo_01.wav、vo_02.wav……
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        sys.exit(f"读取时长失败：{path}\n{out.stderr}")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="读取音频时长并排时间轴")
    ap.add_argument("inputs", nargs="+", help="音频文件或目录")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--gap", type=float, default=0.5, help="句后气口（秒）")
    ap.add_argument("--lead", type=float, default=0.3, help="镜头切入后多久开口（秒）")
    ap.add_argument("--prefix", default="vo/", help="写进 JSON 的文件路径前缀（相对 public/）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not shutil.which("ffprobe"):
        sys.exit("需要 ffprobe（随 ffmpeg 一起安装）")

    files = []
    for p in map(Path, args.inputs):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in EXTS)
        elif p.is_file():
            files.append(p)
    if not files:
        sys.exit("没有找到音频文件")

    fps = args.fps
    cursor = 0
    lines = []
    for f in files:
        dur = probe_duration(f)
        audio_frames = math.ceil(dur * fps)
        lead = round(args.lead * fps)
        shot = lead + audio_frames + round(args.gap * fps)
        lines.append({
            "file": f"{args.prefix}{f.name}",
            "seconds": round(dur, 3),
            "frames": audio_frames,
            "shotFrom": cursor,
            "shotDuration": shot,
            "voiceFrom": cursor + lead,
        })
        cursor += shot

    result = {"fps": fps, "gap": args.gap, "lead": args.lead, "totalFrames": cursor,
              "totalSeconds": round(cursor / fps, 2), "lines": lines}
    for ln in lines:
        print(f"{ln['file']:28s} {ln['seconds']:6.2f}s  镜头 {ln['shotFrom']:>6} 起 {ln['shotDuration']:>5} 帧  开口于第 {ln['voiceFrom']} 帧")
    print(f"合计 {cursor} 帧（{cursor / fps:.1f} 秒）")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {args.out}")


if __name__ == "__main__":
    main()
