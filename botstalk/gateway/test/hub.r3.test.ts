import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { WebSocketServer, WebSocket } from "ws";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { makeEnvelope, PROTOCOL_VERSION_STR } from "@botstalk/protocol";
import type { Envelope, HelloPayload } from "@botstalk/protocol";
import { Hub } from "../src/hub.js";
import { openDb } from "../src/db.js";

let tmpDir: string; let db: ReturnType<typeof openDb>; let wss: WebSocketServer; let port: number; let hub: Hub;
beforeEach(async () => {
  tmpDir = mkdtempSync(join(tmpdir(), "botstalk-hubr3-"));
  db = openDb(tmpDir);
  wss = new WebSocketServer({ port: 0 });
  await new Promise<void>((res) => wss.once("listening", () => res()));
  const addr = wss.address(); port = typeof addr === "object" && addr ? addr.port : 0;
  hub = new Hub(db);
  wss.on("connection", (ws) => hub.handleConnection(ws));
});
const clients: WebSocket[] = [];
afterEach(async () => { for (const c of clients.splice(0)) { try { c.terminate(); } catch {} } await new Promise<void>((res) => wss.close(() => res())); rmSync(tmpDir, { recursive: true, force: true }); });
function connectClient(): Promise<WebSocket> { return new Promise((res, rej) => { const ws = new WebSocket(`ws://127.0.0.1:${port}`); ws.once("open", () => { clients.push(ws); res(ws); }); ws.once("error", rej); }); }
async function waitConn(adapterId: string): Promise<void> { const deadline = Date.now() + 2000; while (!hub.getConn(adapterId)) { if (Date.now() > deadline) throw new Error("timeout " + adapterId); await new Promise((r) => setTimeout(r, 20)); } }
function helloInRoom(ws: WebSocket, adapterId: string, room: string) {
  const env = makeEnvelope<HelloPayload>("hello", adapterId, room, 1, 0, { adapter_id: adapterId, protocol_version: PROTOCOL_VERSION_STR, last_seen_seq: 0 });
  ws.send(JSON.stringify(env));
}

describe("hub.r3 getOnlineAdapters(room)", () => {
  it("无任何连接时 getOnlineAdapters() 返回空数组", () => {
    expect(hub.getOnlineAdapters()).toEqual([]);
  });

  it("不传 room 时返回全部在线 adapter，且按建连插入顺序排列", async () => {
    const wsA = await connectClient();
    helloInRoom(wsA, "a", "room-a");
    await waitConn("a");
    const wsB = await connectClient();
    helloInRoom(wsB, "b", "room-b");
    await waitConn("b");

    expect(hub.getOnlineAdapters()).toEqual(["a", "b"]);
  });

  it("传 room 时只返回属于该 room 的 adapter", async () => {
    const wsA = await connectClient();
    helloInRoom(wsA, "a", "room-a");
    await waitConn("a");
    const wsB = await connectClient();
    helloInRoom(wsB, "b", "room-b");
    await waitConn("b");

    expect(hub.getOnlineAdapters("room-a")).toEqual(["a"]);
    expect(hub.getOnlineAdapters("room-b")).toEqual(["b"]);
  });

  it("传入不存在的 room 时返回空数组", async () => {
    const wsA = await connectClient();
    helloInRoom(wsA, "a", "room-a");
    await waitConn("a");

    expect(hub.getOnlineAdapters("room-ghost")).toEqual([]);
  });

  it("同一 room 内多个 adapter 全部返回", async () => {
    const wsA = await connectClient();
    helloInRoom(wsA, "a", "room-a");
    await waitConn("a");
    const wsB = await connectClient();
    helloInRoom(wsB, "b", "room-b");
    await waitConn("b");
    const wsC = await connectClient();
    helloInRoom(wsC, "c", "room-a");
    await waitConn("c");

    expect(hub.getOnlineAdapters("room-a")).toEqual(["a", "c"]);
  });

  it("断开后该 adapter 不再出现在在线列表中", async () => {
    const wsA = await connectClient();
    helloInRoom(wsA, "a", "room-a");
    await waitConn("a");
    const wsB = await connectClient();
    helloInRoom(wsB, "b", "room-b");
    await waitConn("b");

    wsA.close();
    const deadline = Date.now() + 2000;
    while (hub.getConn("a")) {
      if (Date.now() > deadline) throw new Error("timeout waiting a removed");
      await new Promise((r) => setTimeout(r, 20));
    }

    expect(hub.getOnlineAdapters()).toEqual(["b"]);
    expect(hub.getOnlineAdapters("room-a")).toEqual([]);
  });
});