---
name: kinetic-typography
description: >-
  Add animated "kinetic typography" to an HTML page — headlines whose words cascade in one
  after another, a centered hero headline that gets pushed aside as content/cards slide in,
  top/bottom supporting lines that slide out of the headline, and a fractured/"cracked" word
  effect. Use when building motion-graphics-style titles, an animated headline reveal, a
  product explainer's text, or any "the words move like that launch video" request. Triggers:
  "animate the headline", "kinetic typography", "make the title words fly/rise in", "cracked
  text effect", "headline that slides aside when the cards come in", "word-by-word reveal".
---

# Kinetic Typography

Drop-in building blocks (`assets/kinetic.css` + `assets/kinetic.js`) for motion-graphics text in plain HTML/CSS — the look of polished SaaS launch videos. Three composable effects:

## 1. Word-cascade reveal
Each headline line masks its words; the words **rise into place one after another** behind the mask. `splitWords()` splits `.head .ln > span` into per-word `.wd` spans (preserving an inline colored/gradient word or a `.crackword` as one unit) and tags each with a global `--wi` index; the CSS `@keyframes wordrise` staggers by `--wi` so the whole headline "assembles" line by line.

```html
<div class="head"><span class="ln"><span>Find the <span class="grad">cracks</span></span></span>
                  <span class="ln"><span>first.</span></span></div>
<script src="kinetic.js"></script><script>splitWords();</script>
```
Play it by adding `.show` to an ancestor (e.g. the active scene).

## 2. Hero → push → reveal staging
A headline appears **centered as one line** (hero), then **content slides in and pushes it aside** while the kicker (top line) and subtitle (bottom line) **slide out of the headline**. Structure each scene as a `.lead` (kicker + `.head` + `.sub`) next to a `.cardstage`, mark the scene `.choreo dk-left` or `.choreo dk-right`, and toggle `.cardsin` when the content phase begins:

```html
<section class="scene choreo dk-right">
  <div class="lead"><div class="kicker">Section · Label</div>
       <div class="head"><span class="ln"><span>Govern every agent.</span></span></div>
       <div class="sub">One line of supporting copy.</div></div>
  <div class="cardstage"><!-- your cards / panel --></div>
</section>
```
- No `.cardsin` → headline centered (`--heroX` recenters it from its docked side), kicker/sub hidden, stage off-screen (`--stageHide`).
- Add `.cardsin` → lead slides to its dock, stage slides in from the opposite edge, kicker/sub slide out. Alternate `dk-left`/`dk-right` across scenes for variety.

## 3. Fractured / cracked word
Wrap a word `<span class="crackword" data-text="cracks">cracks</span>`. It renders as two copies clipped along a jagged seam; the CSS variable `--ck` ramps the fracture (0 = solid, 1 = fully cracked) with a red glint in the gap. Drive it in your frame loop so it cracks on cue (e.g. when a voiceover says the word):
```js
setCrack(el, clamp((t - crackStart) / crackDur, 0, 1));   // from kinetic.js
```
Keep `--ck` at 0 until the word has finished its cascade-in, so it reads "word appears → then cracks."

## 4. Typewriter + cursor + pill
A fourth staging, for when a *travelling element* (a logo, a dot, the spark from a reference reel)
is already flying through the frame: instead of the words cascading in, the line **types**, and the
travelling element is the **cursor** typing it.

- **Type without reflow.** Build the line once in its final layout — a span per word, an
  inline-block span per letter — and per frame set each letter's opacity plus a `translateX`
  accumulator that starts at `+.18em` of tracking and closes to 0 over .25 s. Never animate
  `letter-spacing`: that re-lays the line out every frame, so the words crawl and a long line can
  re-wrap mid-type. Step ≈ 35 ms per letter, capped so the whole line takes at most 1.1 s.
- **Ride the mark to the typing edge.** After it lands, lerp the mark from its resting point to the
  right edge of the last-typed letter (arc it over the line with a sine so it never crosses the
  words it just wrote, and shrink it to cursor size on the way out), then ease it back when the
  line is done — well before the cut, so every exit still starts from the resting point.
- **Land the payoff word in a highlighter pill.** The last word sits in a solid accent pill that
  wipes in from its left edge (`clip-path:inset(0 var(--wipe) 0 0)`, 100 %→0 over .3 s) as that
  word's first letter appears, with the letters flat white over it, and the run settles out of a
  6° tilt over .35 s.

Helpers and classes for all three live in the **text-motion** skill
(`tmTypeBuild · tmType · tmTypeCursor`, `.tm-type / .tm-pay`), and the background half of the move
— the rings the mark travelled along and the glow where it landed — is the **mark-driven-ground**
skill. Recipes: "A″ · Spark-driven text" in `../motion-graphics/PLATTER.md`.

## Notes
- Units are container-query units (`cqw`/`cqh`); put the scene inside a `container-type: size` stage, or swap to `vw`/`%`.
- These are **logical-time friendly**: the cascade/push are CSS, the crack is variable-driven — so they render cleanly with the `smooth-render` skill (scale the transition/animation durations by 1/RATE at render time).
- To sync cues (a word cracking, a card raising) to a **voiceover**, pair with the `vo-sync` skill.
