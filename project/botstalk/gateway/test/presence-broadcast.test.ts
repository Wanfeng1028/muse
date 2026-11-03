import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { WebSocketServer, WebSocket } from "ws";
import { openDb } from "../src/db.js";
import { Hub } from "../src/hub.js";
import { PROTOCOL_VERSION_STR, makeEnvelope } from "@botstalk/protocol";

function openSocket(port: number): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}`);
    ws.on("open", () => resolve(ws));
    ws.on("error", reject);
  });
}

function collectFrames(ws: WebSocket): unknown[] {
  const frames: unknown[] = [];
  ws.on("message", (data) => {
    try {
      frames.push(JSON.parse(data.toString()));
    } catch {
      // ignore
    }
  });
  return frames;
}

async function waitFor<T>(fn: () => T | undefined, timeoutMs: number): Promise<T> {
  const start = Date.now();
  for (;;) {
    const v = fn();
    if (v !== undefined) return v;
    if (Date.now() - start > timeoutMs) throw new Error("timeout waiting for condition");
    await new Promise((r) => setTimeout(r, 20));
  }
}

describe("presence broadcast", () => {
  let dir: string;
  let db: ReturnType<typeof openDb>;
  let hub: Hub;
  let wss: WebSocketServer;
  let port: number;
  const sockets: WebSocket[] = [];

  beforeEach(async () => {
    dir = mkdtempSync(join(tmpdir(), "presence-broadcast-"));
    db = openDb(join(dir, "test.db"));
    hub = new Hub(db);
    hub.onMessage = () => {};
    wss = new WebSocketServer({ port: 0 });
    await new Promise<void>((resolve) => wss.once("listening", () => resolve()));
    const addr = wss.address();
    if (typeof addr === "string" || addr === null) throw new Error("no port");
    port = addr.port;
    wss.on("connection", (ws) => hub.handleConnection(ws));
  });

  afterEach(async () => {
    await Promise.all(
      sockets.map(
        (ws) =>
          new Promise<void>((resolve) => {
            if (ws.readyState === WebSocket.CLOSED) {
              resolve();
              return;
            }
            ws.once("close", () => resolve());
            try {
              ws.close();
            } catch {
              resolve();
            }
            setTimeout(() => resolve(), 1000);
          }),
      ),
    );
    sockets.length = 0;
    await new Promise<void>((resolve) => wss.close(() => resolve()));
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("broadcasts online and offline presence to room members", async () => {
    const a = await openSocket(port);
    sockets.push(a);
    const framesA = collectFrames(a);
    a.send(
      JSON.stringify(
        makeEnvelope("hello", "a", "lobby", 1, 0, {
          adapter_id: "a",
          protocol_version: PROTOCOL_VERSION_STR,
          last_seen_seq: 0,
        }),
      ),
    );

    const b = await openSocket(port);
    sockets.push(b);
    b.send(
      JSON.stringify(
        makeEnvelope("hello", "b", "lobby", 1, 0, {
          adapter_id: "b",
          protocol_version: PROTOCOL_VERSION_STR,
          last_seen_seq: 0,
        }),
      ),
    );

    await new Promise((r) => setTimeout(r, 100));

    b.send(
      JSON.stringify(
        makeEnvelope("presence", "b", "lobby", 2, 0, {
          adapter_id: "b",
          status: "online",
        }),
      ),
    );

    const online = await waitFor(() => {
      for (const f of framesA) {
        const env = f as { type?: string; payload?: { adapter_id?: string; status?: string } };
        if (
          env.type === "presence" &&
          env.payload?.adapter_id === "b" &&
          env.payload?.status === "online"
        ) {
          return env;
        }
      }
      return undefined;
    }, 3000);
    expect(online).toBeTruthy();

    b.close();

    const offline = await waitFor(() => {
      for (const f of framesA) {
        const env = f as { type?: string; payload?: { adapter_id?: string; status?: string } };
        if (
          env.type === "presence" &&
          env.payload?.adapter_id === "b" &&
          env.payload?.status === "offline"
        ) {
          return env;
        }
      }
      return undefined;
    }, 3000);
    expect(offline).toBeTruthy();
  });
});
