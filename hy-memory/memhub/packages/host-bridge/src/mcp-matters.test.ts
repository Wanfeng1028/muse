import { expect, it, vi } from "vitest";
import { McpSession } from "./mcp-session.js";

it("exposes read-only matter context without letting a model grant access", async () => {
  const read = vi.fn().mockResolvedValue([]);
  const session = new McpSession(
    "/test/discovery.json",
    undefined,
    undefined,
    undefined,
    undefined,
    read,
  );
  const response = await session.handle({
    jsonrpc: "2.0",
    id: 1,
    method: "tools/call",
    params: { name: "om_matters", arguments: { query: "Atlas" } },
  });
  expect(read).toHaveBeenCalledWith("/test/discovery.json", { query: "Atlas" });
  expect(response?.result).toMatchObject({
    structuredContent: { contexts: [] },
  });
  const invalid = await session.handle({
    jsonrpc: "2.0",
    id: 2,
    method: "tools/call",
    params: {
      name: "om_matters",
      arguments: { query: "Atlas", agent_access: true },
    },
  });
  expect(invalid?.error?.code).toBe(-32602);
  expect(read).toHaveBeenCalledTimes(1);
});
