"""The look of the reel overlays (headline panel, caption chips, font), read from ONE file:
<skill>/look.json, or the file named in $WHITEBOARD_LOOK. Nothing else in scripts/ holds a color
or a font path.

    from look import LOOK
    LOOK["font_path"], LOOK["font_index"], LOOK["font_name"]
    LOOK["headline"]["panel_color"]   -> (r, g, b)
    LOOK["captions"]["gradient_top"]  -> (r, g, b)

`python3 look.py` prints the resolved look (which font was found), for a check after an edit.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from PIL import ImageFont

LOOK_FILE = Path(os.environ.get("WHITEBOARD_LOOK") or Path(__file__).resolve().parent.parent / "look.json")


def _rgb(v):
    s = str(v).lstrip("#")
    if len(s) != 6:
        raise SystemExit(f"{LOOK_FILE}: a color must be #RRGGBB, got {v!r}")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _find_font(cands):
    """The first candidate on this machine, with the face index found by name (the index of a
    style inside a .ttc differs between macOS versions)."""
    tried = []
    for c in cands:
        p = c["path"]
        if not Path(p).exists():
            tried.append(f"{p} (missing)")
            continue
        if "index" in c:
            return p, int(c["index"]), f"{c.get('family', Path(p).stem)} {c.get('style', '')}".strip()
        i = 0
        while i < 64:
            try:
                fam, sty = ImageFont.truetype(p, 20, index=i).getname()
            except OSError:
                break
            if fam == c.get("family", fam) and sty == c.get("style", sty):
                return p, i, f"{fam} {sty}"
            i += 1
        tried.append(f"{p} (no face named {c.get('family')} {c.get('style')})")
    raise SystemExit(f"{LOOK_FILE}: no caption font found. Tried: " + "; ".join(tried) + ". Add a font you have to font.candidates.")


def load():
    try:
        raw = json.load(open(LOOK_FILE))
    except OSError as e:
        raise SystemExit(f"look file not readable: {LOOK_FILE} ({e})")
    path, index, name = _find_font(raw["font"]["candidates"])
    h, c = raw["headline"], raw["captions"]
    return {
        "file": str(LOOK_FILE), "font_path": path, "font_index": index, "font_name": name,
        "font_is_first_choice": path == raw["font"]["candidates"][0]["path"],
        "headline": {"panel_color": _rgb(h["panel_color"]), "text_color": _rgb(h["text_color"]), "cap_px": int(h["cap_px"]),
                     "pad_x": int(h["pad_x"]), "pad_y": int(h["pad_y"]), "corner_radius": int(h["corner_radius"])},
        "captions": {"cap_px": int(c["cap_px"]), "gradient_top": _rgb(c["gradient_top"]), "gradient_bottom": _rgb(c["gradient_bottom"]),
                     "shadow_alpha": int(c["shadow_alpha"]), "shadow_blur": int(c["shadow_blur"]), "shadow_dy": int(c["shadow_dy"])},
    }


LOOK = load()

if __name__ == "__main__":
    print(json.dumps(LOOK, indent=1))
    if not LOOK["font_is_first_choice"]:
        print(f"note: the first choice font is missing, using the fallback {LOOK['font_name']}", file=sys.stderr)
