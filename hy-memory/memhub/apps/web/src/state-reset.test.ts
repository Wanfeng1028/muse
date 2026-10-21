// @vitest-environment jsdom

// No per-file reset here on purpose: only the shared test setup runs between
// these tests, so whatever the first one leaves behind reaches the second.
import { expect, it, vi } from "vitest";
import { saveConnectionPreferences } from "./connection-preferences";
import { autoReconcile } from "./connection-reconcile";
import type { RecallHostStatus } from "./global";
import { refreshRecallHosts } from "./host-state";

type Bridge = NonNullable<typeof window.oneMemory>;

const notInstalled = {
  hostId: "cursor",
  label: "Cursor",
  present: true,
  installed: false,
  permission: {
    hostId: "cursor",
    state: "not-installed",
    reason: null,
    receipt: null,
  },
  selfCheck: null,
  skillDrift: null,
} as RecallHostStatus;

function hanging(): Promise<never> {
  return new Promise(() => {});
}

it("leaves an automatic apply hanging at the end of a test", async () => {
  saveConnectionPreferences({ syncSourceIds: [], hostSourceIds: ["cursor"] });
  window.oneMemory = {
    getRecallHosts: vi
      .fn()
      .mockResolvedValueOnce([notInstalled])
      .mockImplementation(hanging),
    previewRecallInstall: vi.fn(hanging),
    installRecall: vi.fn(),
    getRecallPermission: vi.fn(),
    setRecallPermission: vi.fn(),
  } as unknown as Bridge;
  await refreshRecallHosts();
  void autoReconcile({ sources: [] });
  await new Promise((done) => setTimeout(done, 0));
  window.localStorage.clear();
  window.oneMemory = undefined;
});

it("starts the next test's apply instead of joining the previous one", async () => {
  saveConnectionPreferences({ syncSourceIds: [], hostSourceIds: ["cursor"] });
  const previewRecallInstall = vi.fn(async () => {
    throw Error("connection_client_unavailable");
  });
  window.oneMemory = {
    getRecallHosts: vi.fn(async () => [notInstalled]),
    previewRecallInstall,
    installRecall: vi.fn(),
    getRecallPermission: vi.fn(),
    setRecallPermission: vi.fn(),
  } as unknown as Bridge;
  await refreshRecallHosts();
  const failures = await Promise.race([
    autoReconcile({ sources: [] }),
    new Promise<"joined">((done) => setTimeout(() => done("joined"), 200)),
  ]);
  expect(failures).not.toBe("joined");
  expect(previewRecallInstall).toHaveBeenCalledTimes(1);
  window.localStorage.clear();
  window.oneMemory = undefined;
});
