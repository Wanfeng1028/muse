# Your Library assets workflow (`update_project_settings` on `ASSET_PATHS`)

Use when the user asks to **remove**, **clear**, or **delete** imported items in the project **Your Library** panel (segmented tabs **VIDEO**, **BROLL**, **SOUND**, **MUSIC**). Global rules: **`../../SKILL.md`** → *Removing imported project assets* and *Main VIDEO import*.

## What it looks like

In the app, **Your Library** shows four lanes under the preview (labels in the UI vs internal keys):

| UI tab label | Internal key | `import_frontend_assets` `assetType` | `ASSET_PATHS` field on disk |
|---|---|---|---|
| **VIDEO** | `VIDEOS` | `video` | `main_video_asset_paths` |
| **BROLL** | `BROLL` | `broll` | `broll_video_asset_paths` |
| **SOUND** (sound effects) | `SOUND` | `sound` | `audio_fx_asset_paths` |
| **MUSIC** | `MUSIC` | `music` | `music_asset_paths` — **any number of tracks**; several tracks play back to back in lane order, and the PromptBar can reorder them, trim each one, and place the music on the timeline (see `../project-workflows/auto-edit.md` → *Imported music*). In multi-asset `auto-edit`, imported music also unlocks beat-synced cuts when the PromptBar asks for them (*Music beat sync* in the same file) |

Trash on a card in this panel **only removes the asset from the project** (React state → saved paths). It does **not** call `delete_asset` and does **not** delete the file from disk unless the user separately asks to erase the file.

**Importing into these lanes is free for everyone** — `import_frontend_assets` and `ASSET_PATHS` patches spend no credits, at any balance. Every lane now shows the same three buttons: **IMPORT**, **SEARCH**, and **GENERATE**.

**SEARCH is free and ungated on all four lanes.** SOUND and MUSIC search public-domain (CC0) audio via Openverse — no credits and no sign-in, and results carry no attribution obligation (MCP: `openverse_search_sound_effects`, `openverse_search_music`, `download_openverse_audio`; see `../headless-workflows/openverse-audio.md`). BROLL and MAIN ASSETS search Pexels stock — no credits, but sign-in required because the key lives on the proxy (MCP: `pexels_search_photos`, `pexels_search_videos`; see `../headless-workflows/pexels-stock-media.md`). The BROLL lane additionally offers **GIFs** and **Stickers** toggles that search GIPHY (same terms: free, signed in) and save the pick into Downloaded GIFs as an `image/gif` b-roll asset; a sticker's transparent background is kept at render time, so it composites as a cut-out over the video (MCP: `giphy_search_gifs`, `giphy_search_stickers`, `download_giphy_gif`, then `import_frontend_assets` with `assetType: "BROLL"`; see `../headless-workflows/giphy-gifs-stickers.md`). MAIN ASSETS stays Pexels-only — a GIF is never a main video.

**GENERATE is the paid path** on all four lanes and is gated for zero-balance users; over MCP its equivalents (`generate_images`, `generate_scene_image`, `generate_image_to_video`, `download_generated_music`'s upstream generation) 402 instead, and a free `auto-edit` / `clipping` run does not cover them. When a user says a library button "costs nothing", they mean SEARCH; when they say it "costs credits", they mean GENERATE.

The MUSIC generate panel has **Generate / History** tabs: History lists the tracks made by the in-app generator and by render-time auto-music (`auto_music_*` files in the app's `Generated_Audio` cache, named `auto_music_<prompt-slug>__<generation-id><ext>` — `.mp3` from ElevenLabs Music, `.wav` from Lyria 2, matching the bytes) and re-adds one to the project **for free**. Tracks fetched over MCP with `download_generated_music` are saved as `<timestamp>_<name>.mp3` and do **not** appear in that tab — check `get_audio_assets` before concluding a track doesn't exist. The MCP equivalent of a History re-add is `get_audio_assets` (filter names starting `auto_music_`) → `import_frontend_assets` with `assetType: "music"` **and `overridePaths: ["<absolute path>"]`** (without `overridePaths` the tool opens a native file dialog and hangs headless runs) — never re-generate a track the user already paid for.

**VIDEO** is hidden or disabled for some `projectType`s (`avatar`, `podcast`, `advertisement`, `music-video`, `text-to-video` without `imported` source). Do not clear `main_video_asset_paths` when the UI would not show that tab — see **`../../SKILL.md`** → *Main VIDEO import*. **MUSIC** is hidden in `music-video` projects: the song is the only audio and lives in `MUSIC_VIDEO.music_video_audio_path` (`select_music_video_audio`), not in a lane.

## Two different “delete” meanings

| User intent | MCP approach |
|---|---|
| **Remove from this project** (empty a tab, drop one import, “delete main video asset”) | **`update_project_settings`** — clear or rewrite the matching `ASSET_PATHS.*` comma-separated path string. **Default.** |
| **Delete the file from disk** (My Assets inventory, free disk space) | **`delete_asset`** with absolute `filePath` — **destructive**; confirm first. Also removes the file everywhere it lived on disk; does not automatically rewrite every project’s `settings.json` if paths were copied manually. |

Do **not** use `delete_asset` when the user only wants the project slot cleared (e.g. clipping source removed but keep `HLtkEY_K8RY.mp4` on Desktop).

## Tool contract

| Action | Tool | Notes |
|---|---|---|
| Read current paths | `read_project_settings` | Inspect `ASSET_PATHS.*` |
| Clear **all** items in one lane | `update_project_settings` | `updates: { ASSET_PATHS: { <field>: "" } }` |
| Remove **one** path, keep others | `update_project_settings` | Read field → split on `,` → trim → drop matching path(s) → rejoin with `,` |
| Replace lane contents | `update_project_settings` | Overwrite field with new comma-separated string (same as import flow). Repeated file names in the value you write are collapsed to the first and reported in `duplicateAssetNamesDropped` — see *One asset per file name* |
| Verify lane empty | `read_project_settings` | Field is `""` or whitespace-only |
| Delete file on disk | `delete_asset` | Only after explicit user confirmation |

Paths are stored as a **single comma-separated string** per field (same as Python `load_project_assets_from_settings`). Multiple VIDEO/BROLL clips in `auto-edit` can be several paths in `main_video_asset_paths`. **MUSIC behaves the same way** — `music_asset_paths` holds any number of comma-separated tracks, and they play **back to back in that order** unless the PromptBar reorders them. **Clipping** uses **one** source path only — clearing means `""`, not a list.

**Not cleared** by lane removal: `ASSET_PATHS.last_generated_final_video_for_playback_mode`, `UI_SETTINGS.playback_history_video_paths`, or My Assets library caches. Mention that if the user still sees an old render in Playback.

## Instruction handling rules

1. **Resolve project** — `get_current_open_project` or user-named path via `list_projects`.
2. **Map words to fields** — “main video” / “import main assets” / “source video” → `main_video_asset_paths`; “b-roll” → `broll_video_asset_paths`; “sound” / “sfx” / “audio effects” → `audio_fx_asset_paths`; “music” / “background music” → `music_asset_paths`.
3. **Clear whole tab** — one `update_project_settings` patch with `""` for that field.
4. **Remove specific file** — `read_project_settings`, normalize paths (trim, compare case-insensitively on Windows if needed), rebuild comma list without that entry, patch back. If the path is not in the field, say so; do not call `delete_asset` unless asked.
5. **Confirm** with `read_project_settings` after the patch. The app live-syncs on `update-project-settings` MCP activity.
6. **Project-type gates** — before clearing VIDEO, check **`../../SKILL.md`**; for clipping, clearing source blocks Create Video until a new import/`download_social_video`.

## Import sequence (assign to project lanes)

`import_frontend_assets` with `overridePaths` validates files, **persists to the open project's `ASSET_PATHS`**, and triggers UI refresh (same outcome as Your Library import). One call for library lanes (`video`, `broll`, `sound`, `music`, `audio`). **`video` is gated by project type**: headless imports into a project without the main VIDEOS lane (`avatar`, `podcast`, `advertisement`, `music-video`, `text-to-video` without `imported` source) are **rejected with an error** — use `broll` for supporting footage there. **`music` is rejected in `music-video` projects** (no MUSIC lane — set the song with `select_music_video_audio`).

1. Confirm target project is open (`get_current_open_project`).
2. `import_frontend_assets` — `assetType`: `video` | `broll` | `sound` | `music`; `overridePaths`: absolute paths from disk.
3. **Read `skippedCount` in the result** (see *One asset per file name* below) — a non-zero count means those files are **not** in the project.
4. `read_project_settings` — optional verify; UI live-syncs on `import-assets` MCP activity.

**Not library lanes:** `image` / `avatar` still return metadata only — patch via `set_advertisement_settings`, `select_avatar_image`, etc.

**Manual override:** `update_project_settings` on `ASSET_PATHS` remains available to replace or clear lanes without importing files.

## One asset per file name (per lane)

A lane holds **at most one asset per file name**, compared case-insensitively with the folder ignored. The **backend** addresses assets by basename: PromptBar `@mentions` match on bare filenames, the Python render maps are keyed on basename (with a `name (2).ext` uniquifier for exactly this collision), and `render_music` / `render_sound_effects` resolve LLM-chosen tracks by file name — a music trim then applies to every path sharing that basename. So two same-named entries are ambiguous no matter which folders they came from, and the renderer's asset ids do not help: they are lane- plus path-derived and renderer-only. This is the **same rule the UI applies** to its Import button, drop zone, PromptBar import menu and My Assets "add to library"; MCP and the UI cannot disagree.

The rule is **per lane, not per project** — the same file may legitimately sit in both VIDEO and BROLL.

Enforced on both write surfaces, each against the state it writes into:

| Surface | What is compared | What you get back |
|---|---|---|
| `import_frontend_assets` (`overridePaths`) | Incoming files vs. the lane **on disk**, plus repeats inside one call | `{ success, assetType, persistedToLane, importedCount, imported[], skippedCount, skipped[], note? }` — `imported` holds only what actually landed. Each `skipped` entry is `{ filePath, name, reason }` with reason `duplicate-name`, `already-in-lane`, or `unsupported-extension` (sound/music accept `.mp3`/`.wav`/`.m4a`/`.ogg` only). |
| `update_project_settings` on a lane field | Repeats **within the value you write** (the patch replaces the field, so there is no prior content to compare) | `duplicateAssetNamesDropped: [{ field, filePath, name }]` plus a `note`, present only when something was dropped. Lanes the patch does not touch are untouched — a project that predates the rule never loses entries to an unrelated write. |

**Nothing is overwritten and nothing errors** — the newcomer is skipped and the existing entry stays. If you actually need both files, **rename one and import again**. This matters most right after a paid generation: the credits are already spent, so never assume a file landed — check `skippedCount`.

In practice collisions are rare in automation because app-generated media is written with a `<timestamp>_` prefix. They show up when an external script writes fixed names (`shot-01.png`, `scene1.mp4`) into per-run folders and two runs feed the **same** project. Name files per run (`08-reuters-brin-rsi-quote.png`) and the question never arises.

**Belt-and-braces imports** (`import_frontend_assets` followed by an explicit `ASSET_PATHS` patch of the same list) stay safe: the patch self-dedupes by name, so a lane cannot end up holding a duplicate the import step just skipped.

## Removal sequence

1. `get_current_open_project` (or resolve named project).
2. `read_project_settings` → note relevant `ASSET_PATHS` fields.
3. Apply `update_project_settings` with minimal `updates.ASSET_PATHS` patch (`""` to clear a lane, or edited comma list for one file).
4. `read_project_settings` again to verify.
5. Tell the user which lane was cleared and that **files on disk are unchanged** unless they requested `delete_asset`.

## Common failures

- **Used `delete_asset` for “remove from project”** — Wrong default; file may be gone from disk while user only wanted the slot empty.
- **Used `get_video_assets` to see project VIDEO lane** — Library tool only; use `read_project_settings` → `main_video_asset_paths`.
- **Cleared VIDEO on `avatar` / `podcast`** — Tab hidden; path may be stale but not what the UI shows — still safe to clear if user insists on cleaning disk settings.
- **Clipping: left old path in PromptBar-only workflows** — Source is `ASSET_PATHS`, not PromptBar; clear `main_video_asset_paths`.
- **Reported an import as done without reading `skippedCount`** — `success: true` with `importedCount: 0` means every file was skipped as a duplicate name. Render then runs without them. Always report what landed, not what was sent.
- **Assumed two same-named files can share a lane** — They cannot, on any surface. Rename one first; patching `ASSET_PATHS` by hand does not get around it.
- **Playback still shows old export** — Expected; playback path is a separate key.
