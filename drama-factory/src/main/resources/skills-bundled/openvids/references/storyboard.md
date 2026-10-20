# Storyboarding a launch film

A storyboard turns a product brief into 45 to 120 seconds of scenes. Each scene has one hero moment and one motivated transition out. Write it before any scene code. Every scene designer works from it, together with `design-system.md` and the handoff table.

The worked example is the 75-second film in `examples/droid-launch`. Its scene code is in `examples/droid-launch/src/scenes/S1.tsx` through `S8.tsx`, and its cues are in `examples/droid-launch/src/timeline.ts`.

## Collect verified facts before any picture

A launch film makes claims at 120px. A wrong claim at that size is the first thing a viewer screenshots.

1. Read the brief and list every claim it makes: features, benchmark results, prices, plan limits, supported models, and availability.
2. Find a primary source for each claim, such as the pricing page, the leaderboard, the changelog, or the docs. Record the URL and the date you checked it.
3. Write the facts sheet. Each row is one claim, its exact on-screen wording, its source, and the check date.
4. Move every claim without a source to an open-items list. It does not go on screen.
5. Hand the facts sheet to every scene designer. Designers put only facts-sheet wording on screen.

Some claims need extra rules.

- Benchmark claims name the benchmark, the result, and the date of the result. The example's caption reads "Terminal-Bench · #1 · Sept 2025 · same models, better harness". The direction dropped the date until the parent verified it.
- Competitors stay anonymous ("harness A", "Plan B") and get no invented numbers. Rival bar lengths and scores come from the same published source as the product's number, or the rivals get no scale at all. No competitor logos.
- Prices and multipliers are copied from the pricing page and written as the page writes them ("~5x Pro").
- Numbers about the film itself, such as tokens, cost, and agent count on the example's receipt, come from a data file the pipeline writes (`examples/droid-launch/src/usage.json`). A scene renders a placeholder dash while a value is zero.

## Follow seven beats

Each beat is one scene. Merge or split beats to fit the runtime, but keep their order. Each beat answers the viewer's next question.

| Beat | Job | Share of runtime | Example scene and seconds |
|---|---|---|---|
| hook | name the product with one surprising move | 8% | S1, 6s. A cursor types the name and unfolds into the logo. |
| claim | state the premise the film argues | 13% | S2, 10s. "Same models." Five model chips and a grid of identical inputs. |
| proof | show one verified number that supports the claim | 13% | S3, 10s. "Different harness." A bar race locks at the benchmark score. |
| product in action | a real UI doing a real task | 16% | S4, 12s. A terminal fixes flaky CI with five subagents. |
| offer | pricing and its limit, then the answer | 13% + 16% | S5, 10s. Plans hit their rate limits. S6, 12s. A separate pool keeps working. |
| thesis | one sentence the viewer repeats | 11% | S7, 8s. "Open models ⊕ their own pool." |
| sign-off | the product mark plus one memorable proof | 9% | S8, 7s. A receipt prints what the film cost. |

- A scene runs 6 to 12 seconds. The floor comes from the timing rules. One entrance (21 frames), a 4-word text hold (32), a hero hold (24), an exit (14), and a morph (33) add up to 124 frames, or about 4 seconds, before any content moves.
- For a 45-second film, merge claim and proof into one scene and cut the offer to one scene.
- For a 120-second film, add a second product-in-action scene. Do not stretch holds. Longer holds become dead air.
- The offer beat can state a limit only when the next beat answers it. In the example, the limit appears in neutral colors and the accent arrives with the answer.

## Pick one hero moment per scene

The hero moment is the frame range a thumbnail of the scene would show. Write it down before anything else in the scene.

- Write it as a frame range, what is on screen, and the beat it proves. For example, "S3, 170 to 228, `58.75%` locks at 112px beside the leading accent bar while the other bars recede."
- Describe it in one sentence without "and then". Two events mean two heroes, so cut one.
- It must read at 480px wide in 1 second.
- It holds for at least 24 frames with only the camera moving.
- Everything else in the scene either builds toward the hero or clears the frame for the transition out.

The hero moments in the example film:

| Scene | Frames (local) | Hero |
|---|---|---|
| S1 | 78 to 105 | the cursor collapses to a point and the logo unfolds out of it |
| S2 | 190 to 240 | a calm 5x4 grid of identical nodes, one per model per harness |
| S3 | 170 to 228 | the score hard-locks beside the leading bar |
| S4 | 210 to 258 | five completion checks cascade in time with a musical chord |
| S5 | 228 to 240 | every meter and ring reads 100%, and nothing moves for 12 frames |
| S6 | 200 to 300 | "Usage ran out. Work *didn't.*" over the spent meter, the live meter, and the model pool |
| S7 | 177 to 195 | the product card alone at center under the thesis |
| S8 | 130 to 176 | the stamp lands on the printed receipt beside the lockup |

## Motivate every transition

Each transition says how the last object of one scene becomes the first object of the next. A transition without a motive is a crossfade, and crossfades are banned. Every boundary state below is rendered with a shared component at default props (see `design-system.md`).

### The object becomes the next scene's object

Use this when the next scene is about the thing you just showed. It is the strongest transition, so make it the default.

- S3 to S4. The winning bar morphs into the terminal window over 33 frames. Its fill turns from accent to surface, and the header row draws in. The boundary state is the terminal window with its accent border and header.
- S2 to S3. The five model chips stay in place across the cut and then collapse into one "same 5 models" pill. The boundary state is the chip row.
- Inside S4, the five plan steps become the five subagent rows. Their text slides right and role labels reveal beside them. The objects you read are the agents you watch.

### A shape morphs into a simpler shape

Use this to close a dense scene and open a sparse one. Reduce the content to a line, a dot, or a mark, then build the next scene out of it.

- S4 to S5. The terminal collapses into a 1440x4 accent line at y 778, like a shutter closing. The content stays registered, so it clips instead of squashing. The pricing cards then rise from behind that line. The boundary state is the line.
- S6 to S7. The spent meter becomes the horizontal bar of a ⊕ and the live meter rotates into its vertical bar. The circle draws around them. The boundary state is the 200px ⊕. In S7 the ⊕ shrinks into the headline as a glyph.
- S1. The cursor contracts to a 12px dot at the logo's hub, and the logo's radial sweep grows out of the dot.

### A mask reveals from an edge already on screen

Use this inside a scene to bring in new objects without inventing an entrance. The mask edge is an object already on screen, such as a line, a meter, or a frame edge.

- S5. The pricing cards rise from behind the accent line.
- S6. The second meter rises from behind the first ("separate pool"), and the model chips pour out from under it.
- S7. Rival cards fall away through the frame bottom after they grey out.

### A page turn changes the world

Use this once, when the film moves from the dark background to the light one and the argument turns.

- S5 to S6. The pricing card turns over. The flip is faked in 2D with `scaleX = |cos(πp)|` around the card's moving center, and the faces swap at `p = 0.5`. At the same time the card's rectangle morphs to the full frame over 36 frames. The back face is the light page with the usage meter already in place. No gradient shading. The boundary state is the full meter on the light background.

### A zoom fills the frame with an object

Use this to end on the object the viewer should remember. Animate the rectangle's geometry to (0, 0, 1920, 1080). Never `scale()` a DOM rectangle more than 1.5x.

- S7 to S8. The product card's content exits through its own clip, and the card's geometry grows to the full frame over 34 frames. The boundary state is the solid dark background.
- S1 to S2. The logo is SVG, so it may scale from 1 to 120 while it spins, until its dark fill covers the frame. The boundary state is the solid dark background.

### A freeze with silence before a turn

Use this once per film, on the frame the problem peaks. Every value locks on one frame, the music drops out, and nothing moves for 12 frames except the camera. Then the next transition fires.

- S5, frames 228 to 240. Every meter and ring reads 100% and its label switches to "limit". The page turn starts at frame 252.

## Fill in the storyboard table

Copy this table and fill one row per scene. Seconds are absolute. Frames in the hero and cue columns are scene-local.

| # | Seconds (from to, duration) | Picture | Hero moment (frames) | Transition out and boundary state | Cues (frames) |
|---|---|---|---|---|---|
| S1 | | | | | |
| S2 | | | | | |

The example film's table:

| # | Seconds | Picture | Hero moment | Transition out and boundary state | Cues |
|---|---|---|---|---|---|
| S1 | 0 to 6 (6) | light. A cursor types the product name, then unfolds into the logo. | 78 to 105, the logo grows out of the cursor | logo spins and scales to fill. Solid dark. | keys 30, 36, 41, 48, 54. enter 66. form 78. spin 132 |
| S2 | 6 to 16 (10) | "Same models." Chips land and a grid of identical nodes forms. | 190 to 240, the 5x4 grid | the grid retracts into the chips. The chip row. | headline 20. chips 40, 52, 64, 76, 88. lanes 130 |
| S3 | 16 to 26 (10) | "Different harness." A bar race. | 170 to 228, the score locks | the winning bar becomes the terminal. The terminal window. | headline 10. race 60. win 170. grow 250 |
| S4 | 26 to 38 (12) | A terminal types a task. Plan steps become subagents. | 210 to 258, five checks | the terminal shutters into a line. The accent line. | keys 20 to 70. spec 100. fan-out 150. checks 210, 222, 234, 246, 258. merge 300 |
| S5 | 38 to 48 (10) | Pricing cards rise from the line. Limit rings fill to 100%. | 228 to 240, freeze | the card turns over. The full meter on light. | cards 20, 32, 44. fill 120. full 228. flip 252 |
| S6 | 48 to 60 (12) | A second meter rises. Models pour in. "Usage ran out. Work *didn't.*" | 200 to 300, the full board | the meters fold into ⊕. The 200px ⊕. | rise 24. models 70 to 154, every 12. caption 200. merge 318 |
| S7 | 60 to 68 (8) | The ⊕ becomes a glyph in the thesis. Rival cards fall away. | 177 to 195, the card alone | the card zooms to fill. Solid dark. | line 1 at 10. line 2 at 70. falls 110, 122, 134. zoom 196 |
| S8 | 68 to 75 (7) | A receipt prints the film's real cost. A stamp lands. The paper tears. | 130 to 176, the stamped receipt | the paper drops. Solid dark, end. | print 20, then lines 34 to 94, every 12. stamp 130. tear 176 |

## Turn the table into a timeline

1. Convert every row to frames at 30 fps and write scene starts, durations, and cues to one timeline file. The video and the audio build both read it.
2. Give every cue one visual event. Most cues also get a sound. `sound.md` says when to leave one silent. In the example, keystrokes click, chips land on an ascending pentatonic, checks ping and build a chord, and the freeze is silent.
3. Write the handoff table from the transition column, with exact geometry for every boundary state.
4. Add each boundary object to the shared components file with defaults equal to its boundary state.
5. Give each scene designer the storyboard, the facts sheet, the handoff table, and the shared components. Designers never edit the timeline or the shared files.

## Check the storyboard before design starts

- [ ] Every on-screen claim is in the facts sheet with a source and a check date.
- [ ] No competitor has an invented number or a logo.
- [ ] The runtime is 45 to 120 seconds, and every scene runs 6 to 12 seconds.
- [ ] Every scene has one hero moment, written as a frame range, that holds for at least 24 frames.
- [ ] Every transition names the object that crosses the cut, and its boundary state is in the handoff table.
- [ ] The film uses the page turn once and the freeze once at most.
- [ ] The accent appears only on the product, and a limit or problem stays neutral until the answer.
- [ ] Open items list every unverified fact and every missing data value.
