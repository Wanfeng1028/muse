# Avatar workflow (project type `avatar`)

Single **talking-character** project: an avatar image plus an **ElevenLabs voice**, driven by either a written **script** or an **uploaded audio** file. Use **`set_avatar_settings`** for the panel contract, plus headless image/audio pickers for local files. Global rules and routing live in **`../../SKILL.md`**.

Use this when the user wants a single presenter / talking head. For two-speaker dialogue, switch to **`podcast.md`**. For narrative storyboard work, use **`text-to-video.md`**.

## What it looks like

The Avatar panel shows:

- **Avatar model** — `Kling Avatar`, `Kling Avatar Pro` (default), or `OmniHuman 1.5`.
- **Avatar image** — a single still that the model animates as the speaker. Can come from a generated image (data URL), an imported file, or a path on disk. The in-app **Avatar Creator** can generate it from a text description alone, or from **up to 3 face reference photos** so the avatar keeps a specific person's exact face (headless equivalent: `generate_images` with `referenceImages` — see step 3).
- **Avatar angles (optional)** — up to **3** additional stills of the **same** avatar from different angles. Only available once an avatar image is set. When one or more angles are present, the avatar script is split into **sentences** and a **different angle is chosen per sentence** at render time, so the presenter isn't locked to one pose. Leave empty to keep the single-image behavior.
- **Input mode** — `script` (typed text gets TTS'd) or `audio` (a pre-recorded voice track).
- **Voice** — ElevenLabs voice id/name (only relevant in `script` mode).
- **Motion instructions** — optional cues for how the presenter moves. The **desktop UI exposes this editor only for a Kling model** (either `Kling Avatar` or `Kling Avatar Pro`; labeled “Kling Motion Instructions”); MCP still accepts `avatarMotionInstructions` for any model, though **non‑Kling models may ignore** the field.
- **PromptBar** — optional auto-edit guidance (captions, B-roll, music, etc.) when those auto-edit features are also turned on for this project. **It is not the spoken text.**

Create Video renders the avatar speaking the script (or the audio) with the chosen motion style.

**Main VIDEO (“Import Main Assets”)** — **`avatar`** projects **do not** expose the timeline main VIDEO lane in the Electron UI (`isMainAssetsLaneEnabled` excludes `podcast`/`avatar`/`advertisement`/`music-video`). `import_frontend_assets` with **`assetType: "video"`** is **rejected with an error** here (headless `overridePaths` path); use **`select_avatar_image`**, **`save_avatar_image`**, and audio helpers for character media, or **`assetType: "broll"`** for supporting footage (**SKILL.md** → *Main VIDEO import*).

## Tool contract

**Primary tool:** `set_avatar_settings`

**Arguments:** `projectPath` (absolute) and a `settings` object containing only the keys you want to change.

**Supported keys in `settings`:**

| Key | Type | Notes / validation |
|---|---|---|
| `avatarModel` | string enum | `Kling Avatar` \| `Kling Avatar Pro` \| `OmniHuman 1.5`. Wrong values → rejected with the allowed list. |
| `avatarScript` | string | Max **40000** chars and **6000** words. Used in `script` mode. |
| `avatarImage` | string or `null` | Path / URL to the still image. |
| `avatarAngleImages` | array of strings or `null` | Optional. Up to **3** extra image paths/URLs of the **same** avatar from different angles. When non-empty, the script is split into sentences and a random angle is used per sentence. Pass `[]` or `null` to clear. Only meaningful once `avatarImage` is set. |
| `avatarVoice` | string | Non-empty; typically an ElevenLabs voice id/name. |
| `avatarMotionInstructions` | string | Max **2500** chars. MCP validates length for any model; desktop UI exposes this for a **Kling** model (either `Kling Avatar` or `Kling Avatar Pro`; “Kling Motion Instructions”). |
| `avatarTransitions` | array of strings | Optional. Transition overlays played over each **cut between avatar clips**: `Transition01` … `Transition20`, or `["None"]` (default) for hard cuts. Pass several and one is drawn at random per cut, never repeating back-to-back. Each brings its own whoosh, mixed at the project's Sound Effects volume. Unknown ids → rejected. Only takes effect when the render produces **2+ clips** — that means avatar angles, but **also** a no-angle script long enough to be split at the model's per-request window. |
| `avatarInputMode` | string enum | `script` \| `audio`. |
| `avatarAudioUrl` | string or `null` | Required (non-empty) when `avatarInputMode` is `audio`. |
| `avatarCropX` | number | Avatar preview position X, **clamped 0–100** (50 = centered). Pans the object-cover crop; in a **16:9** project with a portrait/square avatar it instead positions the letterboxed avatar horizontally on the canvas (0 = left, 100 = right). |
| `avatarCropY` | number | Avatar preview position Y, **clamped 0–100** (50 = centered). Pans the object-cover crop vertically; unused in the 16:9 letterbox case. |

**Crop recentring:** changing `avatarImage` resets both crop values to `50` (pan belongs to a specific image shape, mirroring the Avatar panel) — unless the **same** patch also sets `avatarCropX` / `avatarCropY`. To keep a framing across an image swap, send the image and the crop values together.

**Persistence oracle** — confirm via `read_project_settings` → `AVATAR_SETTINGS`:

| MCP key | `AVATAR_SETTINGS` key |
|---|---|
| `avatarModel` | `avatar_model` |
| `avatarScript` | `avatar_script` |
| `avatarImage` | `avatar_image` |
| `avatarAngleImages` | `avatar_angle_images` (JSON array string) |
| `avatarVoice` | `avatar_voice` |
| `avatarMotionInstructions` | `avatar_voice_instructions` |
| `avatarTransitions` | `avatar_transitions` (JSON array string) |
| `avatarInputMode` | `avatar_input_mode` |
| `avatarAudioUrl` | `avatar_audio_url` |
| `avatarCropX` | `avatar_crop_x` (stored as a string, e.g. `"50"`) |
| `avatarCropY` | `avatar_crop_y` (stored as a string, e.g. `"50"`) |

### Project-specific media helpers

In-memory or data-URL sources:

- `save_avatar_image` (`base64Data`, `projectPath`, optional `customFileName`) — save image bytes into the project. The argument name is `base64Data`, but the bridge requires a **PNG/JPEG/etc. data URL** string (`data:image/<type>;base64,<payload>` — same format Electron's `save-avatar-image` expects), not raw base64 alone.
- `save_avatar_audio` (`base64DataUrl`, `projectPath`) — save audio bytes; switches to audio input.
- `delete_avatar_audio` (`projectPath`) — clear stored avatar audio.

Headless local-file pickers (no native dialog):

| Tool | Arguments | Effect |
|---|---|---|
| `select_avatar_image` | `projectPath`, `imageFilePath` | Imports a local image and sets `avatarImage` via the validated `set_avatar_settings` path. |
| `select_avatar_angle_image` | `projectPath`, `imageFilePath` | Imports a local image and **appends** it to `avatarAngleImages` (max 3). Requires `avatarImage` already set; errors if the angle limit is reached. |
| `select_avatar_audio` | `projectPath`, `audioFilePath` | Imports local audio, switches to `avatarInputMode: "audio"`, and sets `avatarAudioUrl`. |

**Supported extensions** — images: `.png`, `.jpg`, `.jpeg`, `.webp`. Audio: `.mp3`, `.wav`, `.m4a`, `.ogg`, `.aac`, `.flac`.

Voice discovery: `list_elevenlabs_voices`.

### PromptBar vs spoken content

For project type `avatar`, the **PromptBar** (`set_user_instructions` → `UI_SETTINGS.user_input_instructions`) is **not** the script. It guides **enabled auto-edit features** (captions, on-screen B-roll, music, zooms) when those panels are turned on. The spoken content always lives in either `avatarScript` (script mode) or `avatarAudioUrl` (audio mode). Never overwrite PromptBar with the user's spoken lines. Never put aspect ratio or pixel dimensions in PromptBar (**SKILL.md** → *Output framing*).

**Imported music works here too.** Import any number of tracks (`import_frontend_assets` with `assetType: "music"`, free) and the PromptBar can arrange them — play order, a section of one named track, where the music starts/ends on the timeline, volume, fade in/out, and whether it mixes under the voice or replaces the clip audio. Full vocabulary: **`auto-edit.md`** → *Imported music*. Typical avatar ask: *"put my track under the whole video at 20% so it never competes with my voice, fade it out over the last 3 seconds."* Beat-synced **cutting** is the one music feature that does **not** apply here — that needs the multi-asset `auto-edit` planner.

## Instruction handling rules

- **Create avatar video from scratch** — confirm `avatarModel`, `avatarInputMode`, voice (script mode), avatar image, and `avatarScript` or `avatarAudioUrl`. Persist PromptBar only if the user asked for auto-edit-style guidance.
- **Switch between script and audio** — patch `avatarInputMode` explicitly and ensure the paired field (`avatarScript` or `avatarAudioUrl`) is in place. If switching to audio without an audio file, save it first.
- **Change motion style only** — patch `avatarMotionInstructions` (and `avatarModel` if needed); leave script/voice/image alone.
- **Change transitions only** — patch `avatarTransitions` with the full desired pool (e.g. `["Transition01","Transition05","Transition12"]`). Pass `["None"]` to go back to hard cuts. Transitions never change the video's length, so lip sync is unaffected, and the pool is NOT part of the render cache key — switching it re-applies overlays to the already-generated clips with no regeneration and no credits. The Podcast panel has the same control (`podcastTransitions`).
- **Change voice or avatar identity only** — patch `avatarVoice` and/or `avatarImage` only. Changing `avatarImage` should usually clear `avatarAngleImages` (angles belong to a specific avatar) unless the new angles are provided too.
- **Add / remove avatar angles** — patch `avatarAngleImages` with the full desired array (max 3). Requires an `avatarImage` already set. Pass `[]` to remove all angles. Each entry is a path/URL to the same avatar from another angle (import local files with `select_avatar_image` first if needed, then collect their paths).
- **Update spoken content** — `avatarScript` or `avatarAudioUrl` only. Do **not** put it in PromptBar.
- **Configure only** — set fields without triggering Create Video.
- **Minimal patches** — pass only requested keys; do not reset unrelated fields.

## Execution sequence

1. **Resolve project** per **SKILL.md** → *Project targeting rules*. Create only with explicit approval via `create_project` with `projectType: "avatar"`.
2. **Read state** (optional): `read_project_settings` → inspect `AVATAR_SETTINGS` and confirm `projectType`.
3. **Avatar image** — `select_avatar_image` (local path) or `save_avatar_image` (data URL). To **generate** a portrait headlessly (same models as the **Avatar Creator** modal), use **`generate_images`** with `imageModel: "gpt-image-2"` or `"nano-banana-2"` and matching **`imageQuality`** (`low` / `medium` / `high` for GPT Image 2.5; `1k` / `2k` / `4k` for Nano Banana 2), then `save_avatar_image` or `select_avatar_image` on the returned path. For path-only updates, set `avatarImage` via `set_avatar_settings`.
   - **Same face from a photo (face references)** — to generate an avatar that must look like a **specific person**, pass up to **3** face photos to `generate_images` via **`referenceImages`** (absolute local paths, http(s) / data / `local-resource://` URLs). With ≥1 reference the same face/identity is preserved (Nano Banana → `image_urls`; GPT Image 2.5 → OpenAI image edits) and `description` is treated as the **scene**, so describe pose/clothing/lighting/background rather than re-describing the face. This is the headless equivalent of the Avatar Creator modal's **"Face reference photos (optional)"** picker.
4. **Avatar angles (optional)** — once `avatarImage` is set, add up to 3 same-avatar angles: `select_avatar_angle_image` per local file, or set the full `avatarAngleImages` array via `set_avatar_settings` for paths/URLs already on disk. With angles present, the render splits the script into sentences and varies the angle per sentence.
5. **Voice and motion** — patch `avatarVoice` and `avatarMotionInstructions` with `set_avatar_settings`. Use `list_elevenlabs_voices` if the user did not name a voice.
6. **Script or audio**:
   - `script` mode → patch `avatarInputMode: "script"` and `avatarScript`.
   - `audio` mode → `save_avatar_audio` / `select_avatar_audio` to install the audio, which also sets `avatarInputMode: "audio"` and `avatarAudioUrl`.
7. **PromptBar (optional)** — `set_user_instructions` only when the user wants auto-edit feature guidance; do not duplicate the script.
8. **Create Video** (only when the user asks for a render):
   - `trigger_create_video` (preferred) or `generate_video`.
   - Poll **`get_video_generation_status`** until terminal. `fetch_app_events` only on request or when debugging.
   - `stop_video_generation` on user request.
9. **Return outcome** — completion status, output path, validation/provider warnings.

## Quick defaults

- `avatarModel`: `Kling Avatar Pro` in the UI's in-memory state — but a brand-new project's disk template writes `Kling`, which canonicalizes to **`Kling Avatar` (std)**, not Pro. Set it explicitly.
- `avatarVoice`: `graham` when the Shorz UI initializes the panel state; `Alice` on a brand-new project that has never been opened (the disk template in `defaultProjectSettings`). Always read `AVATAR_SETTINGS.avatar_voice` to know the current value rather than assuming.
- `avatarInputMode`: `script`
- `avatarScript`: `""`
- `avatarAngleImages`: `[]` (no extra angles; single-image behavior)
- `avatarMotionInstructions`: `""`

## Common failures

- **No output, no error** — a script of 10 characters or fewer (counted raw, untrimmed, script mode only) makes the avatar stage return nothing and the render finishes with no file. The disk placeholder is 45 characters, so it passes that gate and would be spoken aloud — always overwrite it.
- **Pose resets mid-video** — a long script is split at silence to fit the model's per-request window (~29 s OmniHuman, ~60 s Kling) and stitched automatically. Without angles every segment regenerates from the same still, so the pose visibly resets at each seam. Adding angles removes the effect.
- **`.ogg` / `.flac` audio** — `select_avatar_audio` and the desktop picker accept them, but the renderer validates against `.mp3 .wav .m4a .aac .webm` and fails before any conversion. Convert first.

- **`audio` mode without `avatarAudioUrl`** — Save/select audio first, then patch `avatarInputMode`.
- **Invalid `avatarModel`** — Resend with `Kling Avatar`, `Kling Avatar Pro`, or `OmniHuman 1.5`.
- **Script too long** — Trim to ≤ 40000 chars / 6000 words before retrying.
- **Motion instructions too long** — Trim to ≤ 2500 chars.
- **Too many angle images** — `avatarAngleImages` accepts at most **3** entries; trim the array before retrying.
- **PromptBar accidentally filled with the script** — Move spoken text to `avatarScript`; reset PromptBar (set it to a feature-guidance string or clear it via `set_user_instructions` with an empty string).
- **Voice not recognized** — Pick one from `list_elevenlabs_voices` before patching `avatarVoice`.
