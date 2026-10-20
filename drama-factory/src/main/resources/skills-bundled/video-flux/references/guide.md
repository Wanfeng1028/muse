# FLUX.3 Video: draft, select, enhance

Use `flux-3-video` for the documented BFL video surface. Do not confuse this with an older FLUX image model or infer local video weights from another product’s name. Its registry date is the announced early-access release, not universal account availability.

## Choose the operation

The documented creation modes include text-to-video, image/keyframe-conditioned video and video continuation. Mode values are not separate model IDs. Dedicated editing and upscaling tools are separate contracts and are not silently added to the creation endpoint’s capabilities.

1. Read the live model and mode schema. Inventory keyframes separately from loose image references, and establish whether the request is a new shot or continuation.
2. Validate the generation profile and keyframe count. The curated surface records a 5–20 second creation range, while continuation has its own appended-duration range. Do not use total assembled duration as the generation argument.
3. Plan a draft pass with the intended action, framing, audio and ending. Keep exact typography out of the stochastic layer when correctness matters.
4. Generate bounded candidates within the approved budget, then explicitly select one draft. Retain its provider handle and provenance.
5. Use the documented **enhancement** path for that selected draft when appropriate. Do not assume this is equivalent to calling the generation endpoint again with a reused seed. Compare the enhanced result with the accepted draft for semantic changes.
6. Probe the delivered file and apply the requested final delivery transform. The documented full-HD canvas can be 1920×1088; do not report exact 1920×1080 until the actual export has been checked or conformed.

## Retrieval and portability

Search the catalog for `draft-enhance`, `first-last-frame` or `extend`, not simply `flux`. OpenMontage’s `bfl-api` skill is an application integration, not a standalone guarantee of a BFL account or every video operation. Use the original model playbook when no compatible upstream runtime is installed.

Verify account access, license, output-resolution provenance and current cost before submission. This repository does not execute BFL calls or certify their output quality.

Primary references: [FLUX.3 announcement](https://bfl.ai/blog/flux-3), [video modes and enhancement](https://help.bfl.ai/articles/7342522296-what-is-flux-3). Snapshot: 2026-10-01.
