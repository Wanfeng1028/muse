# -*- coding: utf-8 -*-
"""Tạo thumbnail video Tabcom: khung người nói + viền nét đứt + gradient xanh + tiêu đề."""
import os
import subprocess
import sys
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from rembg import remove, new_session

W, H = 1080, 1920
NAVY = (27, 42, 140, 255)
RED = (226, 26, 34, 255)
WHITE = (255, 255, 255, 255)
TEAL_TOP = (18, 214, 160)
TEAL_BOT = (16, 190, 170)

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import tabcom_paths as P
PSDIR = P.FONTS
FONTS = {
    "anton": (os.path.join(PSDIR, "PS Anton - Regular V1.0.otf"),) * 2,
    "shoulders": (os.path.join(PSDIR, "Big Shoulders ExtraBold Viet Hoa.otf"),) * 2,
}


def text_w(f, s):
    b = f.getbbox(s)
    return b[2] - b[0]


def fit(fp, size, s, maxw):
    f = ImageFont.truetype(fp, size)
    while text_w(f, s) > maxw and size > 20:
        size -= 2
        f = ImageFont.truetype(fp, size)
    return f


def segs(line):
    line = line.upper()
    """'Traffic *nội sàn*' -> [('Traffic ', NAVY), ('nội sàn', RED)]"""
    out, red = [], False
    for part in line.split("*"):
        if part:
            out.append((part, RED if red else NAVY))
        red = not red
    return out


def dashed_outline(mask, canvas, offset=26, thick=8, dash=38, gap=26):
    m = (mask > 128).astype(np.uint8)
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (offset * 2 + 1,) * 2))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61)))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return canvas
    c = max(cnts, key=cv2.contourArea).squeeze(1).astype(np.float32)
    # đi dọc contour, bật/tắt theo chu kỳ dash
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    dist, on = 0.0, True
    seg = []
    for i in range(len(c)):
        p, q = c[i], c[(i + 1) % len(c)]
        step = float(np.hypot(*(q - p)))
        if on:
            seg.append(tuple(p))
        dist += step
        limit = dash if on else gap
        if dist >= limit:
            if on and len(seg) > 1:
                d.line(seg, fill=WHITE, width=thick, joint="curve")
            seg = []
            on = not on
            dist = 0.0
    if on and len(seg) > 1:
        d.line(seg, fill=WHITE, width=thick, joint="curve")
    glow = layer.filter(ImageFilter.GaussianBlur(6))
    glow.putalpha(glow.split()[3].point(lambda v: int(v * 0.5)))
    canvas.alpha_composite(glow)
    canvas.alpha_composite(layer)
    return canvas


def gradient_edges(canvas, top_frac=0.30, bot_frac=0.26, alpha=0.62):
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = np.zeros((H, W, 4), dtype=np.uint8)
    th, bh = int(H * top_frac), int(H * bot_frac)
    for y in range(th):
        f = (1 - y / th) ** 1.7
        px[y, :, :3] = TEAL_TOP
        px[y, :, 3] = int(255 * alpha * f)
    for i in range(bh):
        y = H - 1 - i
        f = (1 - i / bh) ** 1.7
        px[y, :, :3] = TEAL_BOT
        px[y, :, 3] = int(255 * alpha * f)
    grad = Image.fromarray(px, "RGBA")
    base = canvas.convert("RGB")
    g_rgb = grad.convert("RGB")
    a = np.array(grad.split()[3]).astype(np.float32) / 255.0
    b = np.array(base).astype(np.float32)
    o = np.array(g_rgb).astype(np.float32)
    screen = 255 - (255 - b) * (255 - o) / 255.0
    out = b * (1 - a[..., None]) + screen * a[..., None]
    return Image.fromarray(out.clip(0, 255).astype(np.uint8)).convert("RGBA")


def title_panel(lines, fontkey, panel_w=960, pad_x=72, pad_y=50, gap=14, size=104):
    fp_bold, fp_black = FONTS[fontkey]
    inner = panel_w - 2 * pad_x
    fonts, sizes = [], []
    for ln in lines:
        plain = ln.replace("*", "").upper()
        f = fit(fp_black, size, plain, inner)
        fonts.append(f)
    s = min(f.size for f in fonts)
    fonts = [ImageFont.truetype(fp_black, s) for _ in lines]
    lh = max(sum(f.getmetrics()) for f in fonts)
    ph = 2 * pad_y + lh * len(lines) + gap * (len(lines) - 1)
    panel = Image.new("RGBA", (panel_w, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle((0, 0, panel_w - 1, ph - 1), 30, fill=(255, 255, 255, 246))
    y = pad_y
    for ln, f in zip(lines, fonts):
        parts = segs(ln)
        total = sum(text_w(f, t) for t, _ in parts)
        x = (panel_w - total) // 2
        for t, col in parts:
            d.text((x, y), t, font=f, fill=col)
            x += text_w(f, t)
        y += lh + gap
    sh = Image.new("RGBA", (panel_w + 60, ph + 60), (0, 0, 0, 0))
    m = panel.split()[3].point(lambda v: min(v, 70))
    sh.paste(Image.new("RGBA", panel.size, (0, 0, 0, 255)), (30, 40), m)
    sh = sh.filter(ImageFilter.GaussianBlur(12))
    sh.paste(panel, (30, 30), panel)
    return sh


def build(src_video, t, lines, out_path, fontkey="anton", panel_y=1400, grad=True):
    here = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(here, exist_ok=True)
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thumb")
    os.makedirs(tmp, exist_ok=True)
    # tên file tạm gắn với video + mốc thời gian, nếu không thumbnail video mới
    # sẽ dùng nhầm mask đã cache của video trước
    key = "%s_%s" % (os.path.splitext(os.path.basename(src_video))[0][:40], str(t).replace(".", "-"))
    frame = os.path.join(tmp, "_frame_%s.png" % key)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", src_video,
                    "-frames:v", "1", "-vf", f"scale={W}:{H}", frame], check=True)
    base = Image.open(frame).convert("RGBA")
    mask_p = frame.replace(".png", "-mask.png")
    if not os.path.exists(mask_p):
        s = new_session("birefnet-portrait")
        Image.fromarray(np.array(remove(Image.open(frame), session=s, only_mask=True))).save(mask_p)
    mask = np.array(Image.open(mask_p).convert("L"))
    canvas = gradient_edges(base) if grad else base
    canvas = dashed_outline(mask, canvas)
    panel = title_panel(lines, fontkey)
    canvas.alpha_composite(panel, ((W - panel.width) // 2, panel_y - panel.height // 2))
    canvas.convert("RGB").save(out_path, quality=95)
    print("saved", out_path, flush=True)


if __name__ == "__main__":
    # python make_thumb.py "<source.mp4>" <giay> "<dong 1, *cum nay mau do*>" "<dong 2>" [thu-muc-ra]
    # Không truyền tham số thì lấy video từ biến môi trường TABCOM_SRC,
    # ảnh ra nằm cạnh file video.
    a = sys.argv[1:]
    VIDEO = a[0] if a else P.src()
    T = float(a[1]) if len(a) > 1 else 62.0
    LINES = [a[2], a[3]] if len(a) > 3 else ["Traffic *nội sàn và ngoại sàn*",
                                             "shop bán online phải phân biệt"]
    OUTDIR = a[4] if len(a) > 4 else os.path.dirname(os.path.abspath(VIDEO))
    build(VIDEO, T, LINES, os.path.join(OUTDIR, "thumb-anton.jpg"), fontkey="anton")
    build(VIDEO, T, LINES, os.path.join(OUTDIR, "thumb-shoulders.jpg"), fontkey="shoulders")
