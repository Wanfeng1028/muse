import type { SourceResponse } from "@one-memory/contracts";

const STORAGE_KEY = "one-memory.source-connection-intents.v1";
const MAX_INTENTS = 64;
const MAX_ATTEMPTS = 16;
const INSTANCE_ID = /^[A-Za-z0-9-]{1,80}$/;
const STORAGE_ERROR =
  "无法保留连接请求编号，请核对本地存储后重试。尚未提交新的授权。";

interface JournalEntry {
  fingerprint: string;
  requestIds: string[];
  // Which running Core created these ids. Absent on journals written before
  // that binding existed; those ids cannot be treated as receipts of this Core.
  instanceId?: string;
}

export interface CheckedConnection {
  identity: string;
  onboarding: boolean;
  readonly importUploadId?: string;
  sources: ReadonlyArray<
    Readonly<
      Pick<
        SourceResponse,
        "source_id" | "candidate_path" | "candidate_kind"
      > & {
        candidate_root_id: string;
        candidate_revision?: number;
        connection_generation?: number;
      }
    >
  >;
}

export function freezeConnection(
  sourceIds: string[],
  snapshot: SourceResponse[] | undefined,
  onboarding: boolean,
  importUploadId?: string,
): CheckedConnection {
  if (
    importUploadId !== undefined &&
    (typeof importUploadId !== "string" ||
      importUploadId.length !== 36 ||
      !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(
        importUploadId,
      ))
  ) {
    throw new Error("上传回执编号无效，请重新核对已确认的文件。");
  }
  if (
    !snapshot ||
    !sourceIds.length ||
    new Set(sourceIds).size !== sourceIds.length
  ) {
    throw new Error("来源身份尚未核对，请重新检测位置并确认所选来源。");
  }
  const sources = [...sourceIds].sort().map((id) => {
    const matches = snapshot.filter((item) => item.source_id === id);
    const source = matches[0];
    if (
      matches.length !== 1 ||
      !id.trim() ||
      !source.available ||
      !source.candidate_root_id?.trim() ||
      !source.candidate_path.trim() ||
      (source.candidate_revision !== undefined &&
        (!Number.isSafeInteger(source.candidate_revision) ||
          source.candidate_revision < 0)) ||
      (source.candidate_kind === "user_selected" &&
        !(source.candidate_revision && source.candidate_revision > 0)) ||
      (source.location_state && source.location_state !== "found")
    ) {
      throw new Error("来源身份尚未核对，请重新检测位置并确认所选来源。");
    }
    const generation = connectionGeneration(source);
    return Object.freeze({
      source_id: id,
      candidate_root_id: source.candidate_root_id,
      candidate_path: source.candidate_path,
      candidate_kind: source.candidate_kind,
      ...((source.candidate_revision ?? 0) > 0
        ? { candidate_revision: source.candidate_revision }
        : {}),
      ...(generation > 0 ? { connection_generation: generation } : {}),
    });
  });
  return Object.freeze({
    // An absent upload retains the exact identity used by existing recovery journals.
    identity: JSON.stringify(
      importUploadId === undefined
        ? [onboarding, sources]
        : [onboarding, sources, importUploadId],
    ),
    onboarding,
    ...(importUploadId === undefined ? {} : { importUploadId }),
    sources: Object.freeze(sources),
  });
}

export function assertCheckedConnection(
  checked: CheckedConnection,
  current: SourceResponse[],
) {
  if (
    checked.sources.some(
      (approved) =>
        !current.some(
          (source) =>
            source.source_id === approved.source_id &&
            source.available &&
            (!source.location_state || source.location_state === "found") &&
            source.candidate_root_id === approved.candidate_root_id &&
            source.candidate_kind === approved.candidate_kind &&
            (source.candidate_revision ?? 0) ===
              (approved.candidate_revision ?? 0) &&
            connectionGeneration(source) ===
              (approved.connection_generation ?? 0) &&
            source.candidate_path === approved.candidate_path,
        ),
    )
  ) {
    throw new Error("来源位置或目录身份已变化，请重新检测并确认。");
  }
}

function connectionGeneration(source: SourceResponse): number {
  const revision = source.grant_revision ?? 0;
  if (!Number.isSafeInteger(revision) || revision < 0) {
    throw new Error("来源授权版本尚未核对，请刷新后重新确认。");
  }
  // Grant increments revision; revoke retains it. A completed grant must still
  // resolve its uncertain request, while a later regrant needs a new intent.
  return source.authorized && revision > 0 ? revision - 1 : revision;
}

export async function connectionFingerprint(identity: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(identity),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

// Browser data is a lookup hint, never consent, a server identity, or a write payload.
export function readIntentRequests(fingerprint: string): string[] {
  return [
    ...(readJournal().find((entry) => entry.fingerprint === fingerprint)
      ?.requestIds ?? []),
  ];
}

export function readIntentInstance(fingerprint: string): string | undefined {
  return readJournal().find((entry) => entry.fingerprint === fingerprint)
    ?.instanceId;
}

export function appendIntentRequest(
  fingerprint: string,
  expected: string[],
  requestId: string,
  instanceId?: string,
) {
  const journal = readJournal();
  const entry = journal.find((item) => item.fingerprint === fingerprint);
  const current = entry?.requestIds ?? [];
  if (JSON.stringify(current) !== JSON.stringify(expected)) {
    throw new Error("连接请求状态已变化，请重新核对回执。");
  }
  if (
    current.length >= MAX_ATTEMPTS ||
    (!entry && journal.length >= MAX_INTENTS)
  ) {
    throw new Error(
      "连接回执保留数量已达上限，请先核对已有请求。尚未提交新的授权。",
    );
  }
  const bound = instanceId ?? entry?.instanceId;
  if (bound !== undefined && !INSTANCE_ID.test(bound)) {
    throw new Error(STORAGE_ERROR);
  }
  if (
    instanceId !== undefined &&
    entry?.instanceId !== undefined &&
    entry.instanceId !== instanceId
  ) {
    throw new Error("连接请求状态已变化，请重新核对回执。");
  }
  writeJournal([
    ...journal.filter((item) => item.fingerprint !== fingerprint),
    {
      fingerprint,
      requestIds: [...current, requestId],
      ...(bound === undefined ? {} : { instanceId: bound }),
    },
  ]);
}

// Drops one id this Core has no receipt for, so the click in front of the
// user can store a new one. Instance binding does not keep a missing id.
export function forgetIntentRequest(
  fingerprint: string,
  expected: string[],
  requestId: string,
) {
  const journal = readJournal();
  const entry = journal.find((item) => item.fingerprint === fingerprint);
  const current = entry?.requestIds ?? [];
  if (
    !entry ||
    JSON.stringify(current) !== JSON.stringify(expected) ||
    !current.includes(requestId)
  ) {
    throw new Error("连接请求状态已变化，请重新核对回执。");
  }
  const requestIds = current.filter((id) => id !== requestId);
  const rest = journal.filter((item) => item.fingerprint !== fingerprint);
  writeJournal(
    requestIds.length
      ? [
          ...rest,
          {
            fingerprint,
            requestIds,
            ...(entry.instanceId === undefined
              ? {}
              : { instanceId: entry.instanceId }),
          },
        ]
      : rest,
  );
}

function writeJournal(intents: JournalEntry[]) {
  const serialized = JSON.stringify({ version: 1, intents });
  try {
    window.localStorage.setItem(STORAGE_KEY, serialized);
    if (window.localStorage.getItem(STORAGE_KEY) !== serialized)
      throw new Error(STORAGE_ERROR);
  } catch {
    throw new Error(STORAGE_ERROR);
  }
}

function readJournal(): JournalEntry[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return [];
    if (raw.length > 64_000) throw new Error(STORAGE_ERROR);
    const value: unknown = JSON.parse(raw);
    if (
      !isObject(value) ||
      value.version !== 1 ||
      !Array.isArray(value.intents) ||
      Object.keys(value).length !== 2 ||
      value.intents.length > MAX_INTENTS
    ) {
      throw new Error(STORAGE_ERROR);
    }
    const fingerprints = new Set<string>();
    const requestIds = new Set<string>();
    return value.intents.map((entry: unknown) => {
      if (
        !isObject(entry) ||
        typeof entry.fingerprint !== "string" ||
        !/^[a-f0-9]{64}$/.test(entry.fingerprint) ||
        fingerprints.has(entry.fingerprint) ||
        !Array.isArray(entry.requestIds) ||
        !entry.requestIds.length ||
        entry.requestIds.length > MAX_ATTEMPTS ||
        !validIntentKeys(entry)
      ) {
        throw new Error(STORAGE_ERROR);
      }
      fingerprints.add(entry.fingerprint);
      const ids = entry.requestIds.map((id: unknown) => {
        if (
          typeof id !== "string" ||
          !/^[a-f0-9-]{36}$/.test(id) ||
          requestIds.has(id)
        ) {
          throw new Error(STORAGE_ERROR);
        }
        requestIds.add(id);
        return id;
      });
      return {
        fingerprint: entry.fingerprint,
        requestIds: ids,
        ...(typeof entry.instanceId === "string"
          ? { instanceId: entry.instanceId }
          : {}),
      };
    });
  } catch {
    throw new Error(STORAGE_ERROR);
  }
}

function validIntentKeys(entry: Record<string, unknown>) {
  const keys = Object.keys(entry);
  if (keys.length === 2) return true;
  return (
    keys.length === 3 &&
    typeof entry.instanceId === "string" &&
    INSTANCE_ID.test(entry.instanceId)
  );
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
