# -*- coding: utf-8 -*-
"""Helpers dựng cảnh cho video 26.08.09 - 4 thuật ngữ ROAS/ACOS/CPA/ROI.

Gộp từ pipeline đã duyệt (10_scene_helpers + 11_scenes_images + 12_layout_archetypes),
thêm banknote() vẽ tờ tiền cách điệu — không dùng ảnh chụp tiền thật (Nghị định 87/2023).
"""
import math
import os
import subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "clips")
os.makedirs(OUT, exist_ok=True)
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import tabcom_paths as P
FIX = P.FIX
AST = P.assets()
SHOTS = P.extra("screenshots")
LOGO = P.LOGO
FONTS = P.FONTS
F_BLACK = os.path.join(FONTS, "PS Anton - Regular V1.0.otf")
F_XBOLD = os.path.join(FONTS, "Big Shoulders ExtraBold Viet Hoa.otf")
F_BOLD = os.path.join(FONTS, "PS Big Shoulders Bold Viet Hoa.otf")

TEAL = (23, 217, 179, 255)
NAVY = (27, 37, 134, 255)
RED = (198, 0, 1, 255)
AMBER = (232, 145, 12, 255)
INK = (23, 23, 23, 255)
WHITE = (255, 255, 255, 255)
GRAY = (85, 89, 107, 255)
MINT = (232, 250, 245, 255)
W, H, FPS = 1080, 1920, 25
NEN = Image.open(os.path.join(FIX, "Nền.png")).convert("RGBA").resize((W, H))
CARD_SRC = Image.open(os.path.join(FIX, "Nền nhỏ đặt sau người khi đã remove bg.png")).convert("RGBA")


def text_w(f, s):
    b = f.getbbox(s)
    return b[2] - b[0]


def fit_font(path, size, s, maxw):
    f = ImageFont.truetype(path, size)
    while text_w(f, s) > maxw and size > 18:
        size -= 2
        f = ImageFont.truetype(path, size)
    return f


def shadowed(img, blur=8, alpha=60, off=(0, 6)):
    sh = Image.new("RGBA", (img.width + 60, img.height + 60), (0, 0, 0, 0))
    m = img.split()[3].point(lambda a: min(a, alpha))
    sh.paste(Image.new("RGBA", img.size, (0, 0, 0, 255)), (30 + off[0], 30 + off[1]), m)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    sh.paste(img, (30, 30), img)
    return sh


def capsule(s, size, fg, bg, icon=None, padx=38, pady=20, radius=28, maxw=940, gap=18, font=F_XBOLD):
    size = int(size * 1.22)
    f = fit_font(font, size, s, maxw - 2 * padx - (icon.width + gap if icon else 0))
    tw = text_w(f, s)
    asc, desc = f.getmetrics()
    th = asc + desc
    iw = (icon.width + gap) if icon else 0
    ih = max(th, icon.height if icon else 0)
    img = Image.new("RGBA", (tw + iw + 2 * padx, ih + 2 * pady), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius, fill=bg)
    x = padx
    if icon:
        img.alpha_composite(icon, (x, (img.height - icon.height) // 2))
        x += icon.width + gap
    d.text((x, (img.height - th) // 2), s, font=f, fill=fg)
    return shadowed(img)


def textimg(s, size, color, font=F_XBOLD, maxw=980):
    size = int(size * 1.22)
    f = fit_font(font, size, s, maxw)
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (text_w(f, s) + 8, asc + desc + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((4, 4), s, font=f, fill=color)
    return img


def checkbox(size=46):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 52
    d.rounded_rectangle((2 * s, 2 * s, 50 * s, 50 * s), 12 * s, fill=WHITE, outline=NAVY, width=int(3 * s))
    d.line((12 * s, 27 * s, 22 * s, 38 * s), fill=TEAL, width=int(6 * s))
    d.line((22 * s, 38 * s, 40 * s, 15 * s), fill=TEAL, width=int(6 * s))
    return img


def warn_tri(size=46):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 52
    d.polygon([(26 * s, 4 * s), (50 * s, 46 * s), (2 * s, 46 * s)], fill=WHITE)
    d.line((26 * s, 18 * s, 26 * s, 33 * s), fill=RED, width=int(4 * s))
    d.ellipse((23 * s, 37 * s, 29 * s, 43 * s), fill=RED)
    return img


def icon_bookmark(size=130, color=NAVY):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.polygon([(16 * s, 6 * s), (48 * s, 6 * s), (48 * s, 58 * s), (32 * s, 44 * s), (16 * s, 58 * s)],
              outline=color, fill=None, width=int(4 * s))
    d.line((24 * s, 24 * s, 40 * s, 24 * s), fill=color, width=int(4 * s))
    return shadowed(img, blur=8, alpha=55)


def icon_qmark(size=140, color=RED):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(F_BLACK, int(size * 1.15))
    b = f.getbbox("?")
    d.text(((size - (b[2] - b[0])) // 2 - b[0], (size - (b[3] - b[1])) // 2 - b[1]), "?", font=f, fill=color)
    return shadowed(img, blur=8, alpha=55)


# ---------------- tờ tiền cách điệu ----------------
def banknote(value="10.000", w=300, col=TEAL, label=None, dim=False):
    """Tờ tiền VẼ CÁCH ĐIỆU. Không dùng ảnh chụp tiền Việt Nam thật —
    Nghị định 87/2023/NĐ-CP giới hạn việc sao chụp tiền."""
    h = int(w * 0.47)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    body = MINT if not dim else (238, 238, 242, 255)
    edge = col if not dim else (176, 180, 196, 255)
    d.rounded_rectangle((0, 0, w - 1, h - 1), int(h * 0.14), fill=body, outline=edge, width=max(3, w // 75))
    inset = int(w * 0.035)
    d.rounded_rectangle((inset, inset, w - 1 - inset, h - 1 - inset), int(h * 0.10),
                        outline=edge, width=max(1, w // 220))
    # con dấu tròn bên trái
    cr = int(h * 0.30)
    ccx, ccy = int(w * 0.17), h // 2
    d.ellipse((ccx - cr, ccy - cr, ccx + cr, ccy + cr), outline=edge, width=max(2, w // 130))
    fd = ImageFont.truetype(F_BLACK, int(cr * 1.5))
    bb = fd.getbbox("đ")
    d.text((ccx - (bb[2] - bb[0]) / 2 - bb[0], ccy - (bb[3] - bb[1]) / 2 - bb[1]), "đ", font=fd, fill=edge)
    # mệnh giá
    fv = fit_font(F_BLACK, int(h * 0.46), value, int(w * 0.56))
    vb = fv.getbbox(value)
    vx = int(w * 0.32)
    d.text((vx, h * 0.30 - vb[1]), value, font=fv, fill=NAVY if not dim else GRAY)
    fs = ImageFont.truetype(F_BOLD, int(h * 0.20))
    d.text((vx + 2, h * 0.62), "ĐỒNG", font=fs, fill=edge)
    out = shadowed(img, blur=10, alpha=68, off=(0, 7))
    if label:
        cap = capsule(label, 26, WHITE, col if not dim else GRAY, padx=18, pady=10, radius=16, maxw=w)
        merged = Image.new("RGBA", (max(out.width, cap.width), out.height + cap.height - 14), (0, 0, 0, 0))
        merged.alpha_composite(out, ((merged.width - out.width) // 2, 0))
        merged.alpha_composite(cap, ((merged.width - cap.width) // 2, out.height - 14))
        return merged
    return out


def money_box(title, notes, col=TEAL, w=470, h=330, note_w=180):
    """Ô chứa mấy tờ tiền, có tiêu đề."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 30, fill=WHITE, outline=col, width=4)
    ft = fit_font(F_XBOLD, int(34 * 1.22), title, w - 40)
    d.text(((w - text_w(ft, title)) // 2, 18), title, font=ft, fill=col)
    top = 18 + sum(ft.getmetrics()) + 10
    bn = banknote("10.000", note_w, col)
    cols = 2 if notes > 1 else 1
    rows = math.ceil(notes / cols)
    gx = (w - cols * bn.width + (cols - 1) * 40) // 2
    for i in range(notes):
        r, c = divmod(i, cols)
        img.alpha_composite(bn, (gx + c * (bn.width - 40), top + r * (bn.height - 30)))
    return shadowed(img, blur=12, alpha=62, off=(0, 8))


def badge(icon_path, size=140, ratio=0.68, crop_box=None):
    im = Image.open(icon_path).convert("RGBA")
    if crop_box:
        im = im.crop(crop_box)
        im = im.crop(im.getbbox())
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, size - 1, size - 1), 30, fill=WHITE,
                                           outline=(224, 227, 238, 255), width=2)
    m = size * ratio
    r = min(m / im.width, m / im.height)
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
    card.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    return shadowed(card, blur=10, alpha=70, off=(0, 8))


def rounded_card(w, h, radius=46):
    card = CARD_SRC.resize((w, h))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    return out


def arrow_down(w=26, h=90, color=NAVY):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line((w // 2, 0, w // 2, h - 22), fill=color, width=6)
    d.polygon([(0, h - 26), (w, h - 26), (w // 2, h)], fill=color)
    return img


def arrow_right(w=120, h=40, color=NAVY, flip=False):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line((6, h // 2, w - 28, h // 2), fill=color, width=8)
    d.polygon([(w - 32, 4), (w - 32, h - 4), (w - 2, h // 2)], fill=color)
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img


# ---------------- ảnh ----------------
def _load(name, folder=None):
    base = folder or (SHOTS if name.startswith("shopee-ads-canh-bao") else AST)
    return Image.open(os.path.join(base, name))


def photo(name, w, h, radius=28, border=6, folder=None, focus=0.38):
    im = _load(name, folder).convert("RGB")
    r = max(w / im.width, h / im.height)
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
    x0 = (im.width - w) // 2
    y0 = int((im.height - h) * focus)
    im = im.crop((x0, y0, x0 + w, y0 + h)).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    card = Image.new("RGBA", (w + 2 * border, h + 2 * border), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, card.width - 1, card.height - 1), radius + border, fill=WHITE)
    card.paste(im, (border, border), mask)
    return shadowed(card, blur=14, alpha=70, off=(0, 10))


def flat_photo(name, w, h, radius=18, folder=None, focus=0.38):
    im = _load(name, folder).convert("RGB")
    r = max(w / im.width, h / im.height)
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
    x0 = (im.width - w) // 2
    y0 = int((im.height - h) * focus)
    im = im.crop((x0, y0, x0 + w, y0 + h)).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def shot(name, target_h=None, target_w=None, radius=22, folder=None):
    im = _load(name, folder).convert("RGBA")
    if im.mode == "RGBA":
        bgw = Image.new("RGBA", im.size, WHITE)
        bgw.alpha_composite(im)
        im = bgw
    r = (target_h / im.height) if target_h else (target_w / im.width)
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius, fill=255)
    card = Image.new("RGBA", (im.width + 12, im.height + 12), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, card.width - 1, card.height - 1), radius + 6, fill=WHITE)
    card.paste(im, (6, 6), mask)
    return shadowed(card, blur=14, alpha=70, off=(0, 10))


def circle_photo(name, d_px=460, ring=10, ring_col=TEAL, folder=None, focus=0.35):
    im = _load(name, folder).convert("RGB")
    r = max(d_px / im.width, d_px / im.height)
    im = im.resize((int(im.width * r), int(im.height * r)))
    x0 = (im.width - d_px) // 2
    y0 = int((im.height - d_px) * focus)
    im = im.crop((x0, y0, x0 + d_px, y0 + d_px)).convert("RGBA")
    mask = Image.new("L", (d_px, d_px), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d_px - 1, d_px - 1), fill=255)
    out = Image.new("RGBA", (d_px + 2 * ring, d_px + 2 * ring), (0, 0, 0, 0))
    ImageDraw.Draw(out).ellipse((0, 0, out.width - 1, out.height - 1), fill=ring_col)
    out.paste(im, (ring, ring), mask)
    return shadowed(out, blur=14, alpha=70, off=(0, 10))


def strip3(names, w=310, h=230, folder=None):
    out = Image.new("RGBA", (w * len(names) + 20 * (len(names) - 1), h), (0, 0, 0, 0))
    for i, n in enumerate(names):
        out.alpha_composite(flat_photo(n, w, h, radius=20, folder=folder), (i * (w + 20), 0))
    return shadowed(out, blur=12, alpha=60, off=(0, 8))


def tile(name, label, w=470, h=330, col=NAVY, folder=None, focus=0.3):
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 26, fill=WHITE, outline=(226, 229, 240, 255), width=2)
    ph = flat_photo(name, w - 24, h - 96, radius=18, folder=folder, focus=focus)
    card.alpha_composite(ph, (12, 12))
    f = fit_font(F_XBOLD, int(38 * 1.22), label, w - 40)
    d.text(((w - text_w(f, label)) // 2, h - 74), label, font=f, fill=col)
    return shadowed(card, blur=12, alpha=62, off=(0, 8))


def bg_photo(name, top=210, bot=1790, scrim_top=0.82, scrim_bot=0.0, folder=None, focus=0.4):
    canvas = NEN.copy()
    h = bot - top
    im = _load(name, folder).convert("RGB")
    r = max(W / im.width, h / im.height)
    im = im.resize((int(im.width * r), int(im.height * r)))
    x0 = (im.width - W) // 2
    y0 = int((im.height - h) * focus)
    im = im.crop((x0, y0, x0 + W, y0 + h)).convert("RGBA")
    g = Image.new("L", (1, h))
    for y in range(h):
        f = y / max(1, h - 1)
        v = int(255 * (scrim_top * (1 - f) ** 1.4 + scrim_bot * f ** 1.4))
        g.putpixel((0, y), v)
    scrim = Image.new("RGBA", (W, h), (250, 250, 248, 255))
    scrim.putalpha(g.resize((W, h)))
    im.alpha_composite(scrim)
    canvas.paste(im, (0, top))
    return canvas


def block(title, sub, col, w=440, h=210):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 32, fill=col)
    ft = fit_font(F_BLACK, int(62 * 1.22), title, w - 50)
    ta = sum(ft.getmetrics())
    d.text(((w - text_w(ft, title)) // 2, 22), title, font=ft, fill=WHITE)
    fs = fit_font(F_BOLD, int(28 * 1.22), sub, w - 50)
    d.text(((w - text_w(fs, sub)) // 2, 22 + ta + 2), sub, font=fs, fill=(232, 238, 255, 255))
    return shadowed(img, blur=12, alpha=65, off=(0, 8))


def row_item(icon_img, head, body, col, w=940, h=180):
    """Một dòng của bảng nhớ: ảnh tròn + tên chỉ số + câu hỏi."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 30, fill=(255, 255, 255, 246), outline=col, width=3)
    ic = icon_img.resize((h - 44, h - 44))
    img.alpha_composite(ic, (18, 22))
    x = 18 + ic.width + 22
    fh = fit_font(F_BLACK, int(46 * 1.22), head, w - x - 40)
    d.text((x, 26), head, font=fh, fill=col)
    fb = fit_font(F_BOLD, int(31 * 1.22), body, w - x - 40)
    d.text((x, 26 + sum(fh.getmetrics()) - 4), body, font=fb, fill=INK)
    return shadowed(img, blur=12, alpha=58, off=(0, 7))


# ---------------- animation ----------------
def eob(p):
    c1, c3 = 1.70158, 2.70158
    p -= 1
    return 1 + c3 * p ** 3 + c1 * p ** 2


def eoc(p):
    return 1 - (1 - p) ** 3


# Làm dịu hiệu ứng: kéo dài thời gian vào và giảm biên độ nảy/giật.
ANIM_SLOW = 1.18


class Layer:
    def __init__(self, img, cx, cy, t0, anim="pop", dur=0.34, dy=70, shake=0.0):
        self.img, self.cx, self.cy, self.t0 = img, cx, cy, t0
        self.anim, self.dy, self.shake = anim, dy, shake
        self.dur = dur * ANIM_SLOW if dur > 0.05 else dur

    def draw(self, canvas, t):
        if t < self.t0:
            return
        p = min(1.0, (t - self.t0) / max(1e-6, self.dur))
        img, cx, cy, alpha = self.img, self.cx, self.cy, 1.0
        if self.anim == "pop":
            sc = 0.74 + 0.26 * eob(p)
            if p < 1.0:
                img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))))
            alpha = min(1.0, p * 3)
        elif self.anim == "slide":
            cy = cy + self.dy * (1 - eoc(p))
            alpha = min(1.0, p * 2.5)
        elif self.anim == "wipe":
            ww = max(1, int(img.width * eoc(p)))
            img = img.crop((0, 0, ww, img.height))
            cx = self.cx - (self.img.width - ww) // 2
        if self.shake and p >= 1.0 and (t - self.t0) < self.dur + 1.1:
            img = img.rotate(self.shake * math.sin(2 * math.pi * 7 * (t - self.t0)),
                             resample=Image.BICUBIC, expand=False)
        if alpha < 1.0:
            img = img.copy()
            img.putalpha(img.split()[3].point(lambda v: int(v * alpha)))
        canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


class L2(Layer):
    """slideL, slideR, blurin, flip, shakein, fly, none (hiện sẵn), float (lơ lửng rung nhẹ).

    t1: mốc biến mất (fade out 0.35s trước t1)."""

    def __init__(self, img, cx, cy, t0, anim="pop", dur=0.34, dy=70, shake=0.0, src=None, t1=None):
        Layer.__init__(self, img, cx, cy, t0, anim, dur, dy, shake)
        self.src = src
        self.t1 = t1

    def _fade_out(self, t):
        if self.t1 is None:
            return 1.0
        if t >= self.t1:
            return 0.0
        if t > self.t1 - 0.35:
            return max(0.0, (self.t1 - t) / 0.35)
        return 1.0

    def draw(self, canvas, t):
        if t < self.t0:
            return
        fo = self._fade_out(t)
        if fo <= 0.0:
            return
        p = min(1.0, (t - self.t0) / max(1e-6, self.dur))
        img, cx, cy, alpha = self.img, self.cx, self.cy, 1.0
        a = self.anim
        if a == "none":
            alpha = min(1.0, (t - self.t0) / max(0.001, self.dur) * 4) if self.dur > 0.05 else 1.0
        elif a == "float":
            e = eoc(p)
            alpha = min(1.0, p * 2.2)
            cy = cy + 26 * (1 - e)
            k = t - self.t0
            cy += 7.0 * math.sin(2 * math.pi * 0.55 * k)
            cx += 4.0 * math.sin(2 * math.pi * 0.37 * k + 1.1)
            ang = 1.1 * math.sin(2 * math.pi * 0.42 * k)
            img = img.rotate(ang, resample=Image.BICUBIC, expand=False)
        elif a in ("slideL", "slideR"):
            off = (self.dy or 160) * (1 - eoc(p))
            cx = cx + (-off if a == "slideL" else off)
            alpha = min(1.0, p * 2.5)
        elif a == "blurin":
            if p < 1.0:
                img = img.filter(ImageFilter.GaussianBlur(14 * (1 - p)))
            alpha = min(1.0, p * 2.2)
        elif a == "flip":
            w = max(2, int(img.width * (0.48 + 0.52 * eob(p)))) if p < 1 else img.width
            img = img.resize((w, img.height))
            alpha = min(1.0, p * 2.4)
        elif a == "shakein":
            sc = 0.84 + 0.16 * eob(p)
            if p < 1.0:
                img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))))
            alpha = min(1.0, p * 2.6)
            if p >= 1.0 and (t - self.t0) < self.dur + 0.45:
                cx += 4 * math.sin(2 * math.pi * 7 * (t - self.t0))
        elif a == "fly":
            sx, sy = self.src
            e = eoc(p)
            cx = sx + (self.cx - sx) * e
            cy = sy + (self.cy - sy) * e - 90 * math.sin(math.pi * p)
            sc = 0.72 + 0.28 * e
            if p < 1.0:
                img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))))
            alpha = min(1.0, p * 4)
        else:
            if fo >= 1.0:
                return Layer.draw(self, canvas, t)
            alpha = 1.0  # lúc fade out thì animation vào đã xong, chỉ cần giảm alpha
        alpha *= fo
        if alpha < 1.0:
            img = img.copy()
            img.putalpha(img.split()[3].point(lambda v: int(v * alpha)))
        canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


class TypeLayer:
    def __init__(self, text, size, color, cx, cy, t0, cps=22, font=None, maxw=980):
        self.text, self.cx, self.cy, self.t0, self.cps = text, cx, cy, t0, cps
        self.font_path = font or F_XBOLD
        self.f = fit_font(self.font_path, int(size * 1.22), text, maxw)
        self.color = color
        asc, desc = self.f.getmetrics()
        self.h = asc + desc
        self.full_w = text_w(self.f, text)

    def draw(self, canvas, t):
        if t < self.t0:
            return
        n = min(len(self.text), int((t - self.t0) * self.cps) + 1)
        s = self.text[:n]
        img = Image.new("RGBA", (self.full_w + 30, self.h + 10), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((0, 0), s, font=self.f, fill=self.color)
        if n < len(self.text) and int((t - self.t0) * 6) % 2 == 0:
            cw = text_w(self.f, s)
            d.rectangle((cw + 6, 8, cw + 16, self.h - 6), fill=self.color)
        canvas.alpha_composite(img, (int(self.cx - self.full_w / 2), int(self.cy - self.h / 2)))


class CountLayer:
    def __init__(self, target, size, color, cx, cy, t0, dur=1.0, suffix="%", font=None):
        self.target, self.t0, self.dur, self.suffix = target, t0, dur, suffix
        self.f = ImageFont.truetype(font or F_BLACK, int(size * 1.22))
        self.color = color
        self.cx, self.cy = cx, cy

    def draw(self, canvas, t):
        if t < self.t0:
            return
        p = min(1.0, (t - self.t0) / self.dur)
        s = f"{int(round(self.target * eoc(p)))}{self.suffix}"
        tw = text_w(self.f, s)
        asc, desc = self.f.getmetrics()
        img = Image.new("RGBA", (tw + 24, asc + desc + 10), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((12, 0), s, font=self.f, fill=self.color)
        if p >= 1.0 and t - self.t0 < self.dur + 0.3:
            sc = 1.0 + 0.12 * (1 - eoc(min(1, (t - self.t0 - self.dur) / 0.3)))
            img = img.resize((int(img.width * sc), int(img.height * sc)))
        canvas.alpha_composite(img, (int(self.cx - img.width / 2), int(self.cy - img.height / 2)))


class MarkerLayer:
    def __init__(self, text, size, color, bar, cx, cy, t0, dur=0.5, font=None, maxw=980):
        self.f = fit_font(font or F_XBOLD, int(size * 1.22), text, maxw)
        self.text, self.color, self.bar = text, color, bar
        self.cx, self.cy, self.t0, self.dur = cx, cy, t0, dur
        asc, desc = self.f.getmetrics()
        self.w, self.h = text_w(self.f, text), asc + desc

    def draw(self, canvas, t):
        if t < self.t0:
            return
        p = min(1.0, (t - self.t0) / self.dur)
        img = Image.new("RGBA", (self.w + 40, self.h + 26), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        bw = int((self.w + 36) * eoc(p))
        if bw > 2:
            d.rounded_rectangle((2, self.h * 0.42, 2 + bw, self.h + 18), 12, fill=self.bar)
        d.text((20, 4), self.text, font=self.f, fill=self.color)
        canvas.alpha_composite(img, (int(self.cx - img.width / 2), int(self.cy - img.height / 2)))


class DivideLayer:
    """Vẽ phép tính dạng A ÷ B = C, từng phần hiện dần."""

    def __init__(self, parts, size, cx, cy, t0, gap=0.45, colors=None, font=None):
        self.parts, self.t0, self.gap = parts, t0, gap
        self.f = ImageFont.truetype(font or F_BLACK, int(size * 1.22))
        self.colors = colors or [NAVY] * len(parts)
        self.cx, self.cy = cx, cy
        self.ws = [text_w(self.f, s) for s in parts]
        self.sp = int(size * 0.35)
        self.total = sum(self.ws) + self.sp * (len(parts) - 1)
        asc, desc = self.f.getmetrics()
        self.h = asc + desc

    def draw(self, canvas, t):
        if t < self.t0:
            return
        img = Image.new("RGBA", (self.total + 20, self.h + 12), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = 10
        for i, s in enumerate(self.parts):
            tt = self.t0 + i * self.gap
            if t >= tt:
                p = min(1.0, (t - tt) / 0.22)
                col = self.colors[i][:3] + (int(255 * min(1.0, p * 2)),)
                d.text((x, 4), s, font=self.f, fill=col)
            x += self.ws[i] + self.sp
        canvas.alpha_composite(img, (int(self.cx - img.width / 2), int(self.cy - img.height / 2)))


def render_seq(name, dur, layers, force=False):
    """Render lớp phủ RGBA (PNG sequence) để đè lên video người nói."""
    d = os.path.join(ROOT, f"seq_{name}")
    n = int(round(dur * FPS))
    if os.path.isdir(d) and len(os.listdir(d)) >= n and not force:
        print("skip seq", name, flush=True)
        return
    if os.path.isdir(d):
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
    os.makedirs(d, exist_ok=True)
    for i in range(n):
        t = i / FPS
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for L in layers:
            L.draw(c, t)
        c.save(os.path.join(d, f"{i + 1:04d}.png"))
    print("seq", name, f"{dur:.2f}s", n, "frame", flush=True)


def render(name, dur, layers, bg=None, force=False):
    outp = os.path.join(OUT, f"{name}.mp4")
    if os.path.exists(outp) and os.path.getsize(outp) > 20000:
        if not force:
            print("skip", name, flush=True)
            return
        os.remove(outp)
    n = int(round(dur * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "fast",
           "-crf", "18", "-pix_fmt", "yuv420p", outp]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    base = bg or NEN
    for i in range(n):
        t = i / FPS
        c = base.copy()
        for L in layers:
            L.draw(c, t)
        p.stdin.write(c.convert("RGB").tobytes())
    p.stdin.close()
    p.wait()
    print("clip", name, f"{dur:.2f}s", flush=True)
