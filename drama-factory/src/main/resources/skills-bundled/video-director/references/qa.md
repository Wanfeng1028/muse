# QA: the verification loop

The full render is the last step of a loop, never the first: stills → strips → draft → critics → master. A model's
"looks great" is never a pass; a frame strip or a measured envelope is.

Contents
1. Review tools, cheapest first
2. What to look for
3. Critics: the judge is never the builder
4. The restate test
5. Limits of AI judges
6. Reference compare (remakes)
7. The anti-AI pass
8. Delivery checklist

---

## 1. Review tools, cheapest first

| Tool | What it shows | Command |
|---|---|---|
| Stills sheet | chosen seconds, labelled, one batched render | `scripts/stills.py Wide out/review/beats.png 0 2.5 6 9.2` |
| Frame strip | every Nth frame of a fast move | `scripts/strip.sh Wide 4.0 5.2 out/review/dive.png --nth 1` |
| Overview sheet | the film at 2 fps | `scripts/sheets.sh contact out/draft.mp4 out/review/contact.png` |
| Phone sheet | readability at 360 px wide; if it doesn't read here, it fails | `scripts/sheets.sh phone out/draft.mp4 out/review/phone.png` |
| Around a moment | 12 frames around t | `scripts/sheets.sh around out/draft.mp4 out/review/t12.png 12.0` |
| Beat sheet | one frame per beat to judge rhythm | `scripts/sheets.sh beats out/draft.mp4 out/review/beats.png 120 0.48` |
| Draft render | rhythm, not sharpness | `npx remotion render Wide out/draft.mp4 --scale=0.5 --crf=28` |
| Automatic scan | pops, one-frame flashes, freezes, black frames, spec | `scripts/qa_video.py out/draft.mp4 --ignore 0 --cuts 12.4,30.1 --beats 120:0.48` |
| Audio checks | LUFS, true peak, envelope, speech spans, split silence | `$SD/audio_qa.py out/mix.wav --envelope 10 14 0.1` |
| Poster | chat thumbnail simulation | `scripts/poster_check.py out/final/film.mp4` or `--render PosterWide,PosterTall` |

Pass `--fps` to `stills.py` and `strip.sh` when the composition isn't 30 fps. `$SD` is `~/.claude/skills/sound-design/scripts`. Full flags: `scripts/README.md`.

- Read every sheet you render (the Read tool shows PNGs). Inspect fresh output only; scripts clear their temp frames.
  `sheets.sh` tiles carry no burned-in timestamps (it prints a time legend per page instead); `stills.py` labels tiles.
- Pop scan logic: a frame-difference spike above 3× both neighbours is a pop; frame n differing from both neighbours
  while n−1 ≈ n+1 is a one-frame flash (the plain spike test misses these). On a finished film most pops are intentional:
  whitelist the poster (`--ignore 0`), hard cuts (`--cuts`) and beat-locked pulses (`--beats BPM:OFFSET` with that
  section's grid), then look at every remaining one with `sheets.sh around` instead of treating it as a defect.
- Loops: the last frame must match frame 0 in position and velocity; cycles must be whole numbers.
- Preview suspicious motion at 0.25× in Studio.
- Re-render only the changed range (`--frames=a-b`); batch frames into one render call (each `still` call re-bundles).

## 2. What to look for

**Frame defects**, most frequent first: em-based gaps resolving against the parent font size (use px around big type);
text overflowing or touching edges; elements visible before their entrance or after their exit (missing clamp); the hero
colour on more than one element; unreadable dim text; wrong layer order; a fallback font (the brand font didn't load);
text overlapping during a swap; blurry scaled text; anything moving linearly; corner labels or frame borders.

**Motion**: the seam rules (`motion.md` §8); settles keyed in 3-frame steps (use a continuous curve); exits that don't
accelerate; the next shot not already moving in the exit's direction; idle wobble filling time; a frozen frame mid-film.

**Pacing**: movement within the first 15 frames; something new every 2 to 4 s; the hook works muted in the first 2 to
3 s; nothing front-loaded; every element readable for at least 1.5 s.

**Sound**: hits land (envelope), the duck works, splits sit in silence, the tail fades, LUFS and true peak on target.

**Truth**: every number in `facts.md`; illustrations labelled; no invented UI or features; tokens match the design source.

**Pre-delivery checklist**:
- [ ] Zero linear position easing; every interpolate clamped
- [ ] Entrances use a spatial property and are staggered by importance; exits faster than entrances
- [ ] Every still image has a treatment; fast snaps have motion blur, read text has none
- [ ] One hero colour per frame; brand font everywhere; px gaps around big type
- [ ] At least three deliberate holds; no frozen frame mid-film
- [ ] Every animated event has an SFX cue or a logged silence; `mix.py` SFX audibility passes; music drop on the key visual
- [ ] Text inside safe zones in every format
- [ ] Frames extracted, inspected, fixed and re-inspected

## 3. Critics: the judge is never the builder

- Critics are separate read-only sub-agents that reject by default ("a harsh motion director, not a proud author").
  Brief them with `assets/CRITIC_BRIEF.template.md` and give them sheets, strips and the draft, not your reasoning.
- Split by axis: motion, design and image, sound, story, muted readability, UI fidelity and translations, brand and copy
  rules. Each defect comes with frame numbers, severity and a measurable fix.
- Score 1 to 10 per axis: hook in the first 2 s, readability at 360 px, motion quality, variety, composition, brand and
  data accuracy, sound sync, taste. Tag every issue **BLOCKER** (a viewer would notice: a wrong fact or claim,
  unreadable text, broken or popping motion, sync off by more than 3 frames, inaudible SFX, a brand violation, a failed
  restate) or **POLISH** (everything else).
- **At most three rounds**, each one doing more than the last could:
  1. **Full review.** Every axis lists every issue it finds, not the worst three. Fix every blocker and every cheap,
     safe polish item in one pass; re-render only the affected ranges.
  2. **Verification.** The critics of the axes that failed, or whose shots changed, get the round 1 findings and mark
     each item FIXED, NOT FIXED or REGRESSED. They may add new blockers (regressions, or defects a viewer would notice),
     never new polish. Axes that passed with unchanged shots are not re-run.
  3. **Only if blockers remain**, on those items alone.
  Then stop. What is left goes to the user at hand-off, one line each with a recommendation. An item that fails twice
  is a design decision, not a fix: it goes to the user (or, in autonomous runs, the decision log), never to round 4.
- **Pass**: no open blocker and every axis at 8 or above. An axis held at 7 by a constraint the brief locked (a talking
  head the speaker's own words must open on) passes with that reason logged; it is not a reason for another round.
- Fix only shots scored 7 or below; don't touch shots at 9 or above.
- With parallel builders, write one FIXES file per builder so fixes run in parallel.
- A new version replaces the previous one only if side-by-side judging finds it better. Keep a version log.
- The critic gets a clean context and the spec (brief, storyboard, design rules), never the builder's reasoning. Your own
  first look is never what you hand to the user.
- Every visual claim carries a timecode and is re-verified by extracting that frame; unverified claims are dropped.
  Reviewers have reported "captions rendered" when no frame showed any, and missed a misspelled word.
- Verdicts are APPROVED, NEEDS REVISION or INCOMPLETE; there is no "approved with minor changes". A review that couldn't
  listen to the audio is INCOMPLETE, not a pass.
- Self-check before showing the user: a ±1.5 s strip at every cut of the rendered output, the first and last 2 s, and 2 to
  3 midpoints. Cap self-check at 3 passes, then report what's left. A second polish pass should come back nearly empty.
- Static checks pixel QC can't do, in seconds: frame coverage (holes and overlaps against the shot table), every literal in
  the source that reaches the screen reconciled with `facts.md`, a count of whitelisted effects (glitches, sweeps) against
  their budget, and every visual accent's time looked up from timing data rather than typed by hand.

## 4. The restate test

A fresh agent that sees only the frames, muted, must restate the film's message in one sentence
(`scripts/media_judge.py restate` on the draft, or a sub-agent given the contact sheet). If it can't, the film fails. If
it hesitates, too much is moving. A cold viewer finds ambiguous metaphors the author can't see: in one film the daily
"pack" read as a box mailed home until it was shown on the phone screen where it actually lives.

## 5. Limits of AI judges

- Video judges sample about 1 fps. They miss easing, one-frame pops, flashes and fast moves, and they invent details
  (claims about easing, emoji and gradients in one review were all wrong). Use them for gist, comprehension, pacing feel
  and transcripts. Verify every specific defect claim in stills or strips before acting on it. A strip caught a real bug
  the judge missed: a dive that first zoomed into the wrong object.
- Audio judges need a blind setup (never reveal which clip is edited), an untouched control from the same track, and
  repeated runs. Force a one-line structured answer so verdicts can be parsed and compared.
- You can't hear: every audio claim needs a measurement or a judge, and important ones need the user's ears.

## 6. Reference compare (remakes)

- Side-by-side sheets of reference | ours per second, seam frames between builder groups, and a scan for leftover colours
  of the reference brand.
- Expect frame boundaries in a spec to be a few frames off, and most "cuts" in modern launch films to be continuous
  moves (10 to 15 true hard cuts in 65 s): measure real cuts by frame-difference spikes.

## 7. The anti-AI pass

Generated films share recognisable mannerisms, and viewers have learned them. Run this pass on the script at G1 and on the
draft at G6, as its own critic axis ("reads as made by a person with taste"). One hit is a fix, not a style choice, unless
the decision log says otherwise.

**Copy (voice, cards, captions, end cards)**
- The banned and capped patterns in the scriptwriting skill (`references/craft.md`, AI-sounding tells): contrast reveals, negation lists, question-then-answer, colon reveals,
  "Imagine", fake-profound kickers, marketing stock and AI vocabulary, em dashes.
- **Unneeded explanatory text**: a subtitle under a graphic that already says it; a label narrating what the visual shows
  ("Fast setup" over a fast setup); a "How it works" or "The problem" header card; a summary card repeating what was just
  shown; "Step 1 / 2 / 3" scaffolding outside a tutorial; captions and kinetic type saying the same words at once.
- Hedges and throat-clearing: "simply", "just", "basically", "actually", "in fact", "it's worth noting".
- Over-politeness and cheerleading: exclamation marks in every line, "Let's", "Ready to…?", "You've got this".
- Symmetry for its own sake: every list exactly three items, every line the same length, every beat ending on a punchline.
- Generic stand-ins: "Lorem", "Your Company", "John Doe", placeholder avatars in a finished film.

**Picture**
- The lazy defaults in `design.md` §6 (gradient text, purple-blue glow, glass cards, particles, emoji, centred everything,
  identical card grids, corner labels).
- Every element floating or breathing; every word animated; every transition a different effect; whole-frame shakes on
  every beat.
- Stock-photo realism with AI tells (waxy skin, extra fingers, warped text, impossible reflections), or model-rendered text
  anywhere in frame.
- The model's default font.

**Sound**
- Wall-to-wall music with no dynamic shape; generic stock ukulele or corporate piano chosen by mood word; meme or
  game-pack SFX; a closing ding.
- A voice that reads every line at the same energy; tags spoken aloud; an accent that drifts on short words.

**Structure**
- A feature tour with a logo at the end; three benefits in a row with no turn; an ending that summarises instead of
  landing; a CTA that names an action without an outcome.

**Tests**: the swap test (could a competitor run this unchanged?), the mute-each-line test (does the picture already say
it?), and the restate test. When presenting the work to the user, apply the same standard: no preamble, no self-praise,
no recap of what they can see for themselves.

## 8. Delivery checklist

- [ ] G3 stills approved; storyboard reconciled with the build
- [ ] Automatic scan: 0 unexplained pops, flashes or freezes
- [ ] Music drop on the key moment; −14 LUFS and ≤ −1 dBTP on the final MP4
- [ ] BT.709, yuv420p, faststart (`qa_video.py` spec report)
- [ ] Poster frame checked as a chat thumbnail
- [ ] "Example data" and "Illustration" labels where needed; every number sourced
- [ ] True caption written; licences and generated-content notes in the README
- [ ] File revealed (`open -R`) and its path given
