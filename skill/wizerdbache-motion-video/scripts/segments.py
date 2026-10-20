"""Global-change events: where (almost) all of the frame's content changes at once.

A product-intro video changes section by swapping the headline AND the product
panel together (fade through the background, blur swap, wipe, hard cut), while
motion inside a section (typing, a panel popping in, a counter rolling) touches
only part of the content. For each frame t this tool compares frame t-w with
frame t+w and measures

    coverage(t) = changed / (content_a | content_b | changed)

where a pixel is "content" if it differs from its own frame's background (the
histogram mode) by more than --thr grey levels, and "changed" if the two frames
differ there by more than --thr. A background swap (light UI -> black card)
makes every pixel changed, so coverage is 1. Peaks of coverage above --min-cov,
at least --min-gap apart, are the events; the gaps between them are the section
durations.

Calibration margin (selftest, 2026-09-27): synthetic content swaps reach
coverage 0.72-1.0 (a persistent anchor holds ~14 % of content unchanged), local
motion inside a section stays <= 0.55; default --min-cov 0.65 sits between.
Real headline swaps measured 0.93-1.0; a modal dimming the whole screen measured
0.77 (C07 35.9 s) — above threshold, so read it off the sheet.

An event whose run lasts longer than SPAN_S (2.5 s) is not one transition but a
stretch of continuous global change (fast montage, rapid switching); it is
reported as kind "span" with its start/end, and the sections list marks it as a
montage section instead of inventing a boundary in its middle.

What it cannot determine: whether an event is a new SECTION (new headline) or a
push-in / zoom / modal overlay inside one section — all change almost every
content pixel. A section change that swaps ONLY the headline (the product panel
stays) is invisible to the full frame; run again with --crop on the headline
region. Map events to headlines by reading the frame sheet.
Map events to headlines by reading the frame sheet. A persistent anchor (logo,
search bar) that stays put lowers coverage by its share of the content area.

Usage:
    python -X utf8 scripts/segments.py <video> --out <dir> [--w 0.33 --min-cov 0.65]
    python -X utf8 scripts/segments.py --selftest
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import load_gray_frames  # noqa: E402


def bg_mode(f):
    h = np.bincount(f.ravel(), minlength=256)
    return int(np.argmax(h))


def coverage_curve(frames, fps, w_s, thr):
    n = len(frames)
    w = max(1, int(round(w_s * fps)))
    bgs = np.array([bg_mode(f) for f in frames])
    ff = frames.astype(np.int16)
    cov = np.zeros(n)
    for t in range(w, n - w):
        a, b = ff[t - w], ff[t + w]
        ca = np.abs(a - bgs[t - w]) > thr
        cb = np.abs(b - bgs[t + w]) > thr
        ch = np.abs(a - b) > thr
        den = (ca | cb | ch).sum()
        cov[t] = ch.sum() / den if den else 0.0
    return cov, w


def events_from(cov, fps, min_cov, min_gap_s):
    """An event is a run of frames with coverage >= min_cov; runs closer than
    min_gap are one event. The window t-w..t+w makes the run symmetric around the
    transition, so the run's midpoint is the transition's centre."""
    gap = int(round(min_gap_s * fps))
    runs = []
    i = 0
    while i < len(cov):
        if cov[i] >= min_cov:
            j = i
            while j + 1 < len(cov) and cov[j + 1] >= min_cov:
                j += 1
            if runs and i - runs[-1][1] < gap:
                runs[-1][1] = j
            else:
                runs.append([i, j])
            i = j + 1
        else:
            i += 1
    out = []
    for lo, hi in runs:
        run_s = (hi - lo + 1) / fps
        e = {"t": round((lo + hi) / 2 / fps, 3), "coverage": round(float(cov[lo:hi + 1].max()), 3),
             "run_s": round(run_s, 3), "kind": "transition" if run_s <= SPAN_S else "span"}
        if e["kind"] == "span":  # continuous global change (montage, fast switching): report its extent
            e["start"], e["end"] = round(lo / fps, 3), round(hi / fps, 3)
        out.append(e)
    return out


SPAN_S = 2.5  # one transition gives a run of about 2w + its own length; a slow dim + per-character headline reveal (C07) runs ~2 s


def analyse(video, width=128, w_s=0.33, thr=20, min_cov=0.65, min_gap_s=0.8, crop=None):
    frames, fps = load_gray_frames(video, width=width, crop=crop)
    cov, w = coverage_curve(frames, fps, w_s, thr)
    ev = events_from(cov, fps, min_cov, min_gap_s)
    dur = len(frames) / fps
    bounds, montage = [0.0], set()
    for e in ev:
        if e["kind"] == "span":
            bounds += [e["start"], e["end"]]
            montage.add(e["start"])
        else:
            bounds.append(e["t"])
    bounds.append(round(dur, 3))
    sections = [{"start": bounds[i], "end": bounds[i + 1], "dur": round(bounds[i + 1] - bounds[i], 3),
                 "montage": bounds[i] in montage}
                for i in range(len(bounds) - 1)]
    res = {"video": str(video), "fps": fps, "duration_s": round(dur, 3), "events": ev, "sections": sections,
           "params": {"width": width, "w_s": w_s, "thr": thr, "min_cov": min_cov, "min_gap_s": min_gap_s,
                      "crop": crop},
           "limits": f"event time = centre of the coverage peak; resolution about 1 frame for cuts, "
                     f"about half the transition length for fades; window w = {w} frames"}
    return res, cov, fps


def plot(res, cov, fps, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = np.arange(len(cov)) / fps
    fig, ax = plt.subplots(figsize=(12, 2.8))
    ax.plot(t, cov, lw=0.8)
    ax.axhline(res["params"]["min_cov"], color="grey", ls=":", lw=0.8)
    for e in res["events"]:
        ax.axvline(e["t"], color="red", lw=0.8)
    ax.set_xlabel("s")
    ax.set_ylabel("coverage")
    ax.set_title(f"{Path(res['video']).name}: {len(res['events'])} global-change events")
    fig.tight_layout()
    fig.savefig(png, dpi=110)
    plt.close(fig)


# ---------- calibration ----------
W, H, FPS, BG = 192, 108, 30, 30


def pattern(seed, h, w, level=210):
    """A text/UI-like block: rows of short 'words' (1-px strokes with gaps), so two
    different blocks overlap about as little as two different lines of real text."""
    rng = np.random.default_rng(seed)
    blk = np.full((h, w), BG, np.int16)
    for r in range(1 + seed % 3, h - 3, 5):          # line baseline shifts with the block
        x = int(rng.integers(1, 5))
        end = int(rng.integers(w // 2, w - 2))
        while x < end:
            ln = int(rng.integers(2, 7))
            cols = np.arange(x, min(x + ln, end))
            rows = r + rng.integers(0, 3, size=cols.size)          # glyph strokes at varying heights
            blk[rows, cols] = level
            x += ln + int(rng.integers(2, 4))
    return blk


def layout(sec):
    f = np.full((H, W), BG, np.int16)
    f[8:30, 8:80] = pattern(100 + sec, 22, 72)          # headline
    f[20:100, 96:186] = pattern(200 + sec, 80, 90, 170)  # product panel
    f[80:98, 14:32] = 235                                 # persistent anchor (never changes)
    return f


def local_motion(f, t, big_pop=False):
    f = f.copy()
    typed = int((t % 2.0) / 2.0 * 60)                     # a line being typed in the panel
    f[92:94, 98:98 + typed] = 250
    if int(t * 2) % 2:                                    # blinking cursor
        f[40:46, 84:86] = 250
    if big_pop and t >= 5.0:                              # large panel pops in over the product area
        f[20:70, 96:186] = pattern(999, 50, 90, 120)
    return f


def synth_sections(path, dur=12.0, scale=1.0):
    """scale < 1 plays the same film faster: every event time is multiplied by scale."""
    n = int(dur * scale * FPS)
    vid = np.zeros((n, H, W), np.uint8)
    for i in range(n):
        t = i / FPS / scale
        if t < 2.5:                                       # hard cut at 2.5
            f = local_motion(layout(0), t)
        elif t < 4.85:
            f = local_motion(layout(1), t)
        elif t < 5.15:                                    # crossfade centred at 5.0
            k = (t - 4.85) / 0.3
            f = (1 - k) * local_motion(layout(1), t) + k * local_motion(layout(2), t)
        elif t < 7.25:
            f = local_motion(layout(2), t)
        elif t < 7.75:                                    # fade through background centred at 7.5
            k = (t - 7.25) / 0.2
            if k <= 1:
                f = BG + (1 - k) * (local_motion(layout(2), t) - BG)
            elif t < 7.55:
                f = np.full((H, W), BG, float)
            else:
                k = (t - 7.55) / 0.2
                f = BG + k * (local_motion(layout(3), t) - BG)
        elif t < 9.8:
            f = local_motion(layout(3), t)
        elif t < 10.2:                                    # black wipe from the right centred at 10.0
            edge = int(W * (1 - (t - 9.8) / 0.4))
            f = local_motion(layout(3), t)
            f[:, edge:] = 5
        else:                                             # a black chapter card with a white word
            f = np.full((H, W), 5, np.int16)
            f[48:60, 60:130] = 245
        vid[i] = np.clip(f, 0, 255).astype(np.uint8)
    _encode(vid, path)
    return [round(x * scale, 3) for x in (2.5, 5.0, 7.5, 10.0)]


def synth_local_only(path, dur=10.0):
    n = int(dur * FPS)
    vid = np.zeros((n, H, W), np.uint8)
    for i in range(n):
        t = i / FPS
        vid[i] = np.clip(local_motion(layout(0), t, big_pop=True), 0, 255).astype(np.uint8)
    _encode(vid, path)


def synth_montage(path, dur=9.0):
    """Hard cuts every 0.4 s from 3.0 to 6.0 s (a montage), static before and after."""
    n = int(dur * FPS)
    vid = np.zeros((n, H, W), np.uint8)
    for i in range(n):
        t = i / FPS
        sec = 0 if t < 3.0 else (1 + int((t - 3.0) / 0.4) if t < 6.0 else 19)
        vid[i] = np.clip(local_motion(layout(sec), t), 0, 255).astype(np.uint8)
    _encode(vid, path)
    return (3.0, 6.0)


def synth_headline_only(path, dur=6.0):
    """Only the headline changes (hard cut at 3.0); panel and anchor stay."""
    n = int(dur * FPS)
    vid = np.zeros((n, H, W), np.uint8)
    for i in range(n):
        t = i / FPS
        f = local_motion(layout(0), t)
        if t >= 3.0:
            f[8:30, 8:80] = pattern(150, 22, 72)
        vid[i] = np.clip(f, 0, 255).astype(np.uint8)
    _encode(vid, path)
    return [3.0]


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
        p = Path(td) / "sec.mp4"
        truth = synth_sections(p)
        res, _, fps = analyse(p, width=W)
        got = [e["t"] for e in res["events"]]
        match = len(got) == len(truth) and all(abs(g - t) <= 0.1 for g, t in zip(got, truth))
        print(f"known-true (cut, crossfade, fade-through-bg, wipe to card): events {got} want {truth} "
              f"(+-0.1 s) -> {'ok' if match else 'FAIL'}")
        ok &= match
        q = Path(td) / "loc.mp4"
        synth_local_only(q)
        res2, cov2, _ = analyse(q, width=W)
        good = len(res2["events"]) == 0
        print(f"known-false (typing, blinking cursor, panel pop over the product area): "
              f"events {[e['t'] for e in res2['events']]} want [] (max coverage {cov2.max():.2f}) "
              f"-> {'ok' if good else 'FAIL'}")
        ok &= good
        r = Path(td) / "head.mp4"
        truth = synth_headline_only(r)
        full, _, _ = analyse(r, width=W)
        good = len(full["events"]) == 0
        print(f"known-false for the full frame (headline-only change): events "
              f"{[e['t'] for e in full['events']]} want [] -> {'ok' if good else 'FAIL'}")
        ok &= good
        head, _, _ = analyse(r, width=80, crop="80:30:4:4")
        got = [e["t"] for e in head["events"]]
        good = len(got) == 1 and abs(got[0] - truth[0]) <= 0.1
        print(f"known-true for --crop on the headline: events {got} want {truth} -> {'ok' if good else 'FAIL'}")
        ok &= good
        m = Path(td) / "mont.mp4"
        a0, a1 = synth_montage(m)
        mon, _, _ = analyse(m, width=W)
        ev = mon["events"]
        good = (len(ev) == 1 and ev[0]["kind"] == "span"
                and abs(ev[0]["start"] - (a0 - 0.33)) <= 0.1 and abs(ev[0]["end"] - (a1 + 0.33)) <= 0.1)
        print(f"known-true montage (cuts every 0.4 s, {a0}-{a1} s): "
              f"{[(e['kind'], e.get('start'), e.get('end')) for e in ev]} want one span "
              f"{a0 - 0.33:.2f}-{a1 + 0.33:.2f} -> {'ok' if good else 'FAIL'}")
        ok &= good
        good = all(e["kind"] == "transition" for e in res["events"])
        print(f"known-false for span: the four single transitions are all 'transition' -> {'ok' if good else 'FAIL'}")
        ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--w", type=float, default=0.33)
    ap.add_argument("--thr", type=int, default=20)
    ap.add_argument("--min-cov", type=float, default=0.65)
    ap.add_argument("--min-gap", type=float, default=0.8)
    ap.add_argument("--crop", help="ffmpeg crop w:h:x:y in source pixels, e.g. the headline column only")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    res, cov, fps = analyse(a.video, w_s=a.w, thr=a.thr, min_cov=a.min_cov, min_gap_s=a.min_gap, crop=a.crop)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "segments.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    np.save(out / "coverage.npy", cov)
    plot(res, cov, fps, out / "segments.png")
    print(f"{len(res['events'])} events in {res['duration_s']} s")
    for e in res["events"]:
        print(f"  {e['t']:6.2f}s  coverage {e['coverage']}")


if __name__ == "__main__":
    main()
