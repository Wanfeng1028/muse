"""Contact sheets for human review.

sheet(): rows of [overlay over a checkerboard | final composite] at key times (item starts,
middles, ends, transition quarter points, camera keys), labelled with t and frame number.
edges(): 3x crops of every visible component box (from XM.bboxes) composited from the
decoded ProRes over black, white, a checkerboard and the real base frame — dark fringes
show up on white, bright/dirty fringes on black.
"""
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from render.common import load_json
from render.overlay import bboxes as page_bboxes


def key_times(res, n=10):
    FPS, N = res["canvas"]["fps"], res["frames"]
    ts = set()
    for s in res["shots"]:
        ts |= {s["t0"] + 0.2, (s["t0"] + s["t1"]) / 2, s["t1"] - 0.12}
    for t in res["transitions"]:
        d = t["t1"] - t["t0"]
        ts |= {t["t0"] + 0.25 * d, t["at"], t["t0"] + 0.75 * d}
    for c in res["base"]:
        ts |= {k["t"] for k in c["camera"]}
    frames = sorted({min(N - 1, max(0, round(t * FPS))) for t in ts})
    if len(frames) > n:
        idx = np.linspace(0, len(frames) - 1, n).round().astype(int)
        frames = [frames[i] for i in idx]
    return frames


def decode(video, frames, W, H, rgba=False):
    sel = "+".join(f"eq(n\\,{n})" for n in frames)
    pf, ch = ("rgba", 4) if rgba else ("rgb24", 3)
    vf = f"select='{sel}'"
    if rgba:   # ProRes 4444 yuva444p10le (BT.709 limited) -> premultiplied RGBA as stored
        vf += ",scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int"
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", vf, "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", pf, "-"],
                       check=True, capture_output=True)
    a = np.frombuffer(r.stdout, np.uint8)
    sz = W * H * ch
    return {n: a[i * sz:(i + 1) * sz].reshape(H, W, ch) for i, n in enumerate(frames[:a.size // sz])}


def checker(H, W, s=24):
    c = ((np.indices((H, W)).sum(0) // s) % 2) * 70 + 95
    yy, xx = np.indices((H, W))
    c = (((yy // s) + (xx // s)) % 2) * 70 + 95
    return np.repeat(c[..., None], 3, 2).astype(np.float32)


def over(rgba, bg):
    """premultiplied over: out = O.rgb + bg * (1 - a)"""
    o = rgba.astype(np.float32)
    return np.clip(o[..., :3] + bg * (1 - o[..., 3:4] / 255.0), 0, 255).astype(np.uint8)


def sheet(res_path, overlay, final, out, frames=None, cell=(360, 480)):
    res = load_json(res_path)
    C = res["canvas"]
    W, H, FPS = C["w"], C["h"], C["fps"]
    frames = frames or key_times(res)
    O = decode(overlay, frames, W, H, rgba=True)
    F = decode(final, frames, W, H) if final else {}
    cb = checker(H, W)
    cw, ch = cell
    cols = 2 if final else 1
    per_row = 4
    rows = (len(frames) + per_row - 1) // per_row
    lab = 26
    img = Image.new("RGB", (per_row * (cols * cw + 12) + 12, rows * (ch + lab + 12) + 12), (18, 18, 20))
    d = ImageDraw.Draw(img)
    for i, n in enumerate(frames):
        r, c = divmod(i, per_row)
        x = 12 + c * (cols * cw + 12)
        y = 12 + r * (ch + lab + 12)
        img.paste(Image.fromarray(over(O[n], cb)).resize(cell, Image.LANCZOS), (x, y))
        if final:
            img.paste(Image.fromarray(F[n]).resize(cell, Image.LANCZOS), (x + cw, y))
        d.text((x + 4, y + ch + 6), f"t={n / FPS:.3f}s  f{n}   overlay | final", fill=(230, 230, 230))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return {"out": str(out), "frames": frames}


def edges(res_path, overlay, final, out, frames=None, zoom=3, max_crops=8, crop=150):
    res = load_json(res_path)
    C = res["canvas"]
    W, H, FPS = C["w"], C["h"], C["fps"]
    frames = frames or key_times(res)
    B = page_bboxes(res, [n / FPS for n in frames])
    picks = []
    for n, boxes in zip(frames, B):
        for b in boxes:
            if b["alpha"] < 0.5:
                continue
            if b["role"] == "transition":   # look at the moving panel edge, not the full panel
                cx, cy = (b["x"] + b["w"] if b["x"] <= 1 else b["x"]), H * 0.35
            else:
                cx, cy = b["x"] + min(b["w"], 2 * crop) / 2, b["y"] + b["h"] / 2
            picks.append((n, b["item"], b["label"], int(cx), int(cy)))
    seen, sel = set(), []
    for p in picks:
        if (p[1], p[2]) in seen:
            continue
        seen.add((p[1], p[2]))
        sel.append(p)
    sel = sel[:max_crops]
    fr = sorted({p[0] for p in sel})
    O = decode(overlay, fr, W, H, rgba=True)
    F = decode(final, fr, W, H) if final else {}
    bgs = [("black", np.zeros((1, 1, 3), np.float32)), ("white", np.full((1, 1, 3), 255, np.float32)), ("checker", None), ("final", None)]
    cs = crop * zoom
    img = Image.new("RGB", (12 + len(bgs) * (cs + 8), 12 + len(sel) * (cs + 30)), (18, 18, 20))
    d = ImageDraw.Draw(img)
    for i, (n, item, label, cx, cy) in enumerate(sel):
        x0 = int(np.clip(cx - crop // 2, 0, W - crop))
        y0 = int(np.clip(cy - crop // 2, 0, H - crop))
        o = O[n][y0:y0 + crop, x0:x0 + crop]
        for j, (name, bg) in enumerate(bgs):
            if name == "checker":
                tile = over(o, checker(crop, crop, 10))
            elif name == "final":
                if n not in F:
                    continue
                tile = F[n][y0:y0 + crop, x0:x0 + crop]
            else:
                tile = over(o, np.broadcast_to(bg, (crop, crop, 3)))
            img.paste(Image.fromarray(tile).resize((cs, cs), Image.NEAREST), (12 + j * (cs + 8), 12 + i * (cs + 30) + 22))
        d.text((12, 12 + i * (cs + 30) + 4), f"f{n} t={n / FPS:.3f}s  {item} '{label}'  crop@({x0},{y0}) x{zoom}   [black | white | checker | final]", fill=(230, 230, 230))
    img.save(out)
    return {"out": str(out), "crops": len(sel)}
