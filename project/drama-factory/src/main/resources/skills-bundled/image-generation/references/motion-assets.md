# Images for motion

Sizes and overscan, light continuity, layers, cutouts, sharpness, text and logos, and image-to-video handoff.

Contents
1. Images made for motion
2. Image-to-video handoff (only as far as images feed it)

---

## Images made for motion

### 5.1 Size, aspect and overscan
- Generate at the delivery aspect. Use custom sizes (multiples of 16), not a crop of a square. For a 16:9 + 9:16
  campaign, generate subjects as cutouts and re-layout them; don't crop one master.
- Overscan rule: source pixels ≥ output pixels × the largest scale the camera reaches, plus the pan travel. Examples:
  - A 1080p push from 1.00 to 1.10 needs at least 2112 px of width at the end frame.
  - A 15% push plus a 5% pan needs about 1.2 × 1920 = 2304 px.
  - 2560x1440 (the largest non-experimental OpenAI size) covers pushes up to about 1.33 at 1080p. For 4K output, use Gemini 4K or upscale (below).
- Composition with margin: keep the subject inside the centre 70-80% and describe empty margin ("10% empty margin on
  every side, nothing cropped"). Ken Burns needs a little extra on the push side; parallax needs extra width on the
  background layer equal to its travel.

### 5.2 Light and camera continuity
- Fix one key-light direction for the whole film in the suffix ("soft key light from upper left") and keep the camera
  height per scene. Generated cutouts placed in one Remotion scene must agree on light direction and on scale: state
  heights relative to one another ("the boy's head reaches the mother's chest").
- For flat styles, avoid cast shadows in the image ("no drop shadows, no floor shadow") and add one consistent
  shadow in code. One skill asks for "subtle contact shadow"; for compositing, shadows in code are cleaner.

### 5.3 Layer separation (parallax, 2.5D)
- Best: generate each depth layer as its own image with the same suffix, camera height and light. The background plate
  is extra-wide and has no characters ("empty kitchen, no people"); the midground props and the characters are cutouts.
- Split later: cut the subject out of the full frame (BiRefNet), then fill the hole in the plate with a masked edit
  ("continue the wall and floor behind, nothing new"). Masks are approximate, so feather the seam and keep the
  fill under the subject's footprint.
- Seedream 5.0 pro layer decomposition gives a base image plus up to 16 alpha layers.

### 5.4 Cutouts: generate, matte, clean, verify
Pipeline that shipped:
1. Generate on "Plain flat solid pure white (#FFFFFF) background with nothing on it, no floor shadow."
2. `rembg` with the `birefnet-general` session (BiRefNet, MIT licence, fine for commercial use; BRIA RMBG-2.0 is CC BY-NC, so avoid it without a licence).
3. Remap alpha to kill faint fringe: `alpha = clip((a - 0.08) / 0.84, 0, 1)`.
4. Trim to the alpha bounding box with a 12 px margin.
5. Write a check image composited over saturated violet #8342C9 and review that.

Native-alpha path: on the 2.5 family, set `background=transparent`, use png/webp, and keep every backdrop word out of the prompt (prompt text overrides the parameter).
- Then check in code that the alpha channel exists and has fully transparent pixels. "A drawn checkerboard is not transparency".
- For subsequent edits, repeat "keep the transparent background".
- Native alpha preserves glass, ribbons and hair better than matting.

Fixes:
- White halo: decontaminate edge colour against the known white backdrop. For pixels with 0 < α < 1, use `C = (C_obs - (1-α)·255) / α`. Or erode alpha by 1 px and feather by 0.5-1 px.
- Holes inside the subject (white shirt, white sneakers on white!): pick a backdrop colour absent from the subject. Use a flat mid-grey or chroma green when the subject has white, and say so in the backdrop line. Then matte.
- Triangulation matting: generate on white, then edit the same image to a black backdrop, and solve alpha from the pair. It gives true semi-transparency, but only works if the edit is pixel-aligned [P, experimental].
- Thin details lost: switch to native alpha.

### 5.5 Sharpness, upscaling, delivery sizes
- Display rule: an image shown at W px wide should be at least W × max zoom. Remotion renders at 1920x1080 or 1080x1920; a
  1536x1024 cutout shown at half-frame is fine; full-bleed plates with camera moves need 2048+ px.
- Prefer generating larger: OpenAI up to 3840 (experimental above 2560x1440), Gemini 4K, Seedream 4K.
- Upscale options: Recraft crispUpscale $0.004, Ideogram upscale (Topaz), or local Real-ESRGAN (unverified).
- For flat vector or cut-paper looks, vectorizing (Recraft $0.01) gives infinite resolution for big zooms.
- Don't ship a 4K PNG for a 300 px sticker: downscale to 2× display size to keep render memory and bundle size sane.

### 5.6 Text, logos, UI
Never ask an image model for brand names, logos, UI, captions, prices or numbers ("EXAMPLE" became "EXAMPEL").
Ask for blank surfaces where text will go, then composite real type, the real logo file and real screenshots in
Remotion. Objects that attract lettering need explicit "no lettering" (storefront signs, book spines, keyboards,
phones).

## Image-to-video handoff (only as far as images feed it)

State of models (2026-10-06):
- **OpenAI Sora 2.** API shut down 2026-09-24.
- **Google Veo 3.1**:
  - 4/6/8 s at 24 fps, 16:9 or 9:16.
  - First+last frame and up to 3 reference images both require 8 s. 1080p and 4K only at 8 s.
  - Extend +7 s per call, up to 148 s at 720p.
  - About $0.05-0.60 per second depending on tier.
- **Gemini Omni Flash** (Google's default video model since 2026-08-27):
  - 3-10 s clips, first+last frame, subject references, extension to 40 s.
  - About $0.10/s at 720p.
- **Kling 3.0**: 3-15 s, start and end frames, up to 3 bound "elements", multi-shot up to 6 segments.
- **Seedance 2.x**: `@Image1` binding syntax. It may block realistic faces, while stylised characters pass.
- **Runway Gen-4.5**: 5/8/10 s, fixed sizes such as 1280x720.
- **LTX-2.5**: start and end images, 2-4 shots.
- **FLUX 3 Video**: `keyframes` takes 1 image (start), 2 (start+end) or timed waypoints, 5-20 s.

Keyframe prep:
1. Same model, suffix and cast refs as the stills. Make each keyframe an edit of one master so identity and palette lock.
2. Exact output aspect and at least the output resolution (1920x1080 for 1080p). Mismatches get cropped.
3. No text, logos or captions in the frame: they warp.
4. A neutral "about to move" pose with no motion blur and no mid-action implied motion. Runway warns that implied motion fights the prompt.
5. Frame wide enough for the planned action. Nothing can stand up out of a head-and-shoulders crop.
6. Start and end frames share the subject, set, light and camera setup. "The wider the gap ... the more unpredictability".
7. Avoid very dark or heavily vignetted keyframes. They silently failed in Veo Lite; generate neutral and grade later.

Prompt split:
- The image carries appearance. The video prompt carries only motion, camera, performance and sound.
- "Effective image to video text prompts focus almost exclusively on motion" (Runway). Re-describing the frame causes static loops.
- Use one subject action and one camera move per clip, and split multi-beat ideas into separate clips.
- Beat budget: 4 s = 1 beat, 8 s = 2-3 beats, 10-12 s = 3-4 beats.
- Write holds positively ("the camera holds completely still").
- Never put the model name, duration or resolution in the prompt text.

Clip length and artefacts:
- Ask for the shortest duration that fits the action. Kling's minimum is 3 s, so trim in post.
- Expect morphing hands and contact points, warped text, identity drift on big angle changes, and bad liquid/cloth physics.
- No vendor publishes artefact rates. Measure your own accept rate per shot and budget retakes on cheap tiers first.
- Parallel generations from the same plate can produce identical motion.
- If two providers fail the same shot, fix the keyframe or prompt.

Never-as-evidence rule: generated clips are for metaphor, mood and the unfilmable.
- Real product, people, places and events come from real footage and screen recordings.
- A clip that needs frame-level fixes to faces, hands, text or physics fails. After one re-constrained retry, switch to motion graphics, a still with a camera move, or real footage.
- Generate clips silent and keep the film's own VO and music.
