"""Spring-motion instrument: track a UI container frame by frame and fit a damped
spring step response to each size change.

Tracking: on a light canvas, the container is the largest dark component
(< DARK) or the largest bright component (> BRIGHT), whichever is larger; when the
container is bright, the largest dark component inside it is recorded as the
"indicator" (tab indicator, selected row). Sizes are SCREEN-SPACE: a camera zoom
in the source multiplies them, so a fit describes container x camera together.

Fit model (x0 -> x1, starting at t0, natural frequency w rad/s, damping ratio z):
    x(t) = x1 + (x0 - x1) * g(t - t0),  g = the unit spring step response
Overshoot is also read directly from the data, not only from the fitted z.

Usage:
    python -X utf8 scripts/springfit.py <video> --out <outdir>/spring [--from 0 --to 14]
    python -X utf8 scripts/springfit.py --selftest
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.optimize import curve_fit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import load_gray_frames  # noqa: E402

DARK, BRIGHT, MIN_AREA = 120, 249, 400


def spring_g(tau, w, z):
    tau = np.maximum(tau, 0.0)
    if abs(z - 1) < 1e-3:
        return np.exp(-w * tau) * (1 + w * tau)
    if z < 1:
        wd = w * np.sqrt(1 - z * z)
        return np.exp(-z * w * tau) * (np.cos(wd * tau) + (z * w / wd) * np.sin(wd * tau))
    s = np.sqrt(z * z - 1)
    r1, r2 = -w * (z - s), -w * (z + s)
    return (r2 * np.exp(r1 * tau) - r1 * np.exp(r2 * tau)) / (r2 - r1)


def largest(mask):
    lab, n = ndimage.label(mask)
    if n == 0:
        return None
    areas = ndimage.sum(mask, lab, range(1, n + 1))
    i = int(np.argmax(areas)) + 1
    ys, xs = np.nonzero(lab == i)
    return {"area": float(areas[i - 1]), "x0": int(xs.min()), "x1": int(xs.max()),
            "y0": int(ys.min()), "y1": int(ys.max())}


def track(frames, fps, scale=1.0):
    rows = []
    for i, fr in enumerate(frames):
        d = largest(fr < DARK)
        b = largest(fr > BRIGHT)
        row = {"t": i / fps, "kind": None}
        box = None
        if b and b["area"] >= MIN_AREA and (not d or b["area"] > d["area"]):
            row["kind"], box = "bright", b
            inner = fr[b["y0"]:b["y1"] + 1, b["x0"]:b["x1"] + 1] < DARK
            ind = largest(inner)
            if ind and ind["area"] >= 50:
                row["ind_x0"] = (ind["x0"] + b["x0"]) * scale
                row["ind_x1"] = (ind["x1"] + b["x0"]) * scale
        elif d and d["area"] >= MIN_AREA:
            row["kind"], box = "dark", d
        if box:
            row.update(w=(box["x1"] - box["x0"] + 1) * scale, h=(box["y1"] - box["y0"] + 1) * scale,
                       cx=(box["x0"] + box["x1"]) / 2 * scale, cy=(box["y0"] + box["y1"]) / 2 * scale)
        rows.append(row)
    return rows


def segments(t, x, fps, vel_thr, settle_s=0.08, min_len_s=0.05, merge_s=0.15):
    """Split a size series into moves: runs where |dx/dt| > vel_thr, padded. Runs
    closer than merge_s are one move (an overshoot's turn-around dips below the
    velocity threshold without ending the move)."""
    v = np.abs(np.gradient(x, 1 / fps))
    moving = v > vel_thr
    out, i, n = [], 0, len(x)
    pad = int(settle_s * fps)
    merge = max(1, int(merge_s * fps))
    while i < n:
        if moving[i]:
            j = i
            while j + 1 < n and (moving[j + 1] or np.any(moving[j + 1:j + 1 + merge])):
                j += 1
            if (j - i) / fps >= min_len_s:
                out.append((max(0, i - pad), min(n - 1, j + pad)))
            i = j + 1
        else:
            i += 1
    return out


def fit_move(t, x):
    x0 = float(np.median(x[:3]))
    x1 = float(np.median(x[-3:]))
    amp = x1 - x0
    if abs(amp) < 4:
        return None

    def model(tt, t0, w, z):
        return x1 + (x0 - x1) * spring_g(tt - t0, w, z)

    best = None
    for z_init in (0.4, 0.8, 1.3):
        try:
            p, _ = curve_fit(model, t, x, p0=[t[0] + 0.03, 25, z_init],
                             bounds=([t[0] - 0.1, 2, 0.05], [t[-1], 300, 3.0]), maxfev=20000)
        except RuntimeError:
            continue
        rmse = float(np.sqrt(np.mean((model(t, *p) - x) ** 2)))
        if best is None or rmse < best[1]:
            best = (p, rmse)
    if best is None:
        return None
    (t0, w, z), rmse = best
    beyond = (x - x1) * np.sign(amp)
    overshoot = float(max(0.0, beyond.max()) / abs(amp))
    settle = None
    g = spring_g(np.linspace(0, 3, 3000), w, z)
    idx = np.where(np.abs(g) > 0.02)[0]
    if len(idx):
        settle = float(idx[-1] * 3 / 3000)
    predicted = float(np.exp(-np.pi * z / np.sqrt(1 - z * z))) if z < 1 else 0.0
    nrmse = rmse / abs(amp)
    return {"t0": float(t0), "from": x0, "to": x1, "omega": float(w), "zeta": float(z),
            "stiffness_k": float(w * w), "damping_c": float(2 * z * w), "settle_2pct_s": settle,
            "overshoot_measured": round(overshoot, 4), "overshoot_predicted": round(predicted, 4),
            "nrmse": round(nrmse, 4),
            # a spring reading is trusted only when the fitted z predicts the overshoot actually seen
            "spring_consistent": bool(abs(predicted - overshoot) <= 0.02 and nrmse <= 0.015),
            "t_start": float(t[0]), "t_end": float(t[-1])}


def analyse(rows, fps, t_from=0.0, t_to=1e9, vel_thr=60.0):
    fits = []
    t_all = np.array([r["t"] for r in rows])
    for key in ("w", "h"):
        # contiguous runs of the same container kind
        run = []
        for r in rows + [{"kind": "__end__"}]:
            if run and (r.get("kind") != run[-1]["kind"] or key not in r):
                if len(run) > 10 and run[0]["kind"] in ("dark", "bright"):
                    t = np.array([q["t"] for q in run])
                    x = np.array([q[key] for q in run], float)
                    for a, b in segments(t, x, fps, vel_thr):
                        if t[a] < t_from or t[b] > t_to:
                            continue
                        f = fit_move(t[a:b + 1], x[a:b + 1])
                        if f:
                            f.update(axis=key, kind=run[0]["kind"])
                            fits.append(f)
                run = []
            if r.get("kind") in ("dark", "bright") and key in r:
                run.append(r)
    for key in ("ind_x0", "ind_x1"):
        idx = [i for i, r in enumerate(rows) if key in r]
        if len(idx) > 10:
            t = t_all[idx]
            x = np.array([rows[i][key] for i in idx], float)
            for a, b in segments(t, x, fps, vel_thr):
                f = fit_move(t[a:b + 1], x[a:b + 1])
                if f:
                    f.update(axis=key, kind="indicator")
                    fits.append(f)
    fits.sort(key=lambda f: f["t0"])
    return fits


def plot(rows, fits, out_png, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = np.array([r["t"] for r in rows])
    fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
    for ax, key, col in ((axes[0], "w", "#1f5fa8"), (axes[0], "h", "#2a9d5b")):
        ax.plot(t, [r.get(key, np.nan) for r in rows], lw=1, color=col, label=f"container {key}")
    axes[0].legend(loc="upper right")
    axes[0].set_ylabel("px (screen space)")
    axes[1].plot(t, [r.get("ind_x0", np.nan) for r in rows], color="#d33", lw=1, label="indicator left edge")
    axes[1].plot(t, [r.get("ind_x1", np.nan) for r in rows], color="#e08a00", lw=1, label="indicator right edge")
    axes[1].legend(loc="upper right")
    axes[1].set_ylabel("px")
    for f in fits:
        ax = axes[1] if f["kind"] == "indicator" else axes[0]
        tt = np.linspace(f["t_start"], f["t_end"], 200)
        ax.plot(tt, f["to"] + (f["from"] - f["to"]) * spring_g(tt - f["t0"], f["omega"], f["zeta"]),
                "k--", lw=0.8)
    axes[0].set_title(title + " (dashed = fitted spring)", fontsize=10)
    axes[1].set_xlabel("s")
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


# ---------- calibration ----------
def synth(path, moves, dur=3.0, fps=60, size=360, bg=236):
    """moves: list of (t0, w_from, w_to, kind, params) where kind 'spring' uses (omega, zeta)
    and kind 'ease' uses (duration,) smoothstep."""
    n = int(dur * fps)
    t = np.arange(n) / fps
    wv = np.full(n, float(moves[0][1]))
    for t0, a, b, kind, prm in moves:
        m = t >= t0
        if kind == "spring":
            wv[m] = b + (a - b) * spring_g(t[m] - t0, *prm)
        else:
            s = np.clip((t[m] - t0) / prm[0], 0, 1)
            wv[m] = a + (b - a) * (s * s * (3 - 2 * s))
    vid = np.full((n, size, size), bg, np.uint8)
    for i, w in enumerate(wv):
        x0 = size / 2 - w / 2
        x1 = size / 2 + w / 2
        cols = np.arange(size) + 0.5
        cov = np.clip(np.minimum(cols - x0, x1 - cols) + 0.5, 0, 1)  # anti-aliased edge
        vid[i, 150:210, :] = (bg * (1 - cov)).astype(np.uint8)
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "v.raw"
        raw.write_bytes(vid.tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{size}x{size}",
                        "-r", str(fps), "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12",
                        str(path)], check=True)


def selftest():
    ok = True
    cases = [
        ("spring z0.6 w18", [(0.5, 80, 240, "spring", (18.0, 0.6))], 0.6, 18.0, True),
        ("spring z1.0 w30", [(0.5, 240, 100, "spring", (30.0, 1.0))], 1.0, 30.0, False),
        ("ease (no spring)", [(0.5, 80, 240, "ease", (0.35,))], None, None, False),
    ]
    with tempfile.TemporaryDirectory() as td:
        for name, moves, z, w, has_os in cases:
            p = Path(td) / "s.mp4"
            synth(p, moves)
            frames, fps = load_gray_frames(p)
            fits = [f for f in analyse(track(frames, fps), fps) if f["axis"] == "w"]
            if len(fits) != 1:
                print(f"{name}: expected 1 fit, got {len(fits)} FAIL")
                ok = False
                continue
            f = fits[0]
            exp_os = float(np.exp(-np.pi * z / np.sqrt(1 - z * z))) if z and z < 1 else 0.0
            os_ok = abs(f["overshoot_measured"] - exp_os) <= 0.02
            if z is not None:
                zw_ok = (abs(f["zeta"] - z) <= 0.1 * z and abs(f["omega"] - w) <= 0.1 * w
                         and f["spring_consistent"])
            else:  # a smoothstep must not be reported as a spring
                zw_ok = f["overshoot_measured"] == 0.0 and not f["spring_consistent"]
            print(f"{name}: zeta {f['zeta']:.3f} omega {f['omega']:.2f} overshoot {f['overshoot_measured']:.3f} "
                  f"(want {exp_os:.3f}) nrmse {f['nrmse']:.4f} -> {'ok' if (os_ok and zw_ok) else 'FAIL'}")
            ok &= os_ok and zw_ok
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--from", dest="t_from", type=float, default=0.0)
    ap.add_argument("--to", dest="t_to", type=float, default=1e9)
    ap.add_argument("--vel", type=float, default=60.0, help="px/s threshold that marks a move")
    ap.add_argument("--width", type=int, help="downscale to this width first (compare sources at one scale)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    frames, fps = load_gray_frames(a.video, width=a.width)
    rows = track(frames, fps)
    fits = analyse(rows, fps, a.t_from, a.t_to, a.vel)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "track.json").write_text(json.dumps(rows), encoding="utf-8")
    (out / "springfit.json").write_text(json.dumps({"video": a.video, "fps": fps, "fits": fits,
                                                    "limits": "screen-space sizes (camera zoom included); "
                                                              "edges from threshold masks (dark<120, bright>249)"},
                                                   ensure_ascii=False, indent=2), encoding="utf-8")
    plot(rows, fits, out / "springfit.png", Path(a.video).name)
    for f in fits:
        print(f"{f['t0']:6.3f}s {f['kind']:9s} {f['axis']:6s} {f['from']:6.0f}->{f['to']:6.0f} "
              f"zeta {f['zeta']:.2f} omega {f['omega']:6.1f} os {f['overshoot_measured']:.3f} nrmse {f['nrmse']:.3f}")


if __name__ == "__main__":
    main()
