// 职责：信封的构造、JSON 解析与结构校验。纯函数，无副作用、无时钟。
// parseEnvelope 对 JSON 语法错误抛 SyntaxError，对字段缺失/类型错误抛 TypeError 并指明字段名。
// validateEnvelope 返回错误字符串列表（空数组=合法），覆盖契约中的结构约束。

import type {
  Envelope,
  FrameType,
  HelloPayload,
  MessagePayload,
  PresencePayload,
  StreamPayload,
  GapPayload,
  CapabilityUpdatePayload,
  Intent,
  TaskStatus,
  TaskEventPayload,
  ApprovalRequestPayload,
  ApprovalDecisionPayload,
} from "./types.js";
import { validateTaskProgress, TASK_PROGRESS_MESSAGE_MAX } from "./types.js";
import { PROTOCOL_VERSION } from "./constants.js";
import { validateVisibility } from "./visibility.js";

const FRAME_TYPES: readonly FrameType[] = [
  "message",
  "stream",
  "hello",
  "presence",
  "gap",
  "capability_update",
  "task_event",
  "game_action",
  "game_state",
  "approval_request",
  "approval_decision",
];

const INTENTS: readonly Intent[] = ["chat", "task"];
const TASK_STATUSES: readonly TaskStatus[] = [
  "running",
  "done",
  "failed",
  "unsupported",
];

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && Number.isFinite(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

/** 构造信封。ts 未提供时使用 Date.now()。 */
export function makeEnvelope<T>(
  type: FrameType,
  sender: string,
  room: string,
  seq: number,
  ack: number,
  payload: T,
  ts?: number,
  extra?: { visibility?: "direct" | "restricted"; visible_to?: string[] },
): Envelope<T> {
  return {
    v: PROTOCOL_VERSION,
    type,
    seq,
    ack,
    sender,
    room,
    ts: ts ?? Date.now(),
    payload,
    ...(extra?.visibility !== undefined ? { visibility: extra.visibility } : {}),
    ...(extra?.visible_to !== undefined ? { visible_to: extra.visible_to } : {}),
  };
}

/** 解析 JSON 信封。JSON 语法错误 -> SyntaxError；结构非法 -> TypeError。 */
export function parseEnvelope(json: string): Envelope {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new SyntaxError(`invalid JSON envelope: ${message}`);
  }

  if (!isPlainObject(parsed)) {
    throw new TypeError("field envelope: expected object");
  }

  const env = parsed;

  if (env["v"] === undefined) {
    throw new TypeError("field v: missing");
  }
  if (env["v"] !== PROTOCOL_VERSION) {
    throw new TypeError(`field v: expected ${PROTOCOL_VERSION}`);
  }

  if (env["type"] === undefined) {
    throw new TypeError("field type: missing");
  }
  if (typeof env["type"] !== "string" || !FRAME_TYPES.includes(env["type"] as FrameType)) {
    throw new TypeError("field type: invalid frame type");
  }

  if (env["seq"] === undefined) {
    throw new TypeError("field seq: missing");
  }
  if (!isFiniteInteger(env["seq"])) {
    throw new TypeError("field seq: expected integer");
  }

  if (env["ack"] === undefined) {
    throw new TypeError("field ack: missing");
  }
  if (!isFiniteInteger(env["ack"])) {
    throw new TypeError("field ack: expected integer");
  }

  if (env["sender"] === undefined) {
    throw new TypeError("field sender: missing");
  }
  if (typeof env["sender"] !== "string") {
    throw new TypeError("field sender: expected string");
  }

  if (env["room"] === undefined) {
    throw new TypeError("field room: missing");
  }
  if (typeof env["room"] !== "string") {
    throw new TypeError("field room: expected string");
  }

  if (env["ts"] === undefined) {
    throw new TypeError("field ts: missing");
  }
  if (!isFiniteInteger(env["ts"])) {
    throw new TypeError("field ts: expected integer");
  }

  if (env["payload"] === undefined) {
    throw new TypeError("field payload: missing");
  }

  return env as unknown as Envelope;
}

/** 校验信封结构，返回错误列表。空数组表示合法。 */
export function validateEnvelope(env: Envelope): string[] {
  const errors: string[] = [];

  if (!isPlainObject(env)) {
    errors.push("envelope: expected object");
    return errors;
  }

  if (env.v !== PROTOCOL_VERSION) {
    errors.push(`v: must equal ${PROTOCOL_VERSION}`);
  }

  if (!isFiniteInteger(env.seq) || env.seq <= 0) {
    errors.push("seq: must be a positive integer");
  }

  if (env.gseq !== undefined && (!isFiniteInteger(env.gseq) || env.gseq <= 0)) {
    errors.push("gseq: must be a positive integer");
  }

  if (!isFiniteInteger(env.ack)) {
    errors.push("ack: must be an integer");
  }

  if (!isNonEmptyString(env.sender)) {
    errors.push("sender: must be a non-empty string");
  }

  if (!isNonEmptyString(env.room)) {
    errors.push("room: must be a non-empty string");
  }

  if (typeof env.type !== "string" || !FRAME_TYPES.includes(env.type as FrameType)) {
    errors.push("type: invalid frame type");
    return errors;
  }

  if (!isFiniteInteger(env.ts)) {
    errors.push("ts: must be an integer");
  }

  errors.push(...validateVisibility(env.visibility, env.visible_to));

  const payload: unknown = env.payload;

  switch (env.type) {
    case "message":
      errors.push(...validateMessagePayload(payload));
      break;
    case "stream":
      errors.push(...validateStreamPayload(payload));
      break;
    case "hello":
      errors.push(...validateHelloPayload(payload));
      break;
    case "presence":
      errors.push(...validatePresencePayload(payload));
      break;
    case "gap":
      errors.push(...validateGapPayload(payload));
      break;
    case "capability_update":
      errors.push(...validateCapabilityUpdatePayload(payload));
      break;
    case "task_event":
      errors.push(...validateTaskEventPayload(payload));
      break;
    case "approval_request":
      errors.push(...validateApprovalRequestPayload(payload));
      break;
    case "approval_decision":
      errors.push(...validateApprovalDecisionPayload(payload));
      break;
  }

  return errors;
}

function validateTaskEventPayload(payload: unknown): string[] {
  const errors: string[] = [];
  if (!isPlainObject(payload)) { errors.push("payload: expected object"); return errors; }
  if (!isNonEmptyString(payload["task_id"])) errors.push("payload.task_id: must be a non-empty string");
  const ok = ["dispatched","running","done","failed","unsupported","cancelled","pending_approval","progress","timed_out"];
  if (typeof payload["status"] !== "string" || !ok.includes(payload["status"])) errors.push("payload.status: invalid task event status");
  for (const k of ["assignee","title","note"]) {
    if (payload[k] !== undefined && typeof payload[k] !== "string") errors.push("payload." + k + ": must be a string");
  }
  if (payload["status"] === "progress") {
    if (payload["progress"] === undefined) errors.push("payload.progress: required when status is 'progress'");
    else errors.push(...validateTaskProgress(payload["progress"]));
    const pc = payload["progress_count"];
    if (pc !== undefined && (!Number.isInteger(pc) || (pc as number) < 0)) errors.push("payload.progress_count: must be a non-negative integer");
  } else if (payload["progress"] !== undefined) {
    errors.push("payload.progress: only allowed when status is 'progress'");
  }
  return errors;
}

function validateApprovalRequestPayload(payload: unknown): string[] {
  const errors: string[] = [];
  if (!isPlainObject(payload)) { errors.push("payload: expected object"); return errors; }
  if (!isNonEmptyString(payload["approval_id"])) errors.push("payload.approval_id: must be a non-empty string");
  if (!isNonEmptyString(payload["task_id"])) errors.push("payload.task_id: must be a non-empty string");
  if (!isNonEmptyString(payload["requester"])) errors.push("payload.requester: must be a non-empty string");
  if (!isNonEmptyString(payload["assignee"])) errors.push("payload.assignee: must be a non-empty string");
  if (typeof payload["title"] !== "string") errors.push("payload.title: must be a string");
  if (!isFiniteInteger(payload["expires_at_ms"])) errors.push("payload.expires_at_ms: must be an integer");
  return errors;
}

function validateApprovalDecisionPayload(payload: unknown): string[] {
  const errors: string[] = [];
  if (!isPlainObject(payload)) { errors.push("payload: expected object"); return errors; }
  if (!isNonEmptyString(payload["approval_id"])) errors.push("payload.approval_id: must be a non-empty string");
  if (payload["decision"] !== "approve" && payload["decision"] !== "reject") errors.push("payload.decision: must be 'approve' or 'reject'");
  if (payload["note"] !== undefined && typeof payload["note"] !== "string") errors.push("payload.note: must be a string");
  return errors;
}

function validateMessagePayload(payload: unknown): string[] {
  const errors: string[] = [];
  if (!isPlainObject(payload)) {
    errors.push("payload: expected object");
    return errors;
  }

  if (!isNonEmptyString(payload["msg_id"])) {
    errors.push("payload.msg_id: must be a non-empty string");
  }
  if (typeof payload["text"] !== "string") {
    errors.push("payload.text: must be a string");
  }
  const mentions = payload["mentions"];
  if (!Array.isArray(mentions) || !mentions.every((m) => typeof m === "string")) {
    errors.push("payload.mentions: must be a string[]");
  }

  const replyTo = payload["reply_to"];
  if (replyTo !== undefined) {
    if (!isNonEmptyString(replyTo) || (replyTo as string).length > 128) errors.push("payload.reply_to: must be a non-empty string of at most 128 chars");
    else if (replyTo === payload["msg_id"]) errors.push("payload.reply_to: must not equal msg_id");
  }
  const threadId = payload["thread_id"];
  if (threadId !== undefined && (!isNonEmptyString(threadId) || (threadId as string).length > 128)) errors.push("payload.thread_id: must be a non-empty string of at most 128 chars");

  const intent = payload["intent"];
  if (intent !== undefined) {
    if (typeof intent !== "string" || !INTENTS.includes(intent as Intent)) {
      errors.push("payload.intent: must be 'chat' or 'task'");
    }
  }

  const effectiveIntent: Intent = (intent as Intent | undefined) ?? "chat";
  if (effectiveIntent === "task") {
    if (!isNonEmptyString(payload["task_id"])) {
      errors.push("payload.task_id: required when intent is 'task'");
    }
  }

  const taskStatus = payload["task_status"];
  if (taskStatus !== undefined) {
    if (typeof taskStatus !== "string" || !TASK_STATUSES.includes(taskStatus as TaskStatus)) {
      errors.push(
        "payload.task_status: must be 'running' | 'done' | 'failed' | 'unsupported'",
      );
    }
  }

  const rc = payload["required_capabilities"];
  if (rc !== undefined) {
    if (!isPlainObject(rc)) {
      errors.push("payload.required_capabilities: expected object");
    } else {
      for (const key of ["skills", "tags", "input_modes", "output_modes"] as const) {
        const v = rc[key];
        if (v !== undefined && (!Array.isArray(v) || !v.every((s) => typeof s === "string"))) {
          errors.push(`payload.required_capabilities.${key}: must be a string[]`);
        }
      }
    }
  }

  const tp = payload["task_progress"];
  if (tp !== undefined) {
    if (!isPlainObject(tp)) {
      errors.push("payload.task_progress: expected object");
    } else {
      if (!isNonEmptyString(tp["task_id"])) errors.push("payload.task_progress.task_id: must be a non-empty string");
      const msg = tp["message"];
      if (typeof msg !== "string" || msg.length === 0 || msg.length > TASK_PROGRESS_MESSAGE_MAX) errors.push("payload.task_progress.message: must be a non-empty string of at most 2000 chars");
    }
  }

  return errors;
}

function validateStreamPayload(payload: unknown): string[] {
  const errors: string[] = [];
  if (!isPlainObject(payload)) {
    errors.push("payload: expected object");
    return errors;
  }

  if (!isNonEmptyString(payload["stream_id"])) {
    errors.push("payload.stream_id: must be a non-empty string");
  }
  if (!isFiniteInteger(payload["chunk_index"]) || (payload["chunk_index"] as number) < 0) {
    errors.push("payload.chunk_index: must be an integer >= 0");
  }
  if (typeof payload["final"] !== "boolean") {
    errors.push("payload.final: must be a boolean");
  }
  if (typeof payload["delta"] !== "string") {
    errors.push("payload.delta: must be a string");
  }

  const error = payload["error"];
  if (error !== undefined && typeof error !== "boolean") {
    errors.push("payload.error: must be a boolean");
  }
  const reason = payload["reason"];
  if (reason !== undefined && typeof reason !== "string") {
    errors.push("payload.reason: must be a string");
  }

  const usage = payload["usage"];
  if (usage !== undefined) {
    if (!isPlainObject(usage)) {
      errors.push("payload.usage: must be an object");
    } else {
      if (!isFiniteInteger(usage["input_tokens"])) {
        errors.push("payload.usage.input_tokens: must be an integer");
      }
      if (!isFiniteInteger(usage["output_tokens"])) {
        errors.push("payload.usage.output_tokens: must be an integer");
      }
    }
  }

  if (payload["error"] === true && typeof payload["reason"] !== "string") {
    errors.push("payload.reason: required when error is true");
  }

  return errors;
}

function validateHelloPayload(payload: unknown): string[] {
  const errors: string[] = [];
  if (!isPlainObject(payload)) {
    errors.push("payload: expected object");
    return errors;
  }
  if (!isNonEmptyString(payload["adapter_id"])) {
    errors.push("payload.adapter_id: must be a non-empty string");
  }
  if (!isNonEmptyString(payload["protocol_version"])) {
    errors.push("payload.protocol_version: must be a non-empty string");
  }
  if (!isFiniteInteger(payload["last_seen_seq"])) {
    errors.push("payload.last_seen_seq: must be an integer");
  }
  return errors;
}

function validatePresencePayload(payload: unknown): string[] {
  const errors: string[] = [];
  if (!isPlainObject(payload)) {
    errors.push("payload: expected object");
    return errors;
  }
  const status = payload["status"];
  if (status !== "online" && status !== "thinking" && status !== "offline") {
    errors.push("payload.status: must be 'online', 'thinking' or 'offline'");
  }
  const usage = payload["usage"];
  if (usage !== undefined) {
    if (!isPlainObject(usage)) {
      errors.push("payload.usage: must be an object");
    } else {
      if (!isFiniteInteger(usage["input_tokens"])) {
        errors.push("payload.usage.input_tokens: must be an integer");
      }
      if (!isFiniteInteger(usage["output_tokens"])) {
        errors.push("payload.usage.output_tokens: must be an integer");
      }
    }
  }
  return errors;
}

function validateGapPayload(payload: unknown): string[] {
  const errors: string[] = [];
  if (!isPlainObject(payload)) {
    errors.push("payload: expected object");
    return errors;
  }
  if (!isFiniteInteger(payload["from_seq"])) {
    errors.push("payload.from_seq: must be an integer");
  }
  if (!isFiniteInteger(payload["to_seq"])) {
    errors.push("payload.to_seq: must be an integer");
  }
  if (isFiniteInteger(payload["from_seq"]) && (payload["from_seq"] as number) <= 0) {
    errors.push("payload.from_seq: must be > 0");
  }
  if (isFiniteInteger(payload["to_seq"]) && (payload["to_seq"] as number) <= 0) {
    errors.push("payload.to_seq: must be > 0");
  }
  if (
    isFiniteInteger(payload["from_seq"]) &&
    isFiniteInteger(payload["to_seq"]) &&
    (payload["from_seq"] as number) > (payload["to_seq"] as number)
  ) {
    errors.push("payload: from_seq must be <= to_seq");
  }
  return errors;
}

function validateCapabilityUpdatePayload(payload: unknown): string[] {
  const errors: string[] = [];
  if (!isPlainObject(payload)) {
    errors.push("payload: expected object");
    return errors;
  }
  if (!isFiniteInteger(payload["version"])) {
    errors.push("payload.version: must be an integer");
  } else if ((payload["version"] as number) <= 0) {
    errors.push("payload.version: must be > 0");
  }
  const capabilities = payload["capabilities"];
  if (!isPlainObject(capabilities)) {
    errors.push("payload.capabilities: must be an object");
  } else {
    const intents = capabilities["intents"];
    if (!Array.isArray(intents) || !intents.every((i) => INTENTS.includes(i as Intent))) {
      errors.push("payload.capabilities.intents: must be an Intent[]");
    }
    for (const key of ["skills", "tags"] as const) {
      const v = capabilities[key];
      if (v !== undefined && (!Array.isArray(v) || !v.every((s) => typeof s === "string"))) {
        errors.push(`payload.capabilities.${key}: must be a string[]`);
      }
    }
  }
  return errors;
}

export type {
  Envelope,
  MessagePayload,
  StreamPayload,
  HelloPayload,
  PresencePayload,
  GapPayload,
  CapabilityUpdatePayload,
};
