import { z } from "zod";

export const ChapterMemoSchema = z.object({
  chapter: z.number().int().min(1),
  goal: z.string().min(1),
  body: z.string().min(1),
  threadRefs: z.array(z.string()),
}).strict();

export type ChapterMemo = z.infer<typeof ChapterMemoSchema>;

export const ChapterIntentSchema = z.object({
  chapter: z.number().int().min(1),
  goal: z.string().min(1),
}).strict();

export type ChapterIntent = z.infer<typeof ChapterIntentSchema>;

export const ContextSourceSchema = z.object({
  source: z.string().min(1),
  reason: z.string().min(1),
  excerpt: z.string().optional(),
  protection: z.enum(["protected", "compressible"]),
}).strict();

export type ContextSource = z.infer<typeof ContextSourceSchema>;

export const ContextPackageSchema = z.object({
  chapter: z.number().int().min(1),
  selectedContext: z.array(ContextSourceSchema),
}).strict();

export type ContextPackage = z.infer<typeof ContextPackageSchema>;

export const ChapterTraceSchema = z.object({
  chapter: z.number().int().min(1),
  plannerInputs: z.array(z.string()),
  composerInputs: z.array(z.string()),
  selectedSources: z.array(z.string()),
  contextTiers: z.object({
    protectedSources: z.array(z.string()),
    compressibleSources: z.array(z.string()),
  }).strict(),
  tokenBudget: z.object({
    protectedTokens: z.number().int().nonnegative(),
    compressibleTokens: z.number().int().nonnegative(),
    totalSelectedTokens: z.number().int().nonnegative(),
  }).strict(),
  compression: z.object({
    compiledSource: z.string().min(1),
    protectedSources: z.array(z.string()),
    compressedSources: z.array(z.string()),
    protectedTokens: z.number().int().nonnegative(),
    compressibleTokens: z.number().int().nonnegative(),
    budgetTokens: z.number().int().nonnegative(),
  }).strict().optional(),
  retrieval: z.object({
    engine: z.literal("sqlite-fts5-bm25"),
    query: z.string(),
    selectionMode: z.enum(["semantic", "complete"]),
    candidates: z.array(z.object({
      id: z.string(),
      kind: z.string(),
      source: z.string(),
      score: z.number(),
    }).strict()),
    semanticSelectedIds: z.array(z.string()),
  }).strict().optional(),
  notes: z.array(z.string()),
}).strict();

export type ChapterTrace = z.infer<typeof ChapterTraceSchema>;
