# MiniMax: H3 is a family, not one interchangeable endpoint

Use this guide for H3, H3 Max and H3 Max Turbo. Use the registry’s **exact model/backend ID**, not the family name, as the execution contract. This is an original routing playbook; upstream skills remain separately licensed.

## Choose the surface

| Requirement | Start here | Do not assume |
| --- | --- | --- |
| Base H3 through fal | `minimax-h3-fal` | Hosted 2K output means native 2K local weights. |
| Local first/last-frame generation | `minimax-h3-local-fl` | The Ref2VA checkpoint accepts the same inputs. |
| Local mixed references | `minimax-h3-local-ref` | Open weights include every hosted refinement stage. |
| H3 Max through fal | `h3-max-fal` | A different platform exposes all fal modes. |
| Turbo drafts | `h3-max-turbo-fal` | Max’s reference endpoint also exists for Turbo. |

## Execute the decision

1. Inventory the first/last frame separately from loose references. Give every reference a stable label and a role: identity, camera, action, sound or environment. Count each type and the combined total.
2. Read the selected endpoint’s current schema. Base H3 requires visual context alongside reference audio on the documented reference surface. The checked H3 Max fal reference schema permits audio-only references. Never copy constraints between them.
3. For **base H3 prompt writing**, read the official `h3-prompt-writing` skill and its base or reference guide. Base modes separate the audiovisual timeline, overall soundscape and non-diegetic music. Reference mode additionally defines subjects and what each reference should preserve. Do not use generic scene prose as a replacement for a required structured prompt.
4. For **H3 Max**, use its endpoint-specific prompt and expansion fields. A base-model prompt skill may provide creative guidance, but is not evidence of Max API compatibility. Record whether expansion was enabled.
5. Confirm resolution provenance. H3 Max’s documented 1080P mode uses latent refinement from 768P. Retain seed, endpoint, expanded prompt, job ID and resulting media metadata. Reconcile an uncertain job before submitting a duplicate paid request.
6. Review character/prop identity, camera continuity, dialogue timing and the requested final frame. Generate exact legal copy and branding as a deterministic overlay when correctness is mandatory.

## Skill selection and failure paths

The official H3 prompt skill is portable. The eight style-production workflows in MiniMax’s H3 repository require **MiniMax Hub**. Their availability does not imply that Claude Code has those tools. ChatCut’s H3 Max adapter is a separate, narrower contract; a capability documented on fal must not be inherited by that adapter. Community direct-API guides with conflicting limits remain review-required in this catalog.

For local generation, lock the checkpoint, tokenizer/encoder, decoder, quantization format and node implementation together. Check the model license and real hardware requirements. This library does not certify a minimum VRAM size or redistribute weights.

Primary references: [H3 model card](https://huggingface.co/MiniMaxAI/MiniMax-H3), [H3 hosted surface](https://fal.ai/minimax-h3), [H3 Max reference schema](https://fal.ai/models/minimax/h3-max/reference-to-video/api), [H3 Max release](https://blog.fal.ai/introducing-h3-max-by-fal/). Recheck these before execution; snapshot: 2026-10-01.
