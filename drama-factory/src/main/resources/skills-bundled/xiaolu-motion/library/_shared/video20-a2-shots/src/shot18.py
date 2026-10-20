"""Shot 18 (v2 2:17.27-2:25.00, frames 4118..4349): split screen. Left: yellow paper, the presenter matted (clean-plate
premultiplied foreground, 0.70), role card 「你 创意 + 拍摄」. Right: an Agent workbench working by itself:
the preview plays the real vlog demo, the timeline cuts out a dead-air piece (ripple), the audio lane fills up to
the moving playhead, 「+ 转场」「+ 音效」「+ 贴纸字幕」 pop one by one and grow their FX blocks, role card
「Agent 剪辑 + 包装」. Same components as storyboard shot18 (render_v2 workbench / role_card / scissors), laid out
100 px lower so nothing sits in the top 150 px.

Word sync (words_v2.json): 创意 -> left card, 拍摄 -> its second half, 剪辑 -> right card, 包装 -> its second
half, 可以 / 全部 / 交给 -> the three chips. The timeline cut lands on the real jump cut of the source (2:20.833).
Open / close: the workbench pushes in from the right edge while the presenter shrinks onto the yellow half (15 frames each);
frame 4118 and frame 4349 are the presenter's untouched frames.
"""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

from a2common import *  # noqa
import a2time as AT

F0, F1 = AT.SHOT_RANGE['18']                 # 4118, 4350
HALF = W // 2
OPEN = (F0, F0 + 14)
CLOSE = (F1 - 15, F1 - 1)                    # 4335..4349
CUT_T = 4225 / FPS                           # source jump cut 19 -> 20 (2:20.833)
W_ = AT.word_on
T = dict(
    chuangyi=AT.kw('18', '创意', 138.45), paishe=W_('拍摄', 139.96), jianji=AT.kw('18', '剪辑和包装', 141.03), baozhuang=W_('包装可以', 141.83),
    keyi=W_('可以全部', 142.27), quanbu=W_('全部交给', 142.62), jiaogei=W_('交给你的', 143.05),
)
S18 = 0.70
PANEL_BG = (30, 31, 34)
DEMO_V = DEMOS / 'vlog/vlog_demo.mp4'
PREVIEW = (28, 206, 484, 540)                # x, y, w, h inside the panel
PREVIEW_SRC_Y = (255, 1460)                  # rows of the 9:16 vlog frame shown (keeps the top cards and the subtitles)
VLOG_T0 = 17.80 - 142.70                     # vlog time = v2 time + VLOG_T0 (the storyboard frame 2:22.70 shows 17.80 s)
TL_LABEL_Y = 786
LANES = {'V': (826, 900), 'FX': (912, 956), 'A': (968, 1032)}
X0 = 84                                      # first clip x in the panel
TRACK_X1 = 512
CHIPS_Y = 1054
CHIPS = [('+ 转场', (255, 214, 10), 'keyi', (0.70, 0.80)), ('+ 音效', (120, 180, 255), 'quanbu', (0.26, 0.36)),
         ('+ 贴纸字幕', (255, 140, 120), 'jiaogei', (0.44, 0.62))]


def pill(text, size=30, fg=(255, 255, 255), bg=INK, padx=20, h=None, weight='Heavy', dot=None, dot_alpha=1.0):
    f = font(weight, size)
    w = int(f.getlength(text) + 2 * padx + (26 if dot else 0))
    h = h or int(size * 1.7)
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=bg)
    x = padx
    if dot:
        d.ellipse((padx - 4, h / 2 - 8, padx + 12, h / 2 + 8), fill=dot[:3] + (int(255 * dot_alpha),))
        x += 26
    d.text((x, h / 2), text, font=f, fill=fg, anchor='lm')
    return im


def role_card(head, line, head_bg, bg=CARD, w=478):
    """storyboard render_v2.role_card"""
    im = Image.new('RGBA', (w, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, 149), radius=20, fill=bg + (255,))
    f1 = font('Heavy', 36)
    hw = f1.getlength(head) + 40
    d.rounded_rectangle((22, 22, 22 + hw, 72), radius=25, fill=head_bg)
    d.text((22 + hw / 2, 47), head, font=f1, fill=(255, 255, 255), anchor='mm')
    d.text((24, 112), line, font=font('Heavy', 56), fill=INK, anchor='lm')
    return im


def scissors(s=46):
    im = Image.new('RGBA', (s * 2, s * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((s * 0.2, s * 1.1, s * 0.8, s * 1.7), outline=RED, width=7)
    d.ellipse((s * 1.2, s * 1.1, s * 1.8, s * 1.7), outline=RED, width=7)
    d.line((s * 0.7, s * 1.15, s * 1.35, s * 0.1), fill=RED, width=8)
    d.line((s * 1.3, s * 1.15, s * 0.65, s * 0.1), fill=RED, width=8)
    return im.resize((s, s), Image.LANCZOS)


def cover(im, w, h):
    s = max(w / im.width, h / im.height)
    r = im.resize((int(im.width * s + 0.5), int(im.height * s + 0.5)), Image.LANCZOS)
    x0, y0 = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x0, y0, x0 + w, y0 + h))


def frame_at(video, t, fps=30):
    return Image.fromarray(grab(video, int(round(t * fps)), fps=fps)).convert('RGBA')


class Shot18:
    def __init__(self, faces):
        self.host = Host(WORK / 'plate18.png')
        pl = cv2.cvtColor(cv2.imread(str(WORK / 'plate18.png')), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        self.plate = pl
        # where the room plate can be shown during open / close: really seen pixels plus a 45 px band around them
        # (the thin guard band next to the presenter's outline); the big never-seen block behind his torso stays yellow
        seen = cv2.imread(str(WORK / 'plate18_seen.png'), 0)
        ok = cv2.dilate(seen, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (91, 91)))
        self.room_ok = cv2.GaussianBlur(ok.astype(np.float32) / 255.0, (0, 0), 10)
        self.yellow = to_f(paper(HALF, H, tone=(255, 214, 10), seed=18, grain=3, blotch=4))
        fr = [v2_src_frame(k) for k in range(F0, F1)]
        fb = np.array([faces[f][0] for f in fr], np.float32)
        cx = float(np.median((fb[:, 0] + fb[:, 2]) / 2))
        fy0 = float(np.median(fb[:, 1]))
        # face centre at x 250 (not 270): the presenter leans +-60 px; at 250 their face box + 12 px stays left of the divider
        # (x 536) and inside the frame in every frame of the shot
        self.M = np.float32([[S18, 0, 250 - cx * S18], [0, S18, 330 - fy0 * S18]])
        ramp = np.clip((H - 1 - np.arange(H, dtype=np.float32)) / 90.0, 0, 1)   # fade the body out above its frame cut
        self.bottom_ramp = ramp[:, None]
        # workbench thumbnails (real demo frames, storyboard 0.1 table)
        vt = [frame_at(DEMO_V, 3.4), frame_at(DEMOS / 'kepu/kepu_demo.mp4', 20.0), frame_at(DEMOS / 'faceless/faceless_demo.mp4', 12.8),
              frame_at(DEMO_V, 9.6)]
        widths = [96, 70, 110, 64]
        vy0, vy1 = LANES['V']
        self.clips = [cover(im, w - 4, vy1 - vy0 - 8) for im, w in zip(vt, widths)]
        self.clip_w = widths
        self.static = self._static_panel()
        self.left_a = role_card('你', '创意', INK)
        self.left_b = role_card('你', '创意 + 拍摄', INK)
        self.right_a = role_card('Agent', '剪辑', BLUE, bg=(255, 244, 190))
        self.right_b = role_card('Agent', '剪辑 + 包装', BLUE, bg=(255, 244, 190))
        self.scissor = scissors(46)
        rng = np.random.default_rng(7)
        xs = list(range(X0, TRACK_X1 - 2, 5))
        self.wave = [(xx, (0.25 + 0.75 * abs(math.sin(i * 0.23)) * rng.uniform(0.4, 1.0))) for i, xx in enumerate(xs)]

    # ---------------------------------------------------------------- right panel
    def _static_panel(self):
        im = Image.new('RGBA', (HALF, H), PANEL_BG + (255,))
        d = ImageDraw.Draw(im)
        px, py, pw, ph = PREVIEW
        d.rounded_rectangle((px - 6, py - 6, px + pw + 6, py + ph + 6), radius=18, fill=(52, 53, 58))
        d.text((px, 172), '预览', font=font('Bold', 28), fill=(170, 172, 180), anchor='lm')
        d.text((px, TL_LABEL_Y), '时间线', font=font('Bold', 28), fill=(170, 172, 180), anchor='lm')
        for name, (y0, y1) in LANES.items():
            d.rounded_rectangle((px, y0, HALF - 28, y1), radius=8, fill=(42, 43, 48))
            d.text((px + 12, (y0 + y1) / 2), name, font=font('Heavy', 22), fill=(120, 122, 130), anchor='lm')
        return im

    def panel(self, t, preview_rgb, qa):
        im = self.static.copy()
        d = ImageDraw.Draw(im)
        boxes = qa.setdefault('boxes', {})
        px, py, pw, ph = PREVIEW
        if preview_rgb is not None:
            pv = Image.fromarray(preview_rgb).convert('RGBA')
            im.paste(pv, (px, py), rrect_mask(pw, ph, 12))
        blink = 0.35 + 0.65 * (0.5 + 0.5 * math.cos(2 * math.pi * 1.2 * t))
        rec = pill('自动剪辑中', size=26, bg=(56, 58, 64, 255), fg=(235, 235, 240), dot=(80, 220, 120), padx=14, dot_alpha=blink)
        im.alpha_composite(rec, (HALF - rec.width - 28, 150))
        track_w = TRACK_X1 - X0
        # ---- V lane: clips, a dead-air piece cut out on the source's jump cut, ripple
        vy0, vy1 = LANES['V']
        cut_p = prog(t, CUT_T, CUT_T + 0.20)                 # dead-air piece drops out
        rip = e_io(prog(t, CUT_T + 0.16, CUT_T + 0.42))       # clips to the right close the gap
        dead_w = 40
        x = X0
        for i, (clip, cw) in enumerate(zip(self.clips, self.clip_w)):
            if i == 1:
                # dead air (a grey striped piece) between clip 1 and 2, before the cut
                if cut_p < 1:
                    da = Image.new('RGBA', (dead_w - 4, vy1 - vy0 - 8), (74, 76, 82, 255))
                    dd = ImageDraw.Draw(da)
                    for k in range(-40, 40, 9):
                        dd.line((k, da.height, k + da.height, 0), fill=(96, 98, 104, 255), width=3)
                    if t >= CUT_T:
                        da = da.resize((da.width, max(1, int(da.height * (1 - 0.6 * cut_p)))), Image.LANCZOS)
                        da.putalpha(da.split()[3].point(lambda v: int(v * (1 - cut_p))))
                    im.alpha_composite(da, (int(x + 2), int(vy0 + 4 + (vy1 - vy0 - 8 - da.height) / 2)))
                x += (dead_w + 6) * (1 - rip)
            im.paste(clip, (int(round(x + 2)), vy0 + 4), rrect_mask(clip.width, clip.height, 6))
            x += cw + 6
        cut_x = X0 + self.clip_w[0] + 3
        if CUT_T - 0.18 <= t:
            # scissors come down onto the cut, snip, then lift away; a red mark stays on the joint
            u_dn = e_out(prog(t, CUT_T - 0.18, CUT_T), 3)
            u_up = e_in(prog(t, CUT_T + 0.55, CUT_T + 0.85), 2)
            sy = vy0 - 58 - 60 * (1 - u_dn) - 80 * u_up
            sa = (1 - u_up)
            if sa > 0:
                sc = self.scissor.copy()
                sc.putalpha(sc.split()[3].point(lambda v: int(v * sa)))
                im.alpha_composite(sc, (int(cut_x - 23), int(sy)))
            if t >= CUT_T:
                flash = 1 - prog(t, CUT_T, CUT_T + 0.3)
                d.line((cut_x, vy0 - 16, cut_x, vy1 + 16), fill=RED + (255,), width=5)
                if cut_p < 1:
                    d.line((cut_x + dead_w + 6, vy0 - 16, cut_x + dead_w + 6, vy1 + 16), fill=RED + (int(255 * (1 - rip)),), width=5)
                if flash > 0:
                    d.rectangle((cut_x - 6, vy0 - 18, cut_x + 6, vy1 + 18), outline=(255, 120, 100, int(200 * flash)), width=2)
        boxes['wb_cut'] = [HALF + int(cut_x) - 23, vy0 - 140, HALF + int(cut_x) + 23, vy1 + 16]
        # ---- FX lane: one block from the start, three more grow in with the chips
        fy0, fy1 = LANES['FX']
        blocks = [((0.02, 0.18), (255, 214, 10), 1.0)]
        for name, col, key, span in CHIPS:
            blocks.append((span, col, e_out(prog(t, T[key], T[key] + 0.18), 3)))
        for (a, b), col, g in blocks:
            if g <= 0:
                continue
            ax = X0 + a * track_w
            bx = ax + (b - a) * track_w * g
            d.rounded_rectangle((ax, fy0 + 6, max(ax + 2, bx), fy1 - 6), radius=6, fill=col + (255,))
        # ---- playhead + audio lane filled up to it
        ph_x = X0 + track_w * lerp(0.30, 0.66, prog(t, F0 / FPS, F1 / FPS))
        ay0, ay1 = LANES['A']
        mid = (ay0 + ay1) / 2
        for xx, amp in self.wave:
            live = 1.0 + (0.18 * math.sin(t * 17 + xx * 0.3) if abs(xx - ph_x) < 30 else 0)
            hgt = amp * (ay1 - ay0) * 0.42 * live
            col = (110, 200, 150, 255) if xx <= ph_x else (64, 100, 84, 255)
            d.line((xx, mid - hgt, xx, mid + hgt), fill=col, width=3)
        ty = TL_LABEL_Y
        d.line((ph_x, ty + 26, ph_x, ay1 + 8), fill=(255, 255, 255, 255), width=3)
        d.polygon([(ph_x - 12, ty + 22), (ph_x + 12, ty + 22), (ph_x, ty + 38)], fill=(255, 255, 255, 255))
        # ---- chips pop one by one
        cx = px
        for name, col, key, span in CHIPS:
            c = pill(name, size=26, fg=INK, bg=col + (255,), padx=16)
            s = pop(t, T[key], 0.24, 0.16)
            if s > 0:
                cs = c.resize((max(1, int(c.width * s)), max(1, int(c.height * s))), Image.LANCZOS)
                im.alpha_composite(cs, (int(cx + c.width / 2 - cs.width / 2), int(CHIPS_Y + c.height / 2 - cs.height / 2)))
                boxes[f'chip_{name}'] = [HALF + int(cx), CHIPS_Y, HALF + int(cx + c.width), CHIPS_Y + c.height]
            cx += c.width + 12
        return im

    # ---------------------------------------------------------------- frame
    def split_L(self, k):
        if k <= OPEN[1]:
            return e_io(prog(k, OPEN[0], OPEN[1]))
        if k >= CLOSE[0]:
            return 1 - e_io(prog(k, CLOSE[0], CLOSE[1]))
        return 1.0

    def frame(self, k, src_u8, matte_u8, preview_rgb, qa):
        t = k / FPS
        L = self.split_L(k)
        if L <= 0:
            qa['layout'] = 'raw'
            return src_u8.copy()
        boxes = qa.setdefault('boxes', {})
        M = (np.float32([[1, 0, 0], [0, 1, 0]]) * (1 - L) + self.M * L).astype(np.float32)
        xd = lerp(W, HALF, L)                                  # divider x
        # background: yellow half (extends to the divider while it moves), the room fading out on it
        canvas = np.zeros((H, W, 3), np.float32)
        yel = np.tile(self.yellow, (1, 2, 1))
        canvas[:] = yel
        if L < 1:
            # the room fades into the yellow; only where the clean plate was really seen (the inpainted part of the
            # plate, always behind the presenter, would show as colour blocks once they shrink), outside the frame: yellow
            room = warp_affine(self.plate, M, interp=cv2.INTER_LINEAR)
            seen = warp_affine(self.room_ok, M, interp=cv2.INTER_LINEAR)
            ra = ((1 - L) * seen)[..., None]
            canvas = canvas * (1 - ra) + room * ra
        P, a = self.host.premult(src_u8, matte_u8)
        ramp = 1 - L * (1 - self.bottom_ramp)                  # the frame-bottom fade grows in with the split
        a = a * ramp
        P = P * ramp[..., None]
        Pw, aw = warp_affine(P, M), warp_affine(a, M)
        canvas = canvas * (1 - aw[..., None]) + Pw
        qa['person_M'] = M.tolist()
        # left role card (创意 -> 创意 + 拍摄), fades with the close
        ca = clamp01((L - 0.55) / 0.45) if k >= CLOSE[0] else 1.0     # gone before the presenter grows back into its place
        if t >= T['chuangyi'] - 0.02:
            s = pop(t, T['chuangyi'] - 0.02, 0.28, 0.05)
            sw = prog(t, T['paishe'] - 0.02, T['paishe'] + 0.08)
            bump = 1 + 0.04 * math.sin(math.pi * prog(t, T['paishe'] - 0.02, T['paishe'] + 0.22))
            card = self.left_b if sw >= 1 else (self.left_a if sw <= 0 else Image.blend(self.left_a, self.left_b, sw))
            rgb, al = affine_elem(card, scale=s * bump, cx=31 + card.width / 2, cy=1136 + card.height / 2, alpha=ca)
            darken(canvas, soft_shadow(al, blur=12, alpha=0.35))
            over_pm(canvas, rgb, al)
            boxes['role_you'] = elem_bbox(al)
        # right panel (workbench) slides in from the right edge, the divider rides its left edge
        pan = self.panel(t, preview_rgb, qa)
        if t >= T['jianji'] - 0.02:
            s = pop(t, T['jianji'] - 0.02, 0.28, 0.05)
            sw = prog(t, T['baozhuang'] - 0.02, T['baozhuang'] + 0.08)
            bump = 1 + 0.04 * math.sin(math.pi * prog(t, T['baozhuang'] - 0.02, T['baozhuang'] + 0.22))
            card = self.right_b if sw >= 1 else (self.right_a if sw <= 0 else Image.blend(self.right_a, self.right_b, sw))
            cs = card.resize((max(1, int(card.width * s * bump)), max(1, int(card.height * s * bump))), Image.LANCZOS)
            sh, pad = shadow_of(cs, blur=12, alpha=0.35)
            cx0, cy0 = 31 + card.width / 2 - cs.width / 2, 1136 + card.height / 2 - cs.height / 2
            pan.alpha_composite(sh, (int(cx0 - pad + 3), int(cy0 - pad + 7)))
            pan.alpha_composite(cs, (int(cx0), int(cy0)))
            boxes['role_agent'] = [HALF + int(cx0), int(cy0), HALF + int(cx0) + cs.width, int(cy0) + cs.height]
        pf = np.asarray(pan.convert('RGB'), np.float32) / 255.0
        x0 = int(round(xd))
        if x0 < W:
            canvas[:, x0:] = pf[:, :W - x0]
        dv0, dv1 = int(round(xd)) - 4, int(round(xd)) + 4
        if dv0 < W:
            canvas[:, max(0, dv0):min(W, dv1)] = 1.0
        boxes['divider'] = [dv0, 0, dv1 - 1, H - 1]
        qa['panel_x'] = x0
        # keep the moved-panel boxes honest during open / close
        if x0 != HALF:
            for n in list(boxes):
                if n.startswith(('chip_', 'wb_', 'role_agent')) and boxes[n]:
                    b = boxes[n]
                    boxes[n] = [b[0] - HALF + x0, b[1], b[2] - HALF + x0, b[3]]
        return to_u8(canvas)


def preview_crop(vlog_u8):
    """vlog frame (1080x1920) -> the preview window (484x540): rows PREVIEW_SRC_Y, area-resampled"""
    y0, y1 = PREVIEW_SRC_Y
    c = vlog_u8[y0:y1]
    return cv2.resize(c, (PREVIEW[2], PREVIEW[3]), interpolation=cv2.INTER_AREA)
