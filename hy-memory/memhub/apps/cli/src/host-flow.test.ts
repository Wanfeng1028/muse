import { describe, expect, it } from "vitest";
import {
  approvalFingerprint,
  hostExitCode,
  isWriteOperation,
  renderHostText,
} from "./host-flow.js";

const DIGEST = "a".repeat(64);

describe("host flow", () => {
  it("separates operations that change a host from ones that read it", () => {
    // The two-phase rule depends on this split: a preview must never be
    // classified as the change it is previewing.
    expect(isWriteOperation("install")).toBe(true);
    expect(isWriteOperation("uninstall")).toBe(true);
    expect(isWriteOperation("applySkillSync")).toBe(true);
    expect(isWriteOperation("previewInstall")).toBe(false);
    expect(isWriteOperation("previewUninstall")).toBe(false);
    expect(isWriteOperation("getPermission")).toBe(false);
  });

  it("accepts only a real sha-256 fingerprint as an approval", () => {
    expect(approvalFingerprint({ fingerprint: DIGEST })).toBe(DIGEST);
    // A shortened or edited fingerprint must not be treated as approval.
    expect(approvalFingerprint({ fingerprint: "a".repeat(63) })).toBeNull();
    expect(approvalFingerprint({ fingerprint: "not-hex" })).toBeNull();
    expect(approvalFingerprint({})).toBeNull();
    expect(approvalFingerprint(null)).toBeNull();
  });

  it("tells the user a preview changed nothing", () => {
    const text = renderHostText({
      schema_version: 1,
      product: "one-memory",
      command: "status",
      host_id: "codex",
      operation: "previewInstall",
      result: { hostId: "codex", files: [], fingerprint: DIGEST },
    });
    expect(text).toContain("未改动任何文件");
    expect(text).toContain(DIGEST);
  });

  it("lists hosts with their installed state", () => {
    const text = renderHostText({
      schema_version: 1,
      product: "one-memory",
      command: "list",
      hosts: [
        { host_id: "codex", label: "Codex", present: true },
        { host_id: "cursor", label: "Cursor", present: false },
      ],
    });
    expect(text).toContain("可连接的应用");
    expect(text).toContain("Codex：已接入");
    expect(text).toContain("Cursor：未接入");
    expect(text).not.toContain("codex");
  });

  it("reports a machine with no hosts rather than an empty table", () => {
    const text = renderHostText({
      schema_version: 1,
      product: "one-memory",
      command: "list",
      hosts: [],
    });
    expect(text).toContain("未发现");
  });

  it("maps document state onto exit codes", () => {
    // 2 is usage, so a bad host id must not look like a failed operation.
    expect(
      hostExitCode({
        schema_version: 1,
        product: "one-memory",
        command: "status",
        state: "invalid",
        code: "invalid_host_id",
      }),
    ).toBe(2);
    expect(
      hostExitCode({
        schema_version: 1,
        product: "one-memory",
        command: "status",
        state: "unavailable",
        code: "runtime_stopped",
      }),
    ).toBe(1);
    expect(
      hostExitCode({
        schema_version: 1,
        product: "one-memory",
        command: "status",
        host_id: "codex",
        operation: "getPermission",
        result: {},
      }),
    ).toBe(0);
  });
});
