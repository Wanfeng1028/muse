/**
 * Particle typography source.
 *
 * The glyphs are never drawn as text on screen. The font outline is rasterised
 * into an offscreen canvas, the ink pixels are sampled, and every sample is
 * converted into a world-space target position. The particle shader then reads
 * those positions from a float texture, so 「天元」 is literally assembled out of
 * the same particles that were the universe one second earlier.
 */

import {
  GLYPH_CANVAS_WIDTH,
  GLYPH_FONT_FILE,
  GLYPH_TEXT,
  GLYPH_TEXTURE_WIDTH,
  TEXT_QUAD_WIDTH,
} from "../config";
import { staticFile } from "remotion";

export type GlyphTargets = {
  /** xyz triples in world units, packed for RGBA32F upload. */
  readonly data: Float32Array;
  /** Number of usable samples. */
  readonly count: number;
  readonly texWidth: number;
  readonly texHeight: number;
  /** Unused slots are padded with the last sample so they stay off-screen. */
  readonly quadWidth: number;
  readonly quadHeight: number;
  /** Mean distance between two neighbouring samples, in world units. */
  readonly spacing: number;
};

let cached: Promise<GlyphTargets> | null = null;

const loadFont = async (): Promise<void> => {
  const face = new FontFace("TianyuanDisplay", `url(${staticFile(GLYPH_FONT_FILE)})`, {
    style: "normal",
    weight: "700",
  });
  await face.load();
  (document.fonts as FontFaceSet).add(face);
};

const buildTargets = async (): Promise<GlyphTargets> => {
  await loadFont();

  const canvas = document.createElement("canvas");
  canvas.width = GLYPH_CANVAS_WIDTH;
  canvas.height = Math.round(GLYPH_CANVAS_WIDTH / 2);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) {
    throw new Error("2D canvas context unavailable for glyph sampling");
  }

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  // Size the text to 88% of the canvas width.
  const targetWidth = canvas.width * 0.88;
  let fontSize = canvas.height * 0.8;
  ctx.font = `700 ${fontSize}px TianyuanDisplay, "Noto Sans SC", "Microsoft YaHei", sans-serif`;
  const probe = ctx.measureText(GLYPH_TEXT);
  const measured = probe.width || fontSize * GLYPH_TEXT.length;
  fontSize = (fontSize * targetWidth) / measured;
  ctx.font = `700 ${fontSize}px TianyuanDisplay, "Noto Sans SC", "Microsoft YaHei", sans-serif`;
  ctx.fillText(GLYPH_TEXT, canvas.width / 2, canvas.height / 2);

  const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const alpha = image.data;

  let minX = canvas.width;
  let maxX = -1;
  let minY = canvas.height;
  let maxY = -1;
  for (let y = 0; y < canvas.height; y++) {
    for (let x = 0; x < canvas.width; x++) {
      if (alpha[(y * canvas.width + x) * 4 + 3] > 120) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  if (maxX < 0) {
    throw new Error("Glyph rasterisation produced no ink");
  }

  const boxW = maxX - minX + 1;
  const boxH = maxY - minY + 1;
  const quadWidth = TEXT_QUAD_WIDTH;
  const quadHeight = (TEXT_QUAD_WIDTH * boxH) / boxW;

  // Sample every ink pixel inside the bounding box.
  const samples: number[] = [];
  // Deterministic xorshift: the mapping has to be stable across renders, but it
  // must not be the rasteriser's own row-major order (see the shuffle below).
  let rngState = 0x9e3779b1 >>> 0;
  const rng = () => {
    rngState ^= rngState << 13;
    rngState >>>= 0;
    rngState ^= rngState >>> 17;
    rngState ^= rngState << 5;
    rngState >>>= 0;
    return rngState / 4294967296;
  };
  for (let y = minY; y <= maxY; y++) {
    for (let x = minX; x <= maxX; x++) {
      if (alpha[(y * canvas.width + x) * 4 + 3] > 120) {
        const u = (x - minX) / boxW;
        const v = (y - minY) / boxH;
        // The third component is depth, so it wants a real hash rather than
        // the 17-step sawtooth that used to band the strokes in Z.
        samples.push((u - 0.5) * quadWidth, (0.5 - v) * quadHeight, rng() - 0.5);
      }
    }
  }

  const count = samples.length / 3;
  /* Shuffle the sample order.
     Only 40k of these points ever receive a particle, and the particle index
     walks the list with a fixed stride. Read in raster order, every stride-th
     ink pixel lands on the same diagonal of the font's own pixel grid, so the
     title comes out covered in a printed mesh. Shuffling turns that stride into
     an even, structureless subset of the outline. */
  for (let i = count - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    for (let k = 0; k < 3; k++) {
      const swap = samples[i * 3 + k];
      samples[i * 3 + k] = samples[j * 3 + k];
      samples[j * 3 + k] = swap;
    }
  }

  const texWidth = GLYPH_TEXTURE_WIDTH;
  const texHeight = Math.max(1, Math.ceil(count / texWidth));
  const data = new Float32Array(texWidth * texHeight * 4);
  for (let i = 0; i < count; i++) {
    data[i * 4 + 0] = samples[i * 3 + 0];
    data[i * 4 + 1] = samples[i * 3 + 1];
    data[i * 4 + 2] = samples[i * 3 + 2];
    data[i * 4 + 3] = 1;
  }
  // Pad the tail so a stray lookup can never land on (0,0,0).
  for (let i = count; i < texWidth * texHeight; i++) {
    data[i * 4 + 0] = samples[0];
    data[i * 4 + 1] = samples[1];
    data[i * 4 + 2] = samples[2];
    data[i * 4 + 3] = 1;
  }

  const inkRatio = count / (boxW * boxH);
  const spacing = quadWidth / (boxW * Math.sqrt(Math.max(inkRatio, 1e-4)));

  return {
    data,
    count,
    texWidth,
    texHeight,
    quadWidth,
    quadHeight,
    spacing,
  };
};

export const sampleGlyphTargets = (): Promise<GlyphTargets> => {
  if (!cached) {
    cached = buildTargets();
  }
  return cached;
};
