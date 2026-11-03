import { z } from "zod";

const PLAY_EVIDENCE_ENTITY_TYPES = new Set(['evidence','clue','claim','proof_chain']);
export function isPlayEvidenceEntityType(type:string):boolean {
  return PLAY_EVIDENCE_ENTITY_TYPES.has(type);
}

// Descriptive event metadata, not an executable command or a closed game taxonomy.
export const PlayActionKindSchema = z.string().trim().min(1);
export type PlayActionKind = z.infer<typeof PlayActionKindSchema>;

export const PlayActionIntentSchema = z.object({
  actionKind: PlayActionKindSchema,
  targetEntityLabel: z.string().min(1).optional(),
  targetLocationLabel: z.string().min(1).optional(),
  intent: z.string().min(1),
  manner: z.string().default(""),
  risk: z.string().default(""),
  ambiguity: z.string().default(""),
  secondaryActions: z.array(z.string().min(1)).default([]),
}).strict();
export type PlayActionIntentInput = z.input<typeof PlayActionIntentSchema>;
export type PlayActionIntent = z.infer<typeof PlayActionIntentSchema>;

export const PlayEntityTypeSchema = z.enum([
  "actor",
  "location",
  "item",
  "evidence",
  "clue",
  "claim",
  "proof_chain",
  "organization",
  "rule",
  "scene",
  "event",
]);
export type PlayEntityType = z.infer<typeof PlayEntityTypeSchema>;

export const PlayEntitySchema = z.object({
  id: z.string().min(1),
  type: PlayEntityTypeSchema,
  label: z.string().min(1),
  summary: z.string(),
  status: z.string().default(""),
  createdEventId: z.string().min(1).optional(),
  updatedEventId: z.string().min(1).optional(),
}).strict();
export type PlayEntityInput = z.input<typeof PlayEntitySchema>;
export type PlayEntity = z.infer<typeof PlayEntitySchema>;

export const PlayVisibilitySchema = z.record(z.string(), z.string());
export type PlayVisibility = z.infer<typeof PlayVisibilitySchema>;

export const PlayEdgeSchema = z.object({
  id: z.string().min(1),
  fromId: z.string().min(1),
  type: z.string().min(1),
  toId: z.string().min(1),
  value: z.record(z.string(), z.unknown()).default({}),
  validFromEventId: z.string().min(1),
  validUntilEventId: z.string().min(1).nullable().default(null),
  sourceEventId: z.string().min(1),
  visibility: PlayVisibilitySchema.default({}),
  strength: z.number().finite().optional(),
}).strict();
export type PlayEdgeInput = z.input<typeof PlayEdgeSchema>;
export type PlayEdge = z.infer<typeof PlayEdgeSchema>;

export const PlayStateSlotKindSchema = z.enum([
  "resource",
  "relation",
  "pressure",
  "clue",
  "evidence",
  "flag",
  "timer",
]);
export type PlayStateSlotKind = z.infer<typeof PlayStateSlotKindSchema>;

export const PlayStateSlotSchema = z.object({
  id: z.string().min(1),
  ownerEntityId: z.string().min(1).nullable().optional(),
  kind: PlayStateSlotKindSchema,
  label: z.string().min(1),
  value: z.unknown(),
  updatedEventId: z.string().min(1),
}).strict();
export type PlayStateSlotInput = z.input<typeof PlayStateSlotSchema>;
export type PlayStateSlot = z.infer<typeof PlayStateSlotSchema>;

export const PlayTimeAdvanceSchema = z.object({
  elapsed: z.string().min(1),
  anchor: z.string().default(""),
  rationale: z.string().default(""),
  synchronized: z.array(z.string().min(1)).default([]),
}).strict();
export type PlayTimeAdvanceInput = z.input<typeof PlayTimeAdvanceSchema>;
export type PlayTimeAdvance = z.infer<typeof PlayTimeAdvanceSchema>;

export const PlayEvidenceStatusSchema = z.enum([
  "unknown",
  "hinted",
  "seen",
  "collected",
  "verified",
  "weaponized",
  "exposed",
  "exhausted",
]);
export type PlayEvidenceStatus = z.infer<typeof PlayEvidenceStatusSchema>;

export const PlayEvidenceTransitionSchema = z.object({
  entityId: z.string().min(1),
  from: PlayEvidenceStatusSchema.optional(),
  to: PlayEvidenceStatusSchema,
  reason: z.string().default(""),
}).strict();
export type PlayEvidenceTransitionInput = z.input<typeof PlayEvidenceTransitionSchema>;
export type PlayEvidenceTransition = z.infer<typeof PlayEvidenceTransitionSchema>;

export const PlayEventSchema = z.object({
  id: z.string().min(1),
  turn: z.number().int().min(0),
  actionKind: PlayActionKindSchema,
  rawInput: z.string().min(1),
  outcomeSummary: z.string().default(""),
  timeAdvance: PlayTimeAdvanceSchema.optional(),
  createdAt: z.string().min(1),
}).strict();
export type PlayEventInput = z.input<typeof PlayEventSchema>;
export type PlayEvent = z.infer<typeof PlayEventSchema>;

export const PlayCurrentStateSchema = z.object({
  turn: z.number().int().nonnegative().default(0),
  lastEventId: z.string().min(1).nullable().default(null),
  lastAction: PlayActionIntentSchema.optional(),
  lastSummary: z.string().default(""),
  timeAdvance: PlayTimeAdvanceSchema.nullable().default(null),
  blocked: z.boolean().default(false),
  worldContract: z.string().default(""),
  visualContract: z.string().default(""),
  premise: z.string().default(""),
  worldId: z.string().min(1).optional(),
  runId: z.string().min(1).optional(),
  mode: z.enum(["open", "guided"]).optional(),
  graphEditedAt: z.string().min(1).optional(),
}).strict();
export type PlayCurrentStateInput = z.input<typeof PlayCurrentStateSchema>;
export type PlayCurrentState = z.infer<typeof PlayCurrentStateSchema>;

const PlayEdgeExpireSchema = z.object({
  edgeId: z.string().min(1),
  validUntilEventId: z.string().min(1),
  reason: z.string().default(""),
}).strict();

export const PlayMutationSchema = z.object({
  eventId: z.string().min(1),
  turn: z.number().int().min(0),
  actionKind: PlayActionKindSchema,
  summary: z.string().default(""),
  timeAdvance: PlayTimeAdvanceSchema.optional(),
  entities: z.object({ upsert: z.array(PlayEntitySchema) }).strict(),
  edges: z.object({
    upsert: z.array(PlayEdgeSchema),
    expire: z.array(PlayEdgeExpireSchema),
  }).strict(),
  stateSlots: z.object({ upsert: z.array(PlayStateSlotSchema) }).strict(),
  evidence: z.object({ transitions: z.array(PlayEvidenceTransitionSchema) }).strict(),
  blocked: z.boolean(),
  blockedReason: z.string(),
  notes: z.array(z.string()),
}).strict();
export type PlayMutationInput = z.input<typeof PlayMutationSchema>;
export type PlayMutation = z.infer<typeof PlayMutationSchema>;
