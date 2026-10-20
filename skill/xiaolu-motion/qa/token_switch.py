"""Same components, same frame, two token files: proves styling lives only in styles/*.json.

  python3 -m qa.token_switch RESOLVED --styles coldlight paperwhite --times 3.75 6.2 --base FINAL_OR_BASE.mp4 --out PNG
Each row: one style; each column: one time, overlay composited (premultiplied) over the base
frame at that time (or over the style's own bg when no base is given).
"""
import argparse

import numpy as np
from PIL import Image, ImageDraw

from render.common import load_json, load_style
from render.overlay import stills
from .contact_sheet import decode, over


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("resolved")
    ap.add_argument("--styles", nargs="+", default=["coldlight", "paperwhite"])
    ap.add_argument("--times", type=float, nargs="+", required=True)
    ap.add_argument("--base")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = load_json(a.resolved)
    W, H, FPS = res["canvas"]["w"], res["canvas"]["h"], res["canvas"]["fps"]
    frames = [round(t * FPS) for t in a.times]
    base = decode(a.base, frames, W, H) if a.base else None
    cw, ch = 432, 576
    sheet = Image.new("RGB", (len(frames) * (cw + 10) + 10, len(a.styles) * (ch + 34) + 10), (18, 18, 20))
    d = ImageDraw.Draw(sheet)
    for r, name in enumerate(a.styles):
        tok = load_style(name)
        ims, _ = stills(res, [n / FPS for n in frames], tokens=tok)
        for c, (n, im) in enumerate(zip(frames, ims)):
            bg = base[n].astype(np.float32) if base is not None else np.broadcast_to(np.array([int(tok["colors"]["bg"][i:i + 2], 16) for i in (1, 3, 5)], np.float32), (H, W, 3))
            x, y = 10 + c * (cw + 10), 10 + r * (ch + 34)
            sheet.paste(Image.fromarray(over(im, bg)).resize((cw, ch), Image.LANCZOS), (x, y))
            d.text((x + 4, y + ch + 8), f"style={name}  t={n / FPS:.3f}s f{n}", fill=(230, 230, 230))
    sheet.save(a.out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
