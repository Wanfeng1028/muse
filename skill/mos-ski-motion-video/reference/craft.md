# Craft: engine rules, briefs, critique

## Render contract
- Every piece is a pure function of time. In Remotion: derive everything from
  `t = useCurrentFrame() / fps` through `lib.ts`. No `setTimeout`, no CSS transitions or
  animations, no state carried between frames, no `Math.random` (use `rng(seed)`).
- Springs, not easing curves. Presets: `SPRING.snappy` (UI, cursors), `ui` (cards, camera),
  `heavy` (big type, logos), `playful` (stickers, visible overshoot). A value with several targets
  uses `track()`, never a restarted spring.
- Text inside a morphing container enters just after the morph starts and leaves just before the
  next one (`swapAlpha`)
- Layout in `unit(format)` (1% of the short side) so 9:16, 1:1 and 16:9 render from one timeline.
  Reframe per format; never crop a wide render to vertical.

## Brief templates (fill these in with the user, or infer and confirm)
**Product reel (most common)**
- Product + URL / Figma link, duration (15–30s), formats, tone (jitter or calm premium)
- Story, one beat each: hook (the problem or promise, ≤6 words) → product appears (UI assembles)
  → 2–3 features, each a UI moment caused by the cursor → one proof number → logo + CTA
- Sound: music file (measure beats) or synthesized; UI clicks and whooshes on the beat

**Event / announcement (the editorial jitter promo in `patterns.md`)**
- Name, date, place, speakers (photo, name, role, company), ticket CTA
- Beats: logo burst → date/venue reveal → speaker conveyor → sticker moments → "don't miss out" →
  lockup with URL

**Style from a reference**: extract a frame every 0.5s, write `work/<name>/style_guide.md` (palette hex,
type family/weight/tracking, shot lengths, transitions, camera, texture, how text enters and
exits), then a shot list in that style. Take the grammar, never the content.

## The shot list gate
Before any code: `work/<name>/shotlist.md`, a table of `# | time (on the beat grid) | what's on
screen | motion | text | SFX`. Show it to the user and get an OK (or proceed if they said not to
wait).

## Critique loop (at least 3 rounds before the full render)
Render stills: one per beat as a contact sheet, a strip of 12 consecutive frames around the
fastest action, and a phone-size sheet (360px wide). `M` = `.motion/venv/bin/python
<skill>/scripts/motion.py`.
```
npx remotion still src/index.ts <Id> ../work/<name>/f<N>.png --frame=<N> --scale=0.33   # per beat (in studio/)
npx remotion render src/index.ts <Id> ../work/<name>/draft.mp4 --scale=0.5               # half-res draft
M sheet work/<name>/draft.mp4 work/<name>/contact.png            # whole film, 2 frames/s
M strip work/<name>/draft.mp4 <t> work/<name>/strip.png          # 12 frames around the fast bit
M sheet work/<name>/draft.mp4 work/<name>/phone.png --width 360 --fps 0.5   # phone size
```
Score 1–10 as a harsh motion director: hook (first 2s), readability at phone size, motion quality
(springs, no dead frames, no sliding), variety (something new every 1–3s), composition, brand
accuracy (design tokens), sound sync. Write the scores and the **3 worst problems with
timestamps** in `work/<name>/review_log.md`. Fix them, re-render only those seconds, re-score.
Ship only when everything is 8+.

Hunt for: text overlapping during swaps, blurry scaled text, things that slide instead of
spring, a dead beat, corner labels or frame borders, centred-on-gradient shots, jitter on body
text (it should be on type and stickers only), and a stutter at the loop seam.

## Deliverables
`output/<name>_<format>.mp4` for each format, `output/<name>_poster.png` (best frame),
`output/<name>_contact.png`, and a 2-line note on what you'd improve next.
