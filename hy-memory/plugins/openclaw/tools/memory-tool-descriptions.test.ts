import { describe, expect, it } from "vitest";
import { createMemoryDeleteTool } from "./memory-delete.ts";
import { createMemorySearchTool } from "./memory-search.ts";
import { createMemoryUpdateTool } from "./memory-update.ts";
import type { ToolDeps } from "./index.ts";

const deps = {
  cfg: {
    serverUrl: "http://127.0.0.1:19527",
    userId: "test-user",
    agentId: "test-agent",
    sessionId: "test-session",
    autoRecall: true,
    autoCapture: true,
    topK: 10,
    searchThreshold: 0,
    profileLimit: 5,
    profileMinScore: 0,
    pythonPath: "python3",
    autoStartServer: false,
    serverPort: 19527,
    memoryWriteTurnWindow: 5,
  },
  provider: {},
  api: {},
} as ToolDeps;

describe("memory tool descriptions", () => {
  it("guides delete requests through search and update/delete decision rules", () => {
    const search = createMemorySearchTool(deps);
    const update = createMemoryUpdateTool(deps);
    const del = createMemoryDeleteTool(deps);

    // search guides user to inspect before deciding
    expect(search.description).toContain("still leaves a complete memory, use memory_update");
    expect(search.description).toContain("otherwise use memory_delete");

    // update: only when remaining content is complete
    expect(update.description).toContain("delete request targets only part of an existing memory");
    expect(update.description).toContain("remaining content after removal is still a complete");

    // delete: entire memory or incomplete residual
    expect(del.description).toContain("first call memory_search to find the target memory");
    expect(del.description).toContain("entire memory should be removed");
    expect(del.description).toContain("incomplete/meaningless residual text");
  });
});
