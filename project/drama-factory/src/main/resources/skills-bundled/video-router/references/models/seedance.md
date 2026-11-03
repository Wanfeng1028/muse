# Seedance: 2.5-first, with provider-specific input semantics

Use Seedance 2.5 for a supported combination of longer single-pass stories, multimodal references, audio conditioning, edits or continuation. Do not carry forward Seedance 2.0 limits merely because an older skill is named `seedance`.

## Select and bind

The curated direct-provider record is `seedance-2-5-byteplus`, with the documented ModelArk identifier `dreamina-seedance-2-5-260628`. The checkpoint suffix is not its public launch date. ModelArk, LAS, Scenario and ChatCut are separate execution surfaces. The last two have useful upstream skills, but require their own tools, credentials and live schemas.

1. Resolve the actual model and operation in the available provider. With Scenario, use its discovery and schema tools; with ChatCut, inspect its video submission tool. Do not send one platform’s field names to another.
2. Separate **first-frame anchoring**, **first/last-frame anchoring** and **reference conditioning**. A reference communicates identity or style; it does not necessarily specify the exact first frame.
3. Give each image, video and audio input a role. Check per-type limits, combined limits, accepted duration, upload format and accessibility. Audio-only reference conditioning is a distinct 2.5 ability, not a generic property of every Seedance wrapper.
4. Write a timed shot plan. Describe observable action, camera changes, who speaks, what sound belongs in the scene and what should remain consistent. Preserve the exact source language for spoken lines. Keep the whole plan within the selected operation’s duration ceiling.
5. For edits, specify **what changes and what is retained**. For continuation, distinguish the appended segment from total assembled length. Some provider adapters use a special duration value for edits; only use it when their live schema documents it.
6. Generate a draft, retain all request/job identifiers, then inspect action adherence, recurring identity, shot transitions, final-frame behavior and sound. Put exact captions, prices and legal copy into a deterministic finishing layer.

## Novel modes to retrieve deliberately

Search by capability rather than a brand label: `audio-only-reference`, `audio-driven-video`, `multishot`, `motion-transfer`, `video-editing`, `extend`, and `first-last-frame`. These are separate requests and may expose different limits in an intermediary platform.

The official launch describes additional creative controls such as white-model and green-screen work. Treat these as directions to investigate in the chosen provider, not permission to invent an undocumented API parameter. The router deliberately does not hardcode an unverified universal reference count or regional availability.

## Useful upstream paths

The reviewed `scenario-seedance` skill covers 2.5 and 2.0 but requires Scenario and its core skill. ChatCut’s `video-gen` skill includes a 2.5 reference, but is tied to the editor. OpenMontage’s `seedance-2-5` skill is project-bound. Older generic Seedance wrappers remain searchable without being automatically certified for 2.5.

Primary references: [2.5 launch](https://seed.bytedance.com/en/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5), [model page](https://seed.bytedance.com/en/seedance2_5), [ModelArk documentation](https://docs.byteplus.com/zh-TW/docs/modelark/seedance-2-5), [LAS surface](https://docs.byteplus.com/en/docs/byteplus_las/video_gen_enhanced). Snapshot: 2026-10-01.
