---
name: long-video-to-shorts
version: 1.0.0
description: 'Turn ONE long video into several vertical (9:16) captioned shorts, fully local and free — a home-made Opus Clip. Use when the user wants to "faire des shorts / des clips à partir d''une longue vidéo", "découper une vidéo en clips verticaux", "reels/shorts/tiktok from a video", "extraire les meilleurs moments", or names Opus Clip / Klap / Vizard and wants it done locally. Handles two content types: face-cam (smart-crop to face + embedded-captions) and screen/gameplay (blurred-pad + burned karaoke captions). French by default. The agent selects the moments; the user approves before any render.'
metadata:
  tags: shorts, clips, reframe, captions, ffmpeg, faster-whisper, opus-clip, 9:16, tiktok, reels, french
---

# long-video-to-shorts

**One long video → N vertical captioned shorts, 100% local.** The agent transcribes,
picks the best moments, and — after the user approves the shortlist — cuts, reframes
to 9:16, and captions each one. French by default. See `DESIGN.md` for the full spec.

## When to use / not use

- **Use:** "fais-moi des shorts de cette vidéo", "découpe en clips verticaux",
  "des reels à partir de ce podcast", "extrait les meilleurs moments".
- **Not this skill:** authoring a video from scratch (→ `hyperframes`), or captioning a
  single already-short talking-head clip with cinematic VFX (→ `embedded-captions`
  directly).

## Requirements (verified on this machine — see `_fixtures/ENV_NOTES.md`)

- ffmpeg/ffprobe, node, python 3.14 + **faster-whisper** (`pip install faster-whisper`)
- `yt-dlp` for URL intake, `embedded-captions` skill for the face-cam caption branch
- bundled font `assets/fonts/DejaVuSans-Bold.ttf`

## Pipeline (6 stages)

Pick a **project dir** (e.g. `~/shorts-jobs/<name>/`). All intermediates live in
`<project>/work/`, finals in `<project>/shorts/`.

```
1. INTAKE     bash scripts/intake.sh <file-or-URL> <project>        -> work/source.mp4
2. PROBE      bash scripts/probe.sh <project>                       -> work/probe.json + work/contactsheet.png
              Read the contact sheet. Classify each time-range: facecam or screen.
3. TRANSCRIBE HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
              python scripts/transcribe.py <project>/work/source.mp4 <project>/work/transcript.json --lang fr --model small
4. PICK       Read references/highlight-selection.md. Read transcript.json.
              Write <project>/work/clips.json (schema: clips.schema.json).
              ⏸  PRESENT the shortlist table → USER APPROVES (keep/drop/adjust).
5. BUILD      For each approved clip, see "Build a clip" below.
6. DELIVER    Write <project>/shorts/manifest.md (title, range, hook, hashtag ideas).
```

## Build a clip (stage 5)

**Screen / gameplay** — fully scripted:

```bash
bash scripts/build_clip.sh <project> \
  --start 00:04:12.0 --end 00:04:58.0 --kind screen \
  --title "Le vrai piège des débutants" --hook true --caption-mode ass \
  --out <project>/shorts/01_slug.mp4
```

**Face-cam** — reframe is scripted, captions are the `embedded-captions` skill:

```bash
# 1) cut + face-crop to 9:16; prints a HANDOFF line and writes *_reframed.mp4
bash scripts/build_clip.sh <project> \
  --start 00:12:03.0 --end 00:12:41.0 --kind facecam --caption-mode embedded \
  --face-cx 0.62 --title "Personne ne t'a dit ça" \
  --out <project>/shorts/02_slug.mp4
# 2) run the embedded-captions skill on 02_slug_reframed.mp4 (pick a CATALOG identity)
# 3) add the hook banner on top of the captioned result:
bash scripts/hook_title.sh <captioned>.mp4 "Personne ne t'a dit ça" \
  <project>/shorts/02_slug.mp4 assets/fonts/DejaVuSans-Bold.ttf
```

Set `face_center_x` by vision: sample a frame, look, estimate the face's horizontal
center as a fraction (see `references/reframe.md`).

## Caption routing

| kind | caption-mode | engine |
|---|---|---|
| facecam | `embedded` (default) | `embedded-captions` skill (subject matte + animated captions) |
| facecam | `ass` (fallback: hard cuts / multi-speaker) | burned karaoke (no matte) |
| screen | `ass` | burned karaoke (`captions_burn.sh`) |

## Decision gate — refuse rather than ship garbage

Read `references/troubleshooting.md`. Refuse / skip / split when: near-silent audio
(whisper hallucinates), transcript is gibberish, source already has burned-in
captions, or a face-cam segment has hard cuts / multiple speakers. Never caption
fabricated words over silence.

## Defaults

- Language `fr` (agent may switch to `en` when a source is clearly English).
- Each short ≤ 60s (hard), ≥ ~12s, snapped to sentence boundaries.
- Volume: list every moment that holds up; the user trims. No fixed count.
- Hook banner ON by default (per-clip `--hook false` to disable). It is **centered**,
  shows for **~4s then disappears**, and colours one accent word — mark it in the title
  with `*asterisks*`, e.g. `--title "Feeling awkward is *normal*"`.
- Captions default to **word-pop** (active word scales + turns the accent colour, single
  line, fixed vertical anchor — no wrap/jump). See `references/captions-gameplay.md`.

## Customization — `config.json`

All look-and-feel lives in `config.json` at the skill root (no code edits needed):

- **`caption_style`** — one of `word-pop | capcut | clean | label | karaoke | one-word | boxed | bicolor`. Override per clip with `build_clip.sh --style <name>`.
- **`accent_color` / `hook_accent_color`** — hex (e.g. your brand colour). Drives the popped word and the hook accent word.
- **`font` / `font_family`** — point `font` at any `.ttf` in `assets/fonts/` and set `font_family` to that font's real family name (what libass matches on).
- **`hook_seconds`** — how long the hook stays (2–6s).
- **`caption_pos_y` / `hook_pos_y`** and **`safe_zone`** — keep captions/hook inside the platform-safe area (bottom/right reserved for TikTok/Reels UI). Positions are auto-clamped into the safe zone.
- **`max_download_height`** — cap for YouTube downloads (default **1080** — plenty for TikTok/Insta/Shorts; never pulls 4K). Bump to 1440 only for sharper face-cam crops.

## Worked example

Input: `interview.mp4` (45 min, face-cam, French).

1. `intake.sh interview.mp4 ~/jobs/itw` → `work/source.mp4`
2. `probe.sh ~/jobs/itw` → read contact sheet → all face-cam.
3. `transcribe.py … --lang fr` → `work/transcript.json`.
4. Read transcript → write `work/clips.json`:

```json
{
  "source": "work/source.mp4", "language": "fr",
  "clips": [
    { "id": "01", "start": "00:03:11.0", "end": "00:03:52.0", "kind": "facecam",
      "title": "L'erreur que tout le monde fait", "hook": true,
      "reason": "hook fort + punchline à 3:47", "face_center_x": 0.58,
      "caption_identity": "anchor" },
    { "id": "02", "start": "00:21:40.0", "end": "00:22:29.0", "kind": "facecam",
      "title": "Ce que personne n'ose dire", "hook": true,
      "reason": "prise de position tranchée, autonome", "face_center_x": 0.61,
      "caption_identity": "anchor" }
  ]
}
```

   Present the table → user approves.
5. For each clip: `build_clip.sh … --kind facecam --caption-mode embedded …`, then
   the embedded-captions skill, then `hook_title.sh`.
6. Write `shorts/manifest.md`.

Result: `~/jobs/itw/shorts/01_*.mp4`, `02_*.mp4` + `manifest.md`.

## Files

- `scripts/` — `intake.sh`, `probe.sh`, `transcribe.py`, `cut.sh`,
  `reframe_facecam.sh`, `reframe_gameplay.sh`, `ass_from_words.cjs`,
  `captions_burn.sh`, `hook_title.sh`, `build_clip.sh`
- `references/` — `highlight-selection.md`, `reframe.md`, `captions-gameplay.md`,
  `troubleshooting.md`
- `clips.schema.json`, `assets/fonts/DejaVuSans-Bold.ttf`, `DESIGN.md`, `PLAN.md`
