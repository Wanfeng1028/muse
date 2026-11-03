/**
 * GPU shaders.
 *
 * Everything visual is produced here from a single particle population:
 * no textures, no image assets, no meshes. Each particle evaluates two of the
 * twelve procedural target distributions and interpolates between them, so the
 * universe is continuously re-computing its own shape.
 */

import {
  ACCRETE_DUR,
  ACCRETE_T0,
  ACCRETION_TRAIL,
  BLACKHOLE_T0,
  DISK_OUTER,
  DISK_TILT_END,
  DISK_TILT_START,
  GALAXY_COUNT,
  GRID_N,
  GRID_SPACING,
  HORIZON_RADIUS,
  PLUNGE_DUR,
  PLUNGE_T0,
  PLANET_DUR,
  PLANET_SPIN,
  PLANET_T0,
  PLANET_TILT,
  PLANET_COUNT,
  RINGS_DUR,
  RINGS_T0,
  SPHERE_RADIUS,
  STAR_BAND_SHARE,
  STAR_FIELD_INNER,
  STAR_FIELD_OUTER,
  WAVE_RADIUS,
  WAVE_T0,
} from "../config";

const f = (v: number) => v.toFixed(6);

const DEFINES = /* glsl */ `
#define PLANET_COUNT ${f(PLANET_COUNT)}
#define GALAXY_COUNT ${f(GALAXY_COUNT)}
#define GRID_N ${f(GRID_N)}
#define GRID_SPACING ${f(GRID_SPACING)}
#define SPHERE_RADIUS ${f(SPHERE_RADIUS)}
#define STAR_INNER ${f(STAR_FIELD_INNER)}
#define STAR_OUTER ${f(STAR_FIELD_OUTER)}
#define STAR_BAND ${f(STAR_BAND_SHARE)}
#define ACCRETE_T0 ${f(ACCRETE_T0)}
#define ACCRETE_DUR ${f(ACCRETE_DUR)}
#define RINGS_T0 ${f(RINGS_T0)}
#define RINGS_DUR ${f(RINGS_DUR)}
#define PLANET_T0 ${f(PLANET_T0)}
#define PLANET_DUR ${f(PLANET_DUR)}
#define PLANET_TILT ${f(PLANET_TILT)}
#define PLANET_SPIN ${f(PLANET_SPIN)}
#define HORIZON ${f(HORIZON_RADIUS)}
#define DISK_OUTER ${f(DISK_OUTER)}
#define BLACKHOLE_T0 ${f(BLACKHOLE_T0)}
#define DISK_TILT_START ${f(DISK_TILT_START)}
#define DISK_TILT_END ${f(DISK_TILT_END)}
#define PLUNGE_T0 ${f(PLUNGE_T0)}
#define PLUNGE_DUR ${f(PLUNGE_DUR)}
#define TRAIL_SECONDS ${f(ACCRETION_TRAIL)}
#define WAVE_T0 ${f(WAVE_T0)}
#define WAVE_R ${f(WAVE_RADIUS)}
/* World-space depth of the finished particle title. */
#define GLYPH_DEPTH 30.0
`;

export const POINT_VERT = `#version 300 es
precision highp float;
${DEFINES}

layout(location = 0) in vec4 aSeed;
layout(location = 1) in float aIndex;
layout(location = 2) in float aBirth;

uniform mat4 uViewProj;
uniform vec3 uCamPos;
uniform float uTime;
uniform float uStateA;
uniform float uStateB;
uniform float uBlend;
uniform float uStagger;
uniform float uPointSize;
uniform float uOpacity;
uniform float uReveal;
uniform float uTurbAmp;
uniform float uFlowScale;
uniform float uExposure;
uniform float uBlackHole;
uniform float uStreak;
uniform float uSwirl;
uniform float uTapIndex;
uniform float uTaps;
uniform float uGather;
uniform float uBurst;
uniform float uParticleCount;
uniform sampler2D uGlyph;
uniform float uGlyphCount;
uniform float uGlyphW;
uniform float uGlyphH;
uniform float uGlyphJitter;

out vec3 vColor;
out float vAlpha;

const float TAU = 6.28318530718;

float h1(float n) { return fract(sin(n * 127.1 + 311.7) * 43758.5453123); }
float h2(float n) { return fract(sin(n * 269.5 + 183.3) * 43758.5453123); }
float h3(float n) { return fract(sin(n * 419.2 + 371.9) * 43758.5453123); }

vec3 rotX(vec3 p, float a) {
  float c = cos(a), s = sin(a);
  return vec3(p.x, c * p.y - s * p.z, s * p.y + c * p.z);
}
vec3 rotY(vec3 p, float a) {
  float c = cos(a), s = sin(a);
  return vec3(c * p.x + s * p.z, p.y, -s * p.x + c * p.z);
}
vec3 rotZ(vec3 p, float a) {
  float c = cos(a), s = sin(a);
  return vec3(c * p.x - s * p.y, s * p.x + c * p.y, p.z);
}

vec3 sphereDir(float a, float b) {
  float u = a * 2.0 - 1.0;
  float phi = b * TAU;
  float r = sqrt(max(0.0, 1.0 - u * u));
  return vec3(r * cos(phi), u, r * sin(phi));
}

/* Cheap 3-octave trig noise over a direction. Used as the planet's "terrain":
   it belongs to the surface, so it rotates with the planet instead of sliding
   over it. */
float dirNoise(vec3 d) {
  return sin(d.x * 2.9 + 1.7) * sin(d.y * 2.3 - 0.8) * sin(d.z * 3.1 + 2.2)
    + 0.48 * sin(d.x * 5.7 - 0.4) * sin(d.y * 6.1 + 1.3) * sin(d.z * 5.3 - 1.9)
    + 0.22 * sin(d.x * 11.3 + 2.1) * sin(d.y * 10.7 - 2.4) * sin(d.z * 12.1 + 0.6);
}

/* Three octaves of a divergence-free trigonometric field: a cheap curl-like
   velocity field that keeps its detail at every scale of the film. */
vec3 flowField(vec3 p, float t, float fs) {
  vec3 q = p / (fs * 9.0);
  vec3 v = vec3(
    sin(q.y * 1.7 + t * 0.21) * cos(q.z * 1.3 - t * 0.17),
    sin(q.z * 1.9 - t * 0.19) * cos(q.x * 1.5 + t * 0.13),
    sin(q.x * 1.6 + t * 0.23) * cos(q.y * 1.4 - t * 0.15));
  vec3 q2 = p / (fs * 2.4) + 7.0;
  v += 0.42 * vec3(
    sin(q2.y * 1.13 - t * 0.37 + 1.3),
    sin(q2.z * 1.31 + t * 0.31 + 2.1),
    sin(q2.x * 1.21 - t * 0.41 + 4.7));
  vec3 q3 = p / (fs * 0.9) + 23.0;
  v += 0.15 * vec3(
    sin(q3.y * 1.7 + t * 0.9),
    sin(q3.z * 1.6 - t * 0.8),
    sin(q3.x * 1.8 + t * 1.1));
  return v;
}

// --- act 1 : 无序星空 -------------------------------------------------------
/* Two populations share one buffer: a deep shell that wraps around the camera
   so the frame is never empty, and a clumpy, flattened band that reads as a
   galaxy seen from inside. Everything is a pure function of the seed. */
vec3 stStarfield(vec4 s) {
  float deep = STAR_INNER + (STAR_OUTER - STAR_INNER) * pow(s.x, 0.55);
  vec3 field = sphereDir(s.y, s.z) * deep;

  float a = s.y * TAU;
  float r = 140.0 + 980.0 * pow(s.x, 0.62);
  float clump =
    0.62
    + 0.40 * sin(a * 2.0 + r * 0.0060)
    + 0.22 * sin(a * 5.0 - r * 0.0115)
    + 0.10 * sin(a * 11.0 + r * 0.0260);
  r *= clamp(clump, 0.28, 1.62);
  float h = s.z * 2.0 - 1.0;
  h = sign(h) * pow(abs(h), 2.9);
  vec3 band = rotX(vec3(cos(a) * r, h * 150.0, sin(a) * r), 0.13);

  return mix(field, band, 1.0 - step(STAR_BAND, s.w));
}

/* Act II opener: every particle falls in along a logarithmic spiral, and each
   one starts falling at its own moment, so the cloud shells itself into a
   vortex instead of shrinking as one rigid object. */
vec3 stAccrete(vec4 s, float t) {
  float tau = clamp((t - ACCRETE_T0 - 0.95 * s.w) / ACCRETE_DUR, 0.0, 1.0);
  float k = 1.0 - pow(1.0 - tau, 3.0);
  float rStart = 260.0 + 980.0 * s.x;
  // knots of density left over from the collapse: the ring is not uniform
  float knot = 1.0
    + 0.055 * sin(s.y * TAU * 3.0 + 0.7)
    + 0.030 * sin(s.y * TAU * 7.0 + 2.1);
  float rLand = (33.0 + 4.5 * (s.z - 0.5) + 5.0 * (s.w - 0.5)) * knot;
  float r = mix(rStart, rLand, k * k * (3.0 - 2.0 * k));
  float a = s.y * TAU + k * (0.34 + 0.62 * s.w) * TAU;
  float th = mix(260.0, 4.0, k) * (s.w - 0.5);
  return rotX(vec3(cos(a) * r, sin(a) * r, th), 0.72 + 0.18 * (s.z - 0.5));
}

/* Act II, second beat: the disc does not jump to a sphere - the particles walk
   their latitude up from the equator, so the ring visibly wraps itself shut.
   Radius is continuous with the ring it came from, so nothing flies backwards. */
vec3 stRings(vec4 s, float t) {
  float tau = clamp((t - RINGS_T0 - 0.6 * s.w) / RINGS_DUR, 0.0, 1.0);
  float k = tau * tau * (3.0 - 2.0 * tau);
  float phi = (s.z * 2.0 - 1.0) * mix(0.18, 1.0, k) * (TAU * 0.25);
  float a = s.w * TAU + k * (0.28 + 0.50 * s.x) * TAU;
  float rad = mix(34.0, SPHERE_RADIUS, k) * (0.93 + 0.155 * s.y);
  vec3 p = vec3(cos(a) * cos(phi), sin(phi), sin(a) * cos(phi)) * rad;
  return rotX(p, 0.72 - 0.32 * k);
}

/* The planet: a shell that is solid enough to occlude its own far side, spun
   about a tilted axis, with a per-particle terrain value that rotates with the
   surface and a thin atmosphere shell on top. */
vec3 stSphere(vec4 s, float t) {
  float tau = clamp((t - PLANET_T0 - 0.5 * s.w) / PLANET_DUR, 0.0, 1.0);
  float k = 1.0 - pow(1.0 - tau, 2.2);

  vec3 loc = sphereDir(s.x, s.y);
  float terrain = dirNoise(loc * 1.15);
  float atmo = step(0.90, s.w);
  float shell = pow(s.z, 0.42);
  float radius = SPHERE_RADIUS
    * mix(0.20, 1.0, k)
    * mix(0.74, 1.0, shell)
    * (1.0 + 0.022 * terrain)
    * mix(1.0, 1.075, atmo);

  vec3 n = rotX(rotY(loc, t * PLANET_SPIN + s.z * 0.06), PLANET_TILT);
  return n * radius;
}

// --- act 3 : one planet becomes many --------------------------------------
vec3 planetCenter(float i) {
  // hash-scattered inside a ball: no lattice, no visible spiral order
  vec3 d = sphereDir(h1(i * 12.9898 + 1.0), h2(i * 78.233 + 2.0));
  float rad = 152.0 * pow(h3(i * 39.425 + 3.0), 0.42);
  return vec3(d.x, d.y * 0.86, d.z) * rad;
}
float planetRadius(float i) { return 5.5 + 6.5 * h2(i * 2.3 + 5.0); }
float planetBirth(float i) { return 15.9 + 4.6 * fract(i * 0.6180339887); }

vec3 stPlanets(vec4 s, float t) {
  float id = floor(s.x * PLANET_COUNT);
  float grow = smoothstep(planetBirth(id), planetBirth(id) + 1.5, t);
  float r = planetRadius(id) * mix(0.04, 1.0, grow) * pow(s.w, 1.5);
  return planetCenter(id) + sphereDir(s.y, s.z) * r;
}

// --- acts 4 + 5 : spiral galaxies, then a field of them, then the board -----
vec3 spiralLocal(vec4 s, float rMax, float arms, float twist) {
  if (s.w < 0.2) {
    float r = rMax * 0.22 * pow(s.z, 0.8);
    return sphereDir(s.x, s.y) * r;
  }
  float r = rMax * (0.06 + 0.94 * pow(s.x, 0.62));
  float arm = floor(s.y * arms);
  float a = arm * (TAU / arms) + r * twist + (s.z - 0.5) * 0.52 + sin(r * 0.5) * 0.16;
  float th = rMax * (0.045 + 0.15 * exp(-r / (rMax * 0.45)));
  return vec3(cos(a) * r, sin(a) * r, (s.w - 0.5) * th * 2.0);
}

vec3 stGalaxy(vec4 s) {
  return rotX(spiralLocal(s, 62.0, 2.0, 0.1216), 0.95);
}

/* A cluster is hierarchical, and the hierarchy is wildly unequal: a handful of
   giants hold most of the particles, a swarm of mid-size spirals fills the
   volume, and what is left is a thin intra-cluster haze. That inequality - not
   the raw number of galaxies - is what makes a field of galaxies read as
   "cosmic scale" instead of as luminous noise. */
#define HERO_GALAXIES 6.0
#define MID_GALAXIES 54.0
#define CLUSTER_R 820.0

vec3 clusterNode(float gi) {
  return h1(gi * 5.77 + 3.1) < 0.5
    ? vec3(-200.0, 74.0, -128.0)
    : vec3(252.0, -96.0, 188.0);
}

/* The giants are placed, not scattered: they are the landmarks the shot reads
   at every distance, so they spread through the volume and anchor the two
   cluster cores. */
vec3 heroAnchor(float gi) {
  float a = gi * (TAU / HERO_GALAXIES) + 0.62;
  float r = 300.0 + 250.0 * h1(gi * 3.71 + 1.9);
  vec3 p = vec3(cos(a) * r, (h2(gi * 4.93 + 2.7) - 0.5) * 520.0, sin(a) * r);
  return mix(p, clusterNode(gi), 0.26 + 0.24 * h1(gi * 8.33 + 5.5));
}

/* Everything else sits in a lumpy, flattened cloud - nodes and filaments, not
   a uniform ball - so the cluster has structure at its largest scale too. */
vec3 cloudAnchor(float gi) {
  vec3 d = sphereDir(h1(gi * 1.371 + 0.5), h2(gi * 2.917 + 17.5));
  float r = CLUSTER_R * pow(h3(gi * 4.113 + 91.5), 0.58);
  float lobe = 0.62 + 0.38 * sin(d.x * 2.7 + d.z * 2.3 + 1.1);
  vec3 p = vec3(d.x, d.y * 0.66, d.z) * r * lobe;
  p = mix(p, clusterNode(gi), 0.22 + 0.26 * h2(gi * 6.19 + 8.3));
  p += (vec3(h1(gi * 9.13), h2(gi * 9.71), h3(gi * 9.37)) - 0.5) * 58.0;
  return p;
}

float galaxyId(vec4 s, float misc) {
  if (misc < 0.34) return floor(s.x * HERO_GALAXIES);
  if (misc < 0.72) return HERO_GALAXIES + floor(s.x * MID_GALAXIES);
  return -1.0;
}

/* One galaxy, built from however many particles its tier was given. 'f' is the
   particle's place along the population that owns this galaxy - crucially NOT
   the raw seed x, which is more or less constant inside a single galaxy and
   would flatten the bulge into a ring. */
vec3 galaxyBody(vec4 s, float f, float rMax, float arms, float wrap) {
  if (s.w < 0.22) {
    // bulge: a compact, round, bright knot
    vec3 d = sphereDir(s.y, s.z);
    return d * (rMax * 0.19 * pow(fract(s.w * 4.55), 0.7));
  }
  // disc: logarithmic arms, thin, flaring outwards
  float disc = (s.w - 0.22) / 0.78;
  /* Scatter across the arm as well as along it, or a galaxy built from a few
     hundred points draws itself as a wire frame instead of a body. */
  float rk = fract(s.y * 7.31 + s.w * 3.17);
  float r = rMax * (0.10 + 0.90 * pow(f, 0.58)) * (0.86 + 0.28 * rk);
  float arm = floor(s.y * arms);
  float a = arm * (TAU / arms) + (r / max(rMax, 1.0)) * wrap + (s.z - 0.5) * 0.46;
  float th = rMax * (0.05 + 0.13 * exp(-r / (rMax * 0.5))) * (0.7 + 0.6 * rk);
  return vec3(cos(a) * r, sin(a) * r, (disc - 0.5) * th * 2.0);
}

/* Every galaxy is spun and tipped into its own orientation, so no two of them
   present the same face to the camera. */
vec3 galaxyOriented(vec3 p, float gi, float tip) {
  float a1 = h1(gi * 11.7 + 2.3) * TAU;
  float a2 = (h2(gi * 13.1 + 5.9) - 0.5) * tip;
  float a3 = h3(gi * 17.3 + 7.7) * TAU;
  return rotZ(rotX(rotY(p, a1), a2), a3);
}

vec3 stGalaxies(vec4 s, float misc) {
  if (misc >= 0.72) {
    /* Intra-cluster medium: a dim, clumpy haze that fills the volume between
       the galaxies. Without it a cluster is isolated dots floating in a void;
       with it there is depth behind and between the spirals. */
    vec3 d = sphereDir(s.x, s.y);
    float r = CLUSTER_R * (0.10 + 0.90 * pow(s.z, 0.5));
    r *= 0.48 + 0.52 * sin(d.x * 2.7 + d.z * 2.3 + 1.1);
    vec3 p = vec3(d.x, d.y * 0.60, d.z) * r;
    p += (vec3(h1(s.w * 91.7), h2(s.w * 87.3), h3(s.w * 79.1)) - 0.5) * 96.0;
    return p;
  }

  float hero = step(misc, 0.34);
  float gi = galaxyId(s, misc);
  float f = hero > 0.5 ? fract(s.x * HERO_GALAXIES) : fract(s.x * MID_GALAXIES);
  float key = h1(gi * 3.11 + 0.7);

  float rMax = mix(18.0 + 30.0 * pow(key, 1.4), 92.0 + 58.0 * key, hero);
  float arms = mix(2.0, 2.0 + step(0.42, h2(gi * 5.23 + 4.4)), hero);
  /* Under one full turn: wind a galaxy up by two turns and the eye stops
     reading a spiral and starts reading concentric rings. */
  float wrap = mix(3.6 + 2.2 * h3(gi * 7.19 + 6.1),
                   4.6 + 2.4 * h3(gi * 7.19 + 6.1), hero);
  float handed = h2(gi * 8.17 + 9.3) < 0.5 ? -1.0 : 1.0;

  vec3 p = galaxyOriented(galaxyBody(s, f, rMax, arms, wrap * handed), gi, 1.75);
  return mix(cloudAnchor(gi), heroAnchor(gi), hero) + p;
}

/* Act VII: the board is never drawn.
   361 galaxies drift into the NEIGHBOURHOOD of a 19x19 lattice, but every node
   is displaced by a large fraction of a cell, every galaxy gets its own size,
   orientation and brightness, the sheet is bent and tipped through the volume
   and its rim is faded out. Close up this is a cluster of galaxies; the order
   only surfaces once the camera has pulled far enough back. */
vec3 stGrid(vec4 s, float misc) {
  float gi = floor(s.x * GALAXY_COUNT);
  float f = fract(s.x * GALAXY_COUNT);
  float col = mod(gi, GRID_N);
  float row = floor(gi / GRID_N);

  float key = h1(gi * 3.11 + 21.7);
  float hero = step(0.92, key);
  /* The nodes have to stay comfortably smaller than a cell. At the pull-back
     distance one cell is roughly fifty pixels wide, so a galaxy allowed to
     grow to the full GRID_SPACING smears into its neighbours and the order
     disappears under its own bodies. */
  float rMax = mix(9.0 + 12.0 * pow(key, 1.3), 26.0 + 16.0 * key, hero);
  float arms = mix(2.0, 2.0 + step(0.45, h2(gi * 5.23 + 24.4)), hero);
  float wrap = (3.2 + 2.0 * h3(gi * 7.19 + 26.1))
    * (h2(gi * 8.17 + 29.3) < 0.5 ? -1.0 : 1.0);

  /* The lattice is a tendency, never a ruler. The displacement has to stay
     under half a cell or the order disappears entirely, and it has to be far
     larger than a dot radius or the order turns into a printed grid; ~1/4 of a
     cell is the window where "they happen to line up" still reads. */
  /* Displacement is a tendency, never a ruler: ~+/-0.17 of a cell. Large
     enough that no dot sits on its mark, small enough that a file still lines
     up when the camera has pulled all the way back. */
  vec2 jit = (vec2(h1(gi * 11.3), h2(gi * 13.7)) - 0.5) * (GRID_SPACING * 0.34);
  vec3 c = vec3((col - 9.0) * GRID_SPACING + jit.x,
                (9.0 - row) * GRID_SPACING + jit.y,
                (h3(gi * 17.1) - 0.5) * 330.0);

  // A slow warp bends the sheet through the volume, so it is neither flat to
  // the lens nor flat in depth.
  c.y += sin(c.x * 0.0031 + 1.1) * 24.0 + cos(c.z * 0.0027) * 12.0;
  c.z += cos(c.y * 0.0035) * 96.0 + sin(c.x * 0.0022) * 54.0;
  c += (vec3(h1(gi * 23.9), h2(gi * 27.1), h3(gi * 31.3)) - 0.5)
    * vec3(14.0, 14.0, 150.0);

  vec3 p = galaxyOriented(galaxyBody(s, f, rMax, arms, wrap), gi, 2.2);

  // The whole structure is tipped in space: a receding plane is a place, a
  // fronto-parallel array is a chart.
  return rotZ(rotX(c + p, 0.40), 0.15);
}

// --- acts 8 + 9 : real accretion flow, not a ring that thickens -------------
vec3 bhPosition(vec4 s, float t) {
  float r0 = HORIZON * 1.06 + (DISK_OUTER - HORIZON) * pow(s.x, 0.62);

  /* Not every particle rides a circular orbit: a graded fraction fall in along
     steep, nearly radial streams. They are what makes the flow look fed rather
     than painted. */
  float streamer = smoothstep(0.70, 0.98, s.y);

  /* Radial attraction. The disc drains over the whole act instead of in one
     collapse, the streams drain faster than the disc, and every particle has
     its own delay so matter at the same radius is never in lockstep. */
  float seed = fract(s.x * 37.13 + s.y * 11.31 + s.w * 5.77);
  float insp = clamp(
    (t - BLACKHOLE_T0 - 1.5 * seed) / mix(26.0, 15.0, streamer),
    0.0,
    1.0);
  /* The flow stops AT the horizon and piles up there: without this clamp the
     inner disc would drain below the horizon and get culled mid-act, and the
     disc would read as a ring with a hole punched in it. */
  float r = max(r0 * (1.0 - 0.34 * insp), HORIZON * 1.02);

  /* Two spiral density waves wind through the disc: matter in an accretion
     flow arrives in streams, not as a smooth annulus. */
  float th0 = s.z * TAU;
  r *= 1.0 + 0.085 * sin(2.0 * th0 - log(max(r, 1.0)) * 3.6 + 1.7);

  /* Tangential velocity: Omega ~ r^-1.5, so the deeper a particle falls the
     faster it turns. That acceleration is the whole point of the shot. */
  float spinUp = clamp((r0 / max(r, 1.0) - 1.0) * 1.15, 0.0, 3.4);
  float omega = mix(0.16 + 0.30 * spinUp, 0.045, streamer) * TAU;
  float th = th0 + omega * max(t - BLACKHOLE_T0, 0.0);

  /* The funnel is dragged through the horizon in the last second and a half.
     The radius keeps shrinking past the horizon, where the vertex stage stops
     drawing it, so the hole visibly eats the disc instead of the disc parking
     on top of it. */
  float plunge = smoothstep(PLUNGE_T0, PLUNGE_T0 + PLUNGE_DUR, t);
  r *= 1.0 - 0.985 * plunge;

  /* Cool, thick halo far out; a thin, fast, flat inner disc. */
  float thick = (HORIZON * 0.05 + 16.0 * pow(r0 / DISK_OUTER, 1.2))
    * (0.30 + 0.70 * (1.0 - insp));
  float zoff = (s.w - 0.5) * thick * 2.0 * (1.0 - 0.55 * streamer);

  /* The flow opens from a steep, near edge-on line into a readable vortex as
     the disc heats up - a frozen inclination reads as a painted ring. */
  float tilt = mix(DISK_TILT_START, DISK_TILT_END, smoothstep(37.0, 44.5, t));
  return rotX(vec3(cos(th) * r, sin(th) * r, zoff), tilt);
}

vec3 stBlackhole(vec4 s, float t, out vec3 vel) {
  /* The trail is drawn along the real velocity, so it has to be the real
     velocity - tangential and radial at once. Two extra evaluations of a
     cheap closed form beat any hand-tuned fake. */
  const float dt = 0.012;
  vel = (bhPosition(s, t + dt) - bhPosition(s, t - dt)) / (2.0 * dt);
  return bhPosition(s, t);
}

// --- acts 10 + 11 : singularity, then controlled radial emission ------------
vec3 stSingularity(vec4 s) {
  return sphereDir(s.x, s.y) * 1.7 * pow(s.z, 1.5);
}

vec3 stWave(vec4 s, float t) {
  float tau = max(t - WAVE_T0, 0.0);
  /* A shock front, not a fog: the shell is thin, so the burst reads as a
     luminous surface racing out of the singularity - which is the thing the
     title then condenses back out of. */
  float reach = WAVE_R * (1.0 - exp(-1.05 * tau));
  float r = reach * (0.92 + 0.16 * s.y);
  vec3 d = sphereDir(s.x, s.z);
  float squash = 0.62 + 0.38 * (0.5 + 0.5 * cos(s.w * TAU));
  return vec3(d.x * r, d.y * r * squash, d.z * r);
}

// --- act 12 : particle typography ------------------------------------------
vec3 stText(vec4 s, float idxN) {
  float gi = floor(idxN * uGlyphCount);
  float u = (mod(gi, uGlyphW) + 0.5) / uGlyphW;
  float v = (floor(gi / uGlyphW) + 0.5) / uGlyphH;
  vec3 g = texture(uGlyph, vec2(u, v)).xyz;
  /* Scatter in the plane, and give the strokes real depth, so the title is a
     cloud of particles that happens to spell 天元 rather than a flat stencil. */
  g.xy += (vec2(s.x, s.y) - 0.5) * uGlyphJitter;
  g.z = g.z * GLYPH_DEPTH + (s.z - 0.5) * uGlyphJitter;
  return g;
}

vec3 statePos(int id, vec4 s, float idxN, float misc, float t, out vec3 vel) {
  vel = vec3(0.0);
  if (id == 0) return stStarfield(s);
  if (id == 1) return stAccrete(s, t);
  if (id == 2) return stRings(s, t);
  if (id == 3) return stSphere(s, t);
  if (id == 4) return stPlanets(s, t);
  if (id == 5) return stGalaxy(s);
  if (id == 6) return stGalaxies(s, misc);
  if (id == 7) return stGrid(s, misc);
  if (id == 8) return stBlackhole(s, t, vel);
  if (id == 9) return stSingularity(s);
  if (id == 10) return stWave(s, t);
  return stText(s, idxN);
}

void main() {
  float idxN = aIndex / uParticleCount;
  vec4 s = aSeed;
  /* An independent per-particle channel. The four seed channels are already
     spoken for (which galaxy, which arm, which orbit), so extra randomness is
     mixed off all four of them instead of stealing one. */
  float misc = fract(s.x * 71.13 + s.y * 41.77 + s.z * 23.31 + s.w * 57.19);
  int sa = int(uStateA + 0.5);
  int sb = int(uStateB + 0.5);

  vec3 velA = vec3(0.0);
  vec3 velB = vec3(0.0);
  vec3 pa = statePos(sa, s, idxN, misc, uTime, velA);
  vec3 pb = statePos(sb, s, idxN, misc, uTime, velB);

  float stag = fract(s.w * 7.31 + idxN * 3.17);
  float w = clamp((uBlend - stag * uStagger) / max(1.0 - uStagger, 1e-3), 0.0, 1.0);
  w = w * w * (3.0 - 2.0 * w);

  vec3 pos = mix(pa, pb, w);
  vec3 vel = mix(velA, velB, w);

  /* Per-state weights. A structure's own shading follows it in and out of the
     morph exactly the way its position does, so nothing pops. */
  float starW = (sa == 0) ? (1.0 - w) : 0.0;
  float planetW = (sa == 3) ? (1.0 - w) : 0.0;
  float clusterW = (sa == 6) ? (1.0 - w) : 0.0;
  float gridW = (sa == 7) ? (1.0 - w) : 0.0;
  float bhW = (sa == 8) ? (1.0 - w) : 0.0;
  float waveW = (sa == 10) ? (1.0 - w) : 0.0;
  float textW = (sa == 11) ? (1.0 - w) : 0.0;
  if (sb == 0) starW = max(starW, w);
  if (sb == 3) planetW = max(planetW, w);
  if (sb == 6) clusterW = max(clusterW, w);
  if (sb == 7) gridW = max(gridW, w);
  if (sb == 8) bhW = max(bhW, w);
  if (sb == 10) waveW = max(waveW, w);
  if (sb == 11) textW = max(textW, w);
  starW = clamp(starW, 0.0, 1.0);
  planetW = clamp(planetW, 0.0, 1.0);
  clusterW = clamp(clusterW, 0.0, 1.0);
  gridW = clamp(gridW, 0.0, 1.0);
  bhW = clamp(bhW, 0.0, 1.0);
  waveW = clamp(waveW, 0.0, 1.0);
  textW = clamp(textW, 0.0, 1.0);

  // Coherent field: every structure (a planet, a galaxy, a stroke of the
  // glyph) drifts as a whole and keeps its shape. The arrival of the title is
  // damped, so the last morph settles onto the strokes instead of boiling.
  float morphAmp = (1.0 + 2.6 * 4.0 * w * (1.0 - w)) * mix(1.0, 0.45, textW);
  pos += flowField(pos, uTime, uFlowScale) * uTurbAmp * morphAmp;

  // Individual micro turbulence, small enough never to break a structure apart.
  float ph = s.w * TAU + uTime * (0.55 + s.x * 1.1);
  pos += vec3(sin(ph * 1.3), sin(ph * 1.7 + 2.1), sin(ph * 0.9 + 4.2))
    * uTurbAmp * 0.22 * (0.35 + 0.65 * stag);

  /* Orbital motion blur. Accreting matter is fast, so one point per particle
     per frame would strobe; each particle is drawn uTaps times, marching
     backwards along its OWN velocity, so the trails follow the orbit - and the
     radial inflow - instead of being a screen-space smear. */
  if (uTapIndex > 0.0 && uSwirl > 0.001) {
    float sp = length(vel);
    if (sp > 1e-3) {
      float len = min(sp * uSwirl * TRAIL_SECONDS, DISK_OUTER * 0.17);
      pos -= (vel / sp) * (uTapIndex * len);
    }
  }

  // the finished glyph stays alive: a few particles drift off and come back
  if (sb == 11) {
    float escape = step(0.93, fract(s.w * 29.7 + idxN * 7.0));
    float drift = uTime * (0.5 + s.x) + s.y * TAU;
    pos += vec3(sin(drift * 1.7), cos(drift * 1.3), sin(drift * 0.9))
      * escape * uFlowScale * 0.022 * w;
  }

  /* Final beat: ONE restrained contraction of the whole title. Nothing is
     picked out and nothing explodes - the swarm simply breathes inward and the
     highlight lifts a little before the frame goes black. */
  if (uGather > 0.0 || uBurst > 0.0) {
    pos *= 1.0 - 0.15 * uGather - 0.05 * uBurst;
  }

  vec4 clip = uViewProj * vec4(pos, 1.0);
  float radius = length(pos);

  /* The horizon is not painted on: a particle that crosses it is simply not
     drawn any more. The threshold is only the innermost core of the funnel -
     the flow is already held at HORIZON by its own radius law, so this exists
     to swallow the last sliver at the very centre rather than to carve a hole
     out of a disc that is still supposed to be feeding the hole. */
  float outside = mix(1.0, step(HORIZON * 0.08, radius), bhW);

  float born = smoothstep(aBirth * 3.3, aBirth * 3.3 + 0.55, uTime);
  float revealed = step(aBirth, uReveal);
  float alpha = uOpacity * born * outside * revealed;

  if (alpha < 0.002) {
    gl_Position = vec4(0.0, 0.0, 2.0, 1.0);
    gl_PointSize = 1.0;
    vAlpha = 0.0;
    vColor = vec3(0.0);
    return;
  }

  // radial streaks: the dolly into the hole, and then the final plunge, where
  // everything left is on the same radius heading for the same point
  if (uStreak > 0.0) {
    vec2 ndc = clip.xy / max(abs(clip.w), 1e-4);
    ndc *= 1.0 - uStreak * 0.13 * (uTapIndex / max(uTaps - 1.0, 1.0));
    clip.xy = ndc * abs(clip.w);
  }
  gl_Position = clip;

  /* --- star classes ------------------------------------------------------
     A couple of per cent of the population are hero stars and ~40% are
     mid-weight: that spread is what makes a night sky read as a sky instead
     of as grey dust. */
  float cls = fract(s.w * 53.7 + s.x * 11.31 + s.y * 3.7);
  float hero = step(0.978, cls);
  float mid = smoothstep(0.55, 0.965, cls);
  float sizeStar = mix(mix(0.42, 1.35, mid), 3.6, hero);
  float sizeCore = 0.55 + 1.15 * fract(s.w * 17.3 + idxN);
  float sizeVar = mix(sizeCore, sizeStar, starW);

  float depthAtt = clamp(760.0 / max(abs(clip.w), 1.0), 0.45, 1.9);
  /* A planet made of 40k points only reads as a body if the grains are big
     enough to close the surface, so the planet gets its own size boost. */
  gl_PointSize = clamp(
    uPointSize * sizeVar * mix(1.0, depthAtt, 0.5)
      * mix(1.0, 2.05, planetW) * mix(1.0, 1.35, waveW),
    1.0,
    16.0);

  float bright = 0.5 + 0.85 * fract(s.x * 3.7 + s.y * 1.9 + s.z * 0.7);
  float brightStar = mix(0.30, 1.30, mid) + hero * 2.5;
  bright = mix(bright, brightStar, starW);

  vec3 tint = vec3(1.0);
  float solid = 1.0;

  /* --- planet surface ----------------------------------------------------
     Real shading: a soft terminator, a lit limb, terrain that belongs to the
     rotating surface, and a thin atmosphere shell on top of it. */
  if (planetW > 0.002) {
    vec3 n = normalize(pos);
    vec3 lightDir = normalize(vec3(-0.58, 0.60, 0.55));
    vec3 viewDir = normalize(uCamPos - pos);
    float lambert = dot(n, lightDir);
    float lit = clamp((lambert + 0.30) / 1.30, 0.0, 1.0);
    float facing = clamp(dot(n, viewDir), 0.0, 1.0);
    float rim = pow(1.0 - facing, 2.6);

    /* The far hemisphere is culled: additive blending cannot occlude, so the
       only way a sphere of points reads as a solid body is to stop drawing the
       half that is behind it. */
    solid = smoothstep(-0.12, 0.30, dot(n, viewDir));

    vec3 surf = normalize(rotY(rotX(n, -PLANET_TILT), -uTime * PLANET_SPIN));
    float terrain = dirNoise(surf * 1.15);
    float land = smoothstep(-0.04, 0.58, terrain);

    float shade = (0.05 + 0.20 * rim) + 1.05 * pow(lit, 0.80);
    shade *= mix(0.52, 1.28, land);
    shade += rim * 0.85;

    vec3 day = mix(vec3(0.34, 0.41, 0.56), vec3(1.0, 0.96, 0.90), pow(lit, 0.62));
    day = mix(day, vec3(1.0, 0.99, 0.97), land * 0.55);
    tint = mix(vec3(1.0), day + rim * vec3(0.30, 0.44, 0.76), planetW);
    bright = mix(bright, shade * 1.18, planetW);

    float atmo = smoothstep(0.90, 1.0, s.w);
    if (atmo > 0.01) {
      float glow = (0.32 + 0.90 * rim) * (0.25 + 0.75 * lit);
      bright = mix(bright, 0.34 + glow, planetW * atmo);
      tint = mix(tint, vec3(0.46, 0.68, 1.0), planetW * atmo * 0.75);
    }
  }

  /* --- galaxy cluster, and the board it quietly becomes -------------------
     Every galaxy carries its own temperature and luminosity, distant ones are
     dimmed by the haze between us and them, and the board is faded out towards
     its rim so the eye is never handed a rectangle to lock onto. */
  if (clusterW > 0.002 || gridW > 0.002) {
    float gw = max(clusterW, gridW);
    float gid = galaxyId(s, misc);
    float haze = mix(1.0, clamp(3200.0 / max(abs(clip.w), 1.0), 0.42, 1.25), gw);
    if (gid < 0.0) {
      // intra-cluster medium: cold, dim, and structurally unimportant
      bright = mix(bright, 0.34, clusterW);
      tint = mix(tint, vec3(0.60, 0.69, 0.88), clusterW * 0.7);
    } else {
      float temp = h1(gid * 23.7 + 11.3);
      float lum = mix(0.55, 1.70, pow(h2(gid * 29.1 + 3.3), 0.85));
      /* On the board the nodes have to stay within reach of each other's
         brightness, or the eye cannot follow a rank or a file at all. The
         cluster keeps its full spread; the board keeps a narrowed one. */
      lum = mix(lum, 0.86 + 0.40 * pow(h2(gid * 29.1 + 3.3), 0.85), gridW);
      float rimFade = 1.0;
      if (gridW > 0.002) {
        float rim = max(abs(mod(gid, GRID_N) - 9.0),
                        abs(floor(gid / GRID_N) - 9.0)) / 9.0;
        /* A gentle vignette, not a stencil: the outer ranks dim to roughly
         half, which softens the rectangle without erasing two thirds of the
         board the way the old 0.52 cutoff did. */
        rimFade = 1.0 - smoothstep(0.70, 1.25, rim);
      }
      bright = mix(bright, lum * haze * rimFade, gw);
      tint = mix(tint, mix(vec3(0.70, 0.82, 1.0), vec3(1.0, 0.93, 0.80), temp),
                 gw * 0.85);
    }
  }

  /* --- accretion flow -----------------------------------------------------
     Matter in orbit is not a lit ring. The side swinging towards the camera is
     beamed brighter, the inner disc is much hotter than the outer one, and a
     thin hot rim sits right on the horizon. */
  if (bhW > 0.002) {
    float inner = 1.0 - clamp((radius - HORIZON) / max(DISK_OUTER - HORIZON, 1.0),
                              0.0, 1.0);
    vec3 velN = vel / max(length(vel), 1e-4);
    vec3 viewN = normalize(uCamPos - pos);
    float beam = clamp(dot(velN, viewN), -1.0, 1.0);
    float dop = 0.42 + 1.45 * smoothstep(-0.65, 0.90, beam);
    float hotRim = exp(-pow((radius - HORIZON * 1.05) / (HORIZON * 0.14), 2.0));
    bright *= mix(
      1.0,
      dop * (0.80 + 1.6 * hotRim) * (0.75 + 1.5 * pow(inner, 2.0)),
      bhW);
    tint = mix(tint, mix(vec3(1.0, 0.86, 0.62), vec3(0.84, 0.91, 1.0),
                         pow(inner, 0.65)), bhW * 0.9);
  }

  /* --- rebirth front ------------------------------------------------------ */
  if (waveW > 0.002) {
    bright = mix(bright, bright * 2.3 + 0.25, waveW);
    tint = mix(tint, vec3(0.76, 0.86, 1.0), waveW * 0.75);
  }

  /* --- the finished title -------------------------------------------------
     A swarm, not a plate: depth, sparkle and a cool-to-warm spread keep the
     strokes alive after they have formed. */
  if (textW > 0.002) {
    float spark = 0.55 + 1.6 * pow(fract(s.w * 31.7 + idxN * 5.3), 2.0);
    bright = mix(bright, bright * (0.80 + 1.45 * spark), textW);
    float temp = fract(s.z * 7.31 + s.y * 3.11);
    tint = mix(tint, mix(vec3(0.72, 0.84, 1.0), vec3(1.0, 0.95, 0.88), temp),
               textW * 0.9);
  }

  if (uBlackHole > 0.001) {
    float rim = exp(-pow((radius - HORIZON * 1.13) / (HORIZON * 0.2), 2.0));
    bright += uBlackHole * rim * 3.2;
  }
  if (sb == 9) {
    // the first particles of the new universe flicker slowly
    bright *= 0.6 + 0.4 * sin(uTime * 2.3 + s.x * TAU);
  }
  bright *= uExposure * (1.0 + 0.45 * uGather + 0.55 * uBurst);

  vec3 col = mix(
    vec3(1.0, 0.985, 0.955),
    vec3(0.74, 0.85, 1.0),
    smoothstep(0.84, 1.0, fract(s.z * 5.13 + s.w * 2.71)) * 0.85);
  col = mix(col, vec3(0.70, 0.81, 1.0), hero * starW * 0.8);
  col *= tint;

  vColor = col * bright;
  /* With motion-blur taps the particle is drawn several times, so the sample
     is split between them and the total light stays put. */
  vAlpha = (0.20 + 0.30 * sizeVar) * uExposure * mix(1.0, 1.55 * solid, planetW)
    / max(uTaps, 1.0);
}
`;

export const POINT_FRAG = `#version 300 es
precision highp float;

in vec3 vColor;
in float vAlpha;
out vec4 outColor;

void main() {
  vec2 c = gl_PointCoord - 0.5;
  float d2 = dot(c, c);
  if (d2 > 0.25) discard;
  float d = sqrt(d2) * 2.0;
  float core = exp(-d * d * 7.0);
  float halo = exp(-d * d * 2.1) * 0.30;
  float a = (core + halo) * vAlpha;
  outColor = vec4(vColor, a);
}
`;

export const QUAD_VERT = `#version 300 es
precision highp float;
out vec2 vUv;
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  vUv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
`;

export const BRIGHT_FRAG = `#version 300 es
precision highp float;
in vec2 vUv;
uniform sampler2D uScene;
uniform float uThreshold;
out vec4 outColor;
void main() {
  vec3 c = texture(uScene, vUv).rgb;
  float l = max(c.r, max(c.g, c.b));
  float s = clamp((l - uThreshold) / max(1.0 - uThreshold, 1e-4), 0.0, 1.0);
  outColor = vec4(c * s, 1.0);
}
`;

export const BLUR_FRAG = `#version 300 es
precision highp float;
in vec2 vUv;
uniform sampler2D uSource;
uniform vec2 uDirection;
out vec4 outColor;
void main() {
  float w0 = 0.227027;
  float w1 = 0.1945946;
  float w2 = 0.1216216;
  float w3 = 0.054054;
  float w4 = 0.016216;
  vec3 acc = texture(uSource, vUv).rgb * w0;
  acc += texture(uSource, vUv + uDirection * 1.0).rgb * w1;
  acc += texture(uSource, vUv - uDirection * 1.0).rgb * w1;
  acc += texture(uSource, vUv + uDirection * 2.0).rgb * w2;
  acc += texture(uSource, vUv - uDirection * 2.0).rgb * w2;
  acc += texture(uSource, vUv + uDirection * 3.0).rgb * w3;
  acc += texture(uSource, vUv - uDirection * 3.0).rgb * w3;
  acc += texture(uSource, vUv + uDirection * 4.0).rgb * w4;
  acc += texture(uSource, vUv - uDirection * 4.0).rgb * w4;
  outColor = vec4(acc, 1.0);
}
`;

export const COMPOSITE_FRAG = `#version 300 es
precision highp float;
in vec2 vUv;
uniform sampler2D uScene;
uniform sampler2D uBloom;
uniform float uBloomStrength;
uniform float uTime;
uniform vec2 uResolution;
out vec4 outColor;

void main() {
  vec3 col = texture(uScene, vUv).rgb
    + texture(uBloom, vUv).rgb * uBloomStrength;

  // soft highlight roll-off keeps the whites white instead of clipping them
  col = col / (1.0 + col * 0.92);

  vec2 c = (vUv - 0.5) * vec2(uResolution.x / uResolution.y, 1.0);
  float r = length(c);
  col *= 1.0 - smoothstep(0.36, 1.12, r) * 0.72;
  col += vec3(0.0040, 0.0060, 0.0170) * (1.0 - smoothstep(0.0, 0.72, r));

  float g = fract(sin(dot(vUv * uResolution, vec2(12.9898, 78.233)) + uTime * 91.7)
    * 43758.5453);
  col += (g - 0.5) * (1.3 / 255.0);
  outColor = vec4(col, 1.0);
}
`;
