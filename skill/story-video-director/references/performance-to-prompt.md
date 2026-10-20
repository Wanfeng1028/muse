# From screenplay to playable, renderable video

Read for any acted scene, especially grief, comedy, conflict, or a multi-clip dialogue exchange. This is a production method, not a list of flattering adjectives for a model. The screenplay determines what changes; the shot and prompt make that change visible and audible.

## 1. Write the scene as an exchange of actions

Before clips or assets, write a **scene card**:

| Field | Required answer |
|---|---|
| Given circumstance | What just happened, what each person knows, and what is at stake now? |
| Objective | What does each participant want from another person *in this scene*? |
| Obstacle | What concretely prevents it? |
| Tactic | What does each person do to overcome the obstacle: ask, bargain, joke, hide, stall, leave, hold on? |
| Turn | Which new fact, refusal, touch, sound, or action forces a different tactic? |
| End state | Who has gained or lost leverage, and what action must follow? |

Write a beat sheet in **stimulus → private processing → playable action → other person's delayed response → changed state** order. A line is an action addressed to a specific person; specify what the speaker is trying to do to that person. Mark a person's refusal to respond when silence is the action. Name every person in group blocking and give each one a reason to be there. Do not write “everyone is sad,” “Hollywood acting,” or a constant catalog of blinking/breathing as a substitute for behavior.

For grief, start from the character's relationship and immediate problem. Someone hearing a spouse has chosen death might first keep packing a bag, ask an absurd practical question, fail to finish a familiar gesture, then refuse a farewell touch. The emotion becomes legible because the ordinary routine fails. A loud cry, tear, or tremor is optional, not the default. A reaction must be triggered by something the character hears or sees; never reset them to neutral in the next clip.

For comedy, identify the **comic engine**: a character's serious objective, the expectation they create, the contrary result, and the cost of maintaining dignity. Allocate time for setup, a readable misread or reversal, and the other person's reaction. Do not instruct all actors to “act funny”; a withheld reply, wrongly timed gesture, or straight-faced attempt to recover can carry the laugh. Protect the payoff with a stable shot and a short post-line beat. If the moment also involves loss, specify whose point of view permits the humor and whose pain remains real.

Film-script references are useful for this discipline: an object can shift attention and expose a hidden fact; an apparent casual exchange can turn into a choice; a sound can bridge an abrupt change of place. Translate the mechanism into the new story. Do not copy source dialogue, scenes, or characters.

## 2. Convert the beat sheet into shots

For every generated clip, maintain a **performance sheet** alongside the screenplay:

```text
Scene/clip ID; cast physically present (stable character IDs); objective and turn.
Opening state: knowledge, emotion, eyelines, body/hand contact, prop owner,
screen positions, last completed action, movement direction and speed.
Beat time: trigger → actor's tactic/body action → recipient's observable response.
Dialogue: utterance ID, exact line, speaker, addressee, speech time, visibility.
Coverage: whose face/hands must be readable, shot size, axis, camera move.
Sound: source and start/end times, ambience continuity, intentional silence.
Outgoing state: exact unfinished action or new question; next shot's first action.
```

First plan human timing. Within the 15-second provider cap, leave room for seeing, deciding, speaking, listening and consequence. A line that fits by character count may still be too dense for its acting beats. Prefer one dominant dramatic turn and one primary speaker per clip when facial sync matters. Split dialogue or move an explanation to an appropriate later shot; do not ask the model to play several emotional turns while sprinting through a paragraph.

Preflight the beat sheet and dialogue ledger on one clock. The speaker must reach the speaking position before the line begins; a child cannot have a close, readable mouth while still far away in a wide running shot unless a specific cut or sound-led path is planned. A line's trigger cannot happen after its scheduled onset. The first and final states must agree with the cast/location record and adjacent handoff; scene headings alone cannot establish geography.

Only then write the prompt. The model-facing prompt should say **who does what, in which order, at what time, and what the camera can actually see**. Keep a small set of identity anchors and concrete locks: the same face/hair/costume, the same hand on the same prop, the same geography and lighting. Use visual adjectives sparingly. “At the word ‘走’, her right hand stops folding his sleeve; she looks at the half-folded cuff, not his face” is more useful than “devastated, deeply emotional, award-winning performance.”

## 3. Plan a three-clip run as one scene

For any three adjacent clips in the same scene, check the whole run in one table before generation. The middle clip must inherit the first clip's consequence and create the third clip's trigger. A repeated establishing shot or restarted action is a screenplay/edit error even if faces match.

Illustrative original scene, three short clips, one room and one continuous tea-kettle hiss:

| Clip | Start → turn → end | Picture/sound handoff |
|---|---|---|
| A | She is folding his coat, assuming he will return. He says he has accepted a fatal mission. At the word “不回”, her folding hand stops with one sleeve half turned. | End on her hand and his visible distance behind it. Kettle hiss continues; the sleeve remains in her **right** hand. |
| B | Begin at the same moment from a clearly closer angle on the same side of the axis. She straightens the cuff as if she did not hear; asks when he needs it. He cannot answer at once. | Match the half-finished cuff action, not the entire last frame. The man stays off-screen during her short line if the generator cannot keep his mouth closed. His failed breath begins before the next cut. |
| C | His breath carries in. Close on him attempting to take the coat; her hand closes around the cuff before he can touch it. He says one short answer. She turns away instead of replying. | The hand contact and gap close the dramatic question. Cut on her turn; carry kettle hiss, do not restart it. |

This run depends on **the wife's tactic changing from denial to a practical question to refusal**, not on mandatory crying. If the story is comic, the same three-part structure may be setup → failed attempt → reaction, with an appropriate held beat after the reversal. A real rendered A tail must be inspected before selecting a frame for B. If A's fingers or face deform, choose a sound/insert/reaction cut or repair A; do not seed B with the defective frame.

## 4. Choose a dialogue production path before prompting

Never promise exact lip sync solely because a prompt says “嘴唇同步.” Choose and record one path per utterance:

1. **Generated sync, controlled coverage:** one visible speaker, short exact line, stable medium close-up, minimal head rotation, listener off-screen or with mouth hidden. Render and inspect at normal speed. Use only if this provider/shot has demonstrated acceptable sync.
2. **Post-recorded voice and lip-sync pass:** generate controlled silent or guide-audio picture, record/produce the approved line with fixed voice identity, then align with a dedicated lip-sync/edit tool. Inspect the actual output. Do not imply the current renderer performs this pass unless it does.
3. **Sound-led coverage:** put the line over the speaker's back, hands, an object, or the listener's reaction when dramatic geography makes the source clear. This is not a trick to disguise random speech; the speaker and listener's behavior must still answer the line.

Keep the dialogue ledger as exact-text truth. Mark `speaker_id`, line ID, visibility and production path. For generated dialogue, budget onset, speech, mouth close and a reaction; do not cut on an open mouth or let the next clip repeat the line. For post audio, mark the final voice/audio source and its absolute timeline. For a sound-led shot, explicitly forbid the visible listener from mouthing the line. If the face visibly says different words or speech starts before the speaker's mouth moves, the result fails even when the voice and line are correct. Record the failure and simplify coverage, use a different path, or repair the edit.

## 5. Review performance and synchronization, not prompt intentions

At each scene pass, watch the contiguous edit once without reading prompts. Ask: Can a viewer tell what each person wants, what changed, and why the next shot exists? Then inspect each critical beat and each 1–2-second boundary window with sound. Record exact timecodes for:

- **Performance:** stimulus precedes response; an emotion persists across cuts; body behavior and listener reaction carry the subtext; comic setup and payoff have enough space.
- **Identity/state:** face, hair, clothing, hands, props, eyeline, axis, location and light remain stable or change for a stated reason. A still frame alone cannot verify motion.
- **Sound/picture:** correct words and speaker, visible mouth motion aligned to the line, listener not mouthing it, no duplicate syllable, breath or ambience restart.

Classify a failure by cause before fixing it: weak dramatic beat → rewrite screenplay; inert acting → change actor task and coverage; bad seam → change cut/trim/bridge or repair the earlier clip; facial drift → fix identity conditioning or use a motivated alternative angle; lip mismatch → shorten/re-shoot dialogue coverage or do a verified post-sync pass. Rerender the smallest affected unit within the project's authorized spend. Do not mark a clip “cinematic,” a cut “seamless,” or lip sync “correct” without viewing the rendered result.
