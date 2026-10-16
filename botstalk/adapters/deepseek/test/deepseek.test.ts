import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { createServer, type Server } from "node:http";
import { AddressInfo } from "node:net";
import { mkdirSync, writeFileSync, chmodSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import {
  chatCompletionStream,
  runDshTask,
  splitDshCommand,
} from "../src/index.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PKG_ROOT = join(__dirname, "..");
const TEST_TMP = join(PKG_ROOT, "test-tmp");

function sseChunk(content: string, usage?: { prompt_tokens: number; completion_tokens: number }): string {
  const payload: Record<string, unknown> = {
    choices: [{ delta: { content } }],
  };
  if (usage) payload.usage = usage;
  return `data: ${JSON.stringify(payload)}\n\n`;
}

describe("chatCompletionStream (brain)", () => {
  let server: Server;
  let port = 0;
  let mode: "ok" | "http-500" = "ok";

  beforeAll(async () => {
    server = createServer((req, res) => {
      if (req.method !== "POST" || !req.url?.endsWith("/chat/completions")) {
        res.statusCode = 404;
        res.end("not found");
        return;
      }
      if (mode === "http-500") {
        res.statusCode = 500;
        res.end("boom");
        return;
      }
      res.setHeader("content-type", "text/event-stream");
      res.setHeader("cache-control", "no-cache");
      res.statusCode = 200;
      res.write(sseChunk("Hello"));
      res.write(sseChunk(", "));
      res.write(sseChunk("world"));
      res.write(
        sseChunk("", { prompt_tokens: 3, completion_tokens: 2 }),
      );
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
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  it("assembles SSE deltas into full text and reads usage", async () => {
    mode = "ok";
    let acc = "";
    const usage = await chatCompletionStream(
      "hi",
      (d) => {
        acc += d;
      },
      {
        apiKey: "test-key-not-real",
        baseUrl: `http://127.0.0.1:${port}`,
        model: "deepseek-chat",
      },
    );
    expect(acc).toBe("Hello, world");
    expect(usage).toEqual({ input_tokens: 3, output_tokens: 2 });
  });

  it("throws upstream_error on non-2xx", async () => {
    mode = "http-500";
    await expect(
      chatCompletionStream(
        "hi",
        () => {},
        {
          apiKey: "test-key-not-real",
          baseUrl: `http://127.0.0.1:${port}`,
          model: "deepseek-chat",
        },
      ),
    ).rejects.toThrow(/upstream_error: http 500/);
  });
});

describe("runDshTask (body)", () => {
  beforeAll(() => {
    mkdirSync(TEST_TMP, { recursive: true });
  });

  it("parses NDJSON and returns final text", async () => {
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

    const cmd = splitDshCommand(scriptPath);
    const result = await runDshTask(cmd, "botstalk-test", "do the thing");
    expect(result.text).toBe("fake-final-text");
  });

  it("rejects on non-zero exit code", async () => {
    const scriptPath = join(TEST_TMP, "fake-dsh-fail.sh");
    const script = `#!/bin/sh
echo '{"type":"session","sessionId":"fake-session"}'
echo "some stderr" 1>&2
exit 2
`;
    writeFileSync(scriptPath, script, { encoding: "utf8" });
    chmodSync(scriptPath, 0o755);

    const cmd = splitDshCommand(scriptPath);
    await expect(runDshTask(cmd, "botstalk-test", "x")).rejects.toThrow(
      /upstream_error/,
    );
  });

  it("rejects when stderr mentions MISSING_CREDENTIAL", async () => {
    const scriptPath = join(TEST_TMP, "fake-dsh-missing.sh");
    const script = `#!/bin/sh
echo '{"type":"session","sessionId":"fake-session"}'
echo "MISSING_CREDENTIAL: no api key" 1>&2
exit 0
`;
    writeFileSync(scriptPath, script, { encoding: "utf8" });
    chmodSync(scriptPath, 0o755);

    const cmd = splitDshCommand(scriptPath);
    await expect(runDshTask(cmd, "botstalk-test", "x")).rejects.toThrow(
      /MISSING_CREDENTIAL/,
    );
  });
});
// 自查：红线 1-5 逐条通过
