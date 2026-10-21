import { describe, expect, it } from "vitest";
import {
  buildSourceImportRequest,
  SourceImportInputError,
} from "./source-import-operation";

const REQUEST = "11111111-2222-4333-8444-555555555555";
const ROOT = `root:v2:${"a".repeat(64)}`;

describe("source import operation", () => {
  it("always sends the CLI plan fields including its sync decision", () => {
    const { path, body } = buildSourceImportRequest({
      sourceIds: ["codex"],
      sourceRoots: { codex: ROOT },
      sourceCandidateRevisions: { codex: 2 },
      confirmEnvironmentOverrides: false,
      fullRescan: false,
      onboarding: true,
      enableSync: true,
      requestId: REQUEST,
    });
    expect(path).toBe("/api/v1/sources/connect");
    expect(body).toStrictEqual({
      source_ids: ["codex"],
      source_roots: { codex: ROOT },
      source_candidate_revisions: { codex: 2 },
      confirm_environment_overrides: false,
      full_rescan: false,
      onboarding: true,
      enable_sync: true,
      request_id: REQUEST,
    });
    // request_id and source_roots are always present, never conditional.
    expect(Object.keys(body)).toEqual(
      expect.arrayContaining(["request_id", "source_roots"]),
    );
  });

  it("defaults the optional booleans exactly like the CLI's false/onboarding plan", () => {
    const { body } = buildSourceImportRequest(
      { sourceIds: ["codex"], requestId: REQUEST },
      () => REQUEST,
    );
    expect(body).toMatchObject({
      confirm_environment_overrides: false,
      full_rescan: false,
      onboarding: false,
      enable_sync: false,
      source_roots: {},
      source_candidate_revisions: {},
    });
  });

  it("mints a request id only when the caller did not supply one", () => {
    const minted = buildSourceImportRequest(
      { sourceIds: ["codex"] },
      () => REQUEST,
    );
    expect(minted.body.request_id).toBe(REQUEST);
    expect(() =>
      buildSourceImportRequest({ sourceIds: ["codex"], requestId: "nope" }),
    ).toThrow("request_id_invalid");
  });

  it("adds import_upload_id only when a caller has one", () => {
    const without = buildSourceImportRequest(
      { sourceIds: ["codex"], requestId: REQUEST },
      () => REQUEST,
    );
    expect(without.body).not.toHaveProperty("import_upload_id");
    const withUpload = buildSourceImportRequest(
      { sourceIds: ["codex"], requestId: REQUEST, importUploadId: "u1" },
      () => REQUEST,
    );
    expect(withUpload.body.import_upload_id).toBe("u1");
  });

  it("fails closed on an empty set or metadata for an unlisted source", () => {
    expect(() => buildSourceImportRequest({ sourceIds: [] })).toThrow(
      SourceImportInputError,
    );
    expect(() =>
      buildSourceImportRequest({
        sourceIds: ["codex"],
        requestId: REQUEST,
        sourceRoots: { cursor: ROOT },
      }),
    ).toThrow("source_metadata_unknown_source");
    expect(() =>
      buildSourceImportRequest({
        sourceIds: Array.from({ length: 33 }, (_, index) => `s${index}`),
        requestId: REQUEST,
      }),
    ).toThrow("source_ids_too_many");
  });
});
