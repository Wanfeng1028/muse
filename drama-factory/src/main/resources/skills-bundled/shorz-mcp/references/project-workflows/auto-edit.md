# Auto-edit workflow (project type `auto-edit`)

Default project type for **general-purpose** Shorz output: a fully edited video built from imported media plus all the cross-project panels (audio, subtitles, titles, B-roll, overlay, border, general video). The user's intent lives in the **PromptBar** plus whatever panels you tune; this is the right file when the request is "make me a polished video," not a specialized template. For specialized formats — text-to-video, avatar, podcast, advertisement, clipping, music-video — open the matching workflow file instead. Global rules and routing live in **`../../SKILL.md`**; cross-project panel contracts live in **`../panel-workflows/*.md`**.

## What it looks like

In an `auto-edit` project the user sees the full Shorz sidebar (Settings, Border, Text, Audio, B-roll, Overlay). PromptBar text drives what the auto-editor leans into; panel settings constrain the look (captions, mix, on-screen B-roll, etc.). Output aspect ratio is **`VIDEO_SIZE`** / **`switch_project_aspect_ratio`**, not PromptBar text (**SKILL.md** → *Output framing*). **Create Video** produces a montage that mixes the user's imported media (videos, images, audio, music) according to those panels and PromptBar intent. There is no project-specific `set_auto_edit_settings` tool — every knob in this workflow is a panel tool or a project setting.

**After Create Video:** to change ONE thing in the finished video ("cut 0:12-0:15", "swap the second and third clip", "remove the zoom near the start", "make the subtitles bigger") use **`edit_generated_video`** — see **`edit-generated-video.md`**. It replays the saved render plan with the change applied and everything else pinned, producing a new version; do not re-run `trigger_create_video` with a tweaked brief for that, it re-plans the whole video.

## Tool contract

This project type **delegates** to the cross-project panel tools. For each panel you change, follow the matching skill — they document supported keys, enums (copy verbatim), clamps, and persistence paths.

| Concern | MCP tool | Panel skill |
|---|---|---|
| Aspect ratio (`16:9` / `1:1` / `9:16`) | **`switch_project_aspect_ratio`** (preferred) | n/a |
| General video (auto zoom, framing, color, freeze frame, speed) | `set_general_video_settings` | `../panel-workflows/settings.md` |
| Border | `set_border_settings` | `../panel-workflows/border.md` |
| Subtitles / captions | `set_subtitle_settings` | `../panel-workflows/subtitle.md` |
| Title / headline | `set_title_settings` | `../panel-workflows/title.md` |
| Audio (mix, dubbing, reverb) | `set_audio_settings` | `../panel-workflows/audio.md` |
| B-roll (Assets/Web/GIF/AI/Emoji) | `set_broll_settings` | `../panel-workflows/broll.md` |
| Overlay | `set_overlay_settings` + `get_overlay_effects` lifecycle | `../panel-workflows/overlay.md` |
| PromptBar | `set_user_instructions` | (this file, below) |
| Create Video | `trigger_create_video` (preferred) or `generate_video` | (this file, below) |
| Status / cancel | `get_video_generation_status`, `stop_video_generation` | (this file, below) |

**Aspect ratio:** use **`switch_project_aspect_ratio`** with `projectPath` and `aspectRatio` (`16:9` \| `1:1` \| `9:16`). Optional `fps`. This is the same tool used by clipping and matches the **Settings** panel aspect control. Do not bake aspect ratio into `set_general_video_settings` unless the user explicitly asks for that path.

**Project-level reads:**

- `read_project_settings` — full `settings.json` for the project; use as the persistence oracle after any `set_*` call.
- `UI_SETTINGS.user_input_instructions` — PromptBar text on disk (after `set_user_instructions`).
- `VIDEO_SIZE` (`video_width`, `video_height`, `video_fps` — all stringified) — written by `switch_project_aspect_ratio`.

**Asset verification:** main timeline media lives under **`ASSET_PATHS.main_video_asset_paths`** when the montage expects imported clips (**SKILL.md** → *Main VIDEO import* — this template **does** expose main VIDEO import). B-roll, sound FX, and music lanes use **`broll_video_asset_paths`**, **`audio_fx_asset_paths`**, **`music_asset_paths`** — clear via **`update_project_settings`**, not `delete_asset`, unless the user wants files erased from disk (**`../panel-workflows/your-library-assets.md`**). The library list tools (`get_video_assets`, `get_image_assets`, `get_audio_assets`, …) describe **My Assets** tabs, not the project’s main/timeline lane — see **SKILL.md** → *Asset verification* and **`../panel-workflows/README.md`** → *Library and cross-cutting MCP tools*.

## PromptBar content

Follow **SKILL.md** → *Output framing*. The brief is creative intent only: pacing, mood, cuts, music, text overlays, what to keep/remove. Never put `9:16`, `16:9`, `1080×1920`, `video_width`/`video_height`, or export fps in `set_user_instructions`. Use **`switch_project_aspect_ratio`** when the user wants a different output shape.

## What the PromptBar can direct (plannable editing vocabulary)

Auto-edit has two AI paths, chosen by how many main assets sit in `ASSET_PATHS.main_video_asset_paths`. Everything below is **prompt-driven — no panel toggle exists for it**, which makes auto-edit the exception to the usual "panels enable, PromptBar steers" rule. Use this section to (a) tell users what is possible and (b) compose PromptBar briefs that reliably trigger each capability.

### Multi-asset montage (2+ main assets): per-clip controls

The edit planner builds a timeline of segments and can attach the controls below to individual segments — but **only when the user's instructions ask for them**. Absent an explicit ask, every one of these is OFF (hard cuts, no motion, clips play as-is). Phrase briefs as imperative editing instructions ("slow the knockdown to half speed", "dissolve between the clips"), not vibes ("make it feel smooth" will NOT add transitions).

**Transitions between clips** — ~0.5s crossfade-style overlap, timing-compensated so cuts stay where planned. The planner picks per cut; it keeps one consistent style unless the user asks for variety, and maps near-miss names ("star wipe") to the closest real one. Valid names:

`fade, fadeblack, fadewhite, fadegrays, wipeleft, wiperight, wipeup, wipedown, slideleft, slideright, slideup, slidedown, smoothleft, smoothright, smoothup, smoothdown, revealleft, revealright, revealup, revealdown, circleopen, circleclose, circlecrop, radial, pixelize, zoomin, distance, hblur` — plus `dissolve`, `squeezeh`, `hrslice`, `hlslice` accepted by the renderer. Common words normalize ("dissolve", "wipe left", "fade to black" → `fadeblack`).

**Per-clip camera motion** (Ken Burns-style; most valuable on still images — video already moves):

| Motion | Behaviour |
|---|---|
| `Zoom In Center` / `Zoom In Left` / `Zoom In Right` / `Zoom In Top` / `Zoom In Bottom` | slow push toward center or an edge |
| `Zoom Out Center` | slow pull-back reveal |
| `Pan Left` / `Pan Right` / `Pan Up` / `Pan Down` | frame travels across the asset |
| `Breathing Zoom` | gentle continuous in/out pulse — subtle, calm, "expensive" look |
| `Punch Zoom` | one fast zoom that holds — emphasis/hype, NOT subtle |
| `Handheld Camera` / `3D Tilt` / `Slow Rotation` | strong stylised looks; planner uses them only when named or the user asks for that energy |

**Per-clip adjustments** (validated + clamped by the renderer; invalid values degrade to "off"):

| Adjustment | Range / values | Notes |
|---|---|---|
| Speed | 0.25–4.0 | video only; changes that segment's length in the output |
| Volume | 0.0–2.0 | 0 = mute that clip; >1 boosts |
| Reverse | yes | video only; duration unchanged |
| Loop | 2–10× | video only |
| Flip | horizontal / vertical / both | mirror |
| Rotate | 90 / 180 / 270 | clockwise |
| Framing | fill | crop-to-fill the frame (no letterbox bars); videos AND images — the go-to when source and project aspect differ |
| RemoveSilence | yes | video only; cuts dead-air pauses out of that segment's own audio (talking-head jump-cut tightening); changes that segment's length by an amount that depends on the footage; **strictly opt-in** — only fires when the brief explicitly asks to remove silences/pauses/dead air or tighten pacing |
| AIEdit | `"<instruction>"` | image only; applies a small, precise, localized AI edit via GPT Image 2.5 (style/color/lighting change, or a pointer/arrow/highlight/border near a subject) — a tweak, not a re-draw; duration-neutral; **strictly opt-in** — only fires when the brief explicitly asks to edit/restyle/annotate that image; **spends Shorz credits**, falls back to the unedited image on failure, and caches by (image content + instruction) so a repeat costs nothing |

**Per-clip titles** — one short title per segment with timing; `titleText` supports inline Unicode emoji (styling comes from the Text panel / `set_title_settings`).

**Filler-word removal** — different mechanism from RemoveSilence: RemoveSilence cuts silent audio gaps found by the renderer; this cuts *specific spoken words* found in the asset's own word-level transcript (fetched for every video asset regardless of whether this is used). **Strictly opt-in** — only when the brief explicitly asks to cut filler words / verbal tics ("remove the ums and uhs", "cut filler words", "trim out every 'like'"). The planner scans the transcript for filler tokens (um, uh, erm, hmm, and — only when used as a tic, not with real meaning — like/you know/I mean/sort of/kind of) and splits one clip usage into several consecutive segments on the same asset, each boundary pinned to the filler word's own transcript timestamps. Never applies to images or assets with no transcript (nothing to hallucinate). Live-tested against the then-production model (Claude Opus 4.8; the default is now Claude Opus 5.5): correctly cut "um"/"uh", correctly *left alone* "I really like this product" (real meaning, not a tic), correctly merged a two-word filler phrase ("you know") into one cut, and correctly left an untranscribed asset untouched.

**AIEdit (small AI image edits)** — only for image segments. Calls `render_ai_image_edit.edit_image_with_ai` (GPT Image 2.5 edit endpoint), wrapping the instruction in a "small localized change, preserve everything else" prompt so it can't turn into a full regeneration — keep the brief's instruction itself short and specific too ("add a red arrow pointing at X", "change the lighting to golden hour", "highlight the red car with a green border"), never "restyle the whole photo" or anything that changes the subject/composition/framing. The edited output is a **new file**; the original asset is never overwritten. On any failure (API error, no result) it silently falls back to the original image — the render never breaks. Cached by (image content + instruction text): the exact same request on the exact same image later reuses the cached file instead of spending credits again. No cost-estimate integration — this is not reflected in the project's cost-estimate bar.

**Imported music (any number of tracks) + PromptBar music steering** — the MUSIC lane accepts **unlimited tracks**; several tracks play **back to back (a playlist, not layered)** in library order. The brief can steer the whole music bus per render (all strictly opt-in — an empty or unrelated brief keeps defaults: library order, full tracks, music from video 0s, mixed with original audio):

- **Track order** — "play calm.mp3 first, then epic.mp3" (files not named keep their relative order after the named ones).
- **Per-track playback range** — "use only 0:30–1:00 of epic.mp3" (trim within one specific file; name the file).
- **Combined playback range** — "skip the first 10 seconds of the music" (applies to the concatenated sequence).
- **Placement on the video** — "start the music at 15s", "music only for the last 30 seconds".
- **Volume / fades / mix mode** — "music at 40% volume, fade out 3 seconds", "replace the original audio with the music".

**Music beat sync** — the planner can place cuts on the beats of **imported** music. Requirements and rules:

- Music must be imported to Your Library → MUSIC (`import_frontend_assets` with `assetType: "music"` → `ASSET_PATHS.music_asset_paths`) **before** Create Video. Auto-Music (generated) cannot beat-sync — it does not exist at planning time.
- **Auto-Music covers the full runtime at any length.** Generation is capped at 5 minutes, but on a longer source the track loops (5s crossfade per seam) to fill the whole video. Imported music plays through once, in the order and length the user arranged — for a 30-minute edit, match the imported total to the video length to keep it covered throughout.
- Strictly opt-in: the brief must explicitly ask to sync/cut/time/pace the edit to the music/beat/rhythm/drops. Merely importing music changes nothing.
- Works with multiple tracks: beats from every analyzable track are merged on the concatenated music timeline (each track shifted by the ones before it; the payload carries per-track start offsets and per-track BPM). When the brief also reorders/trims/moves the music, the SAME derived music plan is applied to the beat timestamps before planning **and** to the final mix — the cuts and the audio cannot drift apart.
- Strong beats are preferred for scene changes; there are no beats past the end of the music (shorter music than video → beat-locked cuts only while it plays).
- **Mutually exclusive with Speed, Loop, RemoveSilence, and filler-word removal** — they all change segment durations by a footage-dependent amount and would destroy the sync. Duration-neutral controls (Volume, Reverse, Framing, Flip, Rotate, AIEdit, transitions, motion) still combine with beat sync.

**Capture time / chronological order** — every asset in the multi-asset planner payload carries an optional `capture_time` describing when the file itself was created (`captured_at` local wall clock, `source`, `precision`, `reliable`, and `order` = a precomputed 1-based oldest-first rank). Like beat data it is **reference data, strictly opt-in**: the brief must ask for something time-based ("put these clips in chronological order", "oldest first", "start with the newest", "group by the day they were shot", "only use footage from March"). Otherwise the planner orders for story and ignores it entirely.

- Source priority: `exif` (camera DateTimeOriginal) → `video_metadata` (MP4/QuickTime creation date via ffprobe) → `filename` (`IMG_20240315_094122.jpg`, `PXL_…`, `Screenshot 2024-03-15 at 09.41.22.png`) → `file_timestamp` (the earlier of the file system's created/modified time). Only the last is flagged `reliable: false` — copying or re-encoding resets it, so it can be far from the real shoot date. `precision: "day"` means only a date was recoverable.
- All values are normalised to naive **local wall-clock** time so sources compare against each other: UTC stamps (the MP4 norm) are converted to local, and stamps carrying an explicit offset (Apple's `com.apple.quicktime.creationdate`) keep the clock as written.
- Assets with no recoverable date get **no** `capture_time` and no rank, so the planner can see they are genuinely undated and place them editorially instead of inventing a position.
- Read fresh from the live file on every render, **not** from the content-hashed asset-analysis cache — two copies of the same footage can legitimately have different dates, and it also keeps the change from invalidating every user's cached vision analysis.
- Duration-neutral, so it combines freely with everything, beat sync and filler-word removal included.
- Scene order inside one clip is already chronological (`captured_at` + the scene's own `timestamp`); clips are never reordered internally.

### Single main asset: tool-call editing

With exactly one main video/image, an LLM picks from a fixed tool set instead of building a timeline: `trim_video`, `remove_audio`, `set_audio_volume`, `change_video_speed`, `set_image_duration`, `rotate_media`, `flip_media`, `reverse_video`, `loop_video`, `fade_video`, `freeze_frame`, `crop_media`, `audio_fade`, `remove_silence`, `edit_image_with_ai`, `resize_media`, `fit_to_aspect`, `extract_audio`, `replace_audio`, `concat_media`, `extract_video_frames`, `get_media_info`, plus content-aware `analyze_video_and_edit` / `auto_edit_video` and `auto_clip_short_from_single_video` (one short highlight from a long file). Timing-gated tools (trim, fades, freeze, loop, image duration) only fire when the brief contains the actual numbers ("trim 5s–12s", "freeze at 1:12 for 3s"). A single still image always comes out as a video: it is shown for the length the brief names ("show it for 10 seconds"), or for 5 seconds when the brief names none. `remove_silence` only fires when the brief explicitly asks to cut pauses/dead air/tighten pacing — it is never applied by default. `edit_image_with_ai` (image only, keep the instruction small and specific) works the same way here as it does headless — see `../headless-workflows/single-asset-edit.md`. Transitions/motion/beat sync/filler-word removal/chronological ordering do **not** apply here — filler-word removal is a multi-asset-planner-only mechanism (transcript splitting), and with a single clip there is nothing to order.

### Brief-writing patterns that work

- "Every clip must fill the frame — no black bars." → `Framing: fill` on all segments.
- "Slow the hardest knockdown to half speed; mute all clips; dissolve between them." → per-segment Speed/Volume + transitions, each landing on the semantically right clip.
- "Change scenes on the strong beats of the music, with dissolves." → beat sync + transitions (music must already be imported).
- "Play upbeat.mp3 first and only its chorus from 0:45 to 1:15, then chill.mp3; start the music at 5 seconds in." → multi-track order + per-track trim + placement, honored consistently by both the beat payload and the final mix.

**Never pad a brief with negatives.** Everything the planner can add is strictly opt-in and already OFF unless the brief asks for it, and everything else on the timeline — zoom, subtitles, titles, b-roll, emojis, sound effects, borders, overlays, dubbing — is a **panel** toggle no brief can switch on or off. So "no transitions, no zoom, no subtitles, no b-roll, no emojis, no sound effects" buys nothing a default project would not already do. It is not free, either: the raw PromptBar text is handed **verbatim to every LLM stage** of the render (edit planner, music derivation, …), so each negative is re-paid in every stage and gives each one irrelevant constraints to reason about — in one live render the music stage spent its entire reply acknowledging clauses about subtitles and emojis. Say what you want and leave the rest unmentioned. To *guarantee* a feature is off, read or patch its panel (`read_project_settings`, `set_*_settings`), never the brief.
- "Hold each photo ~4 seconds with slow zooms and pans." → motion on stills; say the hold length — slow moves need ≥3s segments.
- "Cut the dead air out of the interview clips." → `RemoveSilence: yes` on the talking-head video segments only (not images, not music-synced clips).
- "Add a red arrow pointing at the watch in the product shot." → `AIEdit: "..."` on that one image segment only — keep the instruction that small and specific, never "restyle the whole product shot".
- "Cut the filler words like um and uh from the interview." → transcript-based splitting on the transcribed video segments only (multi-asset planner only; no effect on images or untranscribed clips).
- "Put these clips in chronological order based on the timestamps and cut the boring parts." → ordering by `capture_time.order` + normal engaging-moment selection (multi-asset planner only).
- Negative control: a brief that never mentions transitions/motion/speed gets NONE of them — do not warn users about effects they didn't ask for.

## Instruction handling rules

- **Configure only** — patch only the panels the user mentions, set PromptBar if requested, and **stop**. Do not trigger Create Video.
- **Render now** — confirm source media exists, apply requested panel settings, persist PromptBar text, then trigger Create Video and poll status.
- **Tune style only** — patch panels only; do not touch assets or PromptBar.
- **Replace / curate media only** — perform asset operations (`import_frontend_assets`, `delete_asset`, `rename_asset` on confirmation) without triggering generation.
- **Aspect-ratio change only** — call `switch_project_aspect_ratio`; do not modify unrelated panels.
- **Minimal patches** — for each panel tool, pass only the keys the user asked about; do not send full panel blobs.

## Execution sequence

1. **Resolve project** per **SKILL.md** → *Project targeting rules*: `get_current_open_project`, then `list_projects` if needed. If the project type is not `auto-edit`, ask the user whether to continue or switch.
2. **Read state** (optional but recommended for non-trivial requests): `read_project_settings`. Confirm `projectType: "auto-edit"` (or `UI_SETTINGS.project_type` as fallback) and inspect `VIDEO_SIZE`, `UI_SETTINGS.user_input_instructions`, and any panel section the user is about to change.
3. **Apply panel changes** — for each panel the user mentioned, call the matching `set_*_settings` tool with a minimal `settings` patch. Use `switch_project_aspect_ratio` for aspect changes. Use `update_project_settings` only for nested keys the panel tools do not expose, and pass only the nested `updates` you need (deep merge).
4. **Asset operations** (when requested) — `import_frontend_assets` for new media (`assetType`: `video`, `broll`, `sound`, `music`, `image`, `avatar`, `audio`). Confirm before `delete_asset` or `rename_asset`.
5. **PromptBar + Create Video** (only when the user asks for a render):
   - If the user requested a specific main LLM, `set_main_ai_model` (or pass `mainAiModelName` on `trigger_create_video`). Current lineup snapshot (seven): `anthropic/claude-opus-5-5` (default), `anthropic/claude-fable-5-1`, `anthropic/claude-sonnet-5-5`, `openai/gpt-6-1-sol`, `openai/gpt-6-luna`, `openai/gpt-6-astra`, `google/gemini-3.8-flash` — call `list_main_ai_models` for the live list. **On a free-tier run** (zero-balance account; `auto-edit` is one of the two eligible types) only **`google/gemini-3.8-flash`** is zero-rated, and the MCP path does **not** pin it for you — set it here or the render bills and 402s mid-way. See **SKILL.md** → *Keys and auth dependencies* for the rest (30-minute source cap you must check yourself, and the paid steps to leave off: AI b-roll, dubbing/auto-music/noise removal, thumbnails, Animation Studio chat, publishing — Auto SoundFX, Assets/WEB/GIF/emoji b-roll, subtitles, titles and local effects are free).
   - `set_user_instructions` with the PromptBar text.
   - `trigger_create_video` (preferred — mirrors the Create Video button) or `generate_video`.
   - Poll **`get_video_generation_status`** until `lastStatus` is terminal (`completed`, `completed_no_output`, `error`, `stopped`, …). Use **`fetch_app_events`** only if the user wants live logs or you are debugging a stuck/failed render (see **SKILL.md** → *Event stream*).
   - `stop_video_generation` only on user request.
6. **Return outcome** — `success`/error from each tool call, paths produced, and any clamps/warnings the panel tools reported in `applied`.

## Quick defaults

- Aspect ratio: keep the current `VIDEO_SIZE` unless the user explicitly changes it.
- PromptBar: keep existing `UI_SETTINGS.user_input_instructions` unless the user gives new text.
- Source media: keep existing `ASSET_PATHS.*`; do not replace silently.

## Common failures

- **Trying to set aspect ratio via `set_general_video_settings`** — prefer `switch_project_aspect_ratio` for parity with the UI button and other workflows.
- **PromptBar empty** — for `auto-edit` Create Video, persist non-empty PromptBar text before triggering, or expect a thin/no-intent render.
- **Aspect ratio or pixel size in PromptBar** — remove sizing from the brief; set aspect with **`switch_project_aspect_ratio`** only (**SKILL.md** → *Output framing*).
- **Asset path missing on disk** — `file_exists` on the path from `ASSET_PATHS.*`. Re-import or correct the path before Create Video.
- **Generation appears stalled** — confirm with `get_video_generation_status` first; if still unclear, pull `fetch_app_events` for IPC detail (`video-generation-log`, `video-generation-state`).
- **Unknown keys in panel patches** — strict validation rejects unknown keys; remove the extra fields and retry with only the supported ones from the matching panel skill.
