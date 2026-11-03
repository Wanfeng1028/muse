"""Record what an alpha video really contains (HEVC-alpha / ProRes 4444).

  python3 -m render.probe_alpha OVERLAY.hevc_alpha.mov [--ref OVERLAY.mov] [--frame N] --out probe.json

- ffprobe: codec / tag / profile / pix_fmt / colour tags. For HEVC with alpha ffprobe reports the
  primary layer only (pix_fmt yuv420p): ffmpeg's decoder does not output the alpha layer.
- ffmpeg trace_headers: VPS layer count, nuh_layer_id=1 NAL units (the alpha layer) and the
  Alpha Channel Information SEI (payload 165; alpha_channel_use_idc 1 = premultiplied).
- AVFoundation (render/avf_probe.swift): ContainsAlphaChannel / AlphaChannelMode from the format
  description and the decoded alpha of one frame; compared with the ProRes reference frame.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from .common import CACHE, ffprobe, save_json

SRC = Path(__file__).with_name("avf_probe.swift")
BIN = CACHE / "bin" / "avf_probe"


def _bin():
    if not BIN.exists() or BIN.stat().st_mtime < SRC.stat().st_mtime:
        BIN.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["swiftc", "-O", "-o", str(BIN), str(SRC)], check=True, capture_output=True)
    return BIN


def trace(path, frames=2):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "trace", "-i", str(path), "-c", "copy", "-bsf:v", "trace_headers",
                        "-frames:v", str(frames), "-f", "null", "-"], capture_output=True, text=True)
    txt = r.stderr
    g = lambda pat: [int(m) for m in re.findall(pat, txt)]
    layers = g(r"nuh_layer_id\s+\d+ = (\d+)")
    return {"vps_max_layers_minus1": (g(r"vps_max_layers_minus1\s+\d+ = (\d+)") or [None])[0],
            "nal_units_layer0": layers.count(0), "nal_units_layer1_alpha": layers.count(1),
            "sei_payload_types": sorted(set(g(r"last_payload_type_byte\s+\d+ = (\d+)"))),
            "alpha_channel_use_idc": (g(r"alpha_channel_use_idc\s+\d+ = (\d+)") or [None])[0],
            "alpha_channel_bit_depth_minus8": (g(r"alpha_channel_bit_depth_minus8\s+\d+ = (\d+)") or [None])[0],
            "alpha_transparent_value": (g(r"alpha_transparent_value\s+\d+ = (\d+)") or [None])[0],
            "alpha_opaque_value": (g(r"alpha_opaque_value\s+\d+ = (\d+)") or [None])[0]}


def run(path, ref=None, frame=150):
    P = ffprobe(path)
    v = next(s for s in P["streams"] if s["codec_type"] == "video")
    keys = ("codec_name", "codec_tag_string", "profile", "pix_fmt", "width", "height", "r_frame_rate", "nb_frames", "duration",
            "color_space", "color_primaries", "color_transfer", "color_range")
    out = {"file": str(path), "bytes": Path(path).stat().st_size, "ffprobe": {k: v.get(k) for k in keys},
           "ffprobe_note": "ffmpeg decodes only the primary HEVC layer, so pix_fmt shows no alpha; see trace_headers and avfoundation"}
    if v["codec_name"] == "hevc":
        out["trace_headers"] = trace(path)
    raw = CACHE / "avf_frame.rgba"
    r = subprocess.run([str(_bin()), str(path), str(frame), str(raw)], check=True, capture_output=True, text=True)
    out["avfoundation"] = json.loads(r.stdout)
    if ref:
        W, H = int(v["width"]), int(v["height"])
        a = np.fromfile(raw, np.uint8).reshape(H, W, 4).astype(np.int16)
        rr = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ref), "-vf", f"select=eq(n\\,{frame}),scale=in_color_matrix=bt709:in_range=tv:out_range=pc",
                             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"], check=True, capture_output=True)
        b = np.frombuffer(rr.stdout, np.uint8).reshape(H, W, 4).astype(np.int16)
        d = np.abs(a - b)
        out["vs_prores_frame"] = {"frame": frame, "rgb_max": int(d[..., :3].max()), "rgb_mean": round(float(d[..., :3].mean()), 3),
                                  "rgb_p999": float(np.percentile(d[..., :3], 99.9)), "alpha_max": int(d[..., 3].max()),
                                  "alpha_mean": round(float(d[..., 3].mean()), 3), "alpha_p999": float(np.percentile(d[..., 3], 99.9)),
                                  "opaque_px_ref": int((b[..., 3] == 255).sum()), "opaque_px_hevc": int((a[..., 3] >= 250).sum())}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--ref")
    ap.add_argument("--frame", type=int, default=150)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rep = run(a.path, a.ref, a.frame)
    save_json(a.out, rep)
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
