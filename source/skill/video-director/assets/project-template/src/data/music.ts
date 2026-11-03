import type { MusicSegment } from "./types"

// Replace with the measured values from music_analyze.py once the track is chosen. Never trust an auto beat grid
// for the drop: find it by energy. With no track yet, `file` stays null and the grid still paces the cut.
export const MUSIC = {
  file: null as string | null,
  // Film second where the edited track starts (negative trims its head).
  at: 0,
  // Key for pitched foley, e.g. "F" or "A minor" (music_analyze.py estimates it).
  key: null as string | null,
  bpm: 120,
  beatsPerBar: 4,
  firstDownbeat: 0.0,
  // Film-time span where the camera pulses on the beat (only when a track is set).
  pulse: { from: 0, to: Infinity },
}

// Source ranges of the track, played back to back from MUSIC.at. music_splice.py ranks the splice points.
export const musicSegments: MusicSegment[] = [{ sourceStart: 0, sourceEnd: 60 }]

// Film second where each segment starts.
export function segmentStarts(): number[] {
  return musicSegments.reduce<number[]>((starts, segment, index) => {
    const previous = musicSegments[index - 1]
    starts.push(index === 0 ? MUSIC.at : starts[index - 1] + (previous.sourceEnd - previous.sourceStart))
    return starts
  }, [])
}

export const BEAT = 60 / MUSIC.bpm
export const BAR = BEAT * MUSIC.beatsPerBar

// Each grid point is computed from the origin, never by accumulating a rounded step (that drifts).
export function beat(index: number): number {
  return Number((MUSIC.firstDownbeat + index * BEAT).toFixed(4))
}

export function bar(index: number): number {
  return beat(index * MUSIC.beatsPerBar)
}

// Named phrase starts (4 bars each). Refer to these by name in the timeline, never by number.
export const phrase = {
  p0: bar(0),
  p1: bar(4),
  p2: bar(8),
  p3: bar(12),
} as const

export function beatIndexAt(time: number): number {
  return Math.floor((time - MUSIC.firstDownbeat) / BEAT + 1e-6)
}

export function beatsBetween(start: number, end: number): number[] {
  const beats: number[] = []
  for (let index = Math.max(0, Math.ceil((start - MUSIC.firstDownbeat) / BEAT - 1e-6)); beat(index) < end; index++) {
    beats.push(beat(index))
  }
  return beats
}

export function nearestBeat(time: number): number {
  return beat(Math.round((time - MUSIC.firstDownbeat) / BEAT))
}

export function downbeatAtOrAfter(time: number): number {
  return bar(Math.ceil((time - MUSIC.firstDownbeat) / BAR - 1e-6))
}
