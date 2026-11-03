const KEY = "one-memory.pending-file-upload.v1";
const MAX_BYTES = 256;
const ERROR = "pending_file_upload_failed";
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
function read(storage: JournalStorage): string | null {
  const raw = storage.getItem(KEY);
  if (raw === null) return null;
  if (
    typeof raw !== "string" ||
    raw.length > MAX_BYTES ||
    new TextEncoder().encode(raw).length > MAX_BYTES
  )
    fail();
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  const keys = Object.keys(value);
  if (
    keys.length !== 2 ||
    !keys.includes("schemaVersion") ||
    !keys.includes("operationId")
  )
    fail();
  const envelope = value as Record<string, unknown>;
  if (envelope.schemaVersion !== 1) fail();
  return validateId(envelope.operationId);
}

/** Origin-local recovery intent only. No file metadata, content or authority to resend. */
export function readPendingFileUpload(storage?: JournalStorage): string | null {
  try {
    return read(storage ?? window.localStorage);
  } catch {
    return fail();
  }
}

/** Must read back before POST. localStorage is not cross-tab CAS; the backend
 * operation fence remains authoritative. Storage failure must block dispatch.
 */
export function savePendingFileUpload(
  operationId: string,
  storage?: JournalStorage,
): void {
  try {
    const id = validateId(operationId);
    const target = storage ?? window.localStorage;
    const previous = read(target);
    if (previous !== null && previous !== id) fail();
    if (previous === null)
      target.setItem(
        KEY,
        JSON.stringify({ schemaVersion: 1, operationId: id }),
      );
    if (read(target) !== id) fail();
  } catch {
    fail();
  }
}

/** Only clear a matching observed operation. Damaged data is never auto-deleted. */
export function clearPendingFileUpload(
  operationId: string,
  storage?: JournalStorage,
): void {
  try {
    const id = validateId(operationId);
    const target = storage ?? window.localStorage;
    const previous = read(target);
    if (previous !== null) {
      if (previous !== id) fail();
      target.removeItem(KEY);
    }
    if (read(target) !== null) fail();
  } catch {
    fail();
  }
}
