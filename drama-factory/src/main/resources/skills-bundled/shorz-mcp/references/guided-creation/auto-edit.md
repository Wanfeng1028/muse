# Guided flow — AUTO-EDIT

The general-purpose type: the user's own footage/photos → ONE finished edited video. No dedicated panel — the flow is assets → what it's about → brief → optional panel features → Create Video. Follow `README.md` protocol. Tool semantics: `references/project-workflows/auto-edit.md`.

**Route here when:** "edit my footage", montage, highlight reel, vlog edit, slideshow from photos, "tighten this interview", "make a video from these files".
**Route away:** N separate short files from one long video → `clipping` (auto-edit always outputs ONE video); no footage at all → `text-to-video`, or `music-video` when the input is a song to visualize (their own footage cut to a song stays here — MUSIC lane + beat sync); talking avatar / podcast / product ad → those types.

**Two internal paths, chosen by main-asset count:** 1 asset → single-asset tool-call editing. 2+ assets → multi-asset montage planner. The branch matters less than it looks: the single-asset path can hand off to the same content-aware planner, so **filler-word removal and transitions between segments both work with one file**. Only two things are genuinely multi-asset-only: **beat sync** (no music data reaches the single-asset planner) and **chronological ordering** (meaningless inside one clip).

## Question sequence

### Q1 — Main footage (mandatory, ≥1 file)
"Which files are the video? Give paths or a folder."
1. **A folder / several clips** (Recommended → montage path)
2. Individual files (list them)
3. Photos only (slideshow)
4. One single video (→ single-asset path)

Accepted by the import dialog: `.mp4 .mov .avi .mkv .webm .jpg .jpeg .png .gif .webp` — but the auto-edit planner **silently skips `.webm` and `.gif` main assets** (they are in neither of its accepted lists), so convert those to `.mp4` / `.png` before importing, or they vanish from the edit with only a log line. No count cap; one asset per file name per lane (case-insensitive — duplicates are skipped, check `skippedCount`). Free tier: the 30-min cap is measured on the FIRST main asset only, and not at all on the MCP path. The UI never blocks Create Video on an empty lane — the wizard must require ≥1.

**Probe the footage before continuing** (`get_media_info` on a sample): its orientation sets the Q3 recommendation, and whether it carries an audio track decides whether speech-dependent options (captions, filler-word removal, imported-SFX placement, auto-zoom) are offered at all. Photos-only is silent by definition.

### Q2 — What's this video about? (the creative brief — the single biggest driver of the edit)
"In a sentence or two: what is this video, and what should the edit make sure to keep?"

Free text, no presets — this is the thing the user actually came to make. Prompt for: the subject/occasion, who or what matters most, any must-keep moments, and the intended audience or platform. Offer 3 concrete openers as examples rather than options, e.g. *"a highlight reel of our Japan trip — keep the food and the temple day, my daughter should be in it"*, *"a product demo — the unboxing then the three main features"*, *"a talk recap — keep the strongest argument, cut the Q&A"*.

Everything downstream (style, length, cleanup, motion) refines this sentence; without it the brief is only mechanical settings and the AI edit has no intent to serve. If the user has nothing to add, note that and continue — but ask first, every time.

### Q3 — Output format (always ask — a new project silently defaults to 9:16)
1. **Match the source orientation** — 16:9 for landscape footage, 9:16 for footage already shot vertical (Recommended; base it on the Q1 probe)
2. Vertical 9:16 — TikTok / Reels / Shorts
3. Horizontal 16:9 — YouTube
4. Square 1:1 — Instagram feed

Lead with whatever the platform they named implies; fall back to source orientation. If source and target ratios differ, offer "fill the frame — no black bars" in Q6 (it becomes a per-clip Framing instruction in the brief).

### Q4 — Extra material (batch these three independent questions in ONE call)
**B-roll?** 1. **None — main footage only** (Rec) · 2. My own b-roll files (videos+images, free) · 3. Auto GIFs (free) / auto web images (**free only inside a free run** — on credits the image search is a billed proxy call) · 4. AI-generated b-roll (**paid**)
**Sound effects?** 1. **None** (Rec) · 2. Auto SoundFX — bundled sounds, free · 3. My own SFX files (auto-placed by AI) — **omit options 2 and 3 entirely when the footage has no speech track**; placement is transcript-driven and silently does nothing without one
**Music?** 1. **None** (Rec if footage has dialogue) · 2. My own track(s) — free, unlimited, enables beat-sync + arrangement, plays through once at its imported length (match the total to the video length for full coverage) · 3. Auto-music, AI-generated (**paid**, cannot beat-sync, but always covers the full runtime — it loops past 5 min with a 5s crossfade)

IF own music → one follow-up: play under video (rec) / **cut the edit to the beat** / music only, mute clips / custom order-section-fades. Beat sync is mutually exclusive with speed, loop, silence-removal and filler-word removal — suppress those in Q6 if chosen.

### Q5 — Editing style + target length (one batched call, 2 questions)
**Style:** 1. **Fast & punchy — tight cuts, high energy** (Rec for social) · 2. Calm & cinematic — longer holds, slow zooms, dissolves · 3. Clean & informative — hard cuts, minimal effects
**Length:** 1. **~60 s** (Rec) · 2. ~30 s · 3. ~2 min · 4. Full length, just tightened

Sanity-check against the source: asking for ~2 min out of 40 seconds of footage is impossible — say so and offer the achievable length.

### Q6 — Cleanup & order (multi-select; all opt-in, all OFF by default)
1. **Nothing — keep it simple** (Rec)
2. Cut dead air / long pauses — **speech required**
3. Cut filler words (um, uh, like-as-a-tic) — **speech required** (works with one file too, not multi-asset-only)
4. Chronological order — **multi-asset only**; dates come from EXIF, then video container metadata, then the filename, then the file timestamp

Drop options 2 and 3 entirely for photos-only or silent footage rather than offering a no-op. When Q3 chose a ratio different from the source orientation, also offer **"everything must fill the frame — no black bars"** here (a per-clip Framing instruction; works on videos and images). Chronological ordering is duration-neutral and combines freely with everything — **including beat sync**, unlike the speed/loop/silence/filler group. Clip order alternative: they can name an exact order using `"filename.mp4"` mentions.

### Q7 — Motion & transitions
1. **Hard cuts, no motion** (Rec) — but recommend option 3 for a photos-only slideshow, where stills without motion read as dead air. With a single main file, transitions still apply between segments of that clip; they are just rarer
2. Dissolves between clips
3. Slow zooms & pans (best for photos; zoom feel: normal 1.4× / subtle 1.15× / strong 1.9×; can target a named subject — "zoom onto the lighthouse", images only)
4. Both — dissolves + zooms

### Q8 — Subtitles & titles
**IF the footage has no speech** (photos-only or a silent track) skip straight to titles — captions have nothing to transcribe:
1. **A title card at the start** (Recommended for silent/photo edits; Manual: start 0–60 s, duration 0.5–60 s)
2. None

**ELSE:**
1. **Burned-in captions, bold, 4 words/line** (Recommended for social)
2. Captions + spoken-word highlight
3. A title card at the start (Manual timing) — with or without captions
4. None

### Q9 — Polish (multi-select, default none)
1. **None** (Rec) · 2. Auto Zoom on key moments (Intelligent, count 1–30, strength 1–2) — **transcript-driven, so a no-op on silent or photos-only footage; do not offer it there**; out-of-range values are **rejected with an error**, unlike clip count which clamps silently · 3. Animated border (width 1–100; 9 animations plus None) · 4. Overlay film effects (**multi-select**, not one)

Under "Other": face tracking, freeze frame, dramatic grayscale, color grading, audio visualization (10 styles), reverb (9 presets plus None — "Studio Clean" is currently a passthrough), dubbing (**paid**, 108 Dubbing v2 languages incl. dialects), noise removal (**paid**).

## Brief composition (the critical step)

Compose ONE brief with the **Q2 sentence as its spine**, refined by the Q5–Q7 answers and the Q4 music-behaviour follow-up (order, sections, placement, beat-sync, fades). Persist via `set_user_instructions`. Rules:
- **Must be more than 10 characters** — below that the auto-edit stage is silently skipped, and with several assets that ships only the FIRST file rather than a montage. Treat the brief as required.
- Positive imperatives only — the raw text goes verbatim to every LLM stage; negatives waste tokens. To guarantee something stays off, leave its panel off instead.
- Reference specific files as `"filename.mp4"` (double-quoted bare filename).
- Never include aspect ratio, pixel sizes, or fps.

## Summary + confirm

Per `README.md` contract. Include: what the video is about (the Q2 sentence), asset counts per lane, format, the composed brief text, every panel toggle being switched on, **paid features flagged** (AI b-roll, dubbing, auto-music, noise removal, AI image edits). At zero balance these **fail individually and the render still completes without that feature** — it does not abort — so turn them off rather than letting them silently drop out. Also state free-run/credit status. Auto-edit is **free-tier eligible** (allowance and cap are server-driven; pin the free model yourself on the MCP path).

## Answer → execution map

| Step | MCP call |
|---|---|
| New project | `create_project { projectName, projectType: "auto-edit" }` |
| Q1 | `import_frontend_assets { assetType: "video", overridePaths }` — check `skippedCount` |
| Q3 | `switch_project_aspect_ratio` |
| Q4 | `import_frontend_assets` (`broll` / `sound` / `music`) + `set_broll_settings` + `set_audio_settings` |
| Q2 + Q5–Q7 | the composed brief → `set_user_instructions` |
| Q8 | `set_subtitle_settings` / `set_title_settings` |
| Q9 | `set_general_video_settings` / `set_border_settings` / `set_overlay_settings` / `set_audio_visualization_settings` |
| Free tier | `set_main_ai_model` to the free model id (or `mainAiModelName` on trigger) |
| Render | `trigger_create_video` → poll `get_video_generation_status`. **`completed_no_output` means no file was produced at all** — an empty main lane, or a plan/analysis stage that returned nothing. A too-short brief does NOT cause it |
