# Sound & Dialogue Plan Template (Mode H)

Load this file when you are at Step 11 (sound and dialogue plan) or the user asked for Mode H.
Sound craft — what a bed does, how audio leads a cut, lip-sync and VO technique, what music is
for — is owned by [sound and dialogue](../references/sound-and-dialogue.md). Cut points and pacing
math are owned by [editing and assembly](../references/editing-and-assembly.md). Asset naming is
owned by [continuity bible](../references/continuity-bible.md). This file owns the spreadsheet you
hand to whoever builds the mix.

The worked example inherits its sound direction from [director book](director-book-template.md)
and its shot timings from [shot plan](shot-plan-template.md): project `Under the Door` (`UTD`),
scene 7, 22s, five shots — a courier hesitates outside a Republican-era Shanghai apartment door,
slides an envelope under it, and leaves.

## The five layers

Every shot gets an entry in all five layers, even when the entry is `none`. A blank you never
decided is a hole in the mix; a `none` you decided is a choice, and the difference is visible on
the page.

| Layer | Code | Cut to picture? |
|---|---|---|
| Room tone（房间底噪） | RT | No — continuous |
| Ambience（环境声） | AMB | No — continuous |
| Foley（拟音） | FOL | Yes — frame-accurate |
| Spot FX（效果音） | SFX | Yes — frame-accurate |
| Music（音乐） | MUS | No — to named beats on its own bar grid, never to a picture cut |

What each layer is, and the level range each one sits in, belong to
[sound and dialogue](../references/sound-and-dialogue.md) and are deliberately not repeated here —
two copies of a level table is how a mixer ends up 10 dB off. One thing worth carrying across
while you fill the sheet: every level in the skill is dB relative to dialogue at 0, the programme
is anchored once at delivery rather than per layer, and in a scene with no dialogue the 0 is
notional — the level dialogue would have occupied — so the ranges do not move.

One classification rule this sheet does enforce, because it is the cell people get wrong: anything
continuous is RT or AMB whatever object makes it, and only discrete designed events are SFX. A
filament hum belongs in room tone, not in a spot-FX cue that never stops.

## The continuous-bed rule

Room tone and ambience run as one unbroken pair of tracks across the whole scene, laid before any
other layer and never cut at a picture edit. Only foley, spot FX, and music are cut to picture.

This matters more in AI video than in live action: generated clips each carry their own invented
audio and no two agree about the room, so splicing them produces an audible tone change at every
edit — the aural version of a seam (F15, F18). The fix is procedural, not creative:

1. Mute or discard every generated audio track. Treat generated audio as a timing reference only.
2. Lay one room-tone track for the full scene duration plus 1s of handle at each end.
3. Lay one ambience track the same way. Change it only when the *space* changes, and then
   cross-fade over 0.5–1.0s, never on a hard cut.
4. Build foley and spot FX on top, cut to frame.
5. Place music last, against beats you can name.

When the picture does cut to a different room, the bed changes — by cross-fade, and that change is
itself a story event you should be able to justify in one sentence.

## Per-shot five-layer table

Columns follow the Mode H notation in [sound and dialogue](../references/sound-and-dialogue.md):
`Space` names the shot size and any source not in the camera's room — `same room` when there is none — so the perspective moves with the coverage instead of sitting flat across every size. The four cases and their level, filter and reverb offsets are owned by [sound and dialogue](../references/sound-and-dialogue.md). `@t` is time from that shot's first frame, never program time. Absolute program timecodes live in
one place only, [edit timeline template](edit-timeline-template.md), so a re-time changes one
document instead of two. Write `none` in a cell you decided against; leave nothing blank.

| Shot | In–Out | Space | RT | AMB | FOL | SFX | MUS | Dialogue/VO | Silence |
|---|---|---|---|---|---|---|---|---|---|
| `SHnn` |  |  |  |  |  |  |  |  |  |

Filled — `UTD_SC07`. The book's sound direction is explicit: no score anywhere in this scene, and
the paper scraping tile is the loudest thing in it. There is no dialogue here, so 0 is notional and
every level below is read off the bands in
[sound and dialogue](../references/sound-and-dialogue.md) — the paper cue sits at the top of the
spot-FX band rather than being promoted to 0, which keeps this sheet legible next to a scene that
does have dialogue in it.

| Shot | In–Out | Space | RT | AMB | FOL | SFX | MUS | Dialogue/VO | Silence |
|---|---|---|---|---|---|---|---|---|---|
| `SH01` | 0:00–0:04 | WS, stairwell — same room; street is outside heard from inside | Stairwell tone with the filament bulb's hum baked into it, 0.8s reverb tail, continuous, −34 | Street two floors down, distant, no traffic detail, −28 | Cloth shoes on tile, three crossing steps @0.4 / @1.1 / @1.7, the last one short; satchel canvas shift on the stop | none — the hum is continuous, so it belongs in RT and never gets its own cue | none — no score in this scene | none | none |
| `SH02` | 0:04–0:09 | MCU, landing — same room; radio is through a closed door | bed continues | Radio behind the door comes up @0.6 to −18, mid-band only, no intelligible words | Padded-jacket rustle as the arm rises @0.8; one swallow, close, @2.4; jacket settle @4.2 | none | none | none | none |
| `SH03` | 0:09–0:12 | CU, landing — same room; radio and chair are through a closed door | bed continues | Radio holds; street ducks 2 dB | none — deliberate | Chair scrape behind the door @1.5, the first hard sound in the scene | none | none | The book's 1.5s of near-silence, @0.0–@1.5. Not digital silence: the bed stays under, everything else out |
| `SH04` | 0:12–0:18 | MS low, landing — same room; radio through the door, gap line at 20cm | bed continues | Radio holds, unchanged | Knees and heels on tile @0.2; two fingers on wood @5.4 | Paper scraping tile @2.0–@4.6 at −6, the top of the spot-FX band and the loudest cue in the scene, alone in its band | none | none | none |
| `SH05` | 0:18–0:22 | WS, stairwell — same room; radio recedes through the door as he goes | bed continues; tone tail runs 1.0s past picture | Radio and street unchanged — nothing acknowledges that he left | Two backing steps, then four descending, each 2 dB quieter, gone by @3.0 | none | none | none | none |

Reading it: the bed never breaks; only foley and spot FX respect the cuts; the radio enters on
`SH02` and never leaves, so the room behind the door stays occupied for the rest of the scene.
`SH03` carries the scene's turn in its Silence cell and has an empty foley line on purpose — which
is the reason the column exists. A blank there would have read as an oversight and someone would
have filled it with footsteps.

## Music brief

One block per cue, in the field set owned by
[sound and dialogue](../references/sound-and-dialogue.md) — brief the function, never the genre.
When the scene has no score, still write the block: the decision is worth recording, and a written
`none` is the only thing that stops someone adding a cue in the mix six weeks later.

```text
CUE M0  "no cue"
FUNCTION: none. The book scores this scene with a radio the courier cannot control
IN:       n/a
OUT:      n/a
TEMPO:    n/a
INSTR:    n/a
SHAPE:    n/a
NOT:      no cue at any level anywhere in SC07, including under the exit and the end tail
ENFORCED: no music track exists in the timeline; every generated clip's audio is muted at import
```

The diegetic radio is briefed as a source element, not a cue. It belongs to ambience in the layer
table and to the location in the continuity bible, but it needs a brief of its own because someone
has to make or license it, and because it is the only thing in the scene an era error can reach:

```text
SOURCE SRC-radio  "behind door 3F"
FUNCTION: keep the room he will not enter occupied, from SH02 to the end
PLACEMENT: heard through a closed dark-stained door — low-pass around 900 Hz, 0.8s stairwell tail
IN:       SH02 @0.6
OUT:      runs past picture; leaves with the room-tone tail
ERA:      1937 Shanghai broadcast idiom; small band, no synthesis, no modern kit
LEVEL:    -18, ducking 2 dB while the paper cue runs
NOT:      never intelligible in any language; never lands on a cut; never changes program at the
          chair scrape; never resolves when he leaves
```

Two habits behind those blocks. Name the function before the instrumentation, because a function
survives a change of composer and "solo cello" does not. And fill `NOT:` every time — most bad cues
fail by doing too much, and the exclusion is the only line that stops them.

## Dialogue & VO sheet

Speaking rates, the VO density ceiling, and the clip-length formula are owned by
[sound and dialogue](../references/sound-and-dialogue.md). Two of its numbers do all the work in
this column, and they are not the same number:

- **On camera**, the clip has to hold more than the words: `clip = 0.6s pre-roll + line ÷ rate +
  0.8s hold`, then add 2.5s of handle to the generation — a dialogue take is character performance
  and pays the full rate, and the handle budget is owned by
  [editing and assembly](../references/editing-and-assembly.md). A line that merely fits the clip
  length does not fit the clip.
- **Voice-over** is laid in the mix, so it budgets the speech only — but it is capped by picture,
  not by rate: about 1.3 words per second of shot, roughly half dialogue density.

Estimates are for planning. Measure the recorded take before locking picture.

| ID | Shot | Speaker | On/Off | Lang | Line | Delivery | Count | Est. dur | Decision |
|---|---|---|---|---|---|---|---|---|---|
| D1 | `SHnn` |  |  |  |  |  |  |  |  |

Filled — `UTD_SC07` and the head of the next scene:

| ID | Shot | Speaker | On/Off | Lang | Line | Delivery | Count | Est. dur | Decision |
|---|---|---|---|---|---|---|---|---|---|
| A1 | `SH02`–`SH05` | Radio behind door | Off | — | non-verbal, no intelligible words | Muffled, mid-band | — | 18.0s | Not dialogue. Never treat as a line; no lip-sync risk; must not become intelligible in the mix |
| V1 | `SH05` | Courier | VO | EN | "I told myself it was kindness." | Slow, weighted | 6 words | 3.0s speech | **Cut.** 6 words over a 4s shot is 1.5 words/s, over the VO ceiling — but that is not why it goes. At any length it explains the shot's only job. The aftermath is the argument; a VO turns it into a caption |
| D2 | `SC08_SH01` | Woman, 50s | On camera | 中文 | 「他没有敲门。」 | Slow, flat, reading aloud | 5 spoken chars | 2.8s clip | Keep. 5 ÷ 3.5 = 1.4s of speech, plus 0.6s pre-roll and 0.8s hold = 2.8s inside a 4s clip; generate at 6.5s, because a performance take pays the 2.5s handle and a first/last-frame pair cannot buy it back — the drift is between the pinned frames. Lip-sync required: generate speech, or shoot mute and lay VO |

Three decisions that sheet forces now instead of during the mix. A1 is not a line, so nobody
records it and no model is asked to lip-sync it. V1 dies on the page rather than after someone
records it, and the arithmetic is the cheap part of that call — count the spoken units before you
argue about the words. Note what is *not* counted in D2: the full-width period is a spoken pause,
not a character, and counting punctuation is the standard way a Chinese line comes back 20% over
its budget. D2 is also the project's only lip-sync shot, so it is the only place F15 can occur;
budget the retries there and nowhere else.

## Handoff checklist

- [ ] Room tone and ambience exist as single continuous files, scene length plus 1s handles,
      named `PROJ_SCnn_vNN_amb.wav` — version before role, per the continuity bible's grammar.
- [ ] Every generated clip's native audio is muted or deleted, not merely lowered.
- [ ] Every foley entry names the material, not just the object — "cloth shoes on tile".
- [ ] Every spot FX has an `@t` from its own shot's first frame, not just a shot number.
- [ ] The Silence column is filled on every row, including `none`, and nothing over 1s is held at
      true digital zero — the bed stays under it.
- [ ] The music block exists even when the answer is "no score", and says who enforces it.
- [ ] Every dialogue line has an estimated duration and an explicit lip-sync decision.
- [ ] Any on-camera line fits pre-roll plus speech plus hold inside its clip — not just the speech.
- [ ] Every on-camera line is ordered at clip length plus the 2.5s performance handle, not at clip
      length.
- [ ] Total dialogue and cue durations checked against the cut length in
      [edit timeline template](edit-timeline-template.md).
