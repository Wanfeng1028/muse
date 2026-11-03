import { randomUUID } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import type { BackgroundOperationSnapshot } from "./background-operation.js";
import { BackgroundPreviewService } from "./background-preview-service.js";
import { runtimeInstallLayout } from "./service-plan.js";

const owner = { userId: "local", runtimeId: "stable" };
const layout = runtimeInstallLayout({
  platform: "darwin",
  home: "/Users/example",
  installRoot: "/Users/example/runtime/current",
});
function fixture() {
  const ledger = {
    load: vi.fn(async (): Promise<BackgroundOperationSnapshot | null> => null),
  };
  const verify = vi.fn(async () => ({
    digest: "a".repeat(64),
    version: "1.0.0",
    root: "/Users/example/runtime/versions/1.0.0-darwin-arm64",
  }));
  return {
    ledger,
    verify,
    service: new BackgroundPreviewService(owner, layout, 501, ledger, verify),
  };
}
function snapshot(state: "committed" | "unknown"): BackgroundOperationSnapshot {
  return {
    schemaVersion: 1,
    ...owner,
    revision: 3,
    operations: [
      {
        operationId: randomUUID(),
        expectedRevision: 0,
        action: "enable",
        planDigest: "a".repeat(64),
        artifactDigest: "a".repeat(64),
        state,
        code: null,
      },
    ],
  };
}
describe("background read-only preview", () => {
  it("returns bounded public intent after two revision reads with no writes", async () => {
    const f = fixture();
    const preview = await f.service.preview({ startAtLogin: true });
    expect(preview.intent.expectedRevision).toBe(0);
    expect(preview.startAtLogin).toBe(true);
    expect(JSON.stringify(preview)).not.toContain("/Users");
    expect(f.ledger.load).toHaveBeenCalledTimes(2);
  });
  it.each([
    null,
    {},
    { startAtLogin: true, dataDir: "/other" },
    { startAtLogin: "true" },
  ])("rejects untrusted fields before I/O", async (input) => {
    const f = fixture();
    await expect(f.service.preview(input)).rejects.toThrow("invalid");
    expect(f.verify).not.toHaveBeenCalled();
    expect(f.ledger.load).not.toHaveBeenCalled();
  });
  it("rejects a revision changed during artifact verification", async () => {
    const f = fixture();
    f.ledger.load
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(snapshot("committed"));
    await expect(f.service.preview({ startAtLogin: false })).rejects.toThrow(
      "revision_changed",
    );
  });
  it("does not create a new preview while a prior operation is unknown", async () => {
    const f = fixture();
    f.ledger.load.mockResolvedValue(snapshot("unknown"));
    await expect(f.service.preview({ startAtLogin: true })).rejects.toThrow(
      "pending",
    );
    expect(f.verify).not.toHaveBeenCalled();
  });
});
