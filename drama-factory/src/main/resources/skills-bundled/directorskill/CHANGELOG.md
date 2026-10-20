# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.0] - 2026-08-27

An audit release. A full adversarial audit of the package found the content layer sound and the
delivery layer not: the entry point's frontmatter was not valid YAML, `SKILL.md` contradicted the
files it named as owners in four places, an entire current capability class was missing, and the
behaviour contract had never been executed. Everything below is the repair.

### Fixed

- **`SKILL.md` frontmatter was not parseable YAML.** An unquoted scalar containing `": "` made
  `yaml.safe_load` fail, so any strict parser dropped the skill or read an empty description. It is
  now a folded (`>-`) block. The `description` was also 1327 characters against the 1024-character
  spec cap — a regression introduced in 2.0.0 — and is now 1022. CI checks both from now on.
- **Four contradictions between `SKILL.md` and its own owner files.** The intake block emitted
  `must_avoid: modern objects`, the exact category hard rule 9 calls unresolvable; the S4 skeleton
  emitted an `[emotion]` slot against hard rule 5; the self-check stated the two-size-step cut rule
  unconditionally where four other files state it conditionally; and Mode J chaining contradicted
  the response-size ceiling thirteen lines below it.
- **The lighting invariant was specified in two opposite coordinate systems.** The director's book
  template required world space; `lighting-and-color.md` shipped a camera-space template slot and a
  camera-space worked example that, pasted into a reverse, flips the key. One system now, world
  space, with the camera-relative wording derived per shot-plan row.
- **The shot-size ladder had two definitions.** `prompt-lexicon.md` carried an eight-step table that
  the two-size-step rule cannot be counted on. `cinematic-language.md` now declares ownership of the
  six rungs and everything else cites it.
- **F2 had no QC gate row.** The package's own flagship symptom — the slideshow — was the one code
  of nineteen that Gate 2 could not score, so a static clip was miscoded F4/F5 and repaired down the
  wrong branch.
- **The flagship identity string violated the recipe it demonstrates.** `ID_COURIER` carried zero
  face-structure facts and no hair spec, so an agent imitating it produced strings with no face
  geometry — the definition of F1. Rewritten to the recipe, synchronised byte-identically across all
  six copies, and `continuity-bible.md` is now loaded at the step where the string is written.
- **An absolute dBFS figure that was about 20 dB hot** in `sound-and-dialogue.md`, in a file whose
  own convention is dB relative to dialogue.
- **Two craft errors**: the occlusion geometry on the orbit arc in `blocking-and-staging.md`, and a
  proportional-trim rule in `editing-and-assembly.md` that disagreed with its own fixed-frame rule
  for exactly the slow gestures this package recommends most.
- Stale doc claims: the reference count, the next free F-code, the "stays lean" comparison row, and
  the `LICENSE` file, which appended a non-MIT restriction while the frontmatter declared MIT.

### Added

- **Video-to-video as the fifth control surface.** Restyle, relight, regrade, reframe and
  performance transfer over existing footage were absent from the capability matrices, the prompt
  shapes and the repair ladder, though the description advertised working from existing video. It is
  now a matrix row in both adapter files and rung **L4.5** on the cost ladder — one generation, keeps
  the take — resolving F12, F16, F17 and framing-only F9, which previously jumped to rebuilding the
  keyframe.
- **Cross-cutting and time compression.** The cut-motivation taxonomy had no entry for juxtaposing
  two lines of action, and nothing said why a run of shots reads as time passing rather than as a
  list. Both are now sections in `editing-and-assembly.md`, with a `Thread` column in the beat sheet
  so parallel action can be planned upstream.
- **Two-hander lighting** in `lighting-and-color.md`, which was written end to end for a single
  subject while two-hander dialogue is the package's default drama coverage.
- **Sound perspective**: a level/filter/reverb table across the four space cases, and a `Space`
  column in the sound plan, so a bed no longer sits at one perspective from wide to close-up.
- **The axis of action for three or more people**, which was defined only for pairs.
- **Per-family blocks in `image-model-adapters.md`**, which had none while the video side had twelve.
- **`evals/run.md`** — grader prompt, pass criteria, ship bar — and a CI job that validates
  `evals.json` and the `SKILL.md` frontmatter. The suite had never been executed; it now has a
  procedure and a build that fails when it drifts.
- **Capability snapshot dates** in both adapter files. Nine "as of writing" hedges carried no date
  anywhere, so nothing said what was due for recheck.
- **Routing that was missing**: a staging/blocking row, `example_comparisons.md` (the package's one
  orphan file), `production-workflow.md` on the shot-list row, `continuity-bible.md` at Step 5, and
  `qc-checklist.md` on the keyframe row it gates.
- **A defined fallback for unnamed directors.** Naming a director with no module was undefined
  behaviour; the skill now says so, names the nearest module and the axis it differs on, and builds
  an ad-hoc lens rather than substituting silently.
- **Style-lens application at Steps 7, 8 and 10.** The lens was declared at Step 4 and then never
  mentioned again at the steps it is supposed to override — including Step 8, which Step 4 calls the
  one that matters most.
- **Scoped reads.** The partial-read instruction that existed only for `failure-modes.md` now covers
  the other three large index-plus-sections references.
- **27 eval cases (30 → 57).** All 20 director lenses now covered (12 had none), prompt shapes S3 and
  S4 forced, over-production tested, the no-artifact repair path tested against the guardrail it was
  previously written to violate, and every output mode above one case.

## [2.0.0] - 2026-07-27

A depth release. v1.x knew the vocabulary of directing; v2 knows the craft behind it — lens choice, lighting ratios, continuity geometry, staging, sound, editing, and the operational reality of running a generation queue. The pipeline grew from 10 steps to 13, output modes from 6 to 10, references from 4 to 13, director lenses from 14 to 20, and `SKILL.md` gained an explicit routing table so depth loads on demand instead of all at once.

### Added

- `references/blocking-and-staging.md` — staging geometry library with plan-view diagrams, proxemics, power blocking, entrances and exits, eyeline geometry, a compact blocking notation the skill can emit in shot lists, and an honest reliability grading of what AI video models can and cannot render.
- `references/lighting-and-color.md` — key/fill/back setups, lighting ratios with emotional reads, key direction, hard/soft quality and falloff, a practicals catalogue by era, a time-of-day table, contrast schemes, palette systems, color scripting, source-based color naming for prompts, grading language, and lighting continuity across generated shots.
- `references/sound-and-dialogue.md` — the five-layer sound brief, diegetic boundaries, sound-led pacing, silence engineering, dialogue that actually generates (one speaker per clip, syllable-to-duration guidance, shot-reverse workarounds), voice-over, and a BPM-to-cut-length music brief.
- `references/editing-and-assembly.md` — pacing math from target duration to shot count, cut motivation taxonomy, transition engineering for separately generated clips (match cuts built from paired last/first frames, dissolves as honest repairs, cutaways as continuity patches), trim handles, rhythm patterns, and anti-slideshow rules at the edit stage.
- `references/genre-playbooks.md` — per-genre directorial defaults across 19 genres with a fixed field set, a cross-genre comparison table, and a tone-dial section showing how to move a scene between registers by changing three variables.
- `references/prompt-lexicon.md` — verb banks by body system and environment, a replacement table converting intention words into observable behavior, disambiguated camera vocabulary, material and texture language, prompt slot ordering per prompt shape, a negative-prompt library organized by failure class, token economy rules, and an EN↔中文 craft-term table.
- `references/failure-modes.md` — a coded diagnosis manual (F1–F18) with symptom, ranked root causes, cost-ordered fixes and before/after prompt pairs for each; a 60-second triage tree; the cost ladder; the three-strike rule; a root-cause interview; and an honest list of irreducible model failures with directorial workarounds.
- `references/image-model-adapters.md` — keyframe generation as the real control point: control-surface matrix for image models, nine-slot keyframe anatomy, the character consistency playbook (identity strings, character sheets, reference binding, seed locking, inpaint repair), the location plate technique, reliable first/last-frame pair construction, and a pre-video QC gate.
- `references/production-workflow.md` — the operating loop, the keyframe approval gate, a shot difficulty rubric with retry budgeting, sequencing strategy, versioning and review formats, the handoff package, and where the time actually goes.
- `references/product-and-macro.md` — product, packshot, cosmetics, food, and macro work: the light-moves-not-the-camera principle, lighting by material class (specular, transparent, matte), macro depth-of-field reality, brand hue and logo fidelity as a discrete constraint on a continuous generator, the shot grammar of a spot, the 6s and 15s vertical structures, and an honest shoot-instead-of-generate decision table.
- `assets/beat-sheet-template.md` (Mode B), `assets/director-book-template.md` (Mode C), `assets/sound-plan-template.md` (Mode H), `assets/edit-timeline-template.md` (Mode I) — each with a filled worked example.
- Six director-style overlays, filling real gaps in the library (now 20 total):
  - `15_zhang_yimou.md` — saturated single-color fields, mass choreography as image, folk-ritual iconography.
  - `16_hou_hsiao_hsien.md` — static distant long take, doorway depth, real-time duration, ellipsis over exposition.
  - `17_park_chan_wook.md` — baroque revenge, improbable camera geometry, ironic beauty over cruelty.
  - `18_malick.md` — available light, wide wandering handheld at magic hour, whispered voice-over, associative montage.
  - `19_michael_mann.md` — urban night as a cold luminous field, professional competence, loneliness as architecture.
  - `20_coen_brothers.md` — deadpan geometric dark comedy, closing the comedy gap none of the first 14 covered.
- Three new pipeline steps: 1 Intake and scope, 11 Sound and dialogue plan, 12 Edit and assembly plan.
- Four new output modes: B Beat Sheet, C Director's Book, H Sound & Dialogue Plan, I Edit & Assembly Plan.
- A routing table in `SKILL.md` mapping request type to output mode to the exact files to load, so `SKILL.md` stays lean and depth is pulled in on demand.
- A hard-rules block and a self-check block in `SKILL.md`.
- Prompt shapes S1–S4 (motion-only, full-description, keyframe-pair, multi-shot timestamped) and a capability-first routing model, so unfamiliar tools are handled by control surface rather than by guesswork.
- The motion-budget model: subject motion plus camera motion plus environmental motion plus duration is a finite budget, and exceeding it is what produces warping.
- A `Response size` table and a proportionality hard rule in `SKILL.md`, plus an explicit instruction never to print the intake schema back at the user — over-production was the most common failure in dry runs.
- Non-narrative handling: Steps 2 and 3 now state that commercial, product, corporate, fashion, music-video, and trailer briefs replace the dramatic-core block with the genre playbook's engine and audience contract, and replace pressure-delta beats with the format's structural blocks.
- A single-owner map in `CONTRIBUTING.md` for the eight concepts two files could each plausibly claim, plus reserved id prefixes (`S` prompt shapes, `F` failure codes, `P`/`G`/`Q` QC gates, `SH` shot ids, `L` cost-ladder rungs) so an id in a note is never ambiguous.

### Fixed

Findings from an adversarial verification pass and three live dry runs of the finished skill:

- **F19 — object permanence break.** A prop that *disappears* had no code anywhere; the taxonomy only covered entities appearing. The triage tree also returned exactly one code and hid every additional failure in a clip that had several — it now collects every code before proposing anything, and there is a multi-failure repair format with a shared-root line.
- **Negative prompts named a category the skill's own manual identifies as unresolvable.** `NEG_BASE` shipped "no modern objects" — the documented mechanism behind F8 — in every template and worked example. Negatives now name instances everywhere.
- **Two files defined the identity string with incompatible word budgets**, and the file Step 8 routes to taught a length the owning file declares non-reproducible. `references/continuity-bible.md` is now the sole owner.
- **The 30° rule was restated wrongly** in the adapters file ("one size step *or* 30°" instead of "30°, or two size steps on the same axis").
- **Lighting ratios were quoted in two conventions**, key-to-fill in one file and lit-side-to-shadow-side in another, which is a factor-of-difference error on the same shot.
- **Clip durations, generation handles, retry budgets, and sound levels each disagreed across two or three files.** Each now has one owner and the rest quote it.
- **A one-symptom repair loaded 670 lines** to answer a one-line question, and Mode J was modelled as terminal when in practice it chains to F, I, and G.
- **The root-cause interview contradicted the entry point** — `SKILL.md` forbids interrogating the user while `references/failure-modes.md` prescribed a six-question questionnaire. It is now a list of what to infer, in descending order of yield.
- Craft errors caught in review: an inverted lookroom rule, a geometrically wrong 180° diagram whose crossing camera sat on the legal side, backwards eyeline logic in shot-reverse-shot, a depth-of-field claim with no hyperfocal caveat, and wrong sensor crop factors.
- Unhedged vendor claims — exact durations, parameter names, and capability assertions stated as fact — rewritten as capability classes with a staleness warning.

### Changed

- **Breaking:** pipeline renumbered from 10 steps to 13, and output modes renumbered from A–F to A–J. Anything referencing the old numbers needs updating.
- **Breaking:** tool adapter selection now precedes prompt construction (Step 9 before Step 10). In v1 the pipeline wrote prompts at Step 8 and only then consulted the adapter at Step 9, which was backwards.
- `SKILL.md` — rewritten around routing and progressive disclosure; frontmatter description broadened to cover sound, editing, genre, image models, and the six new lenses; intake schema gained genre, more tools, and more aspect ratios.
- `references/cinematic-language.md` — substantially expanded: lens and focal-length psychology, focus as direction, camera height, continuity geometry (axis of action, the 30° rule, screen direction, eyeline match) with AI-specific encoding notes, coverage patterns, aspect ratio and format including a dedicated vertical 9:16 section, and motion rendition.
- `references/ai-video-tool-adapters.md` — restructured around a control-surface matrix and four prompt shapes; adapters added for Sora-class, Hailuo/MiniMax, Pika, Vidu, Midjourney Video, and open-source/ComfyUI-class models; all model-specific claims hedged as capability classes.
- `references/continuity-bible.md` — schemas expanded (identity strings, wardrobe state, injury and dirt progression, light direction, screen direction, seeds, reference asset IDs), plus prop and wardrobe schemas, an asset naming grammar, a seed registry, a state-change ledger, and a fully filled six-shot worked example.
- `assets/shot-plan-template.md` — added a field dictionary with good/bad examples per column, lens and light-direction columns, a risk column, a compact variant, and a filled example.
- `assets/keyframe-prompt-template.md` and `assets/video-prompt-template.md` — slot dictionaries, more templates (character sheet, location plate, continuation, dialogue shot), filled examples, and per-prompt self-checks.
- `assets/qc-checklist.md` — restructured into three gates (pre-generation, post-generation, sequence), converted to a scored rubric with a pass threshold and a blocker list, and cross-referenced to failure codes F1–F18.
- All 14 existing director-style modules retrofitted to the v2 structure: a bilingual one-line lens, a `反例 / What this lens is NOT` section naming the adjacent styles each gets confused with and the mechanical difference, a machine-readable `风格参数` YAML override block, three prompt templates, and a worked example. Every module now directs the same control scene so the twenty can be read side by side.
- `evals/evals.json` — expanded from 7 cases to a broader suite covering intake with minimal information, motion-budget overload, vertical framing, dialogue two-handers, sound and edit modes, continuity, era risk, commercial and comedy registers, genre-versus-style precedence, unknown tools, shot re-planning, style mixing, and the new lenses. Cases now carry `mode` and `loads` fields.
- `CONTRIBUTING.md` — rewritten for the v2 layout, the step and mode contracts, the new style module structure, and the no-invented-tool-facts rule.
- `README.md` — architecture diagram, feature list, style tables, adapter tables, and repo structure updated for v2 in both EN and 中文.

## [1.2.0] - 2026-05-25

### Added

- `CONTRIBUTING.md` — bilingual guide covering how to add a director style, AI video tool adapter, output mode, or eval case; project layout; style conventions; PR checklist; copyright-safety rule.
- `CHANGELOG.md` — this file.
- `references/director_styles/example_comparisons.md` — same scene treated by four different directors (Spielberg, Kubrick, Wong Kar-wai, Bi Gan), demonstrating how a style overlay actually changes blocking, camera grammar, color, sound, and prompt template.

### Changed

- `references/director_styles/README.md` — links to `example_comparisons.md`.
- Top-level `README.md` — references CONTRIBUTING and CHANGELOG; minor wording polish.

## [1.1.0] - 2026-05-25

### Added

- Four contemporary director-style overlays (now 14 total):
  - `11_villeneuve.md` — monumental scale, mist, geometric symmetry, low-rumble silence.
  - `12_fincher.md` — surgical control, teal-amber palette, procedural investigation, restrained dread.
  - `13_refn.md` — neon color blocks, symmetric ritual framing, slow gaze, sudden violence.
  - `14_bi_gan.md` — misty SW-China small towns, single ultra-long take, dream-memory loops, poetic voice-over.
- GitHub Actions workflows:
  - `.github/workflows/markdownlint.yml` (DavidAnson/markdownlint-cli2-action)
  - `.github/workflows/links.yml` (lycheeverse/lychee-action, `--offline` mode)
- `.markdownlint.json` calibrated for compact prose-heavy bilingual markdown.
- Four style-overlay eval cases (now 7 total):
  - `kubrick-style-corporate-office`
  - `wong-kar-wai-style-rain-street` (overlay variant of `rain-street-image-to-video`)
  - `villeneuve-style-desert-encounter`
  - `bi-gan-style-small-town-walk`
- CI status badges in README (markdownlint, links).

### Changed

- `SKILL.md` frontmatter `description:`, YAML `director_style:` enum, Step 3 "Available styles:" line, and "When to activate" bullet now include the four new directors.
- `SKILL.md` `version` bumped to `1.1.0`.
- `references/director_styles/README.md` table extended to 14 rows.
- Top-level `README.md` EN and 中文 director tables extended; repo-structure tree extended.
- `.markdownlint.json` disables MD022, MD031, MD032 — the director-style files use compact prose-under-heading by design, and the rules don't add real value for this content.
- The three ASCII-diagram fences in `README.md` are tagged `text` so MD040 stays useful.

## [1.0.0] - 2026-05-25

### Added

- Initial release of the `cinematic-director` skill.
- `SKILL.md` — 10-step directorial pipeline: script breakdown → beat map → director style selection → director's book → blocking → shot list → keyframe strategy → AI video prompt construction → tool adapter selection → QC & repair.
- 6 output modes: Director Analysis, Shot Plan, Keyframe Prompt Pack, Video Motion Prompt Pack, Continuity Bible, QC & Repair.
- 10 director-style overlays in `references/director_styles/`: Spielberg, Hitchcock, Kubrick, Kurosawa, Scorsese, Fellini, Bergman, Tarkovsky, Wong Kar-wai, Nolan.
- 6 AI video tool adapters in `references/ai-video-tool-adapters.md`: Runway, Veo, Kling, Luma, 即梦/Dreamina/Seedance, Wanxiang.
- Shared references: `cinematic-language.md`, `continuity-bible.md`.
- Reusable templates in `assets/`: `shot-plan-template.md`, `keyframe-prompt-template.md`, `video-prompt-template.md`, `qc-checklist.md`.
- `evals/evals.json` with 3 baseline cases.
- Bilingual README (EN + 中文), MIT license.

[Unreleased]: https://github.com/wuwangzhang1216/DirectorSKILL/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/wuwangzhang1216/DirectorSKILL/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/wuwangzhang1216/DirectorSKILL/compare/v1.2.0...v2.0.0
[1.2.0]: https://github.com/wuwangzhang1216/DirectorSKILL/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/wuwangzhang1216/DirectorSKILL/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/wuwangzhang1216/DirectorSKILL/releases/tag/v1.0.0
