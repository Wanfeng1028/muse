# Guided flow — THUMBNAIL CREATOR

Produces one or more **still images** into the global `Generated_Thumbnails` folder. Not a project type — no Create Video, no render. Follow `README.md` protocol; the confirmation step is "generate it now?", not "start a project?". Tool semantics: `references/panel-workflows/thumbnail-creator.md`.

**Route here when:** "a thumbnail", "YouTube thumbnail", "cover image", "Shorts cover", "thumbnail with my face in it", "give me a few thumbnail options", "big text on an image".
**Route away:** scene stills inside a video → `generate_scene_image` / B-roll; avatars → the Avatar Creator; generic images → `generate_images`.

**Prerequisites.** The UI opens without a project, but **every MCP tool here requires `projectPath`** — resolve one with `get_current_open_project`, else `list_projects`, before asking anything. Settings and the Recent strip are project-scoped; the PNG files are app-global, so switching projects empties the strip while the files remain on disk.

**Aspect ratio is NOT inherited from the project** — the draft defaults to `16:9` even inside a 9:16 project. Always ask.

## Question sequence

### Q1 — Where will this thumbnail live? (sets `aspectRatio`)
1. **YouTube — 16:9 landscape** (Recommended; app default)
2. Shorts / TikTok / Reels — 9:16 vertical

Only these two exist. **Branch:** picking 9:16 removes Q4 entirely (the YouTube-link field is inert and auto-cleared at 9:16) and leaves all three reference slots free.

### Q2 — What's in the picture? (mandatory)
Free text, 1–2 sentences; the UI caps it at **2,000 characters** and the MCP path does not. Ask for: subject + reaction/action + backdrop + mood. Offer to draft it from the video's topic if they're vague.

**Refuse to proceed on an empty description.** The UI blocks it, but MCP happily generates from the boilerplate alone and bills for the result.

### Q3 — Big text on the image? (sets `textOverlay`)
1. **No text** (Recommended — cleanest, and baked-in text is the least reliable part of image generation)
2. A short punch line, ≤4 words — e.g. `IT WORKED!`
3. A number or price hook — e.g. `$10,000?!`

No length limit anywhere. A font-preference sentence (Bebas Neue, Impact, Anton, Montserrat…) is appended to every prompt automatically — that is the panel's only "style preset"; there is no template picker, no colour control, no font dropdown. Don't invent one.

⚠️ **Always pass `textOverlay` explicitly on generate** — `thumbnail_creator_generate` defaults it to `""` and writes that into the draft, wiping any value set earlier.

### Q4 — Copy the look of an existing YouTube video? (16:9 only)
1. **No** (Recommended)
2. Yes — paste the video link

The link resolves to that video's poster frame and is prepended as the **first** reference. It consumes one of the three reference slots (leaving two uploads), and on GPT Image 2.5 it carries the reference surcharge (see Summary).

⚠️ **`youtubeReferenceUrl` does NOT inherit from the draft on generate** — unlike `referenceImages`, it is read from the call argument. Re-pass it on `thumbnail_creator_generate` or it is silently ignored for that run.

### Q5 — Any photos to work from? (sets `referenceImages`)
1. **None — generate from scratch** (Recommended)
2. One photo (a face, product, or screenshot)
3. Two or three photos

Accept only `.png .jpg .jpeg .webp .gif` and **verify each path exists first** — a missing path or an unmapped extension is forwarded to the provider as a literal string with no warning, producing a broken reference or a garbage image.

**Enforce the 3-image cap yourself.** The UI always caps at 3, but the MCP path only caps when a YouTube reference is present — without one it is uncapped and will ship all ten references you hand it.

**Branch:** any reference changes what the models do — Nano Banana switches to `nano-banana-pro-edit`, and GPT Image 2.5 routes to OpenAI's image-edit endpoint.

### Q6 — Model and quality (one bundled choice — they are coupled)
1. **GPT Image 2.5 · Medium — best value** (Recommended)
2. GPT Image 2.5 · High — sharpest text rendering
3. Nano Banana 2 · 1K — a different look; web-search-informed when no references are attached
4. Nano Banana 2 · 2K/4K — largest source pixels

Read live prices from `get_shorz_usage_and_pricing` rather than quoting fixed numbers. On the repo's most recent snapshot, **Nano at 1K costs about twice GPT at medium per image** — that is the single biggest cost lever in this panel, bigger than variation count at low counts.

Say once: the output is **hard-resized to 1280×720 (16:9) or 1080×1920 (9:16)** regardless of tier, so 4K buys detail density, not final pixels.

⚠️ **Always pass `imageGenerator` explicitly** — omitting it on generate flips the panel to `nano-banana` and roughly doubles the bill.

### Q7 — How many options? (sets `numVariations`, 1–6)
1. **3 variations** (Recommended — enough to choose from)
2. 1 variation — cheapest
3. 6 variations — maximum

Each variation is a **separate billable call**, run sequentially. Pass a whole number — the schema accepts fractions and `2.5` silently runs three times.

⚠️ **A failure partway through discards the earlier variations of that run — and they were already billed.** The UI at least says "stopped after 2/6"; the async MCP path says nothing. That makes 3 a safer bet than 6.

## Summary + confirm

State the bill as a number before generating:

> `perImage × variations` — **plus `2 × references × variations` when the model is GPT Image 2.5 and any reference (including the YouTube link) is attached.**

The panel's own GENERATE button omits that surcharge, so a GPT run with 3 references and 3 variations displays 18 credits and bills roughly 36. Nano is unaffected — it bills from provider-reported cost.

Then ask: 1. **Yes — generate now** (Recommended) · 2. Change something first · 3. No, not yet.

**Paid only — thumbnails are not covered by the free weekly runs.** Check `get_shorz_credits` first.

## Answer → execution map

| Step | MCP call |
|---|---|
| Resolve project | `get_current_open_project` → else `list_projects` (a `projectPath` is required by every tool here) |
| Q1–Q7 | ONE `set_thumbnail_creator_settings { projectPath, aspectRatio, description, textOverlay, referenceImages, youtubeReferenceUrl?, imageGenerator, gptImageQuality \| resolution, numVariations }` (`openModal: false` unless the user wants to watch) |
| Snapshot | `get_thumbnail_creator_generation_status` → record `thumbnailCount` **before** generating |
| Generate | `thumbnail_creator_generate` with **every** field passed explicitly (omitted fields overwrite the draft with defaults); leave `awaitCompletion` off |
| Poll | `get_thumbnail_creator_generation_status` every 3–5 s, hard ceiling ~15 min × variations |
| Result | `isGenerating: false` + `thumbnailCount` **increased** = success → `get_generated_thumbnails` for paths. Unchanged count = **failure** — there is no error field in the status response |
| Close | `close_thumbnail_creator` unless asked to leave it open |

**Stuck-spinner escape.** A known race can leave `isGenerating: true` forever while the PNGs are already written. If polling never terminates, call `set_thumbnail_creator_settings { projectPath, isGenerating: false }` (which also clears the run id) and read the files from `get_generated_thumbnails` by mtime. Never trust `isGenerating` as the only completion signal — always compare `thumbnailCount`.

Free tools here: `set_thumbnail_creator_settings`, `open_thumbnail_creator`, `close_thumbnail_creator`, `get_thumbnail_creator_generation_status`, `get_generated_thumbnails`, `download_generated_thumbnail`. **`thumbnail_creator_generate` is the only one that costs credits.** Thumbnail spend never appears in the project cost bar.
