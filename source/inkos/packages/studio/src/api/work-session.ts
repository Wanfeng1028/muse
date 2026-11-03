import { loadBookSession, type BookSession } from "@actalk/inkos-core";

/** The persisted execution target is authoritative on both success and failure. */
export function workSessionResponseMetadata(session: BookSession) {
  return {
    sessionId: session.sessionId,
    sessionKind: session.sessionKind,
    bookId: session.bookId,
    profileId: session.profileId,
    workId: session.workId ?? session.bookId,
  };
}

export async function recoverSessionAfterAgentFailure(root: string, sessionId: string): Promise<BookSession | null> {
  return loadBookSession(root, sessionId);
}
