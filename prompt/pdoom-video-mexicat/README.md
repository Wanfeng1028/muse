# I'm Upping My P(doom) — music video

A generative, code-rendered music video with word-synced karaoke typography. Every frame is a deterministic function of song time, so the live preview in the browser and the offline 1080p60 (or 4K60) export are identical.

**Watch it in 4K on YouTube:** https://www.youtube.com/watch?v=5EoO5413dBY

The YouTube upload is a slightly outdated render. For the latest and best-quality version, render it locally (see [Render the video](#render-the-video)).

The video was made with Claude (Opus 5.5) in Claude Code: the concept and treatment, the lyric alignment and audio analysis, the renderer, every scene and the renders were all worked out in conversation with Claude.

The song is not ours: see [Credits](#credits) for who wrote and made it.

The concept, style bible and plate-by-plate treatment are in [`docs/TREATMENT.md`](docs/TREATMENT.md). The engine and scene API are documented in [`docs/ENGINE.md`](docs/ENGINE.md).

## Layout

- `audio/pdoom.mp3` — the song (the Claude-Pop version, see Credits).
- `lyrics/lyrics.src.js` — the original line-level lyrics (approximate timings).
- `analysis/` — Python (uv) tools that produced the timing data: Demucs stem separation, CTC forced alignment cross-checked with Whisper, beat/downbeat/onset analysis. See `analysis/align.py` and `analysis/analyze.py`.
- `data/lyrics.json` — word-level (and some syllable-level) lyric timings.
- `data/audio.json` — tempo (132.007 BPM), beats, downbeats, sections, drum/vocal onsets and loudness envelopes.
- `app/` — the renderer: TypeScript + three.js, bun + Vite.
  - `src/engine/` — renderer core: timeline playback, post-processing (bloom, halation, grain), typography (Archivo, IBM Plex Mono, Cormorant Garamond, single-stroke plotter fonts), GPU line batches, HUD.
  - `src/scenes/` — one module per plate (`open`, `loss`, `prompt`, `hook`, `room`, `shoggoth`, `spacetime`, `ascent`, `bureau`, `leftturn`, `paperclips`, `fuse`, `stack`, `dense`, `loom`, `ilya`, `outro`) plus shared motifs.
  - `src/timeline.ts` — the edit: scene windows anchored to lyric lines and snapped to the beat grid.
  - `scripts/render.ts` — offline renderer (headless Chrome → raw frames over WebSocket → ffmpeg).
- `out/` — renders (not in the repo).

## Requirements

[bun](https://bun.sh), Google Chrome (the offline renderer drives it headless through playwright-core) and ffmpeg with libx264. The analysis tools need [uv](https://docs.astral.sh/uv/); the renderer doesn't.

## Preview

```sh
cd app
bun install
bunx vite
```

Open http://localhost:5173 and use the keys below. `?t=23` starts at a given time.

| Key | Action |
|---|---|
| space | play / pause |
| ← / → | seek ±1 s (±5 s with shift) |
| `,` / `.` | step one frame |
| `[` / `]` | previous / next scene |
| `l` | loop the current scene |
| `h` | hide the UI |

The preview renders in real time on a recent Mac. The export is not real time and is heavier.

## Render the video

```sh
cd app
bun scripts/render.ts video --samples auto --shutter 0.2 --out ../out/pdoom.mp4
```

- **Output:** 1920×1080 at 60 fps, x264 CRF 16, AAC audio.
- **Motion blur:** every frame is the average of many sub-frames spread over a short shutter (`--shutter 0.2`, a fifth of the frame time), so fast motion leaves a continuous streak instead of a few stepped copies. `--samples auto` picks the count for each 32×32 tile of the frame: 12 where the image is still, 36 for ordinary camera motion, 108 or 324 for whips, slams and fast zooms. A tile stops once more sub-frames would no longer change it by more than `--tol` levels of 255 (default 3), and later sub-frames skip it, so a fast object over a still background costs little more than the object. `--refine frame` picks one count for the whole frame instead (slower, the sampler before tiles). `--samples N` takes a fixed N (`--samples 4` makes a quick draft). How it works: "Motion blur and sampling" in [`docs/ENGINE.md`](docs/ENGINE.md).
- **Pipeline:** two headless Chromes (`--workers 2`) render chunks of 8 frames (`--chunk`) in turn and stream them to one ffmpeg, which gets them in order: the file is the same as from one renderer. One renderer already keeps the GPU busy in the heavy scenes; the second fills the gaps in the light ones. Frames that wait for the encoder are buffered in memory up to `--mem-gb` (default 1) and then on disk up to `--spool-gb` (default 20, in the system temp folder), so the renderers don't wait for x264 in the light scenes and x264 catches up in the heavy ones.
- **Other modes:** `stills`, `sheet` (contact sheets, `--cuts` for every scene boundary), `perf`, and `plates` (regenerates `public/plates/`, the stills used by the outro's rewind montage; rerun it after changing a scene).

### 4K

```sh
cd app
bun scripts/render.ts video --scale 2 --samples auto --shutter 0.2 --x264 aq-mode=3:rc-lookahead=30 --out ../out/pdoom-4k.mp4
```

- **Output:** a true 3840×2160 render (not an upscale): every layer, line and shader is rendered at the physical resolution. Scenes are laid out in 1920×1080 logical pixels, so the 4K frame looks like the 1080p one, only sharper.
- **Cost:** GPU-bound. A frame takes from about 40 ms (a still frame) to several seconds (the ray-marched rooms at 108–324 sub-frames). The whole song takes about 57 minutes on an M5 Pro. Memory peaks at about 23 GB: up to 6 GB for each headless Chrome, and ffmpeg at about 3.5 GB for most of the render (the shorter x264 lookahead above keeps it down) but up to 10 GB near the end.
- **Encoding:** the film grain is rendered per 4K pixel, which is expensive to encode: at the default CRF 16 the file runs at about 670 Mbit/s (13 GB for the song, 8× the 1080p file), `--crf 18` gives about 450 Mbit/s and `--crf 20` about 230 Mbit/s.
- `--scale 2` works with every mode. `stills` then saves full-resolution PNGs, and `perf` measures 4K frame times. In the browser preview, add `&scale=2` to the URL.

## Regenerate the timing data

The committed `data/*.json` files are all the renderer needs. Regenerating them needs the stems and intermediates, which are not in the repo:

- **Stems:** Demucs `htdemucs_ft` into `analysis/stems/htdemucs_ft/pdoom/` (`uv run python -m demucs -n htdemucs_ft -o stems ../audio/pdoom.mp3`), plus the lead vocal from a mel-band-roformer karaoke model (audio-separator) in `analysis/stems/karaoke/lead.wav`.
- **Intermediates:** `ctc_emissions.py`, `whisper_run.py` and `vocal_feats.py` write them to `analysis/work/`. The pipeline is described at the top of `analysis/align.py`.

```sh
cd analysis
uv run python align.py      # data/lyrics.json
uv run python analyze.py    # data/audio.json
```

The models download about 4 GB of weights into `analysis/.cache/`; delete that folder afterwards.

## Credits

- **Song:** "I'm Upping My P(doom)". The lyrics are by [osmarks](https://docs.osmarks.net/hypha/p%28doom%29_song_objectively_correct_interpretation), built on an opening verse and chorus by [MusicPerson](https://www.udio.com/creators/MusicPerson), with lines suggested on the EleutherAI Discord and help from Claude on the outro and final chorus. The original was generated with Udio and released in November 2024 ([YouTube](https://www.youtube.com/watch?v=uEB5E67vcPA)). This video uses the "Claude-Pop" version made with Suno, posted by [deckard (@slimer48484)](https://x.com/slimer48484/status/2097752569212756134) in September 2026.
- **Fonts:** Archivo, IBM Plex Mono and Cormorant Garamond (SIL Open Font License). Single-stroke EMS and Hershey fonts via the `hersheytext` package (OFL / public domain).

## License

The code is released under the [MIT License](LICENSE). The fonts in `app/public/fonts/` keep their own licenses (see Credits), and the song and lyrics (`audio/`, `lyrics/`, `data/lyrics.json`) are not covered by it: they belong to their authors (see Credits).
