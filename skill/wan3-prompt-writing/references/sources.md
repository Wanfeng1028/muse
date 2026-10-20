# Sources and version boundaries

Based on model guide snapshots reviewed on 2026-09-05:

| Source material | Scope |
| --- | --- |
| Model Studio prompt guide | T2V/I2V guidance, explicit Wan 3.0 multi-shot, sound, and reference sections, plus older-model examples |
| Wan 2.2 `system_prompt.py` | Prompt-rewriting heuristics |
| Wan 2.2 `prompt_extend.py` | Prompt-expander dispatch and runtime code |

The guide identifies the [Model Studio documentation index](https://docs.modelstudio.console.alibabacloud.com/llms.txt). The reviewed snapshots do not establish every current vendor endpoint or capability. The installed skill does not require the original source files.

Apply Wan 3.0-labeled formulas before generic conflicting advice. In particular, the explicit multi-shot formula takes precedence over the generic table saying one clip must contain one continuous shot. Keep the source's under-45-degree orbit advice as a recommendation when an orbit is chosen, not a hard limit. Retain `Image 1`/`Video 1` per-type numbering and documented `No dialogue.` / `No background music.` controls. Do not import Wan 2.6 `character1` syntax or its character count limit, or treat Wan 2.7's `shot_type` note as a universal Wan 3.0 API rule.

From Wan 2.2, retain only intent preservation, motion-focused I2V rewriting, and compatible aesthetic detail. Do not inherit fixed 60–200/100-word budgets, its English/Chinese language switching, forced daytime or blue sky, or silent replacement of the user's requested content. The Python implementations are reference material, not dependencies to execute; no torch, DashScope, Qwen, or GPU setup is needed.

The final prompt is always written in English as a local rule; the user's language or a requested prompt language does not change it. This is separate from the Wan 2.2 language switching above. Exact words are preserved without promising perfect text rendering or word-level lip sync. Examples are illustrative, not model benchmarks.

[OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model) and [Build skills](https://learn.chatgpt.com/docs/build-skills) inform the assistant-facing structure, not Wan generation parameters.

This is a community adaptation, not an official Alibaba release. The supplied Python files retain Alibaba Wan Team copyright notices in the source archive; release licensing is for the repository maintainer to establish separately.
