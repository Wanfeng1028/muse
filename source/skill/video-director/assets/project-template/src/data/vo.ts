import type { VoLine, VoWord } from "./types"

// One entry per voice or language. Pick one with --props='{"variant":"alt"}'; Node tools read VARIANT=alt.
export const VARIANTS = ["main", "alt"] as const
export type Variant = (typeof VARIANTS)[number]
export const DEFAULT_VARIANT: Variant = "main"

// The script, line by line. Lines are discrete cues: each on-screen reveal lands on the word that names it.
export const SCRIPT = {
  l01: "Your one-line promise.",
  l02: "Name where your viewer is stuck.",
  l03: "Then show the change your product makes.",
  l04: "Prove it with one real detail.",
  l05: "Your product name. Where to find it.",
} as const
export type LineId = keyof typeof SCRIPT
export const LINE_IDS = Object.keys(SCRIPT) as LineId[]

// What the voice is asked to say when it differs from the display text: delivery tags ("[warmly] ...") and
// phonetic spellings ("jay-sawn" for JSON). Captions always show SCRIPT; tools/export_script.ts sends these.
export const SPOKEN: Partial<Record<LineId, string>> = {}

// After `vo_build.py picks.json --out public/audio/vo/<variant> --ts src/data/vo-<variant>.generated.ts`, import
// its voLines here and register it, e.g. `import { voLines as main } from "./vo-main.generated"` and `main` in
// GENERATED. Lines it does not cover are estimated from the script so the film times out before any recording.
const GENERATED: Partial<Record<Variant, Record<string, VoLine>>> = {}

const WORDS_PER_SECOND = 2.6
const PAUSE_AFTER = { comma: 0.18, stop: 0.32 }

function estimateWords(text: string): VoWord[] {
  const tokens = text.split(/\s+/).filter(Boolean)
  const letters = tokens.reduce((sum, token) => sum + token.length, 0)
  const speaking = tokens.length / WORDS_PER_SECOND
  let cursor = 0.05
  return tokens.map((token) => {
    const length = (speaking * token.length) / letters
    const word = { text: token, start: Number(cursor.toFixed(3)), end: Number((cursor + length).toFixed(3)) }
    cursor += length + (/[.?!]$/.test(token) ? PAUSE_AFTER.stop : /[,;:]$/.test(token) ? PAUSE_AFTER.comma : 0.02)
    return word
  })
}

function estimateLine(variant: Variant, id: LineId): VoLine {
  const words = estimateWords(SCRIPT[id])
  const duration = Number((words[words.length - 1].end + 0.1).toFixed(3))
  return { id, text: SCRIPT[id], file: `audio/vo/${variant}/${id}.wav`, duration, words, estimated: true }
}

export function voLinesFor(variant: Variant): Record<LineId, VoLine> {
  const generated = GENERATED[variant] ?? {}
  return Object.fromEntries(LINE_IDS.map((id) => [id, generated[id] ?? estimateLine(variant, id)])) as Record<LineId, VoLine>
}

export function isVariant(value: unknown): value is Variant {
  return typeof value === "string" && (VARIANTS as readonly string[]).includes(value)
}

const normalize = (text: string) => text.toLowerCase().replace(/[^\p{L}\p{N}'-]/gu, "")

// Seconds from the start of the line's file to the start of the n-th word that begins with `word`.
export function wordOffset(line: VoLine, word: string, occurrence = 1): number {
  const matches = line.words.filter((candidate) => normalize(candidate.text).startsWith(normalize(word)))
  const found = matches[occurrence - 1]
  if (!found) throw new Error(`Word "${word}" #${occurrence} not found in ${line.id}: "${line.text}"`)
  return found.start
}
