import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { startServer } from "../src/server.js";
import { openDb, saveMessage } from "../src/db.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("GET /api/rooms/:room/history before_id validation", () => {
  let db: ReturnType<typeof openDb>;
  let server: Awaited<ReturnType<typeof startServer>>;
  let baseUrl: string;
  let dataDir: string;

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "history-before-id-"));
    db = openDb(join(dataDir, "dbdir"));
    server = await startServer({
      port: 0,
      dataDir: join(dataDir, "dbdir"),
      roomMaxMembersWorkroom: 50,
      roomMaxMembersPlayroom: 200,
      gameBroadcastThrottleMs: 500,
    }, db);
    const addr = server.httpServer.address() as { port: number };
    baseUrl = `http://127.0.0.1:${addr.port}`;
  });

  afterEach(async () => {
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  function seed7() {
    for (let i = 1; i <= 7; i++) saveMessage(db, { room: "lobby", sender: "alice", seq: i, type: "message", payload: JSON.stringify({ n: i }), ts: 1000 + i });
  }

  const invalid: Array<[string, string]> = [
    ["0", "?before_id=0"],
    ["-1", "?before_id=-1"],
    ["abc", "?before_id=abc"],
    ["1.5", "?before_id=1.5"],
    ["10abc", "?before_id=10abc"],
    ["empty", "?before_id="],
    ["5.0", "?before_id=5.0"],
  ];

  for (const [label, qs] of invalid) {
    it(`rejects before_id ${label}`, async () => {
      const res = await fetch(`${baseUrl}/api/rooms/lobby/history${qs}`);
      expect(res.status).toBe(400);
      await expect(res.json()).resolves.toEqual({ error: "INVALID_BEFORE_ID" });
    });
  }

  const valid: Array<[string, string, number, number | null]> = [
    ["before_id=7", "?before_id=7", 6, 7],
    ["before_id=4", "?before_id=4", 3, 4],
    ["before_id=1", "?before_id=1", 0, 1],
    ["default", "", 7, null],
    ["before_id=100", "?before_id=100", 7, 100],
  ];

  for (const [label, qs, expected, beforeId] of valid) {
    it(`accepts ${label} and returns ${expected} messages`, async () => {
      seed7();
      const res = await fetch(`${baseUrl}/api/rooms/lobby/history${qs}`);
      expect(res.status).toBe(200);
      const body = await res.json() as { messages: Array<{ id: number }> };
      expect(body.messages.length).toBe(expected);
      if (beforeId !== null) {
        expect(body.messages.every((m: { id: number }) => m.id < beforeId)).toBe(true);
      }
    });
  }
});
