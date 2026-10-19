# B-roll workflow (`set_broll_settings`)



Cross-project B-roll, GIF, web image, AI B-roll, and emoji controls. Convention and project targeting: `README.md`.



## Tool contract



**Primary:** `set_broll_settings`



### Allowed transition ids (Assets / Web / GIF / AI)



`None`, `Fade In Transparent`, `Fade In Black`, `Fade In White`, `Blur to Clear`, `Slide In Left`, `Slide In Right`, `Slide In Top`, `Slide In Bottom`, `Scale In`, `Scale Out`, `Vertical Skew`, `Horizontal Skew`



The **same id set** is used for both entrance (`*TransitionAnimations`) and exit (`*TransitionOutAnimations`) pools. Exit plays the chosen effect **reversed** as the asset leaves (e.g. `Slide In Left` exits to the left, `Fade In White` dissolves to white, `Scale In` grows away). `Random *` ids are not accepted by the MCP for either pool.



Multi-select arrays must be **non-empty**. Include `None` alone for no transition effect. Entrance and exit are independent; both default to `["None"]`.



### Overlay position model (Assets fit / Web / GIF / AI / Emoji)



All overlay types use **center-X / top-Y percent** (0–100), matching title/subtitle/emoji:



- **X%** — horizontal center of the overlay box

- **Y%** — top edge of the overlay box



### Keys by panel (matches desktop UI)



- **Assets** (imported B-roll clips / stills → `BROLL_VIDEO_SETTINGS`)

  - `fullscreenBRoll`: boolean — fullscreen cover vs fit inside frame

  - `brollPositionX`, `brollPositionY`: `0..100` — **fit mode only**; ignored when `fullscreenBRoll` is true

  - `brollFitWidthPercent`: `30..100` — **fit mode only**; max width as % of frame (never upscales). Use `<100` when horizontal placement is needed.

  - `brollTransitionAnimations`: non-empty entrance transition array (plays as the asset appears)

  - `brollTransitionOutAnimations`: non-empty exit transition array (plays as the asset leaves)

  - `brollTransitionDuration`: `0.2..1.0` — applies to **both** in and out; **only meaningful when an in or out array includes a value other than `None`**

  - **Prerequisite:** Preview/export show the Assets B-roll overlay only if the project has at least one imported B-roll video or image. Use **`import_frontend_assets`** with **`assetType: "broll"`**.



- **Web images** (`IMAGE_SETTINGS`)

  - `automaticWebImages`: boolean. Billed per search for a paying user, but **zero-rated inside a free run** — safe to enable for a zero-balance `auto-edit` / `clipping` render.

  - `webImagesTransitionAnimations`: non-empty entrance transition array

  - `webImagesTransitionOutAnimations`: non-empty exit transition array

  - `webImagesAnimationDuration`: `0.2..1.0` — applies to both in and out; **only when an in or out array includes a non-`None` value**

  - `webImagesCount`: `1..30`

  - `webImagesSize`: `100..1920` — max width in pixels

  - `webImagesPositionX`, `webImagesPositionY`: `0..100`

  - (No display-time setting: each web image stays on screen for as long as its topic is spoken about, derived from the transcript. Steer it with user instructions / a prompt, e.g. "keep web images on longer".)



- **GIF** (`GIF_SETTINGS`)

  - `automaticGifs`: boolean

  - `gifType`: `sticker` | `standard`

  - `gifCount`: `1..20`

  - `gifPositionX`, `gifPositionY`: `0..100`

  - `gifWidthPercent`: `30..100`

  - `gifTransitionAnimations`: non-empty entrance transition array

  - `gifTransitionOutAnimations`: non-empty exit transition array



- **AI B-roll** (`AI_BROLL_SETTINGS`)

  - `automaticAiBroll`: boolean. **The only paid B-roll source on a free-tier run** (zero-balance `auto-edit` / `clipping`): neither mode is zero-rated, so every generation 402s. Leave it off for those users — Assets, WEB, GIF and EMOJI all work in full.

  - `aiBrollType`: `"image"` (generated stills) or `"video"` (generated text-to-video clips). Video clips cost roughly 10–30× more per placement than stills.

  - `aiBrollImageModel`: image generator for type `image` — server-catalog id (project type `broll`), e.g. `"Nano Banana 2"`, `"Nano Banana 2 Lite"`, `"GPT Image 2"` (the `GPT Image 2` id now serves GPT Image 2.5 Flare — fast), `"GPT Image 2.5 Sunburst"` (sharper, slightly slower, same 2 credits per still).

  - `aiBrollVideoModel`: video generator for type `video` — server-catalog id (project type `broll`), e.g. `"gemini-omni-flash-preview"` (native route, token-billed ~12 cr/s, 1–10s), `"bytedance/seedance-2-0-fast"`, `"bytedance/seedance-2-0"`, `"bytedance/seedance-2-0-mini"`, `"bytedance/seedance-2-5"` (premium, ~27 cr/s — rarely worth it for short overlay clips), `"klingai/video-v3-standard-text-to-video"`.

  - Video clip **length is not settable**: the AI placement analyzer derives each clip's window from the speech word-timestamps, and the renderer clamps it to the model's supported range (Seedance 2.0 family 4–15s, Seedance 2.5 4–30s, Kling 3–15s). A clip is never extended or stitched from multiple generations.

  - `aiBrollCount`: `1..30`

  - `aiBrollPositionX`, `aiBrollPositionY`: `0..100`

  - `aiBrollWidthPercent`: `30..100`

  - `aiBrollTransitionAnimations`: non-empty entrance transition array

  - `aiBrollTransitionOutAnimations`: non-empty exit transition array



- **Emoji** (`IMAGE_SETTINGS` + `AUDIO_SETTINGS`)

  - `automaticEmojis`: boolean

  - `emojiSounds`: boolean → `AUDIO_SETTINGS.audio_emoji_soundfx`

  - `emojiCount`: `1..20`

  - `emojiAnimations`: non-empty animation array

  - `emojiPositionX`: `0..100`, `emojiPositionY`: `0..95`

  - `emojiSize`: `20..400`



### Related audio (not in `set_broll_settings`)



- **B-roll / web / GIF / AI appearance sounds:** `set_audio_settings` → `imageSounds` → `AUDIO_SETTINGS.audio_broll_soundfx`



### Persistence map (`read_project_settings`)



| MCP key(s) | Settings section | Backend field examples |

|------------|------------------|-------------------------|

| Assets position | `BROLL_VIDEO_SETTINGS` | `broll_video_position_x`, `broll_video_position_y` |

| Web position | `IMAGE_SETTINGS` | `web_images_position_x`, `web_images_position_y` |

| GIF position | `GIF_SETTINGS` | `gif_position_x`, `gif_position_y` |

| AI position | `AI_BROLL_SETTINGS` | `ai_broll_position_x`, `ai_broll_position_y` |

| Assets transitions in/out | `BROLL_VIDEO_SETTINGS` | `broll_video_transition_animations`, `broll_video_transition_out_animations` |

| Web transitions in/out | `IMAGE_SETTINGS` | `web_images_transition_animations`, `web_images_transition_out_animations` |

| GIF transitions in/out | `GIF_SETTINGS` | `gif_transition_animations`, `gif_transition_out_animations` |

| AI transitions in/out | `AI_BROLL_SETTINGS` | `ai_broll_transition_animations`, `ai_broll_transition_out_animations` |



Legacy preset keys (`broll_video_vertical_position`, `gif_position`, `web_images_vertical_position`, etc.) are read for migration only; new patches should use `*PositionX` / `*PositionY`.

### Reading vs writing (`read_project_settings`)

`read_project_settings` returns **backend** keys (`broll_video_position_x`, `gif_position_y`, …). To round-trip via MCP, map to camelCase keys in `set_broll_settings` (see persistence table above). When restoring a baseline after tests, **omit** `*PositionY` (and other position keys) if the stored value is empty — otherwise you overwrite legacy-only projects with default `50` and break on-load migration.

### Position clamping and presets

Export and Editor preview **clamp** overlay boxes inside ~2% frame insets (same idea as title/subtitle). UI **Position presets** account for overlay width/height — wait for preview metrics before relying on corner presets. **Editor drag** updates the same `*PositionX`/`*PositionY` values the sliders show.



### Running several B-roll types at once (the placement arbiter)

Every analyzer (AI B-roll, web images, user assets) picks key moments from the **same transcript**,
so their windows collide far more often than chance. A cross-type **arbiter** resolves that in plain
code **after analysis and BEFORE anything is generated or billed** — so a placement it drops costs
nothing. Enabling three sources therefore does **not** yield three times the on-screen B-roll, and
the user should be told that rather than being surprised by it.

- **Value order** (winner keeps its window): **user-selected B-roll** (explicit intent) **> AI
  B-roll** (billed per placement) **> web images** (cheap search). The loser is trimmed to its
  largest free remainder, or **dropped outright** when winners cover ≥ 60% of its window; a kept
  remainder must still be ≥ 1 s.
- **Placements are never moved.** Windows are word-anchored to the exact speech they illustrate, so
  sliding one would detach it from its meaning. Trim or drop only.
- **Only *covering* overlays are arbitrated** — fullscreen mode, or width ≥ **70%** of the frame. A
  small overlay layering over a big one is normal editing, not a collision.
- **GIFs and emojis are exempt**: they composite **last**, on top of every B-roll type, so a sticker
  can never be hidden by one. (This was the reverse until 2026-08-19 — GIFs composited first and were
  silently swallowed by covering B-roll.)
- **No background flicker.** Consecutive covering placements must either hold the main video for
  ≥ **1.5 s** (a beat the viewer registers) or **overlap by ≥ 0.15 s**, like handles in an NLE. A
  frame-exact butt joint counts as neither — the plan is in seconds, the render composites quantized
  frames. Gap-closing extensions prefer free material (images), then re-request a longer AI clip
  **bounded by the model's max length**, and **never** stretch user video assets, which have no spare
  footage.
- Placements skipped as already covered are **reported back**, so surface that in your summary
  instead of letting the user infer a bug from a shorter-than-expected B-roll count.

### Instruction-driven overlays (per-placement geometry + persistent overlays)

There are **no settings keys** for these — they are driven entirely by **user instructions**
(`set_user_instructions` / the PromptBar) and resolved by the B-roll placement AI at render time:

- **Per-placement position/size.** Naming an imported B-roll asset with an explicit spot or size
  ("show chart.png small in the top right", "graph.mp4 half the screen, centered") attaches
  per-placement geometry that **overrides** the panel's global `brollPositionX/Y` /
  `brollFitWidthPercent` / `fullscreenBRoll` for that placement only. Width may go down to **5%**
  (the panel slider's floor is 30). Un-named assets keep the panel settings.
- **Persistent overlays.** Instructions like "display logo.png in the top-right corner for the whole
  video, small" or "play sparkles.mp4 over the video during the CTA" place the asset in a separate
  `persistent_overlays` plan: it stays on screen **while the video plays underneath**, may span the
  whole video (no 60s B-roll cap), loops video/GIF sources to fill its window, gets no
  entrance/exit transitions or transition sounds, and composites **on top of** every timed B-roll
  placement. Never emitted unless asked. In the arbiter, small persistent overlays (< 70% width)
  are exempt like GIFs; covering ones block AI B-roll and web images for their span.
- **Chroma key is automatic.** Green-screen / blue-screen B-roll clips (classic key paints, detected
  from the frame borders) are keyed at render time so the main video shows through — no setting, no
  instruction needed. Works for both normal placements and persistent overlays; `.webm` sources are
  accepted. Kill switch: env `SHORZ_DISABLE_BROLL_CHROMA_KEY=1`.
- **Keyed clips are cropped to their visible content** before sizing. Stock green-screen assets are
  usually a small subject in a large green field (a typical "subscribe" bug fills only ~23% of its
  own frame width), so sizing by the file's dimensions would render "show it big" as a tiny badge
  surrounded by invisible margin. The crop is the union of the opaque content across sampled frames
  (so an animated or moving subject never jitters or gets clipped), and a subject that already fills
  the frame is left alone. Net effect: `width_pct` always means the width of what the viewer sees.
- **Letting an animation finish.** A persistent overlay is cut off at the end of its window, so an
  animated CTA anchored to a short phrase ("when I say X") only plays as long as that phrase — a 4s
  subscribe animation anchored to a 1.4s line showed 34% of itself. Ask for it explicitly ("let the
  whole animation play out", "don't cut it short") and the window is sized to the asset's own length
  instead of the sentence. Clip length now reaches the placement model for every asset (it is probed
  from the file when the cached analysis lacks it — previously only GIFs carried a duration, so the
  model was guessing for every `.mp4`).
- **Loop vs hold.** When a persistent overlay's window is longer than its clip, the clip repeats only
  if the window is at least **2×** the clip length (decoration filling a long span); otherwise it plays
  once and holds its final frame. That is what keeps a subscribe animation resting on "subscribed"
  instead of snapping back to "subscribe" mid-CTA. GIFs always loop.
- **Prerequisite is unchanged:** the asset must be imported to the BROLL lane
  (`import_frontend_assets` with `assetType: "broll"`), and the instructions must use the exact
  file name so the placement AI can match it.
- **Anchor an end-card to the LAST sentence explicitly, and rule out the near misses.** Verified in
  a 4-minute production run: "at the very end, right after the final line about X" put a subscribe
  overlay on the *penultimate* beat and it had finished before the closing line played. The model
  treats "the very end" as a region, not a boundary. What works is naming the closing words, saying
  nothing may follow, and listing the sentences it must NOT pick — e.g. *"on the VERY LAST sentence
  of the narration, the one that ends with the words '…smell of rain'. Nothing may come after it.
  Do NOT anchor it to 'Blue. Very small.' or 'Two hundred million miles away.' It must still be on
  screen when the narration stops."* Check the anchor with `extract_video_frames` before shipping;
  a mis-anchored end card is the most likely defect in an otherwise correct render.
- **Persistent overlays composite above covering B-roll as documented** — verified live: a
  9%-width `logo.png` pinned top-right held every frame of a 3:43 film, including across fullscreen
  image B-roll and across the chroma-keyed subscribe overlay itself.
- **Un-instructed BROLL assets are placed on meaning, not filler.** In the same run, twelve NASA
  stills carrying no instructions were placed on lines they actually illustrate (the
  before/after dust-storm pair landed on "the sun spent a billion patient years stripping the air
  off it"). Importing more un-instructed assets than the edit needs is the right way to use this.

## Instruction handling rules



- **One automatic B-roll source** — enable only the requested toggle unless the user asks for several.

- **Assets fullscreen** — do not patch `brollPositionX/Y` when `fullscreenBRoll` is true; they have no effect.

- **Transitions** — entrance (`*TransitionAnimations`) and exit (`*TransitionOutAnimations`) are separate pools; patch only what the user asks for, leave the other at its current value. When every in/out array is just `None`, do not bother patching duration keys.

- **Aspect ratio** — `webImagesSize` max is the project frame width.

- **Configure only** — patch and stop before Create Video unless export is requested.



## Execution sequence



1. Resolve project (`README.md`).

2. Patch with `set_broll_settings`.

3. Return applied keys.

4. Trigger Create Video only when requested.



## Common failures



- Empty transition or emoji animation arrays.

- Out-of-range position or size numbers are **rejected** (not clamped).

- `brollPositionX/Y` patched while expecting fullscreen placement — use `fullscreenBRoll: true` instead.

