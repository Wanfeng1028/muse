# Audio workflow (`set_audio_settings`)

Cross-project audio mix, automatic music/SFX, B-roll and transition sounds, dubbing, reverb and music fades via **`set_audio_settings`**. Project targeting and shared rules: **`README.md` in this folder**.

## What the audio panel looks like

In the **Audio** sidebar, the user sees **channel faders** for the main program track, overlay/narration, sound effects, and music, plus **toggles** for AI music, general SFX, sounds tied to images/transitions/emojis/zoom, noise reduction, and **dubbing**. **Reverb** is a single preset selector. The panel's **MUSIC** section holds only the **Auto-music** toggle — there are no fade or per-track controls in the UI, so `musicFadeIn` / `musicFadeOut` are set through this tool (or per render in the PromptBar). The same values persist on disk under **`AUDIO_SETTINGS`** and apply to **preview and exported video** for that project.

## Two different music sources (do not conflate)

| | **Auto-music** (`autoMusic`) | **Imported music** (Your Library → MUSIC) |
|---|---|---|
| What it is | One instrumental track generated per render by ElevenLabs from the transcript | The user's own files in `ASSET_PATHS.music_asset_paths` |
| How to enable | `set_audio_settings` → `autoMusic: true` (**paid**, fails at zero balance) | `import_frontend_assets` with `assetType: "music"` (**free**) — see `your-library-assets.md` |
| Track count | Exactly one, generated | **Unlimited** — several tracks play **back to back** (a playlist, not layered) in lane order |
| Covering a long video | **Always full coverage** — generation is capped at 5 minutes, so on a longer video the track **loops**, with a **5s equal-power crossfade** at each seam, cut at the end | **Plays through once**, in the arranged order and length — match the imported total to the video length for full coverage |
| Prompt control | Mood/genre wording only (steers the generation prompt) | Full arrangement: play order, a section of one named track, skipping into the combined music, placement on the timeline, volume, fades, mix-vs-replace — see `../project-workflows/auto-edit.md` → *Imported music* |
| Beat sync | **Not possible** — the track does not exist when the edit is planned | Supported in multi-asset `auto-edit` when the brief asks |
| Volume | `musicVolume` applies to whichever source is playing | same |

Both are mixed by the same renderer stage, so **`musicVolume` governs both**. Imported music is applied in every project type, not just `auto-edit` — except **`music-video`**, whose song is the only audio (no MUSIC lane, no auto-music).

**Music fades: setting = default, prompt = override.** `musicFadeIn` / `musicFadeOut` are the project's standing fade, applied to whichever music is playing (auto-music or imported). A fade in the brief (e.g. "fade the music out over the final 3 seconds") replaces them for that render — see the `musicFadeIn` / `musicFadeOut` row below.

## Tool contract

**Primary:** `set_audio_settings`

**Arguments:**

- `projectPath` — absolute path to the project directory.
- `settings` — only the keys below; do not add other keys; nest under `settings`, not at the root of the tool call.

**Supported keys in `settings`:**

| Key | Type | Notes |
|-----|------|--------|
| `autoMusic`, `autoSoundFX`, `imageSounds`, `transitionSounds`, `emojiSounds`, `zoomSounds`, `removeNoise`, `dubbing` | boolean | Toggles; must be real booleans (not `0`/`1`). |
| `dubbingLanguage` | string | **Must be** one of the accepted values, **verbatim and case-sensitive** (wrong casing fails). Dubbing runs on **ElevenLabs Dubbing v2**: 108 target languages (94 base + 14 regional dialects). Accepted: **BCP-47 codes** (`de`, `es`, `pt-BR`, `es-MX`, …), **display names** (`German`, `Spanish (Mexico)`, …), and the 13 **legacy flag ids** from the v1 era that are not already codes (`gb`, `cn`, `in-tamil`, … — listed in full below) — **prefer codes**; they match the Audio panel. Display names and legacy ids are normalized to codes when saving. ⚠ `my` is the code for **Burmese** (the legacy flag id `my` no longer means Malay — use `ms` or `Malay`). |
| `audioReverbEffect` | string | **Exactly** one of the reverb preset strings below. |
| `originalVolume`, `overlayVideoVolume`, `narratorVolume`, `soundFXVolume`, `musicVolume` | number | **Integers only**, each **0–100** inclusive. Non-integers or out-of-range values are **rejected** (not clamped). `musicVolume` applies to both auto-music and imported music (the brief can override it per render). |
| `musicFadeIn`, `musicFadeOut` | number | **Finite** numbers, each **0–30** inclusive (seconds); `0` = no fade. Out-of-range or non-finite values are **rejected**. Volume fade at the start / end of the music segment, applied to **auto-music and imported music alike**. The renderer reads them for every render of the project (`get_video_music_fadein` / `get_video_music_fadeout`), unless the brief asks for a different fade — a PromptBar fade wins for that render only. The UI has no fade controls, so this tool and the PromptBar are the only ways to set one. |

**Persistence check (`read_project_settings`):** values live under **`AUDIO_SETTINGS`**, for example:

- Volumes → `audio_original_volume`, `audio_overlay_video_volume`, `audio_narrator_volume`, `audio_soundfx_volume`, `audio_music_volume` (stringified integers).
- Toggles → `audio_auto_music`, `audio_general_soundfx`, `audio_broll_soundfx`, `audio_transition_soundfx`, `audio_emoji_soundfx`, `audio_zoom_soundfx`, `audio_remove_noise`, `audio_dubbing_active` (`True` / `False` strings).
- `audio_reverb_effect`, `audio_dubbing_language`.
- Music fades → `audio_music_fadein`, `audio_music_fadeout` (stringified seconds, `0` = no fade).

**Allowed `dubbingLanguage` codes (copy verbatim; every code's display name — e.g. `German`, `Spanish (Mexico)` — is also accepted, as are the 13 legacy flag ids):**

`af`, `ak`, `sq`, `am`, `ar`, `ar-EG`, `hy`, `as`, `az`, `eu`, `be`, `bs`, `bg`, `my`, `yue`, `ca`, `ceb`, `zh`, `zh-TW`, `hr`, `cs`, `da`, `dgo`, `nl`, `en`, `en-AU`, `en-CA`, `en-GB`, `en-US`, `et`, `fil`, `fi`, `fr`, `fr-CA`, `fr-FR`, `gl`, `ka`, `de`, `el`, `gu`, `ha`, `he`, `hi`, `hu`, `is`, `id`, `it`, `ja`, `jv`, `kn`, `kk`, `ki`, `rw`, `rn`, `ko`, `ky`, `lv`, `lt`, `lg`, `mk`, `ms`, `ml`, `cmn`, `mr`, `mn`, `ne`, `no`, `fa`, `pl`, `pt`, `pt-BR`, `pt-PT`, `pa`, `ro`, `ru`, `nso`, `st`, `sd`, `sk`, `sl`, `es`, `es-AR`, `es-CL`, `es-ES`, `es-MX`, `su`, `sw`, `ss`, `sv`, `tg`, `ta`, `te`, `th`, `bo`, `ts`, `tn`, `tr`, `uk`, `ur`, `ug`, `uz`, `ve`, `vi`, `war`, `cy`, `wo`, `yo`, `zu`

Legacy flag ids (still accepted, normalized on save): `gb`→`en`, `sa`→`ar`, `cn`→`zh`, `cz`→`cs`, `dk`→`da`, `gr`→`el`, `in`→`hi`, `jp`→`ja`, `kr`→`ko`, `ph`→`fil`, `se`→`sv`, `in-tamil`→`ta`, `ua`→`uk` (ids like `de`, `es`, `id` already are codes).

**Allowed `audioReverbEffect` values (copy verbatim):**

`None`, `Studio Clean (Dry)`, `Podcast Warm`, `Small Room`, `Casual Home`, `Office / Conference Room`, `Classroom / Lecture Hall`, `Plate Vocal`, `Radio Announcer`, `Telephone / Lo-Fi`

## Instruction handling rules

- **Mute / boost one channel** — patch only that volume key.
- **"Add my own music"** — that is an **import**, not a setting: `import_frontend_assets` with `assetType: "music"` (any number of files; they play back to back in lane order). Leave `autoMusic` **off** for that — it generates a separate AI track and costs credits.
- **Music timing, order, sections, mix-vs-replace** — these are **not** settings: put them in the PromptBar via `set_user_instructions` (see `../project-workflows/auto-edit.md` → *Imported music*). Only `musicVolume` and the two fade keys have real settings keys.
- **Music fades** — patch `musicFadeIn` / `musicFadeOut` when every render of this project should fade its music the same way. For a one-off (“fade the music out at the end of *this* video”), put it in the PromptBar instead: the derived music plan overrides the stored default for that render.
- **Change dubbing** — patch `dubbing` and `dubbingLanguage` together when relevant.
- **Sound design emphasis** — patch toggles and volume keys together; avoid unrelated panels.
- **B-roll-related sounds** — `imageSounds` lives here; `emojiSounds` can be discussed in Audio or Emoji context depending on user wording — prefer the panel whose intent matches.
- **Configure only** — patch and stop before Create Video.
- **Zero-balance user (free tier)** — a free `auto-edit` / `clipping` run zero-rates only the main-AI chat and transcription, so the paid toggles here fail server-side mid-render: leave **`dubbing`**, **`autoMusic`** and **`removeNoise`** off. **`autoSoundFX`** is fine — it places sound files bundled with the app, so it costs nothing at any balance. Volumes, reverb, fades and the appearance-sound toggles are free too, and so is **importing the user's own music** (any number of tracks) — that is the zero-cost way to give a free-tier render a soundtrack. See **`../../SKILL.md`** → *Keys and auth dependencies*.

## Execution sequence

1. Resolve the target project per **`README.md` in this folder** (`get_current_open_project`, then `list_projects` if needed; never auto-pick when multiple match).
2. Call `set_audio_settings` with `projectPath` and a minimal `settings` patch (or a full patch if the user asked to set every control).
3. Return **`success`**, **`error`** (if any), and **`applied`** when present. Use **`read_project_settings`** → **`AUDIO_SETTINGS`** to confirm what was stored.
4. **Create Video** — only when the user wants a rendered video, per **`README.md`** and **`../../SKILL.md`** (poll **`get_video_generation_status`**; use **`fetch_app_events`** only when troubleshooting or when the user wants logs).

## Common failures

- **Unknown keys** — MCP rejects with `unrecognized_keys`; remove extra fields from `settings`.
- **Non-boolean toggles** — rejected at validation (`expected boolean`).
- **Volume keys** — must be **integers** in **0–100**; fractional or out-of-range values are **rejected** (not clamped).
- **Fade keys** — must be **finite** and in **0–30**; otherwise rejected. A stored fade is silently outranked by a fade in the brief, so if a user reports “my 5s fade became 2s”, check the PromptBar text before the settings.
- **Invalid `dubbingLanguage` or `audioReverbEffect`** — use a string from the lists above **with exact spelling and casing** (e.g. `de`, `pt-BR` and `German` are valid; `DE`, `pt-br` and `german` are not). Errors include a hint; retry with a listed value.
- **Wrong shape** — `projectPath` and `settings` must be top-level tool arguments.
- **Music video projects** — auto-music, noise removal, dubbing and reverb are skipped at render time (the song is never re-mixed or processed); the toggles save but do nothing there. See `../project-workflows/music-video.md`.
## Audio Visualization (`set_audio_visualization_settings`)

The Audio panel also has an **AUDIO VISUALIZATION** section: an audio-reactive overlay (bars, waveform, blob, ring, retro LED panel, vectorscope, …) rendered **on top of b-roll, subtitles, titles and emojis** (under the border) in the exported video, driven by the video's final speech + music mix. The user picks one style from preview cards, recolors it (white by default), and drags/resizes it in the editor preview. Costs no credits (local render effect). It is skipped at render time when the video has no audio track.

**Tool:** `set_audio_visualization_settings` — same `projectPath` + `settings` patch shape as `set_audio_settings`.

**Supported keys in `settings`:**

| Key | Type | Notes |
|-----|------|--------|
| `audioVizActive` | boolean | Section toggle. |
| `audioVizStyle` | string | **Exactly** one of: `spectrum_bars`, `mirror_bars`, `waveform`, `wave_line`, `circular_bars`, `voice_blob`, `pulse_ring`, `bouncing_dots`, `led_matrix`, `vectorscope`. Empty string `""` clears the selection (active + no style renders nothing). Invalid ids are **rejected** with the valid list. |
| `audioVizColor` | string | `#RRGGBB` (default `#FFFFFF`). **Per style**: applies to the style set in the same call, else to the currently selected style; **errors** when no style is selected. Invalid hex is **rejected**. |
| `audioVizPositionX` | number | Box **center X** as % of frame width, **clamped** to 0–100. |
| `audioVizPositionY` | number | Box **top Y** as % of frame height, **clamped** to 0–100. |
| `audioVizWidthPercent` | number | Box width as % of frame width, **clamped** to 10–100. Height follows the style's aspect ratio (3:1 bars/dots/LED, 4:1 waveforms, 1:1 circular/blob/ring/vectorscope). |

**Persistence check (`read_project_settings`):** values live under **`AUDIO_VISUALIZATION`** as strings — `audio_viz_active` (`True`/`False`), `audio_viz_style`, `audio_viz_colors` (JSON map styleId → hex; per-style colors), `audio_viz_color` (resolved color of the selected style — what the renderer reads), `audio_viz_position_x`, `audio_viz_position_y`, `audio_viz_width_percent`.

**Example** — bottom-centered white spectrum bars at half frame width:

```json
{ "projectPath": "<project>", "settings": { "audioVizActive": true, "audioVizStyle": "spectrum_bars", "audioVizPositionX": 50, "audioVizPositionY": 75, "audioVizWidthPercent": 50 } }
```
