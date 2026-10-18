// 深测：心跳判离线边界与 usage 落库
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Hub, type Conn } from "../src/hub.js";
import { openDb, getPresence, upsertPresence } from "../src/db.js";
import { HEARTBEAT_MS, OFFLINE_AFTER_MS } from "@botstalk/protocol";

let dir: string;
let db: ReturnType<typeof openDb>;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "presence-usage-deep-"));
  db = openDb(join(dir, "test.db"));
});

afterEach(() => {
  try {
    db.close();
  } catch {
    // 忽略关闭异常
  }
  rmSync(dir, { recursive: true, force: true });
});

/** 构造一个伪造的 Conn 并塞进 hub.conns，terminate 会记录到 terminated 数组 */
function fakeConn(
  hub: Hub,
  id: string,
  opts: {
    room?: string;
    lastFrameAtMs: number;
    usageIn?: number;
    usageOut?: number;
    terminated?: string[];
    terminateThrows?: boolean;
  }
): Conn {
  const terminated = opts.terminated;
  const fake = {
    adapterId: id,
    room: opts.room ?? "r1",
    lastFrameAtMs: opts.lastFrameAtMs,
    usageIn: opts.usageIn ?? 0,
    usageOut: opts.usageOut ?? 0,
    ws: {
      terminate() {
        if (opts.terminateThrows) {
          throw new Error("terminate boom");
        }
        terminated?.push(id);
      },
    },
  } as unknown as Conn;
  hub.conns.set(id, fake);
  return fake;
}

describe("presence/usage 与心跳判离线 深测", () => {
  it("协议常量锁定：HEARTBEAT_MS 为 20000，OFFLINE_AFTER_MS 为 45000", () => {
    expect(HEARTBEAT_MS).toBe(20000);
    expect(OFFLINE_AFTER_MS).toBe(45000);
  });

  it("sweep 边界：恰好等于 OFFLINE_AFTER_MS 时不踢，超过 1ms 才踢", () => {
    const hub = new Hub(db);
    const T = 1_000_000;
    const terminated: string[] = [];
    fakeConn(hub, "a1", { lastFrameAtMs: T, terminated });

    // 差值恰好等于 OFFLINE_AFTER_MS，源码用 > 判断，等于不踢
    hub.sweep(T + OFFLINE_AFTER_MS);
    expect(hub.conns.has("a1")).toBe(true);
    expect(terminated).toEqual([]);

    // 超过 1ms 才被踢
    hub.sweep(T + OFFLINE_AFTER_MS + 1);
    expect(hub.conns.has("a1")).toBe(false);
    expect(terminated).toEqual(["a1"]);
  });

  it("sweep 只踢超时的：a1 超时被删，a2 新鲜保留", () => {
    const hub = new Hub(db);
    const T = 2_000_000;
    const terminated: string[] = [];
    fakeConn(hub, "a1", { lastFrameAtMs: T - 46000, terminated });
    fakeConn(hub, "a2", { lastFrameAtMs: T - 1000, terminated });

    hub.sweep(T);

    expect(hub.conns.has("a1")).toBe(false);
    expect(hub.conns.has("a2")).toBe(true);
    expect(terminated).toEqual(["a1"]);
  });

  it("sweep 写 presence 为 offline，last_seen_ms 为传入的 nowMs", () => {
    const hub = new Hub(db);
    const T = 3_000_000;
    fakeConn(hub, "a1", { lastFrameAtMs: T - 50000 });

    hub.sweep(T);

    const row = getPresence(db, "a1");
    expect(row).toBeDefined();
    expect(row!.adapter_id).toBe("a1");
    expect(row!.status).toBe("offline");
    expect(row!.last_seen_ms).toBe(T);
  });

  it("usage 随 sweep 落库：usageIn=120、usageOut=340 被踢后写透", () => {
    const hub = new Hub(db);
    const T = 4_000_000;
    fakeConn(hub, "a1", {
      lastFrameAtMs: T - 50000,
      usageIn: 120,
      usageOut: 340,
    });

    hub.sweep(T);

    const row = getPresence(db, "a1");
    expect(row).toBeDefined();
    expect(row!.usage_in).toBe(120);
    expect(row!.usage_out).toBe(340);
  });

  it("usage 被 presence 更新覆盖而非累加：100 再 250 最终为 250", () => {
    upsertPresence(db, {
      adapter_id: "a1",
      status: "online",
      last_seen_ms: 1000,
      usage_in: 100,
      usage_out: 100,
    });
    upsertPresence(db, {
      adapter_id: "a1",
      status: "online",
      last_seen_ms: 2000,
      usage_in: 250,
      usage_out: 250,
    });

    const row = getPresence(db, "a1");
    expect(row).toBeDefined();
    expect(row!.usage_in).toBe(250);
    expect(row!.usage_out).toBe(250);
    expect(row!.last_seen_ms).toBe(2000);
  });

  it("sweep 幂等：对已删的连接再 sweep 不抛错，terminate 只调用一次", () => {
    const hub = new Hub(db);
    const T = 5_000_000;
    const terminated: string[] = [];
    fakeConn(hub, "a1", { lastFrameAtMs: T - 50000, terminated });

    hub.sweep(T);
    expect(hub.conns.has("a1")).toBe(false);
    expect(terminated).toEqual(["a1"]);

    expect(() => hub.sweep(T + 1)).not.toThrow();
    expect(hub.conns.has("a1")).toBe(false);
    expect(terminated).toEqual(["a1"]);
  });

  it("getConn/getOnlineAdapters：两连接可见，missing 为 undefined，踢一个后剩一个", () => {
    const hub = new Hub(db);
    const T = 6_000_000;
    fakeConn(hub, "a1", { lastFrameAtMs: T - 50000, room: "r1" });
    fakeConn(hub, "a2", { lastFrameAtMs: T - 1000, room: "r2" });

    const online = hub.getOnlineAdapters();
    expect(online.length).toBe(2);
    expect(online).toContain("a1");
    expect(online).toContain("a2");

    expect(hub.getConn("missing")).toBeUndefined();
    expect(hub.getConn("a1")).toBeDefined();
    expect(hub.getConn("a1")!.adapterId).toBe("a1");

    hub.sweep(T);

    expect(hub.conns.has("a1")).toBe(false);
    expect(hub.conns.has("a2")).toBe(true);
    expect(hub.getOnlineAdapters().length).toBe(1);
    expect(hub.getOnlineAdapters()).toContain("a2");
  });

  it("terminate 抛错不影响 sweep：连接仍被从 conns 删除", () => {
    const hub = new Hub(db);
    const T = 7_000_000;
    fakeConn(hub, "a1", { lastFrameAtMs: T - 50000, terminateThrows: true });

    expect(() => hub.sweep(T)).not.toThrow();
    expect(hub.conns.has("a1")).toBe(false);

    const row = getPresence(db, "a1");
    expect(row).toBeDefined();
    expect(row!.status).toBe("offline");
    expect(row!.last_seen_ms).toBe(T);
  });

  it("多连接混合场景：超时与新晋混合，只有超时者落库为 offline", () => {
    const hub = new Hub(db);
    const T = 8_000_000;
    const terminated: string[] = [];
    fakeConn(hub, "stale1", {
      lastFrameAtMs: T - 50000,
      usageIn: 11,
      usageOut: 22,
      terminated,
    });
    fakeConn(hub, "stale2", {
      lastFrameAtMs: T - 60000,
      usageIn: 33,
      usageOut: 44,
      terminated,
    });
    fakeConn(hub, "fresh", {
      lastFrameAtMs: T - 100,
      usageIn: 55,
      usageOut: 66,
      terminated,
    });

    hub.sweep(T);

    expect(hub.conns.has("stale1")).toBe(false);
    expect(hub.conns.has("stale2")).toBe(false);
    expect(hub.conns.has("fresh")).toBe(true);
    expect(terminated.sort()).toEqual(["stale1", "stale2"]);

    const r1 = getPresence(db, "stale1");
    expect(r1!.status).toBe("offline");
    expect(r1!.usage_in).toBe(11);
    expect(r1!.usage_out).toBe(22);

    const r2 = getPresence(db, "stale2");
    expect(r2!.status).toBe("offline");
    expect(r2!.usage_in).toBe(33);
    expect(r2!.usage_out).toBe(44);

    expect(getPresence(db, "fresh")).toBeUndefined();
  });

  it("sweep 在线上连接会被 offline 覆盖：先 online 再判离线后状态为 offline", () => {
    const hub = new Hub(db);
    const T = 9_000_000;
    fakeConn(hub, "a1", {
      lastFrameAtMs: T - 50000,
      usageIn: 7,
      usageOut: 9,
    });

    // 先写入 online 状态
    upsertPresence(db, {
      adapter_id: "a1",
      status: "online",
      last_seen_ms: T - 100000,
      usage_in: 1,
      usage_out: 2,
    });
    expect(getPresence(db, "a1")!.status).toBe("online");

    hub.sweep(T);

    const row = getPresence(db, "a1");
    expect(row!.status).toBe("offline");
    expect(row!.last_seen_ms).toBe(T);
    expect(row!.usage_in).toBe(7);
    expect(row!.usage_out).toBe(9);
  });

  it("sweep 不修改未被踢连接的 presence：fresh 连接不产生记录", () => {
    const hub = new Hub(db);
    const T = 10_000_000;
    fakeConn(hub, "fresh", { lastFrameAtMs: T - 10, usageIn: 1, usageOut: 2 });

    hub.sweep(T);

    expect(getPresence(db, "fresh")).toBeUndefined();
    expect(hub.conns.has("fresh")).toBe(true);
  });

  it("usage 为零值也正确落库：usageIn=0、usageOut=0 被踢后仍写 0", () => {
    const hub = new Hub(db);
    const T = 11_000_000;
    fakeConn(hub, "a1", { lastFrameAtMs: T - 50000, usageIn: 0, usageOut: 0 });

    hub.sweep(T);

    const row = getPresence(db, "a1");
    expect(row).toBeDefined();
    expect(row!.usage_in).toBe(0);
    expect(row!.usage_out).toBe(0);
    expect(row!.status).toBe("offline");
  });

  it("连续 sweep 多次：已踢连接不重复写 presence，last_seen_ms 保持首次踢除值", () => {
    const hub = new Hub(db);
    const T = 12_000_000;
    fakeConn(hub, "a1", { lastFrameAtMs: T - 50000, usageIn: 5, usageOut: 6 });

    hub.sweep(T);
    const first = getPresence(db, "a1");
    expect(first!.last_seen_ms).toBe(T);

    hub.sweep(T + 1000);
    const second = getPresence(db, "a1");
    expect(second!.last_seen_ms).toBe(T);
    expect(second!.usage_in).toBe(5);
    expect(second!.usage_out).toBe(6);
  });

  it("getOnlineAdapters 按房间过滤：room 参数只返回匹配房间的适配器", () => {
    const hub = new Hub(db);
    const T = 13_000_000;
    fakeConn(hub, "a1", { lastFrameAtMs: T - 100, room: "r1" });
    fakeConn(hub, "a2", { lastFrameAtMs: T - 100, room: "r2" });

    const r1 = hub.getOnlineAdapters("r1");
    expect(r1).toContain("a1");
    expect(r1).not.toContain("a2");

    const all = hub.getOnlineAdapters();
    expect(all.length).toBe(2);
  });
});
