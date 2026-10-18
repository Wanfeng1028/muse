
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, upsertPresence, getPresence, listPresence } from "../src/db.js";
import { startServer } from "../src/server.js";
import type { GatewayConfig } from "../src/config.js";
import type { Envelope } from "@botstalk/protocol";
import type { PresenceStatus } from "@botstalk/protocol";

/**
 * 轻量 FakeHub：逻辑等价于 hub.ts 的 broadcast / broadcastPresence，
 * 但构造不依赖真实 Hub 的复杂依赖。
 */
class FakeHub {
  conns = new Map<string, string>(); // adapter_id -> room
  sent = new Map<string, Envelope[]>(); // adapter_id -> 收到的帧
  private seq = 0;

  private nextSeq(): number {
    this.seq += 1;
    return this.seq;
  }

  addConn(id: string, room: string): void {
    this.conns.set(id, room);
    if (!this.sent.has(id)) this.sent.set(id, []);
  }

  sendTo(id: string, env: Envelope): void {
    if (!this.sent.has(id)) this.sent.set(id, []);
    this.sent.get(id)!.push(env);
  }

  broadcast(room: string, env: Envelope, excludeAdapterId?: string): void {
    for (const [id, r] of this.conns) {
      if (r !== room) continue;
      if (excludeAdapterId && id === excludeAdapterId) continue;
      this.sendTo(id, env);
    }
  }

  broadcastPresence(
    room: string,
    adapter_id: string,
    status: PresenceStatus,
    excludeSelf = true,
  ): void {
    const env: Envelope = {
      type: "presence",
      sender: "gateway",
      room,
      seq: 0,
      ts: 0,
      payload: { adapter_id, status },
    } as unknown as Envelope;
    // 与 hub.ts 一致：先占一个 seq（真实实现里 makeEnvelope 内部走 seq，这里仅模拟）
    this.nextSeq();
    this.broadcast(room, env, excludeSelf ? adapter_id : undefined);
  }
}

const PRESENCE_PAYLOAD = (adapter_id: string, status: PresenceStatus) => ({
  adapter_id,
  status,
});

describe("presence-usage.r2", () => {
  let dir: string;
  let db: ReturnType<typeof openDb>;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "botstalk-r2-"));
    db = openDb(dir);
  });

  afterEach(() => {
    try {
      (db as unknown as { close?: () => void }).close?.();
    } catch {
      /* ignore */
    }
    try {
      rmSync(dir, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
  });

  // 1. broadcastPresence 默认排除自己
  it("1. broadcastPresence 默认 excludeSelf=true：a、b 在线，对 a 广播 online 仅 b 收到", () => {
    const hub = new FakeHub();
    hub.addConn("a", "room1");
    hub.addConn("b", "room1");

    hub.broadcastPresence("room1", "a", "online");

    expect(hub.sent.get("a")!).toEqual([]);
    expect(hub.sent.get("b")!.length).toBe(1);
    expect(hub.sent.get("b")![0].payload).toEqual(PRESENCE_PAYLOAD("a", "online"));
  });

  // 2. excludeSelf=false 时自己也收到（hello 上线状态同步）
  it("2. excludeSelf=false 时自己也收到 presence 帧（hello 上线状态同步）", () => {
    const hub = new FakeHub();
    hub.addConn("a", "room1");
    hub.addConn("b", "room1");

    hub.broadcastPresence("room1", "a", "online", false);

    expect(hub.sent.get("a")!.length).toBe(1);
    expect(hub.sent.get("b")!.length).toBe(1);
    expect(hub.sent.get("a")![0].payload).toEqual(PRESENCE_PAYLOAD("a", "online"));
  });

  // 3. presence 帧结构：type、sender、payload
  it("3. presence 帧：type='presence'、sender='gateway'、payload={adapter_id,status}", () => {
    const hub = new FakeHub();
    hub.addConn("a", "room1");
    hub.addConn("b", "room1");

    hub.broadcastPresence("room1", "a", "offline");

    const env = hub.sent.get("b")![0];
    expect(env.type).toBe("presence");
    expect(env.sender).toBe("gateway");
    expect(env.room).toBe("room1");
    expect(env.payload).toEqual({ adapter_id: "a", status: "offline" });
  });

  // 4. upsertPresence usage 覆盖语义（非累加）
  it("4. upsertPresence usage 覆盖：先 100 再 30 → getPresence 取到 30（非 130）", () => {
    const now = Date.now();
    upsertPresence(db, {
      adapter_id: "a",
      status: "online",
      last_seen_ms: now,
      usage_in: 100,
      usage_out: 200,
    });
    upsertPresence(db, {
      adapter_id: "a",
      status: "online",
      last_seen_ms: now + 1,
      usage_in: 30,
      usage_out: 40,
    });

    const row = getPresence(db, "a");
    expect(row).toBeTruthy();
    expect(row!.usage_in).toBe(30);
    expect(row!.usage_out).toBe(40);
  });

  // 5. status 翻转 + last_seen_ms 取最后一次
  it("5. status online→offline→online：last_seen_ms 为最后一次写入值", () => {
    const t1 = Date.now();
    upsertPresence(db, {
      adapter_id: "a",
      status: "online",
      last_seen_ms: t1,
      usage_in: 1,
      usage_out: 1,
    });
    upsertPresence(db, {
      adapter_id: "a",
      status: "offline",
      last_seen_ms: t1 + 10,
      usage_in: 2,
      usage_out: 2,
    });
    const t3 = t1 + 20;
    upsertPresence(db, {
      adapter_id: "a",
      status: "online",
      last_seen_ms: t3,
      usage_in: 3,
      usage_out: 3,
    });

    const row = getPresence(db, "a");
    expect(row!.status).toBe("online");
    expect(row!.last_seen_ms).toBe(t3);
  });

  // 6. listPresence 全量 + 端点排序
  describe("6. /api/rooms/:room/presence 排序与全量", () => {
    let server: ReturnType<typeof startServer>;
    let port: number;
    let baseDir: string;
    let srvDb: ReturnType<typeof openDb>;

    beforeEach(() => {
      baseDir = mkdtempSync(join(tmpdir(), "botstalk-r2-srv-"));
      const config: GatewayConfig = {
        port: 0,
        dataDir: baseDir,
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      };
      srvDb = openDb(baseDir);
      server = startServer(config, srvDb);
      port = (server.httpServer.address() as { port: number }).port;
    });

    afterEach(async () => {
      await server.close();
      try { (srvDb as unknown as { close?: () => void }).close?.(); } catch { /* ignore */ }
      try {
        rmSync(baseDir, { recursive: true, force: true });
      } catch {
        /* ignore */
      }
    });

    it("6a. 端点返回全量 presence，offline 排在 online 之后", async () => {
      const now = Date.now();
      // 全量写入：两个 room 的 adapter 都进入 listPresence
      upsertPresence(db, {
        adapter_id: "z_online",
        status: "online",
        last_seen_ms: now,
        usage_in: 0,
        usage_out: 0,
      });
      upsertPresence(db, {
        adapter_id: "a_offline",
        status: "offline",
        last_seen_ms: now,
        usage_in: 0,
        usage_out: 0,
      });

      // 该端点使用服务端自己打开的 db（同 dataDir），需要直接访问服务端的数据
      // 这里用另一个独立连接的写法：使用同一 dataDir 打开并写入
      const srvDb = openDb(baseDir);
      upsertPresence(srvDb, {
        adapter_id: "z_online",
        status: "online",
        last_seen_ms: now,
        usage_in: 0,
        usage_out: 0,
      });
      upsertPresence(srvDb, {
        adapter_id: "a_offline",
        status: "offline",
        last_seen_ms: now,
        usage_in: 0,
        usage_out: 0,
      });

      const res = await fetch(`http://127.0.0.1:${port}/api/rooms/room1/presence`);
      expect(res.status).toBe(200);
      const body = (await res.json()) as {
        members: Array<{ adapter_id: string; status: string }>;
      };
      // 语义锁定（DECISIONS 2026-10-18 presence 全局）：presence 是网关全局概念，端点返回全量 listPresence，不按 room 过滤
      expect(body.members.length).toBe(2);
      expect(body.members.map((m) => m.adapter_id)).toEqual(["z_online", "a_offline"]);
      expect(body.members.map((m) => m.status)).toEqual(["online", "offline"]);
    });

    it("6b. 同状态按 adapter_id 字典序升序", async () => {
      const now = Date.now();
      const srvDb = openDb(baseDir);
      upsertPresence(srvDb, {
        adapter_id: "c",
        status: "online",
        last_seen_ms: now,
        usage_in: 0,
        usage_out: 0,
      });
      upsertPresence(srvDb, {
        adapter_id: "a",
        status: "online",
        last_seen_ms: now,
        usage_in: 0,
        usage_out: 0,
      });
      upsertPresence(srvDb, {
        adapter_id: "b",
        status: "offline",
        last_seen_ms: now,
        usage_in: 0,
        usage_out: 0,
      });

      const res = await fetch(`http://127.0.0.1:${port}/api/rooms/anything/presence`);
      expect(res.status).toBe(200);
      const body = (await res.json()) as { members: Array<{ adapter_id: string }> };
      // 语义锁定（DECISIONS 2026-10-18 presence 全局）：presence 是网关全局概念，端点返回全量 listPresence，不按 room 过滤
      expect(body.members.map((m) => m.adapter_id)).toEqual(["a", "c", "b"]);
    });
  });

  // 7. usage 端点 total 累加 + 字段齐全
  describe("7. /api/rooms/:room/usage 累加与字段", () => {
    let server: ReturnType<typeof startServer>;
    let port: number;
    let baseDir: string;
    let srvDb: ReturnType<typeof openDb>;

    beforeEach(() => {
      baseDir = mkdtempSync(join(tmpdir(), "botstalk-r2-usage-"));
      const config: GatewayConfig = {
        port: 0,
        dataDir: baseDir,
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      };
      srvDb = openDb(baseDir);
      server = startServer(config, srvDb);
      port = (server.httpServer.address() as { port: number }).port;
    });

    afterEach(async () => {
      await server.close();
      try { (srvDb as unknown as { close?: () => void }).close?.(); } catch { /* ignore */ }
      try {
        rmSync(baseDir, { recursive: true, force: true });
      } catch {
        /* ignore */
      }
    });

    it("7a. total.input_tokens / total.output_tokens 为各 adapter 之和", async () => {
      const now = Date.now();
      const srvDb = openDb(baseDir);
      upsertPresence(srvDb, {
        adapter_id: "a",
        status: "online",
        last_seen_ms: now,
        usage_in: 10,
        usage_out: 20,
      });
      upsertPresence(srvDb, {
        adapter_id: "b",
        status: "online",
        last_seen_ms: now,
        usage_in: 5,
        usage_out: 7,
      });

      const res = await fetch(`http://127.0.0.1:${port}/api/rooms/room1/usage`);
      expect(res.status).toBe(200);
      const body = (await res.json()) as {
        adapters: Array<{
          adapter_id: string;
          status: string;
          input_tokens: number;
          output_tokens: number;
          last_seen_ms: number;
        }>;
        total: { input_tokens: number; output_tokens: number };
      };
      // 语义锁定（DECISIONS 2026-10-18 presence 全局）：presence 是网关全局概念，端点返回全量 listPresence，不按 room 过滤
      expect(body.adapters.length).toBe(2);
      const map = new Map(body.adapters.map((x) => [x.adapter_id, x]));
      expect(map.get("a")).toMatchObject({
        adapter_id: "a",
        status: "online",
        input_tokens: 10,
        output_tokens: 20,
      });
      expect(map.get("b")).toMatchObject({
        adapter_id: "b",
        status: "online",
        input_tokens: 5,
        output_tokens: 7,
      });
      expect(typeof map.get("a")!.last_seen_ms).toBe("number");
      expect(body.total).toEqual({ input_tokens: 15, output_tokens: 27 });
    });

    it("7b. 单个 adapter 的 usage 更新不影响其他 adapter", async () => {
      const now = Date.now();
      const srvDb = openDb(baseDir);
      upsertPresence(srvDb, {
        adapter_id: "a",
        status: "online",
        last_seen_ms: now,
        usage_in: 1,
        usage_out: 2,
      });
      upsertPresence(srvDb, {
        adapter_id: "b",
        status: "online",
        last_seen_ms: now,
        usage_in: 3,
        usage_out: 4,
      });
      // 只更新 a
      upsertPresence(srvDb, {
        adapter_id: "a",
        status: "online",
        last_seen_ms: now + 1,
        usage_in: 100,
        usage_out: 200,
      });

      const res = await fetch(`http://127.0.0.1:${port}/api/rooms/room1/usage`);
      const body = (await res.json()) as {
        adapters: Array<{
          adapter_id: string;
          input_tokens: number;
          output_tokens: number;
        }>;
        total: { input_tokens: number; output_tokens: number };
      };
      const map = new Map(body.adapters.map((x) => [x.adapter_id, x]));
      expect(map.get("a")!.input_tokens).toBe(100);
      expect(map.get("a")!.output_tokens).toBe(200);
      expect(map.get("b")!.input_tokens).toBe(3);
      expect(map.get("b")!.output_tokens).toBe(4);
      expect(body.total).toEqual({ input_tokens: 103, output_tokens: 204 });
    });
  });

  // 8. presence 端点空库
  it("8. 空库 presence 端点返回 200 且 members 为空数组", async () => {
    const baseDir = mkdtempSync(join(tmpdir(), "botstalk-r2-empty-"));
    const config: GatewayConfig = {
      port: 0,
      dataDir: baseDir,
      roomMaxMembersWorkroom: 50,
      roomMaxMembersPlayroom: 200,
      gameBroadcastThrottleMs: 500,
    };
    const srvDb = openDb(baseDir);
    const server = startServer(config, srvDb);
    const port = (server.httpServer.address() as { port: number }).port;
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/rooms/room1/presence`);
      expect(res.status).toBe(200);
      const body = (await res.json()) as { members: unknown[] };
      expect(body.members).toEqual([]);
    } finally {
      await server.close();
      try { (srvDb as unknown as { close?: () => void }).close?.(); } catch { /* ignore */ }
      try {
        rmSync(baseDir, { recursive: true, force: true });
      } catch {
        /* ignore */
      }
    }
  });

  // 9. 房间隔离
  it("9. broadcastPresence 广播到 room1 时，room2 成员收不到", () => {
    const hub = new FakeHub();
    hub.addConn("a", "room1");
    hub.addConn("b", "room1");
    hub.addConn("c", "room2");
    hub.addConn("d", "room2");

    hub.broadcastPresence("room1", "a", "online");

    expect(hub.sent.get("b")!.length).toBe(1);
    expect(hub.sent.get("c")!).toEqual([]);
    expect(hub.sent.get("d")!).toEqual([]);
  });

  // 10. listPresence 直接返回全量（不按 room）
  it("10. listPresence 返回全量，包含不同 room 写入的 adapter", () => {
    const now = Date.now();
    upsertPresence(db, {
      adapter_id: "a",
      status: "online",
      last_seen_ms: now,
      usage_in: 0,
      usage_out: 0,
    });
    upsertPresence(db, {
      adapter_id: "b",
      status: "offline",
      last_seen_ms: now,
      usage_in: 0,
      usage_out: 0,
    });

    const rows = listPresence(db);
    expect(rows.length).toBe(2);
    const ids = rows.map((r) => r.adapter_id).sort();
    expect(ids).toEqual(["a", "b"]);
    // 字段完整性
    for (const r of rows) {
      expect(typeof r.adapter_id).toBe("string");
      expect(typeof r.status).toBe("string");
      expect(typeof r.last_seen_ms).toBe("number");
      expect(typeof r.usage_in).toBe("number");
      expect(typeof r.usage_out).toBe("number");
    }
  });

  // 11. getPresence 不存在时
  it("11. getPresence 对不存在的 adapter 返回空（falsy）", () => {
    const row = getPresence(db, "no_such_adapter");
    expect(row).toBeFalsy();
  });

  // 12. broadcastPresence 单帧只发一次（不重复发给同一 id）
  it("12. broadcastPresence 对同一成员只发送一帧", () => {
    const hub = new FakeHub();
    hub.addConn("a", "room1");
    hub.addConn("b", "room1");

    hub.broadcastPresence("room1", "a", "online");

    expect(hub.sent.get("b")!.length).toBe(1);
    expect(hub.sent.get("b")![0].payload).toEqual(PRESENCE_PAYLOAD("a", "online"));
  });

  // 13. presence 端点字段齐全
  it("13. presence 端点返回的成员条目包含完整字段", async () => {
    const baseDir = mkdtempSync(join(tmpdir(), "botstalk-r2-fields-"));
    const config: GatewayConfig = {
      port: 0,
      dataDir: baseDir,
      roomMaxMembersWorkroom: 50,
      roomMaxMembersPlayroom: 200,
      gameBroadcastThrottleMs: 500,
    };
    const srvDb = openDb(baseDir);
    const server = startServer(config, srvDb);
    const port = (server.httpServer.address() as { port: number }).port;
    try {
      const now = Date.now();
      upsertPresence(srvDb, {
        adapter_id: "solo",
        status: "online",
        last_seen_ms: now,
        usage_in: 11,
        usage_out: 22,
      });

      const res = await fetch(`http://127.0.0.1:${port}/api/rooms/room1/presence`);
      expect(res.status).toBe(200);
      const body = (await res.json()) as {
        members: Array<{
          adapter_id: string;
          status: string;
          last_seen_ms: number;
          usage_in: number;
          usage_out: number;
        }>;
      };
      expect(body.members.length).toBe(1);
      const m = body.members[0];
      expect(m.adapter_id).toBe("solo");
      expect(m.status).toBe("online");
      expect(m.last_seen_ms).toBe(now);
      expect(m.usage_in).toBe(11);
      expect(m.usage_out).toBe(22);
    } finally {
      await server.close();
      try { (srvDb as unknown as { close?: () => void }).close?.(); } catch { /* ignore */ }
      try {
        rmSync(baseDir, { recursive: true, force: true });
      } catch {
        /* ignore */
      }
    }
  });

  // 14. 连续多次 broadcastPresence 各自独立发送
  it("14. 连续多次 broadcastPresence 每次都独立入队（不合并）", () => {
    const hub = new FakeHub();
    hub.addConn("a", "room1");
    hub.addConn("b", "room1");

    hub.broadcastPresence("room1", "a", "online");
    hub.broadcastPresence("room1", "a", "offline");
    hub.broadcastPresence("room1", "a", "online", false);

    expect(hub.sent.get("b")!.length).toBe(3);
    expect(hub.sent.get("b")!.map((e) => e.payload)).toEqual([
      { adapter_id: "a", status: "online" },
      { adapter_id: "a", status: "offline" },
      { adapter_id: "a", status: "online" },
    ]);
    // excludeSelf=false 那次，a 自己也收到
    expect(hub.sent.get("a")!.length).toBe(1);
    expect(hub.sent.get("a")![0].payload).toEqual({ adapter_id: "a", status: "online" });
  });
});
