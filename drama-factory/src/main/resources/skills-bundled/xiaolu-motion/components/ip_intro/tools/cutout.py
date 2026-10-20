"""Blue-screen die-cut portrait card -> transparent sticker PNG (keeps the white die-cut outline).

  python3 components/ip_intro/tools/cutout.py SRC.png OUT.png [--band 4] [--pad 24] [--report OUT.json]

The source is a flat blue card with a white die-cut outline around the portrait (the portrait
never touches the blue). So the only edge to key is white <-> blue:

  1. key colour K = median of the 8-px border ring; outline white W = median of the bright,
     neutral pixels next to the blue.
  2. background core = pixels close to K (RGB distance < 60) connected to the image border.
  3. transition band = pixels within `band` px of the core. There the pixel is a K/W mix:
     alpha = projection of (P - K) on (W - K); colour is set to W (despill: no blue fringe).
  4. everything else (outline + portrait) keeps its original RGB with alpha 1 — the portrait is
     not repainted or resampled.

Checks written to the report: the unmix residual inside the band (large = something other than
white/blue touches the edge), blue-tinted pixels left in the foreground, and holes / islands in
the alpha mask.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def cutout(src, out, band=4.0, pad=24):
    rgb = cv2.cvtColor(cv2.imread(str(src), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB).astype(np.float64)
    H, W, _ = rgb.shape
    ring = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3), rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)])
    K = np.median(ring, axis=0)
    dK = np.linalg.norm(rgb - K, axis=2)
    close = (dK < 60).astype(np.uint8)
    # background core: close-to-key pixels connected to the border
    n, lab = cv2.connectedComponents(close, connectivity=4)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    core = np.isin(lab, list(border))
    # distance (px) from the core, measured on the non-core side
    dist = cv2.distanceTransform((~core).astype(np.uint8), cv2.DIST_L2, 5)
    near = (~core) & (dist <= band + 6)
    lum_min = rgb.min(axis=2)
    spread = rgb.max(axis=2) - lum_min
    wsel = near & (dist > band) & (lum_min > 225) & (spread < 12)
    Wc = np.median(rgb[wsel], axis=0) if wsel.sum() > 100 else np.array([255.0, 255.0, 255.0])
    axis = Wc - K
    t = ((rgb - K) @ axis) / float(axis @ axis)
    resid = np.linalg.norm(rgb - (K + t[..., None] * axis), axis=2)
    inband = (~core) & (dist <= band)
    alpha = np.ones((H, W))
    alpha[core] = 0.0
    alpha[inband] = np.clip(t[inband], 0.0, 1.0)
    col = rgb.copy()
    col[inband] = Wc
    col[core] = Wc
    # crop to content + pad (shadow room is added by the renderer)
    ys, xs = np.where(alpha > 0.004)
    y0, y1 = max(0, ys.min() - pad), min(H, ys.max() + 1 + pad)
    x0, x1 = max(0, xs.min() - pad), min(W, xs.max() + 1 + pad)
    rgba = np.dstack([np.clip(np.round(col), 0, 255), np.round(alpha * 255)]).astype(np.uint8)[y0:y1, x0:x1]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA), [cv2.IMWRITE_PNG_COMPRESSION, 9])
    # ---- checks
    a8 = rgba[..., 3]
    fg = a8 == 255
    sub = rgb[y0:y1, x0:x1]
    blue_tint = fg & (sub[..., 2] - np.maximum(sub[..., 0], sub[..., 1]) > 90) & (sub[..., 2] > 180)
    solid = (a8 > 127).astype(np.uint8)
    n_fg, _ = cv2.connectedComponents(solid, connectivity=8)
    n_bg, _ = cv2.connectedComponents((1 - solid).astype(np.uint8), connectivity=4)
    rep = {
        "src": str(src), "out": str(out), "src_size": [W, H], "out_size": [int(x1 - x0), int(y1 - y0)], "crop": [int(x0), int(y0), int(x1), int(y1)],
        "key_rgb": [round(float(v), 1) for v in K], "outline_rgb": [round(float(v), 1) for v in Wc], "band_px": band,
        "band_pixels": int(inband.sum()), "band_resid_p99": round(float(np.percentile(resid[inband], 99)), 2), "band_resid_max": round(float(resid[inband].max()), 2),
        "alpha_partial": int(((a8 > 0) & (a8 < 255)).sum()), "blue_tinted_opaque_px": int(blue_tint.sum()),
        "foreground_islands": int(n_fg - 1), "background_regions": int(n_bg - 1),
    }
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--band", type=float, default=4.0)
    ap.add_argument("--pad", type=int, default=24)
    ap.add_argument("--report")
    a = ap.parse_args()
    rep = cutout(a.src, a.out, a.band, a.pad)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    if a.report:
        Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
