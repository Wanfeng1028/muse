import { access, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  appOwnedRuntimeShouldStop,
  claimRuntimeServiceForApp,
  claimRuntimeServiceForCli,
  disableRuntimeService,
  enableRuntimeService,
  readRuntimeServiceOwner,
  runtimeServiceEnableMarkerPath,
  setAppRuntimeStartAtLogin,
} from "./service-ownership.js";

describe("managed Runtime service ownership", () => {
  it("keeps a CLI claim when the App later opens", async () => {
    const dataDir = await mkdtemp(path.join(os.tmpdir(), "memhub-owner-"));
    await claimRuntimeServiceForCli(dataDir);

    const owner = await claimRuntimeServiceForApp({
      dataDir,
      appBundle: "/Applications/MemHub.app",
      appExecutable: "/Applications/MemHub.app/Contents/MacOS/MemHub",
    });

    expect(owner).toEqual({ schema_version: 1, owner: "cli" });
    expect(await readRuntimeServiceOwner(dataDir)).toEqual(owner);
  });

  it("persists the App login-start preference without changing ownership", async () => {
    const dataDir = await mkdtemp(path.join(os.tmpdir(), "memhub-owner-"));
    await claimRuntimeServiceForApp({
      dataDir,
      appBundle: "/Applications/MemHub.app",
      appExecutable: "/Applications/MemHub.app/Contents/MacOS/MemHub",
    });

    await expect(
      setAppRuntimeStartAtLogin(dataDir, false),
    ).resolves.toMatchObject({ owner: "app", start_at_login: false });
    await expect(
      claimRuntimeServiceForApp({
        dataDir,
        appBundle: "/Applications/MemHub.app",
        appExecutable: "/Applications/MemHub.app/Contents/MacOS/MemHub",
      }),
    ).resolves.toMatchObject({ owner: "app", start_at_login: false });
  });

  it("stops an App-owned Runtime only after the App disappears", async () => {
    const dataDir = await mkdtemp(path.join(os.tmpdir(), "memhub-owner-"));
    await claimRuntimeServiceForApp({
      dataDir,
      appBundle: "/Applications/MemHub.app",
      appExecutable: "/Applications/MemHub.app/Contents/MacOS/MemHub",
    });
    await enableRuntimeService(dataDir);
    const present = new Set([
      runtimeServiceEnableMarkerPath(dataDir),
      "/Applications/MemHub.app",
      "/Applications/MemHub.app/Contents/MacOS/MemHub",
    ]);

    const inspect = () =>
      appOwnedRuntimeShouldStop({
        dataDir,
        exists: async (target) => present.has(target),
      });
    await expect(inspect()).resolves.toBe(false);
    present.delete("/Applications/MemHub.app");
    await expect(inspect()).resolves.toBe(true);
    present.add("/Applications/MemHub.app");
    present.delete(runtimeServiceEnableMarkerPath(dataDir));
    await expect(inspect()).resolves.toBe(false);
  });

  it("never stops a CLI-owned Runtime when the GUI App disappears", async () => {
    const dataDir = await mkdtemp(path.join(os.tmpdir(), "memhub-owner-"));
    await claimRuntimeServiceForCli(dataDir);
    await enableRuntimeService(dataDir);

    await expect(
      appOwnedRuntimeShouldStop({
        dataDir,
        exists: async (target) =>
          target === runtimeServiceEnableMarkerPath(dataDir),
      }),
    ).resolves.toBe(false);
  });

  it("creates and removes the launchd enable marker", async () => {
    const dataDir = await mkdtemp(path.join(os.tmpdir(), "memhub-owner-"));
    const marker = runtimeServiceEnableMarkerPath(dataDir);
    await enableRuntimeService(dataDir);
    await expect(access(marker)).resolves.toBeUndefined();
    await disableRuntimeService(dataDir);
    await expect(access(marker)).rejects.toMatchObject({ code: "ENOENT" });
    await rm(dataDir, { recursive: true, force: true });
  });
});
