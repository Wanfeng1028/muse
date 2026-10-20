# DIRECTION — Droid launch film, polish pass

Four designers work in parallel: **A = S1+S2, B = S3+S4, C = S5+S6, D = S7+S8**. You never talk to
each other; this file, `HANDOFF.md`, and the shared components are the contract. Read all three.

## 0. Diagnosis of the draft (what we are fixing)

The structure is right. The execution reads as a wireframe:

- **Scale is timid.** Terminal text 20–30px in a 1200x800 window. The film's most important
  number (58.75%) is 40px mono. Chips are 26px. Meter labels and captions are 18–22px. At
  1080p after h264, anything below 24px turns to mush, and anything below 32px looks like UI
  documentation, not a launch film.
- **Lines vanish.** 1px `#2A2A26` on `#0E0E0C` and 1px `#EAE4D8` on cream are nearly invisible.
  The S3 losing bars, the S2 lanes, and the S6 chip borders all disappear.
- **Dead space and dead time.** Compositions hug the top half (S5 cards, S7 thesis) and leave the
  bottom 40–50% empty. The S4 terminal sits 80% empty for 5 seconds (frames 0–150). The S3→S4
  handoff shows an empty rectangle for about 35 frames. S1→S2 is 28 frames of pure black.
- **Orange is overused.** In S4 the border, chevron, cursor, five underlines and five checks
  are all orange at once, so nothing is the focus.
- **Placeholder data.** S8 prints `tokens 0`, `$0.00`, `≈0.0%`. See Open items.

## 1. Global system (already in `src/theme.ts` and `src/components.tsx`, do not edit them)

### 1.1 Type scale (px). Nothing on screen is ever smaller than 24.
| Token | px | Face | Tracking | Use |
|---|---|---|---|---|
| `T.numeral` | 200 | Geist 600, tabular | -0.05em | hero numbers |
| `T.display` | 168 | Geist 600 | -0.045em, lh 0.92 | at most one per scene: "Same models.", end lockup |
| `T.headline` | 120 | Geist 600 | -0.04em, lh 1.0 | scene headlines |
| `T.thesis` | 104 | Geist 600 | -0.04em | S7 single-line thesis only |
| `T.title` | 64 | Geist 600 | -0.03em | card titles at hero size |
| `T.sub` | 44 | Geist 500 | -0.02em | supporting sentence |
| `T.body` | 36 | Geist 500 | -0.01em | sans UI labels |
| `T.monoLg` | 40 | Geist Mono 400 | 0 | terminal prompt |
| `T.mono` | 30 | Geist Mono 400/500 | 0 | terminal rows, chart and meter labels |
| `T.meta` | 26 | Geist Mono 400 | 0 | captions, sources, header rows |
| `T.floor` | 24 | — | — | absolute minimum, avoid using it |

`Headline` now defaults to 120 and applies -0.045em at 168 and above. The serif italic `Accent`
appears at most once per scene, at the same size as its line. It takes the line's colour, except
in S6, where "didn't." is orange because that word *is* Droid's point.

### 1.2 Grid and margins
- 12 columns: margin 120, gutter 24, column 118. `colX(i)` = left edge of column i. Content
  lives in x 120..1800. Vertical safe area is y 96..984.
- Left-aligned headlines start at x 120 exactly. Centered layouts center on x 960.
- The optical center is y 520, not 540. Center compositions on 500–540, never above 480.

### 1.3 Colour and contrast
| Token | Hex | Rule |
|---|---|---|
| `C.ink` / `C.cream` | `#0E0E0C` / `#F4F0E8` | the only two backgrounds |
| `C.inkSoft` | `#1A1A17` | surfaces on ink (cards, terminal, chips) |
| `C.inkLine` | `#3A3934` (raised from 2A2A26) | 2px rules and borders on ink; fill for losing/recessive bars |
| `C.mute` | `#A39E93` | secondary text on ink (7.4:1). On cream it is ONLY the greyed or disabled state |
| `C.graphite` | `#6E6A62` | secondary text on cream (4.9:1). **Never on ink** |
| `C.creamDeep` | `#E6E0D3` (deepened) | meter tracks and recessed fills on cream. Not for lines |
| `C.creamLine` | `#D6CEBE` (new) | 2px rules and borders on cream |
| `C.paper` | `#FBF9F4` | paper objects on cream |
| `C.orange` | `#EE6018` | **Droid, and only Droid** (see 1.6) |

`C.green` is banned. Primary text is `C.cream` on ink and `C.ink` on cream.

### 1.4 Lines, surfaces, depth
- Every rule, border and connector is **2px** (`HAIR`). 1px is banned. Use inset box-shadow
  (`inset 0 0 0 2px color`) for borders on morphing rects so the size math stays exact.
- Radii: chips 18, cards 24, terminal 28, meters h/2, bars 12.
- Ink surfaces: `inkSoft` fill plus a 2px `inkLine` inset border. No shadows on ink.
- Cream paper objects (S6 model chips, S7 plan cards, S8 receipt edge if wanted):
  `C.paper` fill, 2px `creamLine` inset border, and `SHADOW_PAPER`. This is the only shadow in the film.
- **Grain or texture: forbidden.** h264 at crf16 turns grain into crawling mush and banding,
  and the Claude reference look is flat and exact. Premium comes from scale, contrast, spacing
  and timing. No gradients, vignettes, noise, blur, or glow.

### 1.5 Component sizes
- **ModelChip:** 300x84, radius 18, 32px Geist 500, 12px dot, gap 28. The row spans x 154..1766. `CHIP.y` = 200.
- **Cards on ink (S5):** 440x520, radius 24. **Cards on cream (S7):** 372x236, radius 20.
- **Terminal:** `TERM` = 1440x840 at (240,120), radius 28, padding 64. Prompt is mono 40 with
  line-height 56. Rows are mono 30 at an 84px pitch.
- **Meters:** h 40 (hero, S5/S6) or h 12 (inside cards). Never thinner than 12.
- Status glyphs (✓): mono 34. Dots and nodes are at least 12px.

### 1.6 The one-accent rule
At any frame, orange appears on **one** idea: a single object, plus its own label if it has
one. Orange always means Droid: the S1 cursor, the S3 droid bar and label, the S4 completion
checks, the S6 Core meter, label and "didn't.", the S6/S7 ⊕, the S7 "+ Droid Core pool" line,
and the S8 stamp. It is never used for competitors, limits, warnings, generic UI or decoration.
The draft's S5 "limit reached" orange is removed. Exhaustion is cream/ink; orange arrives in S6
as the answer.

### 1.7 Camera
Every scene wraps its content (not the `Fill` background) in `<Camera dur={scene.dur}>`.
Camera is a push-in that peaks mid-scene and returns to exactly 1.0 on frame 0 and frame
dur-1, with zero velocity at both ends. Boundary frames stay pixel-exact and cuts carry no zoom hitch.
- Amounts: S1 **0** (the rotor zoom is the camera), S2 0.016, S3 0.016, S4 0.012, S5 0.016,
  S6 0.016, S7 0.016, S8 0.012.
- `originX/originY` = that scene's hero point (listed per scene below).
- Parallax: put captions and meta in a sibling `<Camera amount={0.008}>` layer. Never nest Cameras.
- No other camera moves. No pans, tilts, 3D swoops, or rack-focus blur.

### 1.8 Motion timing (frames @30)
- **Enter:** `tween` expo-out, 21 frames (range 18–27). It is always a masked move (`Reveal`,
  clip-path, or emerging from an on-screen object). Opacity-only entrances are banned.
- **Exit:** 14 frames, `EASE_IN`, faster than the entrance, through a mask or off a frame edge.
- **Morph** (geometry continuity, handoffs): `EASE_IN_OUT`, 30–36 frames. Animate
  left/top/width/height/radius directly. **Never `scale()` a DOM rect beyond 1.5x**: it blurs
  and distorts radii and borders. `scale` is only OK for SVG.
- **Stagger:** 3–4 frames, at most 5 items per chain. Larger sets stagger by row or column.
- **Hold:** after a hero lands, hold it at least 24 frames with only the camera moving. Text holds
  at least (words x 5 + 12) frames.
- **Dead air:** never more than 12 consecutive frames with only the camera moving, except the
  designated beats (S5 228–240 silence; boundary holds of 14 or fewer frames).
- Springs: `settle` stiffness 120–300 only (damping 200 means no overshoot). Constant rotation
  is allowed only for the rotor and the S4 status spinner.
- Counters use tabular-nums and are driven by the same curve as the bar or meter they describe.
- Colour or state changes (grey-out, ink→graphite) take 8–14 frames and are not a substitute for motion.

## 2. Boundaries (revised; exact values are in HANDOFF.md)
I revised four boundaries. **Render the shared component with default props on the handoff
frame**, so the cut matches by construction.
- **S2→S3**: same concept, with the new CHIP geometry (300x84 at y 200).
- **S3→S4**: `<TerminalFrame />`, larger (1440x840 at 240,120) and now **including the chrome**
  (header row and rule), so the handoff is never an empty box. S3 draws the chrome during its
  last frames.
- **S4→S5**: `<HorizonBar />` moved from y 538 to **y 778**, full TERM width 1440 at x 240. S5's
  cards stand on it, which centers the S5 composition instead of leaving the bottom half empty.
- **S5→S6**: `<StandardUsage />` is bigger: 1200x40 meter at (360,412), mono 30 labels at top 356.
- **S6→S7**: `<PlusMark />` is bigger: 200px, 8px stroke, 120px cross.
- S1→S2 and S7→S8 stay solid ink.

## 3. Per-scene direction

### S1 — Cursor → Rotor (0–179, cream → ink) · Designer A · Camera amount 0
**Weak:** a 46px prompt floating in a cream void for 66 frames. The rotor mark is only ~236px.
"Droid" is 64px and the credit is 20px.
**Hero:** frame 78–105, the cursor collapses to a point and the rotor unfolds out of it.
- Prompt: mono **88px**, single line, centered horizontally, vertically centered on y 470.
  "›" is `C.orange`. The typed text is `C.ink`. The cursor is a block 0.6em x 1.1em, `C.orange`,
  with a hard blink (15 on / 15 off, no fade) until frame 30. Reveal the chevron and cursor over 0–18.
- Keystrokes: one character per cue, exactly on the cue frame. The cursor advances one cell on the same frame.
- `enter` 66: the word exits upward through its mask (14f, EASE_IN). The cursor slides to the
  hub (960,470) and contracts to a 12px ink dot by 78.
- `rotorForm` 78: the rotor's radial sweep reveal grows out of the dot. **ROTOR_SIZE 560**
  (the mark is about 367px tall), hub at (960,470), rotation -120°→0 over 27f. Check frames 80–104
  at full res: the sweep edge must not show a hairline wedge or a polygon seam.
- 100: lockup under the mark. "Droid" is Geist 600 **120px**, centered, top 724.
  "by Factory" is mono 30 `C.graphite`, top 862. Both use masked Reveals, staggered 6f.
- `rotorSpin` 132: the lockup exits down through its masks (14f). The rotor scale goes 1→120,
  EASE_IN, over 40f around the hub, with rotation +900°. Ink covers the frame by 172; frames
  172–179 are solid ink.

### S2 — Same models (180–479, ink) · Designer A · Camera origin (960,520)
**Weak:** 28 black frames at the start, the headline shrinking to a timid 72px, 1px lanes that
vanish, 8px grey dots that read as noise, a 22px subtitle, and the drop "threads" that read as debris.
**Hero:** frames 190–240, a calm 5x4 grid of identical cream nodes, one per model per harness.
The picture says "same models, everywhere" with no words.
- Frame 0–20: "Same *models.*" in `T.display` 168, cream, centered, top 420. The Reveal **starts at
  frame 0** and settles exactly on cue 20, so the black gap is only S1's 8 frames.
- Subtitle at 30: "Every harness gets the same frontier models." `T.sub` 44 Geist 500 `C.mute`,
  centered, top 640, Reveal 21f.
- Chips: each drops from above the top frame edge into `CHIP.y` 200, landing **exactly** on
  `chipLand[i]` (keep the draft's normalized-spring trick). Delete the threads. On contact, the
  chip's dot goes mute→cream→mute over 12f; that is the only "impact" cue.
- 112–126: headline and subtitle exit up through their masks (14f, stagger 4).
- `lanes` 130: four lane rules at y **452, 588, 724, 860**, 2px `inkLine`, x 154→1766, drawn
  left to right over 27f, stagger 4. Each label sits above its rule at left 154, top (y-48),
  `T.meta` mono `C.mute`: "harness A", "harness B", "harness C", "harness D".
- 136: from each chip's bottom center (y 284), a 2px `inkLine` vertical drops to y 860 (30f,
  stagger 3). As it crosses each lane, a **20px cream node** appears at the intersection (12f expo-out
  from a 0px point). There are 20 nodes total, all identical and all on the same grid.
- Hold the full grid 190–240.
- 240–285: nodes shrink out column by column (12f, stagger 2). Verticals retract up into the chips
  (18f). Rules retract right to left (18f, stagger 3). Labels exit through their masks. From 285 only the chips remain (the boundary).

### S3 — Different harness (480–779, ink) · Designer B · Camera origin (960,560)
**Weak:** losing bars invisible, the hero number 40px, a 18px graphite caption on ink
(unreadable), a 20px pill, and an empty rectangle for about 35 frames at the handoff.
**Hero:** frame 170, `58.75%` hard-locks at 112px next to the leading orange bar while the
others recede.
- 0–10: hold the chips (boundary). `headline` 10: the chips collapse leftward into one pill at
  (120,120), 360x64, radius 32, `inkSoft` with a 2px `inkLine` border, reading "same 5 models"
  in `T.meta` `C.mute` (stagger 3, 24f, keep the draft's mechanic).
- 10: "Different *harness.*" `T.headline` 120 cream, left 120, top 216, Reveal 21f.
- Bars: rows at top **452, 556, 660, 764**, h 72, radius 12, x 420, max width 920. Labels at
  left 120 are `T.mono` 30, vertically centered on the bar: "harness A/B/C" in `C.mute`,
  "droid" in `C.orange` Geist Mono 500. Losing bars are `C.inkLine`; the Droid bar is orange.
  Keep the draft's race lengths and two-leg curve, with `raceStart` 60.
- Score: Geist 600 **112px** tabular, cream, left = Droid bar tip + 36, vertically centered on the
  Droid bar. It is driven by the bar curve and locks to "58.75%" exactly on `raceWin` 170. On
  lock, the losing bars recede to `#26251F` over 12f. That is the only lock flourish: no flash,
  no scale.
- Caption at 69: left 120, top 940, `T.meta` `C.mute`: "Terminal-Bench · #1 · same models,
  better harness". **Drop "Sept 2025"** unless the parent supplies a verified date.
- 228–249: everything except the Droid bar exits (headline and pill up through masks, losing bars
  retract right to left, labels, score and caption through masks; 14f, stagger 3).
- `growToTerminal` 250–283: the Droid bar morphs into `<TerminalFrame>` geometry
  (x/y/w/h/radius interpolated toward TERM, fill orange→`inkSoft`, 2px orange inset border), EASE_IN_OUT 33f, `chrome={0}`.
- 276–296: `chrome` goes 0→1 (tween 20f). 296–299: hold `<TerminalFrame />` defaults.

### S4 — Droid at work (780–1139, ink) · Designer B · Camera amount 0.012, origin (960,540)
**Weak:** small text, the window 80% empty until frame 150, too much orange, and invisible 1px progress lines.
**Hero:** 210–258, five checks cascade down the right edge in time with the chord.
Coordinates below are TERM-local (pass content as `TerminalFrame` children).
- 0–24: border colour orange→`inkLine` (14f, start at 6). From here on, orange inside the terminal = completion checks and the prompt chevron only.
- Prompt row top 148, x 64: "›" orange, then typed "fix flaky ci" in `T.monoLg` 40 cream,
  line-height 56. The cursor is a 22x44 **cream** block. Chevron and cursor appear at 6 (Reveal
  12f). One character per keystroke cue. The cursor shrinks away by `specOk`.
- `specOk` 100: row top 236: "✓" orange, "spec" cream 500, "  plan approved · 5 steps"
  `C.mute`, all `T.mono` 30. **New:** the five plan steps list immediately below (rows at top
  320 + i·84, x 64): "1  map the test suite", "2  patch retry logic", "3  pin node 24 in ci",
  "4  scan the diff", "5  run suite 3x" in `C.mute`, Reveal 18f, stagger 4 starting at 104. The window is now full by frame 124.
- `fanOut` 150: **the plan steps become the agents.** Each row's number exits up through its mask.
  The task text slides from x 64+48 to x 420 (morph 24f, stagger 4). The role label reveals at x 160
  (explorer / worker / worker / reviewer / validator, Geist Mono 500). The trunk (2px `inkLine`,
  x 96, from top 296 to the last row center) draws down, and branches curve into x 144 (radius 16).
  The status spinner on the right at x 1312 is a 28px quarter-arc, 3px `C.mute`, constant rotation.
- Progress rule under each row at top+58, x 160..1376, 2px: track `inkLine`, fill **cream**
  (not orange), filling from row start to that row's check cue.
- `checks[i]`: the spinner is replaced by "✓" in orange mono 34 (`settle` stiffness 200 from 0.9
  scale; SVG or text only). Role and task go mute→cream (8f). These five checks are the only orange in the frame.
- `merge` 300: rows collapse upward into a single line at top 320 (each row slides to 320 and
  clips away, 18f, stagger 2): "✓ 5/5 agents · ci green · 3 runs" (✓ orange, text cream). The trunk retracts.
- 318–350: the terminal collapses to `<HorizonBar>` geometry: y 120→778, h 840→4, radius 28→2,
  fill inkSoft→orange, border width 2→0. EASE_IN_OUT 32f. Content stays registered, so it is clipped
  like a shutter closing down. 350–359: hold `<HorizonBar />`.

### S5 — Plans + limits (1140–1439, ink → cream) · Designer C · Camera origin (960,520)
**Weak:** small cards crowded at the top with the bottom half empty, 160px rings with 18px
labels, an orange "limit" (wrong meaning), and a page turn with gradient shading.
**Hero:** 228–240, every meter and ring locks at 100% and **nothing moves for 12 frames** (the
silence in the score), then the card turns over to reveal the cream world.
- Cards stand on the bar: x **260, 740, 1220**, top 258, 440x520, radius 24, `inkSoft` with a
  2px `inkLine` inset border, clipped so they rise from behind the bar (container bottom = 778).
  Each rises 520→0 over 20f and lands exactly on `cards[i]` (starting at frames 0, 12, 24, so there is no dead air).
- Card content (local coordinates): name in Geist 500 40 cream at (44,44). Price in `T.numeral`-style
  Geist 600 **144px** (-0.05em) at top 112, with "/mo" in Geist 500 32 `C.mute` baseline-aligned
  (gap 10). Multiplier in `T.mono` `C.mute` at top 316: "baseline" / "~5x Pro" / "~10x Pro".
  **Capacity bar** at top 420, x 44, 352x12, radius 6: track `inkLine`, cream fill at **10% / 50% / 100%**,
  drawing in at land+6 over 21f. This is the visual proof of 5x/10x.
- 60–84: Pro and Plus sink back behind the bar (EASE_IN 14f, stagger 4). The bar retracts to
  Max's footprint (x 1220, w 440, 21f).
- 84–117: Max slides to x 260 (morph 33f) with its bar segment. The bar colour goes orange→`inkLine` by
  117 (orange leaves the scene). The Max border goes `inkLine`→cream.
- 94: inside Max, the capacity bar becomes the "Standard usage" meter. Its label row is `T.meta`
  `C.mute` at top 384, value right-aligned with tabular-nums. The fill resets to the usage curve.
- 94: "Rate limits · rolling" in `T.mono` `C.mute` at left 820, top 318. Three rings, **240px**
  diameter, 14px stroke, at left 820 / 1120 / 1420, top 398. Track `inkLine`, progress cream; the
  label inside is mono 44 cream ("5h", "7d", "30d"); the percentage below at top 664 is `T.mono`
  `C.mute` tabular. They rise from below through a mask (24f, stagger 4).
- `meterFill` 120 → `meterFull` 228: keep the draft's EASE_IN_OUT and exponents. At 228,
  every value reads 100% and each percentage label switches to cream 500 "limit" on the same frame.
  **228–240: freeze.**
- 240–252: rings and heading drop behind the bar line (EASE_IN 14f, stagger 3).
- `pageFlip` 252–288: **turn the Max card over.** Fake the flip in 2D: scaleX = |cos(πp)| about the
  card's moving center, swapping faces at p = 0.5, while the card rect morphs from
  (260,258,440,520,r24) to (0,0,1920,1080,r0), EASE_IN_OUT 36f. The back face is cream with
  `<StandardUsage />` laid out in frame coordinates (register it like TerminalFrame does). No
  gradient shading. 288–299: plain cream `Fill` + `<StandardUsage />`.

### S6 — Droid Core (1440–1799, cream) · Designer C · Camera origin (960,500)
**Weak:** an 800px meter stack with 22px labels floating in a big field, model chips with
invisible borders at 20px, and a headline that arrives late with nothing anchoring it.
**Hero:** 200–300, "Usage ran out. Work *didn't.*" over the full board: the spent ink meter, the live orange Core meter, and the pool of open models.
- 0: `<StandardUsage />`. At `coreRise` 24, the standard fill goes ink→graphite (14f) to read as
  spent. Its labels stay "Standard usage" / "100%" with no new text.
- `coreRise` 24: the Core block rises from behind the standard meter (mask top 452, 24f). The label
  row at top 496, `T.mono` orange: "Droid Core · separate pool" / "free". The meter is at y 552, 1200x40,
  track `creamDeep`, fill orange, progress 0→0.64 over 24–204 (EASE_IN_OUT).
- `modelsPour[i]`: eight paper chips "pour" out from under the Core meter (mask top 608). Each
  drops 18f and lands exactly on its cue. Two rows centered on 960, tops **660** and **752**,
  chip h 72, radius 16, padding 0 28, gap 16, `C.paper` with a 2px `creamLine` inset border and
  `SHADOW_PAPER`, `T.mono` 30 ink, auto width (measure via fixed per-name widths ≈ chars × 18 + 56).
  Order and rows as in the draft.
- `caption` 200: "Usage ran out." / "Work *didn't.*" in `T.headline` 120 ink, centered on one
  line, top 150. "didn't." is the orange Accent. Two Reveals at 200 and 210.
- 304–318: headline up through its mask, chips down behind their mask (stagger 2), labels
  through their masks; 14f.
- `merge` 318–351: the standard meter becomes the horizontal cross bar (1200x40 → 120x8 at
  center, ink/graphite→orange). The Core meter becomes the vertical bar (moves to center, shrinks to 120x8,
  rotates 90°). EASE_IN_OUT 33f. The circle draws 326–350 (`<PlusMark draw>`). From 351: `<PlusMark />` only.

### S7 — The thesis (1800–2039, cream → ink) · Designer D · Camera origin (960,480)
**Weak:** a 92px thesis with the bottom 55% empty, 300x200 cards with 18px text, the Droid card
overlapping a falling card mid-slide (frame ~160), and a 12x `scale()` zoom that blurs.
**Hero:** 177–195, the Droid card alone at center under the thesis, followed by the zoom into it.
- 0–24: `<PlusMark>` moves from (960,540)/200 to its inline slot: size 96, stroke 6, cross 56,
  vertically centered on the thesis line (center y 284). Morph 24f.
- `line1` 10: "Open models  ⊕  their own pool." `T.thesis` 104 ink, one line, centered,
  top 232. The left words unmask leftward and the right words unmask rightward, both out of the ⊕
  (keep the draft's clip idea). Measure the real widths with a still; the gap is 40px on each side of the mark.
- `line2` 70: "Every coding plan that survives will ship this." `T.sub` 44 Geist 500
  `C.graphite`, centered, top 392, Reveal 21f.
- 90: four cards, 372x236, gap 24, lefts **180, 576, 972, 1368**, top **580**, radius 20, rising
  40px through a clip (21f, stagger 4). Plan A/B/C: `C.paper`, 2px `creamLine`, `SHADOW_PAPER`, title
  Geist 600 40 ink, lines `T.mono` 28 `C.graphite`: "frontier models" / "one usage pool". Droid (4th):
  `C.ink` fill, `Rotor` 36 cream + "Droid" Geist 600 40 cream, lines cream / **orange** "+ Droid Core pool".
- `fallaway[i]`: the card greys (title and lines → `C.mute`, border to transparent, 8f), then falls
  (EASE_IN 24f, +620px, rotate at most 4°), clipped by the frame bottom.
- 150–177: the Droid card slides to center x 774 (morph 27f). It starts only after the last
  plan card has cleared its path. No overlaps, ever.
- `zoom` 196: thesis and subline exit up through their masks (14f). Droid card content exits up through
  its own clip (12f). The card **geometry** morphs to (0,0,1920,1080), radius 20→0, EASE_IN_OUT
  34f (196–230). Do not use a scale transform. 230–239: solid ink.

### S8 — Receipt (2040–2249, ink) · Designer D · Camera amount 0.012, origin (1380,480)
**Weak:** placeholder zeros printing as if they were real, a 22px receipt, and a dim printer slot.
**Hero:** 130, the SHIPPED stamp landing on a full receipt next to a 168px lockup.
- 4: lockup rises through its mask (21f). `Rotor` 132 cream plus "Droid" `T.display` 168 cream, left
  160, vertically centered on 520. "factory.ai" in `T.mono` 30 `C.mute` sits under the wordmark's
  left edge, 28px below, and reveals at 12.
- 10: the printer slot opens from its center (18f): x 1060, top 132, 640x16, radius 8, `inkSoft` with a 2px
  `inkLine` inset border.
- Paper: w 600, left 1080, emerging below the slot (top 148), PAPER_H 760, `C.paper`. Text is
  `T.mono` **28** with line-height 44 and padding 44. Rows: header (Rotor 32 + "DROID · RECEIPT", 500);
  a 2px dashed `C.graphite` rule; item; subagents; tokens; api cost; max plan used; a usage bar
  (12px, track `creamDeep`, fill orange); a rule; "billed  $0 extra" (mono 500 32). Keep the draft's
  discrete feed steps locked to `printStart` / `printLines`. Each line wipes on within 4f of its cue.
- `stamp` 130: "SHIPPED" in a 4px orange border, 300x96, Geist 600 44, tracking 0.08em,
  rotate -8°, placed bottom-right of the paper inside its edge. `settle` stiffness 300 from scale
  1.12 to 1 (it is text, so the scale is fine).
- `tear` 176: the paper tears at the slot and drops (EASE_IN 24f, at most 3°). The lockup exits down
  through its mask (14f). The slot closes to its center (14f). Solid ink from 200.
- Data: read from `src/usage.json`, never hardcode. While values are 0, render "—" for zero
  numbers so a preview never shows fake zeros. Format: tokens compact (e.g. 4.2M), cost $X.XX,
  percent 1 decimal with ≈ if `approx`.

## 4. Constraints (hard)
- Do not change `src/timeline.ts`. Every cue is a frame-exact visual event. Check each one by
  rendering cue-1 and cue.
- Scene durations are fixed. Edit only your two `src/scenes/S*.tsx` files.
- Boundary frames must equal HANDOFF.md exactly. Render your frame 0 and your last frame, and
  compare them with the neighbour's spec.
- `npx tsc -p .` must pass. No new dependencies, no images, no external fonts.
- Stills: `npx remotion still src/index.ts Film out/<name>.png --frame=<absolute frame>`, or
  per scene with `npx remotion still src/index.ts S4 out/s4_<f>.png --frame=<local frame>`.

## 5. Slop blacklist (any one of these fails review)
1. Glow, bloom, gradient, vignette, grain, noise, blur, light leak, lens flare, particles, confetti.
2. Bounce, overshoot, elastic, wobble, or "pop" scale-ups above 1.0.
3. Opacity-only entrances or crossfades. Per-word fades. Typewriter text outside the S1/S4 prompts.
4. Text under 24px. 1px lines. `C.graphite` on ink. Low-contrast text used to look "subtle".
5. Orange on anything that is not Droid. Two orange ideas in one frame.
6. Emoji, stock icons, macOS traffic-light dots, fake competitor logos, sparkles, "AI" glyphs.
7. `scale()` on a DOM rect above 1.5x. 3D perspective swoops. Random tilts.
8. Everything moving at once. Waves of more than 5 identical staggers. Elements that appear from nowhere.
9. Invented facts: dates, benchmarks, prices, or features not in the brief. Placeholder data shown as real.
10. Dead air over 12 frames outside the designated holds. Compositions that leave a 40% empty band.

## 6. Taste checklist (self-verify with stills before finishing)
- [ ] Rendered at least 12 stills per scene, including frame 0, the last frame, every cue frame, and the hero frame.
- [ ] Thumbnail test: at 25% size (480px wide), every word is legible and the hero reads in 1 second.
- [ ] Squint test: exactly one orange idea per frame.
- [ ] Every element has an answer to "where did it come from, where does it go".
- [ ] The composition centers on y 500–540. No empty band larger than 300px unless it is intentional negative space framing a hero.
- [ ] Left edges sit on x 120 or on a shared axis. Same-row sans and mono share a baseline.
- [ ] Each hold is at least words x 5 + 12 frames. Each hero holds at least 24 frames.
- [ ] Frame 0 and the last frame match HANDOFF.md exactly (shared component, default props, inside Camera).
- [ ] Exits are faster than entrances. Morphs are EASE_IN_OUT. No linear motion.
- [ ] `npx tsc -p .` passes.

## 7. Open items for the parent
- `src/usage.json` is all zeros. S8 needs real numbers before the final render.
- "Sept 2025" in the S3 caption is unverified, so it is dropped unless supplied.
- Model names (Opus 5.5, GPT-6.1, Kimi K3, …) are taken from the draft as given. GLM-5.3 appears
  both as a frontier chip in S2 and as an open model in S6. That is intentional only if the
  parent confirms it.
