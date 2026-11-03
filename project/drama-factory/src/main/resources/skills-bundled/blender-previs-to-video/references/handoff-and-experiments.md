# Reference handoff and experiment records

## Prompt handoff

Identify the actual video submitted: a clean previs, a full edit, or a continuation clip. A side-by-side review video is not automatically the intended generation reference.

Give every used asset an exact file/version and role. Typical roles include camera/action/timing from previs; anatomy/identity from hand or character images; product design and surface content from image sheets. These roles may overlap when the user intends it. State the intended priority where the proxy silhouette and appearance reference differ.

Keep surface assignments explicit when confusion has appeared: cover screen, continuous inner screen, rear housing and cameras, fixed wallpaper versus animated content. Preserve the user's current content policy. Do not switch to invented screen art merely because a placeholder is blank.

Use the chosen model writer for reference identifiers and prompt structure. Do not translate H3 native subject tags into Seedance/Wan aliases by habit. A platform's actual attachment chips, human-readable filenames and native subject definitions are different layers; keep them consistent without claiming a plain-text alias binds an uploaded file.

Separate settings from the creative prompt. Use the selected interface's verified duration controls when submission is in scope; do not assume a historical source guide establishes every platform's limits. If output must be longer than a reference, use a disclosed final hold only when compatible with the request. Do not silently retime the choreography.

Assign each previs placeholder, such as a background, environment, lighting or effect, to a replacement source: an appearance reference, or an explicit prompt description when no reference exists. Strong reference-following models may copy an unassigned proxy look. When text carries the replacement, state the previs's limited role (camera, motion, timing and the effect's position/timing only), identify the placeholder elements and describe their final materials, scale, light and motion. Use the selected model writer's wording for that limit rather than a generic negative list.

Prompt instructions should preserve camera/event/contact intent while assigning real anatomy and materials to appearance references. Avoid contradictory demands to copy every proxy pixel and also replace its geometry. Fix a known important previs error before relying on text to correct it.

## Record a reproducible run

For each actual generation, keep one small Markdown or JSON record with:

- Date, model and service/version when available; unavailable details marked unknown.
- Exact previs filename/version, source interval and local timeline; scene/build version when relevant.
- Appearance assets, actual upload labels and assigned roles.
- Exact submitted prompt, including any manual edits after the draft.
- Selected duration, ratio, resolution, reference strength, seed and other relevant settings when exposed; record only known values.
- Output file/run identifier, synchronized comparison frames, observed defects and successful changes.
- Changes from the preceding run, interpretation, confidence and next question.

Keep videos, `.blend` files, project scripts and experiment records in the project archive. Retain only reusable methods and relevant source attribution in the public skill. Do not store credentials in an experiment record.

## Diagnose before revising

| Observation | First checks | Possible targeted action |
|---|---|---|
| Wrong finger or palm reproduced | Same time in previs; silhouette, wrist and contact | Fix the corresponding geometry/pose; do not assume more negative text is sufficient |
| Front/rear hybrid | Sheet view roles, proxy orientation, actual attachment mapping | Clarify physical surfaces; consider a simpler sheet as an experiment, not a proven universal fix |
| Constant-speed or frozen human movement | Previs interpolation, holds, requested natural motion | Adjust easing or subtle coherent hand motion, then inspect the result |
| New wallpaper or wrong product artwork | Submitted image views and screen-content instructions | Bind artwork to the correct display and remove contradictory invention instructions |
| Extra products or people | Sheet layouts, proxy identity map, shot-specific participants | State object counts and distinguish multiple views from multiple objects |
| Previs background or effect reproduced at proxy quality | Whether that element had an appearance reference; whether the prompt named it as a placeholder and described the final look | Add a background/VFX reference or a concrete placeholder replacement instruction; simplify the proxy to its timing/position role |
| Timing drift | Source versus subclip timestamps, output settings, cut order | Correct the timeline/binding first; retain the user's intended length |

Separate **observed**, **hypothesized** and **pending** findings. If several inputs changed at once, report improvement without attributing it to one change. A user-approved previs is not proof that the next generated video will succeed.

Promote a finding into shared workflow guidance when it changes a useful decision, while retaining model/version context and relevant exceptions. Preserve the original evidence record so future models can be evaluated against it.
