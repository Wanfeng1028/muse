import { describe, expect, it, vi } from "vitest";
import type { CoreReader, ReadOutcome } from "./core-client.js";
import type { CoreOperations, OperationOutcome } from "./core-operations.js";
import {
  renderSourceSyncText,
  setSourceSync,
  sourceSyncExitCode,
} from "./source-sync-flow.js";

const ROOT = `root:v1:${"a".repeat(64)}`;

function source(overrides: Record<string, unknown> = {}) {
  return {
    source_id: "codex",
    display_name: "Codex",
    storage_kinds: ["history"],
    available: true,
    authorized: true,
    detected: true,
    root_label: "Codex history",
    candidate_path: "/synthetic/codex",
    candidate_kind: "default",
    imported_conversations: 7,
    imported_messages: 120,
    capabilities: {
      historical_import: "implemented",
      incremental_import: "implemented",
      live_sync: "implemented",
      recall: "implemented",
      installer: "not_implemented",
      verification: "fixture_only",
    },
    sync_completeness: "additions_only",
    grant_revision: 3,
    root_id: ROOT,
    sync_enabled: true,
    ...overrides,
  };
}

function readerWith(...outcomes: ReadOutcome<unknown>[]) {
  const reader = vi.fn(async () => {
    const outcome = outcomes.shift();
    if (!outcome) throw new Error("unexpected read");
    return outcome;
  });
  return { reader: reader as CoreReader, read: reader };
}

function operationsWith(outcome: OperationOutcome<unknown>) {
  const post = vi.fn(async () => outcome);
  return {
    operations: { post } as CoreOperations,
    post,
  };
}

describe("setSourceSync", () => {
  it.each([
    ["pause", true, false],
    ["resume", false, true],
  ] as const)(
    "%s sends only the requested final state",
    async (action, currentEnabled, requestedEnabled) => {
      const { reader, read } = readerWith({
        state: "ok",
        data: [source({ sync_enabled: currentEnabled })],
      });
      const { operations, post } = operationsWith({
        state: "committed",
        data: { source_id: "codex", sync_enabled: requestedEnabled },
      });

      const document = await setSourceSync(reader, operations, {
        sourceId: "codex",
        action,
      });

      expect(read).toHaveBeenCalledOnce();
      expect(read).toHaveBeenCalledWith("/api/v1/sources");
      expect(post).toHaveBeenCalledOnce();
      expect(post).toHaveBeenCalledWith(
        "/api/v1/sources/codex/sync-permission",
        { enabled: requestedEnabled },
      );
      expect(document).toMatchObject({
        state: "committed",
        source_id: "codex",
        sync_enabled: requestedEnabled,
      });
    },
  );

  it("treats an already-reached final state as idempotent success", async () => {
    const { reader } = readerWith({
      state: "ok",
      data: [source({ sync_enabled: false })],
    });
    const { operations, post } = operationsWith({
      state: "unknown",
      code: "must_not_write",
    });

    const document = await setSourceSync(reader, operations, {
      sourceId: "codex",
      action: "pause",
    });

    expect(post).not.toHaveBeenCalled();
    expect(document).toMatchObject({
      state: "committed",
      source_id: "codex",
      sync_enabled: false,
    });
  });

  it("recovers an unknown POST by reading the final source state", async () => {
    const { reader, read } = readerWith(
      { state: "ok", data: [source({ sync_enabled: false })] },
      { state: "ok", data: [source({ sync_enabled: true })] },
    );
    const { operations } = operationsWith({
      state: "unknown",
      code: "transport_result_unknown",
    });

    const document = await setSourceSync(reader, operations, {
      sourceId: "codex",
      action: "resume",
    });

    expect(read).toHaveBeenCalledTimes(2);
    expect(document).toMatchObject({
      state: "committed",
      source_id: "codex",
      sync_enabled: true,
    });
  });

  it("keeps an unknown POST unknown when the final state was not reached", async () => {
    const { reader } = readerWith(
      { state: "ok", data: [source({ sync_enabled: false })] },
      { state: "ok", data: [source({ sync_enabled: false })] },
    );
    const { operations } = operationsWith({
      state: "unknown",
      code: "transport_result_unknown",
    });

    const document = await setSourceSync(reader, operations, {
      sourceId: "codex",
      action: "resume",
    });

    expect(document).toMatchObject({
      state: "unknown",
      code: "sync_outcome_unknown",
    });
  });

  it("rejects a conflicting write without guessing the final state", async () => {
    const { reader, read } = readerWith({
      state: "ok",
      data: [source()],
    });
    const { operations } = operationsWith({
      state: "rejected",
      code: "source_sync_conflict",
      http_status: 409,
    });

    const document = await setSourceSync(reader, operations, {
      sourceId: "codex",
      action: "pause",
    });

    expect(read).toHaveBeenCalledOnce();
    expect(document).toMatchObject({
      state: "rejected",
      code: "source_sync_conflict",
    });
  });

  it.each([
    [
      "an unauthorized source",
      source({ authorized: false }),
      "source_not_authorized",
    ],
    [
      "a source without live sync",
      source({
        capabilities: {
          historical_import: "implemented",
          incremental_import: "implemented",
          live_sync: "not_implemented",
          recall: "implemented",
          installer: "not_implemented",
          verification: "fixture_only",
        },
      }),
      "live_sync_unavailable",
    ],
  ])("refuses %s before POST", async (_label, fixture, code) => {
    const { reader } = readerWith({ state: "ok", data: [fixture] });
    const { operations, post } = operationsWith({
      state: "unknown",
      code: "must_not_write",
    });

    const document = await setSourceSync(reader, operations, {
      sourceId: "codex",
      action: "pause",
    });

    expect(post).not.toHaveBeenCalled();
    expect(document).toMatchObject({ state: "rejected", code });
  });

  it.each([
    [
      "an unknown source",
      { state: "ok", data: [source()] } as const,
      "nope",
      "source_not_found",
    ],
    [
      "a malformed sources response",
      { state: "ok", data: [{ wrong: true }] } as const,
      "codex",
      "sources_response_invalid",
    ],
    [
      "an unavailable sources read",
      { state: "unavailable", code: "transport_failed" } as const,
      "codex",
      "transport_failed",
    ],
  ])("does not write for %s", async (_label, outcome, sourceId, code) => {
    const { reader } = readerWith(outcome);
    const { operations, post } = operationsWith({
      state: "unknown",
      code: "must_not_write",
    });

    const document = await setSourceSync(reader, operations, {
      sourceId,
      action: "pause",
    });

    expect(post).not.toHaveBeenCalled();
    expect(document).toMatchObject({ code });
  });

  it("rejects an invalid source id before reading Core", async () => {
    const { reader, read } = readerWith({
      state: "ok",
      data: [source()],
    });
    const { operations, post } = operationsWith({
      state: "unknown",
      code: "must_not_write",
    });

    const document = await setSourceSync(reader, operations, {
      sourceId: "../codex",
      action: "pause",
    });

    expect(read).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
    expect(document).toMatchObject({
      state: "invalid",
      code: "invalid_source_id",
    });
  });

  it("refuses a malformed successful POST response", async () => {
    const { reader } = readerWith({
      state: "ok",
      data: [source()],
    });
    const { operations } = operationsWith({
      state: "committed",
      data: { source_id: "codex", sync_enabled: true },
    });

    const document = await setSourceSync(reader, operations, {
      sourceId: "codex",
      action: "pause",
    });

    expect(document).toMatchObject({
      state: "unknown",
      code: "sync_response_invalid",
    });
  });

  it("maps final documents to stable text and exit codes", () => {
    const committed = {
      schema_version: 1,
      product: "one-memory",
      state: "committed",
      source_id: "codex",
      sync_enabled: false,
    } as const;
    const invalid = {
      schema_version: 1,
      product: "one-memory",
      state: "invalid",
      code: "invalid_source_id",
    } as const;

    expect(sourceSyncExitCode(committed)).toBe(0);
    expect(renderSourceSyncText(committed)).toContain("已暂停");
    expect(sourceSyncExitCode(invalid)).toBe(2);
    expect(renderSourceSyncText(invalid)).toBe("未变更：invalid_source_id\n");
  });
});
