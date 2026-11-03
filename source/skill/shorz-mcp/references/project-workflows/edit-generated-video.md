# Edit an already rendered video with text (project types `auto-edit` and `text-to-video`)

Use this when the user has a **finished Auto Edit video** or a **finished Text-to-Video story** and wants **one thing changed** — a cut, a reorder, a moved or removed effect, a style knob, the music, or (in a story) one scene's picture, words, motion or transition, or the narrator's voice — without re-generating the whole video. The tool is **`edit_generated_video`**. It is the MCP twin of the **Edit** pill the app shows over the PLAYBACK video (fullscreen editor with a conversation column). Everything the instruction does not mention stays exactly as rendered: same cuts, zooms, b-roll, emojis, titles, music, subtitles. Global rules live in **`../../SKILL.md`**; creating the video in the first place is **`auto-edit.md`** or **`text-to-video.md`**.

## What it looks like

Every Auto Edit render — and every Text-to-Video render made from generated images or AI clips — writes a **render plan** next to its mp4 (`<video>.plan.json` in the `Videos` cache folder): the cut plan (or, for a story, its scenes) with a timeline map, every effect analyzer's result with the media each placement produced, the music plan, the word transcript of the assembled clip and a full settings snapshot. An edit is **one LLM call** that turns the instruction into a short list of validated operations, applies them to that plan, then **replays the render with every other AI decision pinned** — no re-analysis, no re-planning, no effect analyzer runs, no regeneration of already generated b-roll / GIFs / web images / music. The result is a **new versioned mp4** (the previous one is kept; the playback rail shows one thumbnail per video with a version badge, and every version is in the editor's Versions row), the project's `ASSET_PATHS.last_generated_final_video_for_playback_mode` points at it, and the conversation is remembered **per video**, so a follow-up can say "no, the other one".

## Tool contract

**`edit_generated_video { projectPath, videoPath, instruction, awaitCompletion? }`** — async by default (`{ started, jobId }` → poll **`get_job_status`**; 15-minute blocking window with `awaitCompletion: true`). Paid: one interpreter LLM call, plus generation only when the edit adds new media.

| Field | Notes |
|---|---|
| `projectPath` | The project the video belongs to. |
| `videoPath` | Absolute path of the rendered mp4: `read_project_settings` → `ASSET_PATHS.last_generated_final_video_for_playback_mode`, or an entry of `get_my_videos` that belongs to this project. To edit an older version, pass that version's path. |
| `instruction` | One plain-language change (2–2000 chars). Times are **final-video seconds** as the user watched them: `0:42`, `at 1:05`, `cut 0:12-0:15`. "when I say launch", "the second clip", "the intro", "the ending" all work. |

**Result** `{ status, message, videoPath, operations, generatesMedia, notes, settingsPatch, choices? }`. A `clarify` result may carry `choices`: complete answers to its question (e.g. `"clip 4"`, `"use glitch_static"`) - send one back verbatim as the next `instruction` on the SAME `videoPath`.

| `status` | Meaning | What to do |
|---|---|---|
| `rendered` | New version at `videoPath` (already the playback video). | Report `message` + `notes`; both versions are kept (the editor's Versions row lists them). |
| `clarify` | The instruction was ambiguous; `message` is ONE question. | Ask the user (or answer yourself if obvious) and call again with the SAME `videoPath` — the thread is remembered. |
| `unsupported` | Not doable here; `message` names the panel to use. | Route to that panel workflow (dubbing → audio panel, aspect ratio → `switch_project_aspect_ratio`, new footage → import + `trigger_create_video`). |
| `failed` | The replay could not render; diagnostics are in `get_video_generation_status` / the log. | Do not loop; surface the message. |
| `busy` | A render is in flight. | Wait for `get_video_generation_status` to be terminal, then retry once. |

`operations` is the validated list the instruction became (`remove_range`, `remove_segment`, `trim_segment`, `extend_segment`, `move_segment`, `swap_segments`, `replace_segment_asset`, `insert_segment`, `set_segment`, `set_segment_title`, `add_effect`, `remove_effect`, `move_effect`, `update_effect`, `set_setting`, `set_music`). `settingsPatch` lists style settings written back to the project's `settings.json` so later renders keep them (e.g. `TEXT_SETTINGS.subtitle_font_size`).

**What an instruction can change**

| Area | Examples |
|---|---|
| Cuts & structure | "cut 0:12-0:15", "remove the second clip", "trim 2 s off the start", "make the intro shorter", "swap the second and third clip", "move the demo before the talking head", "use office.mp4 for clip 2", "insert product.jpg after clip 1 for 3 seconds", "slow clip 3 to half speed", "mute clip 2", "dissolve into clip 3", "add a title 'Big reveal' on clip 3" |
| Effect moments | "remove the zoom near the start", "move the fire emoji to when I say launch", "add a freeze frame at 0:42", "make the grayscale moment shorter", "drop the web image at 1:05", "add AI b-roll of a rocket when I say launch" (generates), "add a GIF of confetti at 0:30" (fetches), "add the whoosh sound at 0:07" |
| Overlay effect | Placeable, not just on/off: "put the film grain on the intro only", "glitch from 0:20 to 0:26", "keep the light leaks off the talking-head clip", "add the grain back over the ending", "use the light leaks instead". Removing every window switches the effect off. Any overlay the install ships can be named, not just the ones the project has selected — naming one selects it; naming one that does not exist gets a `clarify` listing the real ones. Swapping the effect swaps it on every window, because one overlay file runs through the whole video. |
| Style knobs | "make the subtitles bigger", "yellow highlight word", "remove the border", "brighter", "no transitions" — any key under `TEXT_SETTINGS`, `VIDEO_BORDER`, `VIDEO_OVERLAY_EFFECT`, `AUDIO_SETTINGS`, `VIDEO_COLOR`, `VIDEO_ZOOM`, `VIDEO_FREEZE_FRAME`, `VIDEO_DRAMATIC_GRAYSCALE`, `VIDEO_TRANSITIONS`, `BROLL_VIDEO_SETTINGS`, `IMAGE_SETTINGS`, `GIF_SETTINGS`, `AI_BROLL_SETTINGS`, `AUDIO_VISUALIZATION` |
| Music | "turn the music down", "use song.mp3", "regenerate the music, calmer", "no auto music" |

**Single-clip renders** (one main asset, or a render where auto-edit was skipped) support cuts, start/end trims, speed and volume, plus every effect and style change — there is only one clip, so reordering / replacing / inserting is refused with a clear message.

**Not possible here** (the tool answers `unsupported`): dubbing, aspect ratio, voice changes on an Auto Edit video, footage that is not in the project's main assets, other project types (avatar, podcast, advertisement, clipping, music-video), Text-to-Video stories built from imported media, and any video rendered **before** this feature existed (no plan file → "create the video again first").

## Text-to-Video stories (scenes)

A Text-to-Video plan is a list of **scenes**, one per narrated line: its narration file, its picture (or AI video clip), its motion and the transition into it, each in the time window the user watched. The editor's strip shows them as **scene 1, scene 2, …** with the spoken line, and the interpreter speaks in scenes (a user saying "clip 3" or "the third shot" means scene 3). Everything in the tables above that is not about cutting footage — effects, overlay, colour, subtitles and other style knobs, music — works on a story exactly as on an Auto Edit video.

| Change | Examples | What is generated again |
|---|---|---|
| A different picture | "give scene 3 a different picture", "show a close-up of Maya in scene 2" | that scene's picture (same character/place references and style), and its AI clip in a `generated_video` story |
| A small picture fix | "make scene 1 a night scene", "remove the text from the sign in scene 4" | an AI edit of the current picture (composition kept) |
| Another take | "another version of the picture in scene 2" | that picture |
| New words | "change what scene 2 says to …", "fix the wording of the last scene" | that scene's narration, in the story's voice; its picture stays |
| New scene | "add a scene after scene 3 that explains why it matters" | its narration + picture (+ clip); it borrows the cast of the scene before it |
| Voice | "use a deeper voice", "narrate it with Rachel" | every scene's narration; every picture stays |
| New take | "record the narration of scene 3 again", "scene 5 sounds off" | that scene's narration, same words and voice (a new seed); picture stays |
| One scene's voice | "let Rachel read the last scene" | that scene's narration only; the story's narrator and every picture stay |
| Order | "remove scene 5", "swap scenes 1 and 2", "move the last scene to the beginning", "cut 0:12-0:18" (removes the scenes it covers) | nothing |
| Motion / transitions | "slow zoom in on scene 1", "pan left on scene 3", "dissolve between every scene", "no transitions" | nothing |
| AI clip movement | "make the camera orbit the rocket in scene 3" (`generated_video` only) | that clip |

Rules of a story: a scene lasts exactly as long as its narration, so scenes are never trimmed, stretched or sped up — remove a scene or give it fewer words instead (a cut that falls inside one scene returns `clarify` with a one-click "remove scene N"). Motion (zoom/pan) only applies to pictures; an AI clip moves on its own. When scenes are re-narrated or reordered, every zoom, emoji, title and b-roll moves with the scene it was placed on (a re-narrated scene's placements are stretched onto its new length) and the subtitles are transcribed again. A story narrated from the user's **own recording** (`input_mode: audio`) cannot change its words or voice or gain narrated scenes (`unsupported`); pictures, order, motion and transitions still change. A story built from **imported media** has no scene plan: the pill says so and the tool answers `unsupported`. A voice change applies to that video only; the Text to Video panel keeps its voice (changing it there regenerates every picture on the next Create Video).

## Instruction handling rules

- The app's editor also shows a **"What's in this video"** strip (every clip and effect placement of the selected version); clicking a piece writes its name into the instruction box. The same list is in the plan sidecar under `elements` — each entry carries the exact `ref` phrase the interpreter resolves, so when a user describes a part vaguely you can name it the way that strip does ("clip 5", "the zoom at 0:02.5"). The strip draws clips as filmstrips of their frames, visual layers as pictures and sound effects and music as waveforms; each entry's `media` names the file (and the stretch of it) behind it, and `elements.music` lists where each music file plays ("the music" is its phrase).
- Pass the user's sentence **verbatim**; do not pre-translate it into operations or timestamps you invented. If the user gave a screenshot or a vague "the part where he talks about pricing", still pass it verbatim — the interpreter has the transcript.
- One change per call. "Cut the intro and make subtitles bigger" is fine (both are one instruction), but do not batch unrelated requests from different turns into one call.
- `clarify` is a question, not an error: relay it, then call again with the answer on the **same `videoPath`**.
- Never "fix" a finished video by re-running `trigger_create_video` with a changed brief when this tool can do it — a re-render re-plans everything and re-bills generated media.
- Never delete the previous version to "clean up"; the user picks versions from the editor's Versions row.
- Style changes persist to the panels (`settingsPatch`). Say so when it matters ("subtitles stay bigger for your next videos too").
- Free tier: an Auto Edit edit spends one weekly free run, the interpreter call is zero-rated on that run; paid users (and every Text-to-Video edit) are billed for the interpreter call and any generation.

## Execution sequence

1. `get_current_open_project` / `read_project_settings` → confirm `project_type` is `auto-edit` or `text-to-video` and take `ASSET_PATHS.last_generated_final_video_for_playback_mode` (or the user's chosen version from `get_my_videos`).
2. Optional: `get_video_generation_status` → not generating.
3. `edit_generated_video { projectPath, videoPath, instruction }` → `{ started, jobId }`.
4. Poll `get_job_status { jobId }` every ~10–20 s until `completed`; read `result.status`.
5. `rendered` → tell the user what changed (`message`, `notes`) and that the previous version is still one click away in the editor's Versions row. `clarify` → relay the question, then repeat from 3 with the answer. `unsupported` → route to the named panel.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `unsupported`: "no saved edit plan" | The mp4 predates the feature, or its `.plan.json` was removed from the `Videos` cache folder. | Create the video again (one normal render), then edit. |
| `unsupported`: "…built from your imported media…" | A Text-to-Video story made from imported media (no scene plan). | Change it in the Text to Video panel and create it again. |
| `failed`: "…the picture for scene N could not be generated" | A scene the edit asked to generate failed (provider error, credits). | Nothing was delivered; retry the same instruction once. |
| `unsupported`: "cannot be edited by text (…)" | The plan was captured but its cut stage is not replayable (e.g. no timeline map). | Same: render once more; if it repeats, report the `not_editable_reason`. |
| `clarify` about a clip with silence removal / loop / reverse | Interior cuts inside such a clip cannot be placed precisely. | Offer "remove the whole clip" or "trim its start/end". |
| `busy` | A render or another edit is running. | Wait for a terminal `get_video_generation_status`, retry once. |
| `failed` with `edit_source_missing` / `edit_prep_step_failed` | The source clip moved or a recorded prep step could not be re-applied. | Re-import the missing main asset with the same file name, or create the video again. |
| Pinned b-roll regenerated (shows in `notes`) | The generated file was removed (cache cleared). | Expected: it regenerates once and is pinned again in the new version. |
