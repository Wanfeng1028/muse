import { describe, expect, it } from "vitest";

import { DEFAULT_CORE_URL, isHealthResponse } from "./api";

describe("Core API contract", () => {
  it("defaults to the local-only Core address", () => {
    expect(DEFAULT_CORE_URL).toBe("http://127.0.0.1:8765");
  });

  it("rejects an old or unrelated health payload", () => {
    expect(
      isHealthResponse({
        status: "ok",
        service: "one-memory-core",
        version: "0.0.0",
      }),
    ).toBe(false);
  });
});
