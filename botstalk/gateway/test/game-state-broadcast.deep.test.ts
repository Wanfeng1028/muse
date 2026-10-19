import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { WebSocketServer, WebSocket } from "ws";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { makeEnvelope, PROTOCOL_VERSION_STR } from "@botstalk/protocol";
import type {
  Envelope,
  HelloPayload,
  GameActionPayload,
  GameStatePayload,
} from "@botstalk/protocol";
import { Hub } from "../src/hub.js";
import { openDb, createRoom } from "../src/db.js";
import type { Db } from "../src/db.js";

let tmpDir: string;
let db: Db;
let wss: WebSocketServer;
let port: number;
let hub: Hub;

beforeEach(async () => {
  tmpDir = mkdtempSync(join(tmpdir(), "botstalk-gamestate-"));
  db = openDb(tmpDir);
  wss = new WebSocketServer({ port: 0 });
  await new Promise<void>((res) => wss.once("listening", () => res()));
  const addr = wss.address();
  port = typeof addr === "object" && addr ? addr.port : 0;
  hub = new Hub(db, { gameBroadcastThrottleMs: 0 });
  wss.on("connection", (ws) => hub.handleConnection(ws));
});

const clients: WebSocket[] = [];

afterEach(async () => {
  for (const c of clients.splice(0)) {
    try {
      c.terminate();
    } catch {
      /* ignore */
    }
  }
  await new Promise<void>((res) => wss.close(() => res()));
  rmSync(tmpDir, { recursive: true, force: true });
});

function connectClient(): Promise<WebSocket> {
  return new Promise((res, rej) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}`);
    ws.once("open", () => {
      clients.push(ws);
      res(ws);
    });
    ws.once("error", rej);
  });
}

function sendHello(ws: WebSocket, adapterId: string, room: string): void {
  const env = makeEnvelope<HelloPayload>(
    "hello",
    adapterId,
    room,
    1,
    0,
    {
      adapter_id: adapterId,
      protocol_version: PROTOCOL_VERSION_STR,
      last_seen_seq: -1,
    },
  );
  ws.send(JSON.stringify(env));
}

 // hello 已占用每连接 seq=1，action 从 2 开始避免被服务端判 duplicate 丢弃
let gameActionSeq = 1;

function sendGameAction(
  ws: WebSocket,
  adapterId: string,
  room: string,
  payload: GameActionPayload,
): void {
  gameActionSeq += 1;
  const env = makeEnvelope<GameActionPayload>(
    "game_action",
    adapterId,
    room,
    gameActionSeq,
    0,
    payload,
  );
  ws.send(JSON.stringify(env));
}

async function waitFor<T>(
  fn: () => T | undefined | Promise<T | undefined>,
  timeoutMs = 3000,
  intervalMs = 20,
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const v = await fn();
    if (v !== undefined) return v;
    if (Date.now() > deadline) throw new Error("waitFor timeout");
    await new Promise<void>((res) => setTimeout(res, intervalMs));
  }
}

function collectFrames(ws: WebSocket): { frames: Envelope[]; stop: () => void } {
  const frames: Envelope[] = [];
  const onMsg = (d: unknown) => frames.push(JSON.parse(String(d)) as Envelope);
  ws.on("message", onMsg);
  return {
    frames,
    stop: () => ws.off("message", onMsg),
  };
}

function sha256Hex(input: string): string {
  return createHash("sha256").update(input).digest("hex");
}

describe("game_state broadcast deep", () => {
  it("broadcasts game_state for a valid werewolf game_action in a playroom", async () => {
    createRoom(db, { id: "r1", type: "playroom" });
    const ws = await connectClient();
    sendHello(ws, "player-1", "r1");
    await waitFor(() => hub.getConn("player-1"));

    const { frames, stop } = collectFrames(ws);
    sendGameAction(ws, "player-1", "r1", {
      game: "werewolf",
      seat: "1",
      action: { vote: "2" },
    });

    const gsFrame = await waitFor(() =>
      frames.find((f) => f.type === "game_state"),
    );
    stop();

    const p = gsFrame.payload as GameStatePayload;
    expect(p.game).toBe("werewolf");
    expect(p.seat).toBe("1");
    expect(p.state).toEqual({ vote: "2" });
    expect(typeof p.state_hash).toBe("string");
  });

  it("computes state_hash as sha256 hex of JSON.stringify(state)", async () => {
    createRoom(db, { id: "r2", type: "playroom" });
    const ws = await connectClient();
    sendHello(ws, "player-2", "r2");
    await waitFor(() => hub.getConn("player-2"));

    const { frames, stop } = collectFrames(ws);
    sendGameAction(ws, "player-2", "r2", {
      game: "werewolf",
      seat: "2",
      action: { vote: "1", note: "x" },
    });

    const gsFrame = await waitFor(() =>
      frames.find((f) => f.type === "game_state"),
    );
    stop();

    const p = gsFrame.payload as GameStatePayload;
    const expected = sha256Hex(JSON.stringify(p.state));
    expect(p.state_hash).toBe(expected);
  });

  it("stamps game_state frames with strictly increasing gseq across two actions", async () => {
    createRoom(db, { id: "r3", type: "playroom" });
    const ws = await connectClient();
    sendHello(ws, "player-3", "r3");
    await waitFor(() => hub.getConn("player-3"));

    const { frames, stop } = collectFrames(ws);
    sendGameAction(ws, "player-3", "r3", {
      game: "werewolf",
      seat: "1",
      action: { a: 1 },
    });

    const first = await waitFor(() => frames.find((f) => f.type === "game_state"));
    expect(typeof first.gseq).toBe("number");
    const gseq1 = first.gseq as number;

    sendGameAction(ws, "player-3", "r3", {
      game: "werewolf",
      seat: "1",
      action: { a: 2 },
    });

    const second = await waitFor(() =>
      frames.filter((f) => f.type === "game_state").find((f) => f !== first),
    );
    stop();

    expect(typeof second.gseq).toBe("number");
    expect(second.gseq as number).toBeGreaterThan(gseq1);
  });

  it("does not broadcast game_state for an invalid game_action with empty game", async () => {
    createRoom(db, { id: "r4", type: "playroom" });
    const ws = await connectClient();
    sendHello(ws, "player-4", "r4");
    await waitFor(() => hub.getConn("player-4"));

    const { frames, stop } = collectFrames(ws);
    sendGameAction(ws, "player-4", "r4", {
      game: "",
      seat: "1",
      action: { vote: "2" },
    });

    await new Promise<void>((res) => setTimeout(res, 300));
    stop();

    expect(frames.find((f) => f.type === "game_state")).toBeUndefined();
  });

  it("does not broadcast game_state when room type disallows the game", async () => {
    createRoom(db, { id: "r5", type: "workroom" });
    const ws = await connectClient();
    sendHello(ws, "player-5", "r5");
    await waitFor(() => hub.getConn("player-5"));

    const { frames, stop } = collectFrames(ws);
    sendGameAction(ws, "player-5", "r5", {
      game: "werewolf",
      seat: "1",
      action: { vote: "2" },
    });

    await new Promise<void>((res) => setTimeout(res, 300));
    stop();

    expect(frames.find((f) => f.type === "game_state")).toBeUndefined();
  });
});
