import type { Timeline } from "./timeline"
import type { TimeSpan, VoWord } from "./types"
import { LINE_IDS } from "./vo"

export type CaptionPage = TimeSpan & { words: VoWord[] }

export const CAPTION_RULES = {
  maxCharsWide: 42,
  maxCharsTall: 26,
  minCharsBeforePunctuationBreak: 8,
  pauseBreak: 0.5,
  holdMin: 0.25,
  holdMax: 0.6,
  minOnScreen: 0.7,
  bridgeGap: 0.15,
} as const

const textLength = (words: VoWord[]) => words.map((word) => word.text).join(" ").length

// Natural phrases first: break after punctuation (once the page has a few characters) and at pauses >= 0.5 s.
function phrases(words: VoWord[]): VoWord[][] {
  const result: VoWord[][] = []
  let current: VoWord[] = []
  words.forEach((word, index) => {
    const previous = words[index - 1]
    if (current.length && previous && word.start - previous.end >= CAPTION_RULES.pauseBreak) {
      result.push(current)
      current = []
    }
    current.push(word)
    if (/[.?!,;:]$/.test(word.text) && textLength(current) >= CAPTION_RULES.minCharsBeforePunctuationBreak) {
      result.push(current)
      current = []
    }
  })
  if (current.length) result.push(current)
  return result
}

// A phrase longer than maxChars becomes n balanced pages instead of a full page plus an orphan word.
function balance(phrase: VoWord[], maxChars: number): VoWord[][] {
  const total = textLength(phrase)
  if (total <= maxChars) return [phrase]
  const target = total / Math.ceil(total / maxChars)
  const pages: VoWord[][] = []
  let current: VoWord[] = []
  phrase.forEach((word) => {
    if (current.length && (textLength(current) >= target || textLength([...current, word]) > maxChars)) {
      pages.push(current)
      current = []
    }
    current.push(word)
  })
  if (current.length) pages.push(current)
  return pages
}

function splitLine(words: VoWord[], maxChars: number): VoWord[][] {
  return phrases(words).flatMap((phrase) => balance(phrase, maxChars))
}

// Each page holds 0.25-0.6 s after its last word, stays at least 0.7 s, never overlaps the next page, and bridges
// gaps shorter than 0.15 s so captions do not blink.
function timePages(pages: VoWord[][]): CaptionPage[] {
  return pages.map((words, index) => {
    const start = words[0].start
    const lastEnd = words[words.length - 1].end
    const next = pages[index + 1]?.[0].start ?? Infinity
    const wanted = Math.max(lastEnd + CAPTION_RULES.holdMax, start + CAPTION_RULES.minOnScreen)
    let end = Math.min(next, Math.max(lastEnd + CAPTION_RULES.holdMin, wanted))
    if (next - end < CAPTION_RULES.bridgeGap) end = next
    return { words, start, end }
  })
}

// Pages built from the VO word timings (film time). maxChars: 42 for wide, 26 for tall.
export function captionPages(t: Timeline, maxChars: number): CaptionPage[] {
  const placed = LINE_IDS.map((id) => t.lines[id].words.map((word) => ({ ...word, start: word.start + t.voStart[id], end: word.end + t.voStart[id] })))
  const pages = placed.flatMap((words) => splitLine(words, maxChars)).sort((a, b) => a[0].start - b[0].start)
  return timePages(pages)
}

// Captions step aside where big kinetic type already says the same words.
export function captionHiddenSpans(t: Timeline): TimeSpan[] {
  return [
    { start: 0, end: t.voEnd("l01") + 0.3 },
    { start: t.scene("end").start, end: Infinity },
  ]
}
