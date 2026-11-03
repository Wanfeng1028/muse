import { readdir, rm } from "node:fs/promises";
import { createBookSession } from "./session.js";
import type { BookSession, PlayMode, SessionKind } from "./session.js";
import {
  appendTranscriptEvents,
  readTranscriptEvents,
  sessionsDir,
  transcriptPath,
} from "./session-transcript.js";
import { deriveBookSessionFromTranscript } from "./session-transcript-restore.js";
import { loadWorkManifest } from "../harness/work-store.js";

/** Commit the execution target after a successful host-owned creation action.
 * Compare and append inside the transcript queue so a stale caller cannot
 * retarget a conversation that has already moved elsewhere.
 */
export async function transitionSessionToWork(projectRoot: string, sessionId: string, expectedWorkId: string | null, workId: string): Promise<BookSession> {
  const work = await loadWorkManifest(projectRoot, workId);
  await appendTranscriptEvents(projectRoot, sessionId, ({ events, nextSeq }) => {
    if (!events.some(event => event.type === "session_created")) throw Object.assign(new Error("Session no longer exists."), { code: "SESSION_NOT_FOUND" });
    let currentWorkId: string | null = null;
    let currentBookId: string | null = null;
    let currentProfileId: string | undefined;
    for (const event of events) {
      if (event.type !== "session_created" && event.type !== "session_metadata_updated") continue;
      if (event.workId !== undefined) currentWorkId = event.workId;
      if (event.bookId !== undefined) currentBookId = event.bookId;
      if (event.profileId !== undefined) currentProfileId = event.profileId;
    }
    const current = currentWorkId ?? currentBookId;
    const bookId = work.profileId === "longform-novel" ? work.id : null;
    if (current === work.id && currentBookId === bookId && currentProfileId === work.profileId) return [];
    if (current !== expectedWorkId) throw Object.assign(new Error("The session execution target has changed."), {
      code: "SESSION_TARGET_CONFLICT", expectedWorkId, actualWorkId: current,
    });
    const now = Date.now();
    return [{ type: "session_metadata_updated", version: 1, sessionId, seq: nextSeq, timestamp: now, updatedAt: now,
      workId: work.id, profileId: work.profileId, bookId, sessionKind: bookId ? "book" : "work" }];
  });
  const session = await loadBookSession(projectRoot, sessionId);
  if (!session) throw Object.assign(new Error("Session no longer exists."), { code: "SESSION_NOT_FOUND" });
  return session;
}

/**
 * 从 messages 数组里取第一条 user 消息作为会话标题。
 * 用于把用户首条提问作为会话标题。
 */
export function extractFirstUserMessageTitle(messages: unknown): string | null {
  if (!Array.isArray(messages)) return null;
  for (const message of messages) {
    if (!message || typeof message !== "object") continue;
    if ((message as { role?: unknown }).role !== "user") continue;
    const content = (message as { content?: unknown }).content;
    if (typeof content !== "string") return null;
    const oneLine = content.trim().replace(/\s+/g, " ");
    if (oneLine.length === 0) return null;
    return oneLine;
  }
  return null;
}

export class SessionAlreadyBoundError extends Error {
  constructor(sessionId: string, currentBookId: string) {
    super(`Session "${sessionId}" is already bound to book "${currentBookId}"`);
    this.name = "SessionAlreadyBoundError";
  }
}

export async function loadBookSession(
  projectRoot: string,
  sessionId: string,
): Promise<BookSession | null> {
  return deriveBookSessionFromTranscript(projectRoot, sessionId);
}

async function appendSessionCreatedEvent(
  projectRoot: string,
  session: BookSession,
): Promise<void> {
  await appendTranscriptEvents(projectRoot, session.sessionId, ({ events, nextSeq }) => {
    if (events.some((event) => event.type === "session_created")) return [];
    return [{
      type: "session_created",
      version: 1,
      sessionId: session.sessionId,
      seq: nextSeq,
      timestamp: session.createdAt,
      bookId: session.bookId,
      ...(session.sessionKind ? { sessionKind: session.sessionKind } : {}),
      ...(session.profileId ? { profileId: session.profileId } : {}),
      ...(session.workId !== undefined ? { workId: session.workId } : {}),
      ...(session.proposalAction ? { proposalAction: session.proposalAction } : {}),
      ...(session.playMode ? { playMode: session.playMode } : {}),
      ...(session.modelOverride ? { modelOverride: session.modelOverride } : {}),
      ...(session.serviceOverride ? { serviceOverride: session.serviceOverride } : {}),
      title: session.title,
      createdAt: session.createdAt,
      updatedAt: session.updatedAt,
    }];
  });
}

async function appendSessionMetadataUpdatedEvent(
  projectRoot: string,
  sessionId: string,
  metadata: {
    readonly bookId?: string | null;
    readonly sessionKind?: SessionKind;
    readonly profileId?: string;
    readonly workId?: string | null;
    readonly proposalAction?: string;
    readonly playMode?: PlayMode;
    readonly modelOverride?: string;
    readonly serviceOverride?: string;
    readonly title?: string | null;
    readonly updatedAt: number;
  },
): Promise<void> {
  await appendTranscriptEvents(projectRoot, sessionId, ({ nextSeq }) => [{
    type: "session_metadata_updated",
    version: 1,
    sessionId,
    seq: nextSeq,
    timestamp: metadata.updatedAt,
    updatedAt: metadata.updatedAt,
    ...("bookId" in metadata ? { bookId: metadata.bookId } : {}),
    ...(metadata.sessionKind ? { sessionKind: metadata.sessionKind } : {}),
    ...(metadata.profileId ? { profileId: metadata.profileId } : {}),
    ...(metadata.workId !== undefined ? { workId: metadata.workId } : {}),
    ...(metadata.proposalAction ? { proposalAction: metadata.proposalAction } : {}),
    ...(metadata.playMode ? { playMode: metadata.playMode } : {}),
    ...(metadata.modelOverride ? { modelOverride: metadata.modelOverride } : {}),
    ...(metadata.serviceOverride ? { serviceOverride: metadata.serviceOverride } : {}),
    ...("title" in metadata ? { title: metadata.title } : {}),
  }]);
}

export async function persistBookSession(
  projectRoot: string,
  session: BookSession,
): Promise<void> {
  const events = await readTranscriptEvents(projectRoot, session.sessionId);
  if (events.length === 0) {
    if (session.messages.length > 0) {
      throw new Error("Persist session messages through transcript events, not BookSession.messages.");
    }
    await appendSessionCreatedEvent(projectRoot, session);
    return;
  }

  await appendSessionMetadataUpdatedEvent(projectRoot, session.sessionId, {
    bookId: session.bookId,
    ...(session.sessionKind ? { sessionKind: session.sessionKind } : {}),
    ...(session.profileId ? { profileId: session.profileId } : {}),
    ...(session.workId !== undefined ? { workId: session.workId } : {}),
    ...(session.proposalAction ? { proposalAction: session.proposalAction } : {}),
    ...(session.playMode ? { playMode: session.playMode } : {}),
    ...(session.modelOverride ? { modelOverride: session.modelOverride } : {}),
    ...(session.serviceOverride ? { serviceOverride: session.serviceOverride } : {}),
    title: session.title,
    updatedAt: session.updatedAt,
  });
}

export interface BookSessionSummary {
  readonly sessionId: string;
  readonly bookId: string | null;
  readonly sessionKind?: SessionKind;
  readonly profileId?: string;
  readonly workId?: string | null;
  readonly proposalAction?: string;
  readonly playMode?: PlayMode;
  readonly modelOverride?: string;
  readonly serviceOverride?: string;
  readonly title: string | null;
  readonly messageCount: number;
  readonly createdAt: number;
  readonly updatedAt: number;
}

export async function listBookSessions(
  projectRoot: string,
  bookId: string | null,
): Promise<ReadonlyArray<BookSessionSummary>> {
  const dir = sessionsDir(projectRoot);
  let files: string[];
  try {
    files = await readdir(dir);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }

  const sessionIds = new Set<string>();
  for (const file of files) {
    if (file.endsWith(".jsonl")) sessionIds.add(file.slice(0, -".jsonl".length));
  }

  const summaries = await Promise.all(
    [...sessionIds].map(async (sessionId): Promise<BookSessionSummary | null> => {
      const session = await loadBookSession(projectRoot, sessionId);
      if (!session || session.bookId !== bookId) return null;

      return {
        sessionId: session.sessionId,
        bookId: session.bookId,
        sessionKind: session.sessionKind,
        profileId: session.profileId,
        workId: session.workId,
        proposalAction: session.proposalAction,
        playMode: session.playMode,
        modelOverride: session.modelOverride,
        serviceOverride: session.serviceOverride,
        title: session.title,
        messageCount: session.messages.length,
        createdAt: session.createdAt,
        updatedAt: session.updatedAt,
      };
    }),
  );

  return summaries
    .filter((summary): summary is BookSessionSummary => summary !== null)
    .sort((a, b) => b.updatedAt - a.updatedAt);
}

export async function renameBookSession(
  projectRoot: string,
  sessionId: string,
  title: string,
): Promise<BookSession | null> {
  const session = await loadBookSession(projectRoot, sessionId);
  if (!session) return null;
  const updatedAt = Date.now();
  await appendSessionMetadataUpdatedEvent(projectRoot, sessionId, { title, updatedAt });
  return loadBookSession(projectRoot, sessionId);
}

export async function deleteBookSession(
  projectRoot: string,
  sessionId: string,
): Promise<void> {
  await rm(transcriptPath(projectRoot, sessionId), { force: true });
}

export async function bindBookSessionToBook(
  projectRoot: string,
  sessionId: string,
  newBookId: string,
): Promise<BookSession | null> {
  const session = await loadBookSession(projectRoot, sessionId);
  if (!session) return null;
  if (session.bookId !== null) {
    throw new SessionAlreadyBoundError(sessionId, session.bookId);
  }

  await appendSessionMetadataUpdatedEvent(projectRoot, sessionId, {
    bookId: newBookId,
    sessionKind: "book",
    profileId: "longform-novel",
    workId: newBookId,
    updatedAt: Date.now(),
  });
  return loadBookSession(projectRoot, sessionId);
}

export async function createAndPersistBookSession(
  projectRoot: string,
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
): Promise<BookSession> {
  // 如果指定了 sessionId 且对应文件已存在，视为幂等操作直接返回（支持"用户发消息时才持久化 draft"流程）
  if (sessionId) {
    const existing = await loadBookSession(projectRoot, sessionId);
    if (existing) {
      if (
        (sessionKind && existing.sessionKind !== sessionKind)
        || (options?.playMode && existing.playMode !== options.playMode)
        || (options?.profileId && existing.profileId !== options.profileId)
        || (options && "workId" in options && existing.workId !== options.workId)
        || (options?.proposalAction && existing.proposalAction !== options.proposalAction)
        || (options?.modelOverride && existing.modelOverride !== options.modelOverride)
        || (options?.serviceOverride && existing.serviceOverride !== options.serviceOverride)
      ) {
        await appendSessionMetadataUpdatedEvent(projectRoot, sessionId, {
          ...(sessionKind ? { sessionKind } : {}),
          ...(options?.playMode ? { playMode: options.playMode } : {}),
          ...(options?.profileId ? { profileId: options.profileId } : {}),
          ...(options && "workId" in options ? { workId: options.workId } : {}),
          ...(options?.proposalAction ? { proposalAction: options.proposalAction } : {}),
          ...(options?.modelOverride ? { modelOverride: options.modelOverride } : {}),
          ...(options?.serviceOverride ? { serviceOverride: options.serviceOverride } : {}),
          updatedAt: Date.now(),
        });
        return await loadBookSession(projectRoot, sessionId) ?? existing;
      }
      return existing;
    }
  }
  const session = createBookSession(bookId, sessionId, sessionKind, options);
  await appendSessionCreatedEvent(projectRoot, session);
  return session;
}
