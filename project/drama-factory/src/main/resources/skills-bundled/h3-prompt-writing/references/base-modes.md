# Video Prompt Writing Guide (T2VA / I2VA / FL2VA / L2VA)

Presentation rules below are defaults: follow an explicit user request while preserving the H3 field names, speaker tags, and timing syntax. Always write the prompt fields in English, regardless of the user's language or any requested prompt language. Preserve supplied dialogue and visible text verbatim unless the user asks to translate or rewrite them. Examples illustrate the format; they do not authorize adding their dialogue, music, or scene details to another request.

## 1. Task Overview

- **T2VA**: Builds a complete audiovisual timeline from text.
- **I2VA**: T2VA body + first-frame instruction + a visual path that develops forward from the first frame.
- **FL2VA**: T2VA body + first-and-last-frame instruction + a continuous path from the first frame to the last frame.
- **L2VA**: T2VA body + last-frame instruction + a path that converges from a plausible preceding state to the last frame.

## 2. Final Prompt Structure

### 2.1 Part One Is the Instruction

**T2VA** has no image-alignment instruction and begins directly with the three core fields.

**I2VA** always uses:

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
```

**FL2VA** always uses:

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.
```

**L2VA** always uses:

```text
How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.
```

Here, `N` is the index of the actual final shot, and `S.SS` is the effective video duration formatted to exactly two decimal places. The instruction must be the first line of the final prompt, followed by one blank line before the core fields.

### 2.2 Part Two Contains the Three Core Fields

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

- **integrated_multimodal_description**: Describes visuals, actions, shots, speakers, dialogue, singing, and diegetic audio along the timeline.
- **overall_soundscape**: Summarizes ambient sound, physical action sounds, and non-verbal human sounds across the entire video.
- **non_diegetic_music**: Describes background music that the characters cannot hear and only the audience can hear.

## 3. How to Incorporate Keyframes into the Multimodal Description

### 3.1 I2VA: Begin from the Image and Develop Forward

`<Picture 1>` is the actual first frame of the video at 0.00 seconds and belongs to `[Shot 1]`. The description should first establish the style, subjects, composition, and scene anchors in the image, then describe the next action. Character identity, clothing, colors, key objects, and spatial relationships should remain consistent.

Recommended structure: **first-frame anchor → action onset → continuous development → result or reaction**.

### 3.2 FL2VA: Describe the Path Between the First and Last Frames

Picture 1 is the opening, and Picture 2 is the ending. Focus on how the subject moves, how poses change, how objects are manipulated, how the composition evolves, and how the scene or lighting transitions.

FL2VA generally favors a single shot so the model can interpolate continuously from the first frame to the last frame. Use multiple shots only when they are explicitly specified. The last frame must be reached by the final `[Shot N]` at the end of the video.

Recommended structure: **first-frame state → observable intermediate changes → progressively narrowing differences → last-frame state**.

### 3.3 L2VA: Infer the Opening and Land on the Image at the End

`<Picture 1>` is the final frame of the video and belongs to the last `[Shot N]`; it does not inherently belong to Shot 1. Infer a plausible earlier state from the user's intent and the last frame, then describe how the characters, objects, camera, and scene gradually approach the reference image.

Recommended structure: **plausible preceding state → explicit action and transition path → gradual convergence in the final shot → last-frame landing**.


Read [shared syntax](shared-syntax.md) for the shot, dialogue, and sound fields.
