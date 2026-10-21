import type { SourceResponse } from "@one-memory/contracts";
import { describe, expect, it } from "vitest";
import {
  buildSourceSyncRequest,
  hasSourceSyncTarget,
  SourceSyncInputError,
} from "./source-sync-operation";

function source(patch: Partial<SourceResponse> = {}): SourceResponse {
  return {
    source_id: "codex",
    display_name: "Codex",
    storage_kinds: ["jsonl"],
    available: true,
    authorized: true,
    detected: true,
    root_label: "current label",
    candidate_path: "/PRIVATE/current-path",
    candidate_kind: "user_selected",
    imported_messages: 0,
    imported_conversations: 0,
    capabilities: {
      historical_import: "implemented",
      incremental_import: "implemented",
      live_sync: "implemented",
      recall: "implemented",
      installer: "implemented",
      verification: "fixture_only",
    },
    sync_completeness: "full_dynamic",
    sync_enabled: false,
    ...patch,
  };
}

describe("source sync operation", () => {
  it("builds the same final-state request for every client", () => {
    expect(buildSourceSyncRequest(source(), true)).toEqual({
      path: "/api/v1/sources/codex/sync-permission",
      body: { enabled: true },
    });
  });

  it("carries pause and resume as the boolean Core expects", () => {
    expect(buildSourceSyncRequest(source(), false).body.enabled).toBe(false);
    expect(buildSourceSyncRequest(source(), true).body.enabled).toBe(true);
  });

  it("refuses a missing source id", () => {
    expect(() =>
      buildSourceSyncRequest(source({ source_id: "" }), true),
    ).toThrow(SourceSyncInputError);
  });

  it("requires authorization and an implemented live-sync capability", () => {
    expect(hasSourceSyncTarget(source())).toBe(true);
    expect(hasSourceSyncTarget(source({ authorized: false }))).toBe(false);
    expect(
      hasSourceSyncTarget(
        source({
          capabilities: {
            ...source().capabilities,
            live_sync: "not_implemented",
          },
        }),
      ),
    ).toBe(false);
  });
});
