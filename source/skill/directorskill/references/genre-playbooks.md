# Genre Playbooks

Load this file when the project has a genre or format but no named director style lens, or when you need to check a genre's default before deviating from it.

## How to use a playbook

A playbook is a set of pre-decided defaults for one genre. It fires at **Step 5 (Director's book)**, is written into Mode C, and carries through Step 6 (blocking), Step 7 (shot list), Step 10 (video prompts), Step 11 (sound), and Step 12 (edit). It does not replace craft reasoning — it pre-decides the twelve items every block below carries, so you argue them once per project instead of once per scene.

Precedence, highest wins:

1. Explicit user instruction ("shoot it flat, no push-ins").
2. Director style lens chosen at Step 4 (`director_styles/`). **A lens outranks a genre on every field it defines.** If the lens sets `lighting.key_ratio: "2:1"` and the horror playbook says 8:1–16:1, you shoot 2:1. The genre still supplies what the style parameter schema does not carry at all — the dramatic engine and the audience contract — plus any dimension the lens leaves unopinionated. All twenty packaged modules fill all thirteen keys of the schema, so a packaged lens never leaves one; the unopinionated case is a lens improvised for this project from a user's reference images or a one-line brief.
3. This file's genre defaults.
4. Skill-level defaults in `SKILL.md`.

Four axes set the fields, and each owns different ones. Settle this before you argue any individual default:

- **Delivery format owns the container.** Aspect ratio, safe margins, clip duration, the **ASL floor** — the shortest shot the format permits, never the ASL target — and the beat **structure**: hook / demonstration / claim / end card for a commercial, hook / change / change / payoff for a social vertical, premise / escalation / barrage / button for a trailer. Where a format and a genre both propose a structure, the format's blocks win and the genre fills them.
- **The director lens owns the craft.** Camera and lens, movement, lighting, palette, blocking, sound, and pacing — including the **ASL target**, which is the number the format's floor constrains from below and nothing constrains from above. These are the seven craft dials named below. This is precedence 2 restated: a lens outranks a genre on every field it defines.
- **The genre owns the dramaturgy.** Dramatic engine and audience contract, always — no lens carries them, and no format replaces them. The seven craft dials come from the genre only when no lens is loaded, or on a dimension an improvised lens left unopinionated.
- **Delivery format outranks the lens on aspect and clip duration only.** It does not outrank the lens on composition. Where a lens's composition rules assume the aspect in its `aspect_bias` field, the lens is neither ignored nor pasted through unchanged: it owes a **restated** composition rule for the delivery aspect. Log the restatement in the director's book as `lens rule at <aspect_bias> → restated as <rule> at <delivery aspect>`, so every later shot inherits the restatement rather than re-deciding it.
- **A genre is a starting position, not a cage.** Deviate freely, but log it in the director's book as `genre default X → chosen Y because Z`. If you have overridden more than three of the seven craft dials named below, you are not deviating — you have chosen a different genre or a hybrid. Say which, and re-derive from that playbook instead of drifting.

Worked, format × genre. Horror delivered vertically keeps horror's 8:1–16:1 key and its silence; takes vertical's 9:16 frame, its safe margins and its top-third face placement; and takes vertical's **0.7 s ASL floor**, which is a minimum and not a range. The ASL target stays horror's 3–8 s build, because the format forbids a shot shorter than the floor and obliges nothing else. A vertical horror piece cutting at an average of 4 s is correct; one cutting at 0.4 s is out of spec.

Worked, format × lens. A lens whose signature is a standing figure at 8–15% of frame height with the camera 12–22 m back ([19_michael_mann.md](director_styles/19_michael_mann.md), `aspect_bias: "2.39:1 / 1.85:1"`) cannot hold that number at 9:16. Frame-height fraction is a function of vertical field of view, so at native vertical the same figure at the same distance on the same focal reads at roughly half the fraction, and [cinematic-language.md](cinematic-language.md) is explicit that an extreme wide in vertical wastes sky and floor and leaves the subject a few pixels tall. The lens survives as a restatement, not as an abandonment: at 9:16 produce the smallness by **depth down a subject that is itself vertical** — stair core, ramp, parking-deck run, alley — and by glass-reflection layering that puts the city over the face, never by lateral distance. The 8–15% height target holds only in those genuinely vertical subjects; everywhere else the figure goes one size step tighter, per the vertical direction rules in `cinematic-language.md`. What the signature was ever about is a person small against a bright field, and vertical can still deliver that in depth — so restate it, do not drop it and do not crop to it.

Field key, in the order every block uses it: **dramatic engine** (what mechanically generates scenes) · **audience contract** (what the viewer is owed) · **camera** (default framing register, plus **lens bias** in mm) · **movement bias** · **lighting** (quality, motivation, and **key ratio**（布光比）) · **palette** · **pacing** (**ASL**, the average-shot-length range, and the **pacing signature**, kept on one line because they are read together; the arithmetic lives in [editing-and-assembly.md](editing-and-assembly.md)) · **sound** · **blocking bias** · **classic amateur mistake** · **AI risk + mitigation** · **seed prompt** to start Step 10 from.

Twelve bullets, nine of which are settings. Two are dramaturgical — engine and contract — and are held whenever you re-register a scene. Seven are the craft dials the tone-dial section below turns: **camera, movement, lighting, palette, pacing, sound, blocking**. The remaining three (mistake, risk, seed) are notes, not settings. Count moved dials against that seven whenever you deviate. Social vertical carries two extra lines — `contract under a lens`, because it is the genre most often requested with a lens attached and the one whose contract a lens most often breaks, and `platform grammar`, because the Chinese-platform vocabulary has no equivalent elsewhere in this file.

Focal lengths here are full-frame (35mm-format) equivalents; convert for your capture format, and remember an AI model reads "28mm" as a look, not as optics — pair the number with the effect you want (see [prompt-lexicon.md](prompt-lexicon.md)). Seeds are English; for a Chinese-UI tool keep the same slot order and translate, e.g. the horror seed becomes `固定广角，28mm，视平线，夜晚厨房。女子背对未点灯的走廊洗碗，走廊占画面右侧三分之一，始终空无一人。只有抽油烟机灯亮着。她停下不动。镜头不动。结束于她开始转头。`

Shot sizes, angles, moves and coverage geometry are defined in [cinematic-language.md](cinematic-language.md); staging terms in [blocking-and-staging.md](blocking-and-staging.md); light setups in [lighting-and-color.md](lighting-and-color.md); sound craft in [sound-and-dialogue.md](sound-and-dialogue.md). Word-level prompt vocabulary and negative lists live in [prompt-lexicon.md](prompt-lexicon.md).

## The playbooks

### Horror

- Engine: withheld information plus a violated safe space. Scenes come from the gap between what the frame knows and what the character knows.
- Contract: you will be made to wait, and the wait will be paid at least once early. Pay it, or the audience stops waiting.
- Camera: locked wide with a load-bearing area of dead space kept deliberately empty. Lens bias 24–35mm — you need depth that can hide things behind the actor. 85mm+ compresses that depth away.
- Move: none, then one slow push（推镜）that tightens the frame 15–25% over 6–10 s — which makes it one of the long shots in the build, not an average one — or an unmotivated pan that reveals.
- Light: single-source low-key, key ratio 8:1 to 16:1, motivated by a visible practical (lamp, TV, phone, moon through blinds). Subject 2 stops above background; steep falloff is the whole effect.
- Palette: desaturated blue-green base, one warm practical, blood or rust as the only saturated accent.
- ASL: 3–8 s in the build, 0.5–1.5 s in the burst. Pacing signature: long, long, longer, then divide shot length by about five on the strike (6 s becomes 1.2 s).
- Sound: sound leads picture. Low bed at 30–60 Hz, room tone that stops just before the reveal. Silence is the loudest cue you have. If the deliverable will be watched on phone or laptop speakers, carry the same cue an octave up (60–120 Hz) as well, or the dread is inaudible on the device most people use.
- Blocking: keep the actor off-center, near an exit that is blocked, with their back to open space.
- Amateur mistake: showing the threat in the first minute, and scoring the scare instead of scoring the dread.
- AI risk: models resolve ambiguity — they fill dark regions with detail and put the thing in frame uninvited. Mitigation: describe the empty part of the frame explicitly ("the hallway behind her is empty and unlit"), negative-prompt the creature out of every build shot, and generate the dark plate and the reveal as separate clips.
- Seed: `Locked wide, 28mm, eye level, kitchen at night. A woman washes dishes with her back to an unlit hallway occupying the right third of frame, which stays empty. Only the range-hood light is on. She stops and holds still. No camera move. End on her head starting to turn.`

### Psychological thriller

- Engine: an unreliable interior. Scenes come from the mismatch between a character's account and the evidence visible in frame.
- Contract: you will be given enough to suspect and never enough to be sure, until one late confirmation.
- Camera: eye level, slightly tight, subject just off geometric center; repeat framings exactly so any change registers. Lens bias 40–75mm, one fixed focal per recurring location so a change of distance reads as a change of state.
- Move: drift, not moves — 5–10% of frame over the whole shot. The audience should not be able to name what moved.
- Light: soft key at 3:1 with one hard practical inside the frame; keep faces half-lit at decision points.
- Palette: near-monochrome and narrow, with one recurring object color that carries meaning.
- ASL: 5–12 s. Pacing signature: even and slightly too long. The discomfort is that nothing cuts away.
- Sound: dialogue dry and close; ambience thinner than the location deserves, so the audience feels the missing sound without locating it.
- Blocking: reflections, glass, doorways; two characters in one frame at unequal depths (one at 1.2 m, one at 4 m).
- Amateur mistake: staging paranoia with Dutch angles and stingers. Paranoia reads as repetition and asymmetry, not tilt.
- AI risk: a 5% drift sits below the effective motion floor of many current tools — "very slow push" comes back either static or as a snap. Mitigation: state displacement in executable terms ("dolly forward about half a meter across the shot"), and if the tool exposes a numeric motion-strength control, use its lowest non-zero setting; otherwise generate a static plate and add the move in post.
- Seed: `40mm, eye level, dolly forward roughly half a meter across the shot. A man re-reads a note at a kitchen table while his reflection sits in the dark window behind him. Desk lamp camera-left, face half in shadow. End with him setting the note face-down.`

### Crime and noir

- Engine: a transaction that goes wrong. Every scene is somebody trying to get paid, get told, or get out.
- Contract: the world is corrupt and competence is the only virtue; you will be shown the procedure in detail.
- Camera: observer positions — across the room, through a doorway, from inside a car. Lens bias 35mm for the room, 100mm+ for surveillance; the focal states whether you are present or watching.
- Move: motivated dolly with a walking character, then a hard stop. No float, no drift.
- Light: hard sidelight at 8:1, one hard source plus a legible shadow shape (blinds, signage, streetlight). Blacks go true black.
- Palette: sodium amber against blue-green night; skin allowed to run warm.
- ASL: 4–9 s on dialogue, 2–4 s on procedure. Pacing signature: dialogue in twos, action in threes.
- Sound: a city bed that never fully stops; music sparse and instrument-specific (upright bass, one horn); gunshots short and dry, no tail.
- Blocking: power by height and door control — who stands, who sits, who is between the other and the exit.
- Amateur mistake: rain, neon, and a trench coat standing in for a plot with money in it. Second offense: voice-over narrating what the picture already said.
- AI risk: hard venetian-blind shadows render as mush, and neon signage generates garbled text. Mitigation: put the shadow source off-frame and describe the shadow shape as geometry ("horizontal bars of shadow across his chest, about 8 cm apart"); keep all signage out of focus or out of frame.
- Seed: `35mm, waist level, framed through an open doorway from the next room. Two men count money at a table under one hanging bulb; the doorframe cuts the foreground to black. Camera holds and does not enter. End when one man stops counting and looks up at the door.`

### Drama

- Engine: an unresolvable want between two people who both have a case.
- Contract: nothing will be explained to you; you will read faces and infer.
- Camera: shoulder height, patient, coverage that lets the scene play in two or three sizes. Lens bias 40–50mm at 1.5–2.5 m — ordinary human distance.
- Move: reframing only. The camera follows the performance; it never leads it.
- Light: soft key at 2:1 to 3:1, window-motivated, consistent with the hour across the whole scene.
- Palette: real-world, low saturation, no signature color. Costume carries what color there is.
- ASL: 6–15 s. Pacing signature: hold two beats past the line.
- Sound: no score under dialogue on the first pass. Ambience full and specific to that room, including its refrigerator, its street, its clock.
- Blocking: give people a task to do while they talk. The task is the subtext meter — when the hands stop, the line landed.
- Amateur mistake: cutting on every line. The scene lives in the shot where nobody speaks.
- AI risk: sustained naturalistic performance is the hardest thing to generate — identity drift grows with clip length and lip-sync degrades faster than anything else in frame. Mitigation: build 3–5 s units around one physical action, keep dialogue off-frame or on the listener, and let the edit carry the scene length rather than the clip.
- Seed: `50mm, shoulder height, 2 m from subject, framed head to hands, static with a small reframe. A woman peels potatoes at a sink while someone speaks off-frame; window light camera-right at 2:1. She does not stop working. End with her hands going still for two seconds.`

### Romance

- Engine: the obstacle between two people who want to be closer. Scenes come from proximity denied.
- Contract: you will be paid in closeness — physical distance must shrink measurably across the film.
- Camera: matched shot/reverse, slightly past the shoulder, camera close to the axis so eyelines nearly hit lens. Lens bias 50–85mm at T1.8–2.8, focus on the eyes, background rendered as light rather than information.
- Move: a gentle arc, or a slow push on the person **listening**, not the person speaking.
- Light: soft wraparound key at 2:1, hair backlight, warm practicals defocused behind.
- Palette: warm skin against a desaturated surround, plus one shared accent color both characters end up wearing.
- ASL: 5–10 s, and longer on the reaction than on the line. Pacing signature: the reverse arrives one beat late. The delay is the feeling.
- Sound: intimate room tone with audible breath; music enters late and stays under.
- Blocking: measure proxemics in centimeters and write them down — 120 cm at the top of the scene, 40 cm at the turn. That number is the scene's plot.
- Amateur mistake: playing romance with the score and the sunset instead of with the blocking distance.
- AI risk: two-person interaction is the top failure class — hands, contact, and face stability across a reverse all break. Mitigation: single-character clips with the other person implied off-frame; place any physical contact at the cut point, never inside a clip.
- Seed: `85mm at T2.0, eye level, 1.5 m from subject for a close-up, arc left about 0.5 m across the shot on a 1.5 m radius. A man listens while someone off-frame finishes a sentence; warm defocused practicals behind him, soft key camera-left with hair backlight. End with him looking down, then back up.`

### Comedy

- Engine: a person fully committed to a plan the situation will not support.
- Contract: the frame will be honest with you — you will be shown the whole joke, not told where it is.
- Camera: wider than feels right, and locked. The frame is the container the joke happens inside. Lens bias 27–40mm, stopped down far enough that the reactor at the back of the room is as sharp as the speaker: a 32mm at T8 focused at 3 m holds roughly 1.8 m to 10 m. Shallow depth of field is a comedy killer, because it decides for the audience where to look.
- Move: none during the joke. A move steals the timing.
- Light: fairly flat at 2:1, high base level. You must be able to see every face at once.
- Palette: saturated, clean, high key. Production design does joke work; let it be legible.
- ASL: 2–5 s across the scene, but the joke shot itself is held long. Pacing signature: set-up, cut, hold, hold past comfortable, then cut. Leaving 4–8 frames early puts the audience slightly ahead of you and buys the bigger laugh; leaving half a second late buys the awkward one. Choose which you want and cut it twice to compare.
- Sound: no score under the punchline, and an ambience that does not pre-announce that something funny is coming.
- Blocking: put the reactor in the same frame as the actor. Two-shots, not singles.
- Amateur mistake: cutting to the reaction by default. A cut points at the joke and tells the audience when to laugh; keeping the reactor in the same frame lets them find it. Cut to the reaction only when the reaction *is* the joke.
- AI risk: comic timing lives in the cut, which the model does not control, and physical gags break physics in ways that read as error rather than joke. Mitigation: generate the wide as one clip and build the timing in the edit; never ask a model for a pratfall.
- Seed: `32mm, locked, eye level, wide enough to hold both people and the door. A man delivers a confident explanation while, in the same frame behind him, the thing he is describing quietly fails. Flat even light. No camera move. End with the second person's face doing nothing at all.`

### Action

- Engine: a physical objective with a clock and a geography.
- Contract: you will always know where everything is and what happens if it fails.
- Camera: establish geography in a wide before any coverage, then hold screen direction (see [cinematic-language.md](cinematic-language.md)). Lens bias 21–35mm inside the fight for impact, 85–135mm for the threat approaching.
- Move: whip pan, track at subject speed, or lock. Handheld shake is not a substitute for choreography.
- Light: high contrast but bright enough to read silhouettes — hard key at 4:1 with separation on **both** bodies, not just the hero.
- Palette: two-team color coding, environment desaturated so bodies read at speed.
- ASL: 0.8–2.5 s inside the sequence, 4–8 s at the geography beats. Pacing signature: shot lengths accelerate into the beat, then one long shot holds on the win or the loss.
- Sound: impacts carry the cut; music is rhythmic and cuts with picture, not under it.
- Blocking: choreograph in beats of three moves. Each shot shows one beat and ends in a pose the next shot starts from.
- Amateur mistake: shake plus fast cutting to hide that no choreography exists. If it cannot be cut slow, it does not exist.
- AI risk: multi-body contact, weapon continuity, and high speed each fail independently and compound. Mitigation: one body per clip, contact placed at the cut rather than inside a clip, and impact sound selling the frame you never generated.
- Seed: `24mm, chest height, tracking laterally at the runner's speed, screen left to right. A woman sprints along a loading dock, vaults one low barrier, lands and keeps running out of frame right. Hard low sun behind her at 4:1. One vault only. End as she clears frame.`

### Science fiction

- Engine: one changed rule, followed honestly to a human cost.
- Contract: the world will be internally consistent, and you will learn its rules by watching them used, not by being told.
- Camera: architectural for the system — wide, level, symmetrical; human framing for the person inside it. Lens bias 21–28mm for scale and single-point perspective, 75–100mm to isolate the person.
- Move: slow, mechanical, motorized. Constant velocity through the body of the move, with short symmetrical ramps at each end — a motion-control rig has to accelerate, but it does not ease the way a human operator does, and that flat middle is what reads as machine.
- Light: sourced from the technology itself — screens, light strips, indicator LEDs. Key ratio 6:1 with heavy negative fill.
- Palette: one cold system color plus one warm human color. Scarcity of hue *is* the world-building.
- ASL: 5–12 s for world, 2–4 s in crisis. Pacing signature: hold on the machine long enough for the audience to learn what it does before you need them to know.
- Sound: designed machines with a distinct pitch identity per system, so the audience can hear which thing is failing. Music textural and low.
- Blocking: person small inside a designed frame; let the architecture do the staging.
- Amateur mistake: panel-and-prop soup with no rule behind it. One changed rule beats twenty gadgets.
- AI risk: hardware and interface designs drift shot to shot, screen text garbles, and scale is inconsistent between clips. Mitigation: lock a reference plate per set (see [image-model-adapters.md](image-model-adapters.md)), describe geometry rather than brand ("a wall of matte grey panels, one amber strip at waist height"), and never request legible screen text.
- Seed: `21mm, level, static, single-point perspective down a corridor of matte grey panels with one amber light strip at waist height. A technician walks away from camera, stops at a wall unit, places a palm on it. The strip changes color along its length toward her. End as she lowers her hand.`

### Fantasy

- Engine: a world with a price. Every power costs something the audience can see.
- Contract: the impossible will be photographed as though it were ordinary.
- Camera: ground the fantastic — put a human eye level and a normal lens on it. Lens bias 32–50mm as standard; save 18–24mm for one scale reveal per act.
- Move: boom up or crane back for the reveal, then settle and hold. One large move per sequence, earned.
- Light: naturalistic sources scaled up — sun, fire, moon — at 4:1 outdoors and 2:1 to 3:1 in interior naturalism, plus one impossible source that obeys its own consistent rule every time it appears.
- Palette: earth base, so a single magic hue reads as an event rather than decoration.
- ASL: 4–10 s. Pacing signature: hold the reveal one beat past comfort so the audience concludes it exists rather than that it was shown.
- Sound: organic materials over synthesizers. Magic should have a material — stone, water, breath — not a whoosh.
- Blocking: physical labor. Climbing, carrying, hauling, riding. Weight is what makes an invented world real.
- Amateur mistake: everything is astonishing, so nothing is. Second offense: costume without weather.
- AI risk: creature anatomy, armor, and cloth detail mutate between clips, and scale between beings breaks. Mitigation: keep non-human elements partly occluded or at distance, derive scale from a human-height object in frame, and keep magic motion to one simple physical behavior.
- Seed: `35mm, eye level, static then slow tilt up. A woman in wet wool carries a full pail across a muddy yard at dusk; behind her the treeline is lit from inside by a single steady green source that does not flicker. She does not look at it. End with the tilt revealing how far the light extends.`

### Period and historical

- Engine: a person constrained by the rules of their time, which they cannot simply refuse.
- Contract: the world will be materially specific and will not wink at you.
- Camera: compose in the era's own image culture — its painting and photographic formats — and stage rather than cover. Lens bias 32–58mm; modern ultra-wide distortion reads as contemporary no matter what is in frame.
- Move: dolly and static only. Handheld reads as now.
- Light: period sources only — window, candle, oil, gas, early tungsten. Key ratio 3:1 to 4:1 at a window, 8:1 or steeper by candle, because a small source with no fill obeys inverse square: move a face from 0.5 m to 1 m off the flame and you lose 2 stops. Use that falloff, do not fight it.
- Palette: dye- and pigment-limited. Choose 5–7 colorants the period could actually produce and refuse the rest.
- ASL: 7–16 s. Pacing signature: let entrances and departures take their real duration.
- Sound: strip the modern floor first — no distant traffic hum, no fluorescent buzz — then add correct material weight (iron, wood, heavy cloth).
- Blocking: formal. Status decides who moves and who is moved toward.
- Amateur mistake: costume-shop accuracy worn with modern posture, modern haircuts, and clean teeth.
- AI risk: anachronism injection — zippers, modern eyewear, printed text, plastic, contemporary dentition. Mitigation: carry an explicit era negative list in every prompt, naming instances and never the category — "no modern objects" is unresolvable and is the mechanism behind F8 (see [prompt-lexicon.md](prompt-lexicon.md) and [failure-modes.md](failure-modes.md)) — and add a per-shot anachronism pass in QC.
- Seed: `50mm, chest height, locked. A woman in a high-collared dress writes at a table lit only by two candles at 1 m; falloff drops the back wall to near black. No plastic, no wristwatch, no printed labels, no electric fixture. She stops, holds the pen, does not write. End with her setting it down and pinching out one candle.`

### War

- Engine: a small task performed under fire, where the objective is minor and the cost is total.
- Contract: you will be shown consequence, not glory.
- Camera: from inside the unit — subjective height, restricted view, obstructed frames. Lens bias 24–35mm handheld at close proximity; long lens only for what the character cannot reach.
- Move: reactive handheld. The camera flinches and re-finds the subject half a second late; that lag is the point.
- Light: available only. Flat overcast, or hard sun at 6:1 with no fill. Flare is allowed.
- Palette: mud and ash, desaturated, one flesh tone. Fire is the only saturation in the film.
- ASL: 1.5–4 s under contact, 8–20 s in the waiting. Pacing signature: waiting is 80% of the runtime and contact is short. That ratio is the genre.
- Sound: dynamic range is the entire strategy — near-silence, then an impact 20–30 dB above it, then dampened ringing. Do not ride it flat, and do not let a loudness-normalized delivery target flatten it for you.
- Blocking: cover to cover. Never let a body stand in the open without a reason someone paid for.
- Amateur mistake: continuous action. Without the waiting, the contact has no scale.
- AI risk: as of writing, crowds, weapons, and pyro in one clip exceed what generative video reliably keeps coherent, and the three failures compound rather than average. Mitigation: one soldier and one action per clip; smoke, ash, and debris as the environmental motion; explosions rendered as an off-frame light change plus sound.
- Seed: `28mm handheld, low and close, reactive — the camera flinches and re-finds the subject half a second late. A soldier presses against a broken wall, breathing, waiting; ash drifts through frame. Off-frame light flashes once from camera-right and dims. He does not move. End as he begins to lean out.`

### Documentary and verite

- Engine: whatever actually happens while the camera is present.
- Contract: nothing has been staged for you. The frame will be imperfect, and the imperfection is the proof.
- Camera: operator-found. Reframe visibly, correct focus visibly, arrive a step behind the event. Lens bias 24–70mm — a single zoom range worked live, with the focal change itself left visible, because the zoom is testimony that someone was standing there deciding.
- Move: handheld with real body weight. Walk and follow, never glide.
- Light: available. Whatever the room gives — expect anything from 2:1 to 10:1 inside one scene and do not normalize it. Leave mixed color temperature uncorrected: tungsten and daylight in one frame is a truth claim.
- Palette: whatever is there. Grade for consistency only, never toward a look.
- ASL: 4–12 s, with deliberate over-long holds. Pacing signature: the truth arrives after the subject stops performing. Hold past the end of the answer.
- Sound: production sound with room, wind, and mic handling left in. No music under the hardest answer.
- Blocking: none. You choose a position, not a staging.
- Amateur mistake: treating "documentary style" as a filter — adding shake to a perfectly framed, perfectly lit shot. Verite is about imperfect *information*, not imperfect stabilization.
- AI risk: generated footage is too clean, too centered, and too well-exposed, which reads immediately as fake. Mitigation: prompt the operator error explicitly — "subject drifts off-center and the camera corrects late; a foreground shoulder crosses frame" — and leave one exposure or focus imperfection in every clip.
- Seed: `24-70mm handheld, operator-found. A woman answers a question at her kitchen table; she drifts off-center, the camera corrects late, focus is pulled visibly. Mixed daylight and tungsten, uncorrected. She finishes speaking and the shot keeps running. End four seconds after she stops.`

### Music video

- Engine: the track's structure. Sections generate scenes; you cut to the arrangement, not to a story.
- Contract: one image idea per section, and a payoff on the last chorus.
- Camera: one strong idea repeated with variation — a fixed format, a single move type, or a single lens. Lens bias: commit one focal per section so focal change marks verse and chorus (for example 35mm verse, 85mm chorus).
- Move: on-beat. A move starts on a downbeat and ends on a bar line, or it does not happen.
- Light: unmotivated is allowed here. Ratio is a design choice rather than a naturalism check; the workhorse is one hard source at 8:1 or steeper so the color reads as a graphic field, not as a room. Color changes hard on the section boundary.
- Palette: 2–3 saturated hues. Change the whole palette at the chorus, never gradually.
- ASL: verse 2–4 s, chorus 0.5–1.5 s, bridge 4–8 s. Pacing signature: the bar structure *is* the edit. Lay the timeline out in bars first.
- Sound: fixed. Everything else obeys the track's tempo map, which you build before you generate a frame.
- Blocking: performance to lens is allowed and usually wanted. Narrative blocking is secondary.
- Amateur mistake: pretty images cut freely "to the vibe" instead of to the bar grid.
- AI risk: lip-sync. Generated singing rarely matches phonemes and the mismatch is instantly visible. Mitigation: avoid frontal singing close-ups; use profile, backlight, obscured mouth, or hold the sung line over non-performance imagery.
- Seed: `85mm at 3.5 m, locked, chest height, waist-up framing with room either side for the arms. Subject centered against a flat saturated red wall. A dancer holds still for the first half of the shot, then executes one full turn on the downbeat, ending in the same position. Hard single source camera-left at 8:1. Mouth not visible. End on the held pose.`

### Commercial and product

Twelve playbook fields only. The depth this genre actually needs — the light-moves principle, lighting by material class, macro working distance, brand and colour fidelity, text and logo, the shot grammar of a spot, the vertical layouts, and what to shoot instead of generate — is owned by [product-and-macro.md](product-and-macro.md). Do not re-derive it here.

- Engine: a single claim, made visible in one action.
- Contract: you will be told what this does inside the first few seconds and then shown proof.
- Camera: product at or slightly below its own eye level, with macro-capable framings. There are no casual angles. Lens bias 50–100mm macro on product, 35mm for lifestyle context.
- Move: the light moves; the camera and the product hold. Where the camera does move at all, motion-control feel — constant-velocity slider or turntable, easing out only into the end card.
- Light: controlled studio — one large soft source plus a hard edge kicker. 3:1 lit side to shadow side on skin; shaping the specular on the product is the entire job.
- Palette: brand palette. The background is a value, not a place.
- ASL: 0.8–2 s. Pacing signature: for a 30 s cut — 5 s hook, 18 s demonstration, 4 s claim, 3 s end card. Delivered vertically, the format outranks that runway: the hook collapses into the first 1–1.5 s and the claim moves forward with it, keeping the demonstration and end-card blocks. Do not scale the runway down to a shorter runtime: the 15 s and 6 s cuts are different structures, laid out second by second, and every per-shot duration including the hero hold is in [product-and-macro.md](product-and-macro.md).
- Sound: sound design sells texture — the click, the pour, the fabric. Music is a bed with one hit on the logo.
- Blocking: hands, not faces, for demonstration. Hero the operative surface of the product.
- Amateur mistake: beauty shots with no claim. If the viewer cannot repeat the claim afterward, the spot failed regardless of how it looks.
- AI risk: product identity drift — logo, proportion and material change every clip, hands mangle the object, and a brand hue lands a shade off. See F1's brand-colour cause and the hand-plus-branded-product entry in [failure-modes.md](failure-modes.md). Mitigation: keep the product static and move only the light, composite the real product over generated environments, and never let a generated hand fully grip a branded object. The workflow is in [product-and-macro.md](product-and-macro.md).
- Seed: `100mm macro, static camera, product at its own eye level. A ceramic cup on a matte surface; steam rises. One large soft source above and camera-right travels slowly right, so a specular line walks along the polished rim from left to right. The cup does not move and the camera does not move. End with the highlight resting at the rim's near edge and the steam continuing.`

### Fashion

- Engine: silhouette in motion. A scene exists to reveal how a garment moves and what it does to a body.
- Contract: this is about surface. You will be shown weave, drape, and edge at a level a still photograph cannot deliver, and you will be shown how the garment behaves when the body moves.
- Camera: full figure has priority. The frame must respect the silhouette's edges — head and toe room is a rule, not a preference. Lens bias 85–135mm for the look-book register, 24mm at ground level for attitude. Budget the throw: holding a full figure with head and toe room needs roughly 7 m at 85mm and roughly 11 m at 135mm, so pick the lens the stage can actually support.
- Move: slow lateral track, or a locked frame the model moves through. Camera and body must not both move fast.
- Light: one hard source for texture and edge at 6:1, or one very large soft source for skin against a black surround. Pick one; do not blend.
- Palette: garment-led. Everything else drops to neutral so the fabric is the only chroma event in frame.
- ASL: 1–3 s cuts set against 8–15 s holds. The contrast between them is the style. Pacing signature: repetition with escalating scale — the same move shown at three sizes.
- Sound: no dialogue. Rhythmic and non-melodic, with fabric and footstep sound pushed well above natural level.
- Blocking: walk toward and past camera; turn at the frame edge; hold still, then release one gesture.
- Amateur mistake: cropping the silhouette to get a "closer look". The silhouette is the product.
- AI risk: fabric physics and garment identity — drape, seam, and pattern regenerate every clip. Mitigation: 2–4 s clips, one garment, motion restricted to walking or wind. Never request a fast turn.
- Seed: `85mm, locked frame, full figure with head and toe room held throughout. The model walks toward camera from 11 m to 7.5 m and stops. One hard source camera-left at 6:1 rakes across the fabric to show weave; black surround, the garment is the only saturated element. End on the stop, with the coat still settling.`

### Corporate and explainer

- Engine: a problem the viewer recognizes, then the mechanism that fixes it.
- Contract: your time will not be wasted. Every 15 s advances understanding by one step you could name.
- Camera: locked, or a minimal slider. Interviews at eye level, slightly off-axis. Lens bias 50–85mm on the speaker at T2.8–4 — shallow enough to separate, deep enough that the background stays readable.
- Move: a 5–10% push across a 20 s answer, and nothing more.
- Light: soft key at 3:1, background separated with one color accent. No mystery, no mood.
- Palette: brand plus neutral interior. Keep skin natural — corporate grades that tint faces read as amateur immediately.
- ASL: 3–6 s on B-roll; interview blocks run 8–20 s. Pacing signature: one idea per 15 s, with a visible change at every idea boundary.
- Sound: voice-over is the spine. Clean and close, with the music bed sitting 15–20 dB under it and high-passed so it does not fight the voice. Mix for laptop speakers, not for headphones, and check it once at low volume.
- Blocking: hands visible, one gesture per point. B-roll shows the specific thing being described, not people typing.
- Amateur mistake: stock abstraction — handshakes, glowing networks, rotating globes — that illustrates nothing and costs credibility.
- AI risk: generic generated B-roll is exactly the material that reads as filler, and it reads that way faster than stock did. Mitigation: generate the specific noun in the script line, never its mood. If the line says "a warehouse pick-and-pack station", generate that, not "logistics".
- Seed: `85mm at T2.8, eye level, off-axis, subject at 2.5 m. Static apart from a push of about 15 cm across the take, which tightens the frame roughly 6 percent. A woman answers an off-camera interviewer, hands visible, one gesture per point. Soft key camera-left at 3:1, background separated by a single accent lamp. End when she finishes the sentence.`

### Trailer

- Engine: escalating promise. This is a structure, not a story.
- Contract: you will be told the premise, shown the scale, and denied the ending.
- Camera: borrow the feature's grammar, but bias one shot size tighter — a wide becomes a medium wide, a medium becomes a close — because trailers are watched small. Lens bias: whatever the feature uses. A trailer that invents new lensing is lying about the film.
- Move: one large move per act of the trailer. More than that reads as desperation.
- Light: the feature's, with contrast pushed slightly for small-screen legibility.
- Palette: the feature's, with hero-to-background separation boosted.
- ASL: act one 3–6 s, act two 1.5–3 s, act three 0.4–1 s, final button 3–5 s. Pacing signature: premise 0–35%, escalation 35–80%, barrage plus button 80–100%.
- Sound: audio drives everything. Risers and hits land on cuts, and there is one full stop of silence before the last act. Without that silence the barrage has no scale.
- Blocking: never let the subject read smaller than about a quarter of frame height. Below that the figure vanishes on a phone, and a scale shot nobody can parse buys nothing.
- Amateur mistake: showing the third act. Close second: a montage with no silence in it.
- AI risk: a trailer exposes continuity drift far more than a scene does, because shots sit adjacent with no connective tissue between them. Mitigation: lock one hero look per character and reuse the same seed and reference across every trailer beat — see [continuity-bible.md](continuity-bible.md).
- Seed: `Same lensing and grade as the feature. 40mm, static, subject at one-quarter frame height — the widest this trailer goes — centered, walking away from camera down an empty street at dusk. Hold the frame with no cut and no music. End with the figure still walking.`

### Social vertical short-form

- Engine: a question posed in the first second, answered before the thumb moves.
- Contract: this pays off fast and stays legible at arm's length on a phone.
- Contract under a lens: split the contract before you negotiate it. Structural and always surviving — a hook inside the first second, a visible change by 3 s, and a reason to keep watching at the loop point. Craft-dependent and therefore negotiable when a lens forbids them — sound-off legibility, the burned-in text hook, high saturation, front-biased light. Captions are a delivery-layer decision made at Step 12, not a craft dial: a lens's `no text in frame` rule governs the generated image, and captions may still be added in the edit over the top of it. Where the lens's register makes captions tonally wrong, the lens arbitrates and the structural items must then be paid in picture — the hook becomes an image rather than a line of type, and the change at 3 s becomes something the viewer sees rather than reads. Log each dropped item in the director's book; a contract you silently abandon is the one nobody notices missing until the completion rate comes back.
- Platform grammar on Chinese platforms: the driving metric is 完播率, completion rate — which is *why* the claim lands inside the first 1.5 s instead of at the commercial's second 5. A viewer who leaves at 2 s costs more than one who never opened it. Named formats, one gloss each: 试色 swatch on the product's own surface · 手臂试色 swatch on the forearm · 上脸对比 before/after on the face · 质地特写 texture macro · 开箱 unboxing · 痛点开场 open on the problem, not the product. 种草 (first person, one benefit, no brand voice) and 硬广 (brand register) are different audience contracts — pick one per cut and never mix them, because the register break is what reads as an ad.
- Camera: 9:16 with the face in the upper-middle third. Treat roughly the top 12% and bottom 20% as unsafe — platform chrome sits there — and confirm against the current safe-area guide for the platform you are delivering to, since those bands move. Lens bias 24–35mm equivalent, close. Wide-and-near, never far-and-long.
- Move: snap or whip transitions, or nothing. Slow moves die on this surface.
- Light: bright and front-biased at 2:1. Assume a small screen viewed outdoors.
- Palette: high saturation, high contrast, aggressive figure/ground separation.
- ASL: 0.7–2 s, of which **0.7 s is the format's floor** and the rest is this genre's target when no lens is loaded. Under a lens, keep the floor and take the lens's ASL target — a 4 s average is in spec, a 0.4 s cut is not. Pacing signature: hook at 0–1 s, change at 3 s, change again at 7 s, payoff before 15 s.
- Sound: legible with sound off, rewarding with sound on. Captions burned in; the first frame carries a text hook.
- Blocking: subject moves toward camera, and all meaningful action stays in the center-safe column.
- Amateur mistake: shooting 16:9 and cropping. The composition has to be born vertical or it will look borrowed.
- AI risk: vertical framing is under-represented relative to horizontal, so composition drifts back toward a center-cropped wide. Mitigation: generate natively at 9:16 where the tool exposes an aspect control (see [ai-video-tool-adapters.md](ai-video-tool-adapters.md)), state "vertical composition, head near the top third" in the prompt, and keep clips at 4 s or under so one bad drift costs one beat.
- Seed: `Native 9:16, 24mm equivalent, close. Subject's face in the upper-middle third with 12 percent top and 20 percent bottom margins kept clear. A woman looks into lens, says nothing, then lifts an object into frame and turns it once. Bright front-biased light. Three seconds.`

### Animation-styled

- Engine: whatever the story is; the medium is the multiplier. It licenses caricature of physics, scale, and time. If the scene would play identically in live action, you are paying for animation without using it — find the beat that only a drawn frame can hold.
- Contract: the rules are drawn, and they will stay consistent for the whole runtime.
- Camera: there is no camera, only a chosen frame. Pushes and pans are graphic moves, so make them deliberate and linear. Lens bias: emulate focal length through perspective construction — draw the vanishing points and the convergence a 35–50mm view would give, or the exaggerated convergence of a 24mm one — never through depth of field.
- Move: 2D-safe moves only unless the style genuinely supports parallax — pan, tilt, push, whip. Avoid orbits and arcs.
- Light: painted. Flat fills plus a hand-placed rim and one deliberate shadow shape. Ratios here are design choices, not measurements.
- Palette: strict, limited, and script-mapped — a fixed palette per sequence, changed only at emotional turns.
- ASL: 2–6 s, holding on key poses. Pacing signature: anticipation, action, settle. Every action gets its anticipation frames or it reads as a glitch.
- Sound: everything is foley; nothing is captured. Silence is total unless you design something into it.
- Blocking: silhouette first. If the pose does not read as a black shape, it is not a pose yet.
- Amateur mistake: applying live-action coverage logic — realistic shot/reverse with shallow depth of field — to a graphic medium that has no lens.
- AI risk: style drift between clips (line weight, shading model, proportion) and 3D-ish motion creeping into a 2D look. Mitigation: name the medium concretely ("flat cel shading, uniform line weight, two-tone shadows, no gradients"), lock a style reference image, and prefer flat lateral moves over anything with implied depth.
- Seed: `Flat cel-shaded 2D, uniform line weight, two-tone shading, no gradients. Locked graphic frame, lateral pan right at constant speed. A character stands in silhouette against a limited five-color sunset palette, then raises one arm with clear anticipation before the move. No depth of field, no orbit. End on the held pose.`

## Cross-genre comparison

One row per genre. Read the columns down to see the landscape; read across to load a genre.

| Genre | ASL | Dominant camera | Key ratio | Palette | Sound lead |
|---|---|---|---|---|---|
| Horror | 3–8 s / 0.5–1.5 s burst | Locked wide with empty dead space | 8:1–16:1 | Desat blue-green + one blood accent | Low bed and silence |
| Psychological thriller | 5–12 s | Static eye level, imperceptible drift | 3:1 | Near-monochrome + one object color | Dry close dialogue, thin ambience |
| Crime / noir | 4–9 s / 2–4 s procedure | Observer position through doorways | 8:1 | Sodium amber vs blue-green night | City bed, sparse instruments |
| Drama | 6–15 s | Shoulder height, reframe only | 2:1–3:1 | Real-world low saturation | Full specific ambience, no score |
| Romance | 5–10 s | Matched near-axis shot/reverse | 2:1 | Warm skin, desat surround | Room tone and breath |
| Comedy | 2–5 s | Locked wide two-shot | 2:1 | Saturated high key | Clean, no score on the punchline |
| Action | 0.8–2.5 s | Track at subject speed | 4:1 | Two-team coding, desat ground | Impacts on the cut |
| Science fiction | 5–12 s | Symmetrical wide, motorized move | 6:1 | One cold system + one warm human | Machine pitch identity |
| Fantasy | 4–10 s | Human eye level, one earned boom | 4:1 sun or fire, 2:1–3:1 interior | Earth base + single magic hue | Organic materials |
| Period / historical | 7–16 s | Staged static and dolly | 3:1–4:1 window, 8:1+ candle | 5–7 period colorants | Material weight, no modern floor |
| War | 1.5–4 s / 8–20 s waiting | Reactive handheld, obstructed | 6:1 no fill | Mud and ash, fire only | Dynamic range, 20–30 dB swings |
| Documentary / verite | 4–12 s | Operator-found handheld | Available, 2:1–10:1 uncorrected | Uncorrected mixed temperature | Production sound with room |
| Music video | 0.5–8 s by section | One repeated idea, on-beat | Design choice, often 8:1+ hard | 2–3 saturated hues per section | The track's tempo map |
| Commercial / product | 0.8–2 s | Static; the light moves, slider if any | 3:1 skin, shaped specular | Brand palette on a value | Texture design + logo hit |
| Fashion | 1–3 s vs 8–15 s holds | Locked full figure, slow lateral | 6:1 hard, or large soft on black | Garment-led, neutral surround | Rhythmic, fabric pushed up |
| Corporate / explainer | 3–6 s, 8–20 s interview | Static, 5–10% push | 3:1 | Brand + neutral, natural skin | Voice-over spine |
| Trailer | 3–6 s → 0.4–1 s | The feature's, one size tighter | Feature's, +contrast | Feature's, +separation | Hits, risers, one silence |
| Social vertical | 0.7–2 s | Close 9:16, snap transitions | 2:1 front-biased | High saturation, high contrast | Captions first, audio second |
| Animation-styled | 2–6 s | Graphic frame, linear moves | Painted, not measured | Fixed per-sequence palette | Total foley |

## Tone dial: change three dials, change the genre

Genre is not a subject; it is a configuration. The fastest way to re-register a scene is to move exactly three of the seven craft dials — camera, movement, lighting, palette, pacing, sound, blocking — and hold the other four. Moving one is a nudge; moving three is a genre change; moving five or more is a different film that no longer matches your script.

All four shifts below run on the same control scene the director style modules use, so you can diff a genre shift against a director-lens shift: *a person stands at a closed apartment door holding something they intend to give away, hesitates, and leaves without knocking.* Engine and contract are held in all four — that is the lesson. Register is carried by craft, not by content, and the same event supports four genres without one word of the action changing.

### Shift 1 — drama to horror

- Drama baseline. Camera: 50mm MS at 2 m, shoulder height. Movement: none. Lighting: soft corridor window key, 2:1. Palette: real-world, low saturation. Pacing: one 8 s shot. Sound: corridor ambience. Blocking: she stands square to the door, 60 cm from it.
- Moved 1, camera: the 50mm MS becomes a 28mm wide from the same position, which brings the unlit stretch of corridor behind her into the right third and keeps it empty.
- Moved 2, lighting: the soft 2:1 window becomes a single stairwell practical at 12:1, her face two stops above the wall behind her.
- Moved 3, sound: corridor ambience becomes a 40 Hz bed (doubled at 80 Hz for phone playback) that cuts out the instant she turns to leave.
- Held: movement (still none), palette, pacing (still one 8 s shot), blocking. Camera height and her performance do not change either.

### Shift 2 — comedy to tragedy

- Comedy baseline. Camera: 32mm locked wide holding her, her door, and a neighbor's door that opens once. Movement: none. Lighting: flat 2:1, high base level. Palette: saturated, clean. Pacing: one unbroken 14 s take. Sound: one banal off-frame domestic noise. Blocking: both doors in frame, she is not centered.
- Moved 1, movement: the locked frame becomes a push on the same 32mm, from 4 m to 2.8 m across the hesitation, so the neighbor's door leaves frame and she is alone in it by the end. Stop short of 2 m — at 32mm that close, wide-angle distortion arrives and starts making its own joke.
- Moved 2, pacing: the single 14 s take becomes four shots averaging 3.5 s, plus a 3 s hold on the closed door after she has gone — a shot with nobody in it, which comedy never allows.
- Moved 3, sound: the banal noise is removed and one sustained low string enters on her turn.
- Held: camera (same 32mm, same start frame), lighting, palette, blocking. The object in her hands and her performance register are unchanged; the push and the aftermath hold do all the work.

### Shift 3 — commercial to verite

- Commercial baseline. Camera: 100mm on the object in her hands. Movement: constant-velocity slider. Lighting: large soft source camera-right plus hard edge kicker, 3:1. Palette: two brand colors on a neutral value. Pacing: 1.2 s cuts with a macro insert. Sound: designed texture — the object's click, a music bed. Blocking: hands hero, face secondary.
- Moved 1, lighting: studio soft-plus-kicker becomes available light only, mixed corridor tungsten and stairwell daylight left uncorrected.
- Moved 2, movement: the motion-control slider becomes handheld at the same long focal, visibly hunting for the object and correcting focus late — long lenses magnify handheld motion, and here that is the signature rather than a fault.
- Moved 3, pacing: 1.2 s cutting plus insert becomes one 12 s hold with no insert at all.
- Held: camera (still long on the object), palette, sound, blocking. Keeping the designed sound is deliberate: it is what stops this becoming documentary. This is a commercial shot verite-style, which is a different and more useful thing than a fake documentary.

### Shift 4 — thriller to romance

- Thriller baseline. Camera: 40mm at 2.5 m, she reads small in frame, off-center, eyeline away from lens. Movement: 5% drift. Lighting: hard practical half-lighting her face at 6:1. Palette: near-monochrome. Pacing: one 10 s shot. Sound: thin ambience. Blocking: she stands 1.5 m back from the door with her back to open corridor.
- Moved 1, camera: 40mm at 2.5 m becomes 85mm at 1.5 m at T2.0, centered, and the camera moves down the corridor in the direction she will leave, so her turn brings the eyeline within 10° of lens for the last two seconds. The corridor behind her becomes light rather than information.
- Moved 2, lighting: hard 6:1 half-light becomes a soft 2:1 wrap plus a hair backlight from the stairwell window.
- Moved 3, blocking: 1.5 m back with open space behind her becomes 40 cm from the door, hand resting on the frame, her back to a closed wall. The door is standing in for the person behind it, so measure the distance to it in centimeters and write the number down; the proxemics are the change, not the mood.
- Held: movement (same 5% drift, which now reads as tenderness instead of surveillance), palette, pacing, sound. Nothing about the object or the decision to leave changes.

Working method: write the three moved dials into the director's book as `dial: from → to` lines before you generate anything. If a clip comes back in the wrong register, one of those three is at fault, and you can re-prompt it without rewriting the scene. If you find yourself wanting a fourth, stop and check whether you have actually chosen a different genre — the precedence rules at the top of this file apply to you too.

## Hybrid and subverted genre

A hybrid is not an average. Averaging two playbooks produces a scene with no contract, which audiences experience as incompetence rather than as originality. Two rules:

- **Split by domain, not by shot.** Assign each of the seven craft dials to one parent genre and write the assignment down. Pacing ownership is never shared — a scene can only have one rhythm. Worked example, crime-horror: crime takes camera (observer position through a doorway), movement (motivated dolly, hard stop), palette (sodium amber against blue-green), and blocking (door control, who is between whom and the exit); horror takes lighting (12:1 off one practical, inside its 8:1–16:1 band), pacing (3–8 s build collapsing to under 1.5 s), and sound (bed plus cut-to-silence). Engine and contract stay crime's — somebody is still trying to get paid. Seven dials, two owners, no field arbitrated twice; that reads as a coherent third thing.
- **Subvert exactly one dial.** A subversion only registers as intentional against an otherwise correct baseline. Run the genre straight on six of the seven craft dials and break the last one hard.

Worked subversions that hold up:

- Horror lit like a commercial: keep every horror dial except lighting — large soft source, 2:1, bright and even. The dread now has nowhere to hide, which is worse. This is why bright horror works and why "bright plus flat plus handheld plus fast cutting" does not: bright and flat are one dial, but handheld and fast cutting add movement and pacing, and three dials moved is a genre change, not a subversion.
- Comedy at drama's pacing: keep comedy's locked wide, flat light, and two-shot blocking, and move only pacing — ASL from 2–5 s up into drama's 10–15 s. The joke stops being a joke somewhere in the hold; that is the effect you are buying.
- Action with documentary movement: keep action's geography discipline, screen direction, 4:1 separation, and choreographic beats; change only movement to operator-found handheld that arrives late. You have now spent your subversion — do not also strip the geography, because that is action's core contract, and losing the contract as well as the movement leaves the audience with nowhere to stand.
- Period with contemporary sound: keep period's lenses, staging, colorant-limited palette, and 7–16 s ASL; change only sound to a score the period could not produce. The picture stays honest, so the anachronism reads as commentary rather than as error.

Failure signature to watch for in review: if you cannot name which genre the scene is subverting, you did not subvert one dial, you abandoned the playbook — re-derive from the block, restore the other six dials, and try again. For how genre defaults interact with per-shot retry budgets and version tracking, see [production-workflow.md](production-workflow.md); for diagnosing a clip that came back in the wrong register, see [failure-modes.md](failure-modes.md).
