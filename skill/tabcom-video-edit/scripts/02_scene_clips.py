# -*- coding: utf-8 -*-
"""Render animated scene clips for v3 (staggered pops, slides, Ken Burns)."""
import math
import os
import subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import tabcom_paths as P
ROOT = P.work()
OUT = os.path.join(ROOT, "build5")
os.makedirs(OUT, exist_ok=True)

FIX = P.FIX
LEGAL = P.assets()
LOGO = P.LOGO
CAR = P.extra("carousel-hook-video-ban-hang")
GEN = P.extra("generated-carousel")
FONTS = P.FONTS
F_BLACK = os.path.join(FONTS, "PS Anton - Regular V1.0.otf")
F_XBOLD = os.path.join(FONTS, "Big Shoulders ExtraBold Viet Hoa.otf")
F_BOLD = os.path.join(FONTS, "PS Big Shoulders Bold Viet Hoa.otf")

TEAL = (23, 217, 179, 255)
NAVY = (27, 37, 134, 255)
RED = (198, 0, 1, 255)
INK = (23, 23, 23, 255)
WHITE = (255, 255, 255, 255)
SHOPEE = (238, 77, 45, 255)
TIKTOK = (0, 0, 0, 255)
GRAY = (85, 89, 107, 255)

W, H, FPS = 1080, 1920, 25
NEN = Image.open(os.path.join(FIX, "Nền.png")).convert("RGBA").resize((W, H))
CARD_SRC = Image.open(os.path.join(FIX, "Nền nhỏ đặt sau người khi đã remove bg.png")).convert("RGBA")


def rounded_card(w, h, radius=46):
    card = CARD_SRC.resize((w, h))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    return out


def text_w(f, s):
    b = f.getbbox(s)
    return b[2] - b[0]


def fit_font(path, size, s, maxw):
    f = ImageFont.truetype(path, size)
    while text_w(f, s) > maxw and size > 20:
        size -= 2
        f = ImageFont.truetype(path, size)
    return f


def shadowed(img, blur=8, alpha=60, off=(0, 6)):
    sh = Image.new("RGBA", (img.width + 60, img.height + 60), (0, 0, 0, 0))
    mask = img.split()[3].point(lambda a: min(a, alpha))
    black = Image.new("RGBA", img.size, (0, 0, 0, 255))
    sh.paste(black, (30 + off[0], 30 + off[1]), mask)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    sh.paste(img, (30, 30), img)
    return sh


def capsule(s, size, fg, bg, icon=None, padx=36, pady=20, radius=26, maxw=940, icon_gap=20, font=F_XBOLD):
    size = int(size * 1.22)
    f = fit_font(font, size, s, maxw - 2 * padx - (icon.width + icon_gap if icon else 0))
    tw = text_w(f, s)
    asc, desc = f.getmetrics()
    th = asc + desc
    iw = (icon.width + icon_gap) if icon else 0
    ih = max(th, icon.height if icon else 0)
    img = Image.new("RGBA", (tw + iw + 2 * padx, ih + 2 * pady), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius, fill=bg)
    x = padx
    if icon:
        img.alpha_composite(icon, (x, (img.height - icon.height) // 2))
        x += icon.width + icon_gap
    d.text((x, (img.height - th) // 2), s, font=f, fill=fg)
    return shadowed(img)


def textimg(s, size, color, font=F_XBOLD, maxw=960):
    size = int(size * 1.22)
    f = fit_font(font, size, s, maxw)
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (text_w(f, s) + 8, asc + desc + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((4, 4), s, font=f, fill=color)
    return img


def checkbox(size=48):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 52
    d.rounded_rectangle((2 * s, 2 * s, 50 * s, 50 * s), 12 * s, fill=WHITE, outline=NAVY, width=int(3 * s))
    d.line((12 * s, 27 * s, 22 * s, 38 * s), fill=TEAL, width=int(6 * s))
    d.line((22 * s, 38 * s, 40 * s, 15 * s), fill=TEAL, width=int(6 * s))
    return img


def icon_store(size=58):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dd = ImageDraw.Draw(im)
    sc = size / 64
    for i in range(4):
        x0 = (6 + i * 13) * sc
        dd.rectangle((x0, 12 * sc, x0 + 13 * sc, 24 * sc), outline=WHITE, width=int(3 * sc))
        dd.pieslice((x0, 18 * sc, x0 + 13 * sc, 30 * sc), 0, 180, fill=WHITE)
    dd.rectangle((10 * sc, 30 * sc, 54 * sc, 56 * sc), outline=WHITE, width=int(4 * sc))
    dd.rectangle((36 * sc, 38 * sc, 48 * sc, 56 * sc), outline=WHITE, width=int(3 * sc))
    return im


def icon_receipt(size=110, color=NAVY):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.rectangle((14 * s, 6 * s, 50 * s, 52 * s), outline=color, width=int(3.5 * s))
    pts = [((14 + i * 6) * s, (52 + (4 if i % 2 == 0 else 0)) * s) for i in range(7)]
    d.line(pts, fill=color, width=int(3 * s))
    for yy in (16, 24, 32):
        d.line((20 * s, yy * s, 44 * s, yy * s), fill=color, width=int(3 * s))
    d.line((20 * s, 42 * s, 34 * s, 42 * s), fill=color, width=int(3 * s))
    return img


def icon_return_box(size=110, color=NAVY):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.rectangle((10 * s, 26 * s, 46 * s, 56 * s), outline=color, width=int(3.5 * s))
    d.line((10 * s, 36 * s, 46 * s, 36 * s), fill=color, width=int(3 * s))
    d.arc((26 * s, 4 * s, 58 * s, 32 * s), 300, 180, fill=color, width=int(3.5 * s))
    d.polygon([(24 * s, 16 * s), (36 * s, 10 * s), (34 * s, 24 * s)], fill=color)
    return img


def icon_clipboard(size=110, color=NAVY):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.rounded_rectangle((12 * s, 10 * s, 52 * s, 58 * s), 6 * s, outline=color, width=int(3.5 * s))
    d.rounded_rectangle((24 * s, 4 * s, 40 * s, 16 * s), 4 * s, fill=color)
    for yy in (26, 34, 42):
        d.line((20 * s, yy * s, 44 * s, yy * s), fill=color, width=int(3 * s))
    return img


def icon_magnifier(size=110, color=NAVY):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.ellipse((8 * s, 8 * s, 44 * s, 44 * s), outline=color, width=int(4 * s))
    d.line((40 * s, 40 * s, 56 * s, 56 * s), fill=color, width=int(6 * s))
    d.line((18 * s, 26 * s, 24 * s, 32 * s), fill=color, width=int(4 * s))
    d.line((24 * s, 32 * s, 35 * s, 18 * s), fill=color, width=int(4 * s))
    return img


def framed(path, target_w=None, target_h=None, border=6):
    a = Image.open(path).convert("RGBA")
    r = (target_w / a.width) if target_w else (target_h / a.height)
    a = a.resize((int(a.width * r), int(a.height * r)))
    fr = Image.new("RGBA", (a.width + 2 * border, a.height + 2 * border), (255, 255, 255, 255))
    d = ImageDraw.Draw(fr)
    d.rectangle((0, 0, fr.width - 1, fr.height - 1), outline=(210, 213, 228, 255), width=2)
    fr.alpha_composite(a, (border, border))
    return shadowed(fr, blur=14, alpha=70, off=(0, 10))


def load_rgba(path, target_h=None, target_w=None):
    im = Image.open(path).convert("RGBA")
    if target_h:
        r = target_h / im.height
        im = im.resize((int(im.width * r), target_h))
    elif target_w:
        r = target_w / im.width
        im = im.resize((target_w, int(im.height * r)))
    return im


# ---------------- animation engine ----------------
def eob(p):  # ease out back
    c1, c3 = 1.70158, 2.70158
    p -= 1
    return 1 + c3 * p ** 3 + c1 * p ** 2


def eoc(p):  # ease out cubic
    return 1 - (1 - p) ** 3


class Layer:
    def __init__(self, img, cx, cy, t0, anim="pop", dur=0.34, dy=70, float_amp=0.0):
        self.img, self.cx, self.cy, self.t0 = img, cx, cy, t0
        self.anim, self.dur, self.dy, self.float_amp = anim, dur, dy, float_amp

    def draw(self, canvas, t):
        if t < self.t0:
            return
        p = min(1.0, (t - self.t0) / self.dur)
        img = self.img
        cx, cy = self.cx, self.cy
        alpha = 1.0
        if self.anim == "pop":
            s = 0.6 + 0.4 * eob(p)
            if p < 1.0:
                img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))))
            alpha = min(1.0, p * 3)
        elif self.anim == "slide":
            cy = cy + self.dy * (1 - eoc(p))
            alpha = min(1.0, p * 2.5)
        elif self.anim == "wipe":
            ww = max(1, int(img.width * eoc(p)))
            img = img.crop((0, 0, ww, img.height))
            cx = self.cx - (self.img.width - ww) // 2
        if self.float_amp and p >= 1.0:
            cy += self.float_amp * math.sin(2 * math.pi * (t - self.t0) / 3.2)
        if alpha < 1.0:
            img = img.copy()
            a = img.split()[3].point(lambda v: int(v * alpha))
            img.putalpha(a)
        canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


def render_scene(name, dur, layers, bg=None, kb=None):
    """kb: (image, zoom0, zoom1) full-frame Ken Burns under layers."""
    n = int(round(dur * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
           os.path.join(OUT, f"{name}.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        t = i / FPS
        canvas = (bg or NEN).copy()
        if kb:
            im, z0, z1 = kb
            z = z0 + (z1 - z0) * (i / max(1, n - 1))
            cw, ch = int(im.width / z), int(im.height / z)
            x0 = (im.width - cw) // 2
            y0 = (im.height - ch) // 2
            crop = im.crop((x0, y0, x0 + cw, y0 + ch)).resize((im.width, im.height))
            canvas.alpha_composite(crop, ((W - im.width) // 2, kb_y))
        for L in layers:
            L.draw(canvas, t)
        proc.stdin.write(canvas.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    print("clip", name, f"{dur:.2f}s", flush=True)


kb_y = 0  # set per scene when kb used

# ============ scenes ============
# S1 title 5.22-9.62 (4.40)
layers = [
    Layer(capsule("5 LƯU Ý", 150, WHITE, TEAL, padx=60, pady=28, radius=44, font=F_BLACK), 540, 660, 0.05, "pop", 0.4),
    Layer(textimg("HÓA ĐƠN ĐIỆN TỬ", 96, NAVY), 540, 900, 0.5, "slide"),
    Layer(textimg("CHO SHOP BÁN SÀN TMĐT", 56, INK), 540, 1020, 0.8, "slide"),
    Layer(shadowed(icon_receipt(120)), 540, 1180, 1.1, "pop"),
]
bar = Image.new("RGBA", (240, 12), (0, 0, 0, 0))
ImageDraw.Draw(bar).rounded_rectangle((0, 0, 239, 11), 6, fill=RED)
layers.append(Layer(bar, 540, 1310, 1.3, "wipe", 0.4))
render_scene("S1", 4.40, layers)

# S2 kênh 18.30-24.98 (6.68)
bag = load_rgba(os.path.join(LOGO, "logo-shopee-bag-trang.png"), target_h=60)
tt = load_rgba(os.path.join(LOGO, "logo-tiktok-icon.png"), target_h=60)
plus = textimg("+", 64, NAVY, font=F_BLACK)
layers = [
    Layer(textimg("MỐC 1 TỶ: TÍNH TỔNG CÁC KÊNH", 64, NAVY), 540, 380, 0.1, "slide"),
    Layer(capsule("2 SHOP SHOPEE", 58, WHITE, SHOPEE, icon=bag), 540, 560, 1.0, "pop"),
    Layer(plus, 540, 665, 1.7, "pop", 0.25),
    Layer(capsule("1 SHOP TIKTOK", 58, WHITE, TIKTOK, icon=tt), 540, 770, 2.0, "pop"),
    Layer(plus, 540, 875, 2.6, "pop", 0.25),
    Layer(capsule("BÁN TẠI CỬA HÀNG", 58, WHITE, TEAL, icon=icon_store(58)), 540, 980, 2.9, "pop"),
    Layer(capsule("= CỘNG CHUNG 1 HỘ KINH DOANH", 52, WHITE, NAVY, maxw=960), 540, 1140, 4.3, "slide"),
]
render_scene("S2", 6.68, layers)

# S3 form 36.60-42.40 (5.80)
form = framed(os.path.join(LEGAL, "nd70-pdf-mau-01-dktd-hddt-to-khai-dang-ky.png"), target_h=1050)
layers = [
    Layer(form, 540, 730, 0.05, "slide", 0.45, dy=90),
    Layer(capsule("ĐĂNG KÝ TRONG 30 NGÀY", 62, WHITE, RED, font=F_BLACK), 540, 1440, 2.0, "pop"),
    Layer(textimg("khi doanh thu lũy kế trong năm vượt 1 tỷ", 44, INK), 540, 1580, 2.4, "slide"),
]
render_scene("S3", 5.80, layers)

# S4 portal 58.64-63.94 (5.30)
portal = framed(os.path.join(LEGAL, "cong-hoadondientu-gdt-gov-vn.png"), target_w=980)
layers = [
    Layer(portal, 540, 760, 0.05, "slide", 0.45, dy=90),
    Layer(capsule("hoadondientu.gdt.gov.vn", 58, WHITE, TEAL), 540, 1270, 1.2, "pop"),
    Layer(textimg("Hệ thống hóa đơn điện tử của Cục Thuế", 44, INK), 540, 1400, 1.6, "slide"),
]
render_scene("S4", 5.30, layers)

# S5 tra hang 75.00-82.30 (7.30)
layers = [
    Layer(shadowed(icon_return_box(110)), 540, 360, 0.1, "pop"),
    Layer(textimg("KHÁCH TRẢ HÀNG: SOÁT KỸ TRƯỚC", 62, NAVY), 540, 500, 0.3, "slide"),
    Layer(capsule("HOÀN MỘT PHẦN", 54, WHITE, TEAL, icon=checkbox(50)), 540, 660, 0.7, "pop"),
    Layer(capsule("HOÀN TIỀN, CHƯA TRẢ HÀNG", 54, WHITE, TEAL, icon=checkbox(50)), 540, 810, 2.1, "pop"),
    Layer(capsule("HÀNG HOÀN VỀ BỊ TRÁO", 54, WHITE, TEAL, icon=checkbox(50)), 540, 960, 4.5, "pop"),
    Layer(capsule("CHƯA XÁC NHẬN HÀNG, ĐỪNG VỘI ĐIỀU CHỈNH", 44, WHITE, RED, maxw=960), 540, 1120, 5.7, "slide"),
]
render_scene("S5", 7.30, layers)

# S6 bang ke 101.94-108.44 (6.50)
items = ["THÔNG TIN NGƯỜI BÁN", "SỐ ĐỊNH DANH", "TÊN HÀNG, SỐ LƯỢNG", "ĐƠN GIÁ, GIÁ TRỊ", "CHỨNG TỪ GIAO DỊCH"]
layers = [
    Layer(shadowed(icon_clipboard(110)), 540, 320, 0.1, "pop"),
    Layer(textimg("BẢNG KÊ MUA HÀNG CẦN CÓ", 64, NAVY), 540, 460, 0.3, "slide"),
]
for i, t in enumerate(items):
    layers.append(Layer(capsule(t, 50, WHITE, TEAL, icon=checkbox(46)), 540, 620 + i * 140, 0.9 + i * 1.1, "pop"))
render_scene("S6", 6.50, layers)

# S7 recap 108.78-114.20 (5.42)
layers = [
    Layer(shadowed(icon_magnifier(110)), 540, 360, 0.1, "pop"),
    Layer(textimg("SHOP KIỂM TRA NGAY 3 THỨ", 66, NAVY), 540, 500, 0.3, "slide"),
    Layer(capsule("TỔNG DOANH THU CÁC KÊNH", 48, WHITE, TEAL, icon=checkbox(46), maxw=980), 540, 680, 0.9, "pop"),
    Layer(capsule("TRẠNG THÁI ĐƠN ĐỂ LẬP HÓA ĐƠN", 48, WHITE, NAVY, icon=checkbox(46), maxw=980), 540, 830, 2.3, "pop"),
    Layer(capsule("BỘ CHỨNG TỪ ĐẦU VÀO", 48, WHITE, RED, icon=checkbox(46), maxw=980), 540, 980, 3.9, "pop"),
]
render_scene("S7", 5.42, layers)

# A1 decree p1 2.50-5.12 (2.62)
p1img = framed(os.path.join(LEGAL, "nd70-pdf-trang-1.png"), target_h=1250)
layers = [
    Layer(p1img, 540, 790, 0.02, "slide", 0.4, dy=80),
    Layer(capsule("NGHỊ ĐỊNH 70/2025/NĐ-CP", 50, WHITE, NAVY), 540, 1560, 0.9, "pop"),
]
render_scene("A1", 2.62, layers)

# A2 infographic 32.26-36.60 (4.34)
info = framed(os.path.join(LEGAL, "chinhphu-luu-y-dang-ky-hinh-noi-dung-2025-04-25.jpg"), target_h=1300)
layers = [
    Layer(info, 540, 810, 0.05, "slide", 0.45, dy=90),
    Layer(textimg("Nguồn: ngành Thuế / Cổng TTĐT Chính phủ", 38, GRAY), 540, 1560, 0.8, "slide"),
]
render_scene("A2", 4.34, layers)

# P1-P4 split bg clips (asset slides in; gradient card static)
P_ASSETS = [
    ("P1", "nd70-pdf-may-tinh-tien-1-ty-trang12.png", 5.58),
    ("P2", "nd70-pdf-thoi-diem-lap-hoa-don-trang6.png", 5.82),
    ("P3", "nd70-pdf-tra-lai-hang-trang24.png", 4.00),
    ("P4", "nd70-pdf-dieu-19-dieu-chinh-thay-the-trang23.png", 2.38),
]
for name, asset, dur in P_ASSETS:
    fa = framed(os.path.join(LEGAL, asset), target_w=950)
    if fa.height > 700:
        fa = framed(os.path.join(LEGAL, asset), target_h=640)
    bg = NEN.copy()
    bg.alpha_composite(rounded_card(850, 760), (115, 1055))
    layers = [
        Layer(fa, 540, 165 + fa.height // 2, 0.05, "slide", 0.4, dy=70),
        Layer(textimg("Nghị định 70/2025/NĐ-CP", 34, GRAY, font=F_BOLD), 540, 185 + fa.height + 20, 0.4, "slide", dy=30),
    ]
    render_scene(name, dur, layers, bg=bg)

# A3/A4 full photo scenes (Ken Burns, vertically centered)
def kb_scene_v5(name, path, dur, tw=980):
    img = framed(path, target_w=tw)
    if img.height > 1400:
        img = framed(path, target_h=1300)
    n = int(round(dur * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
           os.path.join(OUT, f"{name}.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    y_center = max(220, (H - img.height) // 2)
    for i in range(n):
        t = i / FPS
        canvas = NEN.copy()
        z = 1.0 + 0.07 * (i / max(1, n - 1))
        cw, ch = int(img.width / z), int(img.height / z)
        x0, y0 = (img.width - cw) // 2, (img.height - ch) // 2
        crop = img.crop((x0, y0, x0 + cw, y0 + ch)).resize((img.width, img.height))
        p = min(1.0, t / 0.35)
        yoff = int(60 * (1 - eoc(p)))
        if p < 1.0:
            a = crop.split()[3].point(lambda v: int(v * min(1, p * 2.5)))
            crop.putalpha(a)
        canvas.alpha_composite(crop, ((W - img.width) // 2, y_center + yoff))
        proc.stdin.write(canvas.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    print("clip", name, flush=True)


kb_scene_v5("A3", os.path.join(LEGAL, "chinhphu-giai-dap-hkd-may-tinh-tien-2025-08-12.jpg"), 3.30)
kb_scene_v5("A4", os.path.join(LEGAL, "chinhphu-luu-y-dang-ky-cover-2025-04-25.jpg"), 3.40)

# E1 end card with real form image instead of icon
form_small = framed(os.path.join(LEGAL, "nd70-pdf-mau-01-dktd-hddt-to-khai-dang-ky.png"), target_h=560)
layers = [
    Layer(capsule("VIDEO TIẾP THEO", 44, WHITE, TEAL), 540, 480, 0.2, "pop"),
    Layer(textimg("ĐĂNG KÝ & XUẤT HÓA ĐƠN", 82, NAVY), 540, 650, 0.55, "slide"),
    Layer(textimg("TỰ ĐỘNG CHO SHOP BÁN SÀN", 82, NAVY), 540, 770, 0.75, "slide"),
    Layer(form_small, 540, 1200, 1.05, "slide", 0.45, dy=80),
]
bar = Image.new("RGBA", (260, 12), (0, 0, 0, 0))
ImageDraw.Draw(bar).rounded_rectangle((0, 0, 259, 11), 6, fill=TEAL)
layers.append(Layer(bar, 540, 1620, 1.4, "wipe", 0.4))
render_scene("E1", 3.70, layers)

# follow capsule (new font)
cap = capsule("LƯU VIDEO · FOLLOW TABCOM", 56, WHITE, NAVY, maxw=960, font=F_BLACK)
cap.save(os.path.join(ROOT, "stickers", "st-follow.png"))
print("follow capsule regenerated", cap.size, flush=True)

# hook platform logo stickers (white border, real logos)
import numpy as _np
from scipy import ndimage as _ndi
LOGOSTORE = P.LOGO


def logo_sticker(src_img, out, pad_h):
    im = src_img.convert("RGBA")
    r = pad_h / im.height
    im = im.resize((int(im.width * r), pad_h))
    a = _np.array(im.split()[3]) > 40
    dil = _ndi.binary_dilation(a, iterations=14)
    border = Image.fromarray((dil * 255).astype(_np.uint8)).filter(ImageFilter.GaussianBlur(1.5))
    canvas = Image.new("RGBA", (im.width + 48, im.height + 48), (0, 0, 0, 0))
    white = Image.new("RGBA", im.size, (255, 255, 255, 255))
    canvas.paste(white, (24, 24), border)
    canvas.alpha_composite(im, (24, 24))
    sh = shadowed(canvas, blur=10, alpha=70, off=(0, 8))
    sh.save(os.path.join(ROOT, "stickers", out))
    print(out, sh.size, flush=True)


logo_sticker(Image.open(os.path.join(LOGOSTORE, "logo-shopee-mau-goc.png")), "st-logo-shopee.png", 300)
logo_sticker(Image.open(os.path.join(LOGOSTORE, "logo-tiktok-icon.png")), "st-logo-tiktok.png", 210)
logo_sticker(Image.open(os.path.join(ROOT, "logo-lazada.png")), "st-logo-lazada.png", 120)

print("ALL V5 CLIPS DONE", flush=True)


def _unused_kb_scene(name, path, dur, tw=940, cap=None):
    img = framed(path, target_w=tw)
    if img.height > 1400:
        img = framed(path, target_h=1300)
    n = int(round(dur * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
           os.path.join(OUT, f"{name}.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    caplayer = Layer(cap, 540, 340 + img.height + 90, 0.6, "pop") if cap else None
    for i in range(n):
        t = i / FPS
        canvas = NEN.copy()
        z = 1.0 + 0.07 * (i / max(1, n - 1))
        cw, ch = int(img.width / z), int(img.height / z)
        x0, y0 = (img.width - cw) // 2, (img.height - ch) // 2
        crop = img.crop((x0, y0, x0 + cw, y0 + ch)).resize((img.width, img.height))
        # entrance fade+slide
        p = min(1.0, t / 0.35)
        yoff = int(60 * (1 - eoc(p)))
        if p < 1.0:
            a = crop.split()[3].point(lambda v: int(v * min(1, p * 2.5)))
            crop.putalpha(a)
        canvas.alpha_composite(crop, ((W - img.width) // 2, 300 + yoff))
        if caplayer:
            caplayer.draw(canvas, t)
        proc.stdin.write(canvas.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    print("clip", name, flush=True)


pass
