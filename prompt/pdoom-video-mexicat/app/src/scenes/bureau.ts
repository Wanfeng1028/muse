// FIG. 7 `bureau` — "Paperwork". Inverted palette: bone paper, ink, orange accents.
// One long printed document seen by a restless camera:
//   A. Form 7-B (safety evaluation): the lyric is typewritten into the fields; SAFE ENOUGH stamp slams on "reckoned".
//   B. Annex B (MLP schematic): the pulse sweeps forward on "Forward M-L-P", back on "backward" (typeset mirrored,
//      right to left), and "repeat" stutters the last beat x3 (the annex is re-rendered at remapped time).
//   C. Appendix C (the von Neumann architecture, a textbook figure): struck through in orange marker on "obsolete".
//      The hand-off: the next plate's spark comes up its critical path under the page (its light shows through),
//      bursts through on the beat before the cut and burns the page in two as the camera picks up its chase;
//      the halves swing open onto that plate, which is rendered here under the page, line and spark in place.
// Rendering: all ink is drawn on one Canvas2D layer as channel-coded coverage (R = typewriter/pen ink,
// G = printed ink, B = orange ink), composited onto procedural paper by a shader (fibres, ink grain, stamp texture),
// then a burn pass cuts the page along the spark's path and composites the halves over the next plate.
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides } from '../engine/scene';
import { FSPass, Layer2D, W, H, makeRT } from '../engine/gl';
import { DEFAULT_POST, type PostParams } from '../engine/post';
import LeftTurn from './leftturn';
import { type Line, type Word, norm } from '../engine/lyrics';
import { F, font, measure, layout, glyphX } from '../engine/type';
import { strokeText, drawStrokeText, type StrokeText } from '../engine/stroke';
import { clamp, ease, lerp, prog, hash, noise1, pulse, TAU, frameIdx } from '../engine/util';
import { PDoom, formatPDoom } from '../engine/hud';

type Ctx2 = CanvasRenderingContext2D;
interface Cam { x: number; y: number; z: number; r: number }

// channel-coded inks (drawn with 'lighter' onto opaque black)
const TYPE = (a = 1) => `rgba(255,0,0,${a})`;
const PRINT = (a = 1) => `rgba(0,255,0,${a})`;
const ORANGE = (a = 1) => `rgba(0,0,255,${a})`;

// page regions (page px). A: form, B: annex (MLP), C: appendix (von Neumann)
const A = { x: 0, y: 0 };
const B = { x: 0, y: 1500 };
const C = { x: 0, y: 3000 };
/** The appendix sheet's top edge (relative to C), seen only in the hand-off. */
const SHEET_TOP = -625;
/**
 * The hand-off: how much faster than the next plate's drawing the page slides in the chase (it lies nearer
 * the camera), how far the halves peel up behind the spark while the page still holds (rad), and over what
 * length (px).
 */
const HANDOFF = { slideK: 1.25, wake: 0.5, wakeLen: 700 };

const PAPER_FRAG = /* glsl */ `
uniform sampler2D inkTex;
uniform vec3 camA; uniform vec3 camB;     // screen px (y down) -> page px
uniform vec2 blurV;                        // motion blur (screen px)
uniform vec4 st0; uniform vec4 st0b;       // stamp 0: centre.xy, half.xy | angle, strength, seed, -
uniform vec4 st1; uniform vec4 st1b;
uniform float zoom;
uniform float sheetTop;                    // page y of the appendix sheet's top edge (in the hand-off only)

float fibres(vec2 p, float cs) {
  float acc = 0.0;
  vec2 cell = floor(p / cs);
  for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
    vec2 c = cell + vec2(float(i), float(j));
    vec2 h = hash22(c);
    vec2 o = (c + h) * cs;
    float a = hash12(c + 7.1) * TAU;
    float L = cs * (0.3 + 1.1 * hash12(c + 3.3));
    vec2 d = vec2(cos(a), sin(a));
    float dist = sdSegment(p, o - d * L * 0.5, o + d * L * 0.5);
    float s = hash12(c + 9.9) - 0.5;
    acc += s * (1.0 - smoothstep(0.25, 0.9 + 0.4 / zoom, dist));
  }
  return acc;
}

float stampMask(vec2 p, vec4 s, vec4 sb) {
  if (sb.y <= 0.0) return 0.0;
  vec2 q = rot2(-sb.x) * (p - s.xy);
  vec2 d = abs(q) - s.zw;
  return (d.x < 0.0 && d.y < 0.0) ? 1.0 : 0.0;
}
// rubber-stamp ink: voids, mottling, heavier near shape edges
float stampInk(vec2 p, float cov, float edge, float seed, float strength) {
  float n = snoise(p * 0.07 + seed) * 0.45 + snoise(p * 0.23 + seed * 2.0) * 0.35 + snoise(p * 0.9 - seed) * 0.2;
  float press = smoothstep(-0.9, 0.3, snoise(p * 0.0045 + seed * 3.0));
  float voids = smoothstep(-0.58, -0.36, n + (strength - 1.0) * 0.8 + 0.25 * press);
  float mott = 0.72 + 0.28 * press;
  return sat(cov * voids * mott * 1.25 + edge * 0.5);
}

vec4 inkAt(vec2 uv) {
  return texture(inkTex, uv);
}

void main() {
  vec2 sp = vec2(vUv.x * 1920.0, (1.0 - vUv.y) * 1080.0);
  vec2 pp = vec2(dot(camA, vec3(sp, 1.0)), dot(camB, vec3(sp, 1.0)));

  // ---- paper
  float cloud = fbm(pp * 0.0021, 4);
  float mid = snoise(pp * 0.018);
  float fib = fibres(pp, 22.0) + 0.6 * fibres(pp * 1.7 + 31.0, 22.0);
  float speck = step(0.99965, hash12(floor(pp * 0.5)));
  vec3 paper = C_BONE * (0.975 + 0.028 * cloud + 0.008 * mid + 0.05 * fib);
  paper *= 1.0 - speck * 0.35;
  // gentle raking light across the sheet
  paper *= 0.97 + 0.03 * (1.0 - vUv.y * 0.6 - vUv.x * 0.4);

  // ---- inks (with optional motion blur along blurV)
  vec4 ink = vec4(0.0);
  float bl = length(blurV);
  if (bl > 1.0) {
    const int N = 32;
    float j = hash12(sp) ;
    for (int i = 0; i < N; i++) {
      float k = (float(i) + j) / float(N) - 0.5;
      ink += inkAt(vUv + vec2(blurV.x, -blurV.y) * k / vec2(1920.0, 1080.0));
    }
    ink /= float(N);
  } else ink = inkAt(vUv);

  float sm0 = stampMask(pp, st0, st0b), sm1 = stampMask(pp, st1, st1b);
  // edge estimate for stamps (coverage minus local blur)
  float edgeB = 0.0, edgeG = 0.0;
  if (sm0 + sm1 > 0.0) {
    vec2 px = vec2(3.0) / vec2(1920.0, 1080.0);
    vec4 blur4 = (inkAt(vUv + vec2(px.x, 0.0)) + inkAt(vUv - vec2(px.x, 0.0)) + inkAt(vUv + vec2(0.0, px.y)) + inkAt(vUv - vec2(0.0, px.y))) * 0.25;
    edgeB = sat((ink.b - blur4.b) * 2.0);
    edgeG = sat((ink.g - blur4.g) * 2.0);
  }
  float dType = ink.r * (0.86 + 0.14 * smoothstep(-0.5, 0.6, snoise(pp * 0.35))) * (1.0 - 0.18 * sat(fib * 4.0));
  float dPrint = ink.g;
  float dOr = ink.b * (0.92 + 0.08 * snoise(pp * 0.25));
  if (sm0 > 0.0) dOr = stampInk(pp, ink.b, edgeB, st0b.z, st0b.y);
  if (sm1 > 0.0) dPrint = stampInk(pp, ink.g, edgeG, st1b.z, st1b.y) * 0.92;

  // Beer-Lambert overprint: transmission^density
  vec3 col = paper;
  vec3 tOr = clamp(C_SIGNAL / C_BONE, 0.004, 1.0);
  vec3 tInk = clamp(C_INK / C_BONE * 1.25, 0.004, 1.0);
  vec3 tType = clamp(vec3(0.03, 0.028, 0.03) / C_BONE, 0.004, 1.0);
  col *= pow(tOr, vec3(sat(dOr)));
  col *= pow(tInk, vec3(sat(dPrint)));
  col *= pow(tType, vec3(sat(dType)));

  // binder punch holes: see-through to the dark desk, with a lit lower rim
  {
    float hd = min(length(pp - vec2(-770.0, -250.0)), length(pp - vec2(-770.0, 250.0))) - 17.0;
    float w = max(fwidth(hd), 1e-3);
    float inside = 1.0 - smoothstep(-w, w, hd);
    col = mix(col, C_INK * 0.6, inside);
    col *= 1.0 - 0.18 * (1.0 - smoothstep(0.0, 6.0, hd)) * (1.0 - inside);
  }
  // slight vignette on the sheet
  vec2 dc = vUv - 0.5;
  col *= 1.0 - 0.16 * pow(length(dc * vec2(1.0, 0.85)) * 1.5, 2.6);
  // in the hand-off the appendix is a sheet of its own, lying on the next plate's drawing: its top edge was
  // torn off at the perforation (the bridges between the slots stand proud) and slides into view in the chase
  float sheet = 1.0;
  if (sheetTop > -1e8) {
    float f = fract((pp.x + 1400.0) / 18.0);
    float edge = sheetTop - 2.2 * smoothstep(0.42, 0.5, f) * smoothstep(1.0, 0.92, f) - 0.5 * snoise(vec2(pp.x * 0.35, 4.0));
    float w = 0.7 / (zoom * PX_SCALE);
    sheet = smoothstep(edge - w, edge + w, pp.y);
  }
  fragColor = vec4(col, sheet);
}`;


const BURN_FRAG = /* glsl */ `
uniform sampler2D page;
uniform float on;          // 0: the page as it is (opaque); 1: the hand-off, composited over the next plate
uniform float lineX;       // screen x of the next plate's critical path, where its spark runs
uniform float slide;       // how far the page has slid down the screen in the chase (px)
uniform float front;       // the burn front, in page coordinates (screen y before the slide)
uniform vec2 spark;        // the spark head on screen
uniform float open;        // the halves' swing (rad) once the page is in two
uniform float wake;        // their lift behind the spark while the page still holds (rad)
uniform float wakeLen;     // over what length behind it (px)
uniform float glow;        // its light through the page, faded in from the start of the hand-off (0..1)
uniform float flare;       // the flash of light as it flares up through the page (0..1)
uniform float time;

const float CAMD = 2200.0;   // camera distance (px): the halves' perspective as they swing up
const float HINGE = 1250.0;  // the sheet's outer edges, off frame: each half swings about its own

// One half of the page (side -1: left, 1: right) seen at screen px sp: colour + coverage.
vec4 pageHalf(vec2 sp, float side) {
  // the half is a plane hinged on the vertical through h, swung up toward the camera by th (which grows
  // behind the spark while the page holds together): find the page point under this pixel
  float h = lineX + side * HINGE;
  float yf = sp.y, u = 0.0, th = 0.0, z = 0.0;
  for (int i = 0; i < 5; i++) {
    th = open + wake * smoothstep(0.0, wakeLen, yf - slide - front);
    float den = side * CAMD * cos(th) - (sp.x - 960.0) * sin(th);
    u = CAMD * (h - sp.x) / den;
    z = u * sin(th);
    yf = 540.0 + (sp.y - 540.0) * (CAMD - z) / CAMD;
  }
  float xf = h - side * u;
  if (u < 0.0 || z > CAMD * 0.85 || side * (xf - lineX) < 0.0) return vec4(0.0);
  vec4 pg = texture(page, vec2(xf / 1920.0, 1.0 - yf / 1080.0));
  vec2 q = vec2(xf, yf - slide);           // page coordinates
  float r = abs(xf - lineX), dist = q.y - front, back = max(dist, 0.0);

  // the burnt gap: a pointed tip at the spark, burning back behind it, ragged
  float rag = 1.5 * snoise(vec2(q.y * 0.045, side * 3.1)) + 0.7 * snoise(vec2(q.y * 0.21, side * 7.3));
  // (less a px, so that ahead of the tip, where it is 0, the page is whole)
  float hw = dist < 0.0 ? 5.0 * sqrt(max(0.0, 1.0 - dist * dist / 81.0)) : 5.0 + 11.0 * (1.0 - exp(-back / 180.0));
  hw += rag * smoothstep(0.0, 50.0, back) * (1.0 + back / 400.0) - 1.0;
  float e = r - hw;                         // px into the paper from the burnt edge
  float cover = smoothstep(-0.7 / PX_SCALE, 0.7 / PX_SCALE, e) * pg.a;
  if (cover <= 0.0) return vec4(0.0);
  vec3 col = pg.rgb;

  // the edge cools behind the spark, like the trail it rides
  float heat = exp(-back / 300.0) * smoothstep(-12.0, 0.0, dist);
  // scorch: browned paper, wider further back, and a bow wave just ahead of the tip
  float sw = 5.0 + 18.0 * (1.0 - exp(-back / 260.0));
  float sc = exp(-max(e, 0.0) / sw) * smoothstep(-30.0, 5.0, dist);
  sc = max(sc, exp(-r / 12.0) * exp(min(dist, 0.0) / 20.0));
  col *= mix(vec3(1.0), vec3(0.58, 0.40, 0.27), sat(sc) * 0.95);
  // char: a crumbly black band along the edge
  float cw = 1.6 + 3.4 * (1.0 - exp(-back / 220.0));
  float ch = (1.0 - smoothstep(0.0, cw, e + 0.8 * snoise(vec2(q.y * 0.6, side * 5.0)))) * smoothstep(-9.0, -3.0, dist);
  col = mix(col, C_INK * 0.4, ch);
  // the glowing rim: white-hot at the tip, signal, blood, out
  float rim = exp(-max(e, 0.0) / 1.2);
  float flick = 0.6 + 0.4 * snoise(vec2(q.y * 0.07 + side * 11.0, time * 6.0));
  vec3 rc = mix(C_BLOOD * 0.8, C_SIGNAL * 1.6, smoothstep(0.05, 0.4, heat));
  rc = mix(rc, C_EMBER * 3.2, smoothstep(0.6, 1.0, heat));
  col += rc * rim * smoothstep(0.02, 0.12, heat) * flick;

  // the spark's light: through the paper while it is still underneath (the ink stops it), on the paper
  // around the hole
  float d = length(sp - spark);
  float ahead = smoothstep(-2.0, -30.0, dist);
  float clear = sat(luma(pg.rgb) / luma(C_BONE)) * (1.0 - ch);
  float fl = 1.0 + 1.5 * flare;
  col += C_SIGNAL * (0.9 * exp(-d / 80.0) + 0.3 * exp(-d / (260.0 * fl))) * fl * ahead * clear * glow;
  col *= 1.0 + C_EMBER * (1.4 * exp(-d / 30.0) + 0.25 * exp(-d / (120.0 * fl))) * fl * (1.0 - ahead);

  // the half turns away from the raking light (from the upper left) as it swings up
  col *= clamp(mix(1.0, cos(th) - 0.5 * side * sin(th), 0.85), 0.15, 1.2);
  return vec4(col, cover);
}

void main() {
  vec2 sp = vec2(vUv.x * 1920.0, (1.0 - vUv.y) * 1080.0);
  if (on < 0.5) { fragColor = vec4(texture(page, vUv).rgb, 1.0); return; }
  vec4 a = pageHalf(sp, -1.0), b = pageHalf(sp, 1.0);
  float al = a.a + b.a;
  fragColor = vec4((a.rgb * a.a + b.rgb * b.a) / max(al, 1e-4), sat(al));
}`;

type Xf = { a: number; b: number; c: number; d: number; e: number; f: number };
/** Affine that maps page px -> screen px for a camera (+ shake). */
function camXf(cam: Cam, shx = 0, shy = 0): Xf {
  const cs = Math.cos(cam.r) * cam.z, sn = Math.sin(cam.r) * cam.z;
  const a = cs, b = sn, c = -sn, d = cs;
  const e = W / 2 + shx - (a * cam.x + c * cam.y);
  const f = H / 2 + shy - (b * cam.x + d * cam.y);
  return { a, b, c, d, e, f };
}
function invXf(m: Xf): Xf {
  const det = m.a * m.d - m.b * m.c;
  const ia = m.d / det, ib = -m.b / det, ic = -m.c / det, id = m.a / det;
  return { a: ia, b: ib, c: ic, d: id, e: -(ia * m.e + ic * m.f), f: -(ib * m.e + id * m.f) };
}
const apply = (m: Xf, x: number, y: number) => ({ x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f });
const lerpCam = (p: Cam, q: Cam, k: number): Cam => ({ x: lerp(p.x, q.x, k), y: lerp(p.y, q.y, k), z: Math.exp(lerp(Math.log(p.z), Math.log(q.z), k)), r: lerp(p.r, q.r, k) });

interface TypeChar { ch: string; t: number; x: number; y: number; dens: number; jx: number; jy: number; rot: number }

export default class Bureau extends Scene {
  ink = new Layer2D();
  pageRT = makeRT();
  paper = new FSPass(PAPER_FRAG, {
    inkTex: { value: null }, camA: { value: new THREE.Vector3() }, camB: { value: new THREE.Vector3() },
    blurV: { value: new THREE.Vector2() }, zoom: { value: 1 },
    st0: { value: new THREE.Vector4() }, st0b: { value: new THREE.Vector4() },
    st1: { value: new THREE.Vector4() }, st1b: { value: new THREE.Vector4() }, sheetTop: { value: -1e9 },
  });
  burnPass = new FSPass(BURN_FRAG, {
    page: { value: null }, on: { value: 0 }, lineX: { value: W / 2 }, slide: { value: 0 }, front: { value: 1e4 },
    spark: { value: new THREE.Vector2() }, open: { value: 0 }, wake: { value: 0 }, wakeLen: { value: 1 }, glow: { value: 0 }, flare: { value: 0 }, time: { value: 0 },
  }, { blending: THREE.NormalBlending, transparent: true });
  pdoom!: PDoom;
  /** The next plate, rendered here under the last page for the hand-off. */
  next!: LeftTurn;

  // lyric anchors
  L1!: Line; L2!: Line; L3!: Line;
  wEnough!: Word; wWe!: Word; wReck!: Word;
  wFwd!: Word; wMLP!: Word; wBack!: Word; wRep!: Word;
  wNow!: Word; wVon!: Word; wNeu!: Word; wObs!: Word;
  syl: [number, number][] = [];
  beatLen = 0.4645;

  // key times
  T0 = 0; tCR = 0; tStamp = 0; tSig = 0; tFiled = 0; tWhipB = 0; tFwd = 0; tBack0 = 0; tBack1 = 0; tRep0 = 0; tRep1 = 0;
  tNow = 0; tReveal = 0; tPunch = 0; tObs = 0; tStrike2 = 0; tEnd = 0;
  // the hand-off: the spark's light shows through (tGlow), it bursts through (tBurst), the page is in two (tFree)
  tGlow = 0; tBurst = 0; tFree = 0;
  /** The sheet's top edge in page coordinates (the screen before the slide). */
  qTop = 0;

  findings: TypeChar[] = [];
  conclusion: TypeChar[] = [];
  /** the P(doom) cameo: a pre-printed field under the SAFE ENOUGH stamp, typed in once "we reckoned" is done */
  pdoomField: TypeChar[] = [];
  pdoomSize = 38;
  typeSize = 50;
  sig!: StrokeText;
  obsHand!: StrokeText;
  obsCharTimes: [number, number][] = [];
  layers: { x: number; ys: number[] }[] = [];

  override async init() {
    const { lyrics, audio } = this.ctx;
    this.pdoom = new PDoom(lyrics);

    this.ink.texture.colorSpace = THREE.NoColorSpace;
    const find = (l: Line, q: string, from = 0) => l.words.slice(from).find((w) => norm(w.w).startsWith(norm(q))) ?? l.words[Math.min(from, l.words.length - 1)]!;
    this.L1 = lyrics.get('safe enough');
    this.L2 = lyrics.get('Forward MLP');
    this.L3 = lyrics.get('Neumann');
    this.wEnough = find(this.L1, 'enough');
    this.wWe = find(this.L1, 'we', 4);
    this.wReck = find(this.L1, 'reckon');
    this.wFwd = find(this.L2, 'forward');
    this.wMLP = find(this.L2, 'mlp');
    this.wBack = find(this.L2, 'backward');
    this.wRep = find(this.L2, 'repeat');
    this.wNow = this.L3.words[0]!;
    this.wVon = find(this.L3, 'von');
    this.wNeu = find(this.L3, 'neumann');
    this.wObs = find(this.L3, 'obsolete');
    const m = this.wMLP;
    this.syl = m.syl && m.syl.length === 3 ? m.syl.map((s) => [s[0], s[1]] as [number, number]) : [0, 1, 2].map((i) => [lerp(m.start, m.end, i / 3), lerp(m.start, m.end, (i + 1) / 3)] as [number, number]);

    const au = audio;
    const b0 = Math.floor(au.beatAt(this.ctx.start));
    this.beatLen = au.timeOfBeat(b0 + 1) - au.timeOfBeat(b0);
    const nextDown = (t: number) => au.downbeats.find((d) => d >= t - 1e-3) ?? t;
    const nearestBeat = (t: number) => au.timeOfBeat(Math.round(au.beatAt(t)));
    this.T0 = this.ctx.start;
    this.tEnd = this.ctx.end;
    this.tCR = this.wWe.start - 0.03;
    this.tStamp = this.wReck.start;
    this.tFwd = this.wFwd.start;
    this.tFiled = nextDown(this.tStamp + 1.4);
    if (this.tFiled > this.tFwd - 0.7) this.tFiled = this.tStamp + 1.6;
    this.tSig = nearestBeat(lerp(this.tStamp, this.tFiled, 0.5));
    if (this.tSig < this.tStamp + 0.4 || this.tSig > this.tFiled - 0.5) this.tSig = lerp(this.tStamp, this.tFiled, 0.5);
    this.tWhipB = this.tFwd - Math.min(0.46, this.beatLen);
    this.tBack0 = this.wBack.start; this.tBack1 = this.wBack.end;
    this.tRep0 = this.wRep.start; this.tRep1 = Math.max(this.wRep.end, this.tRep0 + 0.45);
    this.tNow = Math.min(this.wNow.start, this.L3.start);
    this.tObs = this.wObs.start;
    this.tStrike2 = this.tObs + Math.min(0.22, this.beatLen * 0.5);
    this.tReveal = au.downbeats.find((d) => d > this.wVon.end - 0.15 && d < this.tObs - 0.6) ?? lerp(this.wNeu.start, this.tObs, 0.2);
    this.tPunch = nearestBeat(lerp(this.tReveal, this.tObs, 0.5));

    // ---- typewriter layout: each word is typed at a natural rate from its start (done by its end)
    const adv = this.typeSize * 0.6;
    const mk = (words: Word[], x0: number, y0: number, seed: number) => {
      const out: TypeChar[] = [];
      let x = x0;
      words.forEach((w, wi) => {
        const chars = Array.from(w.w);
        const per = Math.min(0.07, (w.end - w.start) / Math.max(1, chars.length));
        chars.forEach((ch, i) => {
          const k = out.length + seed * 100;
          out.push({ ch, t: w.start + i * per, x, y: y0, dens: 0.8 + 0.2 * hash(k, 1), jx: (hash(k, 2) - 0.5) * 1.6, jy: (hash(k, 3) - 0.5) * 2.4, rot: (hash(k, 4) - 0.5) * 0.02 });
          x += adv;
        });
        if (wi < words.length - 1) x += adv;
      });
      return out;
    };
    const iWe = this.L1.words.indexOf(this.wWe);
    this.findings = mk(this.L1.words.slice(0, iWe), A.x - 520, A.y - 118, 1);
    this.conclusion = mk(this.L1.words.slice(iWe), A.x - 520, A.y + 142, 2);
    {
      // typed after the last letter of "reckoned", done before the camera snaps to the signature
      const last = this.conclusion[this.conclusion.length - 1]?.t ?? this.tStamp;
      const t0 = Math.max(last + 0.14, this.tStamp + 0.3);
      const txt = formatPDoom(this.pdoom.value(t0));
      const per = clamp((this.tSig - 0.1 - t0) / Math.max(1, txt.length), 0.035, 0.07);
      const pa = this.pdoomSize * 0.6;
      this.pdoomField = Array.from(txt).map((ch, i) => {
        const k = 300 + i;
        return { ch, t: t0 + i * per, x: A.x + 488 + i * pa, y: A.y + 458, dens: 0.82 + 0.18 * hash(k, 1), jx: (hash(k, 2) - 0.5) * 1.4, jy: (hash(k, 3) - 0.5) * 2, rot: (hash(k, 4) - 0.5) * 0.02 };
      });
    }

    this.sig = strokeText('We', 'script', 120);
    this.obsHand = strokeText('obsolete', 'hscript', 124, 1);
    // the next plate, under the last page: its window as the timeline cuts it (on the beat at/before "Gato")
    const gato = lyrics.get('Gato').words[0]!.start;
    this.next = new LeftTurn({ ...this.ctx, id: 'leftturn', params: {}, start: this.ctx.end, end: au.timeOfBeat(Math.floor(au.beatAt(gato + 0.02))) });
    this.next.embedded = true;
    await this.next.init();
    this.tBurst = this.next.T.burst;
    this.tGlow = this.tBurst - this.beatLen;

    // hand-writing of "obsolete": starts with the word and must be done before the burst
    const wEnd = Math.min(this.wObs.end, this.tBurst - 0.12);
    const n = this.obsHand.charRange.length;
    this.obsCharTimes = Array.from({ length: n }, (_, i) => [lerp(this.tObs + 0.03, wEnd, i / n), lerp(this.tObs + 0.03, wEnd, (i + 1) / n)] as [number, number]);

    // ---- MLP geometry (relative to B)
    const counts = [4, 6, 6, 3];
    const xs = [-600, -200, 200, 600];
    this.layers = counts.map((n, i) => ({ x: xs[i]!, ys: Array.from({ length: n }, (_, j) => (j - (n - 1) / 2) * 78) }));

    // ---- the hand-off: the page is in two once the burn front has passed the sheet's top edge (just off the
    // top of the frame where the camera stopped)
    const m0 = camXf(this.camAt(this.tGlow));
    this.qTop = apply(m0, apply(invXf(m0), W / 2, 0).x, C.y + SHEET_TOP).y;
    let lo = this.tBurst, hi = this.tEnd;
    for (let i = 0; i < 30; i++) { const mid = (lo + hi) / 2; if (this.frontAt(mid) > this.qTop) lo = mid; else hi = mid; }
    this.tFree = hi;
  }

  /** The burn front in page coordinates: the spark's height on screen, less the page's slide. */
  frontAt(t: number) {
    return this.next.sparkScreen(t).y - HANDOFF.slideK * this.next.slide(t);
  }

  // ------------------------------------------------------------------ timing helpers
  /** Remapped time for annex B: during "repeat" the last beat (the backward sweep) is replayed three times. */
  remapB(t: number) {
    if (t < this.tRep0 || t >= this.tNow) return { tr: t, loop: -1 };
    // the replayed material: the whole backward sweep (pulse + camera dolly), re-run fast, three times
    const src0 = this.tBack0 - 0.03, src1 = Math.max(this.tBack1 + 0.06, this.tBack0 + 0.4);
    if (t >= this.tRep1) return { tr: src1, loop: 3 };
    const seg = (this.tRep1 - this.tRep0) / 3;
    const k = Math.min(2, Math.floor((t - this.tRep0) / seg));
    const u = (t - this.tRep0 - k * seg) / seg;
    return { tr: lerp(src0, src1, u), loop: k };
  }

  shake(t: number): [number, number] {
    let amp = 0;
    amp += 30 * pulse(t, this.tStamp, 0.07);
    amp += 11 * pulse(t, this.tFiled, 0.06);
    amp += 14 * pulse(t, this.tObs, 0.06) + 9 * pulse(t, this.tStrike2, 0.06);
    for (const s of this.syl) amp += 5 * pulse(t, s[0], 0.05);
    if (t >= this.tRep0 && t < this.tRep1 + 0.2) {
      const seg = (this.tRep1 - this.tRep0) / 3;
      for (let k = 0; k < 3; k++) amp += 9 * pulse(t, this.tRep0 + k * seg, 0.04);
    }
    for (const ch of this.findings) if (t >= ch.t && t < ch.t + 0.1) amp += 1.8 * pulse(t, ch.t, 0.025);
    for (const ch of this.conclusion) if (t >= ch.t && t < ch.t + 0.1) amp += 1.8 * pulse(t, ch.t, 0.025);
    const ph = frameIdx(t);
    return [amp * (hash(ph, 11) - 0.5) * 2, amp * (hash(ph, 12) - 0.5) * 2];
  }

  /** Carriage position: steps one character per keystroke (short eased step). */
  caretX(list: TypeChar[], t: number) {
    let x = list[0]!.x;
    for (const c of list) {
      if (t < c.t) break;
      x = lerp(x, c.x + this.typeSize * 0.6, ease.outCubic(prog(t, c.t, c.t + 0.05)));
    }
    return x;
  }

  /** Is there a camera cut in (t - dt, t]? (no motion blur across cuts) */
  cutBetween(t0: number, t1: number) {
    if (t1 > this.tRep0 && t0 < this.tRep1 + 0.02) return true; // no blur during the stutter
    const cuts = [this.tStamp, this.tNow, this.tRep0, this.tRep0 + (this.tRep1 - this.tRep0) / 3, this.tRep0 + (2 * (this.tRep1 - this.tRep0)) / 3, this.tRep1];
    return cuts.some((c) => c > t0 && c <= t1);
  }

  camAt(t: number): Cam {
    // --- A: the form
    if (t < this.tStamp) {
      const settle = prog(t, this.T0, this.T0 + 0.6, ease.outExpo);
      const z = lerp(1.75, 1.55, settle);
      const fx = this.caretX(this.findings, t), cx = this.caretX(this.conclusion, t);
      const cr = prog(t, this.tCR, this.tCR + 0.17, ease.inOutCubic);
      const x = lerp(Math.max(fx - 200, A.x - 330), Math.max(cx - 200, A.x - 330), cr);
      const y = lerp(A.y - 150, A.y + 110, cr);
      return { x: x - 60 * (1 - settle), y: y - 190 * (1 - settle), z, r: -0.035 - 0.025 * (1 - settle) };
    }
    if (t < this.tWhipB) {
      const wide: Cam = { x: A.x + 40, y: A.y + 12, z: lerp(0.95, 0.985, prog(t, this.tStamp, this.tSig, ease.linear)), r: -0.014 };
      const sig: Cam = { x: A.x - 250, y: A.y + 250, z: lerp(1.42, 1.5, prog(t, this.tSig, this.tFiled, ease.linear)), r: -0.03 };
      const wide2: Cam = { x: A.x + 70, y: A.y + 2, z: lerp(0.9, 0.93, prog(t, this.tFiled, this.tWhipB, ease.linear)), r: 0.01 };
      let cam = lerpCam(wide, sig, prog(t, this.tSig - 0.04, this.tSig + 0.26, ease.outExpo));
      cam = lerpCam(cam, wide2, prog(t, this.tFiled - 0.2, this.tFiled, ease.inOutCubic));
      return cam;
    }
    if (t < this.tFwd) {
      const from = this.camAt(this.tWhipB - 1e-4);
      const to = this.camB(this.tFwd);
      return lerpCam(from, to, prog(t, this.tWhipB, this.tFwd, ease.inOutExpo));
    }
    if (t < this.tNow) return this.camB(this.remapB(t).tr);
    return this.camC(t);
  }

  camB(t: number): Cam {
    const s = this.syl;
    const snap = (k: number) => prog(t, s[k]![0] - 0.02, s[k]![0] + 0.2, ease.outExpo);
    const keysB: Cam[] = [
      { x: -420, y: -60, z: 1.42, r: 0.02 },    // "Forward": tight on the input side
      { x: -250, y: -30, z: 1.25, r: 0.01 },    // M
      { x: -60, y: -10, z: 1.12, r: -0.004 },   // L
      { x: -110, y: 5, z: 0.99, r: 0.006 },     // P: the whole schematic
    ];
    let cam = keysB[0]!;
    cam = { ...cam, z: cam.z * (1 - 0.04 * prog(t, this.tFwd, s[0]![0], ease.linear)) };
    for (let k = 0; k < 3; k++) cam = lerpCam(cam, keysB[k + 1]!, snap(k));
    // "backward": dolly right-to-left with the gradient, slight counter-roll
    const back = prog(t, this.tBack0 - 0.03, this.tBack1 + 0.05, ease.inOutCubic);
    const b0: Cam = { x: 90, y: 20, z: 1.06, r: -0.02 };
    const b1: Cam = { x: -170, y: 20, z: 1.01, r: -0.03 };
    if (back > 0) cam = lerpCam(cam, lerpCam(b0, b1, back), prog(t, this.tBack0 - 0.03, this.tBack0 + 0.12, ease.outCubic));
    return { x: B.x + cam.x, y: B.y + cam.y, z: cam.z, r: cam.r };
  }

  camC(t: number): Cam {
    // tight on the heading as it prints, reveal the figure on the downbeat, punch in on a beat, then the strikes
    const k = prog(t, this.tReveal - 0.04, this.tReveal + 0.34, ease.outExpo);
    const tight: Cam = { x: C.x - 460 + 260 * prog(t, this.tNow, this.tReveal, ease.linear), y: C.y - 370, z: 1.7, r: -0.025 };
    const wide: Cam = { x: C.x - 10, y: C.y - 40, z: 0.9, r: 0.01 };
    let cam = lerpCam(tight, wide, k);
    const punch: Cam = { x: C.x + 10, y: C.y - 20, z: 0.99, r: -0.004 };
    cam = lerpCam(cam, punch, prog(t, this.tPunch - 0.03, this.tPunch + 0.25, ease.outExpo));
    // a slow creep in (3 % a second), held through the hand-off
    cam.z *= 1 + 0.031 * clamp(Math.min(t, this.tGlow) - this.tPunch, 0, 2);
    cam.z *= 1 + 0.04 * pulse(t, this.tObs, 0.08) + 0.03 * pulse(t, this.tStrike2, 0.08);
    return cam;
  }

  // ------------------------------------------------------------------ render
  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const { renderer } = this.ctx;
    const t = f.t;
    // the hand-off: from the first light under the page, the next plate is rendered here, under it
    const hand = t >= this.tGlow;
    const nextPost = hand ? this.next.render(f, out) ?? {} : {};
    const cam = this.camAt(t);
    cam.z *= 1 + 0.05 * pulse(t, this.tStamp, 0.09) + 0.018 * pulse(t, this.tFiled, 0.07);
    const [shx, shy] = this.shake(t);
    const m = camXf(cam, shx, shy);
    // in the chase the page slides down with the drawing under it
    const slide = hand ? HANDOFF.slideK * this.next.slide(t) : 0;
    m.f += slide;
    const im = invXf(m);

    // motion blur: centre displacement over one frame, only on whips / carriage return (never across cuts;
    // the chase is blurred by the sub-frames)
    let bl: [number, number] = [0, 0];
    const dtb = 1 / 60;
    if (!hand && !this.cutBetween(t - dtb, t)) {
      const m2 = camXf(this.camAt(t - dtb));
      const pc = apply(im, W / 2 + shx, H / 2 + shy);
      const q = apply(m2, pc.x, pc.y);
      const bx = q.x - W / 2, by = q.y - H / 2;
      const len = Math.hypot(bx, by);
      const k = len > 40 ? (Math.min(1, (len - 40) / 30) * Math.min(170, len * 0.5)) / len : 0;
      bl = [bx * k, by * k];
    }

    // ---- ink layer (page space)
    const L = this.ink;
    L.clear('#000');
    const c = L.ctx;
    c.globalCompositeOperation = 'lighter';
    c.setTransform(m.a, m.b, m.c, m.d, m.e, m.f);
    const view = this.viewRect(im);
    if (view.y0 < A.y + 800 && view.y1 > A.y - 800) this.drawForm(c, t);
    if (view.y0 < A.y + 800 && view.y1 > A.y + 700) this.drawPerforation(c, A.y + 760);
    if (!hand && view.y0 < B.y + 800 && view.y1 > B.y - 800) {
      const rb = this.remapB(t);
      this.drawAnnex(c, rb.tr, t, rb.loop);
    }
    if (!hand && view.y0 < B.y + 800 && view.y1 > B.y + 700) this.drawPerforation(c, B.y + 760);
    if (view.y0 < C.y + 800 && view.y1 > C.y - 800) this.drawAppendix(c, t);
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalCompositeOperation = 'source-over';

    // ---- paper + inks
    const P = this.paper.u;
    P.inkTex!.value = L.upload();
    (P.camA!.value as THREE.Vector3).set(im.a, im.c, im.e);
    (P.camB!.value as THREE.Vector3).set(im.b, im.d, im.f);
    (P.blurV!.value as THREE.Vector2).set(bl[0], bl[1]);
    P.zoom!.value = cam.z;
    P.sheetTop!.value = hand ? C.y + SHEET_TOP : -1e9;
    const sA = this.stampSafe(t), sF = this.stampFiled(t);
    (P.st0!.value as THREE.Vector4).set(sA.x, sA.y, sA.hw * 1.12, sA.hh * 1.12);
    (P.st0b!.value as THREE.Vector4).set(sA.rot, sA.on ? sA.strength : 0, 3.7, 0);
    (P.st1!.value as THREE.Vector4).set(sF.x, sF.y, sF.hw * 1.12, sF.hh * 1.12);
    (P.st1b!.value as THREE.Vector4).set(sF.rot, sF.on ? 1.0 : 0, 9.1, 0);
    this.paper.render(renderer, this.pageRT);

    // ---- the page (in the hand-off: burnt in two along the spark's path, over the next plate)
    const U = this.burnPass.u;
    U.page!.value = this.pageRT.texture;
    U.on!.value = hand ? 1 : 0;
    if (hand) {
      const sp = this.next.sparkScreen(t);
      U.lineX!.value = sp.x;
      U.slide!.value = slide;
      U.front!.value = sp.y - slide;
      (U.spark!.value as THREE.Vector2).set(sp.x, sp.y);
      U.open!.value = 1.35 * ease.inQuad(prog(t, this.tFree, this.tEnd - 0.01));
      U.wake!.value = HANDOFF.wake;
      U.wakeLen!.value = HANDOFF.wakeLen;
      U.glow!.value = prog(t, this.tGlow, this.tGlow + 0.25, ease.inQuad);
      U.flare!.value = pulse(t, this.tBurst, 0.07);
      U.time!.value = t;
    }
    this.burnPass.render(renderer, out);

    const own: PostOverrides = { hud: 1, paper: 1, bloom: 0.2, bloomThreshold: 1.8, halation: 0.04, vignette: 0.18, grain: 0.045, ca: 0.5 };
    if (!hand) return own;
    // the spark, over the page: through the hole it burns, then over the next plate's line as the halves part
    this.next.renderSpark(out, t);
    // the post goes over to the next plate's as the page swings away, exactly by the cut
    const k = prog(t, this.tFree - 0.05, this.tEnd - 0.03, ease.inOutQuad);
    const post = mixPost(own, nextPost, k);
    const kick = (6 * pulse(t, this.tBurst, 0.05) + 5 * pulse(t, this.tFree, 0.05)) * (1 - k);
    const ph = frameIdx(t);
    post.shake = [post.shake![0] + kick * (hash(ph, 21) - 0.5) * 2, post.shake![1] + kick * (hash(ph, 22) - 0.5) * 2];
    return post;
  }

  viewRect(im: Xf) {
    const pts = [[0, 0], [W, 0], [0, H], [W, H]].map(([x, y]) => apply(im, x!, y!));
    return { x0: Math.min(...pts.map((p) => p.x)), x1: Math.max(...pts.map((p) => p.x)), y0: Math.min(...pts.map((p) => p.y)), y1: Math.max(...pts.map((p) => p.y)) };
  }

  // ------------------------------------------------------------------ A. the form
  stampSafe(t: number) {
    const on = t >= this.tStamp;
    const k = prog(t, this.tStamp, this.tStamp + 0.05, ease.outQuad);
    return { x: A.x + 385, y: A.y + 262, hw: 330, hh: 122, rot: -0.12, on, strength: 1 + 0.5 * (1 - k), scale: lerp(1.07, 1, k) };
  }
  stampFiled(t: number) {
    const k = prog(t, this.tFiled, this.tFiled + 0.05, ease.outQuad);
    return { x: A.x + 520, y: A.y - 330, hw: 190, hh: 66, rot: 0.085, on: t >= this.tFiled, scale: lerp(1.06, 1, k) };
  }

  drawForm(c: Ctx2, t: number) {
    const x0 = A.x - 700, x1 = A.x + 700, y0 = A.y - 470;
    c.save();
    c.textBaseline = 'alphabetic';
    // hole reinforcement rings (the holes themselves are cut in the paper shader)
    for (const yy of [A.y - 250, A.y + 250]) {
      c.strokeStyle = PRINT(0.18); c.lineWidth = 1;
      c.beginPath(); c.arc(x0 - 70, yy, 27, 0, TAU); c.stroke();
    }
    // header band with knocked-out type
    c.fillStyle = PRINT(1);
    c.fillRect(x0, y0, x1 - x0, 92);
    c.globalCompositeOperation = 'difference';
    c.fillStyle = PRINT(1);
    c.font = font(F.archivo(125, 900), 58);
    c.fillText('FORM 7-B', x0 + 26, y0 + 68);
    c.font = font(F.mono(600), 19);
    c.letterSpacing = '4px';
    c.fillText('SAFETY EVALUATION OF A FRONTIER SYSTEM', x0 + 470, y0 + 42);
    c.font = font(F.mono(400), 15);
    c.letterSpacing = '3px';
    c.fillText('ABRIDGED EDITION  ·  PLEASE TYPE OR PRINT CLEARLY', x0 + 470, y0 + 70);
    c.globalCompositeOperation = 'lighter';

    // meta row
    const meta = [['ISSUED BY', 'DEPT. OF REASONABLE ASSURANCES'], ['REF.', '7B-0042/∞'], ['REVIEW TIME', '11 MIN'], ['PAGE', '1 OF 1']];
    let mx = x0;
    const mw = [520, 280, 320, 280];
    c.letterSpacing = '2px';
    meta.forEach(([k, v], i) => {
      c.fillStyle = PRINT(0.55); c.font = font(F.mono(500), 12); c.fillText(k!, mx + 10, y0 + 122);
      c.fillStyle = PRINT(0.95); c.font = font(F.mono(500), 17); c.fillText(v!, mx + 10, y0 + 148);
      mx += mw[i]!;
      if (i < meta.length - 1) { c.fillStyle = PRINT(0.6); c.fillRect(mx, y0 + 104, 1.2, 56); }
    });
    c.fillStyle = PRINT(0.8); c.fillRect(x0, y0 + 164, x1 - x0, 1.5);
    c.letterSpacing = '0px';

    const label = (n: string, s: string, y: number) => {
      c.fillStyle = PRINT(1);
      c.font = font(F.mono(700), 16); c.letterSpacing = '3px';
      c.fillText(n, x0 + 10, y);
      c.fillText(s, x0 + 52, y);
      c.letterSpacing = '0px';
    };
    // 1. FINDINGS (lyric typed here)
    label('1.', 'FINDINGS', A.y - 210);
    c.fillStyle = PRINT(0.3);
    for (let i = 0; i < 2; i++) c.fillRect(x0 + 160, A.y - 105 + i * 64, x1 - x0 - 180, 1.2);
    c.fillStyle = PRINT(0.5); c.font = font(F.mono(400), 13);
    c.fillText('(describe observed behaviour; attach additional sheets if the system asks you to)', x0 + 160, A.y - 205);
    // 2. RISK LEVEL
    label('2.', 'RISK LEVEL', A.y - 10);
    const opts = ['LOW', 'MODERATE', 'HIGH', 'SAFE ENOUGH'];
    let ox = x0 + 290;
    c.font = font(F.mono(500), 21);
    c.letterSpacing = '2px';
    opts.forEach((o, i) => {
      c.strokeStyle = PRINT(0.95); c.lineWidth = 2;
      c.strokeRect(ox, A.y - 34, 30, 30);
      c.fillStyle = PRINT(0.95);
      c.fillText(o, ox + 44, A.y - 10);
      if (i === 3 && t >= this.wEnough.start) {
        c.save();
        c.fillStyle = TYPE(0.95);
        c.font = font(F.mono(600), 40);
        c.fillText('X', ox + 3, A.y - 6);
        c.restore();
      }
      ox += 44 + measure(o, F.mono(500), 21, 2) + 70;
    });
    c.letterSpacing = '0px';
    // 3. CONCLUSION
    label('3.', 'CONCLUSION', A.y + 90);
    c.fillStyle = PRINT(0.3);
    c.fillRect(x0 + 160, A.y + 155, 760, 1.2);
    // 4. signature
    label('4.', 'SIGNATURE OF EVALUATOR(S)', A.y + 250);
    c.fillStyle = PRINT(0.6);
    c.fillRect(x0 + 160, A.y + 360, 520, 1.2);
    c.font = font(F.mono(400), 12); c.letterSpacing = '2px';
    c.fillText('SIGN HERE', x0 + 160, A.y + 380);
    c.letterSpacing = '0px';
    // footnote
    c.fillStyle = PRINT(0.8); c.fillRect(x0, A.y + 415, x1 - x0, 1);
    c.fillStyle = PRINT(0.75);
    c.font = font(F.mono(400), 14);
    c.fillText('* “Safe enough” is defined in Form 7-C, which has not been drafted. Do not detach.', x0 + 10, A.y + 445);
    // 5. the P(doom) field, right under where the stamp lands
    {
      const fx = A.x + 230, fy = A.y + 452;
      c.fillStyle = PRINT(1);
      c.font = font(F.mono(700), 16); c.letterSpacing = '3px';
      c.fillText('5.', fx, fy);
      c.fillText('EST. P(DOOM)', fx + 34, fy);
      c.fillStyle = PRINT(0.55);
      c.font = font(F.mono(400), 12); c.letterSpacing = '2px';
      c.fillText('(ROUND DOWN)', fx + 34, fy + 22);
      c.letterSpacing = '0px';
      c.fillStyle = PRINT(0.55);
      c.fillRect(A.x + 470, fy + 12, x1 - 20 - (A.x + 470), 1.2);
    }
    c.restore();

    this.drawTyped(c, this.findings, t);
    this.drawTyped(c, this.conclusion, t);
    this.drawTyped(c, this.pdoomField, t, this.pdoomSize, 0.12);

    // signature scribble
    if (t >= this.tSig) {
      const k = prog(t, this.tSig, this.tSig + 0.4, ease.inOutQuad);
      c.save();
      c.translate(x0 + 200, A.y + 345);
      c.rotate(-0.06);
      c.strokeStyle = TYPE(0.95); c.lineWidth = 3.4; c.lineCap = 'round'; c.lineJoin = 'round';
      drawStrokeText(c, this.sig, this.sig.total * clamp(k / 0.85));
      if (k > 0.85) {
        const u = (k - 0.85) / 0.15;
        c.beginPath(); c.moveTo(-10, 14); c.quadraticCurveTo(120, 30, lerp(-10, 260, u), lerp(14, 4, u)); c.stroke();
      }
      c.restore();
    }
    this.drawSafeStamp(c, t);
    this.drawFiledStamp(c, t);
  }

  drawTyped(c: Ctx2, list: TypeChar[], t: number, size = this.typeSize, guideLead = 0.7) {
    if (!list.length) return;
    c.save();
    c.font = font(F.mono(500), size);
    c.textBaseline = 'alphabetic';
    for (const ch of list) {
      if (t < ch.t) break;
      const fresh = pulse(t, ch.t, 0.04);
      c.save();
      c.translate(ch.x + ch.jx, ch.y + ch.jy - 4 * fresh);
      c.rotate(ch.rot);
      c.fillStyle = TYPE(ch.dens);
      c.fillText(ch.ch, 0, 0);
      c.restore();
    }
    // the type guide (where the next letter will strike)
    const next = list.find((ch) => ch.t > t);
    if (next && t > list[0]!.t - guideLead) {
      c.fillStyle = ORANGE(1);
      const gx = next.x + size * 0.3, gs = size / this.typeSize;
      c.beginPath(); c.moveTo(gx - 8 * gs, next.y + 20 * gs); c.lineTo(gx + 8 * gs, next.y + 20 * gs); c.lineTo(gx, next.y + 9 * gs); c.closePath(); c.fill();
    }
    c.restore();
  }

  drawSafeStamp(c: Ctx2, t: number) {
    const s = this.stampSafe(t);
    if (!s.on) return;
    c.save();
    c.translate(s.x, s.y); c.rotate(s.rot); c.scale(s.scale, s.scale);
    const hw = s.hw - 12, hh = s.hh - 12;
    c.strokeStyle = ORANGE(1);
    c.lineWidth = 12; c.strokeRect(-hw, -hh, hw * 2, hh * 2);
    c.lineWidth = 3.5; c.strokeRect(-hw + 18, -hh + 18, hw * 2 - 36, hh * 2 - 36);
    c.fillStyle = ORANGE(1);
    c.textAlign = 'center';
    const fam = F.archivo(75, 900);
    const size = Math.min(112, (100 * (hw * 2 - 70)) / measure('SAFE ENOUGH', fam, 100));
    c.font = font(fam, size);
    c.fillText('SAFE ENOUGH', 0, size * 0.36);
    c.font = font(F.mono(700), 16);
    c.letterSpacing = '6px';
    c.fillText('EVALUATED · WE RECKON', 0, -hh + 46);
    c.fillText('DEPT. OF REASONABLE ASSURANCES', 0, hh - 30);
    c.letterSpacing = '0px';
    c.restore();
  }

  drawFiledStamp(c: Ctx2, t: number) {
    const s = this.stampFiled(t);
    if (!s.on) return;
    c.save();
    c.translate(s.x, s.y); c.rotate(s.rot); c.scale(s.scale, s.scale);
    c.strokeStyle = PRINT(1); c.lineWidth = 7;
    const hw = s.hw - 10, hh = s.hh - 10;
    c.beginPath(); c.roundRect(-hw, -hh, hw * 2, hh * 2, 20); c.stroke();
    c.fillStyle = PRINT(1); c.textAlign = 'center';
    c.font = font(F.archivo(125, 900), 62);
    c.fillText('FILED', 0, 12);
    c.font = font(F.mono(600), 13); c.letterSpacing = '4px';
    c.fillText('NO FURTHER ACTION', 0, hh - 14);
    c.letterSpacing = '0px';
    c.restore();
  }

  drawPerforation(c: Ctx2, y: number) {
    c.save();
    c.fillStyle = PRINT(0.4);
    for (let x = -1400; x < 1400; x += 18) c.fillRect(x, y, 9, 1.4);
    c.font = font(F.mono(500), 13); c.letterSpacing = '4px';
    c.fillStyle = PRINT(0.6);
    c.fillText('   DETACH HERE — RETAIN LOWER PORTION FOR YOUR RECORDS', -440, y - 12);
    c.letterSpacing = '0px';
    // the scissors (no font here has ✂), drawn in the first cell: two finger rings, crossed blades
    const sx = -440, sy = y - 16.5;
    c.strokeStyle = PRINT(0.6); c.lineWidth = 1.1;
    c.beginPath();
    c.arc(sx + 2.2, sy - 3, 2.2, 0, Math.PI * 2);
    c.moveTo(sx + 4.4, sy + 3); c.arc(sx + 2.2, sy + 3, 2.2, 0, Math.PI * 2);
    c.moveTo(sx + 4, sy - 1.8); c.lineTo(sx + 12.5, sy + 2.4);
    c.moveTo(sx + 4, sy + 1.8); c.lineTo(sx + 12.5, sy - 2.4);
    c.stroke();
    c.restore();
  }

  // ------------------------------------------------------------------ B. the annex (MLP)
  /** Pulse front in layer units: forward 0 -> 3 with the syllables M, L, P; backward 3 -> 0 over "backward". */
  pulsePos(t: number): { pos: number; dir: number } {
    const s = this.syl;
    if (t < this.tBack0) {
      let pos = 0;
      for (let k = 0; k < 3; k++) pos += prog(t, s[k]![0], Math.min(s[k]![1], s[k]![0] + 0.3), ease.inOutCubic);
      return { pos, dir: 1 };
    }
    const b = prog(t, this.tBack0, Math.max(this.tBack1, this.tBack0 + 0.35), ease.inOutQuad);
    return { pos: 3 - 3 * b, dir: -1 };
  }

  drawAnnex(c: Ctx2, t: number, tReal: number, loop: number) {
    c.save();
    c.translate(B.x, B.y);
    c.textBaseline = 'alphabetic';
    // headers
    c.fillStyle = PRINT(1);
    c.font = font(F.mono(700), 17); c.letterSpacing = '4px';
    c.fillText('ANNEX B — TRAINING PROCEDURE', -880, -540);
    c.font = font(F.mono(400), 13); c.letterSpacing = '2px';
    c.fillStyle = PRINT(0.6);
    c.fillText('SCHEMATIC · NOT TO SCALE · DO NOT OPERATE UNSUPERVISED', -880, -516);
    c.letterSpacing = '0px';
    c.fillStyle = PRINT(0.9); c.fillRect(-880, -500, 1760, 1.5);

    const Ls = this.layers;
    const pp = this.pulsePos(t);
    const s = this.syl;
    const inAct = prog(t, this.tFwd, this.tFwd + 0.3, ease.outCubic);
    const R = 22;

    // edges
    for (let k = 0; k < 3; k++) {
      const a = Ls[k]!, b = Ls[k + 1]!;
      const fwdK = pp.dir > 0 ? clamp(pp.pos - k) : 1;
      const bwdK = pp.dir < 0 ? clamp(k + 1 - pp.pos) : 0;
      for (let i = 0; i < a.ys.length; i++) for (let j = 0; j < b.ys.length; j++) {
        const x0 = a.x + R + 3, y0 = a.ys[i]!, x1 = b.x - R - 3, y1 = b.ys[j]!;
        const w = hash(k, i, j);
        c.strokeStyle = PRINT(0.2 + 0.25 * w); c.lineWidth = 1.1;
        c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke();
        if (pp.dir > 0 && fwdK > 0) {
          if (fwdK < 1) {
            const u = ease.outCubic(fwdK), u0 = Math.max(0, u - 0.3);
            c.strokeStyle = ORANGE(0.95); c.lineWidth = 1.2 + 2.2 * w;
            c.beginPath(); c.moveTo(lerp(x0, x1, u0), lerp(y0, y1, u0)); c.lineTo(lerp(x0, x1, u), lerp(y0, y1, u)); c.stroke();
          } else if (w > 0.45) {
            const fade = 1 - prog(t, s[k]![1], s[k]![1] + 0.5);
            if (fade > 0) { c.strokeStyle = ORANGE(0.9 * fade); c.lineWidth = 1.3; c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke(); }
          }
        }
        if (pp.dir < 0 && bwdK > 0 && w > 0.25) {
          const u = 1 - ease.outCubic(bwdK);
          c.setLineDash([9, 7]);
          c.lineDashOffset = tReal * 140;
          c.strokeStyle = ORANGE(0.95); c.lineWidth = bwdK < 1 ? 1.2 + 1.8 * w : 1.2;
          c.beginPath(); c.moveTo(x1, y1); c.lineTo(lerp(x0, x1, u), lerp(y0, y1, u)); c.stroke();
          c.setLineDash([]);
        }
      }
    }
    // nodes: outlined; solid orange when the pulse has reached them (no half-tones)
    Ls.forEach((l, k) => {
      let on = false;
      if (pp.dir > 0) on = k === 0 ? inAct > 0.5 : pp.pos >= k - 0.05;
      else on = pp.pos <= k + 0.05;
      l.ys.forEach((y, j) => {
        const lit = on && (pp.dir > 0 ? hash(k, j, 5) > 0.3 || k === 0 : hash(k, j, 6) > 0.4);
        if (lit) { c.fillStyle = ORANGE(1); c.beginPath(); c.arc(l.x, y, R, 0, TAU); c.fill(); }
        c.strokeStyle = PRINT(1); c.lineWidth = 2.4;
        c.beginPath(); c.arc(l.x, y, R, 0, TAU); c.stroke();
        if (pp.dir < 0 && lit) {
          // gradient marker
          c.fillStyle = PRINT(1); c.font = font(F.mono(600), 22); c.textAlign = 'center';
          c.fillText('∂', l.x, y + 8);
          c.textAlign = 'left';
        }
      });
      c.fillStyle = PRINT(0.8); c.font = font(F.mono(500), 14); c.letterSpacing = '3px'; c.textAlign = 'center';
      c.fillText(['INPUT x', 'HIDDEN h₁', 'HIDDEN h₂', 'OUTPUT ŷ'][k]!, l.x, 262);
      c.textAlign = 'left'; c.letterSpacing = '0px';
    });
    c.fillStyle = PRINT(0.75); c.font = font(F.serif(400, true), 32); c.textAlign = 'center';
    ['W₁', 'W₂', 'W₃'].forEach((wl, k) => c.fillText(wl, (Ls[k]!.x + Ls[k + 1]!.x) / 2, 240));
    // loss
    const lx = 730;
    c.fillStyle = PRINT(1); c.font = font(F.serif(400, true), 40);
    c.fillText('L', lx, 12); // italic L for the loss (Cormorant has no script ℒ)
    c.textAlign = 'left';
    for (const y of Ls[3]!.ys) { c.strokeStyle = PRINT(0.5); c.lineWidth = 1.1; c.beginPath(); c.moveTo(Ls[3]!.x + R + 3, y); c.lineTo(lx - 22, 0); c.stroke(); }

    c.font = font(F.mono(500), 14); c.letterSpacing = '3px';
    c.fillStyle = PRINT(0.75);
    c.fillText('FORWARD PASS  →', -470, -226);
    c.textAlign = 'right';
    c.fillText('←  BACKWARD PASS  (∂L/∂w)', 860, -160);
    c.textAlign = 'left'; c.letterSpacing = '0px';

    // epoch counter
    const big = tReal >= this.tRep1 - 0.02;
    const epoch = tReal < this.tBack0 ? 41 : 42 + Math.max(0, loop);
    const loss = big ? 0.0001 : 0.693 * Math.pow(0.9, epoch - 41);
    c.fillStyle = PRINT(0.95); c.font = font(F.mono(500), 18); c.letterSpacing = '2px';
    c.textAlign = 'right';
    c.fillText(`EPOCH ${big ? '1,000,000' : String(epoch).padStart(6, '0')}`, 860, -236);
    c.fillStyle = PRINT(0.6);
    c.fillText(`LOSS ${loss.toFixed(4)}`, 860, -210);
    c.textAlign = 'left'; c.letterSpacing = '0px';

    this.drawAnnexLyric(c, tReal, loop);
    c.restore();
  }

  drawAnnexLyric(c: Ctx2, t: number, loop: number) {
    const Ls = this.layers;
    const fam = F.archivo(100, 900), size = 132;
    const yTop = -292;
    c.save();
    c.textBaseline = 'alphabetic';
    c.font = font(fam, size);
    // "Forward" over the input layer, printed L->R within the word
    const fw = layout('Forward', fam, size);
    const fx0 = Ls[0]!.x - fw.width / 2;
    const per = Math.min(0.06, (this.wFwd.end - this.wFwd.start) / fw.glyphs.length);
    for (const g of fw.glyphs) if (t >= this.wFwd.start + g.i * per) { c.fillStyle = PRINT(1); c.fillText(g.ch, fx0 + g.x, yTop); }
    // M, L, P over h1, h2, y-hat, each on its syllable
    ['M', 'L', 'P'].forEach((ch, k) => {
      const ts = this.syl[k]![0];
      if (t < ts) return;
      const w = measure(ch, fam, size);
      // the lyric's comma after P, kerned in under the P's bowl; the syllable bar stops where it starts
      const wb = k === 2 ? glyphX(ch + ',', 1, fam, size) : w;
      const pop = pulse(t, ts, 0.06);
      const x = Ls[k + 1]!.x;
      c.save();
      c.translate(x, yTop);
      c.scale(1 + 0.1 * pop, 1 + 0.1 * pop);
      c.fillStyle = PRINT(1);
      c.fillText(ch, -w / 2, 0);
      if (k === 2) c.fillText(',', -w / 2 + wb, 0);
      c.restore();
      const u = prog(t, ts, ts + 0.14, ease.outCubic) * (1 - prog(t, this.syl[k]![1] + 0.1, this.syl[k]![1] + 0.2));
      if (u > 0) { c.fillStyle = ORANGE(1); c.fillRect(x - w / 2, yTop + 18, wb * u, 9); }
    });
    // "backward," mirrored and set right -> left under the diagram
    if (t >= this.tBack0) {
      const bs = 116;
      // the mirror image of the kerned word: glyph i at the mirrored kerned position
      const lay = layout(this.wBack.w, fam, bs);
      const perB = Math.min(0.05, (this.wBack.end - this.wBack.start) / lay.glyphs.length);
      c.font = font(fam, bs);
      const xr0 = Ls[3]!.x + 70, xr = xr0 - lay.width;
      for (const g of lay.glyphs) {
        if (t >= this.tBack0 + g.i * perB) {
          c.save(); c.translate(xr0 - g.x, 372); c.scale(-1, 1);
          c.fillStyle = PRINT(1); c.fillText(g.ch, 0, 0);
          c.restore();
        }
      }
      const u = prog(t, this.tBack0, this.tBack1, ease.linear);
      if (u > 0 && u < 1) { c.fillStyle = ORANGE(1); c.fillRect(xr0 - (xr0 - xr) * u, 390, 12, 9); }
    }
    // "repeat" at the far left of the same row, re-stamped on every stutter
    if (t >= this.tRep0) {
      c.font = font(fam, 116);
      const rx = -560;
      const seg = (this.tRep1 - this.tRep0) / 3;
      const lk = loop < 0 ? 0 : Math.min(2, loop);
      const pop = t < this.tRep1 ? pulse(t, this.tRep0 + lk * seg, 0.05) : 0;
      c.save();
      c.translate(rx + 200, 372);
      c.scale(1 + 0.14 * pop, 1 + 0.14 * pop);
      c.fillStyle = PRINT(1);
      c.fillText('repeat', -200, 0);
      c.restore();
      if (loop >= 0 && loop < 3) {
        c.fillStyle = ORANGE(1); c.font = font(F.mono(700), 24); c.letterSpacing = '3px';
        c.fillText(`×${loop + 1}`, rx + measure('repeat', fam, 116) + 24, 372);
        c.letterSpacing = '0px';
      }
    }
    c.restore();
  }

  // ------------------------------------------------------------------ C. the appendix (von Neumann)
  drawAppendix(c: Ctx2, t: number) {
    c.save();
    c.translate(C.x, C.y);
    c.textBaseline = 'alphabetic';
    c.fillStyle = PRINT(0.7); c.font = font(F.mono(500), 16); c.letterSpacing = '4px';
    c.fillText('APPENDIX C — LEGACY ARCHITECTURES (FOR REFERENCE ONLY)', -820, -482);
    c.letterSpacing = '0px';
    c.fillStyle = PRINT(0.9); c.fillRect(-820, -467, 1640, 1.5);
    // heading: the lyric, printed word by word
    const fam = F.archivo(100, 900), size = 112;
    c.font = font(fam, size);
    const hx = -820;
    const hy = -340;
    // each word printed on its own, at its kerned position in the heading set as one run
    const hws = [this.wNow, this.wVon, this.wNeu];
    const head = hws.map((w) => w.w).join(' ');
    let gi = 0, extra = 0, prev = '';
    for (const w of hws) {
      // optical word space: two diagonals facing across it ("Now von") read as one word at the font's space
      if (/[vwyVWY]$/.test(prev) && /^[vwyVWYAT]/.test(w.w)) extra += 0.07 * size;
      prev = w.w;
      if (t >= w.start) {
        const k = prog(t, w.start, w.start + 0.07, ease.outCubic);
        c.save();
        c.translate(hx + extra + glyphX(head, gi, fam, size), hy + 10 * (1 - k));
        c.fillStyle = PRINT(k);
        c.fillText(w.w, 0, 0);
        c.restore();
      }
      gi += Array.from(w.w).length + 1;
    }
    const x = hx + extra + measure(head + ' ', fam, size);
    this.drawVonNeumann(c, t);
    // orange marker strikes
    const strike = (x0: number, y0: number, x1: number, y1: number, t0: number, seed: number) => {
      const k = prog(t, t0, t0 + 0.1, ease.outQuad);
      if (k <= 0) return;
      c.save();
      c.strokeStyle = ORANGE(0.95); c.lineCap = 'round'; c.lineJoin = 'round';
      const N = 30;
      for (let pass = 0; pass < 3; pass++) {
        c.lineWidth = 17 - pass * 4;
        c.beginPath();
        for (let i = 0; i <= N * k; i++) {
          const u = i / N;
          const px = lerp(x0, x1, u) + noise1(u * 6 + seed + pass, 3) * 5;
          const py = lerp(y0, y1, u) + noise1(u * 5 + seed * 2 + pass, 4) * 6 + Math.sin(u * 3.1) * 16;
          if (i === 0) c.moveTo(px, py); else c.lineTo(px, py);
        }
        c.stroke();
      }
      c.restore();
    };
    strike(-660, -230, 680, 370, this.tObs, 1);
    strike(-620, 380, 660, -250, this.tStrike2, 5);
    // hand-written "obsolete" in orange marker next to the heading, with an underline
    if (t >= this.tObs) {
      c.save();
      c.translate(x + 6, hy + 12);
      c.rotate(-0.07);
      c.strokeStyle = ORANGE(1); c.lineWidth = 7; c.lineCap = 'round'; c.lineJoin = 'round';
      drawStrokeText(c, this.obsHand, writtenLen(this.obsHand, this.obsCharTimes, t));
      c.restore();
    }
    c.restore();
  }

  drawVonNeumann(c: Ctx2, t: number) {
    const shadowHatch = (x: number, y: number, w: number, h: number, off = 13) => {
      c.save();
      c.beginPath(); c.rect(x + off, y + off, w, h); c.rect(x, y, w, h); c.clip('evenodd');
      c.strokeStyle = PRINT(0.5); c.lineWidth = 1.2; c.beginPath();
      for (let d = 0; d < w + h + off; d += 8) { c.moveTo(x + off + d, y + off); c.lineTo(x + off + d - h, y + off + h); }
      c.stroke(); c.restore();
    };
    const box = (x: number, y: number, w: number, h: number, title: string, sub?: string, hot = 0) => {
      c.strokeStyle = PRINT(1); c.lineWidth = 2.6;
      c.strokeRect(x, y, w, h);
      if (hot > 0) { c.fillStyle = PRINT(0.08 * hot); c.fillRect(x + 6, y + 6, w - 12, h - 12); }
      c.fillStyle = PRINT(1); c.textAlign = 'center';
      c.font = font(F.mono(600), 19); c.letterSpacing = '3px';
      c.fillText(title, x + w / 2, y + h / 2 + (sub ? -4 : 7));
      if (sub) { c.font = font(F.mono(400), 14); c.fillStyle = PRINT(0.65); c.fillText(sub, x + w / 2, y + h / 2 + 22); }
      c.textAlign = 'left'; c.letterSpacing = '0px';
    };
    const arrow = (x0: number, y0: number, x1: number, y1: number, both = false) => {
      c.strokeStyle = PRINT(1); c.fillStyle = PRINT(1); c.lineWidth = 2.4;
      c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke();
      const head = (xa: number, ya: number, xb: number, yb: number) => {
        const a = Math.atan2(yb - ya, xb - xa);
        c.beginPath(); c.moveTo(xb, yb);
        c.lineTo(xb - 18 * Math.cos(a - 0.35), yb - 18 * Math.sin(a - 0.35));
        c.lineTo(xb - 18 * Math.cos(a + 0.35), yb - 18 * Math.sin(a + 0.35));
        c.closePath(); c.fill();
      };
      head(x0, y0, x1, y1);
      if (both) head(x1, y1, x0, y0);
    };
    // fetch-decode-execute cycle, one stage per beat
    const bt = this.ctx.audio.beatAt(t);
    const stage = ((Math.floor(bt) % 4) + 4) % 4;
    const hot = (s: number) => (stage === s ? 1 - (bt - Math.floor(bt)) * 0.6 : 0);
    const cx = -330, cy = -225, cw = 660, ch = 330;
    shadowHatch(cx, cy, cw, ch, 15);
    c.strokeStyle = PRINT(1); c.lineWidth = 3; c.strokeRect(cx, cy, cw, ch);
    c.fillStyle = PRINT(1); c.font = font(F.mono(700), 18); c.letterSpacing = '4px';
    c.fillText('CENTRAL PROCESSING UNIT', cx + 20, cy + 34);
    c.letterSpacing = '0px';
    box(cx + 40, cy + 70, 270, 100, 'CONTROL UNIT', 'decode', hot(1));
    box(cx + 350, cy + 70, 270, 100, 'ALU', 'arithmetic / logic', hot(2));
    box(cx + 40, cy + 200, 580, 90, 'REGISTERS', 'PC · IR · ACC · MAR · MDR', hot(3));
    shadowHatch(-330, 225, 660, 115);
    box(-330, 225, 660, 115, 'MEMORY UNIT', 'instructions + data, one bus', hot(0));
    shadowHatch(-790, -135, 260, 150);
    box(-790, -135, 260, 150, 'INPUT', 'device');
    shadowHatch(530, -135, 260, 150);
    box(530, -135, 260, 150, 'OUTPUT', 'device');
    arrow(-530, -60, cx - 4, -60);
    arrow(cx + cw + 4, -60, 526, -60);
    arrow(-60, cy + ch + 4, -60, 221, true);
    arrow(60, cy + ch + 4, 60, 221, true);
    c.fillStyle = PRINT(0.8); c.font = font(F.serif(400, true), 30);
    c.fillText('the bottleneck', 100, 180);
    // the instruction token shuttling over the bus, one trip per beat
    const u = bt - Math.floor(bt);
    const up = Math.floor(bt) % 2 === 0;
    const ty = up ? lerp(215, 118, ease.inOutCubic(u)) : lerp(118, 215, ease.inOutCubic(u));
    c.fillStyle = PRINT(1); c.fillRect(up ? -70 : 50, ty - 8, 20, 16);
    c.fillStyle = PRINT(0.85); c.font = font(F.serif(400, true), 30);
    c.fillText('Fig. C.1 — The stored-program computer (1945).', 372, 262);
    c.fillText('One memory, one bus, one thing at a time.', 372, 298);
  }

  override dispose() {
    this.pageRT.dispose();
  }
}

/** Post overrides blended from a to b by k (a key one side leaves out is the engine default there). */
function mixPost(a: PostOverrides, b: PostOverrides, k: number): PostOverrides {
  const out: Record<string, unknown> = {};
  for (const key of new Set([...Object.keys(a), ...Object.keys(b)]) as Set<keyof PostParams>) {
    const x = a[key] ?? DEFAULT_POST[key], y = b[key] ?? DEFAULT_POST[key];
    if (typeof x === 'number' && typeof y === 'number') out[key] = lerp(x, y, k);
    else if (Array.isArray(x) && Array.isArray(y)) out[key] = [lerp(x[0], y[0], k), lerp(x[1], y[1], k)];
    else out[key] = k < 0.5 ? x : y;
  }
  out.shake ??= [0, 0];
  return out as PostOverrides;
}

/** Written length of a StrokeText with explicit per-char [start, end] times. */
function writtenLen(st: StrokeText, charTimes: [number, number][], t: number) {
  let len = 0;
  for (let i = 0; i < st.charRange.length; i++) {
    const [a, b] = st.charRange[i]!;
    const [t0, t1] = charTimes[i] ?? [Infinity, Infinity];
    if (t >= t1) len = b;
    else if (t > t0) { len = a + (b - a) * ((t - t0) / Math.max(1e-3, t1 - t0)); break; }
    else break;
  }
  return len;
}
