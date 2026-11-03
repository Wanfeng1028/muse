"""Storyboard v1 drawing kit (paper family): paper, labels, tape, C subtitles, PiP, step bar, icons.

All drawing is PIL + numpy, 1080x1920. Every overlay placed through Frame.add() is recorded with its
bounding box so check() can report overlaps with the face / lips boxes and between overlays.
"""
import math
import os
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

W, H = 1080, 1920
# Default resolves to this repo's own fonts/ (this file lives at library/_shared/storyboard-frames/src/,
# so parents[4] is the repo root); override with XM_FONT_DIR to point elsewhere.
FONTS = Path(os.environ.get("XM_FONT_DIR", str(Path(__file__).resolve().parents[4] / 'fonts')))

INK = (28, 27, 25)
PAPER = (246, 241, 231)
CARD = (255, 253, 248)
KRAFT = (226, 205, 168)
YELLOW = (255, 214, 10)          # same marker yellow as the approved C subtitle sample
RED = (214, 64, 44)
GREEN = (38, 150, 88)
BLUE = (47, 107, 255)
GREY = (150, 145, 136)

SUB_CY = 1368                    # C subtitle centre (same as refs-0926 option_c); strip y 1312..1424
SAFE_TOP, SAFE_BOTTOM = 180, 1480
PIP_BOX = (726, 846, 1050, 1290)  # outer box of the bottom-right PiP (sits above the subtitle strip)

_fc = {}


def font(weight, size):
    key = (weight, size)
    if key not in _fc:
        if weight == 'Kai':
            path = FONTS / 'LXGWWenKai-Medium.ttf'
        else:
            path = FONTS / f'SourceHanSansSC-{weight}.otf'
        _fc[key] = ImageFont.truetype(str(path), size)
    return _fc[key]


# ---------------------------------------------------------------- paper & basic shapes
def paper(w=W, h=H, tone=PAPER, dots=0, seed=1, grain=5.0, blotch=7.0):
    rng = np.random.default_rng(seed)
    base = np.ones((h, w, 3), np.float32) * np.array(tone, np.float32)
    low = rng.normal(0, 1, (h // 24 + 2, w // 24 + 2)).astype(np.float32)
    low = cv2.resize(low, (w, h), interpolation=cv2.INTER_CUBIC)
    low = cv2.GaussianBlur(low, (0, 0), 30)
    fine = rng.normal(0, 1, (h, w)).astype(np.float32)
    base += (low * blotch + fine * grain)[..., None] * np.array([1, 0.97, 0.9], np.float32)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert('RGBA')
    if dots:
        d = ImageDraw.Draw(img)
        for y in range(dots // 2, h, dots):
            for x in range(dots // 2, w, dots):
                d.ellipse((x - 1.6, y - 1.6, x + 1.6, y + 1.6), fill=(196, 186, 170, 255))
    return img


def rrect_mask(w, h, r, ss=2):
    m = Image.new('L', (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=r * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def shadow_of(elem, blur=12, alpha=0.32, spread=0):
    a = elem.split()[3]
    if spread:
        a = a.filter(ImageFilter.MaxFilter(spread * 2 + 1))
    pad = blur * 3
    big = Image.new('L', (elem.width + 2 * pad, elem.height + 2 * pad), 0)
    big.paste(a, (pad, pad))
    big = big.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    sh = Image.new('RGBA', big.size, (20, 16, 10, 0))
    sh.putalpha(big)
    return sh, pad


def rotate(elem, deg):
    if not deg:
        return elem
    return elem.rotate(deg, resample=Image.BICUBIC, expand=True)


def torn_edge_mask(w, h, amp=3, seed=0, sides='lr'):
    rng = random.Random(seed)
    m = Image.new('L', (w, h), 255)
    d = ImageDraw.Draw(m)
    if 'l' in sides:
        pts = [(0, 0)] + [(rng.uniform(0, amp * 2), y) for y in range(0, h + 4, 4)] + [(0, h)]
        d.polygon(pts, fill=0)
    if 'r' in sides:
        pts = [(w, 0)] + [(w - rng.uniform(0, amp * 2), y) for y in range(0, h + 4, 4)] + [(w, h)]
        d.polygon(pts, fill=0)
    return m


def tape(w=150, h=40, color=(250, 222, 120), alpha=205, seed=0, stripes=False):
    t = Image.new('RGBA', (w, h), color + (alpha,))
    if stripes:
        d = ImageDraw.Draw(t)
        for x in range(-h, w + h, 18):
            d.line((x, h, x + h, 0), fill=(255, 255, 255, 70), width=6)
    m = torn_edge_mask(w, h, amp=3, seed=seed)
    a = ImageChops.multiply(t.split()[3], m)
    t.putalpha(a)
    return t


# ---------------------------------------------------------------- text helpers
def text_size(txt, f):
    b = f.getbbox(txt)
    return f.getlength(txt), b[3] - b[1]


def label(runs, size=64, pad=(28, 18), bg=CARD, radius=14, marker=YELLOW, tracking=2, color=INK,
          weight_normal='Medium', weight_key='Heavy', key_bg=None, border=None):
    """Paper label.  runs = [(text, is_key)].  Key runs: Heavy + marker block under the glyphs."""
    fN, fK = font(weight_normal, size), font(weight_key, size)
    chars = [(ch, k) for t, k in runs for ch in t]
    xs, x = [], 0.0
    for i, (ch, k) in enumerate(chars):
        f = fK if k else fN
        xs.append(x)
        x += f.getlength(ch) + (tracking if i < len(chars) - 1 else 0)
    tw = x
    asc = int(size * 0.88)
    w, h = int(tw + 2 * pad[0]), int(size * 1.12 + 2 * pad[1])
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if bg is not None:
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=bg + (255,) if len(bg) == 3 else bg,
                            outline=border, width=3 if border else 0)
    base = pad[1] + asc
    # marker blocks under each contiguous key run
    i = 0
    while i < len(chars):
        if chars[i][1] and marker is not None:
            j = i
            while j + 1 < len(chars) and chars[j + 1][1]:
                j += 1
            x0 = pad[0] + xs[i] - 6
            x1 = pad[0] + xs[j] + fK.getlength(chars[j][0]) + 6
            d.rectangle((x0, base - size * 0.45, x1, base + size * 0.12), fill=marker)
            i = j + 1
        else:
            i += 1
    for (ch, k), x0 in zip(chars, xs):
        d.text((pad[0] + x0, base), ch, font=fK if k else fN, fill=color, anchor='ls')
    return img


def vlabel(text, size=110, pad=(22, 26), bg=CARD, radius=16, color=INK, weight='Heavy', marker=None, gap=4):
    """Vertical (top-to-bottom) paper label."""
    f = font(weight, size)
    cw = max(f.getlength(c) for c in text)
    w = int(cw + 2 * pad[0])
    h = int(len(text) * (size + gap) - gap + 2 * pad[1])
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=bg + (255,))
    if marker:
        d.rectangle((w * 0.52, pad[1] - 4, w - pad[0] + 8, h - pad[1] + 4), fill=marker)
    for i, c in enumerate(text):
        cy = pad[1] + i * (size + gap) + size / 2
        d.text((w / 2, cy), c, font=f, fill=color, anchor='mm')
    return img


def plain_text(txt, size, weight='Heavy', color=INK, stroke=0, stroke_fill=(255, 255, 255)):
    f = font(weight, size)
    b = f.getbbox(txt, stroke_width=stroke)
    img = Image.new('RGBA', (b[2] - b[0] + 8, b[3] - b[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((4 - b[0], 4 - b[1]), txt, font=f, fill=color, stroke_width=stroke, stroke_fill=stroke_fill)
    return img


def sticker_outline(elem, px=10, color=(255, 255, 255)):
    a = elem.split()[3]
    a2 = a.filter(ImageFilter.MaxFilter(px * 2 + 1)).filter(ImageFilter.GaussianBlur(1))
    pad = px + 2
    out = Image.new('RGBA', (elem.width + 2 * pad, elem.height + 2 * pad), (0, 0, 0, 0))
    bg = Image.new('RGBA', (elem.width, elem.height), color + (255,))
    bgA = Image.new('RGBA', out.size, (0, 0, 0, 0))
    big = Image.new('L', out.size, 0)
    big.paste(a2, (pad, pad))
    fill = Image.new('RGBA', out.size, color + (255,))
    fill.putalpha(big)
    out.alpha_composite(fill)
    out.alpha_composite(elem, (pad, pad))
    return out


# ---------------------------------------------------------------- icons (drawn at 2x then reduced)
def _canvas(s):
    return Image.new('RGBA', (s * 2, s * 2), (0, 0, 0, 0))


def _done(img, s):
    return img.resize((s, s), Image.LANCZOS)


def icon_heart(s=120, fill=(236, 84, 84), ink=INK, lw=6):
    im = _canvas(s); d = ImageDraw.Draw(im)
    pts = []
    for t in np.linspace(0, 2 * math.pi, 120):
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((s + x * s * 0.052, s * 0.92 - y * s * 0.052))
    d.polygon(pts, fill=fill, outline=ink, width=lw * 2)
    return _done(im, s)


def icon_star(s=120, fill=(255, 200, 40), ink=INK, lw=6):
    im = _canvas(s); d = ImageDraw.Draw(im)
    pts = []
    for i in range(10):
        r = s * 0.86 if i % 2 == 0 else s * 0.38
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((s + r * math.cos(a), s * 1.06 + r * math.sin(a)))
    d.polygon(pts, fill=fill, outline=ink, width=lw * 2)
    return _done(im, s)


def icon_bubble(s=120, fill=(120, 190, 255), ink=INK, lw=6):
    im = _canvas(s); d = ImageDraw.Draw(im)
    d.rounded_rectangle((s * 0.2, s * 0.3, s * 1.8, s * 1.45), radius=s * 0.35, fill=fill, outline=ink, width=lw * 2)
    d.polygon([(s * 0.55, s * 1.35), (s * 0.45, s * 1.8), (s * 0.95, s * 1.4)], fill=fill)
    d.line([(s * 0.55, s * 1.43), (s * 0.45, s * 1.8), (s * 0.95, s * 1.45)], fill=ink, width=lw * 2, joint='curve')
    for k in (0.62, 1.0, 1.38):
        d.ellipse((s * k - 12, s * 0.88 - 12, s * k + 12, s * 0.88 + 12), fill=ink)
    return _done(im, s)


def icon_plus(s=120, fill=(255, 214, 10), ink=INK, lw=6):
    im = _canvas(s); d = ImageDraw.Draw(im)
    d.ellipse((s * 0.14, s * 0.14, s * 1.86, s * 1.86), fill=fill, outline=ink, width=lw * 2)
    d.line((s * 0.6, s, s * 1.4, s), fill=ink, width=lw * 3)
    d.line((s, s * 0.6, s, s * 1.4), fill=ink, width=lw * 3)
    return _done(im, s)


def icon_check(s=120, color=GREEN, lw=14):
    im = _canvas(s); d = ImageDraw.Draw(im)
    d.line([(s * 0.35, s * 1.05), (s * 0.8, s * 1.5), (s * 1.7, s * 0.5)], fill=color, width=lw * 2, joint='curve')
    return _done(im, s)


def icon_cross(s=120, color=RED, lw=14):
    im = _canvas(s); d = ImageDraw.Draw(im)
    d.line((s * 0.45, s * 0.45, s * 1.55, s * 1.55), fill=color, width=lw * 2)
    d.line((s * 1.55, s * 0.45, s * 0.45, s * 1.55), fill=color, width=lw * 2)
    return _done(im, s)


def icon_sun(s=90, ink=INK):
    im = _canvas(s); d = ImageDraw.Draw(im)
    d.ellipse((s * 0.6, s * 0.6, s * 1.4, s * 1.4), fill=(255, 190, 40), outline=ink, width=8)
    for i in range(8):
        a = i * math.pi / 4
        d.line((s + math.cos(a) * s * 0.55, s + math.sin(a) * s * 0.55, s + math.cos(a) * s * 0.85, s + math.sin(a) * s * 0.85),
               fill=ink, width=8)
    return _done(im, s)


def icon_clock(s=90, ink=INK):
    im = _canvas(s); d = ImageDraw.Draw(im)
    d.ellipse((s * 0.2, s * 0.2, s * 1.8, s * 1.8), fill=(255, 255, 255), outline=ink, width=8)
    d.line((s, s, s, s * 0.55), fill=ink, width=9)
    d.line((s, s, s * 1.38, s * 1.12), fill=ink, width=9)
    return _done(im, s)


def icon_mood(s=90, ink=INK):
    im = _canvas(s); d = ImageDraw.Draw(im)
    d.ellipse((s * 0.2, s * 0.2, s * 1.8, s * 1.8), fill=(255, 176, 190), outline=ink, width=8)
    d.ellipse((s * 0.68, s * 0.72, s * 0.84, s * 0.92), fill=ink)
    d.ellipse((s * 1.16, s * 0.72, s * 1.32, s * 0.92), fill=ink)
    d.arc((s * 0.6, s * 0.75, s * 1.4, s * 1.45), 20, 160, fill=ink, width=8)
    return _done(im, s)


def icon_wave(s=90, ink=INK):
    """sound wave (speaker + arcs)"""
    im = _canvas(s); d = ImageDraw.Draw(im)
    d.polygon([(s * 0.3, s * 0.8), (s * 0.55, s * 0.8), (s * 0.9, s * 0.5), (s * 0.9, s * 1.5), (s * 0.55, s * 1.2), (s * 0.3, s * 1.2)],
              fill=ink)
    for r in (0.35, 0.6, 0.85):
        d.arc((s - s * r + s * 0.1, s - s * r, s + s * r + s * 0.1, s + s * r), -50, 50, fill=ink, width=9)
    return _done(im, s)


def stamp(text, s=260, color=RED, rot=-12, check=True):
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((8, 8, s - 8, s - 8), outline=color + (235,), width=10)
    d.ellipse((24, 24, s - 24, s - 24), outline=color + (200,), width=4)
    f = font('Heavy', int(s * 0.2))
    d.text((s / 2, s * 0.66), text, font=f, fill=color + (235,), anchor='mm')
    if check:
        c = icon_check(int(s * 0.46), color=color, lw=16)
        im.alpha_composite(c, (int(s * 0.27), int(s * 0.1)))
    # ink texture: knock out random specks
    rng = np.random.default_rng(3)
    a = np.array(im.split()[3]).astype(np.float32)
    a *= (rng.random(a.shape) > 0.08) * 0.25 + 0.75
    im.putalpha(Image.fromarray(a.astype(np.uint8)))
    return rotate(im, rot)


def burst(r_in=40, r_out=80, n=9, lw=7, color=INK, a0=0, a1=360):
    s = int(r_out * 2 + 20)
    im = Image.new('RGBA', (s * 2, s * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i in range(n):
        a = math.radians(a0 + (a1 - a0) * (i + 0.5) / n)
        d.line((s + math.cos(a) * r_in * 2, s + math.sin(a) * r_in * 2, s + math.cos(a) * r_out * 2, s + math.sin(a) * r_out * 2),
               fill=color, width=lw * 2)
    return im.resize((s, s), Image.LANCZOS)


def arrow(p0, p1, bend=0.25, color=INK, lw=6, head=26, dash=None):
    """curved arrow image in canvas coordinates: returns (RGBA layer W x H)"""
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = -(y1 - y0), (x1 - x0)
    cx, cy = mx + nx * bend, my + ny * bend
    pts = [((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1, (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1)
           for t in np.linspace(0, 1, 60)]
    if dash:
        for i in range(0, len(pts) - 1, 2):
            d.line([pts[i], pts[i + 1]], fill=color, width=lw)
    else:
        d.line(pts, fill=color, width=lw, joint='curve')
    ex, ey = pts[-1]
    px, py = pts[-4]
    ang = math.atan2(ey - py, ex - px)
    for s in (-1, 1):
        a = ang + math.pi - s * 0.45
        d.line((ex, ey, ex + math.cos(a) * head, ey + math.sin(a) * head), fill=color, width=lw)
    return layer


# ---------------------------------------------------------------- frame with bookkeeping
class Frame:
    def __init__(self, base, face=None, lips=None, name=''):
        self.img = base.convert('RGBA').copy()
        self.face = face          # (x0,y0,x1,y1) in canvas coords, or None
        self.lips = lips
        self.items = []           # (name, bbox, kind)
        self.name = name

    def add(self, elem, x, y, name, kind='overlay', shadow=True, blur=12, salpha=0.30, anchor='tl'):
        if anchor == 'c':
            x, y = int(x - elem.width / 2), int(y - elem.height / 2)
        x, y = int(x), int(y)
        if shadow:
            sh, pad = shadow_of(elem, blur=blur, alpha=salpha)
            self._safe(sh, x - pad + 3, y - pad + 7)
        self._safe(elem, x, y)
        a = np.array(elem.split()[3])
        ys, xs = np.where(a > 40)
        bb = (x + int(xs.min()), y + int(ys.min()), x + int(xs.max()), y + int(ys.max())) if len(xs) else (x, y, x, y)
        self.items.append((name, bb, kind))
        return bb

    def _safe(self, elem, x, y):
        # alpha_composite with clipping for negative / overflowing offsets
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + elem.width), min(H, y + elem.height)
        if x1 <= x0 or y1 <= y0:
            return
        crop = elem.crop((x0 - x, y0 - y, x1 - x, y1 - y))
        self.img.alpha_composite(crop, (x0, y0))

    def layer(self, lay, name, kind='overlay'):
        self.img.alpha_composite(lay)
        a = np.array(lay.split()[3])
        ys, xs = np.where(a > 40)
        if len(xs):
            self.items.append((name, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())), kind))

    def check(self, allow=()):
        """Return list of problems: text/keyword boxes touching face/lips, overlay-overlay overlaps."""
        probs = []

        def inter(a, b, m=0):
            return not (a[2] + m <= b[0] or b[2] + m <= a[0] or a[3] + m <= b[1] or b[3] + m <= a[1])

        for n, bb, k in self.items:
            if k in ('text', 'overlay', 'pip') and self.face and inter(bb, self.face, 0):
                probs.append(f'{n} touches face box')
            if k in ('text', 'overlay', 'pip') and self.lips and inter(bb, self.lips, 12):
                probs.append(f'{n} near lips')
        its = [it for it in self.items if it[2] in ('text', 'overlay', 'pip')]
        for i in range(len(its)):
            for j in range(i + 1, len(its)):
                a, b = its[i], its[j]
                if (a[0], b[0]) in allow or (b[0], a[0]) in allow:
                    continue
                if inter(a[1], b[1]):
                    probs.append(f'{a[0]} x {b[0]} overlap')
        return probs


# ---------------------------------------------------------------- recurring components
def subtitle_c(fr, runs, cy=SUB_CY, size=66, cx=W / 2):
    """C paper-strip subtitle (Medium 66 black on white strip; keyword Heavy on yellow marker)."""
    fN, fK = font('Medium', size), font('Heavy', size)
    chars = [(ch, k) for t, k in runs for ch in t]
    xs, x = [], 0.0
    for i, (ch, k) in enumerate(chars):
        xs.append(x)
        x += (fK if k else fN).getlength(ch) + (2 if i < len(chars) - 1 else 0)
    tw = x
    padx, pady = 30, 20
    x0 = cx - tw / 2
    baseline = cy + 24
    top, bottom = baseline - 60 - pady, baseline + 12 + pady
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.rounded_rectangle((x0 - padx, top, x0 + tw + padx, bottom), radius=16, fill=(255, 255, 255, 245))
    soft = lay.split()[3].filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.35))
    sh = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sh.putalpha(soft)
    fr.img.alpha_composite(sh, (0, 6))
    fr.img.alpha_composite(lay)
    d = ImageDraw.Draw(fr.img)
    i = 0
    while i < len(chars):
        if chars[i][1]:
            j = i
            while j + 1 < len(chars) and chars[j + 1][1]:
                j += 1
            kx0 = x0 + xs[i] - 6
            kx1 = x0 + xs[j] + fK.getlength(chars[j][0]) + 6
            d.rectangle((kx0, baseline - 30, kx1, baseline + 8), fill=YELLOW)
            i = j + 1
        else:
            i += 1
    for (ch, k), cx_ in zip(chars, xs):
        d.text((x0 + cx_, baseline), ch, font=fK if k else fN, fill=(20, 20, 20), anchor='ls')
    bb = (int(x0 - padx), int(top), int(x0 + tw + padx), int(bottom))
    fr.items.append(('subtitle', bb, 'text'))
    return bb


def pip_crop(src, face, head_top, out_wh=(300, 420)):
    """Crop head + upper body from a 1080x1920 source frame at the PiP aspect."""
    ow, oh = out_wh
    ch = 1260
    cw = int(round(ch * ow / oh))
    cx = (face[0] + face[2]) / 2
    x0 = int(min(max(0, cx - cw / 2), W - cw))
    y0 = int(max(0, head_top - 70))
    y0 = min(y0, H - ch)
    return src.crop((x0, y0, x0 + cw, y0 + ch)).resize(out_wh, Image.LANCZOS)


def pip_card(content, border=12, r_out=30, tape_seed=5, tape_color=(250, 222, 120)):
    iw, ih = content.size
    ow, oh = iw + 2 * border, ih + 2 * border
    card = Image.new('RGBA', (ow, oh), (0, 0, 0, 0))
    card.paste(Image.new('RGBA', (ow, oh), CARD + (255,)), (0, 0), rrect_mask(ow, oh, r_out))
    card.paste(content.convert('RGBA'), (border, border), rrect_mask(iw, ih, r_out - border + 4))
    # washi tape over the top edge
    t = rotate(tape(118, 36, color=tape_color, seed=tape_seed), -7)
    out = Image.new('RGBA', (ow, oh + 22), (0, 0, 0, 0))
    out.alpha_composite(card, (0, 22))
    out.alpha_composite(t, (int(ow / 2 - t.width / 2), 0))
    return out


def add_pip(fr, src, face, head_top, name='pip'):
    content = pip_crop(src, face, head_top)
    card = pip_card(content)
    x0, y0 = PIP_BOX[0], PIP_BOX[1] - 22
    return fr.add(card, x0, y0, name, kind='pip', blur=14, salpha=0.35)


STEPS = ['选题', '风格', '分镜', '成片']


def step_bar(fr, active, done=(), appear=False):
    """Minimal 4-step bar at the top (only during the four-step section)."""
    w, h = 900, 64
    bar = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(bar)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=20, fill=CARD + (250,))
    seg = w / 4
    fB, fH = font('Bold', 30), font('Heavy', 30)
    for i, name in enumerate(STEPS):
        n = i + 1
        x0 = i * seg
        if n == active:
            d.rounded_rectangle((x0 + 8, 8, x0 + seg - 8, h - 9), radius=14, fill=YELLOW)
        col = INK if (n == active or n in done) else (170, 164, 154)
        f = fH if n == active else fB
        txt = f'{n} {name}'
        d.text((x0 + seg / 2 + (10 if n in done else 0), h / 2), txt, font=f, fill=col, anchor='mm')
        if n in done:
            c = icon_check(34, color=GREEN, lw=9)
            bar.alpha_composite(c, (int(x0 + seg / 2 - f.getlength(txt) / 2 - 36), 15))
        if i:
            d.line((x0, 16, x0, h - 16), fill=(210, 203, 190), width=2)
    return fr.add(bar, (W - w) / 2, 196, 'step_bar', kind='overlay', blur=8, salpha=0.22)


def chapter_tab(step, title, size=64):
    f1, f2 = font('Heavy', 30), font('Heavy', size)
    pill = f'STEP {step}'
    pw = f1.getlength(pill) + 36
    tw = f2.getlength(title)
    w, h = int(pw + tw + 70), int(size + 56)
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=16, fill=CARD + (255,))
    d.rounded_rectangle((20, h / 2 - 26, 20 + pw, h / 2 + 26), radius=26, fill=INK)
    d.text((20 + pw / 2, h / 2), pill, font=f1, fill=(255, 255, 255), anchor='mm')
    d.rectangle((pw + 40, h / 2 + 2, pw + 46 + tw, h / 2 + size * 0.42), fill=YELLOW)
    d.text((pw + 44, h / 2 + 2), title, font=f2, fill=INK, anchor='lm')
    t = rotate(tape(100, 34, color=(170, 205, 245), seed=11), 8)
    out = Image.new('RGBA', (w + 30, h + 18), (0, 0, 0, 0))
    out.alpha_composite(im, (0, 18))
    out.alpha_composite(t, (w - 110, 0))
    return out


def placeholder_tag(text='演示占位'):
    f = font('Bold', 26)
    w = int(f.getlength(text) + 36)
    im = Image.new('RGBA', (w, 46), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, 45), radius=10, fill=(255, 255, 255, 235), outline=RED + (255,), width=3)
    d.text((w / 2, 23), text, font=f, fill=RED, anchor='mm')
    return im


def photo(img, border=14, radius=10, bg=CARD):
    iw, ih = img.size
    ow, oh = iw + 2 * border, ih + 2 * border
    out = Image.new('RGBA', (ow, oh), (0, 0, 0, 0))
    out.paste(Image.new('RGBA', (ow, oh), bg + (255,)), (0, 0), rrect_mask(ow, oh, radius + 4))
    out.paste(img.convert('RGBA'), (border, border), rrect_mask(iw, ih, radius))
    return out


def demo_page(demo_img, y=300, tone=None, seed=2):
    """3:4 demo (1080x1440) recomposed into 9:16: demo full-width at y, paper page above and below."""
    if tone is None:
        top = np.array(demo_img.convert('RGB').crop((0, 0, W, 12))).reshape(-1, 3).mean(0)
        tone = tuple(int(v) for v in top)
    bg = paper(tone=tone, seed=seed, grain=3.5, blotch=4)
    d = demo_img.convert('RGBA')
    # feather top / bottom 24px of the demo into the paper so the seam never shows as a hard line
    a = Image.new('L', d.size, 255)
    ad = ImageDraw.Draw(a)
    for i in range(24):
        v = int(255 * (i + 1) / 24)
        ad.line((0, i, W, i), fill=v)
        ad.line((0, d.height - 1 - i, W, d.height - 1 - i), fill=v)
    d.putalpha(a)
    bg.alpha_composite(d, (0, y))
    return bg
