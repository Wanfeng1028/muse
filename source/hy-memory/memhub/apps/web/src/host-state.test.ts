// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import type { RecallHostStatus, RecallPermissionStatus } from "./global";
import {
  cachedRecallHosts,
  disconnectHost,
  refreshRecallHosts,
  setHostMemoryPermission,
} from "./host-state";
import { queryClient } from "./query-client";

type Bridge = NonNullable<typeof window.oneMemory>;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function permission(
  revision: number,
  status: "install-only" | "approved" | "revoked",
  installationId = "install-1",
): RecallPermissionStatus {
  return {
    hostId: "cursor",
    state: status,
    reason: null,
    receipt: {
      hostId: "cursor",
      installationId,
      revision,
      status,
      allowedTools: status === "approved" ? ["om_recall"] : [],
      allowedScopes: status === "approved" ? ["all-apps"] : [],
    },
  };
}

function host(
  installed: boolean,
  grant: RecallPermissionStatus = permission(1, "install-only"),
): RecallHostStatus {
  return {
    hostId: "cursor",
    label: "Cursor",
    present: true,
    installed,
    permission: grant,
    selfCheck: null,
    skillDrift: null,
  };
}

function bridge(members: Partial<Bridge>) {
  window.oneMemory = members as Bridge;
  return members;
}

afterEach(() => {
  vi.useRealTimers();
  window.oneMemory = undefined;
});

describe("host writes run one at a time per host", () => {
  it("does not start a second write for a host until the first has settled", async () => {
    const first = deferred<RecallPermissionStatus>();
    const getRecallPermission = vi
      .fn()
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValue(permission(2, "approved"));
    bridge({
      getRecallHosts: vi.fn(async () => [host(true)]),
      getRecallPermission,
      setRecallPermission: vi.fn(async () => permission(2, "approved")),
      revokeRecallPermission: vi.fn(async () => permission(3, "revoked")),
    });
    await refreshRecallHosts();
    const enabling = setHostMemoryPermission({
      hostId: "cursor",
      sourceId: "cursor",
      enabled: true,
    });
    const revoking = setHostMemoryPermission({
      hostId: "cursor",
      sourceId: "cursor",
      enabled: false,
    });
    await new Promise((done) => setTimeout(done, 0));
    expect(getRecallPermission).toHaveBeenCalledTimes(1);
    first.resolve(permission(1, "install-only"));
    await enabling;
    await revoking;
    expect(getRecallPermission).toHaveBeenCalledTimes(2);
  });
});

describe("an older copy never replaces a newer one", () => {
  it("keeps a granted permission when a read that began before the grant lands after it", async () => {
    const late = deferred<RecallHostStatus[]>();
    const getRecallHosts = vi
      .fn()
      .mockResolvedValueOnce([host(true)])
      .mockImplementationOnce(() => late.promise);
    bridge({
      getRecallHosts,
      getRecallPermission: vi.fn(async () => permission(1, "install-only")),
      setRecallPermission: vi.fn(async () => permission(2, "approved")),
    });
    await refreshRecallHosts();
    const reading = refreshRecallHosts();
    await setHostMemoryPermission({
      hostId: "cursor",
      sourceId: "cursor",
      enabled: true,
    });
    late.resolve([host(true, permission(1, "install-only"))]);
    await reading;
    expect(cachedRecallHosts()?.[0]?.permission?.receipt?.revision).toBe(2);
  });

  it("keeps an uninstall when a read that began before it lands after it", async () => {
    const late = deferred<RecallHostStatus[]>();
    const getRecallHosts = vi
      .fn()
      .mockResolvedValueOnce([host(true)])
      .mockImplementationOnce(() => late.promise);
    bridge({
      getRecallHosts,
      previewRecallUninstall: vi.fn(async () => ({
        hostId: "cursor",
        fingerprint: "fp",
      })) as unknown as Bridge["previewRecallUninstall"],
      uninstallRecall: vi.fn(async () => ({
        hostId: "cursor",
        installed: false,
      })) as unknown as Bridge["uninstallRecall"],
    });
    await refreshRecallHosts();
    const reading = refreshRecallHosts();
    await disconnectHost("cursor");
    late.resolve([host(true)]);
    await reading;
    expect(cachedRecallHosts()?.[0]?.installed).toBe(false);
  });

  it("does not take a receipt with a lower revision of the same installation", async () => {
    bridge({
      getRecallHosts: vi.fn(async () => [
        host(true, permission(3, "approved")),
      ]),
      getRecallPermission: vi.fn(async () => permission(1, "install-only")),
      setRecallPermission: vi.fn(async () => permission(2, "approved")),
    });
    await refreshRecallHosts();
    await setHostMemoryPermission({
      hostId: "cursor",
      sourceId: "cursor",
      enabled: true,
    });
    expect(cachedRecallHosts()?.[0]?.permission?.receipt?.revision).toBe(3);
  });
});

describe("host writes leave nothing behind", () => {
  it("keeps no finished write in the mutation cache", async () => {
    bridge({
      getRecallHosts: vi.fn(async () => [host(true)]),
      getRecallPermission: vi.fn(async () => permission(1, "install-only")),
      setRecallPermission: vi.fn(async () => permission(2, "approved")),
    });
    await refreshRecallHosts();
    for (let round = 0; round < 3; round += 1)
      await setHostMemoryPermission({
        hostId: "cursor",
        sourceId: "cursor",
        enabled: true,
      });
    await new Promise((done) => setTimeout(done, 0));
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
  });
});

describe("a failed disconnect keeps its real reason", () => {
  const unavailable =
    "Error invoking remote method 'one-memory:uninstall-recall': Error: host_control_unavailable";

  it("names the desktop's reason when neither removal nor revocation went through", async () => {
    bridge({
      getRecallHosts: vi.fn(async () => [host(true)]),
      previewRecallUninstall: vi.fn(async () => {
        throw Error(unavailable);
      }),
      getRecallPermission: vi.fn(async () => {
        throw Error(unavailable);
      }),
      revokeRecallPermission: vi.fn(),
    });
    await refreshRecallHosts();
    const { outcome } = await disconnectHost("cursor");
    expect(outcome).toMatchObject({
      state: "failed",
      reason: "应用控制通道暂不可用",
      rereadFailed: false,
    });
  });

  it("says so separately when the re-read after the failure also failed", async () => {
    const getRecallHosts = vi
      .fn()
      .mockResolvedValueOnce([host(true)])
      .mockRejectedValue(Error("ipc gone"));
    bridge({
      getRecallHosts,
      previewRecallUninstall: vi.fn(async () => {
        throw Error(unavailable);
      }),
      getRecallPermission: vi.fn(async () => {
        throw Error(unavailable);
      }),
      revokeRecallPermission: vi.fn(),
    });
    await refreshRecallHosts();
    const { outcome } = await disconnectHost("cursor");
    expect(outcome).toMatchObject({ state: "failed", rereadFailed: true });
  });
});

describe("a disconnect that cannot be confirmed", () => {
  it("neither calls it off nor failed, names the place to check, and still revokes the grant", async () => {
    const finding = {
      path: "/home/me/.cursor/hooks.json",
      where: "hooks.stop[1].command",
    };
    const uninstallRecall = vi.fn();
    const revokeRecallPermission = vi.fn(async () => permission(2, "revoked"));
    bridge({
      getRecallHosts: vi.fn(async () => [host(true)]),
      previewRecallUninstall: vi.fn(async () => ({
        hostId: "cursor",
        hostLabel: "Cursor",
        files: [],
        review: [finding],
        fingerprint: "fp",
      })),
      uninstallRecall: uninstallRecall as unknown as Bridge["uninstallRecall"],
      getRecallPermission: vi.fn(async () => permission(1, "install-only")),
      revokeRecallPermission,
    });
    await refreshRecallHosts();
    const { outcome } = await disconnectHost("cursor");
    expect(outcome).toMatchObject({ state: "review", findings: [finding] });
    expect(uninstallRecall).not.toHaveBeenCalled();
    expect(revokeRecallPermission).toHaveBeenCalledTimes(1);
  });
});

describe("a host read that never answers", () => {
  it("gives up after the read timeout and ignores the late answer", async () => {
    vi.useFakeTimers();
    const late = deferred<RecallHostStatus[]>();
    const getRecallHosts = vi
      .fn()
      .mockResolvedValueOnce([host(true)])
      .mockImplementationOnce(() => late.promise);
    bridge({ getRecallHosts });
    await refreshRecallHosts();
    let settled: "pending" | "resolved" | "rejected" = "pending";
    const reading = refreshRecallHosts().then(
      () => {
        settled = "resolved";
      },
      () => {
        settled = "rejected";
      },
    );
    await vi.advanceTimersByTimeAsync(15_000);
    expect(settled).toBe("rejected");
    late.resolve([host(false)]);
    await vi.advanceTimersByTimeAsync(0);
    await reading;
    expect(cachedRecallHosts()?.[0]?.installed).toBe(true);
  });
});
