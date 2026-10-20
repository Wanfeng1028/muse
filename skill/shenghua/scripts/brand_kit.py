#!/usr/bin/env python3
"""Brand kits: load and validate a kit, derive the colour tokens every theme reads, check contrast
and glyph coverage, manage the user's named kits, and install a kit's fonts and logos into its own
asset folder.

  brand_kit.py check   [kit] [--scheme dark|light] [--text FILE]  validate, contrast report, glyph coverage
  brand_kit.py install [kit] [--assets DIR]          copy fonts and logos, fetch Google fonts → assets/kits/<id>/
  brand_kit.py list                                  every kit in the kits folder, with the default marked
  brand_kit.py default [name]                        show or set the default kit (config.json → defaultKit)
  brand_kit.py resolve <name-or-path>                print the kit a name or path resolves to

A kit is a folder holding brand.json (version 2) plus the files it names, or a brand.json path.
An optional "audio" block sets the music, the mix levels and each sound effect (see brand-kits.md);
a sound pack it names is downloaded from templates/sounds.json into assets/sounds/<pack>/ on install.
Named kits live in ~/.config/shenghua/kits/<name>/ (init_kit.py --name writes there); the
single-kit ~/.config/shenghua/brand.json keeps working as the user's own kit.
"""

import argparse
import bisect
import hashlib
import json
import re
import shutil
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path.home() / ".config" / "shenghua"
KITS_DIR = CONFIG_DIR / "kits"
CONFIG_FILE = CONFIG_DIR / "config.json"
LEGACY_KIT = CONFIG_DIR / "brand.json"
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
FONT_EXTENSIONS = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}
LOGO_EXTENSIONS = {".svg", ".png", ".webp"}
BACKGROUND_STYLES = {"theme", "solid", "glow", "gradient", "grid", "image"}
# Every cue type synth_audio.py renders; a kit can tune or replace each one
CUE_TYPES = ("hit", "whoosh", "riser", "down", "type", "tick", "pop", "ding", "stamp", "error")
AUDIO_EXTENSIONS = {".wav", ".ogg", ".mp3", ".flac", ".m4a"}
MIX_LEVELS = {"music": 0.22, "sfx": 0.5}
SOUNDS_JSON = SKILL_DIR / "templates" / "sounds.json"
# A desktop UA makes Google Fonts serve woff2
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
DEFAULT_SUCCESS = "#3ddc84"
DEFAULT_ERROR = "#ff4d4d"


class KitError(Exception):
    """A kit that can't be used; the message names the problem and the fix."""

    def __init__(self, problem, fix):
        super().__init__(problem)
        self.problem = problem
        self.fix = fix


def rgb(color):
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def to_hex(channels):
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in channels)


def mix(color, other, amount):
    return to_hex(a + (b - a) * amount for a, b in zip(rgb(color), rgb(other)))


def luminance(color):
    def linear(channel):
        c = channel / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (linear(c) for c in rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def is_dark(color):
    return luminance(color) < 0.18


def ink(color, bg, minimum=4.5):
    """The brand colour as text: fills keep the true colour, words get the nearest shade that reads on bg."""
    toward = "#000000" if not is_dark(bg) else "#ffffff"
    for step in range(21):
        candidate = mix(color, toward, step / 20)
        if contrast(candidate, bg) >= minimum:
            return candidate
    return toward


def readable_on(color):
    return "#0b0b0f" if contrast(color, "#0b0b0f") >= contrast(color, "#ffffff") else "#ffffff"


def slug(name):
    """The folder-safe form of a kit or brand name: 'Acme Health' → 'acme-health'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "kit"


def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def default_kit():
    """The kits-folder name config.json points at, or None."""
    return load_config().get("defaultKit")


def find_kit(name):
    """The kits-folder entry for a name: the folder, or a kit whose brand name matches."""
    wanted = slug(name)
    if KITS_DIR.is_dir():
        for folder in sorted(KITS_DIR.iterdir()):
            file = folder / "brand.json"
            if not file.is_file():
                continue
            if slug(folder.name) == wanted:
                return folder
            try:
                if slug(json.loads(file.read_text(encoding="utf-8")).get("name", "")) == wanted:
                    return folder
            except json.JSONDecodeError:
                continue
    raise KitError(f"No kit named {name!r} in {KITS_DIR}", "run init_kit.py --name …, or pick one from brand_kit.py list")


def resolve(explicit=None):
    """The kit to use: an explicit path or kit name, ./brand.json, the configured default,
    the legacy single-kit file, then the bundled example."""
    if explicit:
        candidate = Path(explicit).expanduser()
        if (candidate / "brand.json" if candidate.is_dir() else candidate).is_file():
            return candidate
        # Not a path to a kit: try it as a name in the kits folder, and fail loud either way —
        # a mistyped --brand must never render in a silently different brand
        return find_kit(str(explicit))
    candidates = [Path("brand.json")]
    named = default_kit()
    if named:
        try:
            candidates.append(find_kit(named))
        except KitError:
            raise KitError(f"config.json names defaultKit {named!r} but there is no such kit",
                           "set a new default: brand_kit.py default <name from brand_kit.py list>")
    candidates += [LEGACY_KIT, SKILL_DIR / "brand.example.json"]
    for candidate in candidates:
        if (candidate / "brand.json" if candidate.is_dir() else candidate).is_file():
            return candidate
    raise KitError("No brand kit found", "run init_kit.py, or pass --brand <kit folder>")


def installed(kit, root, assets=SKILL_DIR / "assets"):
    """The kit's asset folder, if setup.sh installed this exact version of it."""
    target = assets / "kits" / kit_id(kit, root)
    try:
        if json.loads((target / "kit.json").read_text(encoding="utf-8")).get("digest") == digest(kit, root):
            return target
    except (OSError, json.JSONDecodeError):
        pass
    return None


def load(path):
    """Return (kit dict, kit root). Raises KitError with a fix for anything unusable."""
    path = Path(path).expanduser()
    file = path / "brand.json" if path.is_dir() else path
    if not file.is_file():
        raise KitError(f"No brand kit at {path}", "pass a kit folder containing brand.json, or run init_kit.py")
    try:
        kit = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise KitError(f"{file} is not valid JSON ({error})", "fix the JSON, or run init_kit.py to recreate it")
    if kit.get("version") != 2:
        raise KitError(f"{file} is a version-1 brand file", f"convert it: python3 scripts/init_kit.py --from {file}")
    validate(kit, file.parent)
    return kit, file.parent.resolve()


def validate(kit, root):
    colors = kit.get("colors", {})
    for name in ("primary", "bg"):
        if name not in colors:
            raise KitError(f"brand.json has no colors.{name}", f"add colors.{name} as #rrggbb")
    for name, value in colors.items():
        if not HEX.match(str(value)):
            raise KitError(f"colors.{name} must look like #rrggbb, got {value!r}", "use a six-digit hex colour")
    fonts = kit.get("fonts", {})
    if "display" not in fonts:
        raise KitError("brand.json has no fonts.display", 'add {"google": "Family"} or {"file": "fonts/Display.woff2"}')
    for role, font in fonts.items():
        if "file" in font:
            font_file = root / font["file"]
            if not font_file.is_file():
                raise KitError(f"fonts.{role} file {font_file} does not exist", "put the font file in the kit, or name a Google font")
            if font_file.suffix.lower() not in FONT_EXTENSIONS:
                raise KitError(f"fonts.{role} is {font_file.suffix}, not a web font", "use .woff2, .woff, .ttf or .otf")
        elif "google" not in font:
            raise KitError(f"fonts.{role} names no file and no Google family", 'use {"file": …} or {"google": …}')
    for name, logo in flatten_logos(kit.get("logos", {})):
        logo_file = root / logo
        if not logo_file.is_file():
            raise KitError(f"logos.{name} file {logo_file} does not exist", "add the file to the kit or remove the entry")
        if logo_file.suffix.lower() not in LOGO_EXTENSIONS:
            raise KitError(f"logos.{name} is {logo_file.suffix}", "use .svg, .png or .webp")
    background = kit.get("background", {"style": "theme"})
    if background.get("style", "theme") not in BACKGROUND_STYLES:
        raise KitError(f"background.style {background.get('style')!r} is unknown", f"use one of {', '.join(sorted(BACKGROUND_STYLES))}")
    if background.get("style") == "image" and not (root / background.get("image", "")).is_file():
        raise KitError("background.style is image but background.image is missing", "add background.image pointing at a file in the kit")
    validate_audio(kit.get("audio", {}), root)


def validate_audio(audio, root):
    def audio_file(name, field):
        path = root / name
        if not path.is_file():
            raise KitError(f"{field} file {path} does not exist", "add the file to the kit or remove the entry")
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            raise KitError(f"{field} is {path.suffix}, not audio", f"use one of {', '.join(sorted(AUDIO_EXTENSIONS))}")

    unknown = set(audio) - {"pack", "music", "levels", "sfx"}
    if unknown:
        raise KitError(f"audio has unknown field(s) {', '.join(sorted(unknown))}", "use pack, music, levels and sfx")
    if "pack" in audio and audio["pack"] not in sound_packs():
        raise KitError(f"audio.pack {audio['pack']!r} is unknown", f"use one of {', '.join(sound_packs())}, or remove it")
    music = audio.get("music", "synth")
    if music not in ("synth", "none") and not library_track(music):
        audio_file(str(music), "audio.music")
    for name, level in audio.get("levels", {}).items():
        if name not in MIX_LEVELS:
            raise KitError(f"audio.levels.{name} is unknown", "use audio.levels.music and audio.levels.sfx")
        if not isinstance(level, (int, float)) or not 0 <= level <= 2:
            raise KitError(f"audio.levels.{name} must be a number from 0 to 2, got {level!r}", f"the default is {MIX_LEVELS[name]}")
    for cue, setting in audio.get("sfx", {}).items():
        if cue not in CUE_TYPES:
            raise KitError(f"audio.sfx.{cue} is not a cue type", f"use one of {', '.join(CUE_TYPES)}")
        unknown = set(setting) - {"gain", "file", "mute"}
        if unknown:
            raise KitError(f"audio.sfx.{cue} has unknown field(s) {', '.join(sorted(unknown))}", "use gain, file and mute")
        gain = setting.get("gain", 1)
        if not isinstance(gain, (int, float)) or not 0 <= gain <= 4:
            raise KitError(f"audio.sfx.{cue}.gain must be a number from 0 to 4, got {gain!r}", "1 keeps the default level")
        files = setting.get("file", [])
        for name in [files] if isinstance(files, str) else files:
            audio_file(name, f"audio.sfx.{cue}.file")


def sound_packs():
    return json.loads(SOUNDS_JSON.read_text(encoding="utf-8"))["packs"]


def music_library():
    return json.loads(SOUNDS_JSON.read_text(encoding="utf-8")).get("music", {})


def library_track(name):
    """(album, track) when audio.music names a track in the CC0 music library as album/track, else None."""
    album, _, track = str(name).partition("/")
    library = music_library()
    return (album, track) if album in library and track in library[album]["tracks"] else None


def audio_files(kit):
    """Every audio file brand.json names, relative to the kit root."""
    audio = kit.get("audio", {})
    music = audio.get("music", "synth")
    files = [music] if music not in ("synth", "none") and not library_track(music) else []
    for setting in audio.get("sfx", {}).values():
        named = setting.get("file", [])
        files += [named] if isinstance(named, str) else named
    return files


def fetch_archive(label, source, files, folder, field):
    """Download one archive listed in sounds.json, check its sha256, keep only the named files in folder."""
    if all((folder / file).is_file() for file in files):
        return
    folder.mkdir(parents=True, exist_ok=True)
    zip_path = folder.parent / f"{folder.name}.zip.part"
    download(source["url"], zip_path)
    if hashlib.sha256(zip_path.read_bytes()).hexdigest() != source["sha256"]:
        zip_path.unlink()
        raise KitError(f"{label}: {source['url']} does not match its sha256",
                       f"the download changed upstream; update templates/sounds.json or remove {field}")
    with zipfile.ZipFile(zip_path) as bundle:
        members = {Path(member).name: member for member in bundle.namelist()}
        for file in files:
            if file not in members:
                raise KitError(f"{label}: {file} is not in {source['url']}", "fix the file list in templates/sounds.json")
            (folder / file).write_bytes(bundle.read(members[file]))
    zip_path.unlink()


def fetch_pack(name, assets):
    """Download a sound pack's archives once, check them against sounds.json, keep only the cue files."""
    pack = sound_packs()[name]
    folder = assets / "sounds" / name
    wanted = {}
    for files in pack["cues"].values():
        for entry in files:
            archive, _, file = entry.partition("/")
            wanted.setdefault(archive, set()).add(file)
    for archive, files in wanted.items():
        fetch_archive(f"sound pack {name}", pack["archives"][archive], files, folder / archive, "audio.pack")
    return folder


def fetch_music(album, track, assets):
    """Download a library album once and keep its listed tracks; return the chosen track's file."""
    entry = music_library()[album]
    folder = assets / "music" / album
    fetch_archive(f"music {album}", entry["archive"], set(entry["tracks"].values()), folder, "audio.music")
    return folder / entry["tracks"][track]


def install_audio(kit, root, assets, target):
    """Copy the kit's sounds (and its pack's) into the kit assets; return the manifest's audio block.

    Paths in the block are relative to the work dir, where fill_template.py installs the kit as kit/."""
    audio = kit.get("audio", {})
    sounds = target / "sounds"
    manifest = {"music": "synth", "levels": {**MIX_LEVELS, **audio.get("levels", {})}, "sfx": {}}

    def copy(source, name):
        sounds.mkdir(exist_ok=True)
        shutil.copy2(source, sounds / name)
        return f"kit/sounds/{name}"

    music = audio.get("music", "synth")
    if music in ("synth", "none"):
        manifest["music"] = music
    elif library_track(music):
        source = fetch_music(*library_track(music), assets)
        manifest["music"] = copy(source, "music" + source.suffix.lower())
    else:
        manifest["music"] = copy(root / music, "music" + Path(music).suffix.lower())
    if "pack" in audio:
        folder = fetch_pack(audio["pack"], assets)
        for cue, files in sound_packs()[audio["pack"]]["cues"].items():
            manifest["sfx"][cue] = {"files": [copy(folder / entry, entry.replace("/", "-")) for entry in files]}
    for cue, setting in audio.get("sfx", {}).items():
        entry = manifest["sfx"].setdefault(cue, {})
        named = setting.get("file", [])
        if named:
            entry["files"] = [copy(root / name, f"{cue}-{index}{Path(name).suffix.lower()}")
                              for index, name in enumerate([named] if isinstance(named, str) else named)]
        entry["gain"] = setting.get("gain", 1)
        entry["mute"] = bool(setting.get("mute", False))
    return manifest


def flatten_logos(logos, prefix=""):
    for name, value in logos.items():
        if isinstance(value, dict):
            yield from flatten_logos(value, f"{prefix}{name}.")
        else:
            yield f"{prefix}{name}", value


def kit_id(kit, root):
    return f"{slug(kit.get('name', 'kit'))}-{hashlib.sha1(str(root).encode()).hexdigest()[:8]}"


def palette(kit, scheme=None):
    """Every colour a theme may read, derived from the few the kit names.

    scheme: "dark", "light" or None for the kit's own canvas. A light theme on a dark brand gets
    the kit's bgAlt, or a light canvas tinted with the primary, so the theme keeps its character.
    """
    colors = kit["colors"]
    primary = colors["primary"]
    bg = colors["bg"]
    switched = bool(scheme) and is_dark(bg) != (scheme == "dark")
    if switched:
        bg = colors.get("bgAlt") or (mix("#f7f7f4", primary, 0.04) if scheme == "light" else mix("#0e0f13", primary, 0.06))
    dark = is_dark(bg)
    # The kit's text colour belongs to its own canvas; on the switched canvas it would vanish
    text = colors.get("textAlt" if switched else "text") or ("#eef0f2" if dark else "#14161a")
    lift = "#ffffff" if dark else "#000000"
    secondary = colors.get("secondary") or mix(primary, "#ffffff" if dark else "#000000", 0.35)
    return {
        "scheme": "dark" if dark else "light",
        "primary": primary,
        "primary-ink": ink(primary, bg),
        "secondary": secondary,
        "bg": bg,
        "text": text,
        "muted": mix(text, bg, 0.42),
        "surface1": mix(mix(bg, lift, 0.04), primary, 0.03),
        "surface2": mix(mix(bg, lift, 0.075), primary, 0.045),
        "border": mix(mix(bg, lift, 0.13), primary, 0.08),
        "on-primary": readable_on(primary),
        "success": colors.get("success", DEFAULT_SUCCESS),
        "on-success": readable_on(colors.get("success", DEFAULT_SUCCESS)),
        "error": colors.get("error", DEFAULT_ERROR),
        "on-error": readable_on(colors.get("error", DEFAULT_ERROR)),
    }


def css_tokens(colors):
    return ";".join(f"--brand-{name}:{value}" for name, value in colors.items() if name != "scheme")


def contrast_report(colors):
    """(label, ratio, minimum) for the pairs viewers must read; minimums are WCAG AA."""
    return [
        ("body text on background", contrast(colors["text"], colors["bg"]), 4.5),
        ("body text on panels", contrast(colors["text"], colors["surface2"]), 4.5),
        ("muted text on background", contrast(colors["muted"], colors["bg"]), 3.0),
        ("caption word on its highlight", contrast(colors["on-primary"], colors["primary"]), 4.5),
        ("accent-coloured text on background", contrast(colors["primary-ink"], colors["bg"]), 4.5),
    ]


def logo_warnings(kit, colors):
    """A logo that matches the canvas vanishes; flag kits with no variant for the canvas in use."""
    logos = dict(flatten_logos(kit.get("logos", {})))
    if not logos:
        return ["no logos: the end card and corner fall back to the name and handle"]
    wanted = "wordmark.onDark" if colors["scheme"] == "dark" else "wordmark.onLight"
    if wanted not in logos:
        return [f"no logos.{wanted}: check the mark and wordmark are visible on {colors['bg']} in the board"]
    return []


def google_font_name(url):
    # Google serves two URL shapes: /s/<family>/<file>.woff2 and /l/font?kit=…; the second
    # carries ? and &, which turn into a query string inside CSS url() and 404 the file
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", url.removeprefix("https://fonts.gstatic.com/")).strip("-")
    if not name.endswith(".woff2"):
        name += ".woff2"
    return name


def google_css(family, axes=None):
    """Fetch a family's CSS: the variable axes asked for, else the full weight range, else 400/700."""
    attempts = [axes] if axes else []
    attempts += ["wght@100..900", "wght@400;700", None]
    last_error = ""
    for spec in attempts:
        query = "family=" + urllib.parse.quote(family) + (f":{spec}" if spec else "") + "&display=swap"
        request = urllib.request.Request(f"https://fonts.googleapis.com/css2?{query}", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            # 400 means the family exists but not with these axes; try a plainer request
            last_error = f"Google Fonts returned {error.code} for {family!r}"
            if error.code != 400:
                break
        except OSError as error:
            raise KitError(f"could not reach Google Fonts ({error})", "check the connection, or use local font files in the kit")
    raise KitError(last_error, "check the exact family name on fonts.google.com")


def install(kit, root, assets):
    """Copy fonts, logos and background into assets/kits/<id>/ and write fonts.css and kit.json there."""
    existing = installed(kit, root, assets)
    if existing:
        return existing
    target = assets / "kits" / kit_id(kit, root)
    fingerprint = digest(kit, root)
    if target.exists():
        shutil.rmtree(target)
    (target / "fonts").mkdir(parents=True)
    faces = []
    families = {}
    for role, font in kit["fonts"].items():
        if "file" in font:
            source = root / font["file"]
            shutil.copy2(source, target / "fonts" / source.name)
            family = font.get("family", f"Brand {role.title()}")
            weight = font.get("weight", "100 900")
            fmt = FONT_EXTENSIONS[source.suffix.lower()]
            faces.append(f"@font-face{{font-family:'{family}';src:url('fonts/{source.name}') format('{fmt}');"
                         f"font-weight:{weight};font-style:normal;font-display:block}}")
        else:
            family = font["google"]
            css = google_css(family, font.get("axes"))
            for url in sorted(set(re.findall(r"https://fonts\.gstatic\.com[^)]*", css))):
                name = google_font_name(url)
                download(url, target / "fonts" / name)
                css = css.replace(url, f"fonts/{name}")
            faces.append(css)
        families[role] = family
    (target / "fonts.css").write_text("\n".join(faces) + "\n", encoding="utf-8")
    logos = {}
    for name, logo in flatten_logos(kit.get("logos", {})):
        source = root / logo
        destination = target / "logos" / source.name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(source, destination)
        logos[name] = f"kit/logos/{source.name}"
    background = dict(kit.get("background", {"style": "theme"}))
    if background.get("style") == "image":
        source = root / background["image"]
        shutil.copy2(source, target / source.name)
        background["image"] = f"kit/{source.name}"
    manifest = {"id": target.name, "name": kit.get("name", ""), "handle": kit.get("handle", ""),
                "families": families, "logos": logos, "background": background,
                "audio": install_audio(kit, root, assets, target), "root": str(root), "digest": fingerprint}
    (target / "kit.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target


def digest(kit, root):
    """Changes whenever brand.json or any file it names changes, so an unchanged kit installs once."""
    sha = hashlib.sha1(json.dumps(kit, sort_keys=True).encode())
    files = [font["file"] for font in kit["fonts"].values() if "file" in font]
    files += [logo for _, logo in flatten_logos(kit.get("logos", {}))]
    files += [kit["background"]["image"]] if kit.get("background", {}).get("style") == "image" else []
    files += audio_files(kit)
    if "pack" in kit.get("audio", {}):
        sha.update(json.dumps(sound_packs()[kit["audio"]["pack"]], sort_keys=True).encode())
    if library_track(kit.get("audio", {}).get("music", "synth")):
        sha.update(json.dumps(music_library()[library_track(kit["audio"]["music"])[0]], sort_keys=True).encode())
    for name in sorted(files):
        sha.update((root / name).read_bytes())
    return sha.hexdigest()


def download(url, destination, attempts=5):
    destination.write_bytes(b"")
    error = None
    for _ in range(attempts):
        # A dropped connection resumes from the bytes already saved; music albums run to 80 MB
        have = destination.stat().st_size
        headers = {"User-Agent": USER_AGENT, **({"Range": f"bytes={have}-"} if have else {})}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
                if have and response.status != 206:
                    destination.write_bytes(b"")
                with destination.open("ab") as out:
                    shutil.copyfileobj(response, out, 1 << 20)
            return
        except OSError as caught:
            error = caught
    raise KitError(f"could not download {url} ({error})", "check the connection and re-run setup.sh")


# --- glyph coverage: does the kit's fonts contain every character a text uses? -----------------

def merge_ranges(ranges):
    merged = []
    for first, last in sorted(ranges):
        if merged and first <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], last)
        else:
            merged.append([first, last])
    return [(first, last) for first, last in merged]


def in_ranges(ranges, codepoint):
    i = bisect.bisect_right(ranges, (codepoint, 0x10FFFF))
    return i > 0 and ranges[i - 1][1] >= codepoint


def cmap(path, _cache={}):
    """Sorted (first, last) codepoint ranges a font covers, via fontTools when it is installed."""
    if path not in _cache:
        try:
            _cache[path] = read_cmap(path)
        except KitError:
            raise
        except OSError as error:
            raise KitError(f"cannot read font {path} ({error})", "re-run setup.sh to reinstall the kit's fonts")
    return _cache[path]


def read_cmap(path):
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return cmap_stdlib(path)
    try:
        with TTFont(str(path), lazy=True) as font:
            return merge_ranges([(cp, cp) for cp in (font.getBestCmap() or {})])
    except Exception:  # e.g. a woff2 with no brotli: try the stdlib reader before failing
        return cmap_stdlib(path)


def cmap_stdlib(path):
    data = path.read_bytes()
    if data[:4] == b"wOF2":
        raise KitError(f"cannot check {path.name}: woff2 needs fontTools to unpack",
                       "pip install fonttools brotli, or use .ttf/.otf/.woff fonts in the kit")
    if data[:4] == b"wOFF":
        tables = woff_tables(data)
    else:
        offset = struct.unpack_from(">L", data, 12)[0] if data[:4] == b"ttcf" else 0
        tables = sfnt_tables(data, offset)
    if "cmap" not in tables:
        raise KitError(f"cannot check {path.name}: the font has no cmap table",
                       "use a standard TrueType/OpenType font")
    return parse_cmap(tables["cmap"], path)


def sfnt_tables(data, offset):
    count = struct.unpack_from(">H", data, offset + 4)[0]
    tables = {}
    for i in range(count):
        tag, _, table_offset, length = struct.unpack_from(">4sLLL", data, offset + 12 + i * 16)
        tables[tag.decode("latin-1")] = data[table_offset:table_offset + length]
    return tables


def woff_tables(data):
    count = struct.unpack_from(">H", data, 12)[0]
    tables = {}
    for i in range(count):
        tag, offset, packed, original, _ = struct.unpack_from(">4sLLLL", data, 44 + i * 20)
        raw = data[offset:offset + packed]
        tables[tag.decode("latin-1")] = zlib.decompress(raw) if packed != original else raw
    return tables


def parse_cmap(table, path):
    subtables = []
    for i in range(struct.unpack_from(">H", table, 2)[0]):
        _, _, offset = struct.unpack_from(">HHL", table, 4 + i * 8)
        subtables.append((struct.unpack_from(">H", table, offset)[0], offset))
    for wanted in (12, 4):  # 12 reaches the supplementary planes; 4 is the BMP one every font has
        for fmt, offset in subtables:
            if fmt == wanted:
                return cmap12(table, offset) if fmt == 12 else cmap4(table, offset)
    raise KitError(f"cannot check {path.name}: the cmap table is not format 4 or 12",
                   "use a standard TrueType/OpenType font")


def cmap4(table, offset):
    seg_count = struct.unpack_from(">H", table, offset + 6)[0] // 2
    ends_at, starts_at = offset + 14, offset + 14 + 2 * seg_count + 2
    deltas_at, offsets_at = starts_at + 2 * seg_count, starts_at + 4 * seg_count
    ends = struct.unpack_from(f">{seg_count}H", table, ends_at)
    starts = struct.unpack_from(f">{seg_count}H", table, starts_at)
    deltas = struct.unpack_from(f">{seg_count}h", table, deltas_at)
    covered = []
    for i, (start, end) in enumerate(zip(starts, ends)):
        if start == 0xFFFF:
            continue
        # A delta segment maps (code + delta) mod 65536; the one codepoint landing on glyph 0 is a hole
        if struct.unpack_from(">H", table, offsets_at + 2 * i)[0] == 0:
            gap = (-deltas[i]) % 65536
            if start <= gap <= end:
                if start < gap:
                    covered.append((start, gap - 1))
                if gap < end:
                    covered.append((gap + 1, end))
                continue
        covered.append((start, end))
    return merge_ranges(covered)


def cmap12(table, offset):
    count = struct.unpack_from(">L", table, offset + 12)[0]
    return merge_ranges([struct.unpack_from(">LL", table, offset + 16 + i * 12)[:2] for i in range(count)])


def parse_unicode_range(spec):
    ranges = []
    for part in spec.split(","):
        part = part.strip().upper().removeprefix("U+")
        if "?" in part:
            ranges.append((int(part.replace("?", "0"), 16), int(part.replace("?", "F"), 16)))
        elif "-" in part:
            first, last = part.split("-", 1)
            ranges.append((int(first, 16), int(last, 16)))
        else:
            ranges.append((int(part, 16),) * 2)
    return merge_ranges(ranges)


def font_faces(kit, root):
    """(role, family, faces, skipped) per kit font; a face is (file, unicode ranges or None).

    Google families are read from the installed assets (their css splits coverage into per-subset
    faces with unicode-range); a kit that was never installed skips those roles with a note.
    """
    result = []
    assets = None
    assets_known = False
    for role, spec in kit["fonts"].items():
        if "file" in spec:
            family = spec.get("family", Path(spec["file"]).stem)
            result.append((role, family, [(root / spec["file"], None)], None))
            continue
        family = spec["google"]
        if not assets_known:
            assets = installed(kit, root)
            assets_known = True
        if assets is None:
            result.append((role, family, [], "not installed"))
            continue
        faces = []
        css_file = assets / "fonts.css"
        css = css_file.read_text(encoding="utf-8") if css_file.is_file() else ""
        for block in css.split("@font-face"):
            name = re.search(r"font-family:\s*'([^']+)'", block)
            source = re.search(r"url\('?([^')]+)'?\)", block)
            if not name or not source or name.group(1) != family:
                continue
            spread = re.search(r"unicode-range:\s*([^;]+)", block)
            faces.append((assets / source.group(1), parse_unicode_range(spread.group(1)) if spread else None))
        result.append((role, family, faces, None if faces else "not found in the installed fonts.css"))
    return result


def show_chars(chars, limit=16):
    shown = [f"{ch} (U+{ord(ch):04X})" for ch in chars[:limit]]
    return ", ".join(shown) + (f" … and {len(chars) - limit} more" if len(chars) > limit else "")


def glyph_report(kit, root, text_file):
    """Coverage lines for the characters a text uses, plus (uncovered, skipped) for the exit code."""
    try:
        text = Path(text_file).expanduser().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise KitError(f"cannot read --text {text_file} ({error})",
                       "pass a readable UTF-8 file, e.g. the script or captions")
    chars = sorted({ch for ch in text if ch.isprintable() and not ch.isspace()})
    lines = [f"glyph coverage: {text_file} ({len(chars)} distinct characters)"]
    missing_by_role = {}
    skipped = []
    for role, family, faces, note in font_faces(kit, root):
        if note:
            skipped.append(role)
            lines.append(f"  fonts.{role} ({family}): skipped — {note}; run setup.sh, then re-check")
            continue
        missing = [ch for ch in chars
                   if not any((spread is None or in_ranges(spread, ord(ch))) and in_ranges(cmap(file), ord(ch))
                              for file, spread in faces)]
        missing_by_role[role] = missing
        state = "all covered" if not missing else f"lacks {len(missing)}: {show_chars(missing)}"
        lines.append(f"  fonts.{role} ({family}): {state}")
    # A character is only a problem when no checked font in the kit covers it
    uncovered = [ch for ch in chars
                 if missing_by_role and all(ch in missing for missing in missing_by_role.values())]
    if "fallback" in missing_by_role:
        rescued = [ch for ch in chars
                   if ch not in missing_by_role["fallback"]
                   and any(ch in missing for role, missing in missing_by_role.items() if role != "fallback")]
        if rescued:
            lines.append(f"  covered by fonts.fallback, deliberately: {show_chars(rescued)}")
    return lines, uncovered, skipped


def font_summary(kit):
    def family(spec):
        return spec.get("google") or spec.get("family") or Path(spec.get("file", "?")).stem
    return ", ".join(f"{role}={family(spec)}" for role, spec in kit.get("fonts", {}).items())


def logo_summary(kit):
    names = [name for name, _ in flatten_logos(kit.get("logos", {}))]
    return ", ".join(names) if names else "none"


def audio_summary(audio):
    levels = {**MIX_LEVELS, **audio.get("levels", {})}
    parts = [f"pack {audio['pack']}" if "pack" in audio else "synth sounds",
             f"music {audio.get('music', 'synth')} at {levels['music']}", f"sfx at {levels['sfx']}"]
    for cue, setting in audio.get("sfx", {}).items():
        change = "muted" if setting.get("mute") else ", ".join(
            ([f"gain {setting['gain']}"] if "gain" in setting else []) + (["own file"] if setting.get("file") else []))
        if change:
            parts.append(f"{cue} {change}")
    return " · ".join(parts)


def command_list() -> int:
    entries = []
    if KITS_DIR.is_dir():
        entries += [folder for folder in sorted(KITS_DIR.iterdir()) if (folder / "brand.json").is_file()]
    if LEGACY_KIT.is_file():
        entries.append(LEGACY_KIT)
    if not entries:
        print(f"No kits in {KITS_DIR}")
        print("Next: create one with init_kit.py --name <YourBrand>")
        return 0
    named = default_kit()
    for folder in entries:
        label = folder.name if folder.parent == KITS_DIR else "brand.json (legacy single kit)"
        is_default = (folder.name == named) if named else (folder == LEGACY_KIT)
        try:
            kit, _ = load(folder)
        except KitError as error:
            print(f"{label} · broken: {error.problem} ({error.fix})")
            continue
        colors = palette(kit)
        line = (f"{label} · {kit.get('name', 'kit')} · {colors['scheme']} · {colors['primary']} on {colors['bg']}"
                f" · fonts: {font_summary(kit)} · logos: {logo_summary(kit)} · {folder}")
        print(line + ("  [default]" if is_default else ""))
    if named and not any(folder.parent == KITS_DIR and folder.name == named for folder in entries):
        print(f"warning: config.json names defaultKit {named!r} but there is no such kit", file=sys.stderr)
    print("Next: pick one with --brand <name>; change the default with brand_kit.py default <name>")
    return 0


def command_default(name) -> int:
    if name is None:
        named = default_kit()
        if named:
            print(f"default kit: {named} → {find_kit(named)}")
        else:
            print("no default kit set" + (f"; until one is, {LEGACY_KIT} is used" if LEGACY_KIT.is_file() else ""))
        print("Next: brand_kit.py default <name from brand_kit.py list>")
        return 0
    folder = find_kit(name)
    config = load_config()
    config["defaultKit"] = folder.name
    save_config(config)
    kit, _ = load(folder)
    print(f"default kit: {folder.name} ({kit.get('name', 'kit')}) · written to {CONFIG_FILE}")
    print("Next: brand_kit.py list shows it marked [default]")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate, install and manage shenghua brand kits.")
    sub = parser.add_subparsers(dest="command", required=True)
    check_parser = sub.add_parser("check", help="validate a kit and print its tokens and contrast report")
    check_parser.add_argument("kit", nargs="?", help="kit name, kit folder or brand.json (default: resolved like setup.sh)")
    check_parser.add_argument("--scheme", choices=["dark", "light"], help="the canvas a theme asks for")
    check_parser.add_argument("--text", type=Path, help="report the characters in this file the kit's fonts lack")
    install_parser = sub.add_parser("install", help="install a kit's fonts and logos into the skill's assets")
    install_parser.add_argument("kit", nargs="?", help="kit name, kit folder or brand.json (default: resolved like setup.sh)")
    install_parser.add_argument("--assets", type=Path, default=SKILL_DIR / "assets")
    sub.add_parser("list", help="list the kits in the kits folder, with the default marked")
    default_parser = sub.add_parser("default", help="show or set the default kit")
    default_parser.add_argument("name", nargs="?", help="kit to make the default (a name from brand_kit.py list)")
    resolve_parser = sub.add_parser("resolve", help="print the kit a name or path resolves to")
    resolve_parser.add_argument("kit", help="kit name, kit folder or brand.json")
    args = parser.parse_args()

    try:
        if args.command == "list":
            return command_list()
        if args.command == "default":
            return command_default(args.name)
        if args.command == "resolve":
            print(Path(resolve(args.kit)).resolve())
            print("Next: pass this as --brand to setup.sh, fill_template.py, or brand_kit.py check/install")
            return 0
        kit, root = load(resolve(args.kit))
        if args.command == "install":
            target = install(kit, root, args.assets)
            print(f"{kit.get('name', 'kit')} installed → {target}")
            print("Next: fill_template.py with --brand pointing at this kit")
            return 0
        colors = palette(kit, args.scheme)
        failing = 0
        print(f"{kit.get('name', 'kit')} · {colors['scheme']} · primary {colors['primary']} on {colors['bg']}")
        for warning in logo_warnings(kit, colors):
            print(f"  warning: {warning}")
        if kit.get("audio"):
            print(f"  audio: {audio_summary(kit['audio'])}")
        for label, ratio, minimum in contrast_report(colors):
            verdict = "ok" if ratio >= minimum else f"BELOW {minimum}:1"
            failing += ratio < minimum
            print(f"  {ratio:5.2f}:1  {label}  {verdict}")
        uncovered = []
        skipped = []
        if args.text:
            lines, uncovered, skipped = glyph_report(kit, root, args.text)
            for line in lines:
                print(line)
        if failing:
            print(f"{failing} contrast pair(s) below WCAG AA", file=sys.stderr)
            print("Next: darken or lighten colors.primary or colors.text, or set them explicitly in brand.json", file=sys.stderr)
        if uncovered:
            # With a skipped (uninstalled) font this is a warning: that font may cover them
            stream = sys.stderr if not skipped else sys.stdout
            print(f"warning: no checked font covers {show_chars(uncovered)}" if skipped else
                  f"{len(uncovered)} character(s) covered by no font in the kit: {show_chars(uncovered)}", file=stream)
            if not skipped:
                print("Next: add fonts.fallback naming a family that covers them, or change the text", file=sys.stderr)
        if failing or (uncovered and not skipped):
            return 1
        print("Next: render the brand board, then show it for approval")
        return 0
    except KitError as error:
        print(error.problem, file=sys.stderr)
        print(f"Next: {error.fix}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
