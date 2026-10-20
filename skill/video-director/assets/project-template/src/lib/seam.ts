import type { CSSProperties } from "react"
import { Easing, interpolate } from "remotion"

import type { SceneSpan } from "../data/types"

export type SeamDirection = "left" | "right" | "up" | "down"

// Velocity-matched hard cut ("cut the curve"): the outgoing scene accelerates out and is still moving at the cut,
// its opacity reaching 0 on the cut frame itself (so its last frame is never blank); the incoming scene starts at
// the same speed in the same direction and decelerates. Zero overlap: one scene per frame, over an opaque
// background. Pick ONE direction for every ordinary seam of the film.
export type Seam = {
  exit: number
  entry: number
  // Exit travel as a fraction of the frame's width (or height for up/down). ~12%: never fully off-screen.
  distance: number
  // Polynomial degree of the ease-in / ease-out halves (5 = GSAP power4).
  power: number
  // Peak wrapper blur at the cut, design units: 10 for text-scale content, 18-20 for a full-frame surface.
  blur: number
  direction: SeamDirection
}

export const SEAM: Seam = { exit: 0.33, entry: 0.4, distance: 0.12, power: 5, blur: 8, direction: "left" }

const VECTORS: Record<SeamDirection, { x: number; y: number }> = {
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
}

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const

type Frame = { width: number; height: number; u: number }

function exitDistance(seam: Seam, frame: Frame): number {
  return seam.distance * (VECTORS[seam.direction].x !== 0 ? frame.width : frame.height)
}

// Entry distance scaled by T_entry / T_exit keeps n * D / T (the speed at the cut) equal on both sides.
function entryDistance(seam: Seam, frame: Frame): number {
  return (exitDistance(seam, frame) * seam.entry) / seam.exit
}

export function seamSpeedsAtCut(seam: Seam, frame: Frame): { exit: number; entry: number } {
  return {
    exit: (seam.power * exitDistance(seam, frame)) / seam.exit,
    entry: (seam.power * entryDistance(seam, frame)) / seam.entry,
  }
}

function styleFor(offset: number, opacity: number, blur: number, seam: Seam): CSSProperties {
  const vector = VECTORS[seam.direction]
  return {
    translate: `${vector.x * offset}px ${vector.y * offset}px`,
    opacity,
    filter: blur > 0.05 ? `blur(${blur}px)` : undefined,
  }
}

export function seamExitStyle(time: number, cut: number, seam: Seam, frame: Frame): CSSProperties {
  const start = cut - seam.exit
  const progress = interpolate(time, [start, cut], [0, 1], { ...clamp, easing: Easing.in(Easing.poly(seam.power)) })
  const opacity = interpolate(time, [start, cut], [1, 0], { ...clamp, easing: Easing.in(Easing.cubic) })
  return styleFor(exitDistance(seam, frame) * progress, opacity, seam.blur * frame.u * progress, seam)
}

export function seamEntryStyle(time: number, cut: number, seam: Seam, frame: Frame): CSSProperties {
  const progress = interpolate(time, [cut, cut + seam.entry], [0, 1], { ...clamp, easing: Easing.out(Easing.poly(seam.power)) })
  const opacity = interpolate(time, [cut, cut + seam.entry * 0.6], [0.35, 1], { ...clamp, easing: Easing.out(Easing.cubic) })
  return styleFor(-entryDistance(seam, frame) * (1 - progress), opacity, seam.blur * frame.u * (1 - progress), seam)
}

// Style for a scene's content wrapper: entry after its start, exit before its end. The film's first scene has
// no entry and the last has no exit (the final hold). Apply to the wrapper, never to the children.
export function seamStyle(time: number, span: SceneSpan, frame: Frame, options: { entry?: boolean; exit?: boolean; seam?: Seam } = {}): CSSProperties {
  const seam = options.seam ?? SEAM
  if (options.entry !== false && time < span.start + seam.entry) return seamEntryStyle(time, span.start, seam, frame)
  if (options.exit !== false && time >= span.end - seam.exit) return seamExitStyle(time, span.end, seam, frame)
  return {}
}
