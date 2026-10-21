// A3-02: the MCP write tools.
//
// The point of these tools is not that they exist, but that they hand back a
// durable id instead of writing synchronously. A host that thinks the write
// completed on return would resubmit on the next turn, and HY has no
// idempotency key (A0-03), so a resubmit would duplicate the memory.

import { describe, expect, it, vi } from "vitest";

import { processMcpLine } from "./mcp-protocol.js";
import { McpSession, type MemoryWriteRequest } from "./mcp-session.js";

/** Build a session whose only wired tools are the write ones.
 *
 * The read tools are given stubs that reject, so a test that accidentally
 * dispatches to one fails loudly instead of silently returning nothing. Only
 * the two tools under test are injected.
 */
function sessionWith(
  write: (path: string, request: MemoryWriteRequest) => Promise<unknown>,
  status: (path: string, id: string) => Promise<unknown>,
): McpSession {
  const unwired = async () => {
    throw new Error("read tool is not wired in this test");
  };
  return new McpSession(
    "/tmp/discovery.json",
    unwired as never,
    undefined,
    unwired as never,
    unwired as never,
    unwired as never,
    unwired as never,
    write as never,
    status as never,
  );
}

async function initialize(session: McpSession) {
  await processMcpLine(
    session,
    JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: "2025-03-26", capabilities: {} },
    }),
  );
}

describe("om_memory_write MCP tool", () => {
  it("is listed alongside the read tools", async () => {
    const session = sessionWith(
      async () => ({ request_id: "r1", state: "accepted" }),
      async () => null,
    );
    await initialize(session);
    const listed = await processMcpLine(
      session,
      JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list" }),
    );
    const tools = JSON.parse(listed ?? "{}").result.tools as {
      name: string;
    }[];
    expect(tools.map((tool) => tool.name)).toContain("MemHub_memory_write");
    expect(tools.map((tool) => tool.name)).toContain(
      "MemHub_memory_write_status",
    );
  });

  it("returns the durable request id instead of writing synchronously", async () => {
    const write = vi.fn(async () => ({
      request_id: "req-42",
      state: "accepted",
      created_at: "2026",
      updated_at: "2026",
      detail: "",
    }));
    const session = sessionWith(write, async () => null);
    await initialize(session);

    const response = await processMcpLine(
      session,
      JSON.stringify({
        jsonrpc: "2.0",
        id: 3,
        method: "tools/call",
        params: {
          name: "MemHub_memory_write",
          arguments: {
            internal_session_id: "sess-1",
            first_round: 1,
            last_round: 5,
            evidence_ids: ["e1"],
          },
        },
      }),
    );
    const payload = JSON.parse(response ?? "{}").result.structuredContent as {
      request_id: string;
      state: string;
    };
    expect(payload.request_id).toBe("req-42");
    expect(payload.state).toBe("accepted");
  });

  it("rejects a write with no evidence before any round trip", async () => {
    const write = vi.fn(async () => ({ request_id: "never" }));
    const session = sessionWith(write, async () => null);
    await initialize(session);

    const response = await processMcpLine(
      session,
      JSON.stringify({
        jsonrpc: "2.0",
        id: 4,
        method: "tools/call",
        params: {
          name: "MemHub_memory_write",
          arguments: {
            internal_session_id: "sess-1",
            first_round: 1,
            last_round: 5,
            evidence_ids: [],
          },
        },
      }),
    );
    expect(write).not.toHaveBeenCalled();
    expect(JSON.parse(response ?? "{}").error.code).toBe(-32602);
  });

  it("rejects a descending round range", async () => {
    const write = vi.fn(async () => ({ request_id: "never" }));
    const session = sessionWith(write, async () => null);
    await initialize(session);

    const response = await processMcpLine(
      session,
      JSON.stringify({
        jsonrpc: "2.0",
        id: 5,
        method: "tools/call",
        params: {
          name: "MemHub_memory_write",
          arguments: {
            internal_session_id: "sess-1",
            first_round: 5,
            last_round: 1,
            evidence_ids: ["e1"],
          },
        },
      }),
    );
    expect(write).not.toHaveBeenCalled();
    expect(JSON.parse(response ?? "{}").error).toBeDefined();
  });

  it("passes a never-accepted status through as null rather than an error", async () => {
    const status = vi.fn(async () => null);
    const session = sessionWith(async () => ({ request_id: "r" }), status);
    await initialize(session);

    const response = await processMcpLine(
      session,
      JSON.stringify({
        jsonrpc: "2.0",
        id: 6,
        method: "tools/call",
        params: {
          name: "MemHub_memory_write_status",
          arguments: { request_id: "unknown-id" },
        },
      }),
    );
    expect(status).toHaveBeenCalledWith("/tmp/discovery.json", "unknown-id");
    const result = JSON.parse(response ?? "{}").result;
    expect(result.isError).toBeFalsy();
    expect(result.structuredContent).toBeNull();
  });
});
