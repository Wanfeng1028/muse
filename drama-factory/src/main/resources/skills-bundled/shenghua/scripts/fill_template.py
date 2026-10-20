#!/usr/bin/env python3
"""Copy the composition template into a work directory with every placeholder filled.

  fill_template.py <work-dir> <duration> [--format vertical|landscape|square|portrait]
                   [--resolution 1080p|4k|source] [--brand kit] [--template id] [--board] [--force]

Brand kit resolution order: --brand (a kit folder or its brand.json), ./brand.json,
~/.config/shenghua/brand.json, then the bundled brand.example.json. setup.sh must have
installed the kit, so its fonts and logos are on disk.

Template (theme) selection: --template picks a visual theme from templates/templates.json.
If omitted, the default theme is used. Each theme brings its CSS, the canvas it wants (dark or
light) and a motion profile; the kit brings every colour, font and logo.

--board writes board.html instead: one still showing the kit in the theme, for approval.

--relink re-installs the vendor/ and kit/ copies into an existing work dir (after the skill's
install path moved, or a copy was damaged) without touching the composition; the duration
positional is optional with --relink.

Re-running against a work folder that already has an index.html carries the authored blocks
(BEGIN/END SHOTS, BEGIN/END TIMELINE, NOCAP, CAP_STYLE) into the fresh fill, so a theme, kit,
format or duration change keeps the edit; --force replaces the composition with the stock demo.

vendor/ and kit/ are copies, not symlinks, so a project survives skill updates and being moved
to another machine. --resolution 4k writes render.json with scale 2: render-frames.sh renders
at 2x device pixels and saves at 2x (no downscale) for a 2160x3840 master. --resolution source
reads take.json's probe block (trim_take.py) and picks the scale whose canvas matches the source's
pixel count. Every fill also records encode.maxrate_kbps in render.json — the encoders' bitrate
cap, scaled to the canvas pixels.
"""

import argparse
import html as markup
import json
import math
import re
import shutil
import sys
from pathlib import Path

import brand_kit

SKILL_DIR = Path(__file__).resolve().parent.parent
FORMATS = {
    "vertical": {"width": 1080, "height": 1920, "captionTop": 1500},
    "landscape": {"width": 1920, "height": 1080, "captionTop": 880},
    # Captions sit at ~78% of the height on every canvas, as on vertical (1500/1920)
    "square": {"width": 1080, "height": 1080, "captionTop": 850},
    "portrait": {"width": 1080, "height": 1350, "captionTop": 1050},
}
FPS = 30
RESOLUTIONS = {"1080p": 1, "4k": 2}
# Grain defeats CRF alone, so the bitrate cap scales with the canvas: 16 Mbps at 1080x1920
MAXRATE_MIN, MAXRATE_MAX = 16000, 68000


def source_scale(source_w, source_h, base_w, base_h):
    """The render scale (1 or 2 — render.js's only values) whose canvas comes closest to the
    source's pixel count."""
    base, source = base_w * base_h, source_w * source_h
    return min((1, 2), key=lambda s: abs(s * s * base - source))


def maxrate_kbps(width, height, scale):
    """Bitrate cap for the canvas: 16 Mbps per 1920x1080 of output pixels, clamped."""
    pixels = width * height * scale * scale
    return min(MAXRATE_MAX, max(MAXRATE_MIN, round(16000 * pixels / (1920 * 1080))))

# The authored regions of a composition, carried over on a re-fill
BLOCKS = {
    "shots": re.compile(r"<!-- BEGIN SHOTS -->.*?<!-- END SHOTS -->", re.S),
    "timeline": re.compile(r"// BEGIN TIMELINE.*?// END TIMELINE", re.S),
}
CONSTS = ["NOCAP", "CAP_STYLE"]


def load_templates():
    manifest_path = SKILL_DIR / "templates" / "templates.json"
    if not manifest_path.is_file():
        return {"templates": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def resolve_template(template_id):
    templates = load_templates().get("templates", [])
    by_id = {t["id"]: t for t in templates}
    if template_id:
        if template_id not in by_id:
            print(f"Unknown template '{template_id}'", file=sys.stderr)
            print(f"Next: use one of {', '.join(by_id)} or omit --template for the default", file=sys.stderr)
            return None
        return by_id[template_id]
    for t in templates:
        if t.get("default"):
            return t
    if templates:
        return templates[0]
    return None


def signature(manifest):
    handle = markup.escape(manifest.get("handle", ""))
    mark = manifest["logos"].get("mark")
    if mark:
        return f'<img class="sig-mark" src="{mark}" alt="">{handle}'
    return f"<b>&lt;/&gt;</b> {handle}" if handle else ""


def carry_authored(html, existing):
    """Splice the authored blocks of an existing index.html into a fresh fill."""
    carried = []
    for name, pattern in BLOCKS.items():
        old = pattern.search(existing)
        if old and pattern.search(html):
            html = pattern.sub(lambda _: old.group(0), html, count=1)
            carried.append(name)
    for name in CONSTS:
        pattern = re.compile(rf"^const {name} = .*$", re.M)
        old = pattern.search(existing)
        if old and pattern.search(html):
            html = pattern.sub(lambda _: old.group(0), html, count=1)
            carried.append(name)
    return html, carried


def install(path, source, ignore=None):
    # A copy survives the skill's versioned install path moving on an update; a symlink did not
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path)
    shutil.copytree(source, path, ignore=ignore)


def font_fallback(css, family):
    """Slot the kit's fonts.fallback family into each brand stack ahead of the generic, so a
    glyph the display or mono family lacks renders in the family the kit chose, not the OS's."""
    def slot(match):
        stack, generic = match.group(1), match.group(2)
        return match.group(0) if family in stack else f'{stack},"{family}",{generic}'
    css = re.sub(r'(font-family:[^;{}]*?),\s*(sans-serif|serif|monospace)\b', slot, css)
    css = re.sub(r'(--display:[^;{}]*?),\s*(sans-serif|serif|monospace)\b', slot, css)
    # A --display stack with no generic (--display:"Family") ends at the declaration: append there
    return re.sub(r'(--display:\s*"[^"]+")\s*(?=[;}])',
                  lambda m: m.group(1) if family in m.group(1) else f'{m.group(1)},"{family}"', css)


def write_placeholder(path, body):
    if not path.exists():
        path.write_text(body, encoding="utf-8")


def whole_frames(duration: float) -> float:
    """The duration rounded up to a whole frame, written so render-chunks.sh's ceil(duration x 30) gives that frame count."""
    frames = math.ceil(round(duration * FPS, 6))
    seconds = math.floor(frames / FPS * 10000) / 10000
    while math.ceil(seconds * FPS) != frames:
        seconds = round(seconds - 0.0001, 4)
    return seconds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("work", type=Path)
    parser.add_argument("duration", type=float, nargs="?", default=None,
                        help="composition length in seconds; optional with --relink")
    parser.add_argument("--format", choices=FORMATS, default="vertical")
    parser.add_argument("--resolution", choices=[*RESOLUTIONS, "source"], default="1080p",
                        help="4k records render scale 2 in render.json for a 2x master; "
                             "source matches the probed recording's pixel count")
    parser.add_argument("--brand", type=Path, default=None, help="brand kit folder or its brand.json")
    parser.add_argument("--template", default=None, help="theme id from templates/templates.json")
    parser.add_argument("--board", action="store_true", help="write board.html, the kit shown in this theme")
    parser.add_argument("--force", action="store_true",
                        help="replace an existing composition with the stock demo instead of keeping it")
    parser.add_argument("--relink", action="store_true",
                        help="re-install vendor/ and kit/ into the work dir without touching the composition")
    args = parser.parse_args()

    brand = args.brand
    if args.relink and brand is None:
        # The work dir's kit copy names the kit it came from, so a relink from another cwd
        # re-installs the same brand instead of whatever the default resolution would find
        try:
            root_field = json.loads((args.work / "kit" / "kit.json").read_text(encoding="utf-8")).get("root")
            brand = Path(root_field) if root_field else None
        except (OSError, json.JSONDecodeError):
            brand = None
    try:
        kit, root = brand_kit.load(brand_kit.resolve(brand))
    except brand_kit.KitError as error:
        print(error.problem, file=sys.stderr)
        print(f"Next: {error.fix}", file=sys.stderr)
        return 1
    kit_assets = brand_kit.installed(kit, root)
    if kit_assets is None:
        print(f"Brand kit {root} is not installed, or changed since it was", file=sys.stderr)
        print(f"Next: bash {SKILL_DIR / 'scripts' / 'setup.sh'} {root}", file=sys.stderr)
        return 1
    manifest = json.loads((kit_assets / "kit.json").read_text(encoding="utf-8"))

    if args.relink:
        index = args.work / "index.html"
        if not index.is_file():
            print(f"No composition at {index} to relink into", file=sys.stderr)
            print(f"Next: run fill_template.py {args.work} <duration> for a full fill", file=sys.stderr)
            return 1
        install(args.work / "vendor", SKILL_DIR / "assets", ignore=shutil.ignore_patterns("kits", "sounds", "music"))
        install(args.work / "kit", kit_assets)
        write_placeholder(args.work / "words.js", "window.PHRASES=[];")
        write_placeholder(args.work / "speech.js", "window.SPEECH=[];")
        write_placeholder(args.work / "faces.js", "window.FACES={};")
        write_placeholder(args.work / "excerpts.js", "window.EXCERPTS={};")
        print(f"relinked {args.work}: vendor/ and kit/ re-installed (kit {manifest['name'] or root}); {index} untouched")
        print("Next: re-run the render that failed")
        return 0

    if args.duration is None or args.duration <= 0:
        problem = "Duration must be positive" if args.duration is not None else "No duration given"
        print(f"{problem}, got: {args.duration}", file=sys.stderr)
        print("Next: pass the composition length in seconds, or --relink to only re-install vendor/ and kit/", file=sys.stderr)
        return 1
    args.duration = whole_frames(args.duration)

    template = resolve_template(args.template)
    if template is None:
        print("No templates found in templates/templates.json", file=sys.stderr)
        print("Next: check that templates/ contains a templates.json manifest", file=sys.stderr)
        return 1

    colors = brand_kit.palette(kit, template.get("scheme"))
    background = manifest["background"]
    geometry = FORMATS[args.format]
    if args.resolution == "source":
        take_path = args.work / "take.json"
        try:
            probe = json.loads(take_path.read_text(encoding="utf-8")).get("probe")
        except (OSError, ValueError):
            probe = None
        if not probe or not probe.get("width") or not probe.get("height"):
            print("no probed source — run trim_take.py on the video first, or pass --resolution 1080p or 4k",
                  file=sys.stderr)
            print("Next: trim_take.py records the source's pixels in take.json's probe block", file=sys.stderr)
            return 1
        scale = source_scale(probe["width"], probe["height"], geometry["width"], geometry["height"])
    else:
        scale = RESOLUTIONS[args.resolution]
    values = {
        "width": geometry["width"],
        "height": geometry["height"],
        "captionTop": geometry["captionTop"],
        "grainWidth": geometry["width"] // 2,
        "grainHeight": geometry["height"] // 2,
        "duration": f"{args.duration:g}",
        "brand.tokens": brand_kit.css_tokens(colors),
        "brand.fonts.display": manifest["families"]["display"],
        "brand.fonts.mono": manifest["families"].get("mono", "ui-monospace"),
        "brand.signature": signature(manifest),
        "brand.background": background.get("style", "theme"),
        "brand.backgroundImage": f"url('{background['image']}')" if background.get("image") else "none",
        "brand.json": json.dumps({"name": manifest["name"], "handle": manifest["handle"],
                                  "logos": manifest["logos"], "scheme": colors["scheme"],
                                  "fonts": sorted(set(manifest["families"].values()))}),
    }

    page = "board.html" if args.board else template["file"]
    html = (SKILL_DIR / "templates" / page).read_text(encoding="utf-8")

    # Inject the theme CSS so each work dir is self-contained and the agent can switch themes
    themes_dir = SKILL_DIR / "templates" / "themes"
    theme_css = (themes_dir / "shared.css").read_text(encoding="utf-8") + "\n" + \
        (themes_dir / f"{template['id']}.css").read_text(encoding="utf-8")
    for key, value in values.items():
        theme_css = theme_css.replace("{{" + key + "}}", str(value))
    # The renderer's glyph check treats fallback-covered characters as deliberate, but that only
    # holds if the composed stacks actually reach the fallback family (they end in a generic)
    fallback_family = manifest["families"].get("fallback")
    if fallback_family:
        theme_css = font_fallback(theme_css, fallback_family)
    values["theme.css"] = theme_css
    values["theme.motion"] = json.dumps(template.get("motion", {}))

    for key, value in values.items():
        html = html.replace("{{" + key + "}}", str(value))
    if fallback_family:
        html = font_fallback(html, fallback_family)

    unfilled = sorted(set(re.findall(r"\{\{[^}]+\}\}", html)))
    if unfilled:
        print(f"{page} has placeholders nothing fills: {', '.join(unfilled)}", file=sys.stderr)
        print("Next: give each one a value in fill_template.py (AGENTS.md invariant 8)", file=sys.stderr)
        return 1

    args.work.mkdir(parents=True, exist_ok=True)
    out = args.work / page.replace(template["file"], "index.html")
    carried = []
    if not args.board and out.exists():
        if args.force:
            print(f"warning: --force replaced the composition in {out}; the authored shots are gone")
        else:
            existing = out.read_text(encoding="utf-8")
            missing = [name for name, pattern in BLOCKS.items() if not pattern.search(existing)]
            if missing:
                print(f"{out} exists but its {missing[0]} block markers are gone; refusing to guess", file=sys.stderr)
                print("Next: pass --force to replace the composition with the stock demo", file=sys.stderr)
                return 1
            html, carried = carry_authored(html, existing)
    out.write_text(html, encoding="utf-8")
    # The page loads words.js; without a placeholder a preview render fails before captions exist
    write_placeholder(args.work / "words.js", "window.PHRASES=[];")
    # speak.py writes speech.js in script mode; a recording has no speakers, so hosts stay idle
    write_placeholder(args.work / "speech.js", "window.SPEECH=[];")
    # key_greenscreen.py and find_media.py write faces.js when the vision detector ran
    write_placeholder(args.work / "faces.js", "window.FACES={};")
    # excerpt.js rewrites this with real captures; empty means docCard() stays unused, not a page error
    write_placeholder(args.work / "excerpts.js", "window.EXCERPTS={};")
    # kits/ and sounds/ stay out of vendor: each project gets only its own kit, sounds included, below
    install(args.work / "vendor", SKILL_DIR / "assets", ignore=shutil.ignore_patterns("kits", "sounds", "music"))
    # Re-copied every run, so switching kits in one work dir never renders the old brand
    install(args.work / "kit", kit_assets)
    # render-frames.sh reads scale: render at 2x device pixels, save at scale x CSS pixels
    (args.work / "render.json").write_text(json.dumps({
        "width": geometry["width"], "height": geometry["height"], "format": args.format,
        "resolution": args.resolution, "scale": scale, "duration": args.duration,
        "encode": {"maxrate_kbps": maxrate_kbps(geometry["width"], geometry["height"], scale)},
    }, indent=2) + "\n", encoding="utf-8")

    kept = " · kept the existing shots" if carried else ""
    size = f"{geometry['width'] * scale}x{geometry['height'] * scale}"
    res = f" · {args.resolution} ({size})" if args.resolution != "1080p" else ""
    print(f"{out} · {geometry['width']}x{geometry['height']}{res} · {args.duration:g}s · template {template['id']} · kit {manifest['name'] or root}{kept}")
    if args.board:
        print(f"Next: node {SKILL_DIR / 'scripts' / 'render.js'} board {out} {args.work / 'board.png'}")
    elif carried:
        print(f"Next: re-render to check the edit; carried over {', '.join(carried)}")
    else:
        print("Next: replace the demo shots between BEGIN/END SHOTS and BEGIN/END TIMELINE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
