# Cross-project panel workflows (MCP)

These files are agent-operational instructions for shared Shorz sidebar panels. **Cross-project ≠ always-on:** Which library tabs appear and whether **main VIDEO (“Import Main Assets”)** applies depends on **`projectType`** (`App.tsx`, `MediaPanel.tsx`) — see **`../../SKILL.md`** → *Main VIDEO import (“Import Main Assets”) vs project type*. Global rules — project targeting, PromptBar semantics (no aspect ratio or width/height in PromptBar — **`../../SKILL.md`** → *Output framing*), asset verification, main-video gates, event polling, destructive actions — live in **`../../SKILL.md`**. Per-`projectType` end-to-end flows live in **`../project-workflows/`**. Headless MCP-only file tools live in **`../headless-workflows/`**.

## Handbook layout

Every workflow file in this folder follows the same section order when applicable. **`border.md`** is the canonical template:

1. **Title** — `# <Panel> workflow (\`<primary tool>\`)`
2. **What it looks like** — user-visible behavior in the preview/panel/export
3. **Tool contract** — primary MCP tool(s), arguments, supported keys table, enums "copy verbatim", persistence paths via `read_project_settings`
4. **Instruction handling rules** — minimal patches, intent routing, configure-only vs render
5. **Execution sequence** — numbered steps (project resolution → tool calls → optional Create Video)
6. **Panel-specific sections** — only where needed (animations, stepping, async polling)
7. **Common failures** — validation errors, clamp vs reject, recovery

## Files

- `settings.md` — General Video / Auto Zoom (`set_general_video_settings`)
- `broll.md` — B-roll / GIF / web / AI / emoji (`set_broll_settings`)
- `audio.md` — Audio / mix / dubbing (`set_audio_settings`)
- `overlay.md` — Overlays (`set_overlay_settings`, plus `get_overlay_effects` / `import_overlay_effects` / `delete_overlay_effect`)
- `border.md` — Border (`set_border_settings`)
- `subtitle.md` — Subtitles / captions (`set_subtitle_settings`)
- `title.md` — Title / headline (`set_title_settings`)
- `thumbnail-creator.md` — Thumbnail Creator modal (`open_thumbnail_creator`, `set_thumbnail_creator_settings`, `thumbnail_creator_generate`, `get_thumbnail_creator_generation_status`, …)
- `animation-studio.md` — Animation Studio (`animation_studio_*`, compile / export)
- `canvas.md` — Canvas node-graph video builder (`canvas_list`, `canvas_get`, `canvas_build`, `canvas_remove`, `canvas_run`, `canvas_stop`, `canvas_pick_take`, `canvas_duplicate`, `canvas_rename`, `canvas_delete`); no project needed
- `your-library-assets.md` — Your Library VIDEO / BROLL / SOUND / MUSIC — remove or clear imported project lanes (`ASSET_PATHS` via `update_project_settings`)

## Text panel routing (one sidebar, two MCP tools)

The **Text** sidebar in the app shows subtitles and titles together, but Shorz exposes **two** validated tools with **different key families** (`subtitle*` vs `title*`). There is **no** separate `text.md` skill.

- **Captions / subtitles / transcript-style wording** → `set_subtitle_settings` only.
- **Title / headline / banner text** → `set_title_settings` only (`titleText` is plain text; optional inline Unicode emoji supported — see **`title.md`**).
- **Both** → call each tool once with a minimal patch and return a split summary.
- **Never** mix key families across tools.
- **Emoji disambiguation:** timed transcript emoji overlays → **`broll.md`** / `automaticEmojis`. Emoji **inside the title headline** → **`titleText`** in **`title.md`** only.
- **B-roll overlay position:** center-X / top-Y % via `set_broll_settings` (`brollPositionX/Y`, `webImagesPositionX/Y`, `gifPositionX/Y`, `aiBrollPositionX/Y`). Full details in **`broll.md`**.

## Library and cross-cutting MCP tools (all project types)

Some tools are **not project-scoped at all** — they work without `create_project`, settings, or Create Video. See **`../headless-workflows/`** for the full list. The main example:

- **Single-asset deterministic edits** — `trim_video`, `remove_audio`, `set_audio_volume`, `change_video_speed`, `set_image_duration`, `rotate_media`, `flip_media`, `reverse_video`, `loop_video`, `fade_video`, `freeze_frame`, `crop_media`, `audio_fade`, `remove_silence`, `edit_image_with_ai`, `get_media_info`, `resize_media`, `fit_to_aspect`, `extract_audio`, `replace_audio`, `concat_media`, `extract_video_frames` (22 tools). Operate on local files; **separate from every `projectType`**. Workflow: **`../headless-workflows/single-asset-edit.md`**.

The sections below cover **My Assets library** and imports that may optionally tie into a project.

### Search and list My Assets

These tools mirror the **My Assets** library in the app. They are **not tied to the current project**: the user can ask to list or search assets anytime (inventory, pick a path, verify a download, etc.). Shorz must be running with the MCP bridge active.

**Per-tab listing (no arguments)** — each returns a JSON **array** of items (newest first). Use when you need the **full** contents of one tab or a simple dump.

| Tool | Tab / meaning |
|------|----------------|
| `get_my_videos` | Final exported videos ("MY VIDEOS") |
| `get_video_assets` | AI-generated videos |
| `get_image_assets` | AI-generated images |
| `get_generated_thumbnails` | Thumbnail Creator output cache |
| `get_audio_assets` | Generated / TTS / sound-effect audio |
| `get_downloaded_gifs` | Downloaded GIFs |
| `get_downloaded_images` | Downloaded still images |

Typical fields on each item (for automation): `name`, `id`, `filePath` (absolute disk path), `url` (`local-resource://…`), `type` (`video` \| `image` \| `audio`), `mimeType`, `size` / `sizeBytes`, `date`, `dateModified` (ISO). Video rows from **my videos** and **video assets** also include `youtubeUploaded` / `tiktokUploaded` booleans. Video previews use `local-resource://` URLs; use `filePath` when a plain path is required for another tool.

**Important:** these list **library** assets — they do **not** list a project's main/timeline video. For project-scoped source media (e.g. the clipping main video), read `ASSET_PATHS.*` via `read_project_settings` and verify with `file_exists`. See **SKILL.md** → *Asset verification*.

**`get_available_fonts`** — separate from My Assets: returns a list of font family names for settings that reference fonts.

**Filtered / cross-tab query** — **`query_my_assets`** (single call, optional filters):

- **`categories`** — Optional array of: `my_videos`, `video_assets`, `image_assets`, `generated_thumbnails`, `audio_assets`, `downloaded_gifs`, `downloaded_images`. Omit or pass an empty array to include **all** tabs (same as listing every category).
- **`nameQuery`** — Optional substring match (case-insensitive) against file **name**, **id**, and **filePath**.
- **`modifiedAfter`**, **`modifiedBefore`** — Optional ISO datetimes; inclusive window. Invalid ISO or `modifiedAfter` > `modifiedBefore` returns `success: false` with an error message.
- **`limit`** — Optional integer **1–1000**; default **100**. `totalMatches` is the full count after filters; the response includes at most `limit` rows, sorted by modified time (newest first).

Response shape: `{ success, filters, totalMatches, returnedCount, items }`. Each item includes the same fields as the per-tab tools plus `assetCategory` and `modifiedTimestampMs`.

**When to use what**

- User wants to **find** files by name, date, or across several tabs → **`query_my_assets`**.
- User wants a **complete list** of one tab → matching **`get_*`** tool.
- After listing, use `file_exists` / `open_file_directory` / upload or project tools as needed; confirm before **`delete_asset`** or **`rename_asset`** (destructive).

### Removing project Your Library assets (VIDEO / BROLL / SOUND / MUSIC)

This is **not** the My Assets modal inventory — it is the **per-project** lanes under Your Library in the editor (comma-separated paths in `settings.json` → `ASSET_PATHS`).

| UI tab | `ASSET_PATHS` field |
|---|---|
| VIDEO | `main_video_asset_paths` |
| BROLL | `broll_video_asset_paths` |
| SOUND (sound FX) | `audio_fx_asset_paths` |
| MUSIC | `music_asset_paths` |

- **Remove from project (default):** `update_project_settings` with `updates: { ASSET_PATHS: { <field>: "" } }` to clear a lane, or read → edit comma-separated paths → write back to drop one file. See **`your-library-assets.md`**.
- **Delete file on disk:** `delete_asset` — only when the user explicitly wants the file gone; confirm first. Does not replace patching `ASSET_PATHS` for “unassign from project.”

### Imports and downloads

- **`import_frontend_assets`** — Headless import: `assetType` must be one of `video`, `broll`, `sound`, `music`, `image`, `avatar`, `audio`; optional `overridePaths`. Library lanes persist to `ASSET_PATHS` and sync Your Library when the project is open.
  - **`assetType: "video"`** (main timeline / **Import Main Assets**): Only where the **shipped UI** exposes that lane (**SKILL.md** → *Main VIDEO import* — e.g. `auto-edit`, `clipping`, `text-to-video` with **`imported`** source media). Headless imports into `avatar`/`podcast`/`advertisement`/`music-video` (or non-`imported` text-to-video) are **rejected with an error** — use `"broll"` there. `music-video` also rejects `assetType: "music"`: its song is set with `select_music_video_audio` (`../project-workflows/music-video.md`). For **`advertisement`**, default flow uses **`image`** + advertisement panel tools (`../project-workflows/advertisement.md`), not timeline video.
- **`download_social_video`** — `url` plus optional `platform`: `auto` \| `youtube` \| `tiktok` \| `facebook` \| `instagram` (same URL rules as the Clipping panel / My Assets download). **Async by default:** returns `started: true`, then poll **`get_social_video_download_status`** for `localFilePath` and metadata. `awaitCompletion: true` blocks instead, but YouTube extraction commonly exceeds the MCP request timeout — prefer the poll.
- **`generate_images`** — Standalone AIML image generation **without** opening Thumbnail Creator or Avatar Creator; returns saved local paths under Shorz assets. Distinct from `thumbnail_creator_generate` (modal workflow); see `thumbnail-creator.md` vs generation needs. **`imageModel`:** **`gpt-image-2`** (default) \| **`nano-banana-2`** \| **`nano-banana-2-lite`** (cheaper/faster Nano variant — **never the default**; pass it explicitly). **`imageQuality`:** with **`gpt-image-2`** use **`low`** \| **`medium`** \| **`high`** (default **`medium`**); with **`nano-banana-2`** / **`nano-banana-2-lite`** use **`1k`** \| **`2k`** \| **`4k`** (default **`1k`**). Matches the Avatar Creator and Thumbnail Creator GPT Image 2.5 quality chips.
- **`generate_scene_image`** — Standalone still via the **Python** text-to-video image stack (same models as `textToVideoImageModel`). Supports reference images (max 3), `aspectRatio` or explicit dimensions. Does not patch project settings.
- **`generate_image_to_video`** — Standalone clip via the **Python** i2v stack; requires local `imagePath`, `prompt`, and explicit `videoModel` (Gemini Omni 1.1 Flash, Seedance 2.5, the Seedance 2.0 family, Kling v3 — **not** the retired `google/veo-*` ids, and **not** `custom:happyhorse-1.0`, which still passes MCP validation but has a disabled catalog row and fails at generation time). Does not run Create Video or alter timelines.
- **Async by default:** `generate_images`, `generate_scene_image`, `generate_image_to_video`, `download_generated_video`, and `download_generated_music` return `{ started, jobId }` immediately — poll **`get_job_status { jobId }`** until `lastStatus` is `completed` (`result` = the tool's normal payload; `outputPaths` = absolute saved files) or `error`. `awaitCompletion: true` restores the blocking form. Never re-call a paid generation because a poll timed out — the job is still running and a retry bills again.

### Interactive vs headless image picking

- **`select_local_image_for_import`** — **Opens an OS file dialog**; requires user interaction. Pass `options` (`{ title?: string; extensions?: string[] }`; extensions omit the leading `.`). Returns `{ success, filePath, fileName, canceled }` — use `filePath` with the headless `select_*` tools below.
- **Project-scoped `select_*` tools** (e.g. `select_avatar_image`, `select_advertisement_image`) — **Headless**: pass absolute `imageFilePath`. Documented per workflow under `../project-workflows/avatar.md`, `podcast.md`, `advertisement.md`. The music video tools (`select_music_video_audio`, `select_music_video_character_image`) take `filePath` instead and copy by path — `../project-workflows/music-video.md`.

### Path checks

- **`file_exists`**, **`get_local_file_size`**, **`open_file_directory`** — Validate paths and reveal folders before/after operations (see `../../SKILL.md`).
