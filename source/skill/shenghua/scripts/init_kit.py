#!/usr/bin/env python3
"""Create a brand kit from answers collected by the agent, or convert a version-1 brand.json.

  init_kit.py --name Acme --handle acme.com [--preset midnight-pink] [--primary '#e50914' --bg '#0a0a0a'] …
  init_kit.py --from ~/.config/shenghua/brand.json

Flags, not prompts: the skill runs this after asking the user, and an interactive prompt would hang
there. Files the kit names (fonts, logos, a background image) are copied into the kit folder, so the
kit can be zipped and handed to anyone. Logos and fonts come from the client; nothing is fetched
from a company's website.
"""

import argparse
import json
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

import brand_kit

PRESETS = {
    "midnight-pink": {"bg": "#12121f", "primary": "#f0196a", "text": "#e6e6e6"},
    "carbon-cyan": {"bg": "#0d1117", "primary": "#21d4c2", "text": "#e4eaf2"},
    "ink-amber": {"bg": "#14110d", "primary": "#f5a524", "text": "#ede6da"},
    "violet-signal": {"bg": "#100e1b", "primary": "#8b5cf6", "text": "#e8e6f2"},
}


def google_axes(url, family):
    """The axis spec a v1 googleFontsUrl asked for, so a converted kit keeps e.g. Archivo's width axis."""
    for value in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("family", []):
        name, _, axes = value.partition(":")
        if name == family and axes:
            return axes
    return None


def convert(old_path, out_dir):
    old = json.loads(old_path.read_text(encoding="utf-8"))
    if old.get("version") == 2:
        raise brand_kit.KitError(f"{old_path} is already a version-2 kit", "use it as it is")
    colors, fonts = old.get("colors", {}), old.get("fonts", {})
    if "accent" not in colors or "bg" not in colors or "heading" not in fonts:
        raise brand_kit.KitError(f"{old_path} is not a version-1 brand file (no colors.accent, colors.bg or fonts.heading)",
                                 "create a new kit with init_kit.py --name … instead")
    url = fonts.get("googleFontsUrl", "")
    display = {"google": fonts["heading"]}
    if google_axes(url, fonts["heading"]):
        display["axes"] = google_axes(url, fonts["heading"])
    kit = {"version": 2, "name": old.get("name") or old.get("handle", "").lstrip("@") or "My brand",
           "handle": old.get("handle", ""),
           "colors": {"primary": colors["accent"], "bg": colors["bg"]},
           "fonts": {"display": display},
           "background": {"style": "theme"}}
    if colors.get("textBody"):
        kit["colors"]["text"] = colors["textBody"]
    if fonts.get("mono"):
        kit["fonts"]["mono"] = {"google": fonts["mono"]}
        if google_axes(url, fonts["mono"]):
            kit["fonts"]["mono"]["axes"] = google_axes(url, fonts["mono"])
    if old.get("output"):
        kit["output"] = old["output"]
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "brand.json"
    if target.resolve() == old_path.resolve():
        backup = out_dir / "brand.v1.json"
        shutil.copy2(old_path, backup)
        print(f"kept the original as {backup}")
    return kit


def bring(source, kit_dir, folder):
    """Copy a client file into the kit and return its path relative to the kit."""
    source = Path(source).expanduser()
    if not source.is_file():
        raise brand_kit.KitError(f"No such file: {source}", "pass the path to the file the client supplied")
    (kit_dir / folder).mkdir(parents=True, exist_ok=True)
    if source.resolve() != (kit_dir / folder / source.name).resolve():
        shutil.copy2(source, kit_dir / folder / source.name)
    return f"{folder}/{source.name}"


def font(spec, kit_dir):
    """A font flag is a Google family name, or a path to a font file the client supplied."""
    if Path(spec).expanduser().suffix.lower() in brand_kit.FONT_EXTENSIONS:
        stem = Path(spec).stem
        return {"file": bring(spec, kit_dir, "fonts"), "family": re.sub(r"[-_]+", " ", stem)}
    return {"google": spec}


def create(args, kit_dir):
    colors = dict(PRESETS[args.preset])
    for name in ("primary", "secondary", "bg", "bg_alt", "text", "text_alt"):
        value = getattr(args, name)
        if value:
            colors[name.replace("_alt", "Alt")] = value
    kit = {"version": 2, "name": args.name, "handle": args.handle or "", "colors": colors,
           "fonts": {"display": font(args.display, kit_dir)}, "background": {"style": args.background}}
    if args.mono:
        kit["fonts"]["mono"] = font(args.mono, kit_dir)
    logos = {}
    if args.mark:
        logos["mark"] = bring(args.mark, kit_dir, "logos")
    wordmark = {key: bring(path, kit_dir, "logos") for key, path in (("onDark", args.wordmark_on_dark), ("onLight", args.wordmark_on_light)) if path}
    if wordmark:
        logos["wordmark"] = wordmark
    if logos:
        kit["logos"] = logos
    if args.background_image:
        kit["background"] = {"style": "image", "image": bring(args.background_image, kit_dir, "background")}
    if args.output_dir:
        kit["output"] = {"dir": str(Path(args.output_dir).expanduser().resolve())}
    return kit


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a shenghua brand kit, or convert a version-1 brand.json.")
    parser.add_argument("--from", dest="source", type=Path, help="version-1 brand.json to convert")
    parser.add_argument("--name", help="brand name, shown on the end card")
    parser.add_argument("--handle", help="handle or domain shown in the corner, e.g. acme.com")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="midnight-pink", help="starting colours")
    parser.add_argument("--primary", help="main brand colour, #rrggbb")
    parser.add_argument("--secondary", help="second brand colour, #rrggbb")
    parser.add_argument("--bg", help="background colour, #rrggbb")
    parser.add_argument("--bg-alt", help="background for themes on the other canvas (light brands: a dark one)")
    parser.add_argument("--text", help="text colour on --bg")
    parser.add_argument("--text-alt", help="text colour on --bg-alt")
    parser.add_argument("--display", default="Archivo", help="display font: a Google family or a .woff2/.otf/.ttf file")
    parser.add_argument("--mono", default="Geist Mono", help="code font: a Google family or a font file")
    parser.add_argument("--mark", help="square logo mark (svg, png or webp)")
    parser.add_argument("--wordmark-on-dark", help="wordmark that reads on dark backgrounds")
    parser.add_argument("--wordmark-on-light", help="wordmark that reads on light backgrounds")
    parser.add_argument("--background", choices=sorted(brand_kit.BACKGROUND_STYLES - {"image"}), default="theme")
    parser.add_argument("--background-image", help="background image file; sets the background style to image")
    parser.add_argument("--output-dir", help="where finished videos go")
    parser.add_argument("--out", type=Path, help="kit folder to write (default: ~/.config/shenghua/kits/<name>, or the --from file's folder)")
    parser.add_argument("--force", action="store_true", help="replace an existing kit's brand.json")
    parser.add_argument("--skip-font-check", action="store_true", help="don't verify Google font names")
    args = parser.parse_args()

    if not args.source and not args.name:
        print("Pass --name for a new kit, or --from to convert a version-1 brand.json", file=sys.stderr)
        print("Next: e.g. init_kit.py --name Acme --primary '#e50914' --bg '#0a0a0a'", file=sys.stderr)
        return 1
    kit_dir = (args.out or (args.source.expanduser().parent if args.source
                            else brand_kit.KITS_DIR / brand_kit.slug(args.name))).expanduser()
    target = kit_dir / "brand.json"
    converting_in_place = bool(args.source) and target.resolve() == args.source.expanduser().resolve()
    if target.exists() and not args.force and not converting_in_place:
        print(f"{target} already exists", file=sys.stderr)
        print("Next: pass --out for a new kit folder, or --force to replace it", file=sys.stderr)
        return 1

    try:
        kit = convert(args.source.expanduser(), kit_dir) if args.source else create(args, kit_dir)
        if not args.skip_font_check:
            for role, spec in kit["fonts"].items():
                if "google" in spec:
                    brand_kit.google_css(spec["google"], spec.get("axes"))
        brand_kit.validate(kit, kit_dir)
    except brand_kit.KitError as error:
        print(error.problem, file=sys.stderr)
        print(f"Next: {error.fix}", file=sys.stderr)
        return 1

    kit_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(kit, indent=2) + "\n", encoding="utf-8")
    colors = brand_kit.palette(kit)
    print(f"{target} · {kit['name']} · {colors['primary']} on {colors['bg']} · {colors['scheme']}")
    if not args.source and not brand_kit.default_kit():
        print(f"tip: brand_kit.py default {kit_dir.name} makes this the default kit")
    print(f"Next: bash setup.sh {kit_dir}, then render the brand board for approval")
    return 0


if __name__ == "__main__":
    sys.exit(main())
