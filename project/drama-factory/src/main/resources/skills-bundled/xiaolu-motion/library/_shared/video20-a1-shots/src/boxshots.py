"""Shots 10 (full-screen paper box, two parts) and 11 (the closed box tossed to 'your Agent' on the presenter's live frame).

Geometry, colours, labels and contents are the storyboard's own (v2_parts.py = verbatim render_v2.py parts:
shot10a / shot10b / shot11); this module animates them.
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import a1lib as L
from a1paths import *  # noqa
import sb_lib as SB
import v2_parts as V
from v2_parts import KRAFT_F, KRAFT_S, KRAFT_T, KRAFT_IN, Obl, draw_poly
import assets as A

INK = SB.INK


def _mix(c0, c1, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c0, c1))


def bezier(p0, p1, p2, p3, t):
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def dashed_path(d, pts, color, width=5, dash=18, gap=14):
    """dashes along a polyline"""
    acc, on = 0.0, True
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        seg_len = math.hypot(x1 - x0, y1 - y0)
        pos = 0.0
        while pos < seg_len:
            step = min(seg_len - pos, (dash if on else gap) - acc)
            if on:
                a = pos / seg_len
                b = (pos + step) / seg_len
                d.line((x0 + (x1 - x0) * a, y0 + (y1 - y0) * a, x0 + (x1 - x0) * b, y0 + (y1 - y0) * b), fill=color, width=width)
            pos += step
            acc += step
            if acc >= (dash if on else gap) - 1e-6:
                acc, on = 0.0, not on


def arrow_head(d, tip, frm, color, width=5, head=22):
    ang = math.atan2(tip[1] - frm[1], tip[0] - frm[0])
    for s in (-1, 1):
        a = ang + math.pi - s * 0.45
        d.line((tip[0], tip[1], tip[0] + math.cos(a) * head, tip[1] + math.sin(a) * head), fill=color, width=width)


# ================================================================ shot 10
class Shot10:
    """而这些其实都是同一套东西做出来的，它其实就是一个开源的动效库加音效库加风格包  (v2 49.67-57.67)

    words (v2 s, 04_captions/words_v2.json manual anchors): 同 51.00, 做出来的 51.81-52.46, 它其实就是一个开源的
    52.94-54.50, 动效库 54.68, 音效库 55.64, 风格包 56.91 (包 ends 57.40).
    ① 1522-1576: the dotted paper page slides up over the presenter (1522-1529); the vlog / 科普 / 不露脸 frames (§0.1: vlog
       24.00 s, kepu 1.20 s, faceless 21.80 s) fly in from left / top / right along dashed trails and drop into one
       kraft box (sample shot10a); flaps close, tape seals it (clack 1563 = 52.10); page slides away (1570-1576) and
       the presenter is back for 它其实就是一个开源的.
    ② 1633-1726: on 的 of 开源的 the page slides up again with the closed box (1633-1638); it squashes (1638-1639)
       and pops open on 动效库 into the three-tray toolbox of sample shot10b (1640), lid swings back; 动效库 1641 /
       音效库 1669 / 风格包 1707 light up (tray glow, contents rise, label gets its yellow marker); page slides away
       1720-1726.
    The presenter's live footage is fully covered 1530-1569 (1.33 s) and 1639-1719 (2.70 s): each <= 3 s.
    """
    key, F0, F1 = '10', 1490, 1730
    IN1, OUT1 = (1522, 8), (1570, 7)          # (first frame of motion, frames of motion)
    IN2, OUT2 = (1633, 6), (1720, 7)          # ② starts on 的 (54.50): the presenter stays on screen for 它其实就是一个开源
    # name, asset, label, start centre, hover centre (sample 10a), sample rot, first frame, slot
    MINIS = [
        ('vlog', 'mini_vlog', 'vlog', (-240, 640), (190, 672), -18, 1530, 0),
        ('kepu', 'mini_kepu', '科普', (470, -300), (470, 527), 6, 1535, 1),
        ('faceless', 'mini_faceless', '不露脸', (1330, 660), (735, 682), 16, 1540, 2),
    ]
    MINI_FLY = 14
    CLOSE, CLACK = 1553, 1563                  # minis land 1543 / 1548 / 1553 (5-frame stagger: no overlap)
    SQUASH, POP = 1638, 1640
    LIGHT = [('动效库', 1641), ('音效库', 1669), ('风格包', 1707)]     # words_v2: 54.68 / 55.64 / 56.91
    GEO1 = dict(ox=150, oy=1262, Wb=640, Db=360, Hb=330, Ls=230)
    GEO2 = dict(ox=70, oy=1262, Wb=810, Db=330, Hb=300)

    def __init__(self):
        self.src = L.Source(SRC)
        self.quads = {}
        V.set_assets(A.paths())
        self.paper = L.paper_bg(101, tone=(243, 238, 228))
        self.minis = []
        for name, key, lab, start, hover, rot, f0, slot in self.MINIS:
            t = V.thumb(key, 190, 338)
            tagp = V.pill(lab, size=26, bg=INK + (255,), padx=14)
            t2 = Image.new('RGBA', (t.width, t.height + 30), (0, 0, 0, 0))
            t2.alpha_composite(t, (0, 30))
            t2.alpha_composite(tagp, ((t.width - tagp.width) // 2, 0))
            spr = L.to_pm(t2)
            self.minis.append(dict(name=name, spr=spr, sh=L.shadow_pm(spr, 14, 0.3), start=start, hover=hover, rot=rot,
                                   f0=f0, slot=slot))
        lab = V.label([('开源工具', False)], size=64, pad=(26, 10), radius=10, weight_normal='Heavy')
        self.box_label_pm = L.to_pm(SB.rotate(lab, -2))
        self.box_label_sh = L.shadow_pm(self.box_label_pm, 6, 0.25)
        self.burst = L.to_pm(SB.burst(60, 110, n=9, lw=7, a0=200, a1=340))
        self.burst_ring = L.to_pm(SB.burst(90, 150, n=14, lw=7, a0=180, a1=360))
        self.tray_lab = {}
        for name, _ in self.LIGHT:
            off = SB.label([(name, False)], size=66, pad=(22, 10), radius=10, weight_normal='Heavy')
            on = SB.label([(name, True)], size=66, pad=(22, 10), radius=10, weight_key='Heavy')
            assert off.size == on.size, (off.size, on.size)
            self.tray_lab[name] = (L.to_pm(off), L.to_pm(on), L.shadow_pm(L.to_pm(on), 6, 0.25))
        self.contents = self._tray_contents()
        self.glow = L.to_pm(V.glow((260, 200), alpha=170))

    # ------------------------------------------------------------ timing
    def page_offset(self, F):
        """vertical offset of the paper page (0 = full screen), None = page not shown"""
        for (a, n), (b, m) in ((self.IN1, self.OUT1), (self.IN2, self.OUT2)):
            if a <= F < b + m:
                if F < a + n:
                    return H * (1 - L.cubic_out((F - a + 1) / n))
                if F >= b:
                    return H * L.cubic_in((F - b + 1) / m)
                return 0.0
        return None

    def part(self, F):
        return 1 if F < 1600 else 2

    def light(self, F, i):
        return L.clamp((F - self.LIGHT[i][1] + 1) / 4)

    # ------------------------------------------------------------ ① kraft box with four flaps (sample shot10a)
    @staticmethod
    def flap_quads(Wb, Db, Hb, Ls, phis):
        """flaps for angles (back, left, right, front) deg: sample open = (60, 60, 60, -60), closed flat = 180"""
        pb, pl, pr, pf = phis
        c, s = math.cos(math.radians(pb)), math.sin(math.radians(pb))
        back = [(0, Db, Hb), (Wb, Db, Hb), (Wb, Db + Ls * c, Hb + Ls * s), (0, Db + Ls * c, Hb + Ls * s)]
        c, s = math.cos(math.radians(pl)), math.sin(math.radians(pl))
        left = [(0, 0, Hb), (0, Db, Hb), (-Ls * c, Db, Hb + Ls * s), (-Ls * c, 0, Hb + Ls * s)]
        c, s = math.cos(math.radians(pr)), math.sin(math.radians(pr))
        right = [(Wb + Ls * c, 0, Hb + Ls * s), (Wb, 0, Hb), (Wb, Db, Hb), (Wb + Ls * c, Db, Hb + Ls * s)]
        Lf = Ls * 0.55                      # the sample's front flap (0.55 of the others)
        c, s = math.cos(math.radians(pf)), math.sin(math.radians(pf))
        front = [(0, 0, Hb), (Wb, 0, Hb), (Wb, -Lf * c, Hb + Lf * s), (0, -Lf * c, Hb + Lf * s)]
        return back, left, right, front

    def draw_box1(self, lay4, F):
        g = self.GEO1
        P = Obl(g['ox'], g['oy'])
        Wb, Db, Hb, Ls = g['Wb'], g['Db'], g['Hb'], g['Ls']
        if self.part(F) == 2:
            k_side = k_fb = 1.0
        else:
            k_side = L.cubic_inout((F - self.CLOSE + 1) / 6) if F >= self.CLOSE else 0.0
            k_fb = L.cubic_inout((F - self.CLOSE - 3) / 7) if F >= self.CLOSE + 4 else 0.0
        phis = (60 + 120 * k_fb, 60 + 120 * k_side, 60 + 120 * k_side, -60 + 240 * k_fb)
        back, left, right, front = self.flap_quads(Wb, Db, Hb, Ls, phis)
        closing = k_side > 0 or k_fb > 0
        items = []
        im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        if not closing:
            draw_poly(im, P.poly(back), KRAFT_T)
            draw_poly(im, P.poly(left), KRAFT_S)
        draw_poly(im, P.poly([(0, 0, Hb), (Wb, 0, Hb), (Wb, Db, Hb), (0, Db, Hb)]), KRAFT_IN)
        draw_poly(im, P.poly([(0, Db, Hb), (Wb, Db, Hb), (Wb, Db, Hb - 150), (0, Db, Hb - 150)]), (150, 114, 70), outline=None)
        L.blend(lay4, L.to_pm(im), 0, 0)
        if self.part(F) == 1:
            for m in self.minis:
                items += self.draw_mini(lay4, F, m, P, Wb, Db, Hb)
        im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        draw_poly(im, P.poly([(Wb, 0, 0), (Wb, Db, 0), (Wb, Db, Hb), (Wb, 0, Hb)]), KRAFT_S)
        if not closing:
            draw_poly(im, P.poly(right), KRAFT_T)
        draw_poly(im, P.poly([(0, 0, 0), (Wb, 0, 0), (Wb, 0, Hb), (0, 0, Hb)]), KRAFT_F)
        if not closing:
            draw_poly(im, P.poly(front), KRAFT_T)
        else:
            draw_poly(im, P.poly(left), _mix(KRAFT_S, KRAFT_T, k_side))
            draw_poly(im, P.poly(right), KRAFT_T)
            draw_poly(im, P.poly(back), KRAFT_T)
            draw_poly(im, P.poly(front), KRAFT_T)
            kt = 1.0 if self.part(F) == 2 else (L.cubic_out((F - self.CLACK + 1) / 4) if F >= self.CLACK else 0.0)
            if kt > 0:
                d = ImageDraw.Draw(im)
                d.polygon(P.poly([(Wb * 0.45, -2, Hb + 1), (Wb * 0.55, -2, Hb + 1), (Wb * 0.55, Db * kt, Hb + 1),
                                  (Wb * 0.45, Db * kt, Hb + 1)]), fill=(250, 222, 120, 230))
                d.polygon(P.poly([(Wb * 0.45, 0, Hb), (Wb * 0.55, 0, Hb), (Wb * 0.55, 0, Hb - 60 * kt),
                                  (Wb * 0.45, 0, Hb - 60 * kt)]), fill=(250, 222, 120, 230))
        L.blend(lay4, L.to_pm(im), 0, 0)
        fx, fy = P(Wb / 2, 0, Hb * 0.36)
        pulse = 1.0
        if self.part(F) == 1 and self.CLACK <= F < self.CLACK + 8:
            pulse = 1 + 0.10 * math.sin(math.pi * (F - self.CLACK + 1) / 8)
        sh, pad = self.box_label_sh
        L.place(lay4, sh, fx + 3, fy + 7, scale=pulse)
        items.append(('box_label', L.place(lay4, self.box_label_pm, fx, fy, scale=pulse), 'text'))
        items.append(('box', (int(P(-Ls * 0.5, 0, 0)[0]), int(P(0, Db + Ls * 0.5, Hb + Ls * 0.87)[1]),
                              int(P(Wb + Ls * 0.5, Db, 0)[0]), int(P(0, 0, 0)[1])), 'bg'))
        if self.part(F) == 1 and 1530 <= F < 1552:
            a = min(1.0, (F - 1529) / 3) * (1 - L.seg(F, 1546, 1552))
            sc = L.back_out(min(1.0, (F - 1529) / 5), 1.6)
            bb = L.place(lay4, self.burst, 330 + self.burst.shape[1] / 2, 180 + self.burst.shape[0] / 2, scale=sc, opacity=a)
            items.append(('burst', bb, 'fx'))
        return items

    def draw_mini(self, lay4, F, m, P, Wb, Db, Hb):
        """start -> hover (sample 10a position) -> drops into its slot, shrinking (going deeper), hidden by the
        front face drawn afterwards"""
        u = (F - m['f0'] + 1) / self.MINI_FLY
        if u <= 0:
            return []
        tgt = P(Wb * (0.25 + 0.25 * m['slot']), Db * 0.5, Hb)
        p0, hv = m['start'], m['hover']
        c1 = (lerp(p0[0], hv[0], 0.5), min(p0[1], hv[1]) - 80)
        end = (tgt[0], 1050.0)
        items = []
        trail_a = 1.0 if F < self.CLOSE else max(0.0, 1 - (F - self.CLOSE) / 6)
        if trail_a > 0:
            uu = min(u, 1.0)
            pts = [self.mini_pos(p0, c1, hv, end, t)[0] for t in np.linspace(0, uu, 40)]
            if uu >= 1:
                pts = [self.mini_pos(p0, c1, hv, end, t)[0] for t in np.linspace(0, 0.93, 40)]
            if len(pts) > 3:
                im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                d = ImageDraw.Draw(im)
                col = SB.GREY + (int(255 * trail_a),)
                dashed_path(d, pts, col, width=5)
                if uu >= 1:
                    arrow_head(d, pts[-1], pts[-5], col, width=5)
                L.blend(lay4, L.to_pm(im), 0, 0)
        if u >= 1:
            return items
        (x, y), sc = self.mini_pos(p0, c1, hv, end, u)
        rot = m['rot'] * min(1.0, u / 0.62) * (1 - 0.6 * max(0.0, (u - 0.62) / 0.38))
        spr, (sh, pad) = m['spr'], m['sh']
        L.place(lay4, sh, x + 3, y + 7, rot=rot, scale=sc)
        bb = L.place(lay4, spr, x, y, rot=rot, scale=sc)
        self.quads[f'mini_{m["name"]}'] = L.LAST_QUAD
        items.append((f'mini_{m["name"]}', bb, 'overlay'))
        return items

    @staticmethod
    def mini_pos(p0, c1, hv, end, u):
        """centre + scale at progress u: quadratic curve to the hover point (ease out), then drop (ease in)"""
        if u < 0.62:
            t = L.cubic_out(u / 0.62)
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c1[0] + t * t * hv[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c1[1] + t * t * hv[1]
            return (x, y), 1.0
        t = L.cubic_in((u - 0.62) / 0.38)
        return (lerp(hv[0], end[0], t), lerp(hv[1] - 30 * math.sin(math.pi * t), end[1], t)), lerp(1.0, 0.55, t)

    # ------------------------------------------------------------ ② three-tray toolbox (sample shot10b)
    def _tray_contents(self):
        g = self.GEO2
        Wb, Db, Hb = g['Wb'], g['Db'], g['Hb']
        tw = Wb / 3
        out = {0: [], 1: [], 2: []}
        for j, k in enumerate(['card01', 'card02', 'card06']):
            out[0].append((SB.rotate(V.motion_mini(k), [-12, 2, 13][j]), (-20 + j * 64, Db * (0.8 - j * 0.25), Hb + 110), 176))
        out[1].append((V.speaker_panel(), (tw + 46, Db * 0.4, Hb + 150), 170))
        out[1].append((V.speaker_icon(150), (tw + 150, Db * 0.2, Hb + 40), 118))
        for j, k in enumerate(['vlog_open', 'film_open', 'mag_A']):
            out[2].append((SB.rotate(V.thumb(k, 120, 160), [-12, 0, 11][j]), (2 * tw - 4 + j * 66, Db * (0.8 - j * 0.25), Hb + 110), 158))
        res = {}
        for i, lst in out.items():
            res[i] = []
            for im, (x, y, z), w in lst:
                h = int(im.height * w / im.width)
                spr = L.to_pm(im.resize((int(w), h), Image.LANCZOS))
                res[i].append((spr, L.shadow_pm(spr, 8, 0.3), (x, y, z)))
        return res

    def draw_box2(self, lay4, F):
        g = self.GEO2
        P = Obl(g['ox'], g['oy'])
        Wb, Db, Hb = g['Wb'], g['Db'], g['Hb']
        tw = Wb / 3
        items = []
        # lid swings back: 100 deg at the pop -> overshoot -> the sample's 70 deg
        u = (F - self.POP + 1) / 8
        ang = 70 + 30 * (1 - L.back_out(min(1.0, u), 2.2))
        Ll = 319.5                     # sample lid tip (Db + 110, Hb + 300)
        c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        draw_poly(im, P.poly([(0, Db, Hb), (Wb, Db, Hb), (Wb, Db + Ll * c, Hb + Ll * s), (0, Db + Ll * c, Hb + Ll * s)]), KRAFT_T)
        draw_poly(im, P.poly([(0, 0, Hb), (Wb, 0, Hb), (Wb, Db, Hb), (0, Db, Hb)]), KRAFT_IN)
        L.blend(lay4, L.to_pm(im), 0, 0)
        lit = [self.light(F, i) for i in range(3)]
        if any(a > 0 for a in lit):
            beams = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            bd = ImageDraw.Draw(beams)
            for i, a in enumerate(lit):
                if a > 0:
                    x0, x1 = tw * i + 10, tw * (i + 1) - 10
                    bd.polygon(P.poly([(x0, 4, Hb), (x1, 4, Hb), (x1, Db - 4, Hb), (x0, Db - 4, Hb)]), fill=(255, 226, 90, int(255 * a)))
            L.blend(lay4, L.to_pm(beams.filter(ImageFilter.GaussianBlur(6))), 0, 0)
            for i, a in enumerate(lit):
                if a > 0:
                    gx, gy = P(tw * (i + 0.5), Db * 0.5, Hb + 60)
                    L.blend(lay4, self.glow, int(gx - 260), int(gy - 200), opacity=a)
        for i in range(3):
            f = self.LIGHT[i][1]
            if F < f:
                continue
            k = L.back_out(min(1.0, (F - f + 1) / 7), 1.4)
            for spr, (sh, pad), (x, y, z) in self.contents[i]:
                zn = lerp(Hb - 40 - spr.shape[0], z, k)
                sx, sy = P(x, y, zn)
                x0, y0 = int(sx), int(sy - spr.shape[0])
                L.blend(lay4, sh, x0 - pad + 3, y0 - pad + 7)
                L.blend(lay4, spr, x0, y0)
                items.append((f'tray{i}_content', (x0, y0, x0 + spr.shape[1], y0 + spr.shape[0]), 'overlay'))
        im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        kd = L.cubic_out(min(1.0, (F - self.POP + 1) / 5))
        for i in (1, 2):
            draw_poly(im, P.poly([(tw * i, 0, Hb), (tw * i, Db, Hb), (tw * i, Db, Hb - 8), (tw * i, 0, Hb - 8)]), KRAFT_S, width=4)
        draw_poly(im, P.poly([(Wb, 0, 0), (Wb, Db, 0), (Wb, Db, Hb), (Wb, 0, Hb)]), KRAFT_S)
        draw_poly(im, P.poly([(0, 0, 0), (Wb, 0, 0), (Wb, 0, Hb), (0, 0, Hb)]), KRAFT_F)
        d = ImageDraw.Draw(im)
        for i in (1, 2):
            a_, b_ = P(tw * i, 0, 0), P(tw * i, 0, Hb * kd)
            d.line((a_, b_), fill=INK, width=4)
        L.blend(lay4, L.to_pm(im), 0, 0)
        for i, (name, f) in enumerate(self.LIGHT):
            off, on, (sh, pad) = self.tray_lab[name]
            fx, fy = P(tw * (i + 0.5), 0, Hb * 0.5)
            u_in = min(1.0, (F - self.POP - i + 1) / 6) if F >= self.POP + i else 0.0
            s_in = L.back_out(u_in, 1.0)                  # <= 1.04 overshoot: neighbouring labels are ~20 px apart
            if s_in <= 0.01:
                continue
            spr = off
            a = lit[i]
            if a > 0:
                ramp = np.arange(on.shape[1], dtype=np.float32) / on.shape[1]
                wipe = np.clip((a * 1.25 - ramp) / 0.12, 0, 1)
                spr = off * (1 - wipe[None, :, None]) + on * wipe[None, :, None]
            pop = 1 + 0.05 * math.sin(math.pi * min(1.0, (F - f + 1) / 8)) if f <= F < f + 8 and u_in >= 1 else 1.0
            L.place(lay4, sh, fx + 3, fy + 7, scale=s_in * pop)
            items.append((f'tray_label_{name}', L.place(lay4, spr, fx, fy, scale=s_in * pop), 'text'))
        items.append(('toolbox', (int(P(0, 0, 0)[0]), int(P(0, Db + 110, Hb + 300)[1]), int(P(Wb, Db, 0)[0]), int(P(0, 0, 0)[1])), 'bg'))
        return items

    # ------------------------------------------------------------ page
    def page(self, F):
        self.quads = {}
        page = self.paper.copy()
        lay4 = np.zeros((H, W, 4), np.float32)
        items_bg = []
        if self.part(F) == 2 and self.POP <= F < self.POP + 8:              # rays behind the lid as the box pops open
            a = 1 - L.seg(F, self.POP + 4, self.POP + 8)
            sc = L.back_out(min(1.0, (F - self.POP + 1) / 4), 1.6)
            g = self.GEO2
            cx, cy = Obl(g['ox'], g['oy'])(g['Wb'] / 2, g['Db'] + 110, g['Hb'] + 300)
            items_bg.append(('pop_burst', L.place(page, self.burst_ring, cx, cy - 10, scale=sc * 1.6, opacity=a), 'fx'))
        if self.part(F) == 1 or F < self.POP:
            items = self.draw_box1(lay4, F)
            g = self.GEO1
            anchor = (g['ox'] + g['Wb'] / 2 + g['Db'] * 0.21, g['oy'])
            sx = sy = 1.0
            if self.part(F) == 2 and F >= self.SQUASH:                    # anticipation squash before the pop
                k = L.cubic_out((F - self.SQUASH + 1) / 2)
                sx, sy = 1 + 0.05 * k, 1 - 0.07 * k
        else:
            items = self.draw_box2(lay4, F)
            g = self.GEO2
            anchor = (g['ox'] + g['Wb'] / 2 + g['Db'] * 0.21, g['oy'])
            k = L.back_out(min(1.0, (F - self.POP + 1) / 6), 1.8)
            sx = sy = lerp(0.86, 1.0, k)
        if abs(sx - 1) < 1e-4 and abs(sy - 1) < 1e-4:
            L.blend(page, lay4, 0, 0)
        else:
            L.place(page, lay4, anchor[0], anchor[1], ax=anchor[0], ay=anchor[1], sx=sx, sy=sy)
            items = [(n, _scale_bb(b, anchor, sx, sy), kk) for n, b, kk in items]
            self.quads = {k: [[anchor[0] + (x - anchor[0]) * sx, anchor[1] + (y - anchor[1]) * sy] for x, y in q]
                          for k, q in self.quads.items()}
        return page, items_bg + items

    def frame(self, F):
        sf = src_frame(F)
        live = self.src.get(sf)
        info = {'F': F, 'src': sf, 'items': []}
        off = self.page_offset(F)
        if off is None or off >= H - 0.5:
            info.update(full=True, live_rect=[0, 0, W, H], tr=[1.0, 0.0, 0.0], no_live=False)
            return live.copy(), info
        page, items = self.page(F)
        oy = int(round(off))
        if oy <= 0:
            info.update(live_rect=None, no_live=True, items=items, quads=self.quads)
            return L.to_u8(page), info
        cv = live.astype(np.float32)
        y0 = max(0, oy - 40)
        ramp = (np.arange(y0, oy, dtype=np.float32) - (oy - 40)) / 40
        cv[y0:oy] *= (1 - 0.35 * np.clip(ramp, 0, 1) ** 2)[:, None, None]
        cv[oy:] = page[:H - oy]
        info.update(live_rect=[0, 0, W, oy], no_live=False, page_top=oy,
                    items=[(n, (b[0], b[1] + oy, b[2], b[3] + oy) if b else None, k) for n, b, k in items],
                    quads={k: [[x, y + oy] for x, y in q] for k, q in self.quads.items()})
        return L.to_u8(cv), info

    def no_live(self, F):
        off = self.page_offset(F)
        return off is not None and off <= 0.5

    def close(self):
        self.src.close()


def _scale_bb(b, anchor, sx, sy):
    if b is None:
        return None
    ax, ay = anchor
    return (int(ax + (b[0] - ax) * sx), int(ay + (b[1] - ay) * sy), int(ax + (b[2] - ax) * sx), int(ay + (b[3] - ay) * sy))


def lerp(a, b, t):
    return a + (b - a) * t


# ================================================================ shot 11
class Shot11:
    """你只要把我这个skill丢给你的agent就可以直接来使用  (v2 57.67-61.67), the presenter full frame throughout.

    skill 58.78 (1763): the closed 开源工具 box pops out right of the presenter's face;  the 你的 Agent chip slides in top right
    (1765-1771);  丢给 59.24 (1777): the box is tossed up along the right edge (dashed trail) and lands in the chip at
    1791 (Agent 59.72);  直接来使用 60.46 (1814): 接收中… -> 已就绪 + green tick;  1830-1838 chip leaves, clean after.
    The box stays right of the face box + 12 px while level with the face, and above the hair when it crosses left.
    """
    key, F0, F1 = '11', 1730, 1850
    POP, CHIP_IN, TOSS, LAND, READY, OUT = 1763, 1765, 1777, 1791, 1814, 1830   # words_v2: skill 58.78, 丢给 59.24, Agent 59.72, 直接来使用 60.46
    START = (982, 925)           # box centre when it pops (right of the face)
    CHIP_XY = (W - 300 - 36, 196)

    def __init__(self):
        self.src = L.Source(SRC)
        box = SB.rotate(V.closed_box(0.5), 10)
        self.box = L.to_pm(box)
        self.box_sh = L.shadow_pm(self.box, 14, 0.35)
        self.chip_recv = L.to_pm(V.agent_chip())
        self.chip_ready = L.to_pm(self.ready_chip())
        self.chip_sh = L.shadow_pm(self.chip_recv, 12, 0.35)
        cx, cy = self.CHIP_XY
        self.target = (cx + 56, cy + 60)        # the chip's round 'A' badge
        self.path = [self.START, (1008, 650), (998, 330), (self.target[0] + 120, self.target[1] + 18)]

    @staticmethod
    def ready_chip():
        """agent_chip() with the status line switched to 已就绪 + green tick (same geometry and fonts)"""
        im = Image.new('RGBA', (300, 120), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, 299, 119), radius=26, fill=(24, 24, 26, 240))
        d.ellipse((22, 26, 90, 94), fill=SB.BLUE)
        d.text((56, 60), 'A', font=SB.font('Heavy', 40), fill=(255, 255, 255), anchor='mm')
        d.text((108, 44), '你的 Agent', font=SB.font('Heavy', 34), fill=(255, 255, 255), anchor='lm')
        d.text((142, 86), '已就绪', font=SB.font('Medium', 26), fill=(120, 225, 150), anchor='lm')
        ck = SB.icon_check(30, color=(120, 225, 150), lw=9)
        im.alpha_composite(ck, (106, 71))
        return im

    def box_state(self, F):
        """(cx, cy, scale, rot) of the tossed box, None when not drawn"""
        if F < self.POP:
            return None
        if F < self.TOSS:
            s = L.back_out(min(1.0, (F - self.POP + 1) / 6), 1.8)
            wob = 3 * math.sin((F - self.POP) * 0.9) * max(0.0, 1 - (F - self.POP) / 10)
            return (self.START[0], self.START[1], s, wob)
        if F < self.LAND:
            u = (F - self.TOSS + 1) / (self.LAND - self.TOSS)
            t = L.cubic_out(u)                          # a toss: fast off the hand, slowing into the badge
            x, y = bezier(*self.path, t)
            if t > 0.85:                               # final hop into the badge
                k = (t - 0.85) / 0.15
                x, y = lerp(x, self.target[0], k), lerp(y, self.target[1], k)
            return (x, y, lerp(1.0, 0.32, L.cubic_in(u)), 10 - 25 * t)
        return None

    def trail_pts(self, F):
        if F < self.TOSS or F >= self.LAND + 8:
            return None, 0.0
        u = min(1.0, (F - self.TOSS + 1) / (self.LAND - self.TOSS))
        t = L.cubic_out(u)
        pts = [bezier(*self.path, tt) for tt in np.linspace(0, max(0.02, min(t, 0.85) * 0.97), 50)]
        a = 1.0 if F < self.LAND else 1 - (F - self.LAND + 1) / 8
        return pts, a

    def chip_state(self, F):
        """(x offset, scale) of the Agent chip, None when not drawn"""
        if F < self.CHIP_IN or F >= self.OUT + 9:
            return None
        if F >= self.OUT:
            return (420 * L.cubic_in((F - self.OUT + 1) / 9), 1.0)
        dx = 420 * (1 - L.back_out(min(1.0, (F - self.CHIP_IN + 1) / 7), 1.2))
        s = 1.0
        if self.LAND <= F < self.LAND + 7:
            s = 1 + 0.08 * math.sin(math.pi * (F - self.LAND + 1) / 7)
        if self.READY <= F < self.READY + 6:
            s = 1 + 0.06 * math.sin(math.pi * (F - self.READY + 1) / 6)
        return (dx, s)

    def frame(self, F):
        sf = src_frame(F)
        live = self.src.get(sf)
        info = {'F': F, 'src': sf, 'items': [], 'live_rect': [0, 0, W, H], 'tr': [1.0, 0.0, 0.0], 'no_live': False,
                'quads': {}, 'polys': {}}
        cs = self.chip_state(F)
        bs = self.box_state(F)
        pts, ta = self.trail_pts(F)
        if cs is None and bs is None and pts is None:
            info['full'] = True
            return live.copy(), info
        cv = live.astype(np.float32)
        if pts is not None and ta > 0:
            lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            dashed_path(d, pts, (255, 255, 255, int(235 * ta)), width=6, dash=20, gap=14)
            L.blend(cv, L.to_pm(lay), 0, 0)
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            info['items'].append(('toss_trail', (int(min(xs)) - 3, int(min(ys)) - 3, int(max(xs)) + 3, int(max(ys)) + 3), 'fx'))
            info['polys']['toss_trail'] = [[round(x, 1), round(y, 1)] for x, y in pts]
        if cs is not None:
            dx, s = cs
            spr = self.chip_ready if F >= self.READY else self.chip_recv
            x, y = self.CHIP_XY
            cx, cy = x + dx + 150, y + 60
            sh, pad = self.chip_sh
            L.place(cv, sh, cx + 3, cy + 7, scale=s)
            bb = L.place(cv, spr, cx, cy, scale=s)
            info['quads']['agent_chip'] = L.LAST_QUAD
            info['items'].append(('agent_chip', bb, 'overlay'))
            if F < self.READY and F >= self.LAND:
                # receiving dots: the ellipsis breathes
                pass
        if bs is not None:
            x, y, s, rot = bs
            sh, pad = self.box_sh
            L.place(cv, sh, x + 3, y + 7, scale=s, rot=rot)
            bb = L.place(cv, self.box, x, y, scale=s, rot=rot)
            info['quads']['skill_box'] = L.LAST_QUAD
            info['items'].append(('skill_box', bb, 'overlay'))
            if self.TOSS <= F < self.TOSS + 8:
                # three speed lines under the box as it leaves
                lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                d = ImageDraw.Draw(lay)
                a = int(220 * (1 - (F - self.TOSS) / 8))
                segs = []
                for i in range(3):
                    lx = x - 40 + i * 40
                    d.line((lx, y + 90 + i * 12, lx, y + 150 + i * 12), fill=(255, 255, 255, a), width=6)
                    segs += [[lx, y + 90 + i * 12], [lx, y + 120 + i * 12], [lx, y + 150 + i * 12]]
                L.blend(cv, L.to_pm(lay), 0, 0)
                info['items'].append(('speed_lines', (int(x - 45), int(y + 88), int(x + 45), int(y + 176)), 'fx'))
                info['polys']['speed_lines'] = [[round(a_, 1), round(b_, 1)] for a_, b_ in segs]
        return L.to_u8(cv), info

    def close(self):
        self.src.close()


SHOTS = {'10': Shot10, '11': Shot11}
