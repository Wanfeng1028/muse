import { describe, expect, it, vi } from "vitest";

import { processMcpLine } from "./mcp-protocol.js";
import { McpSession } from "./mcp-session.js";

describe("om_ask MCP tool", () => {
  it("lists om_ask alongside om_recall", async () => {
    const session = new McpSession("/fixture/discovery.json");
    const listed = JSON.parse(
      (await processMcpLine(
        session,
        JSON.stringify({
          jsonrpc: "2.0",
          id: 2,
          method: "tools/list",
        }),
      )) ?? "",
    );

    expect(
      listed.result.tools.map((tool: { name: string }) => tool.name),
    ).toEqual([
      "MemHub_recall",
      "MemHub_ask",
      "MemHub_conversations",
      "MemHub_matters",
      "MemHub_context",
      "MemHub_memory_write",
      "MemHub_memory_write_status",
      "MemHub_diagnostic_trace",
    ]);
    const ask = listed.result.tools.find(
      (tool: { name: string }) => tool.name === "MemHub_ask",
    );
    expect(ask.annotations).toMatchObject({
      readOnlyHint: true,
      destructiveHint: false,
      openWorldHint: false,
    });
  });

  it("forwards question and scope, and injects host workspace_path", async () => {
    const ask = vi.fn(async () => ({
      answer: "现有记忆不足以回答这个问题。",
      memories: [],
      mode: "empty" as const,
    }));
    const session = new McpSession(
      "/fixture/discovery.json",
      undefined,
      "/Users/example/hy-memory-admin",
      ask,
    );

    const response = JSON.parse(
      (await processMcpLine(
        session,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "ask-1",
          method: "tools/call",
          params: {
            name: "om_ask",
            arguments: { question: "我下周的航班是什么？", scope: "all-apps" },
          },
        }),
      )) ?? "",
    );

    expect(ask).toHaveBeenCalledWith("/fixture/discovery.json", {
      question: "我下周的航班是什么？",
      scope: "all-apps",
      workspace_path: "/Users/example/hy-memory-admin",
    });
    // Refuse must pass through unchanged — the bridge must not invent an answer.
    expect(response.result.structuredContent).toEqual({
      answer: "现有记忆不足以回答这个问题。",
      memories: [],
      mode: "empty",
    });
  });

  it("rejects unknown om_ask arguments the same way om_recall does", async () => {
    const session = new McpSession("/fixture/discovery.json");
    const invalid = JSON.parse(
      (await processMcpLine(
        session,
        JSON.stringify({
          jsonrpc: "2.0",
          id: 9,
          method: "tools/call",
          params: {
            name: "om_ask",
            arguments: { question: "x", invent: true },
          },
        }),
      )) ?? "",
    );
    expect(invalid.error.code).toBe(-32602);
  });
});
