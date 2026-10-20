# Model and backend index

Snapshot: 2026-10-01. A model family is not an endpoint contract. Unknown dates receive no recency boost.

| Surface | Family guide | Release/availability | Runtime | New or distinguishing abilities |
| --- | --- | --- | --- | --- |
| `h3-max-fal` | [minimax](models/minimax.md) | 2026-08-27 (model-release) | cloud | fal post-training rather than a renamed base checkpoint; Reference mode now available; 1080P latent refinement from 768P |
| `h3-max-chatcut` | [minimax](models/minimax.md) | 2026-08-27 (underlying-model-release) | cloud | Text/keyframe H3 Max integration inside ChatCut; Narrower reference and resolution support than fal |
| `gemini-omni-1-1-flash` | [gemini-omni](models/gemini-omni.md) | 2026-08-27 (model-release) | cloud | Stateful editing through previous_interaction_id; Extension and first/last-frame interpolation; Low-resolution drafts and separate upscaling |
| `wan-3-0-prime` | [wan](models/wan.md) | 2026-08-20 (provider-availability) | cloud | 30-second single-pass output; Document or webpage as creative context; Unified multimodal reference input |
| `ltx-2-5-pro-api` | [ltx](models/ltx.md) | 2026-08-11 (model-release) | cloud | Higher-quality hosted tier with a distinct duration ceiling |
| `ltx-2-5-fast-api` | [ltx](models/ltx.md) | 2026-08-11 (model-release) | cloud | Audio-driven generation; Last-frame guidance; Model-predicted duration |
| `wan-3-0` | [wan](models/wan.md) | 2026-08-06 (provider-availability) | cloud | 30-second single-pass output; Document or webpage as creative context; Unified multimodal reference input |
| `minimax-h3-local-ref` | [minimax](models/minimax.md) | 2026-08-03 (weights-availability) | local | Local multimodal reference-conditioned audiovisual generation |
| `minimax-h3-local-fl` | [minimax](models/minimax.md) | 2026-08-03 (weights-availability) | local | Open-weight audiovisual first/last-frame generation |
| `seedance-2-5-scenario` | [seedance](models/seedance.md) | 2026-07-31 (underlying-model-release) | cloud | Live discovery and schema-driven Seedance 2.5 workflow; Adapter-specific input and edit-duration semantics |
| `seedance-2-5-chatcut` | [seedance](models/seedance.md) | 2026-07-31 (underlying-model-release) | cloud | Seedance 2.5 integration with editor job tracking; Documented 50-reference adapter ceiling |
| `seedance-2-5-byteplus` | [seedance](models/seedance.md) | 2026-07-31 (model-release) | cloud | Longer single-pass stories; Audio-only conditioning; Timestamp-guided editing and continuation; White-model and green-screen creative control |
| `minimax-h3-fal` | [minimax](models/minimax.md) | 2026-07-31 (model-release) | cloud | Mixed image, video and audio context; Joint stereo audio and video; Reference-guided performance and camera motion |
| `flux-3-video` | [flux](models/flux.md) | 2026-07-23 (early-access) | cloud | A selected draft can be enhanced rather than resampled; Multiple keyframes in one creation request; Continuation as a distinct v2v mode |
| `happyhorse-1-1-t2v` | [happyhorse](models/happyhorse.md) | 2026-06-22 (provider-availability) | cloud | Recent dedicated audiovisual creation endpoints |
| `happyhorse-1-1-r2v` | [happyhorse](models/happyhorse.md) | 2026-06-22 (provider-availability) | cloud | Recent dedicated audiovisual creation endpoints |
| `happyhorse-1-1-i2v` | [happyhorse](models/happyhorse.md) | 2026-06-22 (provider-availability) | cloud | Recent dedicated audiovisual creation endpoints |
| `happyhorse-1-0-edit` | [happyhorse](models/happyhorse.md) | 2026-04-27 (provider-availability) | cloud | Dedicated generative edit endpoint |
| `kling-3-0` | [kling](models/kling.md) | 2026-02-05 (model-release) | cloud | Explicit multi-shot storyboarding and reusable elements |
| `wan-2-7-videoedit` | [wan](models/wan.md) | Unverified (unknown) | cloud | Dedicated effect and camera-motion replication |
| `ltx-2-5-python-exr` | [ltx](models/ltx.md) | Unverified (unknown) | local | Native EXR preservation uses the Python pipeline; no ComfyUI native EXR flow was documented. |
| `ltx-2-5-local-restore` | [ltx](models/ltx.md) | Unverified (unknown) | local | Use the TiledFusion Upscale workflow and the task-specific adapters. |
| `ltx-2-5-local-inout` | [ltx](models/ltx.md) | Unverified (unknown) | local | In/outpainting uses a task-specific IC-LoRA and mask, not the plain generation pipeline. |
| `ltx-2-5-local` | [ltx](models/ltx.md) | Unverified (unknown) | local | Connected multishot generation; New diffusion decoder and duration predictor; Specialized LoRA pipelines |
| `ltx-2-3-pro-api` | [ltx](models/ltx.md) | Unverified (unknown) | cloud | Keep this older route when a new model lacks retake or extension |
| `ltx-2-3-local-foley` | [ltx](models/ltx.md) | Unverified (unknown) | local | Validated on 2.3, not 2.5; use a muted input clip and the dedicated Foley adapter. |
| `ltx-2-3-local-dubit` | [ltx](models/ltx.md) | Unverified (unknown) | local | The official guide validates this on 2.3; 2.5 support remains in development. |
| `kling-3-0-turbo-standard` | [kling](models/kling.md) | Unverified (unknown) | cloud | Faster 720P creation tier |
| `h3-max-turbo-fal` | [minimax](models/minimax.md) | Unverified (unknown) | cloud | Faster draft-oriented post-trained variant |

Use `python3 scripts/avs.py show <id>` for complete constraints, endpoint identifiers, evidence and explicit unsupported modes. Provider schemas must be rechecked before execution.
