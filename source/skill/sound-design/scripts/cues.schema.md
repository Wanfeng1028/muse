# cues.json (input of `mix.py`)

One JSON file describes the whole soundtrack. Export it from the same TypeScript timeline the scenes animate
with (e.g. `npx tsx tools/export_cues.ts > out/cues.json`), so sound and picture share one clock.
The contract is the Pydantic model in `lib_audio/cues_model.py`; `uv run mix.py --print-schema` prints its JSON Schema
and `uv run mix.py out/cues.json --check` validates a file and resolves every path without mixing.

Keys may be camelCase (`sourceStart`, `gainDb`) or snake_case (`source_start`, `gain_db`). Unknown keys are an
error (a typo like `"gian"` would otherwise silently drop a level). All times are seconds of film time unless noted.

## Top level

| Key | Type | Default | Meaning |
|---|---|---|---|
| `duration` | number > 0 | required | Film length. The mix is exactly this long (match the composition). |
| `key` | string | `"C"` | Music key for pitched foley: `"F"`, `"Bb"`, `"F#m"`, `"A minor"`. `--key` overrides. |
| `music` | object | none | The music bed and its edit (below). |
| `vo` | array of clip | `[]` | Voice-over lines. Normalized together as one stem to `--vo-lufs` (default -16). |
| `product` | array of clip | `[]` | Product or diegetic sound (the app's own voice, a UI sound, a screen recording). Alias keys: `cards`, `diegetic`. Stem normalized to `--product-lufs` (default -17). Ducks the bed too unless `--no-duck-product`. |
| `sfx` | array of sfx | `[]` | Sound effects, synthesized (`kind`) or from a file (`file`). |
| `voice`, `name`, `fps`, `meta` | any | none | Free metadata; ignored by the mixer. |

## `music`

| Key | Type | Default | Meaning |
|---|---|---|---|
| `file` | string | required | Track path. |
| `segments` | array of `{sourceStart, sourceEnd}` | whole track | Source spans played back to back. Each join is a crossfade (`--splice-ms`, default 12 ms, equal-power) centred on the join: the end of one span and the start of the next both land on the join time. Put joins on bar lines. |
| `edit` | object of segments | none | Legacy form `{ "a": {...}, "b": {...} }`, joined in key order. Use `segments` or `edit`, not both. |
| `at` | number | `0` | Film time where the edited music starts. Negative trims its head (start the song at `dropInSong - dropInFilm`). |
| `gainDb` | number | `0` | Offset from `--music-lufs` (default -19, the bed level in the gaps before ducking). |
| `fadeIn` | number | `0` | Seconds of fade-in at the music start. |
| `tempo` | number | `1.0` | Pitch-preserving stretch (ffmpeg `atempo`) applied before the edit; segment times stay in ORIGINAL source seconds. Keep within 0.92 to 1.08. |
| `beats` | string | none | A `music_analyze.py` beats.json; the mixer warns when a cut is more than 30 ms from a bar line. |

## Clip (`vo`, `product`)

| Key | Type | Default | Meaning |
|---|---|---|---|
| `file` | string | required | Audio file (any format ffmpeg reads). |
| `at` | number | required | Film time of the clip start (or of its loudest sample with `align: "peak"`). |
| `gainDb` | number | `0` | Per-clip trim, applied before stem normalization. |
| `sourceStart`, `sourceEnd` | number | whole file | Play only this span of the file. |
| `align` | `"start"` or `"peak"` | `"start"` | Use `"peak"` for diegetic hits (a click, a stamp). |
| `id` | string | none | Name used in warnings (overlaps, clips cut at the film end). |

## Sfx

| Key | Type | Default | Meaning |
|---|---|---|---|
| `kind` | string | none | A `foley.py` kind: pop, blip, thump, slap, stamp, whoosh, swell, tear, tick, key, flip, pluck, chime, riser, bass-hit, shimmer, reverse-swoosh. |
| `file` | string | none | Or an SFX file. Exactly one of `kind` / `file`. |
| `at` | number | required | Film time where the TRANSIENT lands (the file's measured peak, argmax of abs). Risers and reverse swooshes peak at their end, so they end on `at`: put them on the cut. |
| `gain` | number >= 0 | `1` | Linear gain on top of `--sfx-peak-db` (default -10.5 dBFS peak). 0.3 to 0.6 for most events, 0.8 to 1 for hero hits, 0.15 to 0.3 for texture runs. |
| `gainDb` | number | `0` | Extra gain in dB. |
| `note` | number | `0` | Semitones above the key's tonic, for pitched kinds (pop, blip, pluck, chime, riser, bass-hit, shimmer). |
| `length` | number | kind default | Seconds, for whoosh, swell, riser, shimmer, reverse-swoosh. |
| `variant` | integer | `0` | Different (still deterministic) noise for repeated sounds, e.g. a run of ticks. |
| `align` | `"peak"` or `"start"` | `"peak"` | `"start"` places the file start at `at` instead. |
| `role` | `"event"` or `"texture"` | `"event"` | `"texture"` for runs meant to sit under the bed (tick runs, typing keys). Events are checked for audibility; textures are not. |

## Paths

Relative paths resolve against `--root` (default `./public`, where Remotion's `staticFile` assets live), then the
current directory, then the folder of the cues file. Absolute paths are used as is.

## Example

```json
{
  "duration": 30,
  "key": "F",
  "music": {
    "file": "audio/music/track.mp3",
    "segments": [{ "sourceStart": 0, "sourceEnd": 8.0 }, { "sourceStart": 16.0, "sourceEnd": 40.0 }],
    "beats": "../out/track.beats.json"
  },
  "vo": [
    { "id": "l01", "file": "audio/vo/l01.wav", "at": 1.0 },
    { "id": "l02", "file": "audio/vo/l02.wav", "at": 9.0 }
  ],
  "product": [{ "file": "audio/app/success.mp3", "at": 16.2 }],
  "sfx": [
    { "kind": "pop", "at": 0.5, "gain": 0.5 },
    { "kind": "pop", "at": 6.2, "gain": 0.4, "note": 7 },
    { "kind": "tick", "at": 7.0, "gain": 0.3 },
    { "kind": "tick", "at": 7.1, "gain": 0.3, "variant": 1 },
    { "kind": "riser", "at": 8.0, "gain": 0.5, "length": 1.5 },
    { "kind": "bass-hit", "at": 8.0, "gain": 0.8 },
    { "file": "sfx/shimmer.wav", "at": 28.0, "gain": 0.3 }
  ]
}
```

## What the mixer does with it

1. VO lines placed at `at`, summed, normalized to `--vo-lufs`. Product clips likewise to `--product-lufs`.
2. SFX rendered (or decoded), peak-normalized, scaled by `--sfx-peak-db` x `gain`, placed peak-on-`at`.
3. Music decoded (stretched if `tempo`), spliced, faded in, placed at `at`, normalized to `--music-lufs` + `gainDb`.
4. Ducking keyed by VO (+ product): RMS envelope (20 ms window, `--attack` 80 ms, `--release` 600 ms,
   `--duck-lookahead` 50 ms). Depth scales with the envelope from `--duck-floor-db` (-40) over `--duck-knee-db` (12).
   The bed is split at `--duck-split-hz` (3.5 kHz): below gets `--duck-db` (6), above gets `--duck-db + --duck-high-db` (9).
   SFX never key the duck.
5. Sum, tail fade (`--tail-fade` 0.9 s, power curve 1.3), look-ahead true-peak limiter so the loudnorm gain cannot
   breach the ceiling, then two-pass linear loudnorm to `--lufs` -14 / `--true-peak` -1 / `--lra` 11.
6. Writes the master (`--out`, default `out/mix.wav`), stems `vo/product/sfx/music.wav` + `mix-raw.wav` (`--stems`,
   pre-master, float), a report (stdout; `--json` adds `<out>.report.json`), and exits 2 if the master misses
   the target by more than 0.5 LU or exceeds the true-peak ceiling.
7. SFX audibility, on the stems: each cue's RMS from 30 ms before to 120 ms after `at`, against voice + product + ducked
   music over the same window. Exits 2 when the median over event cues is below `--sfx-median-db` (-12); warns for
   each event cue below `--sfx-cue-db` (-20). The report's `sfx_audibility` lists the quiet events.
