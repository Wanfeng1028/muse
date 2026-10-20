# -*- coding: utf-8 -*-
"""Scene clips for 26.08.08 - Traffic nội sàn và ngoại sàn."""
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
LOGO = P.LOGO
FONTS = P.FONTS
F_BLACK = os.path.join(FONTS, "PS Anton - Regular V1.0.otf")
F_XBOLD = os.path.join(FONTS, "Big Shoulders ExtraBold Viet Hoa.otf")
F_BOLD = os.path.join(FONTS, "PS Big Shoulders Bold Viet Hoa.otf")

TEAL = (23, 217, 179, 255)
NAVY = (27, 37, 134, 255)
RED = (198, 0, 1, 255)
INK = (23, 23, 23, 255)
WHITE = (255, 255, 255, 255)
GRAY = (85, 89, 107, 255)
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


def icon_siren(size=160):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.pieslice((14 * s, 18 * s, 50 * s, 54 * s), 180, 360, fill=RED)
    d.rectangle((14 * s, 36 * s, 50 * s, 42 * s), fill=RED)
    d.rounded_rectangle((8 * s, 42 * s, 56 * s, 52 * s), 5 * s, fill=NAVY)
    d.arc((20 * s, 24 * s, 36 * s, 40 * s), 160, 260, fill=(255, 190, 190, 255), width=int(3 * s))
    for ang in (-45, 0, 45):
        r = math.radians(ang - 90)
        d.line((32 * s + 22 * s * math.cos(r), 34 * s + 22 * s * math.sin(r),
                32 * s + 30 * s * math.cos(r), 34 * s + 30 * s * math.sin(r)), fill=RED, width=int(3.5 * s))
    return shadowed(img, blur=8, alpha=55)


def icon_chat(size=130, color=NAVY):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.rounded_rectangle((6 * s, 10 * s, 58 * s, 44 * s), 10 * s, outline=color, width=int(4 * s))
    d.polygon([(20 * s, 44 * s), (32 * s, 56 * s), (34 * s, 44 * s)], fill=color)
    for i in range(3):
        d.ellipse(((18 + i * 12) * s, 24 * s, (24 + i * 12) * s, 30 * s), fill=color)
    return shadowed(img, blur=8, alpha=55)


def icon_bookmark(size=130, color=NAVY):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.polygon([(16 * s, 6 * s), (48 * s, 6 * s), (48 * s, 58 * s), (32 * s, 44 * s), (16 * s, 58 * s)],
              outline=color, fill=None, width=int(4 * s))
    d.line((24 * s, 24 * s, 40 * s, 24 * s), fill=color, width=int(4 * s))
    return shadowed(img, blur=8, alpha=55)


def badge(icon_path, size=150, ratio=0.68, crop_box=None):
    im = Image.open(icon_path).convert("RGBA")
    if crop_box:
        im = im.crop(crop_box)
        im = im.crop(im.getbbox())
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, size - 1, size - 1), 32, fill=WHITE, outline=(224, 227, 238, 255), width=2)
    m = size * ratio
    r = min(m / im.width, m / im.height)
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
    card.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    return shadowed(card, blur=10, alpha=70, off=(0, 8))


def framed(path, target_w=None, target_h=None, border=6):
    a = Image.open(path).convert("RGBA")
    r = (target_w / a.width) if target_w else (target_h / a.height)
    a = a.resize((int(a.width * r), int(a.height * r)))
    fr = Image.new("RGBA", (a.width + 2 * border, a.height + 2 * border), (255, 255, 255, 255))
    ImageDraw.Draw(fr).rectangle((0, 0, fr.width - 1, fr.height - 1), outline=(210, 213, 228, 255), width=2)
    fr.alpha_composite(a, (border, border))
    return shadowed(fr, blur=14, alpha=70, off=(0, 10))


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


def eob(p):
    c1, c3 = 1.70158, 2.70158
    p -= 1
    return 1 + c3 * p ** 3 + c1 * p ** 2


def eoc(p):
    return 1 - (1 - p) ** 3


class Layer:
    def __init__(self, img, cx, cy, t0, anim="pop", dur=0.34, dy=70, shake=0.0):
        self.img, self.cx, self.cy, self.t0 = img, cx, cy, t0
        self.anim, self.dur, self.dy, self.shake = anim, dur, dy, shake

    def draw(self, canvas, t):
        if t < self.t0:
            return
        p = min(1.0, (t - self.t0) / self.dur)
        img, cx, cy, alpha = self.img, self.cx, self.cy, 1.0
        if self.anim == "pop":
            sc = 0.6 + 0.4 * eob(p)
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


def render(name, dur, layers, bg=None):
    outp = os.path.join(OUT, f"{name}.mp4")
    if os.path.exists(outp) and os.path.getsize(outp) > 20000:
        print("skip", name, flush=True)
        return
    n = int(round(dur * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "fast",
           "-crf", "18", "-pix_fmt", "yuv420p", os.path.join(OUT, f"{name}.mp4")]
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


# badges
bd_shopee = badge(os.path.join(LOGO, "logo-shopee-mau-goc.png"), 150, 0.66, crop_box=None)
_sh = Image.open(os.path.join(LOGO, "logo-shopee-mau-goc.png")).convert("RGBA")
bd_shopee = badge(os.path.join(LOGO, "logo-shopee-mau-goc.png"), 150, 0.66,
                  crop_box=(0, 0, _sh.width, int(_sh.height * 0.76)))
bd_tiktok = badge(os.path.join(LOGO, "logo-tiktok-icon.png"), 150, 0.72)
bd_fb = badge(os.path.join(LOGO, "logo-facebook-icon.png"), 150, 0.74)
bd_zalo = badge(os.path.join(LOGO, "logo-zalo-icon.png"), 150, 0.78)

# ---------------- 1. S_HOOK 1.50 / 2.45 ----------------
render("S_HOOK", 2.45, [
    Layer(icon_siren(170), 540, 520, 0.02, "pop", 0.36, shake=5),
    Layer(textimg("TẮT ADS 2 NGÀY", 92, NAVY), 540, 790, 0.28, "slide"),
    Layer(capsule("ĐƠN VỀ GẦN 0", 96, WHITE, RED, font=F_BLACK), 540, 1000, 0.6, "pop", 0.38),
    Layer(textimg("Lỗi không nằm ở ads", 50, INK, font=F_BOLD), 540, 1190, 0.95, "slide"),
])

# ---------------- 2. S_ONE 4.10 / 3.65 ----------------
one = [
    Layer(textimg("SHOP ĐANG SỐNG BẰNG", 62, NAVY), 540, 430, 0.05, "slide"),
    Layer(capsule("ĐÚNG 1 NGUỒN TRAFFIC", 78, WHITE, TEAL, font=F_BLACK), 540, 600, 0.35, "pop", 0.4),
    Layer(arrow_down(28, 100, RED), 540, 760, 0.9, "slide", dy=40),
    Layer(capsule("NGUỒN ĐÓ TỤT", 62, WHITE, RED, icon=warn_tri(46)), 540, 920, 1.35, "pop"),
    Layer(arrow_down(28, 100, RED), 540, 1070, 1.75, "slide", dy=40),
    Layer(capsule("DOANH SỐ TỤT THEO", 62, WHITE, NAVY), 540, 1230, 2.1, "pop"),
]
render("S_ONE", 3.65, one)

# ---------------- 3. S_TWO 8.00 / 3.55 ----------------
def block(title, sub, bg_col, w=430, h=300):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 38, fill=bg_col)
    ft = fit_font(F_BLACK, int(62 * 1.22), title, w - 60)
    tw = text_w(ft, title)
    asc, desc = ft.getmetrics()
    d.text(((w - tw) // 2, 78), title, font=ft, fill=WHITE)
    fs = fit_font(F_BOLD, int(34 * 1.22), sub, w - 70)
    sw = text_w(fs, sub)
    d.text(((w - sw) // 2, 78 + asc + desc + 16), sub, font=fs, fill=(235, 240, 255, 255))
    return shadowed(img, blur=12, alpha=65, off=(0, 8))


render("S_TWO", 3.55, [
    Layer(textimg("TRAFFIC VÀO SHOP CHỈ CÓ 2 NHÓM", 60, NAVY), 540, 430, 0.05, "slide"),
    Layer(block("NỘI SÀN", "trong sàn bạn bán", TEAL), 300, 780, 0.45, "pop", 0.4),
    Layer(block("NGOẠI SÀN", "kênh bên ngoài", NAVY), 780, 780, 0.95, "pop", 0.4),
])

# ---------------- 4. S_SHOPEE 14.55 / 6.30 ----------------
render("S_SHOPEE", 6.30, [
    Layer(bd_shopee, 540, 400, 0.05, "pop", 0.38),
    Layer(textimg("TRAFFIC NỘI SÀN SHOPEE", 58, NAVY), 540, 570, 0.3, "slide"),
    Layer(capsule("KHÁCH GÕ TÌM KIẾM", 54, WHITE, TEAL, icon=checkbox(46)), 540, 740, 0.75, "pop"),
    Layer(capsule("SẢN PHẨM ĐỀ XUẤT", 54, WHITE, TEAL, icon=checkbox(46)), 540, 890, 1.9, "pop"),
    Layer(capsule("BẤM QUẢNG CÁO", 54, WHITE, TEAL, icon=checkbox(46)), 540, 1040, 3.1, "pop"),
    Layer(capsule("SHOPEE LIVE & VIDEO", 54, WHITE, TEAL, icon=checkbox(46)), 540, 1190, 4.2, "pop"),
])

# ---------------- 5. S_TIKTOK 21.00 / 5.15 ----------------
render("S_TIKTOK", 5.15, [
    Layer(bd_tiktok, 540, 400, 0.05, "pop", 0.38),
    Layer(textimg("TRAFFIC NỘI SÀN TIKTOK SHOP", 54, NAVY), 540, 570, 0.3, "slide"),
    Layer(capsule("VIDEO", 54, WHITE, TEAL, icon=checkbox(46)), 540, 740, 0.7, "pop"),
    Layer(capsule("LIVESTREAM", 54, WHITE, TEAL, icon=checkbox(46)), 540, 890, 1.5, "pop"),
    Layer(capsule("QUẢNG CÁO", 54, WHITE, TEAL, icon=checkbox(46)), 540, 1040, 2.4, "pop"),
    Layer(capsule("ĐIỂM PHÂN PHỐI TRONG APP", 50, WHITE, TEAL, icon=checkbox(46)), 540, 1190, 3.3, "pop"),
])

# ---------------- 6. S_PRO 26.35 / 4.45 ----------------
render("S_PRO", 4.45, [
    Layer(capsule("ƯU ĐIỂM NỘI SÀN", 46, WHITE, TEAL), 540, 430, 0.05, "pop"),
    Layer(textimg("KHÁCH ĐANG Ở RẤT GẦN", 72, NAVY), 540, 640, 0.35, "slide"),
    Layer(textimg("HÀNH VI MUA", 72, NAVY), 540, 760, 0.55, "slide"),
    Layer(arrow_down(28, 90, TEAL), 540, 900, 1.5, "slide", dy=40),
    Layer(capsule("TRANG BÁN TỐT = CHỐT NHANH", 52, WHITE, NAVY, maxw=980), 540, 1060, 1.9, "pop"),
])

# ---------------- 7. S_RISK 33.95 / 4.45 ----------------
render("S_RISK", 4.45, [
    Layer(icon_siren(130), 540, 360, 0.02, "pop", 0.34, shake=4),
    Layer(textimg("QUYỀN PHÂN PHỐI KHÔNG THUỘC SHOP", 46, RED), 540, 520, 0.25, "slide"),
    Layer(capsule("THUẬT TOÁN THAY ĐỔI", 50, WHITE, RED, icon=warn_tri(44)), 540, 680, 0.6, "pop"),
    Layer(capsule("GIÁ THẦU TĂNG", 50, WHITE, RED, icon=warn_tri(44)), 540, 820, 1.35, "pop"),
    Layer(capsule("VIDEO GIẢM PHÂN PHỐI", 50, WHITE, RED, icon=warn_tri(44)), 540, 960, 2.1, "pop"),
    Layer(capsule("LIVE TỤT MẮT XEM", 50, WHITE, RED, icon=warn_tri(44)), 540, 1100, 2.85, "pop"),
    Layer(textimg("traffic giảm ngay", 44, INK, font=F_BOLD), 540, 1250, 3.4, "slide"),
])

# ---------------- 8. S_OUT 42.10 / 5.05 ----------------
render("S_OUT", 5.05, [
    Layer(textimg("TRAFFIC NGOẠI SÀN", 76, NAVY), 540, 350, 0.05, "slide"),
    Layer(bd_fb, 300, 540, 0.35, "pop", 0.34),
    Layer(bd_zalo, 540, 540, 0.5, "pop", 0.34),
    Layer(bd_tiktok, 780, 540, 0.65, "pop", 0.34),
    Layer(capsule("FANPAGE · GROUP", 52, WHITE, TEAL, icon=checkbox(44)), 540, 760, 1.0, "pop"),
    Layer(capsule("ZALO · WEBSITE", 52, WHITE, TEAL, icon=checkbox(44)), 540, 900, 1.9, "pop"),
    Layer(capsule("KOC · KHÁCH CŨ", 52, WHITE, TEAL, icon=checkbox(44)), 540, 1040, 2.8, "pop"),
    Layer(capsule("KHÁCH GIỚI THIỆU NGƯỜI QUEN", 48, WHITE, NAVY, maxw=980), 540, 1190, 3.7, "pop"),
])

# ---------------- 9. P_COLD 47.25 / 3.60 (split) ----------------
bg = NEN.copy()
fa = framed(os.path.join(AST, "facebook-group-tabcom-2026-08-08.png"), target_h=560)
bg.alpha_composite(rounded_card(850, 760), (115, 1055))
render("P_COLD", 3.60, [
    Layer(fa, 540, 165 + fa.height // 2 - 30, 0.03, "slide", 0.4, dy=70),
    Layer(textimg("Ảnh: Facebook Group người bán", 30, GRAY, font=F_BOLD), 540, 760, 0.35, "slide", dy=30),
    Layer(capsule("KHÁCH LẠNH HƠN · PHẢI NUÔI ĐỀU", 46, WHITE, NAVY, maxw=900), 540, 880, 0.7, "pop"),
], bg=bg)

# ---------------- 10. S_OWN 51.05 / 6.50 ----------------
strike = Image.new("RGBA", (760, 8), (0, 0, 0, 0))
ImageDraw.Draw(strike).rounded_rectangle((0, 0, 759, 7), 4, fill=RED)
render("S_OWN", 6.50, [
    Layer(textimg("ĐỔI LẠI, SHOP XÂY ĐƯỢC", 56, NAVY), 540, 400, 0.05, "slide"),
    Layer(capsule("TỆP KHÁCH CỦA RIÊNG MÌNH", 66, WHITE, TEAL, font=F_BLACK, maxw=980), 540, 570, 0.4, "pop", 0.4),
    Layer(capsule("CHỦ ĐỘNG TIẾP CẬN LẠI", 52, WHITE, NAVY), 540, 760, 1.6, "pop"),
    Layer(textimg("thay vì", 44, GRAY, font=F_BOLD), 540, 900, 2.9, "slide"),
    Layer(capsule("MỖI LẦN CẦN ĐƠN LẠI MUA TRAFFIC", 46, WHITE, RED, maxw=980), 540, 1030, 3.5, "pop"),
    Layer(strike, 540, 1030, 5.1, "wipe", 0.5),
])

# ---------------- 11. P_TEST 58.00 / 8.70 (split) ----------------
bg = NEN.copy()
fa = framed(os.path.join(AST, "shopee-seller-app-hieu-qua-ban-hang-google-play-2026-08-08.png"), target_h=620)
bg.alpha_composite(rounded_card(850, 760), (115, 1055))
render("P_TEST", 8.70, [
    Layer(fa, 540, 200 + fa.height // 2 - 40, 0.03, "slide", 0.4, dy=70),
    Layer(textimg("Ảnh: Shopee Seller trên Google Play", 30, GRAY, font=F_BOLD), 540, 810, 0.35, "slide", dy=30),
    Layer(capsule("MỞ PHÂN TÍCH TRONG TRANG QUẢN LÝ", 42, WHITE, NAVY, maxw=900), 540, 900, 0.7, "pop"),
    Layer(capsule("30 NGÀY GẦN NHẤT · ĐƠN ĐẾN TỪ ĐÂU?", 42, WHITE, TEAL, maxw=900), 540, 990, 6.1, "pop"),
], bg=bg)

# ---------------- 12. S_50A 67.10 / 4.65 ----------------
render("S_50A", 4.65, [
    Layer(textimg("PHẦN LỚN DOANH THU ĐẾN TỪ?", 54, NAVY), 540, 430, 0.05, "slide"),
    Layer(capsule("ADS", 60, WHITE, RED, icon=warn_tri(46)), 540, 640, 0.5, "pop"),
    Layer(capsule("LIVE", 60, WHITE, RED, icon=warn_tri(46)), 540, 800, 1.5, "pop"),
    Layer(capsule("VÀI VIDEO VIRAL", 60, WHITE, RED, icon=warn_tri(46)), 540, 960, 2.5, "pop"),
    Layer(textimg("chỉ 1 chân trụ", 46, INK, font=F_BOLD), 540, 1120, 3.5, "slide"),
])

# ---------------- 13. S_50B 71.85 / 3.60 ----------------
render("S_50B", 3.60, [
    Layer(textimg("NẾU NGÀY MAI CÙNG TỤT", 56, NAVY), 540, 480, 0.05, "slide"),
    Layer(textimg("50%", 300, RED, font=F_BLACK), 540, 780, 0.4, "pop", 0.42),
    Layer(capsule("SHOP CÒN BAO NHIÊU ĐƠN?", 58, WHITE, NAVY, maxw=980), 540, 1080, 1.5, "pop"),
])

# ---------------- 14. S_DEP 75.70 / 3.40 ----------------
render("S_DEP", 3.40, [
    Layer(icon_siren(150), 540, 500, 0.02, "pop", 0.34, shake=5),
    Layer(textimg("GẦN NHƯ KHÔNG CÒN?", 62, NAVY), 540, 740, 0.35, "slide"),
    Layer(capsule("PHỤ THUỘC TRAFFIC QUÁ NẶNG", 56, WHITE, RED, font=F_BLACK, maxw=980), 540, 930, 0.8, "pop", 0.4),
])

# ---------------- 15. S_ORDER 79.25 / 5.10 ----------------
def numbered(num, text, bg_col, w=880):
    cap = capsule(text, 56, WHITE, bg_col, maxw=w - 130)
    img = Image.new("RGBA", (cap.width + 130, max(cap.height, 120)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(F_BLACK, int(92 * 1.22))
    d.text((6, (img.height - sum(f.getmetrics())) // 2), num, font=f, fill=(200, 205, 225, 255))
    img.alpha_composite(cap, (120, (img.height - cap.height) // 2))
    return img


render("S_ORDER", 5.10, [
    Layer(textimg("MUỐN BỀN PHẢI CÓ CẢ HAI", 58, NAVY), 540, 430, 0.05, "slide"),
    Layer(numbered("1", "NỘI SÀN", TEAL), 540, 660, 0.5, "pop"),
    Layer(numbered("2", "NGOẠI SÀN", NAVY), 540, 830, 1.3, "pop"),
    Layer(capsule("SHOP MỚI: LO NỘI SÀN TRƯỚC", 54, WHITE, RED, font=F_BLACK, maxw=980), 540, 1060, 2.6, "pop", 0.4),
])

# ---------------- 16. S_CHK1 84.65 / 5.55 ----------------
render("S_CHK1", 5.55, [
    Layer(capsule("BƯỚC 1 · NỘI SÀN", 44, WHITE, TEAL), 540, 400, 0.05, "pop"),
    Layer(textimg("CHUẨN HÓA TRANG SẢN PHẨM", 60, NAVY), 540, 580, 0.35, "slide"),
    Layer(textimg("để traffic vào là chốt được đơn", 42, INK, font=F_BOLD), 540, 690, 0.6, "slide"),
    Layer(capsule("TIÊU ĐỀ ĐÚNG THỨ KHÁCH TÌM", 48, WHITE, NAVY, icon=checkbox(46), maxw=980), 540, 880, 2.1, "pop"),
    Layer(capsule("HÌNH ẢNH ĐÚNG NHU CẦU", 48, WHITE, NAVY, icon=checkbox(46), maxw=980), 540, 1030, 3.6, "pop"),
])

# ---------------- 17. S_CHK2 90.30 / 6.25 ----------------
render("S_CHK2", 6.25, [
    Layer(capsule("BƯỚC 1 · NỘI SÀN", 44, WHITE, TEAL), 540, 400, 0.03, "pop"),
    Layer(capsule("ĐỦ REVIEW & BẰNG CHỨNG MUA HÀNG", 44, WHITE, NAVY, icon=checkbox(46), maxw=990), 540, 620, 0.35, "pop"),
    Layer(capsule("TỐI ƯU GIÁ", 48, WHITE, NAVY, icon=checkbox(46), maxw=980), 540, 780, 2.1, "pop"),
    Layer(capsule("TỒN KHO · VẬN HÀNH · CSKH", 46, WHITE, NAVY, icon=checkbox(46), maxw=990), 540, 940, 3.4, "pop"),
    Layer(capsule("ỔN ĐỊNH", 52, WHITE, TEAL), 540, 1110, 5.0, "pop"),
])

# ---------------- 18. S_EXP 96.65 / 4.40 ----------------
render("S_EXP", 4.40, [
    Layer(capsule("BƯỚC 2 · NGOẠI SÀN", 44, WHITE, NAVY), 540, 380, 0.05, "pop"),
    Layer(textimg("CHỐT ĐƯỢC ĐƠN RỒI MỚI MỞ RỘNG", 48, NAVY), 540, 540, 0.3, "slide"),
    Layer(bd_tiktok, 350, 730, 0.7, "pop", 0.32),
    Layer(bd_fb, 540, 730, 0.85, "pop", 0.32),
    Layer(bd_zalo, 730, 730, 1.0, "pop", 0.32),
    Layer(capsule("TIKTOK · FACEBOOK · GROUP", 48, WHITE, TEAL, maxw=980), 540, 940, 1.5, "pop"),
    Layer(capsule("SEO CONTENT", 48, WHITE, TEAL), 540, 1080, 2.6, "pop"),
])

# ---------------- 19. S_KEEP 101.15 / 6.20 ----------------
render("S_KEEP", 6.20, [
    Layer(textimg("VÀ GIỮ KHÁCH LẠI", 60, NAVY), 540, 430, 0.05, "slide"),
    Layer(capsule("KÉO KHÁCH MỚI", 50, WHITE, TEAL, icon=checkbox(46)), 540, 640, 0.4, "pop"),
    Layer(capsule("LƯU DATA KHÁCH CŨ", 50, WHITE, TEAL, icon=checkbox(46)), 540, 800, 1.9, "pop"),
    Layer(capsule("CƠ CHẾ QUAY LẠI MUA TIẾP", 48, WHITE, TEAL, icon=checkbox(46), maxw=980), 540, 960, 3.3, "pop"),
    Layer(capsule("KHÁCH GIỚI THIỆU KHÁCH", 48, WHITE, NAVY, maxw=980), 540, 1120, 4.9, "pop"),
])

# ---------------- 20. S_CTA 107.55 / 3.30 ----------------
render("S_CTA", 3.30, [
    Layer(icon_chat(140), 540, 480, 0.03, "pop", 0.36),
    Layer(textimg("COMMENT CHO TABCOM", 62, NAVY), 540, 700, 0.3, "slide"),
    Layer(capsule("NGUỒN NÀO ĐANG KÉO ĐƠN CHÍNH?", 46, WHITE, TEAL, maxw=990), 540, 880, 0.7, "pop"),
])

# ---------------- 21. S_SAVE 111.05 / 3.00 ----------------
render("S_SAVE", 3.00, [
    Layer(icon_bookmark(140), 540, 480, 0.03, "pop", 0.36),
    Layer(capsule("LƯU VIDEO NÀY LẠI", 72, WHITE, NAVY, font=F_BLACK), 540, 720, 0.3, "pop", 0.4),
    Layer(textimg("để biết mình đang lệ thuộc ở đâu", 44, INK, font=F_BOLD), 540, 900, 0.75, "slide"),
])

print("ALL SCENES DONE", flush=True)
