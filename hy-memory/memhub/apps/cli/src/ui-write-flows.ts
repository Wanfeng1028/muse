/**
 * The Web Console's remaining mutating operations, exposed to the CLI without
 * duplicating Core semantics. Each operation is planned first; callers apply
 * the exact plan they reviewed.
 */

import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { type FileHandle, open } from "node:fs/promises";
import type {
  CoreDeleteOperations,
  CoreOperations,
  CoreUploadOperations,
} from "./core-operations.js";
import { PRODUCT } from "./version.js";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const INPUT_KINDS = ["raw_conversation", "memory_content"] as const;
const MAX_UPLOAD_BYTES = 128 * 1024 * 1024;

export type UiWritePlan =
  | {
      schema_version: 1;
      kind: "call_events_clear";
      event_ids: string[];
      digest: string;
    }
  | {
      schema_version: 1;
      kind: "call_events_clear_all";
      digest: string;
    }
  | {
      schema_version: 1;
      kind: "import_file_commit";
      upload_id: string;
      digest: string;
    }
  | {
      schema_version: 1;
      kind: "import_file_discard";
      upload_id: string;
      digest: string;
    }
  | {
      schema_version: 1;
      kind: "import_file_upload";
      operation_id: string;
      path: string;
      filename: string;
      input_kind: (typeof INPUT_KINDS)[number];
      bytes: number;
      sha256: string;
      digest: string;
    };

export type UiWriteOutcome =
  | {
      schema_version: 1;
      product: string;
      state: "preview";
      plan: UiWritePlan;
    }
  | {
      schema_version: 1;
      product: string;
      state: "committed" | "recovered";
      operation_id: string;
      receipt: Record<string, unknown>;
    }
  | {
      schema_version: 1;
      product: string;
      state: "rejected" | "unknown" | "invalid";
      operation_id?: string;
      code: string;
      receipt?: Record<string, unknown>;
    };

function digestOf(value: unknown): string {
  return createHash("sha256").update(canonical(value)).digest("hex");
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  if (value === undefined) return "null";
  return JSON.stringify(value);
}

export type UiWritePlanDraft =
  | Omit<Extract<UiWritePlan, { kind: "call_events_clear" }>, "digest">
  | Omit<Extract<UiWritePlan, { kind: "call_events_clear_all" }>, "digest">
  | Omit<Extract<UiWritePlan, { kind: "import_file_commit" }>, "digest">
  | Omit<Extract<UiWritePlan, { kind: "import_file_discard" }>, "digest">
  | Omit<Extract<UiWritePlan, { kind: "import_file_upload" }>, "digest">;

function preview(plan: UiWritePlanDraft): UiWriteOutcome {
  return {
    schema_version: 1,
    product: PRODUCT,
    state: "preview",
    plan: { ...plan, digest: digestOf(plan) } as UiWritePlan,
  };
}

function invalid(code: string): UiWriteOutcome {
  return { schema_version: 1, product: PRODUCT, state: "invalid", code };
}

function committed(
  operationId: string,
  receipt: Record<string, unknown>,
  state: "committed" | "recovered" = "committed",
): UiWriteOutcome {
  return {
    schema_version: 1,
    product: PRODUCT,
    state,
    operation_id: operationId,
    receipt,
  };
}

export function planCallEventsClear(
  eventIds: readonly string[],
): UiWriteOutcome {
  if (
    eventIds.length < 1 ||
    eventIds.length > 100 ||
    new Set(eventIds).size !== eventIds.length ||
    eventIds.some((id) => !UUID.test(id))
  ) {
    return invalid("call_event_ids_invalid");
  }
  return preview({
    schema_version: 1,
    kind: "call_events_clear",
    event_ids: [...eventIds],
  });
}

export function planCallEventsClearAll(): UiWriteOutcome {
  return preview({ schema_version: 1, kind: "call_events_clear_all" });
}

export function planImportFileCommit(uploadId: string): UiWriteOutcome {
  return UUID.test(uploadId)
    ? preview({
        schema_version: 1,
        kind: "import_file_commit",
        upload_id: uploadId,
      })
    : invalid("import_file_id_invalid");
}

export function planImportFileDiscard(uploadId: string): UiWriteOutcome {
  return UUID.test(uploadId)
    ? preview({
        schema_version: 1,
        kind: "import_file_discard",
        upload_id: uploadId,
      })
    : invalid("import_file_id_invalid");
}

export function planImportFileUpload(input: {
  path: string;
  bytes: number;
  sha256: string;
  inputKind: "raw_conversation" | "memory_content";
}): UiWriteOutcome {
  const filename = input.path.split(/[/\\]/).pop() ?? "";
  if (
    input.path.length === 0 ||
    !Number.isSafeInteger(input.bytes) ||
    input.bytes < 0 ||
    input.bytes > MAX_UPLOAD_BYTES ||
    !/^[0-9a-f]{64}$/.test(input.sha256) ||
    !INPUT_KINDS.includes(input.inputKind) ||
    filename.length === 0 ||
    [...filename].length > 200 ||
    !/\.(?:zip|json|md|txt)$/i.test(filename)
  ) {
    return invalid("import_file_upload_invalid");
  }
  return preview({
    schema_version: 1,
    kind: "import_file_upload",
    operation_id: fileUploadOperationId(
      filename,
      input.inputKind,
      input.sha256,
    ),
    path: input.path,
    filename,
    input_kind: input.inputKind,
    bytes: input.bytes,
    sha256: input.sha256,
  });
}

/**
 * Read one regular, non-symlinked export without buffering past the 128 MiB
 * limit. Returns the bytes plus the checksum the plan records, so apply can
 * prove the file it uploads is the one the caller reviewed.
 */
export async function readImportFileUpload(
  filePath: string,
  inputKind: "raw_conversation" | "memory_content",
): Promise<{ plan: UiWritePlan; bytes: Buffer } | null> {
  let handle: FileHandle;
  try {
    handle = await open(
      filePath,
      constants.O_RDONLY |
        (constants.O_NONBLOCK ?? 0) |
        (constants.O_NOFOLLOW ?? 0),
    );
  } catch {
    return null;
  }
  try {
    const stats = await handle.stat();
    if (!stats.isFile() || stats.nlink !== 1 || stats.size > MAX_UPLOAD_BYTES) {
      return null;
    }
    const buffer = Buffer.alloc(Number(stats.size));
    let offset = 0;
    while (offset < buffer.length) {
      const chunk = await handle.read(
        buffer,
        offset,
        buffer.length - offset,
        offset,
      );
      if (chunk.bytesRead === 0) break;
      offset += chunk.bytesRead;
    }
    if (offset !== buffer.length) return null;
    const checksum = createHash("sha256").update(buffer).digest("hex");
    const result = planImportFileUpload({
      path: filePath,
      bytes: buffer.byteLength,
      sha256: checksum,
      inputKind,
    });
    if (result.state !== "preview") return null;
    return { plan: result.plan, bytes: buffer };
  } catch {
    return null;
  } finally {
    await handle.close().catch(() => undefined);
  }
}

/**
 * Core keys upload idempotency by `operation_id` and rejects a replay whose
 * fingerprint differs. Deriving it from the file's own identity means a retry
 * after a dropped response resumes the same staging operation instead of
 * creating a second upload; a genuinely different payload maps to a different
 * operation and cannot overwrite the first.
 */
function fileUploadOperationId(
  filename: string,
  inputKind: (typeof INPUT_KINDS)[number],
  checksum: string,
): string {
  const hex = createHash("sha256")
    .update(JSON.stringify([filename, inputKind, checksum]))
    .digest("hex");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    `4${hex.slice(13, 16)}`,
    `${(8 + (parseInt(hex[16]!, 16) % 4)).toString(16)}${hex.slice(17, 20)}`,
    hex.slice(20, 32),
  ].join("-");
}

export function validateUiWritePlan(value: unknown): UiWritePlan | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  if (candidate.schema_version !== 1 || typeof candidate.kind !== "string") {
    return null;
  }
  const { digest, ...withoutDigest } = candidate;
  if (typeof digest !== "string" || digest !== digestOf(withoutDigest)) {
    return null;
  }
  switch (candidate.kind) {
    case "call_events_clear":
      return Array.isArray(candidate.event_ids) &&
        candidate.event_ids.length >= 1 &&
        candidate.event_ids.length <= 100 &&
        new Set(candidate.event_ids).size === candidate.event_ids.length &&
        candidate.event_ids.every(
          (id) => typeof id === "string" && UUID.test(id),
        )
        ? (candidate as unknown as UiWritePlan)
        : null;
    case "call_events_clear_all":
      return Object.keys(candidate).length === 3
        ? (candidate as unknown as UiWritePlan)
        : null;
    case "import_file_commit":
    case "import_file_discard":
      return typeof candidate.upload_id === "string" &&
        UUID.test(candidate.upload_id) &&
        Object.keys(candidate).length === 4
        ? (candidate as unknown as UiWritePlan)
        : null;
    case "import_file_upload":
      return typeof candidate.operation_id === "string" &&
        UUID.test(candidate.operation_id) &&
        typeof candidate.path === "string" &&
        typeof candidate.filename === "string" &&
        candidate.filename === candidate.path.split(/[/\\]/).pop() &&
        /^[0-9a-f]{64}$/.test(String(candidate.sha256)) &&
        INPUT_KINDS.includes(
          candidate.input_kind as (typeof INPUT_KINDS)[number],
        ) &&
        Number.isSafeInteger(candidate.bytes) &&
        (candidate.bytes as number) >= 0 &&
        (candidate.bytes as number) <= 128 * 1024 * 1024
        ? (candidate as unknown as UiWritePlan)
        : null;
    default:
      return null;
  }
}

export function uiWriteExitCode(document: UiWriteOutcome): number {
  return ["preview", "committed", "recovered"].includes(document.state) ? 0 : 1;
}

export function renderUiWriteText(document: UiWriteOutcome): string {
  if (document.state === "preview") {
    return `以下操作尚未执行；加 --confirm 后才会写入：\n${document.plan.kind}\nplan_digest：${document.plan.digest}\n`;
  }
  if (document.state === "committed" || document.state === "recovered") {
    return `已提交：${document.operation_id}\n${JSON.stringify(document.receipt)}\n`;
  }
  const code = "code" in document ? document.code : "ui_write_state_invalid";
  return `操作未完成：${document.state}（${code}）\n`;
}

export async function executeCallEventsClear(
  plan: Extract<UiWritePlan, { kind: "call_events_clear" }>,
  operations: CoreOperations,
): Promise<UiWriteOutcome> {
  const result = await operations.post<unknown>("/api/v1/call-events/clear", {
    event_ids: plan.event_ids,
    user_confirmed: true,
  });
  return outcome(result, plan.event_ids.join(","), ["removed"]);
}

export async function executeCallEventsClearAll(
  plan: Extract<UiWritePlan, { kind: "call_events_clear_all" }>,
  operations: CoreOperations,
): Promise<UiWriteOutcome> {
  const result = await operations.post<unknown>(
    "/api/v1/call-events/clear-all",
    { user_confirmed: true },
  );
  return outcome(result, "all", ["removed"]);
}

export async function executeImportFileCommit(
  plan: Extract<UiWritePlan, { kind: "import_file_commit" }>,
  operations: CoreOperations,
): Promise<UiWriteOutcome> {
  const result = await operations.post<unknown>(
    `/api/v1/import-files/${plan.upload_id}/commit`,
    { confirmed: true },
  );
  return outcome(result, plan.upload_id, [
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
  ]);
}

export async function executeImportFileDiscard(
  plan: Extract<UiWritePlan, { kind: "import_file_discard" }>,
  operations: CoreDeleteOperations,
): Promise<UiWriteOutcome> {
  const result = await operations.delete<unknown>(
    `/api/v1/import-files/${plan.upload_id}`,
  );
  // Core answers 204 with no body. A successful delete is a committed
  // operation even though there is no receipt to validate; requiring a body
  // here would report every real discard as `ui_write_receipt_invalid`.
  return outcome(result, plan.upload_id, null);
}

/** Upload one local file through the same recoverable Core staging flow the
 * Web console uses. The operation id is part of the plan, so a retry after a
 * dropped response resumes the same staging record instead of duplicating it.
 */
export async function executeImportFileUpload(
  plan: Extract<UiWritePlan, { kind: "import_file_upload" }>,
  operations: CoreUploadOperations,
): Promise<UiWriteOutcome> {
  // Re-read the file at apply time and re-derive its identity. A plan that
  // names a path whose content changed after review is refused rather than
  // uploading something the caller never saw.
  const reread = await readImportFileUpload(plan.path, plan.input_kind);
  if (reread === null) {
    return invalid("import_file_upload_unreadable");
  }
  const bytes = reread.bytes;
  const checksum = createHash("sha256").update(bytes).digest("hex");
  if (
    bytes.byteLength !== plan.bytes ||
    checksum !== plan.sha256 ||
    reread.plan.digest !== plan.digest
  ) {
    return invalid("import_file_upload_content_mismatch");
  }
  const result = await operations.uploadImportFile<unknown>({
    bytes,
    filename: plan.filename,
    inputKind: plan.input_kind,
    operationId: plan.operation_id,
  });
  if (result.state === "rejected") {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "rejected",
      operation_id: plan.operation_id,
      code: result.code,
    };
  }
  if (result.state === "unknown") {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "unknown",
      operation_id: plan.operation_id,
      code: result.code,
    };
  }
  const receipt =
    result.data !== null &&
    typeof result.data === "object" &&
    !Array.isArray(result.data)
      ? (result.data as Record<string, unknown>)
      : null;
  if (
    receipt === null ||
    receipt.operation_id !== plan.operation_id ||
    typeof receipt.state !== "string"
  ) {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "unknown",
      operation_id: plan.operation_id,
      code: "ui_write_receipt_invalid",
    };
  }
  // Core reports the staged upload as `completed`; `pending`/`not_found` here
  // means the operation record did not settle, so the result is not known.
  if (receipt.state !== "completed") {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "unknown",
      operation_id: plan.operation_id,
      code: `import_upload_${receipt.state}`,
    };
  }
  const uploadId =
    typeof receipt.upload_id === "string" ? receipt.upload_id : undefined;
  if (uploadId === undefined || !UUID.test(uploadId)) {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "unknown",
      operation_id: plan.operation_id,
      code: "ui_write_receipt_invalid",
    };
  }
  return committed(plan.operation_id, {
    operation_id: plan.operation_id,
    upload_id: uploadId,
    upload_state: receipt.upload_state ?? null,
  });
}

function outcome(
  result:
    | Awaited<ReturnType<CoreOperations["post"]>>
    | Awaited<ReturnType<CoreDeleteOperations["delete"]>>,
  operationId: string,
  required: readonly string[] | null,
): UiWriteOutcome {
  if (result.state === "rejected") {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "rejected",
      operation_id: operationId,
      code: result.code,
    };
  }
  if (result.state === "unknown") {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "unknown",
      operation_id: operationId,
      code: result.code,
    };
  }
  if (required === null) {
    return committed(operationId, {});
  }
  const data =
    result.data !== null &&
    typeof result.data === "object" &&
    !Array.isArray(result.data)
      ? (result.data as Record<string, unknown>)
      : null;
  if (data === null || required.some((key) => !Object.hasOwn(data, key))) {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "unknown",
      operation_id: operationId,
      code: "ui_write_receipt_invalid",
    };
  }
  return committed(operationId, data);
}
