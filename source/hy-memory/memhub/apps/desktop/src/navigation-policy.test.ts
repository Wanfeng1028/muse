import { describe, expect, it } from "vitest";

import { isAllowedNavigation } from "./navigation-policy";

const developmentUrl = "http://127.0.0.1:5173";

describe("navigation policy", () => {
  it("allows only the app origin in packaged builds", () => {
    expect(
      isAllowedNavigation("one-memory://app/settings", {
        packaged: true,
        developmentUrl,
      }),
    ).toBe(true);
    expect(
      isAllowedNavigation("https://attacker.example", {
        packaged: true,
        developmentUrl,
      }),
    ).toBe(false);
  });

  it("allows only the configured dev origin during development", () => {
    expect(
      isAllowedNavigation("http://127.0.0.1:5173/settings", {
        packaged: false,
        developmentUrl,
      }),
    ).toBe(true);
    expect(
      isAllowedNavigation("http://localhost:5173/settings", {
        packaged: false,
        developmentUrl,
      }),
    ).toBe(false);
  });
});
