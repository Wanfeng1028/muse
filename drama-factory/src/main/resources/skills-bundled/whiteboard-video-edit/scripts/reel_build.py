"""Reel timeline, audio and camera plan(s), all cut from a long form's rough cut.

Usage: python3 reel_build.py <edit_dir> <clips.json> <master_audio.wav> <source_video>
clips.json: {"label": "Reel: ...", "clips": [{"o_start", "o_end", "label",
             "v": [[null, ["him", 1.15]], [8.40, ["item", "howmuch", 1.25]]],
             "h": [...] (optional; only when every clip has it is a 16:9 plan made too)}]}
Clip times are on the rough cut OUTPUT timeline (o), picked at pauses (never inside a word).
Shot spec: [o_time or null, target]; null = at the clip start (a cut). Targets: ["him", scale]
or ["item", <board.json key>, scale] (the speaker's face kept in when it fits) or
["item", <key>, scale, "solo"] (the item alone, the speaker's face fully out of the window). Scale is relative to the widest window of the aspect
(1215 x 2160 source px for 9:16, the full 3840 x 2160 for 16:9).
Every reel cut changes framing; eased moves (critically damped spring) land on the board item
as the speaker names it. The vertical plan is a 9:16 window that follows the action in the 4K wide shot.
Writes reel/reel-plan.json, reel/props_reel_<kind>.json (and the identical _abs copy, absolute
source path) and reel/reel_audio.wav (the mastered long form audio cut at the same frame exact
clip edges, 30 ms fades).
"""
from __future__ import annotations
import json, math, subprocess, sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from plan_zooms import Pose, ease, SW, SH  # noqa: E402

E = Path(sys.argv[1]).resolve()
SPEC = json.load(open(sys.argv[2]))
AUDIO = Path(sys.argv[3]).resolve()
SRC = str(Path(sys.argv[4]).resolve())
FPS = Fraction(24000, 1001)
fps = float(FPS)
_t = lambda x: tuple(x) if isinstance(x, list) else x
CLIPS = [(c["o_start"], c["o_end"], c["label"], [(a, _t(b)) for a, b in c.get("h", [])], [(a, _t(b)) for a, b in c["v"]])
         for c in SPEC["clips"]]
HORIZONTAL = all(c.get("h") for c in SPEC["clips"])

segs = json.load(open(E / "segments.json"))["segments"]
board = json.load(open(E / "tools/board.json"))
import re as _re
for c in CLIPS:
    for _, tgt in c[3] + c[4]:
        if tgt[0] == "item" and (tgt[1] not in board or not _re.fullmatch(r"[A-Za-z0-9_]+", tgt[1])):
            raise SystemExit(f"clips.json names board item {tgt[1]!r}: it must be a key of tools/board.json made of letters, digits and _ "
                             f"(overlay_geom.py reads item names back out of framing names)")
pose = Pose(E / "frames/pose_4fps.jsonl")


def o_frame_floor(t):
    return math.floor(t * fps + 1e-6)


# ---------------------------------------------------------------- timeline
reel_segments, clips_out, rf = [], [], 0
for a, b, label, hs, vs in CLIPS:
    fa, fb = int(round(a * fps)), int(round(b * fps))  # output-timeline frames
    clip = {"label": label, "o_start": a, "o_end": b, "o_frame": fa, "frames": fb - fa, "reel_frame": rf,
            "reel_t": round(rf / fps, 3), "h": hs, "v": vs}
    clips_out.append(clip)
    for g in segs:
        g0, g1 = g["out_frame"], g["out_frame"] + g["frames"]
        lo, hi = max(fa, g0), min(fb, g1)
        if lo < hi:
            reel_segments.append({"srcFrame": g["src_frame"] + (lo - g0), "frames": hi - lo, "outFrame": rf + (lo - fa),
                                  "o_frame": lo, "lf_seg": g["i"], "clip": len(clips_out) - 1})
    rf += fb - fa
TOTAL = rf


def reel_t_of_o(o):
    for c in clips_out:
        if c["o_start"] - 0.05 <= o <= c["o_end"] + 0.05:
            return (c["reel_frame"] + (o * fps - c["o_frame"])) / fps
    raise ValueError(o)


def o_of_reel_frame(f):
    for s in reel_segments:
        if s["outFrame"] <= f < s["outFrame"] + s["frames"]:
            return (s["o_frame"] + (f - s["outFrame"])) / fps
    s = reel_segments[-1]
    return (s["o_frame"] + s["frames"] - 1) / fps


# ---------------------------------------------------------------- framings
def faces_in(o0, o1):
    sp = pose.span(o0, o1)
    return [s["face"] for s in sp], [w for s in sp for w in s["wr"]]


def union(bs):
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


def clampv(cx, cy, w, ar):
    h = w / ar
    if h > SH:
        h = SH; w = h * ar
    if w > SW:
        w = SW; h = w / ar
    cx = min(max(cx, w / 2), SW - w / 2)
    cy = min(max(cy, h / 2), SH - h / 2)
    return [cx, cy, w]


def inside(box, F, ar, m=0.0):
    cx, cy, w = F
    h = w / ar
    mm = m * w
    return box[0] >= cx - w / 2 + mm and box[2] <= cx + w / 2 - mm and box[1] >= cy - h / 2 + mm and box[3] <= cy + h / 2 - mm


def framing(target, o0, o1, ar):
    """ar = w / h of the window. Scale is relative to the largest window of that aspect."""
    base_w = SW if ar >= 1 else SH * ar  # 3840 for 16:9, 1215 for 9:16
    kind = target[0]
    faces, wrists = faces_in(o0, o1)
    if not faces:  # turned to the board for the whole segment: the speaker's nearest face within 2 s
        faces, _ = faces_in(o0 - 2.0, o1 + 2.0)
    fu = union(faces) if faces else None
    if kind == "him":
        if fu is None:
            print(f"  note: no face near o {o0:.2f} to {o1:.2f}, 'him' falls back to the centred widest window")
            return clampv(SW / 2, SH / 2, base_w, ar), "him 1.00x (no face)"
        sc = target[1]
        for s_try in (sc, sc - 0.1, sc - 0.2, 1.0):
            w = base_w / max(1.0, s_try)
            h = w / ar
            cx = (fu[0] + fu[2]) / 2
            cy = (fu[1] + fu[3]) / 2 + h * (0.5 - 0.33)
            F = clampv(cx, cy, w, ar)
            hands = [(x - 50, y - 50, x + 50, y + 50) for x, y in wrists]
            ok_hands = (sum(inside(hb, F, ar) for hb in hands) / len(hands)) if hands else 1
            if inside(fu, F, ar, 0.03) and ok_hands >= 0.6:
                return F, f"him {base_w / F[2]:.2f}x"
        return clampv((fu[0] + fu[2]) / 2, SH / 2, base_w, ar), "him 1.00x"
    name, sc = target[1], target[2]
    Rc = board[name]
    Rp = (Rc[0] - 70, Rc[1] - 70, Rc[2] + 70, Rc[3] + 70)

    def pin_top(F):
        h = F[2] / ar
        if F[1] - h / 2 < 390 and 390 + h >= Rp[3] + 20 and Rp[1] - 20 >= 390:
            return clampv(F[0], 390 + h / 2, F[2], ar)
        return F

    def face_frac(F):
        if not fu:
            return 0.0
        cx, cy, w = F; h = w / ar
        ix = max(0, min(fu[2], cx + w / 2) - max(fu[0], cx - w / 2))
        iy = max(0, min(fu[3], cy + h / 2) - max(fu[1], cy - h / 2))
        return ix * iy / ((fu[2] - fu[0]) * (fu[3] - fu[1]))

    def per_face(F):
        cx, cy, w = F; h = w / ar
        out = []
        for fb in faces:
            ix = max(0, min(fb[2], cx + w / 2) - max(fb[0], cx - w / 2))
            iy = max(0, min(fb[3], cy + h / 2) - max(fb[1], cy - h / 2))
            out.append(ix * iy / ((fb[2] - fb[0]) * (fb[3] - fb[1])))
        return out

    # 1) item and the speaker's whole face together, as tight as possible down to 1.0x
    #    (skipped for ["item", name, scale, "solo"]: the item alone, the speaker's face fully out of frame)
    solo = len(target) > 3 and target[3] == "solo"
    s_ = sc
    while fu and not solo and s_ >= 1.0 - 1e-9:
        both = union([Rp, fu])
        G = pin_top(clampv((both[0] + both[2]) / 2, (both[1] + both[3]) / 2, base_w / s_, ar))
        if inside(both, G, ar, 0.02):
            return G, f"{name}+him {base_w / G[2]:.2f}x"
        s_ = round(s_ - 0.05, 3)
    # 2) item at the target scale with the speaker's face fully out of the window (never half a face)
    F = pin_top(clampv((Rp[0] + Rp[2]) / 2, (Rp[1] + Rp[3]) / 2, base_w / sc, ar))
    best = None
    for k in range(0, 41):
        for sgn in (1, -1):
            H = clampv(F[0] + sgn * k * 15, F[1], F[2], ar)
            if inside(Rc, H, ar, 0.0) and all(fr <= 0.03 or fr >= 0.97 for fr in per_face(H)):
                best = H
                break
        if best:
            break
    if best:
        return best, f"{name} {base_w / best[2]:.2f}x"
    # 3) loosen until item and face both fit (face fully in)
    s_ = sc
    while fu and s_ > 0.75:
        s_ = round(s_ - 0.05, 3)
        both = union([Rp, fu])
        G = clampv((both[0] + both[2]) / 2, (both[1] + both[3]) / 2, min(base_w / s_, SW if ar >= 1 else SH * ar), ar)
        if inside(both, G, ar, 0.0):
            return G, f"{name}+him {base_w / G[2]:.2f}x"
    if fu:
        # last resort: widest window with the speaker's whole face in at the far edge; the item may lose its left edge
        w = SW if ar >= 1 else SH * ar
        G = clampv(fu[2] + 30 - w / 2, F[1], w, ar)
        return G, f"{name}+him (face kept) {base_w / G[2]:.2f}x"
    return F, f"{name} {base_w / F[2]:.2f}x"


def differ(a, b):
    return max(abs(math.log(a[2] / b[2])) / math.log(1.15), math.hypot(a[0] - b[0], a[1] - b[1]) / (0.12 * min(a[2], b[2])))


def plan(ar, key, out_w):
    shots, cam, prev = [], [], None
    for ci, c in enumerate(clips_out):
        spec = c[key]
        # reel cut points inside this clip = lf rough-cut cuts; each one also changes framing
        my = [s for s in reel_segments if s["clip"] == ci]
        for si, s in enumerate(my):
            f0, f1 = s["outFrame"], s["outFrame"] + s["frames"]
            o0, o1 = o_of_reel_frame(f0), o_of_reel_frame(f1 - 1)
            # which spec entries apply in this segment
            first = spec[0][1]
            moves = []
            for t_o, tgt in spec[1:]:
                if o0 + 0.3 <= t_o < o1 + 0.5 / fps:
                    moves.append((t_o, tgt))
                elif t_o < o0 + 0.3:
                    first = tgt  # at (or before) this cut: take that framing at the cut
            F, name = framing(first, o0, o1, ar)
            if prev is not None and differ(F, prev) < 1 and first[0] != "him":
                G, gname = framing(("him", 1.3 if ar >= 1 else 1.1), o0, o1, ar)
                if differ(G, prev) >= 1:
                    F, name = G, gname
            if prev is not None and differ(F, prev) < 1:
                # punch 1.2x tighter (or 1.2x looser if already tight) so the cut reads as intentional
                maxw = SW if ar >= 1 else SH * ar
                w2 = F[2] / 1.2 if (maxw / (F[2] / 1.2)) <= (2.0 if ar >= 1 else 1.3) else min(maxw, F[2] * 1.2)
                F = clampv(F[0], F[1], w2, ar)
                name += f" -> {(maxw / F[2]):.2f}x (cut change)"
            shot = {"reel_frame": f0, "frames": f1 - f0, "t": round(f0 / fps, 3), "o": round(o0, 3), "line": c["label"],
                    "framing": {"name": name, "cx": round(F[0], 2), "cy": round(F[1], 2), "w": round(F[2], 2)}, "moves": []}
            cur = F
            free = f0 + 3  # a move starts after the cut and after the previous move has landed
            for t_o, tgt in moves:
                G, gname = framing(tgt, t_o, o1, ar)
                rt = reel_t_of_o(t_o)
                fs = max(int(round((rt - 0.25) * fps)), free)
                fn = min(int(round(0.85 * fps)), f1 - 2 - fs)
                if fn < int(round(0.6 * fps)):
                    print(f"  note: move to {gname} at o {t_o:.2f} dropped, under 0.6 s left in its shot (reel frame {f0} to {f1})")
                    continue
                free = fs + fn
                shot["moves"].append({"start_frame": fs, "frames": fn, "t": round(fs / fps, 3), "dur_s": round(fn / fps, 3),
                                      "to": {"name": gname, "cx": round(G[0], 2), "cy": round(G[1], 2), "w": round(G[2], 2)},
                                      "ease": "critically damped spring, omega 9, normalized"})
                cur = G
            A = F
            mv = list(shot["moves"])
            for f in range(f0, f1):
                while mv and f >= mv[0]["start_frame"] + mv[0]["frames"]:
                    m = mv.pop(0); A = [m["to"]["cx"], m["to"]["cy"], m["to"]["w"]]
                if mv and f >= mv[0]["start_frame"]:
                    m = mv[0]
                    p = ease((f - m["start_frame"]) / m["frames"])
                    B = [m["to"]["cx"], m["to"]["cy"], m["to"]["w"]]
                    ax0, ay0 = A[0] - A[2] / 2, A[1] - A[2] / ar / 2
                    bx0, by0 = B[0] - B[2] / 2, B[1] - B[2] / ar / 2
                    cam.append([round(ax0 + (bx0 - ax0) * p, 4), round(ay0 + (by0 - ay0) * p, 4), round(A[2] + (B[2] - A[2]) * p, 4)])
                else:
                    cam.append([round(A[0] - A[2] / 2, 4), round(A[1] - A[2] / ar / 2, 4), round(A[2], 4)])
            shots.append(shot)
            prev = cur
    assert len(cam) == TOTAL, (len(cam), TOTAL)
    return shots, cam


if __name__ == "__main__":
    out = E / "reel"
    out.mkdir(exist_ok=True)
    kinds = [("vertical", 9 / 16, "v", 1080, 1920)] + ([("horizontal", 16 / 9, "h", 1920, 1080)] if HORIZONTAL else [])
    seg_props = [{"srcFrame": s["srcFrame"], "frames": s["frames"], "outFrame": s["outFrame"]} for s in reel_segments]
    plan_out = {"label": SPEC.get("label", "Reel"), "fps": "24000/1001", "total_frames": TOTAL,
                "duration_s": round(TOTAL / fps, 3), "clips": clips_out, "segments": reel_segments}
    for kind, ar, key, ow, oh in kinds:
        shots, cam = plan(ar, key, ow)
        props = {"src": SRC, "srcW": 3840, "srcH": 2160, "outW": ow, "outH": oh, "segments": seg_props, "camera": cam}
        json.dump(props, open(out / f"props_reel_{kind}.json", "w"))
        json.dump(props, open(out / f"props_reel_{kind}_abs.json", "w"))
        plan_out[kind] = {"camera_units": f"[x0, y0, w], {'9:16' if ar < 1 else '16:9'} window in 4K px", "shots": shots}
    json.dump(plan_out, open(out / "reel-plan.json", "w"), indent=1)
    # audio: cut the mastered LF audio (o timeline) at the same frame-exact clip edges, 30 ms fades
    parts = []
    for i, c in enumerate(clips_out):
        a = c["o_frame"] / fps
        d = c["frames"] / fps
        p = out / f"a_{i:02d}.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{a:.6f}", "-t", f"{d:.6f}", "-i", str(AUDIO),
                        "-af", f"apad,atrim=0:{d:.6f},afade=t=in:st=0:d=0.03,afade=t=out:st={d - 0.03:.6f}:d=0.03",
                        "-c:a", "pcm_s24le", "-ar", "48000", str(p)], check=True)
        parts.append(p)
    (out / "a_concat.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(out / "a_concat.txt"),
                    "-c:a", "pcm_s24le", str(out / "reel_audio.wav")], check=True)
    for p in parts:
        p.unlink()
    print(f"reel: {len(clips_out)} clips, {len(reel_segments)} segments, {TOTAL} frames = {TOTAL / fps:.3f} s")
    for c in clips_out:
        print(f"  {c['reel_t']:6.2f}s  o {c['o_start']:7.3f}-{c['o_end']:7.3f}  {c['label']}")
