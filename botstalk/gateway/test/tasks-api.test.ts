import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, saveMessage, upsertTaskDispatch, type Db } from "../src/db.js";
import { startServer, type RunningServer } from "../src/server.js";

describe("tasks http api", () => {
  let root: string;
  let db: Db;
  let server: RunningServer;
  let base: string;

  beforeEach(async () => {
    root = mkdtempSync(join(tmpdir(), "botstalk-tasks-api-"));
    db = openDb(join(root, "dbdir"));
    upsertTaskDispatch(db, { task_id: "t1", room: "lobby", owner: "alice", assignee: "echo", title: "写日报", status: "dispatched" });
    upsertTaskDispatch(db, { task_id: "t2", room: "lobby", owner: "alice", assignee: "echo", title: "查资料", status: "running" });
    upsertTaskDispatch(db, { task_id: "t3", room: "other", owner: "bob", assignee: null, title: "无", status: "unsupported" });
    saveMessage(db, { room: "lobby", sender: "alice", seq: 1, type: "text", payload: JSON.stringify({ text: "m1" }), ts: 1 });
    saveMessage(db, { room: "lobby", sender: "alice", seq: 2, type: "text", payload: JSON.stringify({ text: "m2" }), ts: 2 });
    saveMessage(db, { room: "lobby", sender: "alice", seq: 3, type: "text", payload: JSON.stringify({ text: "m3" }), ts: 3 });
    server = startServer({ port: 0, dataDir: join(root, "dbdir") }, db);
    const addr = server.httpServer.address();
    if (addr === null || typeof addr === "string") throw new Error("no port");
    base = `http://127.0.0.1:${addr.port}`;
  });

  afterEach(async () => {
    await server.close();
    try { rmSync(root, { recursive: true, force: true }); } catch { /* ignore */ }
  });

  it("GET /api/tasks returns 3 tasks", async () => {
    const res = await fetch(`${base}/api/tasks`);
    expect(res.status).toBe(200);
    const body = await res.json() as { tasks: Array<{ task_id: string }> };
    expect(body.tasks).toHaveLength(3);
    const ids = body.tasks.map((t) => t.task_id).sort();
    expect(ids).toEqual(["t1", "t2", "t3"]);
  });

  it("GET /api/tasks?room=lobby returns 2 lobby tasks", async () => {
    const res = await fetch(`${base}/api/tasks?room=lobby`);
    expect(res.status).toBe(200);
    const body = await res.json() as { tasks: Array<{ task_id: string; room: string }> };
    expect(body.tasks).toHaveLength(2);
    for (const t of body.tasks) expect(t.room).toBe("lobby");
  });

  it("GET /api/tasks?room=lobby&status=running returns t2", async () => {
    const res = await fetch(`${base}/api/tasks?room=lobby&status=running`);
    expect(res.status).toBe(200);
    const body = await res.json() as { tasks: Array<{ task_id: string }> };
    expect(body.tasks).toHaveLength(1);
    expect(body.tasks[0]!.task_id).toBe("t2");
  });

  it("GET /api/tasks?status=bogus returns 400", async () => {
    const res = await fetch(`${base}/api/tasks?status=bogus`);
    expect(res.status).toBe(400);
    const body = await res.json() as { error: string };
    expect(typeof body.error).toBe("string");
  });

  it("GET /api/tasks/t1 returns the task", async () => {
    const res = await fetch(`${base}/api/tasks/t1`);
    expect(res.status).toBe(200);
    const body = await res.json() as { task: { task_id: string; title: string; assignee: string | null } };
    expect(body.task.task_id).toBe("t1");
    expect(body.task.title).toBe("写日报");
    expect(body.task.assignee).toBe("echo");
  });

  it("GET /api/tasks/nope returns 404", async () => {
    const res = await fetch(`${base}/api/tasks/nope`);
    expect(res.status).toBe(404);
  });

  it("GET /api/tasks/stats?room=lobby returns counts", async () => {
    const res = await fetch(`${base}/api/tasks/stats?room=lobby`);
    expect(res.status).toBe(200);
    const body = await res.json() as { counts: Record<string, number>; total: number };
    expect(body.counts.dispatched).toBe(1);
    expect(body.counts.running).toBe(1);
    expect(body.total).toBe(2);
  });

  it("GET /api/tasks/stats without room returns total=3", async () => {
    const res = await fetch(`${base}/api/tasks/stats`);
    expect(res.status).toBe(200);
    const body = await res.json() as { total: number };
    expect(body.total).toBe(3);
  });

  it("POST /api/tasks/t1/cancel by non-owner returns 403 and does not change status", async () => {
    const res = await fetch(`${base}/api/tasks/t1/cancel`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ requester: "mallory" }),
    });
    expect(res.status).toBe(403);
    const check = await fetch(`${base}/api/tasks/t1`);
    const body = await check.json() as { task: { status: string } };
    expect(body.task.status).toBe("dispatched");
  });

  it("POST /api/tasks/t1/cancel without requester returns 400", async () => {
    const res = await fetch(`${base}/api/tasks/t1/cancel`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(res.status).toBe(400);
  });

  it("POST /api/tasks/nope/cancel returns 404", async () => {
    const res = await fetch(`${base}/api/tasks/nope/cancel`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ requester: "alice" }),
    });
    expect(res.status).toBe(404);
  });

  it("POST /api/tasks/t1/cancel by owner succeeds then conflicts", async () => {
    const res = await fetch(`${base}/api/tasks/t1/cancel`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ requester: "alice" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json() as { task: { task_id: string; status: string } };
    expect(body.task.task_id).toBe("t1");
    expect(body.task.status).toBe("cancelled");

    const again = await fetch(`${base}/api/tasks/t1/cancel`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ requester: "alice" }),
    });
    expect(again.status).toBe(409);
  });

  it("POST /api/tasks/t3/cancel on unsupported returns 409", async () => {
    const res = await fetch(`${base}/api/tasks/t3/cancel`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ requester: "bob" }),
    });
    expect(res.status).toBe(409);
  });

  it("GET /api/rooms/lobby/unread returns unread=3 latest_id=3", async () => {
    const res = await fetch(`${base}/api/rooms/lobby/unread`);
    expect(res.status).toBe(200);
    const body = await res.json() as { unread: number; latest_id: number | null };
    expect(body.unread).toBe(3);
    expect(body.latest_id).toBe(3);
  });

  it("GET /api/rooms/lobby/unread?since_id=2 returns unread=1 latest_id=3", async () => {
    const res = await fetch(`${base}/api/rooms/lobby/unread?since_id=2`);
    expect(res.status).toBe(200);
    const body = await res.json() as { unread: number; latest_id: number | null };
    expect(body.unread).toBe(1);
    expect(body.latest_id).toBe(3);
  });

  it("GET /api/rooms/lobby/unread?since_id=3 returns unread=0", async () => {
    const res = await fetch(`${base}/api/rooms/lobby/unread?since_id=3`);
    expect(res.status).toBe(200);
    const body = await res.json() as { unread: number };
    expect(body.unread).toBe(0);
  });

  it("GET /api/tasks sets access-control-allow-origin to *", async () => {
    const res = await fetch(`${base}/api/tasks`);
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
  });
});
