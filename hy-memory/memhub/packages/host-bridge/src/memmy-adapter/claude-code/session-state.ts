// Adapted lifecycle state boundary from MemTensor memmy-agent, MIT; no transcript storage.
import { createHash } from "node:crypto";
import { lstat, mkdir } from "node:fs/promises";
import path from "node:path";
import {
  assertNoSymlinks,
  readText,
  withDirectoryLock,
  writeText,
} from "./private-files.js";
import {
  ClaudeAdapterError,
  isRecord,
  sessionIdentity,
} from "./runtime-config.js";

export interface SessionState {
  schemaVersion: 1;
  revision: number;
  turn: number;
  turnIdentity: string | null;
  closed: boolean;
  pendingEventId: string | null;
  notifiedEventId: string | null;
  seenEventIds: string[];
  /** Queries already answered this session, so the same one is not re-fetched.
   *  Absent in state written before this field existed. */
  recalledQueries?: string[];
}
export interface SessionStore {
  read(sessionId: string): Promise<SessionState | null>;
  update(
    sessionId: string,
    update: (current: SessionState | null) => SessionState,
  ): Promise<SessionState>;
}
export function initialState(): SessionState {
  return {
    schemaVersion: 1,
    revision: 0,
    turn: 0,
    turnIdentity: null,
    closed: false,
    pendingEventId: null,
    notifiedEventId: null,
    seenEventIds: [],
    recalledQueries: [],
  };
}
const digests = (value: unknown, limit: number) =>
  Array.isArray(value) &&
  value.length <= limit &&
  value.every((x) => typeof x === "string" && /^[0-9a-f]{64}$/.test(x));
function validate(value: unknown): SessionState {
  if (
    !isRecord(value) ||
    value.schemaVersion !== 1 ||
    !Number.isSafeInteger(value.revision) ||
    (value.revision as number) < 0 ||
    !Number.isSafeInteger(value.turn) ||
    (value.turn as number) < 0 ||
    typeof value.closed !== "boolean" ||
    ![value.turnIdentity, value.pendingEventId, value.notifiedEventId].every(
      (x) => x === null || (typeof x === "string" && /^[0-9a-f]{64}$/.test(x)),
    ) ||
    !digests(value.seenEventIds, 64) ||
    // State written before recalledQueries existed stays readable; a session
    // in flight during an upgrade must not be silenced by its own history.
    (value.recalledQueries !== undefined &&
      !digests(value.recalledQueries, 64)) ||
    Object.keys(value).length !== (value.recalledQueries === undefined ? 8 : 9)
  ) {
    throw new ClaudeAdapterError("invalid_session_state");
  }
  return structuredClone(value) as unknown as SessionState;
}
export function stateKey(installationId: string, sessionId: string): string {
  return createHash("sha256")
    .update(JSON.stringify([installationId, sessionIdentity(sessionId)]))
    .digest("hex");
}

/** Tests inject this explicitly; installed hooks always use the file store. */
export function memorySessionStore(): SessionStore {
  const rows = new Map<string, SessionState>();
  return {
    async read(id) {
      return rows.has(id)
        ? structuredClone(rows.get(id) as SessionState)
        : null;
    },
    async update(id, change) {
      sessionIdentity(id);
      const next = validate(
        change(
          rows.has(id) ? structuredClone(rows.get(id) as SessionState) : null,
        ),
      );
      rows.set(id, next);
      return structuredClone(next);
    },
  };
}

export function fileSessionStore(
  directory: string,
  installationId: string,
): SessionStore {
  const target = (id: string) =>
    path.join(directory, `${stateKey(installationId, id)}.json`);
  const ensure = async () => {
    await assertNoSymlinks(directory);
    await mkdir(directory, { recursive: true, mode: 0o700 });
    const info = await lstat(directory);
    if (
      !info.isDirectory() ||
      info.uid !== process.getuid?.() ||
      (info.mode & 0o777) !== 0o700
    )
      throw new ClaudeAdapterError("unsafe_state_directory");
  };
  const read = async (id: string) => {
    const raw = await readText(target(id), 16_384);
    if (raw === null) return null;
    try {
      return validate(JSON.parse(raw));
    } catch {
      throw new ClaudeAdapterError("invalid_session_state");
    }
  };
  return {
    async read(id) {
      await ensure();
      return read(id);
    },
    async update(id, change) {
      await ensure();
      return withDirectoryLock(`${target(id)}.lock`, async () => {
        const next = validate(change(await read(id)));
        await writeText(target(id), `${JSON.stringify(next)}\n`);
        return next;
      });
    },
  };
}
