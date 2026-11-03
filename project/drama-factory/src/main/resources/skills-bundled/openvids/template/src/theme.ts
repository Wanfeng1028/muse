import { Easing, interpolate, spring } from "remotion";
import { loadFont as loadGeist } from "@remotion/google-fonts/Geist";
import { loadFont as loadMono } from "@remotion/google-fonts/GeistMono";
import { loadFont as loadSerif } from "@remotion/google-fonts/InstrumentSerif";
import { FPS } from "./timeline";

const sans = loadGeist("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["400", "500"], subsets: ["latin"] });
const serif = loadSerif("italic", { weights: ["400"], subsets: ["latin"] });

export const BRAND = {
  name: "Product",
  url: "your.product",
  colors: {
    light: "#F4F0E8",
    dark: "#0E0E0C",
    ink: "#0E0E0C",
    accent: "#EE6018",
    lineLight: "#D6CEBE",
    lineDark: "#3A3934",
    secondaryLight: "#6E6A62",
    secondaryDark: "#A39E93",
    paper: "#FBF9F4",
    surfaceDark: "#1A1A17",
    trackLight: "#E6E0D3",
  },
  fonts: { sans: sans.fontFamily, mono: mono.fontFamily, serif: serif.fontFamily },
  mark: {
    viewBox: "0 0 100 100",
    path: "M0 0H100V100H0Z M32 32V68H68V32Z",
  },
} as const;

export const C = BRAND.colors;
export const F = BRAND.fonts;
export { FPS };
export const W = 1920;
export const H = 1080;
export const T = {
  numeral: 200, display: 168, headline: 120, thesis: 104, title: 64,
  sub: 44, body: 36, monoLg: 40, mono: 30, meta: 26, floor: 24,
} as const;
export const TRACK = {
  numeral: -0.05, display: -0.045, headline: -0.04, title: -0.03, sub: -0.02, body: -0.01,
} as const;
export const GRID = { margin: 120, gutter: 24, col: 118, right: 1800, top: 96, bottom: 984 } as const;
export const colX = (column: number) => GRID.margin + column * (GRID.col + GRID.gutter);
export const spanW = (columns: number) => columns * GRID.col + (columns - 1) * GRID.gutter;
export const HAIR = 2;
export const SHADOW_PAPER = "0 1px 2px rgba(14,14,12,0.06), 0 18px 40px -18px rgba(14,14,12,0.28)";
export const DUR = { enter: 21, exit: 14, morph: 33, stagger: 4, hold: 24 } as const;
export const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);
export const EASE_IN = Easing.bezier(0.7, 0, 0.84, 0);
export const EASE_IN_OUT = Easing.bezier(0.65, 0, 0.35, 1);
export const tween = (frame: number, start: number, dur: number, easing = EASE_OUT) =>
  interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing,
  });
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const settle = (frame: number, start: number, fps = FPS, stiffness = 120) =>
  spring({ frame: frame - start, fps, config: { damping: 2 * Math.sqrt(stiffness), stiffness, mass: 1 } });
