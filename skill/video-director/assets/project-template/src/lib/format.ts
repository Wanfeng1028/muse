import { useVideoConfig } from "remotion"

export type FormatKind = "wide" | "tall" | "square" | "feed"

export type Format = {
  width: number
  height: number
  kind: FormatKind
  tall: boolean
  // One design unit: 1 px at 1080 on the short side.
  u: number
  cx: number
  cy: number
  // Safe insets in px. Tall leaves the bottom ~18% for platform UI (captions, buttons, handles).
  safe: { x: number; top: number; bottom: number }
}

function kindOf(width: number, height: number): FormatKind {
  const ratio = width / height
  if (ratio > 1.2) return "wide"
  if (ratio > 0.95) return "square"
  if (ratio > 0.7) return "feed"
  return "tall"
}

export function useFormat(): Format {
  const { width, height } = useVideoConfig()
  const kind = kindOf(width, height)
  const u = Math.min(width, height) / 1080
  const tall = kind !== "wide"
  return {
    width,
    height,
    kind,
    tall,
    u,
    cx: width / 2,
    cy: height / 2,
    safe: {
      x: (kind === "wide" ? 120 : 80) * u,
      top: (kind === "tall" ? 160 : 100) * u,
      bottom: kind === "tall" ? height * 0.18 : 100 * u,
    },
  }
}

// One value per format. Square and feed fall back to tall (stacked) layouts, then wide.
export function pick<T>(format: Format, values: { wide: T; tall: T; square?: T; feed?: T }): T {
  if (format.kind === "wide") return values.wide
  if (format.kind === "square") return values.square ?? values.tall
  if (format.kind === "feed") return values.feed ?? values.tall
  return values.tall
}
