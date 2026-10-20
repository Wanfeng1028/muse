"""collage.py — paper-craft art kit for the 拼贴手账 vlog (PIL / numpy / cv2, deterministic).

Adapted from our own styles-v2/vlog/src/vlogkit.py (written from scratch in this project).
Technique notes (die-cut sticker edge + warm shadow, torn paper with a white core rim,
translucent washi tape, ransom-letter title, red stamp with missing ink, 8 Hz sticker boil)
follow common collage practice; no third-party code was copied.

Fonts (SIL OFL, from this repo's fonts/ — see FONT_DIR below): 思源黑体 SC for captions / cards,
霞鹜文楷 for small handwritten notes only.
"""
import math
import os
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Default points at this repo's fonts/ (library/_shared/vlog-collage-runtime/src/collage.py
# -> parents[4] is the repo root); override with XM_FONT_DIR to point elsewhere.
FONT_DIR = os.environ.get("XM_FONT_DIR", str(Path(__file__).resolve().parents[4] / "fonts") + "/")
FONT_FILES = {
    'hei_heavy': FONT_DIR + 'SourceHanSansSC-Heavy.otf',
    'hei_bold': FONT_DIR + 'SourceHanSansSC-Bold.otf',
    'hei': FONT_DIR + 'SourceHanSansSC-Medium.otf',
    'kai': FONT_DIR + 'LXGWWenKai-Medium.ttf',
    'kai_r': FONT_DIR + 'LXGWWenKai-Regular.ttf',
}
_fc = {}

# palette (cream / kraft / ink / stamp red / pink / mustard / sage)
CREAM = (243, 236, 222)
PAPER_W = (252, 250, 245)
KRAFT = (214, 186, 144)
INK = (74, 58, 46)
INK_D = (52, 40, 32)
RED = (201, 70, 61)
PINK = (236, 196, 192)
PINK_D = (226, 128, 136)
MUSTARD = (242, 205, 112)
SAGE = (187, 201, 168)
SKY = (178, 208, 226)
SHADOW = (60, 36, 16)          # warm brown shadow


def font(name, size):
    k = (name, int(size))
    if k not in _fc:
        _fc[k] = ImageFont.truetype(FONT_FILES[name], int(size))
    return _fc[k]


def rng(seed):
    return random.Random(seed)


def blank(w, h, c=(0, 0, 0, 0)):
    return Image.new('RGBA', (int(w), int(h)), c)


def rgba(img):
    return img if img.mode == 'RGBA' else img.convert('RGBA')


def pad(img, p):
    img = rgba(img)
    out = blank(img.width + 2 * p, img.height + 2 * p)
    out.paste(img, (p, p), img)
    return out


def alpha_of(img):
    return np.asarray(rgba(img))[:, :, 3].astype(np.float32) / 255.0


def fill_holes(a):
    m = (a > 0.5).astype(np.uint8)
    work = (1 - m).astype(np.uint8)
    flood = np.zeros((m.shape[0] + 2, m.shape[1] + 2), np.uint8)
    cv2.floodFill(work, flood, (0, 0), 2)
    out = a.copy(); out[work == 1] = 1.0
    return out


def die_cut(img, radius, color=(255, 255, 255, 255)):
    """white die-cut sticker edge: silhouette grown by `radius` px, holes filled"""
    p = int(radius + 4)
    img = pad(img, p)
    a = alpha_of(img)
    dist = cv2.distanceTransform((a < 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    edge = fill_holes(np.maximum(np.clip(radius + 0.5 - dist, 0, 1), a))
    base = np.zeros((img.height, img.width, 4), np.uint8)
    base[:, :, :3] = color[:3]; base[:, :, 3] = (edge * color[3]).astype(np.uint8)
    out = Image.fromarray(base, 'RGBA'); out.alpha_composite(img)
    return out


def shadow(img, blur=12, dx=0, dy=7, op=0.36, color=SHADOW):
    img = rgba(img)
    p = int(blur * 2 + max(abs(dx), abs(dy)) + 2)
    big = pad(img, p)
    a = alpha_of(big)
    sh = np.zeros((big.height, big.width, 4), np.uint8)
    sh[:, :, :3] = color; sh[:, :, 3] = np.clip(a * 255 * op, 0, 255).astype(np.uint8)
    shi = Image.fromarray(sh, 'RGBA').filter(ImageFilter.GaussianBlur(blur))
    out = blank(big.width, big.height)
    out.paste(shi, (int(dx), int(dy)), shi)
    out.alpha_composite(big)
    return out


def sticker(img, edge=10, sh=(10, 0, 6, 0.34)):
    return shadow(die_cut(img, edge), *sh)


def with_mask(img, mask):
    out = rgba(img).copy()
    a = np.minimum(np.asarray(out)[:, :, 3], np.asarray(mask))
    out.putalpha(Image.fromarray(a.astype(np.uint8)))
    return out


def rounded_mask(w, h, r, ss=3):
    m = Image.new('L', (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], r * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def shape_mask(w, h, kind, ss=3, **kw):
    m = Image.new('L', (w * ss, h * ss), 0)
    d = ImageDraw.Draw(m)
    cx, cy = w * ss / 2, h * ss / 2
    if kind == 'circle':
        d.ellipse([0, 0, w * ss - 1, h * ss - 1], fill=255)
    elif kind == 'heart':
        pts = []
        for i in range(400):
            t = i / 400 * 2 * math.pi
            x = 16 * math.sin(t) ** 3
            y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
            pts.append((cx + x / 17 * cx, cy + (y + 2) / 17 * cy))
        d.polygon(pts, fill=255)
    elif kind == 'star':
        n = kw.get('n', 5); ro = min(cx, cy); ri = ro * kw.get('inner', 0.5)
        pts = [(cx + (ro if i % 2 == 0 else ri) * math.cos(-math.pi / 2 + i * math.pi / n),
                cy + (ro if i % 2 == 0 else ri) * math.sin(-math.pi / 2 + i * math.pi / n)) for i in range(n * 2)]
        d.polygon(pts, fill=255)
    elif kind == 'scallop':
        n = kw.get('n', 14); rr = min(cx, cy); bump = rr * kw.get('bump', 0.14)
        pts = []
        for i in range(720):
            t = i / 720 * 2 * math.pi
            r = rr - bump + bump * abs(math.cos(t * n / 2))
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
        d.polygon(pts, fill=255)
    return m.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------ text
def text_layer(txt, fnt, fill=(255, 255, 255, 255), stroke=0, stroke_fill=None, spacing=0, padding=None):
    p = padding if padding is not None else int(stroke + fnt.size * 0.25)
    asc, desc = fnt.getmetrics()
    tw = int(sum(fnt.getlength(c) for c in txt) + spacing * max(0, len(txt) - 1)) if spacing else int(fnt.getlength(txt))
    img = blank(tw + 2 * p, asc + desc + 2 * p)
    d = ImageDraw.Draw(img)
    if spacing:
        x = p
        for c in txt:
            d.text((x, p), c, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
            x += fnt.getlength(c) + spacing
    else:
        d.text((p, p), txt, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    bb = img.getbbox()
    if bb:
        img = img.crop((max(0, bb[0] - 2), max(0, bb[1] - 2), min(img.width, bb[2] + 2), min(img.height, bb[3] + 2)))
    return img


def sticker_text(txt, fnt, fill=INK_D + (255,), edge=12, keyline=None, sh=(9, 0, 6, 0.36), spacing=0):
    """black-body sticker lettering: glyphs (optionally with a thin coloured keyline) on a white
    die-cut edge with a warm drop shadow"""
    if keyline:
        base = text_layer(txt, fnt, fill=keyline[0], stroke=keyline[1], stroke_fill=keyline[0], spacing=spacing, padding=edge + 8)
        top = text_layer(txt, fnt, fill=fill, spacing=spacing, padding=edge + 8 + keyline[1])
        img = blank(max(base.width, top.width), max(base.height, top.height))
        img.alpha_composite(base, ((img.width - base.width) // 2, (img.height - base.height) // 2))
        img.alpha_composite(top, ((img.width - top.width) // 2, (img.height - top.height) // 2))
    else:
        img = text_layer(txt, fnt, fill=fill, spacing=spacing, padding=edge + 8)
    return shadow(die_cut(img, edge), *sh)


# ------------------------------------------------------------------ paper, tears, tape
def paper(w, h, color=CREAM, seed=1, fiber=1.0, blotch=1.0):
    r = np.random.default_rng(seed)
    base = np.ones((h, w, 3), np.float32) * np.array(color, np.float32)
    lo = cv2.resize(r.normal(0, 1, (max(2, h // 60), max(2, w // 60))).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    fine = cv2.GaussianBlur(r.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 0.8)
    img = base * (1 + 0.018 * blotch * lo + 0.02 * fine)[:, :, None]
    fib = np.zeros((h, w), np.float32)
    n = int(w * h / 900 * fiber)
    xs = r.uniform(0, w, n); ys = r.uniform(0, h, n); ang = r.uniform(0, math.pi, n); ln = r.uniform(4, 16, n)
    sg = r.choice([-1.0, 1.0], n)
    for x, y, a, l, s in zip(xs, ys, ang, ln, sg):
        cv2.line(fib, (int(x), int(y)), (int(x + math.cos(a) * l), int(y + math.sin(a) * l)), float(s), 1, cv2.LINE_AA)
    img = img * (1 + 0.032 * cv2.GaussianBlur(fib, (0, 0), 0.5)[:, :, None])
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert('RGBA')


def tear_profile(n, seed, amp=10.0, rough=1.0):
    r = np.random.default_rng(seed)
    size = 1 << int(math.ceil(math.log2(max(2, n))))
    p = np.zeros(size + 1, np.float32)
    step = size; a = amp
    while step > 1:
        half = step // 2
        for i in range(0, size, step):
            p[i + half] = (p[i] + p[i + step]) / 2 + r.uniform(-a, a) * (rough if step <= 32 else 1)
        step = half; a *= 0.62
    p += r.uniform(-1.2, 1.2, size + 1) * rough
    return p[:n]


def torn_sheet(w, h, color=PAPER_W, seed=3, edges='tb', amp=9, rim=5, rim_color=(255, 253, 248), tex=True):
    """paper with torn edges (t/b/l/r) showing a lighter core rim; .pad / .core attached"""
    pad_ = int(amp * 3 + rim + 4)
    Wd, Hd = w + 2 * pad_, h + 2 * pad_
    ys, xs = np.mgrid[0:Hd, 0:Wd].astype(np.float32)

    def inside(off):
        m = np.ones((Hd, Wd), bool)
        m &= ys >= pad_ + (tear_profile(Wd, seed, amp)[None, :] if 't' in edges else 0) - off
        m &= ys <= pad_ + h + (tear_profile(Wd, seed + 11, amp)[None, :] if 'b' in edges else 0) + off
        m &= xs >= pad_ + (tear_profile(Hd, seed + 23, amp)[:, None] if 'l' in edges else 0) - off
        m &= xs <= pad_ + w + (tear_profile(Hd, seed + 37, amp)[:, None] if 'r' in edges else 0) + off
        return m

    outer = cv2.GaussianBlur(inside(rim).astype(np.float32), (0, 0), 0.7)
    core = cv2.GaussianBlur(inside(0).astype(np.float32), (0, 0), 0.6)
    arr = np.zeros((Hd, Wd, 4), np.float32); arr[:, :, :3] = rim_color; arr[:, :, 3] = outer * 255
    top = np.zeros_like(arr); top[:, :, :3] = color; top[:, :, 3] = core * 255
    out = Image.fromarray(arr.astype(np.uint8), 'RGBA')
    out.alpha_composite(Image.fromarray(top.astype(np.uint8), 'RGBA'))
    if tex:
        g = np.asarray(paper(Wd, Hd, (128, 128, 128), seed=seed + 5))[:, :, 0].astype(np.float32) / 128.0
        a = np.asarray(out).astype(np.float32); a[:, :, :3] *= g[:, :, None]
        out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA')
    out.pad = pad_; out.core = core
    return out


def washi(w, h, color=MUSTARD, alpha=0.8, pattern=None, pcolor=(255, 255, 255), seed=5):
    """translucent washi tape with zig-zag torn ends and an optional pattern"""
    ss = 3; r = rng(seed)
    img = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    pts = [(r.uniform(0, 4) * ss, i) for i in range(0, h * ss + 1, 5 * ss)]
    pts += [(w * ss - r.uniform(0, 4) * ss, i) for i in range(h * ss, -1, -5 * ss)]
    d.polygon(pts, fill=tuple(color) + (255,))
    if pattern:
        pat = Image.new('RGBA', img.size, (0, 0, 0, 0)); pd = ImageDraw.Draw(pat)
        if pattern == 'stripe':
            s = 14 * ss
            for x in range(-h * ss, w * ss + h * ss, s):
                pd.polygon([(x, 0), (x + s // 2, 0), (x + s // 2 - h * ss, h * ss), (x - h * ss, h * ss)], fill=pcolor + (150,))
        elif pattern == 'dot':
            for y in range(6 * ss, h * ss, 12 * ss):
                off = (y // (12 * ss)) % 2 * 6 * ss
                for x in range(4 * ss + off, w * ss, 12 * ss):
                    pd.ellipse([x - 2.4 * ss, y - 2.4 * ss, x + 2.4 * ss, y + 2.4 * ss], fill=pcolor + (190,))
        elif pattern == 'grid':
            for x in range(0, w * ss, 10 * ss):
                pd.line([(x, 0), (x, h * ss)], fill=pcolor + (110,), width=ss)
            for y in range(0, h * ss, 10 * ss):
                pd.line([(0, y), (w * ss, y)], fill=pcolor + (110,), width=ss)
        a = np.asarray(img)[:, :, 3]
        pa = np.asarray(pat).copy(); pa[:, :, 3] = np.minimum(pa[:, :, 3], a)
        img.alpha_composite(Image.fromarray(pa, 'RGBA'))
    img = img.resize((w, h), Image.LANCZOS)
    arr = np.asarray(img).astype(np.float32)
    tex = np.asarray(paper(w, h, (128, 128, 128), seed=seed))[:, :, 0].astype(np.float32) / 128
    arr[:, :, :3] *= tex[:, :, None]; arr[:, :, 3] *= alpha
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGBA')


# ------------------------------------------------------------------ doodles / icons
def wobble(pts, seed, amt=1.2, step=6):
    r = np.random.default_rng(seed)
    out = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / step))
        out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
    out.append(pts[-1])
    arr = np.array(out, np.float32)
    return [tuple(p) for p in arr + r.normal(0, amt, arr.shape).astype(np.float32)]


def pen(size, strokes, color, width, ss=3, seed=1, amt=1.0):
    w, h = size
    img = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    for k, s in enumerate(strokes):
        pts = [(x * ss, y * ss) for x, y in wobble(s, seed + k, amt)]
        d.line(pts, fill=color, width=int(width * ss), joint='curve')
        rr = width * ss / 2
        for x, y in (pts[0], pts[-1]):
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=color)
    return img.resize((w, h), Image.LANCZOS)


def curved_arrow(w, h, color, width=5, seed=3, bend=0.35, head=20):
    p0 = (width * 2, h - width * 2); p2 = (w - width * 3, width * 3)
    mx, my = (p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2
    nx, ny = -(p2[1] - p0[1]), (p2[0] - p0[0]); L = math.hypot(nx, ny); nx, ny = nx / L, ny / L
    c = (mx + nx * bend * L * 0.5, my + ny * bend * L * 0.5)
    pts = [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p2[0], (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p2[1])
           for t in [i / 40 for i in range(41)]]
    a = math.atan2(pts[-1][1] - pts[-4][1], pts[-1][0] - pts[-4][0])
    hd = [(p2[0] - head * math.cos(a - 0.5), p2[1] - head * math.sin(a - 0.5)), p2,
          (p2[0] - head * math.cos(a + 0.5), p2[1] - head * math.sin(a + 0.5))]
    return pen((w, h), [pts, hd], color, width, seed=seed)


def icon(kind, size, color, accent=None, ss=4):
    s = size * ss; img = Image.new('RGBA', (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    c = s / 2; lw = max(2, int(s * 0.075)); accent = accent or color
    if kind == 'sun':
        r = s * 0.2
        for i in range(8):
            a = i * math.pi / 4
            p0 = (c + math.cos(a) * r * 1.5, c + math.sin(a) * r * 1.5); p1 = (c + math.cos(a) * r * 2.15, c + math.sin(a) * r * 2.15)
            d.line([p0, p1], fill=color, width=lw)
            for (x, y) in (p0, p1):
                d.ellipse([x - lw / 2, y - lw / 2, x + lw / 2, y + lw / 2], fill=color)
        d.ellipse([c - r, c - r, c + r, c + r], fill=color)
    elif kind == 'cloud':
        for (x, y, r) in [(0.36, 0.56, 0.17), (0.52, 0.45, 0.22), (0.68, 0.57, 0.15), (0.5, 0.62, 0.16)]:
            d.ellipse([s * (x - r), s * (y - r), s * (x + r), s * (y + r)], fill=color)
        d.rounded_rectangle([s * 0.2, s * 0.56, s * 0.82, s * 0.74], radius=s * 0.09, fill=color)
    elif kind == 'suncloud':
        img.alpha_composite(icon('sun', size, accent, ss=ss).resize((s, s)).transform((s, s), Image.AFFINE, (1, 0, s * 0.16, 0, 1, s * 0.14)))
        cl = icon('cloud', size, color, ss=ss).resize((s, s))
        img.alpha_composite(cl.transform((s, s), Image.AFFINE, (1, 0, -s * 0.08, 0, 1, -s * 0.12)))
    elif kind == 'moon':
        d.ellipse([s * 0.14, s * 0.14, s * 0.86, s * 0.86], fill=color)
        d.ellipse([s * 0.34, s * 0.04, s * 1.02, s * 0.72], fill=(0, 0, 0, 0))
    elif kind == 'heart':
        img.paste(Image.new('RGBA', (s, s), color), (0, 0), shape_mask(size, size, 'heart').resize((s, s), Image.LANCZOS))
    elif kind == 'star':
        img.paste(Image.new('RGBA', (s, s), color), (0, 0), shape_mask(size, size, 'star', inner=0.48).resize((s, s), Image.LANCZOS))
    elif kind == 'sparkle':
        pts = [(c + (s * 0.48 if i % 2 == 0 else s * 0.12) * math.cos(-math.pi / 2 + i * math.pi / 4),
                c + (s * 0.48 if i % 2 == 0 else s * 0.12) * math.sin(-math.pi / 2 + i * math.pi / 4)) for i in range(8)]
        d.polygon(pts, fill=color)
    elif kind == 'clock':
        r = s * 0.4
        d.ellipse([c - r, c - r, c + r, c + r], fill=accent)
        d.ellipse([c - r, c - r, c + r, c + r], outline=color, width=lw)
        d.line([(c, c), (c, c - r * 0.58)], fill=color, width=lw)
        d.line([(c, c), (c + r * 0.42, c + r * 0.18)], fill=color, width=lw)
        d.ellipse([c - lw, c - lw, c + lw, c + lw], fill=color)
    elif kind == 'smile':
        r = s * 0.42
        d.ellipse([c - r, c - r, c + r, c + r], fill=color)
        e = s * 0.045
        for x in (c - r * 0.36, c + r * 0.36):
            d.ellipse([x - e, c - r * 0.22 - e * 1.5, x + e, c - r * 0.22 + e * 1.5], fill=accent)
        d.arc([c - r * 0.48, c - r * 0.3, c + r * 0.48, c + r * 0.52], 20, 160, fill=accent, width=lw)
        for x in (c - r * 0.62, c + r * 0.62):   # cheeks
            d.ellipse([x - s * 0.06, c + r * 0.12 - s * 0.035, x + s * 0.06, c + r * 0.12 + s * 0.035], fill=(236, 150, 150, 200))
    elif kind == 'calm':   # relaxed face: closed eyes
        r = s * 0.42
        d.ellipse([c - r, c - r, c + r, c + r], fill=color)
        for x in (c - r * 0.36, c + r * 0.36):
            d.arc([x - s * 0.07, c - r * 0.3, x + s * 0.07, c - r * 0.1], 200, 340, fill=accent, width=lw)
        d.arc([c - r * 0.3, c - r * 0.1, c + r * 0.3, c + r * 0.4], 30, 150, fill=accent, width=lw)
        for x in (c - r * 0.62, c + r * 0.62):
            d.ellipse([x - s * 0.06, c + r * 0.12 - s * 0.035, x + s * 0.06, c + r * 0.12 + s * 0.035], fill=(236, 150, 150, 200))
    elif kind == 'drop':   # water drop / cold
        d.polygon([(c, s * 0.12), (c - s * 0.26, s * 0.58), (c + s * 0.26, s * 0.58)], fill=color)
        d.ellipse([c - s * 0.27, s * 0.4, c + s * 0.27, s * 0.9], fill=color)
    elif kind == 'note':   # music note
        d.ellipse([s * 0.18, s * 0.6, s * 0.46, s * 0.84], fill=color)
        d.line([(s * 0.44, s * 0.72), (s * 0.44, s * 0.16)], fill=color, width=lw)
        d.polygon([(s * 0.44, s * 0.16), (s * 0.8, s * 0.26), (s * 0.8, s * 0.38), (s * 0.44, s * 0.3)], fill=color)
    elif kind == 'ball':
        r = s * 0.4
        d.ellipse([c - r, c - r, c + r, c + r], fill=color)
        d.arc([c - r, c - r, c + r, c + r], 0, 360, fill=accent, width=lw // 2 + 1)
        d.line([(c - r, c), (c + r, c)], fill=accent, width=lw // 2 + 1)
        d.line([(c, c - r), (c, c + r)], fill=accent, width=lw // 2 + 1)
    return img.resize((size, size), Image.LANCZOS)


# ------------------------------------------------------------------ props
def rubber_stamp(big, small, color=RED, seed=4, big_size=62, small_size=24, pad_=26):
    """red rubber stamp with uneven / missing ink"""
    fb, fs = font('hei_heavy', big_size), font('hei_bold', small_size)
    tb = text_layer(big, fb, fill=color + (255,), padding=2)
    ts = text_layer(small, fs, fill=color + (255,), spacing=4, padding=2) if small else None
    w = max(tb.width, ts.width if ts else 0) + 2 * pad_
    h = tb.height + (ts.height + 8 if ts else 0) + 2 * pad_ - 6
    img = blank(w + 20, h + 20); d = ImageDraw.Draw(img)
    d.rounded_rectangle([10, 10, 10 + w, 10 + h], 12, outline=color + (255,), width=6)
    d.rounded_rectangle([19, 19, 1 + w, 1 + h], 8, outline=color + (255,), width=2)
    img.alpha_composite(tb, ((img.width - tb.width) // 2, 10 + pad_ - 4))
    if ts:
        img.alpha_composite(ts, ((img.width - ts.width) // 2, 10 + pad_ + tb.height + 4))
    a = np.asarray(img).astype(np.float32)
    rr = np.random.default_rng(seed)
    noise = rr.random(a.shape[:2]).astype(np.float32)
    blot = np.asarray(paper(img.width, img.height, (128, 128, 128), seed=seed))[:, :, 0].astype(np.float32) / 128
    streak = cv2.GaussianBlur(rr.normal(0, 1, (a.shape[0] // 6 + 1, a.shape[1] // 6 + 1)).astype(np.float32), (0, 0), 1.2)
    streak = cv2.resize(streak, (a.shape[1], a.shape[0]))
    keep = (noise > 0.1).astype(np.float32) * np.clip((blot - 0.86) * 6, 0.45, 1) * np.clip(1.25 + streak * 0.9, 0.25, 1)
    a[:, :, 3] *= keep
    return Image.fromarray(a.astype(np.uint8), 'RGBA').filter(ImageFilter.GaussianBlur(0.5))


def ransom_tiles(text, size, seed=3):
    """剪报字: each character cut from a different paper, font weight and angle -> [(tile, angle, dy)]"""
    r = rng(seed)
    papers = [((252, 249, 242), INK + (255,)), ((46, 42, 40), (250, 244, 232, 255)), (KRAFT, (60, 42, 30, 255)),
              (PINK, (120, 44, 52, 255)), ((250, 222, 120), (70, 50, 30, 255)), (SAGE, (40, 56, 40, 255))]
    fonts = ['hei_heavy', 'hei', 'hei_bold', 'hei_heavy', 'hei']      # 剪报字 stays 思源黑体 (3 weights)
    order = [1, 4, 0, 3, 5, 2]
    tiles = []
    for i, ch in enumerate(text):
        bgc, fg = papers[order[(i + seed) % len(order)]]
        fname = fonts[(i + seed) % len(fonts)]
        fn = font(fname, int(size * r.uniform(0.86, 1.06)))
        g = text_layer(ch, fn, fill=fg, stroke=1 if fname.startswith('hei') else 0, stroke_fill=fg, padding=2)
        pw, ph = int(g.width + size * r.uniform(0.24, 0.36)), int(g.height + size * r.uniform(0.22, 0.34))
        sheet = paper(pw, ph, bgc, seed=seed * 10 + i, fiber=0.8)
        m = Image.new('L', (pw * 3, ph * 3), 0); j = size * 0.05 * 3
        pts = [(r.uniform(0, j), r.uniform(0, j)), (pw * 3 - r.uniform(0, j), r.uniform(0, j)),
               (pw * 3 - r.uniform(0, j), ph * 3 - r.uniform(0, j)), (r.uniform(0, j), ph * 3 - r.uniform(0, j))]
        ImageDraw.Draw(m).polygon(pts, fill=255)
        sheet = with_mask(sheet, m.resize((pw, ph), Image.LANCZOS))
        sheet.alpha_composite(g, ((pw - g.width) // 2, (ph - g.height) // 2))
        tiles.append((shadow(sheet, 6, 2, 5, 0.38), (-1) ** i * r.uniform(3, 9), r.uniform(-12, 12)))
    return tiles


def kraft_tag(content, pad_x=26, pad_y=14, seed=12, color=KRAFT, rim=(236, 222, 196)):
    """torn kraft paper tag around an RGBA content layer"""
    tag = torn_sheet(content.width + 2 * pad_x, content.height + 2 * pad_y, color, seed=seed, edges='lr', amp=6, rim=4, rim_color=rim)
    tag.alpha_composite(content, ((tag.width - content.width) // 2, (tag.height - content.height) // 2))
    return tag


def hstack(layers, gap=8, valign='center'):
    w = sum(l.width for l in layers) + gap * (len(layers) - 1); h = max(l.height for l in layers)
    out = blank(w, h); x = 0
    for l in layers:
        y = (h - l.height) // 2 if valign == 'center' else h - l.height
        out.alpha_composite(l, (x, y)); x += l.width + gap
    return out


def time_card(hhmm, seed=21):
    """小卡片 · 时间: clock icon + HH:MM on a torn kraft tag, pink washi on top"""
    clk = icon('clock', 58, INK + (255,), accent=(252, 248, 238, 255))
    txt = text_layer(hhmm, font('hei_heavy', 56), fill=INK_D + (255,), padding=2)
    tag = kraft_tag(hstack([clk, txt], 12), 24, 12, seed=seed)
    tag = shadow(tag, 8, 2, 6, 0.36)
    tape = washi(96, 34, PINK, 0.86, 'dot', seed=seed + 1).rotate(-12, resample=Image.BICUBIC, expand=True)
    out = blank(tag.width + 20, tag.height + 26)
    out.alpha_composite(tag, (10, 20))
    out.alpha_composite(tape, (18, 0))
    return out


def weather_card(kind, label, seed=31):
    """小卡片 · 天气: round scalloped die-cut sticker with an icon + one character"""
    D = 170
    base = paper(D, D, (250, 247, 238), seed=seed, fiber=0.5)
    base = with_mask(base, shape_mask(D, D, 'scallop', n=16, bump=0.08))
    ic = icon(kind, 92, (246, 188, 70, 255) if kind == 'sun' else (150, 178, 200, 255), accent=(246, 188, 70, 255))
    base.alpha_composite(ic, ((D - 92) // 2, 18))
    t = text_layer(label, font('hei_heavy', 40), fill=INK_D + (255,), padding=2)
    base.alpha_composite(t, ((D - t.width) // 2, 104))
    return shadow(die_cut(base, 8), 9, 1, 6, 0.34)


def mood_card(label, face='smile', color=PINK, seed=41):
    """小卡片 · 心情: pink rounded ticket with a face + 心情 label"""
    f = icon(face, 64, (255, 214, 120, 255), accent=INK + (255,))
    small = text_layer('心情', font('hei_bold', 24), fill=(150, 90, 90, 255), padding=2)
    big = text_layer(label, font('hei_heavy', 44), fill=INK_D + (255,), padding=2)
    col = blank(max(small.width, big.width), small.height + big.height + 2)
    col.alpha_composite(small, (0, 0)); col.alpha_composite(big, (0, small.height + 2))
    content = hstack([f, col], 12)
    w, h = content.width + 44, content.height + 30
    card = paper(w, h, color, seed=seed, fiber=0.6)
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([7, 7, w - 8, h - 8], 14, outline=(255, 255, 255, 170), width=3)
    card = with_mask(card, rounded_mask(w, h, 20))
    card.alpha_composite(content, (22, 15))
    return shadow(die_cut(card, 7), 9, 1, 6, 0.34)


def handwrite(txt, size=46, color=INK + (255,), under=None, seed=3, bold=1):
    """霞鹜文楷 small handwritten note (optionally underlined with a pen stroke)"""
    t = text_layer(txt, font('kai', size), fill=color, stroke=bold, stroke_fill=color, padding=6)
    if not under:
        return t
    ul = pen((t.width + 10, 26), [[(6, 14), (t.width * 0.5, 9), (t.width + 2, 13)]], under, 4, seed=seed)
    out = blank(t.width + 10, t.height + 18)
    out.alpha_composite(t, (0, 0)); out.alpha_composite(ul, (0, t.height - 8))
    return out
