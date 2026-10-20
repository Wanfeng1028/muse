# Direction: brief, story, script, pacing, storyboard

Contents
1. Order of work
2. Brief and intake
3. Pitch round for vague requests
4. Story doctrine
5. Structure and hooks
6. Script and narration
7. Pacing and rhythm
8. Music-driven pacing
9. Storyboard formats
10. Per-beat direction
11. Honesty
12. Pre-build self-check

---

## 1. Order of work

Layers of truth: BRIEF (why, for whom) → STORYBOARD (what, frame by frame) → design spec (how it looks) → code.
Each layer only consumes the one above.

1. Brief → one-sentence message → named arc → beat list with VO → proposal in chat.
2. Stills sheet with real copy, real fonts, real colours (Remotion: one `<Still>` per beat, or
   `scripts/stills.py` on each beat's key second). The reviewer judges placement, hierarchy and copy here.
3. Lock (`## Locked` in CREATIVE.md) → time-coded shot design → build.
4. After the build, the code is the truth: regenerate the timing table from the composition and the VO word
   timings, update the storyboard, state the final length. Every shipped film drifts from its storyboard.

- A changed frame in the proposal costs seconds; after the build it costs minutes.
- Arrive as the director, not the contractor: the first proposal is the full treatment (arc, design, motion per
  scene, transitions, sound identity or a chosen silence, a designed open and close). The user trims down.
- A confirmed storyboard sheet is a valid deliverable when the user only asked for a plan.

## 2. Brief and intake

BRIEF frontmatter (lives at the top of `CREATIVE.md`; template in `assets/CREATIVE.template.md`):

```markdown
---
workflow: launch | explainer | demo | overlay | captions | social-cut | music | remake
message: "<the ONE thing, as a claim>"
audience: <who>
destination: <x-feed | reels | youtube | website | whatsapp ...>
formats: [1920x1080, 1080x1920]
length: 45s
language: es-CO
angle: <arc>
narration: yes | minimal | no
reference_style: "<named reference, e.g. Stripe docs, Apple bumper>"
---
## Intent        what, for whom, why now; tone in the user's own words
## Assets        path: what it is, where it belongs
## Facts         link to facts.md (every number, source, date)
## Notes         constraints, references, things to avoid
```

- Do not storyboard until `message` is one sentence written as a claim ("Close isn't final", not "About the
  inspector").
- Derive aspect from destination and say so: feeds 1080x1080 or 1080x1350 (4:5), Reels/Shorts/TikTok 1080x1920,
  YouTube/web 1920x1080, LinkedIn feed 1080x1350.
- Ask only what changes the output; recommended option first with a reason; one topic per question; option lists
  for factual fields, an anchored open question for creative ones. After the answers, surface consequences the
  combination creates. Summaries separate what was stated from what you inferred.
- Named reference style, always. "Premium modern" is not a direction.
- Facts file: every on-screen number with its source and date. No facts file, no numbers on screen.
- Reference video given: extract a frame every 0.5 s, write a style guide (palette hex, type, shot lengths,
  transitions, camera, texture, text in/out) and a shot list on the beat grid. Take the grammar, never the content,
  logos, music or voice; credit the original.
- Ask whether a supplied script is `verbatim` (segment it, never change words) or `restructure` (rewrite, reorder,
  merge to fit the arc and length).

## 3. Pitch round for vague requests

Use when the ask is unformed ("make something cool for the launch"). First ask what the user already pictures; an
existing idea becomes a pitch and is never displaced.

Internal gate before pitching: what does the subject look like; what does the target emotion look like as a frame
(longing = empty space, urgency = compression, awe = one element too large for the canvas); what does the playback
surface demand (lobby = glanced, feed = fights for second 1, story = vertical and fast); what does every other video
on this subject look like (the anti-pattern).

Five concepts, one per path: the subject's world, the emotion, the audience (meet or break expectation), the
anti-pattern inverted, an unusual format (a letter, countdown, recipe, front page, map). At least two must be ideas a
model would rarely produce. Two concepts with the same rough layout are one concept. Present each in three lines
(concept sentence, visual world, opening hook), show all five, then recommend one. Mixing is a valid answer.
Autonomous runs still walk this gate and report the obvious direction they deliberately left behind.

For "I know nothing about video": give a map of 2 to 3 decisions (where it plays, how long, how it should feel), each
with 2 to 4 options and a default.

## 4. Story doctrine

- **The hook speaks the viewer's language**: gain, avoid, finally understand. No internal vocabulary (file, function,
  API names, feature lists). Numbers only when they carry stakes ("40% faster"), never inventory ("23 files changed").
- **Reverse iceberg** (persuasion formats: promos, demos, explainers, ads): the message lands by beat 2; everything after
  is evidence. Test: delete the evidence beats and the value must still stand; delete the value beats and if it still
  "works", it was a feature tour. Story formats (brand films, founder stories, documentaries, trailers) land the question
  or stakes by beat 2 and the message at the turn.
- **Every beat's why traces to the message**, and the message includes the feeling: a breath beat that serves the
  emotional arc stays; anything untraceable is cut.
- **Visuals come from the source.** Mine the product's phrases, entities, verbs and motifs for props. If a prop could
  appear unchanged in another product's video, it didn't come from this one.
- **A website is an information layout; a video is an emotional sequence.** Reorder, merge, omit. The most common
  failure is paraphrasing the source in order.
- Extract the truth first. Product: audience, pain or desire, promise (one-line thesis), product role, proof, CTA.
  Explainer: audience, gap and stakes, thesis, spine (3 to 6 ideas), evidence, landing.
- One job per beat; never "another benefit".
- **The differentiating moment gets the most screen time.** Find the one beat only this product can deliver; the rest
  of the film sets it up. Never spread the runtime evenly across features.
- **Launch and promo films show the product within 3 s.** Lead with the viewer's problem, but the product is on screen
  by 3 s.
- **Ground the problem in something viewers recognise without explanation.** If the pain needs a sentence to be
  understood, the hook is too abstract.
- **End card: one headline and the CTA**, using the landing page's real tagline, not a punchier invention. Add a
  supporting line only when the CTA needs explaining.
- **Spine device**: name the one thing that threads every beat (a persistent window, a hero object, one background
  that leads every transition). A **hero prop** persists and returns; a callback beat states which earlier beat it
  answers.
- **Product-film chain**: problem in the client's own words (3 to 5 s), then each step produces what the next uses
  (the object leaving a step becomes the next scene), measurable result, offer, CTA. Steps 2 to 7 s.
- **Show the behaviour, not only the artefact.** A mechanism beat animates what the product does (cache filling,
  serial becoming parallel). Alternate artefact beats (screens) with mechanism beats; all-screens reads flat.
- A UI demo is a sequence of 3+ beats on one surface (input → response → result → benefit), not a single frame.
- Sell from the pain, comfort rather than frighten, when the brief is emotional: name the pain the viewer recognises,
  then relieve it. Never stage direct fears.

## 5. Structure and hooks

Structures (ABT, story spine, story circle, SCQA, SB7, PAS, BAB, keynote reveal, trailer, testimonial, founder, tutorial,
documentary paper edit), the framework chooser, ads by length and the hook system live in the scriptwriting skill (`references/structures.md`, `references/hooks.md`). Pick the
structure there and write the reason in one line in CREATIVE.md.

**Beat metadata** worth writing for each beat: `type` (hook, pain, product intro, feature, benefit, proof, branding, CTA), a
named `persuasion` move (pain agitation, negative contrast, friction reduction, show-don't-tell proof, feature→benefit,
risk reversal, future pacing, value stacking, analogy, worked example, before/after, callback), the `emotion` with its
`+/−` turn (valley: anxiety, frustration, curiosity → pivot: clarity, anticipation → build: "aha", confidence →
resolution: relief, control, urgency to act), `narrativeRole` ("concretises compound interest as a snowball", not "shows
a chart") and `keyMessage` (one sentence the viewer keeps).

**Visual beat shapes** that carry well: a widget that morphs into the whole product; demo | value line | demo sandwich;
cause→effect couplets ("drag the value: the button follows"); a close-up mystery that zooms out on the landing line;
milestones marching across time; tools piling in until they bury the viewer; a count-up cold open; a calm, near-still end card
(one headline and the CTA). Escalation and ticker shapes ("Hard. Insanely hard.", "A doc? A wiki? No: all of them.") are AI tells:
at most one per film, on purpose (scriptwriting skill, `references/craft.md`).

## 6. Script and narration

Writing the script (process, writing for the ear, AI tells, localisation, self-tests, A/V and beat-sheet formats) is
the scriptwriting skill; performing it with a generated voice is the voice-direction skill. Two rules that shape the storyboard:

- The voice is the clock: retime scenes to real word timestamps; never rush a read to fit a slot; a VO regen reopens every
  seam it touches.
- With captions running, on-screen motion type is short copy (a hero word, a stat), never the narration repeated.

## 7. Pacing and rhythm

- Declare the rhythm before building (`fast-fast-SLOW-fast-HIT-hold`, `hook-PUNCH-breathe-CTA`), derived from brand
  and content, not a lookup. Peak energy where the narration's heaviest emphasis lands.
- Don't overstuff: 15 s cannot carry hook + 3 features + CTA. Ask how many beats the length supports.
- Beats (one idea) run 1.5 to 3.5 s; a beat that must be read ~3 s; a 5 to 7 word line 2 to 2.5 s. Scenes group
  several beats. Sum durations by arithmetic.
- Text on screen for 3 s must be readable in 2. Every element finishes animating and stays readable at least 1.5 s.
- Something new every 2 to 4 s; the hook lands in the first 2 s (0.5 s for short motion graphics).
- **Never front-load**: at t=0 show only what the voice is saying; reveal each further piece when it is named, spread
  across the shot, especially its back half. Window count = number of spoken cues.
- **Holds are deliberate**: allocate at least one beat where the main element is still while the line lands, and a
  0.3 to 0.75 s pause between a major action and its result. A fully frozen frame mid-film for more than ~1 s means the
  plan ran out of story: add story, not wobble. The final hold is exempt.
- **Pause test**: stop at any second; something meaningful should be mid-flight or deliberately held.
- Name a sustained-motion route per scene: staged reveals on narration beats, camera with intent (wide → travel →
  arrive), sequenced UI life (progress advances, counts tick), animated sequences (a card files into a stack),
  cursor-led action.
- Scene phases: build (0 to 30%), breathe (30 to 70%, filled with story), resolve (70 to 100%).
- Speed carries weight: 0.15 to 0.3 s energy; 0.3 to 0.5 s professional; 0.5 to 0.8 s gravity; 0.8 to 2 s cinematic.
  The slowest scene ~3× slower than the fastest.
- The film's first motion starts 0.1 to 0.2 s in (zero delay reads as a jump); seam entries start on their first frame.
- Time is hierarchy: what appears first is most important; stagger by importance, total ≤ 0.5 s per beat.

## 8. Music-driven pacing

- Cut at real musical changes (hard stops, drops, start and end of rolls, big energy jumps); snap every boundary to
  an anchor; no fragment shorter than a bar.
- Per section decide `beat_cut` (rhythmic, dense, steady grid: cuts may anchor to beats) or `phrase_flow` (calm or
  sparse: pace by phrases and energy, long holds, slow transitions). Beat trackers invent grids on calm music.
- A readable message holds at least one beat (headline 3 to 8 beats, sentence 4 to 10). Anything shorter is texture.
- The key visual (flood, logo, reveal) lands on the drop. Reveals may shift up to 0.15 s (small entrances 0.10 s) to
  snap onto a cue. The closing logo lands on the final hit and holds through the ring-out.
- Tempo feel: 60 to 80 BPM regal, 90 to 110 smooth, 115 to 123 sophisticated, above 125 hype.
- Footage on a `beat_cut` section: one clip per strong anchor, hero clip on a downbeat. On `phrase_flow`: one clip
  with a slow push, background clips dimmed 30 to 50% under text.

## 9. Storyboard formats

**Decisions header** (above the first beat): message; audience + arc in one line; format (aspect, length, VO, music);
spine device; brand tokens by role with hex, three type roles with sizes, radii, easings, each with its source;
per-film bans (no glow, no fake UI, no static end card) plus the two motion failures (slideshow: every beat a fresh
card; screensaver: motion that says nothing); held-frame allocation; the direction current (motion.md §8).

**Beat row**:

| Field | Rule |
|---|---|
| Heading | `NN · Name (start–end, ~dur)`, absolute times summing to the target |
| On screen | concrete objects, counts, positions; every on-screen word verbatim in quotes |
| Voiceover | verbatim, or `onscreen` for silent films; reveals land on the naming word |
| Hero prop | object that persists, and the beat where it returns |
| Motion | named moves from a small vocabulary |
| Seam out | named transition + direction |
| Audio cue | an SFX for every animated event (sound + time) and any music cue; an event left silent says why |
| Constraint | at least one explicit "no …" where the beat could go generic |
| Why | the beat's job, traced to the message |
| Truthfulness | where the film depicts something real, what is real |

**Proposal in chat**: "This video tells [audience] that [message]." then the frame table, then a style and duration
footer, then "approve or adjust".

```
| Frame            | Beat      | On screen                                          | Why                            |
| 01 · Not anymore | hook · 3s | States the old pain and resolves it in one breath. | Lands the value claim in beat 1 |
```

Record feedback verbatim under `## Changes from v1`, open questions under `## Still open`, bump the version, revise only
the named beats.

**Time-coded shot sequence** (per beat, at build time):

```
- focal: assets/reject-stat.png (or an invented hero element)
- roles: stat = cutout · timer = supporting · backdrop = background (dim ~40%)
- sfx: impact-soft, riser
Shot 1 (0.0–1.2 s): only what the VO says at t=0; layout by name ("centred, ~50% of frame")
Shot 2 (1.2–3.4 s): next piece reveals as the VO names it ("asymmetric 60/40, three depth layers")
Shot 3 (3.4–5.0 s): content resolved; hold the read
```

Layout and motion by name in the plan; pixels and easing curves belong to the build.

**Seam handoff**: when an element continues across a boundary, write its exact position, scale, opacity, direction and
speed at the cut, so parallel builders don't invent two versions.

**Stills sheet**: header (title, version, one-line dek, resolution, length, beat count); a grid of cells in order,
grouped by act; each cell the key moment with real words in real fonts and colours; label `NN · NAME / start–end`; a
note on what moves first and which way the seam goes; closing cells with the seam map and the token cell.

**Music storyboard**: duration equals the track; style and ≤ 6 swatches quoted from the design spec; per frame
`span_sec`, `pacing` (beat_cut or phrase_flow), `mood`, one-line `feel` ("accelerating onset stream into a held
downbeat"); anchors are real track seconds.

## 10. Per-beat direction

- Each beat is a world, not a layout. Write the experience first, then the pixels. Weak: "Dark navy bg, $1.9T in
  white, 280 px." Strong: "The camera is already mid-flight over a vast dark field; $1.9T slams in so hard the field
  ripples."
- Per beat: concept (2 to 3 sentences: world, metaphor, feeling), mood (cultural or design references, not hex),
  choreography (a verb per element), transition out, depth layers (at least 2), SFX cues.
- Motion verbs by character: impact (SLAMS, PUNCHES, STAMPS, DROPS), directional (SLIDES, PUSHES, WIPES), builds
  (DRAWS, FILLS, GROWS, ASSEMBLES, COUNTS UP), organic (FLOATS, DRIFTS, ORBITS, MORPHS), mechanical (TYPES ON,
  CLICKS, LOCKS IN, SNAPS). If you can't name the verb, the element isn't designed yet.
- Transitions carry meaning: crossfade "this continues", hard cut "wake up", slow dissolve "drift with me", push "next
  point". Spectacle transitions only for the centrepiece (1 to 2 per film). Budget 2 to 3 transition types per film.
- Carriers: the eye follows objects. The strongest seams hand a concrete object across the cut (a cursor mid-path, a
  container that docks into the next layout, a mark flying into its slot). Mechanics in `motion.md` §8.
- Causal motion: each move visibly launched by the last (click → squash → release → flight → impact → reveal).
- One visual system start to end, transformations not cuts; one thing moves at a time unless a single driver moves
  everything.
- **Silent one-sentence test**: muted, a viewer should summarise the shot in one sentence. Hesitation means too much
  moves. The automated version is the restate test in `qa.md`.

## 11. Honesty

- Zero fabrication: real data is sourced on screen ("12 answers · 25 Sep 2026"); illustrative content is labelled
  "Example data" or "Illustration"; never claim a feature that doesn't exist (check the code).
- No invented figures, KPIs, dates, counts, testimonials or stats. Render a placeholder (`— figure —`) until the script
  supplies a sourced number.
- Captions and posts stay true about the making ("made in 10 minutes", "one shot", "no tools" only if true).
- Remakes take the grammar, credit the original, never reuse its music, voice, people or logos; never imply a
  partnership between brands.
- People in the film: generated or illustrated, names that match faces, never a real person without consent; say so in
  the README.

## 12. Pre-build self-check

- Structure named with a reason; sequence narrative-driven, not source order; hook written as three tracks; message (or
  stakes, for story formats) by beat 2; the script passed the scriptwriting self-tests and the anti-AI pass.
- Each beat: one job, a named persuasion move, a specific emotion; VO written in cues; beat shapes vary.
- The emotional arc moves (valley → pivot → build → resolution).
- Durations sum to the target; holds allocated; no front-loading planned.
- Every visual prop traceable to the product; every number traceable to `facts.md`.
- 2 to 3 transition types and one direction current; at least three framings, never the same framing twice in a row.
- Tokens quoted from the design source; nothing invented.
