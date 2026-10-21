import { describe, it, expect, afterAll } from "vitest";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import { AcpClient, type AcpUpdate } from "../src/acp.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = join(__dirname, "..");
const FIXTURE = join(PKG_ROOT, "test-tmp", "fake-acp-agent.mjs");

describe("AcpClient against the fake ACP agent", () => {
  const client = new AcpClient(process.execPath, [FIXTURE], { cwd: PKG_ROOT });

  afterAll(async () => {
    await client.close();
  });

  it("completes the initialize handshake", async () => {
    await client.start();
    const result = (await client.initialize()) as Record<string, unknown>;
    expect(result.protocolVersion).toBe(1);
  }, 15000);

  it("creates a session", async () => {
    const sessionId = await client.newSession(PKG_ROOT);
    expect(sessionId).toBe("fake-session-1");
  }, 15000);

  it("streams agent_message_chunk updates and resolves with end_turn", async () => {
    const chunks: string[] = [];
    client.onUpdate = (params) => {
      const update: AcpUpdate = params.update;
      if (update.sessionUpdate === "agent_message_chunk") {
        const text = update.content?.text;
        if (typeof text === "string") chunks.push(text);
      }
    };
    const result = await client.prompt("fake-session-1", "say hello");
    expect(result.stopReason).toBe("end_turn");
    expect(chunks).toEqual(["Hello, ", "world"]);
  }, 15000);

  it("surfaces a refusal stop reason", async () => {
    client.onUpdate = null;
    const result = await client.prompt("fake-session-1", "please REFUSE this");
    expect(result.stopReason).toBe("refusal");
  }, 15000);

  it("cancel resolves without a response", async () => {
    await expect(client.cancel("fake-session-1")).resolves.toBeUndefined();
  }, 15000);
});
