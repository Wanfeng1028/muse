# Story and motion

## Developer story

Lead with the useful change. Show its mechanism with actual product evidence. Each feature should earn its time with a different proof: a real tool interaction for a computer feature, a topology for interoperability, a saved document for persistence, configuration or a deploy path for self-hosting.

A 30–60 second announcement often needs 4–7 beats. This is a planning aid, not a quota. A short sentence needs time to read after motion settles; code and multi-step UI need longer. Remove a claim before making every scene unreadably fast. Keep the closing URL readable for several seconds and verify its real destination and intended visibility.

Keep one focal event at a time. Use motion to explain causality or shift attention; perpetual bobbing, arbitrary particles, spinning cards, and looping traffic often obscure the product. Do not equate more motion with more polish.

## Visual system

- Choose a small type scale. At a 1920×1080 design size, start around 72–100 px for short headlines, 32–44 px for supporting text, and 26–36 px for useful UI text; inspect at delivery size and adjust.
- Reserve about 5–7% edge space, but measure actual extents, including animation overshoot, shadows, badges, and the CTA icon. Avoid long headings sharing the same horizontal space as a phone.
- Keep each logo's official artwork, aspect ratio, and optical scale. Derive repeated lists from one registry. A generic protocol should not borrow a vendor's mark.
- Make the app panel the subject. Empty device bezels and oversized backgrounds should not consume its readable area.
- Treat mockup content and decoration separately: a button, status receipt, or chart should explain the feature, not become a pile of dashboard filler.

## Animation

Drive every animated value from the frame/time passed by the renderer. No wall-clock timers, CSS transitions, unseeded randomness, or live API calls inside a deterministic composition. A practical shared vocabulary is a 12–18 frame settle, a 4–6 frame sibling stagger, and restrained positional travel. Tune it to the requested style instead of prescribing one curve everywhere.

Use scene-local frame zero and test seeking backwards. Wait for local fonts and media before rendering. A video frame's output time, source trim, speed, and offset must be calculated explicitly.

For architecture scenes, derive card ports and connectors from the same coordinates. Draw shared buses once. Connector highlights must travel along the exact SVG path or measured polyline at arc-length speed. Keep node geometry stable while lines connect; floating a card without moving its wire looks broken. Add a legend only when encoding cannot be understood from labels.

For seamless loops, every animated period must divide the loop length, including background motion. Compare the final-to-first transition at normal speed. A loop can begin fully assembled; a launch reveal may need a separate settled poster or short frozen cover. Never assume frame 0 is a useful thumbnail.

## Audio

Use user-supplied, original, or appropriately licensed music and retain provenance. Match energy to the brief: an upbeat developer launch can use a crisp rhythmic bed, without overpowering the UI. Align major cuts to phrases or beats when it helps, not every small interaction.

If original music is generated procedurally, retain source and seed. If music comes from a library, retain the license/source record. Do not lift reference-video audio. Keep a music stem separate from the film. Use 48 kHz for an editor handoff. Listen for clipping, abrupt truncation, and audible seams. If there is narration, provide captions and mix music beneath it. Silent-view comprehension matters even when there is no speech.
