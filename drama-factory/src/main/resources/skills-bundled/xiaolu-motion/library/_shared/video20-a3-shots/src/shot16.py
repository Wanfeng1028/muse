"""Shot 16 - STEP 4 剪辑成片: the self-check is played directly on the presenter's live full-screen frame.

v2 1:53.13-2:12.23 = v2 frames [3394, 3967) = source frames 5672..6244 (cut-plan segment 17, one continuous take).
Storyboard v2 row 16 + shot16a.png / shot16b.png (same drawing kit: sb_lib subtitle_c / label / sticker_outline,
render_v2 pill / badge / hud_brackets / check_chip). The presenter's picture is never retimed: frame n = timeline.v2_to_src(n).

Order (storyboard): cut line -> keyword sticker + sound-wave badge -> red scan line -> caption deliberately on the
mouth, red box + cross, 压到脸 above, green dashed safe band below -> caption slides into the band, box turns green,
已挪到安全区 -> 挡住字幕: a sticker lands on the caption, the box flashes red, the sticker is pushed away ->
Agent就会自己去重新做一遍 (user feedback 2026-09-27: the 0.5 s rewind was too fast to read): a redo card beside his head plays
压到脸 thumbnail -> spinning loop arrow 重新生成中 + progress 0-100% -> green 自检通过, then leaves before the last frame.
Captions drawn here (SUB_OWNED) use the exact C strip of sb_lib.subtitle_c; everywhere else A0 draws the captions.
"""
import math

import numpy as np
from PIL import Image, ImageDraw

from a3common import *  # noqa

SHOT = '16'
F0, F1 = 3394, 3967
SRC0 = 5672

# Word onsets in SOURCE seconds, read off 01_transcript/source_env10ms_db.npy (10 ms energy envelope): first rise
# out of a pause, or the release after the consonant closure inside a phrase. source_words_pass1.tsv (whisper) puts
# words that follow a pause 0.3-0.8 s early (e.g. 如果 200.40 -> 200.67, Agent 205.34 -> 205.87).
ONSET_SRC = {
    'step4': 189.28,        # 第四步 (whisper 188.96, before the segment start 189.067; speech starts 189.28)
    'jianji_cp': 189.99,    # 剪辑成片 (whisper 189.74 sits in the pause)
    'wancheng3': 191.89,    # 完成前三步之后
    'agent1': 193.50,       # Agent会进行视频的剪辑
    'jianji': 194.96,       # 剪辑
    'dongxiao': 195.87,     # 动效 (pause 195.40-195.86)
    'yinxiao': 196.22,      # 音效
    'wanchenghou': 198.09,  # 完成后他会自己检查一遍
    'jiancha': 199.28,      # 检查一遍
    'ruguo': 200.67,        # 如果出现 (pause 200.52-200.66; 200.28-200.51 is a -70 dB breath)
    'zi': 201.20,           # 字压到脸上
    'huozhe': 202.52,       # 或者说 (pause 202.33-202.51)
    'dang': 202.93,         # 挡住字幕 (closure 202.86-202.92, burst 202.93)
    'deng': 203.85,         # 等影响观感的情况
    'agent2': 205.87,       # Agent就会自己去 (pause 205.57-205.86)
    'jiuhui': 206.33,       # 就会自己去
    'chongxin': 206.97,     # 重新做一遍
    'speech_end': 207.92,
}
WORD_TEXT = {'step4': '第四步', 'jianji_cp': '剪辑成片', 'wancheng3': '完成前三步之后', 'agent1': 'Agent', 'jianji': '剪辑',
             'dongxiao': '动效', 'yinxiao': '音效', 'wanchenghou': '完成后它会自己', 'jiancha': '检查一遍', 'ruguo': '如果',
             'zi': '字压到脸上', 'huozhe': '或者说', 'dang': '挡住字幕', 'deng': '等', 'agent2': 'Agent',
             'jiuhui': '就会', 'chongxin': '重新做一遍'}
# A0's words_v2.json (spectrogram-checked anchors) wins where it has the word; our envelope values are the fallback
K, ONSET_REPORT = onsets(WORD_TEXT, ONSET_SRC)

# A0's caption strips for the two lines this shot draws itself (captions_v2.json): same in / out frames and the
# same keyword brush (first frame, 12 frames) so the hand-over in both directions is invisible
_SA, _SB = caption_strip('如果出现字压到脸上'), caption_strip('或者说挡住字幕')
if _SA and _SB:
    SUB_OWNED = (_SA['f0'], _SB['f1'])                       # [first, last+1) v2 frames
    SWITCH_F = _SB['f0']
    BRUSH_A = (_SA['keywords'][0]['f0'], _SA['keywords'][0]['brush_frames'])
    BRUSH_B = (_SB['keywords'][0]['f0'], _SB['keywords'][0]['brush_frames'])
else:                                                        # fallback before captions_v2.json existed
    SUB_OWNED = (v2_frame(K['ruguo'] - 0.07), v2_frame(K['deng'] - 0.07))
    SWITCH_F = v2_frame(K['huozhe'] - 0.07)
    BRUSH_A = (int(K['zi'] * FPS), 12)
    BRUSH_B = (int(K['dang'] * FPS), 12)

E = dict(
    chip_in=K['jianji_cp'],              # chip STEP 4 剪辑成片
    cut=K['jianji'],                     # cut line zips across
    st_a=K['dongxiao'],                  # keyword sticker
    st_b=K['yinxiao'],                   # sound-wave badge
    scan=K['jiancha'],                   # red scan line top -> bottom, chip + 自检中
    st_out=124.12,                       # stickers leave before the caption lands on the mouth
    sub_on=SUB_OWNED[0] / FPS,           # caption appears on the mouth (A0's strip in-frame)
    conv=SUB_OWNED[0] / FPS + 0.22,      # scan brackets close in on the caption
    lock=BRUSH_A[0] / FPS,               # red lock (glitch) + keyword marker, first frame of 字压到脸上
    x_in=BRUSH_A[0] / FPS + 0.07,
    tag_in=BRUSH_A[0] / FPS + 0.18,
    safe_in=BRUSH_A[0] / FPS + 0.23,
    slide0=126.00, slide1=126.30,        # caption slides into the safe band; box turns green (clack)
    switch=SWITCH_F / FPS,               # caption text -> 或者说挡住字幕 (A0's strip boundary)
    key2=BRUSH_B[0] / FPS,               # first frame of 挡住字幕
    stk_in=BRUSH_B[0] / FPS - 0.10, stk_land=BRUSH_B[0] / FPS + 0.06,   # sticker lands, box flashes red
    push=BRUSH_B[0] / FPS + 0.28, push_end=BRUSH_B[0] / FPS + 0.48,     # sticker pushed off the caption
    green2=BRUSH_B[0] / FPS + 0.40,                                      # box green again once the caption is clear
    box_out=BRUSH_B[0] / FPS + 0.54,                                     # box + badge gone (0.15 s) before hand-over
    handoff=SUB_OWNED[1] / FPS,          # caption goes back to A0 (等影响观感的情况)
    redo_in=K['agent2'],                 # redo card pops beside the head: state A 压到脸 thumbnail
    redo_b=K['jiuhui'] + 0.05,           # state B: loop arrow spins, 重新生成中, progress 0 -> 100 %
    redo_c=K['chongxin'] + 0.55,         # state C: green check 自检通过 (on 做一遍)
    redo_out=131.95,                     # card (and chip) leave; last frames are the untouched picture
    chip_out=131.95,
)
E = {k: round(v * FPS) / FPS for k, v in E.items()}      # every event on the frame grid (sound = picture)
BOX_FADE = 0.15
REDO_EXIT = 0.17
assert E['redo_b'] - E['redo_in'] >= 0.3 and E['redo_c'] - E['redo_b'] >= 0.3 and E['redo_out'] - E['redo_c'] >= 0.3
assert v2_frame(E['redo_out'] + REDO_EXIT) < F1 - 1
assert E['box_out'] + BOX_FADE < E['handoff'] and E['push_end'] < E['handoff']
RUNS_A = [('如果出现', False), ('字压到脸上', True)]
RUNS_B = [('或者说', False), ('挡住字幕', True)]

SCAN_DUR = 0.75
SCAN_Y0, SCAN_Y1 = 285, 1935
CUT_Y = 1262


def scan_y(t):
    return SCAN_Y0 + (SCAN_Y1 - SCAN_Y0) * ease_in_out_sine(prog(t, E['scan'], SCAN_DUR))


def scan_pass_time(y):
    """time the scan line crosses y"""
    ps = np.linspace(0, 1, 2001)
    ys = SCAN_Y0 + (SCAN_Y1 - SCAN_Y0) * np.array([ease_in_out_sine(p) for p in ps])
    return E['scan'] + SCAN_DUR * ps[int(np.searchsorted(ys, y))]


def wave_panel(t, w=108, h=74):
    """render_v2.speaker_panel look (dark panel, yellow bars), bars move with time"""
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=16, fill=(30, 31, 34, 255))
    for i, x in enumerate(range(15, w - 12, 10)):
        a = (0.28 + 0.72 * abs(math.sin(i * 0.55 + t * 7.0)) * (0.75 + 0.25 * math.sin(i * 1.7 + t * 3.1))) * (h * 0.34)
        d.line((x, h / 2 - a, x, h / 2 + a), fill=YELLOW, width=5)
    return sticker_outline(im, px=6)


def dashed_rect(d, box, color, width=5, on=14, off=12, p=1.0):
    """dashes along the perimeter (clockwise from top-left), only the first p fraction drawn"""
    x0, y0, x1, y1 = box
    segs = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    total = 2 * ((x1 - x0) + (y1 - y0))
    lim = total * p
    run = 0.0
    for (ax, ay), (bx, by) in segs:
        L = math.hypot(bx - ax, by - ay)
        s = 0.0
        while s < L:
            e = min(s + on, L)
            if run + s >= lim:
                return
            e = min(e, lim - run)
            d.line((ax + (bx - ax) * s / L, ay + (by - ay) * s / L, ax + (bx - ax) * e / L, ay + (by - ay) * e / L),
                   fill=color, width=width)
            s += on + off
        run += L


def partial_curve(p0, p1, bend, p, n=48):
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = -(y1 - y0), (x1 - x0)
    cx, cy = mx + nx * bend, my + ny * bend
    ts = np.linspace(0, max(1e-3, p), n)
    return [((1 - s) ** 2 * x0 + 2 * (1 - s) * s * cx + s ** 2 * x1, (1 - s) ** 2 * y0 + 2 * (1 - s) * s * cy + s ** 2 * y1)
            for s in ts]


class Renderer:
    def __init__(self, faces):
        self.faces = faces
        self.sticker_a = sticker_outline(label([('动效', True)], size=50, pad=(22, 14)), px=8)
        self.sticker_c = sticker_outline(label([('动效', False)], size=60, pad=(24, 14), bg=YELLOW, marker=None,
                                               weight_normal='Heavy'), px=9)
        self.tag_bad = rotate(pill('压到脸', size=40, bg=RED + (255,), padx=22), 3)
        self.tag_safe = pill('安全区', size=28, fg=GREEN, bg=(255, 255, 255, 235), padx=16)
        self.tag_ok = rotate(pill('已挪到安全区', size=36, bg=GREEN + (255,), padx=22), -2)
        self.bx, self.bok = badge('x', 92), badge('ok', 92)
        self.small_ok = badge('ok', 40)
        # scan beam (W x 140): red glow above the line, core line, thin highlight
        beam = np.zeros((140, W, 4), np.uint8)
        beam[..., 0], beam[..., 1], beam[..., 2] = RED
        ramp = np.linspace(0, 1, 134) ** 2.2
        beam[:134, :, 3] = (ramp * 46).astype(np.uint8)[:, None]
        beam[134:138, :, 3] = 235
        beam[133, :, :3] = (255, 236, 230)
        beam[133, :, 3] = 170
        self.beam = Image.fromarray(beam, 'RGBA')
        self.sc = scissors(56).rotate(-90, resample=Image.BICUBIC, expand=True)
        # fixed geometry
        f_on = src_frame(SUB_OWNED[0])
        lp = faces.lips(f_on)
        self.cy_mouth = (lp[1] + lp[3]) / 2
        _, _, _, self.stripA_mouth = subtitle_layer(RUNS_A, cy=self.cy_mouth)
        _, _, _, self.stripA_safe = subtitle_layer(RUNS_A, cy=SUB_CY)
        _, _, _, self.stripB_safe = subtitle_layer(RUNS_B, cy=SUB_CY)
        wa, wb = self.sticker_a.size, wave_panel(0).size
        self.pos_a = (W - 16 - wa[0] / 2 - 6, 770)
        self.pos_b = (16 + wb[0] / 2 + 4, 905)
        self.pass_a = scan_pass_time(self.pos_a[1])
        self.pass_b = scan_pass_time(self.pos_b[1])

    # -------------------------------------------------------------- caption state (owned interval only)
    def caption(self, t):
        """(runs, cy, marker_p, strip_box) of the caption we draw at t, or None"""
        fi = v2_frame(t)
        if not (SUB_OWNED[0] <= fi < SUB_OWNED[1]):
            return None
        if fi < SWITCH_F:
            p = ease_in_out_cubic(prog(t, E['slide0'], E['slide1'] - E['slide0']))
            cy = self.cy_mouth + (SUB_CY - self.cy_mouth) * p
            return RUNS_A, cy, marker_progress(fi, *BRUSH_A), None
        return RUNS_B, SUB_CY, marker_progress(fi, *BRUSH_B), None

    def box_geom(self, t):
        """current check box (strip box +-16) following the caption: slide, then width morph on the text switch"""
        p = ease_in_out_cubic(prog(t, E['slide0'], E['slide1'] - E['slide0']))
        a0, a1 = self.stripA_mouth, self.stripA_safe
        sb = [a0[i] + (a1[i] - a0[i]) * p for i in range(4)]
        if v2_frame(t) >= SWITCH_F:
            q = ease_out_cubic(prog(t, E['switch'] - 1 / FPS, 0.13))
            b = self.stripB_safe
            sb = [sb[i] + (b[i] - sb[i]) * q for i in range(4)]
        return (sb[0] - 16, sb[1] - 16, sb[2] + 16, sb[3] + 16)

    # -------------------------------------------------------------- graphics (also replayed by the rewind)
    def draw_scan(self, img, t, items):
        p = prog(t, E['scan'], SCAN_DUR)
        if 0 < p < 1:
            y = scan_y(t)
            top = int(round(y - 136))
            beam = self.beam
            if top < STEP_BAND[1] + 1:                    # nothing of ours in the step-bar band (y 180-280)
                cut = STEP_BAND[1] + 1 - top
                if cut >= beam.height:
                    return
                beam = beam.crop((0, cut, W, beam.height))
                top = STEP_BAND[1] + 1
            bb = paste(img, beam, 0, top)
            if bb:
                items.append(('scan_line', bb, 'fx'))

    def draw_check(self, img, t, items, replay=False):
        """scan brackets, red/green box, cross/check badge, 压到脸 tag; replay=True: rewind copy (no caption)"""
        if t < E['conv'] or t >= E['box_out'] + BOX_FADE:
            return
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        box = self.box_geom(t)
        jit = {0: 8, 1: -6, 2: 3}.get(v2_frame(t) - v2_frame(E['lock']), 0)
        if t < E['lock']:                                         # brackets close in on the caption, white
            q = ease_out_cubic(prog(t, E['conv'], E['lock'] - E['conv']))
            s = 1.28 - 0.28 * q
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            hw, hh = (box[2] - box[0]) / 2 * s, (box[3] - box[1]) / 2 * s
            hud_brackets(d, (cx - hw, cy - hh, cx + hw, cy + hh), (255, 255, 255, 235), lw=7, L=46)
            items.append(('scan_brackets', (int(cx - hw - 4), int(cy - hh - 4), int(cx + hw + 4), int(cy + hh + 4)), 'fx'))
        else:
            fl = t - E['stk_land']
            blk = E['green2'] - E['stk_land']
            red = (t < E['slide1']) or (0 <= fl < blk and int(fl * 30) not in (4,))
            hidden = 0 <= fl < blk and int(fl * 30) == 4
            fade = 1 - prog(t, E['box_out'], BOX_FADE)
            col = (RED if red else GREEN) + (int(255 * fade),)
            b = (box[0] + jit, box[1], box[2] + jit, box[3])
            if not hidden:
                wdt = 7 if v2_frame(t) - v2_frame(E['lock']) in (0, 1) else 4
                if v2_frame(t) - v2_frame(E['lock']) in (0, 1):
                    d.rectangle(b, fill=RED + (38,))
                d.rectangle(b, outline=col, width=wdt)
                hud_brackets(d, b, col, lw=7, L=46)
            items.append(('check_box', (int(b[0] - 4), int(b[1] - 4), int(b[2] + 4), int(b[3] + 4)), 'fx'))
        img.alpha_composite(lay)
        # badge: cross on the lock, check after the slide, cross again while the sticker blocks the caption
        if t >= E['x_in']:
            fl = t - E['stk_land']
            ok = (t >= E['slide1'] and not (0 <= fl < E['green2'] - E['stk_land']))
            if ok:
                t_sw = E['slide1'] if t < E['stk_land'] else E['green2']
                sc = 0.55 + 0.45 * ease_out_back(prog(t, t_sw, 0.22), 2.2)
            elif t >= E['stk_land']:
                sc = 0.55 + 0.45 * ease_out_back(prog(t, E['stk_land'], 0.2), 2.2)
            else:
                sc = pop(t, E['x_in'], 0.25)
            fade = 1 - prog(t, E['box_out'], BOX_FADE)
            bx = min(box[2] + 14, W - 100) + jit
            bb = paste_c(img, self.bok if ok else self.bx, bx + 46, (box[1] + box[3]) / 2, scale=sc, alpha=fade,
                         shadow=(6, 0.3, 3, 7))
            if bb:
                items.append(('badge', bb, 'overlay'))
        # 压到脸: right edge above the badge (anchored to the box on the mouth), gone before the slide
        if E['tag_in'] <= t < E['slide0'] + 0.04:
            sc = pop(t, E['tag_in'], 0.26) * (1 - ease_in_cubic(prog(t, E['slide0'] - 0.08, 0.12)))
            tw = self.tag_bad.width
            top = self.stripA_mouth[1] - 16
            bb = paste_c(img, self.tag_bad, W - 34 - tw / 2, top - 90 + self.tag_bad.height / 2, scale=sc,
                         shadow=(8, 0.3, 3, 7))
            if bb:
                items.append(('tag_bad', bb, 'text'))

    def draw_safe(self, img, t, items):
        if not (E['safe_in'] <= t < E['slide1'] + 0.05):
            return
        a = 1 - prog(t, E['slide1'] - 0.08, 0.12)
        tb = (self.stripA_safe[0], SUB_CY - 56, self.stripA_safe[2], SUB_CY + 56)
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        dashed_rect(ImageDraw.Draw(lay), tb, GREEN + (int(210 * a),), p=ease_in_out_cubic(prog(t, E['safe_in'], 0.32)))
        img.alpha_composite(lay)
        items.append(('safe_zone', (tb[0] - 3, tb[1] - 3, tb[2] + 3, tb[3] + 3), 'fx'))
        sc = pop(t, E['safe_in'] + 0.2, 0.25)
        if sc > 0:
            bb = paste_c(img, self.tag_safe, tb[0] - 6 + self.tag_safe.width / 2, tb[3] + 10 + self.tag_safe.height / 2,
                         scale=sc, alpha=a)
            if bb:
                items.append(('tag_safe', bb, 'text'))

    def draw_slide_extras(self, img, t, items):
        # green trail on the right margin, drawn with the slide, fades after
        if E['slide0'] <= t < E['slide1'] + 0.5:
            p = ease_in_out_cubic(prog(t, E['slide0'], E['slide1'] - E['slide0']))
            a = 1 - prog(t, E['slide1'] + 0.3, 0.2)
            pts = partial_curve((1032, self.cy_mouth - 30), (1040, SUB_CY - 88), -0.16, p)
            lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            d.line(pts, fill=GREEN + (int(255 * a),), width=7, joint='curve')
            if p > 0.85:
                ex, ey = pts[-1]
                px_, py_ = pts[-5]
                ang = math.atan2(ey - py_, ex - px_)
                for sg in (-1, 1):
                    aa = ang + math.pi - sg * 0.45
                    d.line((ex, ey, ex + math.cos(aa) * 26, ey + math.sin(aa) * 26), fill=GREEN + (int(255 * a),), width=7)
            img.alpha_composite(lay)
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            items.append(('slide_arrow', (int(min(xs) - 20), int(min(ys) - 20), int(max(xs) + 20), int(max(ys) + 20)), 'overlay'))
        # 已挪到安全区
        if E['slide1'] <= t < E['switch'] + 0.45:
            sc = pop(t, E['slide1'] + 0.04, 0.26) * (1 - ease_in_cubic(prog(t, E['switch'] + 0.30, 0.15)))
            bb = paste_c(img, self.tag_ok, 40 + self.tag_ok.width / 2, SUB_CY + 72 + 30 + self.tag_ok.height / 2,
                         scale=sc, shadow=(8, 0.3, 3, 7))
            if bb:
                items.append(('tag_ok', bb, 'text'))

    def draw_block_sticker(self, img, t, items):
        if not (E['stk_in'] <= t < E['push_end']):
            return
        land = (650, SUB_CY + 2)
        if t < E['stk_land']:                          # flies in from the bottom right, under the badge
            p = ease_in_cubic(prog(t, E['stk_in'], E['stk_land'] - E['stk_in']))
            x, y = 1190 + (land[0] - 1190) * p, 1720 + (land[1] - 1720) * p
            rot, sc, a = 34 + (-10 - 34) * p, 1.0, 1.0
        elif t < E['push']:
            x, y = land
            rot, a = -10, 1.0
            sc = 1.10 - 0.10 * ease_out_cubic(prog(t, E['stk_land'], 0.1))
        else:
            p = ease_in_out_cubic(prog(t, E['push'], E['push_end'] - E['push']))
            x, y = land[0] + (1250 - land[0]) * p, land[1] + (1080 - land[1]) * p
            rot, sc, a = -10 + 40 * p, 1 - 0.12 * p, 1 - clamp((p - 0.6) / 0.4)
        bb = paste_c(img, self.sticker_c, x, y, scale=sc, rot=rot, alpha=a, shadow=(10, 0.32, 4, 9))
        if bb:
            items.append(('sticker_block', bb, 'overlay'))

    # -------------------------------------------------------------- frame
    def render(self, fi, src_rgb):
        t = fi / FPS
        f = src_frame(fi)
        items = []
        img = None

        def canvas():
            nonlocal img
            if img is None:
                img = Image.fromarray(src_rgb).convert('RGBA')
            return img

        # cut line (剪辑): red dashes zip left -> right below the chin, scissors on the tip
        if E['cut'] <= t < E['cut'] + 0.8:
            p = ease_out_cubic(prog(t, E['cut'], 0.22))
            a = 1 - prog(t, E['cut'] + 0.45, 0.3)
            xh = -40 + (W + 80) * p
            lay = Image.new('RGBA', (W, 40), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            for x in range(-10, int(min(xh, W + 10)), 36):
                d.line((x, 20, min(x + 22, xh), 20), fill=(255, 255, 255, int(200 * a)), width=11)
            for x in range(-10, int(min(xh, W + 10)), 36):
                d.line((x, 20, min(x + 22, xh), 20), fill=RED + (int(255 * a),), width=5)
            bb = paste(canvas(), lay, 0, CUT_Y - 20)
            if bb:
                items.append(('cut_line', bb, 'overlay'))
            if p < 1 or t < E['cut'] + 0.5:
                sx = xh if p < 1 else W + 60 * prog(t, E['cut'] + 0.22, 0.2) * 3
                bb = paste_c(canvas(), self.sc, sx, CUT_Y, alpha=a)
                if bb:
                    items.append(('scissors', bb, 'overlay'))
        # keyword sticker + sound-wave badge (包装), checked by the scan, leave before the mouth caption
        for key, pos, rot, pas, dt in (('a', self.pos_a, -7, self.pass_a, 0.0), ('b', self.pos_b, 6, self.pass_b, 0.04)):
            t_in = E['st_a'] if key == 'a' else E['st_b']
            if not (t_in <= t < E['st_out'] + dt + 0.2):
                continue
            sc = pop(t, t_in, 0.3) * (1 - ease_in_cubic(prog(t, E['st_out'] + dt, 0.18)))
            if sc <= 0:
                continue
            el = self.sticker_a if key == 'a' else wave_panel(t)
            r = rot + (1 - clamp((t - t_in) / 0.3)) * (-14 if key == 'a' else 14)
            bb = paste_c(canvas(), el, pos[0], pos[1], scale=sc, rot=r, shadow=(9, 0.3, 3, 8))
            if bb:
                items.append((f'sticker_{key}', bb, 'overlay'))
                if pas <= t < pas + 0.45:            # passed the check: green ring + tick
                    q = 1 - prog(t, pas + 0.25, 0.2)
                    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                    ImageDraw.Draw(lay).rounded_rectangle((bb[0] - 8, bb[1] - 8, bb[2] + 8, bb[3] + 8), radius=18,
                                                          outline=GREEN + (int(255 * q),), width=4)
                    canvas().alpha_composite(lay)
                    ok_bb = paste_c(canvas(), self.small_ok, bb[2] - 4, bb[1] + 4, scale=pop(t, pas, 0.2), alpha=q)
                    if ok_bb:
                        items.append((f'sticker_{key}_ok', ok_bb, 'overlay'))
        # red scan line
        if E['scan'] < t < E['scan'] + SCAN_DUR:
            self.draw_scan(canvas(), t, items)
        # caption we own + the check sequence
        cap = self.caption(t)
        if cap:
            runs, cy, mp, _ = cap
            lay, lx, ly, sbox = subtitle_layer(runs, cy=cy, marker_p=mp)
            paste(canvas(), lay, lx, ly)
            items.append(('subtitle_own', sbox, 'text'))
        if E['safe_in'] <= t < E['slide1'] + 0.05:
            self.draw_safe(canvas(), t, items)
        if E['conv'] <= t < E['box_out'] + BOX_FADE:
            self.draw_check(canvas(), t, items)
        if E['slide0'] <= t < E['switch'] + 0.45:
            self.draw_slide_extras(canvas(), t, items)
        if E['stk_in'] <= t < E['push_end']:
            self.draw_block_sticker(canvas(), t, items)
        # 自己重做 card (Agent就会自己去重新做一遍)
        if E['redo_in'] <= t < E['redo_out'] + REDO_EXIT:
            self.draw_redo_card(canvas(), t, items)
        # chip (STEP 4 剪辑成片 -> · 自检中 -> · 重做中)
        if E['chip_in'] <= t < E['chip_out'] + REDO_EXIT:
            base = 'STEP 4 剪辑成片'
            if t < E['scan']:
                txt, dot = base, YELLOW
            else:
                n = int(clamp((t - E['scan']) / 0.25) * 6 + 0.001)
                txt = base + ' · 自检中'[:n]
                blink = 0.5 + 0.5 * math.cos(2 * math.pi * 1.6 * (t - E['scan']))
                dot = tuple(int(20 + (c - 20) * (0.35 + 0.65 * blink)) for c in RED)
            chip = pill(txt, size=30, bg=(20, 20, 20, 225), dot=dot)
            sc = pop(t, E['chip_in'], 0.3, 1.4) * (1 - ease_in_cubic(prog(t, E['chip_out'], REDO_EXIT)))
            if sc > 0:
                e = transform(chip, sc)
                bb = paste(canvas(), e, 40, 290 + chip.height / 2 - e.height / 2)
                if bb:
                    items.append(('chip', bb, 'text'))
        if img is None:
            return src_rgb, items
        return np.array(img.convert('RGB')), items

    # -------------------------------------------------------------- 自己重做 card
    THUMB_H = 124
    CARD_W, CARD_H = 360, 124 + 130
    # right of / above the presenter's head: the face box top is >= 607 px in frames 3898-3963, the step bar ends at 280;
    # with the tape and the 4 % pop overshoot the card spans y 288-576
    CARD_X, CARD_Y = W - 16 - 360, 316

    def redo_thumbs(self):
        """the two earlier moments of this shot, re-rendered and cropped: mistake (red box on the mouth) / fixed"""
        if getattr(self, '_thumbs', None) is None:
            out = []
            ch = int(round(940 * self.THUMB_H / (self.CARD_W - 32)))
            for fi, y0 in ((v2_frame(E['slide0']) - 4, 850), (v2_frame(E['switch']) - 4, 1200)):
                rgb, _ = self.render(fi, grab_src(src_frame(fi)))
                crop = Image.fromarray(rgb).crop((140, y0, 1080, y0 + ch))
                out.append(crop.resize((self.CARD_W - 32, self.THUMB_H), Image.LANCZOS).convert('RGBA'))
            self._thumbs = out
        return self._thumbs

    def loop_arrow(self, s, color, rot):
        """circular 'regenerate' arrow (300 deg arc + head), drawn at 3x, rotated by rot degrees"""
        S = 3
        im = Image.new('RGBA', (s * S, s * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        m, lw = s * S * 0.14, max(3, int(s * S * 0.11))
        d.arc((m, m, s * S - m, s * S - m), 30, 320, fill=color, width=lw)
        cx = cy = s * S / 2
        r = s * S / 2 - m - lw / 2
        a = math.radians(320)
        ex, ey = cx + r * math.cos(a), cy + r * math.sin(a)
        tang = a + math.pi / 2
        hl = lw * 1.9
        d.polygon([(ex + math.cos(tang) * hl, ey + math.sin(tang) * hl),
                   (ex + math.cos(tang + 2.3) * hl * 0.85, ey + math.sin(tang + 2.3) * hl * 0.85),
                   (ex + math.cos(tang - 2.3) * hl * 0.85, ey + math.sin(tang - 2.3) * hl * 0.85)], fill=color)
        im = im.resize((s, s), Image.LANCZOS)
        return im.rotate(-rot, resample=Image.BICUBIC)

    def redo_card_image(self, t):
        w, h = self.CARD_W, self.CARD_H
        mistake, fixed = self.redo_thumbs()
        card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(card).rounded_rectangle((0, 0, w - 1, h - 1), radius=22, fill=CARD + (255,))
        d = ImageDraw.Draw(card)
        tw, th = w - 32, self.THUMB_H
        state = 'A' if t < E['redo_b'] else ('B' if t < E['redo_c'] else 'C')
        if state == 'C':
            thumb = fixed.copy()
        else:
            thumb = mistake.copy()
            if state == 'B':
                thumb = Image.blend(thumb, Image.new('RGBA', thumb.size, (24, 22, 20, 255)), 0.55)
        card.paste(thumb, (16, 16), rrect_mask(tw, th, 12))
        f40 = font('Heavy', 40)
        row_y = 16 + th + 12
        if state == 'A':
            tag = pill('压到脸', size=40, bg=RED + (255,), padx=22)
            card.alpha_composite(tag, (16, row_y))
            card.alpha_composite(badge('x', 56), (16 + tag.width + 12, row_y + (tag.height - 56) // 2))
        elif state == 'B':
            rot = (t - E['redo_b']) * 360 / 0.8
            big = self.loop_arrow(76, (255, 255, 255, 240), rot)
            card.alpha_composite(big, (16 + tw // 2 - 38, 16 + th // 2 - 38))
            card.alpha_composite(self.loop_arrow(48, INK + (255,), rot), (16, row_y + 6))
            d.text((16 + 58, row_y + 30), '重新生成中', font=f40, fill=INK, anchor='lm')
        else:
            card.alpha_composite(badge('ok', 52), (16, row_y + 4))
            d.text((16 + 64, row_y + 30), '自检通过', font=f40, fill=GREEN, anchor='lm')
        if state != 'A':                                         # progress 0 -> 100 %
            p = 1.0 if state == 'C' else ease_in_out_sine(prog(t, E['redo_b'] + 0.06, E['redo_c'] - E['redo_b'] - 0.14))
            by = row_y + 70
            bw = tw - 118
            d.rounded_rectangle((16, by, 16 + bw, by + 18), radius=9, fill=(226, 220, 208, 255))
            if p > 0:
                d.rounded_rectangle((16, by, 16 + max(18, bw * p), by + 18), radius=9,
                                    fill=(GREEN if state == 'C' else YELLOW) + (255,))
            d.text((w - 16, by + 9), f'{int(round(p * 100))}%', font=font('Bold', 40), fill=INK, anchor='rm')
        out = Image.new('RGBA', (w, h + 22), (0, 0, 0, 0))
        out.alpha_composite(card, (0, 22))
        tp = rotate(tape(118, 36, color=(250, 222, 120), seed=16), -6)
        out.alpha_composite(tp, (int(w / 2 - tp.width / 2), 0))
        return out

    def draw_redo_card(self, img, t, items):
        el = self.redo_card_image(t)
        sc = pop(t, E['redo_in'], 0.28, 0.9) * (1 - ease_in_cubic(prog(t, E['redo_out'], REDO_EXIT)))  # small overshoot: stays below the step bar
        if t >= E['redo_c']:                                      # small bump on 自检通过
            sc *= 1 + 0.05 * math.sin(math.pi * prog(t, E['redo_c'], 0.18))
        cx, cy = self.CARD_X + self.CARD_W / 2, self.CARD_Y - 22 + el.height / 2
        bb = paste_c(img, el, cx, cy, scale=sc, shadow=(14, 0.3, 4, 10))
        if bb:
            items.append(('redo_card', bb, 'overlay'))


# ------------------------------------------------------------------ sound cues (v2 seconds, xiaolu-motion ids)
def sfx():
    pk = pop_peak_time
    return [
        dict(id='bell', t=round(K['step4'], 3), gain_db=-4, pitch=0, align='start',
             note='第四步：章节铃（分镜写 1:53.13 镜头起点；这里对齐「第四步」实际起音）。若 A0 的步骤条切换已带铃，请去重'),
        dict(id='laser_zip', t=round(E['cut'], 3), gain_db=0, pitch=0, align='start', params={'dur': 0.22},
             note='「剪辑」剪口线从左划到右（分镜写 snip，音效库没有这个 id，用 laser_zip）'),
        dict(id='pop_soft', t=round(pk(E['st_a'], 0.3), 3), gain_db=0, pitch=0, align='start',
             note='「动效」关键词贴纸弹出（回弹顶点）'),
        dict(id='pop_soft', t=round(pk(E['st_b'], 0.3), 3), gain_db=0, pitch=2, align='start',
             note='「音效」声波小标弹出（回弹顶点）'),
        dict(id='laser_zip', t=round(E['scan'], 3), gain_db=0, pitch=0, align='start', params={'dur': 0.25},
             note='「检查一遍」红色扫描线从上往下扫（0.75 s）'),
        dict(id='glitch', t=round(E['lock'], 3), gain_db=-2, pitch=0, align='start', params={'dur': 0.2},
             note='「字压到脸上」扫描框锁定变红框（抖 3 帧）'),
        dict(id='whoosh_fast', t=round(E['slide0'], 3), gain_db=0, pitch=0, align='motion',
             note='字幕从嘴上滑到安全区，动作起点'),
        dict(id='clack', t=round(E['slide1'], 3), gain_db=0, pitch=0, align='start', note='落进安全区，框变绿、打勾'),
        dict(id='land', t=round(E['stk_land'], 3), gain_db=-3, pitch=0, align='start', note='「挡住字幕」贴纸拍到字幕上，红框闪'),
        dict(id='whoosh_fast', t=round(E['push'], 3), gain_db=-2, pitch=2, align='motion', note='贴纸被推开'),
        dict(id='pop_soft', t=round(pk(E['redo_in'], 0.28, 0.9), 3), gain_db=-2, pitch=0, align='start',
             note='「Agent就会自己去」重做小卡在头侧弹出（回弹顶点）'),
    ] + [dict(id='tick', t=round(E['redo_b'] + 0.1 * i, 3), gain_db=-20, pitch=round(4 * i / 10, 1), align='start',
              note='循环箭头转动（轻的转动声：连续轻 tick，每 0.1 s 一下，音高缓升）')
         for i in range(int((E['redo_c'] - E['redo_b']) / 0.1))] + [
        dict(id='pluck', t=round(E['redo_c'], 3), gain_db=0, pitch=0, align='start', params={'note': 'D6', 'dur': 0.9},
             note='进度到 100%，变绿勾「自检通过」：清脆完成音')]


def keyword_fx():
    return {
        '剪辑': dict(t=round(E['cut'], 3), fx='红色虚线剪口从左划到右，剪刀跟在线头，0.22 s，随后 0.3 s 淡出'),
        '动效': dict(t=round(E['st_a'], 3), fx='右侧「动效」关键词贴纸弹出（回弹）'),
        '音效': dict(t=round(E['st_b'], 3), fx='左侧声波小标弹出，声波条持续跳动'),
        '检查一遍': dict(t=round(E['scan'], 3), fx='红色扫描线 0.75 s 从 y285 扫到底；扫过贴纸时贴纸绿框打勾；状态条加「· 自检中」'),
        '如果出现': dict(t=round(E['sub_on'], 3), fx='本镜接管字幕，字幕故意出现在嘴上'),
        '字压到脸上': dict(t=round(E['lock'], 3), fx='白色扫描框收拢到字幕上并锁定变红框（抖 3 帧），右侧红叉、右上「压到脸」、下方绿色虚线安全区和「安全区」'),
        '（滑入安全区）': dict(t=round(E['slide0'], 3), fx='字幕 0.3 s 滑到 y1368 安全区，126.30 框变绿、红叉变绿勾，「已挪到安全区」'),
        '或者说': dict(t=round(E['switch'], 3), fx='字幕换成「或者说挡住字幕」，绿框跟着改宽度'),
        '挡住字幕': dict(t=round(E['key2'], 3), fx='关键词马克笔刷出；「动效」贴纸飞来压住字幕，红框闪一下，贴纸被推开，框变绿后淡出'),
        '等影响观感的情况': dict(t=round(E['handoff'], 3), fx='字幕交回 A0'),
        'Agent就会自己去重新做一遍': dict(t=round(E['redo_in'], 3), fx=f'头侧（右上，x {Renderer.CARD_X}-{Renderer.CARD_X + Renderer.CARD_W}，'
                                     f'y {Renderer.CARD_Y}-{Renderer.CARD_Y + Renderer.CARD_H}）弹出重做小卡：{fmt(E["redo_in"])} 先是刚才「压到脸」红框缩略；'
                                     f'{fmt(E["redo_b"])} 循环箭头转动 +「重新生成中」+ 进度条 0→100%；{fmt(E["redo_c"])} 绿勾「自检通过」；'
                                     f'{fmt(E["redo_out"])} 收卡，末帧回原画面。卡上文字 40 px'),
    }


def keyword_animations():
    """every animation interval of this shot (v2 seconds / frames [f0, f1)): pause removal must not cut inside them"""
    def iv(name, t0, t1, note=''):
        return dict(name=name, t0=round(t0, 3), t1=round(t1, 3), f0=v2_frame(t0), f1=v2_frame(t1),
                    timecode=[fmt(t0), fmt(t1)], note=note)
    pk = E['redo_in'] + 0.28
    return [
        iv('状态条弹出', E['chip_in'], E['chip_in'] + 0.3),
        iv('剪口线划过', E['cut'], E['cut'] + 0.8, '0.22 s 划过 + 淡出'),
        iv('动效贴纸弹出', E['st_a'], E['st_a'] + 0.3),
        iv('声波小标弹出', E['st_b'], E['st_b'] + 0.3),
        iv('扫描线 + 状态条加「自检中」', E['scan'], E['scan'] + SCAN_DUR, '扫过贴纸时贴纸打勾，贴纸 2:04.12 收起'),
        iv('贴纸收起', E['st_out'], E['st_out'] + 0.24),
        iv('字幕压嘴 → 红框锁定 → 压到脸 / 安全区', E['sub_on'], E['slide0'], '本镜自画字幕起点 = A0 字幕交接帧'),
        iv('字幕滑入安全区 → 绿勾', E['slide0'], E['slide1'] + 0.3),
        iv('字幕换行（A0 字幕边界）', E['switch'] - 1 / FPS, E['switch'] + 0.13),
        iv('贴纸压字幕 → 红框闪 → 推开 → 框淡出', E['stk_in'], E['box_out'] + BOX_FADE, '到 A0 字幕交接帧前结束'),
        iv('重做小卡·弹出', E['redo_in'], pk),
        iv('重做小卡·状态1「压到脸」红框缩略', E['redo_in'], E['redo_b']),
        iv('重做小卡·状态2 循环箭头 +「重新生成中」+ 进度条 0→100%', E['redo_b'], E['redo_c']),
        iv('重做小卡·状态3 绿勾「自检通过」', E['redo_c'], E['redo_out']),
        iv('重做小卡·收起（状态条同时收起）', E['redo_out'], E['redo_out'] + REDO_EXIT, '之后到镜尾是原画面'),
    ]


# ------------------------------------------------------------------ QA hooks + meta
ALLOW = {('sticker_block', 'subtitle_own'), ('sticker_a', 'sticker_a_ok'), ('sticker_b', 'sticker_b_ok'),
         ('scissors', 'cut_line')}


def intended(t):
    """elements that may touch the face / lips box at time t (storyboard 16a: the caption on the mouth is the point)"""
    s = {'scan_line'}                               # the full-width scan line passes over the face
    if t < E['slide1']:
        s |= {'subtitle_own', 'check_box', 'scan_brackets'}
    return s


def all_texts():
    return ['STEP 4 剪辑成片 · 自检中', '动效', '压到脸', '安全区', '已挪到安全区', '重新生成中', '自检通过', '0123456789%',
            ''.join(t for t, _ in RUNS_A), ''.join(t for t, _ in RUNS_B)]


def meta(pr, sha):
    so = SUB_OWNED
    return dict(
        shot='16', owner='A3「视频20·分镜胶片与自检镜」', title='镜 16 · STEP 4 剪辑成片：自检直接做在出镜者全屏实拍上',
        v2_frames=[F0, F1], v2_seconds=[round(F0 / FPS, 3), round(F1 / FPS, 3)], v2_timecode=[fmt(F0 / FPS), fmt(F1 / FPS)],
        frame_range_note='[first, last+1) in v2 frames, 30 fps; source frames via timeline.v2_to_src',
        source=dict(file=str(SRC_MOV), frames=[SRC0, SRC0 + F1 - F0 - 1], mapping='timeline.v2_to_src: cut-plan segment 17, '
                    'one continuous take, every v2 frame = one source frame in order (no reverse / speed change / skip / repeat)'),
        starts_clean=True, ends_clean=True,
        clean_head=dict(until=fmt(E['chip_in']), note='首帧起到状态条弹出前都是原画面'),
        clean_tail=dict(from_=fmt(E['redo_out'] + REDO_EXIT), note='重做小卡和状态条收起后到末帧都是原画面'),
        subtitle_owned=[dict(v2_frames=[so[0], so[1]], seconds=[round(so[0] / FPS, 3), round(so[1] / FPS, 3)],
                             timecode=[fmt(so[0] / FPS), fmt(so[1] / FPS)],
                             lines=[dict(text='如果出现字压到脸上', keyword='字压到脸上', from_=round(so[0] / FPS, 3),
                                         to=round(E['switch'], 3), keyword_marker_at=round(E['lock'], 3),
                                         position=f'cy {round(Renderer_cy_mouth(), 1)}（嘴上）→ {fmt(E["slide0"])}-{fmt(E["slide1"])} 滑到 cy {SUB_CY}'),
                                    dict(text='或者说挡住字幕', keyword='挡住字幕', from_=round(E['switch'], 3), to=round(so[1] / FPS, 3),
                                         keyword_marker_at=round(E['key2'], 3), position=f'cy {SUB_CY}（标准位），{fmt(E["stk_land"])} 被「动效」贴纸压住，{fmt(E["push"])} 推开')],
                             handoff_to_A0=dict(at=round(so[1] / FPS, 3), frame=so[1], next_line='等影响观感的情况',
                                                note='A0 这一帧起画主字幕；本镜在这之前已清掉框和贴纸，字幕停在标准位 cy 1368'),
                             style='sb_lib.subtitle_c 同一画法（Medium 66 / 关键词 Heavy + 黄色马克笔底块）；两行的入出帧、关键词起刷帧和 12 帧线性刷出都取自 04_captions/captions_v2.json（与 A0 主字幕一致）；出现是硬切')],
        no_max_ranges=[],
        keyword_fx=keyword_fx(), keyword_animations=keyword_animations(), demo_clips=[],
        fonts=[str(FONTS / f) for f in FONT_FILES],
        word_onsets_v2={k: round(v, 3) for k, v in K.items()},
        word_onsets_method='优先用 A0 的 04_captions/words_v2.json（频谱人工锚点）；没有的字用 01_transcript/source_env10ms_db.npy 能量包络估计。两者对照见 word_onsets_check',
        word_onsets_check=ONSET_REPORT,
        spec=dict(codec=pr['codec_name'], profile=pr['profile'], size=f"{pr['width']}x{pr['height']}", fps=pr['r_frame_rate'],
                  frames=int(pr['nb_read_frames']), pix_fmt=pr['pix_fmt'], color=f"{pr.get('color_space')}/{pr.get('color_range')}",
                  crf=10, audio='none'),
        sha256=sha,
        notes=['步骤条（y 196-260）由 A0 画；本镜 y 180-280 不放任何元素，状态条在 y 290-341。',
               '扫描线（2:03.36 起 0.75 s）是整幅宽的细红线，从脸上扫过；字幕压嘴、红框是分镜设计的一部分，qa.json 的 intended_face_contact 列了帧号。',
               '2026-09-27 按用户反馈改结尾：「重新做一遍」原来的 0.5 s 倒带换成重做小卡（压到脸缩略 → 重新生成中 + 进度条 → 自检通过），每个状态 ≥ 0.4 s，卡上字 40 px。',
               '分镜写的 snip 音效在 xiaolu-motion 音效库里没有，sfx.json 用 laser_zip。'],
    )


def Renderer_cy_mouth():
    """caption centre on the mouth: centre of the outer-lip box at the frame the caption appears"""
    import json as _j
    fr = _j.loads((SHOTS_DIR / 's16/_work/faces_src.json').read_text())['frames'][str(src_frame(v2_frame(E['sub_on'])))]
    lp = fr['lips']
    return (lp[1] + lp[3]) / 2
