"""Frame window: is the picture shown through a black matte (letterbox, strip, slanted window), and when
does that window change (T13 crop shapes)?

Frames are decoded at --fps (default 10) and scaled to --width (default 320, grey). Per frame,
after a 3x3 median filter, a pixel is black when grey < 20:

    bars     = leading rows (top, bottom) / columns (left, right) that are >= 98 % black with no raw pixel
               >= 60, kept when at least 3 % of the side; a matte is a whole row of nothing, picture
               darkness rarely is (the max test was added when the synthetic star sky, flat black with
               single-pixel stars the median filter removed, read letterbox)
    edges    = inside the bars, each row's first and last non-black column; a side whose median inset
               is >= 3 % of the width and whose points fit a straight line (two robust passes, >= 80 %
               within 3 px) is a window edge, its angle from vertical in degrees
    no-window  the region inside the bars is < 25 % of the height / 15 % of the width, or is itself
               > 50 % black (a title on black, a dark scene)

Labels per frame (checked in order):

    no-window  as above
    full       no bars and no straight inset edge (or a box covering >= 95 % both ways)
    slant      a window edge > 4 degrees off vertical (a parallelogram or a tilted window)
    letterbox  box >= 95 % of the width and aspect >= 1.95
    pillarbox  box >= 95 % of the height and <= 85 % of the width
    strip      any other box (a vertical or horizontal strip, an inset)

The first version (per-pixel matte components + convex hull) read C36's 2.35 letterbox on 54 % of
frames because dark picture areas touching the bars joined the matte; it was replaced before any
number from it was used (2026-10-04).

Runs of one label shorter than --min-run (0.3 s) are folded into their neighbour; the output lists the
runs (t0, t1, label, median window box and aspect) and the changes between them.

Calibration (selftest, synthetic 320x180 h264): full textured frame, 2.35 letterbox, centred vertical
strip (30 % wide), slanted parallelogram window, pillarbox 4:3 must read as such (median label per
section, change times within 0.2 s). Known-false: a dark night scene (black sky touching the edges,
irregular hills, stars) and a title on black must NOT read letterbox / strip / slant.

Real controls (2026-10-04): C34 (no matte anywhere on its frames) -> full 100 %. C32 read window
changes at 24.9 and 26.6 s -> strip/letterbox from 24.9, pillarbox 26.6-29.2; read vertical window
127.2-128.1 -> pillarbox 127.2-128.5 (aspect 1.19); read slanted top/bottom bars 128.2-129.2 and the
parallelogram wipe 83.7-86 -> not seen (top/bottom slants are outside the method). C36 -> letterbox
72.5 %, full 13.7 %: frames at 95, 190, 290, 310 s confirm full frame, overturning the earlier 0.5 fps
read "letterbox throughout"; its strip runs at 16.8-20.5 / 25.7-27.4 / 85.5-88.5 are a dark straight
door-frame edge in the picture read as an inset edge (false positive). Files:
measurements/C32,C34,C36/framebox.json.

What it cannot determine: a dark straight vertical element of the picture touching the side reads as
an inset edge (C36 18 s); a slanted TOP or BOTTOM edge (only side edges are fitted; a horizontal
slant reads letterbox or strip); a matte that is not near-black (a white or coloured frame around the picture
reads full); a window inside a dark picture whose edge is not straight; soft (feathered) matte edges
below 20 grey shift the box by their width. Looks are not judged (the film's author watches it).

Usage:
    python -X utf8 scripts/framebox.py <video> --out <file.json> [--fps 10 --width 320]
    python -X utf8 scripts/framebox.py --selftest
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

BLACK = 20
BRIGHT = 60        # no pixel of a matte row or column reaches this grey
BAR_MIN = 0.03      # a bar is at least 3 % of the frame side (about 5 px at 180)
EDGE_MIN = 0.03     # a side edge is inset by at least 3 % of the width
SLANT_DEG = 4.0


def frames_of(video, fps, width):
    info = probe(video)
    w = width
    h = int(round(info["height"] * width / info["width"] / 2)) * 2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    n = w * h
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, dtype=np.uint8).reshape(h, w)
    p.wait()


def _edge_line(ys, xs):
    """Robust straight-line fit x = m*y + c: two least-squares passes dropping points > 3 px off.
    Returns (slope, inlier share)."""
    if len(ys) < 10:
        return 0.0, 0.0
    m, c = np.polyfit(ys, xs, 1)
    for _ in range(2):
        keep = np.abs(xs - (m * ys + c)) <= 3
        if keep.sum() < 10:
            return 0.0, 0.0
        m, c = np.polyfit(ys[keep], xs[keep], 1)
    keep = np.abs(xs - (m * ys + c)) <= 3
    return float(m), float(keep.mean())


def frame_window(g):
    h, w = g.shape
    blk = cv2.medianBlur(g, 3) < BLACK
    # a matte row holds nothing: >= 98 % black AND no bright pixel (a star, a subtitle stroke) in the raw row
    rows = (blk.mean(axis=1) >= 0.98) & (g.max(axis=1) < BRIGHT)
    cols = (blk.mean(axis=0) >= 0.98) & (g.max(axis=0) < BRIGHT)

    def lead(v):
        k = 0
        while k < len(v) and v[k]:
            k += 1
        return k

    top, bot = lead(rows), lead(rows[::-1])
    left, right = lead(cols), lead(cols[::-1])
    top, bot = (top if top >= BAR_MIN * h else 0), (bot if bot >= BAR_MIN * h else 0)
    left, right = (left if left >= BAR_MIN * w else 0), (right if right >= BAR_MIN * w else 0)
    y0, y1, x0, x1 = top, h - bot, left, w - right
    out = {"matte": round(float(blk.mean()), 3)}
    if y1 - y0 < 0.25 * h or x1 - x0 < 0.15 * w:
        out["label"] = "no-window"
        return out
    inner = blk[y0:y1, x0:x1]
    if inner.mean() > 0.5:          # a title or a dark scene on black, not a picture behind a matte
        out["label"] = "no-window"
        return out
    # slanted or inset edges: per-row first / last non-black column inside the bars
    ys, L, R = [], [], []
    for y in range(y0, y1):
        nz = np.flatnonzero(~blk[y, x0:x1])
        if nz.size:
            ys.append(y)
            L.append(nz[0])
            R.append(nz[-1])
    ys, L, R = np.array(ys, float), np.array(L, float), np.array(R, float)
    span_w = x1 - x0
    edges = {}
    for name, xs, inset in (("left", L, np.median(L)), ("right", R, span_w - 1 - np.median(R))):
        if inset >= EDGE_MIN * w:
            slope, inl = _edge_line(ys, xs)
            if inl >= 0.8:
                edges[name] = round(float(np.degrees(np.arctan(slope))), 1)
    bx0 = x0 + (int(np.median(L)) if "left" in edges else 0)
    bx1 = x0 + (int(np.median(R)) + 1 if "right" in edges else span_w)
    bw, bh = bx1 - bx0, y1 - y0
    out.update(box=[round(bx0 / w, 3), round(y0 / h, 3), round(bx1 / w, 3), round(y1 / h, 3)],
               aspect=round(bw / bh, 2), bars=[top, bot, left, right], edges=edges)
    if not (top or bot or left or right or edges):
        out["label"] = "full"
    elif any(abs(a) > SLANT_DEG for a in edges.values()):
        out["label"] = "slant"
    elif bw >= 0.95 * w and bw / bh >= 1.95:
        out["label"] = "letterbox"
    elif bh >= 0.95 * h and bw <= 0.85 * w:
        out["label"] = "pillarbox"
    elif bw >= 0.95 * w and bh >= 0.95 * h:
        out["label"] = "full"
    else:
        out["label"] = "strip"
    return out


def runs_of(labels, fps, min_run):
    runs = []
    for i, l in enumerate(labels):
        if runs and runs[-1][2] == l:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1, l])
    k = int(round(min_run * fps))
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for j, (a, b, l) in enumerate(runs):
            if b - a < k:
                if j > 0:
                    runs[j - 1][1] = b
                else:
                    runs[j + 1][0] = a
                runs.pop(j)
                changed = True
                break
        merged = []
        for r in runs:
            if merged and merged[-1][2] == r[2]:
                merged[-1][1] = r[1]
            else:
                merged.append(r)
        runs = merged
    return runs


def analyse(video, fps=10.0, width=320, min_run=0.3):
    per = [frame_window(g) for g in frames_of(video, fps, width)]
    labels = [p["label"] for p in per]
    runs = runs_of(labels, fps, min_run)
    rows = []
    for a, b, l in runs:
        boxes = [per[i]["box"] for i in range(a, b) if per[i]["label"] == l and "box" in per[i]]
        aspects = [per[i]["aspect"] for i in range(a, b) if per[i]["label"] == l and per[i].get("aspect")]
        rows.append({"t0": round(a / fps, 2), "t1": round(b / fps, 2), "label": l,
                     "box": [round(float(v), 3) for v in np.median(boxes, axis=0)] if boxes else None,
                     "aspect": round(float(np.median(aspects)), 2) if aspects else None})
    n = len(labels)
    share = {l: round(labels.count(l) / n, 3) for l in sorted(set(labels))} if n else {}
    changes = [r["t0"] for r in rows[1:]]
    return {"video": str(video), "fps": fps, "width": width, "frames": n,
            "summary": {"share": share, "runs": len(rows), "changes": len(changes),
                        "windowed_share": round(sum(v for k, v in share.items()
                                                    if k in ("letterbox", "pillarbox", "strip", "slant")), 3)},
            "runs": rows, "changes": changes}


# ---------------------------------------------------------------- selftest

W, H, FPS = 320, 180, 10


def _tex(seed):
    rng = np.random.default_rng(seed)
    t = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 2) * 35
    return np.clip(130 + t, 40, 235)


def synth(path):
    A = _tex(1)
    secs = []
    frames = []

    def add(img, label, s=2.0):
        secs.append((len(frames) / FPS, label))
        frames.extend([img] * int(s * FPS))

    add(A, "full")
    lb = A.copy()
    bar = int(round((H - W / 2.35) / 2))
    lb[:bar] = 5
    lb[H - bar:] = 5
    add(lb, "letterbox")
    st = np.full((H, W), 5.0)
    st[:, 112:208] = A[:, 112:208]
    st[:8] = 5
    st[H - 8:] = 5
    add(st, "strip")
    sl = np.full((H, W), 5.0, np.float32)
    mask = np.zeros((H, W), np.uint8)
    cv2.fillPoly(mask, [np.array([[60, 20], [300, 20], [260, 160], [20, 160]], np.int32)], 1)
    sl[mask == 1] = A[mask == 1]
    add(sl, "slant")
    pb = np.full((H, W), 5.0)
    pw = int(H * 4 / 3)
    pb[:, (W - pw) // 2:(W + pw) // 2] = A[:, (W - pw) // 2:(W + pw) // 2]
    add(pb, "pillarbox")
    rng = np.random.default_rng(3)
    night = np.full((H, W), 4.0, np.float32)
    x = np.arange(W)
    ridge = (110 + 18 * np.sin(x / 23) + 9 * np.sin(x / 7 + 1)).astype(int)
    for c in range(W):
        night[ridge[c]:, c] = 40 + rng.normal(0, 10, H - ridge[c])
    for _ in range(80):
        cv2.circle(night, (int(rng.integers(0, W)), int(rng.integers(0, 100))), 1, 230, -1)
    add(night, "no-window|full")
    title = np.full((H, W), 4.0, np.float32)
    cv2.putText(title, "TITLE CARD", (60, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 230, 2)
    add(title, "no-window|full")
    vid = np.clip(np.stack(frames), 0, 255).astype(np.uint8)
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "v.raw"
        raw.write_bytes(vid.tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                        "-r", str(FPS), "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                        str(path)], check=True)
    return secs


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        v = Path(td) / "w.mp4"
        secs = synth(v)
        res = analyse(v)
        for t, want in secs:
            mid = t + 1.0
            r = next((r for r in res["runs"] if r["t0"] <= mid < r["t1"]), None)
            got = r["label"] if r else None
            good = got in want.split("|")
            kind = "known-false" if "no-window" in want else "known-true "
            print(f"{kind} section at {t:4.1f}s -> {got} (want {want}) aspect {r and r['aspect']} "
                  f"{'ok' if good else 'FAIL'}")
            ok &= good
        true_changes = [t for t, _ in secs[1:5]]
        hit = all(any(abs(c - t) <= 0.2 for c in res["changes"]) for t in true_changes)
        print(f"changes at the four true window switches within 0.2 s: {hit} -> {'ok' if hit else 'FAIL'}")
        ok &= hit
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--min-run", type=float, default=0.3)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    res = analyse(a.video, a.fps, a.width, a.min_run)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    for r in res["runs"]:
        if r["label"] != "full":
            print(f"{r['t0']:8.2f}-{r['t1']:8.2f}  {r['label']:10s} aspect {r['aspect']} box {r['box']}")
    print(json.dumps(res["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
