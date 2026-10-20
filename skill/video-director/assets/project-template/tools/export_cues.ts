import { mkdirSync, writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { parseArgs } from "node:util"

import { FPS } from "../src/data/fps"
import { MUSIC, musicSegments } from "../src/data/music"
import { sfxCues } from "../src/data/sfx"
import { checkGaps, timeline } from "../src/data/timeline"
import { DEFAULT_VARIANT, isVariant, LINE_IDS, VARIANTS } from "../src/data/vo"

const USAGE = `Export the audio cue sheet for the offline mixer (sound-design skill, scripts/mix.py) from the film's timeline.

Usage: npx tsx tools/export_cues.ts [--variant ${VARIANTS.join("|")}] [--out PATH] [--min-gap SECONDS]
  --variant   which voice/language timing to export (default: $VARIANT or "${DEFAULT_VARIANT}")
  --out       output path (default: out/cues-<variant>.json)
  --min-gap   minimum silence between spoken lines (default 0.15)
Writes cues JSON in the mix.py contract (scripts/lib_audio/cues_model.py; files relative to public/), then runs
the gap check and exits 1 if it fails.
Example: VARIANT=alt npx tsx tools/export_cues.ts && uv run ~/.claude/skills/sound-design/scripts/mix.py out/cues-alt.json --out public/audio/mix-alt.wav`

const { values } = parseArgs({
  options: {
    variant: { type: "string" },
    out: { type: "string" },
    "min-gap": { type: "string" },
    help: { type: "boolean", short: "h" },
  },
})

if (values.help) {
  console.log(USAGE)
  process.exit(0)
}

const variantName = values.variant ?? process.env.VARIANT ?? DEFAULT_VARIANT
if (!isVariant(variantName)) {
  console.error(`Unknown variant "${variantName}". Expected one of: ${VARIANTS.join(", ")}`)
  process.exit(2)
}

const t = timeline(variantName)
const round = (seconds: number) => Number(seconds.toFixed(3))
const estimated = LINE_IDS.filter((id) => t.lines[id].estimated === true)

const cues = {
  name: "film",
  voice: t.variant,
  fps: FPS,
  duration: round(t.duration),
  ...(MUSIC.key === null ? {} : { key: MUSIC.key }),
  ...(MUSIC.file === null ? {} : { music: { file: MUSIC.file, at: MUSIC.at, segments: musicSegments } }),
  vo: LINE_IDS.map((id) => ({ id, file: t.lines[id].file, at: round(t.voStart[id]) })),
  product: t.diegetic.map((cue) => ({ id: cue.id, file: cue.file, at: round(cue.at) })),
  sfx: sfxCues(t).map((cue) => ({ ...cue, at: round(cue.at) })),
  meta: {
    schema: "video-director/cues@1",
    bpm: MUSIC.bpm,
    firstDownbeat: MUSIC.firstDownbeat,
    scenes: t.scenes.map((span) => ({ id: span.id, start: round(span.start), end: round(span.end) })),
    lines: Object.fromEntries(LINE_IDS.map((id) => [id, { end: round(t.voEnd(id)), text: t.lines[id].text }])),
    estimatedVo: estimated,
  },
}

const target = resolve(values.out ?? `out/cues-${t.variant}.json`)
mkdirSync(dirname(target), { recursive: true })
writeFileSync(target, `${JSON.stringify(cues, null, 2)}\n`)
console.log(`${target}: ${cues.vo.length} VO lines, ${cues.product.length} product sounds, ${cues.sfx.length} sfx, ${cues.duration}s`)
if (MUSIC.file === null) console.log("  note: no music track set (src/data/music.ts MUSIC.file)")
if (estimated.length) console.log(`  note: estimated timings, no recorded VO yet: ${estimated.join(", ")}`)

const issues = checkGaps(t, values["min-gap"] === undefined ? undefined : Number(values["min-gap"]))
issues.forEach((issue) => console.log(`  ${issue.kind.toUpperCase()}: ${issue.message}`))
console.log(issues.length ? `FAIL gap check (${issues.length} issue${issues.length > 1 ? "s" : ""})` : "PASS gap check")
process.exit(issues.length ? 1 : 0)
