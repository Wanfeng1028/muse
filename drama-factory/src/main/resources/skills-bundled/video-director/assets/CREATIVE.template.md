---
title: <film name>
workflow: launch          # launch | explainer | demo | overlay | social-cut | montage | sting | remake
message: "<the ONE thing, written as a claim>"
audience: <who, in one line: role, situation, what they already believe>
destination: <x-feed | reels | shorts | tiktok | youtube | linkedin | website | chat>
formats: [Wide 1920x1080, Tall 1080x1920]   # master first; derive from destination and say why
length: 60s
language: en
reference_style: "<a named film or brand, e.g. 'Linear launch', 'Apple bumper'; never 'premium modern'>"
arc: <pain-to-relief | before-after | problem-proof-offer | how-it-works | countdown | ...>
narration: yes            # yes | minimal | no
clock: vo                 # vo (voice-led) | music (music-led) | speech (footage)
facts: facts.md           # every on-screen number with source and date; no facts file, no numbers on screen
version: v1
---

# <Film name>: creative plan

Working document. The brief says why and for whom, the storyboard says what, the code is how. After the build,
the code is the truth: regenerate section 6 from the timeline and update the storyboard to match what shipped.

## 1. Brief

**Message (claim).** <One sentence a stranger could repeat. "Close isn't final", not "About the inspector".>

**This film tells** <audience> **that** <message>.

**Audience.** <Who watches, where, on what device, with sound on or off. Assume muted autoplay in feeds.>

**The one feeling to leave behind.** <Relief, pride, curiosity... and the sentence they would say to themselves.>

**What we sell.** <Not the features: the change in the viewer's life. Features appear only as answers to a pain.>

**Pains, ranked** (from research; cite where each came from):
1. <pain in the viewer's own words>
2. <...>

**Reframes we can stand behind** (true, no invented stats): <...>

**Tone.** <Three adjectives plus what we never do, e.g. "we never dramatize fear".>

**Language and copy rules.** <Locale, register (tu/usted, contractions), banned words, product vocabulary,
punctuation rules (e.g. no em dashes, no emojis), from the product's own docs.>

**Offer / call to action.** <Exact wording, price and conditions as they are in code or on the site.>

**Voice.** <Provider, voice id, model, settings, casting notes. Or: no narration, and why.>

**Assets.** <path: what it is, where it belongs, licence.>

**Scope.** <What was asked for, and what is offered but not included (captions, music, extra formats).>

## 2. Visual language

- **Ground and palette:** <tokens by role with hex, each with its source file>.
- **Type:** <display / sans / mono roles, sizes at 1080, source>.
- **Shapes, depth, texture:** <what the brand allows; what it forbids (gradients, glow, blur, glass...)>.
- **Real product:** <which screens are captured, which are rebuilt in code, and from what capture>.
- **Illustration / footage:** <style, cast, generator and style suffix, licences>.
- **Motion grammar:** <easing characters (max 3), spring register, the one seam direction, reserved vectors,
  what may stay alive during holds>.
- **Bans for this film:** <at least: no idle wobble on content, no fake UI, no static end card, no slideshow
  (every beat a fresh card), no screensaver (motion that says nothing)>.

## 3. Arc

| Act | Job | Emotion | Ends on |
|---|---|---|---|
| I | <hook + pain> | <recognition> | <the turn> |
| II | <the change, shown> | <relief> | <proof> |
| III | <proof + offer> | <confidence> | <CTA on the final hit> |

Hook strategy (first 2 s, muted): <what moves, what is read>. Value lands by beat 2: <how>.
Rhythm, declared: <e.g. fast-fast-SLOW-fast-HIT-hold>. Held frames: <where, and why>.
Pause before the climax (0.3 to 0.75 s): <where>.

## 4. Script

About 2.5 words/s; one breath per line; each line a set of cues the picture can reveal on. Display text in the
table; spoken text (tags, phonetics) in `src/data/vo.ts` `SPOKEN`.

| # | Beat | Line (display) | Spoken differences | Intent | Words | Target s |
|---|------|----------------|--------------------|--------|-------|----------|
| l01 | Hook | <...> | <[softly]> | <...> | <n> | <s> |

Total words: <n> (budget <length x 2.5>).

## 5. Storyboard

**Decisions header.** Message: <claim>. Audience and arc: <one line>. Format: <aspects, length, VO y/n,
music y/n>. Spine device: <the object or idea that carries through>. Tokens: <roles + hex + source>. Type roles:
<display/sans/mono + sizes>. Easings: <the three>. Seam direction: <LEFT>. Bans: <list>. Held frames: <list>.

### NN: <Name> (<start>-<end>, ~<dur> s)

| Field | |
|---|---|
| On screen | <concrete objects, counts, positions; every on-screen word verbatim in quotes> |
| Voiceover | <verbatim line id + text, or "onscreen" for silent films; reveals land on the naming word> |
| Hero prop | <object that persists, and the beat where it returns> |
| Motion | <named verbs (SLAMS, DRAWS, FILLS...) with easing character and duration> |
| Seam out | <technique + direction + carrier> |
| Audio cue | <an SFX per animated event (sound + time), music events; a silent event says why> |
| Constraint | <at least one explicit "no ..." for anything that could go generic> |
| Why | <the beat's job, traced to the message; untraceable means cut> |
| Truthfulness | <what is real here (capture, real number with source), what is illustration> |

(Repeat per beat. Beats are 1.5 to 3.5 s; scenes group beats. Something new every 2 to 4 s.)

### Seam ledger

| Cut (s) | From -> to | Exit axis/direction | Entry axis/direction | Carrier | Technique |
|---|---|---|---|---|---|
| <4.00> | <hook -> pain> | <x, left> | <x, left> | <kicker> | <cut the curve> |

### Format notes

<How each format re-lays out (stacked, larger type, full-bleed screen), never a crop. Tall safe zone.>

## 6. Locked edit

Music: <track, licence, BPM, key, edit (source ranges), where the drop/final hit lands in film time>.
Generated from `src/data/timeline.ts` after the build; times in film seconds.

| Film time | Phrase / bar | Scene | Key sync |
|---|---|---|---|
| <0.0-4.0> | <intro, bars 0-1> | <hook> | <"promise" underline on its word> |

## 7. Sound plan

- **Clock:** <VO, music or speech; what is anchored to what (e.g. brand word on the P2 downbeat)>.
- **Music:** <mood, tempo, energy event and the visual on it, fade/edit plan>.
- **VO:** <level, pace 140-170 wpm, splits that must land in silence>.
- **Product sounds:** <diegetic audio, and the pause each one sits in>.
- **SFX:** <kit (synthesized via sound-design's foley.py or sourced, with licences), key for pitched sounds, a sound for
  every animated event with gains 0.3-0.6 (hero hits up to 1), texture runs marked; no meme sounds>.
- **Mix:** bed ducked 8-12 dB under the voice with a slow release, SFX peak-aligned and passing `mix.py`'s audibility
  check, master -14 LUFS / -1 dBTP measured on the final file.

## 8. Production pipeline

G0 brief -> G1 script, storyboard, beat map -> G2 VO locked -> G3 style frames -> G4 build -> G5 sound ->
G6 draft review (critics, restate test) -> G7 masters -> G8 hand-off. Record what each gate decided in section 10.

## 9. Quality bar

- Hook works muted in the first 2 s; the message is restated correctly by a fresh viewer from muted frames.
- Every cut on a beat or a phrase; seams velocity-matched in one direction; no dead frames; nothing pops in
  without easing or a spring.
- Captions readable at 360 px wide; nothing critical in the Tall bottom 18% or outside safe margins.
- Brand rules: <the product's own list>. Copy rules: <the product's own list>.
- Every number on screen traceable to `facts.md`; no invented stats, testimonials or UI.
- The <key moment> is the loudest/biggest moment of the film; it ends on the music's final hit and holds.
- Frame 0 works as a thumbnail for a stranger at ~300 px with a play button over its centre.
- Critic scores >= 8 on every axis.

## 10. Decision log

Newest first. What changed, why, and what evidence (test, critic, user note) drove it.

- **<date> <topic>.** <decision>. Why: <evidence>.

## Changes from v1

<Notes recorded verbatim; revise only the named beats.>

## Still open

- <question, owner>

## Locked

<Date and version locked for build.>
