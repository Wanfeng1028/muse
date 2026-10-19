# Guided flow — ANIMATION STUDIO

An LLM writes a **Remotion (React/TSX) composition**, the app compiles it to a live preview, and Remotion renders it to MP4. The wizard's job is to turn a vague "I want an animation" into a brief precise enough to compile on the first try — because **compiling and exporting are free, and only the chat turns cost credits.**

Follow `README.md` protocol; the confirmation step is "generate it now?", not "start a project?". Tool semantics: `references/panel-workflows/animation-studio.md`.

**Route here when:** animated intro/outro, logo reveal, title card, kinetic text, animated chart or counter, explainer motion, abstract/3D loop — where the animation **is** the deliverable.
**Route away — this matters:** if the graphics go **on top of existing footage** (chroma-keyed lower thirds, callouts over a talking head), load the **`shorz-motion-graphics`** companion skill instead. It owns source analysis, safe zones, the green-screen constraint block and the ffmpeg composite. Ask Q0 whenever it is ambiguous.

## What the user actually gets (say this up front)

| | |
|---|---|
| Format | **MP4 (h264)** |
| Transparency | **None.** h264 carries no alpha. A "transparent" animation is impossible — for compositing, ask the model to paint a **flat green background** and hand off to `shorz-motion-graphics` |
| Audio | **Supported via attachments:** attach audio/music (or an unmuted video) and the composition plays it with <Audio> / <OffthreadVideo>; the exported MP4 then carries an AAC track. A composition with no audio elements exports silent |
| Default size | 1920×1080, **30 fps**, **5 s** (150 frames) |
| Where it saves | A native Save-As dialog (UI) or your `outputPath` (MCP). **It does NOT appear in My Assets** — the help centre is wrong about this. To reuse it in a project, import the absolute path as `broll` (or an overlay) yourself |

## The single most important mechanic

**The modal UI has no output controls** — no aspect ratio, no duration, no fps field. In a pure-UI session those come from whatever the model writes into its own `REMOTION_META` line, nudged only by prose.

**So any wizard that promises a format or a length MUST execute through `animation_studio_send_compile_export`**, which takes `aspectRatio` / `width` / `height` / `durationInFrames` / `fps` explicitly. Do not run this flow through the UI path and then claim the user picked 9:16.

⚠️ On that tool, `visualizeInUi` defaults to **true**, and in that mode `messages`, `systemPrompt`, `requireCodeFence`, `fallbackToRawAssistantText` and `revealInFolder` are **silently ignored** — only `prompt` carries the brief.

## Question sequence

### Q0 — Routing gate (ask only when ambiguous)
"Is this going on top of an existing video, or is the animation the whole thing?"
1. **Standalone clip — the animation is the deliverable** (Recommended) → continue here
2. Over footage I already have → **hand off to `shorz-motion-graphics`** and stop

### Q1 — What kind of animation? (drives everything downstream)
1. **Title / logo reveal** (Recommended — smallest, most reliable, compiles first-try most often; ~3–5 s)
2. Explainer beat — steps, arrows, icons building up
3. Data — counters ticking, bars or charts growing
4. Abstract / 3D — shapes, materials, camera moves

**Branch:** option 4 unlocks Three.js in the brief (the studio allows `three`, `@remotion/three`, `@react-three/fiber`). Options 1–3 stay 2D — the system prompt explicitly says not to reach for Three.js on 2D work, and doing so is a common source of compile failures.

**If the user has no idea what they want, suggest — don't interrogate.** Offer three concrete, ready-to-run ideas fitted to what you already know about them (their brand, the video they just made, the platform). Good openers:
- *"Your channel name flying in with a soft spring, then a thin underline sweeping left-to-right"* — the safest possible first animation
- *"Three numbered steps sliding in one after another, each with an icon"* — an explainer beat
- *"A counter running 0 → 10,000 with the digits rolling, then a label fading under it"* — data
- *"Your logo assembling from scattered shapes, then settling with a gentle overshoot"* — a reveal with personality

Always give the user a concrete draft to react to rather than a blank prompt. That is the difference between one paid turn and four.

### Q2 — Style
1. **Clean explainer — light background, one sans-serif, small palette** (Recommended; this is the system prompt's built-in default look, so it needs the least steering)
2. Bold / high-energy — heavy condensed caps, punchy hits, fast timing
3. Corporate / minimal — lots of whitespace, restrained motion, one accent colour
4. Retro / tech — mono type, scanlines, terminal feel

Collect brand specifics in the same step if they have them: exact hex colours, the font name, and the literal text to display. **Naming the real text and the real colours up front is the highest-leverage thing the user can do** — vague briefs are what cause re-rolls, and re-rolls are what cost money.

### Q3 — Bring anything in?
1. **Nothing — draw it all in code** (Recommended; fastest, no image spend, nothing to go missing)
2. My own images — logo, product shot, screenshot
3. My own video clips and/or audio/music — embedded and **played inside the animation**
4. Let the AI generate supporting icons/illustrations

**Fonts and data files cannot be imported** — a font must be one the system already has, and data must be typed into the brief as literal numbers.

- Option 2 (images) limits: **max 8 images, 6 MB each**, `image/*` in the UI. Over MCP pass absolute paths (or `http(s)`/`data:`) as `imageReferences` — the MCP path does **not** check size. The code receives them as `REMOTION_IMAGE_URLS[0]`, `[1]`, … If the list ends up empty but the code still references it, the app injects an empty `REMOTION_IMAGE_URLS` (same for `REMOTION_VIDEO_URLS` / `REMOTION_AUDIO_URLS`), so an optional reference renders nothing instead of failing the export.
- Option 3 (video/audio) limits: **max 8 videos (≤500 MB each) + 4 audio tracks (≤100 MB each)**. Supported formats are deliberately narrow — **video: MP4, MOV, WebM · audio: MP3, WAV, M4A, AAC, OGG** (images: PNG, JPG, WebP, GIF). AVI and MKV are rejected on purpose: ffmpeg could read them but Chromium cannot, so the preview would break while a headless export appeared to work. They attach by **path/URL, never base64** — the preview streams them from the loopback media server and the export rewrites the URLs for the headless renderer. Over MCP pass absolute paths as `videoReferences` / `audioReferences` on `animation_studio_send_compile_export`; nonexistent paths are dropped and reported in `droppedMediaReferences`. In code they arrive as `REMOTION_VIDEO_URLS` (played with `<OffthreadVideo>`, trimmed with `startFrom`/`endAt` in frames) and `REMOTION_AUDIO_URLS` (played with `<Audio>` — fades via the volume prop, delayed starts via `<Sequence from>`). The model is told each file's real duration and must not assume more.
- Option 4 costs money and **happens whether or not you ask for it**: before every send, a preflight LLM call decides whether to generate **1–6 GPT Image 2.5 images** (**1 credit each** — the generator hardcodes `quality: low` at 1024×1024). The step is skipped outright only when the chat's **8-image budget is already full**, and that budget counts every image *already in the conversation* (earlier attachments and earlier generated ones), not just what you attach on this turn — so 8 attachments skip it on a first send, but far fewer will later on. Below that ceiling the preflight runs on every send: attaching your own assets makes it likelier to answer "nothing further needed", but it still generates when the brief implies a distinct asset it does not have. If the user wants nothing generated, word the brief so nothing is needed ("use only text and vector shapes drawn in code").
- **Silent failure to warn about:** if that image generation fails, it is logged to the console and nothing else — the animation is built *without* the picture it planned around, with no toast and no error. A **missing media file** at preview/export time errors visibly instead (broken element in preview, failed fetch in export) — verify paths exist before attaching.

### Q4 — Output format (MCP-only — see the mechanic above)
1. **16:9 — 1920×1080** (Recommended; the tool default)
2. 9:16 — 1080×1920 (TikTok / Reels / Shorts)
3. 1:1 — 1080×1080
4. Custom width × height (128–4096, rounded up to even)

Then **length**: default **5 s**. Set `durationInFrames = round(seconds × fps)` at 30 fps unless they ask otherwise.

⚠️ **The real ceiling is not the 3,600-frame clamp — it is how much code the model can emit in one reply.** Measured behaviour: ~31 s with 6 restrained beats compiles; ~17 s with 5 dense beats compiles; **~31 s with 10 dense beats fails outright**. Keep a single run to roughly **≤6 distinct beats or ~20 s of dense motion**, and split anything longer into separate animations that you concatenate afterwards.

### Q5 — Which model writes the animation?
Call `animation_studio_list_models` and show the live lineup with its price suffixes — never hardcode prices. It returns the same `main_ai` catalog as the PromptBar. (Note it strips the `isDefault` flag, so it cannot tell you which is default; the default is **`anthropic/claude-opus-5-5`**.)

1. **Opus 5.5 — the default, strongest coder** (Recommended for anything with several moving parts, 3D, or precise brand styling)
2. A cheap fast tier (e.g. Gemini Flash) — genuinely much cheaper per turn; good for a single line of kinetic text or a plain logo fade
3. A mid tier (e.g. Sonnet 5.5 / GPT 6.1 Sol) — between the two
4. Show me the live list with prices

**How to advise honestly — the economics are counter-intuitive:**

> Compiling and exporting are **free**. Only the chat turns cost. So the cheapest animation is the one that compiles on the *first* try — not the one from the cheapest model. A weak model that needs three attempts costs more than a strong model that needs one, and **each automatic fix is another full paid turn** (the studio retries a given error exactly once, then stops).

Ballpark on the default model: one turn is roughly **25 credits** (every turn re-sends a ~6,000-token system prompt before your brief is even read), so a clean animation lands around **25–70 credits** including one fix and any generated images. A cheap tier runs roughly **3× less per turn** — worth it for simple work, a false economy for complex work. (These figures dropped ~20% when Opus 5.5 replaced Opus 5 as the default — output went from 4 to 3 credits per 1k tokens. Image generation did not change, so a fix-heavy animation with images moves less than a chat-only one.)

Two grounded caveats to state once:
- **Shorz itself publishes no capability ranking.** The only in-app hint is that the Gemini tier is "cheapest per message". The coding-strength ordering here is an inference from published benchmarks, not something the app asserts.
- Anthropic's own positioning is that **Opus 5.5 leads on agentic coding** — which is what this panel actually does — and that **Fable 5.1 is the one to reach for on demanding reasoning**, or when Opus 5.5 at a higher effort still falls short. So do not tell a user Opus 5.5 is the most capable model in the lineup; it is the right default for animation work, and Fable 5.1 (in the same picker, ~2× the price) is the escalation if a complex brief keeps failing. Sonnet 5.5 is the fast, cheaper Claude, and the Gemini Flash tier is competitive on agentic/terminal coding while being several times cheaper and faster. Separately, framework write-ups note that **React/JSX animation code is harder for models to get right than plain HTML/CSS** — reconciliation, props and the component model consume attention that would otherwise go to the visuals. That is exactly why the model choice matters more here than in a normal chat, and why complexity should drive it.

**Recommendation rule:** pick by Q1, not by price. Options 1–2 of Q1 (logo/title, simple explainer) → a cheap tier is fine. Options 3–4 (data, 3D) or any brand-exact styling → stay on the default.

## Summary + confirm

Show: the animation described in one sentence, style, imports (and whether AI images will be generated), format + length, model + its live price, and the honest cost line — *"roughly 30–80 credits on the default model; compiling and exporting are free, so iterating on wording is what costs money, not re-exporting."*

Also restate the hard facts: **MP4, no transparency**; **audio plays only when the composition includes attached audio or an unmuted video** (otherwise the export is silent); and **it will not appear in My Assets** — hand back the absolute path.

Then: 1. **Yes — generate it now** (Recommended) · 2. Change something first · 3. No, not yet.

**Paid only.** The UI opens a purchase modal at zero balance; the MCP path has no gate and simply 402s.

## Answer → execution map

| Step | MCP call |
|---|---|
| Model list | `animation_studio_list_models` (no args; live catalog — `source: "bundled-fallback"` means it served the bundled snapshot instead. In that same offline state the in-app dropdown collapses to Opus-5-only, silently losing model choice) |
| Generate + compile + export | `animation_studio_send_compile_export { prompt, outputPath, aspectRatio or width/height, durationInFrames, fps, model, imageReferences?, videoReferences?, audioReferences? }` — `outputPath` is the only required arg |
| Preview only, no file | `animation_studio_send_and_compile` (compiles, does not render) |
| Raw chat, no compile | `animation_studio_send_message` (needs `messages`; injects no Shorz system prompt unless you supply one — rarely what you want) |
| Re-render an existing animation | `remotion_render` / `compile_remotion_preview` — **free**, no chat turn |
| Reuse in a project | `import_frontend_assets { assetType: "broll", overridePaths: [outputPath] }` or `import_overlay_effects` — check `skippedCount` (one asset per file name per lane) |
| Export history | `get_animation_studio_exports` (capped at 50, newest first, deduped by path); `remove_animation_studio_export { id }` deletes the entry and thumbnail but **leaves the MP4 on disk** |

**Async contract:** all three `animation_studio_send_*` tools are **async by default** — they return `{ started, jobId }` immediately; poll `get_job_status { jobId }` every ~10–20 s until `lastStatus` is `completed` (the `result` carries the payload and `outputPaths`) or `error`. **If a call or poll times out, the job is still running — NEVER re-call the tool; a retry is another full paid turn.**

**Failure modes to report honestly:**
- A compile error shows as a banner, disables export, and triggers **one** automatic fix for that specific error. A second occurrence of the same error is not retried — report it and offer to simplify the brief.
- Chat retries are capped (3 attempts, 5-minute wall clock) and only for transient/5xx errors; other failures fail fast on purpose.
- The composition must export `MyComposition` or the render refuses.
- Only the **last two messages** are sent to the model, so it forgets anything older than one exchange — restate context when iterating rather than assuming it remembers.
- If the export previews letterboxed in the "Recent exports" strip, that strip is hardcoded to 16:9 — the MP4 on disk is correct. Cosmetic only.
