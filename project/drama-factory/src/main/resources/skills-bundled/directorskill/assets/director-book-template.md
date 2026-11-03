# Director's Book Template

Load this file when you are at Step 5 (director's book / visual treatment) or the user asked for Mode C — a 导演阐述, visual treatment, style bible, or "set the rules before we shoot".

## A director's book is a constraint document

It is not a mood board and not an essay. Its only job is to make later decisions non-arbitrary. Every entry must pass this test:

> Hand the book to two people who have never spoken to each other. Have each write shots 06–10 of the same scene from it. The two sets must cut together — same lenses, same key direction, same palette, same cut rhythm.

If one of them could reasonably choose a 24mm handheld orbit under a big soft source and still be "following the book", the book is not written yet. Prefer a number, a named source, or a forbidden list to any adjective. "Warm and nostalgic" fails the test. "Single bare-bulb 2700K practical, hard, high camera-left 45°, 5:1, no added fill" passes it.

Four more standing rules:

- Anything the book does not forbid, someone will do. Every policy section needs a `never` line.
- The book is written once and quoted forever. The strings in the invariants section get pasted verbatim into every keyframe and video prompt — write them so they survive copy-paste without editing.
- Invariants are described in world space, never in camera space. "High camera-left 45°" is true of one setup and false of its reverse, so it belongs in the shot plan's Light dir column, not in a string that every shot pastes. Write the invariant as "a bare bulb hanging over the stairhead"; let each row say where that lands relative to its own camera.
- `NEG_BASE` names instances, never categories. "No modern objects" is a category no generator can resolve into things, and it is the mechanism behind F8 in [failure modes](../references/failure-modes.md) — name the objects instead: no plastic, no lever handles, no rubber soles, no wristwatch, no printed logos. Keep the whole string to about six classes so it can be pasted into a tool's negative field unedited; inline, paste only the classes this framing can actually produce.

## Skeleton

Fill every field. Delete nothing; write `n/a — <reason>` if a field genuinely does not apply.

```markdown
# Director's Book — <project> / <scene or sequence>

## Frame
- Format: <short film | trailer | scene | spot> · Aspect: <16:9 | 2.39:1 | 4:3 | 9:16>
- Target duration: <s> · Shot count: <n> · Tool class: <first/last-frame · reference-binding · text-to-video>
- Style lens: <slug from ../references/director_styles/, or none — and if none, the genre default used>

## Delivery
- Platform and spec: <where it plays, and the spec you actually checked>
- Safe area: <top % and bottom % you are keeping clear, and the source you checked>
- Captions: <burned in | platform auto | none> · <who burns them, at which step>
- Hook frame: <timecode> — <what is on it>
- Retention checkpoints: <timecodes at which something visibly changes>
- Loudness: <integrated target> · True peak: <ceiling>
- Never: <the delivery habits that would break this format>

## Story
- Logline: <one sentence — who wants what, what stops them, what it costs. No adjectives.>
- Dramatic core: <the collision this scene exists to stage.>
- Subtext: <what it is really about, which nobody in it says out loud.>
- Emotional arc: <state → pressure → turn → state. Endpoints copied from the beat sheet.>
- Visual thesis: <one concrete, photographable rule governing every frame. Testable, not poetic.>

## Lens and framing policy
- Kit: <2-4 focal lengths in mm, full-frame equivalent> — <what each one is for>
- Size-to-lens map: <which shot sizes go on which lens>
- Camera height: <default height and the one exception>
- Headroom / edge policy: <where the subject sits in frame and why>
- Never: <focal lengths and framings that are out of bounds for this project>

## Camera grammar and allowed move set
- Allowed moves: <explicit list of named moves — everything else is forbidden>
- Move budget: <n of N shots may move; max one move per shot>
- Motivation rule: <what has to be true before a move is permitted>
- Never: <named moves that are out of bounds>

## Lighting logic and key direction policy
- Key: <quality, world-space position, height, motivating practical — camera-relative
  degrees belong in the shot plan>
- Ratio: <lit side : shadow side measured on the face, and what the fill actually is — a
  source, a bounce, or nothing. The convention is owned by ../references/lighting-and-color.md;
  a bare ratio written key-to-fill comes back a stop flatter than designed>
- Practical sources in the world: <named fixtures>
- What stays dark: <the planes deliberately held under, and by how many stops>
- Never: <sources, ratios, or directions that break the world>

## Palette and color script
- Dominant / accent / forbidden: <plain color words, not brand names>
- Saturation / contrast: <low | mid | high, each>
- Color script: <how the balance moves beat by beat>

## Production design anchors and era lock
- Era: <place and year> · Anchors: <5-8 specific objects, materials, finishes>
- Must avoid: <anachronisms this era invites, and the AI-specific ones>

## Performance register
- Register: <named>· Largest permitted gesture: <specific>
- Performance lives in: <hands | eyes | breath | posture>
- Never: <the acting the material will tempt you into>

## Editing rhythm and target ASL
- Target ASL: <range in s> · Longest shot: <s> · Shortest: <s>
- Cut point policy: <what frame you cut on>
- Transitions allowed: <list> · Never: <list>

## Sound direction
- Music: <policy, including "none"> · Ambience bed: <named>
- Signature event: <the one sound the scene is built around>
- Silence: <where, and how long>
- Never: <the sounds that would betray the world or do the audience's work for them>

## Invariants
<The copy-paste block. See rules above.>
```

Cross-references, so the book stays a decision record rather than a textbook: lens psychology, sizes, coverage geometry, aspect behaviour and the vertical safe zones the `Delivery` block records in [cinematic language](../references/cinematic-language.md); the loudness figure the `Delivery` block names, declared once, in [edit timeline template](edit-timeline-template.md); ratios, motivation and grading language in [lighting and color](../references/lighting-and-color.md); ASL math and cut logic in [editing and assembly](../references/editing-and-assembly.md); sound in [sound and dialogue](../references/sound-and-dialogue.md); genre defaults in [genre playbooks](../references/genre-playbooks.md); identity strings, ids and seeds in [continuity bible](../references/continuity-bible.md); banned words in [prompt lexicon](../references/prompt-lexicon.md); which control surfaces a tool class actually exposes, including in-frame text, in [image model adapters](../references/image-model-adapters.md).

## Worked example

Abbreviated but real. Beats referenced as `B1`…`B5` come from [beat sheet](beat-sheet-template.md); the shots built from this book are in [shot plan](shot-plan-template.md).

```markdown
# Director's Book — Under the Door / scene 7

## Frame
- Format: short film scene · Aspect: 16:9
- Target duration: 22s · Shot count: 5 · Tool class: first/last-frame image-to-video
- Style lens: none — genre default is restrained period drama, not noir

## Delivery
- Platform: festival short, 1920x1080 at 24 fps, 16:9. Nothing overlays the frame
- Safe area: none applied — no platform UI to clear. If this is ever re-cut vertically it gets
  re-blocked, never cropped: the door plane occupies the right two-thirds of every door-side
  frame and a 9:16 crop throws it away. Vertical safe-zone percentages, when they are needed,
  are in ../references/cinematic-language.md and are per-platform
- Captions: none. No intelligible speech exists in the scene to caption
- Hook frame: n/a — scene 7 of a film, not a feed piece; it inherits the reel's open
- Retention checkpoints: n/a for this delivery
- Loudness: −14 LUFS integrated, true peak −1 dBTP, declared once in the edit timeline's
  export block and nowhere else
- Never: burned-in subtitles, an end card, a platform crop through the door plane

## Story
- Logline: A courier paid to deliver a letter decides he would rather the person inside
  never sees his face, and slides it under the door instead of knocking.
- Dramatic core: He has one job and one decency and they point in opposite directions.
  Choosing the job means choosing not to be present for what the job does.
- Subtext: Cowardice dressed as professionalism. He tells himself he is finishing an errand.
- Emotional arc: On-task → his own hand refuses → the person inside becomes audible →
  he commits irreversibly → he is gone and the letter is not.
- Visual thesis: The door grows and the courier shrinks until the only thing in frame
  still holding light is the 4cm gap underneath it.

## Lens and framing policy
- Kit: 35mm (anything containing both the courier and the door), 50mm (his single
  coverage), 85mm (inserts of the gap and the envelope only)
- Size-to-lens map: EWS/WS/MS on 35 · MCU/CU on 50 · ECU on 85
- Camera height: eye level, except the two door-side setups on the floor at 15cm (B3)
  and 40cm (B4). Heights in cm, so nothing in the plan reads as a focal length.
- Headroom: he sits low in frame with cracked plaster above him in every wide
- Never: 24mm or wider (the corridor's perspective goes cartoonish and reads modern);
  never the door plane fully frontal and centred except the floor-level insert at B3,
  where head-on is the whole point and the one exception makes it land

## Camera grammar and allowed move set
- Allowed: locked, slow dolly-in
- Move budget: 1 of 5 shots may move; max one move per shot, one direction, no reverse
- Motivation rule: the camera moves only when he commits to something (B4 only)
- Never: handheld, orbit, whip pan, crane, zoom. He is disciplined; the camera does not
  panic on his behalf.

## Lighting logic and key direction policy
- Key: bare filament bulb hanging over the stairhead, warm ~2700K, hard, above head
  height and on the stair side of the landing. Every setup in this scene stays on one
  side of the line, so that lands camera-left 45° in all five shots — but the shot plan
  is where that gets written, not here.
- Ratio: 5:1 lit side to shadow side on his face, and the fill is bounce off the cream
  plaster opposite. Nothing is added.
- Practicals: the stairhead bulb, the stairwell window behind him at the head of the
  stairs, the room behind the door
- What stays dark: the door face sits 1.5 stops under him; the only light on the door is
  the thin warm line spilling from the gap beneath it
- Never: a second key, any added bounce, any source in front of the door. The cold window
  is a rim on his back and never a fill — it is behind him, so it cannot open the shadow
  side, and any row that calls it fill has the geometry wrong.

## Palette and color script
- Dominant: dull green wainscot, cracked cream plaster, worn red tile
- Accent: the warm bulb and the door-gap line · Forbidden: any saturated blue, any neon
- Saturation low, contrast high in the lower third of frame
- Color script: B1 coolest (window-dominant), warming as he closes on the door, B4 warmest
  and lowest, B5 returns to cool — except the gap, which stays warm after he leaves. The
  envelope is the only pure white in the scene.

## Production design anchors and era lock
- Era: Shanghai lilong（里弄）apartment block, winter 1937
- Anchors: peeling dark-green wainscot to waist height, mortise knob with a brass
  escutcheon, worn red floor tile, painted iron stair rail, wool cap, canvas satchel,
  padded cotton jacket, a chip in the door's lower-left corner
- Must avoid: lever handles, plastic, conduit wiring, rubber soles, wristwatch, printed
  logos, glass in the door. AI-specific: the brass number plate stays defocused or
  cropped. Not because text cannot be rendered — several image models handle it well —
  but because it would have to render identically across three shots, and small in-frame
  text drifts between generations. The chipped lower-left door corner carries the
  identification instead: it is a shape, and shapes survive re-generation.

## Performance register
- Register: contained · Largest permitted gesture: a two-finger push
- Performance lives in: hands, then breath. The face gets one swallow, in B2.
- Never: crying, head-shaking, hands through hair, any gesture above shoulder height
  except the aborted knock

## Editing rhythm and target ASL
- Target ASL 4-5s (22s / 5 shots = 4.4s) · Longest 6s (B4) · Shortest 3s (B3)
- Logged deviation: genre default 7-16s (period, per ../references/genre-playbooks.md) →
  chosen 4-5s, because the scene runs 22s total and its pressure comes from the courier's
  shrinking runway rather than from held duration. The period register is carried by lens,
  staging and palette instead of by shot length
- Nothing under 2.5s: below that there is no runway for an action to start, complete and
  settle inside one generated clip, and the cut arrives mid-gesture
- Cut point: cut on the frame the action completes, never on the recovery
- Transitions between shots: hard cut only · Never: dissolve, whip, match cut, or any fade
  between two shots. The programme itself may open up from black and close to it — a
  programme fade is not an inter-shot transition and this line does not forbid it

## Sound direction
- Music: none. There is no score anywhere in this scene.
- Ambience: stairwell reverb, roughly 0.8s tail; a muffled radio behind the door, mid-band
  only, no intelligible words; street sound two floors down
- Signature event: the paper scraping tile — the loudest thing in the scene, and the only
  sound that gets its own clear moment
- Silence: 1.5s of near-silence between the aborted knock and the chair scrape
- Never: score of any kind, crisp foley footsteps, any intelligible word through the door

## Invariants
Paste these verbatim into every keyframe and video prompt for this scene. World space
only — the per-shot camera-relative direction is the shot plan's job.

ID_COURIER: a 19-year-old Chinese man with a narrow jaw, deep-set eyes under a low
brow, a 2 cm scar through the left eyebrow, black hair clipped short and shaved high at
the neck, in a grey padded cotton jacket buttoned to the throat with one bone button
missing at the collar

LOCK_LANDING: third-floor landing of a 1937 Shanghai lilong apartment block, peeling
dark-green wainscot to waist height, cracked cream plaster above, worn red floor tile,
dark-stained door with a brass knob and a chipped lower-left corner, a stairwell window
at the head of the stairs opposite the door

LIGHT_INVARIANT: a single bare filament bulb hanging over the stairhead, warm, hard, above
head height, 5:1 lit side to shadow side with no fill but plaster bounce; cold daylight from
the stairwell window behind him, rimming his back and cap and never reaching his shadow
side; the door face stays well under; the only light on the door is a thin warm line
spilling from the 4cm gap beneath it

NEG_BASE: no rendered text, signage or numerals; no watermark; no lever handles, plastic,
rubber soles, wristwatch or printed logos; no extra people; no face or costume change; the
door never opens
```

## Failure signs

- A section that could be pasted into a different project unchanged. Delete and rewrite it with this project's nouns.
- A `never` list that is empty. You have not made a choice yet.
- Palette given as a mood ("melancholy blue"). Name the object that is that color.
- ASL given without a shot count and a duration. It is arithmetic, not a feeling.
- ASL that departs from the genre default with no logged reason. The deviation is usually right; the silence about it is what breaks, because Step 7 cannot tell a decision from an oversight.
- A `NEG_BASE` containing a category — "no modern objects", "nothing anachronistic", "no bad anatomy". Name the things instead, or the string does nothing and F8 arrives anyway.
- A `Delivery` block with `Aspect` filled and everything else blank. That is how a vertical piece gets planned as a scene and loses its format in the edit.
- Invariant strings written in the second person or containing instructions ("try to keep"). They are descriptions and must read as descriptions when pasted mid-prompt.
- Camera-relative words (`camera-left`, `frame-right`, `behind camera`) anywhere in the invariants. They are true for one setup and wrong for its reverse, and they get pasted into both.
