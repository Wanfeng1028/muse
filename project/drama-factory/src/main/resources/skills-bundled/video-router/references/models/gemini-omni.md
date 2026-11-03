# Gemini Omni: versioned, stateful video workflows

Use the curated `gemini-omni-1-1-flash` record for the documented Gemini API surface. This is a video-generation model, unlike the Astra/Opus controller profiles. Preserve the full model name and API version in every job manifest.

## Why the workflow differs

The 1.1 release introduces an iterative path: generate, keep the interaction identifier, then make a targeted edit or continuation. Starting an unrelated fresh generation discards that useful state. Draft resolution and later upscaling are also separate decisions; an upscaled output must not be described as native generation at that resolution.

1. Choose a new generation, first/last-frame operation, targeted edit, extension or upscale. Fetch the current **1.1** Interactions schema rather than applying an older Omni example.
2. Check the account, region, uploaded-video eligibility, reference input types and output profile. The curated record does not approve arbitrary reference-audio upload. Do not substitute native generated sound for requested input-audio conditioning.
3. For a new shot, separate visual action, camera behavior, sound and the intended ending. For an edit, describe a minimal change plus the parts that must remain fixed.
4. Save the interaction identifier. Where documented, use `previous_interaction_id` for the next operation. Maintain a branch ledger so alternative edits do not accidentally overwrite the accepted creative direction.
5. Use a low-resolution draft when appropriate, approve its content, then apply the supported upscale operation. Preserve the original draft as evidence; evaluate whether the enhancement changed identity or detail.
6. For extension, record both appended duration and total timeline duration. Inspect the visual seam and audio continuity. Verify the actual returned duration and output metadata, not only the requested values.

## A documented evidence conflict

During research, the versioned 1.1 announcement and 1.1 API examples described extension and first/last-frame interpolation, while an older cached limitations section still said they were unsupported. The registry favors the dated/versioned evidence, retains this conflict and requires live preflight. A successful documentation lookup is not proof that every account or intermediary has the new feature.

OpenMontage and ChatCut provide application-specific skills worth retrieving, but their aliases, continuation fields and tool availability belong to those applications. They must not be sent directly to Gemini’s API unchanged.

Primary references: [1.1 release](https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-omni-1-1-flash/), [Interactions API](https://ai.google.dev/gemini-api/docs/omni). Snapshot: 2026-10-01. Live operation validation remains mandatory.
