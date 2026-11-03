import { BEAT, beat, beatIndexAt, MUSIC } from "../data/music"

// 0 -> 1 kick on every beat, stronger on downbeats, decaying fast. Silent without a track or outside MUSIC.pulse.
export function beatKick(time: number, decay = 0.16): number {
  if (MUSIC.file === null || time < MUSIC.pulse.from || time > MUSIC.pulse.to) return 0
  const index = beatIndexAt(time)
  const since = time - beat(index)
  if (since < 0 || since > BEAT) return 0
  const strength = index % MUSIC.beatsPerBar === 0 ? 1 : 0.45
  return strength * Math.exp(-since / decay)
}

// Camera-level push on each beat (0.7% at a downbeat): the one sanctioned ambient motion, applied once, on the
// world wrapper in Main. Never stack it with per-element breathing.
export function cameraPulse(time: number, amount = 0.007): number {
  return 1 + amount * beatKick(time)
}
