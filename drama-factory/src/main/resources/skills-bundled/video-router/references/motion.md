# Procedural motion: the controller writes a renderable project

Use this path when the brief calls for exact typography, UI, charts, logos, editable animation, repeatable variants or code-drawn scenes. Opus 5.5 and GPT-6 Astra are **controllers** here. Remotion, Hyperframes, Canvas, Manim and Blender are **renderers/toolchains**, not video models.

| Situation | First route to inspect |
| --- | --- |
| Existing React UI; many personalized variants | Remotion and its maintainer-authored creation/render skills. |
| HTML/GSAP scenes, launch films and timelines | Hyperframes and its motion/animation skills. |
| Lean code-drawn film or kinetic typography | Canvas/SVG/FFmpeg; `brag-slim` is specifically designed around Opus 5.5. |
| Equations and mathematically precise transformations | Manim. |
| Product geometry, physical lighting, camera or render passes | Blender; an MCP bridge is a separate integration. |
| Photoreal footage plus exact branded copy | Hybrid: generate the footage, then composite deterministic typography/UI. |

## Controller-aware, not controller-locked

For Opus 5.5, the upstream `brag` workflow can hand off to `brag-slim`; full or narrated workflows have different requirements. This is an upstream routing design, not an independent quality benchmark. For Astra, use the same renderer/task decision and preserve the project’s existing stack. Do not rename Astra as a video endpoint or force it into an Opus-only invocation branch.

1. Write the brief as a scene ledger: start/end frame, narrative purpose, exact copy, asset roles, motion intent, audio cues and acceptance criteria. Reuse actual approved UI and brand assets instead of inventing a look-alike interface.
2. Choose the renderer based on source material, installed tools and deliverable. Avoid changing a working React pipeline merely because a new HTML skill is trending. Review the engine license separately from the skill’s license.
3. Make rendering deterministic: compute scene state from absolute frame/time, seed randomness, avoid wall-clock timers, pin fonts/dependencies and wait for asset/font readiness. The same frame should render identically out of order.
4. Establish visual hierarchy before movement. Plan anticipation, easing, stagger, holds and exits; animate a purposeful change rather than moving every element continuously. Exact data and on-screen claims need source verification before animation.
5. Render a small proof at the final aspect ratio, then inspect contact sheets **and playback**. Check text fit, safe areas, contrast, clipping, stroke thickness, motion pacing, dropped frames and readable hold times. A screenshot proves layout, not animation quality.
6. Synchronize audio against the same timeline. Record source rights, trim/fade intentionally and verify the encoded audio/video durations. Speech captions need word/phrase timing rather than arbitrary equal subdivisions.
7. Render the full result, probe the encoded file and return the editable project plus output, dependency lock, asset manifest and QA notes. Preserve intermediate frames and approved drafts where practical.

## Retrieval tips

Search by craft (`kinetic typography`, `chart animation`, `audiogram`, `shader`, `lower thirds`, `manim`) after choosing a renderer. Install only the needed upstream pack. iart’s umbrella repository is a directory of packs, not itself a single executable skill. ChatCut motion-graphic JSX skills require ChatCut’s editor tools and are not automatically portable React compositions.

Sources: the pinned [skill catalog](catalog.md) links the reviewed upstream paths; [controller profiles](agents.md) document host/controller separation. Rendering quality and all upstream installations remain unbenchmarked by this repository.
