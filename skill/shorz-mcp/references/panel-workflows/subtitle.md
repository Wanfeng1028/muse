# Subtitle workflow (`set_subtitle_settings`)

Subtitle styling, placement, and toggles via `set_subtitle_settings`. Convention and project targeting: `README.md`.

The **Text** sidebar also includes titles; that half is **`title.md`** / `set_title_settings`. Use **this** skill only for `subtitle*` keys—see **README.md → Text panel** when the user’s wording could mean captions, titles, or both.

## What the subtitles look like

When **captions/subtitles** are on, timed transcript text is drawn on the **main video preview** (and carried into export) using the font, colors, optional background pill, strokes, and vertical/word-wrap settings from this panel. Titles use **`title.md`** and are separate overlay text.

## Tool contract

**Primary:** `set_subtitle_settings`

**Arguments:**

- `projectPath` — absolute path to the project directory.
- `settings` — only documented keys below; nest under `settings`. Unknown keys are rejected (strict schema).

**Persistence:** successful patches merge into **`TEXT_SETTINGS`** (Python-style string values on disk, e.g. `subtitle_active`: `"True"` / `"False"`). Use **`read_project_settings`** after writes to confirm stored keys (`subtitle_font_size` as string, etc.).

**MCP → `TEXT_SETTINGS` (main mappings):** `subtitlesActive` → `subtitle_active`; `subtitleColor` → `subtitle_font_color`; `subtitleFontFamily` → `subtitle_font_name`; `subtitleFontStyle` → `subtitle_font_style`; `subtitleFontSize` → `subtitle_font_size`; `subtitleFontAnimations` → `subtitle_font_animations` (JSON array string) + `subtitle_font_animation` (first entry); `subtitleFontCapitalization` → `subtitle_font_capitalization`; `subtitleHighlightWord` → `subtitle_highlight_word`; `subtitleHighlightFontColor` → `subtitle_highlight_font_color`; `subtitlePositionY` → `subtitle_position_vertical`; `subtitlePositionX` → `subtitle_position_horizontal` (default **50** = centered); `subtitleMaxWordsPerLine` → `subtitle_max_words_per_line`; `subtitleBackgroundType` → `subtitle_bg_type`; `subtitleBackgroundAnimation` → `subtitle_bg_animation`; other background keys → `subtitle_bg_*`; stroke keys → `subtitle_stroke1_*` / `subtitle_stroke2_*`.

**Prefer this tool over raw `update_project_settings` for captions.** If you do patch `TEXT_SETTINGS` directly, the enum keys (`subtitle_font_capitalization`, `subtitle_highlight_word`, `subtitle_bg_type`, `subtitle_bg_animation`, `title_bg_type`) take the exact option strings listed below. Common synonyms (`"Uppercase"` → `Capital Letters`, `"Color"` → `Highlight Spoken Word`) are rewritten and reported in `textSettingsNormalized`; any other value is rejected. `Highlight Spoken Word` with `subtitle_bg_type` `None` paints the active word in `subtitle_highlight_font_color`. The renderer applies the same mapping to settings already on disk and logs an error for anything it cannot map.

**Brand spelling:** transcripts spell the brand `Shorz` / `shorz.ai` automatically. Scribe's "Shores", "Shore's" and "Shors" are corrected when they read as the name, while "the shores of…", "Gulf Shores" and similar stay as spoken.

**Layout keys accepted but not persisted by this tool:** `subtitleAlignment` and `subtitleScale` are validated then dropped server-side (no `TEXT_SETTINGS` mapping). Do **not** generalize this to titles — `titleAlignment` **is** persisted (`title_alignment`); see `title.md`.

**High-value keys (persisted unless noted above):**

- **Toggle / presence:** `subtitlesActive`
- **Typography:** `subtitleFontFamily`, `subtitleFontStyle`, `subtitleFontSize`, `subtitleFontAnimations`, `subtitleFontCapitalization`, `subtitleHighlightWord`, `subtitleHighlightFontColor`
- **Layout (persisted):** `subtitlePositionX`, `subtitlePositionY`, `subtitleMaxWordsPerLine`
- **Background:** `subtitleBackgroundType`, `subtitleBackgroundAnimation`, `subtitleBackgroundColor`, `subtitleBackgroundGradientColor2`, `subtitleBackgroundPadding`, `subtitleBackgroundRadius`, `subtitleBackgroundTransparency`
- **Stroke:** `subtitleStrokeEnabled`, `subtitleStrokeColor`, `subtitleStrokeWidth`, `subtitleStrokeBlur`, `subtitleStroke2Enabled`, `subtitleStroke2Color`, `subtitleStroke2Width`, `subtitleStroke2Blur`

**Integer ranges (inclusive; out-of-range values are rejected, not clamped):** `subtitleFontSize` 8–128; `subtitlePositionX` 0–100; `subtitlePositionY` 0–95; `subtitleMaxWordsPerLine` 1–10; `subtitleBackgroundPadding` / `subtitleBackgroundRadius` 0–50; `subtitleBackgroundTransparency` 0–100; `subtitleStrokeWidth` / `subtitleStroke2Width` 1–20 (width `0` only allowed together with the matching `subtitleStrokeEnabled` / `subtitleStroke2Enabled` `false`); `subtitleStrokeBlur` / `subtitleStroke2Blur` 0–10.

**Colors:** only `#RRGGBB` or `#RRGGBBAA` for `subtitleColor`, `subtitleHighlightFontColor`, `subtitleBackgroundColor`, `subtitleBackgroundGradientColor2`, `subtitleStrokeColor`, `subtitleStroke2Color`.

**`subtitleFontCapitalization`:** `None`, `Capital Letters`, `Lowercase Letters`, `Title Case Letters`

**`subtitleHighlightWord`:** `None`, `Highlight Spoken Word`

**`subtitleBackgroundType`:** `None`, `Solid Background`, `Gradient Vertical`, `Gradient Horizontal`

**`subtitleBackgroundAnimation`:** `None`, `Pop`, `Fade-in`, `Bounce`, `Slide-up` — animates the active spoken word when **`subtitleHighlightWord`** is **`Highlight Spoken Word`**. Ignored for other highlight modes and for whole-line **`subtitleFontAnimations`**.

**`subtitleFontAnimations` (each array entry; copy verbatim):**

`None`, `Fade-in`, `Fade-out`, `Zoom-in`, `Zoom-out`, `Floating`, `Float & Rotate`, `Bounce`, `Slide-in from Top`, `Slide-in from Bottom`, `Slide-in from Left`, `Slide-in from Right`, `Vertical Skew-in`, `Horizontal Skew-in`, `Vertical Skew-out`, `Horizontal Skew-out`

(`Random` / `Random Rotate` are not valid in this array.)

## Instruction handling rules

- **Captions on or off only** — patch `subtitlesActive` only.
- **Style only** — typography / background / stroke without placement unless placement is explicitly requested.
- **Readability** — font size, max words per line, stroke, contrast-related colors first.
- **Position** — use **`subtitlePositionX`** (horizontal center %) and **`subtitlePositionY`** (top edge %). Sliders move linearly; the UI preset grid sets inset-aware percents from measured text size. Do not rely on `subtitleAlignment` or `subtitleScale` over MCP.
- **Configure only** — patch and stop before Create Video.

## Execution sequence

1. Resolve project (`README.md`).
2. Call `set_subtitle_settings` with a minimal patch.
3. Report `success`, `error`, and `applied`; confirm persistence with **`read_project_settings`** → **`TEXT_SETTINGS`** for the keys above (especially after stroke toggles—`applied` may not match disk when disabling stroke with width `0`).
4. Trigger Create Video only when requested.

## Common failures

- Invalid color format — hex only (`#RRGGBB` / `#RRGGBBAA`).
- Unsupported animation ids — errors list allowed strings; copy exactly (including hyphenation and spaces).
- Out-of-range integer fields — **rejected** with a range message (not clamped).
- Non-integer numeric fields where an integer is required (e.g. `subtitleFontSize`) — rejected.
- Stroke width `0` — only valid with disable flows (`subtitleStrokeEnabled: false`, and similarly for stroke 2); enabling stroke with width `0` fails.
- Unknown keys — remove extra fields from `settings`.
- Wrong shape — `projectPath` and `settings` must be top-level tool arguments.
