# Controller profiles and host discovery

A request has several independent coordinates: **host → controller → task → generation model or renderer → provider → skill adapter**. Do not collapse them into one model name.

| Coordinate | Examples | What it changes |
| --- | --- | --- |
| Host | Claude Code, Codex, generic file-reading agent | Skill discovery path and tool permissions. |
| Controller | Claude Opus 5.5, GPT-6 Astra | Planning/coding workflow preferences, not video endpoint support. |
| Renderer | Remotion, Hyperframes, Canvas, Manim, Blender | Editable project format and deterministic rendering. |
| Video model surface | LTX 2.5 Fast API, H3 Max on fal | Supported operations and numeric limits. |
| Adapter | Scenario MCP, ChatCut, ComfyUI | Credentials, tool schema, platform-specific restrictions. |

## Claude Code / Opus 5.5

Start with `CLAUDE.md` when working inside this repository, or install `video-router` into the host’s skill directory. For motion, route to an engine and inspect its upstream skill. The `brag-slim` workflow is designed around Opus 5.5; `brag` retains a fuller Hyperframes path and a separate narration option. Inspect the pinned upstream instructions rather than assuming every controller should follow the same model-name branch.

## Codex / GPT-6 Astra

Start with `AGENTS.md` or install the same portable router. Accepted aliases include `astra`, `gpt-6-astra`, `gpt6stra` and `gpt-6stra`. They resolve only as **controller profiles**. A request such as `--agent astra --task motion --engine remotion` routes to code-authored animation; a footage request instead selects a separate generation model. No measured superiority between controllers is claimed.

## Other agents

Any agent that can read files can navigate the Markdown and JSON. Python 3.10+ enables offline routing and BM25 retrieval. The standalone router contains its own catalog and references; it does not depend on a sibling repository directory. `llms.txt` is a convenience entry point, not a universal automatic-discovery standard. Host-specific skill auto-loading is governed by that host’s documentation and permissions.

Use progressive disclosure: read the router description, produce a structured request, retrieve the chosen guide, inspect a specific upstream skill, then fetch the current provider schema. Do not load all 193 upstream entries into every task or install them indiscriminately.

Primary references: [Agent Skills specification](https://agentskills.io/specification), [Claude Code skills](https://code.claude.com/docs/en/skills), [OpenAI skill documentation](https://developers.openai.com/codex/skills), [Opus model page](https://www.anthropic.com/claude/opus), [Astra announcement](https://openai.com/index/gpt-6-astra/).
