"""Camera moves: global screen motion per section (translation, zoom rate, rotation), from sparse optical flow.

Question it serves (plan.md row 運鏡, stage-2 card T09): which sections have a push-in / pull-out / pan / rotate, and how
fast, in screen coordinates. It measures WHAT THE PICTURE DOES AS A WHOLE, not what made it happen.

Method. Frames are decoded at --fps (default 15) and scaled to --width (default 320), grey. For every frame pair
(i, i + lag) (--lag 0.2 s):
    - corners are found in frame i (goodFeaturesToTrack) and tracked to frame i + lag with pyramidal Lucas-Kanade;
      a point is kept only if tracking it back lands within 0.5 px of where it started (forward-backward check);
    - a similarity transform (translation + uniform scale + rotation about the frame centre) is fitted with RANSAC
      (--rt residual threshold, default 0.6 px) and refined on its inliers;
    - per pair: translation tx, ty (px, content direction on screen, x right / y down), scale s, rotation (positive
      = clockwise on screen), tracked points n, `model_share` (tracked points within --rt of the model),
      `fixed_share` (tracked points that did not move, < 0.3 px), `explained` (1 - sum of squared residuals / sum of
      squared flow: how much of the flow energy the global model carries; undefined when nothing moves).
    A pair is valid when n >= 10 and model_share >= 0.5 (a cut, a dissolve or a flat frame is not). A pair that fails
    at the 0.2 s lag is retried at a 1-frame lag (fast slides), then dropped.
Rates are per second: translation / width (content moves right = positive vx, down = positive vy; both divided by the
frame WIDTH so the units match), zoom = ln(s) / lag (0.05 = 5 % per second; positive = content grows = push-in),
rotation deg/s. The series is smoothed with a running median over 5 pairs.

Sections come from a `segments.py` segments.json (montage spans are reported as `montage` and not measured) or, without
one, from fixed --window s windows. --trim (0.35 s, the segments.py window) is cut from both ends of a section because
the transition itself is not the section's motion. Per section: median rates over valid pairs, median explained /
model_share / fixed_share, valid_share, and the dominant per-pair state (share >= 0.5 of valid pairs, else `mixed`):
    still / push-in / pull-out / pan / rotate  (one flag over its threshold), mixed (>= 2 flags, or no state at 0.5).
`undetermined` when valid_share < 0.4 (too few textured points to fit) or under 0.5 s remains after trimming.
Independently of the label, `moves` lists every run of >= 0.5 s where the smoothed series stays over a threshold
(kind, t0, t1, mean rates): a 1.2 s push-in inside a 5 s section is a `moves` row and a section label `still`.

Thresholds (CALIBRATED, not copied from an external repo's uncalibrated `zoom > 0.006`; see Calibration):
    ZOOM_THR  |zoom rate|  >= 0.03 /s        (3 % per second)
    TRANS_THR speed        >= 0.02 width/s
    ROT_THR   |rotation|   >= 2 deg/s
    EXPLAINED_MIN: a non-still label needs `explained` >= 0.5, else the section is `undetermined` (the flow is not
    one global motion: something inside the frame moves, or two layers move differently).

Also reported: `moves` rows carry scale_x (= exp of the integrated zoom over the run: the total size change of the
picture), peak rates, `at_boundary` (the run touches a segments.py event: a section change and a camera move look the
same in flow, the flag only says which one to check) and a `layer` reading (the points OFF the global model fitted
to their own similarity: an inset that zooms or scrolls while the rest stays).

Calibration (2026-09-30, `--selftest` PASS, exit 0).
    Thresholds come from the noise floor of known-false controls, not from the true-positive side: `--noise` pools the
    smoothed per-sample rates of the known-false cases' camflow.json (C05 C06 C07 C12 C18 C20, all measured sections).
    Pooled n 1177; without C05's shape morph and C06 (7 s of measured video) the maxima are
        |zoom|   0.0181 /s (C12)   threshold 0.03   margin x1.7
        speed    0.0102 w/s (C07)  threshold 0.02   margin x2.0
        |rot|    1.29 deg/s (C18)  threshold 2.0    margin x1.6
    (C05 pooled: zoom max 1.49, speed max 1.26, rot max 2.19: its 4.2-6.0 s morph fills the frame and reads as a camera.)
    Known-false result at these thresholds: 0 non-boundary move runs and 0 non-still sections in C06 C07 C12 C18 C20;
    21 `at_boundary` runs (15 in the first segments set + 6 in C07's second) which are transitions read as camera;
    C05 one `mixed` section (the morph). So on known-false clips a run that is NOT at a boundary was never a false
    positive; a run AT a boundary cannot be told from a camera move (see below).
    Known-true (three cases with camera moves, segments from segments.py, <outdir>/camflow.json):
        C09  0.47-1.93 s push-in x1.67, 6.27-8.00 s pull-out x0.57, 10.93-12.07 s push-in x1.75 (peak zoom +1.28/s)
        C21  0.13-0.80 s pull-out x0.89 (section 0-1.4 s: zoom -0.14/s), 35.40-36.53 s pull-out x0.34
        C01  5.67-6.33 s push-in x1.21, 17.40-17.93 s pull-out x0.86 (both at a boundary: the clip is a montage)
    All three fire. Independent check of the numbers (`--scale-check`: multi-scale template match of a central crop of
    the first frame inside the last, no flow and no RANSAC; measurements/camflow_verify_v00.json):
        C09 0.4-2.2 s  template x1.80 (ncc 0.85)  camflow x1.67; the logo width 127 -> 229 px is x1.80
        C09 6.3-8.0 s  template x0.54 (ncc 0.84)  camflow x0.57
        C09 10.9-12.1  template x2.56 (ncc 0.92)  camflow x1.75: a LOWER BOUND, motion blur hides the fastest phase
        C14 5.0-9.33   template x1.30 (ncc 0.82)  camflow x1.30
        C14 107.3-111.0 template x0.78 (ncc 0.85) camflow x0.76
        C13 0.6-5.6    ncc 0.385: not confirmed (camflow x1.20 is an instrument-only reading)
    Code truth: r9 B1 (a rendered film whose stage drift is 0.012 /s in its source): camflow reads +0.003 (lag 0.2 s)
    to +0.006 (lag 1.0 s) and labels it `still`. A drift of about 1 % per second is UNDER-read by half or more and is
    below the threshold; do not cite a rate below ~0.03 /s as a rate. B1 10.85-11.25 s (whole-frame slide, > 1 width/s)
    is not trackable and stays `undetermined`/invalid.
    Selftest controls (synthetic, --selftest): push-in and pull-out at known rates, pan, rotation, still, static with
    noise, the negative control "camera still, only one element moves or scales" (reads still, layer reads the
    element), a fixed HUD over a push-in (camera is still found), and `--scale-check` on a known push-in (x1.66 for
    x1.67 truth). One info-only probe (an element growing until it fills most of the frame) is printed, not asserted:
    it reads as a camera, which is the limit stated below.

What it cannot determine:
    - 2D stage zoom vs a 3D camera dolly vs the content scaling itself: all give the same global flow. The label is the
      screen motion; the target and the method (production-order.md D1/D2) stay human labels.
    - Parallax: a 3D camera moving through layers gives several flows; the one with most tracked points wins, and
      `explained` drops. Low `explained` means "not one global motion", not "no camera".
    - Content motion that fills most of the frame (a full-width card scrolling, a full-bleed clip zooming) is fitted as
      the global motion; `fixed_share` is low and `explained` high, so it reads as a camera. Only the frame tells.
    - A large fixed overlay (logo, subtitle bar) is ignored as long as most textured points move together;
      `fixed_share` reports how large it was.
    - Flat frames (few corners: black cards, plain colour) are `undetermined`, not `still`.
    - Motion under about 0.3 px per lag (1.5 px/s at width 320) is below the tracker's noise; a drift slower than the
      thresholds reads `still`. A cut or dissolve inside a section adds invalid pairs, not motion.
    - Sections shorter than 0.5 s after trimming, and montage spans, are not measured.
    - A scale or slide TRANSITION and a camera move give the same flow. All 21 runs on the known-false clips (transitions,
      not camera moves) sit at a segments.py event; so do 12 of C09's 14 runs, including its three real push/pull
      moves. `at_boundary` cannot separate them; a reader looks at the frames.
    - A shape or card that morphs or grows until it fills the frame reads as a camera (C05 4.2-6.0 s).
    - A card-level 3D push (perspective tilt of one card while the rest is fixed) does not read as a global camera
      (C21): `layer` sees it, or it is `undetermined`.
    - Whole-frame slides faster than about 1 width/s are lost (tracker range); the scale of a run is a lower bound
      when blur hides its fastest phase.

Usage:
    python -X utf8 scripts/camflow.py <video> --out <file.json> [--segments <segments.json>] [--window 2.0]
    python -X utf8 scripts/camflow.py --selftest
    python -X utf8 scripts/camflow.py --noise a.json b.json ...          (recompute the noise floor of known-false runs)
    python -X utf8 scripts/camflow.py --scale-check VIDEO T0 T1 [--out list.json]   (independent template-match scale)
"""
import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

cv2.setNumThreads(1)

# ---------- calibrated thresholds (see docstring) ----------
ZOOM_THR = 0.03     # 1/s
TRANS_THR = 0.02    # width/s
ROT_THR = 2.0       # deg/s
EXPLAINED_MIN = 0.5
MIN_POINTS = 10
LAYER_MIN_POINTS = 10
QUALITY = 0.002
MIN_MODEL_SHARE = 0.5
MIN_VALID_SHARE = 0.4
MIN_MOVE_S = 0.5
LAYER_MIN_SHARE = 0.3
FIXED_PX = 0.3
FB_PX = 0.5
REL_ERR = 0.05


def decode(video, fps, width):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout
    w0, h0 = (int(x) for x in r.strip().split(",")[:2])
    h = max(2, int(round(h0 * width / w0 / 2)) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={width}:{h}",
                          "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, width)


LK = dict(winSize=(21, 21), maxLevel=4, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.01))


def fit_pair(a, b, rt):
    """Global similarity between two grey frames. Returns a dict, or None if too few points could be tracked."""
    h, w = a.shape
    p0 = cv2.goodFeaturesToTrack(a, maxCorners=400, qualityLevel=QUALITY, minDistance=3, blockSize=3)
    if p0 is None or len(p0) < MIN_POINTS:
        return None
    p1, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p0, None, **LK)
    p0r, st2, _ = cv2.calcOpticalFlowPyrLK(b, a, p1, None, **LK)
    ok = (st.ravel() == 1) & (st2.ravel() == 1) & (np.linalg.norm((p0r - p0).reshape(-1, 2), axis=1) < FB_PX)
    p0, p1 = p0.reshape(-1, 2)[ok], p1.reshape(-1, 2)[ok]
    n = len(p0)
    if n < MIN_POINTS:
        return None
    c = np.array([w / 2.0, h / 2.0], np.float32)
    q0, q1 = p0 - c, p1 - c
    # tracker error grows with displacement (a fast zoom moves the outer points 20+ px per lag): widen the residual
    # threshold by REL_ERR of the typical displacement; a still frame keeps the plain threshold
    rt = rt + REL_ERR * float(np.percentile(np.linalg.norm(q1 - q0, axis=1), 75))
    M, inl = cv2.estimateAffinePartial2D(q0, q1, method=cv2.RANSAC, ransacReprojThreshold=rt, maxIters=800,
                                         confidence=0.995, refineIters=20)
    if M is None:
        return None
    A, t = M[:, :2], M[:, 2]
    pred = q0 @ A.T + t
    res = q1 - pred
    rn = np.linalg.norm(res, axis=1)
    flow = q1 - q0
    fn = np.linalg.norm(flow, axis=1)
    moving = fn >= FIXED_PX
    out = {"n": n, "tx": float(t[0]), "ty": float(t[1]), "s": float(math.hypot(A[0, 0], A[1, 0])),
           "rot": math.degrees(math.atan2(A[1, 0], A[0, 0])),
           "model_share": float((rn < rt).mean()),
           "fixed_share": float((fn < FIXED_PX).mean()),
           # share of the points that move at all which sit on the global model; None when < 5 points move
           "explained": float((rn[moving] < rt).mean()) if moving.sum() >= 5 else None,
           "layer": None}
    # second layer: the points the global model does not carry, fitted about their own centroid
    rest = rn >= rt
    if rest.sum() >= LAYER_MIN_POINTS:
        r0, r1 = p0[rest], p1[rest]
        c2 = r0.mean(axis=0)
        M2, inl2 = cv2.estimateAffinePartial2D(r0 - c2, r1 - c2, method=cv2.RANSAC, ransacReprojThreshold=rt,
                                               maxIters=500, confidence=0.99, refineIters=20)
        if M2 is not None and inl2.sum() >= LAYER_MIN_POINTS and inl2.mean() >= 0.6:
            A2, t2 = M2[:, :2], M2[:, 2]
            out["layer"] = {"tx": float(t2[0]), "ty": float(t2[1]), "s": float(math.hypot(A2[0, 0], A2[1, 0])),
                            "rot": math.degrees(math.atan2(A2[1, 0], A2[0, 0])),
                            "share": float(inl2.sum() / n)}
    return out


def pair_series(frames, fps, lag_s=0.2, rt=0.6):
    """Per-pair rows: t (pair midpoint, s), t0, t1, valid, global rates, optional layer rates."""
    k = max(1, int(round(lag_s * fps)))
    dt = k / fps
    w = frames.shape[2]
    rows = []
    for i in range(len(frames) - k):
        f = fit_pair(frames[i], frames[i + k], rt)
        kk = k
        if (f is None or f["model_share"] < MIN_MODEL_SHARE) and k > 1:
            # a fast move (a whole-frame slide) defeats the tracker at the long baseline: retry with one frame
            f1 = fit_pair(frames[i], frames[i + 1], rt)
            if f1 is not None and f1["model_share"] >= MIN_MODEL_SHARE:
                f, kk = f1, 1
        d_ = kk / fps
        row = {"t": (i + kk / 2) / fps, "t0": i / fps, "t1": (i + kk) / fps, "valid": False, "layer": None, "lag": kk}
        if f is not None and f["model_share"] >= MIN_MODEL_SHARE:
            row.update(valid=True, n=f["n"], vx=f["tx"] / w / d_, vy=f["ty"] / w / d_, zoom=math.log(max(f["s"], 1e-6)) / d_,
                       rot=f["rot"] / d_, model_share=f["model_share"], fixed_share=f["fixed_share"],
                       explained=f["explained"])
            row["speed"] = math.hypot(row["vx"], row["vy"])
            L = f["layer"]
            if L is not None:
                lv = {"vx": L["tx"] / w / d_, "vy": L["ty"] / w / d_, "zoom": math.log(max(L["s"], 1e-6)) / d_,
                      "rot": L["rot"] / d_, "share": L["share"]}
                lv["speed"] = math.hypot(lv["vx"], lv["vy"])
                row["layer"] = lv
        rows.append(row)
    return rows, dt


def view(rows, layer=False):
    """The rows as a series of {t, valid, vx, vy, zoom, rot, speed}: the global model, or the second layer."""
    out = []
    for r in rows:
        src = r.get("layer") if layer else (r if r["valid"] else None)
        if src is None:
            out.append({"t": r["t"], "valid": False})
        else:
            out.append({"t": r["t"], "valid": True, **{k: src[k] for k in ("vx", "vy", "zoom", "rot", "speed")},
                        "explained": r.get("explained")})
    return out


def smooth(series, m=5, min_valid=2):
    """Running median over m pairs for the rate fields (valid pairs only within the window)."""
    keys = ["vx", "vy", "zoom", "rot"]
    out = []
    for i, r in enumerate(series):
        lo, hi = max(0, i - m // 2), min(len(series), i + m // 2 + 1)
        win = [x for x in series[lo:hi] if x["valid"]]
        if not r["valid"] or len(win) < min_valid:
            out.append({"t": r["t"], "valid": False})
            continue
        s = {"t": r["t"], "valid": True}
        for k in keys:
            s[k] = float(np.median([x[k] for x in win]))
        s["speed"] = math.hypot(s["vx"], s["vy"])
        s["explained"] = r.get("explained")
        out.append(s)
    return out


def flags(z, sp, ro):
    return abs(z) >= ZOOM_THR, sp >= TRANS_THR, abs(ro) >= ROT_THR


def state_of(z, sp, ro):
    fz, ft, fr = flags(z, sp, ro)
    n = fz + ft + fr
    if n == 0:
        return "still"
    if n >= 2:
        return "mixed"
    if fz:
        return "push-in" if z > 0 else "pull-out"
    return "pan" if ft else "rotate"


def moves_from(sm, dt, hop):
    """Runs of >= MIN_MOVE_S of consecutive non-still samples on the smoothed series. A gap of invalid samples up to
    0.4 s is bridged (motion blur at the peak of a fast move defeats the tracker), a gap of `still` samples up to
    0.2 s. The run's kind is the state most of its samples are in (>= 0.6), else `mixed`."""
    gap_invalid, gap_still = int(round(0.4 / hop)), int(round(0.2 / hop))
    runs, cur = [], None
    for s in sm:
        st = state_of(s["zoom"], s["speed"], s["rot"]) if s["valid"] else None
        if st not in (None, "still"):
            if cur is None:
                cur = {"rows": [s], "gap": 0, "gap_still": False, "states": [st]}
            else:
                cur["rows"].append(s)
                cur["states"].append(st)
                cur["gap"], cur["gap_still"] = 0, False
            continue
        if cur is not None:
            cur["gap"] += 1
            cur["gap_still"] = cur["gap_still"] or st == "still"
            if cur["gap"] > (gap_still if cur["gap_still"] else gap_invalid):
                runs.append(cur)
                cur = None
    if cur is not None:
        runs.append(cur)
    out = []
    for r in runs:
        rs = r["rows"]
        t0, t1 = rs[0]["t"] - dt / 2, rs[-1]["t"] + dt / 2
        if t1 - t0 < MIN_MOVE_S:
            continue
        mz, ms = abs(float(np.mean([x["zoom"] for x in rs]))), float(np.hypot(np.mean([x["vx"] for x in rs]),
                                                                              np.mean([x["vy"] for x in rs])))
        mr = abs(float(np.mean([x["rot"] for x in rs])))
        if state_of(mz, ms, mr) == "still":  # a brief transient whose run mean stays under every threshold is not a move
            continue
        counts = {k: r["states"].count(k) / len(r["states"]) for k in set(r["states"])}
        top = max(counts, key=counts.get)
        kind = top if counts[top] >= 0.6 else "mixed"
        pk = lambda k: max((x[k] for x in rs), key=abs)  # noqa: E731
        tot, last = 0.0, 0.0  # integral of the zoom rate over the run; an invalid gap keeps the last valid rate
        for x in (x for x in sm if rs[0]["t"] <= x["t"] <= rs[-1]["t"]):
            last = x["zoom"] if x["valid"] else last
            tot += last * hop
        out.append({"kind": kind, "t0": round(t0, 2), "t1": round(t1, 2), "scale_x": round(math.exp(tot), 3),
                    "zoom": round(float(np.mean([x["zoom"] for x in rs])), 4),
                    "vx": round(float(np.mean([x["vx"] for x in rs])), 4),
                    "vy": round(float(np.mean([x["vy"] for x in rs])), 4),
                    "rot": round(float(np.mean([x["rot"] for x in rs])), 2),
                    "peak_zoom": round(pk("zoom"), 4), "peak_speed": round(max(x["speed"] for x in rs), 4),
                    "peak_rot": round(pk("rot"), 2),
                    "explained": round(float(np.median([x["explained"] for x in rs if x["explained"] is not None] or [0])), 3)})
    return out


def section_row(rows, sm, sml, t0, t1, dt, trim, first, last, montage=False):
    a = t0 + (0 if first else trim)
    b = t1 - (0 if last else trim)
    base = {"start": round(t0, 3), "end": round(t1, 3)}
    if montage:
        return {**base, "label": "montage"}
    idx = [i for i, r in enumerate(rows) if r["t0"] >= a - 1e-6 and r["t1"] <= b + 1e-6]
    sel = [(rows[i], sm[i]) for i in idx]
    if b - a < 0.5 or not sel:
        return {**base, "label": "undetermined", "why": "under 0.5 s left after trimming"}
    valid = [(r, s) for r, s in sel if r["valid"] and s["valid"]]
    vs = len(valid) / len(sel)
    row = {**base, "measured": [round(a, 3), round(b, 3)], "valid_share": round(vs, 3)}
    if vs < MIN_VALID_SHARE:
        return {**row, "label": "undetermined", "why": "too few valid pairs (flat frame, cut or dissolve)"}
    lay = layer_summary([(rows[i], sml[i]) for i in idx])
    if lay is not None:
        row["layer"] = lay
    med = lambda k, src: float(np.median([x[k] for x in src]))  # noqa: E731
    # the rates are medians of the SMOOTHED series, the same series the per-sample states come from
    z, vx, vy, ro = med("zoom", [s for _, s in valid]), med("vx", [s for _, s in valid]), med("vy", [s for _, s in valid]), med("rot", [s for _, s in valid])
    sp = math.hypot(vx, vy)
    ex = [r["explained"] for r, _ in valid if r["explained"] is not None]
    states = [state_of(s["zoom"], s["speed"], s["rot"]) for _, s in valid]
    counts = {k: states.count(k) / len(states) for k in set(states)}
    top = max(counts, key=counts.get)
    label = top if counts[top] >= 0.5 else "mixed"
    exm = float(np.median(ex)) if ex else None
    row.update(zoom_rate=round(z, 4), vx=round(vx, 4), vy=round(vy, 4), speed=round(sp, 4), rot_deg_s=round(ro, 2),
               explained=None if exm is None else round(exm, 3),
               model_share=round(med("model_share", [r for r, _ in valid]), 3),
               fixed_share=round(med("fixed_share", [r for r, _ in valid]), 3),
               n_points=int(med("n", [r for r, _ in valid])),
               state_shares={k: round(v, 3) for k, v in sorted(counts.items())})
    if label != "still" and exm is not None and exm < EXPLAINED_MIN:
        return {**row, "label": "undetermined", "why": f"explained {exm:.2f} < {EXPLAINED_MIN}: not one global motion",
                "would_be": label}
    row["label"] = label
    return row


def layer_summary(sel):
    """The second layer inside a section: pairs where the points off the global model move together.
    `sel` is [(pair row, smoothed layer row)]."""
    pairs = [(r, s) for r, s in sel if r["valid"] and r["layer"] is not None]
    valid_n = sum(1 for r, _ in sel if r["valid"])
    if valid_n == 0:
        return None
    share = len(pairs) / valid_n
    if share < LAYER_MIN_SHARE:
        return None
    sm_ok = [s for _, s in pairs if s["valid"]]
    if not sm_ok:
        return None
    states = [state_of(s["zoom"], s["speed"], s["rot"]) for s in sm_ok]
    counts = {k: states.count(k) / len(states) for k in set(states)}
    top = max(counts, key=counts.get)
    label = top if counts[top] >= 0.5 else "mixed"
    med = lambda k: float(np.median([r["layer"][k] for r, _ in pairs]))  # noqa: E731
    return {"label": label, "pair_share": round(share, 3), "zoom_rate": round(med("zoom"), 4), "vx": round(med("vx"), 4),
            "vy": round(med("vy"), 4), "speed": round(math.hypot(med("vx"), med("vy")), 4),
            "rot_deg_s": round(med("rot"), 2), "points_share": round(med("share"), 3)}


def analyse_frames(frames, fps, sections=None, window=2.0, lag_s=0.2, rt=0.6, trim=0.35, bounds=None):
    rows, dt = pair_series(frames, fps, lag_s, rt)
    sm = smooth(view(rows))
    sml = smooth(view(rows, layer=True), min_valid=3)
    dur = len(frames) / fps
    if sections is None:
        edges = list(np.arange(0.0, dur, window)) + [dur]
        if len(edges) > 2 and edges[-1] - edges[-2] < window * 0.5:
            edges.pop(-2)
        sections = [{"start": edges[i], "end": edges[i + 1], "montage": False} for i in range(len(edges) - 1)]
    out = []
    for i, s in enumerate(sections):
        out.append(section_row(rows, sm, sml, s["start"], s["end"], dt, trim, i == 0, i == len(sections) - 1,
                               bool(s.get("montage"))))
    moves = [{"scope": "global", **m} for m in moves_from(sm, dt, 1.0 / fps)]
    for m in moves:
        if m["explained"] < EXPLAINED_MIN:
            m["note"] = f"explained < {EXPLAINED_MIN}: not one global motion"
    lm = moves_from(sml, dt, 1.0 / fps)
    for m in lm:
        m.pop("explained", None)
    moves += [{"scope": "layer", **m} for m in lm]
    moves.sort(key=lambda m: (m["t0"], m["scope"]))
    # a move that overlaps a section boundary (+- its transition zone) may be the transition itself, not a camera
    zones = [(b["t"] - b["half"], b["t"] + b["half"]) for b in (bounds or [])]
    for m in moves:
        m["at_boundary"] = any(m["t0"] < z1 and m["t1"] > z0 for z0, z1 in zones)
    for sec in out:  # attach the moves that fall in a section
        sec["moves"] = [m for m in moves if m["t0"] < sec["end"] and m["t1"] > sec["start"]]
    valid = [r for r in rows if r["valid"]]
    return {"duration_s": round(dur, 3), "sections": out, "moves": moves,
            "valid_pair_share": round(len(valid) / max(1, len(rows)), 3), "lag_s": round(dt, 3)}, rows, sm


def analyse(video, segments=None, width=320, fps=15, window=2.0, lag_s=0.2, rt=0.6, trim=0.35):
    frames = decode(video, fps, width)
    secs, bounds = None, None
    if segments:
        seg = json.loads(Path(segments).read_text(encoding="utf-8"))
        secs = seg["sections"]
        bounds = []
        for e in seg.get("events", []):
            if e.get("kind") == "span":
                bounds.append({"t": (e["start"] + e["end"]) / 2, "half": (e["end"] - e["start"]) / 2 + 0.2})
            else:
                bounds.append({"t": e["t"], "half": max(trim, e.get("run_s", 0) / 2 + 0.15)})
    res, rows, sm = analyse_frames(frames, fps, secs, window, lag_s, rt, trim, bounds)
    res.update(video=str(video), segments=str(segments) if segments else None,
               params={"width": width, "fps": fps, "lag_s": lag_s, "rt": rt, "trim": trim, "window": window,
                       "zoom_thr": ZOOM_THR, "trans_thr": TRANS_THR, "rot_thr": ROT_THR,
                       "explained_min": EXPLAINED_MIN},
               limits="screen-space global motion only: 2D stage zoom, a 3D camera and content scaling look the same; "
                      "low `explained` = not one global motion; flat frames are undetermined")
    step = max(1, int(round(0.2 * fps)))
    res["series"] = [{"t": round(s["t"], 2), "zoom": round(s["zoom"], 4), "speed": round(s["speed"], 4),
                      "vx": round(s["vx"], 4), "vy": round(s["vy"], 4), "rot": round(s["rot"], 2),
                      "explained": None if s["explained"] is None else round(s["explained"], 2)}
                     for s in sm[::step] if s["valid"]]
    return res, rows, sm


def plot(res, sm, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ok = [s for s in sm if s["valid"]]
    t = [s["t"] for s in ok]
    fig, ax = plt.subplots(3, 1, figsize=(12, 5), sharex=True)
    for a, k, thr, lab in ((ax[0], "zoom", ZOOM_THR, "zoom /s"), (ax[1], "speed", TRANS_THR, "speed width/s"),
                           (ax[2], "rot", ROT_THR, "rot deg/s")):
        a.plot(t, [s[k] for s in ok], lw=0.8)
        for sgn in (1, -1):
            if k != "speed" or sgn == 1:
                a.axhline(sgn * thr, color="grey", ls=":", lw=0.8)
        a.set_ylabel(lab)
        for sec in res["sections"]:
            a.axvline(sec["start"], color="red", lw=0.5)
    ax[2].set_xlabel("s")
    ax[0].set_title(Path(res["video"]).name)
    fig.tight_layout()
    fig.savefig(png, dpi=100)
    plt.close(fig)


# ---------- synthetic scenes ----------
W, H, FPS = 320, 180, 15


def make_canvas(seed=1, cw=1280, ch=720):
    """A UI-like texture: blurred noise at two scales, boxes, and text-like strokes, so corners exist everywhere."""
    rng = np.random.default_rng(seed)
    base = cv2.GaussianBlur(rng.random((ch, cw)).astype(np.float32), (0, 0), 6) * 90
    base += cv2.GaussianBlur(rng.random((ch, cw)).astype(np.float32), (0, 0), 1.5) * 60
    img = base + 80
    for _ in range(160):
        x, y = int(rng.integers(0, cw - 80)), int(rng.integers(0, ch - 40))
        ww, hh = int(rng.integers(20, 80)), int(rng.integers(8, 40))
        cv2.rectangle(img, (x, y), (x + ww, y + hh), float(rng.integers(30, 230)), int(rng.integers(1, 3)))
    for _ in range(140):
        x, y = int(rng.integers(0, cw - 120)), int(rng.integers(0, ch - 10))
        for k in range(int(rng.integers(3, 10))):
            ln = int(rng.integers(6, 20))
            cv2.line(img, (x, y), (x + ln, y), float(rng.integers(20, 240)), 2)
            x += ln + 5
    return np.clip(img, 0, 255).astype(np.float32)


def render(canvas, n, fps, zoom_rate=0.0, vx=0.0, vy=0.0, rot=0.0, noise=1.5, seed=3, ln_scale=None):
    """Camera transform about the screen centre, applied to a static canvas. vx, vy = content velocity in
    width/s (screen), zoom_rate = d ln(scale)/dt, rot = deg/s (clockwise); `ln_scale(t)` replaces the constant
    zoom_rate with any ln(scale) curve (an eased push-in). Returns uint8 [n, H, W]."""
    rng = np.random.default_rng(seed)
    ch, cw = canvas.shape
    base = np.array([[W / cw * 1.6, 0, 0], [0, W / cw * 1.6, 0]], np.float64)  # canvas -> screen, canvas 1.6x wider than view
    base[:, 2] = [W / 2 - base[0, 0] * cw / 2, H / 2 - base[1, 1] * ch / 2]
    out = np.zeros((n, H, W), np.uint8)
    for i in range(n):
        t = i / fps
        s = math.exp(ln_scale(t) if ln_scale is not None else zoom_rate * t)
        th = math.radians(rot * t)
        G = np.array([[s * math.cos(th), -s * math.sin(th)], [s * math.sin(th), s * math.cos(th)]])
        tt = np.array([vx * W * t, vy * W * t])
        c = np.array([W / 2, H / 2])
        A = G @ base[:, :2]
        b = G @ (base[:, 2] - c) + c + tt
        M = np.hstack([A, b[:, None]])
        f = cv2.warpAffine(canvas, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        f = f + rng.normal(0, noise, f.shape)
        out[i] = np.clip(f, 0, 255).astype(np.uint8)
    return out


def paste_card(frames, fps, seed=9, size=(80, 56), zoom_rate=0.0, speed_px=0.0):
    """A textured card drawn over a still frame; it moves right at speed_px px/s and scales at zoom_rate (element motion)."""
    rng = np.random.default_rng(seed)
    card = cv2.GaussianBlur(rng.random((size[1], size[0])).astype(np.float32), (0, 0), 1.2) * 200 + 30
    cv2.rectangle(card, (2, 2), (size[0] - 3, size[1] - 3), 250.0, 1)
    out = frames.copy()
    for i in range(len(out)):
        t = i / fps
        s = math.exp(zoom_rate * t)
        cw, ch = int(size[0] * s), int(size[1] * s)
        if cw < 8 or ch < 8:
            continue
        c = cv2.resize(card, (cw, ch), interpolation=cv2.INTER_LINEAR)
        cx = int(60 + speed_px * t)
        cy = 60
        x0, y0 = cx - cw // 2, cy - ch // 2
        xa, ya = max(0, x0), max(0, y0)
        xb, yb = min(W, x0 + cw), min(H, y0 + ch)
        if xb > xa and yb > ya:
            out[i, ya:yb, xa:xb] = np.clip(c[ya - y0:yb - y0, xa - x0:xb - x0], 0, 255).astype(np.uint8)
    return out


def paste_hud(frames, share_h=28):
    """A fixed overlay bar (subtitle/logo strip) that never moves: dark strip, a few short bright text-like marks."""
    out = frames.copy()
    rng = np.random.default_rng(11)
    bar = np.full((share_h, W), 25, np.uint8)
    for _ in range(6):
        x = int(rng.integers(10, W - 90))
        cv2.line(bar, (x, share_h // 2), (x + int(rng.integers(30, 80)), share_h // 2), 235, 3)
    out[:, H - share_h:, :] = bar
    return out


def _encode(vid, path):
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "v.raw"
        raw.write_bytes(vid.tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{vid.shape[2]}x{vid.shape[1]}",
                        "-r", str(FPS), "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
                        str(path)], check=True)


def _read(frames, thr_sections=None, window=2.0):
    res, _, _ = analyse_frames(frames, FPS, thr_sections, window=window)
    return res


def selftest():
    ok = True
    canvas = make_canvas()
    n = int(4.0 * FPS)

    def check(name, cond, detail):
        nonlocal ok
        print(f"{name}: {detail} -> {'ok' if cond else 'FAIL'}")
        ok &= bool(cond)

    def one(frames, window=4.0):
        r = _read(frames, window=window)
        s = r["sections"][0]
        return r, s

    # positives: known push-in, pull-out, pan, rotate; the measured rate must land near the truth
    for name, kw, key, want, label in (
            ("push-in 0.15/s", dict(zoom_rate=0.15), "zoom_rate", 0.15, "push-in"),
            ("push-in 0.06/s (slow)", dict(zoom_rate=0.06), "zoom_rate", 0.06, "push-in"),
            ("pull-out -0.15/s", dict(zoom_rate=-0.15), "zoom_rate", -0.15, "pull-out"),
            ("pan left 0.12 width/s", dict(vx=-0.12), "vx", -0.12, "pan"),
            ("pan down 0.08 width/s", dict(vy=0.08), "vy", 0.08, "pan"),
            ("rotate 8 deg/s", dict(rot=8.0), "rot_deg_s", 8.0, "rotate")):
        r, s = one(render(canvas, n, FPS, **kw))
        got = s.get(key)
        near = got is not None and abs(got - want) <= 0.25 * abs(want) + (0.004 if key != "rot_deg_s" else 0.4)
        check(f"known-true {name}", s["label"] == label and near,
              f"label {s['label']} (want {label}), {key} {got} (want {want}), explained {s.get('explained')}")
    r, s = one(render(canvas, n, FPS, zoom_rate=0.12, vx=-0.10))
    check("known-true push-in + pan", s["label"] == "mixed", f"label {s['label']} (want mixed)")

    # negatives: nothing moves, or only something inside the frame moves
    r, s = one(render(canvas, n, FPS))
    check("known-false still frame (noise sigma 1.5)", s["label"] == "still" and abs(s["zoom_rate"]) < ZOOM_THR / 2
          and s["speed"] < TRANS_THR / 2, f"label {s['label']}, zoom {s['zoom_rate']}, speed {s['speed']}, rot {s['rot_deg_s']}")
    r, s = one(render(canvas, n, FPS, noise=6.0, seed=5))
    check("known-false still frame, heavy noise (sigma 6)", s["label"] in ("still", "undetermined")
          and abs(s.get("zoom_rate", 0)) < ZOOM_THR and s.get("speed", 0) < TRANS_THR,
          f"label {s['label']}, zoom {s.get('zoom_rate')}, speed {s.get('speed')}")
    still = render(canvas, n, FPS)
    r, s = one(paste_card(still, FPS, zoom_rate=0.5, speed_px=0.0))
    check("known-false camera still, one element scales 50 %/s (card 80x56 px)", s["label"] == "still",
          f"label {s['label']}, zoom {s['zoom_rate']}, speed {s['speed']}, fixed_share {s['fixed_share']}")
    r, s = one(paste_card(still, FPS, zoom_rate=0.0, speed_px=50.0))
    check("known-false camera still, one element moves 50 px/s", s["label"] == "still",
          f"label {s['label']}, zoom {s['zoom_rate']}, speed {s['speed']}, fixed_share {s['fixed_share']}")
    lay = s.get("layer")
    check("  ... the moving element is reported as a layer (pan, 50 px/s = 0.156 width/s), not as the camera",
          lay is not None and lay["label"] == "pan" and abs(lay["vx"] - 0.156) <= 0.03,
          f"layer {None if lay is None else (lay['label'], lay['vx'], lay['points_share'])}")
    r, s = one(paste_hud(render(canvas, n, FPS, zoom_rate=0.15)))
    check("known-true push-in under a fixed overlay bar (15 % of the frame)", s["label"] == "push-in",
          f"label {s['label']}, zoom {s['zoom_rate']}, fixed_share {s['fixed_share']}")

    # sections: a still 2 s then a push-in 2 s, cut in the middle; a section pair keeps its own reading
    a = render(canvas, 2 * FPS, FPS)
    b = render(make_canvas(seed=7), 2 * FPS, FPS, zoom_rate=0.15)
    vid = np.concatenate([a, b])
    sec = [{"start": 0.0, "end": 2.0, "montage": False}, {"start": 2.0, "end": 4.0, "montage": False}]
    r = _read(vid, sec)
    lab = [x["label"] for x in r["sections"]]
    check("known-true sections: still | (cut) | push-in", lab == ["still", "push-in"], f"labels {lab} (want ['still', 'push-in'])")
    mv = [m for m in r["moves"] if m["scope"] == "global"]
    check("moves list: exactly one global push-in run, inside 2.0-4.0 s", len(mv) == 1 and mv[0]["kind"] == "push-in"
          and mv[0]["t0"] >= 1.8, f"{[(m['kind'], m['t0'], m['t1']) for m in mv]}")

    # thresholds: a drift just under stays still, just over fires (the thresholds are the calibrated ones)
    r, s = one(render(canvas, n, FPS, zoom_rate=0.012))
    check("below threshold: drift 0.012/s (the r9 B1 brand-scale rate) reads still", s["label"] == "still",
          f"label {s['label']}, zoom {s['zoom_rate']} (thr {ZOOM_THR}; under-reads slow drift: it is a threshold, not a measurement)")
    r, s = one(render(canvas, n, FPS, zoom_rate=0.045))
    check("above threshold: push-in 0.045/s reads push-in", s["label"] == "push-in", f"label {s['label']}, zoom {s['zoom_rate']}")
    r, s = one(render(canvas, n, FPS, vx=-0.008))
    check("below threshold: pan 0.008 width/s reads still", s["label"] == "still", f"label {s['label']}, speed {s['speed']}")
    r, s = one(render(canvas, n, FPS, vx=-0.03))
    check("above threshold: pan 0.03 width/s reads pan", s["label"] == "pan", f"label {s['label']}, speed {s['speed']}")
    r, s = one(render(canvas, n, FPS, vx=-0.6))
    check("fast pan 0.6 width/s (a whip) reads pan", s["label"] == "pan" and abs(s["vx"] + 0.6) < 0.15,
          f"label {s['label']}, vx {s['vx']}")

    # an eased push-in (smoothstep, ln scale 0.5 over 1.2 s inside a 4 s still): a `moves` run, section label still
    def eased(t):
        u = min(max((t - 1.0) / 1.2, 0.0), 1.0)
        return 0.5 * u * u * (3 - 2 * u)
    r, s = one(render(canvas, n, FPS, ln_scale=eased))
    mv = [m for m in r["moves"] if m["scope"] == "global"]
    check("eased push-in (x1.65 over 1.2 s): one push-in run with scale_x near 1.65", len(mv) == 1
          and mv[0]["kind"] == "push-in" and abs(mv[0]["scale_x"] - math.exp(0.5)) <= 0.15
          and abs(mv[0]["t0"] - 1.0) <= 0.5 and abs(mv[0]["t1"] - 2.2) <= 0.5,
          f"{[(m['kind'], m['t0'], m['t1'], m['scale_x']) for m in mv]}; section label {s['label']} (a short burst is not the section's state)")

    # a flat frame is undetermined, not still
    flat = np.full((n, H, W), 128, np.uint8)
    r, s = one(flat)
    check("flat frames are undetermined (no corners)", s["label"] == "undetermined", f"label {s['label']}")

    # decode path: the push-in encoded with x264 and read back through ffmpeg
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "push.mp4"
        _encode(render(canvas, n, FPS, zoom_rate=0.15), p)
        res, _, _ = analyse(p, width=W, fps=FPS, window=4.0)
        s = res["sections"][0]
        check("encode/decode path (x264 crf 23) push-in 0.15/s", s["label"] == "push-in"
              and abs(s["zoom_rate"] - 0.15) <= 0.04, f"label {s['label']}, zoom {s.get('zoom_rate')}")
        sc = scale_check(p, 0.2, 3.6)
        want = math.exp(0.15 * 3.4)
        check("scale_check (independent template match) on the same push-in, t 0.2 -> 3.6 s",
              sc["confirms"] and abs(sc["best_scale"] - want) <= 0.08, f"best scale {sc['best_scale']} (want {want:.2f}), ncc {sc['ncc']}")
        q0 = Path(td) / "still0.mp4"
        _encode(render(canvas, n, FPS), q0)
        sc0 = scale_check(q0, 0.2, 3.6)
        check("scale_check on a still clip reads scale 1.0", sc0["confirms"] and abs(sc0["best_scale"] - 1.0) <= 0.04,
              f"best scale {sc0['best_scale']}, ncc {sc0['ncc']}")
        q = Path(td) / "still.mp4"
        _encode(render(canvas, n, FPS, noise=3.0), q)
        res, _, _ = analyse(q, width=W, fps=FPS, window=4.0)
        s = res["sections"][0]
        check("encode/decode path (x264 crf 23) still with noise", s["label"] == "still",
              f"label {s['label']}, zoom {s.get('zoom_rate')}")

    # documented limit, not part of the verdict: a card that fills most of the frame and scales reads as a camera
    big2 = np.stack([_scale_big(still[i], i / FPS) for i in range(n)])
    r, s = one(big2)
    print(f"limit (info only): a frame-filling element growing 60 % -> 100 % (12.8 %/s) over a still ground reads label {s['label']}, "
          f"zoom {s.get('zoom_rate')}, fixed_share {s.get('fixed_share')}")
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _scale_big(frame, t, rate=0.128):
    """Info-only limit probe: a frame-filling textured card scales over a still dark ground."""
    rng = np.random.default_rng(21)
    card = cv2.GaussianBlur(rng.random((H, W)).astype(np.float32), (0, 0), 1.2) * 200 + 30
    out = np.full((H, W), 20, np.uint8)
    s = 0.6 * math.exp(rate * t)
    cw, chh = min(W, int(W * s)), min(H, int(H * s))
    c = cv2.resize(card, (cw, chh))
    x0, y0 = (W - cw) // 2, (H - chh) // 2
    out[y0:y0 + chh, x0:x0 + cw] = np.clip(c, 0, 255).astype(np.uint8)
    return out


def scale_check(video, t0, t1, crop=0.3, width=640):
    """Independent check of a push-in / pull-out between two times: the scale at which the central `crop` of frame t0
    best matches frame t1 (multi-scale normalised cross-correlation; no optical flow, no RANSAC). A reading with
    ncc < 0.7 is not a confirmation (content changed, or the crop left the frame)."""
    def grab(t):
        w0, h0 = probe_size(video)
        h = int(round(h0 * width / w0))
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1", "-vf",
                              f"scale={width}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(h, width)
    a, b = grab(t0), grab(t1)
    h, w = a.shape
    ch, cw = int(h * crop), int(w * crop)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    tpl = a[y0:y0 + ch, x0:x0 + cw]
    best = (-1.0, None)
    for s in np.arange(0.4, 3.2, 0.02):
        t2 = cv2.resize(tpl, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        if t2.shape[0] >= h or t2.shape[1] >= w or min(t2.shape) < 24:
            continue
        m = float(cv2.matchTemplate(b, t2, cv2.TM_CCOEFF_NORMED).max())
        if m > best[0]:
            best = (m, round(float(s), 2))
    return {"video": str(video), "t0": t0, "t1": t1, "crop": crop, "best_scale": best[1], "ncc": round(best[0], 3),
            "confirms": bool(best[0] >= 0.7)}


def probe_size(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout
    w, h = (int(x) for x in r.strip().split(",")[:2])
    return w, h


def noise_floor(paths, margin_s=0.8):
    """Rate percentiles of camflow.json series samples away from section boundaries (+- margin_s) and montage spans:
    the noise floor of a set of videos known to have no camera. This is how the thresholds were calibrated."""
    Z, S, R, per = [], [], [], {}
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        bnd = [s["start"] for s in d["sections"]] + [s["end"] for s in d["sections"]]
        mont = [(s["start"], s["end"]) for s in d["sections"] if s["label"] == "montage"]
        z, sp, r = [], [], []
        for x in d["series"]:
            t = x["t"]
            if any(abs(t - b) < margin_s for b in bnd) or any(a - 0.5 < t < b + 0.5 for a, b in mont):
                continue
            z.append(abs(x["zoom"]))
            sp.append(x["speed"])
            r.append(abs(x["rot"]))
        per[p] = (len(z), z, sp, r)
        Z += z
        S += sp
        R += r
    pct = lambda a: [round(float(v), 4) for v in np.percentile(a, [50, 90, 99, 100])] if len(a) else None  # noqa: E731
    for p, (n, z, sp, r) in per.items():
        print(f"{p}: n {n}  |zoom| p50/90/99/max {pct(z)}  speed {pct(sp)}  |rot| {pct(r)}")
    print(f"POOLED n {len(Z)}  |zoom| p50/90/99/max {pct(Z)}  speed {pct(S)}  |rot| {pct(R)}")
    print(f"thresholds in force: zoom {ZOOM_THR}, speed {TRANS_THR}, rot {ROT_THR}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--noise", nargs="+", metavar="camflow.json",
                    help="print the rate percentiles of these outputs away from section boundaries (calibration)")
    ap.add_argument("--scale-check", nargs=3, metavar=("VIDEO", "T0", "T1"),
                    help="independent template-match scale between two times; appends to --out (a json list) if given")
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out", help="output json path (the png goes next to it)")
    ap.add_argument("--segments", help="segments.json from scripts/segments.py; sections come from it")
    ap.add_argument("--window", type=float, default=2.0, help="fixed section length in s when no --segments")
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--fps", type=float, default=15)
    ap.add_argument("--lag", type=float, default=0.2, help="frame-pair baseline in s")
    ap.add_argument("--rt", type=float, default=0.6, help="RANSAC residual threshold in px at --width")
    ap.add_argument("--trim", type=float, default=0.35, help="seconds cut from both ends of a section")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.noise:
        noise_floor(a.noise)
        return
    if a.scale_check:
        r = scale_check(a.scale_check[0], float(a.scale_check[1]), float(a.scale_check[2]))
        print(json.dumps(r, ensure_ascii=False))
        if a.out:
            out = Path(a.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            cur = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
            out.write_text(json.dumps(cur + [r], indent=1, ensure_ascii=False), encoding="utf-8")
        return
    if not a.video or not a.out:
        ap.error("video and --out are required")
    res, rows, sm = analyse(a.video, a.segments, a.width, a.fps, a.window, a.lag, a.rt, a.trim)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    plot(res, sm, out.with_suffix(".png"))
    print(f"{len(res['sections'])} sections, {len(res['moves'])} move runs, valid pairs {res['valid_pair_share']}")
    for s in res["sections"]:
        extra = "" if "zoom_rate" not in s else (f"zoom {s['zoom_rate']:+.3f}/s speed {s['speed']:.3f} w/s "
                                                 f"rot {s['rot_deg_s']:+.1f} expl {s['explained']} fixed {s['fixed_share']}")
        print(f"  {s['start']:7.2f}-{s['end']:7.2f}  {s['label']:13s} {extra}")


if __name__ == "__main__":
    main()
