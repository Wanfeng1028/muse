# Thumbnail Creator (MCP workflow)

Use **Shorz MCP** tools to drive Thumbnail Creator headlessly. Resolve **`projectPath`** first (`get_current_open_project`, then `list_projects` if needed). Global panel rules and project targeting live in this folder’s **`README.md`**. MCP bridge setup (Shorz must be running, `%TEMP%\.mcp_bridge_config.json`) is in **`mcp-server/README.md`**.

---

## Tools (what to call)

| Tool | When |
|------|------|
| **`open_thumbnail_creator`** | Optional UI parity before editing. No parameters. |
| **`set_thumbnail_creator_settings`** | Patch draft fields. **`projectPath` required.** **`openModal`** optional (default **`true`**; use **`false`** to avoid focusing the modal). |
| **`thumbnail_creator_generate`** | Start generation. **`projectPath`** + **`description` required.** By default (**`awaitCompletion`** omitted or **`false`**) returns **immediately** with **`generationRunId`**—AIML runs in the background; then **`get_thumbnail_creator_generation_status`** / **`read_project_settings`** until **`isGenerating`** is **`false`**. Pass **`awaitCompletion: true`** only for the legacy synchronous JSON (**`savedLocalFilePaths`** in the same response)—may exceed MCP client timeouts on slow models. Optional **`openModal`**, **`fileNamePrefix`** (default **`"thumbnail"`**). AIML auth uses **Shorz configured API keys** only (no per-call override). |
| **`get_thumbnail_creator_generation_status`** | Poll **`isGenerating`**, **`generationRunId`**, **`thumbnailCount`** after async **`thumbnail_creator_generate`**. **`projectPath`** required. Cheap call—use every few seconds until **`isGenerating`** is **`false`**. |
| **`close_thumbnail_creator`** | After the workflow unless the user asked to leave the panel open. |
| **`get_generated_thumbnails`** | List saved thumbnails (paths, dates, etc.). |
| **`download_generated_thumbnail`** | Save a URL or data URL as a new file under Generated Thumbnails (**`urlOrDataUrl`**, **`fileName`**, optional **`targetWidth`** / **`targetHeight`**). |
| **`delete_asset`** | Remove a file by absolute **`filePath`** (e.g. from listing). Destructive—confirm intent. No separate “delete thumbnail” tool. |
| **`read_project_settings`** | Inspect disk truth after writes or long generation—parse **`THUMBNAIL_CREATOR.thumbnail_creator_draft`** (JSON string) for **`description`**, **`isGenerating`**, **`thumbnails`**, etc. |

Do **not** use **`generate_images`** for this flow; it bypasses Thumbnail Creator draft behavior and uses different options.

**Draft updates:** Prefer **`set_thumbnail_creator_settings`** for field-level patches. Use **`update_project_settings`** only when you must merge partial **`settings.json`** without invoking the thumbnail IPC (same deep-merge rules as **`panel-workflows/README.md`**); avoid replacing the entire project file.

---

## User wording → MCP parameters

When users use app-style labels, map to tool arguments like this:

| User / app label | MCP argument |
|------------------|--------------|
| GPT Image 2.5 | **`imageGenerator`:** **`gpt-image-2`** (the `gpt-image-2` id now serves GPT Image 2.5) |
| Nano Banana 2 | **`imageGenerator`:** **`nano-banana`** |
| Quality 1K / 2K / 4K (with Nano) | **`resolution`:** **`1K`** \| **`2K`** \| **`4K`** |
| Quality Low / Medium / High (with GPT) | **`gptImageQuality`:** **`low`** \| **`medium`** \| **`high`** (GPT Image 2.5 API enum). Default in app + draft: **`medium`**. |
| YouTube (landscape layout) | **`aspectRatio`:** **`16:9`** |
| Shorts (vertical) | **`aspectRatio`:** **`9:16`** |
| Number of variations | **`numVariations`:** integer **1–6** |
| YouTube video link (optional) | **`youtubeReferenceUrl`:** full URL, Shorts/watch/embed URL, or 11-character video id |

**Shorts + YouTube link:** **`youtubeReferenceUrl`** is only applied when **`aspectRatio`** is **`16:9`** — for **either** model (Nano Banana via `image_urls`, GPT Image 2.5 via OpenAI image edits). For **`9:16`**, omit it or expect no effect.

---

## Parameters (all tools that accept them)

- **`description`** — **Required on `thumbnail_creator_generate`.** A **creative thumbnail idea**: the hook or story in one coherent picture—who/what’s in frame, reaction or action, vibe, backdrop, notable props, how it should read when small. Invent or refine from the user; keep it evocative, not shot-list engineering. Omit pixel sizes (**`aspectRatio`** and **`resolution`** set output dimensions).

- **`textOverlay`** — Optional short headline shown on-image. Empty = no overlay line in the model prompt; if set, MCP appends wording of the form: include prominent overlay text **matching** what you passed (quotes literal in prompt). Separate system text adds readability/font hints—do **not** paste long font lists into **`textOverlay`**.

- **`imageGenerator`** — **`nano-banana`** \| **`gpt-image-2`**. **Always pass explicitly when possible.** If **`thumbnail_creator_generate`** omits it, the server default is **`nano-banana`** even though a newly created draft tends toward **`gpt-image-2`**—omission is confusing. Both models accept **`referenceImages`** and (for **16:9**) **`youtubeReferenceUrl`**: Nano Banana edits via `image_urls`, GPT Image 2.5 via OpenAI image edits.

- **`aspectRatio`** — **`16:9`** \| **`9:16`**.

- **`resolution`** — **`1K`** \| **`2K`** \| **`4K`**. Used by **Nano Banana** only; GPT Image 2.5 ignores it for API quality (GPT uses **`gptImageQuality`**).

- **`gptImageQuality`** — **`low`** \| **`medium`** \| **`high`**. **GPT Image 2.5** only; persisted in draft with Nano; **Nano** ignores it for generation. On **`thumbnail_creator_generate`**, if omitted, the server derives quality from the **saved draft’s** `gptImageQuality` (with legacy normalization: **`auto`**→**`medium`**, **`extra_low`**→**`low`**). If the draft value is still ambiguous, fallback uses the **`resolution`** argument **passed to this generate call** (default **`1K`**→**`medium`**, **`2K`**/**`4K`**→**`high`**)—not a silent cross-map from Nano **`resolution`** alone.

- **`numVariations`** — **1–6** (clamped server-side).

- **`referenceImages`** — Array of strings: **`http`/`https`**, **`data:`**, **`local-resource://`**, or **absolute local paths** to image files. **Both** models send them into the generation request: **`nano-banana`** as `image_urls`, **`gpt-image-2`** via OpenAI image edits.

- **`youtubeReferenceUrl`** — See next section.

- **`selectedPreviewUrl`** — **`set_thumbnail_creator_settings`** only (string or **`null`**). The draft's currently highlighted preview — the image the modal shows large and the one the app treats as "the chosen thumbnail". A finished generation sets it to the newest result automatically, so you rarely need to write it; pass a URL from **`read_project_settings`** → **`thumbnail_creator_draft.thumbnails`** to pick a different variation for the user, or **`null`** to clear the selection.

- **`awaitCompletion`** — **`thumbnail_creator_generate`** only. **`false`** or omit (**default**): non-blocking; MCP returns **`accepted`**, **`generationRunId`**, then poll **`get_thumbnail_creator_generation_status`** until **`isGenerating`** is **`false`**. **`true`**: wait for AIML and return **`savedLocalFilePaths`** in that tool response (legacy; risks **`terminated`** from short MCP timeouts).

**GPT vs Nano quality:** Thumbnail Creator keeps **two independent controls** in the draft—**`resolution`** (Nano’s 1K / 2K / 4K) and **`gptImageQuality`** (GPT’s low / medium / high). Switching models in the app does not silently cross-map one into the other except the one-time Nano→GPT shortcut (1K→`medium`, 2K/4K→`high`).

---

## **`youtubeReferenceUrl`** (poster still as reference)

Purpose: steer **`16:9`** generations (either model) using that video’s **static thumbnail URL** as the **first** reference, merged with **`referenceImages`**, **max three** images total (**YouTube URL first**, then extras).

- Parses common YouTube URLs or a bare 11-character id—**not** “save the thumbnail to disk then pass a path.” Separate from **`download_generated_thumbnail`** (extra copies saved on demand).

- **`gpt-image-2`:** used as a reference via OpenAI image edits (same as Nano).

- Over **MCP**, the resolved thumbnail URL uses a fixed **hq-grade** CDN pattern (**no** step-up to larger poster sizes that the GUI might probe automatically).

Practice: channel / “reuse this thumbnail look” workflows → either model + **`16:9`** + **`youtubeReferenceUrl`**; avoid duplicating the same shot again in **`referenceImages`**.

---

## Generation behavior agents should expect

- **Async by default (recommended):** **`thumbnail_creator_generate`** without **`awaitCompletion: true`** finishes the MCP request **immediately** after validation and draft updates; AIML runs **in process**. Poll **`get_thumbnail_creator_generation_status`** (or parse **`read_project_settings`** → **`thumbnail_creator_draft`**) until **`isGenerating`** is **`false`**, then read **`savedLocalFilePaths`** from **`read_project_settings`** / **`get_generated_thumbnails`**. Only one generation per project at a time—if **`isGenerating`** is already **`true`**, the tool returns an error with the existing **`generationRunId`**.

- **Sync / legacy (`awaitCompletion: true`):** Blocks until AIML returns—same JSON as before (**`savedLocalFilePaths`**, **`warnings`**). Can still hit **IDE MCP timeouts** (**`terminated`**) on slow models; prefer async + polling for agents.

- **Latency:** Each image request can still take **minutes**; the server uses a **long HTTP timeout** (~15 minutes) per AIML call when **`awaitCompletion`** is **`true`**. Background jobs use the same timeouts inside the Node process.

- **Stale MCP Node process:** After editing **`mcp-server/index.js`**, restart the MCP server (or Cursor) so **`set_thumbnail_creator_settings`** / **`thumbnail_creator_generate`** match the latest code—long-lived MCP processes can serve old handlers.

- **Nano, no refs and no usable YouTube ref above:** Text-led generation path (with backend web search enabled on that route).

- **Nano, any refs (files, URLs, or YouTube-derived URL):** Reference / edit-style path. The **≤3** cap applies **only when a `youtubeReferenceUrl` resolved** (the poster is prepended and the merged list is then truncated to three); with no YouTube reference, every entry you pass in **`referenceImages`** is sent. Oversized payloads may retry with **only the first reference** (**warning** in **`warnings`**).

- **GPT Image 2.5:** Text + aspect **`size`** from **`aspectRatio`**. With refs, uses OpenAI image edits (**`size`** from **`aspectRatio`**).

- Successful runs **write PNGs** (default names **`{fileNamePrefix}-{timestamp}.png`**) into the app’s **Generated Thumbnails** area; **`16:9`** outputs are resized toward **1280×720**, **`9:16`** toward **1080×1920**. With **`awaitCompletion: true`**, the tool JSON lists **`savedLocalFilePaths`** and **`generatedCount`**. With async mode, infer success from disk after **`isGenerating`** clears.

Typical **`warnings`** strings:

- References present with **`gpt-image-2`** → using references via OpenAI image edits.

- References present with **`nano-banana`** → using references with Nano.

- Retry after payload size → Nano retried with first reference only.

---

## Typical sequence

1. **`projectPath`**
2. **`open_thumbnail_creator`** (optional).
3. **`set_thumbnail_creator_settings`** — minimal patches; mirror the same knobs on **`thumbnail_creator_generate`** (or omit redundant fields on generate so the draft supplies them).
4. **`thumbnail_creator_generate`** — omit **`awaitCompletion`** or set **`false`**; confirm **`accepted`** + **`generationRunId`** in the response.
5. Loop **`get_thumbnail_creator_generation_status`** every **2–5 s** until **`isGenerating`** is **`false`** (or use **`read_project_settings`** for the same fields).
6. **`read_project_settings`** / **`get_generated_thumbnails`** — verify new thumbnails / paths.
7. **`close_thumbnail_creator`** when done unless the user asked to leave the panel open.

**Optional synchronous path:** Pass **`awaitCompletion: true`** on step 4 and skip polling—interpret **`savedLocalFilePaths`** / **`warnings`** directly if the MCP client does not time out.

## Defaults (**`thumbnail_creator_generate`** omit list)

**If omitted:** **`awaitCompletion`** → **`false`** (async). **`textOverlay`** → empty; **`imageGenerator`** defaults **`nano-banana`** (**prefer passing explicitly**); **`aspectRatio`** → **`16:9`**; **`resolution`** → **`1K`**; **`gptImageQuality`** → from saved draft + normalization, with fallback using this call’s **`resolution`** value (see **`gptImageQuality`** bullet above—not only “default medium”); **`numVariations`** → **1**; refs / YouTube inherit from draft when not passed. Generation runs on **Shorz account credits** via the proxy (gpt-image-2 → OpenAI, nano-banana → AIMLAPI); no user-configured AIML key is used — if generation fails, confirm sign-in/balance with **`get_shorz_credits`**. **No free-tier access:** thumbnail generation is not on the free run's zero-rated allowlist, so a zero-balance user 402s here even while a free `auto-edit` / `clipping` render is in flight (the in-app Generate button opens the purchase modal for them). Editing the draft with `set_thumbnail_creator_settings` is free — only `thumbnail_creator_generate` costs.

## Common pitfalls

- Empty **`description`**.

- **`youtubeReferenceUrl`** with **Shorts** (**`9:16`**) expecting a poster ref—inactive.

- Assuming **`gpt-image-2`** ignores **`referenceImages`**. It does **not** — both models consume them (GPT Image 2.5 via OpenAI image edits), so references you leave in the draft still steer a GPT run, and dropping them is an explicit patch (**`referenceImages: []`**), not a side effect of switching models.

- Assuming a **`terminated`** MCP result means generation failed—mostly relevant when using **`awaitCompletion: true`**; use async + polling to avoid long-held tool calls.

- Starting a second **`thumbnail_creator_generate`** while **`isGenerating`** is **`true`**—returns **`error`**; poll until idle first.

- **`delete_asset`** on the wrong **`filePath`** deletes that file outright.
