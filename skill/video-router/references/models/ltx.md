# LTX: route by version, tier and runtime

LTX 2.5 API, LTX 2.5 local checkpoints and older LTX editing APIs are different contracts. Start from the registry record, then verify the live operation. This original playbook does not vendor an upstream skill.

## Selection rules

| Need | Route |
| --- | --- |
| New hosted generation or first/last frames | LTX 2.5 Fast or Pro, subject to the joint output profile. |
| Twenty-second hosted clip | Check Fast’s supported low-frame-rate 720p/1080p profiles; do not infer Pro compatibility. |
| Retake or extend | LTX 2.5’s checked API does not support these. Consider the verified older LTX 2.3 Pro route only when the user has not required 2.5. |
| Local multishot or LoRA work | Inspect LTX 2.5’s model card, exact checkpoint and implementation. API limits do not define local inference. |

## Production workflow

1. Classify text-to-video, image-to-video, input-audio-driven video, connected multishot or editing. Native generated audio is not the same as accepting an audio input. Retake is not equivalent to full regeneration.
2. Choose the **coupled** duration/resolution/frame-rate profile. For the hosted 2.5 API, Fast and Pro have different ceilings; a valid resolution and valid duration separately do not establish a valid pair. For audio-driven generation, read that operation’s audio-duration rules instead of applying the text/image table blindly.
3. Write the scene in chronological, observable language. For a continuous shot, give one coherent action and camera path. For supported local multishot, name each cut, reuse character names and maintain a continuity ledger. Treat community screenplay formats as prompting suggestions, not proof of a provider capability.
4. For local inference, validate width/height alignment and frame count against the selected implementation. The curated model-card constraints include dimensions divisible by 32 and frame count congruent to one modulo eight. Keep dev/distilled schedules, encoders, decoders and LoRAs compatible; do not combine unrelated defaults.
5. Generate one representative draft. Preserve source image/audio, prompt, model revision, scheduler, seed, output profile and job or workflow identifiers. Measure actual output duration and frame rate.
6. Review action completion, identity across cuts, lip movement, audio seams and the ending state. A prompt-only skill cannot establish that a local workflow or hosted job rendered successfully.

## Fallbacks

An explicit `LTX 2.5 + retake` request should return **no compatible route**, not silently choose 2.3. When the model is not constrained, offer the older verified editing surface and explain why. Local weights are an option only after hardware, storage, licensing and checkpoint compatibility checks; no laptop-memory guarantee is made here.

Primary references: [LTX 2.5 API matrix](https://docs.ltx.io/models/ltx-2-5), [all API models](https://docs.ltx.io/models), [API release](https://docs.ltx.io/api-changelog/2026/8/11), [2.5 model card](https://huggingface.co/Lightricks/LTX-2.5), [Diffusers variant](https://huggingface.co/Lightricks/LTX-2.5-Diffusers). Snapshot: 2026-10-01; local weight-release date is intentionally not inferred from the API release.

## Specialized generation and post-production paths

The current 2.5 API documentation also explicitly describes native connected multishot. Its text/image duration table does **not** apply to audio-driven output length, which follows the source audio. The router keeps operation limits separate. For automatic duration, the API requires an explicit `duration: null`; leaving out the field is not the same request, and last-frame image anchoring excludes auto-duration. See [the current API contract](https://docs.ltx.io/models/ltx-2-5).

| Task | Version-specific route | Boundary |
| --- | --- | --- |
| Masked replacement or expanding the canvas | `ltx-2-5-local-inout` | Use the documented in/outpainting IC-LoRA, mask configuration and two-stage stack. |
| Native EXR/HDR preservation | `ltx-2-5-python-exr` | Python pipeline, not an assumed ComfyUI node; do not confuse it with an SDR-to-HDR adapter. |
| Generative cleanup and detail reconstruction | `ltx-2-5-local-restore` | Rebuilt details and colors are plausible synthesis, not recovered ground truth. |
| Dialogue replacement | `ltx-2-3-local-dubit` | Official compatibility remains 2.3; 2.5 support is under development. |
| Foley sound effects for muted footage | `ltx-2-3-local-foley` | Uses the 2.3 Foley adapter; generated sound is not a claim of 2.5 compatibility. |

Route with `--task inpaint`, `outpaint`, `exr-hdr`, `restore`, `dub` or `foley`, adding the exact model/version and local tool inventory. These routes require specialized checkpoints and adapters; downloading the base weights alone does not establish their availability. Input and output rights, speaker consent and actual audiovisual review remain mandatory.

Primary workflow references: [in/outpainting](https://docs.ltx.io/open-source-model/feature-guides/editing-effects/in-outpainting), [EXR/HDR](https://docs.ltx.io/open-source-model/usage-guides/working-with-exr-hdr), [restore/refine](https://docs.ltx.io/open-source-model/vfx-post-production/refine-and-restore), [Dub-It compatibility](https://docs.ltx.io/open-source-model/feature-guides/audio/dub-it-beta), [Foley compatibility](https://docs.ltx.io/open-source-model/feature-guides/audio/video-to-audio-foley).
