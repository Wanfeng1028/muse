import { z } from "zod";
import { ExecutionStateSchema } from "./events.js";
import { assertSafeBookId, isSafeBookId } from "../utils/book-id.js";

export const SessionKindSchema = z.enum(["chat", "work", "book-create", "book", "short", "play", "script", "storyboard", "interactive-film", "edit", "interactive-film-authoring"]);
export type SessionKind = z.infer<typeof SessionKindSchema>;
export const PlayModeSchema = z.enum(["open", "guided"]);
export type PlayMode = z.infer<typeof PlayModeSchema>;

// TUI confirmations persist the already-validated action envelope returned by
// propose_action. The action and payload are revalidated against the current
// action schemas when the user confirms.
export const PendingProposedActionSchema = z.object({
  action: z.string().min(1),
  targetSessionKind: SessionKindSchema,
  instruction: z.string().min(1),
  title: z.string().min(1).optional(),
  summary: z.string().min(1).optional(),
  playMode: PlayModeSchema.optional(),
  requestedSkills: z.array(z.string().min(1)).optional(),
  actionPayload: z.record(z.unknown()).optional(),
}).strict();

export type PendingProposedAction = z.infer<typeof PendingProposedActionSchema>;

export const PipelineStageSchema = z.object({
  label: z.string(),
  status: z.enum(["pending", "active", "completed"]),
  progress: z.object({
    status: z.string().optional(),
    elapsedMs: z.number().nonnegative(),
    totalChars: z.number().int().nonnegative(),
    chineseChars: z.number().int().nonnegative(),
  }).strict().optional(),
}).strict();

export type PipelineStage = z.infer<typeof PipelineStageSchema>;

export const ToolExecutionSchema = z.object({
  id: z.string(),
  tool: z.string(),
  agent: z.string().optional(),
  label: z.string(),
  status: z.enum(["running", "processing", "completed", "error"]),
  args: z.record(z.unknown()).optional(),
  result: z.string().optional(),
  details: z.unknown().optional(),
  error: z.string().optional(),
  stages: z.array(PipelineStageSchema).optional(),
  logs: z.array(z.string()).optional(),
  background: z.boolean().optional(),
  startedAt: z.number(),
  completedAt: z.number().optional(),
}).strict();

export type ToolExecution = z.infer<typeof ToolExecutionSchema>;

export const InteractionMessageSchema = z.object({
  role: z.enum(["user", "assistant", "system"]),
  // Assistant turns may be tool-only. In that case the user-facing content is
  // rendered from toolExecutions, not from free text.
  content: z.string(),
  thinking: z.string().optional(),
  toolExecutions: z.array(ToolExecutionSchema).optional(),
  timestamp: z.number().int().nonnegative(),
}).strict();

export type InteractionMessage = z.infer<typeof InteractionMessageSchema>;

export const InteractionSessionSchema = z.object({
  sessionId: z.string().min(1),
  projectRoot: z.string().min(1),
  sessionKind: SessionKindSchema.optional(),
  profileId: z.string().min(1).optional(),
  workId: z.string().min(1).nullable().optional(),
  playMode: PlayModeSchema.optional(),
  modelOverride: z.string().min(1).optional(),
  serviceOverride: z.string().min(1).optional(),
  activeBookId: z.string().min(1).optional(),
  activeChapterNumber: z.number().int().min(1).optional(),
  messages: z.array(InteractionMessageSchema).default([]),
  pendingProposedAction: PendingProposedActionSchema.optional(),
  currentExecution: ExecutionStateSchema.optional(),
}).strict();

export type InteractionSession = z.infer<typeof InteractionSessionSchema>;

// -- Per-book session --

export const BookSessionSchema = z.object({
  sessionId: z.string().min(1),
  bookId: z.string().refine(isSafeBookId, "Invalid bookId").nullable(),
  sessionKind: SessionKindSchema.optional(),
  profileId: z.string().min(1).optional(),
  workId: z.string().min(1).nullable().optional(),
  proposalAction: z.string().min(1).optional(),
  playMode: PlayModeSchema.optional(),
  modelOverride: z.string().min(1).optional(),
  serviceOverride: z.string().min(1).optional(),
  title: z.string().nullable().default(null),
  messages: z.array(InteractionMessageSchema).default([]),
  currentExecution: ExecutionStateSchema.optional(),
  createdAt: z.number().int().nonnegative(),
  updatedAt: z.number().int().nonnegative(),
}).strict();

export type BookSession = z.infer<typeof BookSessionSchema>;

export function createBookSession(
  bookId: string | null,
  sessionId?: string,
  sessionKind?: SessionKind,
  options?: {
    readonly playMode?: PlayMode;
    readonly profileId?: string;
    readonly workId?: string | null;
    readonly proposalAction?: string;
    readonly modelOverride?: string;
    readonly serviceOverride?: string;
  },
): BookSession {
  const now = Date.now();
  const safeBookId = bookId === null ? null : assertSafeBookId(bookId);
  return {
    sessionId: sessionId ?? `${now}-${Math.random().toString(36).slice(2, 8)}`,
    bookId: safeBookId,
    sessionKind,
    ...(options?.profileId ? { profileId: options.profileId } : {}),
    ...("workId" in (options ?? {}) ? { workId: options?.workId ?? null } : safeBookId ? { workId: safeBookId } : {}),
    ...(options?.proposalAction ? { proposalAction: options.proposalAction } : {}),
    ...(options?.playMode ? { playMode: options.playMode } : {}),
    ...(options?.modelOverride ? { modelOverride: options.modelOverride } : {}),
    ...(options?.serviceOverride ? { serviceOverride: options.serviceOverride } : {}),
    title: null,
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
}

export function appendBookSessionMessage(
  session: BookSession,
  message: InteractionMessage,
): BookSession {
  return {
    ...session,
    messages: [...session.messages, message].sort((a, b) => a.timestamp - b.timestamp),
    updatedAt: Date.now(),
  };
}

export function bindActiveBook(
  session: InteractionSession,
  bookId: string,
  chapterNumber?: number,
): InteractionSession {
  return {
    ...session,
    activeBookId: bookId,
    ...(chapterNumber !== undefined ? { activeChapterNumber: chapterNumber } : {}),
  };
}

export function appendInteractionMessage(
  session: InteractionSession,
  message: InteractionMessage,
): InteractionSession {
  return {
    ...session,
    messages: [...session.messages, message].sort((left, right) => left.timestamp - right.timestamp),
  };
}
