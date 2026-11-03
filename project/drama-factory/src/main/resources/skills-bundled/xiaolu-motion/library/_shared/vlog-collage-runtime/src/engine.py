"""engine.py — tiny frame compositor for the collage vlog.

Everything is premultiplied float32 (RGB canvas, RGBA sprites). Pages are full-canvas paper
scenes holding timed elements; page-to-page transitions (flip / sweep / tear-off / swipe /
rise / curtain) combine two rendered pages. Deterministic: a frame depends only on t.
"""
import hashlib
import math
import subprocess

import cv2
import numpy as np
from PIL import Image

W, H, FPS = 1080, 1920, 30
BOIL_HZ = 8          # stickers re-jitter 8x per second (= 16th notes at 120 BPM)


# ------------------------------------------------------------------ easing
def c01(q):
    return 0.0 if q <= 0 else 1.0 if q >= 1 else q


def back_out(q, s=1.9):
    q = c01(q) - 1
    return q * q * ((s + 1) * q + s) + 1


def back_in(q, s=1.7):
    q = c01(q)
    return q * q * ((s + 1) * q - s)


def expo_out(q):
    q = c01(q)
    return 1.0 if q >= 1 else 1 - 2 ** (-10 * q)


def expo_in(q):
    q = c01(q)
    return 0.0 if q <= 0 else 2 ** (10 * (q - 1))


def cubic_io(q):
    q = c01(q)
    return 4 * q ** 3 if q < 0.5 else 1 - (-2 * q + 2) ** 3 / 2


def quad_out(q):
    q = c01(q)
    return 1 - (1 - q) ** 2


def hrand(*keys):
    h = hashlib.md5(repr(keys).encode()).digest()
    return int.from_bytes(h[:4], 'little') / 2 ** 32


# ------------------------------------------------------------------ sprites
def to_spr(img):
    a = np.asarray(img.convert('RGBA'), np.float32) / 255.0
    a = a.copy()
    a[..., :3] *= a[..., 3:4]
    return a


def draw(canvas, spr, cx, cy, ang=0.0, sc=1.0, alpha=1.0, sx=1.0, sy=1.0, interp=cv2.INTER_LINEAR):
    """alpha-composite a premultiplied RGBA sprite centred at (cx, cy); ang in degrees (ccw+).
    returns the canvas bbox touched (x0, y0, x1, y1) or None"""
    if alpha <= 0.004 or sc * min(sx, sy) <= 0.01:
        return None
    h, w = spr.shape[:2]
    Hc, Wc = canvas.shape[:2]
    a = math.radians(ang); ca, sa = math.cos(a), math.sin(a)
    kx, ky = sc * sx, sc * sy
    m00, m01, m10, m11 = ca * kx, sa * ky, -sa * kx, ca * ky
    tx = cx - (m00 * w / 2 + m01 * h / 2)
    ty = cy - (m10 * w / 2 + m11 * h / 2)
    xs = [tx, m00 * w + tx, m01 * h + tx, m00 * w + m01 * h + tx]
    ys = [ty, m10 * w + ty, m11 * h + ty, m10 * w + m11 * h + ty]
    x0 = max(0, int(math.floor(min(xs)))); x1 = min(Wc, int(math.ceil(max(xs))))
    y0 = max(0, int(math.floor(min(ys)))); y1 = min(Hc, int(math.ceil(max(ys))))
    if x1 <= x0 or y1 <= y0:
        return None
    if abs(ang) < 1e-6 and abs(kx - 1) < 1e-6 and abs(ky - 1) < 1e-6 and abs(tx - round(tx)) < 1e-6 and abs(ty - round(ty)) < 1e-6:
        sx0 = x0 - int(round(tx)); sy0 = y0 - int(round(ty))
        out = spr[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
    else:
        M = np.array([[m00, m01, tx - x0], [m10, m11, ty - y0]], np.float32)
        out = cv2.warpAffine(spr, M, (x1 - x0, y1 - y0), flags=interp, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    al = out[..., 3:4] * alpha
    reg = canvas[y0:y1, x0:x1]
    reg *= (1.0 - al)
    reg += out[..., :3] * alpha
    return (x0, y0, x1, y1)


def reveal(spr, q, soft=18):
    """left-to-right write-on mask for handwriting (q 0..1)"""
    if q >= 1:
        return spr
    w = spr.shape[1]
    edge = q * (w + soft)
    x = np.arange(w, dtype=np.float32)
    m = np.clip((edge - x) / soft, 0, 1)[None, :, None]
    return spr * m


# ------------------------------------------------------------------ video frames
class Reader:
    """sequential RGB frames from a 30 fps CFR proxy; re-seeks only when needed"""

    def __init__(self, path, w, h, fps=FPS):
        self.path, self.w, self.h, self.fps = path, w, h, fps
        self.p = None; self.next = 0; self.last = None

    def _open(self, idx):
        self.close()
        ss = max(0.0, (idx - 0.5) / self.fps)
        self.p = subprocess.Popen(['ffmpeg', '-v', 'error', '-ss', f'{ss:.4f}', '-i', self.path,
                                   '-vf', 'scale=in_color_matrix=bt709:in_range=limited,format=rgb24',
                                   '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE, bufsize=10 ** 8)
        self.next = idx; self.last = None

    def get(self, idx):
        idx = max(0, idx)
        if self.p is None or idx < self.next - 1 or idx > self.next + 45 or (idx == self.next - 1 and self.last is None):
            self._open(idx)
        if idx == self.next - 1 and self.last is not None:
            return self.last
        n = self.w * self.h * 3
        while self.next <= idx:
            buf = self.p.stdout.read(n)
            if len(buf) < n:
                break
            self.last = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
            self.next += 1
        return self.last

    def close(self):
        if self.p is not None:
            try:
                self.p.stdout.close(); self.p.kill(); self.p.wait()
            except Exception:
                pass
            self.p = None


def grade(a_u8):
    """soft warm film-ish grade for footage (low saturation, lifted blacks, creamy highlights)"""
    a = a_u8.astype(np.float32) * (1 / 255.0)
    L = a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722
    a = L[..., None] + (a - L[..., None]) * 0.88
    a = 0.028 + a * 0.955
    hl = np.clip((L - 0.5) * 2, 0, 1)[..., None]
    a += hl * np.array([0.018, 0.008, -0.012], np.float32)
    a += (1 - hl) * np.array([0.006, 0.002, -0.004], np.float32)
    return np.clip(a, 0, 1)


def cover(frame, ww, wh, fx=0.5, fy=0.5, zoom=1.0, fast=False):
    """scale-to-cover crop (float focus + zoom, subpixel) -> uint8 (wh, ww, 3)"""
    sh, sw = frame.shape[:2]
    s = max(ww / sw, wh / sh) * zoom
    cw, ch = ww / s, wh / s
    x0 = (sw - cw) * fx; y0 = (sh - ch) * fy
    if s < 0.95 and not fast:   # downscale: area-average first to avoid shimmer, then subpixel place
        pre = 1.0 / s
        k = int(math.floor(pre))
        if k >= 2:
            small = cv2.resize(frame, (sw // k, sh // k), interpolation=cv2.INTER_AREA)
            frame = small; s = s * k; x0 /= k; y0 /= k
            sh, sw = frame.shape[:2]
    M = np.array([[s, 0, -x0 * s], [0, s, -y0 * s]], np.float32)
    return cv2.warpAffine(frame, M, (ww, wh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


# ------------------------------------------------------------------ transitions
def torn_mask_1d(n, seed, amp):
    r = np.random.default_rng(seed)
    size = 1 << int(math.ceil(math.log2(max(2, n))))
    p = np.zeros(size + 1, np.float32); step = size; a = amp
    while step > 1:
        half = step // 2
        for i in range(0, size, step):
            p[i + half] = (p[i] + p[i + step]) / 2 + r.uniform(-a, a)
        step = half; a *= 0.6
    return p[:n] + r.uniform(-1.0, 1.0, n).astype(np.float32)


_edge_cache = {}


def edge_profile(key, n, amp):
    k = (key, n, amp)
    if k not in _edge_cache:
        _edge_cache[k] = torn_mask_1d(n, hash(key) % 10000, amp)
    return _edge_cache[k]


RIM = np.array([1.0, 0.992, 0.972], np.float32)      # white paper core showing along a tear


def _blend_edge(old, new, cov, rim):
    """cov: coverage of new page (H,W) float; rim: white-core rim mask"""
    out = old * (1 - cov[..., None]) + new * cov[..., None]
    if rim is not None:
        out = out * (1 - rim[..., None]) + RIM * rim[..., None]
    return out


def shadow_band(dist, width=60, strength=0.35):
    return np.clip(1 - dist / width, 0, 1) ** 1.6 * strength


def trans_sweep(old, new, p, key, direction='left', amp=26, rim=11):
    """new page with a torn leading edge slides in over the old one (expo out)"""
    e = expo_out(p)
    if direction in ('left', 'right'):
        off = (1 - e) * (W + 3 * amp + rim + 40)
        prof = edge_profile(key, H, amp)                      # per-row edge x offset
        xs = np.arange(W, dtype=np.float32)[None, :]
        edge = (off + prof)[:, None]                           # new page starts at x >= edge
        if direction == 'right':                               # comes from the left
            xs = (W - 1) - xs
        d = xs - edge
        cov = np.clip(d - rim + 0.5, 0, 1)
        rimm = np.clip(d + 0.5, 0, 1) - cov
        shift = int(round(off))
        nn = np.zeros_like(new)
        if direction == 'left':
            if shift < W:
                nn[:, shift:] = new[:, :W - shift]
        else:
            if shift < W:
                nn[:, :W - shift] = new[:, shift:]
        sh = shadow_band(np.maximum(0, -d), 70, 0.42)
        oldd = old * (1 - sh[..., None])
        vel = (expo_out(min(1, p + 0.04)) - e) * W
        if vel > 6:
            k = int(min(41, vel * 0.9)) | 1
            nn = cv2.blur(nn, (k, 1))
        return _blend_edge(oldd, nn, cov, rimm)
    # vertical: 'up' (from bottom) or 'down' (from top)
    off = (1 - e) * (H + 3 * amp + rim + 40)
    prof = edge_profile(key, W, amp)
    ys = np.arange(H, dtype=np.float32)[:, None]
    if direction == 'down':
        ys = (H - 1) - ys
    d = ys - (off + prof)[None, :]
    cov = np.clip(d - rim + 0.5, 0, 1)
    rimm = np.clip(d + 0.5, 0, 1) - cov
    shift = int(round(off))
    nn = np.zeros_like(new)
    if shift < H:
        if direction == 'up':
            nn[shift:] = new[:H - shift]
        else:
            nn[:H - shift] = new[shift:]
    sh = shadow_band(np.maximum(0, -d), 80, 0.45)
    oldd = old * (1 - sh[..., None])
    vel = (expo_out(min(1, p + 0.04)) - e) * H
    if vel > 6:
        k = int(min(41, vel * 0.9)) | 1
        nn = cv2.blur(nn, (1, k))
    return _blend_edge(oldd, nn, cov, rimm)


def trans_tearoff(old, new, p, key, amp=30, rim=12):
    """old page is torn off upwards: the tear line runs bottom -> top revealing the new page"""
    e = cubic_io(p)
    line = H * (1 - e) - 60 * e
    prof = edge_profile(key, W, amp)
    ys = np.arange(H, dtype=np.float32)[:, None]
    lift = int(round(e * 60))                                  # the torn-off part lifts a bit
    oo = np.zeros_like(old)
    oo[:H - lift] = old[lift:]
    d = (line + prof)[None, :] - ys                            # >0 : old page still there
    covo = np.clip(d - rim + 0.5, 0, 1)
    rimm = np.clip(d + 0.5, 0, 1) - covo
    sh = shadow_band(np.maximum(0, -d), 90, 0.4)
    newd = new * (1 - sh[..., None])
    return _blend_edge(newd, oo, covo, rimm)


def trans_flip(old, new, p, D=5.0):
    """old page turns away around the left spine (perspective), revealing the new page"""
    th = math.pi / 2 * (c01(p) ** 1.1)
    s_r = D * W / (D * W - W * math.sin(th))
    xr = W * math.cos(th) * s_r
    if xr < 2:
        return new
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    dst = np.float32([[0, 0], [xr, H / 2 - H / 2 * s_r], [xr, H / 2 + H / 2 * s_r], [0, H]])
    Mx = cv2.getPerspectiveTransform(src, dst)
    xs0 = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    shade = 1 - (0.12 + 0.4 * xs0 ** 2) * math.sin(th)
    oa = np.dstack([old * shade, np.ones(old.shape[:2], np.float32)])
    warped = cv2.warpPerspective(oa, Mx, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    # shadow cast on the new page just right of the turning edge
    xs = np.arange(W, dtype=np.float32)[None, :]
    sh = np.clip(1 - (xs - xr) / (90 + 260 * math.sin(th)), 0, 1) * (xs >= xr) * 0.45 * math.sin(th) ** 0.6
    base = new * (1 - sh[..., None])
    a = warped[..., 3:4]
    return base * (1 - a) + warped[..., :3]


def trans_swipe(old, new, p, gap=36):
    """photo-carousel swipe: old slides out left, new slides in from right"""
    e = cubic_io(p)
    off = int(round(e * (W + gap)))
    out = np.empty_like(old)
    out[:] = np.array([0.93, 0.9, 0.84], np.float32)
    if off < W:
        out[:, :W - off] = old[:, off:]
    xs0 = W - off + gap
    if xs0 < W:
        n = W - max(0, xs0)
        out[:, max(0, xs0):] = new[:, :n]
    return out


# ------------------------------------------------------------------ finishing
class Finisher:
    def __init__(self, seed=5):
        r = np.random.default_rng(seed)
        self.grain = []
        for i in range(4):   # 4 noise plates rotated per frame
            n = r.normal(0, 1, (H // 2, W // 2)).astype(np.float32)
            n = cv2.resize(cv2.GaussianBlur(n, (0, 0), 0.7), (W, H), interpolation=cv2.INTER_LINEAR)
            self.grain.append((n / n.std()).astype(np.float32))
        ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((xs - W / 2) / (W / 2)) ** 2 + ((ys - H / 2) / (H / 2)) ** 2) / 1.35
        self.vig = (1 - np.clip((d - 0.5) / 0.55, 0, 1) ** 1.6 * 0.12).astype(np.float32)[..., None]

    def __call__(self, canvas, fi):
        a = canvas * self.vig
        L = a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722
        g = self.grain[fi % 4]
        a = a + (g * (0.018 + 0.03 * L * (1 - L)))[..., None]
        # warm soft-light lift: shadows a touch cool, highlights warm
        a += (np.clip(L - 0.55, 0, 1)[..., None] * np.array([0.02, 0.008, -0.01], np.float32))
        return np.clip(a, 0, 1)
