# Design Docs, Plans & Production Slates

Nontrivial videos get written down before they get built. Three document types, in order of altitude.

## 1. The idea sheet → production slate (campaign level)

**Idea sheet** (upstream): a thesis for the campaign ("the artist is the missing ingredient — a real human inside the procedural universes"), a footage inventory table (Set | What it is | State), the skill stack the ideas assume (which renderers/pipelines exist), ranked track-by-track concepts (★ = pilot pick; each with Window / Build / Skills needed / Hook / Why it wins), a compounding series concept, and a pilot batch table (# | Concept | Blocking dependency | Deliverable).

**Production slate** (downstream, shot-by-shot): header carries the governing rules (integrated-FX rule verbatim, the quality-bar reference file path, casting facts, clip-ID source manifest, priority order V1→V7, and global constraints: "Every video: 1080×1920@30, loop-seam ending, tournament-style hook (line 1 frame 0, line 2 beat-fused 0.8–1.3s), 5-hook A/B pack, house grade over all composites"). Then per production:

- Track + concept title + duration + song window + beat length (e.g. "V1 · run to u — 'The Portal at the Pond' (30s, 0:46–1:17, beat 0.511s)").
- One-line premise.
- **Shot-by-shot table**: `Shot | Beats/Time | Source (clip ID) | Action | Integrated effects` — effects name the exact technique (sky-tracked matte, water-reflection duplicate + displacement, corner-pin screen replacement, person-matte echo bodies, digital dolly) and where hook lines land.
- FX kit line (renderers/comp tools needed) + craft-risk notes ("build LAST").

Close with: ground-truth footage pool statement, privacy rule (per-file owner OK before personal material posts), and standing to-dos. Use a **pilot-gate model**: V1 proves the grammar; approval on V1 unlocks batch production of the rest.

## 2. The design doc (per hero piece, before building)

Sections, in order:

- **Objective** — intent + the bar it must beat ("must surpass the existing POC in dimensionality, visual hierarchy, audio synchronization, and finish").
- **Deliverables** — exact files and specs ("One 15.000-second H.264 MP4 at 1080×1920, 30fps, AAC audio", poster frame, contact sheet, reusable renderer path).
- **Creative direction** — hero image, material, typography, composition, named depth layers.
- **Motion & audio design** — a phase timeline over the exact duration (e.g. five phases: 0.0–2.5 reveal → … → 13.5–15.0 plunge); audio as separate control signals (onset / low / mid-high / integrated energy).
- **Rendering & finish** — tech stack + finish features (tonemap, dithering, bloom, supersample + Lanczos).
- **Quality standard** — "complete only when ALL of the following are true": anchor visible every frame, ≥3 distinguishable depth layers, smooth near-black gradients, clean highlight rolloff, no accidental blank output or shader artifacts, probes exactly to spec.
- **Verification** — ordered: compile → stills at mandated timestamps → contact sheet → full render → inspect full-size AND phone-scale → measure frame luminance → ffprobe → play the whole file.
- **Failure handling** — if/then remediation ("if it reads flat, increase depth separation before adding detail"; "if the center loses dominance, darken peripheral machinery").
- **Scope boundary** — explicit exclusions.

For reference-based work add a **comparative visual audit**: contact sheet of reference frames vs final holds; if the work reads flatter/noisier/more generic than the reference, revise and rerender before delivery.

## 3. The implementation plan (task level)

Checkbox tasks, each with Files/Interfaces and strict TDD: write the failing test → confirm it fails → implement to the exact signature → pass → commit. Tests assert the CONTRACT: audio-control determinism and bounds, shader uniform presence, exact ffmpeg flags (`-crf 17`, `yuv420p`, `+faststart`), phase-boundary functions. A config JSON is the single source of truth; validators emit machine-parseable lines. Final tasks are always: full render → visual QA → delivery artifacts → ffprobe verification → "play the final MP4 from start to finish and confirm audio sync, continuous motion, a controlled ending, no blank frames, and no shader artifacts."
