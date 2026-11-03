# Advertisement workflow (project type `advertisement`)

Storyboard-driven **promotional / brand-story** project anchored on a **Product and/or Character** reference image. Use **`set_advertisement_settings`** for the panel contract plus headless image pickers for local files. Global rules and routing live in **`../../SKILL.md`**.

Use this for commercial/product/promo clips and short brand stories. For broad montage requests use **`auto-edit.md`**; for long-form narrated storyboard pieces use **`text-to-video.md`**.

## How it works (pipeline)

On **Create Video**, Shorz builds the ad as one continuous story:

1. A story-plan LLM designs the whole ad and splits the chosen length into **N = round(duration / 10)** ten-second **scenes**.
2. For each scene it generates one **GPT Image 2.5 storyboard image** (consistent character/product/style, re-anchored to the reference images each scene).
3. Each storyboard is animated into a **10-second clip by Gemini Omni 1.1 Flash** (reference-to-video, native audio: speech/ambience/SFX).
4. The scene clips are **concatenated** into the final ad, sized to the project aspect ratio.

It works as a **pure product ad** (product only), a **character/brand story** (character only), or **both together**. Auto Edit and Clipping do not run for this project type.

## What it looks like

The Advertisement panel shows:

- **Product** — optional reference still (the product to feature).
- **Character** — optional reference still (the person who presents / is the story; has a **Generate** button).
- **Video generation model** — locked to **Gemini Omni 1.1 Flash** (single, pre-selected option "for now").
- **Ad duration (seconds)** — total length, **10–40 in steps of 10** (= N × 10s scenes). 40s is Gemini Omni 1.1's maximum total clip length.
- **PromptBar** — the creative brief; this drives style and story, not just the images.

**At least one** of Product / Character is required (the renderer aborts only if BOTH are missing). If the brief carries no style direction, style is derived from the Character image (then Product).

**Main VIDEO lane —** In **Your Library**, the **VIDEOS** tab is **hidden** (same grouping as **`avatar`** / **`podcast`**), and `import_frontend_assets` with **`assetType: "video"`** is **rejected with an error** (headless `overridePaths` path). The flow is **reference stills** via `set_advertisement_settings` / `select_advertisement_image` / **`import_frontend_assets`** with **`assetType: "image"`** — not a main-timeline VIDEO import story.

## Tool contract

**Primary tool:** `set_advertisement_settings`

**Arguments:** `projectPath` (absolute) and a `settings` object with only the keys you want to change.

**Supported keys in `settings`:**

| Key | Type | Notes |
|---|---|---|
| `advertisementVideoModel` | string enum | Accepted for compatibility, but the renderer **always uses `gemini-omni-flash-preview`** (engine is locked for now). |
| `advertisementDurationSeconds` | integer | **TOTAL** ad length, **10–40** (in steps of 10). Split into `round(v/10)` × 10s scenes. 40s is Gemini Omni 1.1's maximum total clip length. |
| `advertisementProductImage` | string or `null` | Path/URL to the Product image. |
| `advertisementPersonImage` | string or `null` | Path/URL to the **Character** image (settings key kept as `*_person_image` for compatibility). |

**MCP validation:** `set_advertisement_settings` **rejects** (`success: false` with an explicit message) when `advertisementDurationSeconds` is not an integer in **10–40**. Duration is the total ad length and is **no longer per-model bounded** (each scene is internally clamped to 10s by the Omni route). Values are typically multiples of 10; the renderer rounds to the nearest 10s scene count.

Default duration when omitted is **`30`** (app default `ADVERTISEMENT.advertisement_duration_seconds`); default model is **`gemini-omni-flash-preview`**.

**Persistence oracle** — confirm via `read_project_settings` → `ADVERTISEMENT`:

| MCP key | `ADVERTISEMENT` key |
|---|---|
| `advertisementVideoModel` | `advertisement_video_model` |
| `advertisementDurationSeconds` | `advertisement_duration_seconds` (stringified integer) |
| `advertisementProductImage` | `advertisement_product_image` |
| `advertisementPersonImage` | `advertisement_person_image` (the Character) |

### Project-specific media helpers

| MCP tool | Arguments | Effect |
|---|---|---|
| `select_advertisement_image` | `projectPath`, `imageFilePath`, `role`: `product` \| `person` \| `character` | Imports the file and sets `advertisementProductImage` or `advertisementPersonImage`. `character` is an alias for `person`. |
| `remove_advertisement_image` | `projectPath`, `role`: `product` \| `person` \| `character` | Clears the corresponding image path. `character` = `person`. |

**Supported image extensions** for `select_advertisement_image`: `.png`, `.jpg`, `.jpeg` (no `.webp`).

For batch imports, use `import_frontend_assets` with `assetType: "image"`, then patch paths via `set_advertisement_settings`.

## Instruction handling rules

- **Create an ad from scratch** — confirm `projectType: "advertisement"`, set the total duration (10–60), and **at least one** of Product / Character image. Persist the PromptBar ad brief. Trigger Create Video on user request. (You don't need to set the model — it's locked to Gemini Omni 1.1 Flash.)
- **Edit existing ad behavior** — patch only the requested keys; keep unrelated settings untouched.
- **Swap or remove product / character image** — `select_advertisement_image` or `remove_advertisement_image`; do not rewrite full settings.
- **Change creative brief only** — `set_user_instructions`; do not modify panel keys. Brief must not include aspect ratio or pixel dimensions (**SKILL.md** → *Output framing*). The brief drives the story, pacing, speech/narration and style.
- **Configure only** — apply settings + PromptBar; skip `trigger_create_video`.
- **Minimal patches** — pass only requested keys.

## Execution sequence

1. **Resolve project** per **SKILL.md** → *Project targeting rules*. Create only with explicit approval via `create_project` with `projectType: "advertisement"`.
2. **Read state** (optional): `read_project_settings` → inspect `ADVERTISEMENT`.
3. **Duration** — `set_advertisement_settings` with `advertisementDurationSeconds` (10–40). Model is optional (locked to Omni).
4. **Imagery** — `select_advertisement_image` per role (local paths) or `import_frontend_assets` + path patch. At least one of Product / Character. Use `remove_advertisement_image` to clear a role.
5. **PromptBar** — `set_user_instructions` with the ad brief (audience, offer, story, tone, exact spoken lines, audio direction).
6. **Create Video** (only when the user asks for a render):
   - `trigger_create_video` (preferred) or `generate_video`.
   - Poll **`get_video_generation_status`** until terminal. Longer ads take longer (one storyboard + one Omni clip per 10s scene). `fetch_app_events` only on request or when debugging.
   - `stop_video_generation` on user request.
7. **Return outcome** — success/failure, output path, validation messages.

## Imported music

The generated ad still goes through the shared effects chain, so Your Library → **MUSIC** applies here too: `import_frontend_assets` with `assetType: "music"` (free, any number of files; several play **back to back** in lane order), no toggle required. The **PromptBar** can steer play order, a section of one named track, placement on the timeline, volume, fades, and mix-vs-replace — full vocabulary in **`auto-edit.md`** → *Imported music*. Note the ad's own spoken lines live in the generated video's audio, so **replace** mode will remove them: prefer mixing, or a lower `musicVolume`, unless the user explicitly wants a music-only ad. Beat-synced **cutting** does not apply (multi-asset `auto-edit` only).

## Quick defaults

- `advertisementVideoModel`: `gemini-omni-flash-preview` (locked)
- `advertisementDurationSeconds`: `30`
- `advertisementProductImage`: `""`
- `advertisementPersonImage`: `""`

## Common failures

- **Duration out of bounds** — `set_advertisement_settings` fails unless `advertisementDurationSeconds` is an integer in **10–40**. Prefer multiples of 10.
- **No imagery** — the render aborts if **both** Product and Character are empty. Ask the user to supply or import at least one image before Create Video.
- **Image extension not supported by `select_advertisement_image`** — Only `.png`, `.jpg`, `.jpeg`. For `.webp` or other formats, import via `import_frontend_assets` (`assetType: "image"`) and patch the returned path.
- **Voice drift across scenes** — a spoken character voice may differ between separately rendered scenes; for a multi-scene ad prefer narration for a consistent voice, or keep spoken lines short.
