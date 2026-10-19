---
name: beat-synced-montage-builder
version: 1.0.0
description: Build beat-synced social video montages from song-analysis outputs and source footage. Use when an agent needs to assemble, plan, or revise a music-timed edit; map footage to beats/onsets/cut markers; create vertical or landscape montage timelines; integrate audio-reactive FX into shots; mix gameplay, crowd, concert, nature, menu, or other accent footage; generate timeline CSVs, contact sheets, and edit briefs; or adapt the Conteto Machino / Smash Mash workflow for another song or footage library.
---

# Beat-Synced Montage Builder

## Overview

Use this skill after a song has been analyzed with `$song-edit-analysis`, or when equivalent beat/cut-marker data already exists. The goal is not just to render clips under music; the edit should feel authored to the song, with subject changes, impacts, crowd reactions, and visual accents landing on meaningful musical markers.

## The Integrated FX Rule (non-negotiable, field-learned 2026-07)

Effects and footage must never be separate. No beat-alternating between full-frame FX segments and full-frame real clips — it reads as two videos spliced together. Every effect must anchor to (a) the subject's matte (per-frame person masks — Apple Vision `VNGenerateForegroundInstanceMaskRequest` on macOS, or equivalent), (b) scene geometry (portals in skies, corner-pinned screens, water reflections, edge-wrapped light bleed), or (c) the shot's own pixels (kaleido/mirror of the live frame, highlight smears, time-ripples of frame history). Procedural renders enter shots as in-scene elements — through skies, screens, doorways, reflections — never as cutaway segments. An untracked screen-blended element reads as a sticker. Related laws: looking good beats following parameters (restructure rather than ship a cohesion failure); one effect language per cut, escalated with song structure — per-shot one-off looks break cohesion; a rich committed grade over every shot (pure restraint reads washed-out and boring; the working formula is rich dense grade + one hard reality-bend per shot). For emotional share-lane pieces, prefer ONE continuous shot with a photometric transformation (grade ramp / light arrival / bloom driven by the song's envelopes) — seams impossible by construction.

Compositing gotcha that will burn you: screen blends must run in RGB (`format=gbrp`) — in YUV, black has chroma 128 and screening floods the frame magenta. Do opacity as an RGB `lutrgb` multiply.

## Cut Engines

Two clocks, pick per lane:

- **Onset-locked (preferred for energy/retention lanes):** `librosa.onset.onset_detect(onset_envelope=onset_strength(...), hop_length=512, backtrack=False, delta=0.02, units="time")`; merge onsets closer than 0.13s keeping the stronger; quantize `int(round((t-t0)*FPS))`; force frame 0; cut on EVERY surviving onset — hold when sparse, burst when busy; punch-in accents on top-quartile-strength onsets. Needs a deep pool (~60+ gated shots). Prefer this over density presets.
- **Marker/priority-driven (this kit's original engine):** cut on primary/secondary markers per the priority table below — still right for landscape gameplay proof cuts and moderate-density edits.
- Snap any estimated beat grid to real detected onsets when within 60ms; for style-switch/transform moments use floor not round so the change lands on the frame containing the transient.

## Build Architectures

- **Segment-render → concat → post-graph** (ffmpeg only): per-shot mp4s with cover-crop (`scale=W:H:force_original_aspect_ratio=increase:flags=lanczos,crop=W:H`, HDR sources tonemapped to bt709 first, `tpad=stop_mode=clone` to freeze-extend short clips — never shorten the music grid), concat demuxer `-c copy`, one `filter_complex` house grade (`eq=contrast=1.05:saturation=1.08`, vignette, film grain via `noise=alls=5:allf=t+u`), audio muxed last with fades.
- **Frame-pipe numpy** (per-pixel integrated FX): decode ffmpeg→rawvideo rgb24→numpy loop→encode ffmpeg stdin at CRF 17. The proven matte pipeline: render a clean graded `base.mp4` (locked cut) → generate person mattes ON the base → drive effects from a per-frame effects table → mux the original audio. Sync is perfect by construction.
- **In-shader fusion** (moderngl GLSL): footage decoded into a texture and the procedural world rendered in the same fragment shader, cuts passed in as `--cuts` so they land as in-shader warp punches. Deepest integration; see `$generated-media-sourcing` for the renderer skeleton.

## Inputs

Prefer these inputs:

- Audio file or an excerpt window.
- `*_cut_markers_30fps.csv` from `$song-edit-analysis`.
- Footage sources or a source manifest with clip paths, categories, weights, and usage notes.
- Generated-media manifest or generated asset folder from `$generated-media-sourcing`, when the user asks for generated clips/images or source footage is incomplete.
- Desired format: `9:16`, `16:9`, or both.
- Target duration, usually `30-40s` for social proof cuts.

If there is no cut-marker CSV yet, first run `$song-edit-analysis`.

## Workflow

1. Pick the musical window before rendering. Use the song analysis to choose a high-energy or narratively coherent `30-40s` span.
2. Inventory footage. Use `scripts/scan_video_sources.py` to score candidate videos for motion, glow, brightness, saturation, and promising start times.
3. If real footage is missing or the user asks for generated media, use `$generated-media-sourcing` to create or plan generated clips and still plates before final source mapping.
4. Create a source taxonomy. Common kinds: `gameplay`, `crowd`, `real_laser`, `photos_festival`, `photos_nature`, `character_select`, `menu`, `reaction`, `product`, `broll`, `generated_video`, `generated_still`.
5. Build the segment plan from adjacent cut markers. Skip micro-segments below about `0.17s` unless the track genuinely calls for stutter cuts.
6. Match footage intensity to marker priority:
   - Priority 1-2: setup, context, holds, gentle motion.
   - Priority 3: medium action, angle changes, rhythmic B-roll.
   - Priority 4: active motion, fast cuts, reaction answers.
   - Priority 5: best impacts, reveals, KOs, crowd hits, laser flashes.
7. Use accents as punctuation, not filler. Real lasers, crowd popoffs, nature flashes, menu moments, generated plates, and abstract lights should amplify phrase turns, snares, fills, and drops.
8. Render segments, concatenate, attach the clean audio excerpt, then output:
   - final video
   - timeline CSV
   - contact sheet
   - brief JSON with source mix, kind mix, dimensions, song window, and creative intent
9. Run `$edit-delivery-qa` before calling the edit finished.

## Rendering Patterns

For vertical edits that include landscape footage, keep the main action readable:

- Use a full-bleed blurred/enhanced background from the same clip.
- Overlay the crisp foreground centered with stable scale and y-position.
- Add only subtle top/bottom separators if needed.
- Avoid tight vertical crops that lose the stage, launch direction, faces, or important UI.

For full-bleed accent footage:

- Scale/crop to fill the delivery format.
- Boost contrast/saturation enough to read quickly.
- Keep laser/festival/reaction accents short: often `2-12` frames or one beat.

For landscape gameplay edits:

- Keep full-frame action visible.
- Prefer `1920x1080`, `30fps` minimum.
- Use rapid one-beat cuts in high-energy sections, but preserve source readability.

## Source Selection Rules

Prefer obvious onscreen action: impacts, collisions, spikes, reveals, fast combo strings, expressive reactions, or high-motion light moments.

Keep explosive human reaction shots for call-and-response after major impacts. Do not reject crowd-only footage automatically; reject only weak, slow, or visually flat reactions.

Use real footage for final laser/festival accents whenever possible. Generated placeholders are acceptable for exploration, but replace them before final delivery if real sources exist.

Reject or heavily deprioritize title cards, interviews, menus without a deliberate role, blank stages, flat slates, overcropped action, and low-motion setup in peak sections.

Generated clips and stills must be labeled in timeline/brief outputs with `generated_video` or `generated_still`, the prompt used, and whether the asset is `final_ok`, `replace_if_real_source_found`, or `placeholder_only`.

## Timing Heuristics

- Use primary markers for hard cuts, subject changes, impacts, reveals, and speed-ramp landings.
- Use secondary markers for continuation cuts, angle changes, small B-roll swaps, and speed-ramp starts.
- During high-energy sections, average segment length around `0.35-0.50s` works well for a dense social montage.
- For a `35s` proof cut, `70-90` segments is a strong target when the source material can support it.
- Reserve the strongest footage for the highest-energy section; do not spend all peak material during setup.

## Vertical Music-Video Pattern (2026-07)

For 9:16 music promotion (the newer lane alongside the Smash pattern): 1080×1920@30 always; loop-seam ending (photometric state returns to frame 0 over the last ~22 frames); hook text with second-line-drop kinetics (line 1 static at frame 0, line 2 appearing beat-fused within ±100ms of a real onset at 0.8–1.3s); either a Sweeps-style container (black canvas, centered footage window, monospace hook above, credit below) or full-bleed cinematic. Iterate as numbered versions on stable infrastructure — change only the effect language between versions; when the client loves a 2-second moment, make that moment the next version's whole language.

## Project Pattern From Conteto Machino

The reusable shape from the Smash Mash project:

- Song window: about `52.98s-88.17s`, a `35.19s` high-energy excerpt.
- Dense marker-driven edit: roughly one segment per beat or major marker.
- Main gameplay/action is dominant.
- Crowd, real lasers, nature, and menu/source-context moments appear as brief punctuation.
- Deliverables include final MP4s, contact sheets, timeline CSVs, and brief JSON files.

For the detailed standard, read `references/conteto-edit-standard.md`.

Optional references:

- `references/example-prompts.md`: reusable prompts for future editing tasks.
- `references/file-schemas.md`: flexible timeline CSV and brief JSON shapes.
- `references/render-recipes.md`: FFmpeg/layout recipes adapted from this project.
- `references/gui-vision.md`: product vision for a future graphical workflow.

## Script

Use `scripts/scan_video_sources.py` when you need a reusable footage inventory:

```bash
python3 scripts/scan_video_sources.py /path/to/videos --out /path/to/source_inventory
```

It writes a CSV and JSON with media duration, coarse motion/glow scores, and recommended start times. Use the output to build source pools and prevent repeatedly cutting from the same dead moments.
