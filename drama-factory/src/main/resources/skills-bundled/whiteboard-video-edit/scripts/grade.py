"""House grade F for the whiteboard rail (the version chosen from a 6 version color test on three takes).
Measured per video, no hand tuning.

  py grade.py measure <E> <L> <source>          24 source frames -> <E>/grade/measure_<L>.json (board white, shadow cast,
                                                black point, skin hue, face luma; Apple Vision faces; board rect from tools/board.json)
  py grade.py lut <E> <L>                       -> <E>/grade/house_<L>.cube (65^3, full range BT.709 R'G'B') + params_<L>.json
  py grade.py props <cube> <props.json>...      stamps "grade": <abs cube> into each props file (the long form AND the reel);
                                                the Node renderers then grade every frame in float before rounding and overlays
  py grade.py gates <encoded.mp4> <props_abs.json> <E> <L> [--overlays <overlays.json>] [--skip-head N] [--out <json>]
                                                the 5 colour gates ON THE ENCODED FILE; exit 0 all pass, 3 a gate failed

F, in order, on full range R'G'B' 0..1:
 1 levels   per channel: the shadow colour (pixels with luma < 20) -> neutral black 4/255 at the p0.5 black point,
            the board white -> 228/255 tinted to a* +0.5, b* +2.0 (a hint of warmth). Board white = the colour of all
            flat, unclipped board cells, at the p90 luma of those cells (the board has a light gradient, so a fixed
            patch would land on a different part of it per video; the colour test's patches put the p90 at 233,
            225 and 227 on the three test takes, median 227.4)
 2 lift     face median luma toward 0.47 with a multiplicative luma gamma, lift only (0.85 <= gamma <= 1)
 3 contrast Y' = Y + 0.07*4*(Y-p)*Y*(1-Y), added to R, G, B (Cb/Cr kept), pivot p = face luma (0.35..0.55)
 4 sat      Cb/Cr x (1 + 0.08*(1 - 0.85*w)), w = skin weight (hue within ~20 deg of 123, chroma > ~4/255)
 5 shoulder max(R,G,B) above 0.88 rolls off with tanh: the board never reaches 1.0
 6 toe      below 10/255 each channel rolls off exponentially: no crushed blacks

Gates (thresholds tested on three takes of one presenter in the colour test):
 G1 white board  board patch C*ab <= 3.0 and b* >= -1.0 on every measured frame
 G2 skin hue     every face frame in 123 +-8 deg, median shift against the same source frames <= 3 deg
 G3 face luma    every face frame 70..190 (full range), MEAN 100..165 (about 40..65 IRE). The mean, not the median: the
                 face luma is bimodal (85 to 95 turned to the board, 125 to 155 facing the lens) and a median lands in the gap
 G4 board clip   board pixels with luma >= 253 <= 0.01 %, luma >= 245 <= 0.5 %, every sampled frame
 G5 cut jump     every cut: board patch dE76 <= 2.0 between the last frame before and the first after
`py` = python3 with Pillow (pure PIL, no numpy)."""
from __future__ import annotations
import json, math, statistics as st, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageStat

HERE = Path(__file__).parent
POSE = HERE / "pose"
FPS = 24000 / 1001
YM = (0.2126, 0.7152, 0.0722, 0)
RGB_VF = "scale=in_range=tv:in_color_matrix=bt709:out_range=pc:out_color_matrix=bt709:flags=accurate_rnd+full_chroma_int,format=rgb24"
CELL, INSET = 64, 60
HOUSE = {"board_luma": 228 / 255, "black": 4 / 255, "toe": 10 / 255, "warm_ab": (0.5, 2.0), "face_target": 0.47,
         "gamma_min": 0.85, "contrast": 0.07, "sat": 0.08, "skin_protect": 0.85, "skin_sigma": 20.0, "shoulder": 0.88}
T = {"G1_chroma_max": 3.0, "G1_b_min": -1.0, "G2_band": [115.0, 131.0], "G2_shift_max": 3.0, "G3_frame": [70.0, 190.0],
     "G3_mean": [100.0, 165.0], "G4_near_pct": 0.5, "G4_clip_pct": 0.01, "G5_dE_max": 2.0}
SKIN_LINE = 123.0


# ------------------------------------------------------------------ colour maths
def luma(r, g, b):
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cbcr(r, g, b):
    y = luma(r, g, b)
    return (b - y) / 1.8556, (r - y) / 1.5748


def hue(cb, cr):
    a = math.degrees(math.atan2(cr, cb))
    return a + 360 if a < 0 else a


def lab(r, g, b):
    def lin(c):
        c = max(0.0, min(1.0, c / 255))
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    R, G, B = lin(r), lin(g), lin(b)
    X = 0.4124 * R + 0.3576 * G + 0.1805 * B; Y = 0.2126 * R + 0.7152 * G + 0.0722 * B; Z = 0.0193 * R + 0.1192 * G + 0.9505 * B
    f = lambda t: t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(X / 0.95047), f(Y), f(Z / 1.08883)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def lab_to_rgb(L, a, b):
    fy = (L + 16) / 116; fx = fy + a / 500; fz = fy - b / 200
    inv = lambda t: t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) / (24389 / 27)
    X, Y, Z = 0.95047 * inv(fx), inv(fy), 1.08883 * inv(fz)
    R = 3.2406 * X - 1.5372 * Y - 0.4986 * Z; G = -0.9689 * X + 1.8758 * Y + 0.0415 * Z; B = 0.0557 * X - 0.2040 * Y + 1.0570 * Z
    enc = lambda c: 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return [enc(max(0.0, c)) for c in (R, G, B)]


# ------------------------------------------------------------------ frame helpers
def grab(src, frame, out, vf=RGB_VF):
    """Exact source frame (the renderers' seek: a quarter frame early) as full range RGB."""
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{(frame - 0.25) / FPS:.6f}", "-i", str(src),
                    "-map", "0:v:0", "-frames:v", "1", "-vf", vf, str(out)], check=True)


def faces(paths):
    """Apple Vision face box per image (normalised x, y, w, h, conf, origin top left) or None."""
    out = {}
    paths = [str(p) for p in paths]
    for i in range(0, len(paths), 100):
        r = subprocess.run([str(POSE)] + paths[i:i + 100], capture_output=True, text=True, check=True)
        for line in r.stdout.splitlines():
            d = json.loads(line)
            out[d["path"]] = d.get("face")
    return {p: out.get(Path(p).name) for p in paths}


def skin(im, box, exclude=()):
    """Mean skin colour inside the inner face box (x 20..80 %, y 20..70 %), pixels with luma 20..240,
    chroma 4..70, hue 90..165; box in pixels (x0, y0, x1, y1). None when under 200 pixels qualify."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    ib = (int(x0 + 0.2 * w), int(y0 + 0.2 * h), int(x0 + 0.8 * w), int(y0 + 0.7 * h))
    for ex in exclude:
        if not (ib[2] <= ex[0] or ib[0] >= ex[2] or ib[3] <= ex[1] or ib[1] >= ex[3]):
            return None
    crop = im.crop(ib)
    sr = sg = sb = 0.0; k = 0
    for (r, g, b) in crop.getdata():
        yv = luma(r, g, b)
        if not 20 <= yv <= 240:
            continue
        cb, cr = cbcr(r, g, b)
        c = math.hypot(cb, cr)
        if not 4 <= c <= 70 or not 90 <= hue(cb, cr) <= 165:
            continue
        sr += r; sg += g; sb += b; k += 1
    if k < 200:
        return None
    m = (sr / k, sg / k, sb / k)
    cb, cr = cbcr(*m)
    return {"rgb": [round(v, 2) for v in m], "luma": round(luma(*m), 2), "hue": round(hue(cb, cr), 2), "pixels": k}


# ------------------------------------------------------------------ measure
def cmd_measure(E, L, src, n=24):
    E = Path(E); g = E / "grade"; g.mkdir(exist_ok=True)
    board = json.load(open(E / "tools/board.json"))["board"]
    bx0, by0, bx1, by1 = board[0] + INSET, board[1] + INSET, board[2] - INSET, board[3] - INSET
    nb = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "csv=p=0", str(src)],
                            capture_output=True, text=True, check=True).stdout.strip())
    frames = [round(nb * (0.08 + 0.84 * (i + 0.5) / n)) for i in range(n)]
    with tempfile.TemporaryDirectory(dir=g) as td:
        td = Path(td)
        with ThreadPoolExecutor(4) as ex:
            list(ex.map(lambda f: grab(src, f, td / f"m_{f:06d}.png"), frames))
        for f in frames:
            Image.open(td / f"m_{f:06d}.png").resize((1920, 1080), Image.BOX).save(td / f"s_{f:06d}.jpg", quality=92)
        fc = faces([td / f"s_{f:06d}.jpg" for f in frames])
        recs, cellsets = [], []
        for f in frames:
            im = Image.open(td / f"m_{f:06d}.png").convert("RGB")
            W, H = im.size
            cells = {}
            for cy in range(by0, by1 - CELL + 1, CELL):
                for cx in range(bx0, bx1 - CELL + 1, CELL):
                    c = im.crop((cx, cy, cx + CELL, cy + CELL)); s = ImageStat.Stat(c)
                    cells[(cx, cy)] = (s.mean, ImageStat.Stat(c.convert("L", YM)).stddev[0], max(e[1] for e in s.extrema))
            lums = sorted(luma(*v[0]) for v in cells.values())
            p90 = lums[int(0.9 * (len(lums) - 1))]
            clean = {k for k, v in cells.items() if v[1] < 2.5 and luma(*v[0]) > 0.8 * p90 and v[2] < 250}
            cellsets.append(clean)
            cl_l = sorted(luma(*cells[k][0]) for k in clean)
            cl_rgb = [st.mean(cells[k][0][i] for k in clean) for i in range(3)]
            ref90 = cl_l[int(0.9 * (len(cl_l) - 1))]
            Lm = im.convert("L", YM); hl = Lm.histogram(); tot = sum(hl)
            def pct(p):
                acc = 0
                for i, c in enumerate(hl):
                    acc += c
                    if acc >= p / 100 * tot:
                        return i
                return 255
            sm = im.resize((960, 540), Image.BOX); L9 = sm.convert("L", YM)
            sh = ImageStat.Stat(sm, mask=L9.point(lambda v: 255 if v < 20 else 0))
            rec = {"src_frame": f, "cells": cells, "black_p0_5": pct(0.5), "white_p99_5": pct(99.5), "clean_cells": len(clean),
                   "board_white": [round(c * ref90 / luma(*cl_rgb), 3) for c in cl_rgb], "board_p50_p90": [round(cl_l[len(cl_l) // 2], 2), round(ref90, 2)],
                   "shadow_rgb": [round(v, 3) for v in sh.mean] if sh.count[0] else None}
            fb = fc[str(td / f"s_{f:06d}.jpg")]
            if fb and fb[4] >= 0.6:
                x, y, w, h, conf = fb
                sk = skin(im, (x * W, y * H, (x + w) * W, (y + h) * H))
                if sk:
                    rec["skin"] = sk
            recs.append(rec)
    from collections import Counter
    cnt = Counter(c for s in cellsets for c in s)
    fixed = {c for c, k in cnt.items() if k >= 0.5 * len(frames)}   # the cells the gates map into the output frames
    if len(fixed) < 8:
        sys.exit(f"grade measure: only {len(fixed)} clean board cells; check tools/board.json")
    per = []
    for r in recs:
        use = [r["cells"][c] for c in fixed]
        rgb = [st.mean(v[0][i] for v in use) for i in range(3)]
        out = {k: v for k, v in r.items() if k != "cells"}
        out["board_rgb"] = [round(v, 3) for v in rgb]
        out["board_lab"] = [round(v, 3) for v in lab(*rgb)]
        per.append(out)
    med = lambda xs: st.median(xs) if xs else None
    sk = [r["skin"] for r in per if "skin" in r]
    if len(sk) < 3:
        sys.exit(f"grade measure: the speaker's face was found in only {len(sk)} of {len(frames)} frames; need 3")
    summ = {"board_rgb": [round(med([r["board_white"][i] for r in per]), 3) for i in range(3)],
            "board_patch_rgb": [round(med([r["board_rgb"][i] for r in per]), 3) for i in range(3)],
            "shadow_rgb": [round(med([r["shadow_rgb"][i] for r in per if r["shadow_rgb"]]), 3) for i in range(3)],
            "black_p0_5": med([r["black_p0_5"] for r in per]), "white_p99_5": med([r["white_p99_5"] for r in per]),
            "skin_luma": round(med([s["luma"] for s in sk]), 2), "skin_hue": round(med([s["hue"] for s in sk]), 2),
            "face_frames": len(sk)}
    summ["board_lab"] = [round(v, 3) for v in lab(*summ["board_rgb"])]
    res = {"video": L, "source": str(src), "frames": frames, "board_rect_inset": [bx0, by0, bx1, by1], "cell_px": CELL,
           "fixed_patch": sorted([list(c) for c in fixed]), "summary": summ, "per_frame": per}
    (g / f"measure_{L}.json").write_text(json.dumps(res, indent=1))
    print(f"grade measure {L}: {len(frames)} frames, {len(fixed)} board cells, board {summ['board_rgb']} Lab {summ['board_lab']}, "
          f"black {summ['black_p0_5']}, shadow {summ['shadow_rgb']}, face luma {summ['skin_luma']} hue {summ['skin_hue']} ({len(sk)} faces)")


# ------------------------------------------------------------------ lut
def house_transform(S):
    H = HOUSE
    board = [c / 255 for c in S["board_rgb"]]
    shadow = [c / 255 for c in S["shadow_rgb"]]
    black_l = S["black_p0_5"] / 255
    sh_l = luma(*shadow)
    black_in = [black_l + (shadow[i] - sh_l) for i in range(3)]
    Lt = lab(H["board_luma"] * 255, H["board_luma"] * 255, H["board_luma"] * 255)[0]
    tw = lab_to_rgb(Lt, *H["warm_ab"])
    k = H["board_luma"] / luma(*tw)
    tw = [c * k for c in tw]
    gains = [(tw[i] - H["black"]) / (board[i] - black_in[i]) for i in range(3)]
    fl = H["black"] + (S["skin_luma"] / 255 - black_l) * luma(*gains)
    gamma = max(H["gamma_min"], min(1.0, math.log(H["face_target"]) / math.log(max(fl, 1e-3))))
    fl2 = fl ** gamma
    pivot = min(0.55, max(0.35, fl2))
    a, s, kn, toe = H["contrast"], H["sat"], H["shoulder"], H["toe"]
    params = {"black_in": [round(x * 255, 3) for x in black_in], "black_out": round(H["black"] * 255, 3),
              "board_in": [round(x * 255, 3) for x in board], "board_out": [round(x * 255, 3) for x in tw],
              "gains": [round(x, 5) for x in gains], "warm_target_ab": list(H["warm_ab"]),
              "face_luma_after_levels": round(fl * 255, 2), "lift_gamma": round(gamma, 4), "face_luma_after_lift": round(fl2 * 255, 2),
              "contrast_a": a, "contrast_pivot": round(pivot, 4), "sat_lift": s, "skin_line_deg": SKIN_LINE,
              "skin_sigma_deg": H["skin_sigma"], "skin_protect": H["skin_protect"], "shoulder_knee": kn, "toe": round(toe * 255, 2)}

    def f(r, g, b):
        c = [H["black"] + (x - black_in[i]) * gains[i] for i, x in enumerate((r, g, b))]
        if gamma != 1.0:
            y = luma(*c)
            if y > 1e-4:
                m = (max(0.0, y) ** gamma) / y
                c = [x * m for x in c]
        y = luma(*c); yc = min(1.0, max(0.0, y))
        d = a * 4 * (yc - pivot) * yc * (1 - yc)
        c = [x + d for x in c]
        y = luma(*c); cb, cr = cbcr(*c)
        ch = math.hypot(cb, cr) * 255
        dh = abs(hue(cb, cr) - SKIN_LINE); dh = min(dh, 360 - dh)
        w = math.exp(-(dh / H["skin_sigma"]) ** 2) * min(1.0, max(0.0, (ch - 2) / 4))
        sc = 1 + s * (1 - H["skin_protect"] * w)
        cb *= sc; cr *= sc
        R = y + 1.5748 * cr; B = y + 1.8556 * cb; G = (y - 0.2126 * R - 0.0722 * B) / 0.7152
        c = [R, G, B]
        m = max(c)
        if m > kn:
            m2 = kn + (1 - kn) * math.tanh((m - kn) / (1 - kn))
            c = [x * m2 / m for x in c]
        out = []
        for x in c:
            if x < toe:
                x = toe * math.exp((x - toe) / toe)
            out.append(min(1.0, max(0.0, x)))
        return out
    return f, params


def cmd_lut(E, L, N=65):
    E = Path(E); g = E / "grade"
    M = json.load(open(g / f"measure_{L}.json"))
    f, params = house_transform(M["summary"])
    lines = [f'TITLE "{L} house grade F"', f"LUT_3D_SIZE {N}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    for bi in range(N):
        for gi in range(N):
            for ri in range(N):
                o = f(ri / (N - 1), gi / (N - 1), bi / (N - 1))
                lines.append(f"{o[0]:.6f} {o[1]:.6f} {o[2]:.6f}")
    (g / f"house_{L}.cube").write_text("\n".join(lines) + "\n")
    params.update({"video": L, "grade": "F (house)", "domain": "full range BT.709 R'G'B' 0..1", "cube": str(g / f"house_{L}.cube")})
    (g / f"params_{L}.json").write_text(json.dumps(params, indent=1))
    print(f"grade lut {L}: {g / f'house_{L}.cube'} gains {params['gains']} lift gamma {params['lift_gamma']} pivot {params['contrast_pivot']}")


def cmd_props(cube, files):
    cube = str(Path(cube).resolve())
    if not Path(cube).exists():
        sys.exit(f"no cube {cube}")
    for p in files:
        d = json.load(open(p))
        d["grade"] = cube
        Path(p).write_text(json.dumps(d))
        print(f"grade props: {p} -> {Path(cube).name}")


# ------------------------------------------------------------------ gates on the encoded file
def cmd_gates(enc, props_path, E, L, overlays=None, skip_head=0, out=None, n_samples=24):
    E = Path(E)
    P = json.load(open(props_path))
    M = json.load(open(E / "grade" / f"measure_{L}.json"))
    board = json.load(open(E / "tools/board.json"))["board"]
    OW, OH = P["outW"], P["outH"]
    cam, segs = P["camera"], P["segments"]
    N = sum(s["frames"] for s in segs)
    OV = json.load(open(overlays)) if overlays else None

    def ov_boxes(f):
        if not OV:
            return []
        out_ = []
        for name, x, y in (OV["frames"][f] if f < len(OV["frames"]) else []):
            ly = OV["layers"][name]
            out_.append((x - 6, y - 6, x + ly["w"] + 6, y + ly["h"] + 6))
        return out_

    def src_of(f):
        s = next(s for s in segs if s["outFrame"] <= f < s["outFrame"] + s["frames"])
        return s["srcFrame"] + f - s["outFrame"]
    cuts = []
    for a, b in zip(segs, segs[1:]):
        if b["srcFrame"] != a["srcFrame"] + a["frames"]:
            cuts.append((b["outFrame"] - 1, b["outFrame"]))
    lo = max(skip_head, int(0.03 * N)); hi = int(0.97 * N)
    samples = sorted({lo + round((hi - lo) * (i + 0.5) / n_samples) for i in range(n_samples)})
    need = sorted(set(samples) | {f for c in cuts for f in c})
    fixed = [tuple(c) for c in M["fixed_patch"]]
    res = {"file": str(enc), "props": str(props_path), "frames": N, "thresholds": T, "samples": samples, "cuts": len(cuts)}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sel = "+".join(f"eq(n\\,{f})" for f in need)
        (td / "sel.txt").write_text(f"select='{sel}',{RGB_VF}")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(enc), "-filter_script:v", str(td / "sel.txt"),
                        "-fps_mode", "passthrough", str(td / "e_%05d.png")], check=True)
        got = sorted(td.glob("e_*.png"))
        if len(got) != len(need):
            sys.exit(f"grade gates: decoded {len(got)} of {len(need)} frames from {enc}")
        path = {f: td / f"e_{i + 1:05d}.png" for i, f in enumerate(need)}
        img = {}
        def im(f):
            if f not in img:
                img[f] = Image.open(path[f]).convert("RGB")
            return img[f]

        def board_cells(f):
            x0, y0, w = cam[f]; s = OW / w
            exc = ov_boxes(f)
            vals = {}
            for (cx, cy) in fixed:
                r = ((cx - x0) * s, (cy - y0) * s, (cx + CELL - x0) * s, (cy + CELL - y0) * s)
                m = 0.15 * (r[2] - r[0])
                r = (int(r[0] + m), int(r[1] + m), int(r[2] - m), int(r[3] - m))
                if r[0] < 2 or r[1] < 2 or r[2] > OW - 2 or r[3] > OH - 2 or r[2] - r[0] < 4:
                    continue
                if any(not (r[2] <= e[0] or r[0] >= e[2] or r[3] <= e[1] or r[1] >= e[3]) for e in exc):
                    continue
                st_ = ImageStat.Stat(im(f).crop(r))
                if max(st_.stddev) < 3.5:
                    vals[(cx, cy)] = st_.mean
            if vals:
                ls = sorted(luma(*v) for v in vals.values())
                ref = ls[int(0.75 * (len(ls) - 1))]
                vals = {k: v for k, v in vals.items() if luma(*v) >= 0.85 * ref}
            return vals

        # G1 + G4 on the samples
        g1, g4 = [], []
        for f in samples:
            v = board_cells(f)
            if len(v) >= 4:
                rgb = [st.mean(x[i] for x in v.values()) for i in range(3)]
                Lb = lab(*rgb)
                g1.append({"frame": f, "cells": len(v), "lab": [round(x, 2) for x in Lb], "chroma": round(math.hypot(Lb[1], Lb[2]), 2)})
            x0, y0, w = cam[f]; s = OW / w
            br = (max(0, int((board[0] - x0) * s)), max(0, int((board[1] - y0) * s)), min(OW, int((board[2] - x0) * s)), min(OH, int((board[3] - y0) * s)))
            if br[2] - br[0] > 20 and br[3] - br[1] > 20:
                mask = Image.new("L", (OW, OH), 0); dr = ImageDraw.Draw(mask)
                dr.rectangle(br, fill=255)
                for e in ov_boxes(f):
                    dr.rectangle(e, fill=0)
                h = im(f).convert("L", YM).histogram(mask=mask); n = sum(h)
                if n > 1000:
                    g4.append({"frame": f, "near_pct": round(100 * sum(h[245:]) / n, 4), "clip_pct": round(100 * sum(h[253:]) / n, 4)})
        # G2 + G3: Vision on the samples, paired with the same source frames (ungraded, same camera window)
        for f in samples:
            im(f).save(td / f"j_{f:05d}.jpg", quality=92)
        fc = faces([td / f"j_{f:05d}.jpg" for f in samples])
        face_frames = [f for f in samples if fc[str(td / f"j_{f:05d}.jpg")] and fc[str(td / f"j_{f:05d}.jpg")][4] >= 0.6]

        def src_crop(f):
            p = td / f"s_{f:05d}.png"
            grab(P["src"], src_of(f), p)
            x0, y0, w = cam[f]; h = w * OH / OW
            sim = Image.open(p).convert("RGB")
            box = (max(0.0, x0), max(0.0, y0), min(float(sim.width), x0 + w), min(float(sim.height), y0 + h))  # a window can graze the edge by a float
            sim.resize((OW, OH), Image.LANCZOS, box=box).save(p)
            return p
        with ThreadPoolExecutor(6) as ex:
            srcp = dict(zip(face_frames, ex.map(src_crop, face_frames)))
        g23 = []
        for f in face_frames:
            x, y, w, h, conf = fc[str(td / f"j_{f:05d}.jpg")]
            box = (x * OW, y * OH, (x + w) * OW, (y + h) * OH)
            a = skin(im(f), box, ov_boxes(f)); b = skin(Image.open(srcp[f]).convert("RGB"), box, ov_boxes(f))
            if a and b:
                g23.append({"frame": f, "luma": a["luma"], "hue": a["hue"], "src_hue": b["hue"], "src_luma": b["luma"]})
        # G5 every cut: encoded frames when 4+ board cells are visible on both sides, else the source frames graded with the cube
        g5 = []
        fallback = []
        for a, b in cuts:
            va, vb = board_cells(a), board_cells(b)
            common = [k for k in va if k in vb]
            if len(common) >= 4:
                ma = [st.mean(va[k][i] for k in common) for i in range(3)]; mb = [st.mean(vb[k][i] for k in common) for i in range(3)]
                g5.append({"cut": [a, b], "via": "encoded", "cells": len(common), "dE": round(math.dist(lab(*ma), lab(*mb)), 3)})
            else:
                fallback.append((a, b))
        if fallback:
            cube = P.get("grade")
            vf = RGB_VF if not cube else (f"scale=in_range=tv:in_color_matrix=bt709:out_range=pc:flags=accurate_rnd+full_chroma_int,format=gbrpf32le,"
                                          f"lut3d=file={cube}:interp=tetrahedral,format=rgb24")
            def gfull(f):
                p = td / f"c_{f:05d}.png"
                grab(P["src"], src_of(f), p, vf + ",scale=960:540:flags=area")
                return p
            with ThreadPoolExecutor(6) as ex:
                fp = dict(zip(sorted({f for c in fallback for f in c}), ex.map(gfull, sorted({f for c in fallback for f in c}))))
            for a, b in fallback:
                A, B = Image.open(fp[a]).convert("RGB"), Image.open(fp[b]).convert("RGB")
                ca, cb_ = [], []
                for (cx, cy) in fixed:
                    r = (cx // 4 + 2, cy // 4 + 2, cx // 4 + 14, cy // 4 + 14)
                    sa, sb = ImageStat.Stat(A.crop(r)), ImageStat.Stat(B.crop(r))
                    if max(sa.stddev) < 3.5 and max(sb.stddev) < 3.5:
                        ca.append(sa.mean); cb_.append(sb.mean)
                if len(ca) >= 4:
                    ma = [st.mean(x[i] for x in ca) for i in range(3)]; mb = [st.mean(x[i] for x in cb_) for i in range(3)]
                    g5.append({"cut": [a, b], "via": "source+cube", "cells": len(ca), "dE": round(math.dist(lab(*ma), lab(*mb)), 3)})
                else:
                    g5.append({"cut": [a, b], "via": "unmeasurable", "cells": len(ca), "dE": None})
    hues = [r["hue"] for r in g23]; lums = [r["luma"] for r in g23]
    shift = st.median(r["hue"] - r["src_hue"] for r in g23) if g23 else None
    gates = {
        "G1_white_board": {"measured_frames": len(g1), "max_chroma": max((r["chroma"] for r in g1), default=None),
                           "min_b": min((r["lab"][2] for r in g1), default=None),
                           "pass": len(g1) >= 4 and all(r["chroma"] <= T["G1_chroma_max"] and r["lab"][2] >= T["G1_b_min"] for r in g1)},
        "G2_skin_hue": {"face_frames": len(g23), "hue_min": min(hues, default=None), "hue_max": max(hues, default=None),
                        "median_shift_vs_source": round(shift, 2) if shift is not None else None,
                        "pass": len(g23) >= 4 and all(T["G2_band"][0] <= h <= T["G2_band"][1] for h in hues) and abs(shift) <= T["G2_shift_max"]},
        "G3_face_luma": {"face_frames": len(g23), "luma_min": min(lums, default=None), "luma_max": max(lums, default=None),
                         "luma_mean": round(st.mean(lums), 2) if lums else None, "luma_median": round(st.median(lums), 2) if lums else None,
                         "pass": len(g23) >= 4 and all(T["G3_frame"][0] <= x <= T["G3_frame"][1] for x in lums)
                         and T["G3_mean"][0] <= st.mean(lums) <= T["G3_mean"][1]},
        "G4_board_clip": {"measured_frames": len(g4), "max_near_pct": max((r["near_pct"] for r in g4), default=None),
                          "max_clip_pct": max((r["clip_pct"] for r in g4), default=None),
                          "pass": len(g4) >= 4 and all(r["near_pct"] <= T["G4_near_pct"] and r["clip_pct"] <= T["G4_clip_pct"] for r in g4)},
        "G5_cut_jump": {"cuts": len(cuts), "measured": sum(r["dE"] is not None for r in g5),
                        "via_encoded": sum(r["via"] == "encoded" for r in g5), "via_source_cube": sum(r["via"] == "source+cube" for r in g5),
                        "max_dE": max((r["dE"] for r in g5 if r["dE"] is not None), default=0.0),
                        "pass": all(r["dE"] is not None and r["dE"] <= T["G5_dE_max"] for r in g5)}}
    res.update({"gates": gates, "all_pass": all(g["pass"] for g in gates.values()),
                "detail": {"G1": g1, "G23": g23, "G4": g4, "G5": g5}})
    outp = Path(out) if out else Path(str(enc) + ".grade-gates.json")
    outp.write_text(json.dumps(res, indent=1))
    G = gates
    print(f"grade gates {Path(enc).name}: "
          f"G1 {'PASS' if G['G1_white_board']['pass'] else 'FAIL'} C*ab max {G['G1_white_board']['max_chroma']} ({G['G1_white_board']['measured_frames']} fr) | "
          f"G2 {'PASS' if G['G2_skin_hue']['pass'] else 'FAIL'} hue {G['G2_skin_hue']['hue_min']}..{G['G2_skin_hue']['hue_max']} shift {G['G2_skin_hue']['median_shift_vs_source']} | "
          f"G3 {'PASS' if G['G3_face_luma']['pass'] else 'FAIL'} face {G['G3_face_luma']['luma_min']}..{G['G3_face_luma']['luma_max']} mean {G['G3_face_luma']['luma_mean']} ({G['G3_face_luma']['face_frames']} fr) | "
          f"G4 {'PASS' if G['G4_board_clip']['pass'] else 'FAIL'} clip {G['G4_board_clip']['max_clip_pct']} % near {G['G4_board_clip']['max_near_pct']} % | "
          f"G5 {'PASS' if G['G5_cut_jump']['pass'] else 'FAIL'} {G['G5_cut_jump']['measured']}/{G['G5_cut_jump']['cuts']} cuts max dE {G['G5_cut_jump']['max_dE']} -> {outp.name}")
    sys.exit(0 if res["all_pass"] else 3)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "measure":
        cmd_measure(a[1], a[2], a[3])
    elif a[0] == "lut":
        cmd_lut(a[1], a[2])
    elif a[0] == "props":
        cmd_props(a[1], a[2:])
    elif a[0] == "gates":
        kw = {}
        rest = a[5:]
        while rest:
            k, v = rest[0], rest[1]; rest = rest[2:]
            kw[{"--overlays": "overlays", "--skip-head": "skip_head", "--out": "out"}[k]] = int(v) if k == "--skip-head" else v
        cmd_gates(a[1], a[2], a[3], a[4], **kw)
    else:
        sys.exit(__doc__)
