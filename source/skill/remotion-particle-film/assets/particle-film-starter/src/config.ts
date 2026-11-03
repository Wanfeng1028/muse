/**
 * Global configuration for 《天元：宇宙起点》 (TIANYUAN - ORIGIN OF THE UNIVERSE).
 *
 * Everything in this file is deterministic: the same frame always produces the
 * same visual result. No wall-clock time is ever used.
 */

export const FPS = 60;
export const DURATION_IN_FRAMES = FPS * 60;
export const WIDTH = 1080;
export const HEIGHT = 1920;

/** 10k - 50k+, tuned for stable 60 FPS. */
export const PARTICLE_COUNT = 40000;

/** Scene states. The whole film is a single particle population morphing
 * between these target distributions - never a scene cut. */
export const STATE = {
  STARFIELD: 0,
  RING: 1,
  RINGS: 2,
  SPHERE: 3,
  PLANETS: 4,
  GALAXY: 5,
  GALAXIES: 6,
  GRID: 7,
  BLACKHOLE: 8,
  SINGULARITY: 9,
  WAVE: 10,
  TEXT: 11,
} as const;

export const PLANET_COUNT = 64;
export const GALAXY_COUNT = 361;
export const GRID_N = 19;
export const GRID_SPACING = 68;
export const GRID_SPAN = (GRID_N - 1) * GRID_SPACING;

/** World radius of the particle planet (act 2). */
export const SPHERE_RADIUS = 26;

// ---------------------------------------------------------------------------
// Act I + II ("无序星空 -> 粒子聚合 -> 粒子星球")
// ---------------------------------------------------------------------------

/** The deep star shell the camera flies through: inner / outer radius. */
export const STAR_FIELD_INNER = 560;
export const STAR_FIELD_OUTER = 2700;
/** Share of particles that form the dense galactic band (the rest: deep sky). */
export const STAR_BAND_SHARE = 0.50;

/** Seconds at which each collapsing structure has wound itself together. */
export const ACCRETE_T0 = 5.6;
export const ACCRETE_DUR = 2.2;
export const RINGS_T0 = 8.2;
export const RINGS_DUR = 2.6;
export const PLANET_T0 = 10.2;
export const PLANET_DUR = 2.8;

/** Axial tilt (radians) and spin (radians / second) of the particle planet. */
export const PLANET_TILT = 0.40;
export const PLANET_SPIN = 0.32;
/** World radius of the black hole event horizon. */
export const HORIZON_RADIUS = 60;
/** World radius of the outermost accretion orbit. */
export const DISK_OUTER = 282;
/** Time (s) the accretion fall begins (matches the morph into the hole). */
export const BLACKHOLE_T0 = 35.4;
/** Inclination of the accretion flow (radians about the world X axis). The
 * funnel opens from a steep, near edge-on line into a readable vortex as the
 * disc heats up - a frozen ring reading is exactly what we must avoid. */
export const DISK_TILT_START = 1.24;
export const DISK_TILT_END = 0.98;
/** Time (s) the whole funnel is dragged through the horizon. */
export const PLUNGE_T0 = 48.35;
export const PLUNGE_DUR = 1.34;
/** Seconds of orbital motion blur carried by an accreting particle. */
export const ACCRETION_TRAIL = 0.052;
/** Time (s) the rebirth wave is released. */
export const WAVE_T0 = 53.6;
export const WAVE_RADIUS = 1150;
/** Time (s) the singularity starts to light up. */
export const SINGULARITY_T0 = 51.05;
/** Seconds the singularity takes to grow from one particle to the full core. */
export const SINGULARITY_GROWTH = 2.35;
/** Time window (s) of absolute black. The cut is deliberately abrupt: the
 * frame is not faded into black, it is switched off. */
export const BLACKOUT = { start: 49.7, end: 51.05 };
/** Time (s) of the final beat: gather to a point, bloom, cut to black. */
export const FINALE = { start: 59.3, end: 60.0 };

export const FOV_DEG = 45;
export const NEAR = 1;
export const FAR = 20000;
/** Camera distance while 「天元」 is on screen. */
export const FINAL_DIST = 900;

const halfHeightAt = (distance: number) =>
  Math.tan(((FOV_DEG * Math.PI) / 180) / 2) * distance;

/** Width of the particle-glyph quad in world units, so the finished title
 * fills 86% of the portrait frame width. */
export const TEXT_QUAD_WIDTH =
  0.86 * 2 * halfHeightAt(FINAL_DIST) * (WIDTH / HEIGHT);

export const GLYPH_TEXT = "天元";
export const GLYPH_FONT_FILE = "fonts/NotoSansSC-Bold.otf";
export const GLYPH_CANVAS_WIDTH = 2048;
export const GLYPH_TEXTURE_WIDTH = 2048;

/** Deep space background (absolute black -> deep blue black). */
export const BG_CORE = "#01020a";
export const BG_EDGE = "#000000";
