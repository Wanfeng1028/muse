# Settings workflow — General Video (`set_general_video_settings`)

Cross-project controls for framing, tuning, zoom, and related effects via `set_general_video_settings`. Convention and project targeting: `README.md`.

## Tool contract

**Primary:** `set_general_video_settings`

Supported keys:

- `aspectRatio`: `16:9` | `1:1` | `9:16`
- `faceTracking`: boolean
- `autoZoom`: boolean
- `freezeFrameEffect`: boolean
- `freezeFrameZoomSpeed`: number (`0..10`)
- `grayscaleEffect`: boolean
- `brightness`, `contrast`, `saturation`: number (`0..2`)
- `videoSpeed`: number (`0.1..5`)
- `zoomCount`: integer (`1..30`)
- `zoomStrength`: number (`1..2`)
- `zoomSpeed`: number (`0.5..3`)
- `zoomType`: `Intelligent Auto Zoom` | `Zoom on Music Beat` (exact strings).
- `zoomInEffects`, `zoomOutEffects`: non-empty string arrays (multi-select pools). Each zoom segment picks one effect from the matching pool (same sequencing idea as B-roll `brollTransitionAnimations`). Select multiple ids for variety.
- Legacy `zoomInEffect` / `zoomOutEffect`: single enum each (deprecated; still accepted; prefer arrays).

### Allowed Auto Zoom overlay effect ids

`None`, `Blur`, `Radial Blur`, `Chromatic`, `Vignette`, `Color Boost`, `Motion Lines`, `Edge Glow`, `Time Ripple`, `Flash`, `Shockwave`, `Matrix Rain`, `Glitch`, `Pixelate`, `Retro VHS`, `Film Grain`

Arrays must be **non-empty**. Use `["None"]` alone for no overlay FX on that ramp.

**Persisted keys (for `read_project_settings`):** `VIDEO_ZOOM.video_zoomin_effect_animations` / `video_zoomout_effect_animations` (JSON string arrays); legacy `video_zoomin_effect_type` / `video_zoomout_effect_type` mirror `pool[0]`.
- **`zoomSounds`** is **not** in this tool — it lives on **`set_audio_settings`** (`zoomSounds` → `AUDIO_SETTINGS.audio_zoom_soundfx`) even though the **Settings** UI groups it under Auto Zoom.

**Zoom type vs. pipeline:** With **`zoomType` = `Zoom on Music Beat`**, zoom in/out effects and max count are **not used** for that mode but still **persist**; they apply when switching back to **Intelligent Auto Zoom**. The Settings panel shows those controls **disabled** in Music Beat mode so stored values (including MCP writes) stay visible.

**What `Zoom on Music Beat` actually listens to:** the audio of the video **at that point in the render**, not a music file on disk. Music is mixed in *before* this effect runs (enforced ordering in `render_video_main.py`), so with a track imported to Your Library → MUSIC the frame really does pulse to that track — and it reacts to speech and sound effects in the mix too. Consequences worth telling the user:

- **Imported music + `Zoom on Music Beat` works** and is the reliable way to get a frame that pulses to a specific song. Auto-music works as well (it is also mixed in before this stage).
- The clip must have **some** audio — the effect is skipped on a silent video (`Video has no audio track`).
- This is a **different mechanism** from beat-synced *cutting* in `auto-edit` (which places cuts using analyzed beat timestamps at plan time, multi-asset only, and needs the brief to ask). The two can be combined: the planner cuts on beats, then the frame pulses on them.
- Because it listens to the finished mix, prompt-driven music choices (order, sections, placement, volume) change what it pulses to — e.g. music placed only over the last 20 seconds means no music-driven pulsing before that.

## Instruction handling rules

- **Visual tuning only** — patch only color/speed keys.
- **Output framing** — patch `aspectRatio` only.
- **Auto-zoom behavior** — patch `autoZoom` and related zoom keys together.
- **Disable an effect** — set the corresponding toggle false; do not reset unrelated values.
- **Configure only** — patch and stop before Create Video.

## Execution sequence

1. Resolve or open the project and obtain `projectPath` (see `README.md`).
2. Call `set_general_video_settings` with a minimal patch.
3. Return applied keys and the tool response.
4. Trigger Create Video only if the user explicitly requests a render (PromptBar + `trigger_create_video` / `generate_video`, then **`get_video_generation_status`**; **`fetch_app_events`** only on request or when debugging; see **Event stream** in `../../SKILL.md`).

## Common failures

- **brightness**, **contrast**, **saturation** (0–2): out-of-range values are **rejected**, not clamped.
- Out-of-range numeric values — **rejected** at MCP validation for zoom keys, freeze-frame, color tuning, and `videoSpeed` (`0.1..5`); fix the value using the tool error text.
- Invalid enum names — use values accepted by the MCP schema or the tool error message.
- **Music video projects** skip `freezeFrameEffect` and `grayscaleEffect` at render time — both hold or slow part of the video, which would stretch the song and pull the cuts off its beat; the toggles save but do nothing there. `Zoom on Music Beat` pulses to the song itself.
