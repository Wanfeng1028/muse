import { describe, expect, it } from "vitest";
import {
  buildMemoryNoteSaveRequest,
  MemoryNoteInputError,
  parseMemoryNoteReceipt,
} from "./memory-note-operation";

const ID = "11111111-2222-4333-8444-555555555555";

describe("memory note save request", () => {
  it("sends exactly request_id, text and the fixed scope", () => {
    expect(
      buildMemoryNoteSaveRequest({
        request_id: ID,
        text: "raw note",
        scope: "all-apps",
      }),
    ).toEqual({
      path: "/api/v1/memory-notes",
      body: { request_id: ID, text: "raw note", scope: "all-apps" },
    });
  });

  it("refuses a bad request id or empty text", () => {
    expect(() =>
      buildMemoryNoteSaveRequest({
        request_id: "nope",
        text: "x",
        scope: "all-apps",
      }),
    ).toThrow("request_id_invalid");
    expect(() =>
      buildMemoryNoteSaveRequest({
        request_id: ID,
        text: "   ",
        scope: "all-apps",
      }),
    ).toThrow(MemoryNoteInputError);
  });
});

describe("memory note receipt validation", () => {
  function receipt(patch: Record<string, unknown> = {}) {
    return {
      evidence_id: ID,
      text: "raw note",
      scope: "all-apps",
      created_at: "2026-09-13T00:00:00+00:00",
      state: "pending",
      task_id: null,
      memory_ids: [],
      ...patch,
    };
  }

  it("accepts a well-formed receipt", () => {
    expect(parseMemoryNoteReceipt(receipt())?.state).toBe("pending");
  });

  it("refuses a non-UUID evidence id or an unknown state", () => {
    expect(parseMemoryNoteReceipt(receipt({ evidence_id: "nope" }))).toBeNull();
    expect(parseMemoryNoteReceipt(receipt({ state: "invented" }))).toBeNull();
  });

  it("refuses a wrong scope or malformed memory_ids", () => {
    expect(parseMemoryNoteReceipt(receipt({ scope: "private" }))).toBeNull();
    expect(parseMemoryNoteReceipt(receipt({ memory_ids: [1] }))).toBeNull();
    expect(
      parseMemoryNoteReceipt(receipt({ memory_ids: undefined })),
    ).toBeNull();
  });

  it("refuses a non-object body", () => {
    for (const value of [null, [], "ok", 7]) {
      expect(parseMemoryNoteReceipt(value)).toBeNull();
    }
  });
});
