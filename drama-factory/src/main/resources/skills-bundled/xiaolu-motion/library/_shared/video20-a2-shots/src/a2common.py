"""Shared kit for the A2 shot renderers (13 chat, 14 card table + style brush, 18 split screen).

Drawing primitives come straight from storyboard_v2/src/sb_lib.py (the approved storyboard kit, read-only),
so the moving version and the storyboard stills are the same design: paper, label, pip_card, stamp, tape,
icons, fonts (Source Han Sans SC from this repo's fonts/, see a2paths.XM_FONTS).

Compositing is done in float32 RGB [0, 1] with numpy / OpenCV; UI elements are drawn with PIL (RGBA) and
pasted with `paste_rgba`. The presenter's footage is decoded frame-exact from the source (BT.709 tv -> RGB)
and never re-timed: every output frame k uses the source frame timeline.v2_to_src(k / 30).
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import a2paths
from a2paths import SRC_VIDEO, WORK, W, H, FPS, DEMOS
import timeline as TL
import sb_lib as SB
from sb_lib import (font, paper, label, rotate, shadow_of, tape, stamp, photo, rrect_mask, pip_card, icon_check,
                    icon_cross, icon_heart, icon_star, icon_sun, burst, torn_edge_mask, INK, PAPER, CARD, KRAFT, YELLOW,
                    RED, GREEN, BLUE, GREY, PIP_BOX, SUB_CY)

X264 = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '10', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv']
RGB2YUV = 'scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p'
YUV2RGB = 'scale=in_color_matrix=bt709:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb24'


# ------------------------------------------------------------------ easing
def clamp01(x):
    return 0.0 if x <= 0 else 1.0 if x >= 1 else float(x)


def lerp(a, b, t):
    return a + (b - a) * t


def prog(t, t0, t1):
    return clamp01((t - t0) / (t1 - t0)) if t1 > t0 else float(t >= t1)


def e_io(x):              # ease in-out cubic
    x = clamp01(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def e_out(x, p=3):
    x = clamp01(x)
    return 1 - (1 - x) ** p


def e_in(x, p=3):
    return clamp01(x) ** p


def e_back(x, s=1.7):     # ease-out-back (small overshoot)
    x = clamp01(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def pop(t, t0, dur=0.28, over=0.12):
    """0 -> 1 scale with one overshoot (1 + over at ~60%), settles at 1 by t0 + dur"""
    x = prog(t, t0, t0 + dur)
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    if x < 0.6:
        return e_out(x / 0.6, 2) * (1 + over)
    return 1 + over * (1 - e_io((x - 0.6) / 0.4))


# ------------------------------------------------------------------ images
def to_f(im):
    """PIL RGB(A) -> float32 [0,1] (RGB only)"""
    return np.asarray(im.convert('RGB'), np.float32) / 255.0


def to_u8(a):
    return np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8)


def paste_rgba(canvas, elem, x, y, alpha=1.0):
    """alpha-composite a PIL RGBA element (straight alpha) onto a float canvas at integer (x, y)"""
    if alpha <= 0:
        return
    x, y = int(round(x)), int(round(y))
    ew, eh = elem.size
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + ew), min(H, y + eh)
    if x1 <= x0 or y1 <= y0:
        return
    e = np.asarray(elem.crop((x0 - x, y0 - y, x1 - x, y1 - y)), np.float32) / 255.0
    a = e[..., 3:4] * alpha
    canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - a) + e[..., :3] * a


def paste_f(canvas, rgb, a, x, y):
    """composite float rgb (h,w,3) with alpha (h,w) at (x, y)"""
    x, y = int(round(x)), int(round(y))
    h, w = a.shape
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    rr = rgb[y0 - y:y1 - y, x0 - x:x1 - x]
    aa = a[y0 - y:y1 - y, x0 - x:x1 - x, None]
    canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - aa) + rr * aa


def affine_elem(elem, scale=1.0, rot=0.0, cx=0.0, cy=0.0, alpha=1.0, blur=0):
    """render a PIL RGBA element scaled / rotated about its centre, centred at (cx, cy) on a full canvas layer;
    returns (premultiplied rgb (H,W,3), alpha (H,W)) - subpixel-smooth motion via cv2.warpAffine"""
    e = np.asarray(elem, np.float32) / 255.0
    pm = np.dstack([e[..., :3] * e[..., 3:4], e[..., 3]])
    eh, ew = e.shape[:2]
    M = cv2.getRotationMatrix2D((ew / 2, eh / 2), rot, scale)
    M[0, 2] += cx - ew / 2
    M[1, 2] += cy - eh / 2
    out = cv2.warpAffine(pm, M, (W, H), flags=cv2.INTER_LINEAR if scale >= 0.7 else cv2.INTER_AREA,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    if blur:
        out = cv2.GaussianBlur(out, (0, 0), blur)
    return out[..., :3] * alpha, out[..., 3] * alpha


def over_pm(canvas, rgb_pm, a):
    canvas *= (1 - a[..., None])
    canvas += rgb_pm


def elem_bbox(a, thr=0.16):
    ys, xs = np.where(a > thr)
    if not len(xs):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def rounded_mask(x, y, w, h, r):
    """anti-aliased rounded-rect coverage (H, W) float, subpixel position"""
    m = np.zeros((H, W), np.float32)
    x0, y0 = max(0, int(math.floor(x)) - 2), max(0, int(math.floor(y)) - 2)
    x1, y1 = min(W, int(math.ceil(x + w)) + 2), min(H, int(math.ceil(y + h)) + 2)
    if x1 <= x0 or y1 <= y0:
        return m
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    cx, cy = x + w / 2, y + h / 2
    r = max(0.0, min(r, w / 2, h / 2))
    qx = np.abs(xx + 0.5 - cx) - (w / 2 - r)
    qy = np.abs(yy + 0.5 - cy) - (h / 2 - r)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    m[y0:y1, x0:x1] = np.clip(0.5 - d, 0, 1)
    return m


def soft_shadow(a, blur=12, alpha=0.3, dx=3, dy=7):
    """drop shadow alpha (H,W) from an element alpha"""
    s = cv2.GaussianBlur(a, (0, 0), blur) * alpha
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(s, M, (W, H), borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def darken(canvas, a, color=(20 / 255, 16 / 255, 10 / 255)):
    canvas *= (1 - a[..., None])
    canvas += a[..., None] * np.array(color, np.float32)


# ------------------------------------------------------------------ source footage
def v2_src_frame(k):
    kind, seg, f = TL.v2_to_src(k / FPS)
    if kind != 'max':
        raise ValueError(f'v2 frame {k} is an insert')
    return f


def src_runs(k0, k1):
    """contiguous runs of source frames for v2 frames [k0, k1): [(k_start, src_start, n)]"""
    runs = []
    for k in range(k0, k1):
        f = v2_src_frame(k)
        if runs and runs[-1][1] + runs[-1][2] == f and runs[-1][0] + runs[-1][2] == k:
            runs[-1][2] += 1
        else:
            runs.append([k, f, 1])
    return [tuple(r) for r in runs]


class FrameStream:
    """sequential RGB uint8 frames of a video from frame `start` (CFR, frame-exact seek), n frames"""

    def __init__(self, video, start, n, fps=FPS, size=(W, H), vf=YUV2RGB):
        self.w, self.h = size
        self.n, self.k = n, 0
        # -fps_mode passthrough: without it ffmpeg 8 duplicates the first frame after an input seek (rawvideo output is
        # constant-frame-rate by default), so every later frame of the run would lag the audio by one frame
        self.p = subprocess.Popen(['ffmpeg', '-v', 'error', '-threads', '1', '-ss', f'{(start - 0.5) / fps:.6f}', '-i', str(video),
                                   '-frames:v', str(n), '-vf', vf, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                                  stdout=subprocess.PIPE)

    def read(self):
        if self.k >= self.n:
            return None
        b = self.p.stdout.read(self.w * self.h * 3)
        if len(b) < self.w * self.h * 3:
            raise RuntimeError(f'short read after {self.k} frames')
        self.k += 1
        return np.frombuffer(b, np.uint8).reshape(self.h, self.w, 3)

    def close(self):
        try:
            self.p.stdout.close()
        except Exception:
            pass
        self.p.wait()


class MatteStream:
    """sequential gray mattes from a WORK/matte*.mkv (FFV1), starting at matte index i0"""

    def __init__(self, path, i0, n):
        vf = f'select=gte(n\\,{i0})' if i0 else 'null'
        self.n, self.k = n, 0
        self.p = subprocess.Popen(['ffmpeg', '-v', 'error', '-threads', '1', '-i', str(path), '-vf', vf, '-fps_mode', 'passthrough',
                                   '-frames:v', str(n), '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], stdout=subprocess.PIPE)

    def read(self):
        b = self.p.stdout.read(W * H)
        if len(b) < W * H:
            raise RuntimeError(f'short matte read after {self.k}')
        self.k += 1
        return np.frombuffer(b, np.uint8).reshape(H, W)

    def close(self):
        try:
            self.p.stdout.close()
        except Exception:
            pass
        self.p.wait()


def load_faces():
    out = {}
    for line in (WORK / 'faces_src.jsonl').read_text().splitlines():
        if line.strip():
            d = json.loads(line)
            out[d['frame']] = (tuple(d['face']), tuple(d['lips']))
    return out


def grab(video, f, fps=FPS):
    """one frame (RGB uint8) of a video, frame-exact"""
    fs = FrameStream(video, f, 1, fps=fps)
    im = fs.read()
    fs.close()
    return im


# ------------------------------------------------------------------ person re-composite (clean plate)
class Host:
    """premultiplied foreground of the presenter from the matte and the shot's clean plate (P = I - (1-a) plate where the
    plate was really seen; I * a elsewhere), then warped by the same affine as the new layout"""

    def __init__(self, plate_png):
        pl = cv2.cvtColor(cv2.imread(str(plate_png)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        seen = cv2.imread(str(Path(plate_png).with_name(Path(plate_png).stem + '_seen.png')), 0).astype(np.float32) / 255.0
        seen = cv2.erode(seen, np.ones((9, 9), np.uint8))
        self.plate = pl
        self.seen = cv2.GaussianBlur(seen, (0, 0), 6)[..., None]

    def premult(self, img_u8, matte_u8):
        I = img_u8.astype(np.float32) / 255.0
        a = matte_u8.astype(np.float32) / 255.0
        A = a[..., None]
        exact = np.clip(I - (1 - A) * self.plate, 0, None)
        P = self.seen * exact + (1 - self.seen) * I * A
        return np.minimum(P, A), a


def warp_affine(img, M, border=cv2.BORDER_CONSTANT, interp=None):
    if interp is None:
        interp = cv2.INTER_AREA if abs(M[0, 0]) < 0.75 else cv2.INTER_LINEAR
    return cv2.warpAffine(img, M, (W, H), flags=interp, borderMode=border, borderValue=0)


def scale_about(s, cx, cy, tx=0.0, ty=0.0):
    """affine: scale s about (cx, cy), then translate"""
    return np.float32([[s, 0, cx * (1 - s) + tx], [0, s, cy * (1 - s) + ty]])


def map_box(b, M):
    x0, y0 = M[0, 0] * b[0] + M[0, 2], M[1, 1] * b[1] + M[1, 2]
    x1, y1 = M[0, 0] * b[2] + M[0, 2], M[1, 1] * b[3] + M[1, 2]
    return [int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))]


# ------------------------------------------------------------------ encode + verify (write *.partial, ffprobe, rename)
class Encoder:
    def __init__(self, out_path, n_frames):
        self.out = Path(out_path)
        self.tmp = self.out.with_name(self.out.name + '.partial')
        self.n = n_frames
        self.count = 0
        self.p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-threads', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                                   '-r', str(FPS), '-i', '-', '-vf', RGB2YUV, *X264, '-threads', '2', '-r', str(FPS), '-an',
                                   '-movflags', '+faststart', '-f', 'mp4', str(self.tmp)], stdin=subprocess.PIPE)

    def write(self, frame_u8):
        assert frame_u8.shape == (H, W, 3) and frame_u8.dtype == np.uint8
        self.p.stdin.write(frame_u8.tobytes())
        self.count += 1

    def close(self):
        self.p.stdin.close()
        if self.p.wait() != 0:
            raise RuntimeError('encoder failed')
        info = probe(self.tmp)
        v = info['v']
        ok = (v['nb_read_frames'] == self.n and v['codec_name'] == 'h264' and v['profile'] == 'High' and v['pix_fmt'] == 'yuv420p'
              and v['width'] == W and v['height'] == H and v['r_frame_rate'] == '30/1' and v.get('color_space') == 'bt709'
              and v.get('color_range') == 'tv' and not info['audio'])
        if not ok:
            raise RuntimeError(f'probe mismatch: {info}')
        self.tmp.rename(self.out)
        return info


def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_entries',
                        'stream=codec_type,codec_name,profile,pix_fmt,width,height,r_frame_rate,avg_frame_rate,nb_read_frames,'
                        'color_space,color_range,color_transfer,color_primaries,duration',
                        '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    ss = json.loads(r.stdout)['streams']
    v = [s for s in ss if s['codec_type'] == 'video'][0]
    v['nb_read_frames'] = int(v['nb_read_frames'])
    return {'v': v, 'audio': [s for s in ss if s['codec_type'] == 'audio']}


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()
