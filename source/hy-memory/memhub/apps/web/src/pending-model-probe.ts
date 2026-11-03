export interface PendingModelProbe {
  operationId: string;
  profileId: string;
  inputRevision: number;
}

const KEY = "one-memory.pending-model-probe.v1";
const MAX_BYTES = 512;
const ERROR = "pending_model_probe_failed";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
type JournalStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function fail(): never {
  throw new Error(ERROR);
}

function validateId(value: unknown): string {
  if (typeof value !== "string" || value.length !== 36 || !UUID.test(value))
    fail();
  return value;
}

function exactObject(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  const ownKeys = Reflect.ownKeys(value);
  if (
    ownKeys.length !== keys.length ||
    ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))
  )
    fail();
  const data: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor)) fail();
    data[key] = descriptor.value;
  }
  return data;
}

function validate(value: unknown): PendingModelProbe {
  const item = exactObject(value, [
    "operationId",
    "profileId",
    "inputRevision",
  ]);
  if (
    typeof item.inputRevision !== "number" ||
    !Number.isSafeInteger(item.inputRevision) ||
    item.inputRevision < 1
  )
    fail();
  return {
    operationId: validateId(item.operationId),
    profileId: validateId(item.profileId),
    inputRevision: item.inputRevision,
  };
}

function read(storage: JournalStorage): PendingModelProbe | null {
  const raw = storage.getItem(KEY);
  if (raw === null) return null;
  if (
    typeof raw !== "string" ||
    raw.length > MAX_BYTES ||
    new TextEncoder().encode(raw).length > MAX_BYTES
  )
    fail();
  const envelope = exactObject(JSON.parse(raw), ["schemaVersion", "value"]);
  if (envelope.schemaVersion !== 1) fail();
  return validate(envelope.value);
}

function same(
  left: PendingModelProbe | null,
  right: PendingModelProbe,
): boolean {
  return (
    left !== null &&
    left.operationId === right.operationId &&
    left.profileId === right.profileId &&
    left.inputRevision === right.inputRevision
  );
}

/** Origin-local metadata only; not authorization, completion or permission to resend. */
export function readPendingModelProbe(
  storage?: JournalStorage,
): PendingModelProbe | null {
  try {
    return read(storage ?? window.localStorage);
  } catch {
    return fail();
  }
}

/** Synchronous readback must succeed before the caller dispatches its POST.
 * localStorage is not cross-tab CAS; backend operation fences remain authoritative.
 */
export function savePendingModelProbe(
  value: PendingModelProbe,
  storage?: JournalStorage,
): void {
  try {
    const intent = validate(value);
    const target = storage ?? window.localStorage;
    const previous = read(target);
    if (previous !== null && !same(previous, intent)) fail();
    if (previous === null)
      target.setItem(KEY, JSON.stringify({ schemaVersion: 1, value: intent }));
    if (!same(read(target), intent)) fail();
  } catch {
    fail();
  }
}

/** Explicit matching clear only. No interpretation of backend not_found or retry policy. */
export function clearPendingModelProbe(
  operationId: string,
  storage?: JournalStorage,
): void {
  try {
    const id = validateId(operationId);
    const target = storage ?? window.localStorage;
    const previous = read(target);
    if (previous !== null) {
      if (previous.operationId !== id) fail();
      target.removeItem(KEY);
    }
    if (read(target) !== null) fail();
  } catch {
    fail();
  }
}
