# Case Study：云上宋式档案馆

Use this case when the user asks for a high-end scene-image test, model comparison, final prompt refinement, or a scene similar to `云上宋式档案馆`.

Final selected image asset:

`assets/case-studies/cloud-song-archive-final.png`

## Scene Thesis

A Song-style timber archive suspended above a sea of clouds has been converted into a quiet modern rare-book conservation and climate-protection center.

The core visual tension is:

ancient scholarly restraint vs precise modern preservation technology.

## Winning Model Route

The strongest route was:

1. Run a broad image-model test only on the requested image models.
2. Use GPT Image2 for the main production-design image.
3. Use Seedream only as an atmosphere reference when it produces better cloud, timber, or poetic light.
4. Avoid switching back to pure text prompts once a strong composition exists.
5. Use the winning image as a locked reference and run narrow repair prompts.

For this case, the final selected image came from GPT Image2 final refinement. Seedream produced attractive atmosphere, but stayed weaker as a final output because it leaned toward exhibition-room design and visible watermarks.

## Success Criteria

The final image must satisfy all of these:

1. Reads immediately as a cliffside Song-style timber archive above cloud sea.
2. Reads as a working rare-book restoration and climate-protection center, not a temple, tea room, tourist site, or ordinary study.
3. Shows practical conservation evidence: archival drawers, restoration tables, soft conservation lamps, linen-wrapped books, sealed book boxes, blank instruments, hidden vents, and quiet conservators.
4. Keeps modern technology embedded, discreet, and protective.
5. Preserves cinematic cool blue exterior mist versus warm amber interior light.
6. Avoids readable text, numbers, UI panels, plaques, labels, logos, and book-spine writing.

## Common Failure Modes

- The image becomes a temple, shrine, tea room, academy, tourist balcony, or fantasy cloud palace.
- Glass cabinets look like museum exhibition vitrines instead of climate-control archival storage.
- Modern equipment turns into a lab, hospital, sci-fi control room, or screen-filled command center.
- The model adds Chinese calligraphy, English letters, labels, numbers, UI blocks, book-spine marks, or signage.
- The image is beautiful but does not read as a functional cultural preservation facility.
- Seedream-style outputs may carry visible `AI生成` watermarks; treat those as atmosphere references, not final winners.

## Final Refinement Prompt Pattern

Use this after a strong candidate image exists.

```text
Use the provided image as the locked composition reference. Do not redesign the scene.

Preserve the wide cinematic composition, the cliffside Song-style timber archive, the sea of clouds, wet stone threshold, dark aged timber, deep eaves, paper-screen rhythm, warm lanterns, cool blue morning mist, and quiet rare-book restoration work.

Make only subtle improvements: reduce the museum-display feeling of the glass cabinets; make them read as discreet climate-control rare-book storage integrated into the timber architecture. Add authentic conservation details such as archival drawers, linen-wrapped volumes, sealed book boxes, paper-repair tools, soft conservation lamps, blank bronze humidity instruments, hidden vents, and careful work surfaces.

Keep the atmosphere restrained, scholarly, expensive, real, and cinematic. Modern technology must be quiet, precise, protective, and embedded.

No readable text, Chinese characters, English letters, numbers, calligraphy, plaques, signboards, labels, book-spine writing, digital UI, logos, temple altar, shrine objects, incense, tourist signage, tea-room props, sci-fi panels, glowing screens, or plastic-looking glass.
```

## Model Notes

- GPT Image2: best for final image when using reference-image lock and narrow repair prompts.
- Seedream: useful for poetic atmosphere and cloud/timber mood, but weaker for final professional conservation-center clarity.
- Midjourney: use only for emotional concept exploration; it may drift toward elegant study, temple, or scenic room.
- Nano Banana-Gemini: useful as a compliance backup, but not needed once GPT Image2 has a strong locked composition.

## Final Gate

Before calling the image final, choose:

- one final selected image,
- one backup image,
- optional atmosphere reference images,
- and one short note explaining why no more random model runs are needed.
