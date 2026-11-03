import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { startServer } from "../src/server.js";
import { openDb, upsertTaskDispatch } from "../src/db.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("GET /api/tasks limit validation", () => {
  let server: ReturnType<typeof startServer>;
  let db: ReturnType<typeof openDb>;
  let base: string;
  let root: string;

  beforeEach(async () => {
    root = mkdtempSync(join(tmpdir(), "botstalk-tasks-limit-"));
    db = openDb(join(root, "dbdir"));
    for (let i = 1; i <= 7; i++) {
      upsertTaskDispatch(db, {
        task_id: `t${i}`,
        room: "lobby",
        owner: "alice",
        assignee: "echo",
        title: `task ${i}`,
        status: "dispatched",
      });
    }
    server = startServer(
      {
        port: 0,
        dataDir: join(root, "dbdir"),
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      },
      db
    );
    const address = server.httpServer.address();
    if (address === null || typeof address === "string") {
      throw new Error("Failed to get server address");
    }
    base = `http://127.0.0.1:${address.port}`;
  });

  afterEach(async () => {
    await server.close();
    rmSync(root, { recursive: true, force: true });
  });

  describe("invalid limit", () => {
    const cases = [
      { query: "?limit=0" },
      { query: "?limit=-1" },
      { query: "?limit=abc" },
      { query: "?limit=1.5" },
      { query: "?limit=10abc" },
      { query: "?limit=" },
      { query: "?limit=5.0" },
    ];

    for (const { query } of cases) {
      it(`returns 400 for ${query}`, async () => {
        const res = await fetch(`${base}/api/tasks${query}`);
        expect(res.status).toBe(400);
        const body = await res.json();
        expect(body).toEqual({ error: "INVALID_TASKS_LIMIT" });
      });
    }
  });

  describe("valid limit", () => {
    const cases = [
      { query: "?limit=5", expected: 5 },
      { query: "?limit=1", expected: 1 },
      { query: "?limit=1000", expected: 7 },
      { query: "", expected: 7 },
      { query: "?limit=200", expected: 7 },
    ];

    for (const { query, expected } of cases) {
      it(`returns ${expected} tasks for ${query || "no query string"}`, async () => {
        const res = await fetch(`${base}/api/tasks${query}`);
        expect(res.status).toBe(200);
        const body = await res.json();
        expect(body.tasks.length).toBe(expected);
      });
    }
  });
});
