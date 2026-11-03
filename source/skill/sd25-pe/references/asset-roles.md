# Asset roles

## Evidence and identifiers

- Preserve explicit user labels, numbering, and assignments. Upload order determines identifiers within each media type, not character identity.
- With unlabeled assets, propose aliases such as `@Image1`, `@Video1`, and `@Audio1` separately by type in supplied order. Give a compact asset/path-to-alias map outside the prompt so the downstream operator can reproduce it. Aliases do not mean files have been uploaded.
- Inspect accessible assets; with many assets, inventory first and examine relevant or conflicting candidates closely. Do not claim a full-video inspection from sparse stills.
- Names, ages, relationships, ownership, and story outcomes come from the brief. Media supplies observable appearance, motion, layout, and sound. Filenames establish none of these.
- If media cannot be read, preserve stated roles and labels, add no invented visual or audio details, and continue. Do not fabricate transcripts or an unused asset inventory.

## Bind the intended dimensions

State each subject's mapping independently: `Mina uses @Image1 for appearance; Jun uses @Image2 for appearance.` One asset can contribute several explicitly assigned dimensions. Multiple views may jointly define one subject; say so to prevent duplication. A group image may define its actual group. Do not map a single-person image to two simultaneous identities unless identical appearances or duplicates are requested.

Bind scenes, props, motion, camera, lighting, style, and voice separately where ambiguity exists. For example, `@Video1 supplies only walking action and tracking camera; Mina's appearance comes from @Image1.` When a reference precisely specifies the action sequence, do not reinvent it.

When assignments cover the request, do not activate extra candidates merely because they look relevant. Select more assets only when requested or needed for an unassigned required role. With a complete inventory, enumerate inactive identifiers by type under `【Unused Assets】`. This is a local writing convention, not an input filter: downstream uploads still count toward limits.

For multiple scenes, activate only relevant subjects/props/references per scene. Anchor positions to stable objects (inside/outside a counter, facing a door). Track a transferred prop as one object whose owner changes.

Voice-timbre reference does not imply copying source words. Written dialogue takes precedence unless the user asks to reuse source audio. State whether audio supplies timbre, spoken content, music, effects, or several assigned roles.

Clarify only unresolved mappings that change a core identity, count, master, boundary frame, or relationship. If mapping assumptions are authorized, make a conservative assignment explicit without presenting it as discovered identity.

## Supplied guide's input envelope

| Asset | Documented maximum |
| --- | --- |
| Images | 30, each within 4K |
| Videos | 10, combined duration at most 30 seconds |
| Audio clips | 10, combined duration at most 30 seconds |
| Total | 50 references |

These are snapshot limits. Use verified selected-interface limits for submission if different. Text exclusions do not remove uploaded assets. When over limit, propose a reduced set outside the prompt while preserving indispensable roles; do not silently drop core references or claim all assets are submittable.

Recommendations, not hard limits: 1–8 image-reference subjects; 1–5 audio/video-reference subjects; 5–10-second subject clips; editing sources within 20 seconds with 1–5 edit-reference images. Exceeding a recommendation alone does not stop authoring.
