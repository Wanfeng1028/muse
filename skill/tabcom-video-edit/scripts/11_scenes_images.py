# -*- coding: utf-8 -*-
"""V2 scenes: images in every scene + varied text animations."""
import math
import os
import subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageFont

here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, "scenes.py"), encoding="utf-8").read()
exec(compile(src[:src.find("# badges")], "helpers", "exec"), globals())

PH = os.path.join(here, "photos")
OUT = os.path.join(here, "clips")


# ---------------- photo helpers ----------------
def photo(name, w, h, radius=28, border=6, folder=None):
    p = os.path.join(folder or PH, name)
    im = Image.open(p).convert("RGB")
    r = max(w / im.width, h / im.height)
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
    x0 = (im.width - w) // 2
    y0 = int((im.height - h) * 0.38)
    im = im.crop((x0, y0, x0 + w, y0 + h)).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    card = Image.new("RGBA", (w + 2 * border, h + 2 * border), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, card.width - 1, card.height - 1), radius + border, fill=WHITE)
    card.paste(im, (border, border), mask)
    return shadowed(card, blur=14, alpha=70, off=(0, 10))


def shot(name, target_h=None, target_w=None, radius=22):
    """Screenshot from collected asset folder, rounded + white frame."""
    p = os.path.join(AST, name)
    im = Image.open(p).convert("RGBA")
    r = (target_h / im.height) if target_h else (target_w / im.width)
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius, fill=255)
    card = Image.new("RGBA", (im.width + 12, im.height + 12), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, card.width - 1, card.height - 1), radius + 6, fill=WHITE)
    card.paste(im, (6, 6), mask)
    return shadowed(card, blur=14, alpha=70, off=(0, 10))


# ---------------- animation layers ----------------
class L2(Layer):
    """Extended animations: slideL, slideR, blurin, flip, shakein."""

    def draw(self, canvas, t):
        if t < self.t0:
            return
        p = min(1.0, (t - self.t0) / self.dur)
        img, cx, cy, alpha = self.img, self.cx, self.cy, 1.0
        a = self.anim
        if a in ("slideL", "slideR"):
            off = (self.dy or 160) * (1 - eoc(p))
            cx = cx + (-off if a == "slideL" else off)
            alpha = min(1.0, p * 2.5)
        elif a == "blurin":
            if p < 1.0:
                img = img.filter(ImageFilter.GaussianBlur(14 * (1 - p)))
            alpha = min(1.0, p * 2.2)
        elif a == "flip":
            w = max(2, int(img.width * (0.15 + 0.85 * eob(p)))) if p < 1 else img.width
            img = img.resize((w, img.height))
            alpha = min(1.0, p * 3)
        elif a == "shakein":
            sc = 0.7 + 0.3 * eob(p)
            if p < 1.0:
                img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))))
            alpha = min(1.0, p * 3)
            if p >= 1.0 and (t - self.t0) < self.dur + 0.7:
                cx += 7 * math.sin(2 * math.pi * 9 * (t - self.t0))
        else:
            return Layer.draw(self, canvas, t)
        if alpha < 1.0:
            img = img.copy()
            img.putalpha(img.split()[3].point(lambda v: int(v * alpha)))
        canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


class TypeLayer:
    """Typewriter reveal, char by char."""

    def __init__(self, text, size, color, cx, cy, t0, cps=22, font=None, maxw=980):
        self.text, self.cx, self.cy, self.t0, self.cps = text, cx, cy, t0, cps
        self.font_path = font or F_XBOLD
        self.size = int(size * 1.22)
        f = fit_font(self.font_path, self.size, text, maxw)
        self.f = f
        self.color = color
        asc, desc = f.getmetrics()
        self.h = asc + desc
        self.full_w = text_w(f, text)

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
    """Number counting up, e.g. 0% -> 50%."""

    def __init__(self, target, size, color, cx, cy, t0, dur=1.0, suffix="%", font=None):
        self.target, self.t0, self.dur, self.suffix = target, t0, dur, suffix
        self.font_path = font or F_BLACK
        self.f = ImageFont.truetype(self.font_path, int(size * 1.22))
        self.color = color
        self.cx, self.cy = cx, cy

    def draw(self, canvas, t):
        if t < self.t0:
            return
        p = min(1.0, (t - self.t0) / self.dur)
        val = int(round(self.target * eoc(p)))
        s = f"{val}{self.suffix}"
        tw = text_w(self.f, s)
        asc, desc = self.f.getmetrics()
        img = Image.new("RGBA", (tw + 20, asc + desc + 10), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((10, 0), s, font=self.f, fill=self.color)
        sc = 1.0 + 0.12 * (1 - eoc(min(1, (t - self.t0 - self.dur) / 0.3))) if p >= 1.0 and t - self.t0 < self.dur + 0.3 else 1.0
        if sc != 1.0:
            img = img.resize((int(img.width * sc), int(img.height * sc)))
        canvas.alpha_composite(img, (int(self.cx - img.width / 2), int(self.cy - img.height / 2)))


class MarkerLayer:
    """Text with a highlight bar sweeping behind it."""

    def __init__(self, text, size, color, bar, cx, cy, t0, dur=0.5, font=None, maxw=980):
        self.font_path = font or F_XBOLD
        self.f = fit_font(self.font_path, int(size * 1.22), text, maxw)
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


# badges
_sh = Image.open(os.path.join(LOGO, "logo-shopee-mau-goc.png")).convert("RGBA")


def badge(icon_path, size=140, ratio=0.68, crop_box=None):
    im = Image.open(icon_path).convert("RGBA")
    if crop_box:
        im = im.crop(crop_box)
        im = im.crop(im.getbbox())
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, size - 1, size - 1), 30, fill=WHITE, outline=(224, 227, 238, 255), width=2)
    m = size * ratio
    r = min(m / im.width, m / im.height)
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
    card.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    return shadowed(card, blur=10, alpha=70, off=(0, 8))


bd_shopee = badge(os.path.join(LOGO, "logo-shopee-mau-goc.png"), 140, 0.66, (0, 0, _sh.width, int(_sh.height * 0.76)))
bd_tiktok = badge(os.path.join(LOGO, "logo-tiktok-icon.png"), 140, 0.72)
bd_fb = badge(os.path.join(LOGO, "logo-facebook-icon.png"), 140, 0.74)
bd_zalo = badge(os.path.join(LOGO, "logo-zalo-icon.png"), 140, 0.78)

FORCE = True
ONLY = {"P_COLD"}


def rr(name, dur, layers, bg=None):
    if ONLY and name not in ONLY:
        print("keep", name, flush=True); return
    p = os.path.join(OUT, f"{name}.mp4")
    if os.path.exists(p) and FORCE:
        os.remove(p)
    render(name, dur, layers, bg=bg)


# ================= scenes =================
# 1. HOOK: typewriter + siren + falling chart photo
rr("S_HOOK", 2.45, [
    L2(icon_siren(150), 540, 430, 0.02, "pop", 0.34, shake=5),
    TypeLayer("TẮT ADS 2 NGÀY", 84, NAVY, 540, 660, 0.25, cps=17),
    L2(capsule("ĐƠN VỀ GẦN 0", 92, WHITE, RED, font=F_BLACK), 540, 850, 0.95, "shakein", 0.38),
    L2(photo("analytics-1.jpg", 700, 380), 540, 1210, 1.35, "blurin", 0.5),
])

# 2. ONE SOURCE: flow + seller photo
rr("S_ONE", 3.65, [
    L2(textimg("SHOP ĐANG SỐNG BẰNG", 56, NAVY), 540, 330, 0.05, "slide"),
    L2(capsule("ĐÚNG 1 NGUỒN TRAFFIC", 72, WHITE, TEAL, font=F_BLACK), 540, 470, 0.3, "flip", 0.42),
    L2(photo("livestream-1.jpg", 620, 400), 540, 800, 0.7, "blurin", 0.5),
    L2(capsule("NGUỒN ĐÓ TỤT", 56, WHITE, RED, icon=warn_tri(44)), 540, 1120, 1.35, "slideL", 0.4, dy=200),
    L2(capsule("DOANH SỐ TỤT THEO", 56, WHITE, NAVY), 540, 1270, 2.1, "slideR", 0.4, dy=200),
])

# 3. TWO GROUPS: blocks with photos, flip in
def flat_photo(name, w, h, radius=18, folder=None):
    p = os.path.join(folder or PH, name)
    im = Image.open(p).convert("RGB")
    r = max(w / im.width, h / im.height)
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
    x0 = (im.width - w) // 2
    y0 = int((im.height - h) * 0.38)
    im = im.crop((x0, y0, x0 + w, y0 + h)).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def block_photo(title, sub, col, img_name, folder=None, w=440):
    h = 450
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 34, fill=col)
    ft = fit_font(F_BLACK, int(52 * 1.22), title, w - 50)
    ta = sum(ft.getmetrics())
    d.text(((w - text_w(ft, title)) // 2, 18), title, font=ft, fill=WHITE)
    fs = fit_font(F_BOLD, int(26 * 1.22), sub, w - 60)
    sa = sum(fs.getmetrics())
    d.text(((w - text_w(fs, sub)) // 2, 18 + ta + 2), sub, font=fs, fill=(232, 238, 255, 255))
    top = 18 + ta + 2 + sa + 16
    ph = flat_photo(img_name, w - 44, h - top - 22, folder=folder)
    img.alpha_composite(ph, (22, top))
    return shadowed(img, blur=12, alpha=65, off=(0, 8))


rr("S_TWO", 3.55, [
    L2(textimg("TRAFFIC VÀO SHOP CHỈ CÓ 2 NHÓM", 56, NAVY), 540, 340, 0.05, "slide"),
    L2(block_photo("NỘI SÀN", "trong sàn bạn bán", TEAL, "phoneshop-1.jpg"), 296, 760, 0.4, "flip", 0.42),
    L2(block_photo("NGOẠI SÀN", "kênh bên ngoài", NAVY, "social-1.jpg"), 784, 760, 0.85, "flip", 0.42),
    L2(photo("packing-3.jpg", 880, 330), 540, 1230, 1.5, "blurin", 0.5),
])

# 4. SHOPEE: app screenshot left, capsules slide from right
sh_app = shot("shopee-app-mua-hang-trang-chu-google-play-2026-08-08.png", target_h=690)
rr("S_SHOPEE", 6.30, [
    L2(bd_shopee, 190, 330, 0.05, "pop", 0.34),
    L2(textimg("TRAFFIC NỘI SÀN SHOPEE", 50, NAVY), 620, 330, 0.25, "slideR", 0.4, dy=180),
    L2(sh_app, 300, 850, 0.5, "slideL", 0.45, dy=260),
    L2(capsule("KHÁCH GÕ TÌM KIẾM", 42, WHITE, TEAL, icon=checkbox(40), maxw=520), 772, 620, 0.85, "slideR", 0.4, dy=200),
    L2(capsule("SẢN PHẨM ĐỀ XUẤT", 42, WHITE, TEAL, icon=checkbox(40), maxw=520), 772, 760, 1.9, "slideR", 0.4, dy=200),
    L2(capsule("BẤM QUẢNG CÁO", 42, WHITE, TEAL, icon=checkbox(40), maxw=520), 772, 900, 3.1, "slideR", 0.4, dy=200),
    L2(capsule("LIVE & VIDEO", 42, WHITE, TEAL, icon=checkbox(40), maxw=520), 772, 1040, 4.2, "slideR", 0.4, dy=200),
    L2(photo("livestream-2.jpg", 480, 250), 772, 1240, 5.0, "blurin", 0.45),
])

# 5. TIKTOK
tt_app = shot("tiktokshop-seller-app-trang-chu-google-play-2026-08-08.png", target_h=650)
rr("S_TIKTOK", 5.15, [
    L2(bd_tiktok, 190, 330, 0.05, "pop", 0.34),
    L2(textimg("NỘI SÀN TIKTOK SHOP", 50, NAVY), 640, 330, 0.25, "slideR", 0.4, dy=180),
    L2(tt_app, 320, 830, 0.5, "slideL", 0.45, dy=260),
    L2(capsule("VIDEO", 44, WHITE, TEAL, icon=checkbox(40), maxw=460), 800, 620, 0.8, "slideR", 0.4, dy=200),
    L2(capsule("LIVESTREAM", 44, WHITE, TEAL, icon=checkbox(40), maxw=460), 800, 760, 1.6, "slideR", 0.4, dy=200),
    L2(capsule("QUẢNG CÁO", 44, WHITE, TEAL, icon=checkbox(40), maxw=460), 800, 900, 2.5, "slideR", 0.4, dy=200),
    L2(capsule("ĐIỂM PHÂN PHỐI", 42, WHITE, TEAL, icon=checkbox(40), maxw=460), 800, 1040, 3.4, "slideR", 0.4, dy=200),
])

# 6. PRO: big photo + marker text
rr("S_PRO", 4.45, [
    L2(capsule("ƯU ĐIỂM NỘI SÀN", 42, WHITE, TEAL), 540, 330, 0.05, "pop"),
    L2(photo("phoneshop-2.jpg", 880, 520), 540, 700, 0.3, "blurin", 0.5),
    MarkerLayer("KHÁCH Ở RẤT GẦN HÀNH VI MUA", 52, NAVY, (196, 250, 240, 255), 540, 1080, 1.1, 0.6),
    L2(capsule("TRANG BÁN TỐT = CHỐT NHANH", 48, WHITE, NAVY, maxw=980), 540, 1250, 2.1, "flip", 0.4),
])

# 7. RISK: chart photo + shaking red capsules
rr("S_RISK", 4.45, [
    L2(icon_siren(120), 540, 320, 0.02, "pop", 0.32, shake=4),
    L2(textimg("QUYỀN PHÂN PHỐI KHÔNG THUỘC SHOP", 42, RED), 540, 450, 0.2, "slide"),
    L2(photo("phoneshop-3.jpg", 640, 300), 540, 660, 0.4, "blurin", 0.45),
    L2(capsule("THUẬT TOÁN THAY ĐỔI", 44, WHITE, RED, icon=warn_tri(40)), 540, 900, 0.65, "shakein", 0.32),
    L2(capsule("GIÁ THẦU TĂNG", 44, WHITE, RED, icon=warn_tri(40)), 540, 1020, 1.35, "shakein", 0.32),
    L2(capsule("VIDEO GIẢM PHÂN PHỐI", 44, WHITE, RED, icon=warn_tri(40)), 540, 1140, 2.1, "shakein", 0.32),
    L2(capsule("LIVE TỤT MẮT XEM", 44, WHITE, RED, icon=warn_tri(40)), 540, 1260, 2.85, "shakein", 0.32),
])

# 8. OUT: screenshot collage of external channels
fanpage = shot("facebook-fanpage-tabcom-2026-08-08.png", target_w=380)
zalo_oa = shot("zalo-oa-gioi-thieu-2026-08-08.png", target_w=380)
website = shot("website-tabcom-2026-08-08.png", target_h=430)
rr("S_OUT", 5.05, [
    L2(textimg("TRAFFIC NGOẠI SÀN", 70, NAVY), 540, 320, 0.05, "slide"),
    L2(bd_fb, 250, 490, 0.3, "pop", 0.32),
    L2(bd_zalo, 540, 490, 0.45, "pop", 0.32),
    L2(bd_tiktok, 830, 490, 0.6, "pop", 0.32),
    L2(fanpage, 300, 820, 0.9, "slideL", 0.45, dy=240),
    L2(zalo_oa, 780, 820, 1.3, "slideR", 0.45, dy=240),
    L2(capsule("FANPAGE · GROUP · ZALO · WEBSITE", 44, WHITE, TEAL, maxw=980), 540, 1130, 2.2, "flip", 0.4),
    L2(capsule("KOC · KHÁCH CŨ · KHÁCH GIỚI THIỆU", 44, WHITE, NAVY, maxw=980), 540, 1270, 3.3, "flip", 0.4),
])

# 10. OWN: zalo chat screenshot + loop
zalo_chat = shot("zalo-app-nhom-chat-google-play-2026-08-08.png", target_h=560)
strike = Image.new("RGBA", (720, 8), (0, 0, 0, 0))
ImageDraw.Draw(strike).rounded_rectangle((0, 0, 719, 7), 4, fill=RED)
rr("S_OWN", 6.50, [
    L2(textimg("ĐỔI LẠI, SHOP XÂY ĐƯỢC", 52, NAVY), 540, 330, 0.05, "slide"),
    MarkerLayer("TỆP KHÁCH CỦA RIÊNG MÌNH", 60, NAVY, (196, 250, 240, 255), 540, 470, 0.35, 0.6),
    L2(zalo_chat, 320, 880, 0.9, "slideL", 0.45, dy=260),
    L2(capsule("CHỦ ĐỘNG TIẾP CẬN LẠI", 44, WHITE, TEAL, maxw=520), 772, 720, 1.6, "slideR", 0.4, dy=200),
    L2(photo("chat-1.jpg", 460, 290), 772, 950, 2.4, "blurin", 0.45),
    L2(textimg("thay vì", 40, GRAY, font=F_BOLD), 772, 1130, 3.1, "slide"),
    L2(capsule("MUA TRAFFIC TỪ ĐẦU", 42, WHITE, RED, maxw=520), 772, 1240, 3.5, "slideR", 0.4, dy=200),
    L2(strike, 772, 1240, 5.1, "wipe", 0.5),
])

# 11. TEST: analytics screenshot + counter-less capsules
an_app = shot("shopee-seller-app-hieu-qua-ban-hang-google-play-2026-08-08.png", target_h=860)
rr("S_TEST", 8.70, [
    L2(capsule("BÀI TEST NHANH", 44, WHITE, RED), 540, 320, 0.05, "shakein", 0.36),
    L2(an_app, 400, 850, 0.35, "slideL", 0.45, dy=260),
    L2(photo("analytics-1.jpg", 420, 280), 806, 620, 1.1, "blurin", 0.45),
    L2(capsule("MỞ PHÂN TÍCH", 42, WHITE, NAVY, maxw=460), 806, 880, 1.7, "slideR", 0.4, dy=200),
    L2(capsule("30 NGÀY GẦN NHẤT", 42, WHITE, NAVY, maxw=460), 806, 1010, 3.6, "slideR", 0.4, dy=200),
    L2(capsule("ĐƠN ĐẾN TỪ ĐÂU?", 42, WHITE, TEAL, maxw=460), 806, 1140, 6.1, "shakein", 0.36),
    L2(textimg("Ảnh: Shopee Seller trên Google Play", 26, GRAY, font=F_BOLD), 540, 1420, 0.9, "slide", dy=30),
])

# 12. 50A
rr("S_50A", 4.65, [
    L2(textimg("PHẦN LỚN DOANH THU ĐẾN TỪ?", 50, NAVY), 540, 340, 0.05, "slide"),
    L2(photo("livestream-3.jpg", 800, 340), 540, 600, 0.25, "blurin", 0.45),
    L2(capsule("ADS", 54, WHITE, RED, icon=warn_tri(44)), 540, 880, 0.5, "slideL", 0.4, dy=220),
    L2(capsule("LIVE", 54, WHITE, RED, icon=warn_tri(44)), 540, 1020, 1.5, "slideR", 0.4, dy=220),
    L2(capsule("VÀI VIDEO VIRAL", 54, WHITE, RED, icon=warn_tri(44)), 540, 1160, 2.5, "slideL", 0.4, dy=220),
    L2(textimg("chỉ 1 chân trụ", 42, INK, font=F_BOLD), 540, 1300, 3.5, "slide"),
])

# 13. 50B: counting number
rr("S_50B", 3.60, [
    L2(textimg("NẾU NGÀY MAI CÙNG TỤT", 52, NAVY), 540, 430, 0.05, "slide"),
    CountLayer(50, 250, RED, 540, 720, 0.35, dur=1.1),
    L2(capsule("SHOP CÒN BAO NHIÊU ĐƠN?", 54, WHITE, NAVY, maxw=980), 540, 1000, 1.6, "shakein", 0.38),
    L2(photo("analytics-3.jpg", 700, 300), 540, 1280, 2.1, "blurin", 0.45),
])

# 14. DEP
rr("S_DEP", 3.40, [
    L2(icon_siren(140), 540, 400, 0.02, "pop", 0.34, shake=5),
    TypeLayer("GẦN NHƯ KHÔNG CÒN?", 56, NAVY, 540, 610, 0.3, cps=18),
    L2(capsule("PHỤ THUỘC TRAFFIC QUÁ NẶNG", 52, WHITE, RED, font=F_BLACK, maxw=980), 540, 790, 1.1, "shakein", 0.4),
    L2(photo("warehouse-3.jpg", 780, 380), 540, 1120, 1.6, "blurin", 0.5),
])

# 15. ORDER
def numbered(num, text, col, ph_name=None, folder=None):
    cap = capsule(text, 52, WHITE, col, maxw=520)
    ph = shot(ph_name, target_h=190) if folder == "shot" else (photo(ph_name, 300, 190) if ph_name else None)
    wtot = 120 + cap.width + (ph.width + 20 if ph else 0)
    h = max(cap.height, ph.height if ph else 0, 120)
    img = Image.new("RGBA", (wtot, h), (0, 0, 0, 0))
    f = ImageFont.truetype(F_BLACK, int(84 * 1.22))
    ImageDraw.Draw(img).text((4, (h - sum(f.getmetrics())) // 2), num, font=f, fill=(200, 205, 225, 255))
    img.alpha_composite(cap, (110, (h - cap.height) // 2))
    if ph:
        img.alpha_composite(ph, (110 + cap.width + 10, (h - ph.height) // 2))
    return img


rr("S_ORDER", 5.10, [
    L2(textimg("MUỐN BỀN PHẢI CÓ CẢ HAI", 54, NAVY), 540, 400, 0.05, "slide"),
    L2(numbered("1", "NỘI SÀN", TEAL, "phoneshop-3.jpg"), 540, 650, 0.5, "slideL", 0.42, dy=240),
    L2(numbered("2", "NGOẠI SÀN", NAVY, "social-1.jpg"), 540, 850, 1.3, "slideR", 0.42, dy=240),
    L2(capsule("SHOP MỚI: LO NỘI SÀN TRƯỚC", 50, WHITE, RED, font=F_BLACK, maxw=980), 540, 1090, 2.6, "shakein", 0.4),
    L2(photo("packing-1.jpg", 760, 320), 540, 1350, 3.4, "blurin", 0.5),
])

# 16. CHK1: product page screenshot
sh_home = shot("shopee-seller-app-kenh-marketing-google-play-2026-08-08.png", target_h=620)
rr("S_CHK1", 5.55, [
    L2(capsule("BƯỚC 1 · NỘI SÀN", 42, WHITE, TEAL), 540, 320, 0.05, "pop"),
    MarkerLayer("CHUẨN HÓA TRANG SẢN PHẨM", 54, NAVY, (196, 250, 240, 255), 540, 460, 0.3, 0.6),
    L2(sh_home, 320, 850, 0.7, "slideL", 0.45, dy=260),
    L2(capsule("TIÊU ĐỀ ĐÚNG THỨ KHÁCH TÌM", 40, WHITE, NAVY, icon=checkbox(40), maxw=490), 778, 780, 2.1, "slideR", 0.4, dy=200),
    L2(capsule("HÌNH ẢNH ĐÚNG NHU CẦU", 40, WHITE, NAVY, icon=checkbox(40), maxw=490), 778, 930, 3.6, "slideR", 0.4, dy=200),
])

# 17. CHK2: warehouse photo
rr("S_CHK2", 6.25, [
    L2(capsule("BƯỚC 1 · NỘI SÀN", 42, WHITE, TEAL), 540, 300, 0.03, "pop"),
    L2(photo("warehouse-2.jpg", 860, 400), 540, 580, 0.25, "blurin", 0.5),
    L2(capsule("ĐỦ REVIEW & BẰNG CHỨNG MUA HÀNG", 40, WHITE, NAVY, icon=checkbox(42), maxw=990), 540, 900, 0.5, "slideL", 0.4, dy=220),
    L2(capsule("TỐI ƯU GIÁ", 44, WHITE, NAVY, icon=checkbox(42), maxw=980), 540, 1040, 2.1, "slideR", 0.4, dy=220),
    L2(capsule("TỒN KHO · VẬN HÀNH · CSKH", 42, WHITE, NAVY, icon=checkbox(42), maxw=990), 540, 1180, 3.4, "slideL", 0.4, dy=220),
    L2(capsule("ỔN ĐỊNH", 48, WHITE, TEAL), 540, 1330, 5.0, "shakein", 0.36),
])

# 18. EXP: tiktok academy + fanpage screenshots
tt_aca = shot("tiktok-shop-academy-vn-2026-08-08.png", target_h=520)
rr("S_EXP", 4.40, [
    L2(capsule("BƯỚC 2 · NGOẠI SÀN", 42, WHITE, NAVY), 540, 300, 0.05, "pop"),
    L2(textimg("CHỐT ĐƯỢC ĐƠN RỒI MỚI MỞ RỘNG", 44, NAVY), 540, 430, 0.25, "slide"),
    L2(tt_aca, 330, 800, 0.6, "slideL", 0.45, dy=260),
    L2(bd_tiktok, 760, 600, 0.9, "pop", 0.32),
    L2(bd_fb, 906, 600, 1.05, "pop", 0.32),
    L2(capsule("TIKTOK · FACEBOOK", 42, WHITE, TEAL, maxw=430), 800, 800, 1.5, "slideR", 0.4, dy=200),
    L2(capsule("GROUP · SEO CONTENT", 42, WHITE, TEAL, maxw=430), 800, 940, 2.6, "slideR", 0.4, dy=200),
])

# 19. KEEP
rr("S_KEEP", 6.20, [
    L2(textimg("VÀ GIỮ KHÁCH LẠI", 56, NAVY), 540, 340, 0.05, "slide"),
    L2(photo("social-3.jpg", 840, 380), 540, 610, 0.25, "blurin", 0.5),
    L2(capsule("KÉO KHÁCH MỚI", 46, WHITE, TEAL, icon=checkbox(42)), 540, 900, 0.45, "slideL", 0.4, dy=220),
    L2(capsule("LƯU DATA KHÁCH CŨ", 46, WHITE, TEAL, icon=checkbox(42)), 540, 1040, 1.9, "slideR", 0.4, dy=220),
    L2(capsule("CƠ CHẾ QUAY LẠI MUA TIẾP", 44, WHITE, TEAL, icon=checkbox(42), maxw=980), 540, 1180, 3.3, "slideL", 0.4, dy=220),
    L2(capsule("KHÁCH GIỚI THIỆU KHÁCH", 44, WHITE, NAVY, maxw=980), 540, 1320, 4.9, "shakein", 0.36),
])

# 20. CTA
rr("S_CTA", 3.30, [
    L2(icon_chat(130), 540, 400, 0.03, "pop", 0.36),
    TypeLayer("COMMENT CHO TABCOM", 56, NAVY, 540, 600, 0.25, cps=20),
    L2(capsule("NGUỒN NÀO ĐANG KÉO ĐƠN CHÍNH?", 42, WHITE, TEAL, maxw=990), 540, 780, 1.0, "flip", 0.4),
    L2(photo("chat-1.jpg", 700, 340), 540, 1090, 1.5, "blurin", 0.5),
])

# 21. SAVE
rr("S_SAVE", 3.00, [
    L2(icon_bookmark(130), 540, 400, 0.03, "pop", 0.36),
    L2(capsule("LƯU VIDEO NÀY LẠI", 66, WHITE, NAVY, font=F_BLACK), 540, 620, 0.28, "shakein", 0.4),
    L2(textimg("để biết mình đang lệ thuộc ở đâu", 40, INK, font=F_BOLD), 540, 790, 0.75, "slide"),
    L2(photo("phoneshop-1.jpg", 720, 360), 540, 1080, 1.1, "blurin", 0.5),
])

# 9. P_COLD split - người nhỏ góc trái dưới, chừa trống nửa trên
bg = NEN.copy()
fa = shot("facebook-group-tabcom-2026-08-08.png", target_h=360)
bg.alpha_composite(rounded_card(790, 690), (15, 1226))
rr("P_COLD", 3.60, [
    L2(capsule("NGOẠI SÀN", 44, WHITE, NAVY), 250, 330, 0.03, "slideL", 0.4, dy=200),
    L2(capsule("KHÁCH LẠNH HƠN · PHẢI NUÔI ĐỀU", 44, WHITE, TEAL, maxw=900), 540, 880, 0.5, "flip", 0.42),
    L2(fa, 890, 1300, 1.1, "slideR", 0.42, dy=220),
    L2(photo("phoneshop-3.jpg", 300, 200), 890, 1620, 1.9, "blurin", 0.45),
], bg=bg)

# labels NỘI SÀN / NGOẠI SÀN cho các đoạn người nói full hình
for nm, txt, col in [("lbl-noisan", "NỘI SÀN", TEAL), ("lbl-ngoaisan", "NGOẠI SÀN", NAVY)]:
    capsule(txt, 52, WHITE, col).save(os.path.join(here, "stick", f"{nm}.png"))
print("labels saved", flush=True)

print("ALL V3 SCENES DONE", flush=True)
