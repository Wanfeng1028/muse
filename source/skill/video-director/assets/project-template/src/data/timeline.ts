import { bar, downbeatAtOrAfter } from "./music"
import type { DiegeticCue, SceneSpan, TimeSpan } from "./types"
import { color } from "../theme/tokens"
import { DEFAULT_VARIANT, LINE_IDS, voLinesFor, wordOffset, type LineId, type Variant } from "./vo"

// Per-variant nudges in film seconds where a slower read needs room. The first variant is the reference timing.
const VARIANT_OVERRIDES: Record<Variant, Partial<Record<LineId, number>>> = {
  main: {},
  alt: { l02: bar(2) + 0.1 },
}

const END_HOLD = 2.5
const MIN_GAP = 0.15

export type Timeline = ReturnType<typeof timelineFor>

// Everything time-related for one variant, in film seconds. Scenes, captions, SFX cues and the mixer all read
// this object, so picture and sound cannot drift apart.
export function timelineFor(variant: Variant = DEFAULT_VARIANT) {
  const lines = voLinesFor(variant)

  // Land a word of a line exactly on a film time (usually a downbeat): returns where the line must start.
  const anchor = (id: LineId, word: string, at: number) => at - wordOffset(lines[id], word)

  const voStart: Record<LineId, number> = {
    l01: 0.4,
    l02: bar(2) + 0.25,
    l03: anchor("l03", "change", bar(4)),
    l04: bar(6) + 0.25,
    l05: bar(8) + 0.35,
    ...VARIANT_OVERRIDES[variant],
  }

  const voEnd = (id: LineId) => voStart[id] + lines[id].duration
  const wordAt = (id: LineId, word: string, occurrence = 1) => voStart[id] + wordOffset(lines[id], word, occurrence)
  const wordEnd = (id: LineId, word: string, occurrence = 1) => {
    const start = wordOffset(lines[id], word, occurrence)
    const found = lines[id].words.find((candidate) => candidate.start === start)
    return voStart[id] + (found?.end ?? start)
  }

  const endStart = bar(8)
  const scenes: SceneSpan[] = [
    { id: "hook", start: 0, end: bar(2), background: color.paper },
    { id: "pain", start: bar(2), end: bar(4), background: color.paper },
    { id: "turn", start: bar(4), end: bar(6), background: color.paperDeep },
    { id: "proof", start: bar(6), end: endStart, background: color.paper },
    { id: "end", start: endStart, end: downbeatAtOrAfter(voEnd("l05") + END_HOLD), background: color.night },
  ]

  const scene = (id: string): SceneSpan => {
    const found = scenes.find((candidate) => candidate.id === id)
    if (!found) throw new Error(`Unknown scene "${id}"`)
    return found
  }

  const diegetic: DiegeticCue[] = []

  return {
    variant,
    lines,
    voStart,
    voEnd,
    wordAt,
    wordEnd,
    scenes,
    scene,
    diegetic,
    duration: scenes[scenes.length - 1].end,
  }
}

export type GapIssue = { kind: "overlap" | "tight" | "outside"; message: string }

// Consecutive spoken lines need >= MIN_GAP between them; diegetic sounds must fall inside a pause; nothing may
// run past the end of the film.
export function checkGaps(timeline: Timeline, minGap = MIN_GAP): GapIssue[] {
  const spans: (TimeSpan & { id: string })[] = [
    ...LINE_IDS.map((id) => ({ id, start: timeline.voStart[id], end: timeline.voEnd(id) })),
    ...timeline.diegetic.map((cue) => ({ id: cue.id, start: cue.at, end: cue.at + cue.duration })),
  ].sort((a, b) => a.start - b.start)

  const issues: GapIssue[] = []
  spans.forEach((span, index) => {
    if (span.start < 0 || span.end > timeline.duration) {
      issues.push({ kind: "outside", message: `${span.id} ${span.start.toFixed(2)}-${span.end.toFixed(2)}s is outside 0-${timeline.duration.toFixed(2)}s` })
    }
    const previous = spans[index - 1]
    if (!previous) return
    const gap = span.start - previous.end
    if (gap < 0) issues.push({ kind: "overlap", message: `${previous.id} -> ${span.id} overlap ${(-gap).toFixed(2)}s` })
    else if (gap < minGap) issues.push({ kind: "tight", message: `${previous.id} -> ${span.id} gap ${gap.toFixed(2)}s < ${minGap}s` })
  })
  return issues
}

const cache = new Map<Variant, Timeline>()

export function timeline(variant: Variant = DEFAULT_VARIANT): Timeline {
  const cached = cache.get(variant)
  if (cached) return cached
  const built = timelineFor(variant)
  cache.set(variant, built)
  return built
}
