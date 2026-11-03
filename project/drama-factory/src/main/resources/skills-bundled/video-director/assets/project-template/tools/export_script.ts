import { mkdirSync, writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { parseArgs } from "node:util"

import { LINE_IDS, SCRIPT, SPOKEN } from "../src/data/vo"

const USAGE = `Write the VO script for vo_record.py from src/data/vo.ts (SPOKEN overrides SCRIPT per line).

Usage: npx tsx tools/export_script.ts [--out PATH]
  --out   output path (default: out/script.json)
Output: [{"id": "l01", "text": "..."}, ...] in film order.
Example: npx tsx tools/export_script.ts && uv run ~/.claude/skills/voice-direction/scripts/vo_record.py out/script.json --voice <id> --dry-run`

const { values } = parseArgs({ options: { out: { type: "string" }, help: { type: "boolean", short: "h" } } })

if (values.help) {
  console.log(USAGE)
  process.exit(0)
}

const lines = LINE_IDS.map((id) => ({ id, text: SPOKEN[id] ?? SCRIPT[id] }))
const words = lines.reduce((sum, line) => sum + line.text.replace(/\[[^\]]*\]/g, "").split(/\s+/).filter(Boolean).length, 0)
const target = resolve(values.out ?? "out/script.json")
mkdirSync(dirname(target), { recursive: true })
writeFileSync(target, `${JSON.stringify(lines, null, 2)}\n`)
console.log(`${target}: ${lines.length} lines, ${words} words (~${(words / 2.5).toFixed(1)} s at 2.5 words/s)`)
