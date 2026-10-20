"""Shot 15 - STEP 3 分镜脚本: a film strip on a light table; the current gate is always the presenter's live footage.

v2 1:37.90-1:53.13 = v2 frames [2937, 3394) = source frames 5151..5607 (cut-plan segment 16, one continuous take).
Storyboard v2 row 15 + shot15.png (same kit: render_v2.film_strip look, 405x720 gate with a yellow frame,
「实拍 · 正在说」 pill, yellow 转场 arrow, green 音效 wave, sb_lib.stamp).

World model: world units = screen pixels at rest. The gate (the presenter's live frame) is fixed at the world origin; the
film strip slides under it along world x (slot pitch 360). The camera maps world -> screen:
  rest       : scale 1 (Phase B pushes slowly to 1.025), rotated 4 deg clockwise, gate centre at (540, 870)
  full screen: scale 1080/405, no rotation, gate video exactly on the 1080x1920 screen (= the untouched frame)
Pull-out on 在这个步骤, push-in on 才会继续往下做; frames outside the camera moves are the source frame itself.
"""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from a3common import *  # noqa

SHOT = '15'
F0, F1 = 2937, 3394
SRC0 = 5151

# Word onsets in SOURCE seconds from 01_transcript/source_env10ms_db.npy (see shot16.py for the method).
ONSET_SRC = {
    'step3': 171.88,       # 第三步 (whisper 171.64, before the segment start 171.70)
    'zai': 174.30,         # 在这个步骤 (whisper 173.54 sits in the pause 173.56-174.29)
    'agent': 175.25,
    'chufenjing': 176.73,  # 出分镜
    'meiyige': 177.73,     # 每一个画面 (pause 177.24-177.72)
    'zenme': 179.69,       # 怎么转场 (pause 179.34-179.68)
    'zhuanchang': 179.90,  # 转场
    'pei': 180.85,         # 配什么音效 (plosive burst after the pause 180.71-180.84)
    'yinxiao': 181.16,     # 音效
    'xian': 181.98,        # 先出几张样片 (pause 181.64-181.97)
    'yangpian': 182.63,    # 样片
    'zhidao': 183.96,      # 直到 (pause 183.56-183.95)
    'queren': 184.21,      # 确认没有问题
    'caihui': 185.61,      # 才会继续往下做 (pause 185.43-185.60)
    'speech_end': 186.70,
}
WORD_TEXT = {'step3': '第三步', 'zai': '在这个步骤', 'agent': 'Agent', 'chufenjing': '出分镜', 'meiyige': '每一个画面',
             'zenme': '怎么转场', 'zhuanchang': '转场', 'pei': '配什么音效', 'yinxiao': '音效', 'xian': '先出几张样片',
             'yangpian': '样片', 'zhidao': '直到', 'queren': '确认没有问题', 'caihui': '才会继续往下做'}
# A0's words_v2.json (spectrogram-checked anchors) wins where it has the word; our envelope values are the fallback
K, ONSET_REPORT = onsets(WORD_TEXT, ONSET_SRC)

E = dict(
    pull0=K['zai'], pull1=K['zai'] + 0.9,                  # camera pulls out of the live frame
    scroll0=K['zai'] + 0.30, scroll1=K['zenme'] - 0.12,     # strip runs from 镜 1 to the live slot (镜 15)
    arrow=K['zenme'], arrow_tag=K['zhuanchang'],            # yellow arrow + 转场
    wave=K['pei'], wave_tag=K['yinxiao'],                   # green wave on the next frame's sound lane + 音效
    ann_out=K['xian'] - 0.25,                               # arrow + 转场 leave
    lift=K['xian'],                                         # three frames lift like fresh prints (staggered)
    wave_out=K['yangpian'] + 0.30,
    stamp=K['queren'],                                      # 确认 stamp lands
    settle=K['caihui'],                                     # prints settle, strip moves on to 镜 20
    scroll2_0=K['caihui'] + 0.05, scroll2_1=K['caihui'] + 0.85,
    push0=K['caihui'] + 0.14, push1=K['caihui'] + 0.14 + 0.75,
)

E = {k: round(v * FPS) / FPS for k, v in E.items()}      # every event on the frame grid (sound = picture)
SB2_DIR = SB2
SB1_DIR = VP / '05_visual/storyboard_v1'
IP_DIR = VP / '05_visual/ip_intro/filmstrip'
SLOTS = [('镜 1', SB2_DIR / 'shot1.png'), ('镜 2', SB2_DIR / 'shotI2.png'), ('镜 3', SB1_DIR / 'shot03.png'),
         ('镜 4', SB2_DIR / 'shot4.png'), ('镜 6', IP_DIR / '9x16_f56.png'), ('镜 7', SB2_DIR / 'shot7.png'),
         ('镜 9', SB2_DIR / 'shot9.png'), ('镜 10', SB2_DIR / 'shot10a.png'), ('镜 11', SB2_DIR / 'shot11.png'),
         ('镜 12', SB1_DIR / 'shot12.png'), ('镜 13', SB2_DIR / 'shot13a.png'), ('镜 14', SB2_DIR / 'shot14a.png'),
         ('镜 15', SB2_DIR / 'shot15.png'), ('镜 16', SB2_DIR / 'shot16a.png'), ('镜 18', SB2_DIR / 'shot18.png'),
         ('镜 20', SB1_DIR / 'shot20.png')]
LIVE = 12                       # the slot of this very shot sits under the gate during the hold
BG_STRIPS = [                   # blurred strips above / below (earlier storyboard version + the rest of v2)
    [SB1_DIR / f'shot{n}.png' for n in ('01', '02', '03', '06', '07', '09', '10', '11', '12', '13', '14', '16', '18',
                                         '20', '01', '02')],
    [SB2_DIR / f'shot{n}.png' for n in ('16b', '18', '10b', '13b', '14b', 'I1', 'I3', '1', '4', '7', '9', '11', '10a',
                                         '13a', '14a', '16a')],
]
BG_LEFT = (-1300, -1100)        # world x of the blurred strips' left edges at the start
BG_Y = (-570, 690)              # world y of their centres (screen ~300 / ~1560 at rest, as in shot15.png)
FILM = (30, 26, 22)
HOLE = (236, 228, 210)
FW, FH, GAP, MARGIN = 300, 533, 60, 86
PITCH = FW + GAP
HF = FH + 2 * MARGIN            # 705
LEAD = 900                      # film leader before slot 0 / after the last slot
GV_W, GV_H, GB = 405, 720, 12   # gate video (exactly 9:16 = 0.375 x 1080x1920) and its yellow border
S_FULL = W / GV_W               # camera scale at which the gate video fills the screen
REST_C = (540.0, 870.0)
ROT_REST = 4.0                  # degrees, clockwise on screen (sample: PIL rotate(-4))
LANE = (120, 220, 170)


# ------------------------------------------------------------------ scroll profile
def _profile(t0, t1, d, ta, td):
    """position 0..d over [t0, t1] with cosine ramps (ta up, td down) and a flat cruise"""
    ts = np.linspace(t0, t1, 4001)
    T_ = t1 - t0
    v = np.ones_like(ts)
    u = ts - t0
    v[u < ta] = (1 - np.cos(np.pi * u[u < ta] / ta)) / 2
    v[u > T_ - td] = (1 - np.cos(np.pi * (T_ - u[u > T_ - td]) / td)) / 2
    x = np.concatenate([[0], np.cumsum((v[1:] + v[:-1]) / 2 * np.diff(ts))])
    return ts, x / x[-1] * d


_P1 = _profile(E['scroll0'], E['scroll1'], LIVE, 0.9, 0.9)
_P2 = _profile(E['scroll2_0'], E['scroll2_1'], len(SLOTS) - 1 - LIVE, 0.35, 0.3)


def scroll(t):
    """slot index under the gate at time t (float)"""
    if t <= E['scroll0']:
        return 0.0
    if t < E['scroll1']:
        return float(np.interp(t, *_P1))
    if t < E['scroll2_0']:
        return float(LIVE)
    if t < E['scroll2_1']:
        return LIVE + float(np.interp(t, *_P2))
    return float(len(SLOTS) - 1)


def light_times():
    """time each slot lights up (scroll - k crosses 0.5) -> tick cues"""
    ts = np.arange(E['scroll0'], E['scroll2_1'] + 0.05, 1 / 600)
    ss = np.array([scroll(t) for t in ts])
    out = {}
    for k in range(len(SLOTS)):
        idx = np.where(ss - k >= 0.5)[0]
        if len(idx):
            out[k] = float(ts[idx[0]])
    return out


def lit_amount(k, s):
    return clamp((s - k - 0.35) / 0.3)


# ------------------------------------------------------------------ camera
def camera(t):
    """(scale, rotation deg clockwise, gate centre on screen) or None when the frame is the untouched source"""
    if t < E['pull0'] or t >= E['push1']:
        return None
    rest_s = 1.0 + 0.025 * ease_in_out_sine(prog(t, E['scroll1'], E['push0'] - E['scroll1']))
    if t < E['pull1']:
        p = ease_in_out_cubic(prog(t, E['pull0'], E['pull1'] - E['pull0']))
        if p <= 0:
            return None
        a, b = S_FULL, 1.0
    elif t >= E['push0']:
        p = 1 - ease_in_out_cubic(prog(t, E['push0'], E['push1'] - E['push0']))
        if p <= 0:
            return None
        a, b = S_FULL, rest_s
    else:
        return rest_s, ROT_REST, REST_C, 1.0
    s = math.exp(math.log(a) + (math.log(b) - math.log(a)) * p)
    c = (540.0, 960.0 + (REST_C[1] - 960.0) * p)
    return s, ROT_REST * p, c, p


def cam_matrix(cam):
    """2x3 world -> screen"""
    s, rot, c, _ = cam
    th = math.radians(rot)
    ca, sa = math.cos(th) * s, math.sin(th) * s
    return np.array([[ca, -sa, c[0]], [sa, ca, c[1]]], np.float64)


def compose(M, A):
    """M o A for 2x3 affines"""
    M3 = np.vstack([M, [0, 0, 1]])
    A3 = np.vstack([A, [0, 0, 1]])
    return (M3 @ A3)[:2]


def affine(scale=1.0, rot=0.0, tx=0.0, ty=0.0):
    th = math.radians(rot)
    ca, sa = math.cos(th) * scale, math.sin(th) * scale
    return np.array([[ca, -sa, tx], [sa, ca, ty]], np.float64)


# ------------------------------------------------------------------ premultiplied blitting on a float canvas
def premul(im):
    a = np.array(im.convert('RGBA'), np.float32)
    a[..., :3] *= a[..., 3:4] / 255.0
    return np.clip(a + 0.5, 0, 255).astype(np.uint8)


class Canvas:
    def __init__(self, bg=(36, 33, 30)):
        self.c = np.empty((H, W, 3), np.float32)
        self.c[:] = np.array(bg, np.float32) / 255

    def draw(self, img, M, alpha=1.0, mul=1.0, blur_x=0):
        """img: premultiplied uint8 HxWx4 in its own pixel space; M: 2x3 image px -> screen. Returns bbox"""
        if alpha <= 0.002:
            return None
        h, w = img.shape[:2]
        pts = M @ np.array([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]], np.float64).T
        x0, y0 = int(math.floor(pts[0].min())) - 1, int(math.floor(pts[1].min())) - 1
        x1, y1 = int(math.ceil(pts[0].max())) + 1, int(math.ceil(pts[1].max())) + 1
        pad = int(blur_x) + 1
        x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0), min(W, x1 + pad), min(H, y1)
        if x1 <= x0 or y1 <= y0:
            return None
        Mr = M.copy()
        Mr[0, 2] -= x0
        Mr[1, 2] -= y0
        wp = cv2.warpAffine(img, Mr, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                            borderValue=(0, 0, 0, 0)).astype(np.float32) / 255
        if blur_x >= 2:
            wp = cv2.blur(wp, (int(blur_x), 1))
        a = wp[..., 3:4] * alpha
        roi = self.c[y0:y1, x0:x1]
        roi *= (1 - a)
        roi += wp[..., :3] * (alpha * mul)
        ys, xs = np.where(a[..., 0] > 0.16)
        if not len(xs):
            return None
        return (x0 + int(xs.min()), y0 + int(ys.min()), x0 + int(xs.max()), y0 + int(ys.max()))

    def rgb(self):
        return np.clip(self.c * 255 + 0.5, 0, 255).astype(np.uint8)


def world_box(M, box):
    pts = M @ np.array([[box[0], box[1], 1], [box[2], box[1], 1], [box[0], box[3], 1], [box[2], box[3], 1]], np.float64).T
    return (int(pts[0].min()), int(pts[1].min()), int(pts[0].max()), int(pts[1].max()))


# ------------------------------------------------------------------ assets
def load_thumb(path, w, h):
    im = Image.open(path).convert('RGB')
    return im.resize((w, h), Image.LANCZOS)


def film_base(scale):
    """the whole main strip (film + sprocket holes + labels + edge codes), no pictures; px = world * scale"""
    n = len(SLOTS)
    Wf = LEAD * 2 + (n - 1) * PITCH
    im = Image.new('RGBA', (int(Wf * scale), int(HF * scale)), FILM + (255,))
    d = ImageDraw.Draw(im)
    s = scale
    for x in range(14, Wf, 46):
        d.rounded_rectangle((x * s, 16 * s, (x + 26) * s, 50 * s), radius=6 * s, fill=HOLE + (255,))
        d.rounded_rectangle((x * s, (HF - 50) * s, (x + 26) * s, (HF - 16) * s), radius=6 * s, fill=HOLE + (255,))
    f_lab, f_edge, f_lead = font('Bold', int(22 * s)), font('Bold', int(20 * s)), font('Heavy', int(34 * s))
    for k, (lab, _) in enumerate(SLOTS):
        cx = LEAD + k * PITCH
        x0 = cx - FW / 2
        d.rectangle((x0 * s, MARGIN * s, (x0 + FW) * s, (MARGIN + FH) * s), fill=(14, 12, 10, 255))
        d.text(((x0 + 6) * s, (MARGIN - 8) * s), lab, font=f_lab, fill=(255, 196, 120), anchor='ls')
        if k != LIVE + 1:                                    # that lane carries the 音效 wave during the hold
            d.text(((x0 + 2) * s, (HF - 58) * s), 'STEP 3 分镜脚本', font=f_edge, fill=(255, 176, 90), anchor='ls')
    for cx in (LEAD / 2 + 60, Wf - LEAD / 2 - 60):             # leader / tail title, like a printed leader
        d.text((cx * s, HF / 2 * s), 'STEP 3 分镜脚本', font=f_lead, fill=(255, 176, 90), anchor='mm')
    return im


def bg_strip(paths, fw=200, gap=22, margin=58):
    fh = int(fw * 16 / 9)
    n = len(paths)
    Wf, Hf = n * (fw + gap) + gap, fh + 2 * margin
    im = Image.new('RGBA', (Wf, Hf), FILM + (255,))
    d = ImageDraw.Draw(im)
    for x in range(14, Wf, 46):
        d.rounded_rectangle((x, 16, x + 26, 16 + 34), radius=6, fill=HOLE + (255,))
        d.rounded_rectangle((x, Hf - 50, x + 26, Hf - 16), radius=6, fill=HOLE + (255,))
    for i, p in enumerate(paths):
        fr = Image.open(p).convert('RGBA').resize((fw, fh), Image.LANCZOS)
        im.alpha_composite(ImageEnhance.Brightness(fr).enhance(0.55), (gap + i * (fw + gap), margin))
    im = im.filter(ImageFilter.GaussianBlur(3))
    return ImageEnhance.Brightness(im).enhance(0.8)


def soft_rect(w, h, blur, alpha, color=(0, 0, 0)):
    pad = blur * 3
    a = Image.new('L', (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(a).rectangle((pad, pad, pad + w, pad + h), fill=int(255 * alpha))
    a = a.filter(ImageFilter.GaussianBlur(blur))
    im = Image.new('RGBA', a.size, color + (0,))
    im.putalpha(a)
    return im, pad


def rrect_mask_np(w, h, r):
    m = np.zeros((h * 2, w * 2), np.uint8)
    r2 = max(0, int(r * 2))
    if r2 == 0:
        return np.full((h, w), 255, np.uint8)
    cv2.rectangle(m, (r2, 0), (w * 2 - 1 - r2, h * 2 - 1), 255, -1)
    cv2.rectangle(m, (0, r2), (w * 2 - 1, h * 2 - 1 - r2), 255, -1)
    for cx, cy in ((r2, r2), (w * 2 - 1 - r2, r2), (r2, h * 2 - 1 - r2), (w * 2 - 1 - r2, h * 2 - 1 - r2)):
        cv2.circle(m, (cx, cy), r2, 255, -1, lineType=cv2.LINE_AA)
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA)


class Renderer:
    def __init__(self, faces):
        self.faces = faces
        self.base = {1: premul(film_base(1)), 2: premul(film_base(2))}
        self.pics = {1: [], 2: []}
        for lab, p in SLOTS:
            for s in (1, 2):
                self.pics[s].append(premul(load_thumb(p, FW * s, FH * s)))
        # white print border for the lifted frames (photo look), 1x and 2x
        self.print_border = {}
        for s in (1, 2):
            b = 10 * s
            im = Image.new('RGBA', (FW * s + 2 * b, FH * s + 2 * b), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=6 * s, fill=CARD + (255,))
            self.print_border[s] = premul(im)
        self.bgs = [premul(bg_strip(p)) for p in BG_STRIPS]
        g = glow((900, 700), color=(255, 236, 200), alpha=120)
        self.glow = premul(g)
        sh, pad = soft_rect(len(SLOTS) * PITCH + 2 * LEAD, HF, 18, 0.5)
        self.strip_shadow, self.strip_shadow_pad = premul(sh), pad
        ps, ppad = soft_rect(FW + 20, FH + 20, 14, 0.55)
        self.print_shadow, self.print_shadow_pad = premul(ps), ppad
        gsh, self.gshadow_pad = shadow_of(Image.new('RGBA', (GV_W + 2 * GB, GV_H + 2 * GB), (0, 0, 0, 255)), blur=16, alpha=0.55)
        self.gshadow = premul(gsh)
        self.rec = pill('实拍 · 正在说', size=26, bg=(20, 20, 20, 225), dot=RED, padx=14)
        self.rec_dim = pill('实拍 · 正在说', size=26, bg=(20, 20, 20, 225), dot=(90, 40, 34), padx=14)
        self.tag_zc = premul(pill('转场', size=32, fg=INK, bg=YELLOW + (255,), padx=18))
        self.tag_yx = premul(pill('音效', size=30, fg=INK, bg=LANE + (255,), padx=16))
        self.stamp = premul(stamp('确认', s=230, color=RED, rot=-12))
        self.lights = light_times()

    # -------------------------------------------------------------- gate (the presenter's live frame)
    def gate_image(self, src, cam_s, p_intro):
        """gate at its drawing resolution: (premul image, px per world unit). Border + rounded video + REC pill."""
        s = cam_s                                   # draw at screen scale: one image px = one screen px
        vw, vh = int(round(GV_W * s)), int(round(GV_H * s))
        b = int(round(GB * s))
        vid = cv2.resize(src, (vw, vh), interpolation=cv2.INTER_AREA if vw < W else cv2.INTER_LINEAR)
        r_vid = 8 * s * p_intro
        m = rrect_mask_np(vw, vh, r_vid).astype(np.float32) / 255
        out = np.zeros((vh + 2 * b, vw + 2 * b, 4), np.float32)
        border = rrect_mask_np(vw + 2 * b, vh + 2 * b, 14 * s * max(p_intro, 0.35)).astype(np.float32) / 255
        out[..., 0], out[..., 1], out[..., 2] = [c / 255 * border for c in YELLOW]
        out[..., 3] = border
        vm = m[..., None]
        out[b:b + vh, b:b + vw, :3] = out[b:b + vh, b:b + vw, :3] * (1 - vm) + vid.astype(np.float32) / 255 * vm
        out[b:b + vh, b:b + vw, 3:4] = out[b:b + vh, b:b + vw, 3:4] * (1 - vm) + vm
        return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8), s, b

    def face_screen(self, fi, cam, lift_gate=0.0):
        """The presenter's face / lips boxes mapped into the gate on screen (for QA), or the source boxes when full screen"""
        f = src_frame(fi)
        fb, lb = self.faces.face(f), self.faces.lips(f)
        if cam is None:
            return fb, lb
        M = cam_matrix(cam)
        A = compose(affine(1.0, 0, 0, -lift_gate), affine(GV_W / W, 0, -GV_W / 2, -GV_H / 2))
        MA = compose(M, A)
        return world_box(MA, fb), world_box(MA, lb)

    # -------------------------------------------------------------- frame
    def render(self, fi, src_rgb):
        t = fi / FPS
        cam = camera(t)
        items = []
        if cam is None:
            return src_rgb, items
        cs, crot, cc, cp = cam
        M = cam_matrix(cam)
        mip = 2 if cs > 1.4 else 1
        cv = Canvas()
        s_now = scroll(t)
        ds = abs(scroll(t + 1 / FPS) - scroll(t - 1 / FPS)) / 2 * PITCH * cs
        blur = ds * 0.5 if ds > 6 else 0
        # background: warm glow + blurred strips (drifting slowly, parallax 0.22 of the main strip)
        gh, gw = self.glow.shape[:2]
        cv.draw(self.glow, compose(M, affine(1, 0, -gw / 2, 10 - gh / 2)))
        tau = t - F0 / FPS
        for j, bg in enumerate(self.bgs):           # parallax 0.22 of the main strip + a slow opposite drift
            h_, w_ = bg.shape[:2]
            x_left = BG_LEFT[j] - 0.22 * s_now * PITCH + (-10 if j == 0 else 10) * tau
            cv.draw(bg, compose(M, affine(1, 0, x_left, BG_Y[j] - h_ / 2)))
        # main strip shadow + film base
        fx0 = -(LEAD + s_now * PITCH)                   # world x of film image x=0
        sp = self.strip_shadow_pad
        cv.draw(self.strip_shadow, compose(M, affine(1, 0, fx0 - sp + 8, -HF / 2 - sp + 20)), alpha=min(1.0, cp * 1.2))
        base = self.base[mip]
        st_bb = cv.draw(base, compose(M, affine(1 / mip, 0, fx0, -HF / 2)), blur_x=blur)
        if st_bb:
            items.append(('main_strip', st_bb, 'bg'))
        # pictures (dim until they have passed the gate), lifted prints during the hold
        lifts = self.lift_state(t)
        order = sorted(range(len(SLOTS)), key=lambda k: (k in lifts, k))
        for k in order:
            cx = (k - s_now) * PITCH
            if abs(cx) * cs > 1500:
                continue
            b = lit_amount(k, s_now)
            if k in lifts:
                b = max(b, lifts[k][3])
            mul = 0.42 + 0.58 * b
            pic = self.pics[mip][k]
            if k in lifts:
                dy, rot, sc, pb = lifts[k]
                Ab = affine(sc, rot, cx, -dy)
                if pb > 0:
                    sp2 = self.print_shadow_pad
                    cv.draw(self.print_shadow, compose(M, compose(Ab, affine(1, 0, -FW / 2 - 10 - sp2 + 6, -FH / 2 - 10 - sp2 + 16))),
                            alpha=pb)
                    pbd = self.print_border[mip]
                    cv.draw(pbd, compose(M, compose(Ab, affine(1 / mip, 0, -FW / 2 - 10, -FH / 2 - 10))), alpha=pb)
                bb = cv.draw(pic, compose(M, compose(Ab, affine(1 / mip, 0, -FW / 2, -FH / 2))), mul=mul)
            else:
                bb = cv.draw(pic, compose(M, affine(1 / mip, 0, cx - FW / 2, -FH / 2)), mul=mul, blur_x=blur)
            if bb:
                items.append((f'pic_{k}', bb, 'bg'))
        # 音效: wave on the sound lane under the next frame + tag on the frame; 确认 stamp on the next print
        self.draw_wave(cv, M, t, s_now, lifts, items)
        self.draw_stamp(cv, M, t, s_now, lifts, items)
        # gate: shadow, border, live video, REC pill (fades in once the frame is small)
        lift_gate = lifts.get('gate', (0, 0, 1, 0))[0]
        img_g, gs, gb = self.gate_image(src_rgb, cs, cp)
        gh_, gw_ = img_g.shape[:2]
        A_g = affine(1 / gs, 0, -gw_ / (2 * gs), -gh_ / (2 * gs) - lift_gate)
        pad = self.gshadow_pad
        cv.draw(self.gshadow, compose(M, affine(1, 0, -(GV_W / 2 + GB) - pad + 6, -(GV_H / 2 + GB) - pad + 14 - lift_gate * 0.4)),
                alpha=min(1.0, cp * (1 + 0.02 * lift_gate)))
        g_bb = cv.draw(img_g, compose(M, A_g))
        items.append(('gate', g_bb, 'gate'))
        rec_a = clamp((cp - 0.55) / 0.45)
        if rec_a > 0:
            blink = 0.5 + 0.5 * math.cos(2 * math.pi * 1.0 * t)
            rec = premul(self.rec if blink > 0.35 else self.rec_dim)
            bb = cv.draw(rec, compose(M, affine(1, 0, -(GV_W / 2 + GB) + 26, -(GV_H / 2 + GB) + 26 - lift_gate)), alpha=rec_a)
            if bb:
                items.append(('rec_pill', bb, 'text'))
        # 转场 arrow + tag
        self.draw_arrow(cv, M, t, lift_gate, items)
        face, lips = self.face_screen(fi, cam, lift_gate)
        self.last_face = (face, lips)
        return cv.rgb(), items

    def gate_sample_points(self, fi, rng, n=3000):
        """random points of the gate video (source px) and where they land on screen, for the frame-exact test"""
        t = fi / FPS
        cam = camera(t)
        if cam is None:
            return None
        lift_gate = self.lift_state(t).get('gate', (0, 0, 1, 0))[0]
        MA = compose(cam_matrix(cam), compose(affine(1.0, 0, 0, -lift_gate), affine(GV_W / W, 0, -GV_W / 2, -GV_H / 2)))
        sx = rng.uniform(60, W - 200, n)          # keep off the REC pill (top-left) and the arrow (right edge)
        sy = rng.uniform(260, H - 60, n)
        ox = MA[0, 0] * sx + MA[0, 1] * sy + MA[0, 2]
        oy = MA[1, 0] * sx + MA[1, 1] * sy + MA[1, 2]
        k = (ox > 2) & (ox < W - 3) & (oy > 2) & (oy < H - 3)
        if k.sum() < 200:
            return None
        return (sx[k], sy[k]), (ox[k], oy[k])

    # -------------------------------------------------------------- hold annotations
    def lift_state(self, t):
        """{slot: (dy, rot, scale, print_amount)} + 'gate': (dy, ...) while the three frames are lifted"""
        out = {}
        if not (E['lift'] <= t < E['settle'] + 0.35):
            return out
        for j, (key, rot) in enumerate(((LIVE - 1, -1.4), ('gate', 0.0), (LIVE + 1, 1.6))):
            t0 = E['lift'] + 0.08 * j
            up = ease_out_back(prog(t, t0, 0.32), 1.6)
            down = ease_in_out_cubic(prog(t, E['settle'] + 0.02 * j, 0.28))
            a = up * (1 - down)
            if a <= 0:
                continue
            if key == 'gate':
                out['gate'] = (18 * a, 0, 1, 0)
            else:
                out[key] = (22 * a, rot * a, 1 + 0.03 * a, clamp(a))
        return out

    def draw_arrow(self, cv, M, t, lift_gate, items):
        if not (E['arrow'] <= t < E['ann_out'] + 0.2):
            return
        a = 1 - prog(t, E['ann_out'], 0.2)
        p = ease_out_cubic(prog(t, E['arrow'], 0.3))
        ax0, ax1, ay = 170.0, PITCH - FW / 2 + 110.0, -HF / 2 + MARGIN + 150.0
        pts = [((1 - u) ** 2 * ax0 + 2 * (1 - u) * u * (ax0 + ax1) / 2 + u ** 2 * ax1,
                (1 - u) ** 2 * ay + 2 * (1 - u) * u * (ay - 130) + u ** 2 * ay) for u in np.linspace(0, p, 40)]
        # draw in a local 2x image around the arrow, then place it in the world
        ox, oy = ax0 - 40, ay - 180
        S = 2
        im = Image.new('RGBA', (int((ax1 - ax0 + 100) * S), int(260 * S)), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        lp = [((x - ox) * S, (y - oy) * S) for x, y in pts]
        d.line(lp, fill=YELLOW + (255,), width=12 * S, joint='curve')
        if p > 0.92:
            ex, ey = lp[-1]
            px_, py_ = lp[-4]
            ang = math.atan2(ey - py_, ex - px_)
            for sg in (-1, 1):
                aa = ang + math.pi - sg * 0.5
                d.line((ex, ey, ex + math.cos(aa) * 40 * S, ey + math.sin(aa) * 40 * S), fill=YELLOW + (255,), width=12 * S)
        bb = cv.draw(premul(im), compose(M, affine(1 / S, 0, ox, oy)), alpha=a)
        if bb:
            items.append(('arrow', bb, 'overlay'))
        sc = pop(t, E['arrow_tag'], 0.26)
        if sc > 0:
            th, tw = self.tag_zc.shape[:2]
            cx_, cy_ = ax1 - 10 + tw / 2, ay - 150 + th / 2
            bb = cv.draw(self.tag_zc, compose(M, affine(sc, 0, cx_ - tw * sc / 2, cy_ - th * sc / 2)), alpha=a)
            if bb:
                items.append(('tag_transition', bb, 'text'))

    def draw_wave(self, cv, M, t, s_now, lifts, items):
        if not (E['wave'] <= t < E['wave_out'] + 0.25):
            return
        a = 1 - prog(t, E['wave_out'], 0.25)
        k = LIVE + 1
        cx = (k - s_now) * PITCH
        x0 = cx - FW / 2
        lane_y = -HF / 2 + MARGIN + FH + 2
        S = 2
        im = Image.new('RGBA', ((FW + 20) * S, 40 * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        grow = prog(t, E['wave'], 0.45)
        rng = np.random.default_rng(15)
        amps = rng.uniform(0.5, 1, 60)
        for i, x in enumerate(range(10, FW + 10, 8)):
            if i / 37 > grow:
                break
            base_a = (0.3 + 0.7 * abs(math.sin(i * 0.4 + t * 6))) * amps[i] * 16
            d.line(((x) * S, (18 - base_a) * S, x * S, (18 + base_a) * S), fill=LANE + (255,), width=4 * S)
        bb = cv.draw(premul(im), compose(M, affine(1 / S, 0, x0, lane_y)), alpha=a)
        if bb:
            items.append(('wave', bb, 'under'))
        sc = pop(t, E['wave_tag'], 0.26)
        if sc > 0:
            dy, rot, s_, _ = lifts.get(k, (0, 0, 1, 0))
            th, tw = self.tag_yx.shape[:2]
            A = compose(affine(s_, rot, cx, -dy), affine(sc, 0, -tw * sc / 2, FH / 2 - th * sc - 16 * sc))
            bb = cv.draw(self.tag_yx, compose(M, A), alpha=a)
            if bb:
                items.append(('tag_sound', bb, 'under'))

    def draw_stamp(self, cv, M, t, s_now, lifts, items):
        if t < E['stamp'] - 0.12:
            return
        k = LIVE + 1
        cx = (k - s_now) * PITCH
        dy, rot, s_, _ = lifts.get(k, (0, 0, 1, 0))
        if t < E['stamp']:
            sc = 1.5 - 0.5 * ease_in_cubic(prog(t, E['stamp'] - 0.12, 0.12))
            al = prog(t, E['stamp'] - 0.12, 0.06)
        else:
            q = prog(t, E['stamp'], 0.12)
            sc = 1.0 - 0.05 * math.sin(math.pi * q)
            al = 1.0
        sh_, sw_ = self.stamp.shape[:2]
        A = compose(affine(s_, rot, cx, -dy), affine(sc, 0, -20 - sw_ * sc / 2, 150 - sh_ * sc / 2))
        bb = cv.draw(self.stamp, compose(M, A), alpha=al * 0.95)
        if bb:
            items.append(('stamp', bb, 'under'))


# ------------------------------------------------------------------ sound cues
def sfx():
    out = [dict(id='bell', t=round(K['step3'], 3), gain_db=-4, pitch=0, align='start',
                note='第三步：章节铃（分镜写 1:37.90 镜头起点；这里对齐「第三步」实际起音）。若 A0 的步骤条切换已带铃，请去重'),
           dict(id='whoosh_slow', t=round(E['pull0'], 3), gain_db=-2, pitch=0, align='motion', params={'dur': 1.0},
                note='「在这个步骤」画面拉远成胶片当前格，动作起点（0.9 s）')]
    lt = light_times()
    for k in sorted(lt):
        if k >= len(SLOTS) - 1 and lt[k] > E['push1']:
            continue
        late = lt[k] > E['settle']
        out.append(dict(id='tick', t=round(lt[k], 3), gain_db=-16 if late else -12, pitch=0, align='start',
                        note=f'胶片第 {k + 1} 格（{SLOTS[k][0]}）滑过当前格后点亮' + ('，推回全屏途中' if late else '')))
    out += [dict(id='laser_zip', t=round(E['arrow'], 3), gain_db=0, pitch=0, align='start', params={'dur': 0.25},
                 note='「怎么转场」黄色箭头从当前格画向下一格'),
            dict(id='blip', t=round(E['wave'], 3), gain_db=0, pitch=0, align='start', note='「配什么音效」下一格声轨长出声波'),
            ]
    for j in range(3):
        out.append(dict(id='pop_soft', t=round(pop_peak_time(E['lift'] + 0.08 * j, 0.32, 1.6), 3), gain_db=-4, pitch=2 * j,
                        align='start', note='「先出几张样片」三格抬起（回弹顶点），依次'))
    out += [dict(id='stamp', t=round(E['stamp'], 3), gain_db=0, pitch=0, align='start', note='「确认没有问题」确认章落在样片上'),
            dict(id='whoosh_mid', t=round(E['push0'], 3), gain_db=-2, pitch=0, align='motion',
                 note='「才会继续往下做」当前格推回全屏，动作起点（0.75 s）')]
    return out


def keyword_fx():
    return {
        '在这个步骤': dict(t=round(E['pull0'], 3), fx='全屏实拍拉远 0.9 s，变成胶片正中加黄框的当前格（405x720，旋 4°）'),
        '出分镜 / 每一个画面': dict(t=round(E['scroll0'], 3), fx=f'胶片从镜 1 滑到镜 15（当前格），滑过的格子点亮，{fmt(E["scroll0"])}-{fmt(E["scroll1"])}'),
        '怎么转场': dict(t=round(E['arrow'], 3), fx='当前格到下一格（镜 16）画出黄色箭头，「转场」标签在「转场」起音弹出'),
        '配什么音效': dict(t=round(E['wave'], 3), fx='下一格声轨上长出绿色声波，「音效」标签在「音效」起音弹出'),
        '先出几张样片': dict(t=round(E['lift'], 3), fx='当前格和左右两格抬起，两侧变成带白边的样片'),
        '确认没有问题': dict(t=round(E['stamp'], 3), fx='红色「确认」章盖在右侧样片上'),
        '才会继续往下做': dict(t=round(E['settle'], 3), fx='样片落回，胶片继续滑到镜 20，当前格推回全屏（0.75 s）'),
    }


# ------------------------------------------------------------------ QA hooks + meta
ALLOW = {('tag_transition', 'arrow'), ('tag_sound', 'wave')}


def intended(t):
    return set()                                    # nothing may touch the presenter's face inside the gate


def all_texts():
    return ['实拍 · 正在说', '转场', '音效', '确认', 'STEP 3 分镜脚本'] + [lab for lab, _ in SLOTS] + \
        [f'STEP 3 分镜脚本 · {k + 1:02d}' for k in range(len(SLOTS))]


def meta(pr, sha):
    lt = light_times()
    return dict(
        shot='15', owner='A3「视频20·分镜胶片与自检镜」', title='镜 15 · STEP 3 分镜脚本：灯箱胶片，当前格一直是出镜者实拍',
        v2_frames=[F0, F1], v2_seconds=[round(F0 / FPS, 3), round(F1 / FPS, 3)], v2_timecode=[fmt(F0 / FPS), fmt(F1 / FPS)],
        frame_range_note='[first, last+1) in v2 frames, 30 fps; source frames via timeline.v2_to_src',
        source=dict(file=str(SRC_MOV), frames=[SRC0, SRC0 + F1 - F0 - 1], mapping='timeline.v2_to_src: cut-plan segment 16, '
                    'one continuous take, every v2 frame = one source frame in order (no reverse / speed change / skip / repeat)'),
        starts_clean=True, ends_clean=True,
        clean_head=dict(until=fmt(E['pull0']), note='首帧起到「在这个步骤」都是原画面全屏'),
        clean_tail=dict(from_=fmt(E['push1']), note='推回全屏后到末帧都是原画面'),
        subtitle_owned=[], no_max_ranges=[],
        max_presence='全程有实拍：拉远后出镜者在胶片当前格里（屏上宽 405-415 px，比右下框 324 px 大），开头结尾全屏',
        camera=dict(pull_out=[round(E['pull0'], 3), round(E['pull1'], 3)], push_in=[round(E['push0'], 3), round(E['push1'], 3)],
                    rest='scale 1 -> 1.025 (hold), rotated 4 deg clockwise, gate centre (540, 870)',
                    full='scale 1080/405, gate video exactly on the screen'),
        strip=dict(slots=[dict(label=l, image=str(p)) for l, p in SLOTS], live_slot=SLOTS[LIVE][0],
                   scroll=[round(E['scroll0'], 3), round(E['scroll1'], 3), round(E['scroll2_0'], 3), round(E['scroll2_1'], 3)],
                   light_up={SLOTS[k][0]: round(v, 3) for k, v in sorted(lt.items())}),
        keyword_fx=keyword_fx(), demo_clips=[],
        storyboard_frames_used='分镜样帧（storyboard_v2 shot*.png、storyboard_v1 shot03/12/20、ip_intro filmstrip 9x16_f56）只作胶片格里的静帧；没有用成片视频片段',
        fonts=[str(FONTS / f) for f in FONT_FILES],
        word_onsets_v2={k: round(v, 3) for k, v in K.items()},
        word_onsets_method='优先用 A0 的 04_captions/words_v2.json（频谱人工锚点）；没有的字用 01_transcript/source_env10ms_db.npy 能量包络估计。两者对照见 word_onsets_check',
        word_onsets_check=ONSET_REPORT,
        spec=dict(codec=pr['codec_name'], profile=pr['profile'], size=f"{pr['width']}x{pr['height']}", fps=pr['r_frame_rate'],
                  frames=int(pr['nb_read_frames']), pix_fmt=pr['pix_fmt'], color=f"{pr.get('color_space')}/{pr.get('color_range')}",
                  crf=10, audio='none'),
        sha256=sha,
        notes=['步骤条（y 196-260）由 A0 画；上方虚化胶片是背景，不放任何元素。',
               '主字幕全程由 A0 画在 y 1300-1440；主胶片和当前格底边都在 y 1300 以上。',
               '分镜表里的时点来自 whisper 词头（偏早 0.1-0.8 s）；本镜改用 words_v2.json：「在这个步骤」1:40.52（分镜 1:39.74）、「怎么转场」1:45.88、「配什么音效」1:47.05、「先出几张样片」1:48.19、「确认没有问题」1:50.51、「才会继续往下做」1:51.82。',
               '胶片格用的是 v2 总览板同一批样帧：storyboard_v2 的 shot*.png，镜 3/12/20 沿用 v1 帧，镜 6 用 ip_intro 的 9x16_f56；镜 2/5/8/17/19 没有样帧，胶片上不放。'],
    )


def at_rest(t):
    """camera at its resting framing (strip / gate must stay above the caption band); False during pull / push"""
    cam = camera(t)
    return cam is not None and cam[3] >= 1.0
