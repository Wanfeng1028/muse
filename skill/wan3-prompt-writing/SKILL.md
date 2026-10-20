---
name: wan3-prompt-writing
description: Write and refine Wan 3.0 prompts from scene ideas and image/video references, including text-to-video, image-to-video, sound, and multi-shot narratives. Use for prompt authoring, not operating a video-generation service.
---

# Wan 3.0 Prompt Writing

Convert the user's creative intent into a prompt the model can execute reliably. Preserve the requested subject, action, setting, mood, style, constraints, and continuity. Add only compatible details that resolve underspecification; never replace the concept with a different one.

User instructions override this skill's writing defaults, including format and creative choices, except that the final model prompt must always be written in English. Complete an actionable rewrite using context and reasonable assumptions. Apply later corrections to the affected parts while preserving the remaining brief. Prompt writing alone does not authorize generation, uploads, or environment changes.

## Choose the generation mode

- **Text-to-video (T2V):** Build `entity + scene + motion + aesthetic control + stylization`. Use the basic `entity + scene + motion` form when the user wants open-ended exploration or a deliberately simple prompt.
- **Image-to-video (I2V):** Treat the image as the source of appearance, composition, scene, and style. Write mainly `motion + camera movement`; mention visible entities only as anchors for who or what moves. Do not needlessly redescribe the image.
- **First/last-frame animation:** Describe the continuous transformation or movement that plausibly connects the supplied frames. Do not invent cuts between them.
- **Reference-to-video (R2V):** Use `reference identifier + action + scene + optional lines/music`. Preserve supplied labels. For unlabeled supplied media, use `Image 1`, `Video 1`, etc., numbered separately by type in upload order. Do not invent media or import Wan 2.6 `character1` identifiers.
- **Multi-shot narrative:** The supplied Wan 3.0 guide supports `overall description + shot number + timestamp + shot content`. Keep requested or clearly implied multi-shot narratives together; do not automatically split them into generation jobs. A requested single shot stays continuous. Read the writing guide for timing and source conflicts.

If the mode is evident from attached media and wording, infer it. Ask one concise question only when the missing mode, duration, or reference mapping would materially change the result.

Missing duration alone does not block an untimed single-clip prompt. When media cannot be inspected, retain the user's labels and stated roles, use only supplied facts, and do not claim to have viewed it. Clarify only if the requested rewrite depends on visual details or mappings that remain unknown.

## Write the prompt

1. Extract hard constraints before embellishing: required subjects, count, identity, action, setting, duration, framing, camera behavior, style, dialogue/audio, and exclusions.
2. Give each shot one clear visual event or compact cause-and-effect beat. Express motion as an observable sequence with direction, speed or intensity, and physical result where useful.
3. Choose a coherent camera plan. One primary move is usually enough. Use `fixed camera` when stillness matters; avoid contradictory moves or piling on cinematic terms.
4. Add only the aesthetic controls that materially shape the shot: shot size, angle, lens, composition, light source/quality, tone, and time of day. Make them mutually compatible.
5. State one consistent visual style when requested or clearly implied. For an underspecified live-action concept, use restrained cinematic realism rather than imposing a conspicuous genre.
6. Put temporal information in execution order. Keep the main action easy to find and avoid long inventories of static detail.
7. Run the checks below, then deliver a copy-ready prompt.

For detailed mode formulas, camera intent, dialogue/audio handling, and prompt repair rules, read [references/wan3-writing-guide.md](references/wan3-writing-guide.md). For representative transformations, read [references/examples.md](references/examples.md) only when examples would help resolve an unusual or ambiguous request.

## Reliability checks

- **Intent:** No requested subject, action, relationship, visual style, or constraint was silently changed.
- **Continuity:** A continuous shot has coherent geography and motion; multi-shot narratives use explicit transitions and stable subjects, props, and event order.
- **Motion:** The prompt says what moves, how it moves, and what changes; I2V prompts prioritize dynamics over static restatement.
- **Camera:** Shot size, angle, lens, and movement support the same composition. If an orbit is desired but its arc is unspecified, the source recommends under 45 degrees to reduce distortion. Preserve an explicit requested angle; this is a recommendation, not an interface limit or a default to add an orbit.
- **Identity:** Keep subject labels unique and consistent. Do not substitute pronouns when multiple speakers or similar subjects could be confused.
- **Model limits:** Preserve requested identities, exact text, and dialogue. Do not silently substitute a generic person or approximate wording. Do not guarantee exact text rendering or word-level lip sync; mention a concrete limitation briefly only when it affects the deliverable, using verified target-interface constraints rather than assumed model restrictions.
- **Syntax:** Do not invent parameters, negative-prompt syntax, weights, or reference identifiers that the user did not provide and the target interface has not established.

## Output contract

Default to a single heading, `Wan 3.0 prompt`, followed by one fenced text block containing only the final model prompt. Always write the model prompt in English, regardless of the user's language or any requested prompt language. Do not write the prompt body in Korean or another language. Dialogue, lyrics, and on-screen text are the exception: write them in the language in which they must be heard or seen, never translated into English because the prompt is English. Keep supplied wording verbatim, write newly drafted lines directly in the intended language, and name the spoken language (for example, `says in Korean`).

Add a short `Assumptions` note after the prompt only when a material choice had to be inferred. If the user asks for prompt-only output, return only the prompt. When the user requests alternatives, vary one meaningful dimension per version and label that difference rather than rewriting arbitrarily.

Keep the final prompt proportional to the scene. Do not print the workflow or reliability checklist. One review of intent, continuity, bindings, and output format is sufficient unless a correction reveals another issue; video generation is not required to validate a text rewrite.

[Sources](references/sources.md) records source scope and legacy Wan 2.2 adaptations for maintainers; it is not a mandatory read on every invocation.
