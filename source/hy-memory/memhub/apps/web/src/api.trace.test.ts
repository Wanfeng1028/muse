import { expect, it, vi } from "vitest";

import { createTraceId } from "./api";

it("creates a canonical correlation UUID when Web Crypto is unavailable", () => {
  const random = vi.fn(() => 0.5);
  const value = createTraceId(random);
  expect(value).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
});
