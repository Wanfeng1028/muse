# HappyHorse: creation and editing have different versions

The curated Model Studio surfaces use **1.1 for creation** and **1.0 for the documented video-edit operation**. Do not construct a `happyhorse-1.1-video-edit` identifier by analogy. The dates in the registry are provider-availability entries, not a claim that all regions launched simultaneously.

## Select an exact route

| Task | Model ID |
| --- | --- |
| Text-to-video | `happyhorse-1.1-t2v` |
| Image-to-video | `happyhorse-1.1-i2v` |
| Image-reference-conditioned video | `happyhorse-1.1-r2v` |
| Generative edit | `happyhorse-1.0-video-edit` |

1. Resolve the operation and current regional account availability. The creation models are separately addressed; a generic HappyHorse wrapper must expose the chosen version and mode before it can execute this plan.
2. Validate duration, output resolution, input format and the applicable reference schema. The approved 1.1 reference record documents image references. It does not approve arbitrary audio/video references merely because the model generates sound.
3. For I2V, treat the input as an opening state. For R2V, specify what should carry over from each reference rather than promising exact frame anchoring.
4. For an edit, identify retained identity, geometry, camera and timing as well as the requested change. Use the explicit edit endpoint rather than reprompting text-to-video and calling the result an edit.
5. Generate a bounded draft, preserve the exact model ID and job details, then inspect visual continuity, action adherence, any speech, and output metadata.
6. Finish exact copy, captions and branding separately when needed. Do not publish automatically as part of generation.

Inference.sh has a HappyHorse skill worth discovering, but its own exposed model version must be checked. A catalog entry for that integration does not certify parity with Model Studio 1.1.

Primary references: [generation/editing matrix](https://www.alibabacloud.com/help/en/model-studio/video-generate-edit-model), [provider release ledger](https://www.alibabacloud.com/help/en/model-studio/newly-released-models). Snapshot: 2026-10-01. The ledger distinguishes June 22 and June 26 regional availability for 1.1 creation.
