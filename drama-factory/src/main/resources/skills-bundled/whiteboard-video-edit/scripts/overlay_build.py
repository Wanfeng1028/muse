"""Reel overlays, rendered in the SAME pass as the camera (subpixel_render_ov.mjs composites them):
  * karaoke caption chips: bold CAPS, cap height 60 px, a silver gradient, no stroke, a soft blur
    shadow, no band behind the words (full bleed footage has no seam to cover), 1 to 2 words per chip
  * the headline: a colored panel with light bold CAPS, on screen from frame 0, a spring pop in
    (scale 0.80 -> 1 with a small overshoot, words fading in one after another), a steady hold,
    a quick scale down and fade out, off by about 3.6 s
The colors, the font and the sizes are DEFAULTS read from ../look.json (look.py): change them there.
Placement is measured, not assumed: every frame's keep out boxes (the speaker's face, the board item the
camera is on) come from overlay_geom.py; the headline gets ONE position for its whole life and
the captions one position per shot, the first candidate that is clear on every frame.

Usage: python3 overlay_build.py <edit_dir> <kind> <words.json> <headline text> <out_dir> [cap_override.json]
cap_override.json (optional): {"<shot start frame>": [x, y]} pins that shot's caption centre (for
example when chip_readback.py finds a chip split by the speaker's lav mic); the audit still checks it and the
run stops if a pinned position overlaps the speaker's face, the item, the headline or leaves the safe box.
Writes <out_dir>/overlays.json (layers + per frame placements, read by the renderer),
<out_dir>/layers/*.rgba, <out_dir>/audit.json (per frame overlap numbers) and chips.json.
"""
from __future__ import annotations
import json, math, sys
from fractions import Fraction
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from overlay_geom import geom, overlap  # noqa: E402
from look import LOOK  # noqa: E402

E, KIND, WORDS, HEADLINE, OUT = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), sys.argv[4], Path(sys.argv[5])
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "layers").mkdir(exist_ok=True)
FPS = Fraction(24000, 1001)
fps = float(FPS)
G = geom(E, KIND)
OW, OH, FR = G["outW"], G["outH"], G["frames"]
N = len(FR)
plan = json.load(open(E / "reel/reel-plan.json"))
VERT = OH > OW

FONT_PATH, FONT_INDEX = LOOK["font_path"], LOOK["font_index"]
SILVER_TOP, SILVER_BOT = LOOK["captions"]["gradient_top"], LOOK["captions"]["gradient_bottom"]
SHADOW_ALPHA, SHADOW_RADIUS, SHADOW_DY = LOOK["captions"]["shadow_alpha"], LOOK["captions"]["shadow_blur"], LOOK["captions"]["shadow_dy"]
BURGUNDY, IVORY = LOOK["headline"]["panel_color"], LOOK["headline"]["text_color"]  # the default panel is burgundy, the text ivory

# safe areas (critical content box): vertical is the reel safe zone rule (check-reel-safe-zones.py); horizontal keeps 5% margins
SAFE = (60, 250, 950, 1560) if VERT else (96, 54, 1824, 1026)
CLEAR = 14  # px of air between overlay ink and a keep out box


def font_for_cap(cap):
    size = 20
    while True:
        f = ImageFont.truetype(FONT_PATH, size, index=FONT_INDEX)
        bb = f.getbbox("H")
        if bb[3] - bb[1] >= cap or size > 200:
            return f, size
        size += 1


# ------------------------------------------------------------------ chips
CAP = LOOK["captions"]["cap_px"]
FONT, FSIZE = font_for_cap(CAP)
GAP = int(FSIZE * 0.30)
CW, CH = 1080, 150
hb = FONT.getbbox("H", anchor="ls")
BASELINE = CH / 2 - (hb[1] + hb[3]) / 2
CAP_TOP, CAP_BOT = BASELINE + hb[1], BASELINE + hb[3]


def gradient(top, bot, w, h, y0, y1):
    g = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = min(1.0, max(0.0, (y - y0) / (y1 - y0)))
        d.line([(0, y), (w - 1, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bot)))
    return g


GRAD = gradient(SILVER_TOP, SILVER_BOT, CW, CH, CAP_TOP, CAP_BOT)
_m = ImageDraw.Draw(Image.new("RGBA", (8, 8)))


def render_chip(text):
    ws = text.split(" ")
    widths = [_m.textlength(w, font=FONT) for w in ws]
    total = sum(widths) + GAP * (len(ws) - 1)
    x0 = (CW - total) / 2
    shadow = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ds = ImageDraw.Draw(shadow)
    mask = Image.new("L", (CW, CH), 0)
    dm = ImageDraw.Draw(mask)
    x = x0
    for w, wd in zip(ws, widths):
        ds.text((x, BASELINE + SHADOW_DY), w, font=FONT, fill=(0, 0, 0, 255), anchor="ls")
        dm.text((x, BASELINE), w, font=FONT, fill=255, anchor="ls")
        x += wd + GAP
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_RADIUS))
    shadow.putalpha(shadow.getchannel("A").point(lambda v: v * SHADOW_ALPHA // 255))
    im = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    im.alpha_composite(shadow)
    layer = GRAD.convert("RGBA")
    layer.putalpha(mask)
    im.alpha_composite(layer)
    ink = mask.getbbox()  # the glyphs themselves
    return im, ink, total


words = [w for w in json.load(open(WORDS))["words"] if w["text"].strip()]
clips = plan["clips"]
clip_edges = [(c["reel_frame"] / fps, (c["reel_frame"] + c["frames"]) / fps) for c in clips]


def clip_of(t):
    for i, (a, b) in enumerate(clip_edges):
        if a - 0.05 <= t < b + 0.05:
            return i
    return len(clip_edges) - 1


for w in words:
    w["clip"] = clip_of((w["start"] + w["end"]) / 2)
# the last word of a clip loses a trailing comma (the reel cuts there, the sentence does not go on)
for i, w in enumerate(words):
    nxt = words[i + 1] if i + 1 < len(words) else None
    if (nxt is None or nxt["clip"] != w["clip"]) and w["text"].endswith(","):
        w["text"] = w["text"][:-1]

chips = []
i = 0
while i < len(words):
    a = words[i]
    grp = [a]
    if i + 1 < len(words):
        b = words[i + 1]
        cl = len(a["text"]) + 1 + len(b["text"])
        if (not a["text"].endswith((".", "?", "!")) and cl <= 13 and b["clip"] == a["clip"]
                and b["start"] - a["end"] < 0.30 and b["end"] - a["start"] <= 0.95):
            grp.append(b)
    chips.append({"text": " ".join(x["text"] for x in grp).upper(), "s": grp[0]["start"], "e": grp[-1]["end"], "clip": a["clip"]})
    i += len(grp)
# display windows in frames: from the first word's onset (one frame early) to the next chip, or
# to the word end plus 0.35 s when the speaker pauses; never across a reel clip edge by more than the gap
for k, c in enumerate(chips):
    nxt = chips[k + 1] if k + 1 < len(chips) else None
    s = c["s"] - 1 / fps
    if nxt and nxt["s"] - c["e"] < 0.6:
        e = nxt["s"] - 1 / fps
    else:
        e = c["e"] + 0.35
        if nxt:
            e = min(e, nxt["s"] - 1 / fps)
    c["f0"] = max(0, int(math.floor(s * fps + 0.5)))
    c["f1"] = min(N, int(math.floor(e * fps + 0.5)))  # exclusive
for k in range(1, len(chips)):
    chips[k]["f0"] = max(chips[k]["f0"], chips[k - 1]["f1"])
chip_at = [None] * N
for k, c in enumerate(chips):
    for f in range(c["f0"], c["f1"]):
        chip_at[f] = k

layers = {}
chip_ink = {}
for k, c in enumerate(chips):
    im, ink, total = render_chip(c["text"])
    bb = im.getbbox()
    crop = im.crop(bb)
    name = f"chip_{k:03d}"
    (OUT / "layers" / f"{name}.rgba").write_bytes(crop.tobytes())
    layers[name] = {"w": crop.width, "h": crop.height, "file": f"layers/{name}.rgba"}
    # offsets of the crop and of the glyph ink relative to the 1080x150 canvas
    c["bbox"], c["ink"], c["ink_w"] = bb, ink, round(total, 1)
    chip_ink[k] = ink

# ------------------------------------------------------------------ headline (1 to 3 variants)
# HEADLINE holds one headline, or several separated by "||" (split test variants H1, H2, H3).
# Every variant sits at the SAME centre and the captions avoid the union of their boxes, so the
# variants differ only while a headline is on screen (frames 0 to H_FRAMES - 1).
H_CAP = LOOK["headline"]["cap_px"] if VERT else 54
H_MAXW = 790 if VERT else 1200  # leaves room for the pop overshoot inside x 130 to 950
H_PADX, H_PADY = LOOK["headline"]["pad_x"], LOOK["headline"]["pad_y"]
SS = 2  # supersample for the master
H_RADIUS = LOOK["headline"]["corner_radius"]
HM = 26  # margin around the panel in the layer for its shadow and the overshoot
VARIANTS = [v.strip() for v in HEADLINE.split("||") if v.strip()]


def wrap(text, maxw, font):
    import itertools
    ws = text.upper().split()
    best = None
    for nl in (1, 2, 3, 4):
        for cuts in itertools.combinations(range(1, len(ws)), nl - 1):
            parts = [ws[a:b] for a, b in zip((0,) + cuts, cuts + (len(ws),))]
            lines = [" ".join(p) for p in parts]
            wmax = max(_m.textlength(l, font=font) for l in lines)
            if wmax + 2 * H_PADX <= maxw and (best is None or (nl, wmax) < (best[0], best[1])):
                best = (nl, wmax, lines)
        if best:
            return best[2]
    raise SystemExit(f"headline does not fit: {text}")


def layout(text):
    """'NN:line|NN:line' sets each line's cap height (two tier: the hook phrase big, the rest
    smaller); plain text is auto wrapped at H_CAP."""
    if "|" in text:
        spec = []
        for part in text.split("|"):
            part = part.strip()
            if ":" in part and part.split(":", 1)[0].isdigit():
                c, t = part.split(":", 1)
                spec.append((int(c), t.strip().upper()))
            else:
                spec.append((H_CAP, part.upper()))
    else:
        spec = [(H_CAP, l) for l in wrap(text, H_MAXW, font_for_cap(H_CAP)[0])]
    fonts = {}
    for c, _ in spec:
        if c not in fonts:
            fonts[c] = font_for_cap(c)
    W = int(max(_m.textlength(t, font=fonts[c][0]) for c, t in spec) + 2 * H_PADX)
    if W > H_MAXW:
        raise SystemExit(f"headline too wide: {W} > {H_MAXW}: {text}")
    words, y = [], H_PADY
    for li, (c, l) in enumerate(spec):
        F = fonts[c][0]
        hbl = F.getbbox("H", anchor="ls")
        if li:
            y += int(0.42 * min(c, spec[li - 1][0]))
        base = y - hbl[1]
        x = (W - _m.textlength(l, font=F)) / 2
        for wd in l.split(" "):
            words.append((wd, x, base, c))
            x += _m.textlength(wd + " ", font=F)
        y += hbl[3] - hbl[1]
    plain = " ".join(t for _, t in spec)
    return {"text": plain, "spec": spec, "lines": [t for _, t in spec], "fonts": fonts, "words": words, "W": W, "H": int(y + H_PADY)}


LAYS = [layout(v) for v in VARIANTS]


def headline_master(L, word_alpha):
    """Panel plus words at full size, supersampled, with per word opacity."""
    HW, HH = L["W"], L["H"]
    W, Hh = (HW + 2 * HM) * SS, (HH + 2 * HM) * SS
    im = Image.new("RGBA", (W, Hh), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, Hh), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([HM * SS, (HM + 6) * SS, (HM + HW) * SS, (HM + HH + 6) * SS], radius=H_RADIUS * SS, fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(10 * SS))
    im.alpha_composite(sh)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([HM * SS, HM * SS, (HM + HW) * SS, (HM + HH) * SS], radius=H_RADIUS * SS, fill=BURGUNDY + (255,))
    for (wd, x, base, c), a in zip(L["words"], word_alpha):
        if a <= 0:
            continue
        f2 = ImageFont.truetype(FONT_PATH, L["fonts"][c][1] * SS, index=FONT_INDEX)
        t = Image.new("RGBA", (W, Hh), (0, 0, 0, 0))
        ImageDraw.Draw(t).text(((HM + x) * SS, (HM + base) * SS), wd, font=f2, fill=IVORY + (round(255 * a),), anchor="ls")
        im.alpha_composite(t)
    return im


def spring(t, z=0.5, wn=2 * math.pi * 2.4):
    """Underdamped spring step response from 0 to 1 (small overshoot)."""
    if t <= 0:
        return 0.0
    wd = wn * math.sqrt(1 - z * z)
    return 1 - math.exp(-z * wn * t) * (math.cos(wd * t) + z * wn / wd * math.sin(wd * t))


T_EXIT0, T_EXIT1 = 3.30, 3.55
H_FRAMES = int(math.ceil(T_EXIT1 * fps))


def headline_state(f, nwords):
    t = f / fps
    scale = 0.80 + 0.20 * spring(t)
    op = min(1.0, 0.6 + 0.4 * (t / 0.17)) if t < 0.17 else 1.0
    wa = []
    for k in range(nwords):
        u = (t - k * 1.5 / fps) / (3 / fps)
        wa.append(max(0.0, min(1.0, u)))
    if f == 0:
        wa = [1.0 if k < 2 else 0.0 for k in range(nwords)]  # frame 0 already reads
    if t >= T_EXIT0:
        u = min(1.0, (t - T_EXIT0) / (T_EXIT1 - T_EXIT0))
        e = u * u  # ease in: leaves quickly at the end
        scale *= 1 - 0.08 * e
        op *= 1 - e
    return scale, op, wa


H_MAXSCALE = max(headline_state(f, 1)[0] for f in range(H_FRAMES))
H_W = max(L["W"] for L in LAYS)  # the reserve box every variant fits in
H_H = max(L["H"] for L in LAYS)


def place_box(cx, cy, w, h):
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]


def clear_of(box, e):
    b = [box[0] - CLEAR, box[1] - CLEAR, box[2] + CLEAR, box[3] + CLEAR]
    ov = 0.0
    if e["face"]:
        ov += overlap(b, e["face"])
    for r in e["targets"]:
        ov += overlap(b, r)
    return ov


# candidate headline centres, in preference order
if VERT:
    cx_c = [540]
else:
    cx_c = [960, 700, 1220]
cy_c = list(range(int(SAFE[1] + H_H / 2), int(SAFE[3] - H_H / 2) + 1, 10))
hw_full, hh_full = H_W * H_MAXSCALE, H_H * H_MAXSCALE
H_POS = None
for cy in cy_c:
    for cx in cx_c:
        box = place_box(cx, cy, hw_full, hh_full)
        if box[0] < SAFE[0] or box[2] > SAFE[2]:
            continue
        if all(clear_of(box, FR[f]) == 0 for f in range(H_FRAMES)):
            H_POS = (cx, cy)
            break
    if H_POS:
        break
if H_POS is None:
    raise SystemExit("no headline position is clear of the speaker's face and the board item on every frame")
H_BOX = place_box(H_POS[0], H_POS[1], hw_full, hh_full)

# headline layers per variant: one per frame, exact fractional scale about the panel centre
hl_place = [dict() for _ in LAYS]
for v, L in enumerate(LAYS):
    masters = {}
    for f in range(H_FRAMES):
        scale, op, wa = headline_state(f, len(L["words"]))
        key = tuple(round(a, 3) for a in wa)
        if key not in masters:
            masters[key] = headline_master(L, wa)
        M = masters[key]
        Wl, Hl = int(math.ceil(L["W"] * 1.06 + 2 * HM)) + 4, int(math.ceil(L["H"] * 1.06 + 2 * HM)) + 4
        Wl += Wl % 2
        Hl += Hl % 2
        lx = int(round(H_POS[0] - Wl / 2)) & ~1  # top left on even pixels, panel centre exactly at H_POS
        ly = int(round(H_POS[1] - Hl / 2)) & ~1
        ccx, ccy = H_POS[0] - lx, H_POS[1] - ly
        mcx, mcy = M.width / 2, M.height / 2
        k = SS / scale  # master pixels per output pixel
        img = M.transform((Wl, Hl), Image.AFFINE, (k, 0, mcx - k * ccx, 0, k, mcy - k * ccy), resample=Image.BICUBIC)
        if op < 1:
            img.putalpha(img.getchannel("A").point(lambda q: round(q * op)))
        name = f"h{v + 1}_{f:03d}"
        (OUT / "layers" / f"{name}.rgba").write_bytes(img.tobytes())
        layers[name] = {"w": Wl, "h": Hl, "file": f"layers/{name}.rgba"}
        hl_place[v][f] = (name, lx, ly, scale, op)
    # the settled headline (all words, scale 1, full opacity) for the reel cover, at 1x and 2x
    S2 = headline_master(L, [1.0] * len(L["words"]))
    S2.save(OUT / f"headline_h{v + 1}_settled_2x.png")
    S2.resize((S2.width // SS, S2.height // SS), Image.LANCZOS).save(OUT / f"headline_h{v + 1}_settled.png")

# ------------------------------------------------------------------ caption placement per shot
if VERT:
    # centre (the caption law), else one low band just above the safe line, stepping up from there
    y_c = [960, 1440, 1460, 1480] + list(range(1420, 1000, -20)) + list(range(920, 300, -20))
    x_c = [540]
else:
    y_c = [930, 945, 960] + list(range(915, 560, -15))
    x_c = [960, 760, 1160, 600, 1320, 1500, 420]
shots = sorted({e["shot"] for e in FR})
shot_frames = {s: [e["f"] for e in FR if e["shot"] == s] for s in shots}
cap_pos = {}


def chip_box(k, cx, cy):
    ink = chip_ink[k]
    # the chip canvas is 1080 x 150 centred on (cx, cy); ink is in canvas coordinates
    ox, oy = cx - CW / 2, cy - CH / 2
    return [ox + ink[0], oy + ink[1], ox + ink[2], oy + ink[3]]


# background luminance under a box, from the reel's own source frames (reel/faceframes, 960x540
# of the 4K source) mapped through each frame's camera: silver chips need a dark background
props = json.load(open(E / f"reel/props_reel_{KIND}.json"))
CAM = props["camera"]
_lcache = {}


def luma_img(f):
    if f not in _lcache:
        if len(_lcache) > 300:
            _lcache.pop(next(iter(_lcache)))
        _lcache[f] = Image.open(E / "reel/faceframes" / f"r_{f:05d}.jpg").convert("L").resize((480, 270))
    return _lcache[f]


def bg_luma(f, box):
    x0, y0, w = CAM[f]
    k = w / OW  # source px per output px
    sx = 480 / 3840.0
    b = [(x0 + box[0] * k) * sx, (y0 + box[1] * k) * sx, (x0 + box[2] * k) * sx, (y0 + box[3] * k) * sx]
    b = [max(0, int(b[0])), max(0, int(b[1])), min(480, int(math.ceil(b[2]))), min(270, int(math.ceil(b[3])))]
    if b[2] <= b[0] or b[3] <= b[1]:
        return 0.0
    from PIL import ImageStat
    return ImageStat.Stat(luma_img(f).crop(b)).mean[0]


DARK = 110  # mean luma (0 to 255) the chip's background must stay under on every frame, when possible
bg_report = {}
for s in shots:
    fs = shot_frames[s]
    ks = {chip_at[f] for f in fs if chip_at[f] is not None}
    if not ks:
        continue
    found = None
    clear_light = []
    prev = cap_pos[max(cap_pos)] if cap_pos else None
    home = (x_c[0], y_c[0])  # the law position first, then wherever the previous shot sat, then the rest
    cands = [home] + ([prev] if prev and prev != home else []) + [(cx, cy) for cy in y_c for cx in x_c]
    for cx, cy in cands:
        if True:
            ok = True
            for f in fs:
                k = chip_at[f]
                if k is None:
                    continue
                b = chip_box(k, cx, cy)
                if b[0] < SAFE[0] or b[2] > SAFE[2] or b[1] < SAFE[1] or b[3] > SAFE[3]:
                    ok = False
                    break
                if clear_of(b, FR[f]) > 0:
                    ok = False
                    break
                if f < H_FRAMES and overlap([b[0] - CLEAR, b[1] - CLEAR, b[2] + CLEAR, b[3] + CLEAR], H_BOX) > 0:
                    ok = False
                    break
            if ok:
                worst = max(bg_luma(f, chip_box(chip_at[f], cx, cy)) for f in fs if chip_at[f] is not None)
                if worst <= DARK:
                    found = (cx, cy)
                    bg_report[s] = round(worst, 1)
                    break
                clear_light.append(((cx, cy), worst))
    if not found and clear_light:
        found, worst = min(clear_light, key=lambda t: t[1])
        bg_report[s] = round(worst, 1)
    if not found:
        raise SystemExit(f"no caption position is clear for the shot at frame {s}")
    cap_pos[s] = found

CAP_OVERRIDE = {int(k): tuple(v) for k, v in json.load(open(sys.argv[6])).items()} if len(sys.argv) > 6 else {}
for s, xy in CAP_OVERRIDE.items():
    if s not in cap_pos:
        raise SystemExit(f"cap_override names shot {s}, but the shots with captions start at {sorted(cap_pos)}")
    for f in shot_frames[s]:
        k = chip_at[f]
        if k is None:
            continue
        b = chip_box(k, *xy)
        if (b[0] < SAFE[0] or b[2] > SAFE[2] or b[1] < SAFE[1] or b[3] > SAFE[3] or clear_of(b, FR[f]) > 0
                or (f < H_FRAMES and overlap([b[0] - CLEAR, b[1] - CLEAR, b[2] + CLEAR, b[3] + CLEAR], H_BOX) > 0)):
            raise SystemExit(f"cap_override {xy} for shot {s} is not clear at frame {f} (face, item, headline or safe box)")
    print(f"  caption centre pinned for shot {s}: {cap_pos[s]} -> {xy}")
    cap_pos[s] = xy
    bg_report[s] = round(max(bg_luma(f, chip_box(chip_at[f], *xy)) for f in shot_frames[s] if chip_at[f] is not None), 1)

# ------------------------------------------------------------------ schedule + audit
frames_v = [[] for _ in LAYS]
audit = []
for f in range(N):
    e = FR[f]
    row = {"f": f, "face": e["face"], "targets": e["targets"], "target_names": e["target_names"]}
    keep = ([e["face"]] if e["face"] else []) + e["targets"]
    heads = [None] * len(LAYS)
    if f < H_FRAMES:
        boxes = []
        for v, L in enumerate(LAYS):
            name, lx, ly, scale, op = hl_place[v][f]
            heads[v] = [name, lx, ly]
            boxes.append(place_box(H_POS[0], H_POS[1], L["W"] * scale, L["H"] * scale))
        row["headline_boxes"] = [[round(x, 1) for x in b] for b in boxes]
        row["headline_overlap_px_no_air"] = round(max(sum(overlap(b, r) for r in keep) for b in boxes), 1)
    chip = None
    k = chip_at[f]
    if k is not None:
        cx, cy = cap_pos[e["shot"]]
        c = chips[k]
        bx, by = c["bbox"][0], c["bbox"][1]
        lx = int(round(cx - CW / 2 + bx)) & ~1
        ly = int(round(cy - CH / 2 + by)) & ~1
        chip = [f"chip_{k:03d}", lx, ly]  # captions are the LAST layer, nothing covers them
        ink = c["ink"]
        cb = [lx - bx + ink[0], ly - by + ink[1], lx - bx + ink[2], ly - by + ink[3]]
        row["chip"] = c["text"]
        row["chip_box"] = cb
        row["chip_overlap_px_no_air"] = round(sum(overlap(cb, r) for r in keep), 1)
        row["chip_headline_overlap_px"] = round(max(overlap(cb, b) for b in row["headline_boxes"]), 1) if "headline_boxes" in row else 0.0
        row["chip_in_safe"] = cb[0] >= SAFE[0] and cb[2] <= SAFE[2] and cb[1] >= SAFE[1] and cb[3] <= SAFE[3]
    for v in range(len(LAYS)):
        frames_v[v].append(([heads[v]] if heads[v] else []) + ([chip] if chip else []))
    audit.append(row)

for v in range(len(LAYS)):
    json.dump({"outW": OW, "outH": OH, "layers": layers, "frames": frames_v[v]}, open(OUT / f"overlays_h{v + 1}.json", "w"))
json.dump({"outW": OW, "outH": OH, "layers": layers, "frames": frames_v[0]}, open(OUT / "overlays.json", "w"))
same_after = all(frames_v[v][f] == frames_v[0][f] for v in range(len(LAYS)) for f in range(H_FRAMES, N))
json.dump({"kind": KIND, "safe": SAFE,
           "headlines": [{"variant": f"H{v + 1}", "text": L["text"], "lines": L["lines"], "w": L["W"], "h": L["H"]} for v, L in enumerate(LAYS)],
           "headline_pos": H_POS, "headline_frames": H_FRAMES, "exit_s": [T_EXIT0, T_EXIT1], "max_scale": round(H_MAXSCALE, 4),
           "overlay_schedules_identical_from_frame": H_FRAMES if same_after else None,
           "caption_positions": {str(s): cap_pos[s] for s in cap_pos}, "caption_bg_luma_worst": {str(k): v for k, v in bg_report.items()},
           "frames": audit},
          open(OUT / "audit.json", "w"))
json.dump([{k: c[k] for k in ("text", "s", "e", "f0", "f1", "clip")} for c in chips], open(OUT / "chips.json", "w"), indent=1)

hv = [a for a in audit if "headline_boxes" in a]
cv = [a for a in audit if "chip_box" in a]
print(f"{KIND}: {N} frames, {len(chips)} chips, widest chip ink {max(c['ink_w'] for c in chips):.0f} px")
for v, L in enumerate(LAYS):
    print(f"  H{v + 1} {L['lines']} panel {L['W']}x{L['H']}")
print(f"  headlines centred at {H_POS}, frames 0 to {H_FRAMES - 1} ({H_FRAMES / fps:.2f} s); "
      f"overlay schedules identical from frame {H_FRAMES} on: {same_after}")
print(f"  headline frames overlapping face or item (worst variant): {sum(1 for a in hv if a['headline_overlap_px_no_air'] > 0)} of {len(hv)}")
print(f"  caption frames: {len(cv)}; overlapping face or item: {sum(1 for a in cv if a['chip_overlap_px_no_air'] > 0)}; "
      f"overlapping a headline: {sum(1 for a in cv if a['chip_headline_overlap_px'] > 0)}; outside the safe box: {sum(1 for a in cv if not a['chip_in_safe'])}")
from collections import Counter
print("  caption centre per shot:", dict(Counter(tuple(v) for v in cap_pos.values())))
print(f"  background under the chips (worst frame mean luma per shot, want <= {DARK}):", {int(k): v for k, v in bg_report.items()})
