"""A1 shots 07-11: easing, premultiplied-alpha compositing, video IO (ffmpeg pipes), PiP card + transition, demo card.

Design code is the storyboard's own (sb_lib.py / v2_parts.py are verbatim copies); this module only moves and layers
those elements over time.  All frames are 1080x1920 RGB, 30 fps CFR.
"""
import json
import math
import os
import subprocess
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from a1paths import *  # noqa
import sb_lib as SB
from sb_lib import W, H, CARD, INK, YELLOW, GREEN, RED, PIP_BOX

# sb_lib.rrect_mask is pure (same args -> same mask); cache it so per-frame pip_card()/photo() stay cheap
_rrect = SB.rrect_mask
SB.rrect_mask = lru_cache(maxsize=64)(_rrect)
_tape = SB.tape
SB.tape = lru_cache(maxsize=64)(_tape)


# ---------------------------------------------------------------- easing (same curves as xiaolu-motion engine/core.js)
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def seg(t, a, b):
    if b == a:
        return 1.0 if t >= b else 0.0
    return clamp((t - a) / (b - a))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def smoother(x):
    x = clamp(x)
    return x * x * x * (x * (x * 6 - 15) + 10)


def cubic_in(x):
    x = clamp(x)
    return x * x * x


def cubic_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def cubic_inout(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def quint_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 5


def expo_out(x):
    x = clamp(x)
    return 1.0 if x >= 1 else (1 - 2 ** (-10 * x)) / (1 - 2 ** -10)


def back_out(x, s=1.4):
    x = clamp(x)
    y = x - 1
    return 1 + (s + 1) * y ** 3 + s * y ** 2


def spring(s, freq=3.2, zeta=0.42):
    """damped spring step response, s = seconds since release, 0 -> 1 with overshoot"""
    if s <= 0:
        return 0.0
    w = 2 * math.pi * freq
    wd = w * math.sqrt(1 - zeta * zeta)
    return 1 - math.exp(-zeta * w * s) * (math.cos(wd * s) + (zeta * w / wd) * math.sin(wd * s))


# ---------------------------------------------------------------- premultiplied float sprites
def to_pm(im):
    """PIL image -> (h, w, 4) float32, rgb premultiplied (0..255), alpha 0..1"""
    a = np.asarray(im.convert('RGBA'), np.float32)
    al = a[..., 3:4] * (1 / 255.0)
    return np.concatenate([a[..., :3] * al, al], axis=2)


def rgb_pm(rgb, alpha=None):
    """(h, w, 3) uint8/float rgb (+ optional (h, w) alpha 0..1) -> premultiplied sprite"""
    rgb = rgb.astype(np.float32)
    if alpha is None:
        alpha = np.ones(rgb.shape[:2], np.float32)
    alpha = alpha.astype(np.float32)
    return np.concatenate([rgb * alpha[..., None], alpha[..., None]], axis=2)


def blend(dst, spr, x, y, opacity=1.0):
    """composite premultiplied sprite over a float canvas at integer (x, y), clipped.  dst is rgb (h, w, 3) or a
    premultiplied rgba layer (h, w, 4) (then alpha is accumulated too)"""
    h, w = spr.shape[:2]
    x, y = int(round(x)), int(round(y))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(dst.shape[1], x + w), min(dst.shape[0], y + h)
    if x1 <= x0 or y1 <= y0 or opacity <= 0:
        return
    s = spr[y0 - y:y1 - y, x0 - x:x1 - x]
    d = dst[y0:y1, x0:x1]
    a = s[..., 3:4] if opacity >= 1 else s[..., 3:4] * opacity
    if dst.shape[2] == 4:
        d *= (1 - a)
        d += s if opacity >= 1 else s * opacity
    else:
        d *= (1 - a)
        d += s[..., :3] if opacity >= 1 else s[..., :3] * opacity


LAST_QUAD = None     # canvas corners of the sprite rectangle drawn by the last place() call (for exact QA overlap)


def place(dst, spr, cx, cy, ax=None, ay=None, scale=1.0, rot=0.0, opacity=1.0, sx=None, sy=None):
    """composite sprite with its anchor (ax, ay) (sprite px, default centre) at canvas (cx, cy), scaled and rotated
    (degrees, counter-clockwise like PIL).  Returns the canvas bbox touched."""
    if opacity <= 0 or scale <= 0.001:
        return None
    h, w = spr.shape[:2]
    ax = w / 2 if ax is None else ax
    ay = h / 2 if ay is None else ay
    sx = scale if sx is None else sx
    sy = scale if sy is None else sy
    if abs(rot) < 1e-4 and abs(sx - 1) < 1e-6 and abs(sy - 1) < 1e-6 and abs(cx - ax - round(cx - ax)) < 1e-6 \
            and abs(cy - ay - round(cy - ay)) < 1e-6:
        blend(dst, spr, cx - ax, cy - ay, opacity)
        return (int(cx - ax), int(cy - ay), int(cx - ax + w), int(cy - ay + h))
    th = math.radians(rot)
    c, s = math.cos(th), math.sin(th)
    # canvas = R(-th) * S * (p - a) + (cx, cy)   (PIL rotate is counter-clockwise on screen, y down)
    A = np.array([[c * sx, s * sy], [-s * sx, c * sy]], np.float64)
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], np.float64) - [ax, ay]
    cc = corners @ A.T + [cx, cy]
    global LAST_QUAD
    LAST_QUAD = [[float(cc[i, 0]), float(cc[i, 1])] for i in (0, 1, 3, 2)]
    bx0, by0 = int(math.floor(cc[:, 0].min())) - 1, int(math.floor(cc[:, 1].min())) - 1
    bx1, by1 = int(math.ceil(cc[:, 0].max())) + 1, int(math.ceil(cc[:, 1].max())) + 1
    bx0c, by0c, bx1c, by1c = max(0, bx0), max(0, by0), min(dst.shape[1], bx1), min(dst.shape[0], by1)
    if bx1c <= bx0c or by1c <= by0c:
        return None
    M = np.zeros((2, 3), np.float64)
    M[:, :2] = A
    M[:, 2] = np.array([cx, cy]) - A @ np.array([ax, ay]) - [bx0c, by0c]
    if min(sx, sy) < 0.5:             # warpAffine has no area filter: pre-shrink big reductions
        k = max(sx, sy) * 2
        spr = cv2.resize(spr, (max(1, int(round(w * k))), max(1, int(round(h * k)))), interpolation=cv2.INTER_AREA)
        M[:, :2] = M[:, :2] * np.array([[w / spr.shape[1], h / spr.shape[0]]])
    out = cv2.warpAffine(spr, M, (bx1c - bx0c, by1c - by0c), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                         borderValue=(0, 0, 0, 0))
    blend(dst, out, bx0c, by0c, opacity)
    return (bx0c, by0c, bx1c, by1c)


def shadow_pm(spr, blur=12, alpha=0.30, spread=0, color=(20, 16, 10)):
    """sb_lib.shadow_of equivalent: returns (shadow sprite, pad); place it at (x - pad + 3, y - pad + 7)"""
    a = spr[..., 3]
    pad = blur * 3
    big = np.zeros((a.shape[0] + 2 * pad, a.shape[1] + 2 * pad), np.float32)
    big[pad:pad + a.shape[0], pad:pad + a.shape[1]] = a
    if spread:
        big = cv2.dilate(big, np.ones((spread * 2 + 1, spread * 2 + 1), np.uint8))
    # PIL GaussianBlur(radius=r) ~ sigma r
    big = cv2.GaussianBlur(big, (0, 0), blur) * alpha
    col = np.array(color, np.float32)
    return np.concatenate([big[..., None] * col, big[..., None]], axis=2), pad


def add_with_shadow(dst, spr, x, y, blur=12, salpha=0.30, opacity=1.0, shadow=None):
    """Frame.add(...) equivalent for an unrotated sprite at integer (x, y)"""
    sh, pad = shadow if shadow is not None else shadow_pm(spr, blur, salpha)
    blend(dst, sh, x - pad + 3, y - pad + 7, opacity)
    blend(dst, spr, x, y, opacity)


def rrect_fast(w, h, r):
    """anti-aliased rounded-rect alpha (h, w) float32 0..1, computed analytically (no supersampling, no cache)"""
    r = max(0.5, min(r, w / 2, h / 2))
    xs = np.arange(w, dtype=np.float32) + 0.5
    ys = np.arange(h, dtype=np.float32) + 0.5
    dx = np.maximum(np.maximum(r - xs, xs - (w - r)), 0)[None, :]
    dy = np.maximum(np.maximum(r - ys, ys - (h - r)), 0)[:, None]
    d = np.sqrt(dx * dx + dy * dy) - r
    return np.clip(0.5 - d, 0, 1).astype(np.float32)


def to_u8(canvas):
    return np.clip(canvas + 0.5, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- video IO
# CPU budget per heavy task = 4 threads (coordinator rule 2026-09-27): encoder 2 + source decoder 1 + demo decoder 1
ENC_THREADS = '2'
DEC_THREADS = '1'
_VF_IN = 'scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int,format=rgb24'


class Reader:
    """sequential rgb24 frames of `path` starting at frame `start` (frame-exact: -ss (start-0.5)/fps before -i)"""

    def __init__(self, path, start, w=W, h=H, out_w=None, out_h=None):
        self.cur = start
        self.ow, self.oh = out_w or w, out_h or h
        self.size = self.ow * self.oh * 3
        vf = _VF_IN
        if out_w:
            vf = f'scale={out_w}:{out_h}:flags=lanczos+accurate_rnd+full_chroma_int:in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24'
        cmd = ['ffmpeg', '-v', 'error', '-threads', DEC_THREADS]
        if start > 0:
            cmd += ['-ss', f'{(start - 0.5) / FPS:.6f}']
        cmd += ['-i', str(path), '-map', '0:v:0', '-vf', vf + ',settb=1/30,setpts=N', '-fps_mode', 'passthrough',
                '-f', 'rawvideo', '-']
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=self.size * 2)

    def next(self):
        b = self.p.stdout.read(self.size)
        if len(b) < self.size:
            raise EOFError(f'decoder ran out at frame {self.cur}')
        self.cur += 1
        return np.frombuffer(b, np.uint8).reshape(self.oh, self.ow, 3)

    def close(self):
        self.p.kill()             # kill first: closing the pipe first makes ffmpeg log a broken-pipe error
        try:
            self.p.stdout.close()
        except Exception:
            pass
        self.p.wait()


class Source:
    """frame server for mostly-forward access: get(i) decodes forward, re-seeks on backward or long forward jumps"""

    def __init__(self, path, out_w=None, out_h=None, max_skip=40):
        self.path, self.ow, self.oh, self.max_skip = path, out_w, out_h, max_skip
        self.r, self.last_i, self.last = None, None, None
        self.seeks = 0

    def get(self, i):
        if i == self.last_i:
            return self.last
        if self.r is None or i < self.r.cur or i > self.r.cur + self.max_skip:
            if self.r:
                self.r.close()
            self.r = Reader(self.path, i, out_w=self.ow, out_h=self.oh)
            self.seeks += 1
        while True:
            f = self.r.next()
            if self.r.cur - 1 == i:
                self.last_i, self.last = i, f
                return f

    def close(self):
        if self.r:
            self.r.close()
            self.r = None


class Encoder:
    """rgb24 frames -> H.264 High yuv420p BT.709 tv, CRF 10, CFR 30, no audio; written as <out>.partial, verified,
    then renamed (verify() checks frame count, codec, profile, pix_fmt, colour tags)"""

    def __init__(self, out, n_frames, crf=10, preset='slow'):
        self.out, self.n = Path(out), n_frames
        self.partial = Path(str(out) + '.partial')
        vf = ('scale=in_range=pc:out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,'
              'setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv')
        cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
               '-i', '-', '-vf', vf, '-c:v', 'libx264', '-preset', preset, '-crf', str(crf), '-profile:v', 'high',
               '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
               '-color_range', 'tv', '-fps_mode', 'cfr', '-threads', ENC_THREADS, '-an', '-movflags', '+faststart',
               '-f', 'mp4', str(self.partial)]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        self.count = 0

    def write(self, rgb_u8):
        assert rgb_u8.shape == (H, W, 3) and rgb_u8.dtype == np.uint8
        self.p.stdin.write(np.ascontiguousarray(rgb_u8).tobytes())
        self.count += 1

    def finish(self):
        self.p.stdin.close()
        rc = self.p.wait()
        assert rc == 0, f'encoder exit {rc}'
        info = probe(self.partial)
        ok = (info['frames'] == self.n == self.count and info['codec'] == 'h264' and info['profile'] == 'High'
              and info['pix_fmt'] == 'yuv420p' and info['w'] == W and info['h'] == H and info['fps'] == '30/1'
              and info['color'] == ['bt709', 'bt709', 'bt709', 'tv'] and not info['audio'])
        assert ok, ('segment verify failed', info, self.n, self.count)
        os.replace(self.partial, self.out)
        return info


def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-count_packets', '-show_streams', '-of', 'json', str(path)],
                       capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    v = [s for s in j['streams'] if s['codec_type'] == 'video'][0]
    return {'frames': int(v['nb_read_packets']), 'codec': v['codec_name'], 'profile': v.get('profile'),
            'pix_fmt': v['pix_fmt'], 'w': v['width'], 'h': v['height'], 'fps': v['r_frame_rate'],
            'avg_fps': v['avg_frame_rate'],
            'color': [v.get('color_space'), v.get('color_primaries'), v.get('color_transfer'), v.get('color_range')],
            'audio': any(s['codec_type'] == 'audio' for s in j['streams'])}


# ---------------------------------------------------------------- faces
_FACES = None


def faces():
    global _FACES
    if _FACES is None:
        d = json.loads((WORK / 'faces_src.json').read_text())
        _FACES = {int(k): v for k, v in d.items()}
    return _FACES


def face_at(sf):
    """face / lips box of source frame sf (linear interpolation between detected frames)"""
    F = faces()
    if sf in F:
        return F[sf]['faces'][0], F[sf]['lips'][0]
    ks = sorted(F)
    lo = max([k for k in ks if k < sf], default=None)
    hi = min([k for k in ks if k > sf], default=None)
    if lo is None or (hi is not None and hi - sf < sf - lo and hi - lo > 12):
        k = hi
        return F[k]['faces'][0], F[k]['lips'][0]
    if hi is None or hi - lo > 12:
        return F[lo]['faces'][0], F[lo]['lips'][0]
    t = (sf - lo) / (hi - lo)
    fa = [round(lerp(a, b, t)) for a, b in zip(F[lo]['faces'][0], F[hi]['faces'][0])]
    la = [round(lerp(a, b, t)) for a, b in zip(F[lo]['lips'][0], F[hi]['lips'][0])]
    return fa, la


def head_top(rgb, face):
    """top of the hair above a face box: highest row (above the face) where >= 18% of the face-width columns are dark
    hair (the wall behind the presenter is light grey, the hair is near-black)"""
    x0, y0, x1, y1 = face
    cx0, cx1 = int(x0 + 0.1 * (x1 - x0)), int(x1 - 0.1 * (x1 - x0))
    g = rgb[:max(1, y0), cx0:cx1].astype(np.float32).mean(2)
    frac = (g < 70).mean(1)
    rows = np.where(frac >= 0.18)[0]
    return int(rows.min()) if len(rows) else max(0, y0 - 300)


# ---------------------------------------------------------------- PiP (右下人像框) and its full-frame <-> box transition
PIP_OUT = (PIP_BOX[0], PIP_BOX[1], PIP_BOX[2], PIP_BOX[3])        # 726, 846, 1050, 1290 (card outer box)
PIP_IN = (738, 858, 1038, 1278)                                    # content 300 x 420 inside a 12 px border


def pip_window(face, htop):
    """sb_lib.pip_crop geometry: 900 x 1260 source window (x0, y0) for a face box and head top"""
    ch = 1260
    cw = int(round(ch * 300 / 420))
    cx = (face[0] + face[2]) / 2
    x0 = int(min(max(0, cx - cw / 2), W - cw))
    y0 = int(max(0, htop - 70))
    y0 = min(y0, H - ch)
    return x0, y0


class Pip:
    """right-bottom PiP card; e = 1 settled in the box (pixel-identical construction to sb_lib.add_pip),
    e = 0 the whole frame full screen; in between the whole frame shrinks into the box"""

    def __init__(self, win):
        self.win = win               # (x0, y0) of the 900 x 1260 window
        t = SB.rotate(SB.tape(118, 36, color=(250, 222, 120), seed=5), -7)
        self.tape = to_pm(t)
        self.tape_w = t.width
        self._settled_shadow = None

    def settled_sprite(self, src_rgb, cover=None):
        x0, y0 = self.win
        crop = Image.fromarray(src_rgb[y0:y0 + 1260, x0:x0 + 900])
        content = crop.resize((300, 420), Image.LANCZOS)
        if cover is not None:
            content = cover(content)
        return to_pm(SB.pip_card(content))

    def draw_settled(self, dst, src_rgb, cover=None):
        spr = self.settled_sprite(src_rgb, cover)
        if self._settled_shadow is None:
            self._settled_shadow = shadow_pm(spr, 14, 0.35)
        add_with_shadow(dst, spr, PIP_BOX[0], PIP_BOX[1] - 22, shadow=self._settled_shadow)
        return (PIP_BOX[0], PIP_BOX[1] - 22, PIP_BOX[0] + spr.shape[1], PIP_BOX[1] - 22 + spr.shape[0])

    def draw(self, dst, src_rgb, e, cover=None):
        """e in [0, 1]; returns the canvas rect of the live picture (content) and the transform (s, ox, oy)"""
        x0, y0 = self.win
        if e >= 0.9999:
            self.draw_settled(dst, src_rgb, cover)
            s = 1 / 3
            return PIP_IN, (s, 738 - x0 * s, 858 - y0 * s)
        if e <= 0.0001:
            dst[:] = src_rgb
            return (0, 0, W, H), (1.0, 0.0, 0.0)
        R = [lerp(a, b, e) for a, b in zip((0, 0, W, H), PIP_OUT)]
        b = 12 * e
        C = [R[0] + b, R[1] + b, R[2] - b, R[3] - b]
        s = 1 - 2 * e / 3
        ox, oy = e * (738 - x0 / 3), e * (858 - y0 / 3)
        # card (white paper border) with rounded corners + soft shadow
        rx0, ry0, rx1, ry1 = [int(round(v)) for v in R]
        cw_, ch_ = rx1 - rx0, ry1 - ry0
        r_out = max(1, int(round(30 * e)))
        m_out = rrect_fast(cw_, ch_, r_out)
        card = np.concatenate([np.ones((ch_, cw_, 3), np.float32) * np.array(CARD, np.float32) * m_out[..., None],
                               m_out[..., None]], axis=2)
        if e > 0.02:
            sh, pad = shadow_pm(card[::4, ::4].copy(), max(1, int(14 / 4)), 0.35 * e)
            sh = cv2.resize(sh, ((cw_ // 4 + 2 * pad) * 4, (ch_ // 4 + 2 * pad) * 4), interpolation=cv2.INTER_LINEAR)
            blend(dst, sh, rx0 - pad * 4 + 3, ry0 - pad * 4 + 7)
        blend(dst, card, rx0, ry0)
        # live picture: source scaled by s, offset (ox, oy), clipped to C with rounded corners
        cx0, cy0, cx1, cy1 = [int(round(v)) for v in C]
        sx0 = max(0, int(math.floor((cx0 - ox) / s)))
        sy0 = max(0, int(math.floor((cy0 - oy) / s)))
        sx1 = min(W, int(math.ceil((cx1 - ox) / s)) + 1)
        sy1 = min(H, int(math.ceil((cy1 - oy) / s)) + 1)
        crop = src_rgb[sy0:sy1, sx0:sx1]
        M = np.array([[s, 0, ox + sx0 * s - cx0], [0, s, oy + sy0 * s - cy0]], np.float64)
        if s < 0.75:
            k = s * 1.5
            crop = cv2.resize(crop, (max(1, int(crop.shape[1] * k)), max(1, int(crop.shape[0] * k))), interpolation=cv2.INTER_AREA)
            M[:, :2] /= k
        pic = cv2.warpAffine(crop, M, (cx1 - cx0, cy1 - cy0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        if cover is not None:
            pic = np.asarray(cover(Image.fromarray(pic)).convert('RGB'))
        r_in = max(1, int(round(22 * e)))
        m_in = rrect_fast(cx1 - cx0, cy1 - cy0, r_in)
        blend(dst, rgb_pm(pic, m_in), cx0, cy0)
        # washi tape arrives in the last 15 %
        ta = seg(e, 0.85, 1.0)
        if ta > 0:
            place(dst, self.tape, (rx0 + rx1) / 2, ry0 - 22 + self.tape.shape[0] / 2 - (1 - ta) * 10, opacity=ta)
        return (cx0, cy0, cx1, cy1), (s, ox, oy)


def pip_face_rect(face, tr):
    """map a source face box through a PiP transform (s, ox, oy)"""
    s, ox, oy = tr
    return [face[0] * s + ox, face[1] * s + oy, face[2] * s + ox, face[3] * s + oy]


# ---------------------------------------------------------------- demo card on the dotted paper page (demo_card_v2)
class DemoCard:
    def __init__(self, seed, scale=0.64, x=30, y=168, rot=-1.2):
        self.seed, self.rot = seed, rot
        self.cw, self.ch = int(W * scale), int(H * scale)                 # 691 x 1228
        blank = Image.new('RGBA', (self.cw, self.ch), CARD + (255,))
        c = SB.photo(blank, border=12, radius=10)                          # 715 x 1252
        t = SB.rotate(SB.tape(150, 40, color=(250, 222, 120), seed=seed), -8)
        out = Image.new('RGBA', (c.width + 10, c.height + 30), (0, 0, 0, 0))
        out.alpha_composite(c, (0, 30))
        self.frame_pm = to_pm(out)                                         # card, content area replaced per frame
        tape_l = Image.new('RGBA', out.size, (0, 0, 0, 0))
        tape_l.alpha_composite(t, (c.width // 2 - 75, 0))
        self.tape_pm = to_pm(tape_l)
        m = np.zeros((out.height, out.width), np.float32)
        m[30 + 12:30 + 12 + self.ch, 12:12 + self.cw] = np.asarray(SB.rrect_mask(self.cw, self.ch, 10), np.float32) / 255
        self.cmask = m
        self.size = out.size
        rot_img = SB.rotate(out, rot)                                      # PIL expand geometry of the sample frame
        self.rest = (x + rot_img.width / 2, y - 30 + rot_img.height / 2)   # centre of the card at rest
        full = self.sprite(np.zeros((self.ch, self.cw, 3), np.uint8))
        self.shadow = shadow_pm(full, 18, 0.3)

    def sprite(self, content_rgb):
        """content (ch, cw, 3) uint8 -> unrotated premultiplied card sprite incl. tape"""
        spr = self.frame_pm.copy()
        m = self.cmask[30 + 12:30 + 12 + self.ch, 12:12 + self.cw, None]
        region = spr[30 + 12:30 + 12 + self.ch, 12:12 + self.cw]
        region[..., :3] = region[..., :3] * (1 - m) + content_rgb.astype(np.float32) * m
        region[..., 3:4] = np.maximum(region[..., 3:4], m)
        tp = self.tape_pm
        spr[..., :3] = spr[..., :3] * (1 - tp[..., 3:4]) + tp[..., :3]
        spr[..., 3:4] = spr[..., 3:4] + tp[..., 3:4] * (1 - spr[..., 3:4])
        return spr

    def draw(self, dst, content_rgb, dx=0.0, dy=0.0, drot=0.0, scale=1.0, opacity=1.0):
        spr = self.sprite(content_rgb)
        cx, cy = self.rest[0] + dx, self.rest[1] + dy
        sh, pad = self.shadow
        place(dst, sh, cx + 3, cy + 7, rot=self.rot + drot, scale=scale, opacity=opacity)
        return place(dst, spr, cx, cy, rot=self.rot + drot, scale=scale, opacity=opacity)

    def content_to_canvas(self, px, py, dx=0.0, dy=0.0, drot=0.0, scale=1.0):
        """map a point of the content (card-content pixels) to canvas coordinates for the current pose"""
        sw, sh_ = self.size
        ax, ay = sw / 2, sh_ / 2
        x, y = px + 12 - ax, py + 30 + 12 - ay
        th = math.radians(self.rot + drot)
        c, s = math.cos(th), math.sin(th)
        return (self.rest[0] + dx + scale * (c * x + s * y), self.rest[1] + dy + scale * (-s * x + c * y))


def demo_content(frame_rgb, cw, ch, zoom=None):
    """demo frame (1080 x 1920) -> card content (cw x ch); zoom = (cx, cy, m) punches in around a demo-space point"""
    if zoom is None or zoom[2] <= 1.0001:
        return cv2.resize(frame_rgb, (cw, ch), interpolation=cv2.INTER_AREA)
    cx, cy, m = zoom
    w, h = W / m, H / m
    x0, y0 = clamp(cx - w / 2, 0, W - w), clamp(cy - h / 2, 0, H - h)
    M = np.array([[cw / w, 0, -x0 * cw / w], [0, ch / h, -y0 * ch / h]], np.float64)
    return cv2.warpAffine(frame_rgb, M, (cw, ch), flags=cv2.INTER_AREA if m < 1.2 else cv2.INTER_LINEAR)


def local_zoom_anchor(content, box, anchor, m, feather=12):
    """magnify the content inside box (x0, y0, x1, y1) by m about anchor (ax, ay), soft edge of `feather` px
    around the magnified box.  m = 1 returns the content untouched (so the effect starts / ends seamlessly)."""
    if m <= 1.0005:
        return content
    x0, y0, x1, y1 = box
    ax, ay = anchor
    mx0, my0 = ax + (x0 - ax) * m, ay + (y0 - ay) * m
    mx1, my1 = ax + (x1 - ax) * m, ay + (y1 - ay) * m
    X0, Y0 = int(max(0, math.floor(mx0 - feather))), int(max(0, math.floor(my0 - feather)))
    X1, Y1 = int(min(content.shape[1], math.ceil(mx1 + feather))), int(min(content.shape[0], math.ceil(my1 + feather)))
    ww, hh = X1 - X0, Y1 - Y0
    # output pixel (u, v) of the window <- source anchor + ((X0 + u, Y0 + v) - anchor) / m
    M = np.array([[1 / m, 0, ax + (X0 - ax) / m], [0, 1 / m, ay + (Y0 - ay) / m]], np.float64)
    src = content.astype(np.float32)
    mag = cv2.warpAffine(src, M, (ww, hh), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
    yy, xx = np.mgrid[Y0:Y1, X0:X1].astype(np.float32) + 0.5
    d = np.maximum(np.maximum(mx0 - xx, xx - mx1), np.maximum(my0 - yy, yy - my1))
    a = np.clip(1 - d / feather, 0, 1)
    a = a * a * (3 - 2 * a)
    out = src.copy()
    out[Y0:Y1, X0:X1] = out[Y0:Y1, X0:X1] * (1 - a[..., None]) + mag * a[..., None]
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- misc
def paper_bg(seed, tone=SB.PAPER, dots=40):
    return np.asarray(SB.paper(tone=tone, dots=dots, seed=seed).convert('RGB'), np.float32)


def jdump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
