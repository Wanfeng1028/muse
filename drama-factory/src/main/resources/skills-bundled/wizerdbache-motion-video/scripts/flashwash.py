"""Flashes and colour washes: short moments where the whole frame turns white, black or one colour (T13).

Frames are decoded in colour at --fps (default 30) and scaled to --width (default 160). Per frame:

    Y     = mean luma (0-255)            std = luma standard deviation
    sat   = mean HSV saturation (0-1) over pixels with V > 40 (hue and saturation are noise on near-black)
    hue_share = share of ALL pixels that are saturated (s > 0.25, V > 40) and in the most common
                30-degree hue bin; hue = that bin's centre
    cf    = colourfulness (Hasler & Suesstrunk 2003): sigma_rgyb + 0.3 mu_rgyb, on their scale
            0 'not colourful', 15 'slightly', 33 'moderately'

A frame is TRANSIENT when it differs from BOTH flanks (medians over [t-0.9, t-0.4] and [t+0.4, t+0.9]):

    flat   std < 0.4 x min(std_pre, std_post)      (both sides had detail, this frame has little)
           AND the mean BGR lies > 20 from the segment between the two sides' mean BGR (a blur or a
           crossfade keeps the mean colour on that segment; added after the synthetic blur ramp read
           as a violet wash in the first selftest run)
    lift   Y > max(Y_pre, Y_post) + 25             (brighter than both sides)
    drop   Y < min(Y_pre, Y_post) - 25             (darker than both sides)

Requiring both sides keeps a cut onto a plain page that then STAYS (C34's cream grounds) out: its after
side is flat too. Consecutive transient frames (gaps <= 2 frames) form one event, kept if <= 1.2 s.
Each event is labelled at its most extreme frame, in this order:

    black-dip     Y <= 40
    colour-wash   sat >= 0.35 and hue_share >= 0.6 (hue reported in degrees and as a name); checked
                  before white-flash, so a pale bright wash is a wash (a white flash has sat ~0)
    white-flash   Y >= 200
    lift          brighter than both sides but none of the above (glow, partial exposure flash)
    flat-other    anything else (a grey or pale near-uniform frame)

and, separately, mono-to-colour: median cf <= 7 on the before side and >= 15 on the after side
(thresholds from the Hasler-Suesstrunk scale, set after the first C32 read missed 37-40 s: HSV
saturation called the black title card colourful (0.47, dark-pixel noise) and the muted anime colour
frame grey (0.135); colourfulness reads them 3.7 and 23.9).

Calibration (selftest, synthetic 320x180 textured frames, h264): known-true = 0.2 s white flash,
0.3 s red wash, 0.3 s dip to black, 0.3 s bloom lift, grey -> flash -> colour (mono-to-colour);
known-false = hard cut, 0.4 s crossfade, blur ramp, a cut onto a plain cream page held 3 s, a textured
paper page held; --auto on the joined film must find exactly the five positives with these labels.

Real controls (2026-10-04; events from the model-read technique inventories, a consistency check):
C32 read flashes 37.4 40.1 -> white-flash, 106.56 210.26 -> lift; the read mono-to-colour run 37-40 s ->
mono_to_colour at 40.03 (cf 3.2 -> 22.9); hard cuts 153.78 156.70 -> none 2/2. Misses: 138.50 (a flash
that decays slowly into the next shot: the after side is still bright, so neither lift nor flat holds),
146.12 (none; blurdip reads it blur-bridge, the inventory listed it under both). C33 read washes 13.5
55.25 85.5 -> flat-other / white-flash / colour-wash yellow, 5.3 none; 33 events in 90.5-140.3 s where
the 4 fps read counted >= 30 (+-8). Rates: C33 29.4/min, C32 11.4, C34 6.5 (C34, cream paper grounds,
is the low control). Files: measurements/C32,C33,C34/flashwash.json.

What it cannot determine: a flash that decays slowly (> 0.5 s) into a bright next shot; whether a wash is a transition or a designed coloured shot shorter than
1.2 s; a wash over a still-visible image (tint, not flat, no lift) is missed; small flashes (a spark,
one card) do not move frame means. Looks are not judged (the film's author watches it).

Usage:
    python -X utf8 scripts/flashwash.py <video> --out <file.json> [--events t1,t2,.. (report frames there)]
    python -X utf8 scripts/flashwash.py --selftest
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

PRE = (0.4, 0.9)
FLAT = 0.4
LUMA = 25.0
MAX_EVENT_S = 1.2
MONO_CF, COLOUR_CF = 7.0, 15.0   # Hasler-Suesstrunk colourfulness: 0 'not colourful', 15 'slightly'
COLOUR_SHIFT = 20.0   # a flat frame counts only if its mean colour leaves the before-after segment
HUE_NAMES = ["red", "orange", "yellow", "yellow-green", "green", "green-cyan", "cyan", "azure",
             "blue", "violet", "magenta", "pink"]


def frame_series(video, fps=30.0, width=160):
    info = probe(video)
    w = width
    h = int(round(info["height"] * width / info["width"] / 2)) * 2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={w}:{h}",
                          "-pix_fmt", "bgr24", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    n = w * h * 3
    rows = []
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        f = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
        y = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        lit = hsv[..., 2] > 40                    # hue and saturation are noise on near-black pixels
        s = hsv[..., 1].astype(np.float32) / 255
        hue = hsv[..., 0].astype(np.int32) * 2   # degrees
        sel = hue[(s > 0.25) & lit]
        if sel.size:
            hist = np.bincount(sel // 30, minlength=12)[:12]
            b = int(np.argmax(hist))
            share, hdeg = float(hist[b] / s.size), b * 30 + 15
        else:
            share, hdeg = 0.0, None
        sat = float(s[lit].mean()) if lit.any() else 0.0
        fb, fg, fr = (f[..., i].astype(np.float32) for i in range(3))
        rg, yb = fr - fg, 0.5 * (fr + fg) - fb
        cf = float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean()))
        mb, mg, mr = (float(c) for c in f.reshape(-1, 3).mean(axis=0))
        rows.append((float(y.mean()), float(y.std()), sat, share, mb, mg, mr, cf, hdeg))
    p.wait()
    arr = np.array([r[:8] for r in rows], dtype=np.float64)
    hues = [r[8] for r in rows]
    return arr, hues, fps


def seg_dist(p, a, b):
    """Distance from colour p to the segment a-b: a blur or a mix of the two sides stays near it."""
    d = b - a
    u = 0.0 if not d.any() else float(np.clip(np.dot(p - a, d) / np.dot(d, d), 0, 1))
    return float(np.linalg.norm(p - (a + u * d)))


def _flanks(x, i, a, b):
    return np.median(x[i - b:i - a + 1]), np.median(x[i + a:i + b + 1])


def classify(arr, hues, k):
    Y, sd, sat, share = arr[k, :4]
    if Y <= 40:
        return "black-dip", None
    if sat >= 0.35 and share >= 0.6:
        return "colour-wash", hues[k]
    if Y >= 200:
        return "white-flash", None
    return None, None


def analyse(video, fps=30.0, width=160):
    arr, hues, fps = frame_series(video, fps, width)
    n = len(arr)
    a, b = int(round(PRE[0] * fps)), int(round(PRE[1] * fps))
    Y, SD, SAT, CF = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 7]
    trans = np.zeros(n, bool)
    kind = [None] * n
    for i in range(b, n - b):
        y0, y1 = _flanks(Y, i, a, b)
        s0, s1 = _flanks(SD, i, a, b)
        c0 = np.median(arr[i - b:i - a + 1, 4:7], axis=0)
        c1 = np.median(arr[i + a:i + b + 1, 4:7], axis=0)
        flat = (SD[i] < FLAT * min(s0, s1) and min(s0, s1) > 4
                and seg_dist(arr[i, 4:7], c0, c1) > COLOUR_SHIFT)
        lift = Y[i] > max(y0, y1) + LUMA
        drop = Y[i] < min(y0, y1) - LUMA
        if flat or lift or drop:
            trans[i] = True
            kind[i] = (flat, lift, drop)
    events, i = [], 0
    while i < n:
        if not trans[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and (trans[j + 1] or (j + 2 < n and trans[j + 2]) or (j + 3 < n and trans[j + 3])):
            j += 1
        while not trans[j]:
            j -= 1
        dur = (j - i + 1) / fps
        if dur <= MAX_EVENT_S:
            seg = range(i, j + 1)
            k = max(seg, key=lambda q: abs(Y[q] - 128) + (128 if kind[q] and kind[q][0] else 0)
                    + 200 * arr[q, 3] * (arr[q, 2] >= 0.35))
            label, hue = classify(arr, hues, k)
            if label is None:
                label = "lift" if any(kind[q][1] for q in seg if kind[q]) else "flat-other"
            before = float(np.median(CF[max(0, i - b):max(1, i - a)]))
            after = float(np.median(CF[min(n - 1, j + a):min(n, j + b + 1)]))
            ev = {"t0": round(i / fps, 3), "t1": round((j + 1) / fps, 3), "duration_s": round(dur, 3),
                  "label": label, "t_peak": round(k / fps, 3), "luma_peak": round(float(Y[k]), 1),
                  "sat_peak": round(float(SAT[k]), 3),
                  "colourfulness": [round(before, 1), round(after, 1)],
                  "mono_to_colour": bool(before <= MONO_CF and after >= COLOUR_CF)}
            if hue is not None:
                ev["hue_deg"], ev["hue_name"] = hue, HUE_NAMES[hue // 30]
            events.append(ev)
        i = j + 1
    counts = {}
    for e in events:
        counts[e["label"]] = counts.get(e["label"], 0) + 1
    return {"video": str(video), "fps": fps, "width": width, "frames": n, "duration_s": round(n / fps, 2),
            "summary": {"events": len(events), "counts": counts,
                        "mono_to_colour": sum(e["mono_to_colour"] for e in events),
                        "per_min": round(len(events) / (n / fps / 60), 2) if n else 0,
                        "wash_hues": sorted({e.get("hue_name") for e in events if e.get("hue_name")})},
            "events": events}, arr


# ---------------------------------------------------------------- selftest

W, H, FPS = 320, 180, 30


def _tex(seed, colour=True):
    rng = np.random.default_rng(seed)
    base = cv2.GaussianBlur(rng.normal(0, 1, (H, W, 3)).astype(np.float32), (0, 0), 3) * 40
    base += cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 1)[..., None] * 25
    img = 120 + base + (rng.uniform(-40, 40, 3)[None, None] if colour else 0)
    if not colour:
        img = img.mean(axis=2, keepdims=True).repeat(3, 2)
    return np.clip(img, 0, 255).astype(np.float32)


def synth_film(path):
    A, B, C, D, E, F = (_tex(s) for s in (1, 2, 3, 4, 5, 6))
    G = _tex(7, colour=False)
    cream = np.full((H, W, 3), (215, 235, 245), np.float32)  # BGR cream
    paper = cream + cv2.GaussianBlur(np.random.default_rng(9).normal(0, 1, (H, W)).astype(np.float32),
                                     (0, 0), 1.5)[..., None] * 6
    red = np.full((H, W, 3), (40, 40, 220), np.float32)
    frames, truth = [], []

    def hold(img, s):
        frames.extend([img] * int(s * FPS))

    def now():
        return len(frames) / FPS

    hold(A, 1.5)
    truth.append((now(), "white flash 0.2 s", "white-flash"))
    for i, u in enumerate((0.5, 1.0, 1.0, 0.5)):
        src = A if i < 2 else B
        frames.append(src + (255 - src) * u)
    hold(B, 1.5)
    truth.append((now(), "red wash 0.3 s", "colour-wash"))
    for i, u in enumerate((0.6, 0.9, 1.0, 0.9, 0.9, 0.9, 0.6, 0.3)):
        frames.append((1 - u) * (B if i < 4 else C) + u * red)
    hold(C, 1.5)
    truth.append((now(), "dip to black 0.3 s", "black-dip"))
    for u in (0.5, 0.9, 1.0, 1.0, 0.9, 0.5):
        frames.append(D * (1 - u))
    hold(D, 1.5)
    truth.append((now(), "bloom lift 0.3 s", "lift"))
    for u in (0.4, 0.8, 1.0, 1.0, 0.8, 0.5, 0.2):
        frames.append(np.clip(D + 60 * u, 0, 255))
    hold(E, 1.5)
    truth.append((now(), "grey image, flash, colour version", "white-flash+mono"))
    frames[-45:] = [G] * 45
    for u in (0.6, 1.0, 1.0, 0.6):
        frames.append(E + (255 - E) * u)
    hold(E, 1.5)
    truth.append((now(), "pale yellow wash 0.3 s (Y ~ 215)", "colour-wash"))
    yellow = np.full((H, W, 3), (120, 235, 245), np.float32)
    for i, u in enumerate((0.6, 0.9, 1.0, 0.9, 0.9, 0.9, 0.6, 0.3)):
        frames.append((1 - u) * (E if i < 4 else F) + u * yellow)
    hold(F, 1.5)
    truth.append((now(), "warm-tinted mono, flash, colour", "white-flash+mono"))
    sep = _tex(8, colour=False) * np.array([0.94, 0.98, 1.03], np.float32)[None, None]
    muted = _tex(8)
    frames[-45:] = [sep] * 45
    for u in (0.6, 1.0, 1.0, 0.6):
        frames.append(muted + (255 - muted) * u)
    hold(muted, 1.5)
    # negatives
    hold(F, 1.5)                                     # hard cut E -> F
    for i in range(12):                              # crossfade F -> A
        frames.append((1 - (i + 1) / 13) * F + (i + 1) / 13 * A)
    hold(A, 1.5)
    for sg in (2, 4, 6, 4, 2):                       # blur ramp
        frames.append(cv2.GaussianBlur(A, (0, 0), sg))
    hold(A, 1.5)
    hold(cream, 3.0)                                 # cut onto a plain cream page, held
    hold(paper, 2.0)                                 # textured paper page, held
    hold(B, 1.5)
    vid = np.clip(np.stack(frames), 0, 255).astype(np.uint8)
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "v.raw"
        raw.write_bytes(vid.tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                        "-r", str(FPS), "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                        str(path)], check=True)
    return truth


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        v = Path(td) / "film.mp4"
        truth = synth_film(v)
        res, _ = analyse(v)
        ev = res["events"]
        for t, kind, want in truth:
            hit = [e for e in ev if e["t0"] - 0.1 <= t + 0.15 <= e["t1"] + 0.3]
            lab = want.split("+")[0]
            good = len(hit) == 1 and hit[0]["label"] == lab
            if good and want.endswith("+mono"):
                good = hit[0]["mono_to_colour"]
            print(f"known-true  {kind:34s} t={t:5.2f} -> "
                  f"{[(e['label'], e.get('hue_name'), e['mono_to_colour']) for e in hit]} (want {want}) "
                  f"{'ok' if good else 'FAIL'}")
            ok &= good
        washes = [e for e in ev if e["label"] == "colour-wash"]
        good = len(washes) == 2 and washes[0]["hue_name"] == "red"
        print(f"first wash hue reads red -> {'ok' if good else 'FAIL'}")
        ok &= good
        good = len(ev) == len(truth)
        print(f"known-false (hard cut, crossfade, blur ramp, cream page held, paper held): total events "
              f"{len(ev)} (want {len(truth)}) -> {'ok' if good else 'FAIL'}")
        ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--events", help="comma-separated seconds: also print the event (if any) at each")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--width", type=int, default=160)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    res, _ = analyse(a.video, a.fps, a.width)
    if a.events:
        checks = []
        for t in (float(x) for x in a.events.split(",") if x.strip()):
            hit = [e for e in res["events"] if e["t0"] - 0.35 <= t <= e["t1"] + 0.35]
            checks.append({"t": t, "found": hit[0] if hit else None})
            print(f"{t:8.2f}  {(hit[0]['label'] + ' ' + str(hit[0].get('hue_name') or '')) if hit else 'none'}")
        res["checks"] = checks
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(json.dumps(res["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
