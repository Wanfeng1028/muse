# Project Workflows (MCP)

These files describe how to operate each Shorz **project type** end-to-end over MCP: project creation, panel/setting patches, media helpers, PromptBar, and Create Video. Pick the file that matches the active or requested `projectType`.

**Not in this folder:** single-file deterministic edits (trim, crop, resize, letterbox, audio mux, concat, probe, etc.) — those are **project-independent** headless MCP tools (23 total); see **`../headless-workflows/single-asset-edit.md`**.

Global rules — project targeting, PromptBar semantics (**no aspect ratio or width/height in PromptBar text** — see *Output framing* in **`../../SKILL.md`**), asset verification (main vs library), **main VIDEO import by `projectType`** (`../../SKILL.md`), event polling, destructive actions — live in **`../../SKILL.md`**. Cross-project panel contracts (subtitle, title, border, audio, B-roll, overlay, general video, thumbnail creator, animation studio) live in **`../panel-workflows/`**. Headless MCP-only file tools live in **`../headless-workflows/`**. Library / cross-cutting MCP tools (`query_my_assets`, `import_frontend_assets`, `download_social_video`, `generate_images`, `generate_scene_image`, `generate_image_to_video`, path checks) are documented in **`../panel-workflows/README.md`** → *Library and cross-cutting MCP tools*.

## Files in this folder

- `auto-edit.md` — general montage; PromptBar carries the creative brief (empty ⇒ weak/no-intent output)
- `edit-generated-video.md` — change ONE thing in a finished auto-edit or text-to-video video by text (`edit_generated_video`): new version, everything else pinned
- `text-to-video.md` — script-or-audio to video; `set_text_to_video_settings`
- `avatar.md` — single talking head; `set_avatar_settings`
- `podcast.md` — two-speaker dialogue; `set_podcast_settings`
- `advertisement.md` — short promo spots; `set_advertisement_settings`
- `music-video.md` — a song → a video cut on the beat with lyric-matched shots; `select_music_video_audio`, `set_music_video_settings`
- `clipping.md` — one long source → 1–8 short clips; `update_project_settings` on `CLIPING` (no `set_clipping_settings` tool)

Every workflow file follows the same section order as `../panel-workflows/border.md`:

1. Title + intro
2. **What it looks like** — user-visible UI behavior
3. **Tool contract** — primary tools, supported keys, enums (verbatim), persistence paths via `read_project_settings`
4. **Instruction handling rules**
5. **Execution sequence**
6. **Common failures**

**Pre-render checklist (all project types):** When the user names a main LLM (Opus 5.5, Fable 5.1, Sonnet 5.5, GPT 6.1 Sol, GPT 6 Luna, GPT 6 Astra, Gemini 3.8 Flash, or a model id), call **`set_main_ai_model`** before Create Video, or pass **`mainAiModelName`** on **`trigger_create_video`**. PromptBar ids are server-driven — call **`list_main_ai_models`** for the live lineup and pass an id from its response (at time of writing seven: `anthropic/claude-opus-5-5` (default), `anthropic/claude-fable-5-1`, `anthropic/claude-sonnet-5-5`, `openai/gpt-6-1-sol`, `openai/gpt-6-luna`, `openai/gpt-6-astra`, `google/gemini-3.8-flash`; treat that as a snapshot, not an allowlist) — not Animation Studio’s separate chat picker. **Exception:** on a free-tier run (`auto-edit` / `clipping` on a zero-balance account) only `google/gemini-3.8-flash` is zero-rated. The in-app picker locks itself to it; the MCP path does not, so set that id yourself or the render bills and 402s part-way. See **`../../SKILL.md`** → *PromptBar main AI model* and *Keys and auth dependencies*.
