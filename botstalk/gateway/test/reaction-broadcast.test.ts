import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { WebSocket } from "ws";
import { openDb, saveMessage } from "../src/db.js";
import { startServer } from "../src/server.js";
import { makeEnvelope, PROTOCOL_VERSION_STR, validateEnvelope } from "@botstalk/protocol";

describe("reaction-broadcast", () => {
  let dataDir: string;
  let db: any;
  let messageId: number;
  let server: any;
  let baseUrl: string;
  let wsUrl: string;
  const sockets: WebSocket[] = [];

  function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function openSocket(url: string): Promise<WebSocket> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      ws.once("open", () => resolve(ws));
      ws.once("error", reject);
    });
  }

  function collectFrames(ws: WebSocket): unknown[] {
    const frames: unknown[] = [];
    ws.on("message", (data) => {
      try {
        frames.push(JSON.parse(data.toString()));
      } catch {
        // ignore unparseable frames
      }
    });
    return frames;
  }

  async function waitFor<T>(fn: () => T | undefined, timeoutMs = 3000): Promise<T> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const result = fn();
      if (result !== undefined) return result;
      await sleep(20);
    }
    throw new Error("timeout waiting for condition");
  }

  async function connectMember(adapterId: string): Promise<{ ws: WebSocket; frames: unknown[] }> {
    const ws = await openSocket(wsUrl);
    const frames = collectFrames(ws);
    const hello = makeEnvelope(
      "hello",
      adapterId,
      "room1",
      1,
      0,
      { adapter_id: adapterId, protocol_version: PROTOCOL_VERSION_STR, last_seen_seq: 0 }
    );
    ws.send(JSON.stringify(hello));
    sockets.push(ws);
    return { ws, frames };
  }

  async function api(
    path: string,
    method: string,
    body?: unknown
  ): Promise<{ status: number; body: any }> {
    const res = await fetch(baseUrl + path, {
      method,
      headers: body !== undefined ? { "content-type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return { status: res.status, body: await res.json() };
  }

  function findReactionEvent(frames: unknown[], action: string): any {
    return frames.find(
      (f) =>
        f && typeof f === "object" && (f as any).type === "reaction_event" && (f as any).payload?.action === action
    );
  }

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "reaction-broadcast-test-"));
    db = await openDb(join(dataDir, "dbdir"));
    messageId = saveMessage(db, {
      room: "room1",
      sender: "alice",
      seq: 1,
      type: "message",
      payload: JSON.stringify({ text: "hello" }),
      ts: Date.now(),
    });
    server = await startServer(
      {
        port: 0,
        dataDir: join(dataDir, "dbdir"),
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      },
      db
    );
    const address = server.httpServer.address();
    const port = typeof address === "object" && address !== null ? address.port : 0;
    baseUrl = `http://127.0.0.1:${port}`;
    wsUrl = `ws://127.0.0.1:${port}`;
  });

  afterEach(async () => {
    // 先关客户端 socket 再关 server：wss.close() 会等全部客户端断开才回调，
    // 若先调 server.close() 将与未关闭的客户端死锁（实测挂起）。
    const closePromises = sockets.map(
      (ws) =>
        new Promise<void>((resolve) => {
          if (ws.readyState === WebSocket.CLOSED) {
            resolve();
            return;
          }
          let settled = false;
          const done = () => {
            if (!settled) {
              settled = true;
              resolve();
            }
          };
          ws.once("close", done);
          setTimeout(done, 1000);
          try {
            ws.close();
          } catch {
            done();
          }
        })
    );
    await Promise.all(closePromises);
    sockets.length = 0;
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  it("POST add broadcasts reaction_event to another room member", async () => {
    const bob = await connectMember("bob");
    const carol = await connectMember("carol");
    await sleep(200);

    const res = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", {
      reaction: "heart",
      requester: "bob",
    });
    expect(res.status, "POST add reaction should return 200").toBe(200);

    const frame = await waitFor(() => findReactionEvent(carol.frames, "add"));
    expect(frame, "carol should receive a reaction_event with action add").toBeTruthy();
    expect(frame.type).toBe("reaction_event");
    expect(frame.sender).toBe("gateway");
    expect(frame.payload.message_id).toBe(messageId);
    expect(frame.payload.reaction).toBe("heart");
    expect(frame.payload.reactor).toBe("bob");
    expect(frame.payload.action).toBe("add");
    expect(frame.payload.added).toBe(true);
    expect(validateEnvelope(frame), "reaction_event frame should pass protocol validation").toEqual([]);
  });

  it("DELETE remove broadcasts reaction_event with action remove", async () => {
    const bob = await connectMember("bob");
    const carol = await connectMember("carol");
    await sleep(200);

    const addRes = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", {
      reaction: "heart",
      requester: "bob",
    });
    expect(addRes.status, "POST add reaction should return 200").toBe(200);

    const delRes = await api(
      `/api/rooms/room1/messages/${messageId}/reactions?reaction=heart&requester=bob`,
      "DELETE"
    );
    expect(delRes.status, "DELETE reaction should return 200").toBe(200);
    expect(delRes.body.removed, "DELETE response should report removed=true").toBe(true);

    const frame = await waitFor(() => findReactionEvent(carol.frames, "remove"));
    expect(frame, "carol should receive a reaction_event with action remove").toBeTruthy();
    expect(frame.payload.action).toBe("remove");
    expect(frame.payload.removed).toBe(true);
    expect(frame.payload.reaction).toBe("heart");
    expect(frame.payload.reactor).toBe("bob");
  });

  it("duplicate add broadcasts nothing", async () => {
    const bob = await connectMember("bob");
    const carol = await connectMember("carol");
    await sleep(200);

    const first = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", {
      reaction: "heart",
      requester: "bob",
    });
    expect(first.status, "first POST add should return 200").toBe(200);
    const second = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", {
      reaction: "heart",
      requester: "bob",
    });
    expect(second.status, "duplicate POST add should still return 200").toBe(200);
    expect(second.body.added, "duplicate add should report added=false").toBe(false);

    carol.frames.length = 0;
    await sleep(300);

    const reactionFrames = carol.frames.filter(
      (f) => f && typeof f === "object" && (f as any).type === "reaction_event"
    );
    expect(reactionFrames, "no reaction_event frames should be broadcast for duplicate add").toEqual([]);
  });

  it("a disconnected member does not break broadcast to others（失败注入）", async () => {
    const dave = await connectMember("dave");
    const erin = await connectMember("erin");
    await sleep(200);

    const daveClosed = new Promise<void>((resolve) => {
      let settled = false;
      const done = () => {
        if (!settled) {
          settled = true;
          resolve();
        }
      };
      dave.ws.once("close", done);
      dave.ws.close();
      setTimeout(done, 1000);
    });
    await daveClosed;

    const res = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "POST", {
      reaction: "heart",
      requester: "bob",
    });
    expect(res.status, "POST add reaction should return 200 even after a member disconnects").toBe(200);

    const frame = await waitFor(() => findReactionEvent(erin.frames, "add"));
    expect(frame, "erin should still receive the reaction_event broadcast").toBeTruthy();

    const getRes = await api(`/api/rooms/room1/messages/${messageId}/reactions`, "GET");
    expect(getRes.status, "gateway should still answer GET reactions after disconnect failure").toBe(200);
  });
});
