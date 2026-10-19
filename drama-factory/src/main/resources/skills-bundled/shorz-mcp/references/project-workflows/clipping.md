# Clipping workflow (project type `clipping`)

Use this when the `projectType` is **`clipping`**: start from **one long source video** and have Shorz produce **one or more shorter clips** (count `1`–`8`). Clip selection is automatic by default; the PromptBar is **optional** and only used to **steer** what gets cut (clip length, topics, platform). **`clipping`** keeps main VIDEO (“Import Main Assets”) enabled in the app — unlike **`avatar`** / **`podcast`** (**SKILL.md**). For a generic edit with B-roll/titles/multiple inputs, use **`auto-edit`** instead. Global rules and routing live in **`../../SKILL.md`**.

## What it looks like

The user opens a clipping project and sees:

- A **single source video** slot (file path or social-video URL) — that's `ASSET_PATHS.main_video_asset_paths` on disk.
- A **clip count** control (`1`–`8`; default `1`) — persisted as `CLIPING.clipping_num_clips` (string, e.g. `"1"`).
- A **Video URL** field that downloads YouTube / TikTok / Facebook / Instagram clips via `download_social_video`.
- An **aspect ratio** selector (default **`9:16`** for vertical short-form).
- A **PromptBar** that is **optional** — when empty, Shorz auto-picks the most interesting moments using transcription of the source video.

**Create Video** runs clipping and saves N short clips to the project output. There is **no** dedicated `set_clipping_settings` MCP tool; you patch `CLIPING` and `ASSET_PATHS` via `update_project_settings`, and `VIDEO_SIZE` via `switch_project_aspect_ratio`.

## Tool contract

| Concern | MCP tool | Notes |
|---|---|---|
| Source video — local file | `import_frontend_assets` with `assetType: "video"` and `overridePaths` | Persists to `ASSET_PATHS.main_video_asset_paths` when project is open. |
| Source video — social URL | **`download_social_video`** | `url` plus optional `platform` (`auto` \| `youtube` \| `tiktok` \| `facebook` \| `instagram`). `auto` detects from the URL. **Async by default:** returns `started: true`, then poll **`get_social_video_download_status`** for `localFilePath`. |
| Download status | **`get_social_video_download_status`** | Poll until `lastStatus` is terminal (`completed` \| `error`). On success returns `localFilePath` + file metadata. |
| Set source path | **`update_project_settings`** with `updates: { ASSET_PATHS: { main_video_asset_paths: "<path>" } }` | Clipping is one-source only — write a **single path string** (overwrite, do not append). |
| Remove source from project | **`update_project_settings`** with `updates: { ASSET_PATHS: { main_video_asset_paths: "" } }` | Clears VIDEO / main asset slot only; does not delete the file on disk (`delete_asset` only if user asks). See **`../panel-workflows/your-library-assets.md`**. |
| Clip count | **`update_project_settings`** with `updates: { CLIPING: { clipping_num_clips: "<\"1\"..\"8\">" } }` | String, not number. |
| Aspect ratio | **`switch_project_aspect_ratio`** (`projectPath`, `aspectRatio`) | `9:16` (default) \| `1:1` \| `16:9`. Optional `fps`. |
| PromptBar text (optional) | `set_user_instructions` | Persisted as `UI_SETTINGS.user_input_instructions`. |
| Create Video | **`trigger_create_video`** (preferred) | Accepts `userInstructionsOverride` — pass `""` for automatic interesting clipping without using saved PromptBar text. |
| Status | **`get_video_generation_status`** | Authoritative for project renders. |
| Cancel | `stop_video_generation` | |

**Supported `download_social_video` URLs** (matches the Clipping panel's *Video URL* field): YouTube, TikTok, Facebook (reels, `fb.watch`), Instagram (reel, `/p/`, `/tv/`, `share/reel`, etc.) — valid video/post URL shapes only. **Not supported:** X, generic hosts, arbitrary profile pages → ask the user for a local file plus `import_frontend_assets`.

### Persistence oracle

After every patch, confirm with `read_project_settings` and inspect:

| Field | Expected |
|---|---|
| `ASSET_PATHS.main_video_asset_paths` | the selected source video path (string) |
| `CLIPING.clipping_num_clips` | `"1"`..`"8"` |
| `VIDEO_SIZE.video_width` / `VIDEO_SIZE.video_height` (stringified ints) | matches the requested aspect ratio |
| `UI_SETTINGS.user_input_instructions` | PromptBar text (empty string if you cleared it) |

Then verify the source file actually exists on disk with **`file_exists`** on `ASSET_PATHS.main_video_asset_paths`. **Do not** call `get_video_assets` to verify the source — that lists **My Assets → AI-generated videos**, not the project's main timeline media (see **SKILL.md** → *Asset verification*).

## Instruction handling rules

- **Source-media gate** — Clipping requires one long source video. If the user has not provided a local path or a supported URL, **ask them to provide one** and stop. Do not import, download, patch `ASSET_PATHS`, or trigger Create Video without an input video.
- **Clip count default `1`** — Use `"1"` whenever the user does not state a count. Only set `"2"`..`"8"` when they explicitly request multiple clips. Never escalate count from silence.
- **Aspect ratio default `9:16`** — Clipping is short-form by default. Switch to `1:1` or `16:9` **only** when the user explicitly asks for square or landscape clips.
- **PromptBar is optional** — Add text only when the user wants to steer:
  - **Clip length** — e.g. "~30 seconds," "under 60 seconds," "15–20 second cuts," "one longer ~90s highlight." There is no separate MCP duration field; put this in PromptBar.
  - **Platform / short-form targets** — TikTok, Reels, Shorts, hooks (often implies length caps). Do **not** put aspect-ratio tokens or pixel dimensions here (**SKILL.md** → *Output framing*); use **`switch_project_aspect_ratio`** for export shape.
  - **Topics, beats, sections** — "only the product demo," "funny moments," "the Q&A part."
  - **Tone or hooks** that the default pass would not infer.
- **No steering text → empty override** — Do not persist saved PromptBar text by accident. When the user wants the default auto-interest pass, call `trigger_create_video` with `userInstructionsOverride: ""` so any old `UI_SETTINGS.user_input_instructions` is ignored for this run.
- **Replace source** — Import or download the replacement first, then **overwrite** `ASSET_PATHS.main_video_asset_paths` with the new path (single string; clipping is one-source).
- **Configure only** — Patch settings without triggering Create Video.
- **Minimal patches** — `update_project_settings` deep-merges `updates`; pass only the nested keys you change. Do not re-read and rewrite the full `settings.json`.

## Execution sequence

1. **Resolve project** per **SKILL.md** → *Project targeting rules*. Create only with explicit approval via `create_project` with `projectType: "clipping"`.
2. **Source-media gate** — If no local path and no URL from the user, ask and stop.
3. **Get the source onto disk:**
   - Local file → `import_frontend_assets` with `assetType: "video"`.
   - Supported social URL → `download_social_video` with `platform: "auto"` (or an explicit platform that matches the URL). It returns as soon as the job starts — poll **`get_social_video_download_status`** until `lastStatus` is `completed` (or `error`) and take `localFilePath` from that.
   - Patch `ASSET_PATHS.main_video_asset_paths` with the returned absolute path via `update_project_settings`.
   - Verify with `file_exists`.
4. **Clip count** — `update_project_settings` with `{ "CLIPING": { "clipping_num_clips": "<value>" } }`. Default `"1"` unless the user asked otherwise.
5. **Aspect ratio** — `switch_project_aspect_ratio` to `9:16` for typical clipping; only `1:1` / `16:9` on explicit request. Skip if already correct.
6. **PromptBar (optional)**:
   - User gave steering text → optionally `set_user_instructions` for UI parity.
   - No steering → do not persist text.
7. **Create Video** (when requested):
   - If the user requested a specific main LLM, `set_main_ai_model` or pass `mainAiModelName` on `trigger_create_video`. Current lineup snapshot (seven): `anthropic/claude-opus-5-5` (default), `anthropic/claude-fable-5-1`, `anthropic/claude-sonnet-5-5`, `openai/gpt-6-1-sol`, `openai/gpt-6-luna`, `openai/gpt-6-astra`, `google/gemini-3.8-flash` — call `list_main_ai_models` for the live list. **On a free-tier run** (zero-balance account; `clipping` is one of the two eligible types) only **`google/gemini-3.8-flash`** is zero-rated, and the MCP path does **not** pin it for you — set it here or the render bills and 402s mid-way. The **30-minute source cap** matters most here (clipping sources are long) and is *not* checked when the render starts from MCP: probe the source with `get_media_info` first. See **SKILL.md** → *Keys and auth dependencies* for the paid steps to leave off (AI b-roll, dubbing/auto-music/noise removal, thumbnails, publishing — Auto SoundFX and Assets/WEB/GIF/emoji b-roll are free).
   - `trigger_create_video` with `userInstructionsOverride` set to the user's steering text **or** `""` for the default auto-interest run.
   - Poll **`get_video_generation_status`** until terminal. Use **`fetch_app_events`** only on request or when debugging (see **SKILL.md** → *Event stream*).
   - `stop_video_generation` on user request.
8. **Return outcome** — success/error, clip output paths, any warnings (e.g. poor source quality, insufficient source length).

## Imported music across multiple clips

Clipping runs the whole effects chain — including the music stage — **once per exported clip**, so imported music behaves per clip, not across the batch:

- **Every clip gets the music from the start of the music.** The tracks do not continue where the previous clip left off, and the music is not split across clips.
- **Placement is resolved against each clip's own duration.** "Start the music at 5 seconds" applies inside every clip; "music over the last 10 seconds" lands in each clip's own final 10 seconds, even though the clips have different lengths.
- **The music plan is derived once** (one LLM pass for the whole render) and reused for every clip, so all clips get the same order, sections, volume, fades and mix mode.
- Any number of tracks is allowed (they play back to back, in lane order) — arrangement vocabulary is in **`auto-edit.md`** → *Imported music*. Beat-synced **cutting** does not apply to clipping (multi-asset `auto-edit` only); clip boundaries come from the segment planner.

## Quick defaults

- **Aspect ratio:** `9:16` (vertical short-form). Use `switch_project_aspect_ratio` to apply.
- **Clip count:** `"1"` (`CLIPING.clipping_num_clips`). Only change when the user specifies `2`..`8`.
- **Source path:** `ASSET_PATHS.main_video_asset_paths` must point to the selected long video.
- **PromptBar:** none. For the default automatic pass, `trigger_create_video` with `userInstructionsOverride: ""`.

## Common failures

- **No source path or URL** — Ask the user to supply a local long-video file or a supported URL before touching settings.
- **`get_video_assets` returns nothing useful for verification** — Expected. That tool lists library AI-generated videos, not the project source. Verify with `read_project_settings` (`ASSET_PATHS.main_video_asset_paths`) + `file_exists`.
- **Clip count normalization** — Sending `clipping_num_clips` via `update_project_settings` does **not** hard-fail: Shorz normalizes/clamps on write (non-numeric ⇒ `"1"`; integers outside **1–8** ⇒ clamped to **1–8**). Persist with `read_project_settings` afterward to confirm the saved string.
- **URL not supported by `download_social_video`** — Ask the user for a local file and import it instead. Do not insist on URL-only flows.
- **`download_social_video` behavior looks wrong** (stale platform errors after MCP updates) — Restart the MCP server / Cursor MCP connection so it loads the current `mcp-server` code.
- **Trying to set aspect ratio via `update_project_settings`** — Prefer `switch_project_aspect_ratio`; it writes `VIDEO_SIZE` correctly (width/height and optional `fps`).
- **Generation appears stalled** — `get_video_generation_status` first; `fetch_app_events` only if status is unclear.
