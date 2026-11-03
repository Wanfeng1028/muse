import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  claimRuntimeServiceForApp,
  claimRuntimeServiceForCli,
  enableRuntimeService,
  readRuntimeServiceOwner,
  runtimeServiceEnabled,
} from "@one-memory/runtime-control";
import { expect, it } from "vitest";
import {
  restoreManagedServiceEnabled,
  setManagedServiceEnabled,
} from "./service-enable-state.js";

it("changes and restores an App-owned service preference", async () => {
  const dataDir = await mkdtemp(path.join(os.tmpdir(), "memhub-enable-"));
  await claimRuntimeServiceForApp({
    dataDir,
    appBundle: "/Applications/MemHub.app",
    appExecutable: "/Applications/MemHub.app/Contents/MacOS/MemHub",
  });
  await enableRuntimeService(dataDir);

  const snapshot = await setManagedServiceEnabled(dataDir, false);
  expect(snapshot).toMatchObject({ enabled: true, appStartAtLogin: true });
  await expect(runtimeServiceEnabled(dataDir)).resolves.toBe(false);
  await expect(readRuntimeServiceOwner(dataDir)).resolves.toMatchObject({
    start_at_login: false,
  });

  await restoreManagedServiceEnabled(dataDir, snapshot);
  await expect(runtimeServiceEnabled(dataDir)).resolves.toBe(true);
  await expect(readRuntimeServiceOwner(dataDir)).resolves.toMatchObject({
    start_at_login: true,
  });
});

it("does not create state for an unmanaged Runtime", async () => {
  const dataDir = await mkdtemp(path.join(os.tmpdir(), "memhub-enable-"));
  await expect(setManagedServiceEnabled(dataDir, true)).resolves.toEqual({
    managed: false,
    enabled: false,
    appStartAtLogin: null,
  });
  await expect(runtimeServiceEnabled(dataDir)).resolves.toBe(false);
});

it("changes a CLI-owned marker without inventing an App preference", async () => {
  const dataDir = await mkdtemp(path.join(os.tmpdir(), "memhub-enable-"));
  await claimRuntimeServiceForCli(dataDir);
  const snapshot = await setManagedServiceEnabled(dataDir, true);
  expect(snapshot.appStartAtLogin).toBeNull();
  await expect(runtimeServiceEnabled(dataDir)).resolves.toBe(true);
});
