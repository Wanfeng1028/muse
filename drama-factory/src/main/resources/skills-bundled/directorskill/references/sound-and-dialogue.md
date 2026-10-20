# Sound and Dialogue

Load this file when the deliverable includes a sound plan, generated or lip-synced dialogue, voice-over, a music brief, or when separately generated clips need audio to hold them together (Step 11, Mode H). Fillable template: [sound-plan-template.md](../assets/sound-plan-template.md). Cut logic, handles and timeline mechanics live in [editing-and-assembly.md](editing-and-assembly.md).

Frame-rate assumption throughout: 24 fps. Times written `m:ss.d`. A time written `@t` is measured from that shot's first frame; a bare timecode is program time.

## Sound is a directing decision

Sound gets decided at shot-design time or it does not get decided at all. What a character hears determines where they look; the look determines the eyeline; the eyeline determines the next shot and its screen direction. Write sound after the shot list and you are decorating, not directing.

Three decisions belong in the director's book, before any generation:

1. What the audience hears that the character does not (suspense), or what the character hears that the audience does not (dread).
2. Which of the five layers carries this scene, and which layer is deliberately absent.
3. Where the scene's one silence lands.

Worked, on the doorway scene used throughout this file: the audience hears a television behind the closed door; she never reacts to it, so we never learn whether she heard it. One sound decision, taken before a single shot existed, is what gives the scene its question.

### The continuity-glue rule

In AI film, sound is the cheapest continuity tool available, by an order of magnitude. Lay **one unbroken ambience region under the whole sequence** — a single audio region spanning every clip, not one per clip, never re-triggered at a cut. The ear then reports "one place, one continuous time," and that buys real tolerance for the mismatches generation produces at the seam: wall texture that shifted, a key half a stop off, a grade that drifted.

It buys nothing for state errors. A changed costume, a prop that swapped hands, a different face — the audience reads those as story, and no bed hides them. Those are tracked in [continuity-bible.md](continuity-bible.md) and checked as item 4 of the hard-cut checklist in [editing-and-assembly.md](editing-and-assembly.md). Know which of the two problems you have before you reach for audio.

Test it on your own cut: mute the bed and replay the same two shots. Muted, the cut reads as two different rooms. With the bed, it reads as one room from two angles. That is a free fix. Regenerating the shot is not.

Corollary — **strip model-generated audio**. Many video models emit their own ambience. It restarts at every clip boundary, which is precisely the seam you are trying to hide. Treat model audio as a scratch guide, keep only sync-critical elements (a lip-synced line), mute everything else, and run your own continuous bed underneath.

## The five-layer sound brief

| Layer | Code | Definition | Cut to picture? | Typical level, dB relative to dialogue at 0 |
|---|---|---|---|---|
| Room tone（房间底噪） | RT | The signature of the enclosing space with nothing happening in it: HVAC, refrigerator, lift shaft, hard-surface hiss | No — continuous under everything | −40 to −30 |
| Ambience（环境声） | AMB | The world outside the frame that is doing something: rain, traffic, birds, crowd, machinery, wind | No — continuous, crossfaded only at a location change | −28 to −18 |
| Foley（拟音） | FOL | Body-and-object sounds the on-screen subject makes: footsteps, cloth, breath, sitting, handling | Yes — synced to the visible movement | −22 to −14 |
| Spot effects（效果音） | SFX | Discrete events with a story job: a lock, a phone, a glass, a door, an impact | Yes — synced to the frame | −16 to −6 |
| Music（音乐） | MUS | Score, or source placed physically in the room | No — to named beats on its own bar grid, never to a picture cut | −20 under dialogue, −8 in the clear |

**One scale, and this file owns it.** Every level in the skill is dB relative to dialogue at 0, and dialogue sits at 0 by definition. None of them is dBFS: the programme is anchored once, at delivery, and a per-layer absolute figure is meaningless before that anchor exists. Where a scene has no dialogue, the 0 reference is notional — the level dialogue would have occupied — and the ranges above are unchanged. Do not re-anchor to the loudest element in the scene; that shifts every number in the plan and the mixer has no way to know it happened. The ranges are starting points, not gates: a deliberately suppressed element sits under its band on purpose, and saying so in the plan is the whole point of writing a level down.

[sound-plan-template.md](../assets/sound-plan-template.md) carries the worksheet that records the per-shot decision, and links here rather than restating these ranges. Programme loudness is declared once, in the export block of [edit-timeline-template.md](../assets/edit-timeline-template.md) — web delivery typically lands between −16 and −14 LUFS integrated, so name the figure per project and check your destination platform's current spec rather than assuming one.

### Sound perspective

The layer table bands a level per layer; perspective is what moves an element inside its band. Every source carries the level, filter and reverb of the distance and the barrier between it and the camera, and a plan that reuses one bed unchanged across an extreme wide and a close-up is the single most audible giveaway of assembled-not-recorded sound. Offsets below are relative to the same element heard in the open, in the camera's own room, on the same dB-relative-to-dialogue scale.

| Where the source is | Level | Filter | Reverb |
|---|---|---|---|
| Same room as camera | 0, the reference | Full band | The room's own tail, early reflections audible |
| Through a partition — closed door, wall | −12 to −18 | LPF 600–900 Hz, 12 dB/oct or steeper | Far room's tail only, no near-room early reflections |
| Outside heard from inside — window, street below | −10 to −16 | LPF 1.5–2.5 kHz, thin below 120 Hz unless the source is traffic | Near-room tail added on top: it enters, then reverberates where the camera is |
| Off-screen versus on-screen, same room | −3 to −6 | Unchanged | Roughly half again as much tail; that wet/dry ratio is what places it out of frame |

Shot size moves perspective with it. Hold the widest size as the reference; on a closer size of the same action bring foley up 3–6 dB and dry it, and reverse the move going wide. Leave room tone and ambience where they are — the bed is the one thing a cut must not move, per the continuity-glue rule above.

### Per-shot notation

Compact one-line form, for shot-list and QC rows:

```text
SND S02 | SPACE MCU, stairwell; TV through the closed door -15, LPF 800 Hz, far-room tail only | RT stairwell, cold, faint lift hum | AMB rain on skylight, steady | FOL coat rustle @0.6, parcel paper crush @2.9 | SFX none | MUS M1 in @1.4 | SIL none
```

The Mode H table itself — its columns, the dialogue sheet, the handoff checklist — is owned by [sound-plan-template.md](../assets/sound-plan-template.md). Four notation rules that make either form auditable: every shot gets a room-tone entry even when the entry is "bed continues"; every shot gets a `SPACE` entry naming the shot size and any source not in the camera's room, written `same room` when there is none; a cell you left blank is a decision you did not take, so write `none`; and deliberate silence is written in as an entry, never as an empty cell.

### Which layer carries which genre

Per-genre sound defaults — the carrying layer, the ASL, the key ratio — are owned by [genre-playbooks.md](genre-playbooks.md), whose one-row-per-genre table carries a `Sound lead` column and whose per-genre blocks each carry a `Sound:` line. Load the genre first, then use this file to execute it. Two decisions that table cannot make for you: which layer you are deliberately **suppressing** — naming the absent layer is the choice, and "no score under this beat" is a stronger instruction than any adjective about the score you do want — and where the scene's one silence lands, which is per-scene, never per-genre.

## Diegetic, non-diegetic, meta-diegetic

- **Diegetic**: exists in the world; the characters can hear it. A radio, a doorbell, footsteps.
- **Non-diegetic**: only the audience hears it. Score, narration from outside the story.
- **Meta-diegetic**: sourced inside a character's head — their memory, their imagining, their distorted perception. The audience is loaned the character's interior.

Moving a sound across a boundary costs zero generations and lives entirely in the audio timeline, which is why it is worth reaching for before any picture fix.

| Move | Effect | Execution |
|---|---|---|
| Non-diegetic → diegetic (score turns out to be a radio in the room) | Deflates the moment, grounds the scene, often comic or cruel | Same stem. At the crossing point, band-pass to roughly 300 Hz–4 kHz, add the room's reverb, narrow to mono, drop 6 dB |
| Diegetic → non-diegetic (a source sound continues over a cut to another place) | Abstracts the sound into a theme; links two places or two times | Same stem. Remove the band-pass, go full-band, dry and wide, hold the level |
| Diegetic → meta-diegetic (the world ducks away to a heartbeat, tinnitus, or one breath) | The audience becomes subjective; interiority without a line of dialogue | Duck AMB and FOL by 18–24 dB over 8–16 frames, bring one close, dry element up, hold 1.5–3 s, restore over 12 frames |

Worked, on the doorway scene below. Cue M1 is non-diegetic and stops dead on a frame. Had it instead resolved into the television behind the door — same stem, band-passed to roughly 300 Hz–4 kHz, the door's reverb added, narrowed to mono, dropped 6 dB — the cue would turn out to have been in the room all along, and her hesitation would read as small rather than as felt. That is the deflation move, and naming it is how you decide the scene does not want it.

Discipline: cross a boundary at most once per scene. Twice and the audience stops trusting the sound.

## Sound as pacing

All six devices below live above the picture and cost nothing to generate. Every one of them needs audio handle at the head and tail of each clip; the handle budget and the trim rule are owned by [editing-and-assembly.md](editing-and-assembly.md).

| Device | Definition from the sound side | Numbers | Execution on a stack of separately generated clips |
|---|---|---|---|
| Pre-lap | Shot B's audio arrives before shot B's picture | Lead 0.3–1.0 s; 0.5 s is the safe default | Slide B's audio region left so it starts under A's tail. Nothing about the clips changes |
| Sound bridge | One sound continues across the cut, welding two spaces | Spans the cut by at least 1 s either side | Place the bridging element on its own track, ignore the clip boundary entirely |
| J-cut | Sound leads picture (generalized pre-lap) | 8–24 f of lead | Trim B's audio in-point earlier than B's video in-point |
| L-cut | Picture leads, A's sound continues under B | A's audio runs 0.5–2 s past A's picture | Split A's audio from A's video, extend the audio tail. Requires the audio to have been separated at import |
| Ambience change as a location cut | Swapping the bed at the cut tells the audience they are somewhere new — no establishing shot required | Crossfade 12–24 f (0.5–1.0 s) for a hard place change, matching the bed rule in [sound-plan-template.md](../assets/sound-plan-template.md); 24–48 f for a drift or a time shift | Removes one generated establishing clip per location, which is the largest saving audio makes on the shot count |
| Hard silence as a cut | Everything drops for a few frames at the cut point | 4–12 f | The ear registers the discontinuity even when the eye does not. Useful precisely where the visual match is weak |

## Silence engineering

Silence and quiet are different tools. **Quiet** thins the layers: kill SFX and score, keep RT and one AMB element. **Silence** removes everything including room tone, which is a violent, unnatural event and reads as an authored decision.

Duration limits, measured from the last audible element:

| Held for | Reads as |
|---|---|
| 4–12 f | A punctuation mark; the audience does not consciously notice |
| 0.5–1.0 s | Impact, shock, or the floor dropping out. Safe |
| 1.0–2.0 s | Deliberate and heavy. Works only if the picture is doing something |
| Over 2.0 s of true digital silence | A technical fault. The audience checks their speakers |

Rule: past 1.0 s, do not hold at true zero. Fall to a room-tone floor roughly 15 dB under the bed's working level instead — with room tone running at −30, that floor is −45 on the same relative-to-dialogue scale as every other number here, not an absolute dBFS figure. The audience still experiences silence; the playback system still sounds alive.

Placement: put silence **before** the line that matters, not after it. Put it **on the reaction**, not on the action. Worked, on the doorway scene: her last footfall lands at `@4.5`, she breathes out at `@5.8`, and then the bed holds alone for 1.2 s while she does nothing but stand at the door. The silence is the decision; the picture only shows the pause. After an impact, one held beat of quiet is what makes the impact memorable — see the breath pattern in [editing-and-assembly.md](editing-and-assembly.md).

## Dialogue for AI video

### Duration budgeting

| Delivery | EN words/s | EN syllables/s | 中文 字/s (characters ≈ syllables) |
|---|---|---|---|
| Weighted, held, thinking between words | 1.6–2.0 | 3.0–3.5 | 3.0–3.5 |
| Neutral film delivery | 2.3–2.7 | 4.0–4.5 | 4.0–5.0 |
| Brisk, argument, comedy | 3.0–3.5 | 5.0–6.0 | 5.5–6.5 |

Working rule of thumb: **2.5 English words per second, 4.5 Chinese characters per second**, matching the planning rates in [sound-plan-template.md](../assets/sound-plan-template.md). Then budget the clip:

```text
clip_length = 0.6 s pre-roll + (words / 2.5) + 0.8 s hold after the last word
generate    = clip_length + 2.5 s of handle
```

A dialogue take is character performance, so it pays the full 2.5 s rate rather than the 1.5 s minimum. The handle budget and its single first/last-frame exception are owned by [editing-and-assembly.md](editing-and-assembly.md); a lip-synced take is never that exception, because the performance happens between the two pinned frames and is exactly what drifts.

| Cut length (generate 2.5 s more) | Words that physically fit | 中文字数 |
|---|---|---|
| 5 s | 9 | 16 |
| 6 s | 11 | 20 |
| 8 s | 16 | 30 |
| 10 s | 21 | 40 |

Two different ceilings apply, and confusing them is the most common planning error in this step:

- **Duration ceiling** — the table above. Whether the words physically fit inside a clip of that length. It is never the binding constraint.
- **Reliability ceiling** — much lower, and it is what actually breaks. An **on-camera lip-synced line: 6 words or fewer, MCU or tighter, and keep the generated clip short, around 4 s** (F15 in [failure-modes.md](failure-modes.md)). Any spoken line laid over picture in the edit — off-screen, VO, over a listening shot — **one sentence, 12 words or fewer per clip**.

So a 10 s clip has room for 21 words, must not carry more than 12, and must not carry more than 6 if the speaker's mouth is visible and in sync. Past those, split the line across shots. You cannot trim your way out, because the line needs its whole duration.

### Lines that lip-sync well, and lines that do not

Write toward:

- Bilabials and open vowels — p, b, m plus "ah / oh / oo". Large, distinct mouth shapes that survive a low-resolution sync model.
- Stressed first syllables. "Stop. I said stop." beats "Well, actually, I did ask you to stop."
- Short declaratives with one idea each.

Write away from:

- Consonant clusters and sibilant strings ("strengths," "she sees six ships"). They smear into a single mouth shape.
- Lines whose meaning hinges on one unstressed monosyllable — "I can't do that" versus "I can do that." Sync smear can flip the sense of the scene.
- Whisper and shout. Both extremes desync in practice; sync holds best on mid-register modal delivery.
- Overlaps, interruptions, and trailing-off. There is no way to specify them inside one generation.
- Numbers and proper nouns, if the model is also generating the voice.

### The one-speaker-per-clip rule

One speaking face per generated clip, wherever the surface does not expose synchronized multi-speaker speech — check your target's `Dialogue + lip-sync` cell in the capability matrix of [ai-video-tool-adapters.md](ai-video-tool-adapters.md), which owns that reading, before you assume either way. Absent a confirmed multi-speaker feature, treat the rule as absolute.

Reasons, in order of how often they bite: sync systems bind one voice track to one detected face, so two faces produce either the wrong mouth moving or both mouths moving; a two-hander inside one clip has no cut point, because you cannot control where a cut falls inside a generation; and a second face doubles the identity-drift surface for no gain.

### Building shot-reverse-shot from single-speaker generations

Generate four assets per two-hander setup, then assemble any exchange of any length from them:

1. **A-speaking** — MCU, eyeline camera-right, clean single.
2. **A-listening** — same size, same lens, same light, eyeline held camera-right, no mouth movement.
3. **B-speaking** — mirrored setup, eyeline camera-left.
4. **B-listening** — mirrored, eyeline camera-left.

Screen direction, the 180° line and the 30° rule are owned by [cinematic-language.md](cinematic-language.md); hold to whatever side that file's geometry assigns before you generate anything.

Two economics notes. Generate the **listening** clips at the longest duration the tool offers — they are your flex material, trimmed to fit whatever the lines turn out to be, and a listening clip has no lip-sync risk, so its first-pass success rate is high. And once the four assets exist, a six-line exchange costs zero further generations.

### Speaker labeling that stops identity swaps

Weak prompt:

```text
Two people argue in a kitchen. The man says "You promised."
```

Strong prompt:

```text
MARA — woman, 34, short black hair, grey wool coat — stands camera-left, facing camera-right, and speaks one line: "You promised." She is the only person in frame. No other character, no other voice, no off-screen speech.
```

Rules: a label is NAME plus three fixed physical anchors plus a screen position; reuse the identical anchor string in every prompt for that character (the canonical string is owned by [continuity-bible.md](continuity-bible.md)); name exactly one speaker per prompt; and state the negative explicitly — "only one person speaks" and "no other character in frame" — because silence about a second person is not the same as excluding one.

### When to abandon on-screen dialogue

Work down this ladder and stop at the first line that fits:

1. Can the line be a look instead? Cut it. This is the correct answer more often than directors admit.
2. Necessary and 6 words or fewer? On-screen, one speaker per clip, MCU or tighter, generated clip around 4 s.
3. Longer than 6 words, technical, or an exchange? Convert to an **off-screen line** played over a listening shot. No lip-sync required, which removes the biggest single failure mode in the pipeline.
4. Exposition? **Voice-over** over inserts and detail shots.
5. Emotional peak with hard-to-sync delivery — crying, shouting, breaking off? **Reaction only**: hold on the face, play the delivery off-camera.

### Rewrite example: an ungeneratable exchange made generatable

Before — four lines, an overlap, an interruption, two speakers, 20-word sentences:

```text
INT. KITCHEN — NIGHT
MARA:  You said you'd tell them. You promised me, in this room, three weeks ago —
DAVID: (overlapping) Don't. Don't do the "in this room" thing.
MARA:  — and you looked at me and said it was handled.
DAVID: It is handled. It's just not handled the way you wanted it handled.
```

After — four single-speaker clips, every on-camera line at or under the 6-word sync ceiling:

```text
C1  4.5 s  MARA  MCU, speaking: "You promised. In this room."           (5 w, on camera)
           Trim her post-line hold to 0.3 s so the cut lands near her last word.
C2  4.0 s  DAVID MCU. Generated as 1.0 s of listening, then "Don't do that."  (3 w)
           That listening second is designed lead, not the trim handle: it is
           there to be cut into. Trim it off and start C2 0.4 s into his line,
           so the picture cut arrives with the line already running. The take
           still pays its 2.5 s of handle on top of the 4.0 s.
C3  8.0 s  MARA  MCU listening, no line, generated long on purpose.
           Trimmed to 4.4 s. DAVID's next line plays OFF-SCREEN over her face:
           "It's handled. Just not your way."                           (6 w, no lip-sync)
C4  5.0 s  DAVID MCU, one held look, no line. No sync risk, so length is free.
```

What survives: the accusation, the deflection, the fact that "handled" is a lie, and who ends the scene holding the power. What no single generation can hold: the overlap.

How the overlap comes back — start David's audio 0.4 s before the picture cut, so his first word lands on the tail of Mara's last word while her face is still on screen. That is a J-cut of about 10 f, and it is the whole reason C2 was generated with a listening head you intend to throw away. **The overlap is created in the edit, not in the generation.** That is the general principle for this section: anything that requires two performances to collide belongs to the timeline, not to the prompt.

## Voice-over

VO is a crutch when it states what the image already shows, explains a feeling the performance should carry, or patches a scene that does not work. VO is structure when it comes from a different time or person than the picture — a later self, another character, a letter, an institutional voice — or when the picture is fragmentary by design.

The reliable device is **VO that contradicts the image**. The words say one thing, the picture quietly shows another, and the gap is the meaning. Construct it by writing a flatly factual VO line, then designing the shot so it contradicts exactly one word in that line. VO: "We were fine that year." Picture: an unmade bed, two coats by the door, one of them dusty.

Writing VO that leaves room for the picture:

- Density ceiling: **1.3 words per second of picture**, roughly half of dialogue density. VO that runs at dialogue density turns the film into an illustrated podcast.
- Enter 0.8–1.5 s after the cut, never on the first frame. The audience needs to see the shot before they are told about it.
- Exit at least 1.0 s before the shot ends. Never land the last word on the last frame.
- One idea per shot. If a VO sentence needs two shots, split the sentence.

## Music brief

Brief the **function**, not the genre. "Sad piano" is unbuildable; "hold the audience inside her indecision and refuse to resolve" is buildable by any composer or search.

Function vocabulary: PRESSURE, WITHHOLD, RELEASE, IRONY (contradicts the picture), GLUE (spans a visual discontinuity), CLOCK (drives the cut rhythm), PERMISSION (tells the audience the scene is over and they may now feel).

The keys below are the ones [sound-plan-template.md](../assets/sound-plan-template.md) uses, so a filled brief drops straight into the Mode H deliverable. This is cue M1 of the worked example at the end of this file:

```yaml
cue_id: M1
scene: DW_SC01
function: WITHHOLD — hold her indecision, never resolve, no cadence
in_point: "0:10.2"
out_point: "0:23.5"
tempo: 72 BPM, 4/4, bar = 3.33 s
bar_lines: ["0:10.2", "0:13.5", "0:16.9", "0:20.2", "0:23.5"]
instrumentation: solo cello, one sustained synth pad beneath, no percussion, no piano
shape: enter at -30, rise 6 dB across 8 s, stop dead on the frame
level_rel_dialogue: -30 rising to -24, deliberately under the music band
must_not: no hummable melody, no cadence, no swell at the exit, no hit on the bag set-down
```

The `must_not` line does more work than the rest of the brief. Fill it every time, including when the answer is "no score in this scene" — the template keeps that block too, so nobody adds a cue in the mix.

### BPM to cut length (4/4)

Use this to let tempo drive shot durations rather than fighting it. Cutting on a bar line is invisible; cutting a fraction off a beat is audible as a stumble.

| BPM | Beat | 1 bar (4 beats) | 2 bars | 4 bars | Natural cut unit |
|---|---|---|---|---|---|
| 60 | 1.00 s | 4.00 s | 8.00 s | 16.0 s | 1–2 bars — slow drama |
| 72 | 0.83 s | 3.33 s | 6.67 s | 13.3 s | 2 bars — drama |
| 80 | 0.75 s | 3.00 s | 6.00 s | 12.0 s | 2 bars — drama |
| 90 | 0.67 s | 2.67 s | 5.33 s | 10.7 s | 1–2 bars |
| 100 | 0.60 s | 2.40 s | 4.80 s | 9.60 s | 1 bar — commercial |
| 120 | 0.50 s | 2.00 s | 4.00 s | 8.00 s | 1 bar — montage |
| 128 | 0.47 s | 1.88 s | 3.75 s | 7.50 s | 1 bar — social vertical |
| 140 | 0.43 s | 1.71 s | 3.43 s | 6.86 s | 1 bar — trailer mid-section |
| 160 | 0.38 s | 1.50 s | 3.00 s | 6.00 s | 1 bar — action |
| 174 | 0.34 s | 1.38 s | 2.76 s | 5.52 s | 1–2 bars |

Read it in both directions. If you want 3-second shots, you want 80 BPM at one bar per shot, or 160 BPM at two. If the track is fixed at 128 BPM, your shot lengths are multiples of the 0.47 s beat — 0.94 / 1.41 / 1.88 / 2.81 / 3.75 / 7.50 s — and where you land inside that grid is itself a choice: a bar line is invisible, beats 2, 3 and 4 are audible but musical, and anything off the grid reads as an error.

### Temp track discipline

Choose a temp by tempo, arrangement density and dynamic shape — never because you like the song. The moment four shots are cut to a hook, the hook owns the edit and every replacement fails against it. If you must temp with a real track, use its first eight bars looped and never cut to its chorus. In the plan, log the **BPM and the shape**, not the track title, so the brief stays executable by someone who has never heard your temp.

### When music should be absent

- Any beat where the question is "what will they do." Score answers it before the character does.
- Under a comic pause. The score fills the hole the laugh was going to occupy.
- The first 15–20 seconds, if the world's own sound needs to establish it. Music has exactly one entrance; spending it on frame one wastes it.
- Under dialogue that is already carrying subtext. Score there becomes an instruction to the audience.
- When the picture already has a pulse — rain, machinery, a treadmill, footsteps, breathing. Two clocks fight.

## Worked example: 25-second, three-shot scene

Scene: a person stands at a closed apartment door holding something they intend to give away, hesitates, and leaves without knocking. Register: drama. Carrying layers: room tone plus foley, with one cue late.

Below is a filled Mode H plan in the column shape of [sound-plan-template.md](../assets/sound-plan-template.md); the template owns the blank form and the handoff checklist.

```markdown
## Sound Plan — "Doorway" (DW_SC01, 0:00–0:25.0, 3 shots, 24 fps)

Picture, for reference only:
  S01  0:00.0–0:09.8  WS landing; she climbs into frame and stops at the door
  S02  0:09.8–0:18.6  MCU her hands on the parcel, then her face at the door
  S03  0:18.6–0:25.0  WS from behind; she turns, sets the parcel down, descends

Bed — one region per layer, 0:00–0:25 plus 1 s handles, never re-triggered at a cut:
  Room tone  interior stairwell, cold concrete, faint lift-motor hum .... -30
  Ambience   rain on the skylight two floors up, steady, no gusts ....... -26

| Shot | In-Out | Dur | Room tone | Ambience | Foley | Spot FX | Music |
|---|---|---|---|---|---|---|---|
| SH01 | 0:00.0-0:09.8 | 9.8 s | bed | bed | Shoe on concrete x6 at @0.0 / 0.7 / 1.5 / 2.4 / 3.4 / 4.5, gaps lengthening as she slows; coat rustle @5.0; breath out @5.8; one scuff @7.6 as her weight shifts. Deliberate: nothing between @5.8 and @7.0 but the bed | none | none - no score yet |
| SH02 | 0:09.8-0:18.6 | 8.8 s | bed continues | bed, 2 dB down - she is closer to the wall | Parcel paper crush @0.4 and @2.1; fabric shift @3.8 | Television behind the door: muffled, no intelligible word, LPF ~800 Hz, -30, in at 0:09.4 (10 f before the picture cut), holds to the end of the shot | M1 in at 0:10.2 |
| SH03 | 0:18.6-0:25.0 | 6.4 s | bed continues; tail runs 1 s past picture | bed returns to level, +2 dB as she moves back into the stairwell | Parcel set down @1.0, soft, no thud; 5 descending steps from @2.2, accelerating and thinning, last one at @4.7 | Television falls 12 dB from @2.2 to @4.9 as she descends out of earshot; gone by 0:23.5 | M1 out at 0:23.5, cut dead on the frame |

### Music
M1 exactly as briefed in the music-brief block above. No second cue.

### Dialogue / VO
None. The television is the only voice and it is deliberately unintelligible - the
audience must not learn whether anyone is home. No lip-sync anywhere in this scene,
so F15 cannot occur in it.

### Silence map
0:05.8-0:07.0  quiet, 1.2 s - bed only. Sits in the 1.0-2.0 s band, which is legal
               only because the picture is doing something: she has stopped moving
               and has not yet decided.
0:23.5-0:25.0  quiet, 1.5 s - score cut dead, television out of earshot, bed only.
No true digital silence anywhere. The bed never falls below -45 relative to dialogue,
15 dB under its working level.

### Assembly notes
- One room-tone region and one ambience region across all three clips. Mute every
  clip's model-generated audio at import.
- The television enters at 0:09.4, 10 f before the picture cut to S02, so the cut is
  motivated by sound. Written as J-cut 10f in the timeline.
- S02 to S03 is the same location, so the bed does not change; the +2 dB is a level
  move, not a new region.
- The descending steps thin out and stop at @4.7 (0:23.3), before the quiet begins.
  She is still on the stairs when the sound leaves her, so the scene ends on the
  room rather than on her.
```

Cross-checks before this plan is finished: every shot has a room-tone entry; the bed is one region per layer; each silence is placed and inside the duration limits; the cue has a `must_not` line; no on-camera line exceeds 6 words and no laid-in line exceeds 12. Failures in generated audio and lip-sync are diagnosed as F15 and F18 in [failure-modes.md](failure-modes.md); per-tool audio control surfaces are in [ai-video-tool-adapters.md](ai-video-tool-adapters.md).
