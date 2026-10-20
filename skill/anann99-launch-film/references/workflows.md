# Optional: multi-agent Workflow scripts

Some Claude Code setups expose a **Workflow** tool for deterministic multi-agent orchestration. It provides:
- `agent()`, `parallel()`, `pipeline()`, `phase()`, `log()`;
- results cached for resume.

Use these scripts **only if that tool is available and the user has opted into multi-agent orchestration**. Otherwise spawn the same prompts (see `agent-prompts.md`) as parallel `Agent` subagents in one message, or run the stages yourself.

Before running, replace `ROOT`, the scene groups, and the notes in each script.

**Robustness lessons:**
- Keep each agent ≤ ~15–20 min.
- Tell agents to resume from existing files.
- Read the journal before assuming an empty result means failure.
- If agents come back with "[Request interrupted]", re-run with resume. Completed agents replay from cache.

## A. Storyboard critique (2 agents)
```js
export const meta = {
  name: 'launch-film-storyboard-critique',
  description: 'Two adversarial critics (brand/truth, craft/readability) review the storyboard',
  phases: [{ title: 'Critique' }],
}
const ROOT = '/path/to/project'
const COMMON = `Read ${ROOT}/BRIEF.md and ${ROOT}/STORYBOARD.md. Work fast (≈6 min), no sub-agents, open at most 4 images. Every issue must quote the exact storyboard line and give an exact fix.`
const SCHEMA = { type: 'object', properties: {
  issues: { type: 'array', items: { type: 'object', properties: {
    severity: { type: 'string', enum: ['high', 'medium', 'low'] }, scene: { type: 'string' },
    quote: { type: 'string' }, problem: { type: 'string' }, fix: { type: 'string' } },
    required: ['severity', 'scene', 'quote', 'problem', 'fix'] } },
  verdict: { type: 'string' } }, required: ['issues', 'verdict'] }
phase('Critique')
const [brand, craft] = await parallel([
  () => agent(`${COMMON}\n<BRAND/TRUTH critic prompt from agent-prompts.md>`, { label: 'critic:brand', phase: 'Critique', schema: SCHEMA }),
  () => agent(`${COMMON}\n<CRAFT/READABILITY critic prompt from agent-prompts.md>`, { label: 'critic:craft', phase: 'Critique', schema: SCHEMA }),
])
return { brand, craft }
```

## B. Build + score + review (6 builders → 6 art directors, 1 composer)
```js
export const meta = {
  name: 'launch-film-build',
  description: 'Build scenes in pairs, compose the score in parallel, then adversarial review-and-fix per pair',
  phases: [{ title: 'Build' }, { title: 'Review' }],
}
const ROOT = '/path/to/project'
const PAIRS = [
  { key: 'A', scenes: ['S01', 'S02'], note: 'Act I kinetic type; the pill swap must be flawless.' },
  { key: 'B', scenes: ['S03', 'S04'], note: 'Problem build + the DROP (hard cut): logo moment must be stunning.' },
  { key: 'C', scenes: ['S05', 'S06'], note: 'Product steps 01–02: precise push-ins from rects.json; typing wipe.' },
  { key: 'D', scenes: ['S07', 'S08'], note: 'Energy peak + payoff; keep demo numbers out of focus.' },
  { key: 'E', scenes: ['S09', 'S10'], note: 'Proof numbers land exactly on hits; small crisp customer logos.' },
  { key: 'F', scenes: ['S11', 'S12'], note: 'Close + end card; full lockup holds ≥ 2.4 s.' },
]
const BUILDER = `<builder prompt from agent-prompts.md, with ${ROOT}>`
const DIRECTOR = `<art-director prompt from agent-prompts.md>`
const BUILD_SCHEMA = { type: 'object', properties: { scenes: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' }, knownIssues: { type: 'array', items: { type: 'string' } }, typecheckClean: { type: 'boolean' } }, required: ['scenes', 'summary', 'knownIssues', 'typecheckClean'] }
const REVIEW_SCHEMA = { type: 'object', properties: { scenes: { type: 'array', items: { type: 'string' } }, issuesFound: { type: 'array', items: { type: 'string' } }, fixesApplied: { type: 'array', items: { type: 'string' } }, remaining: { type: 'array', items: { type: 'string' } }, score: { type: 'number' } }, required: ['scenes', 'issuesFound', 'fixesApplied', 'remaining', 'score'] }

const composer = agent(`<composer prompt from agent-prompts.md>`, { label: 'composer', phase: 'Build' })
const scenes = pipeline(
  PAIRS,
  (p) => agent(`${BUILDER}\nYOUR SCENES: ${p.scenes.join(' and ')}. Direction: ${p.note}`, { label: `build:${p.key}`, phase: 'Build', schema: BUILD_SCHEMA }),
  (built, p) => agent(`${DIRECTOR}\nSCENES: ${p.scenes.join(' and ')}. Builder notes: ${JSON.stringify(built)}`, { label: `review:${p.key}`, phase: 'Review', schema: REVIEW_SCHEMA }),
)
const [score, results] = await Promise.all([composer, scenes])
return { score, results }
```

## C. Final review on the rendered film (2 agents) → D. Fix pass (one per scene group)
```js
export const meta = {
  name: 'launch-film-final-review',
  description: 'Fresh-eyes review of the rendered film: story/brand and cross-scene craft',
  phases: [{ title: 'Review' }],
}
const ROOT = '/path/to/project'
const COMMON = `<final-reviewer prompt from agent-prompts.md, pointing at ${ROOT}/video/out/<name>.mp4>`
const SCHEMA = { type: 'object', properties: {
  issues: { type: 'array', items: { type: 'object', properties: {
    severity: { type: 'string', enum: ['must-fix', 'should-fix', 'nice-to-have'] }, t: { type: 'string' },
    scene: { type: 'string' }, problem: { type: 'string' }, fix: { type: 'string' } },
    required: ['severity', 't', 'scene', 'problem', 'fix'] } },
  overall: { type: 'string' }, score: { type: 'number' } }, required: ['issues', 'overall', 'score'] }
phase('Review')
const [story, craft] = await parallel([
  () => agent(`${COMMON}\nLENS A: story, brand, truth.`, { label: 'final:story', phase: 'Review', schema: SCHEMA }),
  () => agent(`${COMMON}\nLENS B: cross-scene craft consistency and finish.`, { label: 'final:craft', phase: 'Review', schema: SCHEMA }),
])
return { story, craft }
```

**Fix pass:** group the must-fix and should-fix issues by scene files. Run one fixer agent per group with `parallel([...])`, using the fixer prompt. Make central changes yourself, e.g. the hand-off grammar in `Main.tsx` or a shared primitive.
