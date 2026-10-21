import { describe, expect, it } from "vitest";

import { createWindowOptions } from "./window-options";

describe("desktop security defaults", () => {
  it("uses a spacious desktop frame and fits smaller displays", () => {
    expect(
      createWindowOptions(undefined, { x: 0, y: 0, width: 1920, height: 1080 }),
    ).toMatchObject({ width: 1440, height: 960 });
    const small = createWindowOptions(undefined, {
      x: -900,
      y: 30,
      width: 900,
      height: 700,
    });
    expect(small.width).toBeLessThanOrEqual(860);
    expect(small.height).toBeLessThanOrEqual(660);
    expect(small.minWidth).toBeLessThanOrEqual(small.width ?? 0);
    expect(small.x).toBeGreaterThanOrEqual(-900);
  });
  it("keeps renderer isolation enabled", () => {
    const options = createWindowOptions("/bundle/preload.js");

    expect(options.webPreferences).toMatchObject({
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: "/bundle/preload.js",
    });
  });
});
