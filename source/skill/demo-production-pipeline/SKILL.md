---
name: demo-production-pipeline
description: Produce many narrated demos at once with a cheap silent rehearsal pass, one serialized voice and render queue, resettable demo data, and a producer/coordinator split that keeps agent and voice costs low.
---

# Demo production pipeline

Use this skill when you are making more than a handful of narrated demos, or when several agents record against one machine. A single demo can follow the other skills directly. At volume, voice time and expensive model tokens are the scarce resources, so find every problem before either is spent.

## Workflow

1. **Scout before you script.** Collect each page's route, stable anchors, roles, and accessible names with a script or a small model. Give that sheet to the narration writer; writers should not explore the interface with expensive tokens.
2. **Rehearse silently (pass 1).** Run the real browser capture with a synthetic narration clock: no voice and no render. Rehearsals are cheap, so run them in parallel. A rehearsal must fail on everything the final [demo-audit](../demo-audit/SKILL.md) fails on, with a safety margin. Record a pass marker bound to the plan's content hash.
3. **Voice and render in one queue (pass 2).** One serialized queue per machine takes only plans whose latest rehearsal passed for their current hash. It owns the voice engine, behind a single lock and a shared sentence cache. Never discover a plan problem during pass 2.
4. **Reset the data each plan touches.** Before every rehearsal and render, apply the plan's idempotent reset. It restores rows the plan changes and deletes rows it creates. Move date-anchored data to "today", and clear persisted user preferences.
5. **Check the environment before the app.** If a plan passed before and now fails with timeouts, server errors, or clock drift, check machine load, database drift, and whether the served app changed under the recorder.
6. **End at review.** A finished render waits for [an independent review](../demo-story-review/SKILL.md); it is not publishable on its own.

Split the work by role. Producers are mid-tier agents that scout, script and rehearse in their own worktrees. One coordinator owns the voice queue, merges, and issue filing. Producers write findings into their own section of a findings file, and one filing agent dedupes them. A lesson whose text does not match the app goes back to the course outline; it is not a bug.

Read [the pipeline contract](references/pipeline-contract.md) for the rehearsal gate, markers, data resets, shared voice resources, environment checks, and the producer brief.
