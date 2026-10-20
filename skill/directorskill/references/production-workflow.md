# Production Workflow

Load this file when the user is about to start generating, asks how many shots or retries a project will take, asks what order to build things in, or needs a package to hand to an editor, a client, or their future self. This file owns the operating loop and the economics; craft decisions live in the other references.

## The loop

Eight gates. A gate is a question with a yes/no answer and a named place to go back to when the answer is no. Nothing advances on "it's probably fine".

Gate numbers below are execution-loop numbers, not the 13-step pipeline. The "Pipeline" column maps each gate onto the pipeline steps it consumes, so "go back to gate 1" and "go back to pipeline step 6" stay distinguishable in a review note.

| Gate | Step | Pipeline | Input | Gate question | Passes when | On fail, return to |
|---|---|---|---|---|---|---|
| 1 | Plan | 1–7 | Script, beats, style lens | Does every shot have a story function, a size, a duration, and a continuity anchor? | The shot plan has no row whose function is "it looks good" | Whichever of pipeline steps 2–7 is thin; see [../assets/shot-plan-template.md](../assets/shot-plan-template.md) |
| 2 | Keyframe | 8 | Shot plan, character and location locks | Does a still exist at final aspect ratio for every shot that needs one? | Every non-trivial shot has a `kf-first`, and first/last pairs exist where the action has a defined endpoint | Gate 1 if the shot itself is wrong; [image-model-adapters.md](image-model-adapters.md) if the still is wrong |
| 3 | Approve keyframe | 8 | Candidate stills | Is this frame correct on all fifteen continuity axes, and would it survive as a printed storyboard panel? | A named human says yes and the version is logged | Gate 2. Never gate 4 |
| 4 | Generate video | 9–10 | Approved keyframe, motion prompt | Did the clip come back with one primary action, one camera behaviour, and a clean endpoint? | The last frame is usable as the next shot's reference | Gate 3 if the frame was the problem; [ai-video-tool-adapters.md](ai-video-tool-adapters.md) if the prompt was |
| 5 | QC | 13 | Returned clips | Does it pass [../assets/qc-checklist.md](../assets/qc-checklist.md) and the continuity axes? | No axis drifted; no physics tell in the first or last 0.5 s | Gate 4 with exactly one changed variable; [failure-modes.md](failure-modes.md) for diagnosis |
| 6 | Assemble | 11–12 | Approved clips, the sound plan written back at gate 1 | Do the cuts work at the planned rhythm, in order, over a sound bed, with no placeholder? | The cut plays end to end with no gaps, no silent stretch waiting for audio, and no temp shot standing in for an unproven one | Gate 1 if a shot is missing from the plan; see [editing-and-assembly.md](editing-and-assembly.md) and [sound-and-dialogue.md](sound-and-dialogue.md) |
| 7 | Review | 12–13 | Assembled cut, sound bed | Does the scene do the job the beat sheet said it would? | Someone who has not seen the plan can state the dramatic question after one viewing | Gate 1. A cut cannot be fixed at gate 6 if the plan was wrong |
| 8 | Deliver | — | Approved cut plus source | Can a stranger rebuild this without asking you a question? | The handoff package below is complete | Whichever artefact is missing |

Sound is the step most often discovered late. Pipeline step 11 is written at gate 1 alongside the shot plan and executed at gate 6, not invented after picture lock — by then the cut has been trimmed to a rhythm that leaves no room for it, and every fix costs a re-trim.

## The hard gate

Never spend a video generation on an unapproved keyframe（关键帧）. It is the rule this file exists to enforce, and it has exactly two carve-outs, listed below.

The cost logic: in image-to-video, the still already carries identity, wardrobe, framing, lens feel, light direction, palette, and set dressing. Motion adds failure surface, it does not repair anything. So a clip generated from an 80%-correct frame is at best 80% correct and usually worse, because the model interpolates the wrong parts too. Meanwhile a still typically returns far faster than a clip and at a much lower credit cost — as of writing that gap is roughly an order of magnitude on the platforms this skill targets, but treat the direction as stable and the number as something to re-check against your platform's current pricing. The still is the cheapest place in the pipeline to be wrong. Fail there on purpose.

The practical form: no video generation without an approved, named, versioned keyframe file recorded in the approval log.

Two carve-outs are licensed, and they are licensed because the thing the gate protects — identity — is not at stake in either.

1. **A labelled text-to-video feasibility probe.** You have written the word *probe* on it and budgeted it as throwaway. It answers "is this motion achievable at all", and nothing it returns is delivered. The moment you find yourself trying to keep one, it was not a probe and it goes through the gate.
2. **A shot with no legible face in it** — an environment plate, a faceless insert, a detail, a texture, a hand at a size where the hand is the subject and no identity is readable. Text-to-video is a legitimate production route for these, not just a probe: there is no face to drift, so the cheapest place to be wrong is the returned clip itself. They still have to match their neighbours, so judge them against the continuity axes on return — geography, light direction, palette and lens feel all drift in a plate exactly as readily as in a close-up.

Anything with a face in frame goes through an approved keyframe, whatever the shot size and however short the clip. "It is only two seconds" and "it is only a wide" are the two sentences that precede most identity failures.

Corollary: when a clip fails on identity, wardrobe, framing, or light, do not rewrite the motion prompt. Go back to the frame. The concrete shape of that mistake:

```text
WRONG  kf v02 has the key on the wrong side. Six motion prompts follow, each adding
       another clause about the lamp. Six clips, six wrong lights, one wasted afternoon.
RIGHT  kf v02 rejected at gate 3 on axis 7. kf v03 regenerated with "key from camera-left"
       in the still prompt. One clip from v03. The lamp was never a motion problem.
```

## Shot difficulty rubric

Score each dimension 0–3 before you generate anything. Sum is 0–18. Quote a score in the table's own order — Action / People / Camera / Duration / Interaction / Continuity — so that `2/2/0/1/2/3 = 10, Amber` means the same thing in a shot plan, in a review note, and here.

| Dimension | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Action complexity | Ambient only (breathing, cloth, smoke) | One simple whole-body action (turn, sit, step in) | Two chained actions, or one fine-motor action | Precise action with a required outcome (catch, pour, unlock, strike) |
| People in frame | 0 | 1 | 2 | 3 or more |
| Camera movement | Locked | One slow move (push-in, pan, tilt) | One fast or compound move (orbit, crane, handheld follow) | Move plus reframe, or a move that must match across a cut |
| Duration | 3 s or less | 4–5 s | 6–8 s | Over 8 s |
| Physical interaction | None | Subject touches static set | Subject manipulates a prop | Two subjects contact, a prop passes between them, or a prop passes between a subject and a fixed feature — fed under a door, posted into a slot, pushed through a grille, dropped into a gap |
| Continuity dependency | Standalone | Must match one prior shot | Must match prior and following | Must match a locked face plus a progressive state (wet, dirt, injury) |

Three scoring conventions, because all three get argued about. *People in frame* counts bodies present in frame including partial ones, so a two-hand insert scores 2, not 1 — the model still has to render two people's anatomy. *Duration* is scored at the length you intend to keep after trimming, not the length you request from the tool. *Physical interaction* is scored on the contact geometry the model has to resolve, not on how many people are involved: a single pair of hands feeding an envelope under a door is a 3, because the model must land a moving object against a fixed surface at a specific place and produce a specific outcome, and that is the same problem a handoff sets it. This is the most common way a hard shot gets under-scored.

Override: any shot scoring 3 on Physical interaction plus 3 on any other dimension is Red regardless of total. Contact plus anything is where models fail hardest. Contact with a fixed feature counts — the override does not require two people.

| Band | Score | Strategy |
|---|---|---|
| Green | 0–5 | Generate directly. One keyframe, batch 4 parallel takes, pick a winner. Do not over-plan these; they are where you buy back time |
| Amber | 6–11 | Keyframe first, and last frame too where the tool exposes a first/last slot. Simplify one dimension before starting — usually duration or camera. Iterate serially, one variable per version. Probe this shot before you promise a delivery date |
| Red | 12–18 | Do not attempt as written. At 12–14, split at the natural beat break and re-score both halves; the split normally drops each to Amber. At 15–18, splitting is not enough — restage: give the work to the camera or to the actor but not both, move the difficult beat off-screen and cover it with a reaction shot plus sound, or replace the action with its aftermath. See [blocking-and-staging.md](blocking-and-staging.md) |

The band is a budget instruction, not a verdict on the idea. Every attempt count it implies — how many keyframes, how many clips, how long — is planning guidance and lives in the retry budget below; read the counts there rather than inferring them from the strategy column.

Worked example, scored then restaged. The shot as written: "In a heavy downpour, MEI steps out from the shelter and hands a parcel to LU, who takes it with his left hand while holding an umbrella, camera orbits 90° around them in one 10-second take." Action 2, people 2, camera 2, duration 3, interaction 3, continuity 3 = 15, and it trips the contact override twice over.

Restaged into two shots, which is how SH04 and SH05 of the bus-shelter scene got their present shape:

- Shot A, locked MCU two-shot, MEI steps clear of the roof and extends the parcel; LU's hand rises but does not arrive. 4 s. Action 2, people 2, camera 0, duration 1, interaction 2, continuity 3 = 10, Amber. Interaction drops to 2 because the shot ends on the offer — nothing is exchanged inside the frame.
- Shot B, locked CU insert on hands, the parcel transfers into LU's left hand. 3 s. Action 2, people 2, camera 0, duration 0, interaction 3, continuity 2 = 9, Amber. Interaction stays at 3, but continuity falls to 2 because no face is in frame, so the override cannot trip.

The orbit is gone and the cut does the work the camera was attempting. Note what the restage actually bought: not a lower total, but the destruction of the 3+3 pair. Splitting a Red shot without breaking that pair moves the same failure into a shorter clip.

## Crosswalk: risk band and motion budget

The same shot gets scored twice in this skill, by two systems, at two different pipeline steps. That is deliberate, but only if you know which question each one answers — read either as a general difficulty grade and they will contradict each other.

- The **risk band** (this file, pipeline step 7 — six dimensions, 0–18, Green / Amber / Red) **gates the plan**. It is scored on the shot as designed, before a prompt exists and before a tool is chosen. What it sets: how many attempts to budget, whether the shot needs a first/last pair, batch or serial, where the shot sits in the order of work, and whether it must be split or restaged on paper. It is the number you promise a schedule against.
- The **motion budget** (owned by [ai-video-tool-adapters.md](ai-video-tool-adapters.md), pipeline step 10 — three component rows, a duration multiplier, four modifiers, against a per-tool ceiling) **gates the prompt**. It is scored on the clip as written, for a named tool. What it sets: how much movement one clip may carry at once, how many elements the prompt may name, and whether this particular prompt is writable at all.

Neither replaces the other, and the clearest proof is what each one leaves out. The rubric has no environment dimension at all, so rain, fire, smoke, water and swinging practicals cost the plan nothing and can put a prompt over its ceiling on their own. The budget has no contact term and no continuity term, so a handoff or a progressive-state chain costs the prompt nothing and can put the plan in Red. A shot can be Amber and comfortably inside its motion ceiling; a shot can be Green and refused by the budget.

Where the six dimensions land. Read the third column before using the second — none of these is a conversion:

| Risk dimension, step 7 | Where it lands in the motion budget, step 10 | How tight the mapping is |
|---|---|---|
| Action complexity | Subject motion row | Close, not identical. Rubric 0 → row 0–1, rubric 1 → row 1–2, rubric 2 → row 2, rubric 3 → row 2–3 plus the `+1` fine-manipulation modifier where hands do the work. The rubric prices precision of outcome; the row prices quantity of movement. A slow exact action is high in one and low in the other |
| People in frame | `+1` per additional person with an independent action | Deliberately different. The rubric counts bodies, because anatomy is rendered per body. The budget charges only independent actions, and a crowd already paid for in the environment row is not charged twice. Three people doing one thing together is 3 in the rubric and `+0` in the budget |
| Camera movement | Camera motion row | Effectively 1:1, and the one clean conversion in the table. This is also the row a director style module's `motion_budget` field sets directly |
| Duration | The `×1.0` / `×1.3` / `×1.6` multiplier | Structurally different, and the most common source of disagreement. The rubric prices duration additively and flat; the budget makes it multiply everything else. Note that neither system prices identity-over-time — a long, simple, face-carrying shot is cheap in both and still fails. That risk is F1's, and it is capped by clip length, not by either score |
| Physical interaction | `+1` fine manipulation, plus upward pressure on the subject row | The weakest mapping here. The budget has no contact term beyond the hands modifier, so a contact shot can sit far inside its ceiling. When the rubric fires its contact override and the budget looks comfortable, the rubric is the one telling the truth |
| Continuity dependency | `+1` per bound reference beyond the first, and `+1` where a face fills more than a third of frame | Partial. Continuity load only reaches the budget when it becomes an on-screen face or an extra bound input. A progressive-state chain costs the plan a great deal and the prompt nothing |

No number crosses. Do not sum a rubric score into a budget score, and do not convert one band into the other — they run different arithmetic against different ceilings. Write the six dimension scores down when you score them, in or beside the shot plan's `Risk` cell ([../assets/shot-plan-template.md](../assets/shot-plan-template.md)), so step 10 reads them rather than re-deriving People, Interaction and Continuity from the blocking column. Re-derivation is where the two systems quietly stop describing the same shot.

How to run them together:

1. Score the rubric at step 7, on the shot as designed. Split or restage anything Red before writing a prompt.
2. Score the budget at step 10, on the clip as written, for the tool you have actually chosen.
3. When they disagree, both bind, and the stricter one wins inside its own domain. The budget can never authorise a bigger plan; the band can never authorise a fuller prompt.
4. Whenever either one forces a split, re-score **both** on every resulting piece. A split changes the plan and the prompt at the same time.

Worked disagreement. The shot as written: "MEI runs down the night-market lane in the rain, handheld follow from behind, the crowd parting ahead of her and the lanterns swinging. 10 s."

- Risk band: action 1, people 3, camera 2, duration 3, interaction 0, continuity 2 = **11, Amber** — one point below Red, no override, so the rubric's advice is "simplify one dimension, iterate serially, probe it before promising a date".
- Motion budget: subject 3 (run) + camera 2 (handheld follow) + environment 3 (rain, swinging lanterns, parting crowd) = 8; `×1.3` for 10 s = 10.4; no face modifier because she is seen from behind, and the crowd is already charged in the environment row = **10.4 against a ceiling of 6** for a wide shot with people.

They disagree, and the budget is stricter. Resolution: the budget wins on the prompt, so the shot is split before anyone spends a generation — none of Amber's retry allowance buys a clip running at 1.7× its ceiling, and serial iteration on it just produces the same warp six times. Split at the pivot into a locked wide of her running through the lane (subject 3 + camera 0 + environment 2 = 5 at 4 s, ceiling 6) and a short handheld MCU from behind her shoulders as she slows (subject 2 + camera 2 + environment 1 = 5 at 3 s, ceiling 6). Then re-score the band on both new shots: 1/2/0/1/0/2 = 6 and 1/1/2/0/0/2 = 6, two Ambers at the floor of the band rather than one Amber at 11 that was never going to render.

The reverse disagreement is quieter and costs more. SH05 below — the CU insert on hands, 3 s, locked — is Amber 9 on the rubric with interaction at 3, but scores subject 2 + camera 0 + environment 1 = 3, `×1.0`, `+1` because the second person's hand acts independently and `+1` for fine manipulation = 5.0 against a ceiling of 8, which is comfortable. The comfortable budget is not permission to batch it cheaply. What makes that shot hard is a contact outcome, and the budget has no term for one, so the band's Amber prescription stands: first/last pair, serial, one variable per version.

## Retry budget

This section owns retry and attempt economics for the whole skill. Other files quote these bands; none of them states its own.

Every number here is planning guidance for sizing a schedule — not a measured success rate, not a benchmark, and not a guarantee. Stochastic generation has a long tail, and a single shot can eat a day. Read them as the shape you budget against and re-check them against your own tally after the first scene. The useful number is not the average anyway; it is the stop rule.

| Band | Keyframe attempts to approval | Clip generations per approved shot | Wall-clock per approved shot | Stop rule |
|---|---|---|---|---|
| Green | 1–3 | 2–4, normally one batch | 10–25 min | If a second batch produces no winner, the shot is not Green — re-score it |
| Amber | 3–8 | 3–6, serial | 30–90 min | If you pass 12 clip generations, stop prompting and change the shot |
| Red, after splitting | 6–15 per half | 6–15 per half | 2–5 h | If a half still fails after a full split, cut the beat or cover it in sound |

Count generations, not "attempts": a batch of four is four generations even though it is one decision. A *generation* here is one clip the tool returned, kept or discarded — it is a cost, not an asset. That is a different quantity from the takes you end up cutting from, which is what the footage-ordering arithmetic in [editing-and-assembly.md](editing-and-assembly.md) counts; do not feed one number into the other's formula. On this file's counting, a 20-shot Amber-heavy scene plans out at 60–120 clip generations before you count the Red shots, so budget 150 and not 20. First-time users plan for 20 and lose the schedule in the first afternoon. Keep a running tally per shot; the tally is what tells you a shot was mis-scored, and it is the only number in this section that is a measurement.

Scored scene, using the six-shot bus-shelter example from [continuity-bible.md](continuity-bible.md). Columns are Action / People / Camera / Duration / Interaction / Continuity.

| Shot | A | P | C | D | I | Ct | Score | Band | Plan |
|---|---|---|---|---|---|---|---|---|---|
| SH01 EWS shelter, locked, 5 s | 0 | 1 | 0 | 1 | 0 | 0 | 2 | Green | Batch 4, pick one. The EWS does not resolve a face, so there is no identity dependency to score |
| SH02 MS MEI waiting, locked, 5 s | 1 | 1 | 0 | 1 | 1 | 1 | 5 | Green | Batch 4. She holds the parcel but does not manipulate it, so interaction is 1 |
| SH03 WS LU arrives, slow push-in, 6 s | 1 | 2 | 1 | 2 | 1 | 2 | 9 | Amber | Entry from screen-right is the risk; generate a first/last pair |
| SH04 MCU two-shot, the offer, locked, 4 s | 2 | 2 | 0 | 1 | 2 | 3 | 10 | Amber | Ends on the offer, so interaction is 2 and the override does not trip. Wet-state progression starts here; serial, one variable per version |
| SH05 CU insert on hands, the transfer, locked, 3 s | 2 | 2 | 0 | 0 | 3 | 2 | 9 | Amber | Interaction 3, but no face in frame drops continuity to 2. Hands are the failure surface; crop tight, keep it short |
| SH06 WS LU exits, locked, 6 s | 1 | 2 | 0 | 2 | 0 | 2 | 7 | Amber | Batch is acceptable; last shot, nothing downstream depends on it |

Read the plan off the bands: two Green at 2–4 generations each and four Amber at 3–6 gives roughly 16–32 clip generations — call it 30 when you are promising a date — and about half a working day for six shots. Note that the handoff was scored as a single Red shot before it was restaged; the two Amber rows above are the result, and they are the reason the scene fits in half a day at all.

Order of work: probe SH04 and SH05 together first, because they are the highest-scoring pair and the scene has no ending if the transfer will not read; lock MEI and LU; lock the shelter plate; then generate SH01–SH06 in story order, because the rain and the wetness both progress; batch SH01 and SH02 into the dead time while SH04 renders.

## Sequencing

1. Probe the hardest shot first, before the schedule exists. If the one shot the scene depends on cannot be generated, you need to know that on day one, not on day six. A feasibility probe is allowed to be ugly — you are testing whether the motion is achievable, not making the take.
2. Lock the character before the scene. Face, wardrobe, and proportions get their own reference session with neutral light and a clean background. Everything downstream references those assets. See [continuity-bible.md](continuity-bible.md).
3. Lock the location plate before any coverage. One approved wide of the space, then generate every angle referencing it. Coverage generated from text alone rearranges the room.
4. Generate progressive-state shots in story order. Rain, wetness, dirt, and injury are monotonic; each approved clip's last frame seeds the next shot's first frame.
5. Batch the easy environmental and insert shots into the dead time while a hard clip renders, rather than opening the day with them. Starting on the easy shots produces a folder full of progress and no answer to the question the scene depends on.
6. Never build an edit around a shot you have not proven. A timeline containing a placeholder for an unproven shot is a plan to discover, at the end, that the scene does not exist. If a shot is unproven, cut a version of the scene that works without it.

## Batch versus serial

| Situation | Mode | Why |
|---|---|---|
| Prompt structure is right; failures look random (hand shape, one flickery frame, a blink at the wrong moment) | Batch, 4 parallel takes of the identical prompt | You are sampling, not debugging. More samples is the only lever |
| You do not know which clause is causing the failure | Serial, one variable per version | Two changes in one version means you learn nothing from the result |
| Green shots, cheap and fast | Batch | The pick takes seconds |
| Red shots, expensive and slow | Serial | Fanning out a broken shot buys six copies of the same failure |
| The output feeds the next shot (last frame becomes next first frame) | Serial | You cannot branch a chain |
| Choosing between two legitimate directorial options | Batch, but log them as `v03a` and `v03b`, not `v03` and `v04` | They are siblings, not iterations, and the naming grammar reserves the letter suffix for exactly this |

The failure mode to avoid: fanning out twelve variations of a prompt whose keyframe is wrong. That is twelve expensive copies of the same mistake.

## Versioning and review

Version rules: `vNN` starts at `v01`, increments on every send, and is never reused or overwritten — the naming grammar is in [continuity-bible.md](continuity-bible.md). Keep failures. A directory of only successes cannot tell you what you already tried, and by attempt nine you will not remember. Rename a failure with its axis (`clip-FAIL-face`, `clip-FAIL-hands`, `clip-FAIL-drift`) so the listing reads as a diagnosis. Keep the prompt log per shot: every prompt sent, in order, with its version, so the diff between v04 and v05 is visible.

The review note. Write one per take, before you generate the next version. It exists to make the next attempt better, not to record an opinion.

```text
TAKE:    RAIN_SC02_SH04_v04_clip.mp4
VERDICT: reject
WORKED:  MEI's step clear of the roofline reads, and the key steepening on her face
         with it. LU's coat stayed dry. Key stayed camera-left.
BROKE:   Face — at 0:03.2 MEI's jaw widens and the mole disappears (axis 1). The clip
         ran 6 s because it kept trying to finish the transfer inside the shot.
         Prop — a second parcel ghosts in her left hand at 0:04.0 (axis 4).
NEXT:    One change only — end the shot on the offer and cut duration 6 s to 4 s; SH05
         carries the transfer. If the face holds, address the ghost parcel in v06 by
         adding "only one parcel" to the negative list.
```

Rules for the note: name the axis and the timestamp, never "it looks off". State exactly one change under NEXT, and queue the rest. "What worked" is not politeness — it tells you what not to disturb.

The approval log. One table for the project; it is the record that lets a future person trust a file.

| Date | Shot | Asset | Version | Stage | Reviewer | Verdict | Note |
|---|---|---|---|---|---|---|---|
| 2026-03-04 | SC02_SH04 | `kf-first` | v03 | keyframe | director | approve | key camera-left confirmed; mole on left |
| 2026-03-04 | SC02_SH04 | `clip` | v04 | video | director | reject | face drift 0:03.2; see review note |
| 2026-03-05 | SC02_SH04 | `clip` | v05 | video | director | approve | 4 s, ends on the offer; last frame usable as SH05's reference |

## The handoff package

What you deliver to an editor, a client, or yourself in six months. Anything missing here becomes a question someone has to ask you.

1. Shot list, final, with durations and function per row — [../assets/shot-plan-template.md](../assets/shot-plan-template.md).
2. Continuity bible, including the seed and reference registry and the state-change ledger — [continuity-bible.md](continuity-bible.md).
3. Approved keyframes, named to the grammar, with the rejected ones in a `_rejects` subfolder.
4. Approved clips, one per shot, version id in the filename, plus their source keyframes.
5. Sound plan with the assets it names — [../assets/sound-plan-template.md](../assets/sound-plan-template.md) and [sound-and-dialogue.md](sound-and-dialogue.md).
6. Edit timeline as both a project file and a readable table — [../assets/edit-timeline-template.md](../assets/edit-timeline-template.md).
7. Prompt log per shot: every prompt sent, in order, with tool and version.
8. Open-issues list: what is still wrong, what was accepted as a compromise, and what would fix it if there were more time. Write this one honestly; it is the item that saves the most hours later.

## Client and director checkpoints

Three approvals, no more. More checkpoints do not reduce risk; they move the decision to someone who has not seen the material.

| Checkpoint | Show | Ask for | Do not show |
|---|---|---|---|
| Treatment | Beat sheet, director's book, one page of visual thesis and palette, the shot count and the duration estimate — [../assets/beat-sheet-template.md](../assets/beat-sheet-template.md), [../assets/director-book-template.md](../assets/director-book-template.md) | Sign-off on the story, the tone, and the scope. Get the scope number in writing | Any generated image. A good image at this stage gets approved as the film |
| Keyframes | The locked character and location references, plus every approved first frame in shot order as a stills sequence | Sign-off on faces, wardrobe, location, and palette. State clearly that changing a face after this point re-costs the whole scene | Half-finished clips. Motion at this stage reads as "unfinished", not "in progress" |
| First cut | The assembled scene at correct rhythm with a temp sound bed, watched twice without commentary the first time | Notes at the level of the scene, not the frame. Ask what they understood, not what they liked | The shot you are least happy with, apologised for in advance. Either fix it or leave it and take the note |

Between checkpoints, send the open-issues list, not progress clips. Isolated clips get judged as finished work.

## Where the time actually goes

Rough shape of a small narrative project. Read the ordering, not the percentages: these are planning shares to budget against, not a measurement, and they move with the tool and the material.

| Phase | Share | What eats it |
|---|---|---|
| Story, beats, shot design | 15% | Deciding what the scene is about; the cheapest hours in the project |
| Keyframe iteration | 30% | Faces, wardrobe, light direction, hands. This is where the film is actually made |
| Video generation and waiting | 25% | Queue time and re-rolls; roughly half of it is unattended, so overlap it with other work |
| QC and repair | 15% | Continuity axes, physics tells, the last 0.5 s of clips |
| Sound | 5% | Ambience beds and one or two dialogue passes; small share, disproportionate effect |
| Edit, assembly, grade | 10% | Trimming, palette matching across sessions |

First-time users expect this to be 60% "writing prompts" and 40% everything else. It is not. Prompt writing is a small slice of the keyframe and video rows; the majority of the work is deciding what to generate and judging what came back. Plan the keyframe phase as the largest single block and the schedule holds.
