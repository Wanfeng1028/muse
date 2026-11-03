"""Frame fill and motion: how much of the frame carries content, and how often something moves.

Frames are decoded at --fps (default 10) and scaled to --width (default 320). For each frame:

    content pixel  = differs from the frame's background (grey histogram mode) by more than --thr
    occupied tile  = a TILE x TILE px tile (10 px at width 320, i.e. 40 px at 1280) whose content
                     share is at least --tile-min (0.03)
    fill           = occupied tiles / all tiles
    extent         = area of the bounding box of the occupied tiles / frame area

and for each pair of consecutive frames:

    changed share  = pixels whose grey value changed by more than --thr / all pixels
    moving         = changed share > --move-min (0.002, about 115 px at 320x180)

Reported per video: fill and extent (median, p10, p90 over frames), moving share (fraction of
frame pairs that are moving), still runs (lengths in s of consecutive non-moving stretches:
median, p90, max), and the mean changed share.

Calibration (selftest, synthetic): a text block over ~65 % of the frame sliding at constant speed
must read fill >= 0.45 and moving >= 0.9; a small ~8 % block with three cards fading in over 0.4 s
(progressive reveal, truth: moving 0.13, longest still 2.6 s) must read fill <= 0.15, moving
0.08-0.2, longest still 2.4-2.8 s. Fill reads below the block's area because inter-line gaps
leave some tiles under --tile-min; compare fills between videos, not against a drawn area.
A smooth sine slide was tried first: its turning points move < 0.5 px per 0.1 s and read as
still (0.86 moving), which is the tool working as specified, not a fault.

What it cannot determine: whether content is LEGIBLE (type size needs the DOM, see textsize.py)
or good-looking (numbers never judge beauty); a full-bleed photo or gradient background counts as filled because it
differs from the dominant grey; a light card on a light ground (difference < --thr) is not content,
only the text on it is. Motion slower than --thr grey levels per 1/fps s (a very slow fade or a
sub-pixel drift) reads as still.

Usage:
    python -X utf8 scripts/density.py <video> --out <dir> [--fps 10 --width 320]
    python -X utf8 scripts/density.py --selftest
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import probe  # noqa: E402

TILE = 10


def load_frames(path, fps, width):
    info = probe(path)
    w = width
    h = int(round(info["height"] * width / info["width"] / 2)) * 2
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h},format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    frames = np.frombuffer(r.stdout, dtype=np.uint8)
    n = frames.size // (w * h)
    return frames[: n * w * h].reshape(n, h, w)


def frame_fill(f, thr, tile_min):
    bg = int(np.argmax(np.bincount(f.ravel(), minlength=256)))
    content = np.abs(f.astype(np.int16) - bg) > thr
    h, w = content.shape
    th, tw = h // TILE, w // TILE
    tiles = content[: th * TILE, : tw * TILE].reshape(th, TILE, tw, TILE).mean(axis=(1, 3)) >= tile_min
    fill = tiles.mean()
    if tiles.any():
        rows, cols = np.where(tiles)
        extent = (rows.max() - rows.min() + 1) * (cols.max() - cols.min() + 1) / tiles.size
    else:
        extent = 0.0
    return float(fill), float(extent)


def runs_of(mask):
    out, n = [], 0
    for m in mask:
        if m:
            n += 1
        elif n:
            out.append(n)
            n = 0
    if n:
        out.append(n)
    return out


def pct(a, q):
    return round(float(np.percentile(a, q)), 3) if len(a) else None


def analyse(video, fps=10.0, width=320, thr=20, tile_min=0.03, move_min=0.002):
    frames = load_frames(video, fps, width)
    fills, extents = zip(*(frame_fill(f, thr, tile_min) for f in frames))
    ff = frames.astype(np.int16)
    changed = (np.abs(np.diff(ff, axis=0)) > thr).mean(axis=(1, 2))
    moving = changed > move_min
    still = [r / fps for r in runs_of(~moving)]
    res = {
        "video": str(video), "fps_sampled": fps, "frames": len(frames), "duration_s": round(len(frames) / fps, 2),
        "fill": {"median": pct(fills, 50), "p10": pct(fills, 10), "p90": pct(fills, 90)},
        "extent": {"median": pct(extents, 50), "p10": pct(extents, 10), "p90": pct(extents, 90)},
        "moving_share": round(float(moving.mean()), 3),
        "mean_changed_share": round(float(changed.mean()), 4),
        "still_runs_s": {"n": len(still), "median": pct(still, 50), "p90": pct(still, 90),
                         "max": round(max(still), 2) if still else 0.0},
        "params": {"fps": fps, "width": width, "thr": thr, "tile_px": TILE, "tile_min": tile_min,
                   "move_min": move_min},
        "limits": "content = differs from the dominant grey by > thr; legibility and looks are not measured",
    }
    return res, np.array(fills), changed


def plot(res, fills, changed, fps, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = np.arange(len(fills)) / fps
    fig, ax = plt.subplots(2, 1, figsize=(12, 4.5), sharex=True)
    ax[0].plot(t, fills, lw=0.8)
    ax[0].set_ylabel("fill")
    ax[0].set_ylim(0, 1)
    ax[1].plot(t[1:], changed, lw=0.6, color="tab:orange")
    ax[1].axhline(res["params"]["move_min"], color="k", lw=0.5, ls="--")
    ax[1].set_ylabel("changed share")
    ax[1].set_yscale("symlog", linthresh=0.001)
    ax[1].set_xlabel("s")
    fig.suptitle(f"fill median {res['fill']['median']}  moving {res['moving_share']}  "
                 f"still p90 {res['still_runs_s']['p90']} s", fontsize=9)
    fig.tight_layout()
    fig.savefig(png, dpi=110)
    plt.close(fig)


# ---------- calibration ----------
W, H, FPS, BG = 320, 180, 30, 235


def text_block(rng, h, w):
    blk = np.full((h, w), BG, np.int16)
    for r in range(2, h - 3, 6):
        x = 2
        end = int(rng.integers(w // 2, w - 2))
        while x < end:
            ln = int(rng.integers(3, 9))
            blk[r:r + 3, x:min(x + ln, end)] = 40
            x += ln + int(rng.integers(2, 5))
    return blk


def synth_dense(path, dur=8.0):
    """~65 % of the frame is a text block that slides 1 px per frame (constant speed, triangle
    path), so every 1/10 s pair differs by 3 px: truth = always moving."""
    rng = np.random.default_rng(1)
    blk = text_block(rng, 140, 250)
    n = int(dur * FPS)
    vid = np.full((n, H, W), BG, np.uint8)
    for i in range(n):
        ph = i % 80
        x = 10 + (ph if ph < 40 else 80 - ph)
        vid[i, 20:160, x:x + 250] = blk
    _encode(vid, path)


def synth_sparse(path, dur=9.0):
    """A small (~8 %) still block; small cards fade in over 0.4 s at 1, 4 and 7 s and stay
    (progressive reveal). Truth: moving ~1.2 of 9 s, longest still run 2.6 s (1.4-4.0, 4.4-7.0)."""
    rng = np.random.default_rng(2)
    blk = text_block(rng, 45, 100)
    cards = [text_block(rng, 20, 40) for _ in range(3)]
    slots = [(115, 110), (115, 160), (140, 135)]
    n = int(dur * FPS)
    vid = np.full((n, H, W), BG, np.uint8)
    for i in range(n):
        t = i / FPS
        vid[i, 60:105, 110:210] = blk
        for k, t0 in enumerate((1.0, 4.0, 7.0)):
            if t < t0:
                continue
            a = min(1.0, (t - t0) / 0.4)
            y, x = slots[k]
            vid[i, y:y + 20, x:x + 40] = np.clip(BG + a * (cards[k] - BG), 0, 255)
    _encode(vid, path)


def _encode(vid, path):
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "v.raw"
        raw.write_bytes(vid.tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                        "-r", str(FPS), "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12",
                        str(path)], check=True)


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "dense.mp4"
        synth_dense(d)
        r, _, _ = analyse(d)
        good = r["fill"]["median"] >= 0.45 and r["moving_share"] >= 0.9
        print(f"known-true dense+moving: fill {r['fill']['median']} (want >= 0.45), moving {r['moving_share']} "
              f"(want >= 0.9) -> {'ok' if good else 'FAIL'}")
        ok &= good
        s = Path(td) / "sparse.mp4"
        synth_sparse(s)
        r2, _, _ = analyse(s)
        good = (r2["fill"]["median"] <= 0.15 and 0.08 <= r2["moving_share"] <= 0.2
                and 2.4 <= r2["still_runs_s"]["max"] <= 2.8)
        print(f"known-false sparse+mostly still: fill {r2['fill']['median']} (want <= 0.15), moving "
              f"{r2['moving_share']} (want 0.08-0.2, truth 0.13), longest still {r2['still_runs_s']['max']} s "
              f"(want 2.4-2.8, truth 2.6) -> {'ok' if good else 'FAIL'}")
        ok &= good
        good = r["fill"]["median"] > 3 * r2["fill"]["median"]
        print(f"ordering: dense fill > 3 x sparse fill -> {'ok' if good else 'FAIL'}")
        ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--thr", type=int, default=20)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    res, fills, changed = analyse(a.video, fps=a.fps, width=a.width, thr=a.thr)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "density.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    plot(res, fills, changed, a.fps, out / "density.png")
    print(f"fill median {res['fill']['median']} extent median {res['extent']['median']} "
          f"moving {res['moving_share']} still median/p90/max {res['still_runs_s']['median']}/"
          f"{res['still_runs_s']['p90']}/{res['still_runs_s']['max']} s")


if __name__ == "__main__":
    main()
