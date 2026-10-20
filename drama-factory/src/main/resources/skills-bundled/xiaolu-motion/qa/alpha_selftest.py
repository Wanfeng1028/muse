"""Transparent-mode correctness test (glow, antialiased edges, panel edges).

For key frames: render the overlay (transparent, premultiplied) and the same frame in opaque
mode on a flat background colour C (vignette/grain off). A correct transparent layer must
reproduce the opaque look exactly when composited:  O.rgb + C * (1 - O.a)  ==  opaque(C).
Dark fringes (straight alpha treated as premultiplied the wrong way) or dirty edges (glow
keyed badly) would show up as large differences, strongest on white / black.
Also checks the ProRes round trip (decoded MOV frame) and the ffmpeg compositor's blend
(maskedmerge + addition in planar RGB, render/composite.py premul_over) against the same maths.
(ffmpeg's overlay=alpha=premultiplied was measured off by 16 levels in gbrp and mis-weighted
at semi-transparent edges, which is why the compositor does not use it.)

  python3 -m qa.alpha_selftest resolved.json --overlay overlay.mov --out report.json
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from render.common import load_json, save_json
from render.overlay import stills
from .contact_sheet import decode, key_times


def over(o, c):
    return o[..., :3].astype(np.float32) + np.asarray(c, np.float32) * (1 - o[..., 3:4].astype(np.float32) / 255.0)


def stats(a, b):
    d = np.abs(a.astype(np.float32) - b.astype(np.float32))
    return {"max": float(d.max()), "mean": round(float(d.mean()), 4), "p999": float(np.percentile(d, 99.9))}


def ffmpeg_composite(mov, n, color, W, H, FPS, tmpdir):
    """frame n of the overlay blended by the compositor's own graph pieces (render/composite.py
    premul_over) on a flat base encoded like camera footage (yuv420p, BT.709, limited range).
    Returns the blend (RGB, before the final 4:2:0 encode) and the base as the compositor sees it."""
    from render.composite import BASE_TO_RGB, OV_TO_RGBA, premul_over
    base = Path(tmpdir) / ("flat_%02x%02x%02x.mp4" % tuple(color))
    if not base.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x%02X%02X%02X:s=%dx%d:r=%d:d=0.2" % (*color, W, H, FPS),
                        "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "libx264", "-qp", "0", "-color_primaries", "bt709",
                        "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", str(base)], check=True)
    g = ";".join([f"[0:v]trim=end_frame=1,setpts=PTS-STARTPTS,{BASE_TO_RGB},split[bg][bo]",
                  f"[1:v]select=eq(n\\,{n}),setpts=PTS-STARTPTS,{OV_TO_RGBA}[ov]",
                  *premul_over("bg", "ov", "mix", "t"), "[mix]format=rgb24[vout]", "[bo]format=rgb24[bout]"])
    fo, fb = Path(tmpdir) / "mix.rgb", Path(tmpdir) / "base.rgb"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(base), "-i", str(mov), "-filter_complex", g,
                    "-map", "[vout]", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", str(fo),
                    "-map", "[bout]", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", str(fb)], check=True)
    return (np.fromfile(fo, np.uint8)[:W * H * 3].reshape(H, W, 3), np.fromfile(fb, np.uint8)[:W * H * 3].reshape(H, W, 3))


def run(res_path, overlay=None, frames=None):
    res = load_json(res_path)
    C = res["canvas"]
    W, H, FPS = C["w"], C["h"], C["fps"]
    frames = frames or key_times(res, 6)
    times = [n / FPS for n in frames]
    colors = {"black": (0, 0, 0), "white": (255, 255, 255), "gray": (128, 128, 128), "style_bg": tuple(int(res["tokens"]["colors"]["bg"][i:i + 2], 16) for i in (1, 3, 5))}
    ov, _ = stills(res, times, mode="overlay", overrides={"grain": 0})
    dec = decode(overlay, frames, W, H, rgba=True) if overlay else {}
    out = {"frames": frames, "tests": []}
    ok = True
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="xm_alpha_")
    for name, c in colors.items():
        hexc = "#%02x%02x%02x" % c
        op, _ = stills(res, times, mode="opaque", overrides={"bg": hexc, "bgGlow": hexc, "vig": 0, "grain": 0, "fade": 1})
        for n, o, p in zip(frames, ov, op):
            row = {"bg": name, "frame": n, "direct": stats(np.clip(over(o, c) + 0.5, 0, 255).astype(np.uint8), p[..., :3]),
                   "glow_pixels_rgb_gt_alpha": int((o[..., :3].max(2) > o[..., 3]).sum()),
                   "semi_transparent_pixels": int(((o[..., 3] > 0) & (o[..., 3] < 255)).sum())}
            if n in dec:
                row["prores_roundtrip"] = stats(np.clip(over(dec[n], c) + 0.5, 0, 255).astype(np.uint8), p[..., :3])
                mix, base_rgb = ffmpeg_composite(overlay, n, c, W, H, FPS, tmpdir)
                # the compositor must equal premultiplied maths on the base it actually sees
                row["ffmpeg_composite"] = stats(mix, np.clip(over(dec[n], base_rgb.astype(np.float32)) + 0.5, 0, 255).astype(np.uint8))
                row["base_seen_vs_flat"] = stats(base_rgb, np.broadcast_to(np.array(c, np.uint8), base_rgb.shape))
            good = row["direct"]["max"] <= 3 and row["direct"]["p999"] <= 2
            if "prores_roundtrip" in row:
                good = good and row["prores_roundtrip"]["p999"] <= 4 and row["ffmpeg_composite"]["p999"] <= 4
            row["pass"] = bool(good)
            ok = ok and good
            out["tests"].append(row)
    out["pass"] = ok
    out["criteria"] = "direct: max<=3 & p99.9<=2 levels; ProRes round trip and ffmpeg composite: p99.9<=4 levels (8-bit)"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("resolved")
    ap.add_argument("--overlay")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rep = run(a.resolved, a.overlay)
    save_json(a.out, rep)
    worst = {k: max(t[k]["max"] for t in rep["tests"] if k in t) for k in ("direct", "prores_roundtrip", "ffmpeg_composite") if any(k in t for t in rep["tests"])}
    print(json.dumps({"pass": rep["pass"], "worst_max_diff": worst, "n": len(rep["tests"])}, indent=1))
    sys.exit(0 if rep["pass"] else 1)


if __name__ == "__main__":
    main()
