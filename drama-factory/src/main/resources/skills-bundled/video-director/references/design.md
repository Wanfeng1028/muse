# Design for video: layout, type, colour, brand, real product, assets

Contents
1. Brand fidelity
2. Scale for video
3. Layout and composition
4. Colour
5. Typography
6. Lazy defaults to question
7. Real product screens
8. Stills, photos, cutouts, illustrations
9. Data in motion
10. Formats: one timeline, many layouts
11. Remotion notes

---

## 1. Brand fidelity

- Read the product's design source first (precedence example: `frame.md` → `design.md` → `DESIGN.md`/`BRAND.md`).
  Tokens are normative: quote hex, family and weight verbatim, never round or invent. Prose is context for judgement.
- No design source: capture the live product (screenshots, pixel-sampled colours, fonts in use) and write a short
  token file before designing. Each token notes its source. Never brand from memory.
- **Brand is sacred, layout is free.** Strict on hex, families, weight relationships and do/don't lists; free to adapt
  sizes, spacing, decorative opacity and border weight for video.
- If the product ships brand components (logo, stickers, cards, illustration style), rebuild or reuse them verbatim
  for frame-driven animation. Starting from a previous video's files is the most common way to drift off-brand.
- The product's own rules beat generic taste (a brand that forbids gradients, glow or blur wins over any "add a
  grain layer" advice).
- Logos: the brand's own files, or svgl / simple-icons for third parties. Never redraw by hand; never co-marks that
  imply a partnership.
- Never lift a word or label out of the style spec as on-screen content; it is a style spec, not copy.
- Post-build adherence check: every hex on screen exists in the palette; families and weights match; radii, spacing and
  shadow depth match; none of the spec's don'ts appear.
- Custom style (no brand yet): name it after a designer, movement or cultural reference; 2 to 5 colour tokens, 2 to 3
  type sizes, radii, spacing, a motion character; one paragraph of feel, do, avoid.

## 2. Scale for video

Web values vanish on video. Scale at 1080p:

| Element | Web | Video |
|---|---|---|
| Headlines | 32 to 48 px | 64 to 120 px |
| Body | 14 to 16 px | 28 to 42 px |
| Labels | 12 px | 18 to 24 px |
| Decorative opacity | 3 to 8% | 12 to 25% |
| Borders | 1 px | 2 to 4 px |
| Padding | 16 to 32 px | 60 to 140 px |

- Under 24 px needs a reason; decorative opacity under 10% is invisible.
- Feed-sized playback (X, LinkedIn, Instagram): body ≥ 32 px, headlines ≥ 90 px, data labels ≥ 24 px.
- Portrait text ≈ landscape × 1.3; the phone is held close but the frame is narrow.
- Test: everything must read on a phone sheet at 360 px wide (`scripts/sheets.sh phone`).

## 3. Layout and composition

- Fill the frame: hero text 60 to 80% of frame width; the primary visual at least 40% of the canvas. Never a small
  cluster floating in empty space.
- Depth: at least three layers (background treatment, midground message, foreground accents such as rules, labels,
  data marks). Decoration only when it reinforces hierarchy, motion or concept; never as new content or claims.
- Backgrounds are never empty but never noisy: a brand-tinted field, a soft localised glow, oversized ghost type bleeding
  off-frame, hairline rules, a grid, a thematic motif. Two to five per scene. Openings and endings are where emptiness
  creeps in.
- One dominant focal point plus a second for the eye to travel to. Dominance comes from at least two of: size (3:1),
  weight (800 vs 400), contrast, position, motion. Squint test: blurred, the number one element is still obvious.
- Anchor to edges and zones (data left, content right, metadata top bar); centred-and-floating is a web habit. Framing
  vocabulary: centred (hero, climax), rule of thirds, split (comparison), layered depth, asymmetric 60/40 or 70/30,
  triptych, full-width strip. Use at least three framings per film and never the same twice in a row.
- Structural elements (rules, dividers, panels) create paths and animate well. A connector line needs a real start, a
  real end and a job, or it goes.
- Don't show nav bars, footers, scrollbars, browser chrome, generic shapes standing in for a real asset, floating bokeh,
  purple-blue "AI" gradients.
- One accent moment per scene. One accent colour per film.
- **Subject size has thresholds** (measured on a weak vs a strong film with equal motion counts): every shot has one
  subject at ≥ 1/3 of the content height (a graphic ≥ 170 px, or display text ≥ 96 px spanning ≥ 300 px at 1080p). Three
  size tiers only: subject ≥ 170 px, up to 4 supporting elements at 60 to 110 px, up to 6 labels at 22 to 30 px. A largest
  object under 110 px for more than 45 frames is an empty frame. Naturally small subjects (timelines, tables, formulas)
  get a hero element: a big number, an enlarged current row, a magnifier. Show "many" as an ordered grid, never confetti.
- **Cheapness check per beat**: more than two competing motions; more than two font weights; blue-purple gradients, glass
  cards, particles, constant glow or orbs as filler; every keyword popping or glitching. Three or more cheap effect
  families in one beat (glitch + shake + glow once each still counts as three) means delete until at most two remain;
  staggering them in time doesn't count as removing them.
- 9:16 talking head: speaker at the bottom, one graphic at the top, captions. Nothing else; crowded vertical stacks are
  an AI fingerprint.

## 4. Colour

- Declare background, foreground and accent before building; keep the same background family across scenes; no
  per-element colour invention.
- Tint neutrals toward the brand hue; avoid pure #000 and #fff.
- Every scene has one colour that pulls the eye: the accent at 15 to 25% for atmosphere, at full saturation on the focal.
- Light canvases need bolder structure (2 px+ rules, full-saturation hits, subtle texture); don't flip to dark to look
  cinematic. Light suits food, wellness and kids; dark suits tech, cinema and finance (defaults, not laws).
- No full-screen linear gradients on dark backgrounds: they band under H.264. Use radial, solid, or solid plus a
  localised glow; render PNG frames if banding persists.
- Dim text on dark or glass needs alpha ≥ 0.66 to reach 4.5:1. Text must stay readable with decoration removed.

## 5. Typography

- Always set the product's font explicitly and load it before render. The model's default font is recognisable.
- Pairing: one family at two weights, or contrast on several axes (serif/sans, condensed/wide, sans/mono). Never two
  similar-but-different faces. One expressive face per scene; the other recedes.
- Weight contrast must be extreme in motion: 300 vs 900, not 400 vs 700. Headlines 700 to 900, body 300 to 400.
- Display tracking tighter than web: −0.03 to −0.05 em. On dark backgrounds light text reads heavier: drop body weight
  a notch, add 0.05 to 0.1 line-height.
- Assign faces to modes (statements, data, attribution) like voices in a conversation.
- Choosing a face without a brand font: name the register, imagine the font as a physical object the brand could ship
  (museum caption, hand-painted sign, children's book), reject the first instinct (it's the training default),
  question category assumptions (kids needn't be rounded). Over-used defaults to question rather than ban: Inter,
  Roboto, Poppins, Montserrat, Playfair Display, Space Grotesk, Instrument Serif, Fraunces, Syne. A brand's own font
  always wins.
- `tabular-nums` for counting or stacked numbers; small caps for units; no ligatures in code.
- Pixel gaps (not em) between big text blocks in flex rows: em resolves against the parent font size.
- Highlight one word per headline at most: hero colour, an animated underline, or a pill that scales in behind it a few
  frames after the word lands.
- Motion is typography: a 0.1 s slam and a 2 s fade say different things with the same face (`motion.md` §7).

## 6. Lazy defaults to question

Use one only as a deliberate choice for this content: gradient text, left accent stripes on cards, cyan-on-dark,
purple-blue gradients, neon, pure black or white, identical card grids, everything centred at equal weight, rainbow
gradients, particles, glowing chrome, emoji (they render as full-colour platform glyphs that ignore the palette),
lorem ipsum, gratuitous 3D flips, a centred title on a gradient, corner labels and frame borders, a mandatory
grain-plus-vignette stack on every scene.

## 7. Real product screens

- Capture the real UI (run the app, Playwright screenshots or recordings) and list what you found. Never invent screens.
  If capture is blocked, ask for screenshots or label a recreation as an illustration. A failed capture is a stop, not a
  licence to invent.
- Two ways to show a screen, both honest:
  - **Capture as-is** for tours: use the screenshot or recording; overlay real assets at measured positions when
    something must move, or rebuild only the moving component.
  - **Faithful rebuild** when animation demands it: scan screenshots in zoomed tiles, extract one ui-tokens file
    (pixel-sampled colours, fonts, radii, shadows, spacing), rebuild element by element, and compare side by side until
    it is recognisable at a glance.
- When no real screen fits ("show, don't tell" for a behaviour), choose in this order: a faithful UI mock of a real
  surface → an honest analog whose behaviour is the change (caching = the second request short-circuits; batching = ticks
  cluster) → a terminal typing the real command → a checklist of at most six rows. An analog depicts behaviour, never a
  fake product page.
- Anonymised demos: one fictional company used everywhere; no real clients, competitors or people; images with text are
  rebuilt (photo + retyped text) so they can be translated.
- Content evidence (screenshots, tweets, charts, docs) keeps its aspect ratio; only decorative media may be cover-cropped.
  Check all four edges for truncated text or controls.
- Highlights and annotations sweep on after the content settles, anchored to measured element positions. Keep text at a
  readable size and highlight in place instead of blowing it up.
- Locating a target in an image: don't guess pixel coordinates by eye. Pick numbered strips on a 9×9 grid, crop, pick
  again on a 6×6 grid, draw the box and verify (measured error dropped from 6.5% to 2.3%).

## 8. Stills, photos, cutouts, illustrations

- Never show a flat still: give it a slow push (scale 1 → 1.03 to 1.06 over the shot, perceptual scale), a perspective
  tilt (rotateY about −8°, perspective 1200 px), a device frame, extracted UI floating at another depth, or a clipped
  scroll reveal. Keep the push direction across a cut; vary the axis (push vs pan) instead of alternating in and out.
- Backgrounds under readable text are dimmed 30 to 50%.
- People in a layout are cut out, never boxed rectangles.
- Don't push the camera under a fixed overlay (the target drifts out of the ring); scale the whole scene together.
- **Generated illustrations, characters, plates and cutouts**: use the image-generation skill (locked style suffix,
  cast sheet as Image 1 on every edit, sizes with overscan for camera moves, white-backdrop cutouts with BiRefNet reviewed
  over a saturated colour, versioning, hostile review).
- Never trust model-rendered text in images or video clips; overlay real text in code.
- Stock: build a contact sheet of candidates and look before using any. Check each licence; keep a ledger.
- Grade photos to remove off-brand hues with a continuous per-pixel formula; hard hue thresholds blotch JPEG blocks.
- Asset fusion: a real object's geometry can become the chart (a glass's liquid as a pie, a straw as a gauge).

## 9. Data in motion

- Successive stats of one concept stay in the same visual space; only the value changes. A change of look signals a new
  concept.
- Pair every number with a visual that gives it weight (fill bar, ring, shape). One chart, one message; at most 2 to 3
  metrics on screen. No pie charts with many slices, multi-axis charts, dashboards, gridlines, ticks or legends.
- Count-ups run 1.2 to 1.6 s decelerating, then hold. The label lands after the value (value → meaning).
- Every number traces to `facts.md`.

## 10. Formats: one timeline, many layouts

- Design every format from the start; never crop a designed frame. Re-lay out per format from the same timeline with a
  layout function and a design unit `u = min(width, height) / 1080` (the template's `useFormat()`).
- Portrait and square: stack what sits side by side in landscape; bigger type, fewer words per line; anchor the hero
  around 0.2 to 0.35 × height. Keep essential text inside the centre 1080×1080 of a 9:16 frame.
- Safe margins: about 110 px on 16:9 and 80 px on 9:16; every title fits on one line. Platform UI zones on vertical
  video are in `footage.md` §11.
- Camera footage is the exception: it may be cropped, framed on the face, with graphics re-laid out around it.

## 11. Remotion notes

- Fonts: `@remotion/google-fonts` or `@remotion/fonts` `loadFont`, awaited before render. A font with no file silently
  falls back in the headless renderer. See `~/.claude/skills/remotion-markup/google-fonts.md` and `local-fonts.md`.
- Images: official `images.md` (sizing, `<Img>`/`CanvasImage`); text fitting: `measuring-text.md`; DOM measuring:
  `measuring-dom-nodes.md`. Measure text after fonts load; under a camera scale use canvas `measureText`, not DOM rects.
- Text that must stay sharp during a handoff: crossfade only the fill; never scale a blurred copy. Never set
  `will-change` on an element the camera scales.
- Determinism: no `Math.random`; use `random(seed)` from `remotion`.
