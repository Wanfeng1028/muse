/**
 * The remaining Web Console mutating operations the CLI did not expose:
 * 端内新增记忆 (memory-notes), extraction window, graph width, and manual
 * extraction.
 *
 * Core owns every rule; this module only validates the input it is about to
 * send, performs one explicit two-phase write, and normalises the receipt so
 * the CLI never reports a write as committed without evidence.
 */

import { createHash, randomUUID } from "node:crypto";
import {
  buildMemoryNoteSaveRequest,
  MemoryNoteInputError,
  parseExtractionSettingsReceipt,
  parseGraphWidthDecisionReceipt,
  parseManualExtractReceipt,
  parseMemoryNoteReceipt,
} from "@one-memory/operations";
import type { CoreOperations, CorePutOperations } from "./core-operations.js";
import { PRODUCT } from "./version.js";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const DIGEST = /^[0-9a-f]{64}$/;
const NOTE_MAX_CHARACTERS = 12_000;
const EXTRACTION_PRESETS = ["3m", "6m", "1y", "all"] as const;
const GRAPH_DECISIONS = [
  "keep_existing",
  "rebuild_with_new",
  "export_first",
] as const;
const NOTE_STATES = [
  "waiting_for_model",
  "waiting_for_permission",
  "pending",
  "running",
  "failed",
  "ready",
  "no_memories",
] as const;

export type NoteState = (typeof NOTE_STATES)[number];

export type ExtendedWritePlan =
  | {
      schema_version: 1;
      kind: "memory_note_add";
      request_id: string;
      content_sha256: string;
      content_characters: number;
      digest: string;
    }
  | {
      schema_version: 1;
      kind: "memory_note_process";
      evidence_id: string;
      digest: string;
    }
  | {
      schema_version: 1;
      kind: "extraction_window_set";
      window_preset: (typeof EXTRACTION_PRESETS)[number];
      digest: string;
    }
  | {
      schema_version: 1;
      kind: "graph_width_decide";
      decision: (typeof GRAPH_DECISIONS)[number];
      digest: string;
    }
  | {
      schema_version: 1;
      kind: "manual_extract";
      evidence_ids: string[];
      digest: string;
    };

export type ExtendedWriteOutcome =
  | {
      schema_version: 1;
      product: string;
      state: "preview";
      plan: ExtendedWritePlan;
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
    };

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

function digestOf(value: unknown): string {
  return createHash("sha256").update(canonical(value)).digest("hex");
}

type Draft =
  | Omit<Extract<ExtendedWritePlan, { kind: "memory_note_add" }>, "digest">
  | Omit<Extract<ExtendedWritePlan, { kind: "memory_note_process" }>, "digest">
  | Omit<
      Extract<ExtendedWritePlan, { kind: "extraction_window_set" }>,
      "digest"
    >
  | Omit<Extract<ExtendedWritePlan, { kind: "graph_width_decide" }>, "digest">
  | Omit<Extract<ExtendedWritePlan, { kind: "manual_extract" }>, "digest">;

function preview(plan: Draft): ExtendedWriteOutcome {
  return {
    schema_version: 1,
    product: PRODUCT,
    state: "preview",
    plan: { ...plan, digest: digestOf(plan) } as ExtendedWritePlan,
  };
}

function invalid(code: string): ExtendedWriteOutcome {
  return { schema_version: 1, product: PRODUCT, state: "invalid", code };
}

function committed(
  operationId: string,
  receipt: Record<string, unknown>,
  state: "committed" | "recovered" = "committed",
): ExtendedWriteOutcome {
  return {
    schema_version: 1,
    product: PRODUCT,
    state,
    operation_id: operationId,
    receipt,
  };
}

function rejected(
  operationId: string | undefined,
  code: string,
): ExtendedWriteOutcome {
  return {
    schema_version: 1,
    product: PRODUCT,
    state: "rejected",
    ...(operationId === undefined ? {} : { operation_id: operationId }),
    code,
  };
}

function unknown(
  operationId: string | undefined,
  code: string,
): ExtendedWriteOutcome {
  return {
    schema_version: 1,
    product: PRODUCT,
    state: "unknown",
    ...(operationId === undefined ? {} : { operation_id: operationId }),
    code,
  };
}

// --- memory-notes ---------------------------------------------------------

export function planMemoryNoteAdd(text: string): ExtendedWriteOutcome {
  // The plan keeps only the note's identity, like `memories plan add`: the
  //正文 lives in a bounded file and is re-read and re-hashed at apply time, so
  // a plan file never carries the user's private text.
  if (!validNoteText(text)) return invalid("memory_note_text_invalid");
  const requestId = randomUUID();
  return preview({
    schema_version: 1,
    kind: "memory_note_add",
    request_id: requestId,
    content_sha256: createHash("sha256").update(text, "utf8").digest("hex"),
    content_characters: [...text].length,
  });
}

export function validNoteText(text: string): boolean {
  return (
    text.length > 0 &&
    [...text].length <= NOTE_MAX_CHARACTERS &&
    text.trim().length > 0 &&
    ![...text].some((character) => {
      const code = character.charCodeAt(0);
      return code <= 8 || (code >= 11 && code <= 31) || code === 127;
    })
  );
}

export function planMemoryNoteProcess(
  evidenceId: string,
): ExtendedWriteOutcome {
  return UUID.test(evidenceId)
    ? preview({
        schema_version: 1,
        kind: "memory_note_process",
        evidence_id: evidenceId,
      })
    : invalid("memory_note_id_invalid");
}

function noteReceipt(
  operationId: string,
  data: { evidence_id: string; state: NoteState },
): ExtendedWriteOutcome {
  return committed(operationId, { ...data });
}

export async function executeMemoryNoteAdd(
  plan: Extract<ExtendedWritePlan, { kind: "memory_note_add" }>,
  operations: CoreOperations,
  text: string,
): Promise<ExtendedWriteOutcome> {
  if (
    !validNoteText(text) ||
    createHash("sha256").update(text, "utf8").digest("hex") !==
      plan.content_sha256 ||
    [...text].length !== plan.content_characters
  ) {
    return invalid("memory_note_content_mismatch");
  }
  // The shared builder owns the save body (request_id/text/scope=all-apps), so
  // the CLI and the Web console post the same three fields. Its own text check
  // already ran above, so a throw here means an unusable plan.
  let request: ReturnType<typeof buildMemoryNoteSaveRequest>;
  try {
    request = buildMemoryNoteSaveRequest({
      request_id: plan.request_id,
      text,
      scope: "all-apps",
    } as Parameters<typeof buildMemoryNoteSaveRequest>[0]);
  } catch (error) {
    if (error instanceof MemoryNoteInputError) {
      return invalid("memory_note_content_mismatch");
    }
    throw error;
  }
  const result = await operations.post<unknown>(request.path, request.body);
  if (result.state === "rejected") {
    return rejected(plan.request_id, result.code);
  }
  if (result.state === "unknown") {
    return unknown(plan.request_id, result.code);
  }
  const receipt = asNoteReceipt(result.data);
  return receipt === null
    ? unknown(plan.request_id, "ui_write_receipt_invalid")
    : noteReceipt(plan.request_id, receipt);
}

export async function executeMemoryNoteProcess(
  plan: Extract<ExtendedWritePlan, { kind: "memory_note_process" }>,
  operations: CoreOperations,
): Promise<ExtendedWriteOutcome> {
  const result = await operations.post<unknown>(
    `/api/v1/memory-notes/${plan.evidence_id}/process`,
    {},
  );
  if (result.state === "rejected") {
    return rejected(plan.evidence_id, result.code);
  }
  if (result.state === "unknown") {
    return unknown(plan.evidence_id, result.code);
  }
  const receipt = asNoteReceipt(result.data);
  return receipt === null
    ? unknown(plan.evidence_id, "ui_write_receipt_invalid")
    : noteReceipt(plan.evidence_id, receipt);
}

function asNoteReceipt(
  value: unknown,
): { evidence_id: string; state: NoteState } | null {
  // The shared parser is the single judge of a note receipt; a malformed body
  // returns null and the caller reports `unknown`, never a saved note.
  const receipt = parseMemoryNoteReceipt(value);
  return receipt === null
    ? null
    : { evidence_id: receipt.evidence_id, state: receipt.state as NoteState };
}

// --- extraction window / graph width / manual extract ---------------------

export function planExtractionWindowSet(
  windowPreset: string,
): ExtendedWriteOutcome {
  return (EXTRACTION_PRESETS as readonly string[]).includes(windowPreset)
    ? preview({
        schema_version: 1,
        kind: "extraction_window_set",
        window_preset: windowPreset as (typeof EXTRACTION_PRESETS)[number],
      })
    : invalid("extraction_window_preset_invalid");
}

export function planGraphWidthDecide(decision: string): ExtendedWriteOutcome {
  return (GRAPH_DECISIONS as readonly string[]).includes(decision)
    ? preview({
        schema_version: 1,
        kind: "graph_width_decide",
        decision: decision as (typeof GRAPH_DECISIONS)[number],
      })
    : invalid("graph_width_decision_invalid");
}

export function planManualExtract(evidenceIds: string[]): ExtendedWriteOutcome {
  const ids = [...new Set(evidenceIds)];
  return ids.length === evidenceIds.length && ids.every((id) => UUID.test(id))
    ? preview({
        schema_version: 1,
        kind: "manual_extract",
        evidence_ids: ids,
      })
    : invalid("manual_extract_evidence_ids_invalid");
}

export async function executeExtractionWindowSet(
  plan: Extract<ExtendedWritePlan, { kind: "extraction_window_set" }>,
  operations: CorePutOperations,
): Promise<ExtendedWriteOutcome> {
  const result = await operations.put<unknown>("/api/v1/extraction-settings", {
    window_preset: plan.window_preset,
  });
  if (result.state === "rejected") {
    return rejected(plan.window_preset, result.code);
  }
  if (result.state === "unknown") {
    return unknown(plan.window_preset, result.code);
  }
  // The shared parser also enforces that the receipt echoes the requested
  // preset, so a response belonging to another write cannot pass.
  const parsed = parseExtractionSettingsReceipt(
    result.data,
    plan.window_preset,
  );
  if (parsed === null) {
    return unknown(plan.window_preset, "ui_write_receipt_invalid");
  }
  return committed(plan.window_preset, { window_preset: plan.window_preset });
}

export async function executeGraphWidthDecide(
  plan: Extract<ExtendedWritePlan, { kind: "graph_width_decide" }>,
  operations: CoreOperations,
): Promise<ExtendedWriteOutcome> {
  const result = await operations.post<unknown>("/api/v1/graph-width", {
    decision: plan.decision,
  });
  if (result.state === "rejected") {
    return rejected(plan.decision, result.code);
  }
  if (result.state === "unknown") {
    return unknown(plan.decision, result.code);
  }
  const receipt = parseGraphWidthDecisionReceipt(result.data);
  if (receipt === null) {
    return unknown(plan.decision, "ui_write_receipt_invalid");
  }
  return committed(plan.decision, {
    archived_path: receipt.archived_path ?? null,
    exported_path: receipt.exported_path ?? null,
    mismatch: receipt.mismatch ?? null,
  });
}

export async function executeManualExtract(
  plan: Extract<ExtendedWritePlan, { kind: "manual_extract" }>,
  operations: CoreOperations,
): Promise<ExtendedWriteOutcome> {
  const result = await operations.post<unknown>(
    "/api/v1/memory-processing/manual-extract",
    { evidence_ids: plan.evidence_ids },
  );
  if (result.state === "rejected") {
    return rejected("manual_extract", result.code);
  }
  if (result.state === "unknown") {
    return unknown("manual_extract", result.code);
  }
  const receipt = parseManualExtractReceipt(result.data);
  if (receipt === null) {
    return unknown("manual_extract", "ui_write_receipt_invalid");
  }
  return committed("manual_extract", {
    promoted: receipt.promoted,
    batches_planned: receipt.batches_planned,
    batches_current: receipt.batches_current,
  });
}

export function validateExtendedWritePlan(
  value: unknown,
): ExtendedWritePlan | null {
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
    case "memory_note_add":
      return typeof candidate.request_id === "string" &&
        UUID.test(candidate.request_id) &&
        typeof candidate.content_sha256 === "string" &&
        DIGEST.test(candidate.content_sha256) &&
        Number.isSafeInteger(candidate.content_characters) &&
        (candidate.content_characters as number) >= 1 &&
        (candidate.content_characters as number) <= NOTE_MAX_CHARACTERS &&
        Object.keys(candidate).length === 6
        ? (candidate as unknown as ExtendedWritePlan)
        : null;
    case "memory_note_process":
      return typeof candidate.evidence_id === "string" &&
        UUID.test(candidate.evidence_id) &&
        Object.keys(candidate).length === 4
        ? (candidate as unknown as ExtendedWritePlan)
        : null;
    case "extraction_window_set":
      return (EXTRACTION_PRESETS as readonly string[]).includes(
        String(candidate.window_preset),
      ) && Object.keys(candidate).length === 4
        ? (candidate as unknown as ExtendedWritePlan)
        : null;
    case "graph_width_decide":
      return (GRAPH_DECISIONS as readonly string[]).includes(
        String(candidate.decision),
      ) && Object.keys(candidate).length === 4
        ? (candidate as unknown as ExtendedWritePlan)
        : null;
    case "manual_extract":
      return Array.isArray(candidate.evidence_ids) &&
        candidate.evidence_ids.every(
          (id) => typeof id === "string" && UUID.test(id),
        ) &&
        Object.keys(candidate).length === 4
        ? (candidate as unknown as ExtendedWritePlan)
        : null;
    default:
      return null;
  }
}

export function extendedWriteExitCode(document: ExtendedWriteOutcome): number {
  return ["preview", "committed", "recovered"].includes(document.state) ? 0 : 1;
}

export function renderExtendedWriteText(
  document: ExtendedWriteOutcome,
): string {
  if (document.state === "preview") {
    const lines = ["以下操作尚未执行；加 --confirm 后才会写入："];
    const plan = document.plan;
    switch (plan.kind) {
      case "memory_note_add":
        lines.push(`新增端内记忆：${plan.content_characters} 字符`);
        break;
      case "memory_note_process":
        lines.push(`处理端内记忆：${plan.evidence_id}`);
        break;
      case "extraction_window_set":
        lines.push(`设置提取窗口：${plan.window_preset}`);
        break;
      case "graph_width_decide":
        lines.push(`图谱宽度决定：${plan.decision}`);
        break;
      case "manual_extract":
        lines.push(`手动提取：${plan.evidence_ids.length} 条证据`);
        break;
    }
    lines.push(`plan_digest：${plan.digest}`);
    return `${lines.join("\n")}\n`;
  }
  if (document.state === "committed" || document.state === "recovered") {
    return `${document.state === "recovered" ? "已从回执恢复" : "已提交"}：${document.operation_id}\n${JSON.stringify(document.receipt)}\n`;
  }
  const code = "code" in document ? document.code : "ui_write_state_invalid";
  return `操作未完成：${document.state}（${code}）\n`;
}
