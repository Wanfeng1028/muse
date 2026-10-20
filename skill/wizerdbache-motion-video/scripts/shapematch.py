"""Shape-to-shape (shape match) instrument: does the dominant shape before a transition become
(or get replaced in the same place by) the dominant shape after it, so the eye stays on one spot?

For each transition time t (from a segments.py file or given by hand) the tool takes a foreground
mask a stable moment before (t - PRE) and after (t + POST), and every frame in between.

Foreground: a pixel that differs from the frame's own background by more than FG_THR (max channel
difference, 0-255). The background is a quadratic surface per channel fitted to the frame's border
ring (outer 5 %), refitted twice with outliers dropped, so a flat ground and a slow gradient ground
both work; a frame whose ring is mostly NOT background (a full-bleed layout, a textured or
photographic ground) has no background model and is "undetermined", never guessed. A pale object on a
smooth ground (a white card on a pastel gradient) differs from the ground by less than FG_THR but has
edges, so closed edge blobs are added when the ring itself carries almost no edges (EDGE_RING_MAX).
The mask is closed and its outer contours filled (a silhouette); the DOMINANT SHAPE is the largest
connected component.

Per transition it reports
    iou            IoU of the two dominant-shape masks; iou_all = IoU of every foreground blob
    centroid_norm  distance between their centroids / frame diagonal
    area_ratio     smaller area / larger area (1 = same size)
    hu_dist        cv2.matchShapes (Hu moments, I1) of the two largest outer contours; 0 = identical
                   outline up to position, scale and rotation. Reported, NOT used by the label
                   (a circle turning into a square is a shape match with a nonzero hu_dist)
    dip_ratio      weakest in-between foreground contrast / the weaker end's; below DIP_FRAC (or the
                   shape missing in a frame) = the shape dips through the ground
    cut_share      largest single frame-to-frame mask change / total A->B mask change: near or above
                   1 = one-frame cut, low = spread over several frames = a morph
    continuous     no dip and cut_share < CUT_SHARE (checked when the masks differ, 1-iou >= 0.15)
    morph_frames   frames covered by the run of mask changes >= MORPH_STEP (0.03) around the largest one;
                   a LOWER BOUND of the visible morph (a silhouette that barely changes adds no frames)
and a label, tested in this order
    unrelated           centroid_norm > T_CENTROID: the dominant shape moved
    dip-through-ground  same spot, but the shape's contrast to the ground collapses in between and the
                        size is comparable (area_ratio >= T_AREA); a much smaller/larger one = unrelated
    static-shape        iou_all and area_ratio >= T_STATIC: the layout / silhouette is untouched (a fixed
                        skeleton or persistent container; only its content changed). Not a shape transition
    shape-match         same spot and continuous: present and changing gradually all the way
    same-place-replace  same spot, a cut (not continuous), masks overlap (iou >= T_IOU, area_ratio >= T_AREA)
    unrelated           anything else
    undetermined        no background model / no dominant shape / full-bleed shape / dominant share of the
                        foreground below MIN_DOMINANT (several shapes) on either side; reason is in the row
The positive family is {shape-match, same-place-replace}; only shape-match is a continuous morph.

Calibration (2026-09-30). Selftest: synthetic clips, see --selftest. Real controls, all read AFTER the
selftest passed; raw files under <outdir>/shapematch*.json, one strip PNG per transition next to
them (pre frame | pre mask | middle frame | post mask | post frame). Event times were read off 0.1-0.2 s
frame sheets, NOT taken from the tool (C03 and C05 by hand with explicit t:pre:post anchors, C19 from its
analysis table, C07 from segments.py --crop events, C17 from its analysis 14.0 / 24.0 / 34.0 s); C05
11.78 s was re-centred once after its first window (12.0 s) was seen to miss the morph.
    known-true  C05 (one UI shape morph, 60 fps, 720x720, flat ground, 11 windows): shape-match 8,
                same-place-replace 1, unrelated 1, static-shape 1 (the loop-closing toast -> button, silhouette
                0.96 alike). shape-match: iou 0.18-0.39, centroid 0.001-0.019, area_ratio 0.18-0.67,
                morph 9-14 frames (0.15-0.23 s).
                C03 (mascot / cosmos, 24 fps, 12 windows; 10 named pairs from its analysis + 2 eye-zoom
                windows): shape-match 4 (rainbow band -> DNA 11.9 s, DNA -> spiral 12.75 s, spiral -> dotted
                spiral 13.35 s, black-hole disc 19.3 s), same-place-replace 1 (flock -> galaxy 17.4 s),
                dip-through-ground 1, unrelated 4, undetermined 2 (both eye-zoom windows: 6.8 s a full-bleed
                close-up, 29.1 s no shape found on the paper-grain ground). shape-match: iou 0.30-0.83, centroid 0.004-0.063, area_ratio 0.51-0.91, morph 8-16
                frames (0.33-0.67 s).
                C19 (3 events): 0 shape-match; 6.5 s and 20.5 s unrelated, 13.5 s undetermined (several
                shapes). With --crop below the headline (measurements/C19/shapematch_crop.json) 20.5 s reads
                shape-match (centroid 0.123), 6.7 s unrelated, 13.5 s undetermined. C19 is NOT confirmed.
    known-false C07 Pro (6 section changes): static-shape 3 (12.05, 24.05, 31.27 s), dip-through-ground 1
                (19.23 s), unrelated 2 (7.55, 38.35 s). C07 API (6 transitions): unrelated 3, dip 1,
                same-place-replace 1 (14.45 s, FALSE POSITIVE: a headline block swapped in place while the
                skeleton mostly stays, iou_all 0.55), undetermined 1. C17 chapter cards 14.0 / 24.0 / 34.0 s:
                dip-through-ground 3 (each card comes out of black).
                Over the 15 known-false transitions: shape-match 0, positive family 1.
    thresholds  each sits between the nearest readings of both sides:
                T_CENTROID 0.14   between 0.123 (C19 cropped 20.5 s, continuous known-true) and 0.160
                                  (C07 API 21.8 s, continuous known-false); the full-frame C19 20.5 s is 0.145
                                  and reads unrelated: C19 sits on the line
                T_STATIC 0.92     iou_all of the fixed skeletons 0.95-0.97 vs 0.88 (C07 Pro 19.23 s); the
                                  known-true dominant iou is <= 0.83
                DIP_FRAC 0.4      same-spot rows: dips 0.0-0.356 (C07 API 33.9 s 0.356) vs non-dips >= 0.472
                CUT_SHARE 0.83    continuous morphs <= 0.79 (C03 11.9 s) vs cuts >= 0.875 (C03 13.7 s);
                                  the thinnest margin, +-0.04
                T_IOU 0.5, T_AREA 0.25, MIN_DOMINANT 0.5, EDGE_RING_MAX 0.12 (C19 ring 0.06-0.09, C03 paper
                grain 0.19-0.33): set from these few readings, not constrained by them
    n is small (41 real windows in 6 videos of 24/30/60 fps: 26 known-true, 15 known-false): a threshold is
    a reading between two observed clusters, not a population estimate.
    Added afterwards, thresholds NOT changed (C22, 30 fps, 10 windows, measurements/C22/shapematch.json;
    times read from a 0.1 s sheet): circle -> rounded square 4.25 s and rounded square -> triangle 4.7 s read
    same-place-replace, not shape-match, because the shape ROTATES while morphing: the mask path is longer than
    the net change, so cut_share is 1.28 / 1.41 although the per-frame steps are smooth (0.19-0.37 over 8
    frames); a path-based share (max step / sum of steps) was tried on all controls and does not separate cuts
    from morphs, so cut_share stays. Triangle -> flower 5.2 s unrelated (iou 0.45, one 0.54 step at the end);
    flower -> dot field 5.6 s shape-match (iou 0.89) although the ground swaps black -> cream in one frame: a
    ground swap is invisible to a ground-relative mask; torus -> wireframe cube 8.7 s shape-match, sphere ->
    torus 8.05 s same-place-replace; ground swaps cream -> blue 7.5 s undetermined, cube -> yellow 9.35 s
    unrelated; the red ground that fills the frame at 1.85 s becomes the new "ground" (the word on it is read
    as the shape: dip-through-ground).

What it cannot determine: which of several shapes is "the" dominant shape (the biggest blob wins; a
scene whose biggest blob holds under MIN_DOMINANT of the foreground is undetermined, e.g. C19's sticky
notes); anything on a textured, photographic or full-bleed ground (no background model: C03's paper-grain
mascot scenes and the eye zoom); pale objects on a gradient ground (C19: the dashboard is found by its
edges, the headline text joins the same blob, and a fade-and-regrow morph reads as a mask jump, so C19's
known-true morphs are not confirmed); white-on-off-white shapes mid-morph (C05 9.9 s card -> search bar
reads as a cut); whether the shape is the SAME object semantically (a mask overlap, not identity); a
dissolve between two same-place shapes reads shape-match (frame by frame the mask never vanishes and
never jumps, see the selftest's documented limit), read the strip; a fixed-skeleton headline swap can
read same-place-replace (C07 API 14.45 s); a shape that changes identity while travelling (a rocket's arc
becoming a moon horizon, C03 25.2 s) leaves the spot and reads unrelated; a ground change in one frame
(C03 13.7 s, navy to peach) reads as a cut. Anchors are chosen from the event time: an event time off by
more than PRE puts an anchor inside the morph, and neighbours closer than PRE + POST shorten the window
(give t:pre:post to pin it). Sizes are SCREEN-SPACE: a camera zoom in the source multiplies them.

Usage:
    python -X utf8 scripts/shapematch.py <video> --out <file.json> [--segments <segments.json>] [--events t1,t2,..]
                                       [--crop w:h:x:y] [--png <dir>] [--pre 0.6 --post 0.6]
    (an event may be t or t:pre:post; segments.json contributes its kind "transition" events, spans are skipped)
    python -X utf8 scripts/shapematch.py --selftest
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import probe  # noqa: E402

WIDTH = 192          # analysis width in px
FG_THR = 40          # max-channel difference from the background model
RING_FRAC = 0.05     # border ring thickness (fraction of the short side)
BG_DEG = 2          # background surface: 1 = plane, 2 = quadratic in (x, y)
MIN_RING_BG = 0.6    # share of ring pixels that must fit the background model
EDGE_THR = 2.5       # Sobel magnitude / 8 (grey levels per px) that counts as an edge
EDGE_RING_MAX = 0.12 # edge blobs are used only when at most this share of the border ring is edge
EDGE_CLOSE_FRAC = 0.047
CLOSE_FRAC = 0.03    # closing kernel (fraction of the width)
MIN_AREA = 0.004     # dominant shape smaller than this fraction of the frame = missing
MAX_AREA = 0.80      # dominant shape larger than this = full-bleed, undetermined
MIN_DOMINANT = 0.5   # largest blob / all foreground; below = several shapes, undetermined
PRE, POST = 0.6, 0.6
T_STATIC = 0.92      # iou of ALL foreground (and dominant area ratio) at or above this = nothing changed shape
T_CENTROID = 0.14    # calibrated below (see docstring)
T_IOU = 0.5          # a cut counts as a same-place replace only if the two masks overlap this much
DIP_FRAC = 0.4       # foreground contrast in between below this fraction of the weaker end = a dip through the ground
T_AREA = 0.25
CUT_SHARE = 0.83
CUT_MIN_CHANGE = 0.15
MORPH_STEP = 0.03    # frame-to-frame mask change (1 - iou) that counts as "moving" when timing a morph


# ---------- masks ----------
def load_bgr(path, width=WIDTH, crop=None):
    info = probe(path)
    sw, sh = info["width"], info["height"]
    vf = ""
    if crop:                                  # ffmpeg crop w:h:x:y in source pixels, like segments.py --crop
        sw, sh = int(crop.split(":")[0]), int(crop.split(":")[1])
        vf = f"crop={crop},"
    h = int(round(sh * width / sw / 2)) * 2
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"{vf}scale={width}:{h}:flags=area",
                        "-pix_fmt", "bgr24", "-f", "rawvideo", "-"], capture_output=True, check=True)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    n = a.size // (width * h * 3)
    return a[: n * width * h * 3].reshape(n, h, width, 3), info["fps"]


_grid = {}


def _design(h, w):
    if (h, w) not in _grid:
        ys, xs = np.mgrid[0:h, 0:w]
        b = max(2, int(RING_FRAC * min(h, w)))
        ring = np.zeros((h, w), bool)
        ring[:b] = ring[-b:] = True
        ring[:, :b] = ring[:, -b:] = True
        x, y = xs.ravel() / w - 0.5, ys.ravel() / h - 0.5
        full = np.stack([np.ones(h * w), x, y, x * x, x * y, y * y][: 3 if BG_DEG == 1 else 6], 1)
        _grid[(h, w)] = (full, ring.ravel())
    return _grid[(h, w)]


def background_model(f):
    """Plane per channel fitted to the border ring. Returns (bg[h,w,3] float, ring_bg_share)."""
    h, w = f.shape[:2]
    full, ring = _design(h, w)
    X = full[ring]
    Y = f.reshape(-1, 3)[ring].astype(np.float64)
    keep = np.ones(len(Y), bool)
    med = np.median(Y, axis=0)
    keep = np.abs(Y - med).max(1) <= FG_THR          # first guess: near the ring's median colour
    coef = None
    for _ in range(3):
        if keep.sum() < 10:
            return None, 0.0
        coef = np.linalg.lstsq(X[keep], Y[keep], rcond=None)[0]
        res = np.abs(X @ coef - Y).max(1)
        keep = res <= FG_THR * 0.6
    share = float(keep.mean())
    bg = (full @ coef).reshape(h, w, 3)
    return bg, share


_kern = {}


def _close(m, k):
    if k not in _kern:
        _kern[k] = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, _kern[k])


def frame_mask(f):
    """-> dict(ok, reason, mask (largest blob, filled silhouette, uint8 0/1), area, cx, cy, dominant, ring_bg,
    fg_area, edge)."""
    h, w = f.shape[:2]
    fb = cv2.GaussianBlur(f, (3, 3), 0)
    bg, share = background_model(fb)
    if bg is None or share < MIN_RING_BG:
        return {"ok": False, "reason": f"no background model (ring fits {share:.2f})", "ring_bg": share}
    dist = np.abs(fb.astype(np.float64) - bg).max(2)
    fg = _close((dist > FG_THR).astype(np.uint8), max(3, int(round(CLOSE_FRAC * w))))
    # pale objects on a smooth ground (white card on a pastel gradient) differ from the ground by less than
    # FG_THR but have edges: add closed edge blobs, only when the border ring itself carries no edges
    g = cv2.cvtColor(fb, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mag = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)) / 8.0
    e = (mag > EDGE_THR).astype(np.uint8)
    rb = max(2, int(RING_FRAC * min(h, w)))
    ring_edge = float(np.mean(np.concatenate([e[:rb].ravel(), e[-rb:].ravel(), e[:, :rb].ravel(), e[:, -rb:].ravel()])))
    use_edge = ring_edge <= EDGE_RING_MAX
    if use_edge:
        fg = fg | _close(e, max(3, int(round(EDGE_CLOSE_FRAC * w))))
    cs, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(fg)
    if cs:
        cv2.drawContours(filled, cs, -1, 1, -1)
    n, lab, stats, cen = cv2.connectedComponentsWithStats(filled, connectivity=8)
    if n <= 1:
        return {"ok": True, "empty": True, "area": 0.0, "ring_bg": share, "mask": np.zeros_like(fg), "edge": use_edge,
                "strength": 0.0}
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    area = stats[i, cv2.CC_STAT_AREA] / (h * w)
    tot = filled.sum() / (h * w)
    m = (lab == i).astype(np.uint8)
    return {"ok": True, "empty": area < MIN_AREA, "area": float(area), "cx": float(cen[i][0]),
            "cy": float(cen[i][1]), "dominant": float(area / tot) if tot else 0.0, "ring_bg": share,
            "mask": m, "all": filled, "fg_area": float(tot), "edge": use_edge, "strength": float(dist[m > 0].mean())}


def morph_span(steps):
    """Frames covered by the run of mask-change steps >= MORPH_STEP around the largest step (a one-frame gap
    is bridged). 0 when nothing moved. Length of the change as the mask sees it, not of the visible motion."""
    if not steps or max(steps) < MORPH_STEP:
        return 0
    lo = hi = int(np.argmax(steps))
    while True:
        if lo - 1 >= 0 and steps[lo - 1] >= MORPH_STEP:
            lo -= 1
        elif lo - 2 >= 0 and steps[lo - 2] >= MORPH_STEP:
            lo -= 2
        elif hi + 1 < len(steps) and steps[hi + 1] >= MORPH_STEP:
            hi += 1
        elif hi + 2 < len(steps) and steps[hi + 2] >= MORPH_STEP:
            hi += 2
        else:
            break
    return hi - lo + 1


def iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 1.0


def contour_of(m):
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(cs, key=cv2.contourArea) if cs else None


# ---------- one transition ----------
def measure(frames, fps, t, pre, post):
    n, h, w = len(frames), frames.shape[1], frames.shape[2]
    diag = float(np.hypot(w, h))
    ia = int(np.clip(round((t - pre) * fps), 0, n - 1))
    ib = int(np.clip(round((t + post) * fps), 0, n - 1))
    row = {"t": round(t, 3), "pre_t": round(ia / fps, 3), "post_t": round(ib / fps, 3)}
    ma, mb = frame_mask(frames[ia]), frame_mask(frames[ib])
    for tag, m in (("pre", ma), ("post", mb)):
        if not m["ok"]:
            return {**row, "label": "undetermined", "reason": f"{tag}: {m['reason']}"}, None
        if m.get("empty"):
            return {**row, "label": "undetermined", "reason": f"{tag}: no dominant shape (area {m['area']:.4f})"}, None
        if m["area"] > MAX_AREA:
            return {**row, "label": "undetermined", "reason": f"{tag}: full-bleed shape (area {m['area']:.2f})"}, None
        if m["dominant"] < MIN_DOMINANT:
            return {**row, "label": "undetermined",
                    "reason": f"{tag}: several shapes (largest holds {m['dominant']:.2f} of the foreground)"}, None
    inter = [ma] + [frame_mask(frames[i]) for i in range(ia + 1, ib)] + [mb]
    det = [m for m in inter if m["ok"]]
    vanish = any(m.get("empty") for m in det)
    ref = min(ma["strength"], mb["strength"])
    dip_ratio = min(m["strength"] for m in det) / ref if ref > 0 else 1.0
    dip = vanish or dip_ratio < DIP_FRAC
    steps = [1 - iou(p["mask"], q["mask"]) for p, q in zip(inter, inter[1:]) if p["ok"] and q["ok"]
             and not p.get("empty") and not q.get("empty")]
    io = iou(ma["mask"], mb["mask"])
    io_all = iou(ma["all"], mb["all"])       # every foreground blob: a fixed skeleton keeps this near 1
    d_ab = 1 - io
    cut_share = (max(steps) / d_ab) if steps and d_ab >= CUT_MIN_CHANGE else None
    cont = (not dip) and not (cut_share is not None and cut_share >= CUT_SHARE)
    ca, cb = contour_of(ma["mask"]), contour_of(mb["mask"])
    hu = float(cv2.matchShapes(ca, cb, cv2.CONTOURS_MATCH_I1, 0)) if ca is not None and cb is not None else None
    cn = float(np.hypot(ma["cx"] - mb["cx"], ma["cy"] - mb["cy"]) / diag)
    ar = float(min(ma["area"], mb["area"]) / max(ma["area"], mb["area"]))
    if cn > T_CENTROID:
        label = "unrelated"                      # the dominant shape moved
    elif dip:
        # the shape's contrast to the ground collapses in between; a same-size shape after it is a dip, a
        # very different size is simply another layout
        label = "dip-through-ground" if ar >= T_AREA else "unrelated"
    elif io_all >= T_STATIC and ar >= T_STATIC:
        label = "static-shape"                   # the layout / dominant silhouette is untouched by the transition
    elif cont:
        label = "shape-match"                    # same spot, present and changing gradually all the way
    else:
        label = "same-place-replace" if (io >= T_IOU and ar >= T_AREA) else "unrelated"   # a cut onto an overlapping shape
    cent = [(m["cx"], m["cy"]) for m in det if not m.get("empty")]
    jump = max((np.hypot(a[0] - b[0], a[1] - b[1]) / diag for a, b in zip(cent, cent[1:])), default=0.0)
    row.update({"label": label, "iou": round(io, 3), "iou_all": round(io_all, 3), "centroid_norm": round(cn, 4), "area_ratio": round(ar, 3),
                "hu_dist": None if hu is None else round(hu, 4),
                "area_pre": round(ma["area"], 4), "area_post": round(mb["area"], 4),
                "n_between": max(0, ib - ia - 1), "vanish": bool(vanish), "dip": bool(dip), "dip_ratio": round(float(dip_ratio), 3),
                "strength_pre": round(ma["strength"], 1), "strength_post": round(mb["strength"], 1),
                "min_area_between": round(min((m["area"] for m in det), default=0.0), 4),
                "cut_share": None if cut_share is None else round(cut_share, 3),
                "max_step_change": round(max(steps), 3) if steps else None,
                "steps": [round(x, 3) for x in steps],
                "morph_frames": morph_span(steps), "morph_s": round(morph_span(steps) / fps, 3),
                "max_centroid_step": round(float(jump), 4), "continuous": bool(cont),
                "dominant_pre": round(ma["dominant"], 3), "dominant_post": round(mb["dominant"], 3)})
    return row, (ia, ib, ma, mb)


# ---------- events ----------
def parse_event(x):
    """'t' or 't:pre:post' (explicit anchor offsets in seconds, not shortened by neighbours) -> (t, pre, post)."""
    p = [float(v) for v in x.split(":")]
    return (p[0], p[1] if len(p) > 1 else None, p[2] if len(p) > 2 else (p[1] if len(p) > 1 else None))


def read_events(a):
    ev, skipped = [], []
    if a.segments:
        d = json.loads(Path(a.segments).read_text(encoding="utf-8"))
        for e in d["events"]:
            if e.get("kind", "transition") == "transition":
                ev.append((e["t"], None, None))
            else:
                skipped.append({"start": e.get("start"), "end": e.get("end")})
    if a.events:
        ev += [parse_event(x) for x in a.events.split(",") if x.strip()]
    return sorted(ev), skipped


def analyse(video, events, pre=PRE, post=POST, png=None, width=WIDTH, crop=None):
    """events: list of times or (t, pre, post) tuples; a None offset means the default, shortened so the
    window stays clear of the neighbouring events."""
    frames, fps = load_bgr(video, width, crop)
    events = [(e, None, None) if not isinstance(e, tuple) else e for e in events]
    rows = []
    for k, (t, ep, eq) in enumerate(events):
        lo = (t - events[k - 1][0]) / 2 - 0.05 if k else 1e9
        hi = (events[k + 1][0] - t) / 2 - 0.05 if k + 1 < len(events) else 1e9
        p = ep if ep is not None else max(0.1, min(pre, lo))
        q = eq if eq is not None else max(0.1, min(post, hi))
        row, extra = measure(frames, fps, t, p, q)
        row["pre_s"], row["post_s"] = round(p, 3), round(q, 3)
        rows.append(row)
        if png and extra:
            strip(frames, extra, row, Path(png))
        elif png:
            strip(frames, None, row, Path(png), t=t, fps=fps, pre=p, post=q)
    return {"video": str(video), "fps": fps, "duration_s": round(len(frames) / fps, 3), "transitions": rows,
            "params": {"width": width, "fg_thr": FG_THR, "edge_thr": EDGE_THR, "edge_ring_max": EDGE_RING_MAX,
                       "close_frac": CLOSE_FRAC, "min_area": MIN_AREA, "max_area": MAX_AREA,
                       "min_dominant": MIN_DOMINANT, "t_centroid": T_CENTROID, "t_area": T_AREA, "t_iou": T_IOU, "dip_frac": DIP_FRAC,
                       "cut_share": CUT_SHARE, "t_static": T_STATIC, "pre": pre, "post": post, "crop": crop}}


def strip(frames, extra, row, out, t=None, fps=None, pre=0.6, post=0.6):
    """pre frame | pre mask | mid frame | post mask | post frame, one PNG per transition."""
    out.mkdir(parents=True, exist_ok=True)
    if extra is None:
        n = len(frames)
        ia, ib = int(np.clip(round((t - pre) * fps), 0, n - 1)), int(np.clip(round((t + post) * fps), 0, n - 1))
        ma = mb = None
    else:
        ia, ib, ma, mb = extra
    im = lambda m: cv2.cvtColor((m["mask"] * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR) if m else np.zeros_like(frames[0])
    tiles = [frames[ia], im(ma), frames[(ia + ib) // 2], im(mb), frames[ib]]
    img = np.concatenate(tiles, 1)
    cv2.putText(img, f"t={row['t']} {row['label']}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    ok, buf = cv2.imencode(".png", img)
    (out / f"strip_{row['t']:07.3f}.png").write_bytes(buf.tobytes())


# ---------- calibration (synthetic) ----------
SW, SH, SFPS = 384, 216, 30
BGC = (236, 232, 228)


def canvas(gradient=False):
    f = np.empty((SH, SW, 3), np.float32)
    f[:] = BGC
    if gradient:
        g = np.linspace(-14, 14, SW)[None, :, None] + np.linspace(-6, 6, SH)[:, None, None]
        f += g
    return f


def draw(f, shape, cx, cy, a, b, col, alpha=1.0):
    """shape: 'circle' (radius a), 'rect' (half-width a, half-height b), 'mix' handled by caller."""
    m = np.zeros((SH, SW), np.uint8)
    if shape == "circle":
        cv2.circle(m, (int(cx), int(cy)), int(a), 1, -1)
    else:
        cv2.rectangle(m, (int(cx - a), int(cy - b)), (int(cx + a), int(cy + b)), 1, -1)
    mm = (m * alpha)[..., None].astype(np.float32)
    f[:] = f * (1 - mm) + np.array(col, np.float32) * mm


def morph_frame(k, gradient=False):
    """circle (r 44) -> square (half 44): rounded-square interpolation, k in 0..1."""
    f = canvas(gradient)
    yy, xx = np.mgrid[0:SH, 0:SW]
    dx, dy = np.abs(xx - 192), np.abs(yy - 108)
    p = 2 + 10 * k  # superellipse exponent: 2 = circle, 12 = ~square
    inside = (dx / 44.0) ** p + (dy / 44.0) ** p <= 1.0
    f[inside] = (40, 90, 220)
    return f


def card_frame(k):
    """landscape rect 130x70 -> portrait phone card 64x120, same centre, corners rounding as it goes."""
    f = canvas()
    hw = 65 + (32 - 65) * k
    hh = 35 + (60 - 35) * k
    yy, xx = np.mgrid[0:SH, 0:SW]
    r = 4 + 10 * k
    dx, dy = np.maximum(np.abs(xx - 192) - (hw - r), 0), np.maximum(np.abs(yy - 108) - (hh - r), 0)
    f[dx ** 2 + dy ** 2 <= r * r] = (30, 30, 34)
    return f


def encode(frames, path):
    vid = np.clip(np.stack(frames), 0, 255).astype(np.uint8)
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "v.raw"
        raw.write_bytes(vid[..., ::-1].tobytes())  # BGR -> RGB
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{SW}x{SH}",
                        "-r", str(SFPS), "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "14",
                        str(path)], check=True)


def clip(fn, dur=4.0):
    return [fn(i / SFPS) for i in range(int(dur * SFPS))]


def ease(t, t0, d):
    return float(np.clip((t - t0) / d, 0, 1))


def synth_circle_square(gradient=False):
    return clip(lambda t: morph_frame(ease(t, 1.7, 0.6), gradient)), 2.0          # morph 1.7-2.3


def synth_rect_card():
    return clip(lambda t: card_frame(ease(t, 1.7, 0.6))), 2.0


def synth_cut_in_place():
    def fn(t):
        f = canvas()
        if t < 2.0:
            draw(f, "circle", 192, 108, 44, 0, (40, 90, 220))
        else:
            draw(f, "rect", 192, 108, 40, 40, (200, 90, 30))
        return f
    return clip(fn), 2.0


def synth_dip_in_place():
    """circle fades out to the bare background (0.2 s), a square fades in at the same place (0.2 s)."""
    def fn(t):
        f = canvas()
        if t < 1.8:
            draw(f, "circle", 192, 108, 44, 0, (40, 90, 220))
        elif t < 2.0:
            draw(f, "circle", 192, 108, 44, 0, (40, 90, 220), 1 - (t - 1.8) / 0.2)
        elif t < 2.2:
            draw(f, "rect", 192, 108, 40, 40, (200, 90, 30), (t - 2.0) / 0.2)
        else:
            draw(f, "rect", 192, 108, 40, 40, (200, 90, 30))
        return f
    return clip(fn), 2.0


def synth_cut_other_corner():
    def fn(t):
        f = canvas()
        if t < 2.0:
            draw(f, "circle", 192, 108, 44, 0, (40, 90, 220))
        else:
            draw(f, "rect", 320, 40, 34, 22, (30, 140, 60))
        return f
    return clip(fn), 2.0


def synth_fade_full_layout(full_bleed=False):
    """a centred circle cross-fades (0.6 s) into a layout of large panels: 3 panels, ~70 % of the frame
    (bare ground at the border), or a full-bleed one (four colour bands, no ground left) when full_bleed."""
    def layout():
        f = canvas()
        if full_bleed:
            for k, col in enumerate([(60, 120, 200), (200, 140, 40), (90, 180, 90), (150, 60, 160)]):
                f[k * SH // 4:(k + 1) * SH // 4] = col
            return f
        draw(f, "rect", 100, 108, 70, 84, (200, 90, 30))
        draw(f, "rect", 262, 70, 90, 50, (30, 140, 60))
        draw(f, "rect", 262, 160, 90, 40, (40, 90, 220))
        return f

    b = layout()

    def fn(t):
        f = canvas()
        draw(f, "circle", 192, 108, 44, 0, (40, 90, 220))
        k = ease(t, 1.7, 0.6)
        return (1 - k) * f + k * b
    return clip(fn), 2.0


def synth_panel_dim_swap():
    """a fixed-skeleton panel (same frame, same place) dims into the ground and returns with other content:
    the silhouette never changes, the contrast collapses for 0.2 s (a C07-style section change)."""
    def fn(t):
        f = canvas()
        yy, xx = np.mgrid[0:SH, 0:SW]
        inside = (np.abs(xx - 192) <= 100) & (np.abs(yy - 108) <= 60)
        if t < 1.8:
            col, k = np.array((60, 50, 40), np.float32), 1.0
        elif t < 2.0:
            col, k = np.array((60, 50, 40), np.float32), 1 - (t - 1.8) / 0.2
        elif t < 2.2:
            col, k = np.array((40, 110, 60), np.float32), (t - 2.0) / 0.2
        else:
            col, k = np.array((40, 110, 60), np.float32), 1.0
        f[inside] = f[inside] * (1 - k) + col * k
        return f
    return clip(fn), 2.0


def synth_panel_cut():
    """the same fixed panel, its content swapped by a hard cut (a fixed-skeleton section change)."""
    def fn(t):
        f = canvas()
        yy, xx = np.mgrid[0:SH, 0:SW]
        inside = (np.abs(xx - 192) <= 100) & (np.abs(yy - 108) <= 60)
        f[inside] = (60, 50, 40) if t < 2.0 else (40, 110, 60)
        return f
    return clip(fn), 2.0


def synth_dissolve_in_place():
    """circle -> square as a 0.6 s dissolve (both drawn with complementary alpha). NOT a pass criterion:
    printed so the reading is on record (see 'what it cannot determine')."""
    def fn(t):
        f = canvas()
        k = ease(t, 1.7, 0.6)
        draw(f, "circle", 192, 108, 44, 0, (40, 90, 220), 1 - k)
        draw(f, "rect", 192, 108, 40, 40, (200, 90, 30), k)
        return f
    return clip(fn), 2.0


POSITIVE = {"shape-match", "same-place-replace"}


def selftest():
    cases = [  # name, builder, accepted labels
        ("known-true: circle -> square morph in place (0.6 s)", synth_circle_square, {"shape-match"}),
        ("known-true: rectangle -> phone-card reshape, same centre (0.6 s)", synth_rect_card, {"shape-match"}),
        ("known-true: circle -> square morph on a gradient ground", lambda: synth_circle_square(True), {"shape-match"}),
        ("known-true (replace): hard cut circle -> square, same centre and size", synth_cut_in_place,
         {"same-place-replace"}),
        ("known-false: dip through the bare ground, other shape at the same place", synth_dip_in_place,
         {"dip-through-ground"}),
        ("known-false: fixed panel dims into the ground and returns with other content", synth_panel_dim_swap,
         {"dip-through-ground"}),
        ("known-false: fixed panel, content swapped by a hard cut (same silhouette)", synth_panel_cut,
         {"static-shape"}),
        ("known-false: hard cut centred shape -> unrelated shape in another corner", synth_cut_other_corner,
         {"unrelated"}),
        ("known-false: cross-fade to a full-screen 3-panel layout", synth_fade_full_layout, {"unrelated"}),
        ("known-false: cross-fade to a full-bleed layout (no ground left)", lambda: synth_fade_full_layout(True),
         {"undetermined"}),
    ]
    ok = True
    labels, lens = {}, {}
    with tempfile.TemporaryDirectory() as td:
        for name, build, want in cases:
            frames, t = build()
            p = Path(td) / "s.mp4"
            encode(frames, p)
            r = analyse(p, [t])["transitions"][0]
            good = r["label"] in want
            labels[name] = r["label"]
            lens[name] = r.get("morph_frames")
            keys = ("iou", "centroid_norm", "area_ratio", "continuous", "cut_share", "dip_ratio")
            print(f"{name}: {r['label']} (want {'|'.join(sorted(want))}) "
                  f"{ {k: r.get(k) for k in keys if k in r} } {r.get('reason', '')} -> {'ok' if good else 'FAIL'}")
            ok &= good
        card = lens["known-true: rectangle -> phone-card reshape, same centre (0.6 s)"]
        cut = lens["known-true (replace): hard cut circle -> square, same centre and size"]
        circ = lens["known-true: circle -> square morph in place (0.6 s)"]
        good = abs(card - 0.6 * SFPS) <= 3 and cut <= 2
        print(f"morph length in frames: rect -> card {card} (truth {round(0.6 * SFPS)} +-3), hard cut {cut} (want <= 2); "
              f"circle -> square {circ} of {round(0.6 * SFPS)} (a lower bound: the silhouette barely changes in the "
              f"tail) -> {'ok' if good else 'FAIL'}")
        ok &= good
        frames, t = synth_dissolve_in_place()
        p = Path(td) / "d.mp4"
        encode(frames, p)
        r = analyse(p, [t])["transitions"][0]
        print(f"documented limit (not a criterion): 0.6 s dissolve circle -> square in place reads {r['label']} "
              f"(iou {r.get('iou')}, cut_share {r.get('cut_share')}, dip_ratio {r.get('dip_ratio')})")
        # positive control: both required positives fired (a shape-match family label), no negative did
        pos = [v for k, v in labels.items() if k.startswith("known-true")]
        neg = [v for k, v in labels.items() if k.startswith("known-false")]
        good = all(v in POSITIVE for v in pos) and not any(v in POSITIVE for v in neg)
        print(f"positives fire ({len(pos)}/{len(pos)} known-true in the shape-match family), "
              f"negatives silent ({len(neg)} known-false outside it): {good}")
        ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--segments", help="segments.json from scripts/segments.py (kind 'transition' events)")
    ap.add_argument("--events", help="comma-separated transition times in seconds; t:pre:post sets that event's anchor offsets")
    ap.add_argument("--pre", type=float, default=PRE)
    ap.add_argument("--post", type=float, default=POST)
    ap.add_argument("--crop", help="ffmpeg crop w:h:x:y in source pixels: measure only this region (e.g. below a headline)")
    ap.add_argument("--png", help="directory for one before/mask/mid/mask/after strip per transition")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    ev, skipped = read_events(a)
    if not ev:
        sys.exit("no events: give --segments or --events")
    res = analyse(a.video, ev, a.pre, a.post, a.png, crop=a.crop)
    res["skipped_spans"] = skipped
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    for r in res["transitions"]:
        if r["label"] == "undetermined":
            print(f"  {r['t']:7.2f}s  undetermined  {r['reason']}")
        else:
            print(f"  {r['t']:7.2f}s  {r['label']:19s} iou {r['iou']:.2f}  centroid {r['centroid_norm']:.3f}  "
                  f"area {r['area_ratio']:.2f}  hu {r['hu_dist']}  cont {r['continuous']}")


if __name__ == "__main__":
    main()
