"""A0's shots as moving pictures (storyboard v2 §1, same design kit as the approved stills):
1, 2a, I1, 2b, I2, 2c, I3, 3, 4, 5, 6 (ip_intro), 12, 17, 19, 20.
Each shot function gets the v2 frame number and the plate frame (RGB uint8) and returns a Canvas (without the
global layer: main subtitle + step bar are drawn by a0render.global_layer).
Keyword times come from 04_captions/words_v2.json (manually verified onsets). SFX for these shots: SFX below.
"""
import math
import os
import sys
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from a0lib import *  # noqa

ASSETS = WORK / 'assets'
STICK = Path(os.environ.get("XM_STICKER_DIR", "assets/stickers"))  # point this at your own transparent big-head sticker directory


def T(sec):
    return int(round(sec * FPS))


def ki(sec):
    """keyword onset frame"""
    return int(round(sec * FPS))


# ------------------------------------------------------------------ timing (v2 s; keywords = words_v2 manual anchors)
K = dict(bu_hui=0.27, zhe_yang=1.57, vlog=4.13, kepu=7.86, bulou=12.31, buxiang=16.95, buhui=18.52, mianfei=20.70,
         kaiyuan=21.16, wendang=24.19, si=64.88, qianmian=133.08, si_bu=135.55, diyiban=146.52, rensheng=154.93,
         dierqx=155.45, dianzan=156.93, shoucang=157.30, pinglun=157.73, guanzhu=158.24, buyiyang=160.82)

SFX = [
    # shot 1
    dict(id='whoosh_fast', t=0.30, gain_db=-6, align='motion', note='镜1 整幅画面缩进右下框'),
    dict(id='tick', t=0.61, gain_db=-8, note='镜1 卡片 1 vlog'), dict(id='tick', t=0.84, gain_db=-8, note='镜1 卡片 2 科普'),
    dict(id='tick', t=1.07, gain_db=-8, note='镜1 卡片 3 不露脸'), dict(id='tick', t=1.24, gain_db=-8, note='镜1 卡片 4'),
    dict(id='tick', t=1.41, gain_db=-8, note='镜1 卡片 5'),
    dict(id='reverse_whoosh', t=1.57, gain_db=-6, align='end', note='镜1 「这样的视频」蓄力'),
    dict(id='hit', t=1.57, gain_db=-3, note='镜1 「这样的视频」砸下 = 说到「这」'),
    dict(id='whoosh_fast', t=1.95, gain_db=-7, align='motion', note='镜1 右下框放回全屏'),
    # 2a / inserts / 2b / 2c
    dict(id='pluck', t=4.13, gain_db=-6, note='镜2a 关键词 vlog'),
    dict(id='whoosh_fast', t=4.567, gain_db=-6, align='motion', note='切进插入① vlog 成片'),
    dict(id='pop_soft', t=7.567, gain_db=-5, note='插入①切回真人'),
    dict(id='pluck', t=7.86, gain_db=-6, pitch=2, note='镜2b 关键词 科普'),
    dict(id='whoosh_fast', t=8.467, gain_db=-6, align='motion', note='切进插入② 科普成片'),
    dict(id='pop_soft', t=11.80, gain_db=-5, pitch=2, note='插入②切回真人'),
    dict(id='pluck', t=12.31, gain_db=-6, pitch=4, note='镜2c 关键词 不露脸'),
    dict(id='whoosh_fast', t=13.467, gain_db=-6, align='motion', note='切进插入③ 不露脸成片'),
    dict(id='pop_soft', t=16.367, gain_db=-5, pitch=4, note='插入③切回真人'),
    # 3 / 4 / 5
    dict(id='hit', t=16.95, gain_db=-4, note='镜3 「不想剪辑」贴纸砸下'),
    dict(id='hit', t=18.52, gain_db=-4, pitch=2, note='镜3 「不会剪辑」贴纸砸下'),
    dict(id='whoosh_mid', t=20.30, gain_db=-6, align='motion', note='镜4 票根落下'),
    dict(id='stamp', t=20.70, gain_db=-3, note='镜4 「免费」红章'), dict(id='stamp', t=21.16, gain_db=-3, pitch=-2, note='镜4 「开源」黑章'),
    dict(id='whoosh_mid', t=22.84, gain_db=-6, align='motion', note='镜5 文档卡滑入'),
    dict(id='land', t=23.20, gain_db=-5, note='镜5 文档卡停稳'),
    dict(id='pluck', t=24.19, gain_db=-5, note='镜5 「文档」高亮'),
    # 6 ip_intro (sample settings, rel -> abs: shot start 25.0667)
    dict(id='pop_soft', t=25.0667 + 0.125, gain_db=0, note='镜6 大头贴 1'), dict(id='pop_soft', t=25.0667 + 0.975, gain_db=0, pitch=2, note='镜6 大头贴 2'),
    dict(id='pop_soft', t=25.0667 + 1.83, gain_db=0, pitch=4, note='镜6 大头贴 3'), dict(id='land', t=25.0667 + 1.915, gain_db=0, note='镜6 落定'),
    # 12
    dict(id='reverse_whoosh', t=64.88, gain_db=-6, align='end', note='镜12 大号 4 蓄力'),
    dict(id='hit', t=64.88, gain_db=-3, note='镜12 「四个步骤」大号 4 砸下'),
    dict(id='tick', t=65.00, gain_db=-8, note='镜12 步骤条第 1 格'), dict(id='tick', t=65.10, gain_db=-8, pitch=2, note='第 2 格'),
    dict(id='tick', t=65.20, gain_db=-8, pitch=4, note='第 3 格'), dict(id='tick', t=65.30, gain_db=-8, pitch=5, note='第 4 格'),
    # 17
    dict(id='whoosh_fast', t=133.00, gain_db=-7, align='motion', note='镜17 缩进右下框'),
    dict(id='whoosh_fast', t=133.08, gain_db=-6, align='motion', note='镜17 回顾 vlog'),
    dict(id='whoosh_fast', t=133.58, gain_db=-6, align='motion', note='镜17 回顾 科普'),
    dict(id='whoosh_fast', t=134.08, gain_db=-6, align='motion', note='镜17 回顾 不露脸'),
    dict(id='whoosh_fast', t=134.62, gain_db=-7, align='motion', note='镜17 放回全屏'),
    dict(id='hit', t=135.55, gain_db=-3, note='镜17 「4 步」小结贴纸 = 说到「四个步骤」'),
    # 19
    dict(id='stamp', t=146.52, gain_db=-3, note='镜19 「v1.0」贴纸 = 说到「第一版」'),
    dict(id='laser_zip', t=154.93, gain_db=-7, dur=0.25, note='镜19 曲线开始画（人生的）'),
    dict(id='shimmer', t=155.45, gain_db=-8, dur=1.0, note='镜19 「第二曲线」标签弹出 = 说到「第」（曲线同时画到上扬段）'),
    # 20
    dict(id='pop_soft', t=156.93, gain_db=-4, note='镜20 点赞'), dict(id='pop_soft', t=157.30, gain_db=-4, pitch=2, note='镜20 收藏'),
    dict(id='pop_soft', t=157.73, gain_db=-4, pitch=4, note='镜20 评论'), dict(id='pop_soft', t=158.24, gain_db=-4, pitch=7, note='镜20 关注'),
    dict(id='ident_hop', t=160.82, gain_db=-4, align='anchor', note='镜20 片尾标识音（候选「小鹿跳」，待用户定）= 眨眼大头贴落定'),
]


# ------------------------------------------------------------------ assets
@lru_cache(maxsize=None)
def asset(name):
    return Image.open(ASSETS / name).convert('RGBA')


def cover(im, w, h):
    s = max(w / im.width, h / im.height)
    r = im.resize((int(im.width * s + 0.5), int(im.height * s + 0.5)), Image.LANCZOS)
    x0, y0 = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x0, y0, x0 + w, y0 + h))


@lru_cache(maxsize=None)
def paper_bg(tone=(243, 238, 228), seed=11, dots=0):
    return paper(tone=tone, seed=seed, dots=dots)


def speed_lines_layer(x, y, n=5, length=120, gap=22, lw=6, ang=200, color=INK, alpha=200):
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    a = math.radians(ang)
    for i in range(n):
        ox_ = x + i * gap * math.sin(a)
        oy_ = y - i * gap * math.cos(a)
        L = length * (0.6 + 0.4 * ((i * 37) % 5) / 4)
        d.line((ox_, oy_, ox_ + math.cos(a) * L, oy_ + math.sin(a) * L), fill=color + (alpha,), width=lw)
    return lay


# ================================================================== shot 1: hook + six flashing cards, the presenter in the PiP
S1_CARDS = [  # (asset, rot, centre, tall, lands at)
    ('vlog_9.60.png', -15, (330, 1270), True, 0.61), ('kepu_20.00.png', -12, (290, 860), True, 0.84),
    ('faceless_20.00.png', -6, (215, 1060), True, 1.07), ('card01_2.9.png', 9, (660, 860), False, 1.24),
    ('card02_2.6.png', 12, (700, 1250), False, 1.41),
]


@lru_cache(maxsize=None)
def s1_card(i):
    name, rot, c, tall, _ = S1_CARDS[i]
    size = (420, 747) if tall else (560, 747)
    return rotate(photo(cover(asset(name), *size), border=12, radius=8), rot)


@lru_cache(maxsize=None)
def s1_top():
    return rotate(photo(asset('card03_3.55.png').resize((620, 827), Image.LANCZOS), border=14, radius=8), -2)


@lru_cache(maxsize=None)
def s1_labels():
    l1 = rotate(label([('不会剪辑', True), ('也能做出', False)], size=64, pad=(26, 16)), 2)
    l2 = rotate(label([('这样的视频', True)], size=150, pad=(30, 14), radius=20), -2.5)
    return l1, l2


def s01(f, base):
    t = f / FPS
    cv = Canvas(paper_bg())
    region = pip_region(face_union(0, 72))
    # card pile builds up, one card per flash (slam in from 1.25x, 4 frames)
    for i, (name, rot, c, tall, at) in enumerate(S1_CARDS):
        k = f - T(at)
        if k < 0:
            continue
        s = 1.25 - 0.25 * ease_out_cubic((k + 1) / 4) if k < 4 else 1.0
        cv.put(scaled(s1_card(i), s), c[0], c[1], f'pile{i}', kind='bg', anchor='c', blur=10, salpha=0.28)
    k = f - T(K['zhe_yang'])
    if k >= 0:
        s = 1.3 - 0.3 * ease_out_cubic((k + 1) / 4) if k < 4 else 1.0
        cv.put(scaled(s1_top(), s), 430, 1060, 'pile_top', kind='bg', anchor='c', blur=16, salpha=0.4)
    if f >= T(0.61):
        cv.layer(speed_lines_layer(70, 700, n=4, length=110, ang=190), 'speed1', kind='fx')
        cv.layer(speed_lines_layer(80, 1300, n=3, length=90, ang=170), 'speed2', kind='fx')
    # presenter: full -> PiP (0.30-0.75 s), PiP -> full (1.95-2.40 s)
    if t < 0.30:
        p = 0.0
    elif t < 1.95:
        p = ease_in_out_cubic((t - 0.30) / 0.45)
    else:
        p = 1 - ease_in_out_cubic((t - 1.95) / 0.45)
    lay, st = pip_layer(base, p, region)
    cv.img.alpha_composite(lay)
    fc, lp = face_at(f)
    cv.items.append(('max_face', map_box(fc, st), 'face'))
    cv.items.append(('max_lips', map_box(lp, st), 'lips'))
    # hook labels: line 1 pops at 「不」, the keyword slams at 「这」; both leave 2.05-2.35 s
    l1, l2 = s1_labels()
    out_a = 1 - ease_in_out_cubic((t - 2.05) / 0.30) if t > 2.05 else 1.0
    lift = 60 * ease_in_cubic((t - 2.05) / 0.30) if t > 2.05 else 0
    k1 = f - T(K['bu_hui'])
    if k1 >= 0 and out_a > 0:
        cv.put(scaled(l1, pop_curve(k1, grow=3, settle=8, peak=1.1)), 52 + l1.width / 2, 196 + l1.height / 2 - lift,
               'hook_line1', kind='text', anchor='c', alpha=out_a)
    k2 = f - T(K['zhe_yang'])
    if k2 >= -4 and out_a > 0:
        s = slam_curve(k2 + 4, frames=4, start=1.8)
        cv.put(scaled(l2, s), 36 + l2.width / 2, 318 + l2.height / 2 - lift, 'hook_keyword', kind='text', anchor='c',
               blur=16, salpha=0.35, alpha=out_a if k2 >= 0 else 0.55 + 0.45 * (k2 + 4) / 4)
        if k2 >= 0 and k2 < 14:
            b = burst(46, 86, n=7, lw=8, a0=-70, a1=50)
            cv.put(scaled(b, 0.7 + 0.3 * ease_out_cubic(k2 / 5)), 850, 330 - lift, 'burst', kind='fx', shadow=False,
                   alpha=max(0.0, 1 - k2 / 14) * out_a)
    return cv


# ================================================================== inserts: finished demo full screen + small tag
@lru_cache(maxsize=None)
def demo_tag(kind):
    f_ = font('Heavy', 26)
    txt = f'成片 · {kind}'
    w = int(f_.getlength(txt) + 84)
    im = Image.new('RGBA', (w, 52), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, 51), radius=26, fill=(20, 20, 20, 230))
    d.polygon([(20, 21), (29, 21), (40, 12), (40, 40), (29, 31), (20, 31)], fill=YELLOW)
    d.arc((34, 15, 52, 37), -50, 50, fill=YELLOW, width=4)
    d.text((62, 26), txt, font=f_, fill=(255, 255, 255), anchor='lm')
    return im


def s_insert(kind):
    def fn(f, base):
        v0 = [p['v0'] for p in T_.PIECES if p['kind'] == 'insert' and p['key'] == {'vlog': 'vlog', '科普': 'kepu', '不露脸': 'faceless'}[kind]][0]
        cv = Canvas(base)
        k = f - v0
        tag = demo_tag(kind)
        x = 40 - (1 - ease_out_cubic((k + 1) / 5)) * (tag.width + 60)
        cv.put(tag, x, 196, 'demo_tag', kind='text', shadow=False)
        return cv
    return fn


import timeline as T_  # noqa: E402


# ================================================================== 2a / 2b / 2c: the presenter full screen (keyword in the strip)
def s_plain(f, base):
    return Canvas(base)


# ================================================================== shot 3: two vertical stickers slam in on the sides
@lru_cache(maxsize=None)
def s3_stickers():
    left = rotate(vlabel('不想剪辑', size=80), 4)
    right = rotate(vlabel('不会剪辑', size=80, bg=YELLOW), -4)
    return left, right


def s03(f, base):
    cv = Canvas(base)
    fc, lp = face_at(f)
    cv.items += [('max_face', fc, 'face'), ('max_lips', lp, 'lips')]
    left, right = s3_stickers()
    t = f / FPS
    ex = ease_in_cubic((t - 19.25) / 0.2) if t > 19.25 else 0.0         # exit: slide out sideways
    for (im, at, x, y, side, nm) in ((left, K['buxiang'], 14, 330, -1, 'kw_left'), (right, K['buhui'], 1080 - 8 - right.width, 620, 1, 'kw_right')):
        k = f - T(at)
        if k < -3:
            continue
        s = slam_curve(k + 3, frames=3, start=1.7)
        dx = side * ex * (im.width + 80)
        a = 1.0 if k >= 0 else 0.5 + 0.5 * (k + 3) / 3
        cv.put(scaled(im, s), x + im.width / 2 + dx, y + im.height / 2, nm, kind='text', anchor='c', blur=14, salpha=0.4, alpha=a)
        if 0 <= k < 12 and ex == 0:                                     # impact lines above the sticker, away from the face
            b = burst(40, 72, n=7, lw=7, a0=-150, a1=-30)
            cv.put(scaled(b, 0.6 + 0.4 * ease_out_cubic(k / 4)), x + im.width / 2, y - 18, f'hit_{nm}', kind='fx', shadow=False,
                   anchor='c', alpha=max(0.0, 1 - k / 12))
    return cv


# ================================================================== shot 4: ticket stub above the head, two stamps
@lru_cache(maxsize=None)
def ticket_stub(w=620, h=150):
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=14, fill=(250, 244, 228, 255))
    for cy in (0, h):
        d.ellipse((w * 0.32 - 18, cy - 18, w * 0.32 + 18, cy + 18), fill=(0, 0, 0, 0))
    for y in range(18, h - 18, 14):
        d.line((w * 0.32, y, w * 0.32, y + 7), fill=(170, 160, 140, 255), width=3)
    d.text((w * 0.16, h / 2 - 16), 'OPEN', font=font('Heavy', 30), fill=(150, 140, 120), anchor='mm')
    d.text((w * 0.16, h / 2 + 20), 'SOURCE', font=font('Bold', 22), fill=(150, 140, 120), anchor='mm')
    return rotate(im, -2)


@lru_cache(maxsize=None)
def ink_stamp(text, color, s=104, rot=-8):
    im = Image.new('RGBA', (s * 2, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 6, s * 2 - 7, s - 7), radius=16, outline=color + (235,), width=8)
    d.text((s, s / 2 + 2), text, font=font('Heavy', int(s * 0.52)), fill=color + (235,), anchor='mm')
    rng = np.random.default_rng(len(text) + color[0])
    a = np.array(im.split()[3]).astype(np.float32)
    a *= (rng.random(a.shape) > 0.07) * 0.25 + 0.75
    im.putalpha(Image.fromarray(a.astype(np.uint8)))
    return rotate(im, rot)


def s04(f, base):
    cv = Canvas(base)
    fc, lp = face_at(f)
    cv.items += [('max_face', fc, 'face'), ('max_lips', lp, 'lips')]
    t = f / FPS
    tk = ticket_stub()
    tx, ty = (W - tk.width) // 2, 196
    if t < 20.30:
        return cv
    fall = ease_out_back((t - 20.30) / 0.30, 1.2)                       # lands ~20.60
    lift = 420 * ease_in_cubic((t - 21.85) / 0.22) if t > 21.85 else 0  # exit upwards
    y = ty - (1 - fall) * 380 - lift
    cv.put(tk, tx, y, 'ticket', kind='overlay', blur=12, salpha=0.35)
    for (txt, col, at, dx, dy, rot, nm) in (('免费', RED, K['mianfei'], 215, 20, -8, 'stamp_free'),
                                             ('开源', INK, K['kaiyuan'], 420, 26, 6, 'stamp_open')):
        k = f - T(at)
        if k < -3:
            continue
        stp = ink_stamp(txt, col, 104, rot)
        s = slam_curve(k + 3, frames=3, start=1.6)
        a = 1.0 if k >= 0 else 0.4 + 0.2 * (k + 3)
        cv.put(scaled(stp, s), tx + dx + stp.width / 2, y + dy + stp.height / 2, nm, kind='overlay', anchor='c', shadow=False, alpha=a)
    return cv


# ================================================================== shot 5: paper document card slides to the upper right
@lru_cache(maxsize=None)
def doc_card(lit):
    w, h = 270, 300
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(0, 0), (w - 46, 0), (w, 46), (w, h), (0, h)], fill=CARD + (255,))
    d.polygon([(w - 46, 0), (w - 46, 46), (w, 46)], fill=(222, 214, 198, 255))
    d.line([(w - 46, 0), (w - 46, 46), (w, 46)], fill=(200, 190, 172, 255), width=3)
    fT = font('Heavy', 46)
    if lit:
        tw = fT.getlength('文档')
        d.rectangle((24, 84 - 22, 30 + tw * lit, 84 + 12), fill=YELLOW)
    d.text((28, 84), '文档', font=fT, fill=INK, anchor='ls')
    d.text((28 + fT.getlength('文档') + 12, 84), '工具清单', font=font('Bold', 24), fill=(140, 132, 120), anchor='ls')
    for i, item in enumerate(('动效库', '音效库', '风格包')):
        y = 128 + i * 52
        d.rounded_rectangle((28, y, 60, y + 32), radius=6, outline=INK, width=4)
        c = icon_check(34, color=GREEN, lw=9)
        im.alpha_composite(c, (27, y - 3))
        d.text((74, y + 16), item, font=font('Bold', 30), fill=INK, anchor='lm')
        d.line((74 + 100, y + 16, w - 30, y + 16), fill=(214, 206, 192, 255), width=4)
    out = Image.new('RGBA', (w + 10, h + 26), (0, 0, 0, 0))
    out.alpha_composite(im, (0, 26))
    out.alpha_composite(rotate(tape(110, 34, color=(250, 222, 120), seed=5), -6), (w // 2 - 55, 0))
    return rotate(out, 4)


def s05(f, base):
    cv = Canvas(base)
    fc, lp = face_at(f)
    cv.items += [('max_face', fc, 'face'), ('max_lips', lp, 'lips')]
    t = f / FPS
    if t < 22.84:
        return cv
    kx = ease_out_back((t - 22.84) / 0.38, 1.1)                             # lands ~23.2
    out_ = ease_in_cubic((t - 24.85) / 0.21) if t > 24.85 else 0.0
    k = f - T(K['wendang'])
    lit = round(ease_out_cubic((k + 1) / 8), 2) if k >= 0 else 0
    card = doc_card(lit)
    s = pop_curve(k, grow=3, settle=9, peak=1.08) if k >= 0 else 1.0
    x_end = 760
    x = 1100 + (x_end - 1100) * kx + out_ * 380
    cv.put(scaled(card, s), x + card.width / 2, 208 + card.height / 2, 'doc_card', kind='overlay', anchor='c', blur=14, salpha=0.35)
    return cv


# ================================================================== shot 6: ip_intro component (rendered by xiaolu-motion)
class IpIntro:
    def __init__(self):
        self.path = A0 / 'shots/s06/s06_overlay.mov'
        self.r, self.next = None, None

    def frame(self, i):
        if self.r is None or i != self.next:
            if self.r:
                self.r.close()
            self.r = RawReader(self.path, start_frame=i, pix='rgb24')
            self.next = i
        im = self.r.read()
        self.next += 1
        return im


IPI = IpIntro()


def s06(f, base):
    return Canvas(IPI.frame(f - 752))


# ================================================================== shot 12: big 4 + 「个步骤」 sticker, the step bar enters
@lru_cache(maxsize=None)
def s12_parts():
    four = rotate(sticker_outline(plain_text('4', 230, color=INK), px=11), -6)
    tag = rotate(vlabel('个步骤', size=70, bg=YELLOW), -3)
    return four, tag


def s12(f, base):
    cv = Canvas(base)
    fc, lp = face_at(f)
    cv.items += [('max_face', fc, 'face'), ('max_lips', lp, 'lips')]
    four, tag = s12_parts()
    k = f - T(K['si'])
    t = f / FPS
    if k < -4:
        return cv
    out_ = ease_in_cubic((t - 65.50) / 0.22) if t > 65.50 else 0.0
    a = 1 - out_
    s = slam_curve(k + 4, frames=4, start=2.0)
    cv.put(scaled(four, s * (1 - 0.3 * out_)), 905, 300 + four.height / 2, 'big_4', kind='text', anchor='c', blur=16, salpha=0.4,
           alpha=a if k >= 0 else 0.5 + 0.125 * (k + 4))
    if k >= 0 and k < 10:
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        cx, cy = 905 - four.width / 2 + 30, 300 + 40
        for ang in (200, 226, 252):
            aa = math.radians(ang)
            d.line((cx + math.cos(aa) * 26, cy + math.sin(aa) * 26, cx + math.cos(aa) * 74, cy + math.sin(aa) * 74),
                   fill=INK + (int(255 * (1 - k / 10)),), width=9)
        cv.layer(lay, 'impact', kind='fx')
    k2 = f - T(K['si'] + 0.12)
    if k2 >= 0:
        cv.put(scaled(tag, pop_curve(k2, grow=3, settle=8, peak=1.12) * (1 - 0.3 * out_)), 1080 - 30 - tag.width / 2, 590 + tag.height / 2,
               'kw_steps', kind='text', anchor='c', blur=12, salpha=0.35, alpha=a)
    return cv


# ================================================================== shot 17: recap (three demo clips as cards), the presenter in the PiP, 「4 步」
RECAP = [('vlog', 26.40, 133.08, (-9, 270, 800)), ('kepu', 25.90, 133.58, (6, 350, 810)), ('faceless', 28.90, 134.08, (-3, 320, 800))]


class DemoClip:
    def __init__(self, key, t0):
        self.path = DEMOS / {'vlog': 'vlog/vlog_demo.mp4', 'kepu': 'kepu/kepu_demo.mp4', 'faceless': 'faceless/faceless_demo.mp4'}[key]
        self.f0 = int(round(t0 * FPS))
        self.cache = {}

    def frame(self, i):
        i = max(0, min(14, i))
        if not self.cache:
            r = RawReader(self.path, start_frame=self.f0, n=15, pix='rgb24', w=540, h=960, vf_extra='scale=540:960:flags=area')
            for j in range(15):
                self.cache[j] = r.read()
            r.close()
        return self.cache[i]


CLIPS = {k: DemoClip(k, t0) for k, t0, _, _ in RECAP}


@lru_cache(maxsize=None)
def four_bu():
    im = label([('4', True), (' 步', False)], size=120, pad=(30, 10), radius=20)
    return rotate(sticker_outline(im, px=10), -5)


def s17(f, base):
    t = f / FPS
    cv = Canvas(paper_bg(tone=(240, 234, 222), seed=17, dots=40))
    region = pip_region(face_union(3967, 4118))
    if t < 133.00:
        p = 0.0
    elif t < 134.62:
        p = ease_in_out_cubic((t - 133.00) / 0.45)
    else:
        p = 1 - ease_in_out_cubic((t - 134.62) / 0.45)
    out_ = ease_in_cubic((t - 134.62) / 0.30) if t > 134.62 else 0.0
    for key, t0, at, (rot, cx, cy) in RECAP:
        k = f - T(at)
        if k < 0 or p <= 0:
            continue
        idx = min(k, 14)
        clip = Image.fromarray(CLIPS[key].frame(idx)).convert('RGBA').resize((432, 768), Image.LANCZOS)
        card = rotate(photo(clip, border=12, radius=10), rot)
        s = 1.2 - 0.2 * ease_out_cubic((k + 1) / 4) if k < 4 else 1.0
        dx = -out_ * 700
        cv.put(scaled(card, s), cx + dx, cy, f'recap_{key}', kind='bg', anchor='c', blur=16, salpha=0.35)
    lay, st = pip_layer(base, p, region)
    cv.img.alpha_composite(lay)
    fc, lp = face_at(f)
    cv.items += [('max_face', map_box(fc, st), 'face'), ('max_lips', map_box(lp, st), 'lips')]
    k = f - T(K['si_bu'])
    if k >= -4:
        out2 = ease_in_cubic((t - 136.95) / 0.3) if t > 136.95 else 0.0
        im = four_bu()
        s = slam_curve(k + 4, frames=4, start=1.9)
        cv.put(scaled(im, s * (1 - 0.3 * out2)), 1080 - 40 - im.width / 2, 250 + im.height / 2, 'four_bu', kind='text', anchor='c',
               blur=16, salpha=0.4, alpha=(1 - out2) if k >= 0 else 0.5 + 0.125 * (k + 4))
    return cv


# ================================================================== shot 19: v1.0 sticker, hand-drawn rising curve
@lru_cache(maxsize=None)
def v10():
    im = label([('v1.0', True)], size=84, pad=(24, 8), radius=16, marker=None, bg=YELLOW)
    sub = label([('第一版', False)], size=34, pad=(12, 4), radius=8)
    out = Image.new('RGBA', (max(im.width, sub.width) + 20, im.height + sub.height + 6), (0, 0, 0, 0))
    out.alpha_composite(im, (0, 0))
    out.alpha_composite(sub, (14, im.height + 6))
    return rotate(sticker_outline(out, px=9), 7)


def curve_points():
    xs = np.linspace(0, 1, 120)
    pts = []
    for x in xs:                                   # S-curve: flat start, dip, then steep rise
        y = 0.18 * math.sin(x * math.pi * 1.1) * (1 - x) - 0.95 * (1 / (1 + math.exp(-10 * (x - 0.62)))) + 0.02
        pts.append((712 + x * 318, 350 + y * 170))
    return pts


def s19(f, base):
    cv = Canvas(base)
    fc, lp = face_at(f)
    cv.items += [('max_face', fc, 'face'), ('max_lips', lp, 'lips')]
    t = f / FPS
    k = f - T(K['diyiban'])
    if -3 <= k and t < 150.3:
        out_ = ease_in_cubic((t - 150.0) / 0.3) if t > 150.0 else 0.0
        s = slam_curve(k + 3, frames=3, start=1.7)
        im = v10()
        cv.put(scaled(im, s * (1 - 0.2 * out_)), 1080 - 50 - im.width / 2, 300, 'v10', kind='text', anchor='c', blur=12, salpha=0.35,
               alpha=(1 - out_) if k >= 0 else 0.5)
    if t >= K['rensheng']:
        pr = ease_in_out_cubic((t - K['rensheng']) / 1.05)             # drawn 154.93 -> 155.98
        fade = 1 - ease_in_cubic((t - 156.18) / 0.15) if t > 156.18 else 1.0
        pts = curve_points()
        n = max(2, int(len(pts) * pr))
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        # axes (light), the curve (ink, marker yellow under it), an arrow head when done
        d.line((704, 372, 704, 190), fill=INK + (int(110 * fade),), width=4)
        d.line((704, 372, 1040, 372), fill=INK + (int(110 * fade),), width=4)
        d.line(pts[:n], fill=YELLOW + (int(255 * fade),), width=22, joint='curve')
        d.line(pts[:n], fill=INK + (int(255 * fade),), width=8, joint='curve')
        if pr >= 0.98:
            (ex, ey), (px_, py_) = pts[-1], pts[-6]
            ang = math.atan2(ey - py_, ex - px_)
            for sg in (-1, 1):
                aa = ang + math.pi - sg * 0.5
                d.line((ex, ey, ex + math.cos(aa) * 34, ey + math.sin(aa) * 34), fill=INK + (int(255 * fade),), width=8)
        cv.layer(lay, 'curve', kind='overlay')
        if f >= T(K['dierqx']):                                            # tag pops exactly at 「第二曲线」
            tg = label([('第二曲线', True)], size=36, pad=(12, 4), radius=8)
            k2 = f - T(K['dierqx'])
            cv.put(scaled(tg, pop_curve(k2, grow=3, settle=8, peak=1.12)), 722 + tg.width / 2, 212, 'curve_tag', kind='text', anchor='c',
                   blur=8, salpha=0.3, alpha=fade)
    return cv


# ================================================================== shot 20: the presenter as a taped photo, four icons, wink sticker
def live_photo_img(rgb, scale=0.66, rot=1.5):
    s = Image.fromarray(rgb).convert('RGBA')
    w, h = int(W * scale), int(H * scale)
    p = photo(s.resize((w, h), Image.LANCZOS), border=14, radius=18)
    out = Image.new('RGBA', (p.width + 40, p.height + 40), (0, 0, 0, 0))
    out.alpha_composite(p, (20, 34))
    for (tx, ang, col, sd) in ((40, -28, (250, 222, 120), 31), (p.width - 150, 24, (170, 205, 245), 32)):
        out.alpha_composite(rotate(tape(150, 40, color=col, seed=sd), ang), (tx, 0))
    return out.rotate(rot, resample=Image.BICUBIC, expand=True)


@lru_cache(maxsize=None)
def icon_sticker(name):
    ic = {'点赞': icon_heart(96), '收藏': icon_star(96), '评论': icon_bubble(96), '关注': icon_plus(96)}[name]
    im = Image.new('RGBA', (150, 196), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((5, 0, 145, 140), fill=CARD + (255,), outline=(215, 205, 190), width=3)
    im.alpha_composite(ic, (75 - ic.width // 2, 70 - ic.height // 2))
    d.rounded_rectangle((20, 150, 130, 194), radius=12, fill=INK)
    d.text((75, 172), name, font=font('Bold', 30), fill=(255, 255, 255), anchor='mm')
    return im


@lru_cache(maxsize=None)
def wink_card():
    c = Image.open(STICK / 'card-wink-blue.png').convert('RGBA').resize((264, 264), Image.LANCZOS)
    c = photo(c, border=10, radius=26)
    t = rotate(tape(120, 36, color=(245, 170, 190), seed=21), 12)
    out = Image.new('RGBA', (c.width + 20, c.height + 26), (0, 0, 0, 0))
    out.alpha_composite(c, (0, 26))
    out.alpha_composite(t, (c.width - 120, 0))
    return rotate(out, -7)


S20_ICONS = [('点赞', K['dianzan'], (10, 232), -6), ('收藏', K['shoucang'], (186, 256), 5), ('评论', K['pinglun'], (14, 468), 4),
             ('关注', K['guanzhu'], (190, 492), -5)]


def s20(f, base):
    t = f / FPS
    cv = Canvas(paper_bg(tone=PAPER, seed=20, dots=40))
    p = ease_in_out_cubic((t - 156.333) / 0.45)
    # the live frame shrinks from full screen into the photo card on the right
    el = live_photo_img(base)
    s_end = 1.0
    ox_end, oy_end = 1062 - el.width, 220
    if p < 1:
        # interpolate: full frame (scale 1/0.66 of the photo, placed so the photo's inner frame covers the canvas)
        sc = 1 / 0.66 + (1 - 1 / 0.66) * p
        inner_x, inner_y = 20 + 14, 34 + 14
        el2 = scaled(el, sc)
        x_full, y_full = -inner_x * sc, -inner_y * sc
        x = x_full + (ox_end - x_full) * p
        y = y_full + (oy_end - y_full) * p
        cv.put(el2, x, y, 'live_photo', kind='bg', blur=18, salpha=0.35 * p)
        st = (0.66 * sc, x + (20 + 14) * sc, y + (34 + 14) * sc)
    else:
        cv.put(el, ox_end, oy_end, 'live_photo', kind='bg', blur=18, salpha=0.35)
        st = (0.66, ox_end + 20 + 14, oy_end + 34 + 14)
    fc, lp = face_at(f)
    cv.items += [('max_face', map_box(fc, st), 'face'), ('max_lips', map_box(lp, st), 'lips')]
    for name, at, (x, y), rot in S20_ICONS:
        k = f - T(at)
        if k < 0:
            continue
        im = rotate(icon_sticker(name), rot)
        s = ease_out_back((k + 1) / 6, 2.2) if k < 6 else 1.0
        cv.put(scaled(im, max(0.05, s)), x + im.width / 2, y + im.height / 2, f'icon_{name}', kind='overlay', anchor='c', blur=10, salpha=0.3)
    k = f - T(K['buyiyang'])
    if k >= -3:
        im = wink_card()
        s = slam_curve(k + 3, frames=3, start=1.6)
        cv.put(scaled(im, s), 4 + im.width / 2, 770 + im.height / 2, 'big_head_wink', kind='overlay', anchor='c', blur=18, salpha=0.4,
               alpha=1.0 if k >= 0 else 0.6)
    return cv


SHOT_FN = {'01': s01, '02a': s_plain, 'I1': s_insert('vlog'), '02b': s_plain, 'I2': s_insert('科普'), '02c': s_plain,
           'I3': s_insert('不露脸'), '03': s03, '04': s04, '05': s05, '06': s06, '12': s12, '17': s17, '19': s19, '20': s20}
