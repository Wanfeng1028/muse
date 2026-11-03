---
name: generated-media-sourcing
version: 1.0.0
description: Generate or plan media assets for beat-synced edits when real footage is missing or the user asks for generated visuals - AI video (Gemini/Veo/Flow), AI images, or procedural audio-reactive GPU renders (tunnels, portals, kaleidoscopes, starbursts, mandalas, title pieces via Python+moderngl GLSL). Use with beat-synced-montage-builder when a montage needs generated clips, stills, or procedural audio-reactive elements instead of, or alongside, sourced footage.
---

# Generated Media Sourcing

## Purpose

Use this skill when a beat-synced edit needs generated media instead of only found/source footage. Keep the same quality bar as the Smash-style workflow: generated assets must support the cut markers, phrase turns, subject changes, and visual escalation instead of becoming generic filler.

## Routing

- For generated video, use an installed Gemini/Veo skill when available, such as `$gemini-video-generation` or Jake's `$gomez-cloud-veo-generation`.
- For Google Flow browser generation, use the Gomez/Flow route when the user asks for Flow, browser credits, Google Omni, Veo in Chrome, or the visible Flow UI.
- For generated still images, plates, mockups, cutouts, textures, or reference frames, use Codex's built-in `$imagegen` skill/tool when available.
- If neither video nor image generation tools are available, create a prompt manifest and edit plan, then tell the user what generation step remains blocked.

## When To Generate

Generate media when:

- The user explicitly asks for generated video or images.
- Real footage is unavailable, too weak, too repetitive, or blocked by licensing/source access.
- A section needs a specific impossible-to-source visual, transition plate, dream image, title-free abstract, product-safe cutaway, or beat-hit accent.
- The edit is exploratory and generated placeholders will help test timing before final sourced footage is found.

Prefer real footage when:

- The final needs authentic events, people, gameplay, product evidence, BTS, concert crowd reactions, or documentary trust.
- The generated media would reduce specificity or make the edit feel stock.
- A real source can be found quickly and legally.

## Workflow

1. Start from the song analysis and montage plan. Do not generate assets before knowing the target window, aspect ratio, energy ramp, and marker roles.
2. Decide asset type per cue:
   - `generated_video`: short motion clips for phrase turns, transitions, atmosphere, or impossible scenes.
   - `generated_still`: image plates to animate with pans, zooms, parallax, overlays, or quick flashes.
   - `source_footage`: real footage remains preferred for grounded action and final proof cuts.
3. Create a generation manifest with one row/object per requested asset:
   - cue id
   - marker time or time range
   - asset type
   - aspect ratio
   - prompt
   - avoid list
   - intended use in the timeline
   - output path
4. Ask before spending paid/API video credits unless the user clearly requested actual generation.
5. Save generated project assets under ignored local folders such as `media/generated/`, `work/generated-media/`, or `outputs/generated-media/`. Do not commit generated MP4s, raw images, API keys, downloads, or private references.
6. Verify generated clips with `ffprobe` and generated images by opening or inspecting them before using them in a timeline.
7. Add accepted generated assets to the montage source manifest with `source_kind=generated_video` or `source_kind=generated_still`.
8. Render the clean edit first. Treat generated assets as source material, not a reason to skip timeline CSVs, contact sheets, briefs, or `$edit-delivery-qa`.

## Procedural Audio-Reactive Rendering (preferred for abstract visuals)

For abstract/atmospheric elements — tunnels, portals, kaleidoscope mandalas, starburst fields, event horizons, title pieces — prefer a procedural GPU render over AI generation: it is deterministic, watermark-free, fully owned, and can be driven by the song's own onset envelope so every pulse lands on the music by construction.

Skeleton: Python + moderngl standalone context, one fullscreen-triangle `#version 330` fragment shader, per-frame uniforms (`uTime`, `uPulse` from a librosa onset envelope with 95th-percentile normalization and `exp(-1/(fps*0.22))` peak-hold decay, integrated speed/roll accumulators that surge on hits), frames read from the FBO and piped raw RGB straight into `ffmpeg -f rawvideo -pix_fmt rgb24 -vf vflip -c:v libx264 -crf 18 -pix_fmt yuv420p`. Standard CLI: `--audio --start --dur --out --fps 30 --w 1080 --h 1920`, plus a `--still --t` mode for art-direction checks before committing to a full render.

Proven audio mappings: onsets → punch-zoom / white-hot flash / rotation kicks; bass → core bloom / inner-rim heat; integrated energy → travel speed. Keep bands as separate normalized signals.

**The art-direction law (learned twice): near-black base + emissive neon.** Dense procedural fields wash out pastel unless ~50% of the field is black moat, noise carves the light (`I = profile * pow(streak, 1.5+) * gradient`), and saturation is punched. If it reads flat, increase depth separation and darken the periphery before adding detail. Finish: Reinhard-ish tonemap `acc*1.35/(1+acc)`, saturation lift ~1.3, gamma 0.4545; add dithering for near-black gradients on hero pieces.

**Integration rule:** a procedural render must not be intercut as standalone segments (see the integrated-FX rule in `$beat-synced-montage-builder`). Composite it INTO shots — screen-blend into skies in RGB/`gbrp` (never YUV — magenta flood), feathered-disc alpha, reflections, edge-wrapped light bleed, corner-pinned screens — or fuse it in-shader by decoding the base cut into a texture the same fragment shader samples, passing the edit's cut times as uniforms so cuts land as warp punches. Always render on the exact window (`--start/--dur`) the edit uses.

## Video Generation Guidance

Use Gemini/Veo/Flow for generated video. Keep prompts direct, visual, and edit-aware:

```text
9:16 vertical video, 8 seconds, no readable text or logos.
Scene: <specific visual>.
Motion: <one clear action that can cut on beats>.
Camera: <simple camera move>.
Style: <visual style>.
Lighting/mood: <energy>.
Avoid: text, watermark, brand logos, extra characters, malformed hands/faces.
```

For beat-synced edits, request short clips with a clear beginning, middle, and usable impact moment. Avoid prompts that require exact choreography across many beats; generate several simple options instead.

If using Google Flow, select the visible Veo/Omni model that matches the user's cost/quality request. Download finished clips immediately and copy them into a project-local ignored media folder with stable lowercase names.

## Image Generation Guidance

Use Codex image generation for still plates, cutaways, reference frames, album/story visuals, or impossible scenes that can be animated locally. Prefer image plates when the edit only needs:

- a fast flash
- a match-cut frame
- a parallax background
- a symbolic insert
- a thumbnail/contact-sheet concept
- a promptable visual that video generation would overcomplicate

Prompt stills with the intended edit use:

```text
Asset type: beat-synced montage image plate
Primary request: <visual>
Format: 9:16 vertical or 16:9 landscape
Composition: clear subject, readable at social-feed size, room for crop-safe movement
Style/medium: <photo/illustration/3D/etc>
Constraints: no readable text, no logos, no watermark
```

When a project will consume the image, move/copy the selected output into the workspace. Do not leave referenced assets only in Codex's default generated-image cache.

## Quality Rules

- Generated assets must be tied to specific beats, phrases, or story moments.
- Avoid generic B-roll prompts like "cool abstract visuals" unless the section genuinely calls for abstraction.
- Make several narrow prompts instead of one broad prompt when a montage needs variety.
- Reject generated assets with bad text, broken faces/hands, visible watermarks, weak motion, mushy subject readability, or no obvious cut point.
- Mark generated placeholders clearly in manifests so they can be replaced with real footage later.

## Handoff To Montage Builder

After generation or planning, pass the accepted assets back to `$beat-synced-montage-builder` as normal sources. Include:

- asset paths
- cue ids and intended marker times
- source kind
- prompt used
- notes about best frames or best motion moments
- replacement priority: `final_ok`, `replace_if_real_source_found`, or `placeholder_only`
