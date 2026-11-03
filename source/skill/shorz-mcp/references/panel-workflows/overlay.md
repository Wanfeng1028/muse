# Overlay workflow (`set_overlay_settings`)

Cross-project overlay FX toggle and selected effect names. Project targeting and shared rules: **`README.md` in this folder**.

## What overlays look like

When **`overlayFx`** is on, Shorz composites **full-frame overlay video** (glitch, noise, sparkles, user-imported clips, etc.) on top of the **main video preview** and into **exported/generated video** for that project. The user picks one or more effects by **name** in the Overlay panel; the renderer applies overlays to the composed output.

## Tool contract

**Primary:** `set_overlay_settings`

**Related:** `get_overlay_effects`, `import_overlay_effects`, `delete_overlay_effect` (user-imported overlays only; bundled defaults cannot be deleted—see **`../../SKILL.md`**).

**Arguments:**

- `projectPath` — absolute path to the project directory.
- `settings` — only the keys below; nest under `settings`, not at the root of the tool call.

**Supported keys in `settings`:**

| Key | Type | Notes |
|-----|------|--------|
| `overlayFx` | boolean | On/off; same as the Overlay panel toggle. Persists as `VIDEO_OVERLAY_EFFECT.video_overlay_effect_active` (`"True"` / `"False"` strings in `settings.json`). |
| `overlaySelectedEffects` | string[] | Effect **names** from `get_overlay_effects`; matching is **case-insensitive**; stored names are **canonical** from that list. Persists as `VIDEO_OVERLAY_EFFECT.video_overlay_effect_name` (comma-separated). Empty array clears the selection. |

There is **no** MCP key for overlay scope or duration; do not invent extra `settings` fields (schema is strict—unknown keys are rejected).

**Persistence (`read_project_settings` / `settings.json`):** section **`VIDEO_OVERLAY_EFFECT`**

- `video_overlay_effect_active` — toggle
- `video_overlay_effect_name` — comma-separated effect names (may be empty)

Legacy projects may still carry a removed `video_overlay_effect_options` key on disk until the next overlay write; **`set_overlay_settings`** drops that field when it updates this section.

**`import_overlay_effects`**

- Optional `overridePaths`: array of absolute paths to supported video files (e.g. `.mp4`). **Headless / MCP:** pass paths here so the app does not open a file picker.
- If `overridePaths` is omitted or empty after filtering, the **desktop app** opens an **Import Overlay** dialog (interactive only).

## Instruction handling rules

- **Turn overlays on or off only** — send `overlayFx` only. Note that `overlayFx: true` with an empty selection renders **no** overlay; the toggle alone never picks one for the user.
- **Apply specific effects** — call `get_overlay_effects`, map names, then patch `overlaySelectedEffects` **together with `overlayFx: true`**. MCP does not couple the two keys: the Overlay panel auto-enables when the user clicks an effect (and auto-disables when they deselect it), but a patch that only sets names leaves `overlayFx` as it was, so nothing renders.
- **Clear all selected effects** — patch `overlaySelectedEffects: []` (add `overlayFx: false` to match the panel's own deselect behavior).
- **Remove one effect** — derive the list from context, patch with that name omitted (minimal change).
- **Add new overlay files** — `import_overlay_effects` with `overridePaths` when non-interactive, then `set_overlay_settings` to select by returned `name`.
- **Remove a user import** — `delete_overlay_effect` with `nameOrFileName` (base name or `.mp4`); confirm intent per **`../../SKILL.md`** when the user did not ask to delete.

## Execution sequence

1. Resolve the target project per **`README.md` in this folder** (`get_current_open_project`; never auto-pick when ambiguous).
2. Call `get_overlay_effects` before validating or setting `overlaySelectedEffects`.
3. Call `set_overlay_settings` with `projectPath` and a minimal `settings` patch.
4. Report `success`, `error`, and `applied`. To confirm disk state, use **`read_project_settings`** and inspect **`VIDEO_OVERLAY_EFFECT`**.
5. **Create Video** — only when the user wants a rendered video, per **`README.md`**: e.g. `generate_video`, poll **`get_video_generation_status`**. Use **`fetch_app_events`** only for logs on request or when troubleshooting (**`../../SKILL.md`**).

## Common failures

- **Unknown effect names** — `success: false` with message and `validOverlayNames`; fix spelling using `get_overlay_effects` and retry.
- **Unknown keys in `settings`** — MCP rejects (strict schema); only `overlayFx` and `overlaySelectedEffects`.
- **Wrong shape** — `projectPath` and `settings` must be top-level tool arguments; `settings` must be an object.
- **Invalid `projectPath`** — empty/whitespace, not under the Shorz Projects directory, or missing `config/settings.json`: `success: false` with `code` such as `INVALID_PROJECT_PATH` or `ENOENT` (MCP validates before read/write).
- **Duplicate effect names in one patch** — MCP and the app **dedupe** case-insensitively; persisted order keeps the first occurrence.
- **`import_overlay_effects` without paths in automation** — may block on a native file dialog; always pass `overridePaths` for headless runs.
