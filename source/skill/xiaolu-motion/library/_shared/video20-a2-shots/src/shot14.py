"""Shot 14 (v2 1:20.10-1:37.90, frames 2403..2936): 14a card table (the presenter behind a cutting-mat table, style cards
dealt like poker, one picked), 14b collage style brushed down over the live frame.

14a revision after user feedback on the storyboard ("像我的人头被砍掉"): the presenter is scaled 0.85 (shoulders nearly
full width, was 0.62), the table's far edge sits at his chest / the hand holding the mic (source y 1320, was
the collarbone line), the edge has a rim highlight + bevel line (thickness), his torso gets an occlusion
shade just above the edge and the mat gets his contact shadow just below it, cards are dealt on the mat in
front of him, the room behind stays blurred (clean plate, no ghost of the presenter).
"""
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

from a2common import *  # noqa
import a2time as AT

ASSETS = Path(__file__).resolve().parent / 'assets'
if not ASSETS.exists():                       # shared source tree: assets live under s14/src/assets
    ASSETS = a2paths.SHOTS / 's14/src/assets'
F0, F1 = AT.SHOT_RANGE['14']                  # 2403, 2937
SEG_CUT = 2784                                # v2 frame of the jump cut 14 -> 15 (1:32.80), 14a | 14b

# ------------------------------------------------------------------ word times (v2 s), words_v2.json
T = dict(
    start=F0 / FPS,
    huamian=AT.word_on('画面风格', 81.08),
    tu=AT.word_on('风格图', 84.2),
    d1=AT.word_on('拼接', 85.54), d2=AT.word_on('胶片', 86.49), d3=AT.word_on('杂志', 87.50), d4=AT.word_on('发布会', 88.33),
    tiao=AT.word_on('挑一个', 91.04), ge=AT.word_on('个', 91.43),
    yi=AT.kw('14', '以这个风格为标准', 94.42), fengge=AT.word_on('风格为标准', 94.73), bao=AT.kw('14', '包装', 97.28),
    zhuang_end=AT.word_end('包装', 97.28),
)

# ------------------------------------------------------------------ 14a layout
S_P = 0.85                                    # presenter scale behind the table
FACE_CX_SRC = 530.0                           # median face centre x in segment 14 (source px)
OX = 575.0 - FACE_CX_SRC * S_P                # face centre on screen x = 575 (room for the picked card on the left)
OY = 100.0 - 210.0 * S_P                      # hair top (source y ~210) at screen y ~100
EDGE_SRC_Y = 1320                             # table far edge at the presenter's chest / mic hand (source y)
Y_EDGE = OY + EDGE_SRC_Y * S_P                # ~1043 on screen
M_PERSON = np.float32([[S_P, 0, OX], [0, S_P, OY]])
BG_S = 0.96                                   # room plate scale (parallax: moves less than the presenter)
BG_BLUR = 16
BG_DIM = 0.86

MAT = (36, 92, 70)
TW, TH = 1800, 1500                           # mat texture
# texture rect -> screen quad. Flatter than the storyboard's (-120..1200 / -1020..2100) so the four style cards can
# fill y 1054-1289 (the band between the table edge and the subtitle band) without overlapping each other
QUAD = [(-60, Y_EDGE), (1140, Y_EDGE), (1500, 2300), (-420, 2300)]


def _coeffs(pa, pb):
    A = []
    for (x, y), (u, v) in zip(pa, pb):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    return np.linalg.solve(np.array(A, float), np.array(pb, float).reshape(8))


class Plane:
    """texture rect (tw x th) <-> screen quad [tl, tr, br, bl] (same maths as storyboard render_v2.Plane)"""

    def __init__(self, tw, th, quad):
        self.tw, self.th, self.quad = tw, th, quad
        rect = [(0, 0), (tw, 0), (tw, th), (0, th)]
        self.Hf = cv2.getPerspectiveTransform(np.float32(rect), np.float32(quad))
        self.Hi = np.linalg.inv(self.Hf)

    def pt(self, x, y):
        v = self.Hf @ np.array([x, y, 1.0])
        return v[0] / v[2], v[1] / v[2]

    def inv_pt(self, x, y):
        v = self.Hi @ np.array([x, y, 1.0])
        return v[0] / v[2], v[1] / v[2]


PLANE = Plane(TW, TH, QUAD)


def cutting_mat_tex():
    """storyboard render_v2.cutting_mat, same grid; plus a gentle light fall-off toward the camera"""
    rng = np.random.default_rng(14)
    arr = np.ones((TH, TW, 3), np.float32) * np.array(MAT, np.float32)
    arr += rng.normal(0, 3.0, (TH, TW, 1)).astype(np.float32)
    tex = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert('RGBA')
    d = ImageDraw.Draw(tex)
    for x in range(0, TW, 40):
        d.line((x, 0, x, TH), fill=(74, 132, 106, 255), width=5 if x % 200 == 0 else 2)
    for y in range(0, TH, 40):
        d.line((0, y, TW, y), fill=(74, 132, 106, 255), width=5 if y % 200 == 0 else 2)
    for k in range(-TH, TW, 400):
        d.line((k, 0, k + TH, TH), fill=(64, 118, 94, 255), width=2)
    for x in range(0, TW, 20):
        d.line((x, 0, x, 18 if x % 100 else 34), fill=(210, 230, 215, 255), width=3)
    a = np.asarray(tex, np.float32).copy()
    yy = np.linspace(0, 1, TH, dtype=np.float32)[:, None, None]
    a[..., :3] *= 1.05 - 0.30 * yy ** 1.2          # lit near the presenter, falling off toward the camera
    return np.clip(a, 0, 255).astype(np.uint8)


def style_card(key, name, w=300, h=400, label_size=64, ss=2, key_on=False):
    """storyboard style_card_img at ss x resolution: real style sample in a white photo border + name label"""
    src = Image.open(ASSETS / key).convert('RGBA').resize((w * ss, h * ss), Image.LANCZOS)
    c = photo(src, border=12 * ss, radius=8 * ss)
    lab = label([(name, key_on)], size=label_size * ss, pad=(18 * ss, 6 * ss), radius=10 * ss, weight_normal='Heavy', tracking=2 * ss)
    c.alpha_composite(lab, ((c.width - lab.width) // 2, c.height - lab.height - 16 * ss))
    return c


CARDS = [  # dealt left -> right in the spoken order; card 0 (拼贴) is the one picked
    dict(key='style_collage.jpg', name='拼贴', t='d1', rot=-0.8),
    dict(key='style_film.jpg', name='胶片', t='d2', rot=0.7),
    dict(key='style_magazine.png', name='杂志', t='d3', rot=-0.6),
    dict(key='style_launch.png', name='发布会', t='d4', rot=0.8),
]
SLOT_SY = Y_EDGE + 11                          # card far edge on screen (y 1054)
CARD_TW, CARD_TH = 300, 400                    # card size in mat texture units (3:4)
SLOT_PITCH = 318                               # texture units between card centres (12 px gaps on screen)


def slot_tex(i):
    cx, ty = PLANE.inv_pt(540, SLOT_SY)
    return cx + (i - 1.5) * SLOT_PITCH, ty + CARD_TH / 2     # card centre in texture coords


def card_quad_screen(cx, cy, rot, scale_x=1.0, lift=0.0):
    """screen quad of a flat card centred at texture (cx, cy), rotated rot deg on the mat, width squeezed by
    scale_x (flip), lifted `lift` px straight up on screen"""
    hw, hh = CARD_TW / 2 * scale_x, CARD_TH / 2
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    pts = []
    for px, py in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
        tx, ty = cx + px * c - py * s, cy + px * s + py * c
        X, Y = PLANE.pt(tx, ty)
        pts.append((X, Y - lift))
    return np.float32(pts)


def warp_card(img_rgba_f, quad):
    """perspective-warp a card (float RGBA straight alpha, any size) to a screen quad; returns premult rgb, alpha"""
    h, w = img_rgba_f.shape[:2]
    Hm = cv2.getPerspectiveTransform(np.float32([(0, 0), (w, 0), (w, h), (0, h)]), quad)
    pm = np.dstack([img_rgba_f[..., :3] * img_rgba_f[..., 3:4], img_rgba_f[..., 3]])
    out = cv2.warpPerspective(pm, Hm, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return out[..., :3], out[..., 3]


class Shot14:
    def __init__(self):
        self.host = Host(WORK / 'plate14.png')
        pl = cv2.cvtColor(cv2.imread(str(WORK / 'plate14.png')), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        self.plate = pl
        Mb = scale_about(BG_S, W / 2, H / 2)
        bg = warp_affine(pl, Mb, border=cv2.BORDER_REFLECT101, interp=cv2.INTER_LINEAR)
        self.bg_final = cv2.GaussianBlur(bg, (0, 0), BG_BLUR) * BG_DIM
        # static table layer (premultiplied, full canvas) at its final position
        tex = cutting_mat_tex().astype(np.float32) / 255.0
        pm = np.dstack([tex[..., :3], np.ones((TH, TW), np.float32)])
        self.table_pm = cv2.warpPerspective(pm, PLANE.Hf, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        # edge: bevel shade + rim highlight along the far edge (thickness cue)
        ye = int(round(Y_EDGE))
        rim = np.zeros((H, W), np.float32)
        rim[ye:ye + 3] = 0.8
        rim = cv2.GaussianBlur(rim, (0, 0), 0.9)
        bevel = np.zeros((H, W), np.float32)
        bevel[ye + 3:ye + 10] = 1.0
        bevel = cv2.GaussianBlur(bevel, (0, 0), 1.6) * 0.42
        self.rim, self.bevel = rim, bevel
        self.cards = [np.asarray(style_card(c['key'], c['name'], key_on=(i == 0 and False)), np.float32) / 255.0 for i, c in enumerate(CARDS)]
        self.card_back = self._card_back()
        self.picked_hi = np.asarray(self._picked_card(), np.float32) / 255.0
        self.step_tag = self._step_tag()

    # ---------------------------------------------------------------- elements
    def _card_back(self, ss=2):
        w, h = CARD_TW * ss, CARD_TH * ss
        im = Image.new('RGBA', (w + 24 * ss, h + 24 * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=14 * ss, fill=CARD + (255,))
        d.rounded_rectangle((12 * ss, 12 * ss, im.width - 12 * ss, im.height - 12 * ss), radius=8 * ss, fill=(224, 196, 150, 255))
        for k in range(-h, w, 26 * ss):
            d.line((12 * ss + k, 12 * ss, 12 * ss + k + h, 12 * ss + h), fill=(210, 180, 132, 255), width=6 * ss)
        f = font('Heavy', 64 * ss)
        d.text((im.width / 2, im.height / 2), '风格', font=f, fill=(150, 108, 60, 255), anchor='mm')
        return np.asarray(im, np.float32) / 255.0

    def _picked_card(self, ss=2):
        sel = style_card('style_collage.jpg', '拼贴', 282, 376, label_size=52, ss=ss, key_on=True)
        ring = Image.new('RGBA', (sel.width + 30 * ss, sel.height + 30 * ss), (0, 0, 0, 0))
        ImageDraw.Draw(ring).rounded_rectangle((3 * ss, 3 * ss, ring.width - 4 * ss, ring.height - 4 * ss), radius=22 * ss,
                                               outline=YELLOW + (255,), width=12 * ss)
        ring.alpha_composite(sel, (15 * ss, 15 * ss))
        return ring

    def _step_tag(self, ss=2):
        """'STEP 2 画面风格' tag, printed flat on the mat (storyboard: label placed on the cutting mat)"""
        f = font('Heavy', 30 * ss)
        txt = 'STEP 2 画面风格'
        w, h = int(f.getlength(txt) + 40 * ss), int(30 * 1.7 * ss)
        im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(20, 20, 20, 235))
        d.text((20 * ss, h / 2), txt, font=f, fill=(255, 255, 255), anchor='lm')
        return np.asarray(im, np.float32) / 255.0

    # ---------------------------------------------------------------- 14a frame
    def layout(self, t):
        """0 = raw full frame, 1 = table layout (pull-back at the start, push-in before the jump cut)"""
        p = e_io(prog(t, T['start'], T['start'] + 0.5))
        q = e_io(prog(t, (SEG_CUT - 15) / FPS, (SEG_CUT - 1) / FPS))
        return p * (1 - q), p, q

    def table_drop(self, t):
        """screen-y offset of the table layer: rises in (0.05-0.62 s after the cut in), drops out in the push-in"""
        rise = e_out(prog(t, T['start'] + 0.05, T['start'] + 0.62), 3)
        q = e_in(prog(t, (SEG_CUT - 15) / FPS, (SEG_CUT - 1) / FPS), 2)
        return (1 - rise) * (H - Y_EDGE + 60) + q * (H - Y_EDGE + 60)

    def frame14a(self, k, src_u8, matte_u8, qa):
        t = k / FPS
        L, p, q = self.layout(t)
        if L <= 0 and self.table_drop(t) >= H - Y_EDGE + 59:
            qa['layout'] = 'raw'
            return src_u8.copy()
        s = lerp(1.0, S_P, L)
        M = np.float32([[s, 0, lerp(0, OX, L)], [0, s, lerp(0, OY, L)]])
        # background: clean plate, parallax scale, blur, dim
        if L >= 0.999:
            canvas = self.bg_final.copy()
        else:
            Mb = scale_about(lerp(1.0, BG_S, L), W / 2, H / 2)
            bg = warp_affine(self.plate, Mb, border=cv2.BORDER_REFLECT101, interp=cv2.INTER_LINEAR)
            sig = BG_BLUR * L
            if sig > 0.3:
                bg = cv2.GaussianBlur(bg, (0, 0), sig)
            canvas = bg * lerp(1.0, BG_DIM, L)
        # presenter: premultiplied foreground, frame-edge feather (the source crop ends at his arms)
        P, a = self.host.premult(src_u8, matte_u8)
        ramp = np.clip(np.minimum(np.arange(W), W - 1 - np.arange(W)) / 14.0, 0, 1).astype(np.float32)[None, :]
        shade = (1 - 0.14 * np.clip(1 - np.minimum(np.arange(W), W - 1 - np.arange(W)) / 60.0, 0, 1)).astype(np.float32)[None, :]
        a = a * ramp
        P = P * (ramp * shade)[..., None]
        Pw = warp_affine(P, M)
        aw = warp_affine(a, M)
        drop = self.table_drop(t)
        ye = Y_EDGE + drop
        # torso occlusion shade right above the table edge
        if ye < H:
            yy = np.arange(H, dtype=np.float32)[:, None]
            ao = 0.30 * np.clip((yy - (ye - 48)) / 48.0, 0, 1) ** 1.8 * (yy <= ye)
            Pw *= (1 - ao * L)[..., None]
        canvas = canvas * (1 - aw[..., None]) + Pw
        qa['person_M'] = M.tolist()
        # table + cards
        if drop < H - Y_EDGE + 59:
            tab = self.table_layer(t, drop, aw, qa)
            over_pm(canvas, tab[..., :3], tab[..., 3])
            self.cards_layer(canvas, t, drop, qa)
        return to_u8(canvas)

    def table_layer(self, t, drop, aw, qa):
        tab = self.table_pm.copy()
        ye = Y_EDGE
        # contact shadow of the presenter's body on the mat, just in front of the far edge (from the body's width at the edge)
        row0 = int(round(Y_EDGE + drop)) - 10
        if 0 <= row0 < H - 1:
            cover = aw[max(0, row0 - 6):row0].mean(0) if row0 > 6 else aw[row0]
        else:
            cover = np.zeros(W, np.float32)
        cover = cv2.GaussianBlur(cover[None, :], (0, 0), 22)[0]
        yy = np.arange(H, dtype=np.float32)[:, None] - ye
        fall = np.clip(1 - yy / 96.0, 0, 1) ** 1.5 * (yy >= 0)
        sh = 0.62 * fall * cover[None, :]
        tab[..., :3] *= (1 - sh)[..., None]
        # rim highlight + bevel shade on the far edge (thickness)
        tab[..., :3] = tab[..., :3] * (1 - self.bevel[..., None]) + 0.0
        tab[..., :3] = tab[..., :3] * (1 - self.rim[..., None]) + self.rim[..., None] * np.array([0.80, 0.90, 0.84], np.float32)
        # step tag printed on the mat, lower left (below the subtitle band)
        tp = prog(t, T['huamian'], T['huamian'] + 0.22)
        if tp > 0:
            self.flat_elem(tab, self.step_tag, (236, 1492), 1.0 + 0.25 * (1 - e_out(tp)), 0.0, e_out(tp), qa, 'step_tag')
        # empty slot of the picked card (dashed) once it has left the mat
        if t >= T['tiao']:
            self.dashed_slot(tab, 0, alpha=min(1.0, (t - T['tiao']) / 0.15))
        if drop:
            Mt = np.float32([[1, 0, 0], [0, 1, drop]])
            tab = cv2.warpAffine(tab, Mt, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        return tab

    def flat_elem(self, tab, img_f, screen_c, scale, rot, alpha, qa, name):
        """an element lying flat on the mat, centred at a screen point (mapped onto the plane), perspective-warped"""
        cx, cy = PLANE.inv_pt(*screen_c)
        h, w = img_f.shape[:2]
        k = 0.5 * scale                       # element drawn at 2x
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        quad = []
        for px, py in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
            px, py = px * k * 1.25, py * k * 1.25
            quad.append(PLANE.pt(cx + px * c - py * s, cy + px * s + py * c))
        rgb, a = warp_card(img_f, np.float32(quad))
        a = a * alpha
        tab[..., :3] = tab[..., :3] * (1 - a[..., None]) + rgb * alpha
        qa.setdefault('boxes', {})[name] = elem_bbox(a)

    def dashed_slot(self, tab, i, alpha=1.0):
        cx, cy = slot_tex(i)
        q = card_quad_screen(cx, cy, CARDS[i]['rot'])
        lay = Image.new('L', (W, H), 0)
        d = ImageDraw.Draw(lay)
        for j in range(4):
            (x0, y0), (x1, y1) = q[j], q[(j + 1) % 4]
            n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 24))
            for m in range(0, n, 2):
                a0, a1 = m / n, min(1, (m + 1) / n)
                d.line((x0 + (x1 - x0) * a0, y0 + (y1 - y0) * a0, x0 + (x1 - x0) * a1, y0 + (y1 - y0) * a1), fill=255, width=5)
        m = np.asarray(lay, np.float32) / 255.0 * 0.9 * alpha
        tab[..., :3] = tab[..., :3] * (1 - m[..., None]) + m[..., None] * np.array([0.90, 0.94, 0.90], np.float32)

    # ---------------------------------------------------------------- dealt cards + the picked card
    DEAL_DUR = 0.36
    STAND_H = 306.0
    STAND_BOTTOM = (148.0, Y_EDGE + 74.0)       # bottom centre of the picked card standing on the table (screen)
    STAND_TILT = -4.0

    def stand_quad(self, drop, scale=1.0, img=None):
        img = self.cards[0] if img is None else img
        h, w = img.shape[:2]
        hh = self.STAND_H * scale
        ww = hh * w / h
        bx, by = self.STAND_BOTTOM[0], self.STAND_BOTTOM[1] + drop
        c, s = math.cos(math.radians(self.STAND_TILT)), math.sin(math.radians(self.STAND_TILT))
        pts = []
        for px, py in ((-ww / 2, -hh), (ww / 2, -hh), (ww / 2, 0), (-ww / 2, 0)):
            pts.append((bx + px * c - py * s, by + px * s + py * c))
        return np.float32(pts)

    def cards_layer(self, canvas, t, drop, qa):
        boxes = qa.setdefault('boxes', {})
        for i, c in enumerate(CARDS):
            tl = T[c['t']]
            if t < tl - self.DEAL_DUR:
                continue
            sx, sy = slot_tex(i)
            if i == 0 and t >= T['tiao']:
                self.picked(canvas, t, drop, qa)
                continue
            u = e_out(prog(t, tl - self.DEAL_DUR, tl), 3)
            start_x = PLANE.inv_pt(1320, SLOT_SY)[0] + CARD_TW
            cx = lerp(start_x, sx, u)
            rot = c['rot'] + 28 * (1 - u)
            lift = 22 * (1 - u)
            land = 1.0 + 0.035 * math.sin(math.pi * prog(t, tl, tl + 0.12)) if t >= tl else 1.0
            quad = card_quad_screen(cx, sy, rot, scale_x=land, lift=lift)
            quad[:, 1] += drop
            flat = card_quad_screen(cx, sy, rot)
            flat[:, 1] += drop
            # shadow on the mat (under the card; wider and softer while it is in the air)
            _, sa = warp_card(self.cards[i], flat + np.float32([4, 7]))
            sa = cv2.GaussianBlur(sa, (0, 0), 3 + lift * 0.45) * (0.42 - 0.012 * lift)
            darken(canvas, np.clip(sa, 0, 1))
            rgb, a = warp_card(self.cards[i], quad)
            over_pm(canvas, rgb, a)
            boxes[f'card_{c["name"]}'] = elem_bbox(a)
            qa.setdefault('quads', {})[f'card_{c["name"]}'] = np.round(quad, 1).tolist()

    def picked(self, canvas, t, drop, qa):
        boxes = qa.setdefault('boxes', {})
        u = e_io(prog(t, T['tiao'], T['tiao'] + 0.30))
        sx, sy = slot_tex(0)
        flat = card_quad_screen(sx, sy, CARDS[0]['rot'])
        flat[:, 1] += drop
        over = 1.0 + 0.06 * math.sin(math.pi * prog(t, T['tiao'] + 0.22, T['tiao'] + 0.42))
        stand = self.stand_quad(drop, scale=over)
        quad = flat * (1 - u) + stand * u
        # the card rises off the mat: a short arc upward in the middle of the flip
        quad[:, 1] -= 40 * math.sin(math.pi * u)
        ring_on = prog(t, T['tiao'] + 0.24, T['tiao'] + 0.36)
        # soft shadow on the mat under the standing card
        base = self.stand_quad(drop)
        sh = np.float32([base[3], base[2], base[2] + [30, 16], base[3] + [30, 16]])
        m = np.zeros((H, W), np.float32)
        cv2.fillConvexPoly(m, sh.astype(np.int32), 1.0)
        darken(canvas, cv2.GaussianBlur(m, (0, 0), 7) * 0.38 * u)
        rgb, a = warp_card(self.cards[0], quad)
        # drop shadow behind the lifted card (on the presenter / the room)
        darken(canvas, soft_shadow(a, blur=14, alpha=0.35 * u, dx=6, dy=10))
        over_pm(canvas, rgb * (1 - ring_on), a * (1 - ring_on))
        if ring_on > 0:
            rq = self.stand_quad(drop, scale=over * 1.07, img=self.picked_hi)
            # ring card has a 15 px (x2) frame around the same card: keep the card itself where it was
            rgb2, a2 = warp_card(self.picked_hi, rq)
            over_pm(canvas, rgb2 * ring_on, a2 * ring_on)
            a = np.maximum(a * (1 - ring_on), a2 * ring_on)
        boxes['picked_card'] = elem_bbox(a)
        qa.setdefault('quads', {})['picked_card'] = np.round(rq if ring_on > 0 else quad, 1).tolist()
        # green check badge pops on the card's lower right corner (off the face: below the chin line)
        cp = pop(t, T['ge'] - 0.12, 0.26, 0.14)
        if cp > 0:
            b = badge_ok(104)
            rgbb, ab = affine_elem(b, scale=cp, rot=0, cx=self.STAND_BOTTOM[0] + 118, cy=self.STAND_BOTTOM[1] - 52 + drop)
            darken(canvas, soft_shadow(ab, blur=6, alpha=0.3))
            over_pm(canvas, rgbb, ab)
            boxes['check'] = elem_bbox(ab)


def badge_ok(s=104):
    """storyboard render_v2.badge('ok')"""
    b = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(b).ellipse((0, 0, s - 1, s - 1), fill=GREEN)
    b.alpha_composite(icon_check(int(s * 0.76), color=(255, 255, 255), lw=11), (int(s * 0.12), int(s * 0.14)))
    return b


# ====================================================================== 14b: the collage style brushed down over the presenter
TB0 = T['yi']                                  # brush leaves the top on 「以这个风格为标准」
TB1 = T['bao']                                 # full frame packaged on 「包装」 (words_v2 keyword table)
EXIT0, EXIT1 = 2927, 2936                      # cross-fade back to the untouched frame; frame 2936 is raw
MARGIN = 34                                    # storyboard collage_version: page margin + 14 px white border


def cutout_letters(text, size=78, seed=5):
    """storyboard render_v2.cutout_letters: ransom-note letters, each on its own torn paper scrap; returns the
    list of (tile, x, y) so each letter can pop in when the brush reaches it"""
    rng = np.random.default_rng(seed)
    cols = [((20, 20, 20), (255, 255, 255)), ((255, 214, 10), INK), (CARD, INK), ((214, 64, 44), (255, 255, 255)),
            ((226, 205, 168), INK)]
    tiles = []
    for i, ch in enumerate(text):
        bg, fg = cols[i % len(cols)]
        fnt = font('Heavy' if i % 2 == 0 else 'Bold', size)
        t = Image.new('RGBA', (size + 34, size + 34), bg + (255,))
        ImageDraw.Draw(t).text(((size + 34) / 2, (size + 34) / 2 + 2), ch, font=fnt, fill=fg, anchor='mm')
        m = torn_edge_mask(t.width, t.height, amp=3, seed=seed + i, sides='lr')
        t.putalpha(m)
        tiles.append(rotate(t, float(rng.uniform(-9, 9))))
    w = max(t.width for t in tiles) + 20
    out, y = [], 0
    for i, t in enumerate(tiles):
        x = int((w - t.width) / 2 + (8 if i % 2 else -8))
        sh, pad = shadow_of(t, blur=5, alpha=0.35)
        tile = Image.new('RGBA', (t.width + 2 * pad, t.height + 2 * pad), (0, 0, 0, 0))
        tile.alpha_composite(sh, (3, 5))
        tile.alpha_composite(t, (pad, pad))
        out.append((tile, x - pad, y - pad))
        y += t.height - 14
    return out


def date_card():
    c = Image.new('RGBA', (250, 118), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((0, 0, 249, 117), radius=8, fill=(252, 247, 236, 255))
    d.rounded_rectangle((10, 10, 239, 107), radius=6, outline=(196, 60, 50, 255), width=4)
    d.text((125, 50), '09.26', font=font('Heavy', 54), fill=(196, 60, 50), anchor='mm')
    d.text((125, 90), 'SATURDAY', font=font('Bold', 22), fill=(196, 60, 50), anchor='mm')
    return rotate(c, -6)


def with_shadow(elem, blur=8, alpha=0.3, dx=3, dy=7):
    sh, pad = shadow_of(elem, blur=blur, alpha=alpha)
    out = Image.new('RGBA', (elem.width + 2 * pad + dx, elem.height + 2 * pad + dy), (0, 0, 0, 0))
    out.alpha_composite(sh, (dx, dy))
    out.alpha_composite(elem, (pad, pad))
    return out, pad


def pill(text, size=30, fg=(255, 255, 255), bg=INK, padx=20, h=None, weight='Heavy', dot=None):
    """storyboard render_v2.pill"""
    f = font(weight, size)
    w = int(f.getlength(text) + 2 * padx + (26 if dot else 0))
    h = h or int(size * 1.7)
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=bg)
    x = padx
    if dot:
        d.ellipse((padx - 4, h / 2 - 8, padx + 12, h / 2 + 8), fill=dot)
        x += 26
    d.text((x, h / 2), text, font=f, fill=fg, anchor='lm')
    return im


def edge_at(t):
    """y of the brush edge (before the per-column bristle offsets)"""
    u = prog(t, TB0, TB1)
    return -60 + 2050 * (1 - (1 - u) ** 2.6)


def time_edge_reaches(y):
    """inverse of edge_at"""
    f = (y + 60) / 2050
    u = 1 - (1 - min(max(f, 0), 1)) ** (1 / 2.6)
    return TB0 + u * (TB1 - TB0)


class Brush:
    def __init__(self):
        self.page = to_f(paper(tone=(240, 232, 214), dots=40, seed=41))
        tex = to_f(paper(tone=(255, 250, 238), seed=77, grain=9, blotch=12))
        self.print_tex = (0.82 + 0.18 * tex).astype(np.float32)
        rng = np.random.default_rng(3)
        self.grain = (rng.normal(0, 4.0, (H, W)).astype(np.float32) / 255.0)[..., None]
        m = MARGIN
        self.border = rounded_mask(m, m, W - 2 * m, H - 2 * m, 8)
        self.photo = rounded_mask(m + 14, m + 14, W - 2 * m - 28, H - 2 * m - 28, 4)
        # bristle profile of the brush head (fixed per stroke, as in storyboard shot14b)
        rng = np.random.default_rng(9)
        off = np.zeros(W, np.float32)
        x = 0
        while x < W:
            L = int(rng.integers(3, 10))
            off[x:x + L] = rng.gamma(1.6, 12)
            x += L
        self.off = off + np.linspace(0, 26, W, dtype=np.float32)          # slight slant: right side trails
        self.streak = []                                                   # (x0, L, up, down, colour, alpha)
        x = 0
        while x < W:
            L = int(rng.integers(2, 7))
            col = (250, 244, 228) if rng.random() > 0.2 else (255, 214, 10)
            self.streak.append((x, L, rng.uniform(18, 38), rng.gamma(1.5, 9), col, rng.uniform(150, 235) / 255))
            x += L
        self.band_top = np.zeros(W, np.float32)
        self.band_bot = np.zeros(W, np.float32)
        self.band_col = np.zeros((W, 3), np.float32)
        self.band_a = np.zeros(W, np.float32)
        for x0, L, up, down, col, a in self.streak:
            self.band_top[x0:x0 + L] = -up
            self.band_bot[x0:x0 + L] = down
            self.band_col[x0:x0 + L] = np.array(col, np.float32) / 255
            self.band_a[x0:x0 + L] = a
        # collage stickers (storyboard positions; star moved to the right and the letters 14 px left so both stay
        # outside the face box + 12 px of every frame in segment 15; tape1 moved above the step-bar band y 180-280)
        self.stickers = []
        def add(name, elem, x, y, shadow=True, blur=8, alpha=0.3):
            if shadow:
                e, pad = with_shadow(elem, blur=blur, alpha=alpha)
                self.stickers.append((name, e, x - pad, y - pad))
            else:
                self.stickers.append((name, elem, x, y))
        add('tape1', rotate(tape(190, 46, color=(245, 170, 190), seed=61, stripes=True), -32), -10, 30, shadow=False)
        add('tape2', rotate(tape(170, 44, color=(170, 205, 245), seed=62), 28), -20, 1160, shadow=False)
        add('date_card', date_card(), 56, 372)
        for i, (tile, x, y) in enumerate(cutout_letters('开源剪辑', size=78)):
            self.stickers.append((f'cutout_{i}', tile, 22 + x, 540 + y))
        add('heart', rotate(icon_heart(88), -10), 52, 1086, blur=6)
        add('star', rotate(icon_star(72), 12), 905, 330, blur=6)          # top right: clear of the face box and of the chip's path
        self.tag_after = pill('拼贴包装', size=34, bg=INK + (255,), padx=22, dot=YELLOW)
        self.tag_before = pill('原样', size=34, fg=INK, bg=(255, 255, 255, 235), padx=22)
        chip = photo(Image.open(ASSETS / 'style_collage.jpg').convert('RGBA').resize((88, 118), Image.LANCZOS), border=6, radius=6)
        self.chip, _ = with_shadow(rotate(chip, -8), blur=8, alpha=0.35)
        self.chip_x = W - self.chip.width - 4                 # visible chip starts at x >= 902 (face box + 12 px)
        self.chip_stick_y = 1180                  # edge height at which the chip is left on the page

    def collage(self, raw):
        """storyboard collage_version(): warm, faded print on paper, white border on a dotted page"""
        # printed look kept gentle so the skin stays close to the shot (2026-09-27 rule: 脸保持正常肤色):
        # storyboard values were saturation 0.8, R x1.10 / B x0.80, blacks +22, paper multiply 0.82-1.0
        a = raw * 255.0
        grey = a.mean(2, keepdims=True)
        a = grey + (a - grey) * 0.94
        a = a * np.array([1.035, 1.0, 0.955], np.float32) + np.array([5, 3, 0], np.float32)
        a = 10 + a * 0.96
        a = a * (0.55 + 0.45 * self.print_tex)
        g = np.clip(a / 255.0 + self.grain * 0.7, 0, 1)
        out = self.page.copy()
        out = out * (1 - self.border[..., None]) + np.array(CARD, np.float32) / 255 * self.border[..., None]
        out = out * (1 - self.photo[..., None]) + g * self.photo[..., None]
        return out

    def frame(self, k, src_u8, qa):
        t = k / FPS
        raw = src_u8.astype(np.float32) / 255.0
        boxes = qa.setdefault('boxes', {})
        if t < TB0 - 1e-6 or k > EXIT1:
            qa['layout'] = 'raw'
            return src_u8.copy()
        e = edge_at(t)
        edge = e + self.off                                   # per column
        # the untouched part carries the 「原样」 tag (lower right, below the subtitle band) until the brush covers it
        base = raw.copy()
        if e < 1462 + 60:
            paste_rgba(base, self.tag_before, W - self.tag_before.width - 34, 1462)
            boxes['tag_before'] = [W - self.tag_before.width - 34, 1462, W - 34, 1462 + self.tag_before.height]
        col = self.collage(raw)
        for name, el, x, y in self.stickers:
            top = y + 10
            tr = time_edge_reaches(top)
            if t < tr:
                continue
            sc = pop(t, tr, 0.22, 0.14)
            rgb, a = affine_elem(el, scale=sc, cx=x + el.width / 2, cy=y + el.height / 2)
            over_pm(col, rgb, a)
            boxes[name] = elem_bbox(a)
        # 「拼贴包装」 tag on the packaged part, top left (below the step-bar band)
        ta = time_edge_reaches(340)
        if t >= ta:
            sc = pop(t, ta, 0.22, 0.05)
            rgb, a = affine_elem(self.tag_after, scale=sc, cx=40 + self.tag_after.width / 2, cy=292 + self.tag_after.height / 2)
            over_pm(col, rgb, a)
            boxes['tag_after'] = elem_bbox(a)
        yy = np.arange(H, dtype=np.float32)[:, None]
        mask = np.clip(edge[None, :] - yy + 0.5, 0, 1)
        out = base * (1 - mask[..., None]) + col * mask[..., None]
        if t < TB1 + 0.05:
            # soft shadow just below the wet edge + dry-brush bristle streaks riding the edge
            d = yy - edge[None, :]
            sh = np.clip(1 - np.abs(d - 9) / 7.0, 0, 1) * 0.22
            sh = cv2.GaussianBlur(sh, (0, 0), 3)
            out *= (1 - sh[..., None])
            band = ((d >= self.band_top[None, :]) & (d <= self.band_bot[None, :])).astype(np.float32) * self.band_a[None, :]
            band = cv2.GaussianBlur(band, (0, 0), 0.8)
            out = out * (1 - band[..., None]) + self.band_col[None, :, :] * band[..., None]
            b0 = max(0, int(e - 40)); b1 = min(H - 1, int(e + 80))
            if b1 > b0:
                boxes['brush_band'] = [0, b0, W - 1, b1]
        # the style chip rides the right end of the brush head, then stays on the page
        t_in = time_edge_reaches(600)                          # joins below the star (y 330-420)
        if t >= t_in:
            ey = min(e, self.chip_stick_y) + float(self.off[-60])
            cy = ey - self.chip.height + 12
            slide = e_out(prog(t, t_in, t_in + 0.18), 3)
            cx = lerp(W + 20, self.chip_x, slide)
            paste_rgba(out, self.chip, cx, cy)
            boxes['brush_chip'] = [int(cx) + 8, int(cy) + 8, int(cx) + self.chip.width - 8, int(cy) + self.chip.height - 8]
        # exit: the packaged layer fades off, the last frame is the presenter's untouched frame
        if k >= EXIT0:
            x = e_io(prog(k, EXIT0 - 1, EXIT1))
            out = out * (1 - x) + raw * x
            qa['exit'] = round(x, 3)
        return to_u8(out)


def attach_brush(sh):
    sh.brush = Brush()


def frame14b(self, k, src_u8, qa):
    if not hasattr(self, 'brush'):
        attach_brush(self)
    return self.brush.frame(k, src_u8, qa)


Shot14.frame14b = frame14b
