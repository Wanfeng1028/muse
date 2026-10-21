import { describe, expect, it } from "vitest";

import { CORE_SERVICE } from "./index";

describe("Core contract", () => {
  it("has one stable service identity", () => {
    expect(CORE_SERVICE).toBe("one-memory-core");
  });
});
