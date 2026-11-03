---
name: jagz999-explainer-video
description: >-
  Create animated, camera-zooming product explainer videos (SVG/HTML style) with
  voiceover, background music, and synced sound effects. Use when the user wants to
  turn product screenshots or a screen-recording/demo into an explainer video, an
  animated walkthrough, a narrated product demo, or a launch/marketing video. The
  skill interactively interviews the user about design (colors, fonts, scenes, tone),
  then about the TTS provider (and API key), builds a self-contained animated HTML
  explainer, renders it to a sharp MP4, and produces separate music & SFX stems.
  Triggers: "make an explainer video", "animate my product screenshots", "turn this
  demo into a video", "create a narrated walkthrough", "product launch video".
---

# Explainer Video

Build a polished, animated **product explainer video** from screenshots and/or a screen recording. The signature look: a dark, modern SVG/HTML UI mockup that the "camera" **zooms and pans** across, with **3D lift** effects on elements as they're named, **ciphertext→plaintext morph** reveals, a typed-prompt → click → result flow, plus **voiceover, background music, and time-synced sound effects**.

This skill is **interview-driven**: at every stage you ASK the user with `AskUserQuestion` and wait for answers before building. Never assume design, branding, scenes, or the TTS provider — ask. The user explicitly wants to be asked about colors, fonts, layout, scene order, voice, etc.

## Golden rules
- **Gather ALL input files into one working folder BEFORE writing any HTML.** Confirm the folder and its contents with the user first.
- **Ask, don't assume** — design, scenes, voice provider, API keys, resolution. One decision per `AskUserQuestion` (or grouped), wait, then proceed.
- The example in `assets/example-explainer.html` is the proven **engine + reference**. Copy it and adapt the branding/scenes/content/cues to the user's product. Keep the engine (camera, lifts, morph, chat flow, cue runner, audio-master clock) intact.
- Verify visually in the browser preview at each major step (use the preview tools / a local static server). Show the user screenshots; iterate.
- Audio tracks (music, SFX) are delivered as **separate files** unless the user asks to mux them in.

## Workflow

### 1 — Intake & working folder
1. Ask the user for: the product/app name, what it does, and the assets they have (screenshots, a screen recording, a logo). 
2. Create a working folder (e.g. `<product>-explainer/`) and have the user place ALL assets there. If they gave a video, extract reference frames with ffmpeg (`fps=1/3`) and **read them** to understand the UI/flow. If they gave a screen recording of the real interactions, study it to mirror the real animations.
3. Confirm you understand the platform: list the screens/primitives/sections you'll cover. Get the user's OK on scope and scene order.

### 2 — Design interview (ask each, via AskUserQuestion)
Ask, in this order, confirming as you go:
- **Visual style**: dark / light; flat / glassy / neumorphic; how close to the real UI vs stylized.
- **Color palette**: primary accent, background, success/alert colors (offer 3–4 tasteful presets + "match my brand" using the logo).
- **Font**: offer pairings (e.g. Montserrat, Inter, Geist, Space Grotesk). Default Montserrat.
- **Logo**: ask for the exact logo file(s) and USE them as-is (don't recreate a logo). Light variant for dark bg.
- **Scenes**: confirm the ordered scene list and which element each scene zooms to / lifts in 3D. Confirm intro & outro title cards + tagline wording.
- **Animation taste**: confirm the signature effects to include (camera establish→zoom, 3D lift on the spoken word, in-place ciphertext→plaintext morph, typed-prompt→Send→result, dropdown 3D opens, synthetic cursor). Let them toggle any off.

### 3 — Build the HTML explainer
1. Copy `assets/example-explainer.html` into the working folder as `<product>-explainer.html`.
2. Replace branding (logo `<img>`, wordmark, colors via the CSS `:root` variables, font `<link>`), the sidebar/top-bar chrome, and the `SCENES` array + content panels to match the user's product and the design answers.
3. Keep the **engine** functions (`renderScene`, `applyCam`, `animFlow`, `morphHTML`, `applyCues`, cursor, clock). See `reference/ARCHITECTURE.md` for how scenes, camera cams (`cx,cy,s`), cues (3D lifts on spoken words), and the audio-master clock work.
4. For "lift on the spoken word", cue times come from the TTS word timestamps (step 5). Until audio exists, use estimated times; refine after generating VO.
5. Serve locally (`python3 -m http.server`) and verify each scene in the browser preview. Show screenshots, iterate with the user.

### 4 — Choose the voice/TTS provider (ASK)
Ask with `AskUserQuestion`: **"Which voice/TTS provider?"**
- **ElevenLabs** (recommended, fully supported here): highest quality + **word-level timestamps** used to sync the 3D lifts. If chosen, ask for the API key (store it in `.env` as `ELEVENLABS_API_KEY`, chmod 600; never print it back). See `reference/ELEVENLABS.md` and `scripts/elevenlabs.py`.
- **macOS `say`** (free, local, no key): decent for drafts. `say -v <voice> -o out.aiff "..."` then convert with ffmpeg. No word timestamps → use estimated cue times.
- **Bring-your-own / other** (OpenAI, Azure, Google, etc.): generate per-scene script + scene durations and hand the user the script so they can synthesize and drop the clips back in; you wire them up.
- **No voiceover**: skip audio; deliver the silent animated MP4.

Also ask: preferred **voice** (offer a few), **music mood** (ambient/cinematic/corporate/dark), and whether they want a **synced SFX** track.

### 5 — Generate audio
Using `scripts/elevenlabs.py` (or the chosen provider):
- **Voiceover**: write a per-scene `script.json` (`[{id,text}]`), generate one clip per scene **with timestamps** (`/v1/text-to-speech/{voice}/with-timestamps`), extract keyword cue times, concatenate into one gap-free `vo_full.mp3`. Set each scene's `dur` = its clip length, embed `<audio>` as the master clock, and refine the `CUES` times from the real timestamps.
- **Music** (separate file): `/v1/music`, `music_length_ms` = total video length, mood per the user's answer.
- **SFX** (separate file): generate a small palette with `/v1/sound-generation` (whoosh, lift, open, click, type, shimmer, chip, success, logo — min duration **0.5s**), then `scripts/build_sfx.py` places them at the exact event times (scene starts, cue lifts, dropdown opens, typed-prompt/click/decrypt/success). **Always verify each generated clip isn't silent** (ElevenLabs occasionally returns near-silence) — `ffmpeg -af volumedetect`; regenerate if `max < -30 dB`.

### 6 — Render to MP4 (ASK resolution)
Ask the **resolution** (1920×1080 or 2560×1440 / 2K). Then:
- `scripts/render.js` (puppeteer-core + system Chrome) renders the playing HTML at native resolution via CDP screencast, **tagging each frame with the player's logical time** (`window.__log`) so video stays perfectly in sync with the audio. Assemble frames with ffmpeg (per-frame durations from logical-time diffs) and mux the voiceover.
- **Do NOT** capture-then-upscale (causes blur) and **do NOT** timestamp frames by wall-clock (causes ~2s drift). See `reference/ARCHITECTURE.md` → "Rendering & sync".
- Deliver: the MP4 (with voiceover) + separate `music.mp3` and `sfx.mp3` stems. Verify sync by extracting frames at scene boundaries (`ffmpeg -ss <t> -i out.mp4 ...` with `-ss` AFTER `-i` for frame accuracy) and confirming the visual matches the spoken word.

### 7 — Wrap up
Summarize deliverables and offer tweaks (voice, pacing, colors, a specific effect, mux a combined mix). Clean up large temp frame folders (`frames/`) — they can be hundreds of MB.

## Files in this skill
- `assets/example-explainer.html` — the proven engine + a full worked example (Mirror Security). Start here; adapt it.
- `assets/example-vo-script.json` — example narration-script format.
- `scripts/render.js` — native-resolution, logical-time-synced renderer (Chrome screencast → frames + timing).
- `scripts/elevenlabs.py` — ElevenLabs helpers: TTS-with-timestamps, music, SFX palette.
- `scripts/build_sfx.py` — places SFX clips on a timeline → one synced SFX track.
- `scripts/analyze_motion.py` — detect zoom/transition timestamps in a rendered (or user-trimmed) MP4 via frame-difference. Use when scene-detect fails on crossfades.
- `scripts/build_events.py` — turn detected motion into `music_accents.json` + `sfx_events.json` (drops/whooshes synced to the real video).
- `scripts/seed_capture_profile.sh` — seed a clean Chrome profile (`.capdir`) with the user's auth, for reliable headless capture.
- `scripts/capture.js` — puppeteer capture toolkit (clean profile, pipe transport, real clicks, keyboard typing, patient login) → crisp 2x screenshots of the real product.
- `reference/CAPTURE_REAL_DASHBOARD.md` — the real-dashboard capture workflow (when you want to show the actual product, not a recreation).
- `reference/ARCHITECTURE.md` — scene/camera/cue/morph engine, render+sync pipeline, 3D card-rise & button-press on real screenshots, and the two production modes (stylized vs real screenshots).
- `reference/AUDIO_SYNC.md` — how to sync music drops & SFX, incl. the motion-difference method for videos the user has trimmed/edited.
- `reference/PITFALLS.md` — hard-won gotchas (pkill self-kill, background-node logging, puppeteer real-profile timeout, custom-combobox clicks, scene-detect-fails-on-crossfade, music length cap).
- `reference/ELEVENLABS.md` — endpoints, models, voices, gotchas.
