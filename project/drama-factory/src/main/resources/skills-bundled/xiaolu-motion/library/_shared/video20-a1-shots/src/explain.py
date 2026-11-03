"""Shots 07 / 08 / 09: demo explained on a taped card (left, 0.64x, storyboard shot7 / shot9 layout), the presenter in the PiP.

Every shot: frame 0 is the presenter's untouched full frame; the whole frame shrinks into the PiP box (14 frames), the demo card
flies in from the left, the '成片 · xx' tag pops; at the end the card flies out while the PiP grows back to the full
frame (14 frames), the last frames are the presenter's untouched full frame again.  The demo's own sound is muted by A0; its
subtitles stay inside the card at 0.64x (never at full size next to the main subtitle).
"""
import math

import numpy as np
from PIL import Image, ImageDraw

import a1lib as L
from a1paths import *  # noqa
import sb_lib as SB
import v2_parts as V


class TimeMap:
    """v2 frame -> demo frame, piecewise: list of (f0, f1, kind, a) with kind 'play' (demo = F - a) or 'hold' (demo = a)"""

    def __init__(self, pieces, lo=None, hi=None):
        self.pieces, self.lo, self.hi = pieces, lo, hi

    def __call__(self, F):
        for f0, f1, kind, a in self.pieces:
            if f0 <= F <= f1:
                d = F - a if kind == 'play' else a
                break
        else:
            raise ValueError(F)
        if self.lo is not None:
            d = max(self.lo, d)
        if self.hi is not None:
            d = min(self.hi, d)
        return d

    def used(self, F0, F1):
        """list of (demo_first, demo_last) runs actually shown for v2 frames F0..F1"""
        runs, cur = [], None
        for F in range(F0, F1 + 1):
            d = self(F)
            if cur and (d == cur[1] or d == cur[1] + 1):
                cur[1] = d
            else:
                if cur:
                    runs.append(tuple(cur))
                cur = [d, d]
        runs.append(tuple(cur))
        return runs


class ExplainShot:
    """common machinery; subclasses set the constants and the demo time map"""
    key = ''
    F0 = F1 = 0                 # [F0, F1) v2 frames
    demo_path = None
    kind = ''                   # tag text
    seed = 22
    shrink_start = 0            # first frame of the 14-frame shrink (e > 0)
    card_in = 0                 # first frame of the card fly-in
    exit_start = 0              # first frame of the 14-frame grow back to the full frame (card slides out under it)
    pip_frames = 14

    def __init__(self):
        self.src = L.Source(SRC)
        self.demo = L.Source(self.demo_path)
        self.bg = L.paper_bg(self.seed)
        self.card = L.DemoCard(self.seed)
        self.tag = L.to_pm(V.demo_tag(self.kind, False))
        self.win = self.pip_window()
        self.pip = L.Pip(self.win)

    # ------------------------------------------------------------ geometry
    def pip_window(self):
        """one fixed PiP window per shot (no jitter): median face + highest hair top over the shot's frames"""
        fs, tops = [], []
        for F in range(self.F0, self.F1, 6):
            sf = src_frame(F)
            face, _ = L.face_at(sf)
            fs.append(face)
        med = [int(np.median([f[k] for f in fs])) for k in range(4)]
        for F in range(self.F0, self.F1, 24):
            sf = src_frame(F)
            face, _ = L.face_at(sf)
            tops.append(L.head_top(self.src.get(sf), face))
        self.src.close()
        self.src = L.Source(SRC)
        self.head_top = int(min(tops))
        x0, y0 = L.pip_window(med, self.head_top)
        # every face of the shot must sit inside the window with >= 40 px margin (source px)
        for f in fs:
            assert f[0] >= x0 + 40 and f[2] <= x0 + 900 - 40 and f[1] >= y0 + 40 and f[3] <= y0 + 1260 - 40, (self.key, f, x0, y0)
        return x0, y0

    # ------------------------------------------------------------ timing curves
    def pip_e(self, F):
        """1 = settled in the box, 0 = full frame (shrink: shrink_start .. +13, grow: exit_start .. +13)"""
        n = self.pip_frames
        if F < self.shrink_start:
            return 0.0
        if F >= self.exit_start:
            return 1 - L.cubic_inout((F - self.exit_start + 1) / n)
        return L.cubic_inout((F - self.shrink_start + 1) / n)

    def card_pose(self, F):
        """(dx, dy, drot) of the demo card, None when not drawn"""
        if F < self.card_in:
            return None
        if F >= self.exit_start:
            u = L.cubic_in((F - self.exit_start + 1) / self.pip_frames)
            if u >= 1:
                return None
            return (-620 * u, 120 * u, -9 * u)
        u = (F - self.card_in + 1) / 13
        if u >= 1:
            return (0.0, 0.0, 0.0)
        k = L.back_out(u, 1.25)
        return (-820 * (1 - k), 160 * (1 - k), -11 * (1 - k))

    def tag_scale(self, F):
        a = self.card_in + 13
        if F < a or F >= self.exit_start + 5:
            return 0.0
        if F >= self.exit_start:
            return 1 - L.cubic_in((F - self.exit_start + 1) / 5)
        return L.back_out((F - a + 1) / 6, 1.7)

    # ------------------------------------------------------------ per-frame content hooks
    def demo_frame(self, F):
        raise NotImplementedError

    def content(self, F, demo_rgb):
        """card content (691 x 1228 rgb); subclasses may add local emphasis"""
        return L.demo_content(demo_rgb, self.card.cw, self.card.ch)

    def pip_cover(self, F):
        return None

    def no_live(self, F):
        return False

    # ------------------------------------------------------------ frame
    def frame(self, F):
        sf = src_frame(F)
        live = self.src.get(sf)
        info = {'F': F, 'src': sf, 'items': []}
        e = self.pip_e(F)
        if e <= 0.0001:
            info['full'] = True
            info['live_rect'] = [0, 0, W, H]
            info['tr'] = [1.0, 0.0, 0.0]
            return live.copy(), info
        cv = self.bg.copy()
        pose = self.card_pose(F)
        if pose is not None:
            d = self.demo_frame(F)
            info['demo'] = d
            cont = self.content(F, self.demo.get(d))
            bb = self.card.draw(cv, cont, *pose)
            info['items'].append(('demo_card', bb, 'card'))
        ts = self.tag_scale(F)
        if ts > 0.001:
            cx, cy = 752 + self.tag.shape[1] / 2, 196 + self.tag.shape[0] / 2
            bb = L.place(cv, self.tag, cx, cy, scale=ts)
            info['items'].append(('demo_tag', bb, 'text'))
        rect, tr = self.pip.draw(cv, live, e, cover=self.pip_cover(F))
        info['live_rect'] = [round(v) for v in rect]
        info['tr'] = [round(v, 5) for v in tr]
        info['e'] = round(e, 4)
        info['items'].append(('pip', [PIP_BOX_OUT[0], PIP_BOX_OUT[1] - 22, PIP_BOX_OUT[2], PIP_BOX_OUT[3]] if e > 0.999 else rect, 'pip'))
        info['no_live'] = self.no_live(F)
        return L.to_u8(cv), info

    def close(self):
        self.src.close()
        self.demo.close()


PIP_BOX_OUT = L.PIP_OUT


# ================================================================ shot 07: vlog, re-cut to the words
class Shot07(ExplainShot):
    """这是vlog，转场多一点，字幕做成贴纸，时间、天气、心情这些小卡片，它会自己点缀上去  (v2 27.70-35.50)

    word onsets (v2 s, source energy envelope, whisper ~0.1-0.3 s early here): 转 28.68, 场 28.89, 字 29.73,
    贴 30.23, 时 31.04, 天 31.70, 心 32.34, 点缀 34.54.  vlog_demo.mp4 events (frames): page flip 311-314,
    typing-page sticker subtitle pops 327-330 (敲 334-337, 338-341, 342-345), sunset page landed 555, 17:29 time
    card pops 559-561, 晴 weather card pops 439-441 (strip slapped 434-435), 惬意 mood card pops 589-591,
    sparkles ~615, night page (T10) starts 664.
    Avoids the other shots' demo times: 0.30-3.30 (insert), 9.60 (shot 1), 11.50 (shot 18 thumb, the 3rd 敲),
    17.80 (shot 18 preview), 24.00 (10a), 26.40-26.90 (17).
    """
    key, F0, F1 = '07', 831, 1065
    demo_path, kind, seed = VLOG, 'vlog', 22
    shrink_start, card_in, exit_start = 836, 840, 1045

    tmap = TimeMap([
        (831, 863, 'play', 553),     # cup page 9.73-10.33 s (after shot 1's 9.60 still), clamped >= 292 below
        (864, 867, 'play', 553),     # page flip 311-314  <- 转场 (28.68 / 28.89)
        (868, 879, 'hold', 315),     # typing page lands, holds
        (880, 906, 'play', 565),     # 315-341: sticker subtitle pops 327 @ 892 <- 字 29.73; 敲 敲 (stops before 11.50)
        (907, 925, 'hold', 555),     # sunset page (landed), holds
        (926, 944, 'play', 371),     # 555-573: 17:29 time card pops 559-561 @ 930-932 <- 时 31.04
        (945, 957, 'play', 511),     # 434-446: strip slaps, 晴 pops 439-441 @ 950-952 <- 天 31.70
        (958, 963, 'hold', 446),
        (964, 1064, 'play', 380),    # 584-663: 惬意 pops 589-591 @ 969-971 <- 心 32.34; sparkles; stops before T10
    ], lo=292, hi=663)              # (663 is reached at 1043; from 1045 the presenter grows back over the card)

    # local magnification of the element that answers the word (demo px box, anchor, peak m, rise frame, fall end)
    ZOOMS = [
        ('sticker_subtitle', (220, 1460, 760, 1605), (490, 1532), 1.32, 893, 905),
        ('time_card', (40, 155, 430, 380), (45, 300), 1.5, 933, 944),
        ('weather_card', (90, 705, 320, 935), (95, 820), 1.5, 953, 963),
        ('mood_card', (685, 240, 972, 420), (972, 330), 1.5, 972, 992),
    ]

    def demo_frame(self, F):
        return self.tmap(F)

    def zoom_m(self, F, z):
        name, box, anc, m, a, b = z
        if F < a or F > b:
            return 1.0
        up = L.back_out((F - a + 1) / 5, 1.6)
        down = 1 - L.cubic_inout((F - (b - 4)) / 4) if F > b - 4 else 1.0
        return 1 + (m - 1) * min(up, 1.25) * down

    def content(self, F, demo_rgb):
        c = L.demo_content(demo_rgb, self.card.cw, self.card.ch)
        s = self.card.cw / W
        for z in self.ZOOMS:
            m = self.zoom_m(F, z)
            if m > 1.001:
                name, box, anc, _, _, _ = z
                c = L.local_zoom_anchor(c, [v * s for v in box], [v * s for v in anc], m)
        return c.astype(np.uint8) if c.dtype != np.uint8 else c


SHOTS = {'07': Shot07}


# ================================================================ shot 08: kepu, the diagram drawn on the words
def coons_patch(img, box, band=6, smooth=41):
    """clean plate for box (x0, y0, x1, y1) of img: Coons patch from the smoothed colours just outside its 4 sides"""
    x0, y0, x1, y1 = box
    f = img.astype(np.float32)
    top = f[y0 - band:y0, x0:x1].mean(0)
    bot = f[y1:y1 + band, x0:x1].mean(0)
    lef = f[y0:y1, x0 - band:x0].mean(1)
    rig = f[y0:y1, x1:x1 + band].mean(1)
    k = np.ones(smooth, np.float32) / smooth

    def sm(a):
        pad = np.pad(a, ((smooth // 2, smooth // 2), (0, 0)), mode='edge')
        return np.stack([np.convolve(pad[:, c], k, mode='valid') for c in range(3)], 1)
    top, bot, lef, rig = sm(top), sm(bot), sm(lef), sm(rig)
    h, w = y1 - y0, x1 - x0
    u = (np.arange(w, dtype=np.float32) + 0.5)[None, :, None] / w
    v = (np.arange(h, dtype=np.float32) + 0.5)[:, None, None] / h
    TL, TR, BL, BR = (top[0] + lef[0]) / 2, (top[-1] + rig[0]) / 2, (bot[0] + lef[-1]) / 2, (bot[-1] + rig[-1]) / 2
    P = ((1 - v) * top[None] + v * bot[None] + (1 - u) * lef[:, None] + u * rig[:, None]
         - ((1 - u) * (1 - v) * TL + u * (1 - v) * TR + (1 - u) * v * BL + u * v * BR))
    return np.clip(P + 0.5, 0, 255).astype(np.uint8)


class Shot08(ExplainShot):
    """而这是科普，你讲到的原理会变成图和动画，跟着你的内容一步步画出来  (v2 35.50-41.97)

    The presenter stays full frame through 而这是科普 (35.68-36.74), shrinks into the PiP on 科普.  kepu_demo.mp4 diagram
    section (§0.1: 4.95-11.42 s); the empty diagram waits until 图 (38.53, words_v2.json), then the kepu's own
    drawing plays step by step on the words, idle stretches cut out, and its last touch (越厉害 + glow at the blue
    end, frames 318-324) lands on 画 of 画出来 (41.23).  The kepu's own PiP (a second, smaller presenter view, demo px
    x 652-968, y 950-1370 + glow) is replaced by a clean plate of the dark stage, so only the main presenter view is visible.
    """
    key, F0, F1 = '08', 1065, 1259
    demo_path, kind, seed = KEPU, '科普', 24
    shrink_start, card_in, exit_start = 1081, 1084, 1245
    PLATE_BOX = (606, 918, 1012, 1403)       # demo PiP incl. its glow; dark stage around it (measured on frame 300)

    tmap = TimeMap([
        (1065, 1155, 'hold', 162),   # empty diagram (162, ray starts at 163) + subtitle of 164 (fully faded in)
        (1156, 1173, 'play', 993),   # 163-180: white sunlight ray drawn into the atmosphere  <- 图 38.53
        (1174, 1191, 'play', 969),   # 205-222: air molecules pop one by one (207..219)       <- 和动画 38.84-39.3
        (1192, 1212, 'play', 960),   # 232-252: scattering burst (234) + 散射开                <- 跟 39.78
        (1213, 1236, 'play', 950),   # 263-286: flip to the spectrum chart (266-273), curve drawn 276-285 <- 一步步 40.77-41.2
        (1237, 1258, 'play', 919),   # 318-339 (held at 329): 越厉害 + glow + up arrow         <- 画 41.23
    ], hi=329)

    HOLD_SPLIT = 915                          # dark gap under the diagram card: rows above from 162, below from 164

    def __init__(self):
        super().__init__()
        ref = self.demo.get(300)
        self.plate = coons_patch(ref, self.PLATE_BOX)
        top = self.demo.get(162).copy()
        top[self.HOLD_SPLIT:] = self.demo.get(164)[self.HOLD_SPLIT:]
        self.hold_img = top
        self.demo.close()
        self.demo = L.Source(self.demo_path)

    def demo_frame(self, F):
        return self.tmap(F)

    def frame(self, F):
        self._F = F
        return super().frame(F)

    def content(self, F, demo_rgb):
        x0, y0, x1, y1 = self.PLATE_BOX
        f = (self.hold_img if F <= 1155 else demo_rgb).copy()
        f[y0:y1, x0:x1] = self.plate
        return L.demo_content(f, self.card.cw, self.card.ch)


# ================================================================ shot 09: faceless, the PiP closes like an eyelid
class Shot09(ExplainShot):
    """如果你不想露脸，其实也可以，只要放上字和动画，配上你的解说，一条完整的视频就出来了  (v2 41.97-49.67)

    faceless_demo.mp4 11.00-18.70 s played 1:1 (§0.1).  不想露脸 42.53-43.15: the PiP closes like an eyelid (two
    paper flaps meet at eye level, 43.00-43.37), the 不露脸 label lands on it; 配 of 配上你的解说 (46.42) snaps it
    open (opening starts 46.30).  Fully closed 43.37-46.27 = 2.93 s (<= 3 s without live footage).
    """
    key, F0, F1 = '09', 1259, 1490
    demo_path, kind, seed = FACELESS, '不露脸', 23
    shrink_start, card_in, exit_start = 1262, 1265, 1476
    CLOSE0, CLOSED, OPEN0, OPEN1 = 1290, 1301, 1389, 1394    # lids move 1290-1301, closed 1301-1388, open 1389-1394

    def demo_frame(self, F):
        return F - 929           # 1:1, v2 41.967 s = faceless 11.00 s

    def closure(self, F):
        if F < self.CLOSE0 or F > self.OPEN1:
            return 0.0
        if F < self.CLOSED:
            return L.cubic_in((F - self.CLOSE0 + 1) / (self.CLOSED - self.CLOSE0 + 1)) ** 0.8
        if F < self.OPEN0:
            return 1.0
        return 1 - L.cubic_out((F - self.OPEN0 + 1) / (self.OPEN1 - self.OPEN0 + 1))

    def no_live(self, F):
        return self.closure(F) >= 0.9999

    def eye_y(self, F):
        sf = src_frame(min(max(F, self.CLOSE0), self.CLOSED))
        face, _ = L.face_at(sf)
        eyes = face[1] + 0.365 * (face[3] - face[1])
        return (eyes - self.win[1]) * 420 / 1260

    def pip_cover(self, F):
        c = self.closure(F)
        lab_s = 0.0
        if self.CLOSED <= F < self.OPEN0:
            lab_s = L.back_out((F - self.CLOSED + 1) / 6, 1.8)
        elif self.OPEN0 <= F < self.OPEN0 + 3:
            lab_s = 1 - (F - self.OPEN0 + 1) / 3
        if c <= 0.0005 and lab_s <= 0:
            return None
        ey = self.eye_y(F)
        arrows_a = 0.0 if c >= 0.999 or F >= self.OPEN0 else min(1.0, c * 4)

        def cover(content):
            content = content.convert('RGBA')
            h = content.height
            top_edge = c * ey
            bot_edge = h - c * (h - ey)
            lay = Image.new('RGBA', content.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            flap = (238, 230, 214, 255)
            if top_edge > 0.5:
                d.rectangle((0, 0, content.width, top_edge), fill=flap)
                d.line((0, top_edge, content.width, top_edge), fill=(180, 170, 150, 255), width=3)
            if bot_edge < h - 0.5:
                d.rectangle((0, bot_edge, content.width, h), fill=flap)
                d.line((0, bot_edge, content.width, bot_edge), fill=(180, 170, 150, 255), width=3)
            if arrows_a > 0:
                a = int(255 * arrows_a)
                col = SB.INK + (a,)
                for x in (95, 205):
                    if top_edge > 80:
                        d.line((x, top_edge - 70, x, top_edge - 22), fill=col, width=5)
                        d.polygon([(x - 12, top_edge - 34), (x + 12, top_edge - 34), (x, top_edge - 18)], fill=col)
                    if bot_edge < h - 80:
                        d.line((x, bot_edge + 22, x, bot_edge + 70), fill=col, width=5)
                        d.polygon([(x - 12, bot_edge + 34), (x + 12, bot_edge + 34), (x, bot_edge + 18)], fill=col)
            content.alpha_composite(lay)
            if lab_s > 0.01:
                kl = SB.label([('不露脸', True)], size=40, pad=(14, 6), radius=10, bg=SB.CARD)
                w_, h_ = max(1, int(kl.width * lab_s)), max(1, int(kl.height * lab_s))
                kl = kl.resize((w_, h_), Image.LANCZOS)
                content.alpha_composite(kl, ((content.width - w_) // 2, int(ey + 92 - h_ / 2 + 18)))
            return content
        return cover


SHOTS.update({'08': Shot08, '09': Shot09})
