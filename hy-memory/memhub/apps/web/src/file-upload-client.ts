import type {
  FileImportOperationReceipt,
  FileImportReceipt,
} from "@one-memory/contracts";
import {
  clearPendingFileUpload,
  readPendingFileUpload,
  savePendingFileUpload,
} from "./pending-file-upload";

export interface FileUploadTransport {
  lookup(operationId: string): Promise<FileImportOperationReceipt>;
  upload(
    file: File,
    inputKind: "raw_conversation" | "memory_content",
    operationId: string,
    /** Optional trace id, threaded through to the HTTP header by the caller. */
    traceId?: string,
  ): Promise<FileImportOperationReceipt>;
  readPreview(uploadId: string): Promise<FileImportReceipt>;
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
let inFlight = false;
function fail(code = "file_upload_operation_unavailable"): never {
  throw new Error(code);
}
function uuid(value: unknown): value is string {
  return typeof value === "string" && value.length === 36 && UUID.test(value);
}
function object(
  value: unknown,
  required: readonly string[],
  optional: readonly string[] = [],
): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  const keys = Reflect.ownKeys(value);
  if (
    keys.some(
      (key) =>
        typeof key !== "string" || ![...required, ...optional].includes(key),
    ) ||
    required.some((key) => !Object.hasOwn(value, key))
  )
    fail();
  const data: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor)) fail();
    data[key as string] = descriptor.value;
  }
  return data;
}
function receipt(
  value: unknown,
  operationId: string,
): FileImportOperationReceipt {
  const item = object(value, [
    "schema_version",
    "operation_id",
    "state",
    "upload_id",
    "code",
    "upload_state",
  ]);
  if (
    item.schema_version !== 1 ||
    !uuid(item.operation_id) ||
    item.operation_id !== operationId
  )
    fail();
  if (item.state === "not_found" || item.state === "pending") {
    if (
      item.upload_id !== null ||
      item.code !== null ||
      item.upload_state !== null
    )
      fail();
  } else if (item.state === "failed") {
    if (
      item.upload_id !== null ||
      item.code !== "import_upload_invalid" ||
      item.upload_state !== null
    )
      fail();
  } else if (item.state === "completed") {
    if (
      !uuid(item.upload_id) ||
      item.code !== null ||
      !["staged", "committed", "missing", "unknown"].includes(
        item.upload_state as string,
      )
    )
      fail();
  } else fail();
  return item as unknown as FileImportOperationReceipt;
}
function text(value: unknown, max: number, min = 0): value is string {
  return (
    typeof value === "string" && value.length >= min && value.length <= max
  );
}
function filename(value: unknown): value is string {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.includes("/") ||
    value.includes("\\")
  )
    return false;
  // Match Python len(): Unicode code points, not JavaScript UTF-16 units.
  let length = 0;
  for (const _character of value) {
    if (++length > 200) return false;
  }
  return [".zip", ".json", ".md", ".txt"].some((extension) =>
    value.toLowerCase().endsWith(extension),
  );
}
function preview(value: unknown, uploadId: string): FileImportReceipt {
  const item = object(
    value,
    [
      "upload_id",
      "filename",
      "vendor",
      "source_id",
      "messages",
      "conversations",
      "human_messages",
      "agent_messages",
      "skipped_records",
      "ignored_files",
      "checksum",
      "created_at",
      "committed",
    ],
    ["content_kind", "unknown_author_messages", "preview"],
  );
  if (
    item.upload_id !== uploadId ||
    !uuid(item.upload_id) ||
    !filename(item.filename) ||
    !["chatgpt", "claude", "generic", "memory-content"].includes(
      item.vendor as string,
    ) ||
    item.source_id !== `${item.vendor}-export` ||
    (item.content_kind !== undefined &&
      !["raw_conversation", "memory_content"].includes(
        item.content_kind as string,
      )) ||
    !text(item.checksum, 64, 64) ||
    !/^[0-9a-f]{64}$/.test(item.checksum) ||
    !text(item.created_at, 64, 1) ||
    !Number.isFinite(Date.parse(item.created_at)) ||
    typeof item.committed !== "boolean"
  )
    fail();
  for (const key of [
    "messages",
    "conversations",
    "human_messages",
    "agent_messages",
    "unknown_author_messages",
    "skipped_records",
    "ignored_files",
  ]) {
    if (key === "unknown_author_messages" && item[key] === undefined) continue;
    if (
      typeof item[key] !== "number" ||
      !Number.isSafeInteger(item[key]) ||
      item[key] < 0
    )
      fail();
  }
  if (item.preview !== undefined) {
    if (!Array.isArray(item.preview) || item.preview.length > 4) fail();
    item.preview = item.preview.map((value) => {
      const message = object(
        value,
        ["role", "text", "created_at", "truncated"],
        ["written_by"],
      );
      if (
        !text(message.role, 64, 1) ||
        !text(message.text, 1200) ||
        typeof message.truncated !== "boolean" ||
        (message.created_at !== null &&
          (!text(message.created_at, 64, 1) ||
            !Number.isFinite(Date.parse(message.created_at)))) ||
        (message.written_by !== undefined &&
          !["person", "agent", "unknown", "tool"].includes(
            message.written_by as string,
          ))
      )
        fail();
      return message;
    });
  }
  return item as unknown as FileImportReceipt;
}

/** Validate a preview read without trusting the transport's generic type. */
export function parseFileImportReceipt(
  value: unknown,
  uploadId: string,
): FileImportReceipt | null {
  try {
    return preview(value, uploadId);
  } catch {
    return null;
  }
}

function terminal(item: FileImportOperationReceipt): void {
  if (
    item.state === "failed" ||
    (item.state === "completed" && item.upload_state === "missing")
  ) {
    clearPendingFileUpload(item.operation_id);
    fail(
      item.state === "failed" ? "file_upload_invalid" : "file_upload_missing",
    );
  }
  if (item.state !== "completed" || item.upload_state === "unknown")
    fail("file_upload_operation_pending");
}
async function lookup(
  operationId: string,
  transport: FileUploadTransport,
): Promise<FileImportOperationReceipt> {
  let value: unknown;
  try {
    value = await transport.lookup(operationId);
  } catch {
    return fail("file_upload_operation_pending");
  }
  return receipt(value, operationId);
}
async function consume(
  item: FileImportOperationReceipt,
  transport: FileUploadTransport,
): Promise<FileImportReceipt> {
  terminal(item);
  const uploadId = item.upload_id;
  if (!uploadId) fail();
  let value: unknown;
  try {
    value = await transport.readPreview(uploadId);
  } catch {
    return fail("file_upload_operation_pending");
  }
  const result = preview(value, uploadId);
  // Staging completion is historical. Recheck after reading to catch discard or commit.
  const current = await lookup(item.operation_id, transport);
  if (current.state !== "completed" || current.upload_id !== uploadId)
    fail("file_upload_operation_pending");
  terminal(current);
  if (
    current.upload_state !== item.upload_state ||
    result.committed !== (current.upload_state === "committed")
  )
    fail("file_upload_operation_pending");
  clearPendingFileUpload(item.operation_id);
  return result;
}

/** Unknown uploads are lookup-only, even when the caller supplies another File.
 * Does not commit, discard, authorize sources or start imports. Module single-flight
 * is not cross-tab locking; durable server operation identity is the final fence.
 */
export async function recoverableFileUpload(
  file: File,
  inputKind: "raw_conversation" | "memory_content",
  transport: FileUploadTransport,
  /** Optional trace id for the single upload POST; recovery stays GET-only. */
  traceId?: string,
): Promise<FileImportReceipt> {
  if (inFlight) fail("file_upload_in_flight");
  inFlight = true;
  try {
    const pending = readPendingFileUpload();
    if (pending)
      return await consume(await lookup(pending, transport), transport);
    if (
      !(file instanceof File) ||
      !filename(file.name) ||
      !["raw_conversation", "memory_content"].includes(inputKind) ||
      file.size > 128 * 1024 * 1024
    )
      fail("file_upload_input_invalid");
    let operationId: string;
    try {
      operationId = crypto.randomUUID();
      if (
        !uuid(operationId) ||
        (await lookup(operationId, transport)).state !== "not_found"
      )
        fail();
    } catch {
      return fail("file_upload_capability_unavailable");
    }
    savePendingFileUpload(operationId);
    let value: unknown;
    try {
      value = await transport.upload(file, inputKind, operationId, traceId);
    } catch {
      return fail("file_upload_operation_pending");
    }
    return await consume(receipt(value, operationId), transport);
  } finally {
    inFlight = false;
  }
}

/** Explicit GET-only recovery after reload; absent local intent makes no request. */
export async function reconcileFileUpload(
  transport: FileUploadTransport,
): Promise<FileImportReceipt | null> {
  if (inFlight) fail("file_upload_in_flight");
  inFlight = true;
  try {
    const pending = readPendingFileUpload();
    return pending
      ? await consume(await lookup(pending, transport), transport)
      : null;
  } finally {
    inFlight = false;
  }
}
