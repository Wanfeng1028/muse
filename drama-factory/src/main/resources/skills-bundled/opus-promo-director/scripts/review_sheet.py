"""Tile frames from a video into a labelled contact sheet for visual review.

Usage:
  python review_sheet.py VIDEO OUT.jpg --times 0.5,2,4.1
  python review_sheet.py VIDEO OUT.jpg --frames 15,60,123
  python review_sheet.py VIDEO OUT.jpg --around 4.1,6.9 --span 6   # dense frames around each cut
  python review_sheet.py VIDEO OUT.jpg --every 2.5                  # whole-film overview, one frame per 2.5s
  python review_sheet.py VIDEO OUT.jpg --every 2.5 --compare REF.mp4 # same times from a reference video, row by row
Options: --cols 6  --width 300  --project film/
--compare puts the reference frame under each frame of VIDEO. Use it against the look the user approved
(an earlier film, a reference ad, the chosen styleframe video) to judge brightness, density and scale.
"""
import argparse, os, sys, tempfile
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _media import grab_frame, label_font, probe_video, set_project  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--times", help="comma separated seconds")
    g.add_argument("--frames", help="comma separated frame numbers")
    g.add_argument("--around", help="comma separated cut times in seconds")
    g.add_argument("--every", type=float, help="one frame every N seconds")
    ap.add_argument("--span", type=int, default=6, help="frames before/after each cut for --around")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--width", type=int, default=300)
    ap.add_argument("--compare", default=None, help="reference video sampled at the same times")
    ap.add_argument("--project", default=None)
    a = ap.parse_args()
    set_project(a.project)

    w, h, fps, dur = probe_video(a.video)
    last = int(dur * fps) - 1
    if a.times:
        frames = [round(float(t) * fps) for t in a.times.split(",")]
    elif a.frames:
        frames = [int(f) for f in a.frames.split(",")]
    elif a.every:
        frames = [round(i * a.every * fps) for i in range(int(dur / a.every) + 1)]
    else:
        frames = []
        for c in a.around.split(","):
            cf = round(float(c) * fps)
            frames += list(range(cf - a.span, cf + a.span + 1, 2))
    frames = sorted({min(max(0, f), last) for f in frames})

    ref = probe_video(a.compare) if a.compare else None
    tw = a.width
    th = round(tw * h / w)
    rh = round(tw * ref[1] / ref[0]) if ref else 0
    cols = a.cols
    rows = (len(frames) + cols - 1) // cols
    cell_h = th + (rh + 4 if ref else 0)
    sheet = Image.new("RGB", (cols * (tw + 6), rows * (cell_h + 6)), (25, 25, 25))
    font = label_font(18)
    with tempfile.TemporaryDirectory() as tmp:
        for i, f in enumerate(frames):
            p = os.path.join(tmp, f"{i}.png")
            grab_frame(a.video, f, fps, p, tw)
            im = Image.open(p).convert("RGB").resize((tw, th))
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, 150, 24], fill=(0, 0, 0))
            d.text((5, 2), f"{f}  {f / fps:.2f}s", fill=(255, 255, 0), font=font)
            x, y = (i % cols) * (tw + 6), (i // cols) * (cell_h + 6)
            sheet.paste(im, (x, y))
            if ref:
                t = f / fps
                rf = min(round(t * ref[2]), int(ref[3] * ref[2]) - 1)
                rp = os.path.join(tmp, f"r{i}.png")
                grab_frame(a.compare, rf, ref[2], rp, tw)
                rim = Image.open(rp).convert("RGB").resize((tw, rh))
                ImageDraw.Draw(rim).text((5, 2), "ref", fill=(0, 255, 255), font=font)
                sheet.paste(rim, (x, y + th + 4))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sheet.save(a.out, quality=88)
    print(f"{len(frames)} frames ({w}x{h}, {fps:g}fps, {dur:.2f}s){' with reference row' if ref else ''} -> {a.out}")


if __name__ == "__main__":
    main()

