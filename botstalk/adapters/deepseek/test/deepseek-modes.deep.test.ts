import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from "vitest";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { mkdirSync, writeFileSync, chmodSync } from "node:fs";
import { join } from "node:path";
import type { AdapterClient } from "@botstalk/adapter-base";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import {
  readRuntimeConfig,
  createHandlers,
  splitDshCommand,
  summarize,
} from "../src/index.js";

const TEST_TMP = join(__dirname, "..", "test-tmp");

function sseChunk(
  content: string,
  usage?: { prompt_tokens: number; completion_tokens: number },
): string {
  const payload: Record<string, unknown> = {
    choices: [{ delta: { content } }],
  };
  if (usage) payload.usage = usage;
  return `data: ${JSON.stringify(payload)}\n\n`;
}

function makeMockClient() {
  return {
    sendMessage: vi.fn(),
    sendStreamStart: vi.fn(() => "sid"),
    sendStreamChunk: vi.fn(),
    sendStreamFinal: vi.fn(),
    sendStreamError: vi.fn(),
  } as unknown as AdapterClient & {
    sendMessage: ReturnType<typeof vi.fn>;
    sendStreamStart: ReturnType<typeof vi.fn>;
    sendStreamChunk: ReturnType<typeof vi.fn>;
    sendStreamFinal: ReturnType<typeof vi.fn>;
    sendStreamError: ReturnType<typeof vi.fn>;
  };
}

function makeTaskEnv(): Envelope<MessagePayload> {
  return {
    v: 1,
    type: "message",
    seq: 1,
    ack: 0,
    sender: "peer",
    room: "lobby",
    ts: Date.now(),
    payload: {
      msg_id: "m1",
      text: "do the thing",
      mentions: [] as string[],
      intent: "task",
      task_id: "t1",
    },
  } as unknown as Envelope<MessagePayload>;
}

function makeChatEnv(): Envelope<MessagePayload> {
  return {
    v: 1,
    type: "message",
    seq: 2,
    ack: 0,
    sender: "peer",
    room: "lobby",
    ts: Date.now(),
    payload: {
      msg_id: "c1",
      text: "hello",
      mentions: [] as string[],
      intent: "chat",
    },
  } as unknown as Envelope<MessagePayload>;
}

describe("deepseek adapter brain/body modes", () => {
  let server: Server;
  let port: number;

  beforeAll(async () => {
    server = createServer((req, res) => {
      if (req.method !== "POST" || !req.url?.endsWith("/chat/completions")) {
        res.statusCode = 404;
        res.end("not found");
        return;
      }
      res.setHeader("content-type", "text/event-stream");
      res.setHeader("cache-control", "no-cache");
      res.statusCode = 200;
      res.write(sseChunk("Hello"));
      res.write(sseChunk(", "));
      res.write(sseChunk("world"));
      res.write(sseChunk("", { prompt_tokens: 3, completion_tokens: 2 }));
      res.write("data: [DONE]\n\n");
      res.end();
    });
    await new Promise<void>((resolve) => {
      server.listen(0, "127.0.0.1", () => resolve());
    });
    const addr = server.address() as AddressInfo;
    port = addr.port;
  });

  afterAll(async () => {
    await new Promise<void>((resolve) => {
      server.close(() => resolve());
    });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("readRuntimeConfig bodyMode from env", () => {
    vi.stubEnv("DEEPSEEK_BODY", "");
    const cfgBrain = readRuntimeConfig();
    expect(cfgBrain.bodyMode).toBe(false);
    expect(cfgBrain.adapterId).toBe("deepseek");

    vi.stubEnv("DEEPSEEK_BODY", "true");
    const cfgBody = readRuntimeConfig();
    expect(cfgBody.bodyMode).toBe(true);
    expect(cfgBody.adapterId).toBe("deepseek");
  });

  it("brain onTask without apiKey fails fast without network", async () => {
    vi.stubEnv("DEEPSEEK_API_KEY", "");
    vi.stubEnv("DEEPSEEK_BODY", "");

    const mockClient = makeMockClient();
    mockClient.sendMessage.mockClear();
    mockClient.sendStreamStart.mockClear();
    mockClient.sendStreamChunk.mockClear();
    mockClient.sendStreamFinal.mockClear();
    mockClient.sendStreamError.mockClear();

    const cfg = readRuntimeConfig();
    expect(cfg.bodyMode).toBe(false);
    expect(cfg.apiKey).toBe("");

    const handlers = createHandlers(cfg, mockClient);

    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("network should not be touched"));

    await handlers.onTask(makeTaskEnv());

    expect(fetchSpy).not.toHaveBeenCalled();

    const calls = mockClient.sendMessage.mock.calls;
    const failedCall = calls.find((c) => {
      const text = c[0] as string;
      const opts = c[1] as { task_status?: string } | undefined;
      return (
        typeof text === "string" &&
        text.includes("missing DEEPSEEK_API_KEY") &&
        opts !== undefined &&
        opts.task_status === "failed"
      );
    });
    expect(failedCall).toBeDefined();

    fetchSpy.mockRestore();
  });

  it("brain onTask via fake SSE completes with brain label", async () => {
    const mockClient = makeMockClient();
    mockClient.sendMessage.mockClear();
    mockClient.sendStreamStart.mockClear();
    mockClient.sendStreamChunk.mockClear();
    mockClient.sendStreamFinal.mockClear();
    mockClient.sendStreamError.mockClear();

    const cfg = {
      ...readRuntimeConfig(),
      apiKey: "test-key",
      baseUrl: `http://127.0.0.1:${port}`,
      model: "deepseek-chat",
      bodyMode: false,
      dshCmd: [] as string[],
    };

    const handlers = createHandlers(cfg, mockClient);
    await handlers.onTask(makeTaskEnv());

    const calls = mockClient.sendMessage.mock.calls;
    const doneCall = calls.find((c) => {
      const text = c[0] as string;
      const opts = c[1] as { task_status?: string } | undefined;
      return (
        typeof text === "string" &&
        text.startsWith("[deepseek:brain]") &&
        opts !== undefined &&
        opts.task_status === "done"
      );
    });
    expect(doneCall).toBeDefined();
    expect(doneCall![0] as string).toContain("Hello, world");
  });

  it("body onTask via fake dsh needs no apiKey", async () => {
    mkdirSync(TEST_TMP, { recursive: true });
    const scriptPath = join(TEST_TMP, "fake-dsh.sh");
    const script = `#!/bin/sh
echo '{"type":"session","sessionId":"fake-session"}'
echo '{"type":"status","phase":"turn_start","turn":1}'
echo '{"type":"status","phase":"step_start","turn":1}'
echo '{"type":"final","text":"fake-final-text"}'
exit 0
`;
    writeFileSync(scriptPath, script, { encoding: "utf8" });
    chmodSync(scriptPath, 0o755);

    const mockClient = makeMockClient();
    mockClient.sendMessage.mockClear();
    mockClient.sendStreamStart.mockClear();
    mockClient.sendStreamChunk.mockClear();
    mockClient.sendStreamFinal.mockClear();
    mockClient.sendStreamError.mockClear();

    const cfg = {
      ...readRuntimeConfig(),
      apiKey: "",
      bodyMode: true,
      dshCmd: splitDshCommand(scriptPath),
    };

    const handlers = createHandlers(cfg, mockClient);
    await handlers.onTask(makeTaskEnv());

    const calls = mockClient.sendMessage.mock.calls;
    const doneCall = calls.find((c) => {
      const text = c[0] as string;
      const opts = c[1] as { task_status?: string } | undefined;
      return (
        typeof text === "string" &&
        text.startsWith("[deepseek:body]") &&
        opts !== undefined &&
        opts.task_status === "done"
      );
    });
    expect(doneCall).toBeDefined();
    expect(doneCall![0] as string).toContain("fake-final-text");
  });

  it("brain onMessage streams chat via SSE", async () => {
    const mockClient = makeMockClient();
    mockClient.sendMessage.mockClear();
    mockClient.sendStreamStart.mockClear();
    mockClient.sendStreamChunk.mockClear();
    mockClient.sendStreamFinal.mockClear();
    mockClient.sendStreamError.mockClear();

    const cfg = {
      ...readRuntimeConfig(),
      apiKey: "test-key",
      baseUrl: `http://127.0.0.1:${port}`,
      model: "deepseek-chat",
      bodyMode: false,
      dshCmd: [] as string[],
    };

    const handlers = createHandlers(cfg, mockClient);
    await handlers.onMessage(makeChatEnv());

    expect(mockClient.sendStreamChunk).toHaveBeenCalled();

    const chunkCalls = mockClient.sendStreamChunk.mock.calls;
    const joined = chunkCalls
      .map((c) => c[2] as string)
      .join("");
    expect(joined).toBe("Hello, world");

    expect(mockClient.sendStreamFinal).toHaveBeenCalledTimes(1);
  });

  it("body mode onMessage still uses brain SSE", async () => {
    const mockClient = makeMockClient();
    mockClient.sendMessage.mockClear();
    mockClient.sendStreamStart.mockClear();
    mockClient.sendStreamChunk.mockClear();
    mockClient.sendStreamFinal.mockClear();
    mockClient.sendStreamError.mockClear();

    const cfg = {
      ...readRuntimeConfig(),
      apiKey: "test-key",
      baseUrl: `http://127.0.0.1:${port}`,
      model: "deepseek-chat",
      bodyMode: true,
      dshCmd: [] as string[],
    };

    const handlers = createHandlers(cfg, mockClient);
    await handlers.onMessage(makeChatEnv());

    expect(mockClient.sendStreamChunk).toHaveBeenCalled();

    const chunkCalls = mockClient.sendStreamChunk.mock.calls;
    const joined = chunkCalls
      .map((c) => c[2] as string)
      .join("");
    expect(joined).toBe("Hello, world");

    expect(mockClient.sendStreamFinal).toHaveBeenCalled();
  });

  it("summarize truncation boundary", () => {
    const exact = "x".repeat(500);
    const trimmedExact = summarize(exact, 500);
    expect(trimmedExact).toHaveLength(500);
    expect(trimmedExact).toBe(exact);

    const over = "x".repeat(501);
    const trimmedOver = summarize(over, 500);
    expect(trimmedOver).toHaveLength(500);
    expect(trimmedOver).toBe("x".repeat(500));

    expect(summarize(" hi ", 10)).toBe("hi");
  });
});
