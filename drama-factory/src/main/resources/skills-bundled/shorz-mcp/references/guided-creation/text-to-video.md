# Guided flow — TEXT-TO-VIDEO

Script/idea → narrated video with AI-generated (or imported) visuals. The most branched flow: the **script comes first** (it sets the scene count and therefore the cost), then **Source Media is the root branch** that several later questions depend on. Follow `README.md` protocol. Tool semantics: `references/project-workflows/text-to-video.md`.

**Route here when:** "make a video about X", "turn my script into a video", faceless video, storytime, documentary/explainer, "narrate my clips".
**Route away:** general edit without narration → `auto-edit`; one talking head → `avatar`; two speakers → `podcast`; product ad → `advertisement`; visuals for a song (the song is the audio, cuts on the beat) → `music-video`; a single image/clip asset only → standalone `generate_scene_image` / `generate_image_to_video`.

## Question sequence

### Q1 — The script (content first — it sets the scene count, which sets the cost)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template C) when `show_widget` exists: once the script is saved (IF 1 or 2), render narrator voice cards; the pick maps to `set_text_to_video_settings { textToVideoVoice }`. Only if no `show_widget` tool can be found: use the options below.
"What's the video about — and do you have a script, or should I write one?"
1. **Write the script for me from this topic** (Recommended)
2. I have a script, here it is
3. I have a narration audio file already (`textToVideoInputMode: "audio"`)

IF 1 → ask the target length in the same step (**~30 s** (Rec) / ~60 s / ~2 min / ~5 min), draft it, and confirm the draft before saving.
IF 1 or 2 → **≥ 50 characters required** (raw, untrimmed) or the render aborts — enforced by the backend only, so neither the panel nor MCP will warn you. The ≤6,000-word / ≤40,000-char caps are **UI-only**; headless scripts are uncapped. Report the ~150 wpm duration estimate back.
Then **voice**: `list_elevenlabs_voices` → offer 3–4 by fit + preview via `generate_tts_preview` (first ~200 chars). Custom/cloned voices need a BYO ElevenLabs key.
IF 3 → path (`.mp3 .wav .m4a .ogg`) → `save_text_to_video_speech_audio` (it takes `{ base64DataUrl, projectPath }`, **not** a file path — read the file and pass it as a base64 data URL) → **verify** `SCRTIPT_TO_VIDEO.text_to_video_speech_audio_url` is non-empty (an unsaved file silently falls back to the script rule). Skip the voice question; estimate scene count from the audio duration (~1 scene per 5 s).

**Count the sentences before Q2** — that is roughly the scene count, and it multiplies every per-image and per-second price quoted from here on. Treat it as a floor, not an exact number: the backend segmenter is an LLM that can split one long sentence into several short beats, so real scene count (and cost) can run above the sentence count.

### Q2 — Where should the visuals come from? (ROOT BRANCH → `textToVideoSourceMedia`)
Quote the cost in terms of the script just captured — "≈N scenes, so that's roughly X credits" — instead of generic per-unit prices.
1. **AI-generated images with motion** (Recommended; app default, cheapest visual route — ~1 image per scene) → `generated_images`
2. AI-generated video clips (most cinematic, by far the most expensive — a per-second charge on every scene) → `generated_video`
3. My own imported clips & photos, matched to the narration → `imported`

**Steer honestly on long scripts:** a 2-minute narration in `generated_video` costs roughly **1,500 credits on the cheapest model (Seedance 2.0 Mini)** and **4,000+ on Kling v3 or Seedance 2.5**. Quote the figure for the model you are about to recommend, and offer `generated_images` as the cheap alternative.

### Q3 — Format (options depend on Q2)
IF `generated_video` → ONLY two (1:1 is impossible; the panel silently rewrites a square project to **16:9**, and nothing guards this on the MCP path — so set a legal ratio yourself):
1. **Vertical 9:16 — TikTok / Reels / Shorts** (Recommended; new-project default)
2. Horizontal 16:9 — YouTube
ELSE → three: **9:16** (Rec) / 16:9 / 1:1 Instagram square.

### Q4 — Models (only for `generated_images` / `generated_video`; skip for `imported`)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template B) when `show_widget` exists: image-model cards first (2 cards), then — only IF `generated_video` — the video-model cards in the order below with the clip-cap note on each; never render Happy Horse. Only if no `show_widget` tool can be found: use the options below.
**Image model** (both generated modes — i2v needs a source still per scene):
1. **Nano Banana 2** (Recommended; default — 12 cr/image)
2. GPT Image 2.5 (2 cr/image at every aspect ratio — down from 6–7 on GPT Image 2; Flare, the fast variant)
3. GPT Image 2.5 Sunburst (also 2 cr/image; sharper detail and the best same-face likeness from references, a few seconds slower per still — settings value `GPT Image 2.5 Sunburst`)

**Video model** (only IF `generated_video`) — **the per-model clip cap is NOT harmless here** (see the warning below):
1. **Seedance 2.0 Mini — 9 cr/s** (Recommended; cheapest; 15 s cap)
2. Seedance 2.0 Fast — 14 cr/s (15 s cap)
3. Seedance 2.5 — 27 cr/s, top quality **and the only model that comfortably fits long scenes** (30 s cap)
4. Gemini Omni 1.1 Flash — ~12 cr/s (**10 s cap — the riskiest**; Google Tier-1 allows only ~20 requests/day, and once any Omni call fails the whole render latches over to Seedance 2.0 Fast — a visible style shift partway through)

⚠️ **A scene whose narration is longer than the model's cap loses spoken words.** The clip length is derived from the scene's speech, then clamped down to the model maximum — and the compositor then **trims the narration to match the clip** rather than stretching or freezing the picture. Nothing errors; there is only an info-level log line. The models' own auto-stitching does not save you, because text-to-video pre-clamps before the request. The segmenter can legitimately emit 30–40-word beats (12–16 s), so this is reachable in ordinary use. Warn when picking Omni or a 2.0-family model for a script with long sentences, and prefer Seedance 2.5 when the script is written in long flowing lines.

"Other" surfaces: Seedance 2.0 (18 cr/s) and Kling Video v3 Standard (26 cr/s). **`bytedance/seedance-2-0-mini` is the server catalog default for text_to_video** — but do not assume any persisted default: read the current value with `read_project_settings` and write the one you want with `set_text_to_video_settings`. **Never offer Happy Horse 1.0** (`custom:happyhorse-1.0`): its catalog row is disabled, and because it still passes MCP validation the setting saves cleanly and only fails later, at generation time. Clip length is never a user setting. Clips generate **silent**; all audio is the narration. **A clip that fails to generate silently falls back to that scene's still image** — the render succeeds and the user just sees a mix of motion and stills, so mention it rather than letting it look like a bug.

### Q5 — References (only for generated modes; all optional)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template A) when `show_widget` exists: three cards — *Style (0 / 3)*, *Characters (0 / 4)*, *Environments (0 / 4)* — all optional, all with *Skip*; after each character/environment pick ask its name with the question tool before re-rendering. Only if no `show_widget` tool can be found: use the options below.
"Should anything look consistent across the video?"
1. **No — let Shorz invent style, characters and places from the script** (Recommended)
2. A visual style — up to **3** style images (style ONLY: people in a style image never become scene subjects)
3. Recurring characters — up to **4**, each needs a **unique name** (+ optional notes like "the detective")
4. Recurring locations — up to **4**, named

Formats PNG/JPEG/WebP; images are downscaled to max edge 2048 px. Saved via `save_text_to_video_typed_reference { referenceType, imagePath, name }`. If the script has named recurring people, offer option 3 proactively — reference them by the names already in the script.

### Q5-imported — Main assets (only for `imported`)
Collect the file paths → `import_frontend_assets { assetType: "video", overridePaths }` — this is the ONLY source-media mode where main-lane video import is legal (it throws otherwise). Supporting footage in any mode imports as `broll`. Cost note: every imported asset gets a vision-analysis pass (cached on re-runs), so the estimate is a range. **Sanity-check coverage:** if the narration runs 3 minutes and they supplied two 5-second clips, say so — the matcher will reuse assets heavily.

### Q6 — Motion & transitions (batch; parts depend on Q2)
**Transitions between scenes:** 1. **AI Automatic — Shorz picks per cut** (Rec) → `["automatic"]` · 2. None (hard cuts) · 3. Fade · 4. My own pool (32 selectable effects; several = randomized per cut). ⚠ The disk default is `none` — `automatic` must be written explicitly.
**Motion on still images** — ask ONLY for `generated_images` / `imported`; **skip entirely for `generated_video`**, where the video model supplies real motion and this setting does nothing: 1. **AI Automatic** (Rec) → `["ai"]` · 2. Gentle zoom-in · 3. None · 4. My own pool (14 selectable motions).
**Transition sounds:** off (Rec) / on.

### Q7 — Finishing (batch)
**Subtitles:** 1. **Yes — burned-in** (Rec for short-form) · 2. No (disk default off).
**Music:** 1. **None** (Rec) · 2. My own track(s) (free; steer via PromptBar — "25% under the narration, fade out last 3 s"; plays through once at its imported length) · 3. Auto-music (paid; always covers the full runtime, looping past 5 min with a 5s crossfade).
**Look & mood note** (optional free text → PromptBar): lighting, palette, camera, pacing — NOT the script, NOT sizing.

## Summary + confirm

Per `README.md` contract. Include: source media, format, input mode + script length (or audio file), voice, models, references by name, transitions/motions, subtitles, music, mood note, and the cost estimate (planning LLM + ~1 scene per sentence × per-image cost + per-second video cost if `generated_video` + narration TTS ~13 cr/1k chars unless BYO key). **Paid only — no free tier.** Check `get_shorz_credits` first.

## Answer → execution map

| Step | MCP call |
|---|---|
| New project | `create_project { projectName, projectType: "text-to-video" }` |
| Q1 script | `set_text_to_video_settings { textToVideoInputMode: "script", textToVideoScript, textToVideoVoice }` |
| Q1 audio | `set_text_to_video_settings { textToVideoInputMode: "audio" }` + `save_text_to_video_speech_audio { base64DataUrl }` → verify saved |
| Q2 | `set_text_to_video_settings { textToVideoSourceMedia }` |
| Q3 | `switch_project_aspect_ratio` (respect the generated_video 16:9/9:16 rule) |
| Q4 | `set_text_to_video_settings { textToVideoImageModel, textToVideoVideoModel }` |
| Q5 | `save_text_to_video_typed_reference` per image (style ≤3; character/environment ≤4, named, unique) |
| Q5-imported | `import_frontend_assets { assetType: "video", overridePaths }` |
| Q6 | `set_text_to_video_settings { textToVideoTransitionTypes, textToVideoImageMotions }` + `set_audio_settings { transitionSounds }` |
| Q7 | `set_subtitle_settings` / MUSIC import + `set_audio_settings` / `set_user_instructions` |
| Render | `trigger_create_video` → poll `get_video_generation_status` |

Pre-flight: script ≥ 50 chars OR saved speech audio on disk; every character/environment ref named; ratio legal for the chosen video model; balance > 0. **Never** set `google/veo-3.1-i2v-fast` as video model — retired id, rejected by validation on write.
