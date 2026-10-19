# Guided flow — MUSIC VIDEO

A song → a music video that cuts on the beat, with one generated shot per scene written from the lyrics sung in it and the song as the only audio. The **song comes first**: its length sets the scene count and therefore the cost, so the part to use, the format and the concept come before any cost lever. Follow `README.md` protocol. Tool semantics: `references/project-workflows/music-video.md`.

**Route here when:** "make a music video for my song", "visualize this track", "AI visuals for my single", "a video for this mp3", "a music video for the chorus".
**Route away:** the user's own footage cut to a track → `auto-edit` (MUSIC lane + beat sync); a narrated video → `text-to-video`; animated lyric typography only, no generated footage → `animation-studio`; a product promo that merely has music → `advertisement`.

**Never ask about:** a voice (the song is the audio — no TTS), background music (the song is the only audio track), transitions between scenes (cuts land on the beat; the section light-leak is the only option), clip lengths (derived from the beats and the model), or main footage (music video has no main lane).

## Question sequence

### Q1 — The song (mandatory; content first — its length sets the cost)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`).** Render the **song slot** card (path field only — there is no native audio file dialog over MCP) and wait for its phrase. Only if no `show_widget` tool can be found: use the options below.
"Which song? I need the file on this computer (MP3, WAV, M4A, OGG or FLAC)."
1. **Give the file path** (Recommended)
2. It's already in my Shorz audio library → `get_audio_assets`, show the matching names, use the picked file's path

Probe it right away with `get_media_info { inputPath }` (free, no project needed) and **report the length back** ("3:12 song"). No `duration_sec` / `has_audio: false` means the file cannot be read — an undecodable song fails the render, so ask for another file. The copy into the project (`select_music_video_audio`) happens only after the confirmation. Ask in the same step whether it has vocals; an instrumental skips the caption option in Q7.

### Q2 — Whole song or a part? (the main cost lever — asked with the length known)
Quote each option's cost from the real length (`references/project-workflows/music-video.md` → *Cost*: roughly the rendered seconds × the video model's credits/s, plus one keyframe per ~6 s — ~2–6 credits each on the default GPT Image 2.5).
1. **Whole song** (Recommended when they want a full music video, e.g. for YouTube, or the song is under ~90 s)
2. **A 20–60 s part — tell me where it starts and ends** (Recommended when they mention TikTok / Reels / Shorts or a teaser; e.g. the chorus)
3. The first 30 seconds

Nothing over MCP can locate the chorus — for option 2 ask for the timestamps ("the chorus runs 0:48–1:22"). Validate them against the length (start < end ≤ length) before writing. Move the recommendation with what you already know (design rule 4): a 4-minute song for Shorts defaults to option 2.

### Q3 — Format (before any character generation)
Only two — generated video renders 16:9 or 9:16, never square:
1. **Horizontal 16:9 — YouTube / a full music video** (Recommended for the whole song; new music video projects start here)
2. Vertical 9:16 — TikTok / Reels / Shorts (Recommended when Q2 picked a short part)

### Q4 — The concept (what it's about and how it looks)
"What should the video be? And the look — era, palette, setting, style?"
1. **Performance + story** (Recommended) — the artist performing, intercut with scenes that play out the lyrics
2. Story only — no performance shots; the lyrics play out as scenes
3. Abstract / mood — landscapes, textures, light that follow the song's energy
4. Animated — a specific animation or illustration style (anime, claymation, watercolour…)

Follow up in the same step for the look and anything that must appear ("neon city at night, rain, 80s film grain"). This becomes the PromptBar brief. If they want a **photoreal** artist on screen, say now that Seedance models refuse photoreal close-up faces, so those shots switch to a pricier model (Q6 handles it) — stylised looks avoid that entirely.

### Q5 — The artist / lead character (only when Q4 includes a performer or a recurring lead)
> **WIDGET STEP — mandatory when `show_widget` exists (see `widgets.md`).** (Template A) one **optional** *Artist* card with *Open file picker*, *Generate with AI* and *Skip*; the picker dialog uses `extensions: ["jpg","jpeg","png"]`. Only if no `show_widget` tool can be found: use the options below.
1. **Let Shorz invent the cast from the brief** (Recommended — describe them in Q4)
2. Use a photo of the artist (JPEG or PNG) → `select_music_video_character_image`
3. Generate a character with AI → `generate_images` with an explicit `aspectRatio` matching Q3, then select the output

Keep the picked path and mark the card selected; `select_music_video_character_image` needs the music-video project, so it runs at execution. A real photo is a photoreal face: recommend Kling v3 in Q6, or a stylised look in Q4, and quote the difference.

**Lip-synced singing shots** (ask in the same step, only when the song has vocals and a performer appears):
1. **Off** (Recommended; default) — performance shots move to the music, the mouth is not synced
2. On — the AI picks a few moments (hooks, chorus lines — at most a third of the sung scenes) where the artist sings straight to the camera and lip-syncs them to the song with Kling Avatar Pro (~18 cr/s of those shots, instead of the video model's rate). Quote the extra: roughly up to a third of the song's seconds at that rate. OmniHuman 1.5 (~25 cr/s, livelier) and Kling Avatar (~9 cr/s) are the "Other" choices.

### Q6 — Models (cost levers — after the length and concept are known)
> **WIDGET STEP — mandatory when `show_widget` exists (see `widgets.md`).** (Template B) video-model cards in the order below with the price and the fit line, then the image-model cards. Only if no `show_widget` tool can be found: use the options below.
**Video model** — quote the total for the chosen length on each option:
1. **Seedance 2.0 Mini — ~9 cr/s** (Recommended; the default and cheapest; 4–15 s shots) → `bytedance/seedance-2-0-mini`
2. Seedance 2.5 — ~27 cr/s, top quality, up to 30 s per shot → `bytedance/seedance-2-5`
3. Kling v3 Standard — ~26 cr/s — the pick when a **photoreal face** is on screen (Recommended instead of option 1 when Q5 used a real photo) → `klingai/video-v3-standard-image-to-video`
4. Gemini Omni 1.1 Flash — ~12 cr/s — **only for parts under ~90 s**: each scene is one request against Google's ~20/day quota, and once it runs out the rest of the video switches to Seedance 2.0 Fast (a visible style change) → `gemini-omni-flash-preview`

"Other" surfaces: Seedance 2.0 Fast (~14 cr/s, `bytedance/seedance-2-0-fast`) and Seedance 2.0 (~18 cr/s, `bytedance/seedance-2-0`). The lineup is server-driven — `set_music_video_settings` rejects an id the live catalog does not list and names the current ones. Never offer Happy Horse.

**Image model** (one keyframe per scene, ~1 per 6 s):
1. **GPT Image 2.5 — ~2 cr/image** (Recommended; default; ~2 cr more per cast/character reference) → `GPT Image 2`
2. GPT Image 2.5 Sunburst — same price, the best likeness to a Character photo (Recommended when Q5 used a photo) → `GPT Image 2.5 Sunburst`
3. Nano Banana 2 — 12 cr/image, but every keyframe that carries a cast/character reference is billed at Nano Banana Pro Edit rates (~26 cr) → `Nano Banana 2`

### Q7 — Cut pace and finishing (batch)
**Cut pace** — recommend by the genre they named:
1. **Auto** (Recommended) — faster intercuts only in the loud sections
2. Relaxed — longer shots, no intercutting (ballads, acoustic, slow songs)
3. Energetic — intercut wherever a section allows (EDM, hip-hop, rock)

Pace barely changes the bill: intercutting re-uses the same generated seconds (design rule 9 — say so rather than implying "faster = pricier").
**Lyrics as captions:** 1. **Off** (Recommended; default) · 2. On — the transcribed lyrics, karaoke-style. Skip this for an instrumental.
**Light-leak flash on section changes:** 1. **On** (Recommended; default) · 2. Off.
**Pulse on the beat (Zoom on Music Beat):** 1. **Off** (Recommended) · 2. On.

## Summary + confirm

Per `README.md` contract. Include: song file + length, whole song or the part (start–end) and the rendered length, format, concept + look (the brief you will save), the artist image or "invented from the brief", lip-synced shots on/off (and the model), video + image model, cut pace, captions / light leaks / beat pulse, and the **cost estimate** for the rendered length. **Paid only — no free tier.** Check `get_shorz_credits` against the estimate before offering "start now". Mention the Omni quota (if Omni) and the face-refusal reroute (if photoreal) in one line each.

## Answer → execution map

| Step | MCP call |
|---|---|
| New project | `create_project { projectName, projectType: "music-video" }` → use the returned path as `projectPath` everywhere below |
| Q1 | `select_music_video_audio { projectPath, filePath }` |
| Q2 | `set_music_video_settings { useFullSong: true }` — or `{ useFullSong: false, rangeStartSec, rangeEndSec }` |
| Q3 | `switch_project_aspect_ratio { projectPath, aspectRatio }` |
| Q4 | compose the brief (concept · look · who appears · how the sections feel — never the lyrics, never sizing) → `set_user_instructions` |
| Q5 | `select_music_video_character_image { projectPath, filePath }` (after `generate_images` for option 3) · lip sync on → `set_music_video_settings { lipSync: true, lipSyncModel? }` |
| Q6 | `set_music_video_settings { videoModel, imageModel }` |
| Q7 | `set_music_video_settings { cutPace, sectionTransitions }` · `set_subtitle_settings { subtitlesActive: true }` · `set_general_video_settings { autoZoom: true, zoomType: "Zoom on Music Beat" }` |
| Render | pre-flight (`read_project_settings` → `MUSIC_VIDEO.music_video_audio_path` set and `file_exists`) → `trigger_create_video` → poll `get_video_generation_status` |

Notes: `import_frontend_assets` with `video` or `music` is rejected in this project type — the song goes through `select_music_video_audio` only. A shot that fails to generate becomes a slow zoom on its keyframe and the video stays in sync; **check the delivered video's length against the song or part** and tell the user when stills replaced motion. Re-rendering with only finishing changes (captions, title, border) re-uses every generated shot.
