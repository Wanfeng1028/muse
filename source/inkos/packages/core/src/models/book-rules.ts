import { z } from "zod";

const ProtagonistSchema = z.object({
  name: z.string(),
  personalityLock: z.array(z.string()),
  behavioralConstraints: z.array(z.string()),
}).strict().optional();

const GenreLockSchema = z.object({
  primary: z.string(),
  forbidden: z.array(z.string()),
}).strict().optional();

export const BookRulesSchema = z.object({
  version: z.literal("2"),
  protagonist: ProtagonistSchema,
  genreLock: GenreLockSchema,
  narrativePerson: z.string().trim().min(1).optional(),
  prohibitions: z.array(z.string()),
  enableFullCastTracking: z.boolean(),
  fanficMode: z.string().trim().min(1).optional(),
  allowedDeviations: z.array(z.string()),
}).strict();

export type BookRules = z.infer<typeof BookRulesSchema>;

export interface ParsedBookRules {
  readonly rules: BookRules;
  readonly body: string;
}
