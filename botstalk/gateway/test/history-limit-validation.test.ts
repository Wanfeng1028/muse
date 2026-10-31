import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { startServer } from "../src/server.js";
import { openDb, saveMessage } from "../src/db.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("GET /api/rooms/:room/history limit validation", () => {
  let db: ReturnType<typeof openDb>;
  let server: Awaited<ReturnType<typeof startServer>>;
  let baseUrl: string;
  let dataDir: string;

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "history-limit-"));
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
    ["0", "?limit=0"],
    ["-1", "?limit=-1"],
    ["abc", "?limit=abc"],
    ["1.5", "?limit=1.5"],
    ["10abc", "?limit=10abc"],
    ["empty", "?limit="],
    ["5.0", "?limit=5.0"],
  ];

  for (const [label, qs] of invalid) {
    it(`rejects limit ${label}`, async () => {
      const res = await fetch(`${baseUrl}/api/rooms/lobby/history${qs}`);
      expect(res.status).toBe(400);
      await expect(res.json()).resolves.toEqual({ error: "INVALID_HISTORY_LIMIT" });
    });
  }

  const valid: Array<[string, string, number]> = [
    ["limit=5", "?limit=5", 5],
    ["limit=1", "?limit=1", 1],
    ["limit=1000", "?limit=1000", 7],
    ["default", "", 7],
    ["limit=200", "?limit=200", 7],
  ];

  for (const [label, qs, expected] of valid) {
    it(`accepts ${label} and returns ${expected} messages`, async () => {
      seed7();
      const res = await fetch(`${baseUrl}/api/rooms/lobby/history${qs}`);
      expect(res.status).toBe(200);
      const body = await res.json() as { messages: Array<{ id: number }> };
      expect(body.messages.length).toBe(expected);
    });
  }
});
