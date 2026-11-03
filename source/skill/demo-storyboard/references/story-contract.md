# Story contract

## Product proof before polish

Make claims from current source, tests, documentation, or a real product state. Link each important claim to the evidence that supports it. If the behavior cannot be demonstrated, narrow the claim or mark the gap; narration is not proof.

Keep the feature's essential behavior distinct from incidental navigation. Shorten setup only when it does not remove the requested interaction or its visible result. If the feature changes product state, show a meaningful before and after.

## Scene card

Use one primary purpose per scene and fill these fields:

- **Before:** what the viewer can see before the interaction.
- **During:** what the real product visibly changes.
- **After:** the resulting state that remains readable long enough to understand.
- **Say:** the intended spoken thought; later revisions must be hash-bound and exact.
- **Do:** semantic actions and their user purpose, not CSS selectors or coordinates.
- **Learn:** one useful idea the viewer should retain.
- **Next:** how this result sets up the next scene.

Scenes should form one connected explanation: orient the viewer, show a meaningful decision or change, interpret the result, and resolve the opening promise. A collection of correct but disconnected click descriptions is not a storyboard.

## Teach the task

- **One task per lesson.** For course or tutorial lessons, split at distinct tasks or learner outcomes. For a product or marketing walkthrough, connect the necessary actions to the brief's primary outcome. Duration alone does not demonstrate that the story contains a second task.
- **Name terms before using them.** When the task depends on two or three unfamiliar concepts, open with a short orienting scene that names them on screen before the first action.
- **Show the likely mistake.** When viewers commonly go wrong at a step, say so in that scene's Say or Learn and show how to recognize the correct result.
- **Make the ending a capability.** The final scene's Learn states what the viewer can now do. Do not end on a teaser for another lesson or open with a greeting; each lesson stands alone.
- **The screen carries the lesson.** Every scene needs a visible change that makes sense with the sound off. A scene that is only explanation over an unchanging screen belongs in a shorter line, a callout, or a different scene.
- **Point without distraction.** Direct attention with the action itself, a still cursor at the target, or a bordered callout that leaves the rest of the frame visible. Use zoom sparingly; some channels forbid it, so record the choice.

## Review the composition

Check that the full frame contains the promised evidence before and after state changes. A resize must keep nearby evidence visible and legible. A share action must reach a real read-only destination when sharing is part of the claim. Identify needed viewport, responsive, empty-state, or accessibility checks before recording.

Keep selectors, coordinates, recorder-specific IDs, and exact low-level action sequences in the capture plan, not in the story. Do not shape the story around an existing recording. Consider reuse only after the story is locked and compare it against the approved scene and proof requirements.
