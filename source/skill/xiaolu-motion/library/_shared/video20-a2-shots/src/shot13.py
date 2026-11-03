"""Shot 13 (v2 1:05.73-1:20.10, frames 1972..2402): full-screen chat on the dotted input-box paper, the presenter in the
bottom-right PiP. Same components as storyboard shot13a/13b (render_v2 chat_bubble / attach_chip / chat_input /
ime_bar / chat_header, sb_lib stamp / pip_card), animated on the words of words_v2.json:

  确认选题   STEP 1 header lands big, then settles top-left
  素材 / 想讲的内容   attachment chips 「口播素材 4:35」「文案」 drop into the composer
  全部丢给Agent   the user sends 「做一条开源工具的介绍视频」 (with both attachments)
  AI会和你 / 不断打磨   Agent typing dots, then 「开头先放成片？」
  你的选题和想法   the user types 「vlog、科普、不露脸各放一段」 with pinyin candidates, sends
  直到你   Agent 「文案改好了，确认吗？」
  确认 / 没有问题   the user types and sends 「确认」, red 确认 stamp lands between the chat and the composer
  下一步   (step bar 1 done / 2 active is drawn by A0 at 1:19.415)

The step-bar band y 180-280 stays empty; the subtitle band y 1300-1440 stays empty.
PiP in / out: the whole frame shrinks into the box (and grows back) in 15 frames; frame 1972 and frame 2402
are the presenter's untouched frames.
"""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

from a2common import *  # noqa
import a2time as AT

F0, F1 = AT.SHOT_RANGE['13']                 # 1972, 2403
CHAT_PAPER = (244, 240, 232)
W_ = AT.word_on
T = dict(
    start=F0 / FPS,
    queren=W_('确认选题', 66.63), ti_end=AT.word_end('确认选题', 66.63),
    sucai=AT.kw('13', '素材', 68.85), xiang=AT.kw('13', '想讲的内容', 69.72),
    diu=AT.kw('13', '全部丢给', 70.95),
    hui=W_('会和你', 73.77), buduan=AT.kw('13', '不断打磨', 74.37),
    xuanti=AT.kw('13', '选题和想法', 75.20), fa_end=AT.word_end('想法', 76.18),
    zhidao=AT.kw('13', '直到你', 77.00), que=AT.kw('13', '确认', 77.46), meiyou=AT.kw('13', '没有问题', 77.78),
    xiayibu=AT.kw('13', '下一步', 79.38),
)
PIP_IN = (F0, F0 + 14)                       # e: 0 -> 1 over frames 1972..1986
PIP_OUT = (F1 - 15, F1 - 1)                  # e: 1 -> 0 over frames 2388..2402 (2402 = raw)
PIP_INNER = (738.0, 858.0, 300.0, 420.0)     # content rect inside the card (PIP_BOX + 12 px border)
COMPOSER_X, COMPOSER_W, COMPOSER_BOTTOM = 40, 660, 1180
ATTACH_ROW_H = 70


# ------------------------------------------------------------------ storyboard components (render_v2, unchanged look)
def chat_bubble(text, who, size=36, attach=None):
    f = font('Bold', size)
    tw = f.getlength(text)
    padx, pady = 28, 16
    h = int(size * 1.25 + 2 * pady)
    w = int(tw + 2 * padx)
    ah = 0
    chips = []
    if attach:
        chips = [attach_chip(k, t) for k, t in attach]
        ah = max(c.height for c in chips) + 14
        w = max(w, int(sum(c.width for c in chips) + 12 * (len(chips) - 1) + 2 * 22))
    user = who == 'you'
    fill = (255, 243, 190, 255) if user else (255, 255, 255, 245)
    avatar = 0 if user else 66
    im = Image.new('RGBA', (w + avatar, h + ah), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if not user:
        d.ellipse((0, 4, 54, 58), fill=BLUE)
        d.text((27, 31), 'A', font=font('Heavy', 32), fill=(255, 255, 255), anchor='mm')
    d.rounded_rectangle((avatar, 0, avatar + w - 1, h + ah - 1), radius=26, fill=fill, outline=(0, 0, 0, 28), width=2)
    d.text((avatar + padx, h / 2), text, font=f, fill=INK, anchor='lm')
    x = avatar + 22
    for c in chips:
        im.alpha_composite(c, (int(x), int(h - 8)))
        x += c.width + 12
    return im


def attach_chip(kind, text):
    f = font('Bold', 26)
    w = int(f.getlength(text) + 84)
    im = Image.new('RGBA', (w, 52), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, 51), radius=12, fill=(255, 255, 255, 255), outline=(0, 0, 0, 40), width=2)
    if kind == 'video':
        d.rounded_rectangle((12, 9, 56, 43), radius=8, fill=INK)
        d.polygon([(28, 17), (28, 35), (43, 26)], fill=(255, 255, 255))
    else:
        d.rectangle((18, 8, 48, 44), fill=(255, 255, 255), outline=INK, width=3)
        for yy in (17, 25, 33):
            d.line((24, yy, 42, yy), fill=INK, width=3)
    d.text((68, 26), text, font=f, fill=INK, anchor='lm')
    return im


def typing_dots(phase):
    """Agent 'typing' bubble in the same white bubble style: three dots bouncing in turn"""
    w, h = 132, 77
    im = Image.new('RGBA', (w + 66, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 4, 54, 58), fill=BLUE)
    d.text((27, 31), 'A', font=font('Heavy', 32), fill=(255, 255, 255), anchor='mm')
    d.rounded_rectangle((66, 0, 66 + w - 1, h - 1), radius=26, fill=(255, 255, 255, 245), outline=(0, 0, 0, 28), width=2)
    for i in range(3):
        a = max(0.0, math.sin((phase - i * 0.18) * 2 * math.pi))
        cy = h / 2 - 7 * a
        g = int(150 - 60 * a)
        cx = 66 + 36 + i * 30
        d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=(g, g + 2, g + 8))
    return im


def chat_input(text='', compose='', placeholder='继续补充…', w=COMPOSER_W, h=118, chips=(), pressed=0.0):
    """storyboard chat_input + an attachment row on top when files are attached (composer grows upward)"""
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=59, fill=(252, 251, 248, 250), outline=(0, 0, 0, 34), width=2)
    for chip, cx, cy, ca in chips:
        cy = max(0, int(cy))
        im.alpha_composite(chip, (int(cx), cy))
    line_cy = h - 59
    f = font('Bold', 40)
    x = 40
    if text or compose:
        d.text((x, line_cy), text, font=f, fill=INK, anchor='lm')
        x += f.getlength(text)
        if compose:
            fc = font('Medium', 38)
            cw = fc.getlength(compose)
            d.text((x + 2, line_cy), compose, font=fc, fill=(120, 116, 110), anchor='lm')
            d.line((x + 2, line_cy + 26, x + 2 + cw, line_cy + 26), fill=(120, 116, 110), width=2)
            x += cw + 4
        d.line((x + 4, line_cy - 26, x + 4, line_cy + 26), fill=BLUE, width=4)
    else:
        d.text((x, line_cy), placeholder, font=font('Medium', 36), fill=(170, 166, 160), anchor='lm')
    bx = w - 18 - 84
    on = bool(text or compose)
    r = 42 * (1 - 0.12 * pressed)
    cx0 = bx + 42
    d.ellipse((cx0 - r, line_cy - r, cx0 + r, line_cy + r), fill=BLUE if on or pressed else (200, 205, 214))
    d.line((cx0, line_cy + 20 * r / 42, cx0, line_cy - 20 * r / 42), fill=(255, 255, 255), width=6)
    d.line((cx0 - 16 * r / 42, line_cy - 4 * r / 42, cx0, line_cy - 20 * r / 42, cx0 + 16 * r / 42, line_cy - 4 * r / 42), fill=(255, 255, 255), width=6)
    return im


def ime_bar(cands):
    f, fn = font('Bold', 36), font('Medium', 24)
    parts, x = [], 18
    for i, c in enumerate(cands):
        parts.append((x, i, c))
        x += 30 + f.getlength(c) + 34
    w = int(x)
    im = Image.new('RGBA', (w, 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, 69), radius=14, fill=(250, 248, 244, 250), outline=(0, 0, 0, 30), width=2)
    for x, i, c in parts:
        if i == 0:
            d.rounded_rectangle((x - 10, 9, x + 30 + f.getlength(c) + 10, 61), radius=10, fill=(222, 232, 255))
        d.text((x, 35), str(i + 1), font=fn, fill=BLUE if i == 0 else (130, 126, 120), anchor='lm')
        d.text((x + 26, 35), c, font=f, fill=BLUE if i == 0 else INK, anchor='lm')
    return im


def chat_header(ss=1):
    f1, f2 = font('Heavy', 26 * ss), font('Heavy', 44 * ss)
    pw = f1.getlength('STEP 1') + 30 * ss
    tw = f2.getlength('确认选题')
    w, h = int(pw + tw + 40 * ss), 60 * ss
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 8 * ss, pw, 52 * ss), radius=22 * ss, fill=INK)
    d.text((pw / 2, 30 * ss), 'STEP 1', font=f1, fill=(255, 255, 255), anchor='mm')
    d.rectangle((pw + 16 * ss, 32 * ss, pw + 20 * ss + tw, 52 * ss), fill=YELLOW)
    d.text((pw + 18 * ss, 30 * ss), '确认选题', font=f2, fill=INK, anchor='lm')
    return im


CHAT = [('做一条开源工具的介绍视频', 'you', [('video', '口播素材 4:35'), ('doc', '文案')]),
        ('开头先放成片？', 'agent', None),
        ('vlog、科普、不露脸各放一段', 'you', None),
        ('文案改好了，确认吗？', 'agent', None),
        ('确认', 'you', None)]

# typing script of message 3 (v2 s, committed text, pinyin being composed, candidates)
TYPE3 = [(74.80, 'v', '', None), (74.84, 'vl', '', None), (74.88, 'vlo', '', None), (74.92, 'vlog', '', None),
         (74.97, 'vlog、', '', None),
         (75.02, 'vlog、', 'ke', ['可', '科', '课', '客']), (75.08, 'vlog、', 'kepu', ['科普', '可', '课', '客']),
         (75.16, 'vlog、科普', '', None), (75.20, 'vlog、科普、', '', None),
         (75.25, 'vlog、科普、', 'bu', ['不', '部', '步', '布']), (75.30, 'vlog、科普、', 'bulu', ['不露', '不', '部', '步']),
         (75.36, 'vlog、科普、', 'bululian', ['不露脸', '不露', '不', '部']),
         (75.44, 'vlog、科普、不露脸', '', None),
         (75.49, 'vlog、科普、不露脸', 'ge', ['个', '各', '格', '歌']), (75.55, 'vlog、科普、不露脸各', '', None),
         (75.58, 'vlog、科普、不露脸各', 'f', ['发', '放', '分', '方']), (75.61, 'vlog、科普、不露脸各', 'fa', ['发', '法', '放', '罚']),
         (75.64, 'vlog、科普、不露脸各', 'fang', ['放', '方', '房', '防']),
         (75.80, 'vlog、科普、不露脸各放', '', None),
         (75.84, 'vlog、科普、不露脸各放', 'yi', ['一', '以', '已', '意']),
         (75.90, 'vlog、科普、不露脸各放', 'yiduan', ['一段', '一', '以', '已']),
         (75.99, 'vlog、科普、不露脸各放一段', '', None)]
SEND3 = 76.20
# message 1 typed in two-character chunks after the attachments
TYPE1_T0, TYPE1_DT = 70.02, 0.14
TYPE1 = '做一条开源工具的介绍视频'


def type1_state(t):
    n = int((t - TYPE1_T0) / TYPE1_DT) + 1 if t >= TYPE1_T0 else 0
    return TYPE1[:min(len(TYPE1), 2 * n)]


def type3_state(t):
    st = ('', '', None)
    for tt, txt, comp, cands in TYPE3:
        if t >= tt:
            st = (txt, comp, cands)
    return st


def type5_state(t):
    q = T['que']
    if t < q - 0.13:
        return '', '', None
    if t < q - 0.07:
        return '', 'que', ['却', '确', '缺', '雀']
    if t < q:
        return '', 'queren', ['确认', '却', '确', '缺']
    return '确认', '', None


class Shot13:
    def __init__(self, faces):
        self.faces = faces
        self.bg = to_f(paper(tone=CHAT_PAPER, dots=34, seed=13, grain=3.5, blotch=4))
        fr = [v2_src_frame(k) for k in range(F0, F1)]
        fb = np.array([faces[f][0] for f in fr], np.float32)
        cx = float(np.median((fb[:, 0] + fb[:, 2]) / 2))
        head_top = float(np.median(fb[:, 1])) - 390          # hair top above the face box (source, see storyboard)
        cw, ch = 900, 1260                                     # sb_lib.pip_crop geometry (300 x 420 at 1/3)
        x0 = int(min(max(0, cx - cw / 2), W - cw))
        y0 = int(min(max(0, head_top - 70), H - ch))
        self.crop = (x0, y0, x0 + cw, y0 + ch)
        self.header = chat_header(1)
        self.header2 = chat_header(2)
        self.bubbles = [chat_bubble(t, who, attach=att) for t, who, att in CHAT]
        y = 296
        self.slots = []
        for (t, who, att), b in zip(CHAT, self.bubbles):
            x = W - 40 - b.width if who == 'you' else 40
            self.slots.append((x, y))
            y += b.height + 12
        self.chip_v = attach_chip('video', '口播素材 4:35')
        self.chip_d = attach_chip('doc', '文案')
        self.stamp = stamp('确认', s=230, rot=-14)
        self.tape = rotate(tape(118, 36, color=(250, 222, 120), seed=5), -7)

    # ---------------------------------------------------------------- PiP (whole frame <-> card)
    def pip_e(self, k):
        if k <= PIP_IN[1]:
            return e_io(prog(k, PIP_IN[0], PIP_IN[1]))
        if k >= PIP_OUT[0]:
            return 1 - e_io(prog(k, PIP_OUT[0], PIP_OUT[1]))
        return 1.0

    def draw_pip(self, canvas, src_u8, e, qa):
        ix, iy, iw, ih = PIP_INNER
        Dx, Dy = lerp(0, ix, e), lerp(0, iy, e)
        Dw, Dh = lerp(W, iw, e), lerp(H, ih, e)
        kx = lerp(1.0, iw / (self.crop[2] - self.crop[0]), e)
        ccx = lerp(W / 2, (self.crop[0] + self.crop[2]) / 2, e)
        ccy = lerp(H / 2, (self.crop[1] + self.crop[3]) / 2, e)
        sw, sh = Dw / kx, Dh / kx
        sx0 = min(max(0.0, ccx - sw / 2), W - sw)
        sy0 = min(max(0.0, ccy - sh / 2), H - sh)
        b = 12 * e
        ro = 30 * e
        # shadow + white card
        outer = rounded_mask(Dx - b, Dy - b, Dw + 2 * b, Dh + 2 * b, ro)
        if e > 0:
            darken(canvas, soft_shadow(outer, blur=14, alpha=0.35 * e))
        canvas *= (1 - outer[..., None])
        canvas += outer[..., None] * (np.array(CARD, np.float32) / 255)
        # content: the source region, resampled with area averaging (no aliasing when it is small)
        x0, y0 = int(round(sx0)), int(round(sy0))
        x1, y1 = int(round(sx0 + sw)), int(round(sy0 + sh))
        tw, th = max(1, int(round(Dw))), max(1, int(round(Dh)))
        crop = src_u8[y0:y1, x0:x1]
        interp = cv2.INTER_AREA if tw < crop.shape[1] else cv2.INTER_LINEAR
        cont = cv2.resize(crop, (tw, th), interpolation=interp).astype(np.float32) / 255.0
        inner = rounded_mask(round(Dx), round(Dy), tw, th, max(0.0, ro - b + 4 * e))
        X0, Y0 = int(round(Dx)), int(round(Dy))
        sub = inner[Y0:Y0 + th, X0:X0 + tw, None]
        canvas[Y0:Y0 + th, X0:X0 + tw] = canvas[Y0:Y0 + th, X0:X0 + tw] * (1 - sub) + cont[:sub.shape[0], :sub.shape[1]] * sub
        # washi tape over the top edge once the card has formed
        ta = prog(e, 0.72, 1.0)
        if ta > 0:
            paste_rgba(canvas, self.tape, Dx + Dw / 2 - self.tape.width / 2, Dy - b - 22 + 4, alpha=ta)
        qa.setdefault('boxes', {})['pip'] = [int(Dx - b), int(Dy - b - 22 * (ta > 0)), int(Dx + Dw + b), int(Dy + Dh + b)]
        qa['pip_src_rect'] = [round(sx0, 1), round(sy0, 1), round(sw, 1), round(sh, 1)]
        qa['pip_scale'] = round(kx, 4)
        # the presenter's face / lips as shown inside the PiP (screen space), for the overlap QA
        self._pip_map = (Dx, Dy, sx0, sy0, kx)

    # ---------------------------------------------------------------- chat
    def place(self, canvas, elem, x, y, s=1.0, anchor=(0.0, 0.0), alpha=1.0, name=None, qa=None, shadow=(10, 0.16)):
        """elem with its anchor point (fraction of w,h) kept at (x + ax*w, y + ay*h) while scaling by s"""
        w, h = elem.size
        ax, ay = x + anchor[0] * w, y + anchor[1] * h
        cx = ax + (0.5 - anchor[0]) * w * s
        cy = ay + (0.5 - anchor[1]) * h * s
        rgb, a = affine_elem(elem, scale=s, cx=cx, cy=cy, alpha=alpha)
        if shadow:
            darken(canvas, soft_shadow(a, blur=shadow[0], alpha=shadow[1]))
        over_pm(canvas, rgb, a)
        if name and qa is not None:
            qa.setdefault('boxes', {})[name] = elem_bbox(a)

    def composer(self, t):
        """(image, top y, IME candidates, falling chips [(chip, x, y, alpha)]) of the composer at time t"""
        att_h = ATTACH_ROW_H * e_out(prog(t, T['sucai'] - 0.26, T['sucai'] - 0.08), 3) * (1 - e_io(prog(t, T['diu'], T['diu'] + 0.18)))
        h = int(round(118 + att_h))
        top = COMPOSER_BOTTOM - h
        docked, falling = [], []
        if T['sucai'] - 0.20 <= t < T['diu']:
            for chip, cx, tl in ((self.chip_v, 22, T['sucai']), (self.chip_d, 22 + self.chip_v.width + 12, T['xiang'])):
                if t < tl - 0.20:
                    continue
                u = e_out(prog(t, tl - 0.20, tl), 3)
                if u >= 1:
                    bounce = 6 * math.sin(math.pi * prog(t, tl, tl + 0.12))
                    docked.append((chip, cx, 12 - bounce))
                else:
                    falling.append((chip, COMPOSER_X + cx, top + 12 - 110 * (1 - u), min(1.0, prog(t, tl - 0.20, tl - 0.12))))
        cands = None
        pressed = 0.0
        if t < TYPE1_T0:
            text, comp, ph = '', '', '说说你想做的视频…'
        elif t < T['diu']:
            text, comp, ph = type1_state(t), '', ''
        elif t < 74.80:
            text, comp, ph = '', '', '继续补充…'
        elif t < SEND3:
            text, comp, cands = type3_state(t)
            ph = ''
        elif t < T['que'] - 0.13:
            text, comp, ph = '', '', '继续补充…'
        elif t < T['que'] + 0.09:
            text, comp, cands = type5_state(t)
            ph = ''
        else:
            text, comp, ph = '', '', '继续补充…'
        for ts in (T['diu'], SEND3, T['que'] + 0.09):
            if ts - 0.07 <= t < ts + 0.07:
                pressed = 1 - abs(t - ts) / 0.07
        im = chat_input(text, comp, placeholder=ph or '继续补充…', h=h, chips=[(c, x, y, 1.0) for c, x, y in docked], pressed=pressed)
        return im, top, cands, falling

    def sends(self):
        """(message index, send time, land time) for the three user messages"""
        return [(0, T['diu'], T['diu'] + 0.30), (2, SEND3, SEND3 + 0.28), (4, T['que'] + 0.09, T['que'] + 0.09 + 0.14)]

    def replies(self):
        """(message index, dots on, reply time)"""
        return [(1, T['hui'], T['buduan']), (3, SEND3 + 0.32, T['zhidao'])]

    def frame(self, k, src_u8, qa):
        t = k / FPS
        e = self.pip_e(k)
        if e <= 0:
            qa['layout'] = 'raw'
            return src_u8.copy()
        canvas = self.bg.copy()
        boxes = qa.setdefault('boxes', {})
        # header: big pop on 「确认选题」, then settles at top-left
        hq = T['queren']
        if t >= hq - 0.02:
            s_pop = pop(t, hq - 0.02, 0.30, 0.10)
            mv = e_io(prog(t, T['ti_end'] + 0.05, T['ti_end'] + 0.45))
            big_c = (W / 2 - 40, 640)
            small_c = (40 + self.header.width / 2, 300 + self.header.height / 2)
            cx, cy = lerp(big_c[0], small_c[0], mv), lerp(big_c[1], small_c[1], mv)
            scale = lerp(1.0, 0.5, mv) * s_pop                     # header2 is drawn at 2x
            rgb, a = affine_elem(self.header2, scale=scale, cx=cx, cy=cy)
            over_pm(canvas, rgb, a)
            boxes['chat_header'] = elem_bbox(a)
        # messages already in place + messages flying up
        for i, ts, tl in self.sends():
            if t < ts:
                continue
            x, y = self.slots[i]
            b = self.bubbles[i]
            pu = prog(t, ts, tl)
            u = e_out(pu, 3)
            fy = (COMPOSER_BOTTOM - 118 - ATTACH_ROW_H + 10) if i == 0 else (COMPOSER_BOTTOM - 118 + 10)
            fx = COMPOSER_X + (80 if i == 0 else 20)  # leaves from the composer's left: the path stays clear of the PiP
            gx = pu if i == 0 else pu * pu                     # rises first, then slides right: clear of the PiP and the header
            px, py = lerp(fx, x, gx), lerp(fy, y, u)
            self.place(canvas, b, px, py, s=lerp(0.92, 1.0, u), anchor=(0.0, 0.0), name=f'msg{i + 1}', qa=qa)
        for i, ton, tr in self.replies():
            x, y = self.slots[i]
            if ton <= t < tr + 0.06:
                ds = pop(t, ton, 0.22, 0.10) * (1 - e_in(prog(t, tr - 0.02, tr + 0.06), 2))
                if ds > 0:
                    self.place(canvas, typing_dots((t - ton) * 1.6), x, y, s=ds, anchor=(0.0, 0.5), name=f'dots{i + 1}', qa=qa)
            if t >= tr:
                s = pop(t, tr, 0.26, 0.08)
                self.place(canvas, self.bubbles[i], x, y, s=s, anchor=(0.0, 0.5), name=f'msg{i + 1}', qa=qa)
        # stamp slams on 「没有问题」
        tm = T['meiyou']
        t_st = max(tm - 0.12, self.sends()[2][2] + 0.01)      # slams once 「确认」 has landed
        if t >= t_st:
            u = prog(t, t_st, tm)
            sc = lerp(1.9, 1.0, e_in(u, 2)) if u < 1 else 1.0 - 0.04 * math.sin(math.pi * prog(t, tm, tm + 0.10))
            al = min(1.0, u * 2.5)
            st = self.stamp
            rgb, a = affine_elem(st, scale=sc, cx=380 + st.width / 2, cy=806 + st.height / 2, alpha=al)
            over_pm(canvas, rgb, a)
            boxes['stamp'] = elem_bbox(a)
        # composer + IME candidates
        comp_im, ctop, cands, falling = self.composer(t)
        self.place(canvas, comp_im, COMPOSER_X, ctop, name='input', qa=qa, shadow=(14, 0.2))
        for j, (chip, x, y, al) in enumerate(falling):
            self.place(canvas, chip, x, y, alpha=al, name=f'chip_fall{j}', qa=qa, shadow=(6, 0.18))
        if cands:
            bar = ime_bar(cands)
            self.place(canvas, bar, 150, 1196, name='ime', qa=qa, shadow=(8, 0.14))
        self.draw_pip(canvas, src_u8, e, qa)
        Dx, Dy, sx0, sy0, kx = self._pip_map
        f = v2_src_frame(k)
        fc, lp = self.faces[f]
        mp_ = lambda b: [int(Dx + (b[0] - sx0) * kx), int(Dy + (b[1] - sy0) * kx), int(Dx + (b[2] - sx0) * kx), int(Dy + (b[3] - sy0) * kx)]
        qa['face_screen'], qa['lips_screen'] = mp_(fc), mp_(lp)
        return to_u8(canvas)


def who_is(i):
    return CHAT[i][1]
