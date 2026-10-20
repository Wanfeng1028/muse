"""Shared helpers for the web-video scripts (paths, storyboard, ffprobe, fonts).

Not a CLI. Imported by record.py, edl.py, verify.py, tts.py, report.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

FPS = 30                      # edit timeline frame rate; every EDL boundary snaps to 1/FPS
DEFAULT_VIEWPORT = (1280, 720)
MODES = ("feature-demo", "bug-report")

WINFONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
FONT_CANDIDATES = [            # need Vietnamese glyphs (ă ơ ư ạ ...)
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    os.path.join(WINFONTS, "arial.ttf"),
    os.path.join(WINFONTS, "segoeui.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]
MONO_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",
    os.path.join(WINFONTS, "consola.ttf"),
    os.path.join(WINFONTS, "cour.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
]

# Vietnamese text on a Windows console (cp1252) would raise UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def need(binary: str):
    if not shutil.which(binary):
        die(f"'{binary}' not found. Install it first (macOS: brew install {binary}).")


def font(mono: bool = False) -> str:
    env = os.environ.get("WEB_VIDEO_MONO_FONT" if mono else "WEB_VIDEO_FONT")
    if env:
        return env
    for p in (MONO_CANDIDATES if mono else FONT_CANDIDATES):
        if os.path.exists(p):
            return p
    die("no usable font found; set WEB_VIDEO_FONT to a .ttf path")


def link_or_copy(src, dst) -> None:
    """Make dst point at src: symlink, else hard link, else copy (Windows without developer mode)."""
    src, dst = pathlib.Path(src), pathlib.Path(dst)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    for make in (os.symlink, os.link):
        try:
            make(src, dst)
            return
        except (OSError, NotImplementedError):
            continue
    shutil.copy2(src, dst)


def snap(t: float) -> float:
    """Snap a time to the FPS frame grid."""
    return round(round(t * FPS) / FPS, 6)


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s[:48] or "video"


def next_run_dir(root: pathlib.Path, slug: str) -> pathlib.Path:
    """video-out/<slug>/v<N>/ with N one higher than any existing run (never overwrite)."""
    base = root / slug
    base.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for p in base.iterdir() if (m := re.fullmatch(r"v(\d+)", p.name))]
    d = base / f"v{max(nums, default=0) + 1}"
    d.mkdir()
    return d


# ---------- storyboard ----------

def load_storyboard(path: pathlib.Path) -> dict:
    import yaml  # PyYAML
    sb = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))
    errs = validate_storyboard(sb)
    if errs:
        die("storyboard invalid:\n  - " + "\n  - ".join(errs))
    return sb


def validate_storyboard(sb) -> list[str]:
    errs = []
    if not isinstance(sb, dict):
        return ["top level must be a mapping"]
    if sb.get("mode") not in MODES:
        errs.append(f"mode must be one of {MODES}")
    if not sb.get("url"):
        errs.append("url is required")
    steps = sb.get("steps")
    if not isinstance(steps, list) or not steps:
        errs.append("steps must be a non-empty list")
        return errs
    visible = [s for s in steps if not s.get("hidden")]
    if not visible:
        errs.append("at least one step must be visible (hidden: false)")
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict) or "do" not in s:
            errs.append(f"step {i}: needs a 'do' field")
            continue
        if not s.get("hidden") and not s.get("caption"):
            errs.append(f"step {i}: visible steps need a caption")
        if s.get("caption") and len(str(s["caption"]).split()) > 12:
            errs.append(f"step {i}: caption over 12 words")
    if len(visible) > 8:
        errs.append(f"{len(visible)} visible steps; max 8 (split into two videos)")
    if sb.get("mode") == "bug-report":
        bug = sb.get("bug") or {}
        for k in ("expected", "actual"):
            if not bug.get(k):
                errs.append(f"bug.{k} is required in bug-report mode")
        if not any(s.get("bug") for s in steps):
            errs.append("bug-report: mark the step where the bug shows with 'bug: true'")
    if sb.get("theme") and sb.get("mode") != "feature-demo":
        errs.append("'theme' applies to feature-demo only")
    if sb.get("theme") is not None and not isinstance(sb.get("theme"), str):
        errs.append("'theme' must be a theme name (clean, a personal theme) or a path to a theme YAML")
    if sb.get("profile") and sb.get("storage_state"):
        errs.append("use either 'profile' or 'storage_state', not both")
    if sb.get("channel") not in (None, "chrome", "chrome-beta", "msedge", "chromium"):
        errs.append("channel must be chrome, chrome-beta, msedge or chromium")
    if sb.get("channel") and not sb.get("profile"):
        errs.append("'channel' applies only with 'profile'")
    vp = sb.get("viewport", list(DEFAULT_VIEWPORT))
    if not (isinstance(vp, list) and len(vp) == 2 and all(isinstance(v, int) and v % 2 == 0 for v in vp)):
        errs.append("viewport must be [even_width, even_height]")
    return errs


def run_paths(run: pathlib.Path) -> dict:
    run = pathlib.Path(run)
    return {k: run / v for k, v in {
        "storyboard": "storyboard.yaml", "events": "events.json", "raw": "raw.webm",
        "console": "console.json", "har": "net.har", "trace": "trace.zip", "meta": "meta.json",
        "filter": "filter.txt", "edl": "edl.json", "srt": "captions.srt",
        "draft": "draft.mp4", "edited": "edited.mp4", "final": "final.mp4",
        "narration": "narration/manifest.json", "verify": "verify",
    }.items()}


def load_json(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def save_json(p, data):
    tmp = pathlib.Path(str(p) + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


# ---------- ffprobe ----------

def ffprobe(path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"ffprobe failed on {path}")
    return json.loads(out.stdout)


def probe_summary(path) -> dict:
    info = ffprobe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fps = None
    if v and v.get("avg_frame_rate", "0/0") != "0/0":
        n, d = v["avg_frame_rate"].split("/")
        fps = round(int(n) / int(d), 2) if int(d) else None
    return {
        "duration": float(info["format"].get("duration", 0) or 0),
        "size_bytes": int(info["format"].get("size", 0) or 0),
        "video_codec": v and v.get("codec_name"), "pix_fmt": v and v.get("pix_fmt"),
        "width": v and v.get("width"), "height": v and v.get("height"), "fps": fps,
        "audio_codec": a and a.get("codec_name"),
    }


_FF_MAJOR = None


def ffmpeg_major() -> int:
    """Major version of the ffmpeg on PATH (0 if unknown, e.g. git builds)."""
    global _FF_MAJOR
    if _FF_MAJOR is None:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout
        m = re.search(r"ffmpeg version n?(\d+)\.", out)
        _FF_MAJOR = int(m.group(1)) if m else 0
    return _FF_MAJOR


def require_filters(names=("drawtext", "zoompan")):
    """Stop with an install hint when this ffmpeg lacks a filter we use (Homebrew's `ffmpeg` 8+ has no drawtext)."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    have = {parts[1] for parts in (l.split() for l in out.splitlines()) if len(parts) > 2}
    missing = [n for n in names if n not in have]
    if missing:
        hint = {"darwin": "brew install ffmpeg-full, then put $(brew --prefix ffmpeg-full)/bin first on PATH",
                "win32": "winget install Gyan.FFmpeg (full build)"}.get(sys.platform, "install a full ffmpeg build")
        die(f"this ffmpeg has no {', '.join(missing)} filter(s). {hint}")


def filter_script_args(path: str) -> list[str]:
    """Read a filter graph from a file: `-/filter_complex FILE` on ffmpeg >= 7 (the old
    `-filter_complex_script` was deprecated in 7 and removed in 8); unknown versions use the new form."""
    major = ffmpeg_major()
    return ["-filter_complex_script", path] if 0 < major < 7 else ["-/filter_complex", path]


def run_ffmpeg(args: list[str], quiet: bool = True):
    """Run ffmpeg with an argv list (never a shell string)."""
    cmd = ["ffmpeg", "-hide_banner", "-y"] + (["-v", "error"] if quiet else []) + args
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + " ".join(cmd) + "\n" + r.stderr[-3000:])
    return r
