# Scene Model Adapter Rules

The scene contract is model-neutral. Adapters translate it into a provider's prompt and execution settings without changing the scene facts.

## Separation

- Prompt text contains visible scene facts, spatial relationships, materials, light behavior, atmosphere, scale, and the requested medium.
- Reference mapping contains real files, upload order, role, preserve, and exclude rules.
- Execution settings contain model ID, aspect ratio, size, quality, seed, edit mode, and other provider-specific options only when verified for that provider.
- Negative or avoid text is optional. Use positive constraints first; include an avoid block only if the target entry supports it.
- Never write `8K`, `120fps`, seed values, or provider-specific fields in the scene prose as evidence that a setting was applied.

## Adapter result

Each adapter returns:

```json
{
  "model_family": "...",
  "prompt": "...",
  "avoid": "...",
  "references": [],
  "execution_settings": {},
  "unsupported": [],
  "prompt_status": "READY_TO_SUBMIT",
  "visual_status": "UNVERIFIED"
}
```

If a requested model capability is unknown, keep it in `unsupported` and lower `prompt_status` to `BLOCKED` or `DRAFT`; do not silently substitute a different model. The core skill never calls a paid endpoint by itself.

## Provider-neutral selection

Use `model_family` values such as `gpt-image`, `flux-like`, `sdxl-like`, `midjourney-like`, or `model-neutral` only as routing labels. A concrete model ID belongs in execution settings after the host confirms the current entry point. Keep the same scene contract when comparing models; change one experimental axis at a time and record the result outside the contract's design facts.
