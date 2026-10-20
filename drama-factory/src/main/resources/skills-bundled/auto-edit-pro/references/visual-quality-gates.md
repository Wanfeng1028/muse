# Blocking visual quality gates

These checks apply to every real invocation. Passing unit tests, typecheck, build, or render is not visual acceptance.

## 1. Intentional whole-screen presentation

Judge the composition, not whether it protects a fixed center lane. Large foreground graphics, translucent face overlap, opaque full-screen, a clear presenter surrounded by graphics, and front/behind crossings are permitted. A beat can move between these states. The persisted seeded style pool may vary material and atmosphere; coverage and interaction still need a deliberate reason.

Record the purpose and reveal timing of coverage. Real gesture interaction uses observed source frames. Behind-subject effects use aligned transparent person frames; inspect matte edges and depth-order transitions. A merely translucent source duplicate does not pass as depth interaction.

## 2. Content-fit at any scale

There is no fixed maximum card height or side-only rule. Keep headings, items and takeaways readable and intentionally related; remove decorative empty regions. Big components can cross the center or leave the frame during motion, but their intended reading state must be legible. Preserve semantic component identities, not an obligatory original palette. Keep surface effects behind text and evidence; check all four mixed looks rather than only a calm frame.

## 3. Subtitle / keyword handoff

Brief coverage is permitted when an explicit time window and readable keyword phrase carry the same spoken meaning. Check entry, end and restoration; do not introduce a duplicate caption track. Outside handoffs, covered captions need a readable continuation or the original caption area must become visible again. A full-screen beat is not automatically opaque: transparency is a creative choice, not a failure.

## 4. Stable review frames

Representative stills are selected at 72% of each beat, after the main entry animation but before the exit. A midpoint screenshot is not sufficient because it can capture a half-built layout.

Gate C must include:

1. eight frames from eight distinct semantic structures when the video semantics support them;
2. the exact timestamp, structure, presentation mode, visual-style ID/seed when present, and SHA-256 for every frame;
3. a 4×2 contact sheet built from those exact frames;
4. inspect stage interaction entry, contact, depth switch and exit frames in addition to stable frames; review a short motion excerpt for these interactions;
5. manual frame review, recorded as pass/fail for intentional occlusion, observed gesture alignment, matte edges, density, clipping, contrast, semantic fit, and subtitle/keyword continuity.

## 5. Blocking decision

Any of the following blocks Gate D:

- an accidental overlap prevents the intended meaning from being read;
- a promised contact/depth action has visibly incorrect alignment, matte edges or ordering;
- a covered subtitle has no readable keyword/caption handoff;
- side card visibly padded with unused space;
- content clipped, overlapping, or too small to read;
- screenshot captured before the composition reaches a stable readable state;
- structure selected for visual variety rather than spoken meaning;
- an unpersisted or live-random effect changes on repeated seeks, or a surface effect indiscriminately replaces the source background/captions;
- evidence treated as decoration or an illustration treated as proof;
- any manual review item left unchecked.

After fixes, regenerate the real screenshots and review the new images. Do not reuse screenshots from a rejected render.
