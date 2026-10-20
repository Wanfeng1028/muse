---
name: demo-storyboard
description: Shape grounded product evidence into a coherent, reviewable storyboard before planning browser actions.
---

# Demo storyboard

Use this skill to turn an approved brief into a short lesson the viewer can follow. The storyboard explains why each visible change matters; it is not a selector list or an automation transcript.

Ground the story in the current product surface. Keep required feature behavior visible and intact. For each scene, write **Before / During / After / Say / Do / Learn / Next** so a reviewer can judge the whole teaching beat, not just a single frame.

## Workflow

1. Confirm the viewer, outcome, evidence, and required behaviors from the brief.
2. Draft one through-line that the opening raises and the ending resolves. Choose the smallest set of scenes that provides the necessary proof, keep one task per lesson, and end on what the viewer can now do.
3. For each scene, describe the starting state, the visible change, the readable result, the narration intent, actions at a semantic level, one learner takeaway, and the next beat.
4. Check that every required behavior has a visible action and a product-state assertion. Do not replace an action with narration.
5. Review the storyboard against current product behavior, accessibility, and the complete viewport. Then pass it to [demo-narration](../demo-narration/SKILL.md) and [browser-demo-recording](../browser-demo-recording/SKILL.md).

Read [the story contract](references/story-contract.md) when building or revising a plan. Keep exact selectors and low-level timing out of the storyboard until its story and wording have been reviewed.
