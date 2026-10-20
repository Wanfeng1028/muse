"""Camera check: the compositor's push-in/pan equals a uniform crop+resize of the source.

For sample frames, rebuild the expected picture in numpy from the source frame and
render/camera.window() (window always has the canvas aspect -> uniform scale), then compare
with the base-only composite. A stretch, a wrong centre or a one-frame time offset drops the
PSNR far below the threshold; the frame numbers also prove frame-exact alignment.

  python3 -m qa.camera_selftest RESOLVED --base-only BASE_ONLY.mp4 --out report.json
"""
import argparse
import json
import sys

import cv2
import numpy as np

from render.camera import window
from render.common import load_json, save_json, video_info
from .contact_sheet import decode


def psnr(a, b):
    m = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return 99.0 if m == 0 else 10 * np.log10(255 ** 2 / m)


def run(res_path, base_only, frames=None):
    res = load_json(res_path)
    W, H, FPS = res["canvas"]["w"], res["canvas"]["h"], res["canvas"]["fps"]
    cam = res.get("camera") or []
    frames = frames or list(range(0, res["frames"], max(1, res["frames"] // 12)))
    got = decode(base_only, frames, W, H)
    rows, ok = [], True
    for n in frames:
        t = n / FPS
        c = next(c for c in res["base"] if c["t0"] - 1e-9 <= t < c["t1"])
        info = video_info(c["src"])
        m = round((c["in"] + t - c["t0"]) * info["fps"])
        src = decode(c["src"], [m], info["w"], info["h"])[m]
        keys = cam if cam else c["camera"]
        win = window(keys, t, W, H)
        # expected: window of the (cover-fitted = identity here) source, resized to the canvas
        M = np.array([[win["zoom"], 0, -win["x"] * win["zoom"]], [0, win["zoom"], -win["y"] * win["zoom"]]], np.float64)
        exp = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        p = psnr(exp[40:-40, 40:-40], got[n][40:-40, 40:-40])
        # the same frame shifted by one source frame must match worse (time alignment)
        prev = decode(c["src"], [max(0, m - 1)], info["w"], info["h"])[max(0, m - 1)]
        p_prev = psnr(cv2.warpAffine(prev, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)[40:-40, 40:-40], got[n][40:-40, 40:-40])
        good = bool(p >= 35.0 and (p >= p_prev or m == 0))
        ok = ok and good
        rows.append({"frame": n, "t": round(t, 4), "src_frame": m, "zoom": round(win["zoom"], 5), "window": {k: round(win[k], 2) for k in ("x", "y", "w", "h")},
                     "aspect_window": round(win["w"] / win["h"], 6), "aspect_canvas": round(W / H, 6), "psnr_db": round(float(p), 2), "psnr_vs_prev_src_frame_db": round(float(p_prev), 2), "pass": good})
    return {"pass": ok, "criteria": "PSNR >= 35 dB vs numpy crop+resize of the same source frame, and better than the neighbouring source frame", "frames": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("resolved")
    ap.add_argument("--base-only", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rep = run(a.resolved, a.base_only)
    save_json(a.out, rep)
    for r in rep["frames"]:
        print(r["frame"], r["zoom"], r["psnr_db"], r["psnr_vs_prev_src_frame_db"], r["pass"])
    print("PASS" if rep["pass"] else "FAIL")
    sys.exit(0 if rep["pass"] else 1)


if __name__ == "__main__":
    main()
