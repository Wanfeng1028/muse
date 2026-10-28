import { WebSocket, WebSocketServer } from "ws";
import {
  SeqTracker,
  ResendQueue,
  GapRateLimiter,
  StreamTracker,
  makeEnvelope,
  parseEnvelope,
  validateEnvelope,
  validateGameAction,
  isGameAllowed,
  makeGap,
  HEARTBEAT_MS,
  OFFLINE_AFTER_MS,
  ZOMBIE_SWEEP_MS,
  PROTOCOL_VERSION_STR,
  RESEND_MAX_MSGS,
} from "@botstalk/protocol";
import type {
  Envelope,
  MessagePayload,
  StreamPayload,
  HelloPayload,
  PresencePayload,
  PresenceStatus,
  GapPayload,
  CapabilityUpdatePayload,
  TaskEventPayload,
  ReactionEventPayload,
  GameActionPayload,
  GameStatePayload,
  ApprovalDecisionPayload,
} from "@botstalk/protocol";
import * as store from "./db.js";
import { visibleRecipients } from "@botstalk/protocol";
import { deriveThreadId, findReplyTarget, targetThreadId } from "./thread.js";
import type { Db } from "./db.js";
import { randomUUID, createHash, timingSafeEqual } from "node:crypto";
import { hashDeviceKey } from "./devices.js";

/** 小游戏规则引擎：把玩家动作算成新局面。 */
export interface GameEngine {
  applyAction(prevState: unknown, action: GameActionPayload): unknown;
}

/** 默认透传引擎：新局面 = action 本体。真实游戏规则引擎另行注册。 */
export class PassthroughGameEngine implements GameEngine {
  applyAction(_prevState: unknown, action: GameActionPayload): unknown {
    return action.action ?? null;
  }
}

export interface Conn {
  ws: WebSocket;
  adapterId: string;
  room: string;
  /** hello 设备鉴权成功时绑定的 device_id；legacy 连接为 undefined。 */
  deviceId?: string;
  lastFrameAtMs: number;
  maxSeenSeq: number;
  seqTracker: SeqTracker;
  gapLimiter: GapRateLimiter;
  capabilities: { intents: ("chat" | "task")[] };
  capabilityVersion: number;
  /** capability_update 声明的技能键（缺失声明时为空数组）。 */
  capabilitySkills: string[];
  /** capability_update 声明的标签（缺失声明时为空数组）。 */
  capabilityTags: string[];
  usageIn: number;
  usageOut: number;
  online: boolean;
}

export class Hub {
  readonly conns = new Map<string, Conn>();
  readonly serverSeq = new SeqTracker();
  readonly streamTracker = new StreamTracker();
  private resendQueues = new Map<string, ResendQueue>();
  private adapterRooms = new Map<string, string>();
  public onMessage: ((env: Envelope<MessagePayload>) => void) | null = null;
  public onApprovalDecision: ((env: Envelope<ApprovalDecisionPayload>) => void) | null = null;

  private readonly gameBroadcastThrottleMs: number;
  private readonly gameEngines = new Map<string, GameEngine>();
  private readonly lastGameBroadcastMs = new Map<string, number>();

  constructor(private readonly db: Db, opts?: { gameBroadcastThrottleMs?: number }) {
    const raw = store.getGatewayState(db, "global_seq");
    const parsed = raw === undefined ? Number.NaN : Number(raw);
    this.globalSeq = Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
    this.gameBroadcastThrottleMs = opts?.gameBroadcastThrottleMs ?? 500;
  }

  /** 注册指定游戏的规则引擎；未注册的游戏用透传引擎。 */
  registerGameEngine(game: string, engine: GameEngine): void {
    this.gameEngines.set(game, engine);
  }

  public nextSeq(): number {
    return this.serverSeq.nextSeq();
  }

  /**
   * 网关全局序列号计数器。
   * 已知局限（v1.1 明确边界，不修）：globalSeq 是内存计数器，网关重启后从 1 开始；
   * resendQueues 也是内存的，重启即丢。
   */
  /**
   * 网关全局序列号计数器。
   * 现在会写透到 DB，重启后从上次的值继续，不再回到 1。
   */
  private globalSeq = 0;

  /** 给发往客户端的帧打网关全局序列号。幂等：同一逻辑帧 broadcast 给多个客户端时 gseq 必须一致。 */
  private stampOutbound(env: Envelope): Envelope {
    if (env.gseq === undefined) {
      this.globalSeq += 1;
      env.gseq = this.globalSeq;
      store.setGatewayState(this.db, "global_seq", String(this.globalSeq));
    }
    return env;
  }

  private getResendQueue(adapterId: string): ResendQueue {
    let q = this.resendQueues.get(adapterId);
    if (!q) {
      q = new ResendQueue();
      const rows = store.loadPendingFrames(this.db, adapterId);
      for (const r of rows) {
        try {
          q.push(JSON.parse(r.envelope) as Envelope);
        } catch {
          // 坏数据跳过，不让一行脏数据拖垮恢复
        }
      }
      this.resendQueues.set(adapterId, q);
    }
    return q;
  }

  handleConnection(ws: WebSocket): void {
    let conn: Conn | null = null;
    let firstHandled = false;

    const onFirst = (data: unknown) => {
      if (firstHandled) return;
      firstHandled = true;

      const raw = String(data);
      let env: Envelope;
      try {
        env = parseEnvelope(raw);
      } catch (err) {
        ws.close(4401, (err as Error).message);
        return;
      }
      const errs = validateEnvelope(env);
      if (errs.length > 0) {
        ws.close(4401, errs.join("; "));
        return;
      }
      if (env.type !== "hello") {
        ws.close(4401, "first frame must be hello");
        return;
      }
      const hello = env.payload as HelloPayload;
      if (hello.protocol_version !== PROTOCOL_VERSION_STR) {
        ws.close(4400, "protocol version mismatch");
        return;
      }

      // 设备密钥握手鉴权（第 18 轮）：hello 可选携带 device_id/device_key。
      // 两字段都不出现时沿用既有无鉴权握手；只出现一个时直接拒绝；都出现时查 devices 表比对。
      // 校验发生在顶号之前：鉴权失败绝不顶掉既有连接。
      const deviceId = hello.device_id;
      const deviceKey = hello.device_key;
      if ((deviceId === undefined) !== (deviceKey === undefined)) {
        ws.close(4403, "device auth incomplete");
        return;
      }
      if (deviceId !== undefined && deviceKey !== undefined) {
        const deviceRow = store.getDevice(this.db, deviceId, env.room);
        if (!deviceRow) {
          ws.close(4403, "device not found");
          return;
        }
        if (deviceRow.revoked_at_ms !== null) {
          ws.close(4403, "device revoked");
          return;
        }
        if (deviceRow.adapter_id !== hello.adapter_id) {
          ws.close(4403, "device adapter mismatch");
          return;
        }
        const expectedHash = deviceRow.device_key_hash;
        const actualHash = hashDeviceKey(deviceKey);
        const expectedBuf = Buffer.from(expectedHash, "utf8");
        const actualBuf = Buffer.from(actualHash, "utf8");
        if (expectedBuf.length !== actualBuf.length || !timingSafeEqual(expectedBuf, actualBuf)) {
          ws.close(4403, "device key mismatch");
          return;
        }
        // 鉴权成功：只刷新 last_seen，不轮换密钥（传入既有哈希，upsert 保持原值）。
        store.upsertDevice(this.db, { deviceId, room: env.room, deviceKeyHash: expectedHash, adapterId: hello.adapter_id, nowMs: Date.now() });
      }

      // 顶号
      const existing = this.conns.get(hello.adapter_id);
      if (existing) {
        try {
          const sysEnv = makeEnvelope<MessagePayload>(
            "message",
            "gateway",
            existing.room,
            this.nextSeq(),
            0,
            { msg_id: randomUUID(), text: "replaced by new connection", mentions: [] },
          );
          existing.ws.send(JSON.stringify(sysEnv));
        } catch {
          // ignore
        }
        try {
          existing.ws.close(4402, "replaced");
        } catch {
          // ignore
        }
        this.conns.delete(hello.adapter_id);
        store.upsertPresence(this.db, { adapter_id: hello.adapter_id, status: "offline", last_seen_ms: Date.now(), usage_in: existing.usageIn, usage_out: existing.usageOut, room: existing.room });
        this.broadcastPresence(existing.room, hello.adapter_id, "offline");
      }

      conn = {
        ws,
        adapterId: hello.adapter_id,
        room: env.room,
        deviceId: deviceId,
        lastFrameAtMs: Date.now(),
        maxSeenSeq: 0,
        seqTracker: new SeqTracker(),
        gapLimiter: new GapRateLimiter(),
        capabilities: { intents: ["chat"] },
        capabilityVersion: 0,
        capabilitySkills: [],
        capabilityTags: [],
        usageIn: 0,
        usageOut: 0,
        online: true,
      };
      this.conns.set(hello.adapter_id, conn);
      this.adapterRooms.set(hello.adapter_id, env.room);
      conn.seqTracker.seen(env.sender, env.seq);
      conn.maxSeenSeq = env.seq;

      store.upsertPresence(this.db, { adapter_id: hello.adapter_id, status: "online", last_seen_ms: Date.now(), usage_in: 0, usage_out: 0, room: env.room });
      this.broadcastPresence(env.room, hello.adapter_id, "online", false);

      // last_seen_seq 补发：v1.1 起 last_seen_seq 语义为客户端已见最大 gseq，
      // 取队列中 gseq > last_seen_seq 的全部帧（上界用 MAX_SAFE_INTEGER）。
      // last_seen_seq < 0（-1）：全新实例，只订阅新消息，不重放历史，跳过补发。
      if (hello.last_seen_seq >= 0) {
        const missing = this.getResendQueue(hello.adapter_id).getMissing(hello.last_seen_seq + 1, Number.MAX_SAFE_INTEGER);
        for (const f of missing) {
          try {
            ws.send(JSON.stringify(f));
          } catch {
            // ignore
          }
        }
      }

      ws.off("message", onFirst);
      ws.on("message", (d) => {
        if (conn) this.onFrame(conn, String(d));
      });
      ws.on("close", () => {
        if (!conn) return;
        const cur = this.conns.get(conn.adapterId);
        if (cur === conn) {
          this.conns.delete(conn.adapterId);
          try {
            store.upsertPresence(this.db, { adapter_id: conn.adapterId, status: "offline", last_seen_ms: Date.now(), usage_in: conn.usageIn, usage_out: conn.usageOut, room: conn.room });
          } catch {
            // DB 可能已在关停中关闭；presence 丢失可接受，不抛未捕获异常。
          }
          this.broadcastPresence(conn.room, conn.adapterId, "offline");
        }
      });
      ws.on("error", () => {
        // ignore
      });
    };

    ws.on("message", onFirst);
    ws.on("error", () => {
      // ignore
    });
    ws.on("close", () => {
      // no-op until hello
    });
  }

  private onFrame(conn: Conn, json: string): void {
    let env: Envelope;
    try {
      env = parseEnvelope(json);
    } catch (err) {
      conn.ws.close(4401, (err as Error).message);
      return;
    }
    const errs = validateEnvelope(env);
    if (errs.length > 0) {
      conn.ws.close(4401, errs.join("; "));
      return;
    }

    conn.lastFrameAtMs = Date.now();

    const seen = conn.seqTracker.seen(env.sender, env.seq);
    if (seen === "duplicate" || seen === "stale") return;

    conn.maxSeenSeq = Math.max(conn.maxSeenSeq, env.seq);

    const gap = conn.seqTracker.hasGap(env.sender);
    if (gap) {
      for (const [from, to] of gap.missing) {
        if (conn.gapLimiter.shouldSend(from, to, Date.now())) {
          const gapEnv = makeGap(
            "gateway",
            conn.room,
            this.nextSeq(),
            conn.maxSeenSeq,
            from,
            to,
          );
          this.sendTo(conn.adapterId, gapEnv);
        }
      }
    }

    switch (env.type) {
      case "presence": {
        const p = env.payload as PresencePayload;
        const now = Date.now();
        if (p.usage) {
          conn.usageIn = p.usage.input_tokens;
          conn.usageOut = p.usage.output_tokens;
        }
        store.upsertPresence(this.db, { adapter_id: conn.adapterId, status: p.status, last_seen_ms: now, usage_in: conn.usageIn, usage_out: conn.usageOut, room: conn.room });
        this.broadcastPresence(conn.room, conn.adapterId, p.status);
        break;
      }
      case "gap": {
        const g = env.payload as GapPayload;
        const missing = this.getResendQueue(conn.adapterId).getMissing(g.from_seq, g.to_seq);
        for (const f of missing) {
          try {
            conn.ws.send(JSON.stringify(f));
          } catch {
            // ignore
          }
        }
        break;
      }
      case "capability_update": {
        const c = env.payload as CapabilityUpdatePayload;
        if (c.version > conn.capabilityVersion) {
          conn.capabilities = c.capabilities;
          conn.capabilityVersion = c.version;
          conn.capabilitySkills = c.capabilities.skills ?? [];
          conn.capabilityTags = c.capabilities.tags ?? [];
        }
        break;
      }
      case "message": {
        const m = env.payload as MessagePayload;
        const isRestrictedFrame = env.visibility === "direct" || env.visibility === "restricted";
        if (m.reply_to) {
          const history = store.getRoomHistory(this.db, env.room, 1000);
          const target = findReplyTarget(history, m.reply_to);
          if (!target) {
            const reply = makeEnvelope<MessagePayload>(
              "message",
              "gateway",
              env.room,
              this.nextSeq(),
              0,
              { msg_id: randomUUID(), text: "REPLY_TARGET_NOT_FOUND: reply_to message not found in this room", mentions: [], intent: "chat" },
            );
            this.sendTo(conn.adapterId, reply);
            break;
          }
          m.thread_id = deriveThreadId(m.msg_id, m.reply_to, targetThreadId(target));
        } else {
          m.thread_id = deriveThreadId(m.msg_id);
        }
        if (!isRestrictedFrame) {
          // 安全铁律：direct/restricted 消息只发在线、不落共享历史——
          // GET /api/rooms/:room/history 无请求者身份，落库即向全房间泄漏。
          store.saveMessage(this.db, { room: env.room, sender: env.sender, seq: env.seq, type: "message", payload: JSON.stringify(m), ts: env.ts });
        }
        if (this.onMessage) {
          this.onMessage(env as Envelope<MessagePayload>);
        }
        break;
      }
      case "approval_decision": {
        if (this.onApprovalDecision) {
          this.onApprovalDecision(env as Envelope<ApprovalDecisionPayload>);
        }
        break;
      }
      case "stream": {
        const s = env.payload as StreamPayload;
        this.streamTracker.ingest(env as Envelope<StreamPayload>);
        this.broadcast(conn.room, env, conn.adapterId);
        if (s.final) {
          store.saveMessage(this.db, { room: env.room, sender: env.sender, seq: env.seq, type: "stream", payload: JSON.stringify({ stream_id: s.stream_id }), ts: env.ts });
        }
        break;
      }
      case "game_action": {
        this.handleGameAction(conn, env.payload as GameActionPayload);
        break;
      }
      default:
        break;
    }
  }

  private persistPendingFrame(adapterId: string, env: Envelope): void {
    if (env.type === "presence") return;
    if (env.gseq === undefined) return;
    store.savePendingFrame(this.db, adapterId, env.gseq, JSON.stringify(env));
    store.prunePendingFrames(this.db, adapterId, RESEND_MAX_MSGS);
  }

  sendTo(adapterId: string, env: Envelope): boolean {
    env = this.stampOutbound(env);
    const conn = this.conns.get(adapterId);
    if (!conn) {
      if (env.type !== "presence") {
        this.getResendQueue(adapterId).push(env);
        this.persistPendingFrame(adapterId, env);
      }
      return false;
    }
    if (conn.ws.readyState !== WebSocket.OPEN) {
      if (env.type !== "presence") {
        this.getResendQueue(adapterId).push(env);
        this.persistPendingFrame(adapterId, env);
      }
      return false;
    }
    try {
      conn.ws.send(JSON.stringify(env));
    } catch {
      return false;
    }
    if (env.type !== "presence") {
      this.getResendQueue(adapterId).push(env);
      this.persistPendingFrame(adapterId, env);
    }
    return true;
  }

  /**
   * 向房间广播成员 presence 变化（type=presence，sender 固定为 "gateway"）。
   * 默认排除当事人自己（心跳/下线他自己知道，广播是通知其他成员）；
   * hello 上线时包含自己，作为服务端确认的状态同步。
   */
  broadcastPresence(room: string, adapter_id: string, status: PresenceStatus, excludeSelf = true): void {
    const env = makeEnvelope<PresencePayload>(
      "presence",
      "gateway",
      room,
      0,
      0,
      { adapter_id, status },
    );
    this.broadcast(room, env, excludeSelf ? adapter_id : undefined);
  }

  broadcast(room: string, env: Envelope, excludeAdapterId?: string): void {
    const recipients = visibleRecipients(env.sender, env.visibility, env.visible_to);
    for (const [id, r] of this.adapterRooms) {
      if (r !== room) continue;
      if (excludeAdapterId && id === excludeAdapterId) continue;
      if (recipients !== null && !recipients.has(id)) continue;
      this.sendTo(id, env);
    }
  }

  /** 向房间广播任务状态事件（type=task_event，v1.2）。sender 固定为 "gateway"。 */
  broadcastTaskEvent(room: string, payload: TaskEventPayload): void {
    const env = makeEnvelope<TaskEventPayload>(
      "task_event",
      "gateway",
      room,
      this.nextSeq(),
      0,
      payload,
    );
    this.broadcast(room, env);
  }

  /** 向房间广播反应变更事件（type=reaction_event）。sender 固定为 "gateway"，与 task_event 同款广播语义。 */
  broadcastReactionEvent(room: string, payload: ReactionEventPayload): void {
    const env = makeEnvelope<ReactionEventPayload>(
      "reaction_event",
      "gateway",
      room,
      this.nextSeq(),
      0,
      payload,
    );
    this.broadcast(room, env);
  }

  /** 处理 game_action：校验 → 房间类型游戏清单 → 引擎算局面 → 落库 → 节流广播 game_state。 */
  private handleGameAction(conn: Conn, payload: GameActionPayload): void {
    if (validateGameAction(payload).length > 0) return;
    const room = store.getRoom(this.db, conn.room);
    if (!room) return;
    if (!isGameAllowed(room.type, payload.game)) return;
    const sessions = store.listGameSessions(this.db, conn.room);
    let session = sessions.find((s) => s.game === payload.game);
    if (!session) {
      session = store.createGameSession(this.db, {
        id: randomUUID(),
        room_id: conn.room,
        game: payload.game,
        state: "{}",
      });
    }
    let prevState: unknown = {};
    try {
      prevState = JSON.parse(session.state);
    } catch {
      prevState = {};
    }
    const engine = this.gameEngines.get(payload.game) ?? new PassthroughGameEngine();
    const newState = engine.applyAction(prevState, payload);
    const stateStr = JSON.stringify(newState ?? null);
    store.updateGameSessionState(this.db, session.id, stateStr);
    const stateHash = createHash("sha256").update(stateStr).digest("hex");
    const now = Date.now();
    const key = `${conn.room}:${payload.game}`;
    const last = this.lastGameBroadcastMs.get(key) ?? 0;
    if (now - last < this.gameBroadcastThrottleMs) return;
    this.lastGameBroadcastMs.set(key, now);
    const out: GameStatePayload = {
      game: payload.game,
      seat: payload.seat,
      state: newState ?? null,
      state_hash: stateHash,
    };
    const env = makeEnvelope<GameStatePayload>("game_state", "gateway", conn.room, this.nextSeq(), 0, out);
    this.broadcast(conn.room, env);
  }

  sweep(nowMs: number = Date.now()): void {
    for (const [id, conn] of this.conns) {
      if (nowMs - conn.lastFrameAtMs > OFFLINE_AFTER_MS) {
        store.upsertPresence(this.db, { adapter_id: id, status: "offline", last_seen_ms: nowMs, usage_in: conn.usageIn, usage_out: conn.usageOut, room: conn.room });
        try {
          conn.ws.terminate();
        } catch {
          // ignore
        }
        this.conns.delete(id);
      }
    }
  }

  getOnlineAdapters(room?: string): string[] {
    const out: string[] = [];
    for (const [id, conn] of this.conns) {
      if (room && conn.room !== room) continue;
      out.push(id);
    }
    return out;
  }

  getConn(adapterId: string): Conn | undefined {
    return this.conns.get(adapterId);
  }

  /** 只踢同房间且 deviceId 匹配的连接；legacy 连接（deviceId 为 undefined）绝不被踢；其它房间同名设备绝不被踢。close 回调负责删 conns 与 presence 下线，本方法不直接删 conns、不直接写 presence。 */
  kickDeviceConnections(room: string, deviceId: string): number {
    let kicked = 0;
    for (const conn of [...this.conns.values()]) {
      if (conn.room !== room || conn.deviceId !== deviceId) continue;
      try {
        conn.ws.close(4403, "device revoked");
        kicked += 1;
      } catch {
        /* ignore */
      }
    }
    return kicked;
  }
}

// 自查：红线 1-5 逐条通过
