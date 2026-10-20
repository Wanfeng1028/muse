"""Render the v2 storyboard keyframes (1080x1920).

new frames:  I1 I2 I3 (demo inserts), 10a 10b (paper box), 11 (box tossed to Agent), 13a 13b (chat),
             14a 14b (card table + style brush), 15 (film strip), 16a 16b (self-check on the live frame), 18 (split).
inputs (read-only): _work/src_frames + _work/matte + _work/faces.jsonl (extract_frames.py), style samples in the
scratchpad, card frames in _work/assets, v1 frames for the film strip.
usage:  python3 src/render_v2.py [keys...]      (15 must run after the others: it prints them onto the film)
"""
import json
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sb_lib import *  # noqa
from timeline import KEYFRAMES, v2_to_src, fmt, DEMOS

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / '_work'
V1 = ROOT.parent / 'storyboard_v1'
SP = Path(os.environ.get("XM_SCRATCH_DIR", "/tmp/xm_scratch"))
STY = SP / 'styles-v2'
ASSETS = {
    'vlog_open': STY / 'vlog/out/1A_collage_open.jpg',
    'vlog_daily': STY / 'vlog/out/1B_collage_daily.jpg',
    'vlog_trans': STY / 'vlog/out/1C_collage_transition.jpg',
    'film_open': STY / 'vlog/out/2A_film_open.jpg',
    'mag_A': STY / 'explainer/2_杂志编辑风_A_开场标题.png',
    'launch_A': STY / 'explainer/3_发布会大运镜_A_开场标题.png',
    'faceless_A': STY / 'faceless/纸本手绘_A_开场钩子.png',
    'faceless_C': STY / 'faceless/纸本手绘_C_揭晓帧.png',
    'kepu_513': WORK / 'assets/kepu_0513.png',
    'kepu_36': WORK / 'assets/kepu_0036.png',
    'kepu_600': WORK / 'assets/kepu_0600.png',
    'vlog_I1': WORK / 'assets/vlog_0054.png',
    'vlog_7': WORK / 'assets/vlog_0565.png',
    'vlog_10a': WORK / 'assets/vlog_0720.png',
    'vlog_ws': WORK / 'assets/vlog_0534.png',
    'vlog_t1': WORK / 'assets/vlog_0102.png',
    'vlog_t2': WORK / 'assets/vlog_0216.png',
    'vlog_t3': WORK / 'assets/vlog_0288.png',
    'vlog_t4': WORK / 'assets/vlog_0345.png',
    'card03': WORK / 'assets/card03_3.55.png',
    'card01': WORK / 'assets/card01_2.9.png',
    'card02': WORK / 'assets/card02_2.6.png',
    'card04': WORK / 'assets/card04_2.0.png',
    'card06': WORK / 'assets/card06_2.0.png',
    'card07': WORK / 'assets/card07_4.0.png',
}
OUT = ROOT
FACELESS_FRAMES = DEMOS / 'faceless/filmstrip/frames'


def faceless(t):
    """faceless demo still (the mp4 is being re-mixed: stills come from its 0.2 s filmstrip, 540x960 -> 1080x1920)"""
    return Image.open(FACELESS_FRAMES / f't{t:05.1f}s.jpg').convert('RGBA').resize((W, H), Image.LANCZOS)


FACES = {}
for line in (WORK / 'faces.jsonl').read_text().splitlines():
    j = json.loads(line)
    FACES[int(j['frame'])] = j


# ------------------------------------------------------------------ source helpers (same as v1)
def src_of(key):
    kind, seg, f = v2_to_src(KEYFRAMES[key])
    assert kind == 'max', key
    return f


def load_src(frame):
    return Image.open(WORK / f'src_frames/{frame:06d}.png').convert('RGBA')


def load_matte(frame):
    m = cv2.imread(str(WORK / f'matte/{frame:06d}_matte.png'), cv2.IMREAD_GRAYSCALE)
    m = cv2.resize(m, (W, H), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
    core = (m > 0.5).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(core, 8)
    if n > 1:
        big = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])
        keep = [k for k in range(1, n) if st[k, cv2.CC_STAT_AREA] > 0.02 * st[big, cv2.CC_STAT_AREA]]
        roi = cv2.dilate(np.isin(lab, keep).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (97, 97)))
        m *= cv2.GaussianBlur(roi.astype(np.float32), (0, 0), 16)
    solid = (m > 0.25).astype(np.uint8)
    inner = cv2.GaussianBlur(cv2.erode(solid, np.ones((9, 9), np.uint8)).astype(np.float32), (0, 0), 1.2)
    m = np.maximum(m, inner)
    return np.clip((m - 0.04) / 0.92, 0, 1)


def head_top(matte):
    return int(np.where(matte.max(1) > 0.5)[0].min())


def face_of(frame):
    return tuple(FACES[frame]['face'])


def lips_of(frame):
    return tuple(FACES[frame]['lips'])


def img(key, size=None):
    im = Image.open(ASSETS[key]).convert('RGBA')
    return im.resize(size, Image.LANCZOS) if size else im


def cover(im, w, h):
    """scale + centre-crop to exactly w x h"""
    s = max(w / im.width, h / im.height)
    r = im.resize((int(im.width * s + 0.5), int(im.height * s + 0.5)), Image.LANCZOS)
    x0, y0 = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x0, y0, x0 + w, y0 + h))


def person_layer(frame, s=1.0, ox=0, oy=0):
    """matted person (RGBA, full canvas) scaled by s and moved by (ox, oy); plus mapped face / lips boxes"""
    src, m = load_src(frame), load_matte(frame)
    p = src.copy()
    p.putalpha(Image.fromarray((m * 255).astype(np.uint8)))
    p = p.resize((int(W * s), int(H * s)), Image.LANCZOS)
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    lay.alpha_composite(p.crop((max(0, -ox), max(0, -oy), p.width, p.height)), (max(0, ox), max(0, oy)))

    def mp(b):
        return (int(b[0] * s + ox), int(b[1] * s + oy), int(b[2] * s + ox), int(b[3] * s + oy))
    return lay, mp(face_of(frame)), mp(lips_of(frame)), int(head_top(m) * s + oy)


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


def demo_tag(kind, placeholder):
    """small tag top-left of an insert: speaker + 成片 · kind"""
    f = font('Heavy', 26)
    txt = f'成片 · {kind}'
    w = int(f.getlength(txt) + 84)
    im = Image.new('RGBA', (w, 52), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, 51), radius=26, fill=(20, 20, 20, 230))
    # speaker icon (drawn, no glyph)
    d.polygon([(20, 21), (29, 21), (40, 12), (40, 40), (29, 31), (20, 31)], fill=YELLOW)
    d.arc((34, 15, 52, 37), -50, 50, fill=YELLOW, width=4)
    d.text((62, 26), txt, font=f, fill=(255, 255, 255), anchor='lm')
    return im


def save(fr, key, allow=(), expect_face_hit=()):
    out = OUT / f'shot{key}.png'
    fr.img.convert('RGB').save(out, optimize=True)
    probs = fr.check(allow=set(allow))
    probs = [p for p in probs if not any(p.startswith(n + ' ') for n in expect_face_hit)]
    return out, probs


# ================================================================== inserts
def shotI1():
    fr = Frame(img('vlog_I1'), name='I1')
    fr.add(demo_tag('vlog', False), 40, 196, 'demo_tag', kind='text', shadow=False)
    return fr


def shotI2():
    fr = Frame(img('kepu_513'), name='I2')
    fr.add(demo_tag('科普', False), 40, 196, 'demo_tag', kind='text', shadow=False)
    return fr


def shotI3():
    fr = Frame(faceless(3.2), name='I3')
    fr.add(demo_tag('不露脸', False), 40, 196, 'demo_tag', kind='text', shadow=False)
    return fr


# ================================================================== shot 16: self-check on the live frame
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


def shot16(which):
    key = '16a' if which == 'a' else '16b'
    f = src_of(key)
    s = load_src(f)
    fr = Frame(s, face=face_of(f), lips=lips_of(f), name=key)
    step_bar(fr, active=4, done=(1, 2, 3))
    fr.add(check_chip(), 40, 290, 'check_chip', kind='text', shadow=False)
    lips = lips_of(f)
    runs = [('如果出现', False), ('字压到脸上', True)]
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    if which == 'a':
        # the subtitle deliberately sits on the mouth; red box scans it
        cy = int((lips[1] + lips[3]) / 2)
        sb = subtitle_c(fr, runs, cy=cy)
        fr.items[-1] = ('subtitle_on_mouth', sb, 'text')
        # scan line sweeping down through the strip
        for i in range(10):
            a = int(120 * (1 - i / 10))
            d.line((0, sb[3] + 18 + i * 3, W, sb[3] + 18 + i * 3), fill=RED + (a,), width=3)
        box = (sb[0] - 16, sb[1] - 16, sb[2] + 16, sb[3] + 16)
        d.rectangle(box, outline=RED + (255,), width=4)
        hud_brackets(d, box, RED + (255,))
        # target: the safe band (dashed green, ghost)
        tb = (sb[0], SUB_CY - 56, sb[2], SUB_CY + 56)
        for x in range(int(tb[0]), int(tb[2]), 26):
            d.line((x, tb[1], min(x + 14, tb[2]), tb[1]), fill=GREEN + (200,), width=5)
            d.line((x, tb[3], min(x + 14, tb[2]), tb[3]), fill=GREEN + (200,), width=5)
        for y in range(int(tb[1]), int(tb[3]), 26):
            d.line((tb[0], y, tb[0], min(y + 14, tb[3])), fill=GREEN + (200,), width=5)
            d.line((tb[2], y, tb[2], min(y + 14, tb[3])), fill=GREEN + (200,), width=5)
        fr.layer(lay, 'scan_box', kind='fx')
        bx = min(box[2] + 14, W - 100)
        fr.add(badge('x', 92), bx, (box[1] + box[3]) / 2 - 46, 'x_badge', kind='overlay', blur=6, salpha=0.3)
        tag = pill('压到脸', size=40, bg=RED + (255,), padx=22)
        fr.add(rotate(tag, 3), min(box[2] - 60, W - tag.width - 30), box[1] - 110, 'tag_bad', kind='text', blur=8, salpha=0.3)
        safe = pill('安全区', size=28, fg=GREEN, bg=(255, 255, 255, 235), padx=16)
        fr.add(safe, tb[0] - 6, tb[3] + 10, 'tag_safe', kind='text', shadow=False)
        return fr, ['subtitle_on_mouth', 'scan_box', 'x_badge']
    # b: slid down to the safe band, box turns green
    sb = subtitle_c(fr, runs)
    box = (sb[0] - 16, sb[1] - 16, sb[2] + 16, sb[3] + 16)
    d.rectangle(box, outline=GREEN + (255,), width=4)
    hud_brackets(d, box, GREEN + (255,))
    fr.layer(lay, 'ok_box', kind='fx')
    bx = min(box[2] + 14, W - 100)
    fr.add(badge('ok', 92), bx, (box[1] + box[3]) / 2 - 46, 'ok_badge', kind='overlay', blur=6, salpha=0.3)
    tag = pill('已挪到安全区', size=36, bg=GREEN + (255,), padx=22)
    fr.add(rotate(tag, -2), 40, box[3] + 30, 'tag_ok', kind='text', blur=8, salpha=0.3)
    fc = face_of(f)
    # slide trail on the right, outside the face box
    x = max(fc[2] + 60, 930)
    fr.layer(arrow((x + 20, lips[1] - 10), (x + 30, box[1] - 30), bend=-0.18, lw=7, head=26, color=GREEN), 'slide_arrow', kind='fx')
    return fr, []


# ================================================================== shot 18: split screen
def workbench(w, h):
    """right half: an Agent workbench mid-edit (dark UI, no product names)"""
    im = Image.new('RGBA', (w, h), (30, 31, 34, 255))
    d = ImageDraw.Draw(im)
    # preview monitor
    mx0, my0, mx1, my1 = 28, 120, w - 28, 120 + int((w - 56) * 1.18)
    d.rounded_rectangle((mx0 - 6, my0 - 6, mx1 + 6, my1 + 6), radius=18, fill=(52, 53, 58))
    src_prev = img('vlog_ws')
    prev = cover(src_prev, mx1 - mx0, my1 - my0)
    im.paste(prev, (mx0, my0), rrect_mask(mx1 - mx0, my1 - my0, 12))
    # the weather card inside the real vlog frame is popping: burst next to it
    b = burst(18, 36, n=7, lw=5, color=(255, 255, 255), a0=150, a1=330)
    sc = max((mx1 - mx0) / src_prev.width, (my1 - my0) / src_prev.height)
    crop_y = (src_prev.height * sc - (my1 - my0)) / 2
    im.alpha_composite(b, (int(mx0 + 225 * sc - 62), int(my0 + 970 * sc - crop_y - 70)))
    d.text((mx0, 70), '预览', font=font('Bold', 28), fill=(170, 172, 180), anchor='lm')
    rec = pill('自动剪辑中', size=26, bg=(56, 58, 64, 255), fg=(235, 235, 240), dot=(80, 220, 120), padx=14)
    im.alpha_composite(rec, (w - rec.width - 28, 50))
    # timeline
    ty = my1 + 50
    d.text((mx0, ty), '时间线', font=font('Bold', 28), fill=(170, 172, 180), anchor='lm')
    tracks = [('V', 74), ('FX', 44), ('A', 64)]
    y = ty + 40
    rng = np.random.default_rng(7)
    lanes = {}
    for name, th in tracks:
        d.rounded_rectangle((mx0, y, w - 28, y + th), radius=8, fill=(42, 43, 48))
        d.text((mx0 + 12, y + th / 2), name, font=font('Heavy', 22), fill=(120, 122, 130), anchor='lm')
        lanes[name] = (y, y + th)
        y += th + 12
    x0 = mx0 + 56
    # video clips (thumbnails)
    vy0, vy1 = lanes['V']
    thumbs = [img('vlog_t1'), img('kepu_600'), faceless(12.8), img('vlog_t3'), img('vlog_t4')]
    cx = x0
    for i, k in enumerate(thumbs):
        cw = [96, 70, 110, 64, 120][i]
        if cx + cw > w - 30:
            break
        t = cover(k, cw - 4, vy1 - vy0 - 8)
        im.paste(t, (cx + 2, vy0 + 4), rrect_mask(t.width, t.height, 6))
        cx += cw + 6
    # FX blocks
    fy0, fy1 = lanes['FX']
    for (a, b_, col) in ((0.02, 0.18, (255, 214, 10)), (0.26, 0.36, (120, 180, 255)), (0.44, 0.62, (255, 140, 120)),
                         (0.7, 0.8, (255, 214, 10))):
        ax, bx = x0 + a * (w - 30 - x0), x0 + b_ * (w - 30 - x0)
        d.rounded_rectangle((ax, fy0 + 6, bx, fy1 - 6), radius=6, fill=col)
    # audio waveform
    ay0, ay1 = lanes['A']
    mid = (ay0 + ay1) / 2
    for i, xx in enumerate(range(int(x0), w - 32, 5)):
        amp = (0.25 + 0.75 * abs(math.sin(i * 0.23)) * rng.uniform(0.4, 1.0)) * (ay1 - ay0) * 0.42
        d.line((xx, mid - amp, xx, mid + amp), fill=(110, 200, 150), width=3)
    # cut being made: red line + scissors across V
    cutx = x0 + 96 + 3
    d.line((cutx, vy0 - 16, cutx, vy1 + 16), fill=RED, width=5)
    sc = scissors(46)
    im.alpha_composite(sc, (int(cutx - 23), int(vy0 - 58)))
    # playhead
    px = x0 + 0.47 * (w - 30 - x0)
    d.line((px, ty + 26, px, ay1 + 8), fill=(255, 255, 255), width=3)
    d.polygon([(px - 12, ty + 22), (px + 12, ty + 22), (px, ty + 38)], fill=(255, 255, 255))
    # chips popping over the timeline
    chips = [('+ 转场', (255, 214, 10)), ('+ 音效', (120, 180, 255)), ('+ 贴纸字幕', (255, 140, 120))]
    cy = ay1 + 34
    cxx = mx0
    for t, col in chips:
        c = pill(t, size=26, fg=INK, bg=col + (255,), padx=16)
        if cxx + c.width > w - 20:
            break
        im.alpha_composite(c, (int(cxx), int(cy)))
        cxx += c.width + 12
    return im


def scissors(s=46):
    im = Image.new('RGBA', (s * 2, s * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((s * 0.2, s * 1.1, s * 0.8, s * 1.7), outline=RED, width=7)
    d.ellipse((s * 1.2, s * 1.1, s * 1.8, s * 1.7), outline=RED, width=7)
    d.line((s * 0.7, s * 1.15, s * 1.35, s * 0.1), fill=RED, width=8)
    d.line((s * 1.3, s * 1.15, s * 0.65, s * 0.1), fill=RED, width=8)
    return im.resize((s, s), Image.LANCZOS)


def small_pop_card():
    c = Image.new('RGBA', (230, 92), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((0, 0, 229, 91), radius=14, fill=CARD + (255,))
    c.alpha_composite(icon_sun(58), (14, 17))
    d.text((84, 30), '天气', font=font('Bold', 22), fill=(120, 112, 100), anchor='lm')
    d.text((84, 62), '晴 24°', font=font('Heavy', 32), fill=INK, anchor='lm')
    return rotate(c, -4)


def role_card(head, line, head_bg, bg=CARD, w=460):
    im = Image.new('RGBA', (w, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, 149), radius=20, fill=bg + (255,))
    f1 = font('Heavy', 36)
    hw = f1.getlength(head) + 40
    d.rounded_rectangle((22, 22, 22 + hw, 72), radius=25, fill=head_bg)
    d.text((22 + hw / 2, 47), head, font=f1, fill=(255, 255, 255), anchor='mm')
    f2 = font('Heavy', 56)
    d.text((24, 112), line, font=f2, fill=INK, anchor='lm')
    return im


def shot18():
    f = src_of('18')
    fr = Frame(Image.new('RGBA', (W, H), (0, 0, 0, 255)), name='18')
    half = W // 2
    # left panel: yellow paper, the presenter matted
    left = paper(half, H, tone=(255, 214, 10), seed=18, grain=3, blotch=4)
    fr.img.alpha_composite(left, (0, 0))
    s, fc = 0.70, face_of(f)
    ox = int(half / 2 - (fc[0] + fc[2]) / 2 * s)
    oy = int(330 - fc[1] * s)
    lay, face, lips, top = person_layer(f, s, ox, oy)
    lay = lay.crop((0, 0, half, H))
    fr.img.alpha_composite(lay, (0, 0))
    fr.face, fr.lips = face, lips
    # right panel: workbench
    wb = workbench(half, H)
    fr.img.alpha_composite(wb.crop((0, 0, half, H)), (half, 0))
    # divider
    dl = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(dl).rectangle((half - 4, 0, half + 3, H), fill=(255, 255, 255, 255))
    fr.layer(dl, 'divider', kind='fx')
    # role cards, same height, covering the matte's bottom cut
    L = role_card('你', '创意 + 拍摄', INK, w=478)
    R = role_card('Agent', '剪辑 + 包装', BLUE, bg=(255, 244, 190), w=478)
    fr.add(L, 31, 1136, 'role_you', kind='text', blur=12, salpha=0.35)
    fr.add(R, half + 31, 1136, 'role_agent', kind='text', blur=12, salpha=0.35)
    # hide matte bottom edge under the card: fill the strip under the card with the panel colour
    subtitle_c(fr, [('剪辑和包装', True), ('可以全部', False)])
    return fr, []


SHOTS = {}


# ================================================================== shots 1, 7, 9 (v1 layouts, now with the finished demos)
def speed_lines(fr, x, y, n=5, length=120, gap=22, lw=6, ang=200, color=INK):
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    a = math.radians(ang)
    for i in range(n):
        ox_ = x + i * gap * math.sin(a)
        oy_ = y - i * gap * math.cos(a)
        L = length * (0.6 + 0.4 * ((i * 37) % 5) / 4)
        d.line((ox_, oy_, ox_ + math.cos(a) * L, oy_ + math.sin(a) * L), fill=color + (200,), width=lw)
    fr.layer(lay, f'speed@{x},{y}', kind='fx')


def demo_card_v2(demo, seed, scale=0.64, x=30, y=168, rot=-1.2):
    """finished 9:16 demo as a taped card on the dotted paper page, left of the PiP column"""
    fr = Frame(paper(dots=40, seed=seed))
    w, h = int(W * scale), int(H * scale)
    c = photo(demo.resize((w, h), Image.LANCZOS), border=12, radius=10)
    t = rotate(tape(150, 40, color=(250, 222, 120), seed=seed), -8)
    out = Image.new('RGBA', (c.width + 10, c.height + 30), (0, 0, 0, 0))
    out.alpha_composite(c, (0, 30))
    out.alpha_composite(t, (c.width // 2 - 75, 0))
    fr.add(rotate(out, rot), x, y - 30, 'demo', kind='bg', blur=18, salpha=0.3)
    return fr


def shot01():
    f = src_of('1')
    s_, m = load_src(f), load_matte(f)
    fr = Frame(paper(tone=(243, 238, 228), seed=11), name='1')
    pile = [(img('kepu_600'), -12, (290, 860), True), (img('card01'), 9, (660, 860), False), (faceless(20.0), -6, (215, 1060), True),
            (img('vlog_t3'), -15, (330, 1270), True), (img('card02'), 12, (700, 1250), False)]
    for i, (im_, rot, (cx, cy), tall) in enumerate(pile):
        size = (420, 747) if tall else (560, 747)
        c = rotate(photo(cover(im_, *size), border=12, radius=8), rot)
        fr.add(c, cx, cy, f'pile{i}', kind='bg', anchor='c', blur=10, salpha=0.28)
    top = rotate(photo(img('card03', (620, 827)), border=14, radius=8), -2)
    fr.add(top, 430, 1060, 'pile_top', kind='bg', anchor='c', blur=16, salpha=0.4)
    speed_lines(fr, 70, 700, n=4, length=110, ang=190)
    speed_lines(fr, 80, 1300, n=3, length=90, ang=170)
    add_pip(fr, s_, face_of(f), head_top(m))
    l1 = rotate(label([('不会剪辑', True), ('也能做出', False)], size=64, pad=(26, 16)), 2)
    fr.add(l1, 52, 196, 'hook_line1', kind='text')
    l2 = rotate(label([('这样的视频', True)], size=150, pad=(30, 14), radius=20), -2.5)
    fr.add(l2, 36, 318, 'hook_keyword', kind='text', blur=16, salpha=0.35)
    fr.add(burst(46, 86, n=7, lw=8, a0=-70, a1=50), 850, 330, 'burst', kind='fx', shadow=False)
    return fr, []


def shot07():
    f = src_of('7')
    s_, m = load_src(f), load_matte(f)
    fr = demo_card_v2(img('vlog_7'), 22)
    fr.name = '7'
    fr.add(demo_tag('vlog', False), 752, 196, 'demo_tag', kind='text', shadow=False)
    add_pip(fr, s_, face_of(f), head_top(m))
    subtitle_c(fr, [('时间、天气、', False), ('心情', True)])
    return fr, []


def shot09():
    f = src_of('9')
    s_, m = load_src(f), load_matte(f)
    fr = demo_card_v2(faceless(12.2), 23)
    fr.name = '9'
    fr.add(demo_tag('不露脸', False), 752, 196, 'demo_tag', kind='text', shadow=False)
    # PiP closing like an eyelid: two paper flaps meet at eye level (v1 design)
    content = pip_crop(s_, face_of(f), head_top(m)).convert('RGBA')
    fc, ht = face_of(f), head_top(m)
    eyes = fc[1] + 0.365 * (fc[3] - fc[1])
    eye_y = int((eyes - max(0, ht - 70)) * content.height / 1260)
    slit = 48
    d = ImageDraw.Draw(content)
    top_edge, bot_edge = eye_y - slit // 2, eye_y + slit // 2
    flap = (238, 230, 214, 255)
    d.rectangle((0, 0, content.width, top_edge), fill=flap)
    d.rectangle((0, bot_edge, content.width, content.height), fill=flap)
    for yy in (top_edge, bot_edge):
        d.line((0, yy, content.width, yy), fill=(180, 170, 150, 255), width=3)
    for x in (95, 205):
        d.line((x, top_edge - 70, x, top_edge - 22), fill=INK, width=5)
        d.polygon([(x - 12, top_edge - 34), (x + 12, top_edge - 34), (x, top_edge - 18)], fill=INK)
        d.line((x, bot_edge + 22, x, bot_edge + 70), fill=INK, width=5)
        d.polygon([(x - 12, bot_edge + 34), (x + 12, bot_edge + 34), (x, bot_edge + 18)], fill=INK)
    kl = label([('不露脸', True)], size=40, pad=(14, 6), radius=10, bg=CARD)
    content.alpha_composite(kl, ((content.width - kl.width) // 2, bot_edge + 92))
    fr.add(pip_card(content), PIP_BOX[0], PIP_BOX[1] - 22, 'pip_closing', kind='pip', blur=14, salpha=0.35)
    subtitle_c(fr, [('如果你', False), ('不想露脸', True)])
    return fr, []




# ================================================================== shot 4 (changed, bonus frame): one ticket stub above the head
def ticket_stub(w=620, h=150):
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=14, fill=(250, 244, 228, 255))
    for cy in (0, h):                                   # notches
        d.ellipse((w * 0.32 - 18, cy - 18, w * 0.32 + 18, cy + 18), fill=(0, 0, 0, 0))
    for y in range(18, h - 18, 14):                     # perforation
        d.line((w * 0.32, y, w * 0.32, y + 7), fill=(170, 160, 140, 255), width=3)
    d.text((w * 0.16, h / 2 - 16), 'OPEN', font=font('Heavy', 30), fill=(150, 140, 120), anchor='mm')
    d.text((w * 0.16, h / 2 + 20), 'SOURCE', font=font('Bold', 22), fill=(150, 140, 120), anchor='mm')
    return im


def ink_stamp(text, color, s=150, rot=-10):
    im = Image.new('RGBA', (s * 2, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 6, s * 2 - 7, s - 7), radius=16, outline=color + (235,), width=8)
    d.text((s, s / 2 + 2), text, font=font('Heavy', int(s * 0.52)), fill=color + (235,), anchor='mm')
    rng = np.random.default_rng(len(text) + color[0])
    a = np.array(im.split()[3]).astype(np.float32)
    a *= (rng.random(a.shape) > 0.07) * 0.25 + 0.75
    im.putalpha(Image.fromarray(a.astype(np.uint8)))
    return rotate(im, rot)


def shot04():
    f = src_of('4')
    s = load_src(f)
    fr = Frame(s, face=face_of(f), lips=lips_of(f), name='4')
    t = ticket_stub()
    tx, ty = (W - t.width) // 2, 196
    fr.add(rotate(t, -2), tx, ty, 'ticket', kind='overlay', blur=12, salpha=0.35)
    fr.add(ink_stamp('免费', RED, 104, rot=-8), tx + 215, ty + 20, 'stamp_free', kind='overlay', shadow=False)
    fr.add(ink_stamp('开源', INK, 104, rot=6), tx + 420, ty + 26, 'stamp_open', kind='overlay', shadow=False)
    subtitle_c(fr, [('看看我这个', False), ('免费', True), ('的', False), ('开源', True), ('工具', False)])
    return fr, []




# ================================================================== shot 11 (changed, bonus frame): the closed box tossed to the Agent
def closed_box(s=1.0):
    lay = Image.new('RGBA', (int(360 * s), int(330 * s)), (0, 0, 0, 0))
    Wb, Db, Hb = 230 * s, 120 * s, 150 * s
    P = Obl(12 * s, 320 * s)
    draw_poly(lay, P.poly([(0, 0, Hb), (Wb, 0, Hb), (Wb, Db, Hb), (0, Db, Hb)]), KRAFT_T, width=4)
    draw_poly(lay, P.poly([(Wb, 0, 0), (Wb, Db, 0), (Wb, Db, Hb), (Wb, 0, Hb)]), KRAFT_S, width=4)
    draw_poly(lay, P.poly([(0, 0, 0), (Wb, 0, 0), (Wb, 0, Hb), (0, 0, Hb)]), KRAFT_F, width=4)
    d = ImageDraw.Draw(lay)
    tp = P.poly([(Wb * 0.45, 0, Hb), (Wb * 0.55, 0, Hb), (Wb * 0.55, Db, Hb), (Wb * 0.45, Db, Hb)])
    d.polygon(tp, fill=(250, 222, 120, 230))
    lab = label([('开源工具', False)], size=int(34 * s), pad=(10, 4), radius=6, weight_normal='Heavy')
    fx, fy = P(Wb / 2, 0, Hb * 0.45)
    lay.alpha_composite(lab, (int(fx - lab.width / 2), int(fy - lab.height / 2)))
    return lay


def agent_chip():
    im = Image.new('RGBA', (300, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, 299, 119), radius=26, fill=(24, 24, 26, 240))
    d.ellipse((22, 26, 90, 94), fill=BLUE)
    d.text((56, 60), 'A', font=font('Heavy', 40), fill=(255, 255, 255), anchor='mm')
    d.text((108, 44), '你的 Agent', font=font('Heavy', 34), fill=(255, 255, 255), anchor='lm')
    d.text((108, 86), '接收中…', font=font('Medium', 26), fill=(170, 200, 255), anchor='lm')
    return im


def shot11():
    f = src_of('11')
    s = load_src(f)
    fr = Frame(s, face=face_of(f), lips=lips_of(f), name='11')
    chip = agent_chip()
    fr.add(chip, W - chip.width - 36, 196, 'agent_chip', kind='overlay', blur=12, salpha=0.35)
    box = rotate(closed_box(0.56), 12)
    fr.layer(arrow((930, 1230), (1000, 340), bend=0.10, lw=6, head=26, dash=True, color=(255, 255, 255)), 'toss_path', kind='fx')
    fr.add(box, W - box.width - 6, 350, 'skill_box', kind='overlay', blur=16, salpha=0.35)
    speed_x = W - box.width - 6
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(lay)
    for i in range(3):
        dd.line((speed_x + 60 + i * 40, 640 + i * 14, speed_x + 60 + i * 40, 720 + i * 14), fill=(255, 255, 255, 220), width=6)
    fr.layer(lay, 'speed', kind='fx')
    subtitle_c(fr, [('丢给', True), ('你的agent', False)])
    return fr, []




# ================================================================== shot 15: film strip on a light table
FILM = (30, 26, 22)


def frame_img(name):
    """a storyboard frame of this video: v2 frames from this folder, v1 frames for unchanged shots"""
    if name == 'LIVE':
        return Image.new('RGBA', (W, H), (60, 56, 50, 255))
    p = OUT / f'shot{name}.png'
    if not p.exists():
        p = V1 / f'shot{name}.png'
    return Image.open(p).convert('RGBA')


def film_strip(names, fw=300, gap=30, margin=86, lit=(), current=None, dim=0.42, edge_text='', notes=None):
    fh = int(fw * 16 / 9)
    n = len(names)
    Wf = n * (fw + gap) + gap
    Hf = fh + 2 * margin
    im = Image.new('RGBA', (Wf, Hf), FILM + (255,))
    d = ImageDraw.Draw(im)
    for x in range(14, Wf, 46):                       # sprocket holes
        d.rounded_rectangle((x, 16, x + 26, 16 + 34), radius=6, fill=(236, 228, 210, 255))
        d.rounded_rectangle((x, Hf - 50, x + 26, Hf - 16), radius=6, fill=(236, 228, 210, 255))
    boxes = []
    for i, nm in enumerate(names):
        x = gap + i * (fw + gap)
        fr_ = frame_img(nm).resize((fw, fh), Image.LANCZOS)
        if nm not in lit:
            fr_ = ImageEnhance.Brightness(fr_).enhance(dim)
        im.alpha_composite(fr_, (x, margin))
        if nm == current:
            d.rectangle((x - 7, margin - 7, x + fw + 6, margin + fh + 6), outline=YELLOW, width=8)
        boxes.append((x, margin, x + fw, margin + fh))
        tag = (notes or {}).get(nm)
        if tag:
            d.text((x + 6, margin - 8), tag, font=font('Bold', 22), fill=(255, 196, 120), anchor='ls')
    if edge_text:
        ex_ = edge_text[1] if isinstance(edge_text, tuple) else gap
        d.text((ex_, Hf - 58), edge_text[0] if isinstance(edge_text, tuple) else edge_text, font=font('Bold', 20),
               fill=(255, 176, 90), anchor='ls')
    return im, boxes, (Wf, Hf, fw, fh, margin)


def shot15():
    bg = Image.new('RGBA', (W, H), (36, 33, 30, 255))
    g = glow((900, 700), color=(255, 236, 200), alpha=120)
    bg.alpha_composite(g, (W // 2 - 900, 880 - 700))
    fr = Frame(bg, name='15')
    # blurred strips above / below (the rest of the storyboard), dimmed
    for names, cy, rot in ((['1', 'I1', 'I2', 'I3', '03'], 300, -4), (['16a', '16b', '18', '20', '12'], 1560, -4)):
        st, _, _ = film_strip(names, fw=200, gap=22, margin=58, dim=0.55)
        st = rotate(st.filter(ImageFilter.GaussianBlur(3)), rot)
        st = ImageEnhance.Brightness(st).enhance(0.8)
        fr.img.alpha_composite(st, (int(W / 2 - st.width / 2 - 60), int(cy - st.height / 2)))
    # main strip: 13a 13b (lit) | LIVE gate = the presenter's real footage (current, enlarged) | 14a 14b (next, unlit)
    names = ['13a', '13b', 'LIVE', '14a', '14b']
    st, boxes, (Wf, Hf, fw, fh, mg) = film_strip(names, fw=300, gap=60, margin=86, lit=('13a', '13b'), current=None,
                                                edge_text=('STEP 3 分镜脚本  ·  镜 13 → 现在 → 镜 14', 30),
                                                notes={'13a': '镜 13', '13b': '镜 13', '14a': '镜 14 · 选风格', '14b': '镜 14 · 刷风格'})
    d = ImageDraw.Draw(st)
    bL, b14a = boxes[2], boxes[3]
    # sound: waveform in the soundtrack lane under the next frame (14a) + a tag
    lane_y = mg + fh + 2
    rng = np.random.default_rng(15)
    for i, x in enumerate(range(b14a[0] + 10, b14a[2] + 10, 8)):
        a = (0.3 + 0.7 * abs(math.sin(i * 0.4)) * rng.uniform(0.5, 1)) * 16
        d.line((x, lane_y + 18 - a, x, lane_y + 18 + a), fill=(120, 220, 170), width=4)
    sw = pill('音效', size=30, fg=INK, bg=(120, 220, 170, 255), padx=16)
    st.alpha_composite(sw, (int(b14a[0] + fw / 2 - sw.width / 2), int(mg + fh - sw.height - 16)))
    # centre the LIVE gate on screen, strip tilted a little
    cx_frame = (bL[0] + bL[2]) / 2
    rot = -4
    P0 = 260
    big = Image.new('RGBA', (Wf + 2 * P0, Hf + 2 * P0), (0, 0, 0, 0))
    big.alpha_composite(st, (P0, P0))
    # the gate: the presenter's real footage of this very moment, bigger than the strip frames (>= the PiP width)
    live = load_src(src_of('15'))
    gw, gh = 404, 718
    gate = Image.new('RGBA', (gw + 24, gh + 24), (0, 0, 0, 0))
    ImageDraw.Draw(gate).rounded_rectangle((0, 0, gw + 23, gh + 23), radius=14, fill=YELLOW + (255,))
    gate.paste(live.resize((gw, gh), Image.LANCZOS), (12, 12), rrect_mask(gw, gh, 8))
    rec = pill('实拍 · 正在说', size=26, bg=(20, 20, 20, 225), dot=RED, padx=14)
    gate.alpha_composite(rec, (26, 26))
    gsh, gpad = shadow_of(gate, blur=16, alpha=0.55)
    gx, gy = int(P0 + cx_frame - gate.width / 2), int(P0 + mg + fh / 2 - gate.height / 2)
    big.alpha_composite(gsh, (gx - gpad + 6, gy - gpad + 14))
    big.alpha_composite(gate, (gx, gy))
    # transition arrow from the gate to the next frame (arcs over the gap)
    dd = ImageDraw.Draw(big)
    ax0, ax1, ay = gx + gate.width - 60, P0 + b14a[0] + 110, P0 + mg + 150
    pts = [((1 - t) ** 2 * ax0 + 2 * (1 - t) * t * (ax0 + ax1) / 2 + t ** 2 * ax1,
            (1 - t) ** 2 * ay + 2 * (1 - t) * t * (ay - 130) + t ** 2 * ay) for t in np.linspace(0, 1, 40)]
    dd.line(pts, fill=YELLOW, width=12, joint='curve')
    ex, ey = pts[-1]
    px_, py_ = pts[-4]
    ang = math.atan2(ey - py_, ex - px_)
    for sg in (-1, 1):
        a = ang + math.pi - sg * 0.5
        dd.line((ex, ey, ex + math.cos(a) * 40, ey + math.sin(a) * 40), fill=YELLOW, width=12)
    tt = pill('转场', size=32, fg=INK, bg=YELLOW + (255,), padx=18)
    big.alpha_composite(tt, (int(ax1 - 10), int(ay - 150)))
    big = big.rotate(rot, resample=Image.BICUBIC, center=(P0 + cx_frame, P0 + Hf / 2))
    ox, oy = int(W / 2 - (P0 + cx_frame)), int(870 - (P0 + Hf / 2))
    sh = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sh.alpha_composite(big.crop((max(0, -ox), max(0, -oy), max(0, -ox) + W, max(0, -oy) + H)), (max(0, ox), max(0, oy)))
    shadow = sh.split()[3].filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.5))
    sl = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sl.putalpha(shadow)
    fr.img.alpha_composite(sl, (8, 20))
    fr.img.alpha_composite(sh)
    a = np.array(sh.split()[3])
    ys_, xs_ = np.where(a > 40)
    fr.items.append(('main_strip', (int(xs_.min()), int(ys_.min()), int(xs_.max()), int(ys_.max())), 'bg'))
    # live face / lips boxes in screen space (gate scale, then the strip rotation about the gate centre)
    lf = face_of(src_of('15'))
    ll = lips_of(src_of('15'))
    g_s = gw / W
    cxs, cys = P0 + cx_frame, P0 + Hf / 2

    def to_screen(bx):
        pts = []
        for (x_, y_) in ((bx[0], bx[1]), (bx[2], bx[1]), (bx[0], bx[3]), (bx[2], bx[3])):
            X, Y = gx + 12 + x_ * g_s, gy + 12 + y_ * g_s
            th = math.radians(rot)
            dx, dy = X - cxs, Y - cys
            Xr = cxs + dx * math.cos(th) + dy * math.sin(th)
            Yr = cys - dx * math.sin(th) + dy * math.cos(th)
            pts.append((Xr + ox, Yr + oy))
        return (int(min(p_[0] for p_ in pts)), int(min(p_[1] for p_ in pts)), int(max(p_[0] for p_ in pts)), int(max(p_[1] for p_ in pts)))
    fr.face, fr.lips = to_screen(lf), to_screen(ll)
    step_bar(fr, active=3, done=(1, 2))
    subtitle_c(fr, [('怎么转场、', False), ('配什么音效', True)])
    return fr, []




# ================================================================== shot 10: one paper box -> three-tray toolbox
KRAFT_F, KRAFT_S, KRAFT_T, KRAFT_IN = (214, 178, 124), (186, 148, 96), (232, 204, 158), (120, 88, 50)


class Obl:
    """oblique (cabinet) projection: x right, y depth (away), z up; front faces stay undistorted"""

    def __init__(self, ox, oy, kx=0.42, ky=0.36):
        self.ox, self.oy, self.kx, self.ky = ox, oy, kx, ky

    def __call__(self, x, y, z):
        return (self.ox + x + y * self.kx, self.oy - z - y * self.ky)

    def poly(self, pts):
        return [self(*p) for p in pts]


def draw_poly(lay, pts, fill, outline=INK, width=5):
    d = ImageDraw.Draw(lay)
    d.polygon(pts, fill=fill)
    if outline:
        d.line(pts + [pts[0]], fill=outline, width=width, joint='curve')


def upright(im, P, x, y, z, w):
    """paste an image standing upright in the x-z plane at depth y (front-parallel -> undistorted)"""
    h = int(im.height * w / im.width)
    r = im.resize((int(w), h), Image.LANCZOS)
    sx, sy = P(x, y, z)
    return r, (int(sx), int(sy - h))


def thumb(key_or_img, w, h):
    im = key_or_img if isinstance(key_or_img, Image.Image) else img(key_or_img)
    return photo(cover(im.convert('RGBA'), w, h), border=8, radius=8)


def shot10a():
    fr = Frame(paper(tone=(243, 238, 228), dots=40, seed=101), name='10a')
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    Wb, Db, Hb, L = 640, 360, 330, 230
    P = Obl(150, 1262)
    c60, s60 = 0.5, 0.866
    # back + left + right flaps (behind), then interior
    draw_poly(lay, P.poly([(0, Db, Hb), (Wb, Db, Hb), (Wb, Db + L * c60, Hb + L * s60), (0, Db + L * c60, Hb + L * s60)]), KRAFT_T)
    draw_poly(lay, P.poly([(0, 0, Hb), (0, Db, Hb), (-L * c60, Db, Hb + L * s60), (-L * c60, 0, Hb + L * s60)]), KRAFT_S)
    draw_poly(lay, P.poly([(0, 0, Hb), (Wb, 0, Hb), (Wb, Db, Hb), (0, Db, Hb)]), KRAFT_IN)
    # inner back wall (lit a bit)
    draw_poly(lay, P.poly([(0, Db, Hb), (Wb, Db, Hb), (Wb, Db, Hb - 150), (0, Db, Hb - 150)]), (150, 114, 70), outline=None)
    fr.img.alpha_composite(lay)
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    # three demo frames flying in (one already half inside)
    minis = [(img('vlog_10a'), 'vlog', -18, (190, 470)), (img('kepu_36'), '科普', 6, (470, 330)),
             (faceless(21.8), '不露脸', 16, (735, 480))]
    for k, (im, name, rot, (cx, cy)) in enumerate(minis):
        t = thumb(im, 190, 338)
        tagp = pill(name, size=26, bg=INK + (255,), padx=14)
        t2 = Image.new('RGBA', (t.width, t.height + 30), (0, 0, 0, 0))
        t2.alpha_composite(t, (0, 30))
        t2.alpha_composite(tagp, ((t.width - tagp.width) // 2, 0))
        t2 = rotate(t2, rot)
        tgt = P(Wb * (0.25 + 0.25 * k), Db * 0.5, Hb)
        fr.layer(arrow((cx, cy + t2.height // 2), (tgt[0], tgt[1] - 20), bend=0.18 * (1 if k != 1 else -1), lw=5, head=22,
                       dash=True, color=GREY), f'trail{k}', kind='fx')
        fr.add(t2, cx - t2.width // 2, cy, f'mini{k}', kind='overlay', blur=14, salpha=0.3)
    # right side + front face + front flap (in front of everything)
    draw_poly(lay, P.poly([(Wb, 0, 0), (Wb, Db, 0), (Wb, Db, Hb), (Wb, 0, Hb)]), KRAFT_S)
    draw_poly(lay, P.poly([(Wb + L * c60, 0, Hb + L * s60), (Wb, 0, Hb), (Wb, Db, Hb), (Wb + L * c60, Db, Hb + L * s60)]), KRAFT_T)
    draw_poly(lay, P.poly([(0, 0, 0), (Wb, 0, 0), (Wb, 0, Hb), (0, 0, Hb)]), KRAFT_F)
    draw_poly(lay, P.poly([(0, 0, Hb), (Wb, 0, Hb), (Wb, -L * c60 * 0.55, Hb - L * s60 * 0.55), (0, -L * c60 * 0.55, Hb - L * s60 * 0.55)]),
              KRAFT_T)
    fr.img.alpha_composite(lay)
    fr.items.append(('box', (int(P(0, 0, 0)[0]), int(P(Wb + L, Db, Hb + L)[1]), int(P(Wb + L, Db, 0)[0]), int(P(0, 0, 0)[1])), 'bg'))
    lab = label([('开源工具', False)], size=64, pad=(26, 10), radius=10, weight_normal='Heavy')
    fx, fy = P(Wb / 2, 0, Hb * 0.36)
    fr.add(rotate(lab, -2), fx - lab.width / 2, fy - lab.height / 2, 'box_label', kind='text', blur=6, salpha=0.25)
    fr.add(burst(60, 110, n=9, lw=7, a0=200, a1=340), 330, 180, 'burst', kind='fx', shadow=False)
    subtitle_c(fr, [('这些其实都是', False), ('同一套东西', True)])
    return fr, []


def motion_mini(key, w=120, h=160):
    c = thumb(key, w, h)
    out = Image.new('RGBA', (c.width + 40, c.height), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    for i in range(3):
        d.line((0, 30 + i * 36, 30, 30 + i * 36), fill=INK, width=5)
    out.alpha_composite(c, (40, 0))
    return out


def speaker_panel(w=200, h=190):
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=18, fill=(30, 31, 34, 255))
    rng = np.random.default_rng(4)
    for i, x in enumerate(range(18, w - 16, 12)):
        a = (0.2 + 0.8 * abs(math.sin(i * 0.55)) * rng.uniform(0.5, 1)) * (h * 0.36)
        d.line((x, h / 2 - a, x, h / 2 + a), fill=YELLOW, width=6)
    return im


def speaker_icon(s=150):
    im = Image.new('RGBA', (s * 2, s * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(s * 0.25, s * 0.75), (s * 0.7, s * 0.75), (s * 1.2, s * 0.3), (s * 1.2, s * 1.7), (s * 0.7, s * 1.25), (s * 0.25, s * 1.25)],
              fill=(255, 255, 255), outline=INK, width=14)
    for r in (0.45, 0.75):
        d.arc((s * 1.2 - s * r, s - s * r, s * 1.2 + s * r, s + s * r), -50, 50, fill=INK, width=16)
    return im.resize((s, s), Image.LANCZOS)


def glow(size, color=(255, 214, 10), alpha=150):
    w, h = size
    a = Image.new('L', (w * 2, h * 2), 0)
    ImageDraw.Draw(a).ellipse((w / 2, h / 2, w * 1.5, h * 1.5), fill=alpha)
    a = a.filter(ImageFilter.GaussianBlur(min(size) / 4))
    g = Image.new('RGBA', (w * 2, h * 2), color + (0,))
    g.putalpha(a)
    return g


def shot10b():
    fr = Frame(paper(tone=(243, 238, 228), dots=40, seed=102), name='10b')
    Wb, Db, Hb = 810, 330, 300
    P = Obl(70, 1262)
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    # lid flipped back like a toolbox lid
    draw_poly(lay, P.poly([(0, Db, Hb), (Wb, Db, Hb), (Wb, Db + 110, Hb + 300), (0, Db + 110, Hb + 300)]), KRAFT_T)
    draw_poly(lay, P.poly([(0, 0, Hb), (Wb, 0, Hb), (Wb, Db, Hb), (0, Db, Hb)]), KRAFT_IN)
    fr.img.alpha_composite(lay)
    trays = [('动效库', 0), ('音效库', 1), ('风格包', 2)]
    tw = Wb / 3
    # each tray lit (end state): warm light filling the opening + a soft beam rising out of it
    beams = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(beams)
    for name, i in trays:
        x0, x1 = tw * i + 10, tw * (i + 1) - 10
        bd.polygon(P.poly([(x0, 4, Hb), (x1, 4, Hb), (x1, Db - 4, Hb), (x0, Db - 4, Hb)]), fill=(255, 226, 90, 255))
    fr.img.alpha_composite(beams.filter(ImageFilter.GaussianBlur(6)))
    for name, i in trays:
        gx, gy = P(tw * (i + 0.5), Db * 0.5, Hb + 60)
        fr.img.alpha_composite(glow((260, 200), alpha=170), (int(gx - 260), int(gy - 200)))
    # contents standing in each tray
    items = []
    for j, k in enumerate(['card01', 'card02', 'card06']):
        r, pos = upright(rotate(motion_mini(k), [-12, 2, 13][j]), P, -20 + j * 64, Db * (0.8 - j * 0.25), Hb + 110, 176)
        items.append((r, pos, f'motion{j}'))
    wv, pos = upright(speaker_panel(), P, tw + 46, Db * 0.4, Hb + 150, 170)
    items.append((wv, pos, 'wave'))
    sp, pos = upright(speaker_icon(150), P, tw + 150, Db * 0.2, Hb + 40, 118)
    items.append((sp, pos, 'speaker'))
    for j, k in enumerate(['vlog_open', 'film_open', 'mag_A']):
        r, pos = upright(rotate(thumb(k, 120, 160), [-12, 0, 11][j]), P, 2 * tw - 4 + j * 66, Db * (0.8 - j * 0.25), Hb + 110, 158)
        items.append((r, pos, f'style{j}'))
    for r, (x, y), n in items:
        fr.add(r, x, y, n, kind='bg', blur=8, salpha=0.3)
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    # tray dividers + front / side faces
    for i in (1, 2):
        draw_poly(lay, P.poly([(tw * i, 0, Hb), (tw * i, Db, Hb), (tw * i, Db, Hb - 8), (tw * i, 0, Hb - 8)]), KRAFT_S, width=4)
    draw_poly(lay, P.poly([(Wb, 0, 0), (Wb, Db, 0), (Wb, Db, Hb), (Wb, 0, Hb)]), KRAFT_S)
    draw_poly(lay, P.poly([(0, 0, 0), (Wb, 0, 0), (Wb, 0, Hb), (0, 0, Hb)]), KRAFT_F)
    d = ImageDraw.Draw(lay)
    for i in (1, 2):
        a, b = P(tw * i, 0, 0), P(tw * i, 0, Hb)
        d.line((a, b), fill=INK, width=4)
    fr.img.alpha_composite(lay)
    for name, i in trays:
        lab = label([(name, True)], size=66, pad=(22, 10), radius=10, weight_key='Heavy')
        fx, fy = P(tw * (i + 0.5), 0, Hb * 0.5)
        fr.add(lab, fx - lab.width / 2, fy - lab.height / 2, f'tray_{name}', kind='text', blur=6, salpha=0.25)
    plus = [P(tw, 0, Hb * 0.5), P(2 * tw, 0, Hb * 0.5)]
    subtitle_c(fr, [('动效库加音效库加', False), ('风格包', True)])
    return fr, []




# ================================================================== shot 14b: the chosen style brushes over the presenter
def cutout_letters(text, size=92, seed=5):
    """ransom-note letters, each on its own paper scrap (vertical stack)"""
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
    h = sum(t.height - 14 for t in tiles) + 14
    w = max(t.width for t in tiles) + 20
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    y = 0
    for i, t in enumerate(tiles):
        sh, pad = shadow_of(t, blur=5, alpha=0.35)
        x = int((w - t.width) / 2 + (8 if i % 2 else -8))
        out.alpha_composite(sh.crop((pad, pad, pad + t.width, pad + t.height)), (x + 3, y + 5))
        out.alpha_composite(t, (x, y))
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


def brush_mask(x_top, x_bot, seed=9, band=70):
    """after-region = left of a slanted line; the edge is a dry-brush edge (horizontal bristle streaks)"""
    rng = np.random.default_rng(seed)
    ys = np.arange(H)
    base = x_top + (x_bot - x_top) * ys / H
    # bristle streaks: piecewise-constant offsets in bands of 3..9 px, plus a slow wobble
    off = np.zeros(H)
    y = 0
    while y < H:
        L = int(rng.integers(3, 10))
        off[y:y + L] = rng.gamma(1.6, band / 3.2)
        y += L
    wob = cv2.GaussianBlur(rng.normal(0, 1, (H, 1)).astype(np.float32), (1, 0), 40).ravel() * 60
    edge = base + off + wob
    xs = np.arange(W)[None, :]
    m = (xs < edge[:, None]).astype(np.float32)
    # dry streaks beyond the edge: faint paint drag
    drag = np.zeros((H, W), np.float32)
    y = 0
    while y < H:
        L = int(rng.integers(2, 6))
        ln = rng.gamma(1.4, 45)
        a = rng.uniform(0.25, 0.8)
        e0 = int(edge[min(y, H - 1)])
        drag[y:y + L, e0:min(W, int(e0 + ln))] = a
        y += L + int(rng.integers(0, 6))
    m = np.maximum(m, drag)
    return Image.fromarray((m * 255).astype(np.uint8)), edge


def collage_version(src, face):
    """the same frame 'packaged' in the collage style: warm grade + grain, printed on paper with a white border,
    washi tape, date card, cut-out letters, stickers (all kept off the face)"""
    arr = np.array(src.convert('RGB')).astype(np.float32)
    grey = arr.mean(2, keepdims=True)
    arr = grey + (arr - grey) * 0.8                          # a little less saturated
    arr = arr * np.array([1.10, 1.0, 0.80]) + np.array([14, 8, -2])   # warm
    arr = 22 + arr * 0.90                                   # faded blacks, printed look
    tex = np.array(paper(tone=(255, 250, 238), seed=77, grain=9, blotch=12).convert('RGB')).astype(np.float32) / 255
    arr = arr * (0.82 + 0.18 * tex)                          # paper texture multiply
    rng = np.random.default_rng(3)
    arr += rng.normal(0, 6, arr.shape[:2])[..., None]
    graded = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert('RGBA')
    page = paper(tone=(240, 232, 214), dots=40, seed=41)
    m = 34
    photo_ = photo(graded.crop((m + 14, m + 14, W - m - 14, H - m - 14)), border=14, radius=4)
    page.alpha_composite(photo_, (m, m))
    fr = Frame(page)
    fr.add(rotate(tape(190, 46, color=(245, 170, 190), seed=61, stripes=True), -32), -10, 150, 'tape1', kind='fx', shadow=False)
    fr.add(rotate(tape(170, 44, color=(170, 205, 245), seed=62), 28), -20, 1160, 'tape2', kind='fx', shadow=False)
    fr.add(date_card(), 56, 372, 'date_card', kind='overlay', blur=8, salpha=0.3)
    fr.add(cutout_letters('开源剪辑', size=78), 36, 540, 'cutout', kind='overlay', blur=8, salpha=0.3)
    fr.add(rotate(icon_heart(88), -10), 52, 1086, 'heart', kind='overlay', blur=6, salpha=0.3)
    fr.add(rotate(icon_star(72), 12), 140, 1120, 'star', kind='overlay', blur=6, salpha=0.3)
    return fr


def shot14b():
    """the brush comes DOWN the frame: above the edge = collage-packaged, below = raw (edge kept under the chin)"""
    f = src_of('14b')
    src = load_src(f)
    fc = face_of(f)
    col = collage_version(src, fc)
    # horizontal dry-brush edge: build it on the transposed canvas with brush_mask, then transpose back
    y_left, y_right = 1236, 1262
    rng = np.random.default_rng(9)
    xs = np.arange(W)
    base_edge = y_left + (y_right - y_left) * xs / W
    off = np.zeros(W)
    x = 0
    while x < W:
        L = int(rng.integers(3, 10))
        off[x:x + L] = rng.gamma(1.6, 12)
        x += L
    edge = base_edge + off
    ys = np.arange(H)[:, None]
    m = (ys < edge[None, :]).astype(np.float32)
    mask = Image.fromarray((m * 255).astype(np.uint8))
    base = src.copy()
    base.paste(col.img, (0, 0), mask)
    band = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    x = 0
    while x < W:
        L = int(rng.integers(2, 7))
        e = edge[min(x, W - 1)]
        y0 = e - rng.uniform(18, 38)
        y1 = e + rng.gamma(1.5, 9)
        colr = (250, 244, 228) if rng.random() > 0.2 else (255, 214, 10)
        bd.rectangle((x, y0, x + L - 1, y1), fill=colr + (int(rng.uniform(150, 235)),))
        x += L
    band = band.filter(ImageFilter.GaussianBlur(0.8))
    shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for xx in range(0, W, 3):
        e = edge[xx]
        sd.line((xx, e + 4, xx, e + 14), fill=(30, 20, 10, 55), width=3)
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(4)))
    base.alpha_composite(band)
    fr = Frame(base, face=fc, lips=lips_of(f), name='14b')
    fr.items = [it for it in col.items]
    fr.items.append(('brush_band', (0, int(edge.min() - 38), W, int(edge.max() + 30)), 'fx'))
    step_bar(fr, active=2, done=(1,))
    fr.add(pill('拼贴包装', size=34, bg=INK + (255,), padx=22, dot=YELLOW), 40, 282, 'tag_after', kind='text', shadow=False)
    # the style chip riding the brush at the right end of the edge (off the face)
    chip = rotate(photo(img('vlog_open', (104, 139)), border=6, radius=6), -8)
    fr.add(chip, W - chip.width - 26, int(edge[-60] - chip.height + 10), 'brush_chip', kind='overlay', blur=8, salpha=0.35)
    before = pill('原样', size=34, fg=INK, bg=(255, 255, 255, 235), padx=22)
    fr.add(before, W - before.width - 34, 1330, 'tag_before', kind='text', shadow=False)
    subtitle_c(fr, [('以这个', False), ('风格为标准', True)])
    return fr, []




# ================================================================== perspective helpers
def _coeffs(pa, pb):
    """PIL PERSPECTIVE coeffs mapping output points pa -> input points pb"""
    A = []
    for (x, y), (u, v) in zip(pa, pb):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    return np.linalg.solve(np.array(A, float), np.array(pb, float).reshape(8))


class Plane:
    """texture rect (tw x th) <-> screen quad [tl, tr, br, bl]"""

    def __init__(self, tw, th, quad):
        self.tw, self.th, self.quad = tw, th, quad
        rect = [(0, 0), (tw, 0), (tw, th), (0, th)]
        self.inv = _coeffs(quad, rect)      # screen -> texture (for PIL)
        self.fwd = _coeffs(rect, quad)      # texture -> screen

    def pt(self, x, y):
        a, b, c, d, e, f, g, h = self.fwd
        den = g * x + h * y + 1
        return ((a * x + b * y + c) / den, (d * x + e * y + f) / den)

    def inv_pt(self, x, y):
        a, b, c, d, e, f, g, h = self.inv
        den = g * x + h * y + 1
        return ((a * x + b * y + c) / den, (d * x + e * y + f) / den)

    def warp(self, tex):
        return tex.transform((W, H), Image.PERSPECTIVE, tuple(self.inv), Image.BICUBIC)


def style_card_img(key, name, w=300, h=400, label_size=60, key_on=False):
    c = photo(img(key, (w, h)), border=12, radius=8)
    lab = label([(name, key_on)], size=label_size, pad=(18, 6), radius=10, weight_normal='Heavy')
    c.alpha_composite(lab, ((c.width - lab.width) // 2, c.height - lab.height - 16))
    return c


# ================================================================== shot 14a: cards dealt on a cutting mat, the presenter behind the table
MAT = (36, 92, 70)


def cutting_mat(tw, th):
    tex = Image.new('RGBA', (tw, th), MAT + (255,))
    rng = np.random.default_rng(14)
    arr = np.array(tex).astype(np.float32)
    arr[..., :3] += rng.normal(0, 3.0, (th, tw, 1))
    tex = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(tex)
    for x in range(0, tw, 40):
        d.line((x, 0, x, th), fill=(74, 132, 106, 255), width=5 if x % 200 == 0 else 2)
    for y in range(0, th, 40):
        d.line((0, y, tw, y), fill=(74, 132, 106, 255), width=5 if y % 200 == 0 else 2)
    for k in range(-th, tw, 400):
        d.line((k, 0, k + th, th), fill=(64, 118, 94, 255), width=2)
    for x in range(0, tw, 20):
        d.line((x, 0, x, 18 if x % 100 else 34), fill=(210, 230, 215, 255), width=3)
    return tex


def shot14a():
    f = src_of('14a')
    src = load_src(f)
    bg = src.filter(ImageFilter.GaussianBlur(16))
    bg = ImageEnhance.Brightness(bg).enhance(0.86)
    fr = Frame(bg, name='14a')
    s = 0.62
    fc = face_of(f)
    ox = int(480 - (fc[0] + fc[2]) / 2 * s)
    oy = int(300 - fc[1] * s)
    lay, face, lips, top = person_layer(f, s, ox, oy)
    fr.img.alpha_composite(lay)
    fr.face, fr.lips = face, lips
    # table (cutting mat) in perspective
    TW, TH = 1800, 1400
    plane = Plane(TW, TH, [(-120, 800), (1200, 800), (2100, 1920), (-1020, 1920)])
    tex = cutting_mat(TW, TH)
    # dealt cards lying on the mat (texture coords); the chosen slot on the right is empty
    # slot centres chosen in SCREEN space (x at the card's top edge, y = 860), mapped back onto the mat
    def slot_tex(sx_, sy_=880):
        return plane.inv_pt(sx_, sy_)
    slots = [('film_open', '胶片', 176, -5), ('mag_A', '杂志', 428, 3), ('launch_A', '发布会', 680, -3)]
    for k, name, scx, rot in slots:
        tx, ty = slot_tex(scx)
        c = rotate(style_card_img(k, name, 276, 368, label_size=70), rot)
        sh, pad = shadow_of(c, blur=10, alpha=0.45)
        tex.alpha_composite(sh, (int(tx - c.width / 2 - pad + 6), int(ty - pad + 10)))
        tex.alpha_composite(c, (int(tx - c.width / 2), int(ty)))
    # empty slot of the chosen card: dashed outline
    d = ImageDraw.Draw(tex)
    etx, ety = slot_tex(928)
    ex0, ey0, ex1, ey1 = int(etx - 150), int(ety), int(etx + 150), int(ety + 392)
    for x in range(ex0, ex1, 36):
        d.line((x, ey0, min(x + 20, ex1), ey0), fill=(230, 240, 230, 255), width=6)
        d.line((x, ey1, min(x + 20, ex1), ey1), fill=(230, 240, 230, 255), width=6)
    for y in range(ey0, ey1, 36):
        d.line((ex0, y, ex0, min(y + 20, ey1)), fill=(230, 240, 230, 255), width=6)
        d.line((ex1, y, ex1, min(y + 20, ey1)), fill=(230, 240, 230, 255), width=6)
    table = plane.warp(tex)
    # table edge highlight + soft shadow on the wall behind
    shade = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle((0, 770, W, 800), fill=(0, 0, 0, 60))
    shade = shade.filter(ImageFilter.GaussianBlur(10))
    fr.img.alpha_composite(shade)
    fr.img.alpha_composite(table)
    edge = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(edge).line((0, 801, W, 801), fill=(120, 170, 145, 255), width=4)
    fr.img.alpha_composite(edge)
    fr.items.append(('table', (0, 800, W, H), 'bg'))
    step_bar(fr, active=2, done=(1,))
    fr.add(pill('STEP 2 画面风格', size=30, bg=(20, 20, 20, 225)), 40, 1206, 'step_chip', kind='text', shadow=False)
    # chosen card: flipped up from the empty slot, enlarged, standing beside the presenter, checked
    sel = style_card_img('vlog_open', '拼贴', 282, 376, label_size=52, key_on=True)
    ring = Image.new('RGBA', (sel.width + 30, sel.height + 30), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle((3, 3, ring.width - 4, ring.height - 4), radius=22, outline=YELLOW + (255,), width=12)
    ring.alpha_composite(sel, (15, 15))
    ring = rotate(ring, 5)
    sx, sy = W - ring.width - 14, 420
    # flip path from the slot to the card (dashed arc)
    slot_c = plane.pt((ex0 + ex1) / 2, ey0)
    fr.layer(arrow((slot_c[0] - 30, slot_c[1] - 8), (sx + 40, sy + ring.height - 30), bend=0.3, lw=6, head=24, dash=True,
                   color=(255, 255, 255)), 'flip_path', kind='fx')
    fr.add(ring, sx, sy, 'style_selected', kind='overlay', blur=24, salpha=0.45)
    ck = badge('ok', 104)
    fr.add(ck, sx - 40, sy + ring.height - 120, 'check', kind='overlay', blur=8, salpha=0.3)
    fr.items = [it for it in fr.items if it[0] != 'table']
    subtitle_c(fr, [('挑一个', True), ('你喜欢的风格', False)])
    return fr, []




# ================================================================== shot 13: chat on the 03 input-box paper
CHAT_PAPER = (244, 240, 232)


def chat_bubble(text, who, size=36, attach=None, maxw=700):
    f = font('Bold', size)
    tw = f.getlength(text)
    padx, pady = 28, 16
    h = int(size * 1.25 + 2 * pady)
    w = int(tw + 2 * padx)
    ah = 0
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
    if attach:
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


def chat_input(text='', compose='', placeholder='继续补充…', w=660, h=118):
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(252, 251, 248, 250), outline=(0, 0, 0, 34), width=2)
    f = font('Bold', 40)
    x = 40
    if text or compose:
        d.text((x, h / 2), text, font=f, fill=INK, anchor='lm')
        x += f.getlength(text)
        if compose:
            fc = font('Medium', 38)
            cw = fc.getlength(compose)
            d.text((x + 2, h / 2), compose, font=fc, fill=(120, 116, 110), anchor='lm')
            d.line((x + 2, h / 2 + 26, x + 2 + cw, h / 2 + 26), fill=(120, 116, 110), width=2)
            x += cw + 4
        d.line((x + 4, h / 2 - 26, x + 4, h / 2 + 26), fill=BLUE, width=4)
    else:
        d.text((x, h / 2), placeholder, font=font('Medium', 36), fill=(170, 166, 160), anchor='lm')
    bx = w - 18 - 84
    on = bool(text or compose)
    d.ellipse((bx, h / 2 - 42, bx + 84, h / 2 + 42), fill=BLUE if on else (200, 205, 214))
    d.line((bx + 42, h / 2 + 20, bx + 42, h / 2 - 20), fill=(255, 255, 255), width=6)
    d.line((bx + 26, h / 2 - 4, bx + 42, h / 2 - 20, bx + 58, h / 2 - 4), fill=(255, 255, 255), width=6)
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


def chat_header():
    f1, f2 = font('Heavy', 26), font('Heavy', 44)
    pw = f1.getlength('STEP 1') + 30
    tw = f2.getlength('确认选题')
    w, h = int(pw + tw + 40), 60
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 8, pw, 52), radius=22, fill=INK)
    d.text((pw / 2, 30), 'STEP 1', font=f1, fill=(255, 255, 255), anchor='mm')
    d.rectangle((pw + 16, 32, pw + 20 + tw, 52), fill=YELLOW)
    d.text((pw + 18, 30), '确认选题', font=f2, fill=INK, anchor='lm')
    return im


CHAT = [('做一条开源工具的介绍视频', 'you', [('video', '口播素材 4:35'), ('doc', '文案')]),
        ('开头先放成片？', 'agent', None),
        ('vlog、科普、不露脸各放一段', 'you', None),
        ('文案改好了，确认吗？', 'agent', None),
        ('确认', 'you', None)]


def shot13(which):
    key = '13a' if which == 'a' else '13b'
    f = src_of(key)
    s, m = load_src(f), load_matte(f)
    fr = Frame(paper(tone=CHAT_PAPER, dots=34, seed=13, grain=3.5, blotch=4), name=key)
    step_bar(fr, active=1)
    fr.add(chat_header(), 40, 300, 'chat_header', kind='text', shadow=False)
    n = 2 if which == 'a' else 5
    y = 296
    for i, (t, who, att) in enumerate(CHAT[:n]):
        b = chat_bubble(t, who, attach=att)
        x = W - 40 - b.width if who == 'you' else 40
        fr.add(b, x, y, f'msg{i + 1}', kind='overlay', blur=10, salpha=0.16)
        y += b.height + 12
    if which == 'a':
        fr.add(chat_input('vlog、科普、不露脸各', 'fang'), 40, 1062, 'input', kind='overlay', blur=14, salpha=0.2)
        fr.add(ime_bar(['放', '方', '房', '防']), 150, 1196, 'ime', kind='overlay', blur=8, salpha=0.14)
    else:
        fr.add(chat_input(), 40, 1062, 'input', kind='overlay', blur=14, salpha=0.2)
        st = stamp('确认', s=230, rot=-14)
        fr.add(st, 380, 806, 'stamp', kind='overlay', shadow=False)
    add_pip(fr, s, face_of(f), head_top(m))
    if which == 'a':
        subtitle_c(fr, [('不断打磨', False), ('你的选题和想法', True)])
    else:
        subtitle_c(fr, [('直到你', False), ('确认没有问题', True), ('之后', False)])
    return fr, []




def main(keys):
    report = {}
    for k in keys:
        fr, expect = SHOTS[k]()
        out, probs = save(fr, k, allow=ALLOW.get(k, ()), expect_face_hit=expect)
        report[k] = {'file': out.name, 'problems': probs, 'intended_face_overlap': expect,
                     'items': [(a, list(map(int, b)), kk) for a, b, kk in fr.items]}
        print(f'{k:4s} -> {out.name}  problems: {probs if probs else "none"}')
    rp = WORK / 'layout_report.json'
    old = json.loads(rp.read_text()) if rp.exists() else {}
    old.update(report)
    rp.write_text(json.dumps(old, ensure_ascii=False, indent=1))


ALLOW = {'14a': [('style_selected', 'check')], '4': [('ticket', 'stamp_free'), ('ticket', 'stamp_open')]}

SHOTS.update({'14a': shot14a, '14b': shot14b, '10a': shot10a, '10b': shot10b, '15': shot15, '11': shot11, '4': shot04, '1': shot01, '7': shot07,
              '9': shot09})
SHOTS.update({'13a': lambda: shot13('a'), '13b': lambda: shot13('b')})
SHOTS.update({'I1': lambda: (shotI1(), []), 'I2': lambda: (shotI2(), []), 'I3': lambda: (shotI3(), []),
              '16a': lambda: shot16('a'), '16b': lambda: shot16('b'), '18': shot18})

if __name__ == '__main__':
    keys = sys.argv[1:] or list(SHOTS)
    main(keys)
