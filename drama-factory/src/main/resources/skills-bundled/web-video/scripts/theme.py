#!/usr/bin/env python3
"""Design themes for feature-demo videos: a framed recording on a designed background.

USAGE
  theme.py init --repo PROJECT [--out theme.yaml]   # draft a theme from the project's own design (do this first)
  theme.py preview THEME --out DIR [--title T] [--subtitle S] [--caption C]
                                                    # render background, card and caption PNGs to look at
  theme.py check THEME                              # validate keys, colours, fonts, Vietnamese glyphs
  theme.py fonts THEME                              # which font file each role resolves to
  theme.py list                                     # built-in and personal themes

A video for project X should look like project X: run `init --repo X`, review the draft against the
project's design, preview, then set `theme: theme.yaml` in the storyboard. The built-in `clean` base is
neutral and only a fallback. THEME is a name (personal themes in ~/.config/web-video/themes, override
with WEB_VIDEO_THEME_DIR, then built-ins in assets/themes) or a path to a YAML file. A theme file may
start with `extends: NAME_OR_PATH` and override only some keys (deep merge). edl.py calls
render_layers() when the storyboard has `theme:`; every layer is a PNG drawn with Pillow.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import random
import sys

import yaml
from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
THEMES = HERE.parent / "assets" / "themes"
USER_THEMES = pathlib.Path(os.environ.get("WEB_VIDEO_THEME_DIR") or pathlib.Path.home() / ".config/web-video/themes")
REQUIRED_COLORS = ("paper", "paper_deep", "ink", "ink_60", "ink_40", "ink_12", "ink_08", "seal", "seal_text")
COLOR_RE = __import__("re").compile(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?")
FONT_CACHE = pathlib.Path(os.environ.get("WEB_VIDEO_FONT_DIR") or pathlib.Path.home() / ".cache/web-video/fonts")
HANZI_NUMERALS = "〇一二三四五六七八九十"


# ---------- loading ----------

def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def theme_path(spec: str, base_dir: pathlib.Path | None = None) -> pathlib.Path:
    if spec.endswith((".yaml", ".yml")) or os.sep in spec or "/" in spec:
        p = pathlib.Path(spec).expanduser()
        if not p.is_absolute() and base_dir:
            p = base_dir / p
        return p.resolve()
    personal = USER_THEMES / f"{spec}.yaml"
    return personal if personal.exists() else THEMES / f"{spec}.yaml"


def theme_names() -> list[tuple[str, str]]:
    out = {f.stem: "built-in" for f in THEMES.glob("*.yaml")}
    if USER_THEMES.is_dir():
        out.update({f.stem: f"personal ({USER_THEMES})" for f in USER_THEMES.glob("*.yaml")})
    return sorted(out.items())


def validate_theme(t: dict) -> list[str]:
    errs = []
    try:
        cw, ch = t["canvas"]
        if not (isinstance(cw, int) and isinstance(ch, int) and cw % 2 == 0 and ch % 2 == 0 and cw > 0 and ch > 0):
            errs.append("canvas must be [even_width, even_height]")
        if not 0 < int(t["frame"]["width"]) < cw:
            errs.append(f"frame.width must be between 0 and the canvas width ({cw})")
    except (KeyError, TypeError, ValueError):
        errs.append("canvas: [w, h] and frame.width are required")
    colors = t.get("colors") or {}
    for k in REQUIRED_COLORS:
        v = colors.get(k)
        if v is None:
            errs.append(f"colors.{k} is missing")
        elif not (isinstance(v, str) and COLOR_RE.fullmatch(v)):
            errs.append(f"colors.{k} must be #RRGGBB or #RRGGBBAA, got {v!r}")
    fonts = t.get("fonts") or {}
    for role in ("display", "mono"):
        if not fonts.get(role):
            errs.append(f"fonts.{role} needs at least one candidate")
    if t.get("numerals", "arabic") not in ("arabic", "hanzi"):
        errs.append("numerals must be arabic or hanzi")
    if t.get("numerals") == "hanzi" and not fonts.get("hanzi"):
        errs.append("numerals: hanzi needs a fonts.hanzi entry")
    for k in ("caption", "card"):
        if not isinstance(t.get(k), dict):
            errs.append(f"{k} section is missing")
    return errs


def load_theme(spec: str, base_dir: pathlib.Path | None = None, _depth: int = 0) -> dict:
    path = theme_path(spec, base_dir)
    if not path.exists():
        known = ", ".join(p.stem for p in sorted(THEMES.glob("*.yaml")))
        raise SystemExit(f"error: theme {spec!r} not found ({path}); built-in: {known}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    own_name = data.get("name")
    parent = data.pop("extends", None)
    if parent:
        if _depth > 4:
            raise SystemExit("error: theme 'extends' chain is too deep")
        data = _merge(load_theme(parent, path.parent, _depth + 1), data)
    data["name"] = own_name or path.stem               # a child never inherits its parent's name
    if _depth == 0:
        errs = validate_theme(data)
        if errs:
            raise SystemExit(f"error: theme {path}:\n  - " + "\n  - ".join(errs))
    return data


def rgba(value: str) -> tuple[int, int, int, int]:
    v = value.lstrip("#")
    if len(v) == 6:
        v += "FF"
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4, 6))  # type: ignore[return-value]


def font_file(theme: dict, role: str) -> tuple[str, int]:
    """(path, ttc index) of the first available candidate for a role."""
    for entry in theme["fonts"].get(role) or theme["fonts"]["display"]:
        path, _, face = str(entry).partition("::")
        candidate = pathlib.Path(path).expanduser()
        if not candidate.is_absolute() and "/" not in path:
            candidate = FONT_CACHE / path
        if not candidate.exists():
            continue
        if not face:
            return str(candidate), 0
        for index in range(16):
            try:
                name = " ".join(ImageFont.truetype(str(candidate), 12, index=index).getname())
            except OSError:
                break
            if name == face:
                return str(candidate), index
    raise SystemExit(f"error: no font found for role {role!r} in theme {theme.get('name')}")


class Fonts:
    def __init__(self, theme: dict):
        self.theme = theme
        self.cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def __call__(self, role: str, size: int) -> ImageFont.FreeTypeFont:
        key = (role, size)
        if key not in self.cache:
            path, index = font_file(self.theme, role)
            self.cache[key] = ImageFont.truetype(path, size, index=index)
        return self.cache[key]


# ---------- geometry ----------

def layout(theme: dict, viewport: tuple[int, int]) -> dict:
    cw, ch = theme["canvas"]
    vw, vh = viewport
    fy = int(theme["frame"]["top"]) // 2 * 2
    band = int(theme["caption"]["band_gap"]) + int(theme["caption"]["size"] * 1.15) + 24
    max_fh = ch - fy - band
    if max_fh < ch * 0.4:
        raise SystemExit("error: theme frame leaves no room for the caption band; lower frame.top or caption.size")
    fw = int(theme["frame"]["width"]) // 2 * 2
    if fw * vh / vw > max_fh:                            # tall viewports (16:10, 4:3): shrink to fit the band
        fw = int(max_fh * vw / vh) // 2 * 2
    fh = int(round(fw * vh / vw / 2)) * 2
    fx = (cw - fw) // 2 // 2 * 2
    band_top = fy + fh + int(theme["caption"]["band_gap"])
    return {"canvas": (cw, ch), "frame": (fx, fy, fw, fh), "band_top": band_top}


def numeral(n: int, style: str) -> str:
    if style != "hanzi" or n > 99:
        return f"{n:02d}"
    if n <= 10:
        return HANZI_NUMERALS[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else HANZI_NUMERALS[tens]) + "十" + (HANZI_NUMERALS[ones] if ones else "")


# ---------- drawing helpers ----------

_MISSING: dict[int, bytes] = {}


def has_glyph(font, ch: str) -> bool:
    """False when the font would draw its .notdef box for ch (e.g. Menlo has no Vietnamese capitals)."""
    if ch.isspace() or ord(ch) < 128:
        return True
    key = id(font)
    if key not in _MISSING:
        _MISSING[key] = bytes(font.getmask("\U0010fffd"))
    return bytes(font.getmask(ch)) != _MISSING[key]


def _label_font(font, fallback, text: str):
    """One font for the whole label: the fallback when the main font misses any glyph."""
    if fallback is None or all(has_glyph(font, ch) for ch in text):
        return font
    return fallback


def _spaced(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, spacing: float, fallback=None) -> int:
    """Letter-spaced label; uses the fallback font when the main font misses a glyph. Returns the end x."""
    x, y = xy
    f = _label_font(font, fallback, text)
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f) + spacing
    return int(x - spacing)


def _spaced_width(draw, text: str, font, spacing: float, fallback=None) -> int:
    f = _label_font(font, fallback, text)
    width = sum(draw.textlength(ch, font=f) for ch in text)
    return int(width + spacing * max(0, len(text) - 1))


def _grain(img: Image.Image, opacity: float, seed: int = 9) -> Image.Image:
    if opacity <= 0:
        return img
    rnd = random.Random(seed)
    w, h = img.size
    small = Image.new("L", (w // 2, h // 2))
    small.putdata([rnd.randint(0, 255) for _ in range(small.width * small.height)])
    noise = small.resize((w, h), Image.NEAREST).convert("RGBA")
    noise.putalpha(int(255 * opacity))
    return Image.alpha_composite(img, noise)


def _seal(img: Image.Image, center, size: int, glyph: str, theme: dict, fonts: Fonts, angle: float = 0) -> None:
    chip = Image.new("RGBA", (size, size), rgba(theme["colors"]["seal"]))
    d = ImageDraw.Draw(chip)
    cjk = any(ord(c) >= 0x2E80 for c in glyph)
    f = fonts("hanzi" if cjk and theme["fonts"].get("hanzi") else "display", int(size * (0.62 if cjk else 0.5)))
    box = d.textbbox((0, 0), glyph, font=f)
    d.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), glyph,
           font=f, fill=rgba(theme["colors"]["seal_text"]))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=max(2, size // 20), fill=255)
    chip.putalpha(mask)
    if angle:
        chip = chip.rotate(angle, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(chip, (int(center[0] - chip.width / 2), int(center[1] - chip.height / 2)))


def _watermark(img: Image.Image, glyph: str, theme: dict, fonts: Fonts, size: int, xy, opacity: float) -> None:
    if not glyph:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ink = rgba(theme["colors"]["ink"])
    ImageDraw.Draw(layer).text(xy, glyph, font=fonts("brush", size), fill=ink[:3] + (int(255 * opacity),))
    img.alpha_composite(layer)


def _vertical(draw, x: int, y: int, text: str, theme: dict, fonts: Fonts, size: int) -> None:
    f = fonts("hanzi", size)
    for ch in text:
        if ch == " ":
            y += size // 2
            continue
        glyph = "︙" if ch == "·" else ch
        w = draw.textlength(glyph, font=f)
        draw.text((x - w / 2, y), glyph, font=f, fill=rgba(theme["colors"]["ink_40"]))
        y += int(size * 1.25)


def _wrap(draw, text: str, font, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = w
    return lines + ([line] if line else [])


def _balanced(draw, text: str, font, width: int) -> list[str]:
    """Wrap, then even out the lines so a single word never sits alone on the last line."""
    lines = _wrap(draw, text, font, width)
    if len(lines) < 2:
        return lines
    words = text.split()
    target = draw.textlength(text, font=font) / len(lines)
    out, line = [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if line and draw.textlength(trial, font=font) > target * 1.08 and len(out) < len(lines) - 1:
            out.append(line)
            line = w
        else:
            line = trial
    return out + [line]


def _paper(theme: dict, size) -> Image.Image:
    return Image.new("RGBA", size, rgba(theme["colors"]["paper"]))


def _header(img: Image.Image, theme: dict, fonts: Fonts, label: str) -> None:
    cw, _ = img.size
    d = ImageDraw.Draw(img)
    x = 92
    if theme.get("seal_glyph"):
        _seal(img, (92, 56), 40, theme["seal_glyph"], theme, fonts)
        x = 128
    mono, serif = fonts("mono", 17), fonts("display", 18)
    if theme.get("brand"):
        _spaced(d, (x, 46), str(theme["brand"]).upper(), mono, rgba(theme["colors"]["ink"]), 5, serif)
    if label:
        text = label.upper()
        x = cw - 92 - _spaced_width(d, text, mono, 4, serif)
        _spaced(d, (x, 46), text, mono, rgba(theme["colors"]["ink_40"]), 4, serif)


# ---------- layers ----------

def background(theme: dict, lay: dict, label: str) -> Image.Image:
    cw, ch = lay["canvas"]
    fx, fy, fw, fh = lay["frame"]
    fonts = Fonts(theme)
    img = _paper(theme, (cw, ch))
    _watermark(img, theme.get("watermark_glyph", ""), theme, fonts, int(ch * 0.9), (int(cw * 0.58), int(ch * 0.04)), 0.05)
    img = _grain(img, float(theme.get("grain", 0)))
    _header(img, theme, fonts, label)
    d = ImageDraw.Draw(img)
    d.rectangle((fx - 1, fy - 1, fx + fw, fy + fh), outline=rgba(theme["colors"]["ink_12"]), width=1)
    gap = int(theme["frame"].get("double_rule", 0))
    if gap:
        d.rectangle((fx - 1 - gap, fy - 1 - gap, fx + fw + gap, fy + fh + gap),
                    outline=rgba(theme["colors"]["ink_08"]), width=1)
    if theme.get("vertical_note"):
        _vertical(d, cw - (cw - fx - fw) // 2 + 8, fy + 24, theme["vertical_note"], theme, fonts, 20)
    return img


def caption(theme: dict, lay: dict, n: int, text: str) -> Image.Image:
    cw, ch = lay["canvas"]
    fonts = Fonts(theme)
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = int(theme["caption"]["size"])
    while True:                                  # shrink long captions until they fit 90 % of the canvas
        f = fonts("display", size)
        chip = int(size * 1.15)
        tw = d.textlength(text, font=f)
        total = chip + 22 + tw
        if total <= cw * 0.9 or size <= 18:
            break
        size -= 2
    x = (cw - total) / 2
    y = lay["band_top"]
    _seal(img, (x + chip / 2, y + chip / 2), chip, numeral(n, theme.get("numerals", "hanzi")), theme, fonts)
    box = d.textbbox((0, 0), text, font=f)
    d.text((x + chip + 22, y + (chip - (box[3] - box[1])) / 2 - box[1]), text, font=f,
           fill=rgba(theme["colors"]["ink"]))
    return img


def card(theme: dict, lay: dict, title: str, subtitle: str | None, label: str, kind: str = "intro") -> Image.Image:
    cw, ch = lay["canvas"]
    fonts = Fonts(theme)
    img = _paper(theme, (cw, ch))
    _watermark(img, theme.get("watermark_glyph", ""), theme, fonts, int(ch * 1.0), (int(cw * 0.56), int(-ch * 0.02)), 0.055)
    img = _grain(img, float(theme.get("grain", 0)))
    _header(img, theme, fonts, label)
    d = ImageDraw.Draw(img)
    left = 168
    if kind == "intro":
        y = int(ch * 0.30)
        mono = fonts("mono", 18)
        eyebrow = str(theme.get("eyebrow") or "").upper()      # the brand is already in the header
        if eyebrow:
            d.line((left, y + 10, left + 36, y + 10), fill=rgba(theme["colors"]["seal"]), width=2)
            _spaced(d, (left + 54, y), eyebrow, mono, rgba(theme["colors"]["ink_40"]), 5, fonts("display", 19))
        tf = fonts("display", int(theme["card"]["title_size"]))
        lines = _balanced(d, title, tf, int(cw * 0.56))[:3]
        y += 64
        for line in lines:
            d.text((left, y), line, font=tf, fill=rgba(theme["colors"]["ink"]))
            y += int(theme["card"]["title_size"] * 1.18)
        last = d.textlength(lines[-1], font=tf) if lines else 0
        if theme["card"].get("stamp_glyph"):
            _seal(img, (left + last + 54, y - int(theme["card"]["title_size"] * 0.62)), 46,
                  theme["card"]["stamp_glyph"], theme, fonts, angle=-3)
        if subtitle:
            sf = fonts("display_italic", int(theme["card"]["subtitle_size"]))
            for line in _wrap(d, subtitle, sf, int(cw * 0.5))[:2]:
                d.text((left, y + 30), line, font=sf, fill=rgba(theme["colors"]["ink_60"]))
                y += int(theme["card"]["subtitle_size"] * 1.5)
    else:
        tf = fonts("display", int(theme["card"]["title_size"] * 0.72))
        lines = _balanced(d, title, tf, int(cw * 0.72))[:3]
        lh = int(theme["card"]["title_size"] * 0.72 * 1.25)
        y = (ch - lh * len(lines)) // 2
        if theme.get("seal_glyph"):
            _seal(img, (cw // 2, y - 70), 54, theme["seal_glyph"], theme, fonts, angle=2)
        for line in lines:
            w = d.textlength(line, font=tf)
            d.text(((cw - w) / 2, y), line, font=tf, fill=rgba(theme["colors"]["ink"]))
            y += lh
    if theme.get("vertical_note"):
        _vertical(d, cw - 120, int(ch * 0.22), theme["vertical_note"], theme, fonts, 22)
    return img


def render_layers(theme: dict, viewport, out_dir: pathlib.Path, *, title: str, subtitle: str | None,
                  outro: str | None, label: str, captions: list[tuple[int, str]]) -> dict:
    """Write every PNG layer for one video; returns paths relative to out_dir.parent and the layout."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lay = layout(theme, viewport)
    rel = out_dir.name
    files = {"background": f"{rel}/background.png", "intro": f"{rel}/intro.png", "captions": {}}
    background(theme, lay, label).convert("RGB").save(out_dir / "background.png")
    card(theme, lay, title, subtitle, label, "intro").convert("RGB").save(out_dir / "intro.png")
    if outro:
        card(theme, lay, outro, None, label, "outro").convert("RGB").save(out_dir / "outro.png")
        files["outro"] = f"{rel}/outro.png"
    for n, text in captions:
        img = caption(theme, lay, n, text)
        x0, y0, x1, y1 = img.getbbox() or (0, 0, 2, 2)
        x0, y0 = x0 // 2 * 2, y0 // 2 * 2
        x1, y1 = min(img.width, x0 + (x1 - x0 + 1) // 2 * 2), min(img.height, y0 + (y1 - y0 + 1) // 2 * 2)
        img.crop((x0, y0, x1, y1)).save(out_dir / f"caption-{n:02d}.png")
        files["captions"][n] = {"file": f"{rel}/caption-{n:02d}.png", "x": x0, "y": y0}
    return {"files": files, "layout": lay}


# ---------- CLI ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("init")
    p.add_argument("--repo", type=pathlib.Path, required=True)
    p.add_argument("--out", type=pathlib.Path, default=pathlib.Path("theme.yaml"))
    p.add_argument("--name")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("theme")
    p = sub.add_parser("preview")
    p.add_argument("theme")
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--title", default="Tạo hoá đơn chỉ với một nút")
    p.add_argument("--subtitle", default="Hướng dẫn nhanh cho người mới")
    p.add_argument("--caption", default="Bấm Lưu để hoàn tất")
    p.add_argument("--viewport", default="1280x720")
    p = sub.add_parser("fonts")
    p.add_argument("theme")
    a = ap.parse_args()
    if a.cmd == "list":
        for name, origin in theme_names():
            print(f"{name:20} {origin}")
        return 0
    if a.cmd == "init":
        import theme_init
        if not a.repo.is_dir():
            raise SystemExit(f"error: {a.repo} is not a folder")
        if a.out.exists() and not a.force:
            raise SystemExit(f"error: {a.out} exists; pass --force to overwrite it")
        t, sources, notes = theme_init.build_theme(a.repo, a.name)
        a.out.write_text(theme_init.to_yaml(t, sources, notes, a.repo.resolve()), encoding="utf-8")
        load_theme(str(a.out.resolve()))                       # validates the merged result
        print(f"wrote {a.out}")
        for line in sources:
            print(f"  {line}")
        for line in notes:
            print(f"  note: {line}")
        print(f"next: theme.py preview {a.out} --out PREVIEW_DIR, look at frame-preview.png and intro.png")
        return 0
    theme = load_theme(a.theme, pathlib.Path.cwd())
    if a.cmd == "check":
        problems = []
        for role in ("display", "display_italic", "mono", "hanzi", "brush"):
            if role in theme["fonts"]:
                try:
                    path, index = font_file(theme, role)
                except SystemExit as e:
                    problems.append(str(e))
                    continue
        f = Fonts(theme)("display", 40)
        missing = [c for c in "ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ" if not has_glyph(f, c)]
        if missing:
            problems.append("display font lacks Vietnamese glyphs: " + "".join(missing[:12]))
        from theme_init import contrast
        c = theme["colors"]
        ratio = contrast(c["paper"][:7], c["ink"][:7])
        if ratio < 4.5:
            problems.append(f"paper/ink contrast {ratio:.1f} < 4.5")
        for p_ in problems:
            print(f"FAIL  {p_}")
        print("theme OK" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if a.cmd == "fonts":
        for role in theme["fonts"]:
            path, index = font_file(theme, role)
            print(f"{role:15} {path}" + (f" (face {index})" if index else ""))
        return 0
    vw, vh = (int(v) for v in a.viewport.split("x"))
    a.out.mkdir(parents=True, exist_ok=True)
    res = render_layers(theme, (vw, vh), a.out / "theme", title=a.title, subtitle=a.subtitle,
                        outro="Xong! Mọi thứ đã sẵn sàng.", label="Demo", captions=[(1, a.caption)])
    lay = res["layout"]
    fx, fy, fw, fh = lay["frame"]
    bg = Image.open(a.out / "theme/background.png").convert("RGBA")
    placeholder = Image.new("RGBA", (fw, fh), (255, 255, 255, 255))
    ImageDraw.Draw(placeholder).text((fw // 2 - 60, fh // 2), f"{vw}x{vh} recording", fill=(120, 120, 120, 255))
    bg.alpha_composite(placeholder, (fx, fy))
    cap = res["files"]["captions"][1]
    bg.alpha_composite(Image.open(a.out / cap["file"]).convert("RGBA"), (cap["x"], cap["y"]))
    bg.convert("RGB").save(a.out / "frame-preview.png")
    print(f"wrote {a.out / 'frame-preview.png'}, {a.out / 'theme'}/intro.png, outro.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
