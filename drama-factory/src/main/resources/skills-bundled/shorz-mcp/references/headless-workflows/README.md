# Headless workflows (MCP)

These workflows operate on **local files or global app state** and do **not** require a Shorz project, `projectType`, `read_project_settings`, Create Video, or PromptBar.

They are **separate from every project type** (`auto-edit`, `text-to-video`, `avatar`, `podcast`, `advertisement`, `clipping`, `music-video`). No `create_project` step, no `ASSET_PATHS` patch, and no `trigger_create_video` — unless the user later asks to import the result into a project.

Global prerequisites (Shorz running, MCP connected, `file_exists` on input paths) live in **`../../SKILL.md`**.

**The free tier never covers these tools.** A weekly free run is a *lease around one project render*; nothing here runs inside that lease, so every paid headless tool (`edit_image_with_ai`, `x_search`, and the standalone generation tools) bills as usual and **402s at zero balance** — even while a free `auto-edit` / `clipping` render is in flight. The genuinely credit-free ones are the FFmpeg/PIL edits, `get_media_info`, the Pexels and GIPHY tools, and the Openverse audio tools (which do not even need sign-in). See **`../../SKILL.md`** → *Keys and auth dependencies*.

## Files in this folder

- `single-asset-edit.md` — deterministic trim / crop / speed / volume / rotate / fade / aspect fitting / concat / extract or replace audio / probe media / extract still frames / remove silence / AI image edit on local files. Tools: `trim_video`, `remove_audio`, `set_audio_volume`, `change_video_speed`, `set_image_duration`, `rotate_media`, `flip_media`, `reverse_video`, `loop_video`, `fade_video`, `freeze_frame`, `crop_media`, `audio_fade`, `remove_silence`, `edit_image_with_ai`, `get_media_info`, `resize_media`, `fit_to_aspect`, `extract_audio`, `replace_audio`, `concat_media`, `extract_video_frames`.
- `pexels-stock-media.md` — search the free Pexels stock photo/video library by keyword and get direct media URLs + metadata, with quality / file-type / width-height / duration filtering. Tools: `pexels_search_photos`, `pexels_search_videos`, `pexels_curated_photos`, `pexels_popular_videos`, `pexels_get_photo`, `pexels_get_video`. Requires being **signed in to Shorz** (the API key lives on the proxy). Not tied to any project, panel, or `projectType`.
- `giphy-gifs-stickers.md` — search GIPHY GIFs (opaque animated clips) and **stickers** (transparent-background cut-outs) by keyword, browse the trending feeds, fetch one by id, and download a pick into Downloaded GIFs for use as b-roll. Tools: `giphy_search_gifs`, `giphy_search_stickers`, `giphy_trending_gifs`, `giphy_trending_stickers`, `giphy_get_gif`, `download_giphy_gif`. Requires being **signed in to Shorz** (the API key lives on the proxy); free, no credits. `rating` defaults to `g`. Not tied to any project, panel, or `projectType`.
- `openverse-audio.md` — search **CC0 / public-domain** sound effects and background music, then download a pick into the audio library. Tools: `openverse_search_sound_effects`, `openverse_search_music`, `download_openverse_audio`. **No sign-in, no Shorz credits** — Openverse is a keyless public API, so these are the only search tools that work signed out. Results are public domain: the user owes **no attribution in their video**. Not tied to any project, panel, or `projectType`.
- `x-search.md` — live X (Twitter) search in natural language: posts, news, people, trends, media, with handle allow/exclude lists, date range, and image/video understanding. A server-side Grok agent (xAI x_search) runs the searches and answers with citations (x.com post URLs). Tool: `x_search`. Requires being **signed in to Shorz** and **spends Shorz credits** (tokens + per-search fee — typically a few credits per call). Not tied to any project, panel, or `projectType`.

## When to use headless vs a project

| User goal | Use |
|---|---|
| Edit one or more files on disk (trim, crop, resize, letterbox, mute, speed, concat) | **`single-asset-edit.md`** — no project |
| Probe duration/dimensions before editing | **`get_media_info`** (headless) |
| Extract or replace audio on a video | **`extract_audio`** / **`replace_audio`** (headless) |
| See what a video shows / grab thumbnail frames | **`extract_video_frames`** (headless), then read the frame images |
| Full video with panels, captions, B-roll, music, export | Matching **`../project-workflows/`** file + Create Video |
| Transcript text only | **`transcribe_video_file`** (also project-independent; see **`../panel-workflows/README.md`**) |
| Generate a standalone image or i2v clip to library | **`generate_scene_image`** / **`generate_image_to_video`** (see **`../../SKILL.md`** → *Generation and Rendering*) |
| Find existing stock photos/videos by keyword (with quality/size/duration filters) | **`pexels-stock-media.md`** — no project, signed in to Shorz |
| Find a reaction GIF or a transparent sticker to drop on the footage | **`giphy-gifs-stickers.md`** — no project, signed in to Shorz, no credits |
| Find a sound effect or background music track (free, nothing to credit) | **`openverse-audio.md`** — no project, **no sign-in**, no credits |
| Search X/Twitter for news, posts, people, trends, or media (answers with post citations) | **`x-search.md`** — no project, signed in to Shorz, **spends credits** |

After a headless edit, optionally **`save_file_as`**, **`import_frontend_assets`**, or attach the path in a project workflow — that is a **separate** step.
