"""Shot 14a, second design (2026-09-27, after user feedback: 发牌 "怪怪的", "切的太硬", "绿色的台 + 放大人脸很丑"):
style quick-swipes on the live frame + 2x2 style grid + pick.

The presenter stays at their original framing (scale 1, never enlarged). No table, no mat.
  拼接 / 胶片 / 杂志 / 发布会   the whole frame (with the presenter) switches to that style through a horizontal swipe with
                               motion blur and a soft light on the boundary (like swiping camera filters), 7 frames,
                               centred on the word; the style name eases in, in the style's own type
  等等                          two short flashes (paper hand-drawn, floating-card explainer), 4-frame swipes, back to
                               the untouched frame
  你可以从里面…                  the frame shrinks into the top-left cell of a 2x2 grid (turning into the collage
                               style), the other three styles slide in from the edges; every cell is the presenter's live frame
  挑一个                        yellow ring on the collage cell, green check, the cell pushes out to full screen
  (before the source jump cut)  swipe back to the untouched frame; 14b (the brush) follows

Face and skin stay as shot in every style (no black-and-white, no darkening). Style decorations stay outside the
face box + 12 px.
"""
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

from a2common import *  # noqa
import a2time as AT

ASSETS = Path(__file__).resolve().parent / 'assets'
if not ASSETS.exists():
    ASSETS = a2paths.SHOTS / 's14/src/assets'
SERIF = ASSETS / 'fonts/SourceHanSerifCN-Heavy.otf'
_serif = {}


def serif(size):
    if size not in _serif:
        _serif[size] = ImageFont.truetype(str(SERIF), size)
    return _serif[size]


W_ = AT.word_on
T = dict(
    start=2403 / FPS,
    huamian=W_('画面风格', 81.08),
    pin=AT.kw('14', '拼接', 85.54), jiao=AT.kw('14', '胶片', 86.49), za=AT.kw('14', '杂志', 87.50), fa=AT.kw('14', '发布会', 88.33),
    deng=W_('等等', 89.34), ke=W_('可以', 89.94),
    tiao=AT.kw('14', '挑一个', 90.95), yi=W_('一个', 91.24), ge=W_('个你', 91.43),
)
SEG_CUT = 2784
SWIPE = 7
FLASH_SWIPE = 4


def kf(t):
    return int(round(t * FPS))


def cover(im, w, h):
    sc = max(w / im.width, h / im.height)
    r = im.resize((int(im.width * sc + 0.5), int(im.height * sc + 0.5)), Image.LANCZOS)
    x0, y0 = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x0, y0, x0 + w, y0 + h))


# swipe schedule: (start frame, n frames, from style, to style); the swipe is centred on the word frame
SWIPES = [
    (kf(T['pin']) - 3, SWIPE, 'raw', 'collage'),
    (kf(T['jiao']) - 3, SWIPE, 'collage', 'film'),
    (kf(T['za']) - 3, SWIPE, 'film', 'magazine'),
    (kf(T['fa']) - 3, SWIPE, 'magazine', 'launch'),
    (kf(T['deng']) - 2, FLASH_SWIPE, 'launch', 'paper'),
    (kf(T['deng']) + 5, FLASH_SWIPE, 'paper', 'explainer'),
    (kf(T['deng']) + 12, 6, 'explainer', 'raw'),
]
NAME_T0 = {'collage': T['pin'], 'film': T['jiao'], 'magazine': T['za'], 'launch': T['fa']}
GRID_IN = (kf(T['ke']), 13)                           # shrink into the grid
PICK_RING = kf(T['tiao'])
PICK_CHECK = kf(T['yi'])
ZOOM = (kf(T['ge']), 14)                              # collage cell pushes to full screen
BACK = (SEG_CUT - 9, 7)                               # swipe back to the untouched frame before the jump cut
CELLS = [(24, 296, 504, 419), (552, 296, 504, 419), (24, 803, 504, 419), (552, 803, 504, 419)]
CELL_STYLE = ['collage', 'film', 'magazine', 'launch']
CELL_NAME = ['拼贴', '胶片', '杂志', '发布会']
CELL_SRC = (0.0, 330.0, 1080.0, 897.5)               # source window (x, y, w, h) shown in a cell: head + upper body


def style_at(k):
    """(style before, style after, swipe progress 0..1 or None) for frame k in the quick-swipe part"""
    cur = 'raw'
    for s0, n, a, b in SWIPES:
        if k < s0:
            return cur, None, None
        if k < s0 + n:
            return a, b, (k - s0 + 1) / (n + 1)
        cur = b
    return cur, None, None


# ------------------------------------------------------------------ small drawing helpers
def dilate(a, px):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))
    return cv2.dilate(a, k)


def text_img(txt, f, fill, stroke=0, stroke_fill=None, pad=8, tracking=0):
    if tracking:
        w = sum(f.getlength(c) for c in txt) + tracking * (len(txt) - 1)
    else:
        w = f.getlength(txt)
    asc, desc = f.getmetrics()
    im = Image.new('RGBA', (int(w + 2 * pad + 2 * stroke), int(asc + desc + 2 * pad + 2 * stroke)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = pad + stroke
    if tracking:
        for c in txt:
            d.text((x, pad + stroke), c, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
            x += f.getlength(c) + tracking
    else:
        d.text((x, pad + stroke), txt, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    return im


def glow_img(im, color, radius=14, strength=1.0):
    a = np.asarray(im.split()[3], np.float32) / 255
    pad = radius * 3
    big = np.pad(a, pad)
    g = cv2.GaussianBlur(big, (0, 0), radius) * strength
    out = np.zeros(big.shape + (4,), np.float32)
    out[..., :3] = np.array(color, np.float32) / 255
    out[..., 3] = np.clip(g, 0, 1)
    base = Image.fromarray((out * 255).astype(np.uint8), 'RGBA')
    base.alpha_composite(im, (pad, pad))
    return base


def halo_img(im, color=(10, 12, 20), radius=18, strength=0.55):
    """soft dark halo behind a light title (legible on the light sweater); returned image is larger by 3*radius"""
    a = np.asarray(im.split()[3], np.float32) / 255
    pad = radius * 3
    big = np.pad(a, pad)
    g = np.clip(cv2.GaussianBlur(cv2.dilate(big, np.ones((9, 9), np.uint8)), (0, 0), radius) * strength * 1.6, 0, strength)
    out = np.zeros(big.shape + (4,), np.float32)
    out[..., :3] = np.array(color, np.float32) / 255
    out[..., 3] = g
    base = Image.fromarray((out * 255).astype(np.uint8), 'RGBA')
    base.alpha_composite(im, (pad, pad))
    return base


def eased_name(canvas, img, cx, cy, t, t0, dur=0.32, rise=26):
    """style name eases in: scale 0.72 -> 1.05 -> 1, alpha 0 -> 1, small upward drift"""
    if t < t0:
        return None
    s = pop(t, t0, dur, 0.06)
    s = 0.72 + 0.28 * s if s < 1 else s
    al = e_out(prog(t, t0, t0 + dur * 0.6), 2)
    dy = rise * (1 - e_out(prog(t, t0, t0 + dur), 3))
    rgb, a = affine_elem(img, scale=s, cx=cx, cy=cy + dy, alpha=al)
    over_pm(canvas, rgb, a)
    return elem_bbox(a)


# ------------------------------------------------------------------ the styles (full frame, the presenter at scale 1)
class Styles:
    def __init__(self):
        self.host = Host(WORK / 'plate14.png')
        # collage (2026-09-27 user feedback: richer): dotted journal page; behind the presenter: torn kraft / halftone pink / graph paper,
        # polaroids of real vlog-demo frames; in front: tapes, stickers, handwritten notes, date stamp. Everything that is
        # in front of the presenter stays outside their face box + 12 px (x <= 171 or x >= 892 between y 533 and 1265).
        self.collage_bg = to_f(paper(tone=(243, 236, 222), dots=38, seed=141, grain=4, blotch=6))
        back = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        front = Image.new('RGBA', (W, H), (0, 0, 0, 0))

        def torn(w, h, tone, seed, dots=0):
            pz = paper(w, h, tone=tone, seed=seed, grain=5, blotch=8, dots=dots)
            m1 = torn_edge_mask(w, h, amp=6, seed=seed, sides='lr')
            m2 = torn_edge_mask(h, w, amp=6, seed=seed + 1, sides='lr').rotate(90, expand=True)
            pz.putalpha(ImageChops.multiply(m1, m2))
            return pz

        def put(layer, im, x, y, rot=0, shadow=True):
            im = rotate(im, rot)
            if shadow:
                sh, pad = shadow_of(im, blur=9, alpha=0.28)
                layer.alpha_composite(sh, (int(x - pad + 4), int(y - pad + 7)))
            layer.alpha_composite(im, (int(x), int(y)))

        kraft = torn(540, 470, (212, 186, 146), 151)
        put(back, kraft, 610, 250, 6)
        pink = torn(400, 560, (246, 196, 204), 152)
        hd = ImageDraw.Draw(pink)
        for yy in range(12, 560, 18):
            for xx in range(12, 400, 18):
                r = 2.0 + 3.5 * (xx / 400)
                hd.ellipse((xx - r, yy - r, xx + r, yy + r), fill=(226, 150, 166, 255))
        pink.putalpha(ImageChops.multiply(pink.split()[3], torn_edge_mask(400, 560, amp=6, seed=160, sides='lr')))
        put(back, pink, -70, 560, -7)
        grid = torn(480, 440, (250, 251, 252), 153)
        gd = ImageDraw.Draw(grid)
        for g in range(0, 480, 24):
            gd.line((g, 0, g, 440), fill=(150, 185, 225, 255), width=1)
        for g in range(0, 440, 24):
            gd.line((0, g, 480, g), fill=(150, 185, 225, 255), width=1)
        grid.putalpha(ImageChops.multiply(grid.split()[3], torn_edge_mask(480, 440, amp=6, seed=161, sides='lr')))
        put(back, grid, 690, 1060, 5)

        def polaroid(img, w, h, cap=''):
            ph = cover(img, w - 24, h - 70)
            pol = Image.new('RGBA', (w, h), (252, 250, 244, 255))
            pol.paste(ph, (12, 12))
            if cap:
                ImageDraw.Draw(pol).text((w / 2, h - 30), cap, font=font('Kai', 24), fill=(70, 60, 50), anchor='mm')
            return pol

        demo = DEMOS / 'vlog/vlog_demo.mp4'
        v_sun = Image.fromarray(grab(demo, int(19.4 * 30))).convert('RGBA')
        v_drink = Image.fromarray(grab(demo, int(9.6 * 30))).convert('RGBA')
        v_lamp = Image.fromarray(grab(demo, int(24.0 * 30))).convert('RGBA')
        put(back, polaroid(v_sun, 176, 212, '晚霞'), 24, 306, -7)
        put(back, polaroid(v_drink, 150, 188, '冰冰凉'), 910, 622, 7)
        put(back, polaroid(v_lamp, 142, 172), 18, 990, -5)
        put(front, rotate(tape(110, 32, color=(250, 222, 120), seed=71), -12), 62, 296, 0, False)
        put(front, rotate(tape(100, 30, color=(245, 170, 190), seed=72, stripes=True), 10), 934, 608, 0, False)
        put(front, rotate(tape(100, 30, color=(170, 205, 245), seed=73), -20), 40, 978, 0, False)
        dc = Image.new('RGBA', (240, 114), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dc)
        dd.rounded_rectangle((0, 0, 239, 113), radius=8, fill=(252, 247, 236, 255))
        dd.rounded_rectangle((10, 10, 229, 103), radius=6, outline=(196, 60, 50, 255), width=4)
        dd.text((120, 48), '09.26', font=font('Heavy', 52), fill=(196, 60, 50), anchor='mm')
        dd.text((120, 86), 'SATURDAY', font=font('Bold', 20), fill=(196, 60, 50), anchor='mm')
        put(front, dc, 800, 300, 8)
        put(front, rotate(icon_heart(76), -12), 978, 470, 0)
        put(front, rotate(icon_star(64), 14), 96, 880, 0)
        sm = Image.new('RGBA', (70, 70), (0, 0, 0, 0))
        sdr = ImageDraw.Draw(sm)
        sdr.ellipse((3, 3, 66, 66), fill=(255, 214, 10), outline=INK, width=4)
        sdr.ellipse((22, 24, 29, 33), fill=INK)
        sdr.ellipse((41, 24, 48, 33), fill=INK)
        sdr.arc((18, 26, 52, 54), 20, 160, fill=INK, width=4)
        put(front, sm, 962, 930, -8)
        fk = font('Kai', 30)
        ImageDraw.Draw(front).text((34, 560), '周六 · 晴', font=fk, fill=(70, 58, 48))
        ImageDraw.Draw(front).text((904, 846), '今天也要', font=font('Kai', 26), fill=(70, 58, 48))
        ImageDraw.Draw(front).text((904, 878), '好好生活~', font=font('Kai', 26), fill=(70, 58, 48))
        ad = ImageDraw.Draw(front)
        ad.text((30, 1190), '本人', font=font('Kai', 32), fill=(196, 60, 50))
        ad.line([(96, 1210), (120, 1195), (150, 1178)], fill=(196, 60, 50), width=4, joint='curve')
        ad.line([(150, 1178), (134, 1176)], fill=(196, 60, 50), width=4)
        ad.line([(150, 1178), (143, 1192)], fill=(196, 60, 50), width=4)
        self.collage_back = back
        self.collage_front = front
        self.collage_deco = []
        self.collage_boxes = {'polaroid_sun': [16, 296, 212, 528], 'polaroid_drink': [902, 610, 1072, 832], 'photo_lamp': [8, 980, 170, 1170],
                              'date_stamp': [796, 290, 1052, 432], 'heart': [972, 462, 1062, 548], 'star': [90, 874, 168, 952],
                              'smiley': [956, 924, 1040, 1008], 'note_day': [34, 560, 170, 596], 'note_life': [904, 846, 1040, 912],
                              'note_me': [30, 1176, 156, 1232]}
        self.collage_name = self._ransom('拼贴', 128)
        # film
        self.film_edges = self._film_edges()
        self.film_name = halo_img(glow_img(text_img('胶片', font('Kai', 150), (255, 250, 240)), (255, 214, 160), radius=10, strength=0.8),
                                  color=(40, 24, 10), radius=22, strength=0.5)
        self.film_head = text_img('FILM DIARY  ·  No.07', font('Medium', 26), (255, 246, 232, 190), tracking=4)
        self.film_date = glow_img(text_img("'26  9  26", font('Bold', 44), (255, 150, 60), tracking=2), (255, 120, 40), radius=6, strength=0.8)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        leak = np.exp(-(((xx - 1000) / 320) ** 2 + ((yy - 260) / 460) ** 2)) * 0.78
        leak += np.exp(-(((xx - 1080) / 160) ** 2 + ((yy - 900) / 700) ** 2)) * 0.30
        self.leak = cv2.GaussianBlur(leak, (0, 0), 20)[..., None] * np.array([1.0, 0.45, 0.16], np.float32)
        # magazine: a cover (2026-09-27 coordinator: must read as a magazine cover at a glance, not a second beige page):
        # warm red cover stock, a huge serif masthead behind the presenter (layered with their matte), cover lines on both sides
        # outside his face box, issue number + barcode in the corner. Neutral words only (no brand / creator names).
        mg = paper(tone=(214, 66, 44), seed=143, grain=6, blotch=9)
        d = ImageDraw.Draw(mg)
        head = 'STYLE'
        fh = serif(318)
        tw = fh.getlength(head)
        x = (W - tw) / 2
        d.text((x, 262), head, font=fh, fill=(251, 246, 236))
        d.text((W - 60, 292), 'VOL. 03', font=font('Bold', 22), fill=(251, 236, 220), anchor='ra')
        d.text((60, 292), '2026 · 09', font=font('Bold', 22), fill=(251, 236, 220))
        cream, ink2 = (251, 246, 236), (40, 18, 12)
        for (lx, ly, txt, f, col) in [(40, 668, '封面故事', font('Heavy', 26), (255, 214, 10)),
                                      (40, 708, '不会剪辑', serif(32), cream), (40, 748, '也能出片', serif(32), cream),
                                      (40, 812, '四步走完', font('Medium', 22), (251, 226, 214)), (40, 842, '一条视频', font('Medium', 22), (251, 226, 214)),
                                      (904, 700, '本期特辑', font('Heavy', 26), (255, 214, 10)),
                                      (904, 740, '四种风格', serif(32), cream), (904, 780, '任你挑选', serif(32), cream),
                                      (904, 844, '拼贴 胶片', font('Medium', 22), (251, 226, 214)), (904, 874, '杂志 发布会', font('Medium', 22), (251, 226, 214))]:
            d.text((lx, ly), txt, font=f, fill=col)
        grid = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grid)
        for gx in range(60, W - 59, 80):                      # 12-column type-area grid + baseline rules
            gd.line((gx, 290, gx, H - 60), fill=(255, 232, 220, 34), width=1)
        for gy in range(290, H - 59, 48):
            gd.line((60, gy, W - 60, gy), fill=(255, 232, 220, 22), width=1)
        for (cx, cy) in ((40, 280), (W - 40, 280), (40, H - 40), (W - 40, H - 40)):
            gd.line((cx - 16, cy, cx + 16, cy), fill=(255, 240, 230, 120), width=2)
            gd.line((cx, cy - 16, cx, cy + 16), fill=(255, 240, 230, 120), width=2)
        mg.alpha_composite(grid)
        d = ImageDraw.Draw(mg)
        d.text((x, 262), head, font=fh, fill=(251, 246, 236))
        self.mag_bg = to_f(mg)
        self.mag_lines_box = [[40, 668, 168, 872], [904, 700, 1040, 900]]
        bc = Image.new('RGBA', (186, 122), (0, 0, 0, 0))
        db = ImageDraw.Draw(bc)
        db.rounded_rectangle((0, 0, 185, 121), radius=6, fill=(252, 250, 244, 255))
        rng = np.random.default_rng(31)
        xb = 14
        while xb < 172:
            wbar = int(rng.integers(1, 5))
            db.rectangle((xb, 12, xb + wbar - 1, 82), fill=(18, 18, 18, 255))
            xb += wbar + int(rng.integers(1, 4))
        db.text((93, 102), '9 787 0 20 26 09 3', font=font('Bold', 15), fill=(18, 18, 18), anchor='mm')
        self.mag_barcode = rotate(bc, 0)
        nm = Image.new('RGBA', (560, 250), (0, 0, 0, 0))
        dn = ImageDraw.Draw(nm)
        dn.text((10, 10), '杂', font=serif(200), fill=(21, 20, 18))
        dn.text((10 + serif(200).getlength('杂'), 10), '志', font=serif(200), fill=(29, 86, 214))
        self.mag_name = halo_img(nm.crop(nm.getbbox()), color=(252, 250, 244), radius=16, strength=0.55)
        self.mag_meta = text_img('封面  ·  特稿', font('Medium', 24), (94, 90, 83), tracking=3)
        # launch (2026-09-27 user feedback: learn from Apple keynotes): pure black -> dark grey stage, a giant screen far behind
        # glowing softly around the presenter, one minimal title (colour-gradient word + light word), soft rim light, slow push-in
        r = np.sqrt(((xx - 540) / 820) ** 2 + ((yy - 1250) / 1250) ** 2)
        stage = np.clip(1 - r, 0, 1)[..., None] ** 1.6 * (np.array([38, 38, 42], np.float32) / 255)
        scr = rounded_mask(60, 300, 960, 900, 28)
        glow = np.exp(-(((xx - 360) / 330) ** 2 + ((yy - 620) / 300) ** 2))[..., None] * np.array([0.55, 0.20, 0.62], np.float32)
        glow += np.exp(-(((xx - 760) / 330) ** 2 + ((yy - 760) / 320) ** 2))[..., None] * np.array([0.10, 0.34, 0.80], np.float32)
        glow += np.exp(-(((xx - 540) / 420) ** 2 + ((yy - 1060) / 220) ** 2))[..., None] * np.array([0.70, 0.30, 0.10], np.float32) * 0.6
        screen = (np.array([10, 10, 12], np.float32) / 255 + glow * 0.42) * scr[..., None]
        edge = np.clip(rounded_mask(58, 298, 964, 904, 30) - scr, 0, 1)[..., None] * np.array([0.30, 0.30, 0.33], np.float32)
        self.launch_bg = np.clip(stage * (1 - scr[..., None]) + screen + edge, 0, 1).astype(np.float32)
        grad = Image.new('RGBA', (1, 1))
        t1 = text_img('发布会', font('Heavy', 142), (255, 255, 255), tracking=4)
        gw = t1.width
        gradient = np.zeros((t1.height, gw, 3), np.float32)
        stops = [(0.0, (255, 149, 0)), (0.36, (255, 55, 95)), (0.7, (175, 82, 222)), (1.0, (10, 132, 255))]
        xs_ = np.linspace(0, 1, gw)
        for c in range(3):
            gradient[..., c] = np.interp(xs_, [p_[0] for p_ in stops], [p_[1][c] for p_ in stops])[None, :]
        ga = np.asarray(t1.split()[3])
        t1 = Image.fromarray(np.dstack([gradient.astype(np.uint8), ga]), 'RGBA')
        t2 = text_img('风格。', font('Medium', 142), (214, 214, 220), tracking=4)
        title = Image.new('RGBA', (t1.width + t2.width - 10, max(t1.height, t2.height)), (0, 0, 0, 0))
        title.alpha_composite(t1, (0, 0))
        title.alpha_composite(t2, (t1.width - 10, 0))
        self.launch_name = halo_img(title.crop(title.getbbox()), color=(0, 0, 0), radius=24, strength=0.62)
        bx = np.minimum(np.arange(W), W - 1 - np.arange(W)).astype(np.float32)[None, :]
        by = (H - 1 - np.arange(H)).astype(np.float32)[:, None]
        self.border_fade = np.clip(np.minimum(bx, by) / 40.0, 0, 1)
        # paper hand-drawn (flash)
        self.paper_bg = to_f(paper(tone=(246, 240, 226), seed=145, grain=3, blotch=4))
        # explainer card (flash)
        self.card = self._explainer_card()

    def _ransom(self, text, size):
        rng = np.random.default_rng(15)
        cols = [((20, 20, 20), (255, 255, 255)), ((255, 214, 10), INK), ((214, 64, 44), (255, 255, 255))]
        tiles = []
        for i, ch in enumerate(text):
            bg, fg = cols[i % len(cols)]
            t = Image.new('RGBA', (size + 44, size + 44), bg + (255,))
            ImageDraw.Draw(t).text(((size + 44) / 2, (size + 44) / 2 + 2), ch, font=font('Heavy', size), fill=fg, anchor='mm')
            t.putalpha(torn_edge_mask(t.width, t.height, amp=4, seed=20 + i, sides='lr'))
            tiles.append(rotate(t, float(rng.uniform(-8, 8))))
        w = sum(t.width for t in tiles) - 18 * (len(tiles) - 1) + 20
        h = max(t.height for t in tiles) + 20
        out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        x = 10
        for i, t in enumerate(tiles):
            sh, pad = shadow_of(t, blur=6, alpha=0.35)
            out.alpha_composite(sh.crop((pad, pad, pad + t.width, pad + t.height)), (x + 4, 10 + 6 + (i % 2) * 8))
            out.alpha_composite(t, (x, 10 + (i % 2) * 8))
            x += t.width - 18
        return out

    def _film_edges(self):
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        strip = 88
        for x0 in (0, W - strip):
            d.rectangle((x0, 0, x0 + strip - 1, H), fill=(24, 20, 16, 255))
            for y in range(-20, H + 40, 72):
                d.rounded_rectangle((x0 + 26, y, x0 + 62, y + 44), radius=7, fill=(236, 228, 214, 255))
        fo = font('Bold', 22)
        for i, y in enumerate(range(160, H, 420)):
            n = 24 + i
            for x0, lab in ((0, f'{n}'), (W - 88, f'{n}A')):
                t = text_img(lab, fo, (240, 150, 60)).rotate(90, expand=True)
                lay.alpha_composite(t, (x0 + 60 if x0 == 0 else x0 + 2, y))
        t = text_img('FILM 400', font('Bold', 20), (240, 150, 60), tracking=3).rotate(90, expand=True)
        lay.alpha_composite(t, (62, 1500))
        # DX edge code: a row of light / dark cells along the inner edge of both strips
        rng = np.random.default_rng(400)
        pattern = rng.integers(0, 2, 40)
        for x0 in (70, W - 86):
            for y0 in range(200, H - 200, 380):
                for i, bit in enumerate(pattern[:24]):
                    if bit:
                        d.rectangle((x0, y0 + i * 9, x0 + 12, y0 + i * 9 + 6), fill=(226, 218, 204, 255))
        return lay

    def _explainer_card(self):
        w, h = 520, 300
        c = Image.new('RGBA', (w, h + 14), (0, 0, 0, 0))
        d = ImageDraw.Draw(c)
        d.rounded_rectangle((0, 8, w - 1, h + 13), radius=24, fill=(159, 182, 210, 255))
        g = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        for yy in range(h):
            v = yy / h
            col = (int(244 - 24 * v), int(248 - 20 * v), int(253 - 14 * v), 255)
            gd.line((0, yy, w, yy), fill=col)
        c.paste(g, (0, 0), rrect_mask(w, h, 24))
        d.rounded_rectangle((16, 16, w - 16, h - 16), radius=14, outline=(27, 38, 56, 45), width=2)
        d.text((44, 56), 'WHY  IS  IT  SO ?', font=font('Bold', 22), fill=(91, 100, 117))
        d.text((40, 108), '为什么', font=font('Heavy', 92), fill=(27, 38, 56))
        d.text((40 + font('Heavy', 92).getlength('为什么'), 108), '？', font=font('Heavy', 92), fill=(47, 107, 216))
        sh, pad = shadow_of(c, blur=26, alpha=0.45)
        out = Image.new('RGBA', (c.width + 2 * pad, c.height + 2 * pad + 20), (0, 0, 0, 0))
        out.alpha_composite(sh, (0, 24))
        out.alpha_composite(c, (pad, pad))
        return out

    # ------------------------------------------------------------ per-style frame (float RGB)
    def fg(self, src_u8, matte_u8):
        P, a = self.host.premult(src_u8, matte_u8)
        return P, a

    def raw(self, ctx, with_name=True):
        return ctx['raw'].copy()

    def collage(self, ctx, with_name=True):
        P, a = ctx['P'], ctx['a']
        out = self.collage_bg.copy()
        paste_rgba(out, self.collage_back, 0, 0)
        # the presenter as a sticker: white border + soft shadow
        ring = cv2.GaussianBlur(dilate(a, 16), (0, 0), 1.2)
        darken(out, soft_shadow(ring, blur=14, alpha=0.32, dx=8, dy=12))
        out = out * (1 - ring[..., None]) + ring[..., None] * np.array([1.0, 0.992, 0.972], np.float32)
        out = out * (1 - a[..., None]) + P
        paste_rgba(out, self.collage_front, 0, 0)
        ctx.setdefault('boxes', {}).update(self.collage_boxes)
        if with_name:
            b = eased_name(out, self.collage_name, 290, 1545, ctx['t'], NAME_T0['collage'] + 0.05)
            if b:
                ctx['boxes']['name_collage'] = b
        return out

    def film(self, ctx, with_name=True):
        I = ctx['raw']
        k = ctx['k']
        g = I * np.array([1.05, 1.0, 0.93], np.float32)
        g = 0.035 + g * 0.95                                  # lifted blacks, soft highlights (no darkening)
        # gate weave: the picture wobbles a pixel or so inside the gate (the film border stays put)
        dx = 1.1 * math.sin(k * 0.9) + 0.5 * math.sin(k * 2.3 + 0.7)
        dy = 0.8 * math.sin(k * 1.3 + 1.0) + 0.4 * math.sin(k * 3.1)
        g = cv2.warpAffine(g, np.float32([[1, 0, dx], [0, 1, dy]]), (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
        # halation: highlights bloom red-orange
        lum = g[..., 0] * 0.3 + g[..., 1] * 0.59 + g[..., 2] * 0.11
        hl = cv2.GaussianBlur(np.clip((lum - 0.70) / 0.30, 0, 1), (0, 0), 14)[..., None]
        g = 1 - (1 - g) * (1 - hl * np.array([0.60, 0.22, 0.10], np.float32))
        rng = np.random.default_rng(1000 + k)
        n = cv2.GaussianBlur(rng.normal(0, 1, (H // 2, W // 2)).astype(np.float32), (0, 0), 0.7)
        n = cv2.resize(n, (W, H), interpolation=cv2.INTER_LINEAR)[..., None] * (6.0 / 255)
        g = g + n
        drift = 0.85 + 0.15 * math.sin(ctx['t'] * 2.1)
        g = 1 - (1 - g) * (1 - self.leak * drift)             # screen-blend light leak
        out = np.clip(g, 0, 1)
        paste_rgba(out, self.film_edges, 0, 0)
        paste_rgba(out, self.film_head, 110, 290)
        paste_rgba(out, self.film_date, W - 110 - self.film_date.width, 1600)
        ctx.setdefault('boxes', {}).update({'film_head': [110, 290, 110 + self.film_head.width, 290 + self.film_head.height],
                                            'film_date': [W - 110 - self.film_date.width, 1600, W - 110, 1600 + self.film_date.height]})
        if with_name:
            b = eased_name(out, self.film_name, 110 + self.film_name.width / 2, 1540, ctx['t'], NAME_T0['film'] + 0.05)
            if b:
                ctx['boxes']['name_film'] = b
        return out

    def magazine(self, ctx, with_name=True):
        P, a = ctx['P'], ctx['a']
        out = self.mag_bg.copy()
        darken(out, soft_shadow(a, blur=22, alpha=0.30, dx=16, dy=20), color=(60 / 255, 14 / 255, 8 / 255))
        out = out * (1 - a[..., None]) + P
        paste_rgba(out, self.mag_barcode, W - 40 - self.mag_barcode.width, 1478)
        ctx.setdefault('boxes', {}).update({'mag_lines_l': self.mag_lines_box[0], 'mag_lines_r': self.mag_lines_box[1],
                                            'mag_barcode': [W - 40 - self.mag_barcode.width, 1478, W - 40, 1478 + self.mag_barcode.height]})
        if with_name:
            b = eased_name(out, self.mag_name, 72 + self.mag_name.width / 2, 1552, ctx['t'], NAME_T0['magazine'] + 0.05)
            if b:
                ctx.setdefault('boxes', {})['name_magazine'] = b
        return out

    def launch(self, ctx, with_name=True):
        P, a = ctx['P'], ctx['a']
        t = ctx['t']
        # slow push-in: the stage / screen 1.00 -> 1.05, the presenter 1.00 -> 1.015 (reads as the camera creeping in)
        u = e_io(prog(t, NAME_T0['launch'] - 0.1, NAME_T0['launch'] + 1.0))
        sb, sp = 1.0 + 0.05 * u, 1.0 + 0.015 * u
        bg = self.launch_bg if sb == 1.0 else warp_affine(self.launch_bg, scale_about(sb, 540, 760), border=cv2.BORDER_REPLICATE, interp=cv2.INTER_LINEAR)
        if sp != 1.0:
            M = scale_about(sp, 540, 900)
            P, a = warp_affine(P, M), warp_affine(a, M)
        out = bg.copy()
        edge = np.clip(dilate(a, 5) - a, 0, 1)
        rim = cv2.GaussianBlur(edge, (0, 0), 7) * 1.1 + cv2.GaussianBlur(edge, (0, 0), 22) * 0.55
        side = np.clip(1.2 - np.arange(W, dtype=np.float32) / W, 0.45, 1.0)[None, :]
        rim = np.clip(rim * side * self.border_fade, 0, 1)
        out = 1 - (1 - out) * (1 - rim[..., None] * np.array([0.78, 0.80, 0.88], np.float32))
        out = out * (1 - a[..., None]) + P
        inner = np.clip(a - cv2.erode(a, np.ones((7, 7), np.uint8)), 0, 1) * side * self.border_fade
        out = out + inner[..., None] * np.array([0.08, 0.08, 0.10], np.float32)
        if with_name:
            b = eased_name(out, self.launch_name, W / 2, 1560, t, NAME_T0['launch'] + 0.05, dur=0.42, rise=18)
            if b:
                ctx.setdefault('boxes', {})['name_launch'] = b
        return np.clip(out, 0, 1)

    def paper(self, ctx, with_name=False):
        P, a = ctx['P'], ctx['a']
        out = self.paper_bg.copy()
        rng = np.random.default_rng(7)
        # highlighter swash behind the shoulder + ink outline around the presenter
        hl = np.zeros((H, W), np.float32)
        cv2.line(hl, (60, 1180), (1020, 1060), 1.0, 70)
        hl = cv2.GaussianBlur(hl, (0, 0), 3) * 0.75
        out = out * (1 - hl[..., None]) + hl[..., None] * np.array([1.0, 0.86, 0.25], np.float32) * 0.98
        ink = np.clip(dilate(a, 4) - dilate(a, 1), 0, 1)
        jit = cv2.GaussianBlur(rng.normal(0, 1, (H // 8, W // 8)).astype(np.float32), (0, 0), 1)
        jit = cv2.resize(jit, (W, H))
        ink = np.clip(ink * (0.75 + 0.35 * jit), 0, 1)
        out = out * (1 - a[..., None]) + P
        out = out * (1 - ink[..., None]) + ink[..., None] * np.array([0.1, 0.1, 0.1], np.float32)
        return out

    def explainer(self, ctx, with_name=False):
        out = ctx['raw'].copy()
        P, a = ctx['P'], ctx['a']
        c = self.card
        rgb, al = affine_elem(c, scale=0.9, rot=6, cx=250, cy=468)
        # card floats in the room behind the presenter's head, never on their face
        over_pm(out, rgb * (1 - a[..., None]), al * (1 - a))
        for (cx, cy, r, col) in ((905, 360, 40, (255, 214, 120)), (960, 470, 22, (238, 244, 252))):
            yy, xx = np.ogrid[0:H, 0:W]
            d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r
            m = np.clip(1.2 - d, 0, 1).astype(np.float32)
            shade = np.clip(1.15 - np.sqrt((xx - cx + r * 0.35) ** 2 + (yy - cy + r * 0.35) ** 2) / (r * 1.6), 0.45, 1)
            ball = np.array(col, np.float32)[None, None] / 255 * shade[..., None]
            out = out * (1 - m[..., None]) + ball * m[..., None]
        ctx.setdefault('boxes', {})['explainer_card'] = elem_bbox(al * (1 - a))
        return out

    def render(self, name, ctx, with_name=True):
        return getattr(self, name)(ctx, with_name)


# ------------------------------------------------------------------ swipe (motion blur + soft light on the boundary)
def swipe(img_a, img_b, u, n):
    """img_b comes in from the right; u in (0, 1)"""
    eu = e_io(u)
    xb = lerp(W + 70, -70, eu)
    xs = np.arange(W, dtype=np.float32)
    feather = 26
    m = np.clip((xs - xb) / feather + 0.5, 0, 1)[None, :, None]
    out = img_a * (1 - m) + img_b * m
    # speed (px / frame) of the boundary at this u
    du = 1.0 / (n + 1)
    v = abs(lerp(W + 70, -70, e_io(min(1, u + du / 2))) - lerp(W + 70, -70, e_io(max(0, u - du / 2))))
    L = int(min(64, 0.28 * v))
    if L >= 3:
        blur = cv2.blur(out, (L, 1))
        wgt = np.exp(-((xs - xb) / 170.0) ** 2)[None, :, None]
        out = out * (1 - wgt) + blur * wgt
    glow = (np.exp(-((xs - xb) / 10.0) ** 2) * 0.55 + np.exp(-((xs - xb) / 46.0) ** 2) * 0.22)[None, :, None]
    glow = glow * min(1.0, v / 120.0 + 0.35)
    out = 1 - (1 - out) * (1 - glow * np.array([1.0, 0.98, 0.94], np.float32))
    return np.clip(out, 0, 1), xb


# ------------------------------------------------------------------ grid
def cell_view(img_full, rect, src_win=CELL_SRC):
    """resample the source window of a full-frame style image into a cell rect (x, y, w, h), rounded"""
    x, y, w, h = rect
    sx, sy, sw, sh = src_win
    crop = img_full[int(round(sy)):int(round(sy + sh)), int(round(sx)):int(round(sx + sw))]
    tw, th = max(1, int(round(w))), max(1, int(round(h)))
    return cv2.resize(crop, (tw, th), interpolation=cv2.INTER_AREA if tw < crop.shape[1] else cv2.INTER_LINEAR)


def put_cell(canvas, cell, x, y, radius=18, alpha=1.0, shadow=True):
    th, tw = cell.shape[:2]
    X, Y = int(round(x)), int(round(y))
    m = rounded_mask(X, Y, tw, th, radius) * alpha
    if shadow:
        darken(canvas, soft_shadow(m, blur=14, alpha=0.28, dx=4, dy=9))
    x0, y0, x1, y1 = max(0, X), max(0, Y), min(W, X + tw), min(H, Y + th)
    if x1 <= x0 or y1 <= y0:
        return
    sub = m[y0:y1, x0:x1, None]
    canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - sub) + cell[y0 - Y:y1 - Y, x0 - X:x1 - X] * sub


def cell_label(text):
    return label([(text, False)], size=40, pad=(22, 8), radius=12, weight_normal='Heavy')


class Shot14a:
    def __init__(self, faces):
        self.faces = faces
        self.st = Styles()
        self.grid_bg = to_f(paper(tone=(244, 240, 232), dots=34, seed=13, grain=3.5, blotch=4))
        self.labels = [cell_label(n) for n in CELL_NAME]
        self.check = badge_ok(96)
        self.pill = self._step_pill()

    def _step_pill(self):
        f = font('Heavy', 30)
        txt = 'STEP 2 画面风格'
        w, h = int(f.getlength(txt) + 40), 51
        im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=25, fill=(20, 20, 20, 225))
        d.text((20, h / 2), txt, font=f, fill=(255, 255, 255), anchor='lm')
        return im

    def ctx(self, k, src_u8, matte_u8):
        c = {'k': k, 't': k / FPS, 'raw': src_u8.astype(np.float32) / 255.0, 'boxes': {}}
        if matte_u8 is not None:
            c['P'], c['a'] = self.st.fg(src_u8, matte_u8)
        return c

    def frame(self, k, src_u8, matte_u8, qa):
        t = k / FPS
        c = self.ctx(k, src_u8, matte_u8)
        g0, gn = GRID_IN
        if k < g0:
            a, b, u = style_at(k)
            if u is None:
                out = self.st.render(a, c)
                qa['style'] = a
            else:
                ca = dict(c, boxes={})
                ia = self.st.render(a, ca)
                cb = dict(c, boxes={})
                ib = self.st.render(b, cb)
                out, xb = swipe(ia, ib, u, [n for s0, n, x, y in SWIPES if x == a and y == b][0])
                qa['style'] = f'{a}->{b}'
                qa['swipe_x'] = round(float(xb), 1)
                for n, bx in ca['boxes'].items():                       # old style: visible left of the boundary
                    if bx and bx[0] < xb - 1:
                        c['boxes'][n] = [bx[0], bx[1], min(bx[2], int(xb) - 1), bx[3]]
                for n, bx in cb['boxes'].items():                       # new style: visible right of the boundary
                    if bx and bx[2] > xb + 1:
                        c['boxes'][n] = [max(bx[0], int(xb) + 2), bx[1], bx[2], bx[3]]
            if a == 'raw' and u is None and t < T['pin'] - 0.2:
                self.step_pill(out, t, qa)
        elif k < SEG_CUT:
            out = self.grid_phase(k, c, qa)
            if not qa.get('style', '').startswith(('collage (picked', 'collage->raw')):
                c['boxes'] = {}
        else:
            out = c['raw']
            qa['style'] = 'raw'
        qa.setdefault('boxes', {}).update({n: b for n, b in c['boxes'].items() if b})
        return to_u8(out)

    def step_pill(self, out, t, qa):
        tp = T['huamian'] - 0.05
        if t < tp:
            return
        s = pop(t, tp, 0.28, 0.1)
        al = 1 - prog(t, T['pin'] - 0.45, T['pin'] - 0.2)
        rgb, a = affine_elem(self.pill, scale=s, cx=40 + self.pill.width / 2, cy=300 + self.pill.height / 2, alpha=al)
        over_pm(out, rgb, a)
        qa.setdefault('boxes', {})['step_pill'] = elem_bbox(a)

    def grid_phase(self, k, c, qa):
        g0, gn = GRID_IN
        z0, zn = ZOOM
        b0, bn = BACK
        t = k / FPS
        if k >= b0:                                              # swipe back to the untouched frame
            if k >= b0 + bn:
                qa['style'] = 'raw'
                return c['raw']
            ia = self.st.render('collage', c)
            u = (k - b0 + 1) / (bn + 1)
            out, xb = swipe(ia, c['raw'], u, bn)
            qa['style'] = 'collage->raw'
            return out
        if k >= z0 + zn:
            qa['style'] = 'collage (picked, full)'
            return self.st.render('collage', c)
        canvas = self.grid_bg.copy()
        styles = {}
        zoom_on = k >= z0
        for s in CELL_STYLE:
            styles[s] = self.st.render(s, c, with_name=(s == 'collage' and zoom_on))
        boxes = qa.setdefault('boxes', {})
        ui = e_io(prog(k, g0 - 1, g0 + gn))                      # shrink progress
        zi = e_io(prog(k, z0 - 1, z0 + zn)) if k >= z0 else 0.0  # zoom progress
        veil = e_out(prog(k, PICK_RING, PICK_RING + 6), 2) if k >= PICK_RING else 0.0
        order = [1, 2, 3, 0]                                      # the picked cell is drawn last (on top)
        for i in order:
            x, y, w, h = CELLS[i]
            if i == 0:
                continue
            d = 3 + 2 * (i - 1)
            v = e_out(prog(k, g0 + d - 1, g0 + d + 10), 3)
            if v <= 0:
                continue
            if i == 1:
                x = lerp(W + 30, x, v)
            elif i == 2:
                y = lerp(H + 30, y, v)
            else:
                x, y = lerp(W + 30, x, v), lerp(H + 30, y, v)
            cell = cell_view(styles[CELL_STYLE[i]], (x, y, w, h))
            self._cell_face(qa, c['k'], (x, y, w, h), CELL_SRC)
            if veil > 0:
                cell = cell * (1 - 0.35 * veil) + 0.35 * veil * np.array([0.96, 0.95, 0.93], np.float32)
            put_cell(canvas, cell, x, y)
            if zi == 0:
                boxes[f'cell_{CELL_NAME[i]}'] = [int(x), int(y), int(x + w), int(y + h)]
            la = prog(k, g0 + d + 8, g0 + d + 14)
            if la > 0:
                lb = self.labels[i]
                lx, ly = x + w / 2 - lb.width / 2, y + h + 7
                paste_rgba(canvas, lb, lx, ly, alpha=la * (1 - 0.35 * veil))
                if zi == 0:
                    boxes[f'label_{CELL_NAME[i]}'] = [int(lx), int(ly), int(lx + lb.width), int(ly + lb.height)]
        # the picked / shrinking cell: the frame shrinks from full screen into cell 0 (raw -> collage), later zooms out
        x0, y0, w0, h0 = CELLS[0]
        e = ui * (1 - zi)
        Dx, Dy, Dw, Dh = lerp(0, x0, e), lerp(0, y0, e), lerp(W, w0, e), lerp(H, h0, e)
        k_s = lerp(1.0, w0 / CELL_SRC[2], e)
        sw, sh = Dw / k_s, Dh / k_s
        ccx = lerp(W / 2, CELL_SRC[0] + CELL_SRC[2] / 2, e)
        ccy = lerp(H / 2, CELL_SRC[1] + CELL_SRC[3] / 2, e)
        sx0 = min(max(0.0, ccx - sw / 2), W - sw)
        sy0 = min(max(0.0, ccy - sh / 2), H - sh)
        mix = e_io(prog(k, g0 + 2, g0 + gn - 2)) if k < z0 else 1.0
        src_img = styles['collage'] if mix >= 1 else (c['raw'] * (1 - mix) + styles['collage'] * mix)
        cell0 = cell_view(src_img, (Dx, Dy, Dw, Dh), (sx0, sy0, sw, sh))
        self._cell_face(qa, c['k'], (Dx, Dy, Dw, Dh), (sx0, sy0, sw, sh))
        rad = 18 * e
        if veil > 0 and zi < 1:
            ring = rounded_mask(Dx - 10, Dy - 10, Dw + 20, Dh + 20, rad + 10) - rounded_mask(Dx - 1, Dy - 1, Dw + 2, Dh + 2, rad + 1)
            ring = np.clip(ring, 0, 1) * veil * (1 - zi)
            canvas = canvas * (1 - ring[..., None]) + ring[..., None] * (np.array(YELLOW, np.float32) / 255)
            boxes['pick_ring'] = [int(Dx - 10), int(Dy - 10), int(Dx + Dw + 10), int(Dy + Dh + 10)]
        put_cell(canvas, cell0, Dx, Dy, radius=rad, shadow=e > 0.05)
        boxes['cell_拼贴'] = [int(Dx), int(Dy), int(Dx + Dw), int(Dy + Dh)]
        if e > 0.6 and zi == 0:
            lb = self.labels[0]
            la = prog(k, g0 + gn - 3, g0 + gn + 3)
            if la > 0:
                lx, ly = x0 + w0 / 2 - lb.width / 2, y0 + h0 + 7
                paste_rgba(canvas, lb, lx, ly, alpha=min(1, la))
                boxes['label_拼贴'] = [int(lx), int(ly), int(lx + lb.width), int(ly + lb.height)]
        if k >= PICK_CHECK and zi < 0.3 and Dy + 58 - 52 >= 290:
            s = pop(t, PICK_CHECK / FPS, 0.26, 0.14)
            cx, cy = Dx + Dw - 30, Dy + 58
            rgb, a = affine_elem(self.check, scale=s, cx=cx, cy=cy, alpha=1 - zi / 0.3)
            darken(canvas, soft_shadow(a, blur=6, alpha=0.3))
            over_pm(canvas, rgb, a)
            boxes['check'] = elem_bbox(a)
        qa['style'] = 'grid' if zi == 0 else 'zoom'
        qa['face_screen'], qa['lips_screen'] = None, None      # faces are the per-cell ones (faces_extra)
        qa['cell0'] = {'dst': [round(Dx, 1), round(Dy, 1), round(Dw, 1), round(Dh, 1)], 'src': [round(sx0, 1), round(sy0, 1), round(sw, 1), round(sh, 1)]}
        return canvas


def _cell_face(self, qa, k, rect, win):
    f = v2_src_frame(k)
    fc, lp = self.faces[f]
    x, y, w, h = rect
    sx, sy, sw, sh = win
    kx = w / sw
    def mp(b):   # mapped into the cell and clipped to what the cell shows
        bx = [x + (b[0] - sx) * kx, y + (b[1] - sy) * kx, x + (b[2] - sx) * kx, y + (b[3] - sy) * kx]
        bx = [max(bx[0], x), max(bx[1], y), min(bx[2], x + w), min(bx[3], y + h)]
        return [int(v) for v in bx] if bx[2] > bx[0] and bx[3] > bx[1] else None
    qa.setdefault('faces_extra', []).append({'face': mp(fc), 'lips': mp(lp)})


Shot14a._cell_face = _cell_face


def badge_ok(s=104):
    b = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(b).ellipse((0, 0, s - 1, s - 1), fill=GREEN)
    b.alpha_composite(icon_check(int(s * 0.76), color=(255, 255, 255), lw=11), (int(s * 0.12), int(s * 0.14)))
    return b


# ------------------------------------------------------------------ sound design for 14a (v2 global seconds)
def sfx_cues():
    """cue dicts {id, t, gain_db, pitch, align, note, params}; ids from xiaolu-motion audio/sfx/CATALOG.md"""
    out = []

    def c(id_, t, g, p=0, align='start', note='', params=None):
        d = {'id': id_, 't': round(float(t), 3), 'gain_db': g, 'pitch': p, 'align': align, 'note': note}
        if params:
            d['params'] = params
        out.append(d)
    c('bell', T['start'], -2, note='chapter start 第二步 (storyboard)')
    c('pop_soft', T['huamian'] - 0.05 + 0.17, -6, note='STEP 2 画面风格 pill')
    notes = ['D5', 'F#5', 'A5', 'D6']
    for i, (s0, n, a, b) in enumerate(SWIPES[:4]):
        c('whoosh_fast', s0 / FPS, -6, 0, 'motion', f'swipe {a} -> {b}', {'travel': -0.6})
        c('pluck', NAME_T0[b] + 0.05 + 0.19, -6, 0, 'start', f'style name {b} eases in (keyword)', {'note': notes[i]})
    for s0, n, a, b in SWIPES[4:]:
        c('whoosh_fast', s0 / FPS, -12, 0, 'motion', f'flash swipe {a} -> {b}', {'travel': -0.6, 'dur': 0.2})
    g0, gn = GRID_IN
    c('whoosh_mid', g0 / FPS, -6, 0, 'motion', 'frame shrinks into the grid, three cells slide in')
    for i in (1, 2, 3):
        d = 3 + 2 * (i - 1)
        c('pop_soft', (g0 + d + 9) / FPS, -12, 2 * i, 'start', f'cell {CELL_NAME[i]} lands')
    c('tick', PICK_RING / FPS, -6, 0, 'start', 'yellow ring on 拼贴 (挑)')
    c('clack', PICK_CHECK / FPS + 0.6 * 0.26, -3, 0, 'start', 'green check pops')
    c('push', ZOOM[0] / FPS, -4, 0, 'motion', 'picked cell pushes to full screen')
    c('whoosh_fast', BACK[0] / FPS, -9, 0, 'motion', 'swipe back to the untouched frame', {'travel': -0.6})
    return out
