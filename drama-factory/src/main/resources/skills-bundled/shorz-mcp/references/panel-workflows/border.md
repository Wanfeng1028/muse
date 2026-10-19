# Border workflow (`set_border_settings`)

Cross-project border toggle, width, colors, animation, and duration. Project targeting and shared rules: **`README.md` in this folder**.

## What the border looks like

When **`border`** is on, Shorz draws a **picture frame** around the **edges of the main video preview** (a ring that sits on the outer rim of the composited picture, not a margin around the whole app). **`borderWidth`** controls how thick that rim is.

- **`borderAnimation` = `None`** — the ring is a **solid band** in **`borderColor1`** (the second color is not used for this static look).
- The ring is drawn **inside** the frame, so the exported video keeps its **original resolution and aspect ratio** (a 1080x1920 short stays 1080x1920 — the border never pads the video out to 1180x2020). A thick border covers more of the picture's outer rim; it does not make the file bigger.
- **Any other animation** — the ring uses a **blend between `borderColor1` and `borderColor2`**, and the chosen style **moves or changes** that border over time; **`borderAnimationDuration`** sets how long one full cycle of that motion takes (seconds).

The same project values are what the user tweaks in the **Border** sidebar and what will carry into **exported/generated video** for that project, so describing it as a configurable colored frame around the video helps set expectations.

## Tool contract

**Primary:** `set_border_settings`

**Arguments:**

- `projectPath` — absolute path to the project directory.
- `settings` — only the keys below; do not add other keys; nest under `settings`, not at the root of the tool call.

**Supported keys in `settings`:**

| Key | Type | Notes |
|-----|------|--------|
| `border` | boolean | On/off toggle—same meaning as the Border panel and persisted `video_border_active`. **Always use this key.** |
| `borderWidth` | number | **1–100**. Out-of-range values are **clamped**; report **`applied`**. |
| `borderColor1`, `borderColor2` | string | **Only** `#RRGGBB` or `#RRGGBBAA`. Anything else errors. |
| `borderAnimation` | string | **Exactly** one of the strings below (case-sensitive). Wrong values fail with the allowed list in the error. |
| `borderAnimationDuration` | number | **1–5** seconds. Out-of-range values are **clamped**; confirm with **`applied`**. |

Legacy integrations may still send **`borderActive`** instead of `border`; if both appear in one patch, **`border` wins** (matches the app). New work should send **`border` only**.

**Allowed `borderAnimation` values (copy verbatim):**

`None`, `Fade`, `Circular`, `Moving Circles`, `Hypnotizing Grid`, `Wave`, `Grain`, `Scratches`, `Blink`, `Full Color Spectrum`

## Instruction handling rules

- **Enable or disable border only** — send only `border` (boolean).
- **Solid / static border** — set `borderAnimation` to `None` plus any requested width and/or colors.
- **Animated border** — set `borderAnimation` and `borderAnimationDuration`; add colors and width only when the user asked (do not reset unrelated fields).
- **Invalid animation name** — do not guess. Fix spelling/casing using the error’s allowed list and retry.

## Execution sequence

1. Resolve the target project per **`README.md` in this folder** (`get_current_open_project`, then `list_projects` if needed; never auto-pick when multiple match).
2. Call `set_border_settings` with `projectPath` and a minimal `settings` patch.
3. Tell the user **`success`**, **`error`** (if any), and **`applied`** values (after clamp). To confirm what was stored for the toggle, use **`read_project_settings`** and check `VIDEO_BORDER.video_border_active` (`True` / `False` strings).
4. **Create Video** — only when the user wants a rendered video, per **`README.md`**: e.g. `set_user_instructions`, then `trigger_create_video` or `generate_video`, and poll **`get_video_generation_status`**. Use **`fetch_app_events`** only for logs on request or when troubleshooting (see **`../../SKILL.md`**).

## Common failures

- **Invalid `borderAnimation`** — error lists allowed strings; copy one exactly and retry.
- **Invalid colors** — message asks for `#RRGGBB` or `#RRGGBBAA`.
- **Out-of-range width or duration** — call still **succeeds** but values are **clamped** to **1–100** and **1–5**; always show **`applied`** so the user sees what was stored.
- **Unknown keys** — remove extra fields from `settings`.
- **Wrong shape** — `projectPath` and `settings` must be top-level tool arguments.

## Stepping through animations (UI preview)

To let the user see each animation type, call **`set_border_settings`** once per item in this order (same spelling as the tool). Keep **`border: true`** and other fields stable unless they asked otherwise. Pause a few seconds between calls if they need time to look at the Border panel.

1. `None`
2. `Fade`
3. `Circular`
4. `Moving Circles`
5. `Hypnotizing Grid`
6. `Wave`
7. `Grain`
8. `Scratches`
9. `Blink`
10. `Full Color Spectrum`

Then set whatever they want next (often **`Fade`** plus their width, duration **1–5**, and hex colors).
