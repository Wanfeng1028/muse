"""Read a project's design (tokens, CSS, Tailwind, DESIGN.md, fonts, brand) and draft a video theme.

Not a CLI on its own: `theme.py init --repo PATH` calls scan() and write_theme().
The draft extends the neutral `clean` base and records where each value came from, so the agent
(and the user) can check it against the project's real design before the take.
"""
from __future__ import annotations

import colorsys
import json
import os
import pathlib
import re
from collections import Counter

SKIP_DIRS = {"node_modules", ".git", "dist", "build", "out", ".next", ".nuxt", "coverage", "vendor", ".venv",
             "venv", "__pycache__", ".turbo", ".cache", "target", "storybook-static", "video-out"}
TEXT_EXT = {".css", ".scss", ".sass", ".less", ".pcss", ".html", ".htm", ".vue", ".svelte", ".astro",
            ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json", ".md", ".mdx", ".yaml", ".yml"}
MAX_FILES, MAX_BYTES = 1500, 512 * 1024

ROLE_WORDS = {
    "paper": ("background", "bg", "paper", "surface", "canvas", "base", "page", "body-bg"),
    "ink": ("foreground", "fg", "text", "ink", "body", "content", "on-background"),
    "accent": ("primary", "brand", "accent", "seal", "cta", "action", "highlight"),
}
HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
CSS_VAR_RE = re.compile(r"--([\w-]+)\s*:\s*([^;}{]+)[;}]")
NAMED_HEX_RE = re.compile(r"""['"]?([A-Za-z][\w-]*)['"]?\s*[:=]\s*['"]?(#[0-9a-fA-F]{3,8})\b""")
RGB_RE = re.compile(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})")
HSL_RE = re.compile(r"(?:hsla?\()?\s*(-?\d+(?:\.\d+)?)(?:deg)?[\s,]+(\d+(?:\.\d+)?)%[\s,]+(\d+(?:\.\d+)?)%")
FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
TW_FONT_RE = re.compile(r"\b(sans|serif|mono|display|heading|body)\s*:\s*\[\s*['\"]([^'\"]+)['\"]")
NEXT_FONT_RE = re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]next/font/google['\"]")
GFONT_RE = re.compile(r"fonts\.googleapis\.com/css2?\?family=([A-Za-z0-9+]+)")
TITLE_RE = re.compile(r"<title>([^<]{1,120})</title>", re.I)
GENERIC_FONTS = {"sans-serif", "serif", "monospace", "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace",
                 "-apple-system", "blinkmacsystemfont", "segoe ui", "roboto", "helvetica neue", "arial",
                 "helvetica", "inherit", "initial", "var", "emoji", "apple color emoji", "segoe ui emoji",
                 "noto color emoji", "cursive", "fantasy", "math", "menlo", "monaco", "consolas", "courier new"}


# ---------- colour helpers ----------

def hex6(value: str) -> str | None:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) == 8:
        v = v[:6]
    return "#" + v.upper() if re.fullmatch(r"[0-9a-fA-F]{6}", v) else None


def parse_color(value: str) -> str | None:
    """#hex, rgb(), hsl(), or a bare shadcn HSL triplet ('222.2 47.4% 11.2%')."""
    value = value.strip()
    m = HEX_RE.search(value)
    if m:
        return hex6(m.group(0))
    m = RGB_RE.search(value)
    if m:
        r, g, b = (min(255, int(x)) for x in m.groups())
        return f"#{r:02X}{g:02X}{b:02X}"
    m = HSL_RE.fullmatch(value) or (HSL_RE.search(value) if value.startswith("hsl") else None)
    if m:
        h, s, l = float(m.group(1)) % 360 / 360, float(m.group(2)) / 100, float(m.group(3)) / 100
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"
    return None


def luminance(hexv: str) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def saturation(hexv: str) -> float:
    r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)[2]


def shade(hexv: str, factor: float) -> str:
    r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{max(0, min(255, round(c * factor))):02X}" for c in (r, g, b))


def canvas_from(bg: str) -> str:
    """The canvas sits a step away from the app background so the framed recording stands out."""
    return shade(bg, 0.95) if luminance(bg) > 0.4 else shade(bg, 1.45) if bg != "#000000" else "#161616"


# ---------- scanning ----------

def iter_files(repo: pathlib.Path):
    n = 0
    for root, dirs, files in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for f in sorted(files):
            p = pathlib.Path(root) / f
            if p.suffix.lower() not in TEXT_EXT or p.name.endswith((".min.css", ".min.js", ".lock")) \
                    or p.name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
                continue
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            n += 1
            if n > MAX_FILES:
                return
            yield p


def role_of(name: str) -> str | None:
    n = name.lower().replace("_", "-")
    if any(w in n for w in ("muted", "border", "ring", "shadow", "hover", "disabled", "destructive", "error",
                            "danger", "warning", "success", "chart", "sidebar", "secondary", "popover", "input")):
        return None
    for role, words in ROLE_WORDS.items():
        if any(n == w or n.endswith("-" + w) or n.startswith(w + "-") or n == "color-" + w or w in n.split("-")
               for w in words):
            return role
    return None


def scan(repo: pathlib.Path) -> dict:
    """Collect design signals. Returns {colors: {role: [(hex, source)]}, all_colors, fonts, brand, docs}."""
    repo = repo.resolve()
    named: dict[str, list[tuple[str, str]]] = {"paper": [], "ink": [], "accent": []}
    all_colors: Counter = Counter()
    fonts: dict[str, list[tuple[str, str]]] = {"display": [], "body": [], "mono": []}
    titles, docs, brand = [], [], None
    dark_scopes = re.compile(r"\.dark|\[data-theme=['\"]?dark|prefers-color-scheme:\s*dark", re.I)

    for p in iter_files(repo):
        rel = str(p.relative_to(repo))
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        low = p.name.lower()
        if low in ("design.md", "design-system.md", "brand.md", "style-guide.md", "styleguide.md") \
                or ("design" in low and p.suffix in (".md", ".mdx")):
            docs.append(rel)
        if low == "package.json":
            try:
                pkg = json.loads(text)
                brand = brand or pkg.get("productName") or pkg.get("displayName")
                if not brand and pkg.get("name") and p.parent == repo:
                    brand = pkg["name"].split("/")[-1].replace("-", " ").title()
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                for d in deps:
                    if d.startswith("@fontsource/") or d.startswith("@fontsource-variable/"):
                        fam = d.split("/", 1)[1].replace("-", " ").title()
                        fonts["mono" if "mono" in fam.lower() else "body"].append((fam, rel))
            except ValueError:
                pass
            continue
        if p.suffix.lower() in (".html", ".htm"):
            titles += [t.strip() for t in TITLE_RE.findall(text)]
        # CSS custom properties, skipping dark-mode blocks for the light palette
        light_text = text
        for m in dark_scopes.finditer(text):
            end = text.find("}", m.end())
            light_text = light_text.replace(text[m.start():end + 1], "") if end > 0 else light_text
        for name, value in CSS_VAR_RE.findall(light_text):
            c = parse_color(value)
            if not c:
                continue
            all_colors[c] += 1
            r = role_of(name)
            if r:
                named[r].append((c, f"{rel} --{name}"))
        if "tailwind" in low or low.startswith(("tokens", "theme", "colors")) or p.suffix in (".md", ".mdx"):
            for name, value in NAMED_HEX_RE.findall(text):
                c = hex6(value)
                if not c:
                    continue
                all_colors[c] += 1
                r = role_of(name)
                if r:
                    named[r].append((c, f"{rel} {name}"))
        for v in HEX_RE.findall(light_text):
            c = hex6(v)
            if c:
                all_colors[c] += 1
        for decl in FONT_FAMILY_RE.findall(text):
            fam = decl.split(",")[0].strip().strip("'\"")
            if fam and fam.lower() not in GENERIC_FONTS and not fam.startswith("var("):
                kind = "mono" if "mono" in fam.lower() or "code" in fam.lower() else "body"
                fonts[kind].append((fam, rel))
        for kind, fam in TW_FONT_RE.findall(text):
            if fam.lower() in GENERIC_FONTS:
                continue
            role = {"serif": "display", "display": "display", "heading": "display", "mono": "mono"}.get(kind, "body")
            fonts[role].append((fam, rel))
        for group in NEXT_FONT_RE.findall(text):
            for fam in (x.strip() for x in group.split(",")):
                if fam:
                    fonts["mono" if "Mono" in fam else "body"].append((fam.replace("_", " "), rel))
        for fam in GFONT_RE.findall(text):
            fonts["body"].append((fam.replace("+", " "), rel))

    if not brand and titles:
        parts = Counter(seg.strip() for t in titles for seg in re.split(r"\s[·|—–-]\s", t) if seg.strip())
        common = [s for s, n in parts.most_common() if n > 1]
        brand = common[0] if common else re.split(r"\s[·|—–-]\s", titles[0])[-1].strip()
    return {"repo": str(repo), "named": named, "all_colors": all_colors, "fonts": fonts, "brand": brand,
            "docs": docs}


# ---------- choosing a palette ----------

def pick(scan_result: dict) -> dict:
    """Decide paper / ink / accent with sources; fall back to the overall palette when names are missing."""
    named, allc = scan_result["named"], scan_result["all_colors"]
    chosen, notes = {}, []

    def best(role, key):
        cands = named[role]
        if not cands:
            return None
        counts = Counter(c for c, _ in cands)
        top = sorted(counts, key=lambda c: (-counts[c], key(c)))[0]
        return top, next(src for c, src in cands if c == top)

    chosen["paper"] = best("paper", lambda c: -luminance(c))
    chosen["ink"] = best("ink", lambda c: luminance(c))
    chosen["accent"] = best("accent", lambda c: -saturation(c))
    pool = [c for c, _ in allc.most_common(60)]
    if not chosen["paper"] and pool:
        c = max(pool, key=luminance)
        chosen["paper"] = (c, "lightest colour used in the project")
    if not chosen["ink"] and pool:
        c = min(pool, key=luminance)
        chosen["ink"] = (c, "darkest colour used in the project")
    if not chosen["accent"] and pool:
        sat = [c for c in pool if saturation(c) > 0.35 and 0.05 < luminance(c) < 0.7]
        if sat:
            c = max(sat, key=lambda c: allc[c])
            chosen["accent"] = (c, "most used saturated colour in the project")
    if chosen["paper"] and chosen["ink"] and contrast(chosen["paper"][0], chosen["ink"][0]) < 4.5:
        notes.append(f"paper {chosen['paper'][0]} vs ink {chosen['ink'][0]} contrast "
                     f"{contrast(chosen['paper'][0], chosen['ink'][0]):.1f} < 4.5: check these two")
    return {"colors": chosen, "notes": notes}


# ---------- fonts ----------

def font_dirs() -> list[pathlib.Path]:
    home = pathlib.Path.home()
    dirs = [pathlib.Path(os.environ.get("WEB_VIDEO_FONT_DIR") or home / ".cache/web-video/fonts"),
            home / "Library/Fonts", pathlib.Path("/Library/Fonts"), pathlib.Path("/System/Library/Fonts"),
            pathlib.Path("/System/Library/Fonts/Supplemental"), home / ".local/share/fonts", home / ".fonts",
            pathlib.Path("/usr/share/fonts"), pathlib.Path("/usr/local/share/fonts")]
    win = os.environ.get("WINDIR")
    if win:
        dirs.append(pathlib.Path(win) / "Fonts")
    if os.environ.get("LOCALAPPDATA"):
        dirs.append(pathlib.Path(os.environ["LOCALAPPDATA"]) / "Microsoft/Windows/Fonts")
    return [d for d in dirs if d.is_dir()]


def find_font_files(family: str, extra_dirs=(), italic=False) -> list[str]:
    """Installed .ttf/.otf/.ttc files whose name starts with the family (Inter -> Inter-Regular.ttf)."""
    key = re.sub(r"[^a-z0-9]", "", family.lower())
    hits = []
    for d in [*extra_dirs, *font_dirs()]:
        for p in d.rglob("*"):
            if p.suffix.lower() not in (".ttf", ".otf", ".ttc"):
                continue
            stem = re.sub(r"[^a-z0-9]", "", p.stem.lower())
            if not stem.startswith(key):
                continue
            rest = stem[len(key):]
            is_italic = "italic" in rest or rest.endswith("it")
            if is_italic != italic:
                continue
            rank = 0 if rest in ("", "regular", "variablefont", "vf") or rest.startswith(("wght", "opsz")) else \
                1 if rest in ("light", "book", "text") else 2
            hits.append((rank, len(str(p)), str(p)))
    return [h[2] for h in sorted(hits)][:3]


def pick_fonts(scan_result: dict, repo: pathlib.Path) -> tuple[dict, dict, list[str]]:
    """{role: family}, {role: [files]}, missing families."""
    fams = {}
    for role in ("display", "body", "mono"):
        counts = Counter(f for f, _ in scan_result["fonts"][role])
        if counts:
            fams[role] = counts.most_common(1)[0][0]
    if "display" not in fams and "body" in fams:
        fams["display"] = fams["body"]
    repo_fonts = [d for d in (repo / "public/fonts", repo / "assets/fonts", repo / "src/assets/fonts",
                              repo / "fonts", repo / "static/fonts") if d.is_dir()]
    files, missing = {}, []
    for role, fam in fams.items():
        if role == "body":
            continue
        found = find_font_files(fam, repo_fonts)
        if found:
            files[role] = found
            if role == "display":
                it = find_font_files(fam, repo_fonts, italic=True)
                if it:
                    files["display_italic"] = it
        else:
            missing.append(fam)
    return fams, files, sorted(set(missing))


# ---------- writing ----------

def build_theme(repo: pathlib.Path, name: str | None = None) -> tuple[dict, list[str], list[str]]:
    """Return (theme dict, source comments, notes)."""
    s = scan(repo)
    p = pick(s)
    fams, files, missing = pick_fonts(s, repo)
    t: dict = {"extends": "clean", "name": name or re.sub(r"[^a-z0-9-]+", "-", (s["brand"] or repo.name).lower()).strip("-")}
    sources, notes = [], list(p["notes"])
    colors = {}
    c = p["colors"]
    if c.get("paper"):
        bg = c["paper"][0]
        colors["paper"] = canvas_from(bg)
        colors["paper_deep"] = shade(colors["paper"], 0.96 if luminance(bg) > 0.4 else 1.25)
        sources.append(f"paper  {colors['paper']}  <- app background {bg} ({c['paper'][1]}), one step "
                       f"{'darker' if luminance(bg) > 0.4 else 'lighter'} so the recording stands out")
    if c.get("ink"):
        ink = c["ink"][0]
        colors.update({"ink": ink, "ink_60": ink + "9E", "ink_40": ink + "80", "ink_12": ink + "1F",
                       "ink_08": ink + "14"})
        sources.append(f"ink    {ink}  <- {c['ink'][1]}")
    if c.get("accent"):
        acc = c["accent"][0]
        colors["seal"] = acc
        colors["seal_text"] = "#FFFFFF" if contrast(acc, "#FFFFFF") >= contrast(acc, "#111111") else "#111111"
        sources.append(f"accent {acc}  <- {c['accent'][1]}")
    if colors:
        t["colors"] = colors
    if files:
        t["fonts"] = {role: lst for role, lst in files.items()}
    for role, fam in fams.items():
        sources.append(f"font {role:8} {fam}" + ("" if role in files or role == "body" else "  (not installed)"))
    if missing:
        notes.append("fonts not installed: " + ", ".join(missing) + ". The theme falls back to the base fonts; "
                     "installing them (e.g. from Google Fonts into ~/.cache/web-video/fonts) is a download: ask first")
    if s["brand"]:
        t["brand"] = str(s["brand"]).upper()
        sources.append(f"brand  {s['brand']}")
    if s["docs"]:
        sources.append("design docs: " + ", ".join(s["docs"][:5]))
        notes.append("read the design docs above and adjust colors/fonts/furniture by hand where they say more")
    if not c.get("paper") and not c.get("accent") and not fams:
        notes.append("no design signals found: the theme is the plain `clean` base. Ask the user for brand "
                     "colours or a logo before a client-facing video")
    return t, sources, notes


def to_yaml(t: dict, sources: list[str], notes: list[str], repo: pathlib.Path) -> str:
    import yaml
    head = [f"# Video theme drafted from {repo} by `theme.py init`. Check it against the project's design.",
            "# Sources:"] + [f"#   {s}" for s in sources] + (["# Notes:"] + [f"#   {n}" for n in notes] if notes else [])
    return "\n".join(head) + "\n" + yaml.safe_dump(t, allow_unicode=True, sort_keys=False)
