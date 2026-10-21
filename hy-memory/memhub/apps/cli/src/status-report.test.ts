import { describe, expect, it } from "vitest";

import { renderStatusText, type StatusDocument } from "./status-report.js";

describe("status default output", () => {
  it("formats blocked task objects recursively instead of printing object coercions", () => {
    const report: StatusDocument = {
      schema_version: 1,
      product: "memhub",
      data_dir: "/tmp/isolated",
      runtime: { state: "running", code: "ok", host: "127.0.0.1", port: 30001 },
      bridge: { state: "healthy", code: "ok" },
      sections: {
        sources: { state: "ok", authorized: 1 },
        sync: { state: "ok", running: 0 },
        processing: {
          state: "ok",
          blocked: [
            { kind: "extract", reason: "waiting_for_model", count: 2 },
            { kind: "extract", reason: "input_too_long", count: 1 },
          ],
        },
        model: { state: "ok", profiles: 1 },
        memories: { state: "ok", memory_count: 8 },
      },
      summary: { state: "ok", degraded: [], not_checked: [] },
    };

    const text = renderStatusText(report, "MemHub");
    expect(text).not.toContain("[object Object]");
    expect(text).toContain("卡住 类型 整理对话/原因 等待模型/数量 2");
    expect(text).not.toMatch(/background_verified|additions_only|error_codes=/);
    expect(text).not.toMatch(
      /provider_kind|has_api_key|credential_state|observed_at/,
    );
  });
});
