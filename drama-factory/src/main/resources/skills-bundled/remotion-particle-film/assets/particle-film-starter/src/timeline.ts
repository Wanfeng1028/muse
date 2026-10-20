/**
 * Timeline, morph engine and camera language.
 *
 * The film is NOT a set of scenes. It is one population of particles whose
 * TARGET DISTRIBUTION changes over time. Every act overlaps the next with a
 * per-particle staggered interpolation, so each state visibly grows out of the
 * previous one.
 */

import {
  BLACKOUT,
  FINALE,
  SINGULARITY_GROWTH,
  SINGULARITY_T0,
  STATE,
} from "./config";

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const smooth = (v: number) => {
  const x = clamp01(v);
  return x * x * (3 - 2 * x);
};
const smoothRange = (v: number, a: number, b: number) => smooth((v - a) / (b - a));

// ---------------------------------------------------------------------------
// Act structure
// ---------------------------------------------------------------------------

export type Segment = {
  /** Target distribution this act settles into. */
  readonly state: number;
  readonly start: number;
  readonly end: number;
  /** Seconds spent morphing out of the previous distribution. */
  readonly blend: number;
};

/**
 * Act map (seconds, 60 FPS, total 60s):
 *  0.0 -  6.5  I    漫天星辰
 *  6.5 - 15.5  II   粒子法阵 / 星球形成   (ring -> multi ring -> sphere)
 * 15.5 - 22.0  III  星球增殖
 * 22.0 - 30.0  IV   粒子星系              (single galaxy -> galaxy cluster)
 * 30.0 - 38.0  V    隐藏的棋局 19x19
 * 38.0 - 43.0  VI   镜头冲向天元 (fast dolly)
 * 43.0 - 47.5  VII  黑洞出现 / 吸积盘
 * 47.5 - 50.0  VIII 吞噬宇宙
 * 50.0 - 51.5  IX   黑暗
 * 51.5 - 53.4  X    奇点
 * 53.4 - 56.2  XI   宇宙重生
 * 56.2 - 60.0  XII  天元
 */
export const SEGMENTS: readonly Segment[] = [
  { state: STATE.STARFIELD, start: 0.0, end: 6.5, blend: 0 },
  { state: STATE.RING, start: 6.5, end: 9.0, blend: 2.0 },
  { state: STATE.RINGS, start: 9.0, end: 12.0, blend: 2.0 },
  { state: STATE.SPHERE, start: 12.0, end: 15.5, blend: 2.5 },
  { state: STATE.PLANETS, start: 15.5, end: 22.0, blend: 3.0 },
  { state: STATE.GALAXY, start: 22.0, end: 25.5, blend: 2.5 },
  { state: STATE.GALAXIES, start: 25.5, end: 30.0, blend: 3.0 },
  { state: STATE.GRID, start: 30.0, end: 38.0, blend: 5.0 },
  { state: STATE.BLACKHOLE, start: 38.0, end: 50.0, blend: 4.0 },
  { state: STATE.SINGULARITY, start: 50.6, end: 53.6, blend: 1.2 },
  { state: STATE.WAVE, start: 53.6, end: 56.2, blend: 1.5 },
  { state: STATE.TEXT, start: 56.2, end: 60.0, blend: 2.4 },
];

export type MorphState = {
  /** Distribution being left. */
  readonly a: number;
  /** Distribution being approached. */
  readonly b: number;
  /** Global progress 0..1 (per-particle staggering happens on the GPU). */
  readonly w: number;
};

export const resolveStates = (t: number): MorphState => {
  for (let i = 1; i < SEGMENTS.length; i++) {
    const s = SEGMENTS[i];
    const lo = s.start - s.blend * 0.65;
    const hi = s.start + s.blend * 0.35;
    if (t >= lo && t < hi) {
      return { a: SEGMENTS[i - 1].state, b: s.state, w: smooth((t - lo) / (hi - lo)) };
    }
  }
  for (let i = SEGMENTS.length - 1; i >= 0; i--) {
    if (t >= SEGMENTS[i].start) {
      return { a: SEGMENTS[i].state, b: SEGMENTS[i].state, w: 1 };
    }
  }
  return { a: SEGMENTS[0].state, b: SEGMENTS[0].state, w: 1 };
};

// ---------------------------------------------------------------------------
// Monotone cubic tracks (no overshoot -> the camera never wobbles backwards)
// ---------------------------------------------------------------------------

type Key = readonly [number, number];

const buildTrack = (keys: readonly Key[]) => {
  const n = keys.length;
  const d: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    d.push((keys[i + 1][1] - keys[i][1]) / (keys[i + 1][0] - keys[i][0]));
  }
  const m: number[] = new Array(n).fill(0);
  m[0] = d[0];
  m[n - 1] = d[n - 2];
  for (let i = 1; i < n - 1; i++) {
    m[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
  }
  for (let i = 0; i < n - 1; i++) {
    if (d[i] === 0) {
      m[i] = 0;
      m[i + 1] = 0;
      continue;
    }
    const a = m[i] / d[i];
    const b = m[i + 1] / d[i];
    const s = a * a + b * b;
    if (s > 9) {
      const tau = 3 / Math.sqrt(s);
      m[i] = tau * a * d[i];
      m[i + 1] = tau * b * d[i];
    }
  }
  return (t: number): number => {
    if (t <= keys[0][0]) return keys[0][1];
    if (t >= keys[n - 1][0]) return keys[n - 1][1];
    let i = 0;
    while (i < n - 2 && t > keys[i + 1][0]) i++;
    const h = keys[i + 1][0] - keys[i][0];
    const s = (t - keys[i][0]) / h;
    const s2 = s * s;
    const s3 = s2 * s;
    return (
      (2 * s3 - 3 * s2 + 1) * keys[i][1] +
      (s3 - 2 * s2 + s) * h * m[i] +
      (-2 * s3 + 3 * s2) * keys[i + 1][1] +
      (s3 - s2) * h * m[i + 1]
    );
  };
};

// ---------------------------------------------------------------------------
// Camera language: ONE continuous move, slow forward -> long pull back ->
// fast dolly in -> locked -> static -> slow outward.
// ---------------------------------------------------------------------------

const CAMERA_DISTANCE = buildTrack([
  [0.0, 760],
  [6.5, 280],
  [9.0, 195],
  [12.0, 160],
  [15.5, 120],
  [22.0, 700],
  [25.5, 1400],
  [30.0, 2900],
  [38.0, 3400],
  [39.3, 3300],
  [40.3, 3020],
  [41.3, 2520],
  [42.2, 1600],
  // The dolly overshoots into the flow and then settles back, which is the only
  // way the whole accretion vortex ever fits in frame - and the whole vortex is
  // the point of the act.
  [43.0, 520],
  [44.4, 700],
  [47.5, 780],
  // Final plunge: the camera accelerates into the horizon while the funnel is
  // dragging itself in, so the last second reads as a dive, not a fade.
  [48.4, 640],
  [49.1, 380],
  [49.45, 170],
  [49.7, 40],
  [51.2, 100],
  [53.4, 46],
  [56.2, 1150],
  [60.0, 900],
]);

const CAMERA_FOV = buildTrack([
  [0.0, 45],
  [37.0, 45],
  [39.5, 50],
  [41.5, 60],
  [43.0, 52],
  [45.0, 46],
  [48.4, 46],
  [49.6, 58],
  [51.2, 45],
  [60.0, 45],
]);

/** Characteristic world scale of the active distribution. Drives turbulence
 * amplitude and point sizing so the film keeps a consistent feel even though
 * the subject spans 2 units (singularity) to ~1200 units (galaxy cluster). */
const SCENE_SCALE = buildTrack([
  [0.0, 620],
  [6.5, 28],
  [15.5, 28],
  [22.0, 150],
  [25.5, 90],
  [30.0, 640],
  [38.0, 640],
  [47.5, 180],
  [50.0, 70],
  [50.6, 2.4],
  [53.6, 0.5],
  [54.4, 420],
  [56.2, 1200],
  // The finished title needs a little room to breathe: enough turbulence that
  // the swarm keeps moving, nowhere near enough to break the strokes.
  [57.2, 150],
  [60.0, 150],
]);

const POINT_SIZE = buildTrack([
  [0.0, 2.1],
  [6.5, 2.3],
  [15.5, 2.2],
  [22.0, 2.0],
  [25.5, 2.35],
  [30.0, 2.7],
  [38.0, 2.5],
  [47.5, 2.1],
  [50.6, 3.4],
  [53.6, 3.6],
  [54.4, 2.4],
  [56.2, 2.0],
  [57.4, 2.7],
  [60.0, 2.6],
]);

const EXPOSURE = buildTrack([
  [0.0, 0.55],
  [3.5, 0.95],
  [6.5, 1.0],
  [24.0, 1.05],
  [28.0, 1.25],
  [34.0, 1.25],
  [38.0, 1.0],
  [42.0, 1.08],
  [43.0, 0.95],
  [47.5, 1.0],
  [48.6, 1.12],
  [49.6, 1.35],
  [50.5, 1.25],
  [51.05, 1.0],
  [53.6, 1.15],
  [55.0, 1.0],
  [56.2, 1.05],
  [58.0, 0.96],
  [59.3, 1.05],
  [60.0, 1.0],
]);

/** Bloom is the difference between "grey dust" and "stars": the starfield wants
 * a low threshold so every hero star carries a halo, the planet wants a high
 * one so its lit hemisphere does not turn into a white blob. */
const BLOOM_THRESHOLD = buildTrack([
  [0.0, 0.15],
  [6.5, 0.14],
  [9.0, 0.22],
  [12.0, 0.30],
  [15.5, 0.30],
  [22.0, 0.28],
  [30.0, 0.30],
  [38.0, 0.26],
  [47.5, 0.28],
  [50.6, 0.18],
  [53.6, 0.22],
  [56.2, 0.26],
  [58.6, 0.24],
  [59.3, 0.16],
  [60.0, 0.16],
]);

export type FrameState = {
  readonly time: number;
  readonly stateA: number;
  readonly stateB: number;
  readonly blend: number;
  readonly camPos: readonly [number, number, number];
  readonly camTarget: readonly [number, number, number];
  readonly fov: number;
  readonly opacity: number;
  readonly bloom: number;
  readonly scale: number;
  readonly pointSize: number;
  readonly exposure: number;
  readonly blackHole: number;
  readonly reveal: number;
  readonly streak: number;
  /** Orbital motion-blur weight of the accretion flow (0..1). */
  readonly swirl: number;
  readonly gather: number;
  readonly burst: number;
};

export const computeFrameState = (time: number): FrameState => {
  const { a, b, w } = resolveStates(time);

  const distance = CAMERA_DISTANCE(time);
  const fov = CAMERA_FOV(time);

  // Handheld drift, only while the camera is "exploring". It fades out before
  // the dolly so the rush into the centre stays clean and locked - and it also
  // stops for act II, so the collapse and the planet build happen dead centre.
  const locked =
    smoothRange(time, 5.6, 7.2) * (1 - smoothRange(time, 15.2, 17.6));
  const drift = (1 - smoothRange(time, 36.5, 43.0)) * (1 - locked);
  const dx = Math.sin(time * 0.19) * 0.11 * drift;
  const dy = Math.cos(time * 0.23) * 0.085 * drift;
  const camTarget: [number, number, number] = [
    -dx * distance * 0.5,
    -dy * distance * 0.5,
    0,
  ];
  const camPos: [number, number, number] = [
    dx * distance * 0.5,
    dy * distance * 0.5,
    distance,
  ];

  // The cut is not a fade: the frame survives until the funnel is gone and
  // then switches off inside a fifth of a second.
  const opacity =
    time < BLACKOUT.start
      ? 1
      : time < SINGULARITY_T0
        ? 1 - smoothRange(time, BLACKOUT.start, BLACKOUT.start + 0.2)
        : smoothRange(time, SINGULARITY_T0, SINGULARITY_T0 + 0.3);

  // The singularity lights up one particle at a time: 1 -> a few -> dozens ->
  // thousands -> the full core.
  const reveal =
    time < SINGULARITY_T0
      ? 1
      : Math.pow(
          clamp01((time - SINGULARITY_T0) / SINGULARITY_GROWTH),
          4.5,
        );

  // Accretion accent: thin blue-white rim just outside the event horizon.
  const blackHole = smoothRange(time, 36.0, 40.0) * (1 - smoothRange(time, 49.7, 50.2));

  // Radial streak intensity. Two windows: the fast dolly that dives at the
  // hole, and the final plunge, where every surviving particle is dragged down
  // the same radius and the frame becomes a starburst.
  const streak =
    smoothRange(time, 39.0, 41.8) * (1 - smoothRange(time, 42.6, 43.6)) +
    smoothRange(time, 48.3, 49.68) * 1.2;

  // Orbital motion blur. Accretion is fast, so a single point per particle per
  // frame would strobe; this drives the per-particle trail along its own
  // velocity and is what turns concentric rings into moving matter.
  const swirl = smoothRange(time, 36.4, 39.6) * (1 - smoothRange(time, 49.42, 49.94));

  // Final beat: ONE restrained contraction of the whole title. Nothing is
  // picked out, nothing explodes - the swarm simply breathes inward, the
  // highlight rolls off, and the last frame is black.
  const gather = smoothRange(time, FINALE.start, FINALE.start + 0.5);
  const burst = smoothRange(time, FINALE.start + 0.56, FINALE.end - 0.08);
  const finalFade = 1 - smoothRange(time, FINALE.end - 0.12, FINALE.end - 0.01);

  return {
    time,
    stateA: a,
    stateB: b,
    blend: w,
    camPos,
    camTarget,
    fov: (fov * Math.PI) / 180,
    opacity: opacity * finalFade,
    bloom: BLOOM_THRESHOLD(time),
    scale: SCENE_SCALE(time),
    pointSize: POINT_SIZE(time),
    exposure: EXPOSURE(time),
    blackHole,
    reveal,
    streak,
    swirl,
    gather,
    burst,
  };
};
