---
name: wizerdbache-motion-video
description: >-
  Making a whole code-rendered video (every frame computed by a program: HTML/SVG/canvas
  driven by time, rendered frame by frame to MP4): intro ads, hype (eye-grabbing) ads, product tours / intro films,
  data-driven showreels, narrated explainers, profile reels. Whole-film decisions (audience, tone,
  locked ground), film-type skeletons, section rhythm (bar or narration line), transitions,
  camera moves, product fidelity, render/export, frame-sheet review. Trigger on
  「做一支產品介紹片/宣傳片/廣告」「酷炫、抓眼球的廣告」「做 showreel」「做旁白說明動畫」「影片怎麼分段、換段、轉場、運鏡」
  「這支片的基調/受眾」. NOT a single UI animation's easing or spring (a UI-motion skill, if
  installed), NOT studying or cataloguing a stream of reference videos.
---

# motion-video — making a whole code-rendered film

Router skill for FILM-level work. Element-level motion (duration, easing, springs,
colour swaps inside one component) is not this skill's subject; the measured spring and
colour-swap numbers a film needs are in `references/element-motion-params.md`.

The rules were distilled from the author's private lab: a library of source films (case
IDs `Cnn`), technique cards (`Tnn`) and isolated imitation rounds (`rNN`). Those IDs stay
in the text as provenance labels; the lab itself is not shipped. The lab's general
measuring instruments ARE shipped, in `scripts/` (`references/evidence-and-instruments.md`).

Every rule in the references carries an evidence tier (`references/evidence-and-instruments.md`
§Tiers): **author** (the skill's author judged it watching films), **measured** (a calibrated
instrument read it on source films), **verified** (a blinded A/B round moved it, ranges
disjoint), **unvalidated** (measured on sources, never tested by imitation). Do not
state an unvalidated rule as a proven one. An author-tier rule is one person's taste
record: when the current user rules otherwise, the user wins.

## Routing table

| If the task is about… | Read |
|---|---|
| What to decide first; audience, tone, ground colour, what info belongs; device-tone pairing; materials and text | `references/whole-film-rules.md` |
| Which film type; section skeletons (intro ad, hype ad, product tour, data showreel, narrated explainer); storyboard vs one paragraph | `references/film-types.md` |
| Section changes on the bar or on the narration line; beat alignment; transitions (shape-to-shape, dim, wipe); camera moves | `references/rhythm-transitions-camera.md` |
| Building the page, time-driven rendering, export to MP4, product fidelity (claims file), cover, review loop | `references/build-and-export.md` |
| Evidence tiers; which instrument in `scripts/` measures what; where each number comes from | `references/evidence-and-instruments.md` |
| Spring / colour-swap parameters for one element | `references/element-motion-params.md` |
| The same principle in posts, decks or web pages (cross-medium form, axes A–H, named schools) | not shipped; the author keeps it outside this skill |
| A paragraph to append to any product-video prompt (ask the owner, don't guess) | `references/ask-owner-addon.md` |

## Order of work (each step before the next)

0. **Confirm before anything** (`whole-film-rules.md` §0): purpose / film type (intro
   ad, hype ad, product tour, explainer, profile), where it will be shown, what the viewer
   should do after watching, the audience, the ONE thing to remember, the ENERGY (calm /
   lively / hype; asked, never inferred from the product alone) and ground, the
   materials and limits, the content voice (marketing vs light technical) and the
   presentation form (paged vs continuous-stage). A user present → ask these and wait. Unattended → write each
   open one to `build/questions.md` and take the request's most literal reading, stated
   in `build/plan.md`. "產品介紹片" alone does not settle ad vs tour (author r14); "廣告" alone does not settle intro
   vs hype (author r15).
1. **Whole film first** (`whole-film-rules.md` §1): name the ONE audience, what that
   audience needs to know, the tone (the energy named in step 0; only if none, from product + audience), and the ONE
   ground colour (a hype ad loosens it, `whole-film-rules.md` §6).
   These four are fixed before any device is chosen. If the product's documents do not
   say what a feature solves, ask the owner (`build-and-export.md` §4 item 7); unattended, write
   `build/questions.md` instead of inventing a pain point.
2. **Film type** (`film-types.md`): intro ad, hype ad, product tour, data showreel, narrated explainer,
   or profile reel — from step 0's purpose, never from which skeleton is closest to hand. Pick the skeleton; decide storyboard (fixed content) vs one paragraph
   (screen many runs).
3. **Rhythm source** (`rhythm-transitions-camera.md` §1): music only → section changes on
   bar lines; narration or lyrics present → section changes on line starts, and the music
   is not also hard-locked. Whether a film gets narration at all follows the film type and
   tone (step 1-2); a quiet film may still use music with slow sections.
4. **Storyboard table before code**: per section `t`, headline, visual, data, layout,
   transition in/out, camera goal, **motion intent** (one line per moving element and per
   stacked effect layer: what the motion says; an element with no line stays still or
   goes, `whole-film-rules.md` §2a). Show it to the user and wait for confirmation when a
   user is present. Record each design decision you make yourself, at the moment you make
   it, as one line in a decision log in `build/plan.md` (what, why, reversible or not).
5. **Devices**: each device has its own tone; a device that clashes with step 1's tone is
   dropped, the tone is never changed to fit the device (author 2026-09-30). A stock device
   (particle burst, tunnel, floating card pile, glitch, big-text-as-design, fake HUD
   numbers) is used only with a motion-intent line tying it to content (§2a).
6. **Build** (`build-and-export.md` §1): one HTML page whose every frame is a pure
   function of time (`window.__setTime(t)`); no timers, no CSS transitions.
7. **Export** (`build-and-export.md` §2): frame-by-frame capture + ffmpeg; wait for fonts;
   the render is done only when `ffprobe` reads the duration.
8. **Review** (`build-and-export.md` §3): 1 fps whole-film sheet first, then details;
   feedback as "second / where / change"; one change at a time; at most 3 rounds.
9. **Deliver** with the acceptance shape below, into the project the user named.

## Verdicts this skill may give, and how each is verified

Instruments are in this skill's `scripts/` folder (Python 3.10+, ffmpeg on PATH; see
`references/evidence-and-instruments.md`). Run `python scripts/<name>.py --selftest`
once before trusting a number.

- "Section changes sit on the bar / line" → `scripts/measure_product.py` or
  `scripts/narrlock.py` on the rendered MP4.
- "Motion is continuous under narration" → `scripts/density.py` moving share and still runs.
- "Every number / feature is real" → `scripts/fidelity.py` + `build/claims.json` (T05).
- "There is a camera move" → `scripts/camflow.py`; `at_boundary` runs need a frame look.
- "Looks good / matches the reference" → NEVER from numbers. A model-read frame sheet
  AND the user's own viewing. Numbers prove the data path, not the picture.

## Delivery shape (a human must watch the film)

End every delivery with an unasked checklist, ranked by consequence:

- `A 必驗` (must check, ≤ 7): audience right; energy is the one asked for (a hype ad stops the eye
  in the first second); ground colour locked (hype ad: only hit runs may alternate); a
  separate cover delivered; every on-screen number and feature traceable and meaningful
  to the viewer; nothing unreadable (text held long enough — a titled page/level ~3.2 s
  and up, author r19 — labels large and high-contrast, nothing cut at the frame edge); end card resolves the logo fully and holds 2.5-3.5 s (author r14: 5.8 s and 7.4 s
  too long; r17 3.7 s accepted).
- `B 體驗` (experience): transitions feel smooth; pace fits the tone; camera moves read as intended;
  demos do not drag (waits sped up, `build-and-export.md` §1 speed map); nothing moves
  for the sake of moving (each motion matches its storyboard intent line).

Name the likely runtime failures and what the user would see: fonts not loaded (fallback
glyphs in early frames), a background render that ended early (short MP4), a blank frame
from a failed asset. The page itself announces load failures on screen, not silently.

## Extensions (not scope)

Unvalidated items worth an imitation round, only when a film needs them: T08 line-locked
sections, T09 camera parameters, T10 shape-to-shape, T11 guide character with concept
cards and screenshots (r18, n=1; author rulings in `whole-film-rules.md` §2), and C19
click-and-grow inside a full product film (never tried). Each needs a blinded A/B before its tier is raised.
