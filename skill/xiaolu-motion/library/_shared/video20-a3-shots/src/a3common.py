"""A3 (shots 15 and 16) shared code: paths, timeline, word onsets, frame IO, drawing, compositing, QA helpers.

Authorities, imported read-only and never copied:
  timeline -> 05_visual/storyboard_v2/src/timeline.py  (every v2 frame -> source frame goes through v2_to_src)
  sb_lib   -> 05_visual/storyboard_v2/src/sb_lib.py    (storyboard drawing kit: C subtitle, label, stamp, icons)
Small helpers of storyboard_v2/src/render_v2.py are copied verbatim (pill, badge, hud_brackets, glow, scissors,
check_chip) because importing render_v2 would pull its keyframe caches. Same design as the approved sample frames.

This file is identical in s15/src and s16/src (build.py checks the copies match).
"""
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

for _v in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ.setdefault(_v, '1')
import cv2  # noqa: E402
import numpy as np  # noqa: E402

cv2.setNumThreads(1)
# CPU budget per heavy task (coordinator rule, 2026-09-27): 4 threads = x264 2 + source decoder 1 + Python renderer 1
ENC_THREADS, DEC_THREADS = '2', '1'
from PIL import Image, ImageDraw, ImageFilter

VP = Path(os.environ.get("XM_VIDEO_PROJECT_ROOT", "."))  # your own project's working dir
SB2 = VP / '05_visual/storyboard_v2'
sys.path.insert(0, str(SB2 / 'src'))
import timeline as T  # noqa: E402  read-only authority
from sb_lib import (W, H, INK, CARD, YELLOW, RED, GREEN, SUB_CY, FONTS, font, label, stamp,  # noqa: E402,F401
                    icon_check, icon_cross, rotate, shadow_of, rrect_mask, sticker_outline, photo, paper, tape)

FPS = 30
SHOTS_DIR = VP / '05_visual/build/shots'
SRC_MOV = Path(T.SRC)
AUTH_SHA = {  # authorities this build was made against (recorded in meta.json)
    'storyboard_v2/src/timeline.py': '13978704192f3df332ae58cb1c34de4ad510a8494a5789238584d927437f4d07',
    'storyboard_v2/src/sb_lib.py': '41e778ca209ef6d078994dad92dacb625cd2aae7b866d1c6932e80a7e0899318',
    'storyboard_v2/src/render_v2.py': '0b7c519ecf28137ca268ee898c846343f71b9890df5f0cf901a2144466a28a10',
}
FONT_FILES = ['SourceHanSansSC-Medium.otf', 'SourceHanSansSC-Bold.otf', 'SourceHanSansSC-Heavy.otf']
STEP_BAND = (180, 280)          # A0 step bar lives at y 196-260 during shots 12-16: nothing of ours in 180-280
SUB_BAND = (1300, 1440)         # A0 main subtitle band (C strip centre 1368, bottom <= 1424)

# ffmpeg colour handling: identical filter strings to A0 (a0common.RawReader / encoder)
DEC_VF = 'scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int,format=rgb24'
ENC_VF = 'scale=in_range=pc:out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p'


# ------------------------------------------------------------------ time
def v2_frame(t):
    return int(round(t * FPS))


def src_frame(v2f):
    """v2 frame -> source frame via the timeline authority (the frame-centre grid, same call as A0)"""
    kind, seg, f = T.v2_to_src(v2f / FPS)
    assert kind == 'max', (v2f, kind)
    return f


def fmt(t):
    m, s = divmod(t, 60)
    return f'{int(m)}:{s:05.2f}'


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def prog(t, t0, dur):
    return clamp((t - t0) / dur) if dur > 0 else float(t >= t0)


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def ease_in_cubic(p):
    return p ** 3


def ease_in_out_cubic(p):
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def ease_in_out_sine(p):
    return -(math.cos(math.pi * p) - 1) / 2


def ease_out_back(p, s=1.70158):
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def pop(t, t0, dur=0.28, s=1.9):
    """0 -> overshoot -> 1 scale for a pop-in starting at t0 (0 before t0)"""
    if t < t0:
        return 0.0
    return ease_out_back(prog(t, t0, dur), s)


def pop_peak_time(t0, dur=0.28, s=1.9):
    """time of the overshoot peak of pop() (for pop_soft cues: 'same frame as the rebound apex')"""
    ps = np.linspace(0, 1, 401)
    v = [ease_out_back(p, s) for p in ps]
    return t0 + dur * ps[int(np.argmax(v))]


# ------------------------------------------------------------------ word timing (A0's words_v2.json / captions_v2.json)
WORDS_V2 = VP / '04_captions/words_v2.json'
CAPTIONS_V2 = VP / '04_captions/captions_v2.json'


def words_v2_units():
    return json.loads(WORDS_V2.read_text(encoding='utf-8'))['units'] if WORDS_V2.exists() else []


def unit_onset(units, text, near, tol=1.2):
    """v2 start of the run of units spelling `text` whose start is closest to `near` (None if not found)"""
    best = None
    for i in range(len(units)):
        acc = ''
        for j in range(i, min(i + 14, len(units))):
            acc += units[j]['w']
            if acc == text:
                d = abs(units[i]['s'] - near)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, units[i]['s'])
                break
            if not text.startswith(acc):
                break
    return None if best is None else best[1]


def onsets(word_text, env_src):
    """key onsets on the v2 clock: A0's words_v2.json (spectrogram-checked anchors) when present, else our own
    envelope estimates (source seconds -> v2). Returns (K, report)"""
    units = words_v2_units()
    K, rep = {}, {}
    for k, v in env_src.items():
        env = T.src_to_v2(v)
        w = unit_onset(units, word_text[k], env) if k in word_text else None
        K[k] = w if w is not None else env
        rep[k] = dict(text=word_text.get(k), words_v2=None if w is None else round(w, 3), envelope=round(env, 3),
                      used='words_v2' if w is not None else 'envelope')
    return K, rep


def caption_strip(text):
    """A0's strip for `text` from captions_v2.json: dict(f0, f1, keywords=[{text, f0, brush_frames}]) or None"""
    if not CAPTIONS_V2.exists():
        return None
    for st in json.loads(CAPTIONS_V2.read_text(encoding='utf-8'))['strips']:
        if st['text'] == text:
            return st
    return None


# ------------------------------------------------------------------ frame IO
class SrcReader:
    """sequential source frames (RGB full range) from src_first; frame-exact seek (f-0.5)/30"""

    def __init__(self, src_first, n, w=W, h=H):
        self.w, self.h, self.size = w, h, w * h * 3
        vf = DEC_VF if (w, h) == (W, H) else f'scale={w}:{h}:in_color_matrix=bt709:in_range=tv:out_range=pc:flags=area+accurate_rnd,format=rgb24'
        vf = 'settb=1/30,setpts=N,' + vf            # monotonic timestamps for the rawvideo pipe (frames untouched)
        self.p = subprocess.Popen(['ffmpeg', '-v', 'error', '-filter_threads', '1', '-threads', DEC_THREADS, '-ss', f'{(src_first - 0.5) / FPS:.6f}',
                                   '-i', str(SRC_MOV), '-map', '0:v:0', '-frames:v', str(n), '-vf', vf,
                                   '-fps_mode', 'passthrough', '-f', 'rawvideo', '-'],
                                  stdout=subprocess.PIPE, bufsize=self.size * 2)

    def read(self):
        b = self.p.stdout.read(self.size)
        if len(b) < self.size:
            return None
        return np.frombuffer(b, np.uint8).reshape(self.h, self.w, 3)

    def close(self):
        try:
            self.p.stdout.close()
        except Exception:
            pass
        try:
            self.p.kill()
        except Exception:
            pass
        self.p.wait()


def frames_by_index(indices, w=W, h=H):
    """source frames picked by decode index from the start of the file (select=eq(n,..)): an independent check of the
    frame-exact seek used by SrcReader. Heavy (decodes up to max(indices)); returns {index: HxWx3}"""
    idx = sorted(set(int(i) for i in indices))
    sel = '+'.join(f'eq(n\\,{i})' for i in idx)
    vf = f"select='{sel}'," + (DEC_VF if (w, h) == (W, H) else
                               f'scale={w}:{h}:in_color_matrix=bt709:in_range=tv:out_range=pc:flags=area+accurate_rnd,format=rgb24')
    r = subprocess.run(['ffmpeg', '-v', 'error', '-filter_threads', '1', '-threads', '2', '-i', str(SRC_MOV), '-map', '0:v:0', '-vf', vf,
                        '-fps_mode', 'passthrough', '-frames:v', str(len(idx)), '-f', 'rawvideo', '-'],
                       capture_output=True, check=True)
    n = w * h * 3
    assert len(r.stdout) == n * len(idx), (len(r.stdout), n * len(idx))
    return {i: np.frombuffer(r.stdout[k * n:(k + 1) * n], np.uint8).reshape(h, w, 3) for k, i in enumerate(idx)}


def grab_src(f, w=W, h=H):
    r = SrcReader(f, 1, w, h)
    a = r.read()
    r.close()
    return a.copy()


def encoder(out_partial):
    """H.264 High, CRF 10, yuv420p BT.709 tv, 30 fps CFR, no audio; output is a *.partial file (mp4)"""
    cmd = ['ffmpeg', '-v', 'error', '-y', '-filter_threads', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
           '-i', '-', '-vf', ENC_VF, '-c:v', 'libx264', '-preset', 'slow', '-crf', '10', '-profile:v', 'high',
           '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
           '-color_range', 'tv', '-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv',
           '-fps_mode', 'cfr', '-threads', ENC_THREADS, '-an', '-movflags', '+faststart', '-f', 'mp4', str(out_partial)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                        'stream=codec_name,profile,width,height,pix_fmt,r_frame_rate,avg_frame_rate,nb_read_frames,'
                        'color_range,color_space,color_transfer,color_primaries', '-show_entries',
                        'format=duration,nb_streams', '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    s = j['streams'][0]
    s['nb_streams'] = j['format']['nb_streams']
    s['duration'] = float(j['format']['duration'])
    return s


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def save_json(path, obj):
    p = Path(path)
    tmp = p.with_name(p.name + '.partial')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    tmp.rename(p)


# ------------------------------------------------------------------ faces (src/faces_track.py output)
class Faces:
    def __init__(self, path):
        j = json.loads(Path(path).read_text())
        self.fr = {int(k): v for k, v in j['frames'].items()}

    def face(self, f):
        return tuple(self.fr[f]['face'])

    def lips(self, f):
        return tuple(self.fr[f]['lips'])


# ------------------------------------------------------------------ helpers copied verbatim from render_v2.py
def pill(text, size=30, fg=(255, 255, 255), bg=INK, padx=20, h=None, weight='Heavy', radius=None, dot=None):
    f = font(weight, size)
    w = int(f.getlength(text) + 2 * padx + (26 if dot else 0))
    h = h or int(size * 1.7)
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius if radius is not None else h // 2, fill=bg)
    x = padx
    if dot:
        d.ellipse((padx - 4, h / 2 - 8, padx + 12, h / 2 + 8), fill=dot)
        x += 26
    d.text((x, h / 2), text, font=f, fill=fg, anchor='lm')
    return im


def hud_brackets(d, box, color, lw=7, L=46):
    x0, y0, x1, y1 = box
    for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.line((cx, cy, cx + sx * L, cy), fill=color, width=lw)
        d.line((cx, cy, cx, cy + sy * L), fill=color, width=lw)


def badge(kind, s=84):
    b = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(b).ellipse((0, 0, s - 1, s - 1), fill=RED if kind == 'x' else GREEN)
    if kind == 'x':
        b.alpha_composite(icon_cross(int(s * 0.74), color=(255, 255, 255), lw=11), (int(s * 0.13), int(s * 0.13)))
    else:
        b.alpha_composite(icon_check(int(s * 0.76), color=(255, 255, 255), lw=11), (int(s * 0.12), int(s * 0.14)))
    return b


def check_chip():
    return pill('STEP 4 剪辑成片 · 自检中', size=30, bg=(20, 20, 20, 225), dot=RED)


def scissors(s=46):
    im = Image.new('RGBA', (s * 2, s * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((s * 0.2, s * 1.1, s * 0.8, s * 1.7), outline=RED, width=7)
    d.ellipse((s * 1.2, s * 1.1, s * 1.8, s * 1.7), outline=RED, width=7)
    d.line((s * 0.7, s * 1.15, s * 1.35, s * 0.1), fill=RED, width=8)
    d.line((s * 1.3, s * 1.15, s * 0.65, s * 0.1), fill=RED, width=8)
    return im.resize((s, s), Image.LANCZOS)


def glow(size, color=(255, 214, 10), alpha=150):
    w, h = size
    a = Image.new('L', (w * 2, h * 2), 0)
    ImageDraw.Draw(a).ellipse((w / 2, h / 2, w * 1.5, h * 1.5), fill=alpha)
    a = a.filter(ImageFilter.GaussianBlur(min(size) / 4))
    g = Image.new('RGBA', (w * 2, h * 2), color + (0,))
    g.putalpha(a)
    return g


# ------------------------------------------------------------------ C subtitle with the keyword marker wipe
_sub_cache = {}


def subtitle_layer(runs, cy=SUB_CY, size=66, cx=W / 2, marker_p=1.0):
    """sb_lib.subtitle_c drawn on a transparent canvas (same geometry, fonts, colours, shadow), except that the
    yellow marker under each keyword run is revealed left -> right by marker_p (0..1). Returns (RGBA crop, x, y, bbox)
    where bbox is the strip box in canvas coordinates. marker_p is quantised to 1/64 for caching."""
    mp = round(clamp(marker_p) * 64) / 64
    key = (tuple(runs), round(cy, 1), size, round(cx, 1), mp)
    if key in _sub_cache:
        return _sub_cache[key]
    fN, fK = font('Medium', size), font('Heavy', size)
    chars = [(ch, k) for t, k in runs for ch in t]
    xs, x = [], 0.0
    for i, (ch, k) in enumerate(chars):
        xs.append(x)
        x += (fK if k else fN).getlength(ch) + (2 if i < len(chars) - 1 else 0)
    tw = x
    padx, pady = 30, 20
    x0 = cx - tw / 2
    baseline = cy + 24
    top, bottom = baseline - 60 - pady, baseline + 12 + pady
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.rounded_rectangle((x0 - padx, top, x0 + tw + padx, bottom), radius=16, fill=(255, 255, 255, 245))
    soft = lay.split()[3].filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.35))
    sh = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sh.putalpha(soft)
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    out.alpha_composite(sh, (0, 6))
    out.alpha_composite(lay)
    d = ImageDraw.Draw(out)
    i = 0
    while i < len(chars):
        if chars[i][1]:
            j = i
            while j + 1 < len(chars) and chars[j + 1][1]:
                j += 1
            kx0 = x0 + xs[i] - 6
            kx1 = x0 + xs[j] + fK.getlength(chars[j][0]) + 6
            if mp > 0:
                d.rectangle((kx0, baseline - 30, kx0 + (kx1 - kx0) * mp, baseline + 8), fill=YELLOW)
            i = j + 1
        else:
            i += 1
    for (ch, k), cx_ in zip(chars, xs):
        d.text((x0 + cx_, baseline), ch, font=fK if k else fN, fill=(20, 20, 20), anchor='ls')
    bb = (int(x0 - padx), int(top), int(x0 + tw + padx), int(bottom))
    a = np.array(out.split()[3])
    ys, xs_ = np.where(a > 0)
    cx0, cy0, cx1, cy1 = int(xs_.min()), int(ys.min()), int(xs_.max()) + 1, int(ys.max()) + 1
    res = (out.crop((cx0, cy0, cx1, cy1)), cx0, cy0, bb)
    if len(_sub_cache) > 400:
        _sub_cache.clear()
    _sub_cache[key] = res
    return res


def marker_progress(fi, f_key, brush_frames=12):
    """keyword marker brushed left -> right from frame f_key over brush_frames frames (A0 captions_v2 convention:
    f_key = floor(onset * 30), brush_frames = min(12, max(6, keyword length in frames)), linear)"""
    return clamp((fi - f_key + 1) / brush_frames)


# ------------------------------------------------------------------ PIL compositing with clipping
def paste(dst, elem, x, y, alpha=1.0):
    """alpha-composite RGBA `elem` onto RGBA `dst` at (x, y) (float ok, rounded), clipped; returns the drawn bbox"""
    if elem is None or alpha <= 0:
        return None
    if alpha < 1:
        e = elem.copy()
        e.putalpha(e.split()[3].point(lambda v: int(v * alpha + 0.5)))
        elem = e
    x, y = int(round(x)), int(round(y))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst.width, x + elem.width), min(dst.height, y + elem.height)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = elem.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    dst.alpha_composite(crop, (x0, y0))
    a = np.array(crop.split()[3])
    ys, xs = np.where(a > 40)
    if not len(xs):
        return None
    return (x0 + int(xs.min()), y0 + int(ys.min()), x0 + int(xs.max()), y0 + int(ys.max()))


def transform(elem, scale=1.0, rot=0.0):
    """scaled + rotated copy (rotation in degrees, PIL convention: positive = counter-clockwise)"""
    if scale <= 0.001:
        return None
    e = elem
    if abs(scale - 1) > 1e-3:
        e = e.resize((max(1, int(round(e.width * scale))), max(1, int(round(e.height * scale)))), Image.BICUBIC)
    if abs(rot) > 1e-3:
        e = e.rotate(rot, resample=Image.BICUBIC, expand=True)
    return e


def paste_c(dst, elem, cx, cy, scale=1.0, rot=0.0, alpha=1.0, shadow=None):
    """paste centred at (cx, cy) with scale / rotation; shadow = (blur, alpha, dx, dy) or None"""
    e = transform(elem, scale, rot)
    if e is None:
        return None
    if shadow:
        blur, sa, dx, dy = shadow
        sh, pad = shadow_of(e, blur=blur, alpha=sa)
        paste(dst, sh, cx - e.width / 2 - pad + dx, cy - e.height / 2 - pad + dy, alpha)
    return paste(dst, e, cx - e.width / 2, cy - e.height / 2, alpha)


# ------------------------------------------------------------------ QA helpers
def inter(a, b, m=0):
    return not (a[2] + m <= b[0] or b[2] + m <= a[0] or a[3] + m <= b[1] or b[3] + m <= a[1])


def glyph_missing(texts, weights=('Medium', 'Bold', 'Heavy')):
    """characters of `texts` that a font lacks (tofu check via the cmap of the actual font files)"""
    from fontTools.ttLib import TTFont
    miss = {}
    for wgt in weights:
        cmap = TTFont(str(FONTS / f'SourceHanSansSC-{wgt}.otf'), lazy=True).getBestCmap()
        m = sorted({c for s in texts for c in s if not c.isspace() and ord(c) not in cmap})
        if m:
            miss[wgt] = m
    return miss


BANNED = ['剪映', 'Claude', 'claude', 'Codex', 'codex', 'GitHub', 'Github', 'github', '小红书', '抖音', 'CapCut',
          'capcut', 'ChatGPT', 'OpenAI', 'Cursor', '快手', 'B站', '哔哩', '视频号', 'Remotion', 'HyperFrames']


def contact_sheet(frames, labels, cols, cell_w, out_path, quality=86):
    """frames: list of HxWx3 uint8; writes a JPEG grid with a small time label under each cell"""
    cell_h = int(cell_w * 16 / 9)
    rows = (len(frames) + cols - 1) // cols
    lab_h = 26
    sheet = Image.new('RGB', (cols * cell_w, rows * (cell_h + lab_h)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    f = font('Bold', 20)
    for i, (fr, lb) in enumerate(zip(frames, labels)):
        x, y = (i % cols) * cell_w, (i // cols) * (cell_h + lab_h)
        sheet.paste(Image.fromarray(fr).resize((cell_w, cell_h), Image.LANCZOS), (x, y))
        d.text((x + 6, y + cell_h + 3), lb, font=f, fill=(235, 235, 235))
    tmp = Path(str(out_path) + '.partial')
    sheet.save(tmp, 'JPEG', quality=quality)
    tmp.rename(out_path)
    return sheet.size
