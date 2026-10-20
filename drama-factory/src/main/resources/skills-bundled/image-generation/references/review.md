# Review, failures, workflow

How to review your own images, the failure table, and the brief-to-handoff workflow with cost control.

Contents
1. Review checklist (how an AI reviews its own images)
2. Failure modes and fixes
3. Workflow (brief to Remotion)

---

## Review checklist (how an AI reviews its own images)

Run in order; stop at the first failure and decide edit or regenerate.

1. **Technical.**
   - The file decodes, and its size and aspect are as requested.
   - Alpha is present when required (count the fully transparent pixels).
   - No watermark or signature.
   - No checkerboard painted in.
2. **Brief compliance.** The image shows the action, the count, who looks at whom, and the hands doing the named thing. A beautiful image that misses the beat fails.
3. **Identity.** Compare against the cast sheet: silhouette, skin tone, hair, garment colours and brightness, signature item. Check that adjacent characters haven't converged.
4. **Anatomy and contact.**
   - Count fingers. Check that hands are gripping objects, feet are on the ground, and straps and tools are attached.
   - Check that eyes look at the target and that expressions read at thumbnail size.
5. **Stray text.** No pseudo-letters on signs, screens, spines, keys or clothing, and no numbers.
6. **Palette and style.** No gradients or shading where the style forbids them, no cream drift, no off-palette colours. The texture should match the rest of the set.
7. **Set consistency.**
   - Put the image on a contact sheet with its neighbours in the edit.
   - Check light direction, scale between characters, line weight and margin.
8. **Motion readiness.**
   - There is margin for the planned move, and the subject isn't cropped.
   - Blank surfaces really are blank.
   - The cutout has no halo over violet, and there are no holes in white garments.
9. **Honesty.** No real person, brand, logo or trademarked character, and nothing reads as documentary evidence.

Vision-model judges sample and hallucinate details. In the Repitis film, an AI video judge's claims about gradients
and emojis were wrong. Verify any claimed defect by cropping and zooming the actual pixels before acting on it.

## Failure modes and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `Transparent background is not supported for this model` | gpt-image-2 preview discontinued (~2026-10-01) | use gpt-image-2.5 with transparent, or white + BiRefNet |
| `input_fidelity` rejected | gpt-image-2/2.5 always high fidelity | omit the parameter |
| Background painted although `background=transparent` | prompt describes a backdrop or scene | describe an isolated subject only; say "transparent background" |
| Character changes face or outfit between shots | sheet not passed, descriptor paraphrased, or identity chained through scene images | pass the sheet as Image 1 every time, repeat the descriptor verbatim, never chain through scenes |
| Two characters merge traits | adjacent descriptions bleed | make the differences big and specific; repeat them; generate a tight two-shot as an edit of the sheet |
| Wrong reading of the subject (rooster for hen, lighthouse for tower) | name only, no distinguishing traits | add physical traits and "clearly X, not Y" |
| Gibberish text on props | model fills surfaces | "plain, blank, no lettering"; composite real text |
| Objects with faces, smiling suns | kid-style prior | "inanimate objects, the sun and the moon have no face" |
| Off-palette greys or browns | animals or materials with natural colours | accept consciously, or recolour in post; name the palette colour for fur |
| Glossy highlights in a flat style | "jar" or "glass" priors | "flat opaque paper with no shine or highlights" |
| Too small in frame | default composition | "filling about 80 percent of the frame with even margin" |
| Masked edit spills outside the mask | masks are guidance only | composite the edited region back over the original with your own feathered mask |
| Edits slowly degrade the image | each pass re-renders everything | go back to the last good version; one change per edit; restate the preserve list |
| Halo or white fringe after matting | white backdrop bleeding into edge pixels | colour decontamination or 1 px alpha erode; non-white backdrop for white subjects |
| `moderation_blocked` on innocent prompts | words like "shoot", "naked eye", child + bath scenes | rephrase; never auto-retry unchanged; read `moderation_stage` |
| A few hundred bytes returned | error JSON saved as an image | check the status and content type before writing files |

## Workflow (brief to Remotion)

1. **Brief.** Write down the format, the delivery aspects, the shot list with each image's job (plate, cutout, keyframe, insert), and the style references. Mark which surfaces will carry real text.
2. **Style exploration.** Make three to four directions, each as one suffix applied to the same two test subjects (one character, one object), at low quality with n=4. Build a labelled contact sheet and pick one with the owner. Cost is cents.
3. **Lock.** Freeze the suffix (versioned), the palette, the light direction and the backdrop line. Generate and approve the cast sheet (and a prop/set sheet if needed) at high quality.
4. **Batch.** Write a prompts file (name → prompt, size, references with roles) and generate in waves (references first).
   - Keep 2-4 requests in flight (Build tier is 20 images/min).
   - Never overwrite: archive to `raw/<name>.vN.png`.
   - Write a sidecar JSON per image with prompt, model, size, quality, refs, usage and request id.
5. **Review** (above). Make a contact sheet of the whole batch, then zoom in per image.
6. **Fix.**
   - Edit when composition and identity are right and one local thing is wrong (expression, prop, colour, stray text). Use one change per edit and restate the preserve list.
   - Regenerate when the composition, pose, identity or style is wrong, or after two failed edits.
   - Make a pixel-critical fix by compositing in code, not by re-prompting.
7. **Cutout and QA.** Run the matte, then check over a saturated colour and at 200% on edges.
8. **Handoff.**
   - Put trimmed PNGs in `public/img/cut/`, referenced with `staticFile()` in `<Img>`.
   - Record the native size and the anchor point (feet or centre) in a small manifest so layouts can place them.
   - Keep raw masters outside the bundle if they're large.
   - Keep prompts with the images (Repitis embeds them as `.webp.json` sidecars).

Cost control:
- Draft at low quality and 1K.
- Use `n` variants in one call rather than repeated calls.
- Move to high only for picks. Use xhigh/max only for a specific unmet requirement.
- Use the Batch API (half price) for big non-urgent sets.
- Reuse the cast sheet rather than many refs: each reference adds input tokens per call.
- Measure the cost per *accepted* image, not per call.
- Reference points:
  - Repitis cards: 113 cards at medium 1024² plus a dozen regenerations. About $6-7 at the gpt-image-2 medium price (estimate from list prices).
  - Film: 8 images at high 1536x1024 is about $1.30 in output plus reference input tokens (estimate).
