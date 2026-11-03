# Gameplay / screen captions (ASS karaoke burn-in)

The `embedded-captions` skill needs a human subject to matte, so it does **not**
apply to screen/gameplay. For those we burn clean karaoke captions with ffmpeg
via `captions_burn.sh` → `ass_from_words.cjs`.

## Pipeline

```
ass_from_words.cjs  transcript.json + [startSec,endSec] -> subs.ass
captions_burn.sh    burn subs.ass into the 9:16 clip
```

`ass_from_words.cjs` reads the FLAT `words[]` array (`{text,start,end}`), keeps
words inside `[start,end]`, rebases them to clip-relative time, and emits the
**word-pop** style: words are packed into **single lines** by a character budget
(`build_clip.sh` passes ~16), and each word gets its own "active" state where it
**scales up (122%) and turns yellow** while spoken. Consecutive captions never
overlap (each state ends exactly when the next begins).

## Styles (config-driven — `config.json` + `--style`)

`ass_from_words.cjs` ships **8 styles**; pick one in `config.json` (`caption_style`)
or override per clip with `build_clip.sh --style <name>`:

| style | look |
|---|---|
| `word-pop` (default) | active word scales 122% + accent colour, single line, fixed anchor |
| `capcut` | UPPERCASE, active word in accent colour, thick outline |
| `clean` | title-case, active word accent, thin outline |
| `label` | words on a tight dark box, active word accent |
| `karaoke` | words fill to the accent colour as spoken |
| `one-word` | one giant word at a time |
| `boxed` | one word at a time in a solid accent box |
| `bicolor` | words alternate white / accent |

Colour, font, position and safe margins all come from `config.json`:
`accent_color`, `font`/`font_family`, `caption_pos_y`, `caption_max_chars`, `safe_zone`.

**Why the default is steady:** every caption is a single line (`packByChars`, budget
`caption_max_chars`) anchored at a fixed point (`{\an5\pos(540,caption_pos_y)}`), so it
never wraps and never jumps. Positions are clamped inside `safe_zone` (bottom/right
reserved for the TikTok/Reels UI).

## Hook banner (`hook_title.sh` → `hook_ass.cjs`)

"Clean" style (H2), ASS-based: **top-CENTER aligned**, **no box**, big bold white
(size 88), thick black outline + soft shadow, wrapped to ≤16 chars/line (max 2 lines).

- **Accent word:** mark the main word with `*asterisks*` in the title, e.g.
  `"Feeling awkward is *normal*"` → `normal` renders in yellow (matches the caption
  accent). Pass marked titles via `build_clip.sh --title`.
- **Timed:** the hook shows for ~4s then disappears (5th arg to `hook_title.sh`,
  clamped 2–6s; default 4). It is NOT on screen for the whole clip.

## Windows path gotcha (SOLVED — don't reintroduce)

The ffmpeg `subtitles` filter fails on drive-colon paths (`C:/...`). Do **not**
try to escape the colon. `captions_burn.sh` instead copies the `.ass` + font into
a temp dir and runs ffmpeg from **inside** it with relative paths
(`subtitles=subs.ass:fontsdir=.`). The libass line
`Error opening memory font 'subs.ass'` is a harmless quirk — as long as you see
`fontselect: (DejaVu Sans, 700, 0) -> DejaVuSans-Bold`, the font loaded.

## Font family override

`captions_burn.sh` passes family `DejaVu Sans` (env `CAPTION_FONT_FAMILY` to
override). If you swap the bundled font, set this to the new font's **family**
name (not the filename), and keep a matching `.ttf` in `assets/fonts/`.

## Tuning

- Words per line: `build_clip.sh` passes `3`; raise to 4 for denser captions.
- To reposition, change `MarginV` in the style line.
