import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WebSocketServer } from "ws";
import type { WebSocket } from "ws";
import { AdapterClient } from "../src/client.js";
import { mkdtempSync, rmSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

interface ReceivedFrame {
  v: number;
  type: string;
  seq: number;
  ack: number;
  sender: string;
  room: string;
  ts: number;
  payload: unknown;
}

interface FakeGateway {
  url: string;
  received: ReceivedFrame[];
  sockets: WebSocket[];
  sendToClients: (frame: unknown) => void;
  close: () => Promise<void>;
}

async function startFakeGateway(): Promise<FakeGateway> {
  const wss = new WebSocketServer({ port: 0 });
  await new Promise<void>((resolve) => wss.once("listening", () => resolve()));
  const addr = wss.address();
  if (typeof addr === "string" || addr === null) {
    throw new Error("no address");
  }
  const url = `ws://127.0.0.1:${addr.port}`;
  const received: ReceivedFrame[] = [];
  const sockets: WebSocket[] = [];

  wss.on("connection", (socket) => {
    sockets.push(socket);
    socket.on("message", (data) => {
      const text = typeof data === "string" ? data : String(data);
      const frame = JSON.parse(text) as ReceivedFrame;
      received.push(frame);
      if (frame.type === "hello") {
        socket.send(
          JSON.stringify({
            v: 1,
            type: "presence",
            seq: 1,
            ack: frame.seq,
            sender: "gateway",
            room: "lobby",
            ts: Date.now(),
            payload: { status: "online" },
          }),
        );
      }
    });
  });

  return {
    url,
    received,
    sockets,
    sendToClients: (frame: unknown) => {
      const text = JSON.stringify(frame);
      for (const s of sockets) {
        if (s.readyState === s.OPEN) s.send(text);
      }
    },
    close: async () => {
      for (const s of sockets) {
        try {
          s.close();
        } catch {
          // ignore
        }
      }
      await new Promise<void>((resolve) => wss.close(() => resolve()));
    },
  };
}

function waitFor(predicate: () => boolean, timeoutMs = 2000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = () => {
      if (predicate()) {
        resolve();
        return;
      }
      if (Date.now() - start > timeoutMs) {
        reject(new Error("timeout waiting for predicate"));
        return;
      }
      setTimeout(tick, 10);
    };
    tick();
  });
}

function makeMessageFrame(opts: {
  seq: number;
  sender: string;
  gseq?: number;
  text?: string;
}): unknown {
  const frame: Record<string, unknown> = {
    v: 1,
    type: "message",
    seq: opts.seq,
    ack: 0,
    sender: opts.sender,
    room: "lobby",
    ts: Date.now(),
    payload: {
      msg_id: `m-${opts.seq}`,
      text: opts.text ?? "hi",
      mentions: [],
    },
  };
  if (opts.gseq !== undefined) {
    frame.gseq = opts.gseq;
  }
  return frame;
}

describe("AdapterClient gseq persistence and reconnect watermark", () => {
  let gateway: FakeGateway | null = null;
  let client: AdapterClient | null = null;
  let stateDir: string | null = null;

  beforeEach(() => {
    vi.useRealTimers();
  });

  afterEach(async () => {
    if (client) {
      try {
        client.disconnect();
      } catch {
        // ignore
      }
      client = null;
    }
    if (gateway) {
      try {
        await gateway.close();
      } catch {
        // ignore
      }
      gateway = null;
    }
    if (stateDir) {
      try {
        rmSync(stateDir, { recursive: true, force: true });
      } catch {
        // ignore
      }
      stateDir = null;
    }
    vi.useRealTimers();
  });

  it("gseq frame persists watermark to disk", async () => {
    stateDir = mkdtempSync(join(tmpdir(), "botstalk-gseq-1-"));
    gateway = await startFakeGateway();
    const adapterId = "gseq-1";
    client = new AdapterClient({
      adapterId,
      gatewayUrl: gateway.url,
      room: "lobby",
      stateDir,
    });
    client.connect();

    await waitFor(() => gateway!.received.some((f) => f.type === "hello"));

    gateway.sendToClients(
      makeMessageFrame({ seq: 1, sender: "peer", gseq: 7, text: "hi" }),
    );

    const watermarkFile = join(stateDir, `${adapterId}.gseq`);
    await waitFor(() => {
      try {
        return readFileSync(watermarkFile, "utf8").trim() === "7";
      } catch {
        return false;
      }
    });

    expect(readFileSync(watermarkFile, "utf8").trim()).toBe("7");
  });

  it("larger gseq overwrites watermark", async () => {
    stateDir = mkdtempSync(join(tmpdir(), "botstalk-gseq-2-"));
    gateway = await startFakeGateway();
    const adapterId = "gseq-2";
    client = new AdapterClient({
      adapterId,
      gatewayUrl: gateway.url,
      room: "lobby",
      stateDir,
    });
    client.connect();

    await waitFor(() => gateway!.received.some((f) => f.type === "hello"));

    const watermarkFile = join(stateDir, `${adapterId}.gseq`);

    gateway.sendToClients(
      makeMessageFrame({ seq: 1, sender: "peer", gseq: 7 }),
    );
    await waitFor(() => {
      try {
        return readFileSync(watermarkFile, "utf8").trim() === "7";
      } catch {
        return false;
      }
    });

    gateway.sendToClients(
      makeMessageFrame({ seq: 2, sender: "peer", gseq: 12 }),
    );
    await waitFor(() => {
      try {
        return readFileSync(watermarkFile, "utf8").trim() === "12";
      } catch {
        return false;
      }
    });

    expect(readFileSync(watermarkFile, "utf8").trim()).toBe("12");
  });

  it("frame without gseq does not change watermark", async () => {
    stateDir = mkdtempSync(join(tmpdir(), "botstalk-gseq-3-"));
    gateway = await startFakeGateway();
    const adapterId = "gseq-3";
    client = new AdapterClient({
      adapterId,
      gatewayUrl: gateway.url,
      room: "lobby",
      stateDir,
    });
    client.connect();

    await waitFor(() => gateway!.received.some((f) => f.type === "hello"));

    const watermarkFile = join(stateDir, `${adapterId}.gseq`);

    gateway.sendToClients(
      makeMessageFrame({ seq: 1, sender: "peer", gseq: 12 }),
    );
    await waitFor(() => {
      try {
        return readFileSync(watermarkFile, "utf8").trim() === "12";
      } catch {
        return false;
      }
    });

    gateway.sendToClients(makeMessageFrame({ seq: 2, sender: "peer" }));

    await new Promise((resolve) => setTimeout(resolve, 300));

    expect(readFileSync(watermarkFile, "utf8").trim()).toBe("12");
  });

  it("gseq regression resets watermark (gateway restart)", async () => {
    stateDir = mkdtempSync(join(tmpdir(), "botstalk-gseq-4-"));
    gateway = await startFakeGateway();
    const adapterId = "gseq-4";
    client = new AdapterClient({
      adapterId,
      gatewayUrl: gateway.url,
      room: "lobby",
      stateDir,
    });
    client.connect();

    await waitFor(() => gateway!.received.some((f) => f.type === "hello"));

    const watermarkFile = join(stateDir, `${adapterId}.gseq`);

    gateway.sendToClients(
      makeMessageFrame({ seq: 1, sender: "peer", gseq: 12 }),
    );
    await waitFor(() => {
      try {
        return readFileSync(watermarkFile, "utf8").trim() === "12";
      } catch {
        return false;
      }
    });

    gateway.sendToClients(
      makeMessageFrame({ seq: 2, sender: "peer", gseq: 3 }),
    );
    await waitFor(() => {
      try {
        return readFileSync(watermarkFile, "utf8").trim() === "3";
      } catch {
        return false;
      }
    });

    expect(readFileSync(watermarkFile, "utf8").trim()).toBe("3");
  });

  it("fresh instance hello has last_seen_seq -1", async () => {
    stateDir = mkdtempSync(join(tmpdir(), "botstalk-fresh-1-"));
    gateway = await startFakeGateway();
    const adapterId = "fresh-1";
    client = new AdapterClient({
      adapterId,
      gatewayUrl: gateway.url,
      room: "lobby",
      stateDir,
    });
    client.connect();

    await waitFor(() => gateway!.received.some((f) => f.type === "hello"));

    const hello = gateway.received.find((f) => f.type === "hello");
    expect(hello).toBeDefined();
    const payload = hello!.payload as { last_seen_seq: number };
    expect(payload.last_seen_seq).toBe(-1);
  });

  it("corrupt watermark file degrades silently to -1", async () => {
    stateDir = mkdtempSync(join(tmpdir(), "botstalk-dirty-1-"));
    const adapterId = "dirty-1";
    writeFileSync(join(stateDir, `${adapterId}.gseq`), "abc", "utf8");

    gateway = await startFakeGateway();
    client = new AdapterClient({
      adapterId,
      gatewayUrl: gateway.url,
      room: "lobby",
      stateDir,
    });

    expect(() => client!.connect()).not.toThrow();

    await waitFor(() => gateway!.received.some((f) => f.type === "hello"));

    const hello = gateway.received.find((f) => f.type === "hello");
    expect(hello).toBeDefined();
    const payload = hello!.payload as { last_seen_seq: number };
    expect(payload.last_seen_seq).toBe(-1);
  });

  it("reconnect carries in-memory watermark in hello", async () => {
    stateDir = mkdtempSync(join(tmpdir(), "botstalk-reconn-1-"));
    gateway = await startFakeGateway();
    const adapterId = "reconn-1";
    client = new AdapterClient({
      adapterId,
      gatewayUrl: gateway.url,
      room: "lobby",
      stateDir,
    });
    client.connect();

    await waitFor(() => gateway!.received.some((f) => f.type === "hello"));

    const watermarkFile = join(stateDir, `${adapterId}.gseq`);

    gateway.sendToClients(
      makeMessageFrame({ seq: 1, sender: "peer", gseq: 5 }),
    );
    await waitFor(() => {
      try {
        return readFileSync(watermarkFile, "utf8").trim() === "5";
      } catch {
        return false;
      }
    });

    gateway.sockets[0]?.close();

    await waitFor(
      () => gateway!.received.filter((f) => f.type === "hello").length >= 2,
      10000,
    );

    const hellos = gateway.received.filter((f) => f.type === "hello");
    const secondHello = hellos[1];
    const payload = secondHello.payload as { last_seen_seq: number };
    expect(payload.last_seen_seq).toBe(5);
  });

  it("in-memory watermark wins over tampered disk file on reconnect", async () => {
    stateDir = mkdtempSync(join(tmpdir(), "botstalk-reconn-2-"));
    gateway = await startFakeGateway();
    const adapterId = "reconn-2";
    client = new AdapterClient({
      adapterId,
      gatewayUrl: gateway.url,
      room: "lobby",
      stateDir,
    });
    client.connect();

    await waitFor(() => gateway!.received.some((f) => f.type === "hello"));

    const watermarkFile = join(stateDir, `${adapterId}.gseq`);

    gateway.sendToClients(
      makeMessageFrame({ seq: 1, sender: "peer", gseq: 9 }),
    );
    await waitFor(() => {
      try {
        return readFileSync(watermarkFile, "utf8").trim() === "9";
      } catch {
        return false;
      }
    });

    writeFileSync(watermarkFile, "2", "utf8");

    gateway.sockets[0]?.close();

    await waitFor(
      () => gateway!.received.filter((f) => f.type === "hello").length >= 2,
      10000,
    );

    const hellos = gateway.received.filter((f) => f.type === "hello");
    const secondHello = hellos[1];
    const payload = secondHello.payload as { last_seen_seq: number };
    expect(payload.last_seen_seq).toBe(9);
  });
});
