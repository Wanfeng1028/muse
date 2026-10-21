// @vitest-environment jsdom

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { startNativeDisplayPreferences } from "./display-preferences";
import { useMediaPreference } from "./use-media-preference";

const motion = "(prefers-reduced-motion: reduce)";
const transparency = "(prefers-reduced-transparency: reduce)";
const width = "(max-width: 1100px)";
let stopNative: (() => void) | undefined;
let listener: (value: {
  reduceMotion: boolean;
  reduceTransparency: boolean;
  revision: number;
}) => void;
let matches: Map<string, boolean>;
let listeners: Map<string, Set<() => void>>;
let unsubscribe: ReturnType<typeof vi.fn>;

beforeEach(() => {
  listener = () => {};
  matches = new Map();
  listeners = new Map();
  unsubscribe = vi.fn();
  vi.stubGlobal("oneMemory", {
    getDisplayPreferences: vi.fn().mockResolvedValue({
      reduceMotion: false,
      reduceTransparency: false,
      revision: 0,
    }),
    onDisplayPreferencesChanged: vi.fn((callback) => {
      listener = callback;
      return unsubscribe;
    }),
  });
  vi.stubGlobal("matchMedia", (query: string) => {
    if (!listeners.has(query)) listeners.set(query, new Set());
    return {
      get matches() {
        return matches.get(query) ?? false;
      },
      addEventListener: (_type: string, callback: () => void) =>
        listeners.get(query)?.add(callback),
      removeEventListener: (_type: string, callback: () => void) =>
        listeners.get(query)?.delete(callback),
    };
  });
});

afterEach(() => {
  cleanup();
  stopNative?.();
  stopNative = undefined;
  vi.unstubAllGlobals();
});

it("updates existing hooks for independent native dimensions without remounting", async () => {
  const { result } = renderHook(() => [
    useMediaPreference(motion),
    useMediaPreference(transparency),
  ]);
  await act(async () => {
    stopNative = startNativeDisplayPreferences();
  });
  expect(result.current).toEqual([false, false]);
  act(() =>
    listener({ reduceMotion: true, reduceTransparency: false, revision: 1 }),
  );
  expect(result.current).toEqual([true, false]);
  act(() =>
    listener({ reduceMotion: false, reduceTransparency: true, revision: 2 }),
  );
  expect(result.current).toEqual([false, true]);
});

it("resubscribes query changes and keeps width browser-only", async () => {
  await act(async () => {
    stopNative = startNativeDisplayPreferences();
  });
  act(() =>
    listener({ reduceMotion: true, reduceTransparency: true, revision: 1 }),
  );
  const { result, rerender, unmount } = renderHook(
    ({ query }) => useMediaPreference(query),
    { initialProps: { query: motion } },
  );
  expect(result.current).toBe(true);
  rerender({ query: width });
  expect(result.current).toBe(false);
  expect(listeners.get(motion)?.size).toBe(0);
  act(() => {
    matches.set(width, true);
    for (const notify of listeners.get(width) ?? []) notify();
  });
  expect(result.current).toBe(true);
  unmount();
  expect(listeners.get(width)?.size).toBe(0);
  expect(unsubscribe).not.toHaveBeenCalled();
  stopNative?.();
  expect(unsubscribe).toHaveBeenCalledOnce();
});

it("falls back to browser preference after bootstrap teardown without losing the subscription", async () => {
  const { result } = renderHook(() => useMediaPreference(motion));
  await act(async () => {
    stopNative = startNativeDisplayPreferences();
  });
  act(() =>
    listener({ reduceMotion: true, reduceTransparency: false, revision: 1 }),
  );
  expect(result.current).toBe(true);
  act(() => stopNative?.());
  expect(result.current).toBe(false);
  act(() => {
    matches.set(motion, true);
    for (const notify of listeners.get(motion) ?? []) notify();
  });
  expect(result.current).toBe(true);
});

it("keeps media fallback in old shells and without matchMedia", () => {
  vi.stubGlobal("oneMemory", undefined);
  matches.set(width, true);
  const first = renderHook(() => useMediaPreference(width));
  expect(first.result.current).toBe(true);
  first.unmount();
  vi.stubGlobal("matchMedia", undefined);
  const second = renderHook(() => useMediaPreference(motion));
  expect(second.result.current).toBe(false);
});
