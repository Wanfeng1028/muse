# Task routing and locked settings

Use for edits/extensions, boundary frames, or setting conflicts. Parameters describe the supplied guide's interface and stay outside the creative prompt.

| Task | Relationship | Source-guide settings |
| --- | --- | --- |
| Reference generation | Semantic guidance for a new video | Ratio/duration configurable |
| Video/audio editing | One source is the editing master | `ratio=adaptive`, `duration=-1`; source ratio and approximate duration retained |
| Strict first/last frames | `content.role=first_frame/last_frame` | `ratio=adaptive`; duration configurable |
| Semantic keyframes/storyboard | `content.role=reference_image` | Ratio/duration configurable; no strict frame matching |
| Extension before/after | New material beyond a source boundary | `ratio=adaptive`; extension duration configurable |

Editing duration may differ by approximately 0.3 seconds due to frame processing; the guide says Seedance 2.5-generated sources avoid this difference. This is output behavior, not an intent-classification threshold. MOV is recommended for edits and MOV input/output for extension continuity.

## Preserve the operation

A motion reference or blockout is not automatically an editing master. Distinguish a new generation, an existing-video change, and new material before/after it.

If an explicit edit also requests different ratio/duration, retain the edit and explain the lock outside the prompt. Suggest a separate crop/retime stage or reference regeneration as a distinct alternative. Do not silently reroute editing to regeneration. Reframing or shortening alone does not prove generative replacement is wanted.

For genuine new reference generation with confusing wording, clarify that it is a new generation using assigned reference dimensions. `Please note that this is not video editing.` is an optional local sentence, not documented special syntax or an unlock command. If metadata is unavailable, use stated intent without claiming a measured conflict.

## Video editing

Name one master. Describe original-to-target change, region/subject, count, and interval where specified. Bind replacements only to intended attributes. Preserve content outside the edit and source camera, event order, paths, and occlusions unless they are the edit target.

For moving-object replacement, explicitly remove the original and let the replacement inherit appearances, trajectory, timing, and occlusions. Do not duplicate it. Use observed source events only; do not invent timelines from incomplete previews.

A concise scope closure suffices: `Keep all other subjects, props, background, camera work, and events from @Video1 unchanged.` Adapt when the user requests removing everything except named objects. No exhaustive untouched-object inventory is required.

### Audio-only editing

Specify speaker/layer, change, language/timbre/content, and interval. Preserve other sound and visuals. Removing BGM needs no replacement asset.

For translation/replacement, preserve meaning and speaking intervals unless rewriting is requested. If lip movement adaptation is requested, include it as the allowed visual change while preserving other performance and imagery. Do not impose unchanged lips against that request or guarantee word-level synchronization.

## Extension

Use explicit boundaries, not ambiguous “forward/backward” alone:

- **After:** new material starts at the source's final state, then develops the requested action.
- **Before:** preceding action ends at the source's first state; later source events must not appear prematurely.

Preserve relevant identity/count, posture, prop state, space, camera, lighting, motion, and sound at the join. Continuing subjects remain the same instances through turns/occlusions. Extra references do not override the source boundary. Natural continuity does not guarantee pixel identity.

Infer an established “continue from the end”; clarify before/after only if ambiguous. For edit-plus-extension, provide ordered prompts: edit into a new master, then extend that master when the change must persist. State the dependency without generating or inventing an output asset ID.
