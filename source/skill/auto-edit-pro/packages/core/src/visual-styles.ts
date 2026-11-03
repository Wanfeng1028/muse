import {CATALOG_STYLE_IDS} from './catalog-styles';
import {z} from 'zod';

// Independent of schema.ts so renderer, planner and validation share one contract.
export const VISUAL_STYLE_IDS = [
  'balatro', 'crt-warp', 'cubes', 'hyperspeed',
  'shape-waves', 'ripple-distortion', 'evil-eye', 'electric-border', 'lightning',
  'grid-motion', 'waves', 'metallic-paint', 'circular-carousel', 'micro-slats',
  'ghost-fibers', 'acid-squares', 'light-tunnel', 'light-pillar', 'floating-lines',
  'grid-scan', 'prismatic-burst',
  ...CATALOG_STYLE_IDS,
] as const;
export type VisualStyleId = (typeof VISUAL_STYLE_IDS)[number];
const uint32 = z.number().int().min(0).max(0xffffffff);
const hex = z.string().regex(/^#[0-9a-f]{6}$/i);
export const VisualStyleSchema = z.object({
  id: z.enum(VISUAL_STYLE_IDS),
  seed: uint32,
  intensity: z.number().min(0).max(1),
  colors: z.tuple([hex, hex, hex]).optional(),
});
export const StyleMixSchema = z.object({
  mode: z.literal('seeded-shuffle'),
  seed: uint32,
  pool: z.array(z.enum(VISUAL_STYLE_IDS)).min(1).max(VISUAL_STYLE_IDS.length)
    .refine((pool) => new Set(pool).size === pool.length, 'Style pool must contain unique style IDs'),
});
export type VisualStyle = z.infer<typeof VisualStyleSchema>;
export type StyleMix = z.infer<typeof StyleMixSchema>;
export type StyleOptions = {styleMix?: 'seeded-shuffle' | 'legacy'; styleSeed?: number; stylePool?: VisualStyleId[]};

export const validateStyleOptions = (options: StyleOptions): void => {
  z.object({styleMix: z.enum(['seeded-shuffle', 'legacy']).optional(), styleSeed: uint32.optional(), stylePool: StyleMixSchema.shape.pool.optional()}).parse(options);
  if (options.styleMix === 'legacy' && (options.styleSeed !== undefined || options.stylePool !== undefined)) {
    throw new Error('Legacy style mode does not accept --style-seed or --style-pool');
  }
};

// FNV-1a is stable across platforms; no current time, runtime random or frame state.
export const deriveStyleSeed = (id: string): number => {
  let hash = 0x811c9dc5;
  for (let index = 0; index < id.length; index += 1) hash = Math.imul(hash ^ id.charCodeAt(index), 0x01000193) >>> 0;
  return hash;
};

export const seededStyleAssignments = (count: number, config: StyleMix): VisualStyleId[] => {
  StyleMixSchema.parse(config);
  if (!Number.isInteger(count) || count < 0) throw new Error('Style assignment count must be a nonnegative integer');
  let state = config.seed;
  const next = (): number => {
    state = (state + 0x6d2b79f5) >>> 0;
    let result = Math.imul(state ^ (state >>> 15), state | 1);
    result ^= result + Math.imul(result ^ (result >>> 7), result | 61);
    return ((result ^ (result >>> 14)) >>> 0) / 4294967296;
  };
  const result: VisualStyleId[] = [];
  while (result.length < count) {
    const bag = [...config.pool];
    for (let index = bag.length - 1; index > 0; index -= 1) {
      const swap = Math.floor(next() * (index + 1));
      [bag[index], bag[swap]] = [bag[swap], bag[index]];
    }
    if (bag.length > 1 && result.at(-1) === bag[0]) [bag[0], bag[1]] = [bag[1], bag[0]];
    result.push(...bag.slice(0, count - result.length));
  }
  return result;
};

export const parseStyleCliOptions = (args: Record<string, string | boolean>): StyleOptions => {
  const options: StyleOptions = {};
  if (args['style-mix'] !== undefined) {
    if (args['style-mix'] !== 'seeded-shuffle' && args['style-mix'] !== 'legacy') throw new Error('Invalid --style-mix; expected seeded-shuffle or legacy');
    options.styleMix = args['style-mix'];
  }
  if (args['style-seed'] !== undefined) {
    const raw = args['style-seed'];
    if (typeof raw !== 'string' || !/^\d+$/.test(raw) || Number(raw) > 0xffffffff) throw new Error('Invalid --style-seed; expected an integer from 0 to 4294967295');
    options.styleSeed = Number(raw);
  }
  if (args['style-pool'] !== undefined) {
    const raw = args['style-pool'];
    if (typeof raw !== 'string') throw new Error('Invalid --style-pool; expected comma-separated style IDs');
    options.stylePool = raw.split(',').map((id) => id.trim()) as VisualStyleId[];
  }
  validateStyleOptions(options);
  return options;
};
