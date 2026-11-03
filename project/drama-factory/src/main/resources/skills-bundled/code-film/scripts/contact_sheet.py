"""生成缩略图墙：按固定间隔抽帧，拼成一张或几张大图，一眼看完整部片子。需要 ffmpeg。

用法：
  python contact_sheet.py out/draft.mp4 --every 1 --cols 8
  python contact_sheet.py out/check --cols 5          把一个目录里的静帧 PNG/JPG 拼起来

输出在视频旁边的 <名字>_sheet_01.png ……，并打印每一格对应的时间。
"""
import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd):
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        sys.exit(f"命令失败：{' '.join(cmd)}\n{out.stderr[-2000:]}")
    return out


def duration_of(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)])
    return float(out.stdout.strip())


def tile_images(images, out_prefix, cols, rows, width):
    per = cols * rows
    sheets = []
    with tempfile.TemporaryDirectory() as tmp:
        for page in range(math.ceil(len(images) / per)):
            batch = images[page * per:(page + 1) * per]
            for i, img in enumerate(batch):
                shutil.copy(img, Path(tmp) / f"f{i:04d}{Path(img).suffix.lower()}")
            ext = Path(batch[0]).suffix.lower()
            r = math.ceil(len(batch) / cols)
            dst = f"{out_prefix}_{page + 1:02d}.png"
            run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-start_number", "0",
                 "-i", str(Path(tmp) / f"f%04d{ext}"),
                 "-vf", f"scale={width}:-2,tile={cols}x{r}:padding=4:margin=8:color=0x1a1a1a",
                 "-frames:v", "1", dst])
            for f in Path(tmp).iterdir():
                f.unlink()
            sheets.append(dst)
    return sheets


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="缩略图墙")
    ap.add_argument("input", help="视频文件，或者存放静帧的目录")
    ap.add_argument("--every", type=float, default=1.0, help="每隔多少秒抽一帧")
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--rows", type=int, default=6, help="每张图最多几行，超出会分成多张")
    ap.add_argument("--width", type=int, default=320, help="每格宽度（像素）")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("需要 ffmpeg")
    src = Path(args.input)

    if src.is_dir():
        images = sorted(str(p) for p in src.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
        if not images:
            sys.exit("目录里没有 PNG 或 JPG")
        exts = {Path(p).suffix.lower() for p in images}
        if len(exts) > 1:
            sys.exit("目录里的图片格式要统一（全是 png 或全是 jpg）")
        sheets = tile_images(images, str(src / "sheet"), args.cols, args.rows, args.width)
        for i, p in enumerate(images):
            print(f"  第 {i + 1:>3} 格  {Path(p).name}")
    else:
        dur = duration_of(src)
        with tempfile.TemporaryDirectory() as frames_dir:
            run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", f"fps=1/{args.every},scale={args.width}:-2",
                 str(Path(frames_dir) / "g%05d.png")])
            images = sorted(str(p) for p in Path(frames_dir).iterdir())
            prefix = str(src.with_name(src.stem + "_sheet"))
            sheets = tile_images(images, prefix, args.cols, args.rows, args.width)
        per = args.cols * args.rows
        for i in range(len(images)):
            t = min(i * args.every, dur)
            if i % args.cols == 0:
                print(f"  图 {i // per + 1} 第 {(i % per) // args.cols + 1} 行：从 {t:6.1f}s 开始，每格 {args.every}s")
    for s in sheets:
        print(f"[OK] {s}")


if __name__ == "__main__":
    main()
