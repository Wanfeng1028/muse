"""Zone profile + box helpers shared by qa/check.py (bbox QA) and qa/pixel_qa.py (pixel QA)."""
from pathlib import Path

from render.common import load_json

PROFILES = Path(__file__).with_name("safe_zones.json")


def profile(name, W, H, override=None):
    P = load_json(PROFILES)[name]
    z = {
        "name": name, "W": W, "H": H,
        "safe": {"x": P["safe"]["x0"] * W, "y": P["safe"]["y0"] * H, "w": (P["safe"]["x1"] - P["safe"]["x0"]) * W, "h": (P["safe"]["y1"] - P["safe"]["y0"]) * H},
        "caption_band": {"x": 0, "y": P["caption_band"]["y0"] * H, "w": W, "h": (P["caption_band"]["y1"] - P["caption_band"]["y0"]) * H},
        "top_band": {"x": 0, "y": 0, "w": W, "h": P["top_band"]["y1"] * H},
        "min_font_px": P.get("min_font_px", 24), "face_pad": P.get("face_pad", 0.0),
        "persistent_top": P.get("persistent_top", {"min_ratio": 0.8, "min_span_s": 10}),
    }
    if override and override.get("band"):
        b = override["band"]
        z["caption_band"] = {"x": b[0] * W, "y": b[1] * H, "w": (b[2] - b[0]) * W, "h": (b[3] - b[1]) * H}
    return z


def mouth_zone(face):
    """lower third of the face box"""
    return {"x": face["x"], "y": face["y"] + face["h"] * 2 / 3, "w": face["w"], "h": face["h"] / 3}


def pad(b, f):
    return {"x": b["x"] - b["w"] * f, "y": b["y"] - b["h"] * f, "w": b["w"] * (1 + 2 * f), "h": b["h"] * (1 + 2 * f)}


def inter(a, b):
    x0, y0 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x1, y1 = min(a["x"] + a["w"], b["x"] + b["w"]), min(a["y"] + a["h"], b["y"] + b["h"])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def area(b):
    return max(0.0, b["w"]) * max(0.0, b["h"])


def contains(outer, inner, tol=4):
    return (inner["x"] >= outer["x"] - tol and inner["y"] >= outer["y"] - tol and
            inner["x"] + inner["w"] <= outer["x"] + outer["w"] + tol and inner["y"] + inner["h"] <= outer["y"] + outer["h"] + tol)


def outside(b, frame, tol=1):
    return b["x"] < frame["x"] - tol or b["y"] < frame["y"] - tol or b["x"] + b["w"] > frame["x"] + frame["w"] + tol or b["y"] + b["h"] > frame["y"] + frame["h"] + tol


def rnd(b):
    return {k: round(float(v), 1) for k, v in b.items() if k in ("x", "y", "w", "h")}
