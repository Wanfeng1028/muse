# Themes: the video looks like the project it shows

A theme puts the recording in a frame on a designed canvas, moves captions into a band under the frame (they never cover the app), and draws the intro and outro cards. `scripts/theme.py` renders every layer as a PNG with Pillow; `edl.py` composites them. bug-report keeps its own panel layout and ignores themes.

**Rule: a client video for project X uses X's design.** Colours, typefaces and the product name come from X's repository, not from this skill. The built-in `clean` base is a neutral fallback, never a brand.

## Workflow

1. **Draft from the repo.** `theme.py init --repo <X> --out theme.yaml` scans X (skipping `node_modules`, builds, `.git`):
   - CSS custom properties (`--background`, `--foreground`, `--primary`, shadcn HSL triplets, `rgb()`, hex), ignoring `.dark` / `prefers-color-scheme: dark` blocks for the light palette;
   - Tailwind config / token / theme files (`brand: '#0F766E'`, `surface`, `ink` …) and design docs (`DESIGN.md`, `*design*.md`, style guides);
   - fonts from `font-family`, Tailwind `fontFamily`, `next/font/google`, Google Fonts links, `@fontsource/*`; installed files are looked up (system dirs, `~/.cache/web-video/fonts`, the repo's `public/fonts` …);
   - the product name from `package.json` (`productName`, `displayName`, `name`) or the shared part of `<title>`s.
   The draft `extends: clean` and lists every value's source in `# Sources:`, plus notes (missing fonts, weak contrast, design docs to read).
2. **Review the draft against the project.** Open the listed design docs or UI skill and the logo. Fix what the scanner could not know: which accent is the brand colour, furniture (`brand`, `eyebrow`, `seal_glyph`, `watermark_glyph`, `vertical_note`), title sizes. Missing fonts: offer to install them (a download: ask first) or keep the fallback and say so.
3. **Check and preview.** `theme.py check theme.yaml` (keys, colours, font files, Vietnamese glyphs, paper/ink contrast ≥ 4.5), then `theme.py preview theme.yaml --out DIR --title "…" --caption "…"` and Read `DIR/frame-preview.png` and `DIR/theme/intro.png`.
4. **Use it.** `theme: theme.yaml` in the storyboard (path relative to the storyboard). Keep `theme.yaml` with the project's video storyboards so the next video reuses it.
5. **No design signals at all** (`init` says so): use `theme: clean`, tell the user, and ask for brand colours or a logo before a client-facing video.

The canvas colour is the app background one step darker (light apps) or lighter (dark apps), so the framed recording stands out from it.

## Where themes live

| Kind | Location | Use |
|---|---|---|
| Project theme | next to the storyboard, e.g. `<project>/video/theme.yaml` | the normal case; versioned with the project |
| Personal / company theme | `~/.config/web-video/themes/NAME.yaml` (`WEB_VIDEO_THEME_DIR`) | a brand you reuse across projects; referenced by name; stays off this public repo |
| Built-in | `assets/themes/clean.yaml` | neutral fallback and the base that `init` extends |

A theme file can `extends:` a name or a path and override only some keys (deep merge, up to 5 levels). Its `name` is its own, never the parent's.

## Theme file keys

| Key | Meaning |
|---|---|
| `extends` | base theme name or path |
| `canvas` | `[width, height]` of the output, even numbers |
| `frame.width`, `frame.top`, `frame.double_rule` | recording width on the canvas (shrinks automatically for tall viewports so the caption band fits), top offset, outer rule gap (0 = single rule) |
| `colors.*` | `#RRGGBB` or `#RRGGBBAA`: `paper` (canvas), `paper_deep`, `ink` (text), `ink_60`, `ink_40`, `ink_12` (frame rule), `ink_08`, `seal` (accent: chips, dash), `seal_text` (text on the accent) |
| `grain` | film grain opacity, 0 = off |
| `fonts.display`, `display_italic`, `mono`, `hanzi`, `brush` | candidate lists; first existing file wins. Bare names are looked up in `~/.cache/web-video/fonts` (`WEB_VIDEO_FONT_DIR`). `path::Family Style` picks one face of a `.ttc`. Missing roles fall back to `display` |
| `brand`, `seal_glyph`, `watermark_glyph`, `vertical_note`, `eyebrow` | text furniture; empty hides it |
| `numerals` | `arabic` (01 02 03) or `hanzi` (一 二 三, needs `fonts.hanzi`) for caption chips |
| `caption.size`, `caption.band_gap` | caption size (long captions shrink to fit 90 % of the width) and the gap under the frame |
| `card.title_size`, `card.subtitle_size`, `card.stamp_glyph` | intro and outro typography; titles wrap into balanced lines |

A mono label containing a glyph the mono font lacks (Menlo has no Vietnamese capitals) is drawn in the display font instead, so labels never show boxes. `load_theme` validates every theme and lists all problems at once.

## Rendering

Caption layers are cropped to their own box and overlaid at their position, so a video with eight steps does not composite eight full-frame layers. Themed renders take a few seconds longer than plain ones (8 s vs 2 s for the 15 s selftest clip). `edl.py --no-theme` renders the same run with plain captions.
