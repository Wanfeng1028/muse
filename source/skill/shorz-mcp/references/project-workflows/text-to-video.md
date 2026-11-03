# Text-to-Video workflow (project type `text-to-video`)

Script-or-audio driven storyboard project: a narration plus generated/imported visuals turned into a video. Use **`set_text_to_video_settings`** for the panel contract, plus the speech-audio / reference-image helpers. Global rules and routing live in **`../../SKILL.md`**.

Use this when the user cares about **narration-first or storyboard-style** control (script per scene, model picks, transitions). For a general edit, use **`auto-edit.md`**. For a single talking head or two-speaker dialogue, use **`avatar.md`** or **`podcast.md`**.

## What it looks like

The Text-to-Video panel shows:

- **Input mode** — `script` (write the narration; Shorz TTSes it) or `audio` (upload a pre-recorded voice track).
- **Source media** — `imported` (user's own clips), `generated_images` (AI stills with motion), or `generated_video` (AI video clips).
- **Script** field (script mode).
- **Voice** — ElevenLabs voice id/name (script mode).
- **Transition type(s)** and **image motion(s)** — drive how scenes change and how stills animate.
- **Image model** — `Nano Banana 2`, `GPT Image 2` (the `GPT Image 2` id now serves GPT Image 2.5 Flare — the fast variant) or `GPT Image 2.5 Sunburst` (OpenAI's sharper, slightly slower variant; same 2 credits per still, best same-face likeness from references) (when `source_media` uses generated images). (Nano Banana 2 Lite is not a TTV option — use it for AI B-roll or standalone image generation instead.)
- **Video model** — pick from the supported list (when `source_media` uses generated video).
- **Reference images** — optional, **typed** since v2.5.x: **Style** (0–3), **Characters** (0–4, each with a required unique name; 4 = the verified per-frame identity limit), **Environments** (0–4, named). Every type is optional — the pipeline auto-generates whatever is missing from the script. Named characters/environments do NOT need to be mentioned in the script: explicit role matches are used when present (character "Maya" with notes "the detective" plays "a detective"; notes settable via MCP, not shown in the panel UI), otherwise the pipeline stages them itself — characters become the cast that visualizes the narration, environments the recurring settings, decided per scene by the shot writer. They stay visually consistent across every scene that features them; only genuinely people-free content (infographics, object demos) skips character references. The panel also has a per-type **Generate…** modal to create references in-app.
- **Style references contribute STYLE ONLY.** The pipeline distills style images into a textual "style bible" applied to every scene; the raw style photos are NOT attached to per-scene generation, so a person, object or place visible in a style photo never becomes a scene subject and never competes with Character/Environment references (they still shape the look of the generated character/environment sheets). A person who should appear in the video must be added as a **Character** reference — putting their photo in the Style bucket only donates its look.
- **PromptBar** — optional **look and mood** guidance (lighting, style, pacing). **Not** a replacement for the script.

**Main VIDEO (“Import Main Assets”)** applies **only when** **Source Media** is **`imported`**: **`MediaPanel.tsx`** hides the Your Library → **VIDEOS** tab otherwise, **`canImportMainAssets`** in **`App.tsx`** blocks PromptBar **Import Main Assets**, and headless **`import_frontend_assets`** with **`assetType: "video"`** is **rejected with an error** unless `textToVideoSourceMedia` is `imported` (switch it via `set_text_to_video_settings` first, or use `"broll"`). For **`generated_images`** / **`generated_video`**, timelines are assembled from AI sources — do not tell users to add main VIDEO library clips unless they switched to **`imported`**.

Create Video turns the script + visuals into a finished video using the selected models.

## Standalone generation vs Create Video

Use **project tools** (`set_text_to_video_settings` + `trigger_create_video`) when the user wants a **full text-to-video export** (script/audio, scene assembly, transitions, motions).

Use **standalone MCP tools** when the user only wants **individual assets** without opening or changing a project:

| Goal | Tool | Notes |
|---|---|---|
| One scene still (TTV image models) | `generate_scene_image` | `prompt`, optional `imageModel`, `aspectRatio` or `width`/`height`, optional `referenceImagePaths` (max 3). Python stack; does not write `SCRTIPT_TO_VIDEO`. |
| One i2v clip from a still | `generate_image_to_video` | `imagePath`, `prompt`, **required** `videoModel`, optional `durationSec`. Same model ids as `textToVideoVideoModel`. |
| Quick AIML still (no TTV parity) | `generate_images` | Node/AIML only; different model id labels. |

All three are **async by default**: they return `{ started, jobId }` immediately — poll `get_job_status { jobId }` until `lastStatus` is `completed` (`result` carries the normal payload; `outputPaths` lists the absolute saved files) or `error`. GPT Image 2.5 stills can take a few minutes (2.5 is up to ~50% faster than GPT Image 2) and i2v clips longer; `awaitCompletion: true` restores the blocking form only if your tool-call timeout allows it. **Never re-call a generation because a poll timed out — the job is still running and a retry would bill credits twice.**

After standalone generation, import or assign paths manually (`import_frontend_assets`, reference image helpers) if building a project later. **Never** put script text in PromptBar; **never** use standalone tools as a shortcut for Create Video on an existing text-to-video project unless the user only asked for assets.

## Tool contract

**Primary tool:** `set_text_to_video_settings`

**Arguments:** `projectPath` (absolute) and a `settings` object with only the keys you want to change.

**Supported keys in `settings`:**

| Key | Type | Notes |
|---|---|---|
| `textToVideoScript` | string | Used in `script` mode. |
| `textToVideoInputMode` | string enum | `script` \| `audio`. |
| `textToVideoSourceMedia` | string enum | `imported` \| `generated_images` \| `generated_video`. |
| `textToVideoVoice` | string | ElevenLabs voice id/name (script mode). |
| `textToVideoTransitionType` | string enum | One of the transitions below. |
| `textToVideoTransitionTypes` | string[] | Array of the same enum values. |
| `textToVideoImageMotion` | string enum | One of the image motions below. |
| `textToVideoImageMotions` | string[] | Array of the same enum values. |
| `textToVideoImageModel` | string enum | `Nano Banana 2` \| `GPT Image 2` (GPT Image 2.5 Flare, fast) \| `GPT Image 2.5 Sunburst` (sharper, slightly slower, same price). (Lite is not a TTV option.) |
| `textToVideoVideoModel` | string enum | See video model list below. |
| `textToVideoReferenceImagePaths` | string[] | Up to **3** entries; extra entries are dropped server-side. **Legacy: style references only.** Writing it also syncs the typed styles bucket. For characters/environments use the typed tools below. |

**Allowed `textToVideoTransitionType` values (copy verbatim):**

`none`, `automatic`, `fade`, `dissolve`, `fadeblack`, `fadewhite`, `fadegrays`, `wipeleft`, `wiperight`, `wipeup`, `wipedown`, `slideleft`, `slideright`, `slideup`, `slidedown`, `smoothleft`, `smoothright`, `smoothup`, `smoothdown`, `revealleft`, `revealright`, `revealup`, `revealdown`, `circleopen`, `circleclose`, `circlecrop`, `radial`, `pixelize`, `distance`, `hrslice`, `hlslice`, `squeezeh`, `zoomin`, `hblur`

**Allowed `textToVideoImageMotion` values (copy verbatim):**

`none`, `ai`, `zoom_out`, `zoom_in`, `zoom_in_left`, `zoom_in_right`, `zoom_in_top`, `zoom_in_bottom`, `random_zoom`, `rapid_zoom`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `handheld_camera`, `rotation`

**Allowed `textToVideoVideoModel` values (copy verbatim):**

- `klingai/video-v3-standard-image-to-video` — 3–15s clips (~26 cr/s)
- `gemini-omni-flash-preview` — native Google route; token-billed (~12 credits/sec real cost); 1–10s clips, 16:9/9:16. Also the locked Advertisement engine. Cheapest is Seedance 2.0 Mini (9 cr/s). NB Google's Tier-1 quota is only 20 requests/day: if an Omni clip fails mid-render, the remaining scene/b-roll clips of that render automatically reroute to Seedance 2.0 Fast (closest credit cost, ~14 cr/s); ads never reroute.
- `bytedance/seedance-2-5` — premium Seedance tier (~27 cr/s @720p, the priciest video model). Generates **4–30s in one coherent clip**, where the 2.0 family caps at 15s and stitches anything longer from chained segments. 480p/720p only (no 1080p/4k — use `bytedance/seedance-2-0` for those). Requires app 3.1.0+.
- `bytedance/seedance-2-0` — the only Seedance with 1080p/4k output
- `bytedance/seedance-2-0-fast`
- `bytedance/seedance-2-0-mini` — **the server catalog default for `text_to_video`** (4–15s clips, cheapest at ~9 cr/s @720p)

**Retired — do not send:** `google/veo-3.1-i2v-fast` is rejected by validation on write. `custom:happyhorse-1.0` is worse — it **still passes MCP validation**, so the write succeeds, but its catalog row is disabled and the render then fails at generation time.

**Persistence oracle** — confirm via `read_project_settings` → `SCRTIPT_TO_VIDEO` (yes, with that spelling — it is the on-disk key):

| MCP key | `SCRTIPT_TO_VIDEO` key |
|---|---|
| `textToVideoScript` | `text_to_video_script` |
| `textToVideoInputMode` | `text_to_video_input_mode` |
| `textToVideoSourceMedia` | `text_to_video_type` |
| `textToVideoVoice` | `text_to_video_voice` |
| `textToVideoTransitionType` | `text_to_video_transition_type` |
| `textToVideoTransitionTypes` | `text_to_video_transition_types` (JSON-encoded string) |
| `textToVideoImageMotion` | `text_to_video_motion_type` |
| `textToVideoImageMotions` | `text_to_video_motion_types` (JSON-encoded string) |
| `textToVideoImageModel` | `text_to_video_image_model` |
| `textToVideoVideoModel` | `text_to_video_video_model` |
| `textToVideoReferenceImagePaths` | `text_to_video_reference_image_paths` (comma-joined string; mirrored from typed styles) |
| _(typed reference tools)_ | `text_to_video_typed_references` — JSON `{version, characters[], environments[], styles[]}` written by the typed tools below. |
| _(not in `set_text_to_video_settings`)_ | `text_to_video_speech_audio_url` — written by `save_text_to_video_speech_audio` / cleared by `delete_text_to_video_speech_audio`. Required (non-empty) for `audio` input mode. |

### Typed reference tools (characters / environments / styles)

- `save_text_to_video_typed_reference` (`projectPath`, `referenceType: "character"|"environment"|"style"`, `imagePath` (local file, copied into the project), `name` (**required** for character/environment, must be unique), optional `notes`, optional `source`) — adds one typed reference and persists it (styles are mirrored into the legacy flat list). Caps: 4 characters / 4 environments / 3 styles (4 characters = the verified per-frame identity limit). Returns `{ success, item, typedReferences }`; keep `item.id` for later edits.
- `delete_text_to_video_typed_reference` (`projectPath`, `id`) — removes the reference, its image and any cached pipeline artifacts (character sheets / restyled environments).
- `update_text_to_video_typed_reference` (`projectPath`, `id`, optional `name`, optional `notes`) — rename or re-annotate a character/environment.
- **Pipeline behavior:** character references get a turnaround sheet generated from the photo (1 extra image-edit call, cached; visible in Generation Logs). Environment photos are used directly and restyled once when a style context exists. Unused roster entries are logged as warnings — a script with no characters still renders character-free (references never force content in).

### Project-specific media helpers

- `save_text_to_video_speech_audio` (`base64DataUrl`, `projectPath`) — install pre-recorded narration audio.
- `delete_text_to_video_speech_audio` (`projectPath`) — clear it.
- `save_text_to_video_reference_images` (`dataUrls`, `projectPath`, optional `options`) — **legacy, style-only**; prefer `save_text_to_video_typed_reference`.
- `delete_text_to_video_reference_image` (`filePath`) — legacy single-file removal; prefer `delete_text_to_video_typed_reference`.
- `list_elevenlabs_voices` — voice discovery.
- `select_local_image_for_import` — **opens a native OS dialog**; only when interactive picking is acceptable. Single `options` object argument that supports `{ title?: string, extensions?: string[] }` (extension strings without leading dots; defaults to `["jpg", "jpeg", "png"]`). Returns `{ success, filePath, fileName, canceled }` — `filePath` is the absolute path of the picked file (feed it to `save_text_to_video_typed_reference`'s `imagePath`, `import_frontend_assets`, or any path-taking tool). No base64 comes back. For fully headless flows from known paths, prefer `import_frontend_assets` or `save_text_to_video_reference_images` instead.

### PromptBar vs script

For project type `text-to-video`, the **PromptBar** (`set_user_instructions` → `UI_SETTINGS.user_input_instructions`) is **look-and-mood guidance** — lighting, style, pacing, what each beat should feel like. **The narration script lives in `textToVideoScript`** (`script` mode) **or in the saved speech-audio file installed via `save_text_to_video_speech_audio`** (`audio` mode — persisted as `SCRTIPT_TO_VIDEO.text_to_video_speech_audio_url`, not directly settable through `set_text_to_video_settings`). Never put the script in PromptBar. Never put aspect ratio or pixel dimensions in PromptBar (**SKILL.md** → *Output framing*).

### Example Styles (UI one-click demo presets, 2026-08-05)

The PromptBar suggestions panel (textarea focused) has an **Example Styles** tab for text-to-video: bundled demo cards (first: *"Historic — Comic Line Art"*, the Evolution of Warfare demo). Clicking a card **overwrites** the project's script, PromptBar instructions, ALL typed references (existing reference files are deleted and replaced by the demo's bundled images), and sets source media `generated_images`, image model `GPT Image 2`, the card's own narration voice (each style names its own — Shaun for the first card), transitions `["automatic"]`, motions `["ai"]`. There is **no MCP tool** for applying a demo style — it is UI-only. If a project's settings/references suddenly changed to these values mid-session, the user likely clicked a demo style card; re-read settings before further patches instead of assuming your earlier writes persist. Demo style data lives in `frontend/src/data/exampleStyles/` (one file per style + registry).

## Instruction handling rules

- **Create new text-to-video output** — set or confirm panel options (input mode, source media, script, voice, models), persist PromptBar with look/mood notes if requested, trigger Create Video.
- **Transitions & motion default to AI Automatic** — unless the user explicitly names transitions or motions, set `textToVideoTransitionType: "automatic"` (AI Automatic) and `textToVideoImageMotion: "ai"` (AI Automatic). Never substitute `fade`/`dissolve`/`zoom_*` or the multi-value `textToVideoTransitionTypes`/`textToVideoImageMotions` arrays unasked. Only deviate when the user requests specific looks.
- **Switch source mode** — patch only `textToVideoSourceMedia` (and related fields only if asked).
- **Audio-input flow** — `textToVideoInputMode: "audio"` plus a saved speech-audio file via `save_text_to_video_speech_audio` (or the equivalent path).
- **Style / look only** — patch transition/motion/model keys; leave script and PromptBar alone.
- **Update script only** — patch `textToVideoScript` (do **not** put script content in PromptBar).
- **Reference images only** — typed: `save_text_to_video_typed_reference` (character/environment need a unique `name`; notes help script matching). Style-only shortcuts: `save_text_to_video_reference_images` or patch `textToVideoReferenceImagePaths` (max 3).
- **Configure only** — `set_text_to_video_settings` + optional `set_user_instructions`, then stop before Create Video.
- **Minimal patches** — pass only requested keys.

## Execution sequence

1. **Resolve project** per **SKILL.md** → *Project targeting rules*. Create only with explicit approval via `create_project` with `projectType: "text-to-video"`.
2. **Read state** (optional): `read_project_settings` → inspect `SCRTIPT_TO_VIDEO`.
3. **Pick input mode** — `script` (set `textToVideoScript` and `textToVideoVoice`) or `audio` (install via `save_text_to_video_speech_audio` before Create Video).
4. **Pick source media** — `imported`, `generated_images`, or `generated_video`. **Transitions and motion default to AI Automatic**: set `textToVideoTransitionType: "automatic"` and `textToVideoImageMotion: "ai"` unless the user explicitly asks for specific transitions/motions. Do **not** invent `fade`/`dissolve`/`zoom_*` choices on your own.
5. **Models** — `textToVideoImageModel` and/or `textToVideoVideoModel` depending on `textToVideoSourceMedia`.
6. **Reference images (optional)** — typed characters/environments/styles via `save_text_to_video_typed_reference` (named, from local paths); style-only via `save_text_to_video_reference_images` (data URLs) or `textToVideoReferenceImagePaths` (max 3). All reference types are optional — missing ones are auto-generated from the script.
7. **PromptBar (optional)** — `set_user_instructions` for look/mood guidance.
8. **Create Video** (only when the user asks for a render):
   - `trigger_create_video` (preferred) or `generate_video`.
   - Poll **`get_video_generation_status`** until terminal. `fetch_app_events` only on request or when debugging.
   - `stop_video_generation` on user request.
9. **Return outcome** — success/failure, generated output location(s), model/provider warnings.

**After Create Video:** to change ONE thing in the finished story ("give scene 3 a different picture", "change what scene 2 says to …", "remove scene 4", "use a deeper voice", "make the subtitles bigger") use **`edit_generated_video`** — see **`edit-generated-video.md`** → *Text-to-Video stories*. It rebuilds the story from its saved scenes with only the named scenes generated again and every effect kept on its words, producing a new version. Do not edit the script and re-run `trigger_create_video` for that: any script change is a new cache key, so every picture and clip would be generated (and billed) again.

**Re-rendering an unchanged project is free.** Script, voice, models, references and PromptBar text form a cache key; an exact match reuses the scene images, AI clips and narration from the previous run and skips every AI call (so it costs no credits and finishes in render time alone). The Generation Logs list each reused asset — `Cached scene image N/M`, `Cached scene video N/M`, `Cached narration audio N/M`, one preview per file — so the reused set is auditable. Change any keyed input and only the affected assets regenerate.

## Imported music

Your Library → **MUSIC** works here exactly as elsewhere: `import_frontend_assets` with `assetType: "music"` (free, any number of files; several play **back to back** in lane order). Nothing needs enabling — imported music is mixed into every render. The **PromptBar** can then steer play order, a section of one named track, skipping into the combined music, where the music sits on the timeline, volume, fades, and whether it mixes under the narration or replaces the clip audio. Full vocabulary: **`auto-edit.md`** → *Imported music*. Typical TTV ask: *"25% volume under the narration, fade out over the last 3 seconds."* Beat-synced **cutting** does not apply (multi-asset `auto-edit` only) — scene changes here follow the script's sentences.

## Quick defaults

- `textToVideoInputMode`: `script`
- `textToVideoSourceMedia`: `generated_images`
- `textToVideoTransitionType`: `automatic` (**AI Automatic** — the default; let Shorz pick transitions unless the user names specific ones)
- `textToVideoImageMotion`: `ai` (**AI Automatic** — the default; let Shorz pick motion unless the user names specific ones)
- `textToVideoImageModel`: `Nano Banana 2`
- `textToVideoVideoModel`: `bytedance/seedance-2-0-mini` — the server catalog marks it the `text_to_video` default, and it is also the cheapest. **Do not assume a persisted default**: read the current value with `read_project_settings` → `SCRTIPT_TO_VIDEO.text_to_video_video_model` and set it explicitly with `set_text_to_video_settings`. **Never** send `google/veo-3.1-i2v-fast` (retired 2026-07-24, rejected by validation on write) or `custom:happyhorse-1.0` (passes validation, then fails at generation — disabled catalog row)
- `textToVideoReferenceImagePaths`: `[]`

## Common failures

- **Narration silently truncated in `generated_video`** — a scene whose speech runs longer than the video model's per-clip maximum has the clip clamped down, and the compositor then **trims the narration to match** rather than stretching the picture. Words are lost with only an info-level log line. The models' own auto-stitching does not help, because TTV pre-clamps before the request. Caps: Gemini Omni 10 s (riskiest), Seedance 2.0 family 15 s, Kling 15 s, Seedance 2.5 30 s (safest).
- **A failed AI clip is not fatal** — that scene falls back to its still image, so the render succeeds as a mix of motion and stills. Check the output before reporting full success.
- **Script too short** — script mode requires **≥ 50 characters** (raw, untrimmed) or the render aborts; the ≤6,000-word / ≤40,000-char caps are UI-only and MCP does not enforce them.

- **`audio` mode without saved speech audio** — Save it first (`save_text_to_video_speech_audio`) before triggering Create Video.
- **Invalid enum value** — Resend with a verbatim string from the lists above.
- **More than 3 reference images** — Extra entries are dropped; trim before retry to match what will actually be used.
- **Generation appears stalled** — `get_video_generation_status` first; if still unclear, pull `fetch_app_events` for raw `video-generation-log` traffic.
- **Script accidentally placed in PromptBar** — Move script to `textToVideoScript`; clear or rewrite PromptBar via `set_user_instructions`.
