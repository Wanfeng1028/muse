import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, saveMessage, upsertPresence, type Db } from "../src/db.js";
import { startServer, type RunningServer } from "../src/server.js";

describe("http api", () => {
  let root: string;
  let db: Db;
  let server: RunningServer;
  let base: string;

  beforeEach(async () => {
    root = mkdtempSync(join(tmpdir(), "botstalk-server-"));
    db = openDb(join(root, "dbdir"));
    // port 0 = 随机端口；startServer 内同步 listen
    server = startServer({ port: 0, dataDir: join(root, "dbdir") }, db);
    const addr = server.httpServer.address();
    if (addr === null || typeof addr === "string") throw new Error("no port");
    base = `http://127.0.0.1:${addr.port}`;
  });

  afterEach(async () => {
    await server.close();
    try {
      rmSync(root, { recursive: true, force: true });
    } catch {
      // ignore
    }
  });

  it("returns history sorted ASC with parsed payload", async () => {
    saveMessage(db, {
      room: "lobby",
      sender: "alice",
      seq: 1,
      type: "message",
      payload: JSON.stringify({ text: "first" }),
      ts: 1000,
    });
    saveMessage(db, {
      room: "lobby",
      sender: "bob",
      seq: 2,
      type: "message",
      payload: JSON.stringify({ text: "second" }),
      ts: 2000,
    });

    const res = await fetch(`${base}/api/rooms/lobby/history`);
    expect(res.status).toBe(200);
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
    const body = (await res.json()) as {
      messages: Array<{
        id: number;
        room: string;
        sender: string;
        seq: number;
        type: string;
        payload: unknown;
        ts: number;
      }>;
    };
    expect(body.messages.length).toBe(2);
    expect(body.messages[0].seq).toBe(1);
    expect(body.messages[1].seq).toBe(2);
    expect(body.messages[0].id).toBeLessThan(body.messages[1].id);
    expect(body.messages[0].payload).toEqual({ text: "first" });
    expect(body.messages[1].payload).toEqual({ text: "second" });
    expect(typeof body.messages[0].payload).toBe("object");
  });

  it("history before_id paginates", async () => {
    for (let i = 1; i <= 5; i++) {
      saveMessage(db, {
        room: "lobby",
        sender: "alice",
        seq: i,
        type: "message",
        payload: JSON.stringify({ n: i }),
        ts: 1000 + i,
      });
    }
    const full = (await (await fetch(`${base}/api/rooms/lobby/history?limit=5`)).json()) as {
      messages: Array<{ id: number }>;
    };
    expect(full.messages.length).toBe(5);
    const beforeId = full.messages[2].id;
    const page = (await (
      await fetch(`${base}/api/rooms/lobby/history?limit=5&before_id=${beforeId}`)
    ).json()) as { messages: Array<{ id: number }> };
    expect(page.messages.length).toBe(2);
    expect(page.messages.every((m) => m.id < beforeId)).toBe(true);
  });

  it("presence returns all members with usage", async () => {
    upsertPresence(db, {
      adapter_id: "online-1",
      status: "online",
      last_seen_ms: 5000,
      usage_in: 10,
      usage_out: 20,
    });
    upsertPresence(db, {
      adapter_id: "offline-1",
      status: "offline",
      last_seen_ms: 4000,
      usage_in: 1,
      usage_out: 2,
    });

    const res = await fetch(`${base}/api/rooms/lobby/presence`);
    expect(res.status).toBe(200);
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
    const body = (await res.json()) as {
      members: Array<{
        adapter_id: string;
        status: string;
        last_seen_ms: number;
        usage_in: number;
        usage_out: number;
      }>;
    };
    expect(body.members.length).toBe(2);
    expect(body.members[0].adapter_id).toBe("online-1");
    expect(body.members[0].status).toBe("online");
    expect(body.members[0].last_seen_ms).toBe(5000);
    expect(body.members[0].usage_in).toBe(10);
    expect(body.members[0].usage_out).toBe(20);
    expect(body.members[1].adapter_id).toBe("offline-1");
    expect(body.members[1].status).toBe("offline");
    expect(body.members[1].last_seen_ms).toBe(4000);
    expect(body.members[1].usage_in).toBe(1);
    expect(body.members[1].usage_out).toBe(2);
  });

  it("usage aggregates tokens", async () => {
    upsertPresence(db, {
      adapter_id: "online-1",
      status: "online",
      last_seen_ms: 5000,
      usage_in: 10,
      usage_out: 20,
    });
    upsertPresence(db, {
      adapter_id: "offline-1",
      status: "offline",
      last_seen_ms: 4000,
      usage_in: 1,
      usage_out: 2,
    });

    const res = await fetch(`${base}/api/rooms/lobby/usage`);
    expect(res.status).toBe(200);
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
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
    expect(body.adapters.length).toBe(2);
    expect(body.adapters[0].adapter_id).toBe("online-1");
    expect(body.adapters[0].input_tokens).toBe(10);
    expect(body.adapters[0].output_tokens).toBe(20);
    expect(body.adapters[1].adapter_id).toBe("offline-1");
    expect(body.adapters[1].input_tokens).toBe(1);
    expect(body.adapters[1].output_tokens).toBe(2);
    expect(body.total.input_tokens).toBe(11);
    expect(body.total.output_tokens).toBe(22);
  });
});
