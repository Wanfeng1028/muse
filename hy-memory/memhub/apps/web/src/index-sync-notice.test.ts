import { describe, expect, it } from "vitest";
import { indexSyncPresentation } from "./index-sync-notice";

const sync = (
  patch: Partial<Parameters<typeof indexSyncPresentation>[0]> = {},
) => ({
  memory_id: "memory-1",
  status: "pending" as const,
  attempts: 1,
  last_error_code: null,
  updated_at: "2026-09-01T00:00:00Z",
  ...patch,
});

describe("indexSyncPresentation", () => {
  it("offers retry after an unknown transient failure", () => {
    expect(
      indexSyncPresentation(
        sync({ last_error_code: "hy_memory_update_failed" }),
        "09/01 08:00",
      ),
    ).toMatchObject({
      action: "retry",
      explanation: expect.stringContaining("最近一次同步未成功"),
    });
  });

  it("does not pretend an unstarted sync has failed", () => {
    expect(
      indexSyncPresentation(
        sync({ attempts: 0, last_error_code: null }),
        "09/01 08:00",
      ),
    ).toMatchObject({
      action: "retry",
      attemptedLine: expect.stringContaining("尚未尝试同步"),
    });
  });

  it("sends a missing model to configuration and never offers blind retry", () => {
    expect(
      indexSyncPresentation(
        sync({ attempts: 0, last_error_code: "model_profile_not_active" }),
        "09/01 08:00",
      ),
    ).toMatchObject({ action: "configure" });
  });

  it("sends a changed version or permission to refresh", () => {
    expect(
      indexSyncPresentation(
        sync({ last_error_code: "context_changed" }),
        "09/01 08:00",
      ),
    ).toMatchObject({ action: "refresh" });
  });

  it("keeps a rejected HY record out of the retry loop", () => {
    expect(
      indexSyncPresentation(
        sync({ attempts: 4, last_error_code: "hy_memory_update_rejected" }),
        "09/01 08:00",
      ),
    ).toMatchObject({
      action: "none",
      explanation: expect.stringContaining("仅重试同步不能补齐"),
    });
  });
});
