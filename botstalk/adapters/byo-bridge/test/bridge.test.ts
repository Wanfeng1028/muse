import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { WebSocketServer, type WebSocket } from "ws";
import type { AddressInfo } from "node:net";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import { makeEnvelope, type Envelope, type StreamPayload } from "@botstalk/protocol";
import { ByoBridge } from "../src/bridge.js";
import type { ByoProfile } from "../src/profile.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = join(__dirname, "..");
const FIXTURE = join(PKG_ROOT, "test-tmp", "fake-acp-agent.mjs");
const STATE_DIR = join(PKG_ROOT, "test-tmp", "bridge-state");

interface CapturedFrame {
  type: string;
  sender: string;
  payload: Record<string, unknown>;
}

async function waitFor(cond: () => boolean, timeoutMs = 8000): Promise<void> {
  const start = Date.now();
  while (!cond()) {
    if (Date.now() - start > timeoutMs) throw new Error("waitFor timed out");
    await new Promise((r) => setTimeout(r, 25));
  }
}

describe("ByoBridge task flow against a fake gateway", () => {
  let wss: WebSocketServer;
  let socket: WebSocket | null = null;
  let bridge: ByoBridge;
  const frames: CapturedFrame[] = [];

  beforeAll(async () => {
    mkdirSync(STATE_DIR, { recursive: true });
    process.env.BOTSTALK_STATE_DIR = STATE_DIR;
    wss = new WebSocketServer({ host: "127.0.0.1", port: 0 });
    await new Promise<void>((resolve) => wss.on("listening", () => resolve()));
    const port = (wss.address() as AddressInfo).port;
    wss.on("connection", (ws) => {
      socket = ws;
      ws.on("message", (data) => {
        try {
          const env = JSON.parse(String(data)) as Envelope<Record<string, unknown>>;
          frames.push({ type: env.type, sender: env.sender, payload: env.payload });
        } catch {
          // ignore unparsable frames
        }
      });
    });
    const profile: ByoProfile = {
      agentId: "byo-test",
      gatewayUrl: `ws://127.0.0.1:${port}`,
      room: "lobby",
      provider: { command: process.execPath, args: [FIXTURE], cwd: PKG_ROOT },
      createdAtMs: 1,
      updatedAtMs: 1,
    };
    bridge = new ByoBridge(profile);
    bridge.connect();
    await waitFor(() => frames.some((f) => f.type === "hello"));
  }, 20000);

  afterAll(async () => {
    await bridge.shutdown();
    socket?.close();
    await new Promise<void>((resolve) => wss.close(() => resolve()));
    delete process.env.BOTSTALK_STATE_DIR;
    rmSync(STATE_DIR, { recursive: true, force: true });
  });

  it("announces itself with hello and capability_update", () => {
    expect(frames.some((f) => f.type === "hello" && f.sender === "byo-test")).toBe(true);
    const cap = frames.find((f) => f.type === "capability_update");
    expect(cap).toBeDefined();
    const capabilities = cap?.payload.capabilities as { intents?: string[] } | undefined;
    expect(capabilities?.intents).toEqual(expect.arrayContaining(["chat", "task"]));
  });

  it("runs a task through ACP and streams the result back", async () => {
    const taskEnv = makeEnvelope("message", "user-1", "lobby", 1, 0, {
      msg_id: "m1",
      text: "say hello",
      mentions: [] as string[],
      intent: "task" as const,
      task_id: "t1",
    });
    socket?.send(JSON.stringify(taskEnv));

    await waitFor(() =>
      frames.some(
        (f) =>
          f.type === "message" &&
          (f.payload as { task_status?: string }).task_status === "done",
      ),
    );

    const running = frames.find(
      (f) => f.type === "message" && (f.payload as { task_status?: string }).task_status === "running",
    );
    expect(running).toBeDefined();

    const streamFrames = frames.filter((f) => f.type === "stream");
    const deltas = streamFrames
      .filter((f) => (f.payload as unknown as StreamPayload).final !== true)
      .map((f) => (f.payload as unknown as StreamPayload).delta)
      .join("");
    expect(deltas).toBe("Hello, world");
    const finalFrame = streamFrames.find(
      (f) => (f.payload as unknown as StreamPayload).final === true,
    );
    expect(finalFrame).toBeDefined();

    const done = frames.find(
      (f) => f.type === "message" && (f.payload as { task_status?: string }).task_status === "done",
    );
    expect((done?.payload as { task_id?: string }).task_id).toBe("t1");
    expect((done?.payload as { text?: string }).text).toBe("Hello, world");
  }, 20000);

  it("ignores chat that does not mention the agent", async () => {
    const before = frames.filter((f) => f.type === "message").length;
    const chatEnv = makeEnvelope("message", "user-1", "lobby", 2, 0, {
      msg_id: "m2",
      text: "hello room",
      mentions: [] as string[],
      intent: "chat" as const,
    });
    socket?.send(JSON.stringify(chatEnv));
    await new Promise((r) => setTimeout(r, 400));
    const after = frames.filter((f) => f.type === "message").length;
    expect(after).toBe(before);
  }, 20000);
});
