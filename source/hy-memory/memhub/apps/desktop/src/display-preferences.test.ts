import { describe, expect, it, vi } from "vitest";
import { DisplayPreferences } from "./display-preferences";

describe("native display preference observations", () => {
  it.each([
    [false, false],
    [false, true],
    [true, false],
    [true, true],
  ])(
    "keeps simulated motion=%s and transparency=%s independent",
    (reduceMotion, reduceTransparency) => {
      const motion = vi.fn(() => reduceMotion);
      const transparency = vi.fn(() => reduceTransparency);
      const preferences = new DisplayPreferences(motion, transparency);
      expect(preferences.read()).toEqual({
        reduceMotion,
        reduceTransparency,
        revision: 0,
      });
      expect(preferences.read()).toEqual({
        reduceMotion,
        reduceTransparency,
        revision: 0,
      });
      expect(motion).toHaveBeenCalledTimes(2);
      expect(transparency).toHaveBeenCalledTimes(2);
    },
  );

  it("starts with no data, caches partial knowledge and recovers without false values", () => {
    const motion = vi.fn<() => unknown>(() => {
      throw new Error("unsupported");
    });
    const transparency = vi.fn<() => unknown>(() => undefined);
    const preferences = new DisplayPreferences(motion, transparency);
    expect(preferences.read()).toBeNull();
    motion.mockReturnValue(true);
    expect(preferences.read()).toBeNull();
    motion.mockImplementation(() => {
      throw new Error("temporary failure");
    });
    transparency.mockReturnValue(false);
    expect(preferences.read()).toEqual({
      reduceMotion: true,
      reduceTransparency: false,
      revision: 0,
    });
  });

  it("preserves last-known true on failure while the other dimension changes", () => {
    const motion = vi.fn<() => unknown>(() => true);
    const transparency = vi.fn<() => unknown>(() => true);
    const preferences = new DisplayPreferences(motion, transparency);
    expect(preferences.read()).toEqual({
      reduceMotion: true,
      reduceTransparency: true,
      revision: 0,
    });
    motion.mockImplementation(() => {
      throw new Error("unavailable");
    });
    transparency.mockReturnValue(false);
    expect(preferences.read()).toEqual({
      reduceMotion: true,
      reduceTransparency: false,
      revision: 1,
    });
    motion.mockReturnValue("false");
    transparency.mockReturnValue(null);
    expect(preferences.read()).toEqual({
      reduceMotion: true,
      reduceTransparency: false,
      revision: 1,
    });
    motion.mockReturnValue(false);
    expect(preferences.read()).toEqual({
      reduceMotion: false,
      reduceTransparency: false,
      revision: 2,
    });
  });

  it("does not let consumers mutate its cached observation", () => {
    const preferences = new DisplayPreferences(
      () => false,
      () => true,
    );
    const value = preferences.read();
    if (!value) throw new Error("expected complete snapshot");
    value.reduceMotion = true;
    value.revision = 100;
    expect(preferences.read()).toEqual({
      reduceMotion: false,
      reduceTransparency: true,
      revision: 0,
    });
  });
});
