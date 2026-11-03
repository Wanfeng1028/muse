import type { SourceResponse } from "@one-memory/contracts";
import { describe, expect, it } from "vitest";
import { connectionSourceMetadata } from "./connection-source-metadata.js";

const ERROR = "connection_setup_invalid_core_metadata";

function source(): SourceResponse {
  return {
    source_id: "cursor",
    display_name: "Cursor",
    candidate_path: "/fixture/cursor",
    candidate_kind: "user_selected",
    available: true,
    authorized: true,
    detected: true,
    root_label: "Selected Cursor",
    root_id: "root-1",
    candidate_root_id: "root-1",
    grant_revision: 3,
    sync_enabled: false,
    location_state: "found",
    imported_messages: 12,
    imported_conversations: 2,
    storage_kinds: ["sqlite", "jsonl"],
    capabilities: {
      historical_import: "implemented",
      incremental_import: "implemented",
      live_sync: "implemented",
      recall: "implemented",
      installer: "implemented",
      verification: "real_replayed",
    },
    sync_completeness: "full_dynamic",
  };
}

describe("connectionSourceMetadata", () => {
  it("projects exactly the existing metadata contract without arbitrary response keys", () => {
    const expected = source();
    const input = {
      ...expected,
      candidate_revision: 4,
      private_payload: { value: "not metadata" },
    };
    const result = connectionSourceMetadata([input]);
    expect(result).toStrictEqual([expected]);
    expect(result[0]).not.toBe(input);
    expect(input.candidate_revision).toBe(4);
    expect(input.private_payload).toEqual({ value: "not metadata" });
    expect(connectionSourceMetadata([])).toEqual([]);
  });

  it("preserves optional fields and does not infer authorization or resolve paths", () => {
    const input = source();
    delete input.root_id;
    delete input.candidate_root_id;
    delete input.grant_revision;
    delete input.location_state;
    input.root_label = null;
    input.detected = null;
    input.authorized = false;
    input.available = false;
    input.candidate_path = "relative/unchanged";
    expect(connectionSourceMetadata([input])).toStrictEqual([
      {
        ...input,
        root_id: undefined,
        candidate_root_id: undefined,
        grant_revision: undefined,
        location_state: undefined,
      },
    ]);
  });

  it.each([null, undefined, {}, "sources", 1, [null], [[]]])(
    "rejects malformed source collection %j with the fixed error",
    (input) => {
      expect(() => connectionSourceMetadata(input)).toThrow(new Error(ERROR));
    },
  );

  it("bounds sources and rejects duplicate identities", () => {
    const sources = Array.from({ length: 256 }, (_, i) => ({
      ...source(),
      source_id: `source-${i}`,
    }));
    expect(connectionSourceMetadata(sources)).toHaveLength(256);
    expect(() => connectionSourceMetadata([...sources, source()])).toThrow(
      ERROR,
    );
    expect(() => connectionSourceMetadata([source(), source()])).toThrow(ERROR);
  });

  it.each(["", "Cursor", "../cursor", "cursor_1", "a".repeat(129), 1, null])(
    "rejects invalid source id %j",
    (source_id) => {
      expect(() =>
        connectionSourceMetadata([{ ...source(), source_id }]),
      ).toThrow(new Error(ERROR));
    },
  );

  it.each(["authorized", "available", "detected", "sync_enabled"])(
    "requires boolean %s (detected alone permits null)",
    (field) => {
      for (const value of ["true", 1, [], {}]) {
        expect(() =>
          connectionSourceMetadata([{ ...source(), [field]: value }]),
        ).toThrow(ERROR);
      }
      if (field !== "detected") {
        expect(() =>
          connectionSourceMetadata([{ ...source(), [field]: null }]),
        ).toThrow(ERROR);
      }
    },
  );

  it.each([
    "grant_revision",
    "candidate_revision",
    "imported_messages",
    "imported_conversations",
  ])("requires nonnegative safe integers for %s", (field) => {
    for (const value of [
      -1,
      0.5,
      NaN,
      Infinity,
      Number.MAX_SAFE_INTEGER + 1,
      "1",
      null,
    ]) {
      expect(() =>
        connectionSourceMetadata([{ ...source(), [field]: value }]),
      ).toThrow(new Error(ERROR));
    }
    for (const value of [0, Number.MAX_SAFE_INTEGER]) {
      expect(() =>
        connectionSourceMetadata([{ ...source(), [field]: value }]),
      ).not.toThrow();
    }
  });

  it.each([
    "imported_messages",
    "imported_conversations",
    "detected",
    "authorized",
    "available",
  ])("rejects a missing required %s", (field) => {
    const input: Record<string, unknown> = { ...source() };
    delete input[field];
    expect(() => connectionSourceMetadata([input])).toThrow(ERROR);
  });

  it.each([
    "display_name",
    "candidate_path",
    "root_id",
    "candidate_root_id",
    "root_label",
  ])("bounds and sanitizes %s without echoing input", (field) => {
    for (const value of ["x".repeat(4097), "private\nvalue", "bad\u007f", 4]) {
      expect(() =>
        connectionSourceMetadata([{ ...source(), [field]: value }]),
      ).toThrow(new Error(ERROR));
    }
    expect(() =>
      connectionSourceMetadata([{ ...source(), [field]: "x".repeat(4096) }]),
    ).not.toThrow();
  });

  it.each([
    ["candidate_kind", ["default", "environment_override", "user_selected"]],
    ["location_state", ["found", "not_found", "inaccessible", "invalid"]],
    [
      "sync_completeness",
      ["full_dynamic", "additions_only", "one_time_snapshot"],
    ],
  ] as const)("validates the %s enum without coercion", (field, values) => {
    for (const value of values) {
      expect(
        connectionSourceMetadata([{ ...source(), [field]: value }])[0][field],
      ).toBe(value);
    }
    for (const value of [
      "unknown",
      null,
      [values[0]],
      { toString: () => values[0] },
    ]) {
      expect(() =>
        connectionSourceMetadata([{ ...source(), [field]: value }]),
      ).toThrow(ERROR);
    }
  });

  it("requires the exact capability keys and valid values", () => {
    for (const capabilities of [
      null,
      [],
      {},
      { ...source().capabilities, extra: "implemented" },
    ]) {
      expect(() =>
        connectionSourceMetadata([{ ...source(), capabilities }]),
      ).toThrow(ERROR);
    }
    for (const key of Object.keys(source().capabilities)) {
      const caps: Record<string, unknown> = { ...source().capabilities };
      delete caps[key];
      expect(() =>
        connectionSourceMetadata([{ ...source(), capabilities: caps }]),
      ).toThrow(ERROR);
      for (const value of [
        true,
        "unknown",
        [source().capabilities[key as keyof SourceResponse["capabilities"]]],
      ]) {
        expect(() =>
          connectionSourceMetadata([
            {
              ...source(),
              capabilities: { ...source().capabilities, [key]: value },
            },
          ]),
        ).toThrow(ERROR);
      }
    }
    const input = source();
    input.capabilities = {
      historical_import: "not_implemented",
      incremental_import: "not_implemented",
      live_sync: "not_implemented",
      recall: "not_implemented",
      installer: "not_implemented",
      verification: "fixture_only",
    };
    expect(connectionSourceMetadata([input])).toEqual([input]);
  });

  it("bounds storage kinds and validates each text value", () => {
    for (const storage_kinds of [
      null,
      "sqlite",
      Array(33).fill("sqlite"),
      [2],
      ["bad\t"],
      ["x".repeat(65)],
    ]) {
      expect(() =>
        connectionSourceMetadata([{ ...source(), storage_kinds }]),
      ).toThrow(ERROR);
    }
    expect(() =>
      connectionSourceMetadata([
        {
          ...source(),
          storage_kinds: Array(32).fill("x".repeat(64)),
        },
      ]),
    ).not.toThrow();
  });
});
