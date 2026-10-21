// @vitest-environment jsdom

import { afterEach, expect, it, vi } from "vitest";

const bridge = vi.hoisted(() => ({
  preferences: null as null | {
    reduceMotion: boolean;
    reduceTransparency: boolean;
    revision: number;
  },
  listener: null as null | (() => void),
  start: vi.fn(),
  stop: vi.fn(),
  unsubscribe: vi.fn(),
}));
vi.mock("./display-preferences", () => ({
  getNativeDisplayPreferences: () => bridge.preferences,
  subscribeNativeDisplayPreferences: (listener: () => void) => {
    bridge.listener = listener;
    return bridge.unsubscribe;
  },
  startNativeDisplayPreferences: () => {
    bridge.start();
    return bridge.stop;
  },
}));

import { installNativeDisplayStyles } from "./native-display-styles";

afterEach(() => {
  bridge.preferences = null;
  bridge.listener = null;
  delete document.documentElement.dataset.nativeReduceMotion;
  delete document.documentElement.dataset.nativeReduceTransparency;
  document.body.className = "";
  vi.clearAllMocks();
});

it("reflects the two native dimensions independently without changing app preferences", () => {
  document.body.className = "reduce-transparency";
  const stop = installNativeDisplayStyles();
  expect(bridge.start).toHaveBeenCalledOnce();
  expect(document.documentElement.dataset.nativeReduceMotion).toBe("false");
  bridge.preferences = {
    reduceMotion: true,
    reduceTransparency: false,
    revision: 1,
  };
  bridge.listener?.();
  expect(document.documentElement.dataset.nativeReduceMotion).toBe("true");
  expect(document.documentElement.dataset.nativeReduceTransparency).toBe(
    "false",
  );
  bridge.preferences = {
    reduceMotion: false,
    reduceTransparency: true,
    revision: 2,
  };
  bridge.listener?.();
  expect(document.documentElement.dataset.nativeReduceMotion).toBe("false");
  expect(document.documentElement.dataset.nativeReduceTransparency).toBe(
    "true",
  );
  expect(document.body.className).toBe("reduce-transparency");
  stop();
  expect(
    document.documentElement.hasAttribute("data-native-reduce-motion"),
  ).toBe(false);
  expect(bridge.unsubscribe).toHaveBeenCalledOnce();
  expect(bridge.stop).toHaveBeenCalledOnce();
});

it("restores prior document attributes when the bootstrap owner is disposed", () => {
  document.documentElement.dataset.nativeReduceMotion = "previous";
  const stop = installNativeDisplayStyles();
  stop();
  expect(document.documentElement.dataset.nativeReduceMotion).toBe("previous");
  expect(
    document.documentElement.dataset.nativeReduceTransparency,
  ).toBeUndefined();
});
