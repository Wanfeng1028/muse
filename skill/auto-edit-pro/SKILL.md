---
name: auto-edit-pro
description: Use when packaging talking-head video or SRT into whole-screen motion graphics or a transparent overlay, with reproducible mixed visual styles, large components and source-aligned presenter interaction.
---

# 自动剪辑pro

Turn center-presenter talking-head content plus SRT into a reproducible, semantically directed packaging project. Accept either SRT-only transparent-overlay output or video-plus-SRT composite output. Preserve the source edit and voice. Preserve readable meaning when intentionally covering burned-in captions: briefly hand off to relevant keywords, then restore subtitle continuity.

## Required workflow for real media

1. Parse and hash the SRT, then probe and hash the video when supplied. For SRT-only overlay output, lock width, height, fps, and duration from the cues before writing Gate A documents. Gate A is analysis only.
2. Present the plan first. Do not continue until the user approves this exact job. Silence, urgency, another job's approval, or broad permission is not approval.
3. After explicit Gate A approval, build the composition inputs at Gate B. Use Remotion by default; use the HyperFrames adapter only when requested with legacy presentation/style, not mixed-style stage scenes. The cumulative A/B CLI flags record that approved-plan execution, not two separate user approval requests.
4. When Gate B is ready, automatically continue to Gate C to generate eight representative review stills and a contact sheet; do not ask for another approval between B and C. Stop after review evidence and do not render the final video. Use `--gate-b-only` only when the user explicitly wants input preparation without review stills. The legacy `--approve-gate-c` flag remains accepted but is optional.
5. After explicit Gate D approval, render and verify the actual artifact with ffprobe, full decode, eight representative frames, hashes, and a manifest. Composite MP4 requires black-frame detection; transparent MOV requires ProRes 4444, no audio track, an alpha-capable pixel format, and sampled alpha variation.

## Choose the output mode

- Default to `--output-mode composite` for first-time users. Require both video and SRT, review the real presenter and burned-in subtitles, and output `packaged.mp4`.
- Use `--output-mode overlay` when the user wants a ProRes 4444 Alpha `overlay.mov`. Video is optional, but SRT, width, height, and fps must describe the target edit exactly. Warn that SRT-only mode cannot inspect the real face position or subtitle height.

## Four gates, two user approval boundaries

```bash
# Gate A: plan only
npm run package-video -- --video INPUT.mp4 --srt INPUT.srt --out RUN --renderer remotion --captions burned-in --output-mode composite

# Gate B only: optional, when the user explicitly requests inputs only
npm run package-video -- --video INPUT.mp4 --srt INPUT.srt --out RUN --renderer remotion --captions burned-in --output-mode composite --approve-gate-a --approve-gate-b --gate-b-only

# Gate A approved: prepare B, then automatically generate C review stills; no final MP4
npm run package-video -- --video INPUT.mp4 --srt INPUT.srt --out RUN --renderer remotion --captions burned-in --output-mode composite --approve-gate-a --approve-gate-b

# Gate D: final render and artifact QA
npm run package-video -- --video INPUT.mp4 --srt INPUT.srt --out RUN --renderer remotion --captions burned-in --output-mode composite --approve-gate-a --approve-gate-b --approve-gate-d --render

# SRT-only transparent ProRes 4444 overlay
npm run package-video -- --srt INPUT.srt --out RUN --renderer remotion --captions burned-in --output-mode overlay --width 1920 --height 1080 --fps 30 --approve-gate-a --approve-gate-b --approve-gate-d --render
```

## Mixed visual styles and component examples

New whole-screen-stage plans default to `seeded-shuffle` across 71 registered styles, rather than selecting one look for the whole video:

- Original four: `balatro`, `crt-warp`, `cubes`, `hyperspeed`.
- Added directions: `shape-waves`, `ripple-distortion`, `evil-eye`, `electric-border`, `lightning`, `grid-motion`, `waves`, `metallic-paint`, `circular-carousel`, `micro-slats`, `ghost-fibers`, `acid-squares`, `light-tunnel`, `light-pillar`, `floating-lines`, `grid-scan`, `prismatic-burst`.

The catalog expansion adds **50 further executable visual directions: 20 backgrounds, 15 animations and 15 component motifs**. Read [React Bits catalog](references/react-bits-catalog.md) to choose a category or explicit IDs; `npm run list:styles -- --category components --pool` prints a reusable component-only pool. These 50 are additions to the original 21, not replacements or duplicates. All 71 participate in the default per-scene random pool.

Shuffle each pool once per bag; avoid adjacent repeats when the pool has more than one style. Short videos use only as many assignments as their meaningful beats require; never add beats just to exhaust 71 styles. Save the seed, pool and beat assignments in the storyboard; reopens and renders do not reshuffle. Saved four-style and 21-style pools retain their exact pool and assignments. Structure follows meaning; stylistic choice is independently randomized and reproducible.

Read [Visual style mixing](references/visual-style-mixing.md) for materials, motion, the beat schema, CLI controls, official references and how to admit additional styles. Existing saved storyboards without these fields keep their original appearance. `--style-mix legacy` keeps the original palette/material system for a new plan.

These effects are local original frame-driven interpretations of the linked references, not redistributed React Bits code or pixel-identical upstream components. Animation/component references contribute executable decorative geometry plus the semantic component’s palette/material; they are not full browser widgets. Interaction-driven references use a predetermined seeded frame path, not real input events. The ten meaning-driven content structures remain independent: a carousel uses abstract geometry or explicitly approved assets, and ripple/metallic effects never warp evidence text, source screenshots, captions or the presenter.

When the user explicitly asks for synthetic component examples, run `npm run demo:styles -- --out DEMO_DIR` to generate the three existing component MP4 previews covering the original four styles, stills and a gallery without real media. This fulfills a demo request only; it does not approve Gate A or Gate D for any real video. Verify the actual preview files and label them synthetic. A style-upgrade-only request does not also request presentation examples; run implementation verification without adding a showcase deliverable.

## V2 semantic structures

Select by spoken meaning, independently of the randomized visual style:

- `editorial-dual-rail`: two-sided facts, categories, or action lists.
- `thesis-and-proof`: one claim plus its reason, attribution, or proof boundary.
- `bidirectional-flow`: input/output, human/AI, or generate/review loops.
- `command-palette`: literal operations, checks, approvals, or run steps.
- `four-stage-pipeline`: three or four ordered production stages.
- `before-after-scrub`: exactly two anchored states and one comparison criterion.
- `evidence-panel`: a real approved screenshot or document plus source and interpretation.
- `metric-odometer`: one to three attributed or source-backed numbers.
- `signal-route`: three to five nodes connected by a traceable path.
- `semantic-doodle`: an integrated subject/action/outcome metaphor, never evidence.

## Non-negotiable visual rules

- Maintain one continuous source video/audio track. Do not silently recut or reorder it.
- **The whole screen is the stage / 整个屏幕都是特效和组件的舞台.** Keep the ten semantic content contracts and four-gate workflow. Palettes, materials, typography and decorative motion may change through the registered visual styles; the original aesthetics remain a legacy option.
- Default new work to whole-screen-stage composition. Position and scale graphics by meaning, gesture and composition: foreground coverage, translucent overlays, opaque full-screen, surrounding graphics with a clear person, and front/behind-subject crossings may all be mixed. There is no mandatory center exclusion, fixed side-card size cap, or forced left/right alternation.
- Deliberate partial or complete face/body coverage is valid. Make the reason, duration and reveal intentional; accidental unreadable piles remain a composition failure. Large is permitted, not compulsory. Seeded visual-style variation does not randomly change meaning, evidence, gesture or subtitle timing.
- Stage interaction must show subject, action and consequence: a spoken command can trigger assembly; an observed point, lift or sweep can summon, support or move a component. Inspect source frames before matching a real hand or body action; SRT alone is not gesture evidence.
- Real front/behind-subject interaction requires a synchronized transparent foreground person layer and correct occlusion order. Preserve appearance, source camera alignment and original background; an opaque duplicate of the source is not a cutout. Use documented local frame sequences rather than claiming automatic matting or hand tracking.
- Components remain content-fit and readable; their dimensions can extend across the canvas or beyond its edge for a motivated entry/exit. Important content lands on screen long enough to read.
- Brief intentional subtitle coverage is allowed when explicit timed keywords carry that exact meaning. After the interval, restore source subtitles or a single readable caption layer. Do not repeat the whole subtitle as decorative text or leave an uncovered meaning gap.
- Visual styles affect material and atmosphere; color or style variation alone never counts as a new semantic layout. Scope effects inside stage surfaces by default, behind readable content, rather than replacing the real source background or indiscriminately covering captions.
- If captions are burned in, use `burned-in`; avoid duplicate caption layers. An explicit stage subtitle handoff may temporarily replace covered text, then resume continuity.
- Visual beats normally last 1.6–3.2 seconds and never exceed six seconds.
- Evidence panels require an actual source asset and readable label. Never invent metrics, logos, testimonials, or product capabilities.
- Every animation is frame-driven and seek-safe. Seeded planning randomness is allowed; live `Math.random()`, timers, wall-clock animation, stateful CSS transitions and poster-only tricks are not. The same seed and frame must reproduce the same state.
- Programmatic line illustrations must be integrated into the semantic layout, use explicit SVG `fill="none"`, and communicate subject, action, and outcome. They never prove a claim.
- Videos longer than 30 seconds require at least eight semantically valid structures; the same structure may not appear more than twice consecutively.
- Old storyboards without stage configuration retain their legacy layouts. New stage scenes are not restricted to those layouts.
- A component gallery, successful build or mockup does not prove a rendered video. Synthetic preview MP4s fulfill only a requested component-demo task; real-video delivery still requires Gate D and actual artifact verification.
- Gate C screenshots are taken at 72% of each selected beat so the layout is readable after entry motion. Perform manual frame review for intentional occlusion, gesture alignment, foreground matte edges, card density, clipping, contrast, semantic fit, and subtitle/keyword continuity. Any failed item blocks Gate D.

## Presentation configuration

Read [Whole-screen stage](references/whole-screen-stage.md) when designing size, opacity, gesture keyframes, depth crossings or keyword handoffs, and [Visual style mixing](references/visual-style-mixing.md) when selecting or extending the style pool. Neither changes real-media approvals or source continuity.

`docs/superpowers/` preserves historical plans/specifications, not active stage constraints. Use this Skill and its current references for new jobs.

Read only the reference needed for the current step:

- Gate contract: [references/gates.md](references/gates.md)
- Director and evidence rules: [references/director-rules.md](references/director-rules.md)
- Ten semantic structures: [references/visual-structures.md](references/visual-structures.md)
- Motion and integrated doodles: [references/motion-and-illustration.md](references/motion-and-illustration.md)
- QA and troubleshooting: [references/qa-and-troubleshooting.md](references/qa-and-troubleshooting.md)
- Blocking visual QA: [references/visual-quality-gates.md](references/visual-quality-gates.md)
