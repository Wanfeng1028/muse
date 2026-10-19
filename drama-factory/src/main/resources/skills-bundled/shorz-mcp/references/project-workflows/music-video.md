# Music Video workflow (project type `music-video`)

A song in, a finished music video out: the cuts land on the beat, every shot is written from the words being sung at that moment, and the song is the video's only audio — the video is exactly as long as the song (or the part of it you choose). Use **`select_music_video_audio`** for the song and **`set_music_video_settings`** for the panel. Global rules and routing live in **`../../SKILL.md`**.

Use this when the user has a **song** (or a section of one) and wants visuals made for it. For the user's own footage cut to a track, use **`auto-edit.md`** (MUSIC lane + beat-synced cutting); for a narrated explainer, **`text-to-video.md`**; for a product promo, **`advertisement.md`**.

## How it works (pipeline)

On **Create Video**, Shorz:

1. **Analyses the song** — tempo, a regular beat grid, bars, and energy sections (quiet verse-like parts vs loud chorus-like parts).
2. **Transcribes the lyrics word by word** (ElevenLabs Scribe). An instrumental simply has no lyrics; everything below still works from the song's energy and the PromptBar. (The first render of an instrumental asks for the lyrics twice before treating the song as instrumental; later renders reuse that verdict.)
3. **Plans the timeline** — scenes whose cuts land on bar downbeats (preferring the bar where a sung line starts), each scene inside the video model's per-clip range. In high-energy sections two scenes can be **intercut** — alternating every bar or every two beats — so the cutting gets faster without generating (or paying for) extra seconds.
4. **Writes the shot plan** — the project's main AI model (`set_main_ai_model`) writes one visual per scene that matches the words sung in it, plus a global style and a consistent cast of up to three, following the PromptBar brief. By default the intercut shots split into **performance** shots of the artist/cast and **story** shots. The image prompts ask for no lyrics as on-image text (a request to the image model, not a hard guarantee) — on-screen lyrics are the optional captions of step 7.
5. **Generates** one keyframe image per scene with the chosen image model (cast reference portraits keep faces consistent; the optional **Character** image stands in for the lead), then animates every keyframe with the chosen video model, **generated audio off**.
   - **Lip-synced singing shots** (`lipSync: true`): the main AI then picks the few sung moments where the performer singing straight into the camera makes sense — the hook, chorus lines, a line sung to "you", an emotional or boastful peak — and re-shoots only those scenes as close-ups of the performer in the same setting. The avatar model (`lipSyncModel`, the Avatar project type's models) moves their mouth to exactly the slice of the song each shot plays over, intercut shots included; every other scene animates as usual. At most a third of the sung scenes (6 in all) are picked, and none when nothing fits the brief.
6. **Assembles** a frame-exact, beat-cut timeline exactly as long as the song or the chosen part, with an optional light-leak flash on the cuts that start a new section (never shifts a cut, no whoosh), and attaches the song as the only audio track.
7. Runs the **normal finishing chain** on it — subtitles (the **lyrics**, karaoke-style, when captions are on), **Zoom on Music Beat**, titles, overlays, border, colours.

**Re-rendering is cheap when nothing upstream changed.** With the same song, part, settings and PromptBar, the analysis, shot plan, keyframes and clips come back from Shorz's render cache and no video is billed again — so changing only finishing settings (captions, title, border…) and rendering again costs next to nothing. Changing the brief, the cut pace, the song range, the aspect ratio, the Character image or a model (including the main AI model) regenerates whatever depends on it. Turning **lip sync** on for a video already rendered keeps its shot plan and every other shot: only the picked close-ups are drawn and lip-synced; turning it off again brings the earlier shots back from the cache.

**What the cache keeps, and for how long.** Each song (or song part) keeps the shot plans, cast portraits, keyframes, clips and assembled cut of its **last 3 renders** — the latest always — so switching back to one of the last three briefs or models is free too. A retry of a render stopped by failed scenes or a failed assembly counts as the same render and reuses every clip it already paid for. At the end of each render, older renders' files are deleted; a song part not rendered for **30 days** is deleted whole; and while the whole cache is over **5 GB**, the least recently rendered song parts go first (never the one just rendered, never one another render is using). A deleted version is billed in full again — say so before someone returns to a fourth-oldest brief or an old song expecting it to be free.

## What it looks like

The **Music Video** panel shows:

- **Song** — drop zone / browse (`.mp3 .wav .m4a .ogg .flac`), file name, length, player, remove; a **Full song** toggle with **Start / End** sliders when it is off.
- **Music Video Settings** — **Video generation model** and **Keyframe image model** (the same server-driven lists as Text-to-Video), **Cut pace** (Auto / Relaxed / Energetic), **Section transitions** toggle, **Lip-synced singing shots** toggle (and its **Lip-sync model** when on).
- **Character** (optional) — the **Artist or character** image, picked or generated.
- A **cost estimate** bar pinned at the bottom.
- **PromptBar** — the creative brief: concept, look, setting, who appears, how each part should feel.

New music video projects start **16:9**. Generated video renders only **16:9 or 9:16**, so square is not offered — `switch_project_aspect_ratio` rejects `1:1` on a music-video project.

**No main lane, no music lane.** Your Library hides the **VIDEOS** and **MUSIC** tabs, and headless `import_frontend_assets` with `assetType: "video"` or `"music"` is **rejected with an error** — the song lives in `MUSIC_VIDEO.music_video_audio_path`, set by `select_music_video_audio`. B-roll and sound-effect imports still work.

**Features that would retime or re-mix the song are skipped** for this type (the app hides them; an enabled one is logged as skipped, not applied): freeze frame, dramatic grayscale, auto-music, imported MUSIC-lane tracks, noise removal, dubbing, reverb. Captions are **off** by default for a new music video.

## Tool contract

**Primary tool:** `set_music_video_settings`

**Arguments:** `projectPath` (absolute) and a `settings` object with only the keys you want to change. Unknown keys are rejected.

**Supported keys in `settings`:**

| Key | Type | Notes |
|---|---|---|
| `videoModel` | string (live catalog id) | The model that animates every shot. Same set as `textToVideoVideoModel` — see *Models* below. **Server-driven:** there is no enum; an id that is not an enabled `text_to_video` video row in the live catalog is **rejected** and the error lists the current ids. |
| `imageModel` | string (live catalog id) | Keyframe image model. Same set as `textToVideoImageModel`. Checked the same way. |
| `cutPace` | `auto` \| `relaxed` \| `energetic` | `auto` intercuts only in high-energy sections; `relaxed` never intercuts (longer shots — ballads, slow songs); `energetic` intercuts wherever a section allows, with faster cuts (EDM, hip-hop, rock). |
| `sectionTransitions` | boolean | Light-leak flash on the cuts that start a new song section (at least 1.2 s apart). |
| `useFullSong` | boolean | `true` = the whole song; `false` = only `rangeStartSec`..`rangeEndSec`. |
| `rangeStartSec` | number ≥ 0 | Start of the part, seconds into the song. |
| `rangeEndSec` | number ≥ 0 | End of the part; **`0` = to the end of the song.** When both are sent, a non-zero end must be greater than the start (rejected otherwise). |
| `lipSync` | boolean | Lip-synced singing shots: the AI turns a few sung scenes into close-ups of the performer singing to the camera, lip-synced to the song. Needs a performer in the cast (a Character image, or a brief with a singer in it). |
| `lipSyncModel` | `Kling Avatar Pro` \| `Kling Avatar` \| `OmniHuman 1.5` | The avatar model of those shots. Kling Avatar Pro is the default (steady face and light); OmniHuman 1.5 moves more but costs more, and its lighting can drift over a long shot; Kling Avatar is the cheapest. |

**What else the tool writes:** a new `videoModel` also stores that model's per-clip length range in `music_video_clip_min_sec` / `music_video_clip_max_sec` — the live catalog's duration capability, with **Gemini Omni floored at 3 s** (Omni 1.1 will not render shorter). The panel keeps the same two keys in sync, so the renderer plans scenes for the model it will really use. When the catalog is unreachable the ids are saved **unchecked**, the range comes from the bundled table, and the result carries a `notes` entry saying so.

**Result:** `{ success, writeResult, applied, currentSubset, notes? }` — `currentSubset` shows the persisted `MUSIC_VIDEO` values the call wrote (including the clip range).

**Persistence oracle** — confirm via `read_project_settings` → `MUSIC_VIDEO` (every value is a string):

| MCP key / tool | `MUSIC_VIDEO` key | Default |
|---|---|---|
| `select_music_video_audio` | `music_video_audio_path` | `""` |
| `videoModel` | `music_video_video_model` | `bytedance/seedance-2-0-mini` |
| `imageModel` | `music_video_image_model` | `GPT Image 2` |
| `cutPace` | `music_video_cut_pace` | `auto` |
| `sectionTransitions` | `music_video_section_transitions` | `True` |
| `useFullSong` | `music_video_use_full_song` | `True` |
| `rangeStartSec` | `music_video_range_start_sec` | `0` |
| `rangeEndSec` | `music_video_range_end_sec` | `0` |
| `select_music_video_character_image` | `music_video_character_image` | `""` |
| `lipSync` | `music_video_lip_sync` | `False` |
| `lipSyncModel` | `music_video_lip_sync_model` | `Kling Avatar Pro` |
| (derived from `videoModel`) | `music_video_clip_min_sec` / `music_video_clip_max_sec` | `4` / `15` |

### Song and character files

| MCP tool | Arguments | Effect |
|---|---|---|
| `select_music_video_audio` | `filePath`, `projectPath?` | The app copies the song **by path** (no upload, any size) into `<project>/music_video/song/`, deletes the previous song, and sets `music_video_audio_path`. Accepts `.mp3 .wav .m4a .ogg .flac`. Returns `{ success, projectPath, selectedAudioPath, projectAudioPath, durationSeconds, writeResult }` — `durationSeconds` is the number every cost estimate starts from (`0` + a `warning` when it could not be read). |
| `remove_music_video_audio` | `projectPath?` | Clears `music_video_audio_path` and deletes the copy (your original file is never touched). |
| `select_music_video_character_image` | `filePath`, `projectPath?` | Copies a `.jpg .jpeg .png` into `<project>/music_video/character/` and sets `music_video_character_image`. It becomes the lead cast member's reference in every keyframe that features the lead (shots the plan gives to other cast or to scenery don't carry it). |
| `remove_music_video_character_image` | `projectPath?` | Clears `music_video_character_image` and deletes the copy; the cast is then invented from the song and the brief. |

`projectPath` defaults to the project open in Shorz. All four **refuse a project whose type is not `music-video`** instead of quietly storing a song nobody will render. There is no native audio file dialog over MCP (`select_local_image_for_import` is image-only) — ask the user for the path, or list their library with `get_audio_assets`.

### Models

The lists are **server-driven** — the catalog's `text_to_video` rows, the same as Text-to-Video (Gemini Omni included). Treat this table as a snapshot; the tool's error message always carries the live ids.

| Video model id | Price | Shot range here | Notes |
|---|---|---|---|
| `bytedance/seedance-2-0-mini` | ~9 cr/s @720p | 4–15 s | Default and cheapest. |
| `bytedance/seedance-2-0-fast` | ~14 cr/s | 4–15 s | |
| `bytedance/seedance-2-0` | ~18 cr/s | 4–15 s | |
| `bytedance/seedance-2-5` | ~27 cr/s @720p | 4–30 s | Top Seedance quality; longest single shots. |
| `klingai/video-v3-standard-image-to-video` | ~26 cr/s | 3–15 s | Renders photoreal close-up faces that every Seedance model refuses. |
| `gemini-omni-flash-preview` | ~12 cr/s | 3–10 s | One Google request per scene against a ~20/day quota — see *Common failures*. |

`custom:happyhorse-1.0` (Happy Horse) is disabled in the catalog, so the tool rejects it — never offer it.

| Image model id | Price | Notes |
|---|---|---|
| `Nano Banana 2` | 12 cr/image; ~26 when the keyframe carries a cast/character reference (billed as Nano Banana Pro Edit) | Optional. |
| `GPT Image 2` | 2 cr/image | Serves GPT Image 2.5 Flare (fast). |
| `GPT Image 2.5 Sunburst` | 2 cr/image | Sharper; the best same-face likeness from a Character image. |

## Cost

Cost scales with the length you render — **every generated second bills**:

- **Video** ≈ (song or part seconds + up to ~1 s per scene of whole-second rounding and minimum-length padding) × the model's credits per second. Intercutting reuses the same generated clips, so **cut pace barely moves the bill** (relaxed makes slightly fewer, longer scenes).
- **Keyframes** — one image per scene (about one scene per 6 s) × the image price, plus up to three cast portraits. A Nano Banana keyframe that reuses the cast portraits bills as Nano Banana Pro Edit (~26 credits), so the panel's estimate is a range.
- **Lyrics** — transcription at about 1 credit per minute of song.
- **Shot plan** — main-AI tokens, a fraction of the total.
- **Lip-synced shots** (when on) — each picked shot bills its seconds (plus ~0.6 s) at the avatar model's rate *instead of* a video clip: Kling Avatar Pro ~18 cr/s, Kling Avatar ~9, OmniHuman 1.5 ~25 (live catalog rates win), plus a small main-AI call to pick them. Measured live 2026-09-30 on 8 s of rap: Kling Avatar Pro 155 credits, OmniHuman 1.5 221. The panel prices the most shots the AI may pick, so its estimate is a range.

Worked examples (Seedance 2.0 Mini + the default GPT Image 2.5 keyframes): a **3-minute song** is ~30 scenes → ~200 billed seconds × 9 ≈ 1,800 + keyframes ≈ 60–250 ⇒ **~1,900–2,100 credits**; on Seedance 2.5 the same song is **~5,600**. A **30-second chorus** is ~5 scenes ⇒ **~300 credits** (measured live: a 24 s part on Seedance 2.0 Mini billed 254 credits, a 40 s energetic rap with a Character photo 400). Cut pace moves the keyframe count: Relaxed ~⅔ of Auto's scenes, Energetic ~¼ more. The biggest lever is the length: `useFullSong: false` with a start/end turns a full song into a short. Next, the video model; Nano Banana 2 keyframes cost far more (12, or ~26 with a reference). **Paid only** — the free tier covers auto-edit and clipping, never music video. The in-app panel shows its own estimate bar; `get_shorz_usage_and_pricing` has the live per-model rates.

## Instruction handling rules

- **The PromptBar is the creative brief**: the concept (performance, story, abstract), the look (palette, lighting, film stock or animation style), the setting, who appears and what they look like, and how the sections should feel ("slow and dark in the verses, explosive in the chorus"). The lyrics come from the song itself — **never paste lyrics into the PromptBar** and never ask for them as on-screen text.
- **Performance vs story** — by default intercut pairs are performance shots of the cast/artist plus story or b-roll shots; the brief can override it ("no performance shots", "only the dancer", "everything underwater").
- **A consistent artist** — describe them in the brief ("a woman with a shaved head in a silver jacket") or give a Character image; the cast stays at three or fewer.
- **A short from a long song** — set `useFullSong: false` plus the part's start/end; don't write "use the chorus" in the brief (the brief cannot trim the song).
- **Captions are the lyrics** — `set_subtitle_settings { subtitlesActive: true }` shows the transcribed words verbatim (no spelling clean-up), karaoke-style, and starts a new caption wherever the singing pauses for 0.8 s or more; leave them off for an instrumental, where every transcript-driven effect (captions, GIFs, emojis, AI B-roll, web images, auto sound effects, automatic title placement, Intelligent Auto Zoom) has nothing to place.
- **Output framing** stays out of the brief (no `9:16`, pixel sizes or fps — **SKILL.md** → *Output framing*); use `switch_project_aspect_ratio`.
- **Minimal patches** — send only the keys the user asked about.

## Execution sequence

1. **Resolve project** per **SKILL.md** → *Project targeting rules*. Create only with approval: `create_project { projectName, projectType: "music-video" }` (hyphenated — `music_video` is rejected).
2. **Song** — `select_music_video_audio { projectPath, filePath }`. Note `durationSeconds`; if it is `0`, probe the file with `get_media_info` before going on.
3. **Which part** — for a short: `set_music_video_settings { useFullSong: false, rangeStartSec, rangeEndSec }` (ask the user where the chorus is; nothing over MCP can locate it). Whole song: leave `useFullSong: true`.
4. **Format** — `switch_project_aspect_ratio { aspectRatio: "9:16" }` for TikTok / Reels / Shorts; new projects start `16:9`.
5. **Models and pace** — `set_music_video_settings { videoModel, imageModel, cutPace, sectionTransitions, lipSync, lipSyncModel }` (only what the user chose). Quote the cost for the length first. Offer `lipSync` when the user wants the artist singing to the camera.
6. **Artist image** (optional) — `select_music_video_character_image { projectPath, filePath }`.
7. **Brief** — `set_user_instructions`; optionally `set_main_ai_model` (it writes the shot plan).
8. **Finishing** (optional) — lyrics captions via `set_subtitle_settings`, a beat pulse via `set_general_video_settings { autoZoom: true, zoomType: "Zoom on Music Beat" }`, title / border / overlay panels.
9. **Pre-flight** — `read_project_settings` → `MUSIC_VIDEO.music_video_audio_path` is non-empty and `file_exists` confirms it; `get_shorz_credits` covers the estimate.
10. **Create Video** (only when asked) — `trigger_create_video`, then poll `get_video_generation_status` until terminal. A full song generates dozens of shots and takes a while; `fetch_app_events` only on request or when debugging (the render logs `Music video: …` progress lines).
11. **Report** — output path, and check the delivered length matches the song or part.

## Quick defaults

- `videoModel`: `bytedance/seedance-2-0-mini` · `imageModel`: `GPT Image 2` (GPT Image 2.5)
- `cutPace`: `auto` · `sectionTransitions`: `true`
- `lipSync`: `false` · `lipSyncModel`: `Kling Avatar Pro`
- `useFullSong`: `true` · `rangeStartSec` / `rangeEndSec`: `0` / `0`
- Aspect ratio: `16:9` · captions: off

## Common failures

- **No song** — the render stops (`music_video_no_song`). `trigger_create_video` does not check this for you; select the song first and verify it.
- **Unreadable song or empty part** — the render stops (`music_video_song_unreadable`) when the song cannot be decoded or analysed, the chosen part is under a second long, or `rangeStartSec` lies past the end of the song. Check the file with `get_media_info` and the range against its length.
- **No shot plan** — the render stops (`music_video_plan_failed`) when the main AI model returns no usable shots (out of credits, a model error). Nothing is drawn or animated before this point, so no image or video credits are spent.
- **Assembly failed** — the render stops (`music_video_assembly_failed`) when the beat-cut timeline cannot be put together. Every clip is already cached, so rendering again retries the assembly without paying for the clips twice.
- **Wrong project type** — the four file tools refuse non-`music-video` projects; `set_music_video_settings` on another type saves keys nothing renders. Check `UI_SETTINGS.project_type` before configuring.
- **Gemini Omni quota** — Omni allows only ~20 requests per day and a music video spends one per scene (a 3-minute song is ~30). Once an Omni clip fails, that clip and the rest of the render switch to **Seedance 2.0 Fast** (~14 cr/s) — a visible style change partway through. Use Omni only for parts under ~90 s, and mention it when someone renders several a day.
- **Seedance refuses photoreal close-up faces** — every Seedance 2.x model rejects a keyframe it reads as a real person's face (a photoreal artist image makes this likely on performance shots). That clip then reroutes to Gemini Omni (~12 cr/s), then Kling v3 (~26 cr/s), billed at the substitute's rate. Stylised looks and wider framing avoid it; for a photoreal performance video, pick Kling v3 up front.
- **A shot that still fails** becomes a slow zoom on its keyframe, so the video stays in sync — tell the user rather than letting it look like a bug. If more than half the shots fail, the render stops (`music_video_generation_failed`).
- **Lip-synced shots** — a picked shot whose avatar job fails plays as a slow zoom on its close-up keyframe and is lip-synced on the next render (the rest comes from the cache). When the AI cannot be asked for picks, that render has no lip sync and says so in the log; with no performer in the cast (an abstract brief) or nothing sung, none are added. OmniHuman takes shots up to 28 s; longer scenes are never offered to it.
- **Imports rejected** — `import_frontend_assets` with `video` or `music` fails in this project type by design; use the song tools, and `broll` for supporting footage.
- **Range ignored** — `rangeStartSec` / `rangeEndSec` only apply with `useFullSong: false`. Sending both with an end at or before a non-zero start is rejected; an end of 0 (or a lone `rangeEndSec` at or before the stored start) runs to the end of the song. The part is stored exactly as sent (fractions and parts shorter than the panel sliders allow are kept), and `select_music_video_audio` / `remove_music_video_audio` reset it to the whole song, like the panel's Replace.
- **Quieter than the original file** — every Shorz render is loudness-normalised to -14 LUFS on delivery, so a loud mastered song plays back a little quieter than the file you picked.
