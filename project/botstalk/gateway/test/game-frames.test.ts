import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createHash } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { WebSocketServer, WebSocket } from "ws";
import { makeEnvelope, PROTOCOL_VERSION_STR } from "@botstalk/protocol";
import { Hub } from "../src/hub.js";
import { openDb, createRoom, listGameSessions } from "../src/db.js";
import type { Database } from "better-sqlite3";

function sha256Hex(s: string): string {
  return createHash("sha256").update(s).digest("hex");
}

function connectClient(port: number): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}`);
    ws.once("open", () => resolve(ws));
    ws.once("error", reject);
  });
}

function waitFrameWhere(
  ws: WebSocket,
  pred: (e: any) => boolean,
  timeoutMs = 3000,
): Promise<any> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      ws.off("message", onMsg);
      reject(new Error("timeout waiting for frame"));
    }, timeoutMs);
    const onMsg = (raw: WebSocket.RawData) => {
      let e: any;
      try {
        e = JSON.parse(raw.toString());
      } catch {
        return;
      }
      if (pred(e)) {
        clearTimeout(timer);
        ws.off("message", onMsg);
        resolve(e);
      }
    };
    ws.on("message", onMsg);
  });
}

async function expectNoFrame(
  ws: WebSocket,
  pred: (e: any) => boolean,
  timeoutMs = 500,
): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      ws.off("message", onMsg);
      resolve();
    }, timeoutMs);
    const onMsg = (raw: WebSocket.RawData) => {
      let e: any;
      try {
        e = JSON.parse(raw.toString());
      } catch {
        return;
      }
      if (pred(e)) {
        clearTimeout(timer);
        ws.off("message", onMsg);
        reject(new Error("unexpected frame received"));
      }
    };
    ws.on("message", onMsg);
  });
}

function sendHello(ws: WebSocket, adapterId = "player1", room = "play1") {
  ws.send(
    JSON.stringify(
      makeEnvelope("hello", adapterId, room, 1, 0, {
        adapter_id: adapterId,
        protocol_version: PROTOCOL_VERSION_STR,
        last_seen_seq: 0,
      }),
    ),
  );
}

function sendGameAction(
  ws: WebSocket,
  opts: {
    adapterId?: string;
    room?: string;
    seq?: number;
    game?: string;
    seat?: string;
    action?: unknown;
  } = {},
) {
  const {
    adapterId = "player1",
    room = "play1",
    seq = 2,
    game = "who_is_undercover",
    seat = "1",
    action = { vote: "2" },
  } = opts;
  ws.send(
    JSON.stringify(
      makeEnvelope("game_action", adapterId, room, seq, 0, {
        game,
        seat,
        action,
      }),
    ),
  );
}

describe("game frames", () => {
  let dir: string;
  let db: Database;
  let wss: WebSocketServer;
  let hub: Hub;
  let port: number;

  beforeEach(async () => {
    dir = mkdtempSync(join(tmpdir(), "game-frames-"));
    db = openDb(join(dir, "test.db"));
    createRoom(db, { id: "play1", type: "playroom", name: "厅", owner: "u1" });
    wss = new WebSocketServer({ port: 0 });
    await new Promise<void>((resolve) => wss.once("listening", () => resolve()));
    const addr = wss.address();
    if (typeof addr === "object" && addr) port = addr.port;
    else throw new Error("no port");
    hub = new Hub(db, { gameBroadcastThrottleMs: 50 });
    wss.on("connection", (ws) => hub.handleConnection(ws));
  });

  afterEach(async () => {
    await new Promise<void>((resolve) => wss.close(() => resolve()));
    try {
      db.close();
    } catch {
      /* ignore */
    }
    rmSync(dir, { recursive: true, force: true });
  });

  it("broadcasts game_state with correct payload and sha256 hash", async () => {
    const ws = await connectClient(port);
    sendHello(ws);
    await waitFrameWhere(ws, (e) => e.type === "presence");
    const action = { vote: "2" };
    sendGameAction(ws, { action });
    const frame = await waitFrameWhere(ws, (e) => e.type === "game_state");
    expect(frame.payload.game).toBe("who_is_undercover");
    expect(frame.payload.seat).toBe("1");
    expect(frame.payload.state).toEqual(action);
    expect(frame.payload.state_hash).toBe(sha256Hex(JSON.stringify(action)));
    ws.close();
  });

  it("persists game session to db", async () => {
    const ws = await connectClient(port);
    sendHello(ws);
    await waitFrameWhere(ws, (e) => e.type === "presence");
    const action = { vote: "2" };
    sendGameAction(ws, { action });
    await waitFrameWhere(ws, (e) => e.type === "game_state");
    const rows = listGameSessions(db, "play1");
    expect(rows.length).toBe(1);
    expect(rows[0].game).toBe("who_is_undercover");
    expect(JSON.parse(rows[0].state)).toEqual(action);
    ws.close();
  });

  it("throttles rapid game_action frames", async () => {
    const ws = await connectClient(port);
    sendHello(ws);
    await waitFrameWhere(ws, (e) => e.type === "presence");
    sendGameAction(ws, { seq: 2, action: { vote: "2" } });
    sendGameAction(ws, { seq: 3, action: { vote: "3" } });
    const frame = await waitFrameWhere(ws, (e) => e.type === "game_state");
    expect(frame).toBeTruthy();
    await expectNoFrame(ws, (e) => e.type === "game_state", 200);
    ws.close();
  });

  it("ignores game not allowed in playroom", async () => {
    const ws = await connectClient(port);
    sendHello(ws);
    await waitFrameWhere(ws, (e) => e.type === "presence");
    sendGameAction(ws, { game: "poll", action: { x: 1 } });
    await expectNoFrame(ws, (e) => e.type === "game_state", 500);
    ws.close();
  });

  it("ignores invalid payload with empty game", async () => {
    const ws = await connectClient(port);
    sendHello(ws);
    await waitFrameWhere(ws, (e) => e.type === "presence");
    sendGameAction(ws, { game: "", action: { x: 1 } });
    await expectNoFrame(ws, (e) => e.type === "game_state", 500);
    ws.close();
  });

  it("ignores game_action for nonexistent room", async () => {
    const ws = await connectClient(port);
    sendHello(ws, "player1", "nope");
    sendGameAction(ws, { room: "nope", action: { x: 1 } });
    await expectNoFrame(ws, (e) => e.type === "game_state", 500);
    ws.close();
  });

  it("uses custom registered engine", async () => {
    hub.registerGameEngine("who_is_undercover", {
      applyAction: (_prev: unknown, _action: unknown) => ({ merged: true }),
    });
    const ws = await connectClient(port);
    sendHello(ws);
    await waitFrameWhere(ws, (e) => e.type === "presence");
    sendGameAction(ws, { action: { vote: "2" } });
    const frame = await waitFrameWhere(ws, (e) => e.type === "game_state");
    expect(frame.payload.state).toEqual({ merged: true });
    ws.close();
  });
});
