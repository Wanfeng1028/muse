# Wan 3.0 writing guide

Use this reference when a request needs more than the entrypoint's basic workflow.

## Source priority

Follow the user's explicit creative and output instructions before this reference's writing defaults. Use verified documentation for the selected Wan interface when a capability or hard limit matters. The older Wan 2.2 system prompt contributes only durable writing heuristics such as intent preservation, motion expansion, and camera consistency. Do not carry forward its version-specific defaults, language limits, or content-replacement rules.

## Mode formulas

### Text-to-video

Use this order as a reasoning checklist, not a rigid sentence template:

1. **Entity:** Identity, count, defining appearance, wardrobe or material, posture.
2. **Scene:** Foreground, environment, spatial relation, time and weather when relevant.
3. **Motion:** Main action, direction, amplitude, speed, sequence, interaction, and result.
4. **Aesthetic control:** Light source and quality, shot size, angle, lens, composition, camera movement, tone.
5. **Stylization:** One coherent medium, genre, rendering treatment, or photographic language.

The final prompt should read as a unified shot description, not a labeled form, unless the user asks for a structured breakdown.

### Image-to-video

Assume the image already defines entity, scene, composition, and style. Include only enough visual anchoring to disambiguate motion. A strong I2V prompt normally specifies:

- the subject's first motion, continuation, and end state;
- secondary motion already plausible in the image, such as hair, cloth, foliage, water, smoke, reflections, or background traffic;
- camera behavior, including `fixed camera` when no movement is wanted;
- preservation constraints that matter, such as stable identity, unchanged background geometry, or no new objects.

Do not invent a new subject, wardrobe, scene, or major prop. Do not spend most of the prompt repeating visible details.

### First and last frames

Name the subject that persists across both frames and describe the most plausible continuous path from the first state to the last. Keep changes causally ordered. If the brief requests a scene transition, preserve that transition. Offer separate clips only when the selected interface cannot express the requested structure, not merely because a scene changes.

### Reference-guided generation

Use reference identifiers exactly as supplied by the interface or user. Bind the identifier to a stable noun every time ambiguity is possible, for example, `the red robot in Image 1`. For Wan 3.0, images and videos are numbered separately in upload order. In English use `Image 1` and `Video 1` (capitalized, with a space); the supplied guide uses `Image1` and `Video1` for Chinese. A lone source may be called `reference image` or `reference video`. Preserve explicit user/interface labels; if conversion is necessary, state the alias mapping rather than silently changing bindings. Do not inherit Wan 2.6's `character1` convention or its three-character limit.

## Multi-shot narratives

Use an overall description followed by numbered shots and their content. For a timed request, add ordered ranges matching the total duration, keeping identities, props, and causal state consistent across cuts. When timing is not supplied, use shot order alone or a reasonable disclosed draft timing if helpful; do not block a usable untimed draft.

The source explicitly includes Wan 3.0 in its multi-shot formula, while a generic “what not to prompt” table says one clip must be continuous. Apply that caution to overloaded single-shot prompts; it does not negate the version-specific multi-shot formula. Do not copy the source example's unexplained timing gaps. Keep newly designed ranges contiguous. Interface-specific submission settings must be checked only when needed, not used to block prompt writing.

## Motion design

Prefer a short causal chain over a verb list:

`initial state -> initiating movement -> visible reaction/effect -> readable end state`

Useful motion controls include direction, trajectory, speed, acceleration, force, repetition, amplitude, and interaction with surfaces or nearby elements. Select only the controls that affect the shot. For subtle scenes, micro-actions such as breathing, gaze shifts, finger movement, cloth response, or changing reflections can carry the clip without forcing an unrelated large action.

Keep action density proportional to clip duration. A short clip should usually contain one main beat and at most one secondary reaction.

## Camera and aesthetics

Choose camera behavior for narrative function:

- **Push-in:** intimacy, attention, realization, or tension.
- **Pull-out:** reveal scale, context, isolation, or surprise.
- **Tracking/follow:** travel alongside the subject and preserve motion readability.
- **Lateral move or pan:** reveal comparison or guide attention across space.
- **Orbit:** present the subject as central or heroic; use the source recommendation of an arc under 45 degrees when the orbit arc is unspecified, and preserve the user's requested angle. This is a composition heuristic, not a hard model limit.
- **Fixed camera:** emphasize stillness, performance, transformation, or precise object motion.

Use one dominant shot size and angle. Add a lens only when its effect matters: long-focus for compression and separation, wide-angle for spatial depth, fisheye for deliberate distortion, tilt-shift for miniature appearance. Avoid incompatible combinations and duplicate labels.

Lighting descriptions work best when they identify a plausible source and one or two consequences, such as `soft daylight through a north-facing window, gentle side light and low contrast`. Do not dump every lighting keyword into the prompt.

## Dialogue and sound

Add audio only when the user requests it or the target generation path supports it. Separate the sound plan mentally into:

- **Voice:** exact line, speaker, emotion, tone, pace, timbre, accent/language.
- **Sound effects:** source, action, material, timing, and ambient context.
- **Background music:** style, energy, instrumentation, and temporal change.

For multiple speakers:

1. Assign unique, stable visual labels.
2. Anchor each line to that character's visible action first.
3. Give distinct voice qualities.
4. Use explicit temporal connectors such as `then`, `immediately after`, or `after a pause`.

Keep spoken lines short. Preserve requested words without guaranteeing exact word-level lip synchronization. In the supplied Wan 3.0 R2V guidance, omitting lines allows the model to invent dialogue and omitting music permits contextual BGM. When the user wants those layers absent, use `No dialogue.` or `No background music.`; omission alone is not a silence instruction. These are documented natural-language controls, not API flags.

## Prompt repair rules

Repair weak inputs without changing their premise:

- **Too vague:** Add a plausible setting, motion path, camera plan, and restrained aesthetic choices that fit the request.
- **Too static:** Convert state into observable change; add micro-motion before inventing a new major action.
- **Too long:** Preserve required beats and remove adjective stacks, redundant static details, and secondary actions.
- **Conflicting camera terms:** Keep the term most important to the stated intention and remove the rest.
- **Several locations:** Use the multi-shot formula for a narrative with scene changes. Split only when requested or required by a verified interface limit; simplify overloaded action within each shot.
- **Exact text on screen:** Keep the exact requested wording in its display language; do not translate it into English. If precision is essential, briefly identify postproduction as an option without silently replacing the text with approximate signage.
- **Named real person:** Preserve the requested identity; do not apply a blanket content-replacement rule. If a verified target-interface restriction affects the request, state it and distinguish any proposed alternative from the requested prompt.
- **Exact lip sync:** Keep the spoken line concise and recommend a dedicated lip-sync or postproduction stage only if precision is essential.

## Final quality gate

Before answering, confirm that another reader can identify, in one pass: who or what is present, where it is, what visibly happens, how the camera observes it, and what visual treatment governs the shot. For I2V, the answer should instead emphasize what changes from the supplied frame and what must remain stable.
