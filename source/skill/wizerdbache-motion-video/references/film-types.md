# Film types and their skeletons

Evidence: the author's lab technique cards (not shipped). Numbers are from the source
films named; each card held the instrument and raw file.

## §0 Storyboard or one paragraph (author, r11)

- Fixed content to follow → a storyboard. Many runs to screen → one paragraph. They make
  DIFFERENT film types (storyboard leans team / identity; one paragraph leans product /
  data), not better and worse.
- A storyboard fixes each section's content, order and seconds only; transitions, layout
  and motion stay free. Measured (r11): a storyboard written to the second makes the model
  change sections on whole seconds.
- Production prompt, four parts: format (ratio, resolution, length), style, content,
  technical requirements — plus a MOTION spec and a RHYTHM spec (a prompt that only asks
  for "clear" gives a clear but static film: C20 moved 16% of the time vs 57-100% in
  other cases, `scripts/density.py`).

## §1 Intro ad, hype ad, product tour — three film types (author r14, r15, 2026-09-30)

The lab's old `showcase-ad` tag held both, and T04 was measured on a mix, so a request for
a "product intro" slid into a tour (r14: both arms made detailed walk-throughs; the author
wanted an ad). Decide which one in SKILL step 0 before choosing a skeleton.

| | Intro ad (`ad-intro`: C08 C16 C17 C18) | Hype ad (`ad-hype`: C01 C21; device source C06) | Product tour (`product-tour`: C07 C09 C15 C23) |
|---|---|---|---|
| Viewer leaves with | ONE thing to remember + an action | a feeling + the name + an action | how to use it, feature by feature |
| Features | 1-3, only as proof of the one message, each a product action cut straight to its result | product screens are material, one striking frame per hit; no walk | every main feature in usage order |
| Opening | a hook in the first ~3 s | a hit in the first second | the product's first screen / name |
| Skeleton | free (§1a) | hit runs on the beat grid (§1b) | fixed skeleton (§1c) |
| Pace | set by tone; waits cut or sped up | every cut on a beat, 2-8 beat sections | follows the operation |

The lab split `ad` into `ad-intro` and `ad-hype` on 2026-09-30 (author r15: "還是很說明 不夠抓眼球";
wanted the r10-r13 eye-grabbing kind). Case tags are a model call the author may flip.

## §1a Intro ad — sources C08 C16 C17 C18 (+ C01 C21 before the split); skeleton unvalidated (r15 S is its first imitation; author: still explanatory)

```
length   : 20-50 s in the sources (C01 20, C16 30, C18 30, C21 40, C08 45, C17 50)
opening  : 0-3 s hook: a problem the viewer has (C08), the product's most striking real result (C16),
           or the brand assembling from the product's own material (C21)
message  : the ONE thing from whole-film §0 item 5; every section serves it
features : 1-3, each shown as action -> result, fast; never a step-by-step walkthrough
brand    : early (C21 ~10% mark) and at the end
end      : brand + the call to action from §0 item 3; hold 2.5-3.5 s (author r14, provisional)
rhythm   : section changes on bars / beats (C16 cuts on the beat)
```

Layer-1 rules (`whole-film-rules.md`) apply on top; they were verified on ad-register
rounds (r12, r13).

## §1b Hype ad — sources: r10 A1 promise section, C21 40 s, C06, C01; author-reviewed once (r17, 2026-09-30)

Pick this when the user asks for 酷炫 / 抓眼球 / showreel / hype, and when the content is
relatively static (few screens, a utility): r16's calm version read "too tame" (author r17).

Hype ads come in tones (lab axis `hype_register`). The skeleton below is the
**fast-precise** tone (快、很準: C06, r17 H; author accepted its hard cuts and speed-ups).
Another tone will get its own block when a round builds one; do not stretch this one to fit. The loosened rules are in
`whole-film-rules.md` §6. The device list below is a menu, not a checklist (r10: a named
list gets built item by item); use 3-5 of them, never all.

```
length   : 15-40 s (C06 15, C01 20, C21 40)
grid     : measure the BPM; every cut on a beat; sections 2 / 4 / 8 beats (C06: 2-2-4-2-2-8-4-4-4)
opening  : a hit in the first second; by ~10% the brand (C21 4 s of 40)
hit run  : one full-frame statement per 2 beats (r10 A1 at 120 BPM = 1 per second), up to 4 in a row:
           word scale 2.2 -> 1 in 0.28 s (exponential out) + blur 14 px -> 0 + shake 14 px decaying
           over 0.3 s; each card its own ground, rotating the product's theme colours (author r17: ok);
           an impact sound on the hit (r10 A1, author-praised). NO giant outline "ghost" word behind
           the statement: it reads hollow and ugly (author r17)
frame    : every word, URL and number stays inside the frame with a margin, also at the peak of
           its scale / shake; nothing runs off an edge (author r17: the URL was cut at the edge)
per beat : word-by-word on beats (C06 FEEL / THE / BEAT), an invert frame as a one-beat accent,
           a ring pulse from the subject on every beat, count-up numbers that land on the beat
product  : real screens as material: 3D tilt push-in (perspective + rotateX/Y), a wall of tiles,
           one cropped number pushed full frame (C01 1.8x -> 4.2x), a whip pan with motion blur
           that stops on the hero (C01 10.5 s); every number real (T05) AND one the viewer
           cares about (users, platforms, time saved); no such number -> no number. Engineering
           counts (tests, commits) are not proof for a viewer (author r17)
variety  : each section a different visual grammar; the SAME transition kind at most twice
data     : if the product has countable things, draw them all (C21: one mark per record converging
           into the shape while a counter counts up)
opening' : a first second the viewer does not yet understand holds them (author r17: ok)
end      : bookend the opening; brand + call to action; hold 2.5-3.5 s (r17 ok)
cover    : ALWAYS deliver a separately designed cover (`build-and-export.md` §2); frame 0 of a
           hype ad is a hit in motion and never works as a thumbnail (r17 made none, author r17)
```

## §1c Product tour (T04 + T05) — measured on 4 source films; end-card hold verified

```
length        : 40-50 s at 16:9; 1 idea per section
opening       : 2-9.5 s hook: logo assembles from product data, a surprising number the product
                then explains, or the product's first screen with a real query typed
feature section: headline (2 clauses, <= 13 CJK chars, 2nd clause = the benefit) + ONE product action
                on the real product screen (cursor click, typing, a panel appearing, a number rolling)
skeleton      : headline zone and product zone never move; one anchor (logo / search box) stays on
                screen through every transition
section length: whole bars; early sections 2-4 bars, later ones 1 bar. Section CHANGE on a bar line;
                motion inside a section need not be on the beat
transition    : ONE kind for the whole film: dim-to-ground 0.2 s + <= 0.2 s empty + per-character
                headline (whole transition <= 0.7 s; fade the product window out fully, no empty frame),
                or blur-swap 0.1 s out / 0.1 s in, or black wipe card 0.37 s
end card      : logo + product name + one-line tagline + URL; T04 measured >= 3 s, author r14 caps it at
                2.5-3.5 s (5.8 s and 7.4 s too long; provisional)
palette       : the product's own colours; one accent only
```

**Roles of three borrowed devices (author 2026-09-30)** — not alternatives, each has a place:
- opening = shape to name (C07): a real element draws in, collapses into the logo / product
  name, which is flung to its resting place;
- feature chapters = verb card (C17): one single-verb card per feature, then the real screen
  where that verb happens;
- in-feature transition = click and grow (C19): the clicked control grows into the view it
  opens. Opening + verb cards were built together in lab round r7; click-and-grow inside a
  full film is untried (unvalidated).

Evidence notes: the end-card hold is the only T04 rule a blinded round separated (with the
card 5.82-7.78 s vs without 3.58-5.68 s, n=3 each). Bar-locking could not be credited to
the card (the frame gave beat times). What sets a section's length in C07 is unknown (not
headline length, not bars; seems to be the amount of UI demonstrated).

Product screens are real captures (T05 rule 1); see `build-and-export.md` §4.

## §2 Data-driven showreel (T07) — n=1 source film (C21 40 s); data trait verified

```
source      : the product's own data file; read it before planning; every number computed from it;
              charts drawn to scale
opening     : 0-4 s, the WHOLE dataset, one mark per record placed by its own attribute
              (coordinates -> map shape), converging while a counter counts to the record total
brand       : right after the opening (~10% mark), 3-4 s; again at the end
sections    : 2-6 s each, ONE fact from the data each: short headline + one data visual + one motion
variety     : never repeat a visual grammar (map, count grid, accent bar chart, date flip, rotating
              list, people cards, phone UI, full-bleed statement) in two sections
layout      : soft skeleton (headline left, visual right); no persistent anchor
transitions : 3-4 kinds across the film; section changes need NOT sit on the beat
ending      : the opening's marks reassemble into the logo; hold ~2 s
```

Verified (r9): the one-paragraph prompt alone already makes the model open the data file
and map real coordinates, with no invented numbers (3/3). Adding the example card made
runs copy its section order almost verbatim — give principles, not an example order.
Layer-1 rules (`whole-film-rules.md`) apply on top.

## §3 Narrated explainer (T06 + T08) — T06 verified, T08 unvalidated

- Narration first (TTS), measure each line's start, THEN time the sections (T08).
- While a line is spoken something moves with it: draw what is said, assemble it, move it;
  stretch the entrance close to the whole line instead of popping it in 0.4 s and holding.
- Targets (T06, `scripts/density.py` definitions): moving share >= 0.6; still runs p90 <= 2.2 s,
  max <= 4 s. Text holds still once shown; the picture moves, not the words.
- Devices seen: draw-on lines, one persistent anchor object moving between views, numbers
  counting, typing, sequential assembly, flow in diagrams.
- Verified (r8-c20, 3 runs each): moving share 0.67-0.71 with the card vs 0.20-0.28 without.
  Caveat: runs self-measured against the stated threshold, so the numbers prove compliance,
  not beauty; cost 1.6-3.3x.
- Lines per section: explainer / profile 3-5 lines (~7-11 s); lyrics one line per section.
- An anthology of separate voice blocks is the counter-type: its sections change BETWEEN
  voice blocks, not on line starts (C23).

## §4 Profile / showreel reel (C19, C22 as sources) — measured only

Short (15-30 s), music-driven, sections change on beats; each section's main shape becomes
the next (shape-to-shape, `rhythm-transitions-camera.md` §3); a bookend (the opening mark
returns as the end card). A showreel may change ground colour per section — that is the
opposite of the promo ground rule and belongs to the showreel register only.

## §5 Music PV / MV (`music-video`: C14 C29-C36) — analysed only, no skeleton yet

Added 2026-10-04 (author). The film carries a song: the timeline is the song's
structure, lyrics are the picture's subject, no product / thesis / CTA. Same day the author's lab
split off narrative film (AI anime / AI drama, shot-based storytelling) as a named but
unopened purpose (on the lab's waiting list) and added `mv_form`, borrowed from MAD culture's
form classes: `still-image` (static stills moved by push-in + a code type layer: C29 C30)
vs `procedural` (every frame program-drawn and moving: C14 C31). None of the four is a MAD
in the strict sense (nothing existing is re-edited); the lab borrows the form classes only. Observed, not
measured with a calibrated instrument: section density follows the song (C29: verses 3-4
hard cuts per 20 s, last chorus ~1.2 per second, interludes as continuous camera moves with
almost no cuts, a near-black one-line pause before a chorus), one new type layout per lyric
line, a resident HUD / ground layer tying many stills together, and one image motif that
runs head to tail (C29: a point of light). C29's characters are static image-model stills
moved only by push-in, glow and overlaid type. Build a skeleton here only after a round.

Naming (the author's lab taxonomy, author 2026-10-04; the name is the first lookup key, so
it follows the tags): music PV / MV = purpose `music-video`; still-image form (靜止畫型) =
`mv_form: still-image`, any material (C29 C30 C32-C34); MAD ONLY for `material: source-work`
re-edits (C32-C36) - C14 C29 C30 C31 and anything we make from original stills are NOT MADs.
MAD types (author 2026-10-05, Niconico titles + Chinese usage) have TWO independent levels:
picture (`mv_form`) 靜止畫 MAD (静止画MAD, C32-C34) vs 動畫 MAD (動画MAD, C35 C36); content
(`mv_story`, four peers) 劇情向 / ストーリー (C36), 誤解向 (Chinese, C35), 複合, ゲーム (last
two not opened); none -> plain MAD. Never "靜止系" (系 = tone / editing classes there).
Classify the levels apart, but SEARCH with mixed forms (靜止畫/静止画/靜止系/静止,
劇情向/剧情向/ストーリー, 誤解向/误解向/誤解系) or the bare root + MAD, in Simplified,
Traditional and Japanese glyphs: titles mix them. A finding measured on MADs says MAD; using it for our own original still PV is a
marked transfer ("unverified on original material"). Median absolute deviation is never
abbreviated MAD.

Real MADs (lab C32-C36, 2026-10-04; material `source-work` = existing work re-edited).
New axis `mv_story`: `lyric-image` (pictures follow the lines; all still-image cases) /
`story` (dialogue clips build a plot, the song scores it: C36) / `reinterpretation` (the
original rearranged into a story it does not tell, often through an added frame such as a
dating-sim UI: C35); both story types are `mv_form: clip-edit`, audio `dialogue`, named
combination 'source-footage story cut', and sit next to the unopened film purpose.
Still-image devices (the author's cards). T12 and T13 are **measured**
(blurdip / flashwash / framebox on C32-C34); T14-T16 stay **observed** (frame-sheet reads only):
- T12 blur bridge: each picture change goes blurred-then-sharp (defocus entry, motion-blur
  whip-in, radial push-in); measured 5-13 blur changes per minute, median time spent blurred
  0.27-0.37 s. Imitation r20 (n=3 per arm): the instrument counted 5/6/5 of 7 changes blurred
  with the card vs 3/3/3 without, but the author saw the six films as essentially the same - the
  model already does blur dissolves and whips unprompted, so the card adds no visible effect.
  Hold the blur ~0.3 s; a very short blur (< ~0.15 s) reads as shake / heartbeat: a local
  accent tied to picture content or a lyric, never the whole film (author ruling). The beat
  grid alone is NOT a reason for a heartbeat pulse (author r21: the beat map is a calculation
  aid); a pulse too small or too short reads as an unstable, shaking frame.
  A brief that offers a place-name title gets a film location card, not MV type.
- T13 window / light / colour: change the frame shape (letterbox, strip, slant via
  clip-path), the light (white flash, single-colour wash ~0.25-0.4 s, a point of light in a
  black dip) and the colour world (mono to colour) at each change. Only for still-image PVs,
  never for promos (opposite of the one-resident-ground rule). A per-page ground change
  with a fixed design system (type, ink, treatment, components) still reads as one film (C34).
- T14 staggered layers: 3-6 layers per page enter 0.3-0.6 s apart (ground, picture, type,
  small parts, connecting line), so a held page never stops; a large canvas crossed by a
  virtual camera as an alternative (C34 18-38 s, zero cuts).
- T15 motif thread and callback: one motif that MEANS something (C34 two-strand thread =
  the two characters' colour codes; C29 point of light = the title) or a composition that
  returns later (C32, segsim 0.989).
- T16 lyric type family: pick one or two treatments for the whole film (giant type behind
  the character, vertical spread, slide-in with tracking collapse, shard assembly,
  per-glyph blur reveal, two-tier type, single-glyph cards); a list to choose from, not
  rules to perform. Never copy lyrics into a card or a test input.
No still-MAD boundary set was beat-locked (C32 R 0.11; C34 none significant; C33 marginal
at small n), so none of these devices is tied to beats. Music analysis (the author's lab, `scripts/cutdrivers.py`): testing cuts against beat, accent, loudness
change, section and harmonic change from the mix, no stream locks consistently across C32-C36,
and transition peaks lock to none. The driver is the LYRIC LINE (author: cuts follow lyric
content and section character, not beats); speech recognition on singing fails, so line
times come from on-screen text (an OCR detector, partial, not shipped) and a model frame read. Measured
on still-image MADs C32 and C33 (model-read lines, 2026-10-04): almost every lyric line
arrives WITH a picture change (C32 hard cut, median 0.04 s; C33 hard cut or blur/flash), and
further changes fall between lines (C33: on beats). Applied (author ruling, observed tier) to
our own original still-image PVs as a TRANSFER, unverified on original material: one new
picture per lyric line, then optional in-line changes on beats; never beat-snapping alone.
C34 (still-image MAD, page turns by camera sweep and layer entrance) is undeterminable: no
instrument sees its page turns yet (open in the lab). Animation MADs C35 (誤解向) and C36 (劇情向) show NO
lyric track: their on-screen text is source dialogue; C36's shots change with each dialogue
line (p 0.001), C35's dialogue box changes lines inside a shot. So the lyric-line rule is a
still-image MAD finding only.
