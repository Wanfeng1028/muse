// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getNativeDisplayPreferences,
  readDisplayPreference,
  startNativeDisplayPreferences,
  subscribeDisplayPreference,
  subscribeNativeDisplayPreferences,
} from "./display-preferences";

const motion = "(prefers-reduced-motion: reduce)";
const transparency = "(prefers-reduced-transparency: reduce)";
const width = "(max-width: 1100px)";
const disposals: Array<() => void> = [];
let matches: Map<string, boolean>;
let media: Map<
  string,
  {
    addEventListener: ReturnType<typeof vi.fn>;
    removeEventListener: ReturnType<typeof vi.fn>;
    listeners: Set<() => void>;
  }
>;

function own(dispose: () => void) {
  disposals.push(dispose);
  return dispose;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function host(
  initial: unknown = {
    reduceMotion: false,
    reduceTransparency: false,
    revision: 0,
  },
) {
  let listener: (value: unknown) => void = () => {};
  const unsubscribe = vi.fn();
  const api = {
    getDisplayPreferences: vi.fn(() => Promise.resolve(initial)),
    onDisplayPreferencesChanged: vi.fn((callback: (value: unknown) => void) => {
      listener = callback;
      return unsubscribe;
    }),
  };
  vi.stubGlobal("oneMemory", api);
  return { api, unsubscribe, emit: (value: unknown) => listener(value) };
}

function browserChange(query: string, value: boolean) {
  matches.set(query, value);
  for (const listener of media.get(query)?.listeners ?? []) listener();
}

beforeEach(() => {
  matches = new Map();
  media = new Map();
  vi.stubGlobal("oneMemory", undefined);
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => {
      let value = media.get(query);
      if (!value) {
        const listeners = new Set<() => void>();
        value = {
          listeners,
          addEventListener: vi.fn((_type: string, listener: () => void) =>
            listeners.add(listener),
          ),
          removeEventListener: vi.fn((_type: string, listener: () => void) =>
            listeners.delete(listener),
          ),
        };
        media.set(query, value);
      }
      return {
        ...value,
        get matches() {
          return matches.get(query) ?? false;
        },
      };
    }),
  );
});

afterEach(() => {
  for (const dispose of disposals.splice(0).reverse()) dispose();
  vi.unstubAllGlobals();
});

describe("native display preferences store", () => {
  it("starts empty and never contacts IPC merely by reading or subscribing", () => {
    const { api } = host();
    expect(getNativeDisplayPreferences()).toBeNull();
    expect(readDisplayPreference(motion)).toBe(false);
    own(subscribeDisplayPreference(motion, vi.fn()));
    own(subscribeNativeDisplayPreferences(vi.fn()));
    expect(api.getDisplayPreferences).not.toHaveBeenCalled();
    expect(api.onDisplayPreferencesChanged).not.toHaveBeenCalled();
  });

  it.each([
    [false, false, false],
    [false, true, true],
    [true, false, true],
    [true, true, true],
  ])(
    "motion OR: native=%s browser=%s yields %s",
    async (native, browser, expected) => {
      matches.set(motion, browser);
      host({ reduceMotion: native, reduceTransparency: false, revision: 0 });
      own(startNativeDisplayPreferences());
      await Promise.resolve();
      expect(readDisplayPreference(motion)).toBe(expected);
      expect(readDisplayPreference(transparency)).toBe(false);
    },
  );

  it.each([
    [false, false, false],
    [false, true, true],
    [true, false, true],
    [true, true, true],
  ])(
    "transparency OR: native=%s browser=%s yields %s",
    async (native, browser, expected) => {
      matches.set(transparency, browser);
      host({ reduceMotion: false, reduceTransparency: native, revision: 1 });
      own(startNativeDisplayPreferences());
      await Promise.resolve();
      expect(readDisplayPreference(transparency)).toBe(expected);
      expect(readDisplayPreference(motion)).toBe(false);
    },
  );

  it("subscribes before reading and ignores a late lower-revision initial response", async () => {
    const pending = deferred<unknown>();
    const { api, emit } = host();
    api.getDisplayPreferences.mockReturnValue(pending.promise);
    own(startNativeDisplayPreferences());
    expect(
      api.onDisplayPreferencesChanged.mock.invocationCallOrder[0],
    ).toBeLessThan(api.getDisplayPreferences.mock.invocationCallOrder[0]);
    emit({ reduceMotion: true, reduceTransparency: false, revision: 4 });
    pending.resolve({
      reduceMotion: false,
      reduceTransparency: true,
      revision: 2,
    });
    await Promise.resolve();
    expect(getNativeDisplayPreferences()).toEqual({
      reduceMotion: true,
      reduceTransparency: false,
      revision: 4,
    });
  });

  it("preserves one immutable snapshot for duplicate, conflicting equal and stale revisions", async () => {
    const { emit } = host({
      reduceMotion: true,
      reduceTransparency: false,
      revision: 3,
    });
    const notify = vi.fn();
    own(subscribeNativeDisplayPreferences(notify));
    own(startNativeDisplayPreferences());
    await Promise.resolve();
    const snapshot = getNativeDisplayPreferences();
    expect(Object.isFrozen(snapshot)).toBe(true);
    emit({ reduceMotion: true, reduceTransparency: false, revision: 3 });
    emit({ reduceMotion: false, reduceTransparency: true, revision: 3 });
    emit({ reduceMotion: false, reduceTransparency: false, revision: 2 });
    expect(getNativeDisplayPreferences()).toBe(snapshot);
    expect(notify).toHaveBeenCalledTimes(1);
    emit({ reduceMotion: false, reduceTransparency: true, revision: 4 });
    expect(getNativeDisplayPreferences()).not.toBe(snapshot);
    expect(notify).toHaveBeenCalledTimes(2);
  });

  it.each([
    null,
    undefined,
    [],
    {},
    { reduceMotion: "true", reduceTransparency: false, revision: 5 },
    { reduceMotion: true, reduceTransparency: 1, revision: 5 },
    { reduceMotion: true, reduceTransparency: false },
    { reduceMotion: true, reduceTransparency: false, revision: -1 },
    { reduceMotion: true, reduceTransparency: false, revision: 0.5 },
    { reduceMotion: true, reduceTransparency: false, revision: Number.NaN },
    {
      reduceMotion: true,
      reduceTransparency: false,
      revision: Number.POSITIVE_INFINITY,
    },
    {
      reduceMotion: true,
      reduceTransparency: false,
      revision: Number.MAX_SAFE_INTEGER + 1,
    },
  ])("ignores invalid native event and initial payload %j", async (invalid) => {
    const { api, emit } = host();
    api.getDisplayPreferences.mockResolvedValue(invalid);
    const notify = vi.fn();
    own(subscribeNativeDisplayPreferences(notify));
    own(startNativeDisplayPreferences());
    await Promise.resolve();
    expect(getNativeDisplayPreferences()).toBeNull();
    emit({ reduceMotion: false, reduceTransparency: true, revision: 1 });
    const saved = getNativeDisplayPreferences();
    emit(invalid);
    expect(saved).toEqual({
      reduceMotion: false,
      reduceTransparency: true,
      revision: 1,
    });
    expect(getNativeDisplayPreferences()).toBe(saved);
    expect(notify).toHaveBeenCalledOnce();
  });

  it("copies only display fields instead of retaining a mutable native object", async () => {
    const incoming = {
      reduceMotion: true,
      reduceTransparency: false,
      revision: 1,
      extra: "not retained",
    };
    host(incoming);
    own(startNativeDisplayPreferences());
    await Promise.resolve();
    incoming.reduceMotion = false;
    expect(getNativeDisplayPreferences()).toEqual({
      reduceMotion: true,
      reduceTransparency: false,
      revision: 1,
    });
  });

  it("refcounts explicit owners, unsubscribes once on the last stop and resets the snapshot", async () => {
    const { api, emit, unsubscribe } = host({
      reduceMotion: true,
      reduceTransparency: true,
      revision: 7,
    });
    const first = own(startNativeDisplayPreferences());
    const second = own(startNativeDisplayPreferences());
    await Promise.resolve();
    expect(api.getDisplayPreferences).toHaveBeenCalledOnce();
    expect(api.onDisplayPreferencesChanged).toHaveBeenCalledOnce();
    first();
    first();
    expect(unsubscribe).not.toHaveBeenCalled();
    expect(readDisplayPreference(motion)).toBe(true);
    second();
    second();
    expect(unsubscribe).toHaveBeenCalledOnce();
    expect(getNativeDisplayPreferences()).toBeNull();
    emit({ reduceMotion: true, reduceTransparency: true, revision: 8 });
    expect(getNativeDisplayPreferences()).toBeNull();
  });

  it("never lets disposed responses or native events enter the next session", async () => {
    const pending = deferred<unknown>();
    const old = host();
    old.api.getDisplayPreferences.mockReturnValue(pending.promise);
    const stopOld = own(startNativeDisplayPreferences());
    stopOld();
    const fresh = host({
      reduceMotion: false,
      reduceTransparency: true,
      revision: 0,
    });
    own(startNativeDisplayPreferences());
    await Promise.resolve();
    pending.resolve({
      reduceMotion: true,
      reduceTransparency: false,
      revision: 100,
    });
    old.emit({ reduceMotion: true, reduceTransparency: false, revision: 101 });
    await Promise.resolve();
    expect(getNativeDisplayPreferences()).toEqual({
      reduceMotion: false,
      reduceTransparency: true,
      revision: 0,
    });
    fresh.emit({ reduceMotion: true, reduceTransparency: true, revision: 1 });
    expect(getNativeDisplayPreferences()?.reduceMotion).toBe(true);
  });

  it("uses browser fallback when the bridge is absent or its initial read rejects", async () => {
    matches.set(motion, true);
    const stop = own(startNativeDisplayPreferences());
    expect(readDisplayPreference(motion)).toBe(true);
    stop();
    const { api, emit } = host();
    api.getDisplayPreferences.mockRejectedValueOnce(
      new Error("old shell unavailable"),
    );
    own(startNativeDisplayPreferences());
    await Promise.resolve();
    expect(getNativeDisplayPreferences()).toBeNull();
    expect(readDisplayPreference(motion)).toBe(true);
    emit({ reduceMotion: false, reduceTransparency: true, revision: 1 });
    expect(readDisplayPreference(transparency)).toBe(true);
  });

  it("retains known true values when the delayed initial request rejects", async () => {
    const pending = deferred<unknown>();
    const { api, emit } = host();
    api.getDisplayPreferences.mockReturnValue(pending.promise);
    own(startNativeDisplayPreferences());
    emit({ reduceMotion: true, reduceTransparency: true, revision: 1 });
    const snapshot = getNativeDisplayPreferences();
    pending.reject(new Error("display_preferences_unavailable"));
    await Promise.resolve();
    expect(getNativeDisplayPreferences()).toBe(snapshot);
    expect(readDisplayPreference(motion)).toBe(true);
    expect(readDisplayPreference(transparency)).toBe(true);
  });

  it("handles throwing legacy bridge methods and cleanup without breaking media fallback", async () => {
    const { api } = host();
    api.onDisplayPreferencesChanged.mockImplementationOnce(() => {
      throw new Error("subscribe unavailable");
    });
    api.getDisplayPreferences.mockImplementationOnce(() => {
      throw new Error("read unavailable");
    });
    const stop = own(startNativeDisplayPreferences());
    expect(stop).not.toThrow();
    expect(getNativeDisplayPreferences()).toBeNull();
    const next = host();
    next.unsubscribe.mockImplementationOnce(() => {
      throw new Error("disposed shell");
    });
    const nextStop = own(startNativeDisplayPreferences());
    await Promise.resolve();
    expect(nextStop).not.toThrow();
    expect(getNativeDisplayPreferences()).toBeNull();
  });

  it("native subscriptions are independent, idempotently removable, and never open IPC", async () => {
    const { emit } = host();
    own(startNativeDisplayPreferences());
    await Promise.resolve();
    const notify = vi.fn();
    const one = own(subscribeNativeDisplayPreferences(notify));
    const two = own(subscribeNativeDisplayPreferences(notify));
    one();
    one();
    emit({ reduceMotion: true, reduceTransparency: false, revision: 1 });
    expect(notify).toHaveBeenCalledOnce();
    two();
    emit({ reduceMotion: false, reduceTransparency: false, revision: 2 });
    expect(notify).toHaveBeenCalledOnce();
  });

  it("only applies native values to the two reduce queries and preserves width changes", async () => {
    host({ reduceMotion: true, reduceTransparency: true, revision: 1 });
    own(startNativeDisplayPreferences());
    await Promise.resolve();
    const notify = vi.fn();
    const stop = own(subscribeDisplayPreference(width, notify));
    expect(readDisplayPreference(width)).toBe(false);
    expect(readDisplayPreference("(prefers-color-scheme: dark)")).toBe(false);
    browserChange(width, true);
    expect(readDisplayPreference(width)).toBe(true);
    expect(notify).toHaveBeenCalledOnce();
    stop();
    stop();
    expect(media.get(width)?.removeEventListener).toHaveBeenCalledOnce();
  });

  it("notifies effective changes only and OR prevents either input clearing the other", async () => {
    const { emit } = host();
    const stopNative = own(startNativeDisplayPreferences());
    await Promise.resolve();
    const notify = vi.fn();
    const stop = own(subscribeDisplayPreference(motion, notify));
    emit({ reduceMotion: false, reduceTransparency: true, revision: 1 });
    expect(notify).not.toHaveBeenCalled();
    emit({ reduceMotion: true, reduceTransparency: true, revision: 2 });
    expect(notify).toHaveBeenCalledTimes(1);
    browserChange(motion, true);
    emit({ reduceMotion: false, reduceTransparency: false, revision: 3 });
    expect(readDisplayPreference(motion)).toBe(true);
    expect(notify).toHaveBeenCalledTimes(1);
    browserChange(motion, false);
    expect(notify).toHaveBeenCalledTimes(2);
    emit({ reduceMotion: true, reduceTransparency: false, revision: 4 });
    stopNative();
    expect(notify).toHaveBeenCalledTimes(4);
    stop();
    browserChange(motion, true);
    expect(notify).toHaveBeenCalledTimes(4);
  });

  it("keeps native reduction usable when matchMedia is unavailable", async () => {
    vi.stubGlobal("matchMedia", undefined);
    const { emit } = host();
    const notify = vi.fn();
    own(subscribeDisplayPreference(transparency, notify));
    own(startNativeDisplayPreferences());
    await Promise.resolve();
    emit({ reduceMotion: false, reduceTransparency: true, revision: 1 });
    expect(readDisplayPreference(transparency)).toBe(true);
    expect(readDisplayPreference(width)).toBe(false);
    expect(notify).toHaveBeenCalledOnce();
  });
});
