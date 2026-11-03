---
name: viral-video-edits
version: 1.0.0
description: End-to-end system for making S-tier beat-synced short-form music video edits — song analysis, viral window selection, footage sourcing with shot-level QA, hook writing, onset-locked cutting, integrated audio-reactive FX (person mattes, procedural GLSL renderers, cinematic grade), and delivery QA. Use this whenever the user asks to make a video edit, music video, reel, TikTok/Shorts/vertical video, beat-synced montage, lyric/hook video, audio-reactive visual, tunnel/portal/kaleidoscope render, or to promote a song with video content — even if they don't say "edit" (e.g. "make something for this track", "cut this to the song", "make it hit on the beat", "add effects to this clip"). Also use it when reviewing or QA-ing a finished video edit.
---

# Viral Video Edits

A complete method for producing beat-perfect, effect-integrated vertical music videos that read as S-tier videography. Built from a working production system (an independent musician's short-form promo campaign) and its accumulated client feedback. The single success metric is performance (retention + shares), and every rule below exists because its violation was field-observed to fail.

## The Laws (non-negotiable; each was learned the hard way)

1. **Integrated FX only.** Effects are fused INTO shots — anchored to the subject's matte, to scene geometry, or to the shot's own pixels. Never cut away to standalone FX segments; never alternate full-frame FX with full-frame footage; an untracked composited element reads as a sticker. Read `references/integrated-fx.md` before adding any effect.
2. **Looking good beats following parameters.** If the requested footage or structure fights quality, change the structure and say so. Many mismatched clips stitched at beat boundaries read as chaos even with a shared motif.
3. **Rich, not restrained — and not cheesy.** The working register is a RICH dense grade (true blacks, contrast S-curve, committed palette) + ONE hard reality-bend per shot on the beat grid. Pure restraint reads washed-out and boring; per-shot random one-offs read chaotic. One effect language per cut, escalated with song structure.
4. **Cut on what the song gives.** Onset-locked cutting: a cut on every real onset (merged below 0.13s keeping the stronger), holds when sparse, bursts when busy — never off-grid filler cuts, never a density preset overriding the song. For share-lane pieces, the opposite pole: one continuous shot, zero cuts, photometric transformation driven by the song's envelopes.
5. **Sync by construction.** All FX renders are generated against the exact same window (`--start/--dur`) and cut list as the edit. Snap estimated beats to real detected onsets (≤60ms). Style switches land on the frame CONTAINING the transient (floor, not round).
6. **Near-black + emissive** for all procedural imagery. Washed pastel fields fail every time; light must be carved out of darkness.
7. **Hooks pass the 5-test gate** (glance/speech/name/gap/pull, ≥4 of 5). No poetry, no "nobody:", no engagement-bait commands. See `references/hooks-and-text.md`.
8. **Shot-level footage gates.** Vibe spec before sourcing; highest-tier sources first; per-shot quality gate + human contact-sheet glance; only accepted shots enter edits. License-verify per file. See `references/footage-sourcing.md`.
9. **Automated QA never replaces watching.** Every deliverable gets a probe report AND eyes on the contact sheet and the full render at normal speed and phone scale. See `references/delivery-qa.md`.
10. **Iterate as numbered versions on stable infrastructure.** Change only the effect language between versions; when the client loves a 2-second moment, make that moment the next version's whole language.

## House format

1080×1920 @ 30fps vertical, libx264 yuv420p `+faststart`, aac 192k, CRF 17 (frame-pipe finals) / 18–19 (segment finals). Loop-seam endings. Versioned filenames under `outputs/<project>/`. Every edit ships with a contact sheet + timeline file + QA report.

## The Workflow

For anything nontrivial, write the plan down first (design doc / shot-by-shot slate — `references/design-docs.md`), and for a new campaign run a pilot: V1 proves the grammar, approval unlocks the batch.

1. **Analyze the song** → beat grid, per-beat energy/cut-priority, sections, 8-beat phrases. Then **choose the window** (15–30s) by repetition (chorus-ness), energy rise, loop seam, lyric placement, artist prior. → `references/song-analysis.md`
2. **Source & gate footage** → vibe spec, tiered sources, per-shot quality gate into a shot map, semantic contract checks when the concept requires specific content. → `references/footage-sourcing.md`
3. **Write the hook pack** → 5-test gate, second-line-drop kinetics (line 1 at frame 0, line 2 beat-fused at 0.8–1.3s ±100ms), A/B pack on the warm-funny vs quiet-specific axis. → `references/hooks-and-text.md`
4. **Build the cut** → pick the clock (beats CSV for musical bars; onset grid for transient cutting), author the shot plan in beats, assert structural anchors (drop on its bar ±0.02s). Architecture: segment→concat→post-graph (ffmpeg only) for cut-driven edits; frame-pipe numpy for per-pixel FX; in-shader fusion for the deepest integration. → `references/integrated-fx.md`
5. **Integrate FX** → person mattes (Apple Vision, quality-gated), matte/scene/pixel-anchored effects, the proven base.mp4→mattes→effects-table pipeline; procedural elements rendered on the same window and entered through scene geometry. → `references/integrated-fx.md`, `references/procedural-renderers.md`
6. **Grade & craft layer** → the exact filmic recipe (halation, ACES, split-tone, grain, vignette, letterbox), matte-centroid push-ins, escalation spine, loop seam. → `references/cinematic-grade.md`
7. **QA & deliver** → cheap-proof the first 3–5s early; probe + contact sheet + watch; cohesion check (any sticker-look or cutaway = revision); package variants with manifest + gallery; log posts into the experiment loop. → `references/delivery-qa.md`

## Choosing the lane

| Ask | Lane |
|---|---|
| Emotional/lyrical track, share-focused | One continuous shot + photometric transformation (grade ramp, light arrival, bloom) driven by song envelopes; affirmation-identity hook |
| Energy track, retention-focused | Onset-locked rapid cut from a deep gated shot pool (60+ shots), punch-in accents on top-quartile onsets |
| Artist-in-frame showcase | Cinematic craft layer + one matte-anchored signature effect per shot (style flicker, echo clones, subject↔world swap, beat-stamp multitude) |
| Abstract/visual banger | Procedural GLSL renderer (tunnel/kaleido/starburst), near-black + emissive, onsets→punch bass→bloom energy→speed; fuse with footage via in-shader weave when there's a subject |
| Hero title/brand piece | Design doc first; phased motion timeline; TDD build; comparative visual audit against references |

## References (read on demand)

- `references/song-analysis.md` — analysis formulas, viral-window scoring, onset grid, beat math, envelope followers. Read when starting any new song or debugging sync.
- `references/integrated-fx.md` — THE core craft doctrine: anchoring rules, failure modes, matte pipeline, three build architectures, compositing gotchas (screen-blend in RGB!), subject-FX vocabulary. Read before any FX work.
- `references/procedural-renderers.md` — moderngl skeleton, GLSL house library, house color finish, near-black law, portal-weave fusion, TouchDesigner lane. Read when rendering procedural visuals.
- `references/cinematic-grade.md` — the exact grade recipe, camera language, escalation spine, and the iteration case studies (dreamcatcher v1→v5, with-u v4→v7, the portal arc). Read when the edit must read as cinema, or before iterating a version.
- `references/hooks-and-text.md` — 5-test gate, container format, text kinetics, tournament method, field references, optimization loop. Read when writing any on-video text or choosing between creative approaches.
- `references/footage-sourcing.md` — vibe specs, source tiers, exact gate thresholds, licensing, semantic contracts, matte-pair contracts. Read before sourcing or admitting any footage.
- `references/delivery-qa.md` — encode settings, deliverables, QA pass, verdict format, publishing package. Read before calling anything finished.
- `references/design-docs.md` — idea sheet → slate → design doc → plan patterns. Read when planning a new production or campaign.

## Bundled scripts (runnable, not just described)

These are working implementations of the core engines — reach for them before writing new ones from scratch. All are plain CLI tools; run `--help` or read the docstring at the top of each file.

- `scripts/choose_viral_window.py` — viral window selection (song-analysis.md §2). `--audio song.wav [--transcript whisper.json] [--tiktok-start SEC] [--durations 15,22,30] --out DIR`.
- `scripts/scan_shot_quality.py` — the shot-level footage quality gate (footage-sourcing.md). `--root path/to/footage [--min-shot 1.2] [--jobs 3]` → writes `shot_map.json`. Needs `opencv-python`, `scenedetect`, `pytesseract`.
- `scripts/build_onset_cut.py` — the onset-locked v2 cut engine (song-analysis.md §3, integrated-fx.md architecture A). `--config job.json [--shot-map shot_map.json]`; see the docstring for the job schema.
- `scripts/matte/generate_local_person_matte.swift` — per-frame person matting via Apple Vision (integrated-fx.md). Compile with `swiftc generate_local_person_matte.swift -O -framework AVFoundation -framework Vision -framework CoreImage -framework ImageIO -o mattegen` (macOS 14+), then run `mattegen source.mp4 proposal_dir/`.
- `scripts/matte/media_contract.py` — the matte quality-gate implementation (`validate_matte_statistics`, `matte_statistics`, `probe_media`, `validate_sync`) — the exact thresholds from integrated-fx.md as code, not just prose.
- `scripts/procedural/` — 10 standalone moderngl/GLSL renderers (`render_color_tunnel.py`, `render_glass_bloom.py`, `render_mandala.py`, `render_fractal_neon.py`, `render_shader_pack.py`, `render_neon_cathedral.py`, `render_dream_portal.py`, `render_hyper_space_jump.py`, `render_hyper_kaleido.py`, `render_portal_weave.py`) plus `footage_fx.py` (whole-frame FX on real footage) and `subject_fx.py` (matte-anchored FX sampler) — see procedural-renderers.md. Each takes `--audio --start --dur --out [--fps 30 --w 1080 --h 1920]`; several also support `--still` for fast art-direction checks. Needs `moderngl`, `librosa`, `numpy`, `Pillow`.

Song-analysis (`script/analyze_song_for_editing.py`, the beats/sections/energy producer) isn't bundled here — use the equivalent script already bundled in the companion `song-edit-analysis` skill (same kit), or reimplement from song-analysis.md §1.

## Working in the home repo

If this skill is running inside the original production workspace it was extracted from, prefer that repo's own copies of these scripts (they may have accumulated fixes) plus its batch/sourcing infrastructure (job generators, gallery builders, the posting-experiment loop) over the bundled versions here. Elsewhere — which is the common case for this public skill — the bundled `scripts/` are the full implementations; the reference docs contain every load-bearing constant needed to extend or reimplement them.
