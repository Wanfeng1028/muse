# -*- coding: utf-8 -*-
"""V3 layouts: new archetypes (full-width photo, 2x2 grid, side column, circle, strip)."""
import math
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

here = os.path.dirname(os.path.abspath(__file__))
s1 = open(os.path.join(here, "scenes.py"), encoding="utf-8").read()
exec(compile(s1[:s1.find("# badges")], "h1", "exec"), globals())
PH = os.path.join(here, "photos")
OUT = os.path.join(here, "clips")
s2 = open(os.path.join(here, "scenes2.py"), encoding="utf-8").read()
exec(compile(s2[s2.find("# ---------------- photo helpers"):s2.find("FORCE = True")], "h2", "exec"), globals())
exec(compile(s2[s2.find("def flat_photo("):s2.find("def block_photo(")], "h3", "exec"), globals())


def rr(name, dur, layers, bg=None):
    p = os.path.join(OUT, f"{name}.mp4")
    if os.path.exists(p):
        os.remove(p)
    render(name, dur, layers, bg=bg)


# ============ archetype A: ảnh phủ khổ, chữ đè trên nền mờ ============
def bg_photo(name, top=210, bot=1790, scrim_top=0.82, scrim_bot=0.0, folder=None):
    canvas = NEN.copy()
    h = bot - top
    p = os.path.join(folder or PH, name)
    im = Image.open(p).convert("RGB")
    r = max(W / im.width, h / im.height)
    im = im.resize((int(im.width * r), int(im.height * r)))
    x0 = (im.width - W) // 2
    y0 = int((im.height - h) * 0.4)
    im = im.crop((x0, y0, x0 + W, y0 + h)).convert("RGBA")
    # scrim gradient: sáng ở trên để chữ navy đọc được
    g = Image.new("L", (1, h))
    for y in range(h):
        f = y / max(1, h - 1)
        v = int(255 * (scrim_top * (1 - f) ** 1.4 + scrim_bot * f ** 1.4))
        g.putpixel((0, y), v)
    scrim = Image.new("RGBA", (W, h), (250, 250, 248, 255))
    scrim.putalpha(g.resize((W, h)))
    im.alpha_composite(scrim)
    mask = Image.new("L", (W, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, h - 1), 0, fill=255)
    canvas.paste(im, (0, top), mask)
    return canvas


# ============ archetype B: lưới 2x2 ảnh có nhãn ============
def tile(img, label, w=470, h=330, col=NAVY, is_shot=False):
    inner = (shot(img, target_w=w - 24) if is_shot else None)
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 26, fill=WHITE, outline=(226, 229, 240, 255), width=2)
    if True:
        src_im = Image.open(os.path.join(AST, img)).convert("RGB")
        r = (w - 24) / src_im.width
        src_im = src_im.resize((w - 24, int(src_im.height * r)))
        src_im = src_im.crop((0, 0, w - 24, min(h - 96, src_im.height)))
        m = Image.new("L", src_im.size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, src_im.width - 1, src_im.height - 1), 18, fill=255)
        card.paste(src_im, (12, 12), m)
    f = fit_font(F_XBOLD, int(38 * 1.22), label, w - 40)
    d.text(((w - text_w(f, label)) // 2, h - 74), label, font=f, fill=col)
    return shadowed(card, blur=12, alpha=62, off=(0, 8))


# ============ archetype F: ảnh tròn ============
def circle_photo(name, d_px=460, ring=10, ring_col=TEAL):
    im = Image.open(os.path.join(PH, name)).convert("RGB")
    r = max(d_px / im.width, d_px / im.height)
    im = im.resize((int(im.width * r), int(im.height * r)))
    x0 = (im.width - d_px) // 2
    y0 = int((im.height - d_px) * 0.35)
    im = im.crop((x0, y0, x0 + d_px, y0 + d_px)).convert("RGBA")
    mask = Image.new("L", (d_px, d_px), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d_px - 1, d_px - 1), fill=255)
    out = Image.new("RGBA", (d_px + 2 * ring, d_px + 2 * ring), (0, 0, 0, 0))
    ImageDraw.Draw(out).ellipse((0, 0, out.width - 1, out.height - 1), fill=ring_col)
    out.paste(im, (ring, ring), mask)
    return shadowed(out, blur=14, alpha=70, off=(0, 10))


# ============ archetype E: dải 3 ảnh ngang ============
def strip3(names, w=310, h=230):
    out = Image.new("RGBA", (w * 3 + 40, h), (0, 0, 0, 0))
    for i, n in enumerate(names):
        out.alpha_composite(flat_photo(n, w, h, radius=20), (i * (w + 20), 0))
    return shadowed(out, blur=12, alpha=60, off=(0, 8))


bd_tiktok = badge(os.path.join(LOGO, "logo-tiktok-icon.png"), 130, 0.72)
bd_fb = badge(os.path.join(LOGO, "logo-facebook-icon.png"), 130, 0.74)
bd_zalo = badge(os.path.join(LOGO, "logo-zalo-icon.png"), 130, 0.78)

# ---------- P_COLD: cân giữa, gọn ----------
bg = NEN.copy()
bg.alpha_composite(rounded_card(800, 690), (140, 1226))
fa = shot("facebook-group-tabcom-2026-08-08.png", target_h=400)
rr("P_COLD", 3.60, [
    L2(capsule("NGOẠI SÀN", 42, WHITE, NAVY), 210, 300, 0.03, "slideL", 0.4, dy=200),
    L2(fa, 540, 700, 0.25, "blurin", 0.45),
    L2(capsule("KHÁCH LẠNH HƠN · PHẢI NUÔI ĐỀU", 44, WHITE, TEAL, maxw=920), 540, 990, 0.9, "flip", 0.42),
], bg=bg)

# ---------- S_PRO: ảnh phủ khổ + chữ đè (archetype A) ----------
rr("S_PRO", 4.45, [
    L2(capsule("ƯU ĐIỂM NỘI SÀN", 42, WHITE, TEAL), 540, 330, 0.05, "pop"),
    MarkerLayer("KHÁCH Ở RẤT GẦN", 62, NAVY, (255, 255, 255, 235), 540, 520, 0.35, 0.55),
    MarkerLayer("HÀNH VI MUA", 62, NAVY, (255, 255, 255, 235), 540, 640, 0.6, 0.55),
    L2(capsule("TRANG BÁN TỐT = CHỐT NHANH", 48, WHITE, NAVY, maxw=980), 540, 1620, 2.1, "flip", 0.4),
], bg=bg_photo("phoneshop-2.jpg", scrim_top=0.86, scrim_bot=0.18))

# ---------- S_DEP: ảnh phủ khổ, tông cảnh báo ----------
rr("S_DEP", 3.40, [
    L2(icon_siren(140), 540, 380, 0.02, "pop", 0.34, shake=5),
    TypeLayer("GẦN NHƯ KHÔNG CÒN?", 56, NAVY, 540, 570, 0.3, cps=18),
    L2(capsule("PHỤ THUỘC TRAFFIC QUÁ NẶNG", 52, WHITE, RED, font=F_BLACK, maxw=980), 540, 1600, 1.1, "shakein", 0.4),
], bg=bg_photo("warehouse-3.jpg", scrim_top=0.88, scrim_bot=0.22))

# ---------- S_OUT: lưới 2x2 (archetype B) ----------
rr("S_OUT", 5.05, [
    L2(textimg("TRAFFIC NGOẠI SÀN", 66, NAVY), 540, 300, 0.05, "slide"),
    L2(tile("facebook-fanpage-tabcom-2026-08-08.png", "FANPAGE", is_shot=False), 290, 640, 0.35, "flip", 0.4),
    L2(tile("zalo-oa-gioi-thieu-2026-08-08.png", "ZALO OA", is_shot=False), 790, 640, 0.6, "flip", 0.4),
    L2(tile("website-tabcom-2026-08-08.png", "WEBSITE", is_shot=False), 290, 1010, 0.85, "flip", 0.4),
    L2(tile("tiktok-shop-academy-vn-2026-08-08.png", "TIKTOK", is_shot=False), 790, 1010, 1.1, "flip", 0.4),
    L2(capsule("KOC · KHÁCH CŨ · KHÁCH GIỚI THIỆU", 44, WHITE, NAVY, maxw=980), 540, 1330, 3.3, "slide"),
])

# ---------- S_KEEP: cột ảnh trái + checklist phải (archetype C) ----------
col = Image.new("RGBA", (430, 900), (0, 0, 0, 0))
for i, n in enumerate(["social-3.jpg", "chat-1.jpg", "packing-3.jpg"]):
    col.alpha_composite(flat_photo(n, 430, 285, radius=22), (0, i * 308))
col = shadowed(col, blur=12, alpha=60, off=(0, 8))
rr("S_KEEP", 6.20, [
    L2(textimg("VÀ GIỮ KHÁCH LẠI", 54, NAVY), 540, 320, 0.05, "slide"),
    L2(col, 300, 950, 0.3, "slideL", 0.5, dy=280),
    L2(capsule("KÉO KHÁCH MỚI", 40, WHITE, TEAL, icon=checkbox(38), maxw=440), 800, 700, 0.45, "slideR", 0.4, dy=200),
    L2(capsule("LƯU DATA KHÁCH CŨ", 40, WHITE, TEAL, icon=checkbox(38), maxw=440), 800, 850, 1.9, "slideR", 0.4, dy=200),
    L2(capsule("CƠ CHẾ QUAY LẠI", 40, WHITE, TEAL, icon=checkbox(38), maxw=440), 800, 1000, 3.3, "slideR", 0.4, dy=200),
    L2(capsule("KHÁCH GIỚI THIỆU KHÁCH", 38, WHITE, NAVY, maxw=440), 800, 1150, 4.9, "shakein", 0.36),
])

# ---------- S_CHK2: ảnh phủ nửa trên + panel trắng dưới (archetype D) ----------
panel = Image.new("RGBA", (980, 560), (0, 0, 0, 0))
ImageDraw.Draw(panel).rounded_rectangle((0, 0, 979, 559), 36, fill=(255, 255, 255, 242))
panel = shadowed(panel, blur=16, alpha=55, off=(0, 10))
rr("S_CHK2", 6.25, [
    L2(capsule("BƯỚC 1 · NỘI SÀN", 42, WHITE, TEAL), 540, 300, 0.03, "pop"),
    L2(panel, 540, 1180, 0.2, "slide", 0.45, dy=90),
    L2(capsule("ĐỦ REVIEW & BẰNG CHỨNG", 42, WHITE, NAVY, icon=checkbox(40), maxw=900), 540, 1000, 0.5, "slideL", 0.4, dy=220),
    L2(capsule("TỐI ƯU GIÁ", 44, WHITE, NAVY, icon=checkbox(40), maxw=900), 540, 1140, 2.1, "slideR", 0.4, dy=220),
    L2(capsule("TỒN KHO · VẬN HÀNH · CSKH", 42, WHITE, NAVY, icon=checkbox(40), maxw=900), 540, 1280, 3.4, "slideL", 0.4, dy=220),
    L2(capsule("ỔN ĐỊNH", 46, WHITE, TEAL), 540, 1430, 5.0, "shakein", 0.36),
], bg=bg_photo("warehouse-2.jpg", top=210, bot=1150, scrim_top=0.55, scrim_bot=0.55))

# ---------- S_50A: dải 3 ảnh ngang (archetype E) ----------
rr("S_50A", 4.65, [
    L2(textimg("PHẦN LỚN DOANH THU ĐẾN TỪ?", 50, NAVY), 540, 330, 0.05, "slide"),
    L2(strip3(["livestream-3.jpg", "analytics-1.jpg", "social-1.jpg"]), 540, 600, 0.25, "blurin", 0.5),
    L2(capsule("ADS", 52, WHITE, RED, icon=warn_tri(42)), 540, 880, 0.5, "slideL", 0.4, dy=220),
    L2(capsule("LIVE", 52, WHITE, RED, icon=warn_tri(42)), 540, 1010, 1.5, "slideR", 0.4, dy=220),
    L2(capsule("VÀI VIDEO VIRAL", 52, WHITE, RED, icon=warn_tri(42)), 540, 1140, 2.5, "slideL", 0.4, dy=220),
    L2(textimg("chỉ 1 chân trụ", 42, INK, font=F_BOLD), 540, 1290, 3.5, "slide"),
])

# ---------- S_SAVE: ảnh tròn (archetype F) ----------
rr("S_SAVE", 3.00, [
    L2(circle_photo("phoneshop-1.jpg", 440), 540, 620, 0.05, "pop", 0.42),
    L2(icon_bookmark(120), 540, 960, 0.3, "pop", 0.34),
    L2(capsule("LƯU VIDEO NÀY LẠI", 62, WHITE, NAVY, font=F_BLACK), 540, 1140, 0.55, "shakein", 0.4),
    L2(textimg("để biết mình đang lệ thuộc ở đâu", 38, INK, font=F_BOLD), 540, 1290, 1.0, "slide"),
])

# ---------- S_CTA: ảnh tròn + icon ----------
rr("S_CTA", 3.30, [
    L2(circle_photo("chat-1.jpg", 420, ring_col=NAVY), 540, 620, 0.03, "pop", 0.42),
    TypeLayer("COMMENT CHO TABCOM", 54, NAVY, 540, 960, 0.3, cps=20),
    L2(capsule("NGUỒN NÀO ĐANG KÉO ĐƠN CHÍNH?", 42, WHITE, TEAL, maxw=980), 540, 1130, 1.0, "flip", 0.4),
    L2(bd_fb, 380, 1330, 1.5, "pop", 0.32),
    L2(bd_tiktok, 540, 1330, 1.62, "pop", 0.32),
    L2(bd_zalo, 700, 1330, 1.74, "pop", 0.32),
])

print("V3 LAYOUTS DONE", flush=True)
