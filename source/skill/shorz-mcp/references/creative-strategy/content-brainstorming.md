# Content brainstorming & viral playbooks

High-retention short-form formats distilled from top-performing organic apps (e.g. [Social Growth Engineers](https://www.socialgrowthengineers.com/)), mapped to Shorz **`projectType`** values and MCP tools. Use this when the user wants **ideas**, **hooks**, **scripts**, or **format selection** — not panel field documentation.

**Global rules:** Follow **`../../SKILL.md`** for PromptBar semantics, aspect ratio (`switch_project_aspect_ratio`), and project targeting. Never put export geometry (`9:16`, pixel sizes) in PromptBar text.

---

## How agents should use this file

1. **Clarify goal** — platform (TikTok / Reels / Shorts), niche, product, and whether the user wants faceless, founder-led, or avatar-led content.
2. **Pick a playbook** from the tables below (or combine two: e.g. hook from POV Shock + CTA from Before/After).
3. **Map to Shorz** — choose `projectType`, then open the matching **`../project-workflows/*.md`** before any `set_*` calls.
4. **Draft the creative brief** — hook (0–2 s), body (3–15 s), CTA (last 2–3 s). Put spoken text in the correct panel field (`podcastScript`, `textToVideoScript`, `avatarScript`, etc.), not PromptBar, per **SKILL.md**.
5. **Propose 3–5 variants** — same format, different hooks or niches; let the user pick before configuring.
6. **Execute** — configure panels → optional headless prep → `trigger_create_video` → poll `get_video_generation_status`.

---

## Viral video anatomy (what actually moves reach)

Every strong organic short shares the same skeleton:

| Layer | Job | Shorz lever |
|---|---|---|
| **Hook (0–2 s)** | Stop the scroll — contrast, shock, POV, or bold claim | First frame in `advertisement` / title overlay / subtitle style / clip start in `clipping` |
| **Format** | Recognizable pattern viewers already binge (split screen, debate, slideshow) | `projectType` + B-roll layout + overlay |
| **Retention body** | Payoff, demo, or story beat every 2–3 s | `auto-edit` pacing, `text-to-video` scenes, satisfying B-roll |
| **CTA** | One clear action — save, comment, try, download | `set_title_settings`, last slide in `concat_media` chain, spoken line in script |
| **Duration** | Most winners: **7–15 s** for ads; **15–45 s** for story/education | `advertisementDurationSeconds`, `trim_video`, clipping PromptBar steer |

**Organic loop:** Post format → measure saves/comments → remix hook → repost same structure with new niche copy. Shorz makes the **structure** repeatable via saved projects and headless `concat_media` chains.

---

## Creative brief template (agent output)

When pitching ideas, use this structure:

```text
Concept: [one line]
Playbook: [name from this doc]
Project type: [auto-edit | text-to-video | avatar | podcast | advertisement | clipping | music-video]
Hook (on-screen + spoken): [first 2 seconds]
Body: [what happens seconds 2–12]
CTA: [comparison / curiosity / download]
Assets needed: [product still, screen recording, satisfying clip, etc.]
Shorz tool chain: [ordered MCP tools]
Aspect: [9:16 default for TikTok/Reels — set via switch_project_aspect_ratio]
```

---

## Hook cheat sheet

| Hook style | Example copy | Best `projectType` | MCP starting points |
|---|---|---|---|
| **Outcome first** | "I can't believe this is the same photo" | `advertisement`, `auto-edit` | `select_advertisement_image`, `set_broll_settings` |
| **POV reaction** | "POV: you just found the app that…" | `avatar`, `auto-edit` | `set_avatar_settings`, `save_avatar_audio`, `set_overlay_settings` |
| **Study / pain** | "Why is [subject] so hard?" / "My GPA before vs after" | `text-to-video`, `auto-edit` | `set_text_to_video_settings`, `set_subtitle_settings` (bold captions) |
| **Competitor mention** | "Sorry [Big App], I'm cheating on you with…" | `avatar`, `podcast` | `set_podcast_settings` (debate skit), `set_user_instructions` for tone only |
| **Duolingo-for-X** | "Duolingo but for [niche]" | `text-to-video`, `advertisement` | `set_text_to_video_settings`, short `advertisementDurationSeconds` |
| **Founder confessional** | "I built this because I was tired of…" | `avatar`, `auto-edit` | `save_avatar_image`, `save_avatar_audio`, main asset talking head |
| **Cliffhanger story** | "She didn't know the door was already open…" | `text-to-video`, headless loop | `save_text_to_video_speech_audio`, `concat_media` + satisfying B-roll |
| **Sign / text on screen** | Handwritten sign: "Stop scrolling if you…" | `auto-edit`, `clipping` | `set_title_settings`, `import_frontend_assets` |
| **Before / after split** | Side-by-side or swipe reveal | `advertisement`, `auto-edit` | `switch_project_aspect_ratio`, `set_broll_settings` (fit-mode `brollPositionX/Y` + `brollFitWidthPercent`) |
| **Hot take debate** | "AI will replace tutors" vs "No it won't" | `podcast` | `set_podcast_settings` with `[Interviewer]` / `[Interviewee]` tags |

---

## CTA cheat sheet

| CTA type | Example | Where to put it |
|---|---|---|
| **Comparison** | "Comment which looks better: A or B" | Title overlay or last `concat_media` slide |
| **Curiosity** | "Part 2 if this hits 500 saves" | Spoken line in `podcastScript` / `textToVideoScript` |
| **Soft download** | "Search [AppName] — link in bio" | `set_title_settings` + avatar closing line |
| **Save trigger** | "Save this for your next [exam / workout / trip]" | Subtitle emphasis via `set_subtitle_settings` |
| **Identity** | "If you're a [student / founder / mom], you need this" | PromptBar mood only; hook in script |
| **Challenge** | "Try this on your worst photo" | `advertisement` brief + product image |

---

## Core viral playbooks (mapped to Shorz)

### 1. Before-vs-After contrast slideshow (WayShot playbook)

**Goal:** Drive saves and shares via aesthetic transformation.

**Hook:** Show the polished, jaw-dropping **result first** (1–2 s), then reveal the raw phone source — **reverse** the obvious order.

**Structure:** Result → raw → quick tool demo → side-by-side → CTA ("Which would you post?").

| Shorz | Choice |
|---|---|
| **Project type** | `advertisement` (single hero transformation) or `auto-edit` (multi-clip montage) |
| **Aspect** | `switch_project_aspect_ratio` → `9:16` |

**MCP tool chain:**

1. `create_project` (if needed) → `advertisement` or `auto-edit`
2. `import_frontend_assets` — `broll` for the before/after stills; `video` for screen captures (`auto-edit` only). **Do not use `assetType: "image"`** — it returns metadata only and persists nothing to any lane.
3. `select_advertisement_image` — `role: product` (after) + optional `person` (creator reaction still). This, not `import_frontend_assets`, is how stills reach an `advertisement` project.
4. `set_advertisement_settings` — shortest ad length (`advertisementDurationSeconds: 10`; ads are 10–40 s in 10 s steps). The ad engine is locked to Gemini Omni 1.1 Flash — no model to pick.
5. `set_broll_settings` — the comparison is a **fit-mode overlay**, not a tile grid: `fullscreenBRoll: false` plus `brollPositionX` / `brollPositionY` (center-X / top-Y percent) and `brollFitWidthPercent` (30–100). There is **no** tile, split, or picture-in-picture layout control — an inset is just a narrow fit width parked to one side (`auto-edit` path)
6. `set_title_settings` — "BEFORE → AFTER" or swipe-style headline
7. `set_user_instructions` — ad brief: outcome-first hook, comparison CTA (no pixel sizes)
8. `trigger_create_video` → `get_video_generation_status`

**Headless prep (optional):** `fit_to_aspect`, `concat_media` to stitch result clip + raw clip + CTA slide before importing.

**Niche variants:** photo editing, room makeover, skincare, fitness progress, UI redesign.

---

### 2. POV shock reaction & screen flip (Replit / Cantina playbook)

**Goal:** Emotional hit + instant product demo.

**Hook:** Selfie-style reaction — shocked face, headphones, hands over mouth — then **flip** to screen recording of the product working.

| Shorz | Choice |
|---|---|
| **Project type** | `avatar` (talking head + layered demo) or `auto-edit` (reaction clip + inset screen via fit-mode B-roll) |
| **Aspect** | `9:16` |

**MCP tool chain:**

1. `set_avatar_settings` — script mode with short reaction line ("Wait… this actually works?")
2. `save_avatar_image` / `select_avatar_image` — creator or stock avatar
3. `save_avatar_audio` or TTS via script field
4. `import_frontend_assets` — the screen recording as **`broll`**. `assetType: "video"` is **rejected in an `avatar` project** (no main VIDEOS lane — the tool errors and tells you to use `broll`); it is only available on the `auto-edit` path.
5. `set_broll_settings` — the screen capture is either fullscreen (`fullscreenBRoll: true`) or a fit-mode overlay you place with `brollPositionX` / `brollPositionY` + `brollFitWidthPercent` (e.g. lower third = low `brollPositionY`, width ~60). There is **no timed "flip after 2 s"** and no PIP mode — placement is a static setting, and when the cut happens is the compositor's call
6. `set_overlay_settings` — whip pan / flash transition at flip point (`get_overlay_effects` for available ids)
7. `set_user_instructions` — optional: "fast cuts, high energy, no corporate tone" (not the spoken script)
8. `trigger_create_video`

**Cantina variant — competitor hook:** Open with `[Competitor] could never…` then demo your app. Use `podcast` for two-voice banter or `avatar` for single spokesperson.

---

### 3. "PDF to brainrot" split-screen (Coconote playbook)

**Goal:** Faceless high-retention study / productivity content.

**Hook:** Satisfying dopamine lane (Subway Surfers, Minecraft parkour, ASMR slicing) **plus** main lane showing app converting PDF → summary / flashcards / diagram. Bold captions carry the story.

| Shorz | Choice |
|---|---|
| **Project type** | `text-to-video` (narrated explainer) or `auto-edit` (imported satisfying + screen B-roll) |
| **Aspect** | `9:16` |

**MCP tool chain:**

1. `set_text_to_video_settings` — `textToVideoInputMode: script`, `textToVideoSourceMedia: imported` or `generated_images`
2. `textToVideoScript` — concise TTS: problem → app solves it → CTA (panel field, not PromptBar)
3. `save_text_to_video_speech_audio` — if refining voice timing before render
4. `import_frontend_assets` — satisfying `broll` + screen `video` (when `imported`)
5. `set_broll_settings` — **there is no split-tile / 40-60 layout.** The satisfying lane is fit-mode B-roll placed with `brollPositionX` / `brollPositionY` + `brollFitWidthPercent` (e.g. width 100 parked at the bottom half via `brollPositionY`), or fullscreen (`fullscreenBRoll: true`) if it should take the frame outright
6. `set_subtitle_settings` — high-contrast animated style. Animation ids come from the **subtitle** enums (`Pop`, `Bounce`, `Zoom-in`, `Slide-in from Bottom`, …) plus bold color/stroke; **`Glitch` and `Retro VHS` are NOT subtitle animations** — they are *zoom overlay effects* (`zoomInEffects` / `zoomOutEffects` on `set_general_video_settings`) and passing them here fails validation
7. `set_audio_settings` — duck music under voice
8. `switch_project_aspect_ratio` → `9:16`
9. `trigger_create_video`

**StudyTok hooks:** "Why tf is [language] so hard?", "My GPA before vs after using this", "POV: finals week and you still haven't opened the textbook."

---

### 4. Dual-speaker creative debate skit (Fable playbook)

**Goal:** Narrative tension — two opposing views in rapid exchange.

**Hook:** Line 1 is controversial; line 2 immediately disagrees.

| Shorz | Choice |
|---|---|
| **Project type** | `podcast` |
| **Aspect** | `9:16` (stacked top/bottom) or `16:9` (side-by-side). **Not `1:1`** for a two-on-screen debate — see the warning below |

**MCP tool chain:**

1. `set_podcast_settings`:
   - `podcastScript` with tagged lines, e.g.  
     `[Interviewer] AI replaces every tutor by 2027.`  
     `[Interviewee] Only if you've never met a good tutor.`
   - Contrasting `podcastInterviewerVoice` / `podcastIntervieweeVoice` — use `list_elevenlabs_voices`
   - `podcastAvatarDisplayType`: `Show Both Avatars` for split debate
   - Optional `podcastCameraMotion`: `Handheld Camera` for urgency
2. `select_podcast_avatar_image` for each role. **`import_frontend_assets` with `assetType: "avatar"` (or `"image"`) will not do this** — those return metadata only and persist nothing; use the dedicated select/save avatar tools (`select_podcast_avatar_image`, `select_avatar_image` / `save_avatar_image`).
3. `set_user_instructions` — B-roll/mood only: "minimal B-roll, fast pacing"
4. `switch_project_aspect_ratio`
5. `trigger_create_video`

⚠️ **Never pair `1:1` with `Show Both Avatars`.** A square podcast project renders **fullscreen single-avatar regardless of the display type** — but the idle-clip cost is keyed on the display type **alone**, so the render still generates and bills **2 idle clips (~4 s each)** the viewer never sees. On a square project use `Show Only Talking Avatar`; keep `Show Both Avatars` for `9:16` (stacked) or `16:9` (side-by-side). See **`../guided-creation/podcast.md`** → Q3/Q4.

**Variants:** strict professor vs lazy student; user vs app; skeptic vs fanboy; "old way" vs "new way."

---

### 5. Satisfying storytelling loop (Macaron AI playbook)

**Goal:** Low-cost faceless stories with constant brand presence — creepy, wholesome, or confession formats over satisfying footage.

**Hook:** Intriguing first sentence over visually satisfying B-roll; loop ends on cliffhanger or CTA.

| Shorz | Choice |
|---|---|
| **Project type** | Headless assembly **or** `text-to-video` / `auto-edit` for full render |
| **Aspect** | `9:16` |

**Headless MCP chain (7–12 s loop):**

1. `get_media_info` — confirm duration and resolution of satisfying clip + brand clip
2. `trim_video` — cut satisfying background to 7–12 s
3. `change_video_speed` — 1.15×–1.25× for retention
4. `fit_to_aspect` — pad to `9:16` if source is horizontal
5. `fade_video` / `audio_fade` — smooth loop points
6. `concat_media` — `[hook clip] + [demo/CTA slide] + [optional logo sting]`
7. Import result into new `auto-edit` project if adding captions via `set_subtitle_settings`

**Full-project path:** `text-to-video` with `generated_images` or imported satisfying B-roll + narration script; `set_subtitle_settings` for story text overlay.

**Story angles:** "She didn't know…", "I still think about…", "The last person who tried this…"

---

## Additional high-performing formats

### Founder-led confessional

**Pattern:** Face to camera, raw lighting, "I built X because Y failed me."

| Shorz | `avatar` or `auto-edit` with imported talking-head `video` |
| Tools | `save_avatar_image`, `save_avatar_audio`, `set_subtitle_settings` (optional captions), `set_user_instructions` for edit pacing |

---

### Clipping long-form into Shorts

**Pattern:** Podcast, webinar, or interview → auto-extract viral moments.

| Shorz | `clipping` |
| Tools | `download_social_video` or `import_frontend_assets` (`video`) → `update_project_settings` (`ASSET_PATHS`, `CLIPING.clipping_num_clips`) → `switch_project_aspect_ratio` (`9:16`) → `set_user_instructions` (optional: "hooks about [topic], 15–30 s each") → `trigger_create_video` |

**PromptBar steer examples:** "Prefer moments with strong opinions", "15 second clips", "TikTok hooks only."

---

### Sign-holding / static hook frame

**Pattern:** Person holds phone or sign with bold text; cuts to demo.

| Shorz | `auto-edit` |
| Tools | `import_frontend_assets`, `set_title_settings` (large headline), `set_broll_settings`, quick `trigger_create_video` |

---

### "Duolingo for X" positioning

**Pattern:** Anchor to a famous app metaphor so viewers instantly get the category.

| Shorz | `advertisement` (10 s product hero) or `text-to-video` (explainer) |
| Tools | `set_advertisement_settings` + product still; script: "It's like Duolingo but for [skill]" |

---

### Daily volume / series hooks (Fit With Coco playbook)

**Pattern:** Same format daily; only the hook number or challenge changes.

| Shorz | Reuse one `auto-edit` or `avatar` project; swap PromptBar + title |
| Tools | `set_user_instructions`, `set_title_settings` ("Day 14 of…"), `trigger_create_video` |

---

### Faith / lifestyle / niche story stacks

**Pattern:** Text-on-screen testimony + soft music + product at end.

| Shorz | `text-to-video` + `set_audio_settings` (music bed) |
| Tools | `set_text_to_video_settings`, `set_subtitle_settings`, gentle CTA in last scene script |

---

## Project type picker (quick reference)

| User intent | Start here |
|---|---|
| Product demo / transformation / hero ad | `advertisement` |
| Montage with captions, music, mixed media | `auto-edit` |
| One spokesperson, script or audio | `avatar` |
| Two characters arguing or interviewing | `podcast` |
| Narrated storyboard, scene-by-scene | `text-to-video` |
| Extract shorts from long video | `clipping` |
| Visuals for a song, cut on the beat | `music-video` |
| Stitch / trim / loop without a project | Headless tools → **`../headless-workflows/single-asset-edit.md`** |

---

## End-to-end agent workflow (brainstorm → publish)

1. **Brainstorm** — output 3–5 briefs from this doc; user picks one.
2. **Project** — `create_project` or `get_current_open_project`; confirm `projectType`.
3. **Format** — `switch_project_aspect_ratio` (`9:16` default for short-form).
4. **Assets** — `import_frontend_assets`, `select_*` helpers, or `download_social_video` (clipping).
5. **Configure** — panel `set_*_settings` per matching workflow file.
6. **Brief vs script** — PromptBar = creative direction only; spoken content in typed panel fields (**SKILL.md**).
7. **Render** — `set_main_ai_model` (if requested) → `trigger_create_video` → poll `get_video_generation_status`.
8. **Post-production** — optional headless `trim_video`, `concat_media`, `fade_video` for platform-specific length.
9. **Publish** — YouTube / TikTok MCP tools when user asks (see **SKILL.md** publish section).

---

## Brainstorm prompts (ask the user)

- What product or niche? Who is the viewer (student, founder, parent)?
- Faceless, avatar, or real footage?
- Outcome-first or curiosity-first hook?
- Single 10 s ad or 30 s story?
- Competitor or "before/after" angle?
- Need clipping from existing long video?

Use answers to narrow to **one playbook** and **one project type** before touching MCP settings.

---

## Sources & inspiration

Formats and hooks in this guide are adapted from public organic growth breakdowns published by [Social Growth Engineers](https://www.socialgrowthengineers.com/) (WayShot, Replit, Coconote, Macaron, Fable, Cantina, StudyTok patterns, and related case studies). Treat them as **starting templates** — always localize copy, comply with platform policies, and avoid misleading claims.
