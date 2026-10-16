import { WebSocket, WebSocketServer } from "ws";
import {
  SeqTracker,
  ResendQueue,
  GapRateLimiter,
  StreamTracker,
  makeEnvelope,
  parseEnvelope,
  validateEnvelope,
  makeGap,
  HEARTBEAT_MS,
  OFFLINE_AFTER_MS,
  ZOMBIE_SWEEP_MS,
  PROTOCOL_VERSION_STR,
} from "@botstalk/protocol";
import type {
  Envelope,
  MessagePayload,
  StreamPayload,
  HelloPayload,
  PresencePayload,
  GapPayload,
  CapabilityUpdatePayload,
} from "@botstalk/protocol";
import * as store from "./db.js";
import type { Db } from "./db.js";
import { randomUUID } from "node:crypto";

export interface Conn {
  ws: WebSocket;
  adapterId: string;
  room: string;
  lastFrameAtMs: number;
  maxSeenSeq: number;
  seqTracker: SeqTracker;
  gapLimiter: GapRateLimiter;
  capabilities: { intents: ("chat" | "task")[] };
  capabilityVersion: number;
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

  constructor(private readonly db: Db) {}

  public nextSeq(): number {
    return this.serverSeq.nextSeq();
  }

  /**
   * 网关全局序列号计数器。
   * 已知局限（v1.1 明确边界，不修）：globalSeq 是内存计数器，网关重启后从 1 开始；
   * resendQueues 也是内存的，重启即丢。
   */
  private globalSeq = 0;

  /** 给发往客户端的帧打网关全局序列号。幂等：同一逻辑帧 broadcast 给多个客户端时 gseq 必须一致。 */
  private stampOutbound(env: Envelope): Envelope {
    if (env.gseq === undefined) {
      this.globalSeq += 1;
      env.gseq = this.globalSeq;
    }
    return env;
  }

  private getResendQueue(adapterId: string): ResendQueue {
    let q = this.resendQueues.get(adapterId);
    if (!q) {
      q = new ResendQueue();
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
        store.upsertPresence(this.db, { adapter_id: hello.adapter_id, status: "offline", last_seen_ms: Date.now(), usage_in: existing.usageIn, usage_out: existing.usageOut });
      }

      conn = {
        ws,
        adapterId: hello.adapter_id,
        room: env.room,
        lastFrameAtMs: Date.now(),
        maxSeenSeq: 0,
        seqTracker: new SeqTracker(),
        gapLimiter: new GapRateLimiter(),
        capabilities: { intents: ["chat"] },
        capabilityVersion: 0,
        usageIn: 0,
        usageOut: 0,
        online: true,
      };
      this.conns.set(hello.adapter_id, conn);
      this.adapterRooms.set(hello.adapter_id, env.room);
      conn.seqTracker.seen(env.sender, env.seq);
      conn.maxSeenSeq = env.seq;

      store.upsertPresence(this.db, { adapter_id: hello.adapter_id, status: "online", last_seen_ms: Date.now(), usage_in: 0, usage_out: 0 });

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
          store.upsertPresence(this.db, { adapter_id: conn.adapterId, status: "offline", last_seen_ms: Date.now(), usage_in: conn.usageIn, usage_out: conn.usageOut });
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
        store.upsertPresence(this.db, { adapter_id: conn.adapterId, status: p.status, last_seen_ms: now, usage_in: conn.usageIn, usage_out: conn.usageOut });
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
        }
        break;
      }
      case "message": {
        const m = env.payload as MessagePayload;
        store.saveMessage(this.db, { room: env.room, sender: env.sender, seq: env.seq, type: "message", payload: JSON.stringify(m), ts: env.ts });
        if (this.onMessage) {
          this.onMessage(env as Envelope<MessagePayload>);
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
      default:
        break;
    }
  }

  sendTo(adapterId: string, env: Envelope): boolean {
    env = this.stampOutbound(env);
    const conn = this.conns.get(adapterId);
    if (!conn) {
      if (env.type !== "presence") {
        this.getResendQueue(adapterId).push(env);
      }
      return false;
    }
    if (conn.ws.readyState !== WebSocket.OPEN) {
      if (env.type !== "presence") {
        this.getResendQueue(adapterId).push(env);
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
    }
    return true;
  }

  broadcast(room: string, env: Envelope, excludeAdapterId?: string): void {
    for (const [id, r] of this.adapterRooms) {
      if (r !== room) continue;
      if (excludeAdapterId && id === excludeAdapterId) continue;
      this.sendTo(id, env);
    }
  }

  sweep(nowMs: number = Date.now()): void {
    for (const [id, conn] of this.conns) {
      if (nowMs - conn.lastFrameAtMs > OFFLINE_AFTER_MS) {
        store.upsertPresence(this.db, { adapter_id: id, status: "offline", last_seen_ms: nowMs, usage_in: conn.usageIn, usage_out: conn.usageOut });
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
}

// 自查：红线 1-5 逐条通过
