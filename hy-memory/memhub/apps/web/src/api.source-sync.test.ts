// @vitest-environment jsdom

import type { SourceResponse } from "@one-memory/contracts";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fake = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("axios", () => ({
  default: {
    create: () => ({ ...fake, interceptors: { request: { use: vi.fn() } } }),
  },
}));

import { setSourceSync } from "./api";

const source: SourceResponse = {
  source_id: "codex",
  display_name: "Codex",
  storage_kinds: ["jsonl"],
  available: true,
  authorized: true,
  detected: true,
  root_label: "sessions",
  candidate_path: "~/.codex/sessions",
  candidate_kind: "default",
  imported_messages: 0,
  imported_conversations: 0,
  sync_completeness: "additions_only",
  capabilities: {
    historical_import: "implemented",
    incremental_import: "implemented",
    live_sync: "implemented",
    recall: "implemented",
    installer: "implemented",
    verification: "fixture_only",
  },
  root_id: `root:v2:${"a".repeat(64)}`,
  grant_revision: 3,
  sync_enabled: false,
};

beforeEach(() => {
  vi.resetAllMocks();
});

describe("source sync API integration", () => {
  it("posts only the requested state and returns Core's state", async () => {
    fake.post.mockResolvedValue({
      data: { source_id: "codex", sync_enabled: true },
    });
    await expect(setSourceSync(source, true)).resolves.toEqual({
      source_id: "codex",
      sync_enabled: true,
    });
    expect(fake.post).toHaveBeenCalledExactlyOnceWith(
      "/api/v1/sources/codex/sync-permission",
      { enabled: true },
      undefined,
    );
  });

  it("forwards the interaction trace only as request metadata", async () => {
    fake.post.mockResolvedValue({
      data: { source_id: "codex", sync_enabled: false },
    });
    await setSourceSync(source, false, "trace-1");
    expect(fake.post).toHaveBeenCalledWith(
      "/api/v1/sources/codex/sync-permission",
      { enabled: false },
      { headers: { "X-One-Memory-Trace-Id": "trace-1" } },
    );
  });

  it.each([
    { source_id: "other", sync_enabled: true },
    { source_id: "codex", sync_enabled: false },
  ])("rejects a mismatched state response %#", async (data) => {
    fake.post.mockResolvedValue({ data });
    await expect(setSourceSync(source, true)).rejects.toThrow(
      "source_sync_response_invalid",
    );
  });

  it("rejects an unauthorized source before transport", async () => {
    await expect(
      setSourceSync({ ...source, authorized: false }, true),
    ).rejects.toThrow("source_not_authorized");
    expect(fake.post).not.toHaveBeenCalled();
  });
});
