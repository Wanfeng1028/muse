import { Easing, interpolate, random, spring, useCurrentFrame, useVideoConfig } from "remotion"

import { FPS } from "../data/fps"
import { useFrameOffset } from "./clock"

// Film time in seconds at the current frame, including the offset of the enclosing scene <Sequence>.
export function useTime(): number {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  return (frame + useFrameOffset()) / fps
}

export type SpringPreset = { stiffness: number; damping: number; mass?: number }

// Damping ratio zeta = damping / (2 * sqrt(stiffness * mass)). Remotion's default spring is zeta 0.5 (bouncy):
// always pass a preset. Keep zeta >= 0.72 unless the brief declares a playful register (never below 0.55).
export const springs = {
  settle: { stiffness: 170, damping: 26 },
  snappy: { stiffness: 320, damping: 30 },
  heavy: { stiffness: 120, damping: 24 },
  playful: { stiffness: 180, damping: 17 },
} satisfies Record<string, SpringPreset>

export function dampingRatio(preset: SpringPreset): number {
  return preset.damping / (2 * Math.sqrt(preset.stiffness * (preset.mass ?? 1)))
}

// Spring progress 0 -> 1 started at `start` seconds. Physics depend on elapsed seconds only; fps sets sampling.
export function sp(time: number, start: number, preset: SpringPreset = springs.settle, fps: number = FPS): number {
  if (time < start) return 0
  return spring({ frame: (time - start) * fps, fps, config: { mass: 1, ...preset } })
}

// Three easing characters per film, chosen by role. Entrances ease out, exits ease in, moves between two
// on-screen positions ease in-out. Never linear on an entrance or exit position.
export const ease = {
  out: Easing.bezier(0.16, 1, 0.3, 1),
  outSoft: Easing.bezier(0.33, 1, 0.68, 1),
  in: Easing.bezier(0.7, 0, 0.84, 0),
  inOut: Easing.bezier(0.65, 0, 0.35, 1),
  linear: Easing.linear,
}

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const

// Clamped tween in seconds.
export function tw(time: number, start: number, end: number, from: number, to: number, easing: (value: number) => number = ease.out): number {
  return interpolate(time, [start, end], [from, to], { ...clamp, easing })
}

// Clamped scale tween in seconds; perceptual output so growth does not read as decelerating.
export function twScale(time: number, start: number, end: number, from: number, to: number, easing: (value: number) => number = ease.inOut): number {
  return interpolate(time, [start, end], [from, to], { ...clamp, easing, output: "perceptual-scale" })
}

export function mix(from: number, to: number, progress: number): number {
  return from + (to - from) * progress
}

// Deterministic value in [min, max) from a seed (Remotion's seeded random). Never Math.random in a film.
export function seeded(seed: string | number, min = 0, max = 1): number {
  return min + random(seed) * (max - min)
}
