# Animation Studio workflow (`animation_studio_*`, compile / export)

Generate, compile, or export Remotion-style animations via MCP. **Project targeting** and global panel rules: **`README.md`**. Shorz + bridge setup: **`mcp-server/README.md`**.

**Async by default:** `animation_studio_send_message`, `animation_studio_send_and_compile`, `animation_studio_send_compile_export`, and `remotion_render` return `{ started, jobId }` immediately (LLM code generation + render/UI export can run for minutes). Poll `get_job_status { jobId }` until `lastStatus` is `completed` (`result` carries the payload documented below; `outputPaths` lists the rendered MP4 when there is one) or `error`. Pass `awaitCompletion: true` for the old blocking single response only when your tool-call timeout comfortably exceeds the run (up to **~15 minutes** for UI exports). Do not re-call a send tool because a poll is slow — the job (and its AIML spend) is still running. `compile_remotion_preview` stays synchronous (fast transpile only).

## Tool contract

| Tool | Role |
|------|------|
| **`get_current_open_project`** / **`list_projects`** | Resolve **`outputPath`** directory (absolute paths). See **`README.md`** targeting rules. |
| **`animation_studio_open_modal`** | Opens the Animation Studio modal (optional if the next **`animation_studio_send_compile_export`** uses default **`openModal: true`**). **Required** before a UI export if the modal is closed and you rely on the UI workflow (otherwise the app may queue the payload until the modal opens). |
| **`animation_studio_close_modal`** | Closes the modal. Use when a task ends without **`closeModal: true`** on export, or after **`animation_studio_send_message`** / **`animation_studio_send_and_compile`**. |
| **`animation_studio_list_models`** | Returns supported **`model`** ids. **Not a static list** — it fetches the **live server catalog** (same `main_ai` category as the PromptBar picker) and only falls back to a bundled snapshot when the catalog is unreachable; the response's **`source`** field says which (**`live-catalog`** or **`bundled-fallback`**). Call it whenever the user asks for a non-default model or you need the exact **`id`** string, and prefer its ids over any list written down here. |
| **`animation_studio_send_message`** | **Headless AIML chat only** — does **not** open Animation Studio, does **not** apply the in-app Remotion system prompt. **`messages`** is **required** (MCP schema). Optional **`systemPrompt`** is merged **before** `messages`. Use for brainstorming copy outside the panel, or supply your own full **`systemPrompt`** if you truly need raw chat completions. **Not** the normal way to drive the Animation Studio UI. |
| **`animation_studio_send_and_compile`** | **Headless:** AIML → extract code → **`compile-remotion-preview`**. **`prompt`** and/or **`messages`** (at least one must yield a user turn after merge). No MP4; response includes **`compileResult`**. When **`systemPrompt`** is omitted, the server injects a default Remotion system prompt + **fixed** timing note (**150 / 30**); custom **`systemPrompt`** replaces that block (no auto timing append). |
| **`animation_studio_send_compile_export`** | End-to-end: AIML → compile → MP4 at **`outputPath`**. Behavior splits on **`visualizeInUi`** (see **UI-driven vs headless**). Defaults: **`visualizeInUi`** **true**, **`openModal`** **true**, **`closeModal`** **true**, **`durationInFrames`** **150**, **`fps`** **30**, **`requireCodeFence`** **false**, **`fallbackToRawAssistantText`** **true**. |
| **`compile_remotion_preview`** | Bridge-only: transpile TSX already in hand. Argument **`source`** (string). No AIML call. |
| **`get_animation_studio_exports`** | Optional: list saved export rows from **persisted** Animation Studio history (disk-backed JSON via the app bridge — same ordering the modal’s Recent exports uses). Use to verify history after runs. |
| **`remotion_render`** | Low-level bridge: render given **`code`** to MP4 (advanced; **`animation_studio_send_compile_export`** already wraps this when headless). |

---

## UI-driven vs headless (`animation_studio_send_compile_export`)

This is the main source of agent mistakes — **`visualizeInUi`** changes which fields actually take effect.

### **`visualizeInUi: true`** (default) — in-app modal workflow

- **Drives:** `run-animation-studio-mcp-workflow` in the desktop app: chat + preview compile + export run **inside** Animation Studio using **`REMOTION_STUDIO_SYSTEM_PROMPT`** plus an injected **composition timing** system line derived from **`durationInFrames`** / **`fps`**.
- **Uses from MCP:** **`prompt`** (string), **`model`**, **`outputPath`**, **`durationInFrames`**, **`fps`**, **`aspectRatio`** / **`width`** / **`height`**, **`imageReferences`** (max **8**; local absolute paths, `http(s)`, `data:`, `local-resource://` after normalization), **`videoReferences`** / **`audioReferences`** (max **8** videos and **4** audio; **video MP4/MOV/WebM, audio MP3/WAV/M4A/AAC/OGG** — other extensions are dropped as `unsupported-format`; absolute local paths or `http(s)`/`local-resource://` — attached by URL, never base64, and injected into the composition as `REMOTION_VIDEO_URLS` / `REMOTION_AUDIO_URLS` for `<OffthreadVideo>` / `<Audio>`; nonexistent local paths are dropped and reported in `droppedMediaReferences`; the exported MP4 carries an AAC track only when the composition actually plays audio), **`openModal`**, **`closeModal`**.
- **Ignored by this path (do not rely on them):** **`messages`**, **`systemPrompt`**, **`requireCodeFence`**, **`fallbackToRawAssistantText`**, **`revealInFolder`** — they are **not** forwarded to the UI workflow.
- **Waits:** MCP polls two signals every **`ANIMATION_STUDIO_UI_EXPORT_POLL_INTERVAL_MS`** = **5 seconds**, up to **`ANIMATION_STUDIO_UI_EXPORT_TIMEOUT_MS`** = **15 minutes** (`mcp-server/index.js`):
  1. **`get-animation-studio-mcp-workflow-result`** — the **authoritative** signal. The renderer reports a terminal outcome for the run (matched by **`runId`**) whether it succeeded or failed, so a failure returns **immediately** with the real message instead of burning the full timeout.
  2. **`file-exists`** on **`outputPath`** — fallback, and the only signal on app builds predating the outcome channel (the handler is simply absent there, and MCP degrades to the old behaviour).
- **Returns:** JSON with **`success`**, **`uiDriven: true`**, **`renderResult.outputPath`** on success. On failure: **`success: false`** plus **`stage`** (**`input`** | **`chat`** | **`compile`** | **`export`** | **`unexpected`**) and **`error`** carrying the actual cause.
- **Transient chat failures self-heal:** the modal retries a failing chat turn up to **3 attempts** (2s then 5s backoff) when the error looks transient — `upstream error`, 5xx, 408/425/429, rate limits, dropped sockets. Deterministic errors (4xx, payload-too-large, refusals) fail fast and are **not** retried. Retries are additionally capped by a **5-minute wall clock**: a single attempt on a big composition can run for minutes, and without the cap three slow retries would consume the caller's whole wait window so the failure never got reported. An `upstream error` after ~300 s (older builds), or a message naming the 30-minute limit, means the reply took **too long to generate**. A retry would fail the same way, so none is attempted. Shrink the brief instead (see *Generation time*).

### **`visualizeInUi: false`** — headless (no UI player export)

- **AIML** in the MCP server with **`messages`** + optional **`prompt`** (appended as a user message), optional **`systemPrompt`** (else default Remotion MCP system + **timing note** from this call’s **`durationInFrames`** / **`fps`**), **`imageReferences`** merged into the **last user** message as vision parts.
- **`requireCodeFence`** / **`fallbackToRawAssistantText`** apply here.
- **`revealInFolder`** is passed to **`remotion-render`** (reveal in Explorer after render when supported).
- **Render timing:** headless **`remotion-render`** receives **`durationInFrames`** and **`fps`** from **this tool’s arguments** only — not from the user’s prose. **Do not** put `REMOTION_META`, frame counts, fps, or “first line must be…” timing instructions in the **`prompt`** / **`messages`** user content; the MCP server already injects a timing system line from **`durationInFrames`** / **`fps`**. User-facing copy should stay creative (look, story, on-screen words); the model still emits `REMOTION_META` inside the fenced TSX where required, aligned with those tool args.
- **`closeModal: true`** in **`finally`** only for this branch (closes a stray modal if one was open).
- **Returns:** JSON with **`compileResult`**, **`renderResult`**, **`success`**, no **`uiDriven`** poll loop for the file (result is in the tool response body).

---

## User `prompt` shape (creative brief)

Describe **ideas only**: mood, story, palette, pacing in plain language, on-screen words, how to use attached images. **Do not** put Remotion plumbing in the user **`prompt`** / user **`messages`**: no `REMOTION_META`, no “durationInFrames=… fps=…”, no “first line in the fence must be…”, no “export MyComposition”, no markdown fence instructions — **timing and code-shape rules come from the app / MCP system** (`durationInFrames` / **`fps`** on the tool, plus injected system prompts). The model writes `REMOTION_META` inside the fenced TSX reply as needed; that belongs in **assistant output**, not in what you ask the user to type.

- **`animation_studio_send_compile_export`** (**`visualizeInUi: true`**): supply a **non-empty** **`prompt`** string (default MCP `prompt` is `""` — an empty string still triggers the UI workflow but yields a useless user turn). Do not use **`messages`** for this path.
- **`animation_studio_send_compile_export`** (**`visualizeInUi: false`**) or **`animation_studio_send_and_compile`**: use **`messages`** for multi-turn and/or **`prompt`** for a single appended user line (server requires at least one valid user content path).
- **`animation_studio_send_message`**: **`messages`** required; there is **no** top-level **`prompt`** field on this tool.

**`systemPrompt`:** Optional override of the **headless** Remotion system text on **`send_compile_export`** / **`send_and_compile`**. On **`send_and_compile`**, if you pass **`systemPrompt`**, you **replace** the server’s default system + timing block — only do this when you intentionally carry the full rules yourself. The **UI** path ignores **`systemPrompt`** from MCP.

---

## Briefing for launch-film quality (and the SFX cue sheet)

The in-app system prompt carries a **MOTION CRAFT STANDARD** (`frontend/src/prompts/remotionMotionCraft.prompt.txt`):
universal motion-design rules distilled from frame-by-frame and optical-flow study of top launch films —
one continuous shot, a transforming hero object, a camera that never parks (measured zoom/pan magnitudes
and easings), the result shown large, one dominant motion at a time, readable holds, bold high-contrast
type that keeps its word spaces, faithful use of attached UI/logos/footage, and an SFX cue sheet.
For quality-critical pieces (promos, launch films, hero videos) follow the **`shorz-premium-motion`**
skill: plan the story and hero object, brief one clip at a time, verify each clip frame by frame,
then score and assemble. You do not need to repeat those rules — brief the *content*:

- Name each beat, the on-screen words, and what transforms into what. "The prompt bar collapses into a
  dot that becomes the first clip on a timeline" gets better motion than "then show a timeline".
- Attach real UI screenshots as `imageReferences` whenever a product surface appears — the prompt tells the
  model to reproduce attached UI faithfully rather than invent one. Attach real logos the same way.
- Keep each run to ~5 s / 3–4 beats (see size limits below); state the start state of every segment after
  the first so the seams continue.
- Pass **`newSession: true`** on every self-contained brief and every segment of a multi-segment film.
  Without it each run continues the open chat: the model copies its earlier code (bugs included), the
  request grows toward the size ceiling, and earlier attachments take image slots from this run's
  references (8 max, oldest first).

## Sound effects and background music on request

Ask for sound in the prompt and the export comes back with it: **"with sound effects"**, **"add a
whoosh when it lands"**, **"with upbeat background music"**, in any language. The model marks the
request in the composition (`// SFX_AUTO on`, `// MUSIC_AUTO on | <track brief>`). As soon as the reply
compiles, the app generates each distinct cue sound (ElevenLabs sound generation) and, when music was
asked for, one instrumental track at the composition's length (ElevenLabs Music, 10 s minimum). The
**Live preview plays them**, and the export mixes the same files into the MP4 (music ducked under the
effects and faded out). Every file is cached on disk by what it is (description + length, or brief +
length), so follow-up edits, a reopened chat and the export only pay for sounds not generated before.
Everything is billed to Shorz credits: about 16 per new sound effect, and music scales with length.

- **Default is silent.** Without a request in the prompt nothing is generated and nothing is spent.
- The result's **`soundtrack`** field reports what landed: `{ ok, soundEffects, music, warnings }`.
  When it is present, **do not score that MP4 again**. A single failed sound is skipped with a warning.
  `ok: false` means the MP4 was kept silent and `error` says why.
- At most 12 distinct sounds are generated per export. Repeats of the same sound are generated once and
  placed at every cue.
- **Older builds** (before 2026-09-28) ignore the request. There, score `sfxCues` by hand: one
  `generate_sound_effect` per distinct cue, then ffmpeg `adelay` at each `t`.

Every successful in-app export also returns `sfxCues: [{ t, sound }]` (seconds from the segment start)
and writes them beside the MP4 as `<outputPath>.sfx.json`, whether or not sound was generated.

## Generation time

The model's reply is written before anything shows, and thinking dominates the time (a 9 KB map
composition took **277 s** on Opus 5.5; complex briefs take far longer). Since 2026-09-28 the reply
runs as a **proxy chat job**: the app starts it and polls every 4 s, so it can run for up to
**30 minutes** on every selectable model (Claude, GPT 6, Gemini). MCP waits up to 45 minutes for
the whole export.

Before that, the call was a single request, and **Railway's edge closes a request after 5 minutes
with no bytes transferred**. Every generation past 5 minutes died with a bare **`upstream error`**
(Railway logged HTTP 499 at exactly 300000 ms), and **installed builds older than the fix still do**.
For those builds, and to keep runs fast and cheap anyway:

- End the brief with a budget line, e.g. *"Keep it compact: repeated elements from data arrays with
  map(), no long comments."* Current builds inject a budget note into every turn themselves.
- **Keep precomputable static detail out of the animation run.** Render a detailed map, coastline or
  data table once as a static plate (`durationInFrames: 30`), take a PNG with `extract_video_frames`,
  and attach it as an `imageReferences` background for the animated run.

## Waiting for the result: poll `get_job_status`, never only the output file

A failed run **never creates `outputPath`**, so a watcher that only waits for the MP4 sits silent for its
whole timeout while the job already reported `error` minutes earlier. After every `animation_studio_send_*`
call, poll **`get_job_status`** every ~30 s. It is the channel that reports failure (`lastStatus: "error"`,
`result.stage`, `result.error`). The MP4 also appears **before** its soundtrack is mixed in, so wait for
`completed` before using the file.

## Composition size limits (generation and export)

Two separate ceilings, both measured. Neither is the `durationInFrames` clamp (**3600**).

**1. Generation time.** Up to 30 minutes per reply as a chat job (see *Generation time*); a reply that exceeds it fails with **`stage: "chat"`** and a message naming the limit. Duration alone does not predict the time; *beat count × element density* does.

| Duration | Distinct beats | Density | Result |
|---|---|---|---|
| 31.4s | 6 | restrained | ✅ |
| 10.0s / 14.0s / 17.5s | 5 each | dense | ✅ |
| 31.4s | **10** | dense | ❌ twice |

Rule of thumb per run: **≤ ~6 distinct beats, or ~20s of dense motion**. Sparse compositions run much longer in one go. Beyond that, **split into segments** at beat boundaries, generate sequentially (**`closeModal: false`** on all but the last), and join the outputs afterwards — full recipe, including seam continuity, in the **`shorz-motion-graphics`** skill.

**2. Export wait — 15 minutes.** MCP waits **`ANIMATION_STUDIO_UI_EXPORT_TIMEOUT_MS`** = 15 min, ending early on either terminal signal. This was **8 minutes** and dense ~17s 1080×1920 compositions measured **467s and 481s**, so a render that actually succeeded could be reported as a timeout depending on which side of 480s it landed. Real renders now sit comfortably inside the window. A timeout still means "no outcome was ever reported" (modal closed or crashed, or a genuinely enormous composition) — **check `outputPath` with `get_media_info` before re-running**, since a needless re-run spends credits again.

---

## Composition canvas (aspect ratio)

Animation Studio renders at the size carried by the composition — **not** a fixed 1920x1080.

| Arg | Meaning |
|---|---|
| **`aspectRatio`** | **`16:9`** → 1920x1080 (**default**), **`9:16`** → 1080x1920, **`1:1`** → 1080x1080 |
| **`width`** / **`height`** | Explicit override for non-standard sources. Clamped to **128–4096** and rounded **up to even** (h264 rejects odd edges). |

- Available on **`animation_studio_send_compile_export`** (both UI and headless paths) and **`remotion_render`**.
- The tool injects the canvas into a **“Composition timing and canvas”** system line, and the model echoes it as `// REMOTION_META durationInFrames=N fps=M width=W height=H`. The export renders at exactly that `width`/`height`, and the in-app Player previews at the same aspect.
- Omitting `width`/`height` in a reply is backward compatible — the app's current size is used, not a hardcoded 16:9.
- **Match the canvas to whatever the output has to sit alongside.** For overlay work this must equal the source video's pixel dimensions; see the **`shorz-motion-graphics`** skill.

---

## Model selection

Animation Studio chat models are **separate** from the PromptBar **`AI_MODEL.main_ai_model_name`** dropdown used by Create Video (see **`../../SKILL.md`** → *PromptBar main AI model*).

The lineup is **server-driven** (proxy catalog `main_ai` category — same list as the PromptBar picker); the table below is the current snapshot:

| Label (`animation_studio_list_models`) | AIML `model` id |
|---|---|
| `Opus 5.5` | `anthropic/claude-opus-5-5` (the default; replaced Opus 5 on 2026-09-22 by migration `0051` — 1 / 3 credits per 1k, down from 1 / 4) |
| `Fable 5.1` | `anthropic/claude-fable-5-1` |
| `Sonnet 5.5` | `anthropic/claude-sonnet-5-5` (replaced Sonnet 5 on 2026-09-28 by migration `0054`; ~0.3 / 1.3 credits per 1k tokens) |
| `GPT 6.1 Sol` | `openai/gpt-6-1-sol` (replaced GPT 6 Sol on 2026-09-30 by migration `0055` at the same price; `openai/gpt-6-sol` and the GPT 5.6 ids still resolve to it; 1 / 2 credits per 1k) |
| `GPT 6 Luna` | `openai/gpt-6-luna` (added 2026-09-23 by migration `0052`; ~0.01 / 0.07 credits per 1k) |
| `GPT 6 Astra` | `openai/gpt-6-astra` (added 2026-09-05 by migration `0042`; 2 / 7 credits per 1k, the priciest row) |
| `Gemini 3.8 Flash` | `google/gemini-3.8-flash` (cheapest main-AI tier, ~0.2 / 1 credits per 1k tokens) |

- **`animation_studio_list_models`** — optional; returns the live catalog lineup (bundled snapshot when the catalog is unreachable — the snapshot matches the seven models above, but only the live catalog reflects server-side additions).
- **Default model** when **`model`** is omitted: **`anthropic/claude-opus-5-5`**. Override only when asked.
- **Retired (do not pass):** `anthropic/claude-opus-4-6`, `anthropic/claude-opus-4-7`, `anthropic/claude-opus-4-8`, `anthropic/claude-opus-5`, `anthropic/claude-fable-5` — no longer in the UI selector. (`anthropic/claude-sonnet-5-5` replaced Sonnet 5 on 2026-09-28 via `0054`; the old `anthropic/claude-sonnet-5` id still resolves to 5.5 through a disabled legacy-alias row.) The proxy still resolves `claude-opus-4-8`, `claude-opus-5` and `claude-fable-5` through disabled legacy-alias catalog rows so older saved projects keep working — `claude-fable-5` transparently serves **Fable 5.1** at the identical rate since migration `0041`, and `claude-opus-4-8`/`claude-opus-5` serve **Opus 5.5** at the new, cheaper rate since `0051` — but none is a valid choice for new work: pass **`anthropic/claude-opus-5-5`** / **`anthropic/claude-fable-5-1`**.
- **Order:** resolve project → open modal if needed → optional **`animation_studio_list_models`** → **`animation_studio_send_*`**.

---

## Closing the modal (default: close when done)

- **`animation_studio_send_compile_export`** defaults **`closeModal: true`** — the app closes Animation Studio **after a successful UI export** when **`visualizeInUi: true`**. On export **failure**, call **`animation_studio_close_modal`** unless the user wants the modal left open to retry.
- **Chained UI exports** (same session, same images, different briefs): use **`closeModal: false`** on intermediate runs, **`closeModal: true`** on the last — or **`animation_studio_close_modal`** after the final failure/skip.
- **Same-chat sequential exports (production):** the desktop app waits for the **next** preview compile to bump **`previewKey`** after each `sendChat` before running **Export MP4** in the MCP-driven workflow. Chained **`animation_studio_send_compile_export`** calls therefore serialize on **chat + compile + export** per call; do not assume the second call returns as soon as AIML finishes streaming if Remotion preview compile is still running. Very long compositions can still hit the **15-minute** export wait above.
- **`animation_studio_send_message`** / **`animation_studio_send_and_compile`** do not auto-close anything — call **`animation_studio_close_modal`** when the task is done (unless the user asked to keep tools open).

---

## Instruction handling rules

- **Brainstorm / no Remotion panel** — **`animation_studio_send_message`** (own **`systemPrompt`** if you need structure).
- **Compile-only check** — **`animation_studio_send_and_compile`** or **`compile_remotion_preview`** with existing TSX.
- **Final MP4** — **`animation_studio_send_compile_export`** + writable absolute **`outputPath`**.
- **Iterate inside the UI** — repeated **`animation_studio_send_compile_export`** with **`visualizeInUi: true`**; each call appends chat in the modal (still only **`prompt`** is sent from MCP per call).
- **Configure but not run** — **`animation_studio_open_modal`** only; no send/compile/export.
- **Keep modal open** — user explicitly asked: last export with **`closeModal: false`** and skip **`animation_studio_close_modal`** until they are done.

---

## Execution sequence

1. **Project:** **`get_current_open_project`** (or **`list_projects`** per **`README.md`**). Pick a writable **`outputPath`** (often under the project folder).
2. **Modal (UI path):** If **`visualizeInUi: true`** and you set **`openModal: false`** on export, call **`animation_studio_open_modal`** first so the modal mounts and **`run-animation-studio-mcp-workflow`** is subscribed before the export call. With default **`openModal: true`**, the export tool opens the modal for you (separate open is optional / redundant).
3. **Models:** Optional **`animation_studio_list_models`** if not using the default.
4. **Mode:** choose **`animation_studio_send_message`** vs **`send_and_compile`** vs **`send_compile_export`** per **Instruction handling** and the **UI vs headless** section.
5. **Report:** **`success`**, **`model`**, **`assistant`** / code summary, **`compileResult`**, **`renderResult`** / **`renderResult.outputPath`**, **`uiDriven`** when applicable; surface errors verbatim.
6. **Close:** follow **Closing the modal** above.

---

## Common failures & recovery

- **Not signed in / out of credits** — Animation Studio chat runs on **Shorz account credits** via the proxy (no user AIML key). Confirm with **`get_shorz_credits`**; if `signedIn:false`, sign in via **`shorz_sign_in_send_code`** → **`shorz_sign_in_verify_code`**, then retry. **The free tier does not cover this modal:** a free `auto-edit` / `clipping` run zero-rates only that render's own main-AI chat, so every `animation_studio_send_*` call from a zero-balance user 402s (in the app the Send button opens the purchase modal). Compiling or exporting an **already-built** animation (`compile_remotion_preview`, `remotion_render`) is local Remotion work and stays free.
- **UI workflow unavailable** (`success: false`, trigger skipped/failed) — restart Shorz; ensure modal can open before MCP export.
- **`success: false` with a `stage`** — the run failed and the renderer said why. Read **`stage`** first: **`chat`** = the model call failed. If it failed at **~300 s** with **`upstream error`** (a build older than 2026-09-28), or with a message naming the 30-minute limit, the reply took too long to generate. Re-sending the same brief fails the same way and spends credits again, so cut it down: move static detail into a pre-rendered plate, reduce the beats, or segment it (see *Generation time*). `chat job not found` means the proxy restarted mid-job (a deploy) twice in a row: the app already restarts a job lost to one deploy automatically, so re-send. A quick `upstream error` (seconds, not minutes) is a real provider or proxy outage: wait, then retry; **`compile`** = no usable Remotion code or the preview threw (simplify the prompt); **`export`** = Remotion render produced no file (check disk space / antivirus / `outputPath` writability); **`input`** = empty prompt.
- **Timed out after 15 min waiting for the UI export** — means the app never reported an outcome **at all**: the modal was closed or crashed mid-run, the app build predates the outcome channel, or the composition is genuinely enormous. **Check `outputPath` first** — then the Animation Studio modal for an on-screen error, verify **absolute** writable **`outputPath`**, and segment the composition rather than retrying it whole.
- **`file-exists` stays false while the UI shows success** — rare race or wrong path (different drive / typo); confirm **`outputPath`** matches the toast path in the app and that antivirus is not blocking writes.
- **Remotion `ProtocolError` / `Target closed`** (sometimes in app logs during headless or heavy renders) — usually a crashed or recycled Chromium target; restart Shorz, avoid overlapping heavy renders, retry.
- **No fenced code / compile error** — headless: tighten **`systemPrompt`** or set **`requireCodeFence: true`**; UI path: rephrase **`prompt`** (MCP cannot toggle fence requirement for UI).
- **Wrong assumption about `messages`** — with **`visualizeInUi: true`**, only **`prompt`** is used; put the creative brief there.
- **Empty `prompt` on UI export** — workflow still fires but produces a meaningless chat turn; always pass substantive text.
- **`animation_studio_send_message` without `systemPrompt`** — model may ignore Shorz Remotion rules; prefer UI **`send_compile_export`** for real compositions, or supply a full **`systemPrompt`**.
