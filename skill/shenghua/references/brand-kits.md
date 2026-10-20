# Brand kits — create, manage, choose

Load this when a kit has to be created, converted or picked: the first run with no kit, a client's
brand, several kits to choose between, or a contrast/glyph problem. A kit is a folder holding
`brand.json` (version 2) plus the fonts and logos it names; `SKILL_DIR/examples/kits/` has two
fictional ones (dark Northwind, light Lumen) to copy.

---

## Where kits live and which one a video uses

Named kits live in `~/.config/shenghua/kits/<name>/`; `init_kit.py --name <Name>` writes there
by default (`--out <folder>` puts a kit anywhere else, e.g. a client's project folder). The
single-kit `~/.config/shenghua/brand.json` keeps working as the user's own kit.

The kit a video uses, in order: the `kit` input (a path **or a kit name**), then `./brand.json`,
then the configured default, then the legacy `brand.json`, then the bundled
`SKILL_DIR/brand.example.json`. `--brand <name>` resolves a kit name as well as a path everywhere a
kit is accepted (`setup.sh`, `fill_template.py`, the board, `brand_kit.py check`).

```bash
python3 SKILL_DIR/scripts/brand_kit.py list                 # every kit in the kits folder, default marked
python3 SKILL_DIR/scripts/brand_kit.py default              # show the default
python3 SKILL_DIR/scripts/brand_kit.py default <name>       # set it (config.json → "defaultKit")
python3 SKILL_DIR/scripts/brand_kit.py resolve <name|path>  # print the kit a name or path resolves to
```

**Choosing at Step 0:** when `brand_kit.py list` shows more than one kit and the request names none,
list them (name, colours, fonts, which is the default) and ask which to use *before anything
renders*. A request that names one — "in the Acme kit", `--brand acme` — skips the question. With one
kit or none configured, proceed without asking.

## Creating a kit

**First run — no kit anywhere:** the example kit ships someone else's handle and colours, so ask
before rendering. Four questions, each with its default, answered in one message:

| Ask | Default |
|---|---|
| Name and handle shown on the video | required, no default |
| Look: `midnight-pink`, `carbon-cyan`, `ink-amber`, `violet-signal`, or their own colours | `midnight-pink` |
| Fonts: display and code — a Google font name, or a font file they have | `Archivo` / `Geist Mono` |
| Where finished videos go | `~/shenghuas` |

```bash
python3 SKILL_DIR/scripts/init_kit.py --name "Their Name" --handle @theirhandle [--preset carbon-cyan] \
  [--primary '#ff6600' --bg '#0d1117'] [--display Archivo --mono 'Geist Mono'] [--output-dir ~/shenghuas]
```

Then `brand_kit.py default <name>` makes it the default if it is the user's own kit.

**A client's brand** (a company video): build a kit from what the client supplies — never fetch a
company's logo or font from the web. Ask for the brand colours, the font files or Google names, and
the logo files (a mark, and a wordmark for dark and for light backgrounds), then:

```bash
python3 SKILL_DIR/scripts/init_kit.py --name Acme --handle acme.com --primary '#e50914' --bg '#0a0a0a' \
  --display ~/client/fonts/AcmeSans.woff2 --mono 'JetBrains Mono' --mark ~/client/logo-mark.svg \
  --wordmark-on-dark ~/client/wordmark-white.svg --wordmark-on-light ~/client/wordmark.svg \
  --background glow --out ~/clients/acme-kit
```

A light brand also passes `--bg-alt` and `--text-alt`: dark themes use them. `--background` is
`theme` (the theme's own canvas), `solid`, `glow`, `gradient` or `grid`; `--background-image <file>`
uses a picture. Only `primary`, `bg` and a display font are required; everything else is derived and
checked (panel and border shades, a readable text shade of the brand colour, a canvas for themes
designed for the other scheme).

**A version-1 brand file** (no `"version": 2`; scripts say so): convert it once. The original is
kept as `brand.v1.json`:

```bash
python3 SKILL_DIR/scripts/init_kit.py --from ~/.config/shenghua/brand.json
```

## The brand board (Step 1a)

First run, and every new kit:

```bash
python3 SKILL_DIR/scripts/fill_template.py "$work" 6 --format landscape --brand <kit> --template <template-id> --board
node SKILL_DIR/scripts/render.js board "$work"/board.html "$work"/board.png
python3 SKILL_DIR/scripts/brand_kit.py check <kit>
```

The board shows the kit inside the theme: headline and highlight, a panel, a lower third, captions, a
pill, a stamp, the end card with the logo, and the colour swatches. `render.js board` fails if a kit
font fell back to a default face. `brand_kit.py check` prints the contrast report (exit 1 below WCAG
AA; `--scheme dark|light` reports the other canvas) and warns when a logo has no variant for the
canvas. Show the board and wait for a yes; if you cannot view images, give the user `board.png` and
the contrast report. A wrong colour costs seconds here and a full render later. Pick the theme in
Step 4 first if the user hasn't — the board renders one theme. To compare themes, render one board
per theme and show them side by side.

## Sound: the `audio` block

Optional. Without it every sound is synthesized and the mix uses the default levels. With it, a kit
carries the creator's sound everywhere it is used:

```json
"audio": {
  "pack": "kenney-tech",
  "music": "music/bed.mp3",
  "levels": { "music": 0.15, "sfx": 0.4 },
  "sfx": {
    "whoosh": { "gain": 0.4 },
    "hit":    { "file": ["sounds/boom-1.wav", "sounds/boom-2.wav"] },
    "type":   { "mute": true }
  }
}
```

| Field | Default | What it does |
|---|---|---|
| `pack` | none (all synth) | a CC0 sound pack from `templates/sounds.json`; it replaces every cue it maps with recorded sounds, downloaded once on install |
| `music` | `synth` | `synth` (the theme's generated bed), `none`, a library track such as `holizna-chill-beats/old-age`, or a track in the kit; a track loops to the video's length, crossfading each repeat, with the same fades and `--drop` |
| `levels.music` / `levels.sfx` | `0.22` / `0.5` | mix levels, 0 to 2; the music still ducks under the voice |
| `sfx.<cue>.gain` | `1` | 0 to 4, on top of `levels.sfx` |
| `sfx.<cue>.file` | the pack's, else synth | one file or a list, played in turn; overrides the pack for that cue |
| `sfx.<cue>.mute` | `false` | drop that cue type entirely |

Cue types: `hit` `whoosh` `riser` `down` `type` `tick` `pop` `ding` `stamp` `error`. A recorded file
plays at the synth sound's peak level, so swapping one in keeps the mix balanced before any `gain`. A
recorded `riser` ends on its cue and a `down` stops with it; `type` and `tick` repeat the file as
each click. Files are `.wav`, `.ogg`, `.mp3`, `.flac` or `.m4a`; anything but 16-bit 48 kHz WAV is
decoded with ffmpeg.

**Packs.** `kenney-tech` (CC0, [Kenney](https://kenney.nl)): interface clicks, ticks, pops, a
confirmation ding and an error blip; a digital power-up riser and power-down; punchy impacts for
hits and stamps. It maps no whoosh, so whooshes stay synthesized; tune them with `sfx.whoosh.gain`.
`brand_kit.py install` (and `setup.sh <kit>`) downloads the archives, checks each against its sha256
and keeps only the mapped files in `assets/sounds/<pack>/`.

**Music library.** `audio.music` can name a CC0 track as `<album>/<track>`; `brand_kit.py install` downloads
the album once (checked against its sha256) and keeps only its listed tracks in `assets/music/<album>/`.

| `audio.music` | Length | Feel (measured, not listened to; audition before choosing) |
|---|---|---|
| `holizna-chill-beats/city-in-the-rearview` | 2:56 | slow (~74 bpm), dark and warm |
| `holizna-chill-beats/families` | 2:24 | ~81 bpm, brighter, the most dynamic of the six |
| `holizna-chill-beats/opinions` | 2:48 | ~81 bpm, bright |
| `holizna-chill-beats/old-age` | 3:34 | ~86 bpm, warm and even |
| `holizna-chill-beats/dream-pop` | 4:02 | slow (~72 bpm), even; the longest, so the fewest repeats |
| `holizna-chill-beats/autumn` | 2:50 | the fastest and brightest, very even |

All six are by [HoliznaCC0](https://holiznacc0.bandcamp.com), dedicated to the public domain (CC0): no
credit required, though "Music: HoliznaCC0" in a description is a kind gesture. The album is an 81 MB
download the first time a kit uses it. A track loops like a playlist: each repeat crossfades into the next
over 2 s, after its silent ends are trimmed, so a long video hears the song end and start again every few
minutes.

`brand_kit.py check` prints an `audio:` line summarising the block. The kit's sounds travel into the
project with `kit/`, `synth_audio.py` applies them, and it writes `mix.json`, which `mix-encode.sh`
and `render-chunks.sh` read for the levels and the music file. Nobody can hear the result but the
user: after changing a kit's sound, ask them to listen.

## Glyph coverage: `check --text` and `fonts.fallback`

Kit fonts that lack a character render it silently in a fallback face. Two tools catch that:

- `brand_kit.py check <kit> --text <file>` reports the characters in a file (the script, the
  transcript) the kit's fonts lack.
- `render.js check` (Step 7) flags every missing glyph in the composition, naming the characters and
  the family.

A kit can declare `"fonts": { "fallback": "<family>" }` for characters it deliberately covers
elsewhere (an emoji or CJK family): `check` then reports those characters as covered, deliberately.
Otherwise swap the characters, or give the kit a fallback family that covers them.

---

## Failure states

| Symptom | Cause | Fix |
|---|---|---|
| `… is a version-1 brand file` | a brand.json from before kits | `init_kit.py --from <that file>` |
| `No kit named 'acme' in …/kits` | the name is wrong or the kit lives elsewhere | `brand_kit.py list`, or pass the folder path |
| `Brand kit … is not installed, or changed since it was` | the kit is new or was edited after setup | `setup.sh <kit>` |
| `font … did not load` from `render.js board` | a kit font file is missing or broken, or a Google family name is misspelled | fix the kit's `fonts`, re-run `setup.sh <kit>` |
| Logo invisible on the end card | a dark logo on a dark canvas, or an SVG with no size | add `wordmark.onDark`; give the `<img>` a height (see *Logo end card*) |
| `font X lacks glyphs for: …` from `render.js check` | characters the kit's fonts don't cover | swap the characters, or set `fonts.fallback` in brand.json |
| Contrast report shows `BELOW` | a derived shade fails WCAG AA | adjust the kit's colours; check the other `--scheme` |
| `audio.sfx.<x> is not a cue type` | a misspelled cue name | use one of the ten cue types above |
| `sound pack …: … does not match its sha256` | the pack's archive changed upstream | update its entry in `templates/sounds.json`, or remove `audio.pack` |
