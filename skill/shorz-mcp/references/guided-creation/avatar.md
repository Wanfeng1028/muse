# Guided flow — AVATAR

One presenter, one face, lip-synced to speech; the generated avatar clip then runs through the normal auto-edit chain (subtitles, B-roll, music…) if enabled. Follow `README.md` protocol. Tool semantics: `references/project-workflows/avatar.md`.

**Route here when:** talking head, AI presenter/spokesperson, UGC ad read, "make me say this", faceless channel WITH a host face, digital twin.
**Route away:** two speakers / dialogue → `podcast`; no person on screen → `text-to-video`; product ad from product photos → `advertisement`; editing their own filmed footage → `auto-edit`; visuals for a song (beat-cut scenes, not one lip-synced face) → `music-video`.

**Order matters:** set the aspect ratio before generating the avatar image. The in-app Avatar Creator sizes its output from the project ratio (16:9→1536×1024, 9:16→1024×1536, 1:1→1024×1024); over MCP you pass `aspectRatio` per call, so there it is a quality safeguard rather than a hard dependency — a mismatched image is centre-cropped at render time.

## Question sequence

### Q1 — Format
1. **Vertical 9:16 — TikTok / Reels / Shorts** (Recommended; app default)
2. Horizontal 16:9 — YouTube
3. Square 1:1 — Instagram feed

### Q2 — Who is the presenter? (branch point)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template A) when `show_widget` exists: a single *Presenter* card with *Open file picker* (`extensions: ["jpg","jpeg","png","webp"]`) and *Generate with AI* (routes to option 1/3/4 questions). Only if no `show_widget` tool can be found: use the options below.
1. **Generate a presenter with AI from a description** (Recommended)
2. Use a photo / image file I already have
3. Make it look like a specific real person (face reference photos)
4. Pick a ready-made art style

IF 1 → ask for a description (the desktop modal caps this at 4000 chars; MCP does not; nudge: age, hair, clothing, setting, lighting — head-and-shoulders facing camera) + a look (photoreal (rec) / cinematic / studio corporate / casual UGC selfie). Generate via `generate_images { description, aspectRatio, imageModel: "gpt-image-2", imageQuality: "medium", numVariations: 1 }` → `select_avatar_image`.
IF 2 → ask for the path. MCP accepts `.png .jpg .jpeg .webp` (TIFF works only in the desktop UI).
IF 3 → up to **3** face photos (JPEG/PNG/WebP), then ask the SCENE (pose/clothing/background — not the face) → `generate_images { referenceImages: [...] }` → `select_avatar_image`.
IF 4 → the app ships **33 preset styles**. Offer 4 at a time with "show more": start with 3D Pixar (rec) / Realistic cinematic / Claymation / Studio Ghibli; other notables: flat vector, comic book, pixel art, LEGO, South Park cutout, minimalist line art, cyberpunk neon 3D, watercolor. The style prompt becomes the description + its thumb the reference.

### Q3 — Where do the words come from? (branch point — ask BEFORE angles, the script sets the clip count)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template C) when `show_widget` exists: after the script is saved, render the voice cards (pre-filter to 8 by fit, `Show more` for the rest); the pick maps to `set_avatar_settings { avatarVoice }`. Only if no `show_widget` tool can be found: use the options below.
1. **I have a script (or want one written) — pick an AI voice** (Recommended)
2. I have a voiceover audio file already
3. I'll record my own voice (UI-only: Avatar panel → Record Audio; MCP has no recorder)

IF 1 → collect/draft the script. Limits: ≤**40,000 chars** AND ≤**6,000 words**; must be more than **10 characters** (counted raw, untrimmed) or the render produces **no output file at all**. Show the ~150 wpm duration estimate. If drafting from a topic, ask the target length first (**~30 s** (Rec) / ~60 s / ~2 min / longer) and confirm the draft before saving. → `set_avatar_settings { avatarInputMode: "script", avatarScript }`. **Always overwrite** — older projects (created before 2026-08-19) ship the 45-character default "Write your script here for the avatar to speak", which clears the >10 gate and would be spoken aloud if left in place. New projects start empty.
Then **voice**: `list_elevenlabs_voices` → offer 4 by fit (warm female / warm male / energetic / authoritative), offer a preview via `generate_tts_preview` (first ~200 chars). → `set_avatar_settings { avatarVoice }`.
IF 2 → path. `select_avatar_audio` (and the desktop file picker) accept `.mp3 .wav .m4a .ogg .aac .flac`, but the renderer only supports `.mp3 .wav .m4a .aac .webm` — **`.ogg` and `.flac` are accepted at selection and then fail validation before any conversion**, so insist on `.mp3/.wav/.m4a/.aac`. Sets mode + audio URL in one call.

**Count the sentences before moving on** — that number is the clip count if angles are enabled, and it drives the Q5 model advice.

### Q4 — Camera angles (needs an avatar image AND a known script length)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template A) when `show_widget` exists: for option 3 only — one *Angle images (n / 3)* card whose picker phrase is `Open the Shorz file picker for the angle image`; re-render until 3 or the user continues. Only if no `show_widget` tool can be found: use the options below.
Quote the real, *editorial* consequence from the script just captured: "your script is N sentences, so the video will cut between angles N times instead of holding one pose the whole way."
1. **Yes — auto-generate 3 angles (¾ left, close-up, wide)** (Recommended once the script runs past a few sentences — a static pose gets visually monotonous fast)
2. No — single pose (fine for a very short script, and skips the extra image generations)
3. I'll supply my own angle images (up to 3)

**Be accurate about the cost:** angles do *not* multiply the bill — the per-second rate depends only on the model, and the same script is the same duration either way. Angles add three one-time image generations (~18–21 credits total, and not shown in the panel cost bar) plus whole-second rounding of about **0.5 s per sentence** — roughly 10% on a script with 5-second sentences, closer to 20% on short punchy lines. **In audio mode**, angles additionally force a transcription pass to split the voiceover per sentence (script mode does not). Present this as a *look* decision, not a budget one.

Max **3** angles; changing the main image resets both the angles and the crop. Worth knowing for option 2: a long script is split at silence to fit the model's per-request window and stitched automatically, and **without angles every split segment regenerates from the same still, so the pose visibly resets at each seam** (roughly every 29 s on OmniHuman, 60 s on Kling). With angles the split is per sentence anyway, so this never shows.

### Q5 — Quality / budget (avatar model)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template B) when `show_widget` exists: three model cards in this order, Kling Avatar Pro recommended; price from the live catalog; OmniHuman card carries the highest-cost note. Only if no `show_widget` tool can be found: use the options below.
1. **Kling Avatar Pro — balanced quality/cost** (Recommended)
2. Kling Avatar — cheapest
3. OmniHuman 1.5 — highest quality, most expensive per second

→ `set_avatar_settings { avatarModel }`. Quote prices from `get_shorz_usage_and_pricing` / the live catalog — never hardcoded rates. A fresh project's disk default is `Kling` (canonicalizes to Kling Avatar std), so set this explicitly.
IF a Kling model → offer **motion style** in the same step (≤2500 chars → `avatarMotionInstructions`): subtle presenter (rec) / energetic / calm authoritative / none. Skip for OmniHuman (the UI hides it; MCP accepts it and the model ignores it).

### Q6 — Extras (multi-select; every panel is OFF by default on a new project)
1. **Subtitles** (Recommended for social)
2. B-roll cutaways (imported = free; AI B-roll costs credits)
3. Background music (imported free, plays once; auto-music paid, loops to cover the whole video)
4. Nothing — just the talking avatar

If any chosen → also ask ONE free-text "editing guidance" line for the PromptBar (`set_user_instructions`) — explicitly NOT the spoken script, never aspect/pixel tokens. Transitions (`avatarTransitions`: `None` or `Transition01`–`Transition20` light leaks) apply whenever the render produces **2+ clips** — that means angles, but also a no-angle script long enough to be split at the model's per-request window. They are free to change and never trigger regeneration.

## Summary + confirm

Per `README.md` contract. Include: format, presenter source (+ style/model used), input mode + script length or audio file, voice, angles, avatar model + motion, extras, cost estimate, and the runtime warning ("minutes to hours depending on script length"). **Paid only — no free tier**: require signed-in + balance > 0 (`get_shorz_credits`) before offering "start now".

## Answer → execution map

| Step | MCP call |
|---|---|
| New project | `create_project { projectName, projectType: "avatar" }` |
| Q1 | `switch_project_aspect_ratio` (BEFORE image generation) |
| Q2 generate | `generate_images` (async → `get_job_status`) → `select_avatar_image { imageFilePath }` |
| Q2 own file | `select_avatar_image` (clears any angles + resets crop) |
| Q3 script | `set_avatar_settings { avatarInputMode: "script", avatarScript, avatarVoice }` |
| Q3 audio | `select_avatar_audio { audioFilePath }` |
| Q4 auto angles | 3× `generate_images` with angle prompts → `set_avatar_settings { avatarAngleImages: [...] }` (max 3) |
| Q4 own angles | `select_avatar_angle_image` per file (errors without a main image / beyond 3) |
| Q5 | `set_avatar_settings { avatarModel, avatarMotionInstructions? }` |
| Q6 | `set_subtitle_settings` / `set_broll_settings` / `set_audio_settings` / `set_avatar_settings { avatarTransitions }` + `set_user_instructions` |
| Render | `trigger_create_video` → poll `get_video_generation_status` |

Pre-flight (the UI does NOT block on these — we must): `avatarImage` set + file exists; script mode → script > 10 chars AND voice set; audio mode → `avatarAudioUrl` set + file exists. Main VIDEO lane is disabled for avatar — supporting footage imports as `broll`. Framing: `avatarCropX` / `avatarCropY` (0–100) **pan the avatar inside the frame on 9:16, 1:1, and 16:9 with a landscape image**. The one case where the image is NOT cropped is 16:9 with a portrait avatar — there it letterboxes and `avatarCropX` slides the letterboxed clip left↔right instead. Offer under "Other".
