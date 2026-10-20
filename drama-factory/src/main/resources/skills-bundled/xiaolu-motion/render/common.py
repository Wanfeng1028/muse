"""Shared paths and small helpers for the render / timeline / qa tools."""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / ".cache"
STYLES = REPO / "styles"
COMPONENTS = REPO / "components"


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save_json(p, obj, indent=1):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")
    return p


def run(cmd, **kw):
    """subprocess.run with check=True and captured text output."""
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True, **kw)


def ffprobe(path):
    r = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    return json.loads(r.stdout)


def video_info(path):
    """(width, height, fps(float), frames, duration) of the first video stream."""
    P = ffprobe(path)
    v = next(s for s in P["streams"] if s["codec_type"] == "video")
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    fps = num / den
    dur = float(v.get("duration") or P["format"]["duration"])
    frames = int(v.get("nb_frames") or round(dur * fps))
    has_audio = any(s["codec_type"] == "audio" for s in P["streams"])
    return {"w": int(v["width"]), "h": int(v["height"]), "fps": fps, "fps_str": v["r_frame_rate"], "frames": frames,
            "duration": dur, "has_audio": has_audio, "pix_fmt": v.get("pix_fmt"), "color_space": v.get("color_space")}


def deep_merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        o = dict(a)
        for k, v in b.items():
            o[k] = deep_merge(a.get(k), v) if k in a else v
        return o
    return b


def load_style(name_or_path):
    """styles/<name>.json with `extends` chain merged (child overrides parent)."""
    p = Path(name_or_path)
    if not p.suffix:
        p = STYLES / f"{name_or_path}.json"
    st = load_json(p)
    parent = st.get("extends")
    if parent:
        st = deep_merge(load_style(parent), st)
    return st
