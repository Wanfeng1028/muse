"""Screen Studio style zoom planner for the whiteboard long form (and reused by the reels).

Inputs (output timeline of the rough cut): segments.json, pose_4fps.jsonl (Apple Vision face
and joints every 0.25 s), board.json (item rectangles in 4K source pixels) and the focus
events below (from the transcript). Output: zoom-plan.json, zoom-plan.md and a per-frame
camera file [x0, y0, w] in 4K source pixels (h = w * 9 / 16 for 16:9).

Rules encoded here (from the brief):
  * every cut changes the framing (hard punch in or out), never animated across a cut
  * eased moves only inside a segment: critically damped spring, no overshoot, 0.6 to 1.0 s
  * targets come from the content: each board item when the speaker introduces or marks it, the
    caller and title when the speaker names them, close ups on the speaker for key lines
  * never past 2.0x (viewport at least 1920 px wide in the 3840 px source)
  * the speaker's face (and hands, when they fit) stay inside every speaker framing for the whole hold
"""
from __future__ import annotations
import json, math, sys
from fractions import Fraction
from pathlib import Path

FPS = Fraction(24000, 1001)
SW, SH = 3840.0, 2160.0
MAX_SCALE = 2.0


def ease(u: float, omega: float = 9.0) -> float:
    """Critically damped spring from rest, normalized to land exactly on 1 at u = 1.
    x(u) = 1 - (1 + w u) e^(-w u); monotonic, zero start velocity, no overshoot."""
    if u <= 0: return 0.0
    if u >= 1: return 1.0
    f = lambda v: 1 - (1 + omega * v) * math.exp(-omega * v)
    return f(u) / f(1.0)


class Pose:
    def __init__(self, path: Path):
        rows = [json.loads(l) for l in open(path)]
        rows.sort(key=lambda r: r["path"])
        self.s = []
        for k, r in enumerate(rows):
            f = r.get("face")
            j = r.get("joints", {})
            face = None
            if f:
                face = (f[0] * SW, f[1] * SH, (f[0] + f[2]) * SW, (f[1] + f[3]) * SH)
            wr = [(j[n][0] * SW, j[n][1] * SH) for n in ("lWr", "rWr") if n in j and j[n][2] >= 0.35]
            self.s.append({"t": k / 4.0, "face": face, "wr": wr})

    def span(self, t0: float, t1: float):
        out = [s for s in self.s if t0 - 0.13 <= s["t"] <= t1 + 0.13 and s["face"]]
        return out


def clamp(cx, cy, w):
    w = max(SW / MAX_SCALE, min(SW, w))
    h = w * 9 / 16
    cx = min(max(cx, w / 2), SW - w / 2)
    cy = min(max(cy, h / 2), SH - h / 2)
    return [round(cx, 3), round(cy, 3), round(w, 3)]


def rect_of(F):
    cx, cy, w = F
    h = w * 9 / 16
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def inside(box, F, margin=0.0):
    x0, y0, x1, y1 = rect_of(F)
    m = margin * F[2]
    return box[0] >= x0 + m and box[1] >= y0 + m and box[2] <= x1 - m and box[3] <= y1 - m


def union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def differ(a, b) -> float:
    """>= 1 means the two framings read as a deliberate change at a cut."""
    zs = abs(math.log(a[2] / b[2])) / math.log(1.15)
    d = math.hypot(a[0] - b[0], a[1] - b[1]) / (0.12 * min(a[2], b[2]))
    return max(zs, d)


WIDE = clamp(SW / 2, SH / 2, SW)


def speaker(pose: Pose, t0, t1, scale, face_frac=0.34):
    """Frame the speaker at `scale`; face boxes over the whole hold must stay inside with a margin,
    hands too when they fit. Steps the scale down until the hold fits."""
    sp = pose.span(t0, t1)
    if not sp:
        return WIDE, "no face"
    faces = [s["face"] for s in sp]
    fu = union(faces)
    hands = [(x - 60, y - 60, x + 60, y + 60) for s in sp for (x, y) in s["wr"]]
    fcx = sorted((f[0] + f[2]) / 2 for f in faces)[len(faces) // 2]
    fcy = sorted((f[1] + f[3]) / 2 for f in faces)[len(faces) // 2]
    def frame_at(sc):
        w = SW / sc
        h = w * 9 / 16
        cx = (fu[0] + fu[2]) / 2 if (fu[2] - fu[0]) < 0.8 * w else fcx
        cy = fcy + h * (0.5 - face_frac)
        return clamp(cx, cy, w)

    def hand_ratio(F):
        if not hands:
            return 1.0
        return sum(inside(hb, F) for hb in hands) / len(hands)

    # 1) target scale (or a little looser, never below 1.15) with the face always in and the
    #    hands in for at least 85% of the samples; slide sideways toward the hands if needed
    for sc in (scale, round(scale - 0.1, 3), round(scale - 0.2, 3)):
        if sc < 1.15 and sc != scale:
            continue
        F = frame_at(sc)
        w = F[2]; h = w * 9 / 16
        for dx in (0, 0.04, -0.04, 0.08, -0.08, 0.12, -0.12):
            G = clamp(F[0] + dx * w, F[1], w)
            if inside(fu, G, 0.03) and hand_ratio(G) >= 0.85:
                return G, f"face in, hands {100 * hand_ratio(G):.0f}%"
    # 2) face only, stepping down until the whole face path fits
    sc = scale
    while sc >= 1.0:
        F = frame_at(sc)
        if inside(fu, F, 0.03):
            return F, f"face in, hands {100 * hand_ratio(F):.0f}%"
        sc = round(sc - 0.05, 3)
    return WIDE, "wide (moves too much)"


BOARD_TOP_VIEW = 390.0  # item framings never show more than ~60 px of wall above the board


def keep_board_up(F, R):
    """Slide an item framing down so its top edge sits near the board top (less dark ceiling),
    as long as the item still fits."""
    cx, cy, w = F
    h = w * 9 / 16
    y0 = cy - h / 2
    if y0 < BOARD_TOP_VIEW:
        y0n = min(BOARD_TOP_VIEW, R[1] - 20)
        if y0n + h >= R[3] + 20:
            return clamp(cx, y0n + h / 2, w)
    return F


def item(board, pose: Pose, name, t0, t1, scale):
    F, why = _item(board, pose, name, t0, t1, scale)
    R = board[name]
    return keep_board_up(F, (R[0] - 70, R[1] - 70, R[2] + 70, R[3] + 70)), why


def _item(board, pose: Pose, name, t0, t1, scale):
    R = board[name]
    pad = 70
    R = (R[0] - pad, R[1] - pad, R[2] + pad, R[3] + pad)
    sc = scale
    while True:
        w = SW / sc
        F = clamp((R[0] + R[2]) / 2, (R[1] + R[3]) / 2, w)
        if inside(R, F) or sc <= 1.0:
            break
        sc = round(sc - 0.05, 3)
    # pull the speaker's face in too when it fits beside the item at this scale
    sp = pose.span(t0, t1)
    if sp:
        fu = union([s["face"] for s in sp])
        both = union([R, fu])
        G = clamp((both[0] + both[2]) / 2, (both[1] + both[3]) / 2, F[2])
        if inside(both, G, 0.02):
            return G, f"{name}+face"
        # otherwise favour the item but slide toward the speaker while the item stays fully in
        best = F
        for k in range(1, 21):
            H = clamp(F[0] + (G[0] - F[0]) * k / 20, F[1] + (G[1] - F[1]) * k / 20, F[2])
            if inside(R, H, 0.01):
                best = H
        return best, name
    return F, name


def build(segments, pose, board, events, total_frames, label):
    shots, camera = [], []
    prev = None
    toggle = 0
    n_moves = 0

    def desired(t):
        for e in events:
            if e["t0"] <= t < e["t1"]:
                return e
        return None

    for sg in segments:
        f0, nf = sg["out_frame"], sg["frames"]
        t0 = float(Fraction(f0) / FPS)
        t1 = float(Fraction(f0 + nf) / FPS)
        # phases inside this segment: (start, end, event or None)
        cuts_in = sorted({t0, t1} | {e[k] for e in events for k in ("t0", "t1") if t0 < e[k] < t1})
        phases = []
        for a, b in zip(cuts_in, cuts_in[1:]):
            phases.append([a, b, desired((a + b) / 2)])
        # a phase that starts within 0.45 s of the cut is applied AT the cut
        while len(phases) > 1 and phases[1][0] - t0 < 0.6:
            phases[1][0] = t0
            phases.pop(0)
        # an event that STARTS at this cut gets an eased move in instead of a hard punch:
        # cut on a speaker framing, then ease to the target (Screen Studio style)
        ev0 = phases[0][2]
        if ev0 is not None and ev0["t0"] >= t0 - 0.35 and (phases[0][1] - t0) >= 1.45:
            phases = [[t0, t0 + 0.05, None], [t0 + 0.05, phases[0][1], ev0]] + phases[1:]
        # drop tiny phases (< 0.9 s), they would only add a twitch
        phases = [p for i, p in enumerate(phases) if i == 0 or p[1] - p[0] >= 0.9]

        def framing_for(ph, alt: int):
            a, b, ev = ph
            if ev is None:
                sc = [1.3, 1.0][alt % 2]
                if sc == 1.0:
                    return WIDE, "wide", "wide"
                F, why = speaker(pose, a, b, sc)
                return F, why, f"med {SW / F[2]:.2f}x"
            if ev["kind"] == "close":
                sc = [1.7, 1.35][alt % 2]
                F, why = speaker(pose, a, b, sc, face_frac=0.36)
                return F, why, f"close {SW / F[2]:.2f}x ({ev['why']})"
            sc = [ev.get("scale", 1.8), 1.3][alt % 2]
            F, why = item(board, pose, ev["item"], a, b, sc)
            return F, why, f"{ev['item']} {SW / F[2]:.2f}x"

        # framing at the cut
        F, why, name = framing_for(phases[0], toggle)
        if prev is not None and differ(F, prev) < 1:
            toggle += 1
            G, why2, name2 = framing_for(phases[0], toggle)
            if differ(G, prev) >= 1:
                F, why, name = G, why2, name2
            else:
                # last resort: a 1.2x punch on the speaker (or out of the previous tight framing)
                if prev[2] >= SW * 0.95:
                    F, why = speaker(pose, phases[0][0], phases[0][1], 1.2)
                    name = f"med {SW / F[2]:.2f}x"
                else:
                    w2 = F[2] / 1.2 if F[2] / 1.2 >= SW / MAX_SCALE else min(SW, F[2] * 1.25)
                    F = clamp(F[0], F[1], w2)
                    name = f"{name.split(' ')[0]} {SW / F[2]:.2f}x"
        shot = {"seg": sg["i"], "out_frame": f0, "frames": nf, "t": round(t0, 3), "end_t": round(t1, 3),
                "framing": {"name": name, "cx": F[0], "cy": F[1], "w": F[2], "scale": round(SW / F[2], 3), "fit": why},
                "moves": []}
        cur = F
        # eased moves for later phases
        for ph in phases[1:]:
            a, b, ev = ph
            G, why, name = framing_for(ph, toggle + 1 if ev is None else 0)
            if differ(G, cur) < 0.6:
                continue
            dur = 0.9 if ev and ev["kind"] == "item" else 0.8
            start = a - 0.2  # the camera leads the word slightly, as Screen Studio does
            if start + dur > t1 - 0.2:
                start = t1 - 0.2 - dur
            if start < t0 + 0.3:
                start = t0 + 0.3
            if start + dur > t1 - 0.15 or dur < 0.6:
                continue
            fs = int(round(start * FPS))
            fn = int(round(dur * FPS))
            shot["moves"].append({"start_frame": fs, "frames": fn, "t": round(float(Fraction(fs) / FPS), 3),
                                  "dur_s": round(fn / float(FPS), 3),
                                  "to": {"name": name, "cx": G[0], "cy": G[1], "w": G[2], "scale": round(SW / G[2], 3), "fit": why},
                                  "ease": "critically damped spring, omega 9, normalized, no overshoot"})
            n_moves += 1
            cur = G
        # long speaker holds get one gentle push in (Screen Studio style) at a pause near the middle
        if not shot["moves"] and phases[0][2] is None and (t1 - t0) >= 4.5:
            G, why = speaker(pose, t0 + (t1 - t0) / 2, t1, min(SW / cur[2] * 1.25, 1.75))
            if differ(G, cur) >= 0.8:
                mid = t0 + (t1 - t0) * 0.45
                fs = int(round(mid * FPS)); fn = int(round(0.9 * FPS))
                shot["moves"].append({"start_frame": fs, "frames": fn, "t": round(float(Fraction(fs) / FPS), 3), "dur_s": round(fn / float(FPS), 3),
                                      "to": {"name": f"push in {SW / G[2]:.2f}x", "cx": G[0], "cy": G[1], "w": G[2], "scale": round(SW / G[2], 3), "fit": why},
                                      "ease": "critically damped spring, omega 9, normalized, no overshoot", "why": "long hold, gentle push in"})
                n_moves += 1
                cur = G
        # per-frame camera for this segment
        A = F
        mv = list(shot["moves"])
        for f in range(f0, f0 + nf):
            while mv and f >= mv[0]["start_frame"] + mv[0]["frames"]:
                m = mv.pop(0)
                A = [m["to"]["cx"], m["to"]["cy"], m["to"]["w"]]
            if mv and f >= mv[0]["start_frame"]:
                m = mv[0]
                p = ease((f - m["start_frame"]) / m["frames"])
                B = [m["to"]["cx"], m["to"]["cy"], m["to"]["w"]]
                # interpolate the viewport rectangle (top-left and width): a zoom about a fixed point
                ra, rb = rect_of(A), rect_of(B)
                x0 = ra[0] + (rb[0] - ra[0]) * p
                y0 = ra[1] + (rb[1] - ra[1]) * p
                w = A[2] + (B[2] - A[2]) * p
            else:
                ra = rect_of(A); x0, y0, w = ra[0], ra[1], A[2]
            camera.append([round(x0, 4), round(y0, 4), round(w, 4)])
        shots.append(shot)
        prev = cur
        toggle += 1
    assert len(camera) == total_frames, (len(camera), total_frames)
    return shots, camera, n_moves


def write_md(path, shots, label, events):
    L = [f"# Zoom plan, {label}", "",
         "Times are on the output timeline (the rough cut), in seconds. Scale is relative to the full 4K frame (1.0 = the wide shot, 2.0 = the maximum punch in at 1080p).",
         "Every row starts at a cut with a hard framing change; a move is an eased camera move inside that shot (critically damped spring, no overshoot).", "",
         "| Shot | Time | Framing at the cut | Scale | Moves inside the shot |", "| --- | --- | --- | --- | --- |"]
    for s in shots:
        mv = "; ".join(f"{m['t']:.2f}s, {m['dur_s']:.2f}s ease to {m['to']['name']} ({m['to']['scale']:.2f}x)" for m in s["moves"]) or "hold"
        L.append(f"| {s['seg']} | {s['t']:.2f} to {s['end_t']:.2f} | {s['framing']['name']} | {s['framing']['scale']:.2f} | {mv} |")
    L += ["", "## Content targets", ""]
    for e in events:
        L.append(f"- {e['t0']:.2f} to {e['t1']:.2f}: {e.get('item', 'him, close')} ({e['why']})")
    Path(path).write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    E = Path(sys.argv[1])
    segs = json.load(open(E / "segments.json"))
    board = json.load(open(E / "tools/board.json"))
    if len(sys.argv) < 3:
        raise SystemExit("usage: python3 plan_zooms.py <edit_dir> <label>   (reads tools/focus_<label>.json, tools/board.json, segments.json, frames/pose_4fps.jsonl)")
    LBL = sys.argv[2]
    events = json.load(open(E / f"tools/focus_{LBL}.json"))
    pose = Pose(E / "frames/pose_4fps.jsonl")
    shots, camera, n_moves = build(segs["segments"], pose, board, events, segs["total_frames"], LBL.upper())
    json.dump({"label": f"{LBL.upper()} long form", "fps": "24000/1001", "source_size": [3840, 2160], "output_size": [1920, 1080],
               "camera_units": "per output frame [x0, y0, w] of the 16:9 viewport in 4K source pixels",
               "ease": "critically damped spring x(u)=1-(1+9u)e^(-9u), normalized to end at 1", "events": events, "shots": shots},
              open(E / "zoom-plan.json", "w"), indent=1)
    json.dump({"camera": camera}, open(E / f"camera_{LBL}.json", "w"))
    write_md(E / "zoom-plan.md", shots, f"{LBL.upper()} long form", events)
    scales = [SW / c[2] for c in camera]
    print(f"{len(shots)} shots, {n_moves} eased moves, max scale {max(scales):.3f}, frames {len(camera)}")
