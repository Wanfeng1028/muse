import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  claimRuntimeServiceForApp,
  readRuntimeServiceOwner,
} from "@one-memory/runtime-control";
import { expect, it } from "vitest";
import {
  claimCliServiceOwnership,
  restoreServiceOwnership,
} from "./service-owner-state.js";

it("temporarily claims and restores App ownership", async () => {
  const dataDir = await mkdtemp(path.join(os.tmpdir(), "memhub-owner-tx-"));
  await claimRuntimeServiceForApp({
    dataDir,
    appBundle: "/Applications/MemHub.app",
    appExecutable: "/Applications/MemHub.app/Contents/MacOS/MemHub",
    startAtLogin: false,
  });

  const previous = await claimCliServiceOwnership(dataDir);
  await expect(readRuntimeServiceOwner(dataDir)).resolves.toEqual({
    schema_version: 1,
    owner: "cli",
  });
  await restoreServiceOwnership(dataDir, previous);
  await expect(readRuntimeServiceOwner(dataDir)).resolves.toMatchObject({
    owner: "app",
    start_at_login: false,
  });
});

it("removes a new CLI claim when the transaction rolls back", async () => {
  const dataDir = await mkdtemp(path.join(os.tmpdir(), "memhub-owner-tx-"));
  const previous = await claimCliServiceOwnership(dataDir);
  expect(previous).toBeNull();
  await restoreServiceOwnership(dataDir, previous);
  await expect(readRuntimeServiceOwner(dataDir)).resolves.toBeNull();
});
