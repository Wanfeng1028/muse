#!/usr/bin/env python3
"""
make_frame_sheets.py — 把一段视频切成「带时间戳的关键帧板」，供视觉大模型逐张拆解。

为什么需要它：现有 teardown_video.py 只能给出可量化的统计量（切点、运动、响度…），
回答不了「这一镜在讲什么、怎么演的」这类语义问题。要回答语义问题就得让能看图的
模型真的看画面，而模型一次看整段视频不现实 —— 于是把视频降采样成若干张 3x3 / 4x4
的接触表，每格标上精确时间戳，让模型能按时间轴逐格描述。

用法：
    python3 scripts/make_frame_sheets.py <video> --out <dir> [--label 名字]
        [--mode both|overview|fine] [--window 6.0] [--grid 3] [--tile 640x360]

产出：
    <dir>/overview.jpg           整片 16 格总览（看结构 / 叙事弧）
    <dir>/fine-00_0000-0006.jpg  每 ~6s 一张 9 格细节板（看镜头怎么演）
    <dir>/sheet_manifest.json    每个格子的精确时间戳（模型引用它对齐时间轴）
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,r_frame_rate",
         "-of", "json", str(video)],
        capture_output=True, text=True).stdout
    d = json.loads(out)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    num, den = v["r_frame_rate"].split("/")
    return {
        "duration": float(d["format"]["duration"]),
        "width": v["width"], "height": v["height"],
        "fps": round(float(num) / float(den), 3),
    }


def grab(video: Path, t: float, w: int, h: int) -> Image.Image:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
         "-frames:v", "1",
         "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
         "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True).stdout
    if not raw:
        return Image.new("RGB", (w, h), (18, 18, 20))
    return Image.open(io.BytesIO(raw)).convert("RGB")


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def fmt(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def make_sheet(video: Path, times, out: Path, label: str,
               tile_w: int, tile_h: int, cols: int, header: str) -> None:
    rows = (len(times) + cols - 1) // cols
    pad, head_h, cap_h = 8, 46, 30
    W = cols * tile_w + pad * (cols + 1)
    H = head_h + rows * (tile_h + cap_h) + pad * (rows + 1)
    sheet = Image.new("RGB", (W, H), (12, 12, 14))
    draw = ImageDraw.Draw(sheet)
    f_head, f_cap = font(28), font(20)
    draw.text((pad + 4, 10), f"{label}  ·  {header}", fill=(240, 240, 245), font=f_head)

    for i, t in enumerate(times):
        r, c = divmod(i, cols)
        x = pad + c * (tile_w + pad)
        y = head_h + pad + r * (tile_h + cap_h + pad)
        sheet.paste(grab(video, t, tile_w, tile_h), (x, y))
        draw.rectangle([x, y + tile_h, x + tile_w, y + tile_h + cap_h],
                       fill=(26, 26, 30))
        draw.text((x + 8, y + tile_h + 4), f"t={fmt(t)}  ({t:.2f}s)",
                  fill=(120, 220, 160), font=f_cap)
    sheet.save(out, quality=88)
    print(f"  wrote {out.name}  ({W}x{H}, {len(times)} tiles)")


def build_times(a: float, b: float, n: int):
    if n == 1:
        return [(a + b) / 2]
    step = (b - a) / n
    return [a + step * (i + 0.5) for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--mode", choices=["both", "overview", "fine"], default="both")
    ap.add_argument("--window", type=float, default=6.0)
    ap.add_argument("--grid", type=int, default=3)
    ap.add_argument("--tile", default="640x360")
    ap.add_argument("--overview-grid", type=int, default=4)
    args = ap.parse_args()

    video = Path(args.video).resolve()
    outdir = Path(args.out).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    label = args.label or video.stem
    tw, th = (int(x) for x in args.tile.lower().split("x"))
    info = probe(video)
    dur = info["duration"]
    manifest = {"video": str(video), "label": label, "probe": info, "sheets": []}

    if args.mode in ("both", "overview"):
        g = args.overview_grid
        times = build_times(0, dur, g * g)
        name = "overview.jpg"
        make_sheet(video, times, outdir / name, label, tw, th, g,
                   f"整片总览 0.0-{dur:.1f}s")
        manifest["sheets"].append({"file": name, "kind": "overview",
                                   "times": [round(t, 2) for t in times]})

    if args.mode in ("both", "fine"):
        k = args.grid * args.grid
        w0, idx = 0.0, 0
        while w0 < dur - 0.15:
            w1 = min(w0 + args.window, dur)
            times = build_times(w0, w1, k)
            name = f"fine-{idx:02d}_{w0:04.0f}-{w1:04.0f}.jpg"
            make_sheet(video, times, outdir / name, label, tw, th, args.grid,
                       f"{w0:.1f}-{w1:.1f}s")
            manifest["sheets"].append({"file": name, "kind": "fine",
                                       "window": [round(w0, 2), round(w1, 2)],
                                       "times": [round(t, 2) for t in times]})
            w0, idx = w1, idx + 1

    (outdir / "sheet_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done: {len(manifest['sheets'])} sheets -> {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
