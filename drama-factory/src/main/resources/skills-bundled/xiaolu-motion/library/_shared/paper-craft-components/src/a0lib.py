"""A0 drawing kit on top of the storyboard's own kit (05_visual/storyboard_v2/src/sb_lib.py, imported read-only, so the
moving version uses the same design as the approved stills): easing, compositing with bbox bookkeeping, the
animated C subtitle strip (sb_lib.subtitle_c geometry + marker brush + keyword pop), the step bar (sb_lib.step_bar
geometry, state changes), the PiP 'whole frame shrinks into the box' transform, face / lip lookup.
"""
import math
import sys
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from a0common import *  # noqa
sys.path.insert(0, str(SB2 / 'src'))
import sb_lib as SB  # noqa: E402  (read-only design kit)
from sb_lib import (INK, PAPER, CARD, KRAFT, YELLOW, RED, GREEN, BLUE, GREY, font, label, vlabel, paper, photo, tape,  # noqa
                    rotate, burst, shadow_of, rrect_mask, icon_check, icon_heart, icon_star, icon_bubble, icon_plus,
                    plain_text, sticker_outline, stamp, pip_card, SUB_CY, PIP_BOX)


# ------------------------------------------------------------------ easing
def clamp01(x):
    return max(0.0, min(1.0, x))


def ease_out_cubic(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t):
    t = clamp01(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_back(t, s=1.70158):
    t = clamp01(t)
    c3 = s + 1
    return 1 + c3 * (t - 1) ** 3 + s * (t - 1) ** 2


def ease_in_cubic(t):
    t = clamp01(t)
    return t ** 3


def pop_curve(k, grow=4, settle=9, peak=1.08):
    """scale factor for a keyword / sticker pop k frames after its onset: 1 -> peak (grow) -> 1 (settle)"""
    if k < 0:
        return 1.0
    if k < grow:
        return 1 + (peak - 1) * ease_out_cubic((k + 1) / grow)
    if k < settle:
        return peak - (peak - 1) * ease_in_out_cubic((k - grow) / (settle - grow))
    return 1.0


def slam_curve(k, frames=5, start=1.9):
    """scale for an element slamming onto the page, landing exactly at k == frames (then a small rebound)"""
    if k < 0:
        return None
    if k < frames:
        return start - (start - 1) * ease_in_cubic((k + 1) / frames) if k + 1 < frames else 1.0
    r = k - frames
    return 1 + 0.06 * math.exp(-r / 2.2) * math.cos(r * 1.9) if r < 10 else 1.0


# ------------------------------------------------------------------ faces
@lru_cache(maxsize=1)
def _faces():
    d = load_json(WORK / 'faces_v2.json')
    fr = {int(k): v for k, v in d['frames'].items()}
    return fr, sorted(fr)


def face_at(f):
    """Vision face / lip boxes at v2 frame f, linearly interpolated between the sampled frames (every 3rd)"""
    fr, keys = _faces()
    import bisect
    i = bisect.bisect_left(keys, f)
    if i < len(keys) and keys[i] == f:
        v = fr[f]
        return tuple(v['face']), tuple(v['lips'])
    a = keys[max(0, i - 1)]
    b = keys[min(len(keys) - 1, i)]
    if a == b or abs(b - a) > 12:
        v = fr[a if abs(f - a) <= abs(b - f) else b]
        return tuple(v['face']), tuple(v['lips'])
    w = (f - a) / (b - a)
    lerp = lambda p, q: tuple(int(round(x + (y - x) * w)) for x, y in zip(p, q))
    return lerp(fr[a]['face'], fr[b]['face']), lerp(fr[a]['lips'], fr[b]['lips'])


def face_union(f0, f1):
    fr, keys = _faces()
    vs = [fr[k] for k in keys if f0 <= k < f1]
    return (min(v['face'][0] for v in vs), min(v['face'][1] for v in vs), max(v['face'][2] for v in vs),
            max(v['face'][3] for v in vs))


# ------------------------------------------------------------------ compositing with bookkeeping
class Canvas:
    """RGBA working frame + list of placed items (name, bbox, kind) for the per-frame QA"""

    def __init__(self, rgb):
        self.img = Image.fromarray(rgb).convert('RGBA') if isinstance(rgb, np.ndarray) else rgb.convert('RGBA')
        self.items = []

    def put(self, elem, x, y, name, kind='overlay', shadow=True, blur=12, salpha=0.30, anchor='tl', alpha=1.0):
        if elem is None:
            return None
        if anchor == 'c':
            x, y = x - elem.width / 2, y - elem.height / 2
        x, y = int(round(x)), int(round(y))
        if alpha < 1.0:
            elem = elem.copy()
            elem.putalpha(elem.split()[3].point(lambda v: int(v * alpha)))
        if shadow:
            sh, pad = shadow_of(elem, blur=blur, alpha=salpha)
            self._paste(sh, x - pad + 3, y - pad + 7)
        self._paste(elem, x, y)
        a = np.asarray(elem.split()[3])
        ys, xs = np.where(a > 40)
        if len(xs):
            bb = (x + int(xs.min()), y + int(ys.min()), x + int(xs.max()), y + int(ys.max()))
            self.items.append((name, bb, kind))
            return bb
        return None

    def layer(self, lay, name, kind='fx'):
        self.img.alpha_composite(lay)
        a = np.asarray(lay.split()[3])
        ys, xs = np.where(a > 40)
        if len(xs):
            self.items.append((name, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())), kind))

    def _paste(self, elem, x, y):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + elem.width), min(H, y + elem.height)
        if x1 <= x0 or y1 <= y0:
            return
        self.img.alpha_composite(elem.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))

    def rgb(self):
        return np.asarray(self.img.convert('RGB'))


def scaled(elem, s, rot=0.0):
    if elem is None or s is None or s <= 0.01:
        return None
    im = elem
    if abs(s - 1) > 1e-3:
        im = elem.resize((max(1, int(elem.width * s)), max(1, int(elem.height * s))), Image.LANCZOS)
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    return im


# ------------------------------------------------------------------ PiP: the whole frame shrinks into the box
PIP_CONTENT = (PIP_BOX[0] + 12, PIP_BOX[1] + 12, PIP_BOX[2] - 12, PIP_BOX[3] - 12)   # 738,858,1038,1278 (300x420)


def pip_region(face):
    """source crop shown in the PiP (sb_lib.pip_crop geometry): 900x1260 around the face, head room above"""
    cw, ch = 900, 1260
    cx = (face[0] + face[2]) / 2
    x0 = int(min(max(0, cx - cw / 2), W - cw))
    head_top = face[1] - 0.22 * (face[3] - face[1])
    y0 = int(min(max(0, head_top - 70), H - ch))
    return (x0, y0, x0 + cw, y0 + ch)


def pip_layer(rgb, p, region, card_alpha=None):
    """p = 0: full frame; p = 1: the region sits in the PiP content rect (card + tape fade in over the last 40 %).
    Returns an RGBA canvas-size layer (transparent outside the moving rounded window)."""
    p = clamp01(p)
    x0, y0, x1, y1 = region
    s1 = (PIP_CONTENT[2] - PIP_CONTENT[0]) / (x1 - x0)
    s = 1 + (s1 - 1) * p
    # the region's top-left moves from its own place to the content rect's top-left
    tx = (PIP_CONTENT[0] - x0 * s1) * p
    ty = (PIP_CONTENT[1] - y0 * s1) * p
    M = np.float32([[s, 0, tx], [0, s, ty]])
    src = rgb if isinstance(rgb, np.ndarray) else np.asarray(rgb.convert('RGB'))
    warped = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_AREA if s < 0.8 else cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT)
    # visible window: full canvas -> content rect, corner radius 0 -> 22
    wx0 = 0 + (PIP_CONTENT[0] - 0) * p
    wy0 = 0 + (PIP_CONTENT[1] - 0) * p
    wx1 = W + (PIP_CONTENT[2] - W) * p
    wy1 = H + (PIP_CONTENT[3] - H) * p
    r = 22 * p
    mask = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((wx0, wy0, wx1 - 1, wy1 - 1), radius=r, fill=255)
    lay = Image.fromarray(warped).convert('RGBA')
    lay.putalpha(mask)
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ca = clamp01((p - 0.6) / 0.4) if card_alpha is None else card_alpha
    if ca > 0:
        card = _pip_frame()
        c2 = card.copy()
        c2.putalpha(c2.split()[3].point(lambda v: int(v * ca)))
        sh, pad = shadow_of(c2, blur=14, alpha=0.35 * ca)
        out.alpha_composite(sh, (PIP_BOX[0] - pad + 3, PIP_BOX[1] - 22 - pad + 7))
        out.alpha_composite(c2, (PIP_BOX[0], PIP_BOX[1] - 22))
    out.alpha_composite(lay)
    # the presenter's face inside the moved frame (for QA): map the full-frame face box
    return out, (s, tx, ty)


@lru_cache(maxsize=1)
def _pip_frame():
    """pip_card look (white card, washi tape) with a transparent hole where the content goes"""
    blank = Image.new('RGBA', (300, 420), (0, 0, 0, 0))
    card = pip_card(blank)
    return card


def map_box(b, st):
    s, tx, ty = st
    return (int(b[0] * s + tx), int(b[1] * s + ty), int(b[2] * s + tx), int(b[3] * s + ty))


# ------------------------------------------------------------------ C subtitle strip (sb_lib.subtitle_c geometry)
SUB_SIZE = 66


def _runs_of(markup):
    runs, cur, key = [], '', False
    for ch in markup:
        if ch == '[':
            if cur:
                runs.append((cur, key))
            cur, key = '', True
        elif ch == ']':
            runs.append((cur, True))
            cur, key = '', False
        else:
            cur += ch
    if cur:
        runs.append((cur, key))
    return runs


def strip_geometry(markup):
    fN, fK = font('Medium', SUB_SIZE), font('Heavy', SUB_SIZE)
    runs = _runs_of(markup)
    chars = []
    for ri, (t, k) in enumerate(runs):
        for ch in t:
            chars.append((ch, k, ri))
    xs, x = [], 0.0
    for i, (ch, k, ri) in enumerate(chars):
        xs.append(x)
        x += (fK if k else fN).getlength(ch) + (2 if i < len(chars) - 1 else 0)
    tw = x
    padx, pady = 30, 20
    x0 = W / 2 - tw / 2
    baseline = SUB_CY + 24
    top, bottom = baseline - 60 - pady, baseline + 12 + pady
    box = (x0 - padx, top, x0 + tw + padx, bottom)
    # keyword runs in order of appearance -> (i0, i1) char ranges
    kr = []
    i = 0
    while i < len(chars):
        if chars[i][1]:
            j = i
            while j + 1 < len(chars) and chars[j + 1][1] and chars[j + 1][2] == chars[i][2]:
                j += 1
            kr.append((i, j))
            i = j + 1
        else:
            i += 1
    return chars, xs, tw, x0, baseline, box, kr


@lru_cache(maxsize=4096)
def strip_image(markup, marks, pops):
    """RGBA of the whole strip on a local canvas + its canvas offset.
    marks: tuple of marker progress 0..1 per keyword run; pops: tuple of scale per keyword run."""
    fN, fK = font('Medium', SUB_SIZE), font('Heavy', SUB_SIZE)
    chars, xs, tw, x0, baseline, box, kr = strip_geometry(markup)
    M = 40                                                     # margin for shadow / popping keywords
    bx0, by0 = int(box[0]) - M, int(box[1]) - M
    Wl, Hl = int(box[2] - box[0]) + 2 * M, int(box[3] - box[1]) + 2 * M
    lay = Image.new('RGBA', (Wl, Hl), (0, 0, 0, 0))
    strip = Image.new('RGBA', (Wl, Hl), (0, 0, 0, 0))
    ImageDraw.Draw(strip).rounded_rectangle((box[0] - bx0, box[1] - by0, box[2] - bx0, box[3] - by0), radius=16,
                                            fill=(255, 255, 255, 245))
    soft = strip.split()[3].filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.35))
    sh = Image.new('RGBA', (Wl, Hl), (0, 0, 0, 0))
    sh.putalpha(soft)
    lay.alpha_composite(sh, (0, 6))
    lay.alpha_composite(strip)
    d = ImageDraw.Draw(lay)
    # marker blocks (brushed left -> right)
    for n, (i0, i1) in enumerate(kr):
        pr = marks[n] if n < len(marks) else 1.0
        if pr <= 0:
            continue
        kx0 = x0 + xs[i0] - 6
        kx1 = x0 + xs[i1] + fK.getlength(chars[i1][0]) + 6
        xe = kx0 + (kx1 - kx0) * pr
        d.rectangle((kx0 - bx0, baseline - 30 - by0, xe - bx0, baseline + 8 - by0), fill=YELLOW)
    popping = {n for n, s in enumerate(pops) if abs(s - 1) > 1e-3}
    in_pop = {}
    for n, (i0, i1) in enumerate(kr):
        for i in range(i0, i1 + 1):
            in_pop[i] = n
    for i, ((ch, k, ri), cx_) in enumerate(zip(chars, xs)):
        if in_pop.get(i) in popping:
            continue
        d.text((x0 + cx_ - bx0, baseline - by0), ch, font=fK if k else fN, fill=(20, 20, 20), anchor='ls')
    for n in popping:
        i0, i1 = kr[n]
        s = pops[n]
        kx0 = x0 + xs[i0]
        kx1 = x0 + xs[i1] + fK.getlength(chars[i1][0])
        wk, hk = int(kx1 - kx0) + 8, SUB_SIZE + 30
        kl = Image.new('RGBA', (wk, hk), (0, 0, 0, 0))
        kd = ImageDraw.Draw(kl)
        for i in range(i0, i1 + 1):
            kd.text((xs[i] - xs[i0] + 4, hk - 14), chars[i][0], font=fK, fill=(20, 20, 20), anchor='ls')
        ax, ay = wk / 2, hk - 39                              # glyph visual centre inside kl
        cxk, cyk = kx0 - 4 + ax, baseline - 25                # ... and on the canvas (unscaled)
        kl = kl.resize((int(wk * s), int(hk * s)), Image.LANCZOS)
        lay.alpha_composite(kl, (int(round(cxk - ax * s - bx0)), int(round(cyk - ay * s - by0))))
    return lay, (bx0, by0), box


def strip_state(row, f):
    """marker progress / pop scale per keyword for caption row at frame f"""
    marks, pops = [], []
    for k in row['keywords']:
        kf = k['f0']                                   # frame that contains the spoken onset
        bf = k['brush_frames']
        marks.append(round(clamp01((f - kf + 1) / bf), 3) if f >= kf else 0.0)     # linear brush, as shot 16 (A3)
        pops.append(round(pop_curve(f - kf), 3))
    return tuple(marks), tuple(pops)


# ------------------------------------------------------------------ step bar (sb_lib.step_bar geometry)
STEPS = SB.STEPS


@lru_cache(maxsize=64)
def step_bar_image(active, done, lit):
    """lit: how many cells are lit (entrance), 4 = all"""
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
        on = n <= lit
        col = INK if (n == active or n in done) else ((140, 134, 124) if on else (206, 200, 190))
        f_ = fH if n == active else fB
        txt = f'{n} {name}'
        d.text((x0 + seg / 2 + (10 if n in done else 0), h / 2), txt, font=f_, fill=col, anchor='mm')
        if n in done:
            c = icon_check(34, color=GREEN, lw=9)
            bar.alpha_composite(c, (int(x0 + seg / 2 - f_.getlength(txt) / 2 - 36), 15))
        if i:
            d.line((x0, 16, x0, h - 16), fill=(210, 203, 190), width=2)
    sh, pad = shadow_of(bar, blur=8, alpha=0.22)
    out = Image.new('RGBA', (sh.width, sh.height), (0, 0, 0, 0))
    out.alpha_composite(sh, (3, 7))
    out.alpha_composite(bar, (pad, pad))
    return out, pad


STEP_X, STEP_Y = (W - 900) // 2, 196
