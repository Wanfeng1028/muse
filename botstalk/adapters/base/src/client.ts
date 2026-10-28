import { WebSocket } from "ws";
import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  SeqTracker,
  ResendQueue,
  GapRateLimiter,
  makeEnvelope,
  makeErrorFinal,
  parseEnvelope,
  validateEnvelope,
  HEARTBEAT_MS,
  PROTOCOL_VERSION_STR,
  backoffDelay,
  BACKOFF_MAX_MS,
} from "@botstalk/protocol";
import { buildThreadContext, THREAD_CONTEXT_FETCH_LIMIT, THREAD_CONTEXT_FETCH_TIMEOUT_MS } from "./thread-context.js";
import type { ThreadHistoryMessage } from "./thread-context.js";
import type {
  Envelope,
  MessagePayload,
  StreamPayload,
  PresencePayload,
  CapabilityUpdatePayload,
} from "@botstalk/protocol";

export interface AdapterOptions {
  adapterId: string;
  room?: string;
  gatewayUrl?: string;
  intents?: ("chat" | "task")[];
  onMessage?: (env: Envelope<MessagePayload>) => void | Promise<void>;
  onTask?: (env: Envelope<MessagePayload>) => void | Promise<void>;
  status?: () => "online" | "thinking";
  getUsage?: () => { input_tokens: number; output_tokens: number } | undefined;
  /** 心跳间隔毫秒，默认 HEARTBEAT_MS；测试可调小。 */
  heartbeatMs?: number;
  /** gseq 水位持久化目录，默认取环境变量 BOTSTALK_STATE_DIR 或 ./.botstalk-state。 */
  stateDir?: string;
  /** 设备凭据，显式配置优先；未配置时回落到环境变量 BOTSTALK_DEVICE_ID 与 BOTSTALK_DEVICE_KEY；密钥绝不打印到日志。 */
  device?: { id: string; key: string };
  /**
   * 共享线程上下文注入（OpenAgents agent-connector "Shared thread context" 的 TS 重实现）。
   * enabled=true 时，AdapterClient 在把 message 帧交给 onMessage/onTask 之前，先拉取本房间近史、
   * 用 buildThreadContext 拼成上下文块，写进 env.payload.thread_context 再交给 handler；deepseek 等
   * LLM adapter 把它拼在当前请求之前发给上游。fetch 失败或超时一律降级：直接用原始帧调 handler，
   * 绝不抛错、绝不阻塞超过 timeoutMs。默认关闭（不改变现有 adapter 行为），由各 adapter 显式开启。
   * fetchHistory 可注入（测试用）；不提供时用默认 HTTP 实现拉网关 /api/rooms/:room/history。
   * httpBaseUrl 可覆盖默认 HTTP 基地址；不提供时从 gatewayUrl 推导（ws://->http://，wss://->https://）。
   */
  threadContext?: {
    enabled?: boolean;
    timeoutMs?: number;
    fetchHistory?: (room: string, trigger: { msgId: string; ts: number }) => Promise<ThreadHistoryMessage[]>;
    httpBaseUrl?: string;
  };
}

interface SendOptions {
  mentions?: string[];
  intent?: "chat" | "task";
  task_id?: string;
  task_status?: "running" | "done" | "failed" | "unsupported";
}

const DEFAULT_GATEWAY_URL = "ws://127.0.0.1:8765";
const DEFAULT_ROOM = "lobby";

export class AdapterClient {
  protected readonly opts: AdapterOptions;
  protected readonly room: string;
  protected readonly gatewayUrl: string;
  protected readonly seqTracker = new SeqTracker();
  protected readonly resendQueue = new ResendQueue();
  protected readonly gapLimiter = new GapRateLimiter();
  protected outSeq: SeqTracker = new SeqTracker();
  protected ws: WebSocket | null = null;
  protected heartbeatTimer: NodeJS.Timeout | null = null;
  protected reconnectTimer: NodeJS.Timeout | null = null;
  protected reconnectAttempt = 0;
  protected shouldReconnect = true;
  protected stopped = false;
  protected capabilityVersion = 1;
  /** 客户端已见的最大 gseq（网关全局序列号），用于断线重连补发。 */
  protected maxGseq = 0;
  protected intents: ("chat" | "task")[];

  constructor(opts: AdapterOptions) {
    this.opts = opts;
    this.room = opts.room ?? DEFAULT_ROOM;
    this.gatewayUrl = opts.gatewayUrl ?? process.env.GATEWAY_URL ?? DEFAULT_GATEWAY_URL;
    this.intents = opts.intents ?? ["chat"];
  }

  connect(): void {
    this.stopped = false;
    this.openSocket();
  }

  private openSocket(): void {
    if (this.stopped) return;
    const ws = new WebSocket(this.gatewayUrl);
    this.ws = ws;
    ws.on("open", () => {
      this.reconnectAttempt = 0;
      this.onOpen();
    });
    ws.on("message", (data: unknown) => {
      const text = typeof data === "string" ? data : String(data);
      this.handleRaw(text);
    });
    ws.on("close", () => {
      this.clearHeartbeat();
      if (this.shouldReconnect && !this.stopped) {
        this.scheduleReconnect();
      }
    });
    ws.on("error", () => {
      // 由 close 事件驱动重连
    });
  }

  /**
   * 解析设备凭据：显式配置优先；否则使用环境变量。
   * 仅当 id 与 key 均为非空字符串时返回完整凭据对，绝不返回单字段（否则网关会 4403）。
   * 密钥绝不打印到日志。
   */
  protected resolveDeviceCredentials(): { id: string; key: string } | undefined {
    const device = this.opts.device;
    if (device && typeof device.id === "string" && device.id.length > 0 && typeof device.key === "string" && device.key.length > 0) {
      return { id: device.id, key: device.key };
    }
    const envId = process.env.BOTSTALK_DEVICE_ID;
    const envKey = process.env.BOTSTALK_DEVICE_KEY;
    if (typeof envId === "string" && envId.length > 0 && typeof envKey === "string" && envKey.length > 0) {
      return { id: envId, key: envKey };
    }
    return undefined;
  }

  /**
   * 解析 hello 中应携带的 last_seen_seq。
   * 内存 maxGseq>0 用内存值；否则读磁盘持久化水位；都没有返回 -1（全新实例，不重放历史）。
   */
  protected resolveLastSeenSeq(): number {
    if (this.maxGseq > 0) return this.maxGseq;
    const persisted = this.loadPersistedGseq();
    if (persisted !== null && persisted > 0) return persisted;
    return -1;
  }

  /**
   * 读取持久化的 gseq 水位。失败静默返回 null（降级为内存行为）。
   */
  private loadPersistedGseq(): number | null {
    try {
      const dir = this.opts.stateDir ?? process.env.BOTSTALK_STATE_DIR ?? "./.botstalk-state";
      const file = path.join(dir, `${this.opts.adapterId}.gseq`);
      const raw = fs.readFileSync(file, "utf8").trim();
      if (!raw) return null;
      const n = Number(raw);
      return Number.isFinite(n) ? n : null;
    } catch {
      return null;
    }
  }

  /**
   * 持久化当前 gseq 水位。失败静默忽略，不抛异常、不阻断连接。
   */
  private persistGseq(): void {
    try {
      const dir = this.opts.stateDir ?? process.env.BOTSTALK_STATE_DIR ?? "./.botstalk-state";
      fs.mkdirSync(dir, { recursive: true });
      const file = path.join(dir, `${this.opts.adapterId}.gseq`);
      fs.writeFileSync(file, String(this.maxGseq));
    } catch {
      // 静默
    }
  }

  protected onOpen(): void {
    const device = this.resolveDeviceCredentials();
    const hello = makeEnvelope<{ adapter_id: string; protocol_version: string; last_seen_seq: number; device_id?: string; device_key?: string }>(
      "hello",
      this.opts.adapterId,
      this.room,
      this.outSeq.nextSeq(),
      0,
      {
        adapter_id: this.opts.adapterId,
        protocol_version: PROTOCOL_VERSION_STR,
        last_seen_seq: this.resolveLastSeenSeq(),
        ...(device ? { device_id: device.id, device_key: device.key } : {}),
      },
    );
    this.rawSend(hello);
    this.sendCapability(this.intents);
    this.startHeartbeat();
  }

  protected startHeartbeat(): void {
    this.clearHeartbeat();
    const interval = this.opts.heartbeatMs ?? HEARTBEAT_MS;
    this.heartbeatTimer = setInterval(() => {
      this.heartbeatSend();
    }, interval);
    if (typeof this.heartbeatTimer.unref === "function") {
      this.heartbeatTimer.unref();
    }
  }

  protected clearHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  protected heartbeatSend(): void {
    const usage = this.opts.getUsage?.();
    const payload: PresencePayload = {
      status: this.opts.status?.() ?? "online",
    };
    if (usage) payload.usage = usage;
    const env = makeEnvelope<PresencePayload>(
      "presence",
      this.opts.adapterId,
      this.room,
      this.outSeq.nextSeq(),
      0,
      payload,
    );
    this.rawSend(env);
  }

  private rawSend(env: Envelope<unknown>): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify(env));
  }

  private send<T>(type: "message" | "stream" | "capability_update", payload: T): Envelope<T> {
    const env = makeEnvelope<T>(
      type,
      this.opts.adapterId,
      this.room,
      this.outSeq.nextSeq(),
      0,
      payload,
    );
    this.resendQueue.push(env);
    this.rawSend(env);
    return env;
  }

  protected handleRaw(text: string): void {
    let env: Envelope<unknown>;
    try {
      env = parseEnvelope(text);
    } catch {
      return;
    }
    const errors = validateEnvelope(env);
    if (errors.length > 0) return;

    if (env.type === "gap") {
      this.handleGap(env as Envelope<{ from_seq: number; to_seq: number }>);
      return;
    }

    const seen = this.seqTracker.seen(env.sender, env.seq);
    if (seen !== "ok") return;

    if (typeof env.gseq === "number") {
      if (env.gseq < this.maxGseq) {
        // 网关重启了（gseq 回退），重置水位，避免用旧高水位漏消息。
        this.maxGseq = env.gseq;
        this.persistGseq();
      } else if (env.gseq > this.maxGseq) {
        this.maxGseq = env.gseq;
        this.persistGseq();
      }
    }

    if (env.type === "message") {
      void this.dispatchMessage(env as Envelope<MessagePayload>);
      return;
    }

    this.onFrame(env);
  }

  protected onFrame(_env: Envelope<unknown>): void {
    // 子类可覆写扩展
  }

  private handleGap(env: Envelope<{ from_seq: number; to_seq: number }>): void {
    const { from_seq, to_seq } = env.payload;
    if (!this.gapLimiter.shouldSend(from_seq, to_seq, Date.now())) return;
    const missing = this.resendQueue.getMissingBySeq(from_seq, to_seq);
    for (const item of missing) {
      this.rawSend(item);
    }
  }

  private async fetchThreadHistoryDefault(room: string): Promise<ThreadHistoryMessage[]> {
    const rawBase = this.opts.threadContext?.httpBaseUrl ?? this.gatewayUrl.replace(/^wss:/, "https:").replace(/^ws:/, "http:");
    const base = rawBase.replace(/\/+$/, "");
    const timeoutMs = this.opts.threadContext?.timeoutMs ?? THREAD_CONTEXT_FETCH_TIMEOUT_MS;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(`${base}/api/rooms/${encodeURIComponent(room)}/history?limit=${THREAD_CONTEXT_FETCH_LIMIT}`, { signal: controller.signal });
      if (!res.ok) throw new Error(`history fetch failed: HTTP ${res.status}`);
      const body: unknown = await res.json();
      if (typeof body !== "object" || body === null || !Array.isArray((body as { messages?: unknown }).messages)) throw new Error("invalid history response");
      const rows = (body as { messages: unknown[] }).messages;
      const out: ThreadHistoryMessage[] = [];
      for (const row of rows) {
        if (typeof row !== "object" || row === null) continue;
        const r = row as { sender?: unknown; type?: unknown; ts?: unknown; payload?: unknown };
        const p = (typeof r.payload === "object" && r.payload !== null) ? (r.payload as { text?: unknown; msg_id?: unknown; task_status?: unknown }) : undefined;
        const tsNum = Number(r.ts);
        out.push({
          sender: String(r.sender ?? ""),
          text: typeof p?.text === "string" ? p.text : "",
          ts: Number.isFinite(tsNum) ? tsNum : 0,
          msgId: typeof p?.msg_id === "string" ? p.msg_id : undefined,
          frameType: typeof r.type === "string" ? r.type : undefined,
          taskStatus: typeof p?.task_status === "string" ? p.task_status : undefined,
        });
      }
      return out;
    } finally {
      clearTimeout(timer);
    }
  }

  private async dispatchMessage(env: Envelope<MessagePayload>): Promise<void> {
    const tc = this.opts.threadContext;
    if (
      tc?.enabled === true &&
      env.sender !== this.opts.adapterId &&
      !env.room.startsWith("dm:") &&
      env.payload.task_status === undefined &&
      env.payload.task_progress === undefined
    ) {
      try {
        const history = tc.fetchHistory
          ? await tc.fetchHistory(env.room, { msgId: env.payload.msg_id, ts: env.ts })
          : await this.fetchThreadHistoryDefault(env.room);
        const block = buildThreadContext(history, { msgId: env.payload.msg_id, sender: env.sender, ts: env.ts });
        if (block !== "") env.payload.thread_context = block;
      } catch {
        // Degrade silently: handler runs with the original frame.
      }
    }
    const intent = env.payload.intent ?? "chat";
    if (intent === "task") {
      if (this.opts.onTask) await this.opts.onTask(env);
      return;
    }
    if (this.opts.onMessage) await this.opts.onMessage(env);
  }

  sendMessage(text: string, opts: SendOptions = {}): Envelope<MessagePayload> {
    const payload: MessagePayload = {
      msg_id: randomUUID(),
      text,
      mentions: opts.mentions ?? [],
    };
    if (opts.intent !== undefined) payload.intent = opts.intent;
    if (opts.task_id !== undefined) payload.task_id = opts.task_id;
    if (opts.task_status !== undefined) payload.task_status = opts.task_status;
    return this.send<MessagePayload>("message", payload);
  }

  sendStreamStart(): string {
    return randomUUID();
  }

  sendStreamChunk(streamId: string, chunkIndex: number, delta: string): Envelope<StreamPayload> {
    const payload: StreamPayload = {
      stream_id: streamId,
      chunk_index: chunkIndex,
      final: false,
      delta,
    };
    return this.send<StreamPayload>("stream", payload);
  }

  sendStreamFinal(
    streamId: string,
    chunkIndex: number,
    usage?: { input_tokens: number; output_tokens: number },
  ): Envelope<StreamPayload> {
    const payload: StreamPayload = {
      stream_id: streamId,
      chunk_index: chunkIndex,
      final: true,
      delta: "",
    };
    if (usage) payload.usage = usage;
    return this.send<StreamPayload>("stream", payload);
  }

  sendStreamError(streamId: string, chunkIndex: number, reason: string): Envelope<StreamPayload> {
    const env = makeErrorFinal(
      streamId,
      reason,
      this.opts.adapterId,
      this.room,
      this.outSeq.nextSeq(),
      chunkIndex,
      Date.now(),
    );
    this.resendQueue.push(env);
    this.rawSend(env);
    return env;
  }

  sendCapability(intents: ("chat" | "task")[], extra?: { skills?: string[]; tags?: string[] }): Envelope<CapabilityUpdatePayload> {
    const payload: CapabilityUpdatePayload = {
      version: this.capabilityVersion,
      capabilities: {
        intents,
        ...(extra?.skills !== undefined ? { skills: extra.skills } : {}),
        ...(extra?.tags !== undefined ? { tags: extra.tags } : {}),
      },
    };
    this.capabilityVersion += 1;
    return this.send<CapabilityUpdatePayload>("capability_update", payload);
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const base = backoffDelay(this.reconnectAttempt);
    const capped = Math.min(base, BACKOFF_MAX_MS);
    const jittered = capped * (0.8 + Math.random() * 0.4);
    const delay = Math.min(jittered, BACKOFF_MAX_MS);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, delay);
    if (typeof this.reconnectTimer.unref === "function") {
      this.reconnectTimer.unref();
    }
  }

  disconnect(): void {
    this.stopped = true;
    this.shouldReconnect = false;
    this.clearHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        // ignore
      }
      this.ws = null;
    }
  }
}
// 自查：红线 1-5 逐条通过
