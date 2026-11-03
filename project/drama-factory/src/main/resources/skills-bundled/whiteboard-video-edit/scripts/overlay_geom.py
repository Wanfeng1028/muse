"""Per-frame "keep out" boxes for reel overlays (captions, headline), in OUTPUT pixels.

For every frame of a reel render it maps, through that frame's camera viewport:
  * the speaker's face (Apple Vision face box from pose_4fps.jsonl, interpolated to the frame's time on
    the rough cut timeline, padded for hair above and beard below), and
  * the board item(s) the camera is on (the shot's framing target and, from the start of an
    eased move, the move's destination), from tools/board.json.

Usage as a module: frames = geom(E, kind) with E the edit dir and kind 'vertical' or
'horizontal'. Each entry: {"f", "o", "face": [x0,y0,x1,y1] or None, "targets": [[...]],
"target_names": [...], "scale"}.
"""
from __future__ import annotations
import json, re
from fractions import Fraction
from pathlib import Path

FPS = Fraction(24000, 1001)
fps = float(FPS)
SW, SH = 3840.0, 2160.0
# face box padding, as a fraction of the Vision face box: sides, top (hair), bottom (beard)
PAD_X, PAD_TOP, PAD_BOT = 0.22, 0.45, 0.40
ITEM_PAD = 30.0  # source px around a board item


def load_pose(path: Path):
    rows = [json.loads(l) for l in open(path)]
    rows.sort(key=lambda r: r["path"])
    out = []
    for r in rows:
        f = r.get("face")
        out.append((f[0] * SW, f[1] * SH, (f[0] + f[2]) * SW, (f[1] + f[3]) * SH) if f else None)
    return out  # index k <-> t = k / 4 on the rough cut output timeline


def face_at(pose, t, lo, hi):
    """Union of the pose samples that bracket time t, using only samples inside the rough cut
    segment [lo, hi) that t belongs to (a cut is a jump in the speaker's position, so never mix the two
    sides). Conservative on purpose: a keep out box may be a little big, never late."""
    ks = [k for k in (int(t * 4.0), int(t * 4.0) + 1) if lo - 1e-6 <= k / 4.0 < hi and 0 <= k < len(pose)]
    if not ks:
        # no sample on this side of the cut within the bracket: nearest sample inside the segment
        cand = [k for k in range(int(lo * 4) - 1, int(hi * 4) + 2) if lo - 1e-6 <= k / 4.0 < hi and 0 <= k < len(pose)]
        if not cand:
            cand = [min(max(0, round(t * 4)), len(pose) - 1)]
        ks = [min(cand, key=lambda k: abs(k / 4.0 - t))]
    c = [pose[k] for k in ks if pose[k]]
    if not c:
        return None
    return (min(x[0] for x in c), min(x[1] for x in c), max(x[2] for x in c), max(x[3] for x in c))


def items_of(name: str):
    head = name.split(" ")[0]
    return [p for p in re.split(r"\+", head) if p and p != "him" and p != "no"]


def geom(E: Path, kind: str, pose_path: Path | None = None, board_path: Path | None = None):
    E = Path(E)
    plan = json.load(open(E / "reel/reel-plan.json"))
    props = json.load(open(E / f"reel/props_reel_{kind}.json"))
    board = json.load(open(board_path or (E / "tools/board.json")))
    pose = load_pose(pose_path or (E / "frames/pose_4fps.jsonl"))
    OW, OH = props["outW"], props["outH"]
    cam = props["camera"]
    segs = plan["segments"]
    shots = plan[kind]["shots"]
    lfseg = json.load(open(E / "segments.json"))["segments"]
    bounds = [(g["out_frame"] / fps, (g["out_frame"] + g["frames"]) / fps) for g in lfseg]

    def seg_of(o):
        for a, b in bounds:
            if a - 1e-6 <= o < b:
                return a, b
        return bounds[-1]
    total = plan["total_frames"]
    assert len(cam) == total

    def o_of(f):
        for s in segs:
            if s["outFrame"] <= f < s["outFrame"] + s["frames"]:
                return (s["o_frame"] + (f - s["outFrame"])) / fps
        raise ValueError(f)

    pf = E / "reel/faces_perframe.json"
    perframe = json.load(open(pf))["faces"] if pf.exists() else None
    segidx = [None] * total
    for i, sg in enumerate(segs):
        for k in range(sg["outFrame"], sg["outFrame"] + sg["frames"]):
            segidx[k] = i
    same_seg = lambda a, b: segidx[a] == segidx[b]

    def rect(name):
        r = board[name]
        return (r[0] - ITEM_PAD, r[1] - ITEM_PAD, r[2] + ITEM_PAD, r[3] + ITEM_PAD)

    frames = []
    for sh in shots:
        f0, f1 = sh["reel_frame"], sh["reel_frame"] + sh["frames"]
        base = items_of(sh["framing"]["name"])
        for f in range(f0, f1):
            names = list(base)
            for m in sh["moves"]:
                if f >= m["start_frame"]:
                    to = items_of(m["to"]["name"])
                    if f >= m["start_frame"] + m["frames"]:
                        names = to  # move finished: only the destination is "the item the camera is on"
                    else:
                        names = list(dict.fromkeys(names + to))
            x0, y0, w = cam[f]
            s = OW / w
            mp = lambda r: [round((r[0] - x0) * s, 1), round((r[1] - y0) * s, 1), round((r[2] - x0) * s, 1), round((r[3] - y0) * s, 1)]
            o = o_of(f)
            if perframe is not None:
                # exact per frame detection, unioned with the frames either side (same segment)
                c = [perframe[k] for k in (f - 1, f, f + 1) if 0 <= k < total and perframe[k] and same_seg(k, f)]
                fc = (min(x[0] for x in c), min(x[1] for x in c), max(x[2] for x in c), max(x[3] for x in c)) if c else None
            else:
                fc = face_at(pose, o, *seg_of(o))
            face = None
            if fc:
                fw, fh = fc[2] - fc[0], fc[3] - fc[1]
                face = mp((fc[0] - PAD_X * fw, fc[1] - PAD_TOP * fh, fc[2] + PAD_X * fw, fc[3] + PAD_BOT * fh))
            frames.append({"f": f, "o": round(o, 3), "face": face, "targets": [mp(rect(n)) for n in names],
                           "target_names": names, "scale": round((SW if OW > OH else SH * 9 / 16) / w, 3), "shot": f0})
    assert len(frames) == total
    return {"outW": OW, "outH": OH, "frames": frames}


def overlap(a, b):
    """Intersection area of two [x0,y0,x1,y1] boxes (0 when they only touch)."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def clip_to_frame(b, OW, OH):
    return [max(0, b[0]), max(0, b[1]), min(OW, b[2]), min(OH, b[3])]
