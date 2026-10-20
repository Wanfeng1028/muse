"""Blur dips at transitions: does a shot change pass through a blurred frame instead of a crossfade (T12)?

Frames are decoded at --fps (default 30) and scaled to --width (default 320, grey). Per frame:

    S    = variance of the Laplacian (3x3), the standard focus measure; falls as the frame blurs
    std  = grey standard deviation (contrast); a blur keeps most of it, a flash or a black frame does not

At an event time t (given with --events / --segments, or found with --auto):

    ref        = min(median S over [t-0.9, t-0.4], median S over [t+0.4, t+0.9])   (the softer side,
                 so a hard cut from a sharp shot to a soft one is not read as a dip)
    dip        = min S over [t-0.35, t+0.35] / ref
    std_ratio  = std at that frame / median std of the two flanks
    duration   = seconds the run of frames with S < 0.5 x ref lasts around the minimum
    entry      = 'step' when S falls from >= 0.7 ref to the minimum within 1 frame (cut onto a blurred
                 shot, then focus), 'ramp' when it falls over several frames (blur out, then in)

Labels, checked in this order (depth classes set from physics before any real film was read; the
luma and focus-in rules were added after the first C32 read, each first reproduced as a synthetic case
that the old rules failed):

    no-dip         dip >= 0.7 (hard cut, level shift, nothing happened)
    flash-dip      the minimum frame's mean grey lies above both flanks' means by > 12 levels: a blur or
                   any mix of two shots keeps the mean inside their range, a flash or glow lifts it
    flat-dip       std_ratio < 0.4 (near-uniform frame: white, black, solid wash) or the mean drops > 12
                   levels below both flanks (dip through black)
    blur-bridge    dip < 0.3: a 50/50 mix of two uncorrelated sharp images has S ~ 0.25 (S_A + S_B), at
                   least 0.5 of the softer one, so a plain crossfade cannot reach 0.3
    focus-in       0.3 <= dip < 0.7 with a step entry, S climbing to >= 1.5 x its minimum within 1 s, and
                   the soft frame matching the later sharp frame low-passed (Pearson >= 0.8, +-3 px at
                   80 px wide): a cut onto a slightly soft shot that then focuses. A crossfade never steps.
    crossfade-like any other 0.3 <= dip < 0.7. A DEPTH class only: in C32, 5 of 5 sampled were glow
                   pulses, in-shot motion blur or partial blur, none a dissolve (sheet read 2026-10-04)
    undetermined   flank sharpness below --s-floor (flat or black flanks) or the window leaves the film

--auto: every frame whose dip value (same formula, centred on that frame) is below 0.7 and is the
lowest within +-0.35 s becomes a candidate; candidates closer than 0.5 s keep the lower one.

Calibration (selftest, synthetic 320x180 textured stills, h264): known-true = blur ramp through the cut,
cut onto a blurred shot then focus, horizontal motion-blur whip-in (blur-bridge), cut onto a mildly soft
shot with a 0.8 s focus (focus-in). Known-false = 0.4 s crossfade (crossfade-like), hard cut and hard cut
onto a permanently soft shot (no-dip), white flash and bloom flash (flash-dip), fade through black
(flat-dip), cut onto a pale paper ground with three layers entering (anything but a blur label). --auto
on the joined film must find exactly the four blur positives.

Real controls (2026-10-04, events from the C32/C34 technique inventories, model-read, so agreement is
a consistency check rather than ground truth): C32 flashes 106.56 138.50 210.26 -> flash-dip 3/3; hard
cuts 153.78 156.70 -> no-dip 2/2; read defocus entries 24.95 29.4 146 -> focus-in / blur-bridge 3/6
(90.9 reads flat-dip: a dark fade under the blur; 17.38 and 122 show no sharpness dip at all). C34
camera sweeps over the board 19.6-33.7 -> blur-bridge 6/6; whip-ins -> blur-bridge 5/12, the black-gap
whips (3.6, 95.9) flat-dip. Files: measurements/C32/blurdip_controls.json, blurdip_auto.json,
measurements/C34/blurdip_controls.json.

What it cannot determine: whether a flash also blurred (flash wins the label); WHY a frame is soft (a blur filter, a defocused source image, motion blur from a
fast pan, heavy compression all lower S); whether a dip is a transition or a soft shot held < 0.8 s; a
blur confined to a small area (text revealed through blur) barely moves S. A very short dip (1 frame at
30 fps) still counts. Looks are not judged (the film's author watches it).

Usage:
    python -X utf8 scripts/blurdip.py <video> --out <file.json> (--events t1,t2,.. | --segments seg.json | --auto)
    python -X utf8 scripts/blurdip.py --selftest
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

PRE = (0.4, 0.9)       # flank window, seconds from t
SEARCH = 0.35          # minimum search half-width
DIP_BRIDGE = 0.3
DIP_SHALLOW = 0.7
FLAT_STD = 0.4
S_FLOOR = 5.0
LUMA_MARGIN = 12.0     # grey levels: a blur or a mix of two shots keeps the mean inside their range
FOCUS_RISE = 1.5       # focus-in: S climbs to >= 1.5 x its minimum within 1 s
IDENTITY = 0.8         # focus-in: the soft frame is the later sharp frame, low-passed
SMALL_W = 80
BLUR_LABELS = ("blur-bridge", "focus-in")


def frame_series(video, fps=30.0, width=320):
    """Stream frames once; return per-frame S (Laplacian variance), mean and std, plus the frame rate."""
    info = probe(video)
    w = width
    h = int(round(info["height"] * width / info["width"] / 2)) * 2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                          f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE)
    n = w * h
    S, M, D, small = [], [], [], []
    sw, sh = SMALL_W, int(round(h * SMALL_W / w))
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        f = np.frombuffer(buf, dtype=np.uint8).reshape(h, w).astype(np.float32)
        S.append(float(cv2.Laplacian(f, cv2.CV_32F, ksize=3).var()))
        M.append(float(f.mean()))
        D.append(float(f.std()))
        small.append(cv2.resize(f, (sw, sh), interpolation=cv2.INTER_AREA).astype(np.uint8))
    p.wait()
    return np.array(S), np.array(M), np.array(D), np.stack(small), fps


def _idx(t, fps):
    return int(round(t * fps))


def measure_at(S, M, D, small, fps, t, s_floor=S_FLOOR):
    n = len(S)
    a0, a1 = _idx(t - PRE[1], fps), _idx(t - PRE[0], fps)
    b0, b1 = _idx(t + PRE[0], fps), _idx(t + PRE[1], fps)
    w0, w1 = _idx(t - SEARCH, fps), _idx(t + SEARCH, fps)
    if a0 < 0 or b1 >= n:
        return {"t": round(t, 3), "label": "undetermined", "why": "window leaves the film"}
    pre, post = float(np.median(S[a0:a1 + 1])), float(np.median(S[b0:b1 + 1]))
    ref = min(pre, post)
    if ref < s_floor:
        return {"t": round(t, 3), "label": "undetermined", "why": f"flank sharpness {ref:.1f} < floor"}
    k = w0 + int(np.argmin(S[w0:w1 + 1]))
    dip = S[k] / ref
    std_ref = float(np.median(np.r_[D[a0:a1 + 1], D[b0:b1 + 1]]))
    std_ratio = D[k] / std_ref if std_ref > 1e-6 else 0.0
    lo, hi = k, k
    while lo - 1 >= 0 and S[lo - 1] < 0.5 * ref:
        lo -= 1
    while hi + 1 < n and S[hi + 1] < 0.5 * ref:
        hi += 1
    dur = (hi - lo + 1) / fps if dip < 0.5 else 0.0
    j = k
    while j - 1 >= 0 and S[j - 1] < 0.7 * ref and k - j < fps:
        j -= 1
    entry = "step" if k - j <= 1 else "ramp"
    m_pre, m_post = float(np.median(M[a0:a1 + 1])), float(np.median(M[b0:b1 + 1]))
    luma_out = (M[k] > max(m_pre, m_post) + LUMA_MARGIN, M[k] < min(m_pre, m_post) - LUMA_MARGIN)
    r1 = min(n - 1, k + _idx(1.0, fps))
    r = k + 1 + int(np.argmax(S[k + 1:r1 + 1])) if r1 > k else k
    rise = S[r] / S[k] if S[k] > 1e-6 else 0.0
    ident = identity(small[k], small[r]) if entry == "step" else None
    focus_s = None
    if rise >= FOCUS_RISE:
        q = k
        while q < r and S[q] < 0.7 * S[r]:
            q += 1
        focus_s = round((q - k) / fps, 3)
    if dip >= DIP_SHALLOW:
        label = "no-dip"
    elif luma_out[0]:
        label = "flash-dip"
    elif std_ratio < FLAT_STD or luma_out[1]:
        label = "flat-dip"
    elif dip < DIP_BRIDGE:
        label = "blur-bridge"
    elif entry == "step" and rise >= FOCUS_RISE and ident is not None and ident >= IDENTITY:
        label = "focus-in"
    else:
        label = "crossfade-like"
    return {"t": round(t, 3), "t_min": round(k / fps, 3), "label": label, "dip": round(float(dip), 3),
            "std_ratio": round(float(std_ratio), 3), "duration_s": round(dur, 3),
            "entry": entry if label in BLUR_LABELS else None, "rise": round(float(rise), 2),
            "focus_s": focus_s, "identity": None if ident is None else round(ident, 3),
            "luma": [round(m_pre, 1), round(float(M[k]), 1), round(m_post, 1)],
            "s_pre": round(pre, 1), "s_post": round(post, 1)}


def identity(soft, sharp, shift=3):
    """Best Pearson r between the soft frame and the sharp frame, both low-passed, over +-shift px."""
    a = cv2.GaussianBlur(soft.astype(np.float32), (0, 0), 1.5)
    b = cv2.GaussianBlur(sharp.astype(np.float32), (0, 0), 1.5)
    best, h, w = -1.0, a.shape[0], a.shape[1]
    for dy in range(-shift, shift + 1):
        for dx in range(-shift, shift + 1):
            x = a[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)]
            y = b[max(0, -dy):h + min(0, -dy), max(0, -dx):w + min(0, -dx)]
            if x.std() > 1e-6 and y.std() > 1e-6:
                best = max(best, float(np.corrcoef(x.ravel(), y.ravel())[0, 1]))
    return best


def auto_candidates(S, fps, s_floor=S_FLOOR):
    n = len(S)
    a, b = _idx(PRE[0], fps), _idx(PRE[1], fps)
    ratio = np.full(n, np.inf)
    for i in range(b, n - b):
        ref = min(np.median(S[i - b:i - a + 1]), np.median(S[i + a:i + b + 1]))
        if ref >= s_floor:
            ratio[i] = S[i] / ref
    half = _idx(SEARCH, fps)
    cand = [i for i in range(n) if ratio[i] < DIP_SHALLOW
            and ratio[i] == ratio[max(0, i - half):i + half + 1].min()]
    keep = []
    for i in cand:
        if keep and i - keep[-1] < 0.5 * fps:
            if ratio[i] < ratio[keep[-1]]:
                keep[-1] = i
        else:
            keep.append(i)
    return [i / fps for i in keep]


def analyse(video, events=None, auto=False, fps=30.0, width=320):
    S, M, D, small, fps = frame_series(video, fps, width)
    times = auto_candidates(S, fps) if auto else list(events or [])
    rows = [measure_at(S, M, D, small, fps, t) for t in times]
    counts = {}
    for r in rows:
        counts[r["label"]] = counts.get(r["label"], 0) + 1
    br = [r for r in rows if r["label"] == "blur-bridge"]
    summary = {"events": len(rows), "counts": counts,
               "blur_bridge_duration_s": sorted(r["duration_s"] for r in br),
               "blur_bridge_entry": {e: sum(1 for r in br if r["entry"] == e) for e in ("step", "ramp")}}
    return {"video": str(video), "fps": fps, "width": width, "mode": "auto" if auto else "events",
            "frames": len(S), "summary": summary, "rows": rows}


# ---------------------------------------------------------------- selftest

W, H, FPS = 320, 180, 30


def _texture(seed):
    rng = np.random.default_rng(seed)
    img = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 1.2)
    img += cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 6) * 3
    for _ in range(12):  # hard-edged shapes, as in illustrations
        x, y, r = rng.integers(0, W), rng.integers(0, H), rng.integers(8, 40)
        cv2.circle(img, (int(x), int(y)), int(r), float(rng.normal(0, 3)), -1)
    img = (img - img.mean()) / img.std()
    return np.clip(128 + 40 * img, 0, 255).astype(np.float32)


def _blur(img, sigma):
    return img if sigma < 0.05 else cv2.GaussianBlur(img, (0, 0), sigma)


def _hblur(img, length):
    k = max(1, int(length))
    return cv2.blur(img, (k, 1)) if k > 1 else img


def synth_film(path):
    """One film with eight transitions at known times; returns [(t, kind, want)]."""
    A, B, C, Dt, E = (_texture(s) for s in (1, 2, 3, 4, 5))
    soft = _blur(_texture(6), 3.0)
    frames, events = [], []

    def hold(img, sec):
        frames.extend([img] * int(sec * FPS))

    def t_now():
        return len(frames) / FPS

    hold(A, 1.5)
    events.append((t_now(), "blur ramp through cut", "blur-bridge"))       # 0.15 s out, 0.15 s in
    for i in range(5):
        frames.append(_blur(A, 6 * (i + 1) / 5))
    for i in range(5):
        frames.append(_blur(B, 6 * (4 - i) / 5))
    hold(B, 1.5)
    events.append((t_now(), "cut onto blurred shot, focus 0.3 s", "blur-bridge"))
    for i in range(9):
        frames.append(_blur(C, 6 * (8 - i) / 8))
    hold(C, 1.5)
    events.append((t_now(), "horizontal motion-blur whip-in 0.25 s", "blur-bridge"))
    for i in range(8):
        u = (i + 1) / 8
        shift = int(W * (1 - u) ** 2)
        f = C.copy()
        f[:, shift:] = Dt[:, :W - shift] if shift else Dt
        frames.append(_hblur(f, 60 * (1 - u) + 1))
    hold(Dt, 1.5)
    events.append((t_now(), "crossfade 0.4 s", "crossfade-like"))
    for i in range(12):
        u = (i + 1) / 13
        frames.append((1 - u) * Dt + u * E)
    hold(E, 1.5)
    events.append((t_now(), "hard cut", "no-dip"))
    hold(A, 1.5)
    events.append((t_now(), "hard cut onto soft shot", "no-dip"))
    hold(soft, 1.5)
    events.append((t_now(), "white flash 0.2 s", "flash-dip"))
    for i in range(3):
        frames.append(soft + (255 - soft) * (i + 1) / 3)
    for i in range(3):
        frames.append(B + (255 - B) * (2 - i) / 3)
    hold(B, 1.5)
    events.append((t_now(), "fade through black 0.4 s", "flat-dip"))
    for i in range(6):
        frames.append(B * (5 - i) / 6)
    for i in range(6):
        frames.append(E * (i + 1) / 6)
    hold(E, 1.5)
    # added 2026-10-04 after the C32 real controls: exposure flashes (106.56, 210.26) read blur-bridge,
    # a slow focus pull (24.95) read crossfade-like. Each case is synthesised here before the rule changes.
    events.append((t_now(), "bloom flash 0.3 s (glow + lift)", "flash-dip"))
    for u in (1.0, 0.8, 0.6, 0.4, 0.2):      # bloom: blurred glow added and lifted, as C32 106.56 reads
        frames.append(np.clip((1 - u) * A + u * (_blur(A, 3) * 1.3 + 40), 0, 255))
    for u in (0.6, 0.4, 0.2, 0.05):
        frames.append(np.clip((1 - u) * C + u * (_blur(C, 3) * 1.3 + 40), 0, 255))
    hold(C, 1.5)
    events.append((t_now(), "cut onto mild blur, slow focus 0.8 s", "focus-in"))
    for i in range(24):                      # sigma 0.5 -> 0: S at the cut ~0.35 of sharp, as C32 24.95
        frames.append(_blur(Dt, 0.5 * (1 - i / 24)))
    hold(Dt, 1.5)
    events.append((t_now(), "cut onto paper ground, 3 layers enter", "not-blur"))
    paper = 200 + 0.15 * (_texture(7) - 128)
    for i in range(30):
        f = paper.copy()
        for j, (x0, y0) in enumerate(((20, 20), (170, 30), (90, 100))):
            if i >= 6 * (j + 1):
                f[y0:y0 + 70, x0:x0 + 120] = B[y0:y0 + 70, x0:x0 + 120]
        frames.append(f)
    hold(frames[-1], 1.5)
    vid = np.clip(np.stack(frames), 0, 255).astype(np.uint8)
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "v.raw"
        raw.write_bytes(vid.tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                        "-r", str(FPS), "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                        str(path)], check=True)
    return events


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        v = Path(td) / "film.mp4"
        truth = synth_film(v)
        res = analyse(v, events=[t for t, _, _ in truth])
        for (t, kind, want), r in zip(truth, res["rows"]):
            good = r["label"] not in BLUR_LABELS if want == "not-blur" else r["label"] == want
            print(f"{'known-true ' if want in BLUR_LABELS else 'known-false'} {kind:38s} t={t:5.2f} -> "
                  f"{r['label']:14s} dip {r.get('dip')} std {r.get('std_ratio')} dur {r.get('duration_s')} "
                  f"entry {r.get('entry')} (want {want}) {'ok' if good else 'FAIL'}")
            ok &= good
        e1, e2 = res["rows"][0]["entry"], res["rows"][1]["entry"]
        good = e1 == "ramp" and e2 == "step"
        print(f"entry shape: blur-through {e1} (want ramp), blur-in {e2} (want step) -> {'ok' if good else 'FAIL'}")
        ok &= good
        d1 = res["rows"][0]["duration_s"]
        good = 0.15 <= d1 <= 0.4
        print(f"duration of the 0.33 s blur ramp: {d1} s (want 0.15-0.4) -> {'ok' if good else 'FAIL'}")
        ok &= good
        au = analyse(v, auto=True)
        pos = [t for t, _, w in truth if w in BLUR_LABELS]
        found = [r for r in au["rows"] if r["label"] in BLUR_LABELS]
        hit = all(any(abs(r["t_min"] - t) <= 0.4 for r in found) for t in pos)
        good = hit and len(found) == len(pos)
        print(f"--auto: {len(found)} blur-bridge/focus-in found (want {len(pos)}, all at the true times: {hit}); "
              f"all labels {au['summary']['counts']} -> {'ok' if good else 'FAIL'}")
        ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--events", help="comma-separated seconds")
    ap.add_argument("--segments", help="segments.json; its events become the event list")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    events = None
    if a.events:
        events = [float(x) for x in a.events.split(",") if x.strip()]
    elif a.segments:
        seg = json.loads(Path(a.segments).read_text(encoding="utf-8"))
        events = [e["t"] if isinstance(e, dict) else float(e) for e in seg["events"]]
    elif not a.auto:
        ap.error("give --events, --segments or --auto")
    res = analyse(a.video, events=events, auto=a.auto, fps=a.fps, width=a.width)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    for r in res["rows"]:
        print(f"{r['t']:8.2f}  {r['label']:14s} dip {r.get('dip')} std {r.get('std_ratio')} "
              f"dur {r.get('duration_s')} entry {r.get('entry')}")
    print(json.dumps(res["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
