import type { Timeline } from "./timeline"

// Kinds rendered by foley.py (synthesized) or played from public/sfx/<kind>.wav. Use `file` for a sourced sound.
export type SfxKind =
  | "pop"
  | "blip"
  | "thump"
  | "slap"
  | "stamp"
  | "whoosh"
  | "swell"
  | "tear"
  | "tick"
  | "key"
  | "flip"
  | "pluck"
  | "chime"
  | "riser"

export type SfxCue = {
  kind: SfxKind
  // Film second the sound's transient peak lands on (the visual contact frame). The mixer aligns the measured peak.
  at: number
  gain: number
  // Pitch in semitones above the kind's base note (tune pitched kinds to the song's key).
  note?: number
  file?: string
  // "texture" for runs meant to sit under the bed (tick runs, typing); events must be heard over voice and music.
  role?: "event" | "texture"
}

const SEAM_GAIN = 0.4

// Every animated event gets a sound, placed with the same timeline helpers the scenes animate with. Event gains 0.3-0.6,
// hero hits up to 1: mix.py fails when events sit too far under voice and music.
export function sfxCues(t: Timeline): SfxCue[] {
  const cues: SfxCue[] = []
  const add = (kind: SfxKind, at: number, gain: number, note?: number) => cues.push({ kind, at, gain, note })

  t.scenes.slice(1).forEach((span) => add("whoosh", span.start, SEAM_GAIN))

  ;["Your", "one-line", "promise"].forEach((word, index) => add("pop", t.wordAt("l01", word) + 0.12, 0.3, [0, 4, 7][index]))
  add("swell", t.wordAt("l03", "change") - 0.25, 0.3)
  add("tick", t.wordAt("l04", "detail"), 0.35)
  add("thump", t.scene("end").start, 0.5)
  add("chime", t.wordAt("l05", "Where"), 0.35, 7)

  return cues.sort((a, b) => a.at - b.at)
}
