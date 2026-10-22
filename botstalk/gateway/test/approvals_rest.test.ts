import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, type Db } from "../src/db.js";
import { startServer, type RunningServer } from "../src/server.js";
import { getPendingApprovals } from "../src/router.js";
import type { PendingApproval } from "../src/approvals.js";
import type { Envelope, MessagePayload } from "@botstalk/protocol";

describe("approvals REST endpoints", () => {
  let root: string;
  let db: Db;
  let server: RunningServer;
  let base: string;

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), "botstalk-server-"));
    db = openDb(join(root, "dbdir"));
    server = startServer(
      {
        port: 0,
        dataDir: join(root, "dbdir"),
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      },
      db,
    );
    const addr = server.httpServer.address();
    if (addr === null || typeof addr === "string") throw new Error("no port");
    base = `http://127.0.0.1:${addr.port}`;
  });

  afterEach(async () => {
    await server.close();
    rmSync(root, { recursive: true, force: true });
  });

  it("lists pending approvals for the room only", async () => {
    const now = Date.now();
    const env = {
      v: 1,
      type: "message",
      seq: 1,
      ack: 0,
      sender: "req-a",
      room: "room-a",
      ts: now,
      payload: {
        msg_id: "m1",
        text: "do work",
        mentions: ["worker-a"],
        intent: "task",
        task_id: "task-a",
      },
    } as unknown as Envelope<MessagePayload>;

    const roomA: PendingApproval = {
      approval_id: "ap-a",
      task_id: "task-a",
      room: "room-a",
      requester: "req-a",
      assignee: "worker-a",
      title: "Room A job",
      env,
      expires_at_ms: now + 60000,
    };
    const roomB: PendingApproval = {
      approval_id: "ap-b",
      task_id: "task-b",
      room: "room-b",
      requester: "req-b",
      assignee: "worker-b",
      title: "Room B job",
      env,
      expires_at_ms: now + 60000,
    };

    getPendingApprovals().put(roomA);
    getPendingApprovals().put(roomB);

    const res = await fetch(`${base}/api/rooms/room-a/approvals`);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { approvals: Array<Record<string, unknown>> };
    expect(body.approvals).toHaveLength(1);
    expect(body.approvals[0]).toEqual({
      approval_id: "ap-a",
      task_id: "task-a",
      requester: "req-a",
      assignee: "worker-a",
      title: "Room A job",
      expires_at_ms: now + 60000,
    });
    expect(body.approvals[0]).not.toHaveProperty("env");
  });

  it("returns empty array when none pending", async () => {
    const res = await fetch(`${base}/api/rooms/empty-room-zzz/approvals`);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ approvals: [] });
  });

  it("removes entry after take", async () => {
    const now = Date.now();
    const env = {
      v: 1,
      type: "message",
      seq: 2,
      ack: 0,
      sender: "req-c",
      room: "room-c",
      ts: now,
      payload: {
        msg_id: "m-c",
        text: "do work",
        mentions: ["worker-c"],
        intent: "task",
        task_id: "task-c",
      },
    } as unknown as Envelope<MessagePayload>;

    getPendingApprovals().put({
      approval_id: "ap-c",
      task_id: "task-c",
      room: "room-c",
      requester: "req-c",
      assignee: "worker-c",
      title: "Room C job",
      env,
      expires_at_ms: now + 60000,
    });

    getPendingApprovals().take("ap-c");

    const res = await fetch(`${base}/api/rooms/room-c/approvals`);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ approvals: [] });
  });
});