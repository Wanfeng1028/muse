import { describe, expect, it, vi } from "vitest";

import type {
  CoreDeleteOperations,
  CoreOperations,
} from "./core-operations.js";
import {
  executeCallEventsClear,
  executeCallEventsClearAll,
  executeImportFileCommit,
  executeImportFileDiscard,
  planCallEventsClear,
  planCallEventsClearAll,
  planImportFileCommit,
  planImportFileDiscard,
  planImportFileUpload,
  validateUiWritePlan,
} from "./ui-write-flows.js";

const EVENT = "11111111-1111-4111-8111-111111111111";
const UPLOAD = "22222222-2222-4222-8222-222222222222";

function planOf(value: ReturnType<typeof planCallEventsClear>) {
  if (value.state !== "preview") throw new Error("expected preview");
  return value.plan;
}

describe("UI write plans", () => {
  it("permits only valid call-event ids and rejects duplicates", () => {
    expect(planCallEventsClear([EVENT]).state).toBe("preview");
    expect(planCallEventsClear([]).state).toBe("invalid");
    expect(planCallEventsClear([EVENT, EVENT]).state).toBe("invalid");
  });

  it("plans all remaining UI write operations", () => {
    expect(planCallEventsClearAll().state).toBe("preview");
    expect(planImportFileCommit(UPLOAD).state).toBe("preview");
    expect(planImportFileDiscard(UPLOAD).state).toBe("preview");
    expect(
      planImportFileUpload({
        path: "/tmp/export.json",
        bytes: 42,
        sha256: "a".repeat(64),
        inputKind: "raw_conversation",
      }).state,
    ).toBe("preview");
  });

  it("rejects a tampered plan digest", async () => {
    const plan = planOf(planCallEventsClear([EVENT]));
    expect(validateUiWritePlan(plan)).toEqual(plan);
    expect(validateUiWritePlan({ ...plan, event_ids: [UPLOAD] })).toBeNull();
  });
});

describe("UI write execution", () => {
  it("posts clear with Core's confirmation field", async () => {
    const post = vi.fn(async () => ({
      state: "committed" as const,
      data: { removed: 1 },
    }));
    const plan = planOf(planCallEventsClear([EVENT]));
    if (plan.kind !== "call_events_clear") throw new Error("kind");
    const result = await executeCallEventsClear(plan, {
      post,
    } as unknown as CoreOperations);
    expect(result.state).toBe("committed");
    expect(post).toHaveBeenCalledWith("/api/v1/call-events/clear", {
      event_ids: [EVENT],
      user_confirmed: true,
    });
  });

  it("posts clear-all with Core's confirmation field", async () => {
    const post = vi.fn(async () => ({
      state: "committed" as const,
      data: { removed: 2 },
    }));
    const plan = planOf(planCallEventsClearAll());
    if (plan.kind !== "call_events_clear_all") throw new Error("kind");
    await executeCallEventsClearAll(plan, {
      post,
    } as unknown as CoreOperations);
    expect(post).toHaveBeenCalledWith("/api/v1/call-events/clear-all", {
      user_confirmed: true,
    });
  });

  it("uses POST commit and DELETE discard endpoints", async () => {
    const post = vi.fn(async () => ({
      state: "committed" as const,
      data: {
        upload_id: UPLOAD,
        filename: "x.json",
        vendor: "generic",
        source_id: "generic-export",
        messages: 0,
        conversations: 0,
        human_messages: 0,
        agent_messages: 0,
        skipped_records: 0,
        ignored_files: 0,
        checksum: "a".repeat(64),
        created_at: "T",
        committed: true,
      },
    }));
    const del = vi.fn(async <T>() => ({
      state: "committed" as const,
      data: {} as T,
    }));
    const operations = {
      post,
      delete: del,
    } as unknown as CoreOperations & CoreDeleteOperations;
    const commit = planOf(planImportFileCommit(UPLOAD));
    if (commit.kind !== "import_file_commit") throw new Error("kind");
    await executeImportFileCommit(commit, operations);
    expect(post).toHaveBeenCalledWith(`/api/v1/import-files/${UPLOAD}/commit`, {
      confirmed: true,
    });
    const discard = planOf(planImportFileDiscard(UPLOAD));
    if (discard.kind !== "import_file_discard") throw new Error("kind");
    expect((await executeImportFileDiscard(discard, operations)).state).toBe(
      "committed",
    );
    expect(del).toHaveBeenCalledWith(`/api/v1/import-files/${UPLOAD}`);
  });

  it("treats a malformed success receipt as unknown", async () => {
    const plan = planOf(planCallEventsClear([EVENT]));
    if (plan.kind !== "call_events_clear") throw new Error("kind");
    const result = await executeCallEventsClear(plan, {
      post: vi.fn(async () => ({
        state: "committed" as const,
        data: { wrong: true },
      })),
    } as unknown as CoreOperations);
    expect(result).toMatchObject({
      state: "unknown",
      code: "ui_write_receipt_invalid",
    });
  });
});
