// 职责：定义 BotsTalk 协议 v1 的全部类型与常量形状（帧信封、各 payload、artifacts）。
// 本文件仅含类型，无运行时逻辑；字段与冻结契约逐字对应，不得增删。
// intent 默认为 "chat"：若帧中未显式提供 intent，语义上等价于 "chat"（序列化时可选省略）。

/** 协议版本号，v1 恒为 1。 */
export type ProtocolVersion = 1;

/** 帧类型联合。 */
export type FrameType =
  | "message"
  | "stream"
  | "hello"
  | "presence"
  | "gap"
  | "capability_update"
  | "task_event"
  | "game_action"
  | "game_state"
  | "approval_request"
  | "approval_decision";

/** type=game_action 的 payload（客户端→网关：玩家动作）。 */
export interface GameActionPayload {
  game: string;
  seat?: string;
  action?: unknown;
}

/** type=game_state 的 payload（网关→房间广播：当前局面）。 */
export interface GameStatePayload {
  game: string;
  seat?: string;
  state?: unknown;
  state_hash?: string;
}

/** 校验 GameActionPayload，返回错误列表（空表示通过）。 */
export function validateGameAction(p: unknown): string[] {
  const errs: string[] = [];
  if (typeof p !== "object" || p === null) return ["game_action payload must be an object"];
  const o = p as Record<string, unknown>;
  if (typeof o.game !== "string" || o.game.length === 0) errs.push("game must be a non-empty string");
  if (o.seat !== undefined && typeof o.seat !== "string") errs.push("seat must be a string");
  return errs;
}

/** 消息 intent。默认 "chat"。 */
export type Intent = "chat" | "task";

/** task 回执状态。 */
export type TaskStatus = "running" | "done" | "failed" | "unsupported";

/** 任务进度上报内容。 */
export interface TaskProgress {
  message: string;
  data?: unknown;
}

/** 进度上报 message 最大字符数。 */
export const TASK_PROGRESS_MESSAGE_MAX = 2000;

/** 校验 TaskProgress，返回错误列表（空表示通过）。 */
export function validateTaskProgress(p: unknown): string[] {
  const errs: string[] = [];
  if (typeof p !== "object" || p === null) return ["progress: expected object"];
  const o = p as Record<string, unknown>;
  if (typeof o.message !== "string" || o.message.length === 0 || o.message.length > TASK_PROGRESS_MESSAGE_MAX) {
    errs.push("progress.message: must be a non-empty string of at most 2000 chars");
  }
  return errs;
}

/** type=task_event 的 payload（网关向房间广播的任务状态事件）。 */
export interface TaskEventPayload {
  task_id: string;
  status: "dispatched" | TaskStatus | "cancelled" | "pending_approval" | "progress" | "timed_out";
  assignee?: string;
  title?: string;
  note?: string;
  /** status=progress 时必填。 */
  progress?: TaskProgress;
  /** status=progress 时为累计上报次数。 */
  progress_count?: number;
}

/** type=approval_request 的 payload（网关→房间广播：有任务在等人工放行）。 */
export interface ApprovalRequestPayload {
  approval_id: string;
  task_id: string;
  /** 提出任务的发送方 id。 */
  requester: string;
  /** 将执行任务的 adapter id。 */
  assignee: string;
  title: string;
  /** Unix 毫秒：超过此时刻未决策视为过期。 */
  expires_at_ms: number;
}

/** 审批决定。 */
export type ApprovalDecision = "approve" | "reject";

/** type=approval_decision 的 payload（成员→网关：放行或驳回一个待审批任务）。 */
export interface ApprovalDecisionPayload {
  approval_id: string;
  decision: ApprovalDecision;
  note?: string;
}

/** 统一错误码枚举（stream error 终帧与 task 失败共用）。 */
export type ErrorCode =
  | "upstream_error"
  | "timeout"
  | "rate_limited"
  | "cancelled";

/** presence 状态。 */
/** presence 状态；"offline" 用于网关向房间广播成员下线（v1.2 新增）。 */
export type PresenceStatus = "online" | "thinking" | "offline";

/** 累计 token 用量。 */
export interface Usage {
  input_tokens: number;
  output_tokens: number;
}

/** 信封顶层，所有帧共有。 */
export interface Envelope<T = unknown> {
  v: ProtocolVersion;
  type: FrameType;
  /** per-sender 全局单调递增整数，从 1 开始。 */
  seq: number;
  /** 确认对端 seq，整数。 */
  ack: number;
  /** 发送方 id。 */
  sender: string;
  /** 房间 id。 */
  room: string;
  /** Unix 毫秒时间戳。 */
  ts: number;
  /** 网关全局序列号：网关发往客户端的所有帧都携带，从 1 单调递增；客户端发往网关的帧不带，网关忽略入站帧的 gseq。 */
  gseq?: number;
  payload: T;
}

/** type=message 的 payload。intent 未提供时默认为 "chat"。 */
export interface MessagePayload {
  msg_id: string;
  text: string;
  mentions: string[];
  /** 默认 "chat"。 */
  intent?: Intent;
  /** intent=task 时必须提供。 */
  task_id?: string;
  /** task 回执状态。 */
  task_status?: TaskStatus;
  /** 进度上报：assignee→网关，仅 intent=task 时有效。帧顶层 task_id 仍必填（codec 对 intent=task 帧强制要求），须与此处 task_id 一致。 */
  task_progress?: { task_id: string; message: string; data?: unknown };
  /** Shared thread context for the current turn (local-only). Set by AdapterClient on the inbound envelope AFTER wire validation, from gateway room history; never sent on the wire by any adapter. Empty/absent means no context was available (fetch failed, timed out, or feature disabled) and the handler must proceed with text alone. */
  thread_context?: string;
}

/** type=stream 的 payload（增量流式帧）。 */
export interface StreamPayload {
  stream_id: string;
  /** 从 0 开始。 */
  chunk_index: number;
  final: boolean;
  /** 本帧文本增量。 */
  delta: string;
  error?: boolean;
  reason?: string;
  /** 仅末帧携带累计值。 */
  usage?: Usage;
}

/** type=hello 的 payload（建连首帧）。 */
export interface HelloPayload {
  adapter_id: string;
  /** v1.1 为 "1.1"。 */
  protocol_version: string;
  /** v1.1 起语义为客户端已见的最大 gseq（网关全局序列号），用于断线补发；v1.0 语义已废弃。 */
  last_seen_seq: number;
}

/** type=presence 的 payload（心跳）。 */
/** 网关广播成员上下线时带 adapter_id（v1.2 新增可选字段）。 */
export interface PresencePayload {
  status: PresenceStatus;
  adapter_id?: string;
  usage?: Usage;
}

/** type=gap 的 payload（缺口信号）。左闭右闭。 */
export interface GapPayload {
  from_seq: number;
  to_seq: number;
}

/** type=capability_update 的 payload（控制帧，热更新不断线）。 */
export interface CapabilityUpdatePayload {
  /** 单调递增。 */
  version: number;
  capabilities: {
    intents: Intent[];
  };
}

/** artifacts v1：独立 HTTP 上传流程的建模。 */
export interface ArtifactUploadRequest {
  filename: string;
  declared_size: number;
  mime?: string;
}

export interface ArtifactUploadGrant {
  upload_url: string;
  expires_at_ms: number;
}

export interface ArtifactRecord {
  id: string;
  filename: string;
  size: number;
  external_url?: string;
}
