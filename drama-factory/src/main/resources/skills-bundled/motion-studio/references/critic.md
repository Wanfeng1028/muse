# The critic pass

The blind read asks whether the film still makes its point. The critic asks whether it is worth watching. Run it on every long-form draft and on any short film the user calls dull.

## 1. Numbers first

`longform.py check <film>` measures the render and the timeline:

- **text-only share**: time spent on words over a background (`title chapter statement quote list`). Over 40% flags; so does a text-only run over 25 s, or three scenes of one type in a row.
- **holds**: stretches where nothing visible changes (mean luma change under the `--event` threshold) for `--hold` seconds (default 4). A 10-minute explainer should have none over 6 s; the original toll-text cut had 59 over 4 s.
- **per chapter**: events per minute and the share of still frames, so a flat chapter stands out from the others.
- **cue landings**: every word cue should produce a visible change within -0.2 to +0.8 s of its word. A change in any small block above the caption band counts (`--local`), so a small reveal such as a spoke label registers.
- **one-frame flashes**: a frame that differs from both neighbours while they match each other (back-to-back pops that verify's single-frame check misses).

## 2. A fresh critic, not the builder

Give a fresh agent only: the contact sheet (`stills --every 2.5`), `review/check.txt`, the script's narration, and the brief. Never the builder's reasoning or notes. Prompt:

> You are reviewing a draft explainer video. You see stills every 2.5 s, the narration, and measured numbers. Report only problems you can point to in these materials; if a section has none, say so and do not invent one. For each chapter: the seconds it could lose, any stretch where the picture repeats what was just shown, any line whose picture doesn't show what is being said, and any number on screen without a source. Then the top 6 fixes, most important first, each tied to a segment id and a timestamp.

## 3. Verify the fixes

After changes, a second fresh critic gets the previous list and the new materials and marks each item FIXED, PARTLY or STILL PRESENT, then answers SHIP or ONE MORE PASS (at most 3 more fixes). Fix one thing at a time and keep timing and motion otherwise untouched, so a revision doesn't regress what worked.

Credit: the fresh-critic loop and verification round come from echris6/motion-video-kit; the "report only what you observe" wording from charlie947/motion-graphics-skills; the stillness and flash measures from cclank/lanshu-create-ai-presenter-video and howseen-ai/claude-motion-design (all MIT).
