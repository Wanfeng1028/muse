# Guided flow — ADVERTISEMENT

Storyboard-driven ad built from reference stills: story-plan LLM → GPT Image 2.5 storyboard per scene → Gemini Omni 10-second clip per scene → concatenated. Follow `README.md` protocol. Tool semantics: `references/project-workflows/advertisement.md`.

**Route here when:** "ad / promo / commercial for my product", UGC-style product ad, founder/brand story spot.
**Route away:** one person talking to camera from a script with no product continuity → `avatar`; editing existing footage → `auto-edit`; long narrated explainer → `text-to-video`; visuals for a song with no product → `music-video`. Disambiguator for "UGC ad": product must appear consistently across scenes → advertisement; single talking head → avatar.

**Never ask about:** the video model (locked to `gemini-omni-flash-preview` — the renderer forces it regardless of settings) or a voice (speech/ambience/SFX are generated natively inside each Omni clip — no TTS, no voice picker).

## Question sequence

### Q1 — What's in the ad? (drives which images to collect, and gates the delivery options later)
1. **A product presented by a person** (Recommended — richest results; needs both images) → mode `product+character`
2. Product only — no people (pure product motion spot) → `product-only`
3. A person / founder / brand story — no product shown → `character-only`

### Q2 — Format (BEFORE images — character generation inherits the project ratio)
1. **Vertical 9:16 — TikTok / Reels / Shorts** (Recommended; app default)
2. Horizontal 16:9 — YouTube / web
3. Square 1:1 — Instagram feed (**warn:** the Omni clip is generated 16:9 and centre-cropped to square; the storyboard itself is generated square)

Ask this before Q3 because the in-app character generator re-syncs to the project ratio every time it opens, so a format chosen afterwards produces a wrongly-framed portrait. On the headless path the ratio does not inherit at all — pass it explicitly on `generate_images`.

### Q3 — Reference images (mandatory: at least ONE of the two, max 1 per slot)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template A) when `show_widget` exists: one card per slot Q1 requires (Product · Character); Character also gets *Generate with AI*; the picker dialog uses `extensions: ["jpg","jpeg","png"]`. Re-render after each pick until every required slot is filled. Only if no `show_widget` tool can be found: use the options below.
Ask for the image(s) Q1 requires — one clear **product photo** and/or one **character portrait**, JPEG or PNG:
1. **Give a file path now** (Recommended)
2. Pick with the native file dialog (`select_local_image_for_import`)
3. Generate the character with AI (character slot only — Avatar Generator in the UI, or `generate_images` with a face `referenceImages` headlessly, then select the output). **Headlessly you must pass `aspectRatio` explicitly** — `generate_images` defaults to 16:9 and does NOT inherit the project ratio

`.webp` and other formats: `select_advertisement_image` only accepts `.png/.jpg/.jpeg`, so route them through `import_frontend_assets { assetType: "image" }` and patch via `set_advertisement_settings` — the renderer itself re-encodes every reference before upload, so this is a convenience path around the selector, not a format the pipeline rejects. **Hard guard:** if both slots would end empty, the render aborts — the wizard must not proceed. The Create Video button does NOT enforce this; we must.

### Q4 — Length (legal values: 10/20/30/40/50/60 s — one 10s scene per 10s)
1. **30 s — 3 scenes** (Recommended; app default)
2. 10 s — 1 scene (single hook; fastest & cheapest)
3. 20 s — 2 scenes
4. 60 s — 6 scenes (maximum)

Custom input: stick to multiples of 10. MCP accepts any integer 10–40 without a step check, but the renderer then computes `round(duration/10)` scenes with banker's rounding — 25 s quietly becomes 2 scenes, not 3. State the cost here; it is the main cost lever. Real estimate-bar totals: **10 s ≈ 136 · 20 s ≈ 263 · 30 s ≈ 391 · 40 s ≈ 518 credits** (~120 cr Omni + 6 cr storyboard per scene, plus the story-plan LLM call). Treat the per-scene image price as a floor: the estimator prices the 1536×1024 medium tier with the ratio hardcoded to 16:9, while the renderer actually requests 2048×1152 (2048×2048 on a square project).

⚠️ **Gemini Omni quota is a real ceiling on ad length.** Every scene is one Omni request and Google's Tier-1 allowance is only ~20 per day, so a 60-second ad burns 6 of them. Unlike text-to-video, the advertisement flow **never reroutes to another model** — reference-to-video has no equivalent elsewhere — so once the quota is gone the remaining scenes simply fail and are skipped, and a 60-second ad comes back as a 30-second one with no error. Mention this before recommending long ads, especially to someone rendering several in a day.

### Q5 — Tone + hook
"What's the angle, and the one-line offer/hook?"
1. **Energetic UGC / social-native** (Recommended)
2. Premium cinematic
3. Founder / brand story, conversational
4. Sound-design led (product sounds, minimal speech)

Follow up in the same step for the hook/CTA (free text or: launch discount / free trial / pure benefit / awareness-no-CTA). The app ships 10 ad prompt examples (`frontend/src/data/promptExamples.ts` `ad-*`) usable as templates.

### Q6 — Spoken delivery (options depend on Q1 — never offer a speaker that doesn't exist)
Word budget ≈ 2–2.5 words/s: 10s ≈ 20–25 w · 30s ≈ 60–75 w · 40s ≈ 80–100 w. Quote the budget for the length they actually picked in Q4.

**IF Q1 = product-only** (there is no character — do NOT offer "character speaks"):
1. **Off-screen narrator** (Recommended)
2. Mostly silent — product sound design + one closing line
3. Fully silent — sound design only, text does the talking
4. Exact narrator lines (they provide them; passed through in quotes verbatim)

**ELSE** (a character exists):
1. **Off-screen narrator, character reacts** (Recommended when Q4 ≥ 30 s / 3+ scenes — each scene is an independent generation, so a character voice is not guaranteed to stay consistent across them)
2. Character speaks to camera (best at 10–20 s / 1–2 scenes — recommend this instead when they picked a short length)
3. Mostly silent — sound design + one closing line
4. Exact scripted lines (they provide them; passed through in quotes verbatim)

Flip the recommendation between options 1 and 2 based on the Q4 scene count rather than always leading with the narrator.

### Q7 — Extras (multi-select, default none)
1. **None — generate as-is** (Recommended)
2. Burned-in subtitles (`set_subtitle_settings`; transcribed from the generated audio — **skip this option entirely if Q6 = fully silent**, there is nothing to transcribe)
3. Background music — import to MUSIC lane and mix it under the ad. Do not reach for a replace-audio operation: the speech lives inside the generated clips, so replacing the track would take the ad's voice with it
4. Border / overlay polish

## Summary + confirm

Per `README.md` contract. Include: mode (product+character / product-only / character-only), image file names, format (+1:1 crop warning if chosen), duration & scene count, tone/hook, delivery, extras, and the cost estimate. **Paid only — no free tier.** Check `get_shorz_credits` before offering "start now".

## Answer → execution map

| Step | MCP call |
|---|---|
| New project | `create_project { projectName, projectType: "advertisement" }` |
| Q2 | `switch_project_aspect_ratio { aspectRatio }` — before any character generation |
| Q3 product | `select_advertisement_image { imageFilePath, role: "product" }` |
| Q3 character | `select_advertisement_image { imageFilePath, role: "person" }` (`character` is an accepted alias) |
| Q3 webp | `import_frontend_assets { assetType: "image", overridePaths }` → `set_advertisement_settings { advertisementProductImage / advertisementPersonImage }` |
| Q4 | `set_advertisement_settings { advertisementDurationSeconds: <int 10–40> }` |
| Q5+Q6 | compose brief (audience · hook · tone · must-show beats · quoted lines · audio direction) → `set_user_instructions` — never include aspect/pixel/fps tokens |
| Q7 | `set_subtitle_settings` / MUSIC lane import + `set_audio_settings` (mix) / `set_border_settings` / `set_overlay_settings` |
| Render | `trigger_create_video` → poll `get_video_generation_status` |

Notes: main VIDEO lane is disabled (`assetType: "video"` import is rejected — supporting footage goes to `broll`). A scene whose storyboard or clip fails is skipped and the ad assembles from the survivors; only a total failure aborts. **Always check the delivered duration against what was requested** and tell the user when scenes dropped out — a short ad is the normal symptom of a failed scene or an exhausted Omni quota, not a rendering bug.
