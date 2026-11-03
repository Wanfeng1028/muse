# Explainer video styles

40 explainer styles, each with a starter prompt for a coding agent. Live page: https://24fps.dev/explainers.
Pick the style closest to the brief, fill the [BRACKETS] and run the prompt. Each style names the tool it builds best in.
The styles describe a look, not a channel: build your own scenes and never copy a channel's footage, code or assets.

## Contents

- **Science and education**: `math-intuition-board`, `flat-vector-science`, `illustrated-lesson`, `whiteboard-marker`, `speed-sketch-lecture`, `blueprint-schematic`, `code-walkthrough`, `pixel-game-explainer`
- **Journalism, maps and data**: `map-annotation-essay`, `flat-logistics-infographic`, `geopolitics-dark-map`, `data-chart-journalism`, `bar-chart-race`, `timeline-history`, `news-lower-third-pack`, `headline-highlight`
- **Collage and hand-made**: `paper-collage-explainer`, `cutout-surreal`, `claymation-look`, `sketchbook-doodle`, `comic-halftone`
- **Product, launch and brand**: `device-reveal`, `tech-review-broll`, `saas-launch-video`, `cursor-zoom-demo`, `cinematic-tech-intro`, `liquid-glass-ui`, `year-in-review`, `swiss-grid-motion`, `brand-sizzle-kinetic`
- **Creator and social edits**: `retention-edit`, `educator-talking-head`, `podcast-clip`, `lyric-kinetic`, `anime-opening`, `beat-edit-amv`
- **Documentary, film and retro**: `doc-photo-pan`, `retro-vhs`, `vaporwave-synth`, `lofi-study-loop`

## Science and education

### Math intuition on a dark board (`math-intuition-board`)

Inspired by 3Blue1Brown, an intuition-first maths channel. Manim + manim-voiceover, 16:9, about 75 s. https://24fps.dev/explainers#math-intuition-board

- Palette: near-black navy bg, blue/yellow/green/red accents
- Type: LaTeX serif for maths plus a clean sans for labels
- Motion: transforms between shapes and equations (morph, not cut), camera pans on a plane, number lines, vector fields
- Transitions: objects morph or fade; few hard cuts
- Sound: calm piano/ambient, low narration, no stingers
- Rights: Manim CE is MIT. Build your own scenes; do not copy anything from the channel's published code or videos (its repository is non-commercial licensed).

```text
Make a 75-second 1920x1080 explainer on [TOPIC] with Manim Community Edition. First write a 7-beat narration script (one idea per beat) and show it to me.
Build intuition before notation: open with one concrete visual, animate the change, then name the idea and only then show the formula (MathTex).
Style: near-black navy background, blue/yellow/green accents, smooth Transform between objects instead of cuts, slow camera moves, labels fade in beside the thing they name.
Sync narration with manim-voiceover using [TTS]. Render per scene and join with ffmpeg. No logos, no copied scenes.
```

### Flat-vector cosmic science (`flat-vector-science`)

Inspired by Kurzgesagt, flat-vector science animation. HyperFrames + Motion Canvas, 16:9, about 60 s. https://24fps.dev/explainers#flat-vector-science

- Palette: deep indigo/space-blue bg with saturated gradients (teal, magenta, orange), light-blue halos
- Type: friendly geometric sans, small caps labels
- Motion: squash-and-stretch, springs, parallax, characters with simple faces, infinite zoom in/out between scales
- Transitions: zoom-through, wipe-with-shape
- Sound: warm synth/orchestral bed, pop/whoosh on object entry
- Rights: HyperFrames is Apache-2.0, Motion Canvas MIT. Invent your own mascot; no reuse of any channel's characters or assets.

```text
Make a 60-second 16:9 explainer on [TOPIC] in a flat-vector, rounded-shape style, using HyperFrames with inline SVG and GSAP.
Deep indigo background with soft gradients, 4-colour saturated palette, light halos behind key objects, no outlines, no photos. One small original mascot character with simple shapes.
Scale is the story: use infinite-zoom transitions between sizes (cell to body, planet to galaxy). Entrances use springy overshoot, staggered 0.06s; add gentle parallax.
Dense, rapid facts: one number or label per beat. Narration [TTS], soft synth bed, pop SFX on entrances. Render MP4 and give me the script.
```

### Illustrated lesson animation (`illustrated-lesson`)

Inspired by TED-Ed, narrated animated lessons. Motion Canvas + HyperFrames, 16:9, about 90 s. https://24fps.dev/explainers#illustrated-lesson

- Palette: warm, painterly flats with limited 5-colour palette per lesson
- Type: rounded serif/sans titles, minimal on-screen text
- Motion: character-and-object storytelling, camera pans across layered illustrated scenes, 2D rigs, simple lip-free narration
- Transitions: pan-through, object-match-cut
- Sound: light orchestral/pizzicato, soft SFX
- Rights: Motion Canvas is MIT, HyperFrames Apache-2.0. Draw your own illustrations or use public-domain art.

```text
Make a 90-second 16:9 illustrated lesson on [TOPIC] for curious teenagers.
Structure: question hook (0-8s), three short story scenes each showing one cause-and-effect, a twist, a one-sentence takeaway.
Look: layered 2D illustration, warm limited palette (5 colours), soft paper-grain overlay, characters built from simple shapes. Camera does slow horizontal pans and push-ins between layers (parallax). Almost no text; one title card and one final question card.
Use Motion Canvas or HyperFrames. Narration [TTS]; light acoustic score; one gentle SFX per scene change.
```

### Whiteboard marker explainer (`whiteboard-marker`)

Inspired by MinutePhysics, whiteboard animation. HyperFrames + rough.js, 16:9, about 60 s. https://24fps.dev/explainers#whiteboard-marker

- Palette: white bg, black marker plus 2-3 marker colours (red, blue, green)
- Type: handwritten (Caveat, Patrick Hand, Gochi Hand)
- Motion: strokes draw on in real time, quick erase/wipe, items drawn at narration speed; a hand optional
- Transitions: pan across the board, draw-over
- Sound: marker squeak SFX optional, otherwise voice only
- Rights: HyperFrames is Apache-2.0, GSAP is free to use, rough.js is MIT. Handwriting fonts named are OFL.

```text
Make a 60-second 16:9 whiteboard explainer on [TOPIC] with HyperFrames.
White background, black marker plus red and blue accents, handwritten font (Caveat). Everything is drawn: SVG strokes animate on with GSAP DrawSVG, slightly wobbly lines, stick figures only.
One idea per drawing; draw each element right as the narration mentions it; wipe the board with a quick horizontal erase every 12-15 seconds.
Narration [TTS], no music, subtle marker-scratch SFX. Keep it seekable and render MP4.
```

### Speed-sketch lecture (`speed-sketch-lecture`)

Inspired by RSA Animate, drawn-along lectures. HyperFrames + Motion Canvas, 16:9, about 120 s. https://24fps.dev/explainers#speed-sketch-lecture

- Palette: warm off-white paper, black fine-liner, spot colour (one)
- Type: hand lettering as keywords only
- Motion: one continuous drawing on a single canvas that grows; camera travels across it; a hand holding a pen
- Transitions: the drawing itself transitions (a line becomes the next scene)
- Sound: lecture audio plus light underscore
- Rights: HyperFrames is Apache-2.0. Only use lecture audio you have the rights to.

```text
Turn [TOPIC / lecture transcript] into a 2-minute 16:9 speed-sketch video with HyperFrames.
One big off-white canvas that is drawn progressively with a black fine-liner (SVG paths, GSAP DrawSVG); the camera pans and zooms across the growing drawing. Single spot colour for emphasis.
Key phrases appear as hand-lettered words at the moment they are spoken. A line from one drawing flows into the next scene; no hard cuts.
Add a simple hand+pen sprite following the stroke tips. Narration from [audio file / TTS], quiet piano underscore. Render MP4.
```

### Blueprint how-it-works (`blueprint-schematic`)

Inspired by engineering explainers and technical drawings. HyperFrames + Three.js, 16:9, about 50 s. https://24fps.dev/explainers#blueprint-schematic

- Palette: blueprint blue (#0B3D91-ish) with white linework, or black with cyan
- Type: mono (JetBrains Mono, IBM Plex Mono) for labels and dimensions
- Motion: lines draw on, dimension arrows extend, callouts with leader lines, exploded views
- Transitions: grid pan, section-cut reveal
- Sound: soft clicks, low hum
- Rights: HyperFrames is Apache-2.0, Three.js MIT. Mono fonts named are OFL.

```text
Make a 50-second 16:9 "how [TOPIC] works" schematic video with HyperFrames.
Blueprint-blue grid background, white 2px linework, monospace labels, dimension lines with arrowheads, numbered callouts (1-5) with leader lines.
Sequence: whole system, exploded view, then trace the flow one stage at a time with a highlighted path. Lines draw on with stroke-dashoffset; labels type in.
Narration [TTS], quiet hum + soft click SFX on each callout. MP4 out, plus a text script.
```

### Code and algorithm explainer (`code-walkthrough`)

Inspired by coding-interview and algorithm explainers. HyperFrames + Manim, 9:16 or 16:9, about 45 s. https://24fps.dev/explainers#code-walkthrough

- Palette: dark editor theme (One Dark / Tokyo-Night-like own tokens), one accent
- Type: JetBrains Mono
- Motion: line-by-line highlight, variable boxes updating, array cells swapping, pointer arrows, call-stack panel
- Transitions: slide between code and diagram
- Sound: soft key clicks, subtle ticks on state change
- Rights: HyperFrames is Apache-2.0, Manim CE MIT. The editor theme uses your own colour tokens.

```text
Make a [45-second 9:16 | 90-second 16:9] explainer of this algorithm: [TOPIC / code snippet] using HyperFrames.
Left/top: code in a dark editor theme (JetBrains Mono), the current line highlighted. Right/bottom: a live visual of the data structure (array cells, pointers, call stack) that updates exactly when that line runs.
Hook: show the input and the answer in the first 3 seconds, then walk through step by step with one example, then state complexity in one line.
Narration [TTS] with word-timed captions, tick SFX on each state change. Render MP4.
```

### 8-bit game-style explainer (`pixel-game-explainer`)

Inspired by retro pixel-art game interfaces. HyperFrames + Remotion, 16:9, about 45 s. https://24fps.dev/explainers#pixel-game-explainer

- Palette: limited 16-colour palette, dithering
- Type: pixel fonts (Press Start 2P, Silkscreen, VT323)
- Motion: stepped frames at 8-12 fps, typed dialogue box, health-bar/XP-bar reveals, sprite walk cycles
- Transitions: pixel dissolve/iris
- Sound: chiptune, blip text SFX
- Rights: Pixel fonts named are OFL. Generate all sprites in code; no copied game art.

```text
Make a 45-second 16:9 explainer on [TOPIC] styled like a retro pixel-art game with HyperFrames.
16-colour palette, pixel font (Press Start 2P), `image-rendering: pixelated`, animation stepped at 8 fps. A dialogue box types the narration; each fact is a "level" with a progress bar; key numbers appear as XP/score counters.
Transitions are pixel-dissolve or iris wipes. Chiptune loop, blip SFX per typed letter, level-up jingle at the end.
Render MP4 and keep all sprites generated in code (no copied game art).
```

## Journalism, maps and data

### Map-and-annotation video essay (`map-annotation-essay`)

Inspired by map-driven video essays. HyperFrames + Remotion + d3-geo + MapLibre GL JS, 16:9, about 60 s. https://24fps.dev/explainers#map-annotation-essay

- Palette: muted terrain/satellite or flat dark map, one bright highlight (red/orange) for the subject region
- Type: clean sans callouts, serif headlines
- Motion: camera swoop from globe to region, border outlines draw on, arrows/routes animate, labels pop with a tick
- Transitions: zoom-through map to footage
- Sound: low drone/pulse underscore, soft whoosh on camera moves
- Rights: Use open data only: Natural Earth is public domain, world-atlas and d3-geo are ISC. Do not use satellite imagery whose terms limit reuse. Remotion needs a company licence in some cases.

```text
Make a 60-second 16:9 map-driven explainer on [TOPIC] with [HyperFrames | Remotion].
Build the maps from open data only (d3-geo + world-atlas TopoJSON, Natural Earth). Dark muted base map, one orange highlight for the subject region.
Beats: globe overview, camera glides in to the region, borders draw on, a route/arrow animates, three callout labels pop in with leader lines, one key number counts up.
Add a small source caption on screen. Narration [TTS], low drone bed, whoosh on each camera move. Render MP4.
```

### Clean logistics map and flow (`flat-logistics-infographic`)

Inspired by logistics and economics explainer channels. Remotion + HyperFrames + d3-geo, 16:9, about 90 s. https://24fps.dev/explainers#flat-logistics-infographic

- Palette: pale warm-grey or white bg, saturated route lines (blue, orange), pastel land
- Type: neutral grotesque
- Motion: routes animate as moving dots, bars grow, icons (plane, ship, truck) travel along paths, numbers tick
- Transitions: simple pans and slides
- Sound: understated light music, no SFX clutter
- Rights: Remotion needs a company licence in some cases; HyperFrames is Apache-2.0. Use only data you can cite, and cite it on screen.

```text
Make a 90-second 16:9 explainer on how [TOPIC] works as a flow of goods or money, with HyperFrames or Remotion.
Light grey background, pastel flat map, two saturated route colours. Icons travel along curved paths; bars and counters animate with the narration; simple labelled diagrams for each stage.
Calm, measured pacing: one stage per 12 seconds, a recap diagram at the end. Use only numbers from [source URL/CSV] and cite them on screen.
Narration [TTS], quiet minimal music, almost no SFX. MP4 out.
```

### Geopolitics dark-map documentary (`geopolitics-dark-map`)

Inspired by geopolitics and economics channels. Remotion + HyperFrames + d3-geo, 16:9, about 120 s. https://24fps.dev/explainers#geopolitics-dark-map

- Palette: black/charcoal bg, muted red and amber, white labels, faint grid
- Type: condensed sans for place names, serif for titles
- Motion: slow push-ins, borders shift over time, arrows for flows and conflicts, timeline scrubber
- Transitions: dissolve through archival still, dip-to-black
- Sound: tense low strings, long reverb hits
- Rights: Supply only images you are licensed to use. Natural Earth borders are public domain. Remotion needs a company licence in some cases.

```text
Make a 2-minute 16:9 dark-map explainer on [TOPIC] with HyperFrames or Remotion.
Black/charcoal map, muted red for the actor, amber for the contested area, white labels in a condensed sans. Slow push-ins; borders and arrows change with a visible year counter at the lower left.
Between map sections, show a still-image placeholder card with a caption and slow pan-and-zoom drift (I will supply licensed images).
Narration [TTS], low tense drone, soft impact hit on each major event, dip-to-black between chapters. MP4 out.
```

### Data-journalism animated chart (`data-chart-journalism`)

Inspired by newspaper data-journalism charts. Remotion + HyperFrames + D3, 16:9, about 30 s. https://24fps.dev/explainers#data-chart-journalism

- Palette: warm paper tone (own salmon/cream hex), one strong accent line, greys for context
- Type: serif headline plus small sans labels; annotations in italic
- Motion: grey context lines draw first, accent line draws last, annotation fades in with an arrow, axis labels direct on-line
- Transitions: chart morphs between types
- Sound: very quiet bed; tick on reveal
- Rights: D3 is ISC. Use your own colours rather than a publication's palette. Never invent data; cite the source on screen. Remotion needs a company licence in some cases.

```text
Make a 30-second 16:9 animated chart on [TOPIC] from this data: [CSV/URL]. Use [Remotion | HyperFrames + D3].
Warm paper background, serif headline stating the finding, small sans axis labels written directly on the lines (no legend box). Draw the grey context series first, then reveal the accent series last; add one italic annotation with a thin arrow at the key moment.
End with a source line. Never invent data. Quiet bed, soft tick on the reveal. Also export a 1080x1080 version.
```

### Bar-chart race (`bar-chart-race`)

Inspired by bar-chart-race explainers. Remotion + HyperFrames + D3 + racing-bars, 1:1, about 40 s. https://24fps.dev/explainers#bar-chart-race

- Palette: bright distinct bar colours per category on white or dark
- Type: bold sans value labels, large year counter in the corner
- Motion: bars overtake with eased rank swaps; counter ticks
- Transitions: none, continuous
- Sound: upbeat steady beat
- Rights: racing-bars and D3 are open source (MIT, ISC). Cite the data source on screen. Remotion needs a company licence in some cases.

```text
Make a 40-second 1080x1080 bar-chart race of [TOPIC] using [CSV]. Use Remotion or HyperFrames with D3.
Top 10 bars, rank swaps eased over 0.5s, per-category colours, labels inside bars, a giant year counter at the bottom right, one-line annotations when a leader changes.
Upbeat steady beat, tick when the leader changes. Cite the data source on screen. MP4 out.
```

### Animated timeline with parallax (`timeline-history`)

Inspired by history and space-timeline videos. Remotion + HyperFrames, 16:9, about 60 s. https://24fps.dev/explainers#timeline-history

- Palette: dark bg, one era-coded accent per period
- Type: big year numerals plus a serif body
- Motion: horizontal timeline scrolls, cards slide in with year numerals, icons parallax
- Transitions: scroll-through
- Sound: light underscore, tick per era
- Rights: Use only dates you can cite. Icons are drawn in SVG; no third-party art needed.

```text
Make a 60-second 16:9 timeline of [TOPIC] with 6-8 events using HyperFrames or Remotion.
Dark background, a horizontal timeline that scrolls with easing; each event lands with a giant year numeral, a one-line title, and a simple icon drawn in SVG. Use a different accent colour per era.
Add subtle parallax (two background layers). Narration [TTS] with the year spoken at each event, tick SFX on landing. Use only dates from [source] and cite it. MP4 out.
```

### News lower-third and ticker package (`news-lower-third-pack`)

Inspired by broadcast lower thirds and tickers. HyperFrames + Remotion, 16:9, about None s. https://24fps.dev/explainers#news-lower-third-pack

- Palette: brand colour block + white, high contrast
- Type: bold condensed sans (Barlow Condensed, Oswald) plus light sans for the sub-line
- Motion: bar wipes in, text slides after the bar, hold 4-5s, wipes out; ticker scrolls
- Transitions: bar wipe
- Sound: short whoosh
- Rights: Original shapes and colours only; do not copy a broadcaster's graphics. Fonts named are OFL.

```text
Create a 1920x1080 transparent-background lower-third pack for [TOPIC / show name] with HyperFrames (alpha output).
Three variants: (1) one-tier name; (2) two-tier name + role; (3) three-tier with a timestamp tag. A coloured bar wipes in (0.35s), text slides out of it (0.25s delay), holds 4s, exits in reverse.
Add a bottom ticker that scrolls [3 headlines] at constant speed. Stay inside the title-safe area. Short whoosh on enter. Export each as WebM with alpha, plus a preview MP4.
```

### Newspaper headline highlight (`headline-highlight`)

Inspired by newspaper headline-highlight clips. HyperFrames + Remotion, 4:5, about 20 s. https://24fps.dev/explainers#headline-highlight

- Palette: newsprint off-white, black serif, yellow marker highlight, a red underline
- Type: Playfair Display/Libre Caslon plus mono for dateline
- Motion: article clipping slides in, key phrase gets a marker swipe, zoom to the sentence, annotations scribble
- Transitions: page flip or cut-in zoom
- Sound: paper rustle, marker swipe
- Rights: Quote under 15 words and credit the publication on screen. Fonts named are OFL.

```text
Make a 20-second 1080x1350 "headline highlight" video for this article: [TOPIC / URL / quote], using HyperFrames or Remotion.
Newsprint background, black serif headline, dateline in monospace. Animate: article card slides in, the key phrase gets a yellow marker swipe, zoom into that sentence, a red hand-drawn underline appears, then a one-line takeaway.
Paper-rustle on entry, marker-swipe SFX, soft cut. Quote under 15 words only and credit the publication on screen.
```

## Collage and hand-made

### Paper collage explainer (`paper-collage-explainer`)

Inspired by Vox, paper-collage explainers. HyperFrames + Remotion, 16:9, about 60 s. https://24fps.dev/explainers#paper-collage-explainer

- Palette: kraft brown, off-white, one punchy red/blue/yellow
- Type: cut-out letter blocks (Bowlby One, Rubik Mono One) plus a typewriter face
- Motion: stepped 12 fps jitter, elements slide in with a slight rotation, drop shadows, hand-drawn arrows self-draw
- Transitions: paper-wipe, tear reveal
- Sound: warm acoustic bed, paper slap SFX, soft pop
- Rights: Draw the paper pieces yourself in SVG or CSS. Fonts named are OFL. Do not reuse any outlet's artwork.

```text
Make a 60-second 16:9 paper-collage explainer on [TOPIC] with HyperFrames.
Kraft-paper background with a subtle moving texture, torn-edge shapes, hand-cut-style illustrations (drawn in SVG with rough edges), labels set as cut-out letter blocks, hand-drawn arrows that draw themselves.
Animate everything stepped at 12 fps (use GSAP steps) with 1-2 degree wobble; drop shadow under every piece. One idea per scene; each scene gets a different paper colour accent.
Warm acoustic bed, paper-slap SFX on arrival. Narration [TTS]. MP4 out.
```

### Surreal cut-out animation (`cutout-surreal`)

Inspired by cut-out collage animation. HyperFrames, 16:9, about 30 s. https://24fps.dev/explainers#cutout-surreal

- Palette: sepia/muted photographic textures, harsh outlines, Victorian engravings
- Type: old serif/typewriter
- Motion: jointed puppets with limited rotation joints (hinged), jerky pops, things slide on and off, absurd scale shifts
- Transitions: object swallows the frame
- Sound: brass/oompah, slide-whistle, drop-in thuds
- Rights: Use public-domain engravings and photographs only (for example from public-domain archives), never film frames.

```text
Make a 30-second 16:9 absurdist cut-out animation about [TOPIC] with HyperFrames.
Characters and props are flat cut-outs from public-domain engravings/photos (I will supply the folder), with hinged limbs rotating around pivots; movement is stepped and jerky.
Props slide on and off, scale absurdly, and one big object swallows the screen as the transition. Sepia texture, thin torn outlines, serif captions.
Brass-band loop with slide-whistle and thud SFX. MP4 out.
```

### Claymation look (`claymation-look`)

Inspired by stop-motion clay animation. HyperFrames + Three.js + Remotion, 1:1, about 15 s. https://24fps.dev/explainers#claymation-look

- Palette: saturated plasticine colours, soft warm key light, shallow depth of field
- Type: chunky rounded (Fredoka, Baloo 2) looking like rolled clay
- Motion: 12 fps stepped movement, slight "boil" in outlines and textures, squash
- Transitions: none or cut
- Sound: foley (squishes), quirky score
- Rights: Three.js is MIT. Fonts named are OFL. Materials are generated in code.

```text
Make a 15-second 1080x1080 claymation-look animation about [TOPIC] with Three.js in HyperFrames.
Plasticine-style materials: rounded geometry, bump-mapped fingerprint noise, soft warm key light with shallow depth of field. Drive animation on twos (update every 2nd frame at 24 fps) and add a subtle per-frame geometry wobble ("boil").
Chunky rounded title in clay colours. Foley squish SFX, quirky pizzicato loop. Render MP4.
```

### Sketchbook doodle explainer (`sketchbook-doodle`)

Inspired by notebook doodles and sketchnotes. HyperFrames + rough.js, 9:16, about 45 s. https://24fps.dev/explainers#sketchbook-doodle

- Palette: cream grid/dot paper, ink blue, highlighter yellow/pink
- Type: handwriting (Gochi Hand, Kalam)
- Motion: doodles draw, highlighters swipe, sticky notes slap on, washi tape
- Transitions: page-turn
- Sound: pen scratch, paper flip
- Rights: rough.js is MIT. Handwriting fonts named are OFL.

```text
Make a 45-second 9:16 sketchbook-doodle explainer on [TOPIC] with HyperFrames and rough.js.
Dot-grid cream paper, blue ink doodles drawn stroke by stroke, highlighter swipes on key words, sticky notes that slap on with a tiny rotation, tape strips. Handwriting font (Kalam).
One idea per page; page-turn transition between pages. Word-timed captions at the bottom. Pen-scratch + page-flip SFX, light lo-fi bed. MP4 out.
```

### Comic-book halftone pop (`comic-halftone`)

Inspired by pop-art and comic panels. HyperFrames + Remotion, 9:16, about 30 s. https://24fps.dev/explainers#comic-halftone

- Palette: CMYK-primary flat colours, black ink outlines, halftone dots
- Type: comic lettering (Bangers, Comic Neue)
- Motion: panels pop in on a grid, speech bubbles scale-pop, impact bursts, onomatopoeia stamps
- Transitions: panel slide, whip-pan
- Sound: punchy hits
- Rights: Halftone is pure CSS. Lettering fonts named are OFL. Draw your own characters.

```text
Make a 30-second 9:16 comic-book style video about [TOPIC] with HyperFrames.
Panel grid with thick black borders, halftone-dot shading (CSS radial-gradient pattern), primary-colour flats. Panels pop in one by one; speech bubbles scale-pop with a tail; bursts and onomatopoeia ("BOOM") stamp on impacts.
Snappy hits and whooshes on each panel; short upbeat loop. MP4 out.
```

## Product, launch and brand

### Premium product reveal (`device-reveal`)

Inspired by premium keynote-style product reveals. HyperFrames + Three.js + Remotion, 16:9, about 15 s. https://24fps.dev/explainers#device-reveal

- Palette: pure black and soft grey-white scenes, product lit with a single rim light, one subtle gradient
- Type: Inter (stand-in; SF Pro is proprietary), weight 600, tight tracking
- Motion: slow ease-out cubic rise, depth-of-field, light sweep across edges, text appears as relevant then exits
- Transitions: dip to black, match-cut on shape
- Sound: low sub swell, single clean chime, minimal music
- Rights: Use your own product model or a generic one. No stock footage, no fake UI and no logos you do not own. Inter is OFL.

```text
Make a 15-second 1920x1080 premium product reveal for [PRODUCT / TOPIC] with HyperFrames (Three.js adapter).
Pure black background, the product centred, single rim light. 1.5s ease-out-cubic rise from below with a 35 to 8 degree tilt and scale 0.8 to 1.0; a soft light sweep along the edge.
Then one short statement per scene in Inter 600, tight tracking, white on black, timed to the beat; alternate with a pale grey scene. No stock footage, no fake UI, no logos.
Sub-bass swell into a single chime, minimal pad. Render MP4 and a 9:16 cut.
```

### Tech-review B-roll (`tech-review-broll`)

Inspired by flagship tech-review channels. HyperFrames + Remotion, 16:9, about None s. https://24fps.dev/explainers#tech-review-broll

- Palette: black, deep red/accent, clean product-on-matte-surface
- Type: bold geometric sans; spec callouts in mono
- Motion: slow macro slider/orbit shots, whip-cut to spec cards, floating callout arrows, on-screen spec comparisons
- Transitions: whip-pan, glitch-light
- Sound: sync bass hits to cuts, electronic bed
- Rights: Overlay package for your own footage. Use only a music track you have the rights to.

```text
Create a spec-card and callout overlay package for a 16:9 tech review of [PRODUCT], using HyperFrames over my footage.
Elements: (1) intro title card, (2) animated spec table that fills row by row, (3) floating callout with an arrow pointing at a spot on the product, (4) side-by-side comparison bars, (5) verdict score card.
Black + one accent colour, bold geometric sans, mono for specs. Cards enter with a short whip; hold 3s. Cut on bass hits of the track I supply. Export transparent WebM per element plus a demo MP4.
```

### SaaS launch video (`saas-launch-video`)

Inspired by developer-tool launch videos. HyperFrames + Remotion, 16:9, about 30 s. https://24fps.dev/explainers#saas-launch-video

- Palette: dark gradient bg (deep indigo to black), neon accent glow, soft grid
- Type: Inter/Geist-like (use Inter) headlines, mono for code
- Motion: UI cards with rounded corners fly in with depth and blur, cursor clicks trigger changes, glow pulses, number counters
- Transitions: zoom into a UI element becomes the next scene
- Sound: tight synth pulses, click SFX, riser into logo
- Rights: Use your own product screenshots and claim no features that do not exist. Inter is OFL.

```text
Make a 30-second 1920x1080 launch video for [PRODUCT: one-line pitch] with HyperFrames or Remotion.
Dark indigo-to-black gradient, faint grid, neon accent glow. Structure: pain hook (0-4s), the product in 3 UI cards that fly in with depth blur (4-20s), one proof number counting up, call-to-action with the URL.
A cursor clicks a button and the UI reacts; zoom into one element to transition to the next. Headlines in Inter 700; code in a mono font. Use my screenshots from [folder], no invented features.
Synth pulse bed, click SFX, riser into the end card. MP4 + 9:16 cut.
```

### Product demo with cursor zoom (`cursor-zoom-demo`)

Inspired by polished screen-recording demos. HyperFrames + Remotion, 16:9, about None s. https://24fps.dev/explainers#cursor-zoom-demo

- Palette: soft gradient wallpaper around a rounded window, subtle shadow
- Type: minimal captions
- Motion: smooth cursor path, auto-zoom to the click target, motion blur, keystroke chips
- Transitions: crossfade between recorded segments
- Sound: soft click and key SFX only
- Rights: Open-source screen recorders can produce the cursor log. Record only content you have the right to show.

```text
Turn my screen recording [file] into a polished 1920x1080 product demo with HyperFrames or Remotion.
Place the video in a rounded window with a soft shadow on a subtle gradient wallpaper. Auto-zoom (1.0 to 1.6, ease in-out 0.6s) to each click or typed region using the cursor log in [json] or detected from the video; smooth the cursor path; show keystrokes as small chips.
Add 4 short captions (max 6 words) at the key moments. Trim dead time over 1s. Soft click SFX only. MP4 out.
```

### Cinematic tech intro/trailer (`cinematic-tech-intro`)

Inspired by cinematic trailers and tech intros. HyperFrames + Three.js + Remotion, 16:9, about 12 s. https://24fps.dev/explainers#cinematic-tech-intro

- Palette: near-black with teal/orange or monochrome, lens flare, volumetric haze
- Type: wide-tracked uppercase sans (Syncopate, Michroma) with slow fade
- Motion: slow camera push, parallax particles, title letters resolve from blur, light streaks
- Transitions: flash, light-leak
- Sound: braam, riser, deep hit
- Rights: Three.js is MIT. Fonts named are OFL. Flares and haze are generated in code.

```text
Make a 12-second 1920x1080 cinematic intro for [TOPIC / product] with HyperFrames.
Near-black scene with volumetric haze and drifting particles, a slow push-in, a moving lens flare crossing the frame. Title in wide-tracked uppercase (Syncopate), letters resolving from blur on the beat.
Hit the title on 0:07 with a flash; end with the tagline at 60% opacity. Deep riser into a single impact. MP4 + loopable 6-second version.
```

### Glass UI motion (`liquid-glass-ui`)

Inspired by glassmorphism interface motion. HyperFrames + Three.js, 1:1, about 15 s. https://24fps.dev/explainers#liquid-glass-ui

- Palette: pastel gradient blobs behind translucent frosted panels, white inner highlights
- Type: rounded clean sans
- Motion: panels float, refract, morph shape, spring to hover
- Transitions: panels morph into the next layout
- Sound: airy chimes
- Rights: Pure CSS and SVG filters. Fonts are OFL.

```text
Make a 15-second 1080x1080 glass-UI motion piece about [TOPIC / feature list] with HyperFrames.
Soft pastel gradient blobs drifting behind frosted-glass panels (backdrop-filter blur 24px, 1px white border, inner highlight). Panels spring-in, float, and morph from one shape into the next to show each feature.
Rounded clean sans, 3 features with 4-word labels. Airy chime SFX, soft pad. MP4 out.
```

### Year-in-review story cards (`year-in-review`)

Inspired by Spotify Wrapped, story-format year-in-review cards. Remotion + HyperFrames, 9:16, about 25 s. https://24fps.dev/explainers#year-in-review

- Palette: saturated flat colour fields that change per card, one gradient accent
- Type: very heavy display sans (Anton, Bricolage Grotesque; the real campaign face is proprietary)
- Motion: oversized numbers slam in, stat cards stack, quick colour wipes, confetti
- Transitions: swipe/colour-block wipes
- Sound: upbeat beat that builds
- Rights: Use fonts that are OFL; the original campaign typeface is proprietary. Remotion needs a company licence in some cases; HyperFrames is Apache-2.0. Batch-render only with data users agreed to share.

```text
Make a 25-second 1080x1920 "year in review" story for [TOPIC] using this data: [JSON], with Remotion or HyperFrames.
Six cards, each a different flat saturated colour with one oversized number or word in a heavy display sans, plus a one-line caption. Cards enter with colour-block wipes; numbers slam in with overshoot and count up; confetti on the last card.
Upbeat beat that builds, tick on each number. Parameterise by data so I can batch-render for many users. MP4 per user.
```

### Swiss/Bauhaus grid motion (`swiss-grid-motion`)

Inspired by Swiss and Bauhaus design. HyperFrames, 16:9, about 20 s. https://24fps.dev/explainers#swiss-grid-motion

- Palette: white/black with one red, strict grid
- Type: Inter Tight/Archivo, huge numerals, flush-left
- Motion: modular blocks slide on a grid, lines extend, rotating geometric forms, type snaps to baseline
- Transitions: grid-reflow
- Sound: minimal percussion, clicks
- Rights: Fonts named are OFL. All shapes are generated in code.

```text
Make a 20-second 1920x1080 Swiss-grid motion piece presenting [TOPIC: title + 3 facts] with HyperFrames.
12-column grid, white background, black type (Archivo / Inter Tight), a single red accent block. Blocks slide and snap to grid positions on every beat; huge flush-left numerals; thin rules extend to connect facts.
Hard, exact easing (expo.out), no shadows or gradients. Minimal percussion and click SFX. MP4 out.
```

### Brutalist kinetic type (`brand-sizzle-kinetic`)

Inspired by neo-brutalist kinetic type. HyperFrames, 9:16, about 20 s. https://24fps.dev/explainers#brand-sizzle-kinetic

- Palette: black/white plus acid yellow or primary red, thick borders, hard offset shadows
- Type: grotesques at huge scale (Anton, Space Grotesk, Archivo Black), mono secondary
- Motion: hard cuts on beat, text stacking/overlapping, slam-and-shake, marquee strips, word flashes
- Transitions: hard cut, invert-flash
- Sound: kicks and clap, metal hits
- Rights: Fonts named are OFL. Use a beat you made or licensed.

```text
Make a 20-second 1080x1920 brutalist kinetic-type video of this script: [TOPIC / 6-10 short lines] using HyperFrames.
Black, white and one acid-yellow; 4px black borders and hard offset shadows; giant grotesque type (Anton) filling the frame; mono sub-labels.
Each line hard-cuts on the beat (120 BPM), words stack and overlap, marquee strips run behind, invert-flash on emphasis. Slight shake on key words.
Kick + clap track, metal hit on the last line. MP4 out.
```

## Creator and social edits

### Retention-optimised creator edit (`retention-edit`)

Inspired by retention-style creator edits. HyperFrames, 9:16, about None s. https://24fps.dev/explainers#retention-edit

- Palette: saturated, high contrast, bright yellow/white captions with black stroke
- Type: heavy sans (Bangers/Anton/Luckiest Guy)
- Motion: punch-ins, bounce zooms, shake, pop captions, emoji/sticker pops, quick B-roll inserts
- Transitions: whip, zoom, flash
- Sound: whooshes, pops, risers, "bwoom" hits
- Rights: Edit only footage you own. Caption fonts named are OFL; use sound effects you have the rights to.

```text
Re-edit my video [file] into a fast retention-style 9:16 cut using HyperFrames.
Rules: a visual change at least every 2 seconds (punch-in, bounce-zoom, B-roll insert, or text pop); word-timed captions in a heavy sans, yellow with black stroke, key word scaled 1.3x; SFX on every cut (whoosh, pop, riser into reveals).
First 2 seconds: the strongest line as on-screen text plus a zoom. Remove silences over 0.3s. Keep the pacing human, not strobing; allow 2 breathing shots.
Output MP4 and a list of the cuts.
```

### Educator talking head with callouts (`educator-talking-head`)

Inspired by productivity educators. HyperFrames, 16:9, about None s. https://24fps.dev/explainers#educator-talking-head

- Palette: warm, bright, pastel overlays on a clean desk setting; handwritten accents
- Type: friendly sans (Poppins/DM Sans) plus handwritten notes
- Motion: numbered list cards pop, doodle underlines, sticker cut-outs of the speaker, screen-inset B-roll, chapter title cards
- Transitions: jump cuts with small zoom
- Sound: light upbeat music, pop SFX
- Rights: Overlay layer for your own footage. Fonts named are OFL; use music you have the rights to.

```text
Add an overlay layer to my talking-head video [file] (16:9) with HyperFrames.
Detect the 5 key points from the transcript; for each, show a numbered card in a friendly sans with a hand-drawn underline; add a chapter title card at each topic change; pop a simple doodle icon beside key nouns.
Alternate a 1.05x punch-in every other cut. Word-timed captions at the bottom third in white with a soft shadow. Light upbeat bed at -22 dB under speech, pop SFX on cards. Output MP4 and chapter timestamps.
```

### Podcast clip (`podcast-clip`)

Inspired by audiogram-style podcast clips. HyperFrames + Remotion, 9:16, about 60 s. https://24fps.dev/explainers#podcast-clip

- Palette: dark brand-colour gradient, speaker photo circles, white captions with highlighted word
- Type: bold sans captions
- Motion: waveform reacts to audio, speaker name chips swap, word-by-word highlight, progress bar, show-cover bug
- Transitions: crossfade between speakers
- Sound: the audio itself
- Rights: Use audio and speaker photos you have permission to publish. Whisper is MIT.

```text
Turn this podcast audio [file, 30-60s] into a 1080x1920 clip with HyperFrames or Remotion.
Dark gradient background, round speaker photos [files] that scale up for the active speaker, an audio-reactive waveform in the lower third, big word-timed captions with the current word highlighted, a thin progress bar at the very top, show name and episode title chip at the start.
Transcribe with Whisper for word timestamps. No music. Output MP4 and the SRT.
```

### Kinetic lyric video (`lyric-kinetic`)

Inspired by kinetic lyric videos. HyperFrames + Remotion, 16:9, about None s. https://24fps.dev/explainers#lyric-kinetic

- Palette: bold two-colour per verse, textured
- Type: expressive display fonts with variations per line
- Motion: words appear on the sung syllable with size/weight tied to loudness; text rotates and tracks
- Transitions: type wipes
- Sound: the track
- Rights: Use only a track and lyrics you own or have licensed.

```text
Make a 1920x1080 kinetic lyric video for my own track [audio file] with lyrics [text], using HyperFrames.
Align lyrics to the audio (forced alignment, word timestamps). Each line is a typographic scene: size and weight scale with loudness, key words in a contrasting display face, words slam in on the beat and exit with a wipe.
Palette changes per section (verse, chorus). No stock footage. Render MP4 and keep the alignment JSON.
```

### Anime-opening title sequence (`anime-opening`)

Inspired by classic anime title sequences. HyperFrames, 16:9, about 30 s. https://24fps.dev/explainers#anime-opening

- Palette: black/white cards, sudden saturated sunsets, speed lines, film grain
- Type: heavy Mincho for title cards, tiny sans credits
- Motion: fast pan-and-scan on illustrations, speed lines, flash frames, freeze with outline, text stacked vertically
- Transitions: hard cuts on drums, flash cuts
- Sound: high-energy rock/pop track, drum fills, impact hits
- Rights: The original title face is commercial; use an OFL substitute (Shippori Mincho B1). Use only your own art and a track you have licensed.

```text
Make a 30-second 1920x1080 anime-opening-style sequence for [TOPIC / show concept] with HyperFrames.
Beat-cut to [BPM]. Mix: black title cards with heavy Mincho serif text (Shippori Mincho B1 ExtraBold) stretched and cropped for drama; pan-and-scan over illustrations I supply; speed-line overlays; 2-frame white flashes; a freeze-frame with an outline pulse on the last beat.
Credits in tiny sans. Film grain + slight chromatic aberration. Use only my art and my licensed track. MP4 out.
```

### Beat-synced fan edit (`beat-edit-amv`)

Inspired by beat-synced fan edits. HyperFrames, 16:9, about None s. https://24fps.dev/explainers#beat-edit-amv

- Palette: footage-driven, with glow/bloom, RGB-split, shake grade
- Type: minimal, lyric lines optional
- Motion: cuts exactly on drum hits, speed ramps, zoom-hits, strobe on drops
- Transitions: whip, glitch, flash
- Sound: the track
- Rights: You supply the clips and the track, and you need the rights to both.

```text
Cut my clips [folder] to my track [audio] as a beat-synced 1920x1080 edit with HyperFrames.
Detect beats and drops; cut on strong beats, never mid-beat. Add: speed-ramp into each drop, zoom-hit on snares, RGB-split flash on the drop, 2-frame strobe on the final hit, soft bloom grade.
Keep each shot at least 6 frames. I own the clips and licence the track; no external footage. Output MP4 and a cut list.
```

## Documentary, film and retro

### Documentary photo pan (`doc-photo-pan`)

Inspired by documentary slow pan and zoom on stills. HyperFrames + Remotion, 16:9, about 90 s. https://24fps.dev/explainers#doc-photo-pan

- Palette: sepia/black-and-white archival, vignette, grain
- Type: classic serif captions
- Motion: slow push-in on a face or detail, lateral pan between subjects, 2.5D parallax from depth maps
- Transitions: slow crossfade, dip-to-black
- Sound: fiddle/piano score, letters read aloud, ambient sound
- Rights: Public-domain or licensed stills only; credit each image on the final card. Remotion needs a company licence in some cases.

```text
Make a 90-second 16:9 documentary sequence on [TOPIC] from public-domain stills I supply in [folder] using HyperFrames or Remotion.
Each still: 8-10s slow push-in or lateral pan toward the detail mentioned in the narration, vignette + film grain; optional 2.5D parallax from a depth map. Slow crossfades; dip-to-black between chapters.
Serif lower-third captions for dates and places. Narration [TTS reading quotes in a period tone], gentle piano/strings bed, ambient room tone. Credit each image on the final card.
```

### Retro VHS camcorder (`retro-vhs`)

Inspired by 1990s camcorder tape looks. HyperFrames, 16:9, about 10 s. https://24fps.dev/explainers#retro-vhs

- Palette: desaturated warm with magenta/cyan fringing, scanlines
- Type: pixel timestamp (VT323) in orange; "PLAY ▶" OSD
- Motion: tracking glitches, jitter, tape rewind noise bars, date stamp
- Transitions: static burst, rewind
- Sound: tape hiss, mechanical clunk, VCR beeps
- Rights: VT323 is OFL. Effects are generated in code; use footage you own.

```text
Apply a 1990s VHS camcorder look to my clip [file] (16:9) with HyperFrames and write a 10-second title sequence for [TOPIC].
Effects: scanlines, 12% chromatic fringing, horizontal tracking glitches every 3-4s, slight vertical jitter, soft bloom, desaturated warm grade, 4:3 pillarbox option.
On-screen display: orange pixel date/time stamp (VT323) and a "PLAY" OSD at the start; rewind noise bars as the transition. Tape hiss + clunk SFX. Output MP4.
```

### Vaporwave / synthwave (`vaporwave-synth`)

Inspired by vaporwave and synthwave art. HyperFrames + Three.js, 16:9, about 20 s. https://24fps.dev/explainers#vaporwave-synth

- Palette: pink/cyan/purple gradient sunset, grid floor
- Type: fullwidth latin, chrome serif (Playfair/Syncopate), Japanese katakana accents
- Motion: infinite grid scrolling toward a sun, slow rotating bust, floating shapes, scanlines
- Transitions: glitch, fade
- Sound: slowed, reverb-heavy, chorused synth
- Rights: Three.js is MIT. Fonts named are OFL. Models are low-poly and generated in code.

```text
Make a 20-second 1920x1080 vaporwave loop about [TOPIC] with Three.js in HyperFrames.
Pink-to-cyan gradient sky with a striped sun, an infinite perspective grid scrolling toward the horizon, a slowly rotating low-poly bust or object, floating geometric shapes, light scanlines.
Title in fullwidth characters plus a katakana tag; chrome gradient text. Seamless loop. Slow reverb-heavy synth bed. MP4 + loop.
```

### Lo-fi study loop (`lofi-study-loop`)

Inspired by lo-fi study-stream loops. HyperFrames + Three.js, 16:9, about 30 s. https://24fps.dev/explainers#lofi-study-loop

- Palette: dusk purples/oranges, warm lamp glow, window rain
- Type: tiny handwritten "now playing" tag
- Motion: tiny loops (rain, curtain, cat breathing, steam), parallax, 2-4 frame loops
- Transitions: none (continuous)
- Sound: dusty jazz-hop beat, vinyl crackle, rain
- Rights: No copyrighted music: use a track you made or have licensed.

```text
Make a seamless 30-second 1920x1080 lo-fi scene about [TOPIC / room] with HyperFrames.
Cosy room at dusk: lamp glow, rain on the window, steam from a mug, a cat breathing, slow parallax between 4 layers. Warm purple-orange palette, soft grain and slight vignette.
Every element loops independently so the whole clip tiles at exactly 30s. Tiny handwritten "now playing" tag. Add vinyl-crackle and rain ambience; no copyrighted music. MP4 + loop.
```
