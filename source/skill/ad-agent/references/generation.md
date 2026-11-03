# Generation: H3 clips, keyframes, voice lines

All three are async and cost credits. Each returns a `task_id` to poll with `composer_task_status(task_id, wait=50)`. Paths are project-relative.

## Boreal-H3 footage (`composer_generate_clip`)

One clip per call, 5–15 seconds (`duration` outside that range is rejected):

```
# reference-to-video: the primary mode for people/style; condition on character/product/style references
composer_generate_clip(project_id, mode="r2v", prompt="<shot description>",
  images=["assets/<hash>_spokesperson.png", "assets/<hash>_packshot.png"],
  videos=["assets/<hash>_motion.mp4"],         # optional; project paths or https URLs
  audios=["assets/<hash>_voice.wav"],          # optional voice/sound reference; project paths or https URLs
  duration=10, aspect_ratio="9:16", out="gen/shot1.mp4")

# text-to-video: no references
composer_generate_clip(project_id, mode="t2v", prompt="<shot description>", duration=8, aspect_ratio="9:16", out="gen/shot1.mp4")

# image-to-video: animate a keyframe (e.g. the last frame of the previous shot, for continuity)
composer_generate_clip(project_id, mode="i2v", prompt="<shot description>", image="gen/shot1_last.png",
  last_image="gen/kf_end.png",                 # optional anchored end frame
  duration=8, aspect_ratio="<the keyframe's own aspect>", out="gen/shot2.mp4")

# audio-to-video / LIP-SYNC: a provided dialogue track with a speaking person.
composer_generate_clip(project_id, mode="a2v", image="gen/speaker_frame.png", audio="assets/<hash>_dialogue.wav",
  prompt="<short motion guidance, same scene only>", out="gen/shot1.mp4")
```

Asset paths: pass the `path` that `composer_import_asset` returned, exactly. Imports get a hash prefix (e.g. `assets/4b42891a_logo_white.png`); there is no `assets/000_` numbering.

- **Dialogue / lip-sync is a2v, never r2v.** When the assets include a provided speech/dialogue/voiceover track AND the video shows a person speaking, use a2v: first frame + the exact audio → that person speaking that audio. The output already carries the original waveform. Do NOT duck, re-mix, or replace it; that waveform IS the deliverable's voice. An r2v audio reference is style/content conditioning only and will NOT sync the lips. When the speaker's reference is a video, grab its frame with `composer_exec`: `ffmpeg -v error -y -ss 0.1 -i assets/<hash>_ref.mp4 -frames:v 1 gen/speaker_frame.png`. Pick a frame where the face is visible and roughly centered in the framing you want (`composer_view` it).
- **On-camera speakers lip-sync their lines.** When a person on screen speaks first-person lines, or the brief casts actors/creators on camera (UGC, testimonial, presenter), they say those lines on camera. With no audio given, use `composer_list_voices(language="<language code>", source="library")`, review previews and select the voice with the user, then voice all of that speaker's lines in one call: `composer_voice_line(project_id, voice_id="<selected provider voice_id>", text=["<line 1>", "<line 2>"], out="gen/line.wav")` → `gen/line_1.wav`, … in one voice. Then a2v each line from that speaker's keyframe. Lines stay captions-only, or go to an off-screen narrator, only when the brief asks for music/captions only or a narrator.
- a2v length comes from the audio, capped at ~14.4s. **The audio is HARD-TRIMMED at the cap**: a 15.0s dialogue loses its last ~0.6s (the typical casualty is the final 1–2 words, like "…is live"). TRUNCATED DIALOGUE IS A HARD FAIL, not a padding problem: the provided track must never end up silently shortened.
  - Dialogue ≤ ~14s: one a2v call. Pad VIDEO to the Duration target with a freeze+fade tail in assembly. Never extend with footage of the person not speaking.
  - Dialogue > ~14s: split the WAV into ≤13s segments at quiet sentence boundaries (find and cut them with the silence and segment recipes in media-recipes.md). a2v segment 1 from the speaker frame. Each NEXT segment's `image` is the PREVIOUS segment's last frame (`ffmpeg -sseof -0.2 -frames:v 1`), so face and framing continue. Concat the segments in assembly. The provided waveform must survive end-to-end, so check coverage (audio-sync.md).
  - **a2v is load-bearing. Degrade honestly, not silently.** a2v calls already retry internally. If a segment still fails, try ONCE more with a plain no-prompt call. If a2v remains unreachable, r2v+mux MAY be shipped as a fallback, but then lip-sync is NOT guaranteed and you must say so in the take report's "Known gaps" line, in plain words ("lip-sync not verified: the lip-sync model was unavailable, so the voice is laid over the footage"). A gap between claim and method is a defect worse than a failed run.
- Renders take minutes. Poll; don't restart.
- **Motion must be READABLE in a 15-frame contact sheet.** H3's default register is subtle. Left un-prompted, i2v on a still image drifts toward a locked-camera cinemagraph that reads as a photo. Prompt specific, visible movement at the brief's intensity: camera ("slow push-in", "pan across the room"), light/prop/body action ("steam rises", "curtain sways", "she shapes the clay"), pacing beats. Use looping/cinemagraph ONLY if the brief says loop/cinemagraph.
- Renders are `boreal-h3` (our post-trained H3) at `resolution="1088P"`. `resolution="768P"` is an optional cheap draft tier (current prices in `composer_billing_state`; a 9 s clip cost 4.0 vs 11.0 at 1088P), or the final tier when the budget can't afford 1088P. It returns 768×1344, slightly off 9:16: keep the project canvas and accept the scale-up on drafts, or create a 720p project for draft-only checks (stage-api.md). **A 1088P re-render of an approved 768P draft is a NEW generation, not an upscale of it**: framing, motion and details will differ, so judge it again before it ships. a2v ignores `resolution` and always renders at 720p (priced about half of a 1080p lip-sync). **r2v is the workhorse for people/style references. For a product or app screen, follow product-fidelity.md (keyframe + i2v).** r2v takes the typed references (≤9 `images`, then `videos`, then `audios`) and generates its own synchronized audio.
- **The person who carries the ad starts from a keyframe, never t2v.** That means a speaker, anyone seen in more than one shot, or a face that fills the frame. Make their first frame with `composer_edit_image` (a plain canvas as the input image when no photo of them exists) as a candid phone photo in the scene: ordinary framing, the brief's own light, visible skin texture. End the prompt with "no studio lighting, no ring light, no retouching, no beauty filter, no smoothing, no bokeh, no professional headshot polish, no text on props". Then drive it with i2v or a2v; H3 t2v renders people as glossy, ring-lit influencer beauty. Passers-by and wide shots where no face is the subject can stay t2v, with the same "no …" list in the prompt.
- Always state `aspect_ratio` on r2v and t2v: the output aspect, never the reference's shape. (The project's aspect is the default when you omit it.)
- On i2v the keyframe stretches onto the canvas, so pass the keyframe's own aspect as `aspect_ratio` (from its import probe or an `ffprobe` via `composer_exec`).
- **Colour is not locked.** On i2v, Boreal-H3 may not start exactly on the supplied first frame, and it can drift in hue across the clip; compare the first and last tiles of the sheet with the keyframe. Don't list banned colours as negatives ("no pink, no purple"): naming a colour tends to bring it in. Describe the colours you want instead, and fix a hue drift for free in the page (the grade recipe in graphics-craft.md) before paying for a regen.
- One shot per call. Parallelize independent shots as parallel tool calls (≤4 in flight per project), then poll each.
- **`out` is not the truth: read `result.probe` for every delivered clip.** The delivered length can differ from the request by about ±0.6s (two 9s requests both returned 9.457s); plan `in`/`dur` from `probe`.
- `seed`: pass the user's seed on the first take; a deliberate re-roll uses a new seed (an identical call within ~10 minutes returns the old task with `reused: true`).

## Keyframes and reference prep (`composer_edit_image`)

```
composer_edit_image(project_id, prompt="<edit instruction>. Do not alter the product design.",
  images=["assets/<hash>_product.png", "gen/scene.png"], aspect_ratio="9:16", out="gen/kf1.png")
# GPT Image 2.5 Sunburst, 2K PNG at the stated aspect
```

Composes or edits a still from references: a first frame that already contains the exact product, a clean cutout, or a reference extended to the output aspect. Pass the product image FIRST and describe it concretely (shape, closures, materials, colors, every word printed on it), and end with "Do not alter the product design." Look at every keyframe (`composer_view`) and show its `footage_urls` link before driving a clip from it.

**Worn products, several looks, or before/after: one look board.** When a person wears the product or it changes state across shots, first make ONE keyframe holding every look side by side (same person, room and light; the product's exact pattern and colour from its photos; no text). Then drive each shot from its panel with `composer_generate_clip(mode="r2v")`, passing the board or the panel crop (cut with `composer_exec`) plus the product photo as `images`. Keyframes made one look at a time drift in face, room and product detail. The board shows only the colours and states the page sells, unless the user asks for others.

## Voice lines (`composer_voice_line`)

- **Choose exactly one selector:** library/workspace provider `voice_id` OR authorized `like` samples. `describe` / voice design is removed; missing, conflicting or obsolete selectors are rejected before task creation/credits. Never infer a voice ID from a description or pass an Accent/Voice record UUID.
- **Catalog first:** `composer_list_voices(language="pl", source="library", limit=20, offset=0)` is a read-only, no-credit lookup. `source="mine"` returns eligible voices in the authenticated workspace; `"all"` includes library and workspace voices. Results include provider `voice_id`, languages, accent, description and preview URL. Review previews/casting with the user; language support alone does not guarantee a native accent or pronunciation quality. Use returned `total` and `offset` to page if needed.
- **Selected voice:** `composer_voice_line(project_id, voice_id="<provider voice_id returned by composer_list_voices>", text=["Zażółć gęślą jaźń!"], out="gen/vo.wav")`. Preserve the user's exact script/language; do not add an English-language instruction to the spoken text.
- **Authorized cloning:** `composer_voice_line(project_id, like=["assets/authorized_sample.wav"], text=["<line>"], out="gen/vo.wav")`. Use only clean speech the user owns or has rights to clone. It makes a temporary clone, performs TTS and deletes the clone; omit `voice_id` and `describe`.
- **Provided audio:** if the user already has a rights-cleared recording, import and use that exact recording (including as a2v audio when appropriate); no new TTS is needed. Import/assembly/lip-sync still have their normal costs and need user consent.
- Each line costs credits (1 credit per line observed; current prices in `composer_billing_state`). A single line writes exactly `out`; several lines in one call → `out_1.wav`, `out_2.wav`, … in one voice. `lead` (default 0.4 s) is the silence before each line.
- If `composer_list_voices` / `voice_id` is missing from the live tool schema, the coordinated server rollout or client schema refresh is incomplete. Reconnect and start a new conversation after rollout; do not retry `describe`, guess an ID, or run voice generation through the networkless `composer_exec` sandbox. Ask for authorized samples/provided audio or report the capability unavailable.
- A re-voiced line becomes exact audio for an a2v shot. See audio-sync.md for when a line must be re-voiced.
