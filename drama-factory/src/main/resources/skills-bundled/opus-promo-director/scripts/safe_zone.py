"""Overlay vertical-video platform UI zones on real frames and save a sheet for review.

Usage:
  python safe_zone.py VIDEO OUT.jpg --frames 100,280,640      # frames where the most text is on screen
  python safe_zone.py VIDEO OUT.jpg --times 3.3,9.4 --platform reels
Options: --platform common|reels|shorts|tiktok (default common), --width 270, --project film/
Red areas are where the app covers the video. Text, logos and the call to action must stay out of red.
Pick frames at the moment each scene shows the most text (last card in, before it leaves), not at cuts.
Zone values (1080x1920) are conservative planning numbers checked on 2026-09-30; preview in the app too.
"""
import argparse, os, sys, tempfile
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _media import grab_frame, label_font, probe_video, set_project  # noqa: E402

# Safe text rectangle (x0, y0, x1, y1) on a 1080x1920 canvas.
ZONES = {
    "reels": (65, 269, 1015, 1248),    # Meta: keep 14% top, 35% bottom, 6% sides clear
    "shorts": (48, 288, 888, 1248),    # right-side buttons and bottom title/description
    "tiktok": (90, 150, 900, 1420),    # right buttons and bottom caption; varies by ad format
    "common": (90, 288, 888, 1248),    # all three at once
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--frames")
    g.add_argument("--times")
    ap.add_argument("--platform", default="common", choices=sorted(ZONES))
    ap.add_argument("--width", type=int, default=270)
    ap.add_argument("--project", default=None)
    a = ap.parse_args()
    set_project(a.project)
    w, h, fps, dur = probe_video(a.video)
    if abs(w / h - 9 / 16) > 0.02:
        sys.exit(f"{w}x{h} is not 9:16; safe zones apply to vertical video")
    frames = [int(f) for f in a.frames.split(",")] if a.frames else [round(float(t) * fps) for t in a.times.split(",")]
    x0, y0, x1, y1 = ZONES[a.platform]
    sx, sy = w / 1080, h / 1920
    font = label_font(max(14, a.width // 12))
    tiles = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in frames:
            p = os.path.join(tmp, f"{f}.png")
            grab_frame(a.video, f, fps, p)
            im = Image.open(p).convert("RGBA")
            ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            red = (255, 40, 40, 105)
            d.rectangle([0, 0, w, y0 * sy], fill=red)
            d.rectangle([0, y1 * sy, w, h], fill=red)
            d.rectangle([0, y0 * sy, x0 * sx, y1 * sy], fill=red)
            d.rectangle([x1 * sx, y0 * sy, w, y1 * sy], fill=red)
            d.rectangle([x0 * sx, y0 * sy, x1 * sx, y1 * sy], outline=(255, 230, 0, 255), width=max(2, w // 270))
            im = Image.alpha_composite(im, ov).convert("RGB").resize((a.width, round(a.width * h / w)))
            ImageDraw.Draw(im).text((6, 4), f"{f}  {f / fps:.2f}s", fill=(255, 255, 0), font=font)
            tiles.append(im)
    tw, th = tiles[0].size
    cols = min(len(tiles), 8)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 4), rows * (th + 4)), (20, 20, 20))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * (tw + 4), (i // cols) * (th + 4)))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sheet.save(a.out, quality=88)
    print(f"{len(tiles)} frames, platform {a.platform}, safe text area x {x0}-{x1}, y {y0}-{y1} -> {a.out}")


if __name__ == "__main__":
    main()

