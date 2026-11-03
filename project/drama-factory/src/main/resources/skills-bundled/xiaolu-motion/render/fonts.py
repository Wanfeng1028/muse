"""Resolve the font faces named in the style tokens to font files the page loads with
FontFace(ArrayBuffer).

tokens.fonts.<role> = {
  family, fallback, default_weight,
  open:            {name, license, download, faces:[{weight, ps, files:[path|glob, ...]}]}
                   distributable open-source fonts (default). Relative paths resolve against the
                   repo, so fonts dropped into ./fonts/ (git-ignored) are found.
  system_fallback: {faces:[{weight, ps}], files:[...]}   local-only fonts used when the open
                   font is not installed; the render report marks them non-distributable.
  subset:          reserved (distributable subset file; not produced in this version)
}
Faces inside .ttc collections are copied out by PostScript name into .cache/fonts
(raw table copy via fontTools, no re-compilation).
"""
import glob
import hashlib
import os
from pathlib import Path

from .common import CACHE, REPO

FONT_CACHE = CACHE / "fonts"


def _expand(pat):
    pat = os.path.expanduser(pat)
    if not os.path.isabs(pat):
        pat = str(REPO / pat)
    return pat


def _find_file(patterns):
    for pat in patterns or []:
        pat = _expand(pat)
        hits = sorted(glob.glob(pat)) if any(ch in pat for ch in "*?[") else ([pat] if Path(pat).exists() else [])
        if hits:
            return hits[0]
    return None


def _extract_face(path, ps):
    from fontTools.ttLib import TTCollection, TTFont
    FONT_CACHE.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1(f"{path}|{Path(path).stat().st_size}|{ps}".encode()).hexdigest()[:10]
    if path.lower().endswith((".ttc", ".otc")):
        coll = TTCollection(path, lazy=True)
        for i, f in enumerate(coll.fonts):
            if f["name"].getDebugName(6) == ps:
                ext = ".otf" if "CFF " in f else ".ttf"
                out = FONT_CACHE / f"{ps}-{tag}{ext}"
                if not out.exists():
                    tmp = out.with_suffix(out.suffix + ".part")
                    f.save(str(tmp))
                    tmp.rename(out)
                return str(out), i
        raise FileNotFoundError(f"face {ps} not found in {path}")
    if ps:
        f = TTFont(path, lazy=True)
        got = f["name"].getDebugName(6)
        if got != ps:
            raise FileNotFoundError(f"{path} is {got}, expected {ps}")
    return path, 0


def _wnum(w):
    return float(str(w).split()[0])


def resolve_faces(tokens):
    """-> [{key, role, family, weight, style, path, source, ps, index, bytes, fallback, distributable, font_name}]"""
    out = []
    for role, spec in (tokens.get("fonts") or {}).items():
        sub = spec.get("subset") or {}
        if sub.get("enabled") and sub.get("file") and Path(_expand(sub["file"])).exists():
            p = _expand(sub["file"])
            out.append({"key": f"{role}-subset", "role": role, "family": spec["family"], "weight": spec.get("default_weight", 400), "style": "normal",
                        "path": p, "source": p, "ps": None, "index": 0, "bytes": Path(p).stat().st_size, "fallback": False, "distributable": True,
                        "font_name": "subset"})
            continue
        op = spec.get("open") or {}
        found = []
        for face in op.get("faces", []):
            f = _find_file(face.get("files"))
            if f:
                try:
                    path, idx = _extract_face(f, face.get("ps")) if face.get("ps") else (f, 0)
                    found.append((face, f, path, idx))
                except FileNotFoundError:
                    pass
        if found:
            for face, src, path, idx in found:
                out.append({"key": f"{role}-{str(face['weight']).replace(' ', '_')}", "role": role, "family": spec["family"], "weight": face["weight"],
                            "style": face.get("style", "normal"), "path": path, "source": src, "ps": face.get("ps"), "index": idx,
                            "bytes": Path(path).stat().st_size, "fallback": False, "distributable": True, "font_name": op.get("name")})
            continue
        fb = spec.get("system_fallback") or {}
        src = _find_file(fb.get("files"))
        if not src:
            raise FileNotFoundError(f"font role {role}: open font {op.get('name')} not installed and no system fallback found "
                                    f"(download: {op.get('download')})")
        for face in fb.get("faces") or [{"weight": 400, "ps": None}]:
            path, idx = _extract_face(src, face.get("ps")) if face.get("ps") else (src, 0)
            out.append({"key": f"{role}-{str(face['weight']).replace(' ', '_')}", "role": role, "family": spec["family"], "weight": face["weight"],
                        "style": face.get("style", "normal"), "path": path, "source": src, "ps": face.get("ps"), "index": idx,
                        "bytes": Path(path).stat().st_size, "fallback": True, "distributable": False,
                        "font_name": f"system fallback for {op.get('name') or role}"})
    return out


def missing_open_fonts(tokens):
    """[(role, name, download)] of open fonts that fell back to system fonts"""
    miss = []
    for role, spec in (tokens.get("fonts") or {}).items():
        op = spec.get("open") or {}
        if op and not any(_find_file(f.get("files")) for f in op.get("faces", [])):
            miss.append((role, op.get("name"), op.get("download")))
    return miss
