# Title workflow (`set_title_settings`)

Title headline text, styling, timing, and background via `set_title_settings`. Convention and project targeting: `README.md`.

The **Text** sidebar also includes subtitles; that half is **`subtitle.md`** / `set_subtitle_settings`. Use **this** skill only for `title*` keys—see **README.md → Text panel** when the user’s wording could mean captions, titles, or both.

## What titles look like

When **Title** is on, the headline from **`titleText`** is drawn on the **main video preview** (Editor mode) and in **export** using the title font, colors, optional background box, strokes, position, and entrance animation from this panel.

- **Manual placement** — uses the exact string in **`titleText`** for the full clip window (or the manual start/duration window).
- **AI automatic placement** — Create Video may replace visible copy with AI-generated segment headlines from the transcript; **`titleText`** still drives Editor preview and is the fallback headline when AI placement is off or segments are empty.
- **Optional inline Unicode emojis** — if included in **`titleText`**, standard emoji characters (e.g. `Hook 🔥`) render **inline inside the title line** in Editor preview and export (color Twemoji-style glyphs via backend `pilmoji`). Plain text titles work unchanged; no emoji is required. No extra MCP key or toggle. Requires network on first use per emoji glyph unless already cached in the Python session.
- **Not the same as B-roll emojis** — timed PNG overlays from **`set_broll_settings`** (`automaticEmojis`, `emojiCount`, …) are transcript-timed inserts. For emoji **in the headline string**, patch **`titleText`** only (**this** skill).

## Tool contract

**Primary:** `set_title_settings`

**Arguments:**

- `projectPath` — absolute path to the project directory.
- `settings` — only documented keys below; nest under `settings`. Unknown keys are rejected (strict schema), including legacy **`titleScale`** (removed; use the Text UI / raw settings if you ever need that concept—it is not in this MCP tool).

**Persistence:** successful patches merge into **`TEXT_SETTINGS`** (Python-style string values on disk). `titleFullscreenBackground` ↔ `title_fullscreen_background`. Use **`read_project_settings`** after writes to confirm.

**MCP → `TEXT_SETTINGS` (layout):** `titlePositionY` → `title_position_vertical`; `titlePositionX` → `title_position_horizontal` (default **50** = centered horizontally).

**Text alignment vs position — two different things:**

- **`titleAlignment`** (`left` | `center` | `right`, default `center`, persisted as `title_alignment`) sets how **wrapped lines sit relative to each other inside the title block**. The block is as wide as its longest line, so alignment is only visible when the title wraps onto **more than one line** (see `titleMaxWordsPerLine`); a one-line title looks identical at all three values.
- It does **not** move the title around the frame. For that use `titlePositionX` / `titlePositionY` — the block keeps its position, only the short lines shift inside it.
- Applies to both placement modes (Manual `apply_title` and AI automatic `apply_title_placement`), and to `render_text_preview` via the payload's `textAlign` field.
- Projects saved before this key existed have no `title_alignment` at all; backend and UI both fall back to `center`, which renders byte-identically to how they always did.

**Position semantics (export + Editor preview):**

- **`titlePositionX`** — horizontal **center** of the title image as **0–100%** of frame width (not the left edge).
- **`titlePositionY`** — **top edge** of the title image as **0–95%** of frame height.
- **Bounds clamping** — backend and preview clamp X/Y so the full measured title box (font, padding, strokes, emoji width) stays inside a ~**2%** frame inset. Raw slider values like **100%** horizontal are stored but clamped at render time if the text would clip off-screen.
- **Preset grid** — the Text panel **Position presets** compute inset-aware X/Y from **measured** title width/height; presets stay disabled until preview metrics load. Prefer presets or clamp-aware percents over guessing edge values from font size alone.

High-value keys:

- **Toggle / content:** `titleActive`, `titleText` (plain text or optional inline Unicode emoji; UTF-8 string)
- **Typography:** `titleFontFamily`, `titleFontStyle`, `titleFontSize`, `titleFontAnimations`, `titleColor`, `titleMaxWordsPerLine`, `titleAlignment`
- **Layout (persisted):** `titlePositionX`, `titlePositionY`
- **Timing / placement:** `titlePlacement` (`AI automatic` | `Manual`; **new-project default is `Manual`**), `titleStartTime`, `titleDuration`, `titleAnimationIn`, `titleAnimationOut`
- **AI automatic fullscreen backdrop:** `titleFullscreenBackground` — project path, `https` URL, `local-resource://`, or data URL; `""` or `null` clears. Persisted as `TEXT_SETTINGS.title_fullscreen_background` (same as the Title timing panel control; shown when placement is **AI automatic**). Typical image types: jpg, jpeg, png (match what the panel accepts).
- **Background:** `titleBackgroundType`, `titleBackgroundColor`, `titleBackgroundGradientColor2`, `titleBackgroundPadding`, `titleBackgroundRadius`, `titleBackgroundTransparency`
- **Stroke:** `titleStrokeEnabled`, `titleStrokeColor`, `titleStrokeWidth`, `titleStrokeBlur`, `titleStroke2Enabled`, `titleStroke2Color`, `titleStroke2Width`, `titleStroke2Blur`

**Integer ranges (inclusive; out-of-range values are rejected, not clamped):** `titleFontSize` 12–256; `titlePositionX` 0–100; `titlePositionY` 0–95; `titleMaxWordsPerLine` 1–10; `titleBackgroundPadding` / `titleBackgroundRadius` 0–50; `titleBackgroundTransparency` 0–100; stroke widths/blur same family as subtitles (see `subtitle.md`).

## Instruction handling rules

- **Headline text only** — patch `titleText`; set `titleActive: true` if enabling is implied. Do not add emoji unless the user asks; when present, they are part of the string (e.g. `"Summer sale 🔥"`). Do not enable B-roll `automaticEmojis` for headline emoji unless the user also wants timed transcript emoji overlays.
- **Manual timing** — patch `titlePlacement: "Manual"` plus timing keys.
- **Style only** — typography / background / stroke without timing unless timing is explicitly requested.
- **Position** — use **`titlePositionX`** (horizontal center %) and **`titlePositionY`** (top edge %; max **95**). For corner/side alignment, prefer the app preset grid or inset-aware percents; export clamps overflow. After changing **`titleText`**, font size, or **`titleMaxWordsPerLine`**, re-check position if the user had edge alignment — wider text may need a lower **`titlePositionX`** for right-aligned layouts.
- **Disable titles** — `titleActive: false` only unless cleanup of text content is explicitly requested.

## Preview tooling

- **`render_text_preview`** — optional; payload `{ type: "title", text, font, colors, background, stroke1/2, maxWordsPerLine, textAlign, video: { width, height }, positionXPercent, positionYPercent }`. `textAlign` mirrors `titleAlignment` (`left` | `center` | `right`); omit it for `center`. Title payloads render any inline emoji in `text` the same as export. Useful to verify layout (and optional emoji) without Create Video. Returns `{ success, previews: [{ pngFilePath, width, height, yPixel, bytes }] }` — the PNG is written to a file and only its path comes back, so read `pngFilePath` to look at the render.

## Execution sequence

1. Resolve project (`README.md`).
2. Patch requested keys with `set_title_settings`.
3. Return applied values and placement mode (`AI automatic` vs `Manual`).
4. Trigger Create Video only when requested.

## Common failures

- Invalid `titlePlacement` — only `AI automatic` or `Manual`.
- **Unknown or legacy keys** — MCP returns validation errors (e.g. `unrecognized_keys`). Do not send `titleScale`.
- Invalid color, animation, or font-style values — use schema / error hints.
- Out-of-range timing or numeric fields — clamp or fix per validation.
- **Title clipped at frame edge** — `titlePositionX`/`titlePositionY` may be out of bounds for current text width; lower **`titlePositionX`** for right-side titles or use Position presets after text/metrics settle.
- **`titleFullscreenBackground`** — max length and no control characters; empty string clears.
- Stroke width `0` — only valid with `titleStrokeEnabled: false`.
