// PLACEHOLDER BRAND. Replace every value from the product's design source (DESIGN.md, BRAND.md, CSS variables or
// tokens captured from the live product) and note the source next to it. Never inline a hex value in a scene.
export const color = {
  paper: "#f2f1ee",
  paperDeep: "#e7e5df",
  ink: "#121418",
  mutedInk: "#5f636c",
  line: "#d3d0c8",
  surface: "#ffffff",
  accent: "#3a5bff",
  accentInk: "#ffffff",
  night: "#121418",
  nightInk: "#f2f1ee",
  nightMuted: "#9a9ea8",
} as const

// Sizes in design units (1 unit = 1 px on a 1080 px short side; multiply by `u` from useFormat()).
// Floors from the official video layout rules: headline >= 84, supporting text >= 44 at 1080 wide.
export const size = {
  display: 156,
  headline: 104,
  title: 72,
  body: 48,
  label: 30,
  captionWide: 40,
  captionTall: 50,
} as const

export const radius = {
  card: 28,
  pill: 999,
} as const

export const type = {
  display: { fontWeight: 800, letterSpacing: "-0.035em", lineHeight: 0.96 },
  headline: { fontWeight: 750, letterSpacing: "-0.025em", lineHeight: 1.02 },
  body: { fontWeight: 500, letterSpacing: "-0.005em", lineHeight: 1.25 },
  label: { fontWeight: 650, letterSpacing: "0.14em", lineHeight: 1, textTransform: "uppercase" },
} as const
