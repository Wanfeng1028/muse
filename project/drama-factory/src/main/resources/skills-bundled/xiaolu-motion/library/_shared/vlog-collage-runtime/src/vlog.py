"""vlog.py — 20–30 s 拼贴手账 vlog demo: timeline + renderer.

  python3 vlog.py test 3.2 7.1 ...       # render single frames -> ../work/test_<t>.png
  python3 vlog.py render                  # full render (parallel) -> ../work/video_noaudio.mp4
                                          #   + filmstrip frames every 0.2 s + text bbox log

Timing: BGM 120 BPM, video t = music t - 2.03 s, so every beat lands on a whole frame
(beat k at 0.5 + 0.5k s = frame 15 + 15k); downbeats at 0.5, 2.5, 4.5 ... Main cuts sit on
downbeats, jump cuts on beats, sticker pops on beats / 8th notes.
"""
import functools
import json
import math
import os
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw

import collage as C
import engine as E
from engine import W, H, FPS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, 'work')
CLIPS = {k.replace('IMG_', ''): v for k, v in json.load(open(os.path.join(WORK, 'clips.json'))).items()}
# the sunset plays at 0.8x (slow pan up, away from a parked car): use a 60 fps proxy for smooth motion
if os.path.exists(os.path.join(ROOT, 'proxy', 'IMG_1082_60.mp4')):
    CLIPS['1082'] = dict(CLIPS['1082'], proxy=os.path.join(ROOT, 'proxy', 'IMG_1082_60.mp4'), proxy_fps=60)
DUR = 29.0
NFR = int(round(DUR * FPS))
MUSIC_OFFSET = 2.03          # music time = video time + 2.03 (see bgm_pick / audio.py)
TEXT_ROLES = ('sub', 'emph', 'card', 'note', 'title', 'stamp')


def clock(cid):
    return CLIPS[cid]['clock']


# ============================================================ assets (lazy, per process)
_assets = {}


def asset(key):
    if key not in _assets:
        fn, args = BUILDERS[key]
        _assets[key] = fn(*args)
    return _assets[key]


def spr_of(img):
    return E.to_spr(img)


def shadow_pad(blur, dx, dy):
    return int(blur * 2 + max(abs(dx), abs(dy)) + 2)


def b_polaroid(pw, ph, border=22, bottom=96, caption=None, seed=7, color=(252, 250, 244), sh=(16, 3, 11, 0.36)):
    cw, ch = pw + 2 * border, ph + border + bottom
    card = C.paper(cw, ch, color, seed=seed, fiber=0.6, blotch=0.5)
    d = ImageDraw.Draw(card)
    d.rectangle([border - 1, border - 1, border + pw, border + ph], outline=(0, 0, 0, 30), width=1)
    if caption:
        t = C.text_layer(caption, C.font('kai', int(min(48, bottom * 0.5))), fill=C.INK + (255,), padding=2)
        card.alpha_composite(t, (border + 8, border + ph + (bottom - t.height) // 2))
    p = shadow_pad(sh[0], sh[1], sh[2])
    img = C.shadow(card, *sh)
    return spr_of(img), (p + border, p + border, pw, ph, None)


def b_torn_print(w, h, edges='tb', amp=12, rim=8, inset=10, seed=3, sh=(18, 2, 12, 0.4)):
    sheet = C.torn_sheet(w, h, (252, 250, 244), seed=seed, edges=edges, amp=amp, rim=rim)
    core = (sheet.core > 0.5).astype(np.uint8)
    if inset > 0:
        core = cv2.erode(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * inset + 1, 2 * inset + 1)))
    m = cv2.GaussianBlur(core.astype(np.float32), (0, 0), 0.8)
    p = shadow_pad(sh[0], sh[1], sh[2])
    img = C.shadow(sheet, *sh)
    mask = np.zeros((img.height, img.width), np.float32)
    mask[p:p + m.shape[0], p:p + m.shape[1]] = m
    ys, xs = np.nonzero(mask > 0.01)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    return spr_of(img), (int(x0), int(y0), int(x1 - x0), int(y1 - y0), mask[y0:y1, x0:x1].copy())


def b_strip(w, h, seed, amp=14, rim=9, inset=9):
    return b_torn_print(w, h, 'tb', amp, rim, inset, seed, sh=(14, 0, 10, 0.42))


def b_page(kind, seed=1):
    if kind == 'navy':
        img = C.paper(W, H, (36, 42, 86), seed=seed, fiber=0.8)
        d = ImageDraw.Draw(img)
        r = C.rng(seed)
        for _ in range(70):
            x, y = r.uniform(30, W - 30), r.uniform(30, H - 30); s = r.uniform(1.2, 3.2)
            d.ellipse([x - s, y - s, x + s, y + s], fill=(250, 238, 200, int(r.uniform(90, 200))))
        for (x, y, s) in [(160, 180, 34), (930, 520, 26), (120, 1320, 30), (980, 1500, 24), (560, 150, 20), (90, 760, 18)]:
            st = C.icon('sparkle', s, (250, 232, 180, 230))
            img.alpha_composite(st, (int(x - s / 2), int(y - s / 2)))
    elif kind == 'kraft':
        img = C.paper(W, H, (219, 193, 152), seed=seed, fiber=1.4, blotch=1.3)
    else:
        img = C.paper(W, H, (248, 243, 232), seed=seed)
        d = ImageDraw.Draw(img)
        if kind == 'dot':
            for y in range(40, H, 40):
                for x in range(40, W, 40):
                    d.ellipse([x - 1.7, y - 1.7, x + 1.7, y + 1.7], fill=(170, 150, 125, 80))
        elif kind == 'grid':
            for x in range(0, W, 54):
                d.line([(x, 0), (x, H)], fill=(150, 175, 190, 60), width=1)
            for y in range(0, H, 54):
                d.line([(0, y), (W, y)], fill=(150, 175, 190, 60), width=1)
        elif kind == 'ruled':
            for y in range(150, H, 66):
                d.line([(0, y), (W, y)], fill=(140, 175, 205, 90), width=2)
            d.line([(118, 0), (118, H)], fill=(222, 120, 120, 110), width=2)
            d.line([(124, 0), (124, H)], fill=(222, 120, 120, 70), width=1)
    a = np.asarray(img.convert('RGB'), np.float32) / 255.0
    return a


def still(cid, t):
    c = CLIPS[cid]; w, h = c['proxy_size']
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', c['proxy'], '-frames:v', '1',
                          '-vf', 'scale=in_color_matrix=bt709:in_range=limited,format=rgb24', '-f', 'rawvideo', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3)


def b_still_card(cid, t, pw, ph, border=14, bottom=None, fx=0.5, fy=0.5, zoom=1.0, seed=9):
    spr, (x, y, ww, wh, _) = b_polaroid(pw, ph, border, bottom if bottom is not None else border, None, seed,
                                        sh=(10, 2, 7, 0.36))
    ph_ = E.grade(E.cover(still(cid, t), ww, wh, fx, fy, zoom))
    spr = spr.copy(); spr[y:y + wh, x:x + ww, :3] = ph_; spr[y:y + wh, x:x + ww, 3] = 1
    return spr


def b_sticker_text(txt, size, fill, keyline=None, edge=12, fontname='hei_heavy'):
    return spr_of(C.sticker_text(txt, C.font(fontname, size), fill=fill, edge=edge, keyline=keyline))


def b_strip_text(txt, size=58, seed=17, color=(252, 250, 244)):
    t = C.text_layer(txt, C.font('hei_heavy', size), fill=C.INK_D + (255,), padding=2)
    strip = C.torn_sheet(t.width + 64, t.height + 40, color, seed=seed, edges='tb', amp=5, rim=4)
    strip.alpha_composite(t, ((strip.width - t.width) // 2, (strip.height - t.height) // 2 + 1))
    return spr_of(C.shadow(strip, 9, 0, 6, 0.4))


def b_img(fn, *a, **k):
    return spr_of(fn(*a, **k))


def b_icon_sticker(kind, size, color, edge=8, accent=None):
    return spr_of(C.sticker(C.icon(kind, size, color, accent=accent), edge, sh=(8, 1, 5, 0.32)))


def b_icon(kind, size, color):
    return spr_of(C.pad(C.icon(kind, size, color), 4))


def b_washi(w, h, color, pattern, seed, alpha=0.84):
    return spr_of(C.washi(w, h, color, alpha, pattern, seed=seed))


def b_moon():
    D = 190
    base = C.paper(D, D, (250, 236, 190), seed=77, fiber=0.6)
    m = Image.new('L', (D * 3, D * 3), 0); d = ImageDraw.Draw(m)
    d.ellipse([0, 0, D * 3 - 1, D * 3 - 1], fill=255)
    d.ellipse([D * 0.9, -D * 0.35, D * 3.4, D * 2.1], fill=0)
    base = C.with_mask(base, m.resize((D, D), Image.LANCZOS))
    return spr_of(C.sticker(base, 9, sh=(12, 2, 8, 0.45)))


def b_arrow(w, h, color, flip=False, seed=3, bend=0.4, halo=False):
    a = C.curved_arrow(w, h, color, 6, seed=seed, bend=bend)
    if flip == 'rot180':
        a = a.transpose(Image.ROTATE_180)
    elif flip:
        a = a.transpose(Image.FLIP_LEFT_RIGHT)
    a = C.pad(a, 6)
    if halo:
        a = C.shadow(a, 4, 0, 2, 0.7, color=(20, 14, 10))
    return spr_of(a)


BUILDERS = {}


def reg(key, fn, *args):
    BUILDERS[key] = (fn, args)
    return key


# ============================================================ elements & pages
class El:
    def __init__(self, key, at, t1, x, y, rot=0.0, sc=1.0, z=10, enter='pop', ed=None, exit='none', xd=0.14,
                 boil=True, role='deco', label='', media=None, sfx=None, anim=None, alpha=1.0, spin=None):
        lead = {'pop': 0.135, 'drop': 0.125, 'stamp': 0.12, 'slap': 0.06, 'spin': 0.16, 'write': 0.0,
                'none': 0.0, 'slide_up': 0.1, 'rise': 0.1, 'flipin': 0.1}[enter]
        self.ed = ed if ed is not None else {'pop': 0.24, 'drop': 0.3, 'stamp': 0.12, 'slap': 0.14, 'spin': 0.34,
                                               'write': 0.45, 'none': 0.0, 'slide_up': 0.3, 'rise': 0.3, 'flipin': 0.22}[enter]
        self.key, self.at, self.t0, self.t1 = key, at, at - lead, t1
        self.x, self.y, self.rot, self.sc, self.z = x, y, rot, sc, z
        self.enter, self.exit, self.xd, self.boil = enter, exit, xd, boil
        self.role, self.label, self.media, self.sfx = role, label, media, sfx or []
        self.anim, self.alpha, self.spin = anim, alpha, spin

    def state(self, t):
        if t < self.t0 or t >= self.t1:
            return None
        x, y, rot, sc, al, sx = self.x, self.y, self.rot, self.sc, self.alpha, 1.0
        q = (t - self.t0) / self.ed if self.ed > 0 else 1.0
        e = self.enter
        if e == 'pop':
            sc *= max(0.0, E.back_out(q, 1.9)); rot += (1 - E.c01(q)) * (self.spin if self.spin is not None else 14)
        elif e == 'drop':
            y -= (1 - E.back_out(q, 1.4)) * 700; rot += (1 - E.c01(q)) * (self.spin if self.spin is not None else -10)
        elif e == 'stamp':
            k = E.c01(q)
            sc *= 1 + 0.85 * (1 - k * k); al *= min(1.0, 0.25 + k)
            if q > 1:
                sc *= 1 - 0.05 * max(0.0, 1 - (q - 1) * self.ed / 0.08)
        elif e == 'slap':
            sc *= 1 + 0.3 * (1 - E.expo_out(q)); al *= E.c01(q * 3); rot += (1 - E.expo_out(q)) * 4
        elif e == 'spin':
            sc *= 0.35 + 0.65 * E.back_out(q, 1.5); rot += (1 - E.expo_out(q)) * (self.spin if self.spin is not None else -38)
        elif e in ('slide_up', 'rise'):
            y += (1 - E.expo_out(q)) * 900
        elif e == 'flipin':
            sx = max(0.02, E.back_out(q, 1.4))
        if self.exit == 'pop' and t > self.t1 - self.xd:
            qx = (t - (self.t1 - self.xd)) / self.xd
            sc *= max(0.0, 1 - E.back_in(qx, 1.6))
        if self.anim:
            dx, dy, dr, ds = self.anim(t)
            x += dx; y += dy; rot += dr; sc *= ds
        if self.boil:
            b = int(math.floor(t * E.BOIL_HZ))
            x += (E.hrand(self.key, self.x, b, 1) - 0.5) * 2.6
            y += (E.hrand(self.key, self.y, b, 2) - 0.5) * 2.6
            rot += (E.hrand(self.key, b, 3) - 0.5) * 1.1
        return x, y, rot, sc, al, sx, q

    def render(self, canvas, t, ctx):
        st = self.state(t)
        if st is None:
            return None
        x, y, rot, sc, al, sx, q = st
        if self.media is not None:
            spr = self.media_sprite(t, ctx)
            if spr is None:
                return None
        else:
            spr = asset(self.key)
            if self.enter == 'write':
                spr = E.reveal(spr, q)
        return E.draw(canvas, spr, x, y, rot, sc, al, sx)

    def media_sprite(self, t, ctx):
        m = self.media
        tpl, win = asset(self.key)
        x, y, ww, wh, mask = win
        frame = ctx.frame(m['clip'], media_src_time(m, t))
        fx, fy, z = media_look(m, t)
        ph = E.grade(E.cover(frame, ww, wh, fx, fy, z))
        if m.get('gain'):
            ph = np.clip(ph * m['gain'], 0, 1)
        if m.get('defocus'):
            seg_i, frac, sig = m['defocus']
            cur, _ = media_seg(m, t)
            if m['segs'].index(cur) >= seg_i:
                ramp = np.clip((np.arange(ww, dtype=np.float32) - ww * frac) / 70.0, 0, 1)[None, :, None]
                ph = ph * (1 - ramp) + cv2.GaussianBlur(ph, (0, 0), sig) * ramp
        spr = tpl.copy()
        reg_ = spr[y:y + wh, x:x + ww]
        if mask is None:
            reg_[..., :3] = ph; reg_[..., 3] = 1.0
        else:
            mm = mask[..., None]
            reg_[..., :3] = reg_[..., :3] * (1 - mm) + ph * mm
            reg_[..., 3:4] = reg_[..., 3:4] * (1 - mm) + mm
        return spr


def media_seg(m, t):
    if m.get('freeze') is not None:
        t = min(t, m['freeze'])
    cur = m['segs'][0]
    for sg in m['segs']:
        if t >= sg[0]:
            cur = sg
    return cur, t


def media_src_time(m, t):
    cur, t = media_seg(m, t)
    return max(0.0, cur[1] + (t - cur[0]) * m.get('rate', 1.0))


def media_look(m, t):
    """focus-y and zoom for the active segment: segs may be (t, src) or (t, src, fy, zoom)"""
    cur, _ = media_seg(m, t)
    fy = cur[2] if len(cur) > 2 else m.get('fy', 0.5)
    z = cur[3] if len(cur) > 3 else m.get('zoom', 1.0)
    if callable(z):
        z = z(t)
    return m.get('fx', 0.5), fy, z


class Page:
    def __init__(self, name, t0, t1, bg, trans='cut', tdur=0.3, els=None, full=None):
        self.name, self.t0, self.t1, self.bg, self.trans, self.tdur = name, t0, t1, bg, trans, tdur
        self.els = els or []
        self.full = full          # full-bleed media dict (drawn right after the paper)
        for el in self.els:       # main prints ride in with the page during its transition
            if el.enter == 'none' and abs(el.t0 - t0) < 1e-6:
                el.t0 = t0 - tdur

    def render(self, t, ctx, log=None):
        canvas = ctx.bg(self.bg).copy()
        if self.full is not None:
            m = self.full
            fx, fy, z = media_look(m, t)
            fr = ctx.frame(m['clip'], media_src_time(m, t))
            canvas[:] = E.grade(E.cover(fr, W, H, fx, fy, z))
        for el in sorted(self.els, key=lambda e: e.z):
            bb = el.render(canvas, t, ctx)
            if bb is not None and log is not None and el.role in TEXT_ROLES:
                log.append((self.name, el.role, el.label, [int(v) for v in bb]))
        return canvas


class Ctx:
    def __init__(self):
        self.readers = {}; self.bgs = {}

    def frame(self, cid, src_t):
        c = CLIPS[cid]
        fps = c.get('proxy_fps', FPS)
        if cid not in self.readers:
            self.readers[cid] = E.Reader(c['proxy'], *c['proxy_size'], fps=fps)
        idx = int(round(min(src_t, c['duration'] - 0.05) * fps))
        return self.readers[cid].get(idx)

    def bg(self, kind):
        if kind not in self.bgs:
            self.bgs[kind] = b_page(kind, seed={'dot': 1, 'grid': 2, 'kraft': 3, 'ruled': 4, 'navy': 5}[kind])
        return self.bgs[kind]

    def close(self):
        for r in self.readers.values():
            r.close()


# ============================================================ timeline helpers
SUB_Y = 1530


def zoom_jump(t_jump, k=1.05, t0=None, t1=None, drift=(0.0, -8.0, 0.6, 0.02)):
    """jump-cut accent (scale step at the cut) + a slow hand-held drift across the page"""
    def f(t):
        q = E.c01((t - t0) / (t1 - t0)) if t0 is not None else 0.0
        dx, dy, dr, ds = drift
        return dx * q, dy * q, dr * q, (k if t >= t_jump else 1.0) * (1 + ds * q)
    return f


def opaque_x(spr, thr=0.5):
    """x-extent of the solid (die-cut) part of a sprite, ignoring its soft shadow"""
    cols = np.nonzero((spr[..., 3] > thr).any(axis=0))[0]
    return int(cols[0]), int(cols[-1]) + 1


def subtitle(name, parts, at, t_end, y=SUB_Y, emph_at=None, emph_step=0.125, emph_color=C.RED, size=68, esize=90,
             style='die', seed=1, sfx_note='C#6'):
    """贴纸字幕: `parts` = list of (text, is_emphasis). Normal parts pop together at `at`; emphasis
    parts pop per character from `emph_at` (16th / 8th notes) bigger, coloured, with a keyline."""
    els = []
    specs = []
    for i, (txt, em) in enumerate(parts):
        if em:
            for j, ch in enumerate(txt):
                k = reg(f'{name}_e{i}_{j}', b_sticker_text, ch, esize, emph_color + (255,), (C.INK_D + (255,), 5), 13)
                specs.append((k, True))
        else:
            if style == 'strip':
                k = reg(f'{name}_n{i}', b_strip_text, txt, size, seed + i)
            else:
                k = reg(f'{name}_n{i}', b_sticker_text, txt, size, C.INK_D + (255,), None, 12)
            specs.append((k, False))
    # lay out on the solid extents so neighbouring die-cut edges just overlap (reads as one sticker)
    ext = [opaque_x(asset(k)) for k, _ in specs]
    gaps = [(-14 if (a[1] and b[1]) else -8) for a, b in zip(specs[:-1], specs[1:])]
    total = sum(r - l for l, r in ext) + sum(gaps)
    x = W / 2 - total / 2
    ei = 0
    emph_at = emph_at if emph_at is not None else at + 0.25
    for idx, ((k, em), (l, r)) in enumerate(zip(specs, ext)):
        w = asset(k).shape[1]
        cx = x - l + w / 2
        if em:
            t_e = emph_at + ei * emph_step
            els.append(El(k, t_e, t_end, cx, y - 4, rot=(-5 if ei % 2 == 0 else 4), z=62 + ei, role='emph', label=k,
                          exit='pop', sfx=[('pop_soft', t_e, {'pitch': 3 + 2 * ei}), ('pluck', t_e, {'note': sfx_note})]))
            ei += 1
        else:
            els.append(El(k, at, t_end, cx, y, rot=0, z=60, role='sub', label=k, exit='pop',
                          sfx=[('pop_soft', at, {'pitch': 0})]))
        x += (r - l) + (gaps[idx] if idx < len(gaps) else 0)
    return els


def card(kind, key, at, t_end, x, y, rot, *args):
    if kind == 'time':
        reg(key, b_img, C.time_card, *args)
    elif kind == 'weather':
        reg(key, b_img, C.weather_card, *args)
    elif kind == 'mood':
        reg(key, b_img, C.mood_card, *args)
    return El(key, at, t_end, x, y, rot=rot, sc=1.2, z=70, role='card', label=key, exit='pop',
              sfx=[('pop_soft', at, {'pitch': 5})])


def b_note(text, size, color, under, halo):
    img = C.handwrite(text, size, color, under)
    if halo:   # white ink on a photo: soft dark halo keeps it readable
        img = C.shadow(C.pad(img, 8), 6, 0, 2, 0.9, color=(20, 14, 10))
    return spr_of(img)


def note(key, text, at, t_end, x, y, rot=-4, size=56, color=C.INK + (255,), under=None, z=66, halo=False):
    reg(key, b_note, text, size, color, under, halo)
    return El(key, at, t_end, x, y, rot=rot, z=z, role='note', label=key, enter='write', boil=False, exit='pop',
              sfx=[('scribble', at, {'dur': 0.4})])


def deco(key, builder, args, at, t_end, x, y, rot=0, z=40, enter='pop', exit='pop', sfx=True, spin=None, boil=True):
    reg(key, builder, *args)
    return El(key, at, t_end, x, y, rot=rot, z=z, enter=enter, exit=exit, boil=boil, spin=spin,
              sfx=[('pop_soft', at, {'pitch': 7, 'gain_db': -4})] if sfx else [])


def tape(key, at, t_end, x, y, rot, w=150, h=44, color=C.MUSTARD, pattern='stripe', seed=2, z=45, sfx=False):
    reg(key, b_washi, w, h, color, pattern, seed)
    return El(key, at, t_end, x, y, rot=rot, z=z, enter='slap', ed=0.12, exit='none', boil=False,
              sfx=[('tape', at, {})] if sfx else [])


# ============================================================ the timeline
def build():
    P = []

    # ---------------------------------------------------------------- P0 title (0 – 2.5)
    reg('p0_cat', b_polaroid, 430, 573, 22, 92, None, 11)
    reg('p0_sunset', b_still_card, '1082', 1.9, 300, 533, 16, None, 0.5, 0.5, 1.0, 12)
    reg('p0_drink', b_still_card, '9596', 5.8, 300, 400, 16, None, 0.5, 0.45, 1.0, 13)
    els = [
        El('p0_cat', 0.0, 2.5, 330, 520, rot=-7, z=20, enter='drop', boil=False, role='media',
           media={'clip': '0083', 'segs': [(0.0, 0.3)], 'fy': 0.5},
           sfx=[('land', 0.0, {'gain_db': -6})]),
        El('p0_sunset', 0.25, 2.5, 810, 500, rot=6, z=21, enter='drop', boil=False, role='deco',
           sfx=[('pop_soft', 0.25, {'pitch': 2})]),
        El('p0_drink', 0.375, 2.5, 255, 1505, rot=7, z=22, enter='drop', boil=False, role='deco',
           sfx=[('pop_soft', 0.375, {'pitch': 4})]),
        tape('p0_t1', 0.3, 2.5, 330, 222, -4, 170, 46, C.MUSTARD, 'stripe', 2),
        tape('p0_t2', 0.42, 2.5, 800, 212, 8, 140, 42, C.PINK, 'dot', 6),
        tape('p0_t3', 0.55, 2.5, 185, 1268, -30, 130, 40, C.SAGE, 'grid', 8),
    ]
    tiles = C.ransom_tiles('我的一天', 150, seed=2)
    xs = []
    total = sum(t.width for t, _, _ in tiles) - 4 * (len(tiles) - 1)
    x = W / 2 - total / 2
    for i, (tile, ang, dy) in enumerate(tiles):
        k = f'p0_title_{i}'
        BUILDERS[k] = (lambda im=tile: spr_of(im), ())
        at = 0.5 + 0.25 * i
        els.append(El(k, at, 2.5, x + tile.width / 2, 1060 + dy, rot=ang, z=50, role='title', label='title',
                      sfx=[('pop_soft', at, {'pitch': [0, 2, 4, 7][i]})]))
        x += tile.width - 4
    els.append(note('p0_hand', '随手记下今天的碎片', 1.375, 2.5, 530, 1240, rot=-2, size=56, under=C.RED + (230,)))
    BUILDERS['p0_stamp'] = (lambda: spr_of(C.rubber_stamp('日常', 'DAILY VLOG', seed=4)), ())
    els.append(El('p0_stamp', 1.5, 2.5, 805, 1480, rot=9, z=55, enter='stamp', role='stamp', label='stamp',
                  sfx=[('stamp', 1.5, {})]))
    els += [deco('p0_heart', b_icon_sticker, ('heart', 84, (233, 120, 128, 255)), 0.625, 2.5, 585, 300, -12),
            deco('p0_star', b_icon_sticker, ('star', 70, (246, 196, 80, 255)), 1.75, 2.5, 140, 905, 10),
            deco('p0_spark', b_icon, ('sparkle', 46, C.RED + (255,)), 1.25, 2.5, 955, 930, 0, sfx=False),
            deco('p0_spark2', b_icon, ('sparkle', 30, C.INK + (255,)), 1.3, 2.5, 990, 885, 0, sfx=False)]
    P.append(Page('title', 0.0, 2.5, 'dot', 'cut', 0, els))

    # ---------------------------------------------------------------- P1 gym + elevator (2.5 – 6.5)
    reg('p1_gym', b_torn_print, 800, 1150, 'tb', 13, 9, 10, 21)
    els = [
        El('p1_gym', 2.5, 6.5, 540, 820, rot=-2, z=20, enter='none', boil=False, role='media',
           media={'clip': '0399', 'segs': [(2.15, 0.0), (3.5, 2.2)], 'fy': 0.28, 'freeze': 4.5, 'gain': 1.14,
                  'defocus': (1, 0.66, 9.0)},   # 2nd jump: soften the far-right background (mirrored lettering on a weight plate)
           anim=zoom_jump(3.5, 1.035, 2.2, 4.5)),
        tape('p1_t1', 2.6, 6.5, 250, 250, -28, 170, 46, C.MUSTARD, 'stripe', 3, sfx=True),
        tape('p1_t2', 2.66, 6.5, 850, 1390, -24, 150, 44, C.PINK, 'dot', 9),
        card('time', 'p1_time', 2.75, 4.4, 820, 300, 5, clock('0399'), 22),
        note('p1_note', '咔嚓!', 3.5, 4.4, 300, 1020, rot=-8, size=80, color=(255, 250, 240, 255), halo=True),
    ]
    els += subtitle('p1_sub', [('健身房', False), ('打卡', True)], 3.0, 4.4, emph_at=3.25, emph_color=(236, 96, 84))
    # elevator: two polaroids dropped on top of the gym print (stacked collage)
    reg('p1_elevA', b_polaroid, 560, 747, 24, 100, clock('1559'), 23)
    reg('p1_elevB', b_polaroid, 470, 627, 22, 70, None, 24)
    els += [
        El('p1_elevA', 4.5, 6.5, 600, 800, rot=5, z=30, enter='drop', boil=False, role='media',
           media={'clip': '1559', 'segs': [(4.3, 10.0)]}, sfx=[('land', 4.5, {'gain_db': -3})]),
        tape('p1_t3', 4.62, 6.5, 600, 395, 4, 160, 46, C.SAGE, 'grid', 10, z=31, sfx=True),
        El('p1_elevB', 5.5, 6.5, 400, 1010, rot=-7, z=32, enter='drop', boil=False, role='media',
           media={'clip': '1559', 'segs': [(5.3, 17.6)]}, sfx=[('land', 5.5, {'gain_db': -3})]),
        tape('p1_t4', 5.62, 6.5, 250, 700, -40, 130, 42, C.PINK, 'dot', 12, z=33),
        deco('p1_spark', b_icon, ('sparkle', 54, (246, 190, 70, 255)), 5.75, 6.5, 700, 1150, 0),
        deco('p1_spark2', b_icon, ('sparkle', 34, C.RED + (255,)), 5.82, 6.5, 745, 1100, 0, sfx=False),
    ]
    els += subtitle('p1_sub2', [('电梯里秀一下', False), ('背', True)], 4.75, 6.5, emph_at=5.0,
                    emph_color=(226, 128, 136), sfx_note='E6')
    P.append(Page('gym', 2.5, 6.5, 'dot', 'flip', 0.35, els))

    # ---------------------------------------------------------------- P2 cat (6.5 – 8.5)
    reg('p2_cat', b_polaroid, 860, 1147, 24, 24, None, 31, (252, 250, 244), (18, 3, 12, 0.38))
    els = [
        El('p2_cat', 6.5, 8.5, 540, 860, rot=-2, z=20, enter='none', boil=False, role='media',
           media={'clip': '0083', 'segs': [(6.0, 0.3), (7.5, 2.3)]}, anim=zoom_jump(7.5, 1.03, 6.2, 8.5, (0, -6, -0.6, 0.02))),
        tape('p2_t1', 6.55, 8.5, 190, 300, -35, 180, 48, C.PINK, 'dot', 14),
        tape('p2_t2', 6.6, 8.5, 900, 300, 32, 180, 48, C.MUSTARD, 'stripe', 15),
        card('time', 'p2_time', 6.75, 8.5, 250, 250, -5, clock('0083'), 23),
        note('p2_note', '盯——', 6.875, 7.5, 790, 560, rot=6, size=88, color=(255, 250, 240, 255), halo=True),
        card('mood', 'p2_mood', 7.75, 8.5, 820, 1260, 6, '开心', 'smile', C.PINK, 42),
    ]
    reg('p2_arrow', b_arrow, 200, 150, (255, 250, 240, 245), 'rot180', 5, 0.45, True)
    els.append(El('p2_arrow', 6.95, 7.5, 660, 700, rot=0, z=65, enter='write', boil=False, role='deco'))
    els += subtitle('p2_sub', [('窗边的猫在', False), ('发呆', True)], 7.0, 8.5, emph_at=7.25,
                    emph_color=(244, 196, 70), sfx_note='A5')
    P.append(Page('cat', 6.5, 8.5, 'grid', 'sweep', 0.3, els))

    # ---------------------------------------------------------------- P3 drink, full bleed (8.5 – 10.5)
    els = [
        card('time', 'p3_time', 8.75, 10.5, 250, 300, -4, clock('9596'), 24),
        deco('p3_drop', b_icon_sticker, ('drop', 70, (120, 180, 230, 255)), 9.75, 10.5, 800, 760, 12),
        deco('p3_spark', b_icon, ('sparkle', 50, (255, 255, 255, 255)), 9.875, 10.5, 870, 690, 0, sfx=False),
        deco('p3_spark2', b_icon, ('sparkle', 30, (255, 255, 255, 255)), 9.9, 10.5, 740, 700, 0, sfx=False),
    ]
    els += subtitle('p3_sub', [('来一杯', False), ('冰冰凉', True)], 9.0, 10.5, emph_at=9.25,
                    emph_color=(120, 184, 232), sfx_note='E6', style='strip', seed=40)
    P.append(Page('drink', 8.5, 10.5, 'kraft', 'tearoff', 0.36, els,
                  full={'clip': '9596', 'segs': [(8.1, 1.0), (9.5, 5.3)], 'fy': 0.5,
                        'zoom': lambda t: 1.0 + 0.04 * E.c01((t - 8.5) / 2.0)}))

    # ---------------------------------------------------------------- P4 typing (10.5 – 12.5)
    reg('p4_type', b_polaroid, 740, 1060, 22, 22, None, 41, (252, 250, 244), (18, 3, 12, 0.38))
    els = [
        El('p4_type', 10.5, 12.5, 560, 840, rot=-3, z=20, enter='none', boil=False, role='media',
           media={'clip': '3888', 'segs': [(10.1, 2.0), (11.5, 8.0)], 'fy': 0.3}, anim=zoom_jump(11.5, 1.05, 10.2, 12.5)),
        tape('p4_t1', 10.6, 12.5, 560, 318, 3, 200, 50, C.SAGE, 'grid', 16, sfx=True),
        deco('p4_heart', b_icon_sticker, ('heart', 70, (233, 120, 128, 255)), 11.75, 12.5, 890, 1180, 14),
        note('p4_note', '专心中', 11.875, 12.5, 830, 770, rot=-6, size=66, color=C.INK + (255,), under=(90, 140, 190, 220)),
    ]
    els += subtitle('p4_sub', [('对着电脑', False), ('敲敲敲', True)], 11.0, 12.5, emph_at=11.25,
                    emph_color=(236, 96, 84), sfx_note='A5')
    for i in range(3):   # typing clicks under the three 敲
        els[-3 + i].sfx.append(('typing_key', 11.25 + 0.125 * i, {'heavy': 1 if i == 2 else 0}))
    P.append(Page('typing', 10.5, 12.5, 'ruled', 'flip', 0.35, els))

    # ---------------------------------------------------------------- P5 window + desert strips (12.5 – 16.5)
    reg('p5_win', b_torn_print, 980, 1740, 'tblr', 12, 9, 10, 51)
    reg('p5_des1', b_strip, 1120, 560, 61)
    reg('p5_des2', b_strip, 1120, 520, 62)
    els = [
        El('p5_win', 12.5, 16.5, 540, 960, rot=0.8, z=20, enter='none', boil=False, role='media',
           media={'clip': '8474', 'segs': [(12.2, 0.3), (13.5, 1.75)], 'fy': 0.5, 'freeze': 14.5},
           anim=zoom_jump(13.5, 1.03, 12.2, 14.5, (0, -5, 0.3, 0.015))),
        card('mood', 'p5_mood', 12.75, 14.4, 820, 300, 5, '放空', 'calm', (206, 222, 238), 52),
        El('p5_des1', 14.5, 16.5, 540, 430, rot=-3, z=30, enter='slap', boil=False, role='media',
           media={'clip': '9280', 'segs': [(14.4, 1.0)], 'fy': 0.5, 'zoom': 1.0},
           sfx=[('tear', 14.38, {}), ('land', 14.5, {'gain_db': -6})]),
        El('p5_des2', 15.5, 16.5, 540, 1480, rot=2.5, z=31, enter='slap', boil=False, role='media',
           media={'clip': '9280', 'segs': [(15.4, 4.8)], 'fy': 0.56, 'zoom': 1.3},
           sfx=[('tear', 15.38, {}), ('land', 15.5, {'gain_db': -6})]),
        tape('p5_t1', 14.6, 16.5, 110, 250, -60, 150, 46, C.MUSTARD, 'stripe', 17, z=32),
        tape('p5_t2', 15.6, 16.5, 975, 1680, -55, 150, 46, C.PINK, 'dot', 18, z=33),
        card('weather', 'p5_weather', 14.75, 16.5, 205, 820, -8, 'sun', '晴', 33),
    ]
    els += subtitle('p5_sub', [('看看', False), ('窗外', True)], 13.0, 14.4, emph_at=13.25,
                    emph_color=(130, 176, 120), sfx_note='C#6')
    els += subtitle('p5_sub2', [('天好', False), ('蓝', True)], 15.0, 16.5, emph_at=15.25,
                    emph_color=(84, 140, 214), sfx_note='E6')
    P.append(Page('window', 12.5, 16.5, 'kraft', 'swipe', 0.3, els))

    # ---------------------------------------------------------------- P6 court (16.5 – 18.5)
    reg('p6_court', b_polaroid, 720, 960, 26, 112, None, 61)
    els = [
        El('p6_court', 16.5, 18.5, 560, 840, rot=3, z=20, enter='none', boil=False, role='media',
           media={'clip': '1800', 'segs': [(16.2, 0.1), (17.5, 2.1)]}, anim=zoom_jump(17.5, 1.03, 16.2, 18.5, (0, -6, -0.5, 0.02))),
        tape('p6_t1', 16.6, 18.5, 560, 330, -2, 190, 48, C.MUSTARD, 'stripe', 19, sfx=True),
        card('weather', 'p6_weather', 16.75, 18.5, 210, 330, -6, 'suncloud', '多云', 34),
        note('p6_note', '咚 咚', 17.75, 18.5, 860, 1338, rot=4, size=64, color=(214, 110, 50, 255)),
        deco('p6_ball', b_icon_sticker, ('ball', 64, (232, 130, 60, 255), 8, (120, 60, 30, 255)), 17.625, 18.5, 700, 1336, -10),
    ]
    els += subtitle('p6_sub', [('篮球场', False), ('拍拍球', True)], 17.0, 18.5, emph_at=17.25,
                    emph_color=(238, 142, 64), sfx_note='A5')
    P.append(Page('court', 16.5, 18.5, 'dot', 'rise', 0.3, els))

    # ---------------------------------------------------------------- P7 sunset, full bleed (18.5 – 22.5)
    els = [
        card('time', 'p7_time', 18.75, 22.5, 250, 300, -4, clock('1082'), 25),
        card('mood', 'p7_mood', 19.75, 22.5, 830, 330, 6, '惬意', 'smile', (250, 214, 170), 53),
        deco('p7_spark', b_icon, ('sparkle', 60, (255, 240, 200, 255)), 20.5, 22.5, 880, 760, 0),
        deco('p7_spark2', b_icon, ('sparkle', 36, (255, 240, 200, 255)), 20.58, 22.5, 820, 700, 0, sfx=False),
    ]
    els += subtitle('p7_sub', [('晚霞是', False), ('橘子味', True), ('的', False)], 19.0, 22.5, emph_at=19.25,
                    emph_color=(244, 150, 60), sfx_note='C#6')
    els[-3].sfx.append(('shimmer', 19.25, {'dur': 1.4}))
    P.append(Page('sunset', 18.5, 22.5, 'kraft', 'sweep', 0.3, els,
                  full={'clip': '1082', 'segs': [(18.2, 1.4)], 'fy': 0.3, 'rate': 0.8,
                        'zoom': lambda t: 1.35 + 0.07 * E.c01((t - 18.5) / 4.0)}))

    # ---------------------------------------------------------------- P8 night + recap (22.5 – 29)
    reg('p8_speaker', b_polaroid, 720, 720, 28, 104, None, 71)
    reg('p8_moon', b_moon)
    els = [
        El('p8_moon', 22.5, 29.0, 945, 205, rot=-12, sc=0.78, z=15, enter='none', role='deco'),
        El('p8_speaker', 22.5, 25.0, 540, 880, rot=-3, z=20, enter='none', boil=False, role='media', exit='pop', xd=0.16,
           media={'clip': '7752', 'segs': [(22.1, 1.2, 0.1, 1.0), (24.0, 3.3, 0.1, 1.1)]}, anim=zoom_jump(24.0, 1.03, 22.2, 25.0, (0, -6, 0.5, 0.02))),
        tape('p8_t1', 22.6, 25.0, 540, 452, -4, 190, 48, (160, 170, 214), 'dot', 20),
        card('time', 'p8_time', 22.75, 25.0, 230, 310, -5, clock('7752'), 26),
        card('mood', 'p8_mood', 23.75, 25.0, 835, 1270, 5, '放松', 'calm', (200, 214, 240), 54),
    ]
    els += subtitle('p8_sub', [('夜里的', False), ('小蓝灯', True)], 23.0, 25.0, emph_at=23.25,
                    emph_color=(96, 150, 236), sfx_note='E6', style='strip', seed=44)
    # recap: the whole day as mini prints popping onto the night page (16th notes, rising notes)
    recap = [('0399', 0.6, 0.5, 0.3), ('1559', 10.5, 0.5, 0.5), ('0083', 1.0, 0.5, 0.5), ('9596', 5.8, 0.5, 0.45),
             ('3888', 2.5, 0.5, 0.3), ('8474', 1.0, 0.6, 0.5), ('9280', 1.5, 0.5, 0.5), ('1800', 1.8, 0.5, 0.5),
             ('1082', 1.9, 0.5, 0.45), ('7752', 3.0, 0.5, 0.1)]
    pos = [(250, 610), (540, 590), (830, 610), (175, 950), (415, 935), (665, 950), (905, 935), (250, 1290), (540, 1305), (830, 1290)]
    pitches = [0, 2, 4, 7, 9, 12, 14, 16, 19, 21]
    for i, ((cid, st, fx, fy), (x, y)) in enumerate(zip(recap, pos)):
        k = f'p8_r{i}'
        reg(k, b_still_card, cid, st, 210, 280, 12, 34, fx, fy, 1.35 if cid == '7752' else 1.0, 80 + i)
        at = 25.125 + 0.125 * i
        r = (E.hrand('recap', i) - 0.5) * 14
        x += (E.hrand('rx', i) - 0.5) * 30; y += (E.hrand('ry', i) - 0.5) * 30
        els.append(El(k, at, 29.0, x, y, rot=r, z=30 + i, enter='pop', boil=False, role='deco',
                      sfx=[('pop_soft', at, {'pitch': pitches[i] - 9, 'gain_db': -2})]))
    tiles = C.ransom_tiles('我的一天', 96, seed=5)
    total = sum(t.width for t, _, _ in tiles) - 4 * (len(tiles) - 1)
    x = W / 2 - total / 2
    for i, (tile, ang, dy) in enumerate(tiles):
        k = f'p8_title_{i}'
        BUILDERS[k] = (lambda im=tile: spr_of(im), ())
        els.append(El(k, 25.125 + 0.0625 * i, 29.0, x + tile.width / 2, 330 + dy * 0.6, rot=ang, z=50, role='title',
                      label='title2', sfx=[]))
        x += tile.width - 4
    BUILDERS['p8_stamp'] = (lambda: spr_of(C.rubber_stamp('晚安', 'GOOD NIGHT', color=(226, 88, 76), seed=9)), ())
    els.append(El('p8_stamp', 26.5, 29.0, 760, 1545, rot=-8, z=60, enter='stamp', role='stamp', label='stamp2',
                  sfx=[('stamp', 26.5, {})]))
    els.append(note('p8_hand', '明天见', 27.0, 29.0, 320, 1560, rot=-5, size=86, color=(250, 238, 205, 255),
                    under=(250, 200, 120, 230)))
    P.append(Page('night', 22.5, 29.0, 'navy', 'curtain', 0.35, els))
    return P


# ============================================================ frame render
TRANS_SFX = {'flip': [('page_flip', -0.3, {})], 'sweep': [('whoosh_mid', -0.3, {'dur': 0.4, 'gain_db': -6}), ('paper_slide', -0.3, {})],
             'tearoff': [('tear', -0.36, {'dur': 0.38})], 'swipe': [('whoosh_fast', -0.3, {'gain_db': -2}), ('paper_slide', -0.28, {})],
             'rise': [('whoosh_mid', -0.3, {'dur': 0.4, 'gain_db': -6}), ('paper_slide', -0.3, {})],
             'curtain': [('whoosh_slow', -0.35, {'dur': 0.9, 'gain_db': -6}), ('paper_slide', -0.33, {})]}


def page_at(pages, t):
    cur = pages[0]
    for p in pages:
        if t >= p.t0:
            cur = p
    return cur


def render_frame(pages, fi, ctx, fin, log=None):
    t = fi / FPS
    cur = page_at(pages, t)
    i = pages.index(cur)
    nxt = pages[i + 1] if i + 1 < len(pages) else None
    if nxt is not None and nxt.trans != 'cut' and t >= nxt.t0 - nxt.tdur:
        p = (t - (nxt.t0 - nxt.tdur)) / nxt.tdur
        old = cur.render(t, ctx, log)
        new = nxt.render(t, ctx, None)
        key = nxt.name
        if nxt.trans == 'flip':
            out = E.trans_flip(old, new, p)
        elif nxt.trans == 'sweep':
            out = E.trans_sweep(old, new, p, key, 'left')
        elif nxt.trans == 'rise':
            out = E.trans_sweep(old, new, p, key, 'up')
        elif nxt.trans == 'curtain':
            out = E.trans_sweep(old, new, p, key, 'down')
        elif nxt.trans == 'tearoff':
            out = E.trans_tearoff(old, new, p, key)
        elif nxt.trans == 'swipe':
            out = E.trans_swipe(old, new, p)
        else:
            out = new
    else:
        out = cur.render(t, ctx, log)
    out = fin(out, fi)
    if t > DUR - 1.0:                       # fade to black over the last second
        out = out * (1 - E.cubic_io((t - (DUR - 1.0)) / 1.0))
    return (out * 255 + 0.5).astype(np.uint8)


def sfx_cues(pages):
    cues = []
    for p in pages:
        for kind, dt, params in TRANS_SFX.get(p.trans, []):
            cues.append({'id': kind, 'at': round(p.t0 + dt, 4), 'params': params, 'src': f'trans:{p.name}'})
        for el in p.els:
            for kind, at, params in el.sfx:
                cues.append({'id': kind, 'at': round(at, 4), 'params': params, 'src': el.key})
    cues = sorted(cues, key=lambda c: c['at'])
    out = []
    for c in cues:      # one sound per id per moment (a subtitle's parts pop together = one pop)
        if any(o['id'] == c['id'] and abs(o['at'] - c['at']) < 0.03 for o in out[-6:]):
            continue
        out.append(c)
    return out


# ============================================================ drivers
def worker(args):
    wi, f0, f1, out_path, strip_dir = args
    pages = build()
    ctx = Ctx(); fin = E.Finisher()
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
                            '-i', '-', '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
                            '-c:v', 'libx264', '-preset', 'fast', '-crf', '10', '-g', '30',
                            '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
                            out_path], stdin=subprocess.PIPE)
    logs = []
    for fi in range(f0, f1):
        log = []
        img = render_frame(pages, fi, ctx, fin, log)
        enc.stdin.write(img.tobytes())
        logs.append({'f': fi, 'boxes': log})
        if fi % 6 == 0:                                    # filmstrip: one frame every 0.2 s
            Image.fromarray(img).save(os.path.join(strip_dir, f'f{fi:04d}.jpg'), quality=90)
    enc.stdin.close(); enc.wait(); ctx.close()
    return logs


def render_all(n_workers=8):
    import concurrent.futures as cf
    seg_dir = os.path.join(WORK, 'segs'); strip_dir = os.path.join(WORK, 'strip_full')
    os.makedirs(seg_dir, exist_ok=True); os.makedirs(strip_dir, exist_ok=True)
    bounds = np.linspace(0, NFR, n_workers + 1).astype(int)
    jobs = [(i, int(bounds[i]), int(bounds[i + 1]), os.path.join(seg_dir, f'seg{i:02d}.mp4'), strip_dir) for i in range(n_workers)]
    t0 = time.time()
    with cf.ProcessPoolExecutor(n_workers) as ex:
        results = list(ex.map(worker, jobs))
    logs = [l for r in results for l in r]
    json.dump(logs, open(os.path.join(WORK, 'text_boxes.json'), 'w'))
    lst = os.path.join(seg_dir, 'list.txt')
    with open(lst, 'w') as f:
        for j in jobs:
            f.write(f"file '{j[3]}'\n")
    out = os.path.join(WORK, 'video_noaudio.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', out], check=True)
    print(f'rendered {NFR} frames in {time.time() - t0:.1f}s -> {out}')


def test(times):
    pages = build(); ctx = Ctx(); fin = E.Finisher()
    for t in times:
        fi = int(round(float(t) * FPS))
        t0 = time.time()
        img = render_frame(pages, fi, ctx, fin)
        Image.fromarray(img).save(os.path.join(WORK, f'test_{float(t):05.2f}.jpg'), quality=90)
        print(t, f'{time.time() - t0:.2f}s')
    ctx.close()


if __name__ == '__main__':
    if sys.argv[1] == 'test':
        test(sys.argv[2:])
    elif sys.argv[1] == 'render':
        render_all(int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    elif sys.argv[1] == 'cues':
        json.dump(sfx_cues(build()), open(os.path.join(WORK, 'sfx_cues.json'), 'w'), indent=1, ensure_ascii=False)
        print('cues written')
