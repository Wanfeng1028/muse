---
name: h3-prompt-writing
description: Write and refine MiniMax H3 prompts for text, first/last frames, and full image/video/audio references. Use for audiovisual prompt authoring and reference bindings, not operating a generation service.
---

# H3 Prompt Writing

## Scope and instruction priority

Write the requested H3 prompt to completion. User instructions override this skill's writing defaults, including presentation, except that the prompt fields must always be written in English regardless of the user's language or any requested prompt language; retain the H3 field syntax when delivering a directly submittable H3 prompt. These are video-model formats, not settings for the assistant's own model.

Infer routine creative details from the request and conversation. Ask one focused question only when an unresolved choice would change the core subject, reference role, or required timing. Preserve supplied reference labels when media cannot be inspected, and do not invent observations. Apply later corrections to the affected content while retaining the rest of the brief.

Prompt writing does not authorize generation, uploads, or skill installation. If the user also requests generation, pass the completed prompt to an available generation workflow within that authorization.

## Workflow

1. Identify the input mode: T2VA, I2VA, FL2VA, L2VA, or full-reference Ref2VA.
2. Read [shared syntax](references/shared-syntax.md) for shots, speakers, dialogue, and sound.
3. Read [base modes](references/base-modes.md) for text/keyframes or [full-reference mode](references/full-reference.md) for Ref2VA. Load both mode guides only when the request needs both.
4. Preserve the exact field names, section order, labels, and timing notation from the selected guide.

## Base Modes

- T2VA: build the full audiovisual timeline from text.
- I2VA: start from the first frame and develop forward from it.
- FL2VA: describe the continuous path between the first and last frames.
- L2VA: infer a plausible opening and converge to the supplied last frame.

Use `integrated_multimodal_description`, `overall_soundscape`, and `non_diegetic_music` in the order shown in the base-mode guide.

## Full-Reference Mode

Ref2VA rewrites use `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, and `non_diegetic_music` in that order. Reference labels stay consistent across all sections.

Use the full-reference guide for labels and retention markers.

## Output Rules

- Always write every prompt section in English, regardless of the user's language or any requested prompt language. Do not write the prompt body in Korean or another language. Dialogue, lyrics, and visible scene text are the exception: write them in the language in which they must be heard or seen (inside `<d>` with the matching language tag, or in quotation marks for on-screen text), never translated into English because the prompt is English. Keep supplied wording verbatim unless the user requests translation or rewriting, and write newly drafted lines directly in the intended language.
- Describe each shot by composition, subjects, environment, actions, camera, sound, and the exact point where referenced content appears.
- Avoid plot summaries, unresolved reference labels, and timing that does not match the requested duration.
- Return the selected mode's prompt fields and required keyframe alignment line without prefaces, extra headings, or explanations by default. Keep `retention_analysis` as the reference-role summary required by Ref2VA, not an account of internal reasoning. Follow an explicitly requested response format.
- Check the applicable field order, reference and speaker bindings, quoted text, and timing once before delivery. Recheck affected parts after a correction; do not generate a video merely to validate a text rewrite.
## Tips for Better Results
- Match the timeline to the requested duration. The supplied H3 source mentions 4–15 seconds but does not establish every interface's limits; verify the selected interface when submission limits matter. Do not silently clamp a requested duration. If FL2VA or L2VA requires an endpoint time and no duration is available in context, use a disclosed draft-duration assumption if authorized; otherwise ask for the endpoint time before claiming exact alignment.
- Keep reference labels consistent (e.g. `<Picture 1>`, `<Video 1>`, `<Audio 1>`) across every section.
- Prefer concrete visual and audio details over abstract words like "cinematic" or "beautiful".
- When using keyframes (I2VA / FL2VA / L2VA), clearly state how the first and/or last frame connects to the timeline.

Read [examples](references/examples.md) only when a concrete example is useful. [Sources](references/sources.md) records provenance and adaptation decisions for maintenance. Neither is a mandatory prompt-time read.
