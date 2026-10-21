import { chmod, mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";

import { discoverRuntimeAttachment, RuntimeDiscoveryError } from "./index.js";

async function runtimeFixture(changes: Record<string, unknown> = {}) {
  const dataDir = await mkdtemp(path.join(tmpdir(), "runtime-control-"));
  await mkdir(dataDir, { recursive: true });
  await writeFile(
    path.join(dataDir, "runtime.json"),
    JSON.stringify({
      schema_version: 1,
      service: "one-memory-core",
      instance_id: "shared-runtime",
      pid: 1234,
      parent_pid: null,
      host: "127.0.0.1",
      port: 8765,
      started_at: "2026-09-19T01:00:00Z",
      ...changes,
    }),
  );
  const token = path.join(dataDir, "runtime-token");
  await writeFile(token, "shared-token", { mode: 0o600 });
  if (process.platform !== "win32") await chmod(token, 0o600);
  return dataDir;
}

async function serviceFixture(
  dataDir: string,
  changes: Record<string, unknown> = {},
) {
  await writeFile(
    path.join(dataDir, "runtime-service.json"),
    JSON.stringify({
      schema_version: 1,
      service: "one-memory-runtime",
      status: "running",
      instance_id: "shared-runtime",
      pid: 4321,
      core_port: 8765,
      started_at: "2026-09-19T01:00:00Z",
      ...changes,
    }),
  );
}

describe("Runtime attachment discovery", () => {
  it("returns a verified standalone instance", async () => {
    const dataDir = await runtimeFixture();
    const probe = vi.fn(async () => ({
      status: "ok" as const,
      service: "one-memory-core" as const,
      version: "1.2.3",
      instance_id: "shared-runtime",
    }));

    const attachment = await discoverRuntimeAttachment({
      dataDir,
      processIsAlive: () => true,
      probeIdentity: probe,
      platform: "linux",
      currentUid: process.getuid?.(),
    });

    expect(attachment).toMatchObject({
      instanceId: "shared-runtime",
      apiToken: "shared-token",
      port: 8765,
    });
    expect(probe).toHaveBeenCalledWith(8765, "shared-token");
  });

  it("leaves absent, stale, legacy and parent-owned receipts to the caller", async () => {
    const missing = await mkdtemp(
      path.join(tmpdir(), "runtime-control-missing-"),
    );
    const probe = vi.fn();
    await expect(
      discoverRuntimeAttachment({
        dataDir: missing,
        processIsAlive: () => true,
        probeIdentity: probe,
      }),
    ).resolves.toBeNull();

    const stale = await runtimeFixture();
    await expect(
      discoverRuntimeAttachment({
        dataDir: stale,
        processIsAlive: () => false,
        probeIdentity: probe,
      }),
    ).resolves.toBeNull();

    const parentOwned = await runtimeFixture({ parent_pid: 4321 });
    await expect(
      discoverRuntimeAttachment({
        dataDir: parentOwned,
        processIsAlive: () => true,
        probeIdentity: probe,
      }),
    ).resolves.toBeNull();
    expect(probe).not.toHaveBeenCalled();
  });

  it("attaches to a Core owned by a verified Runtime service", async () => {
    const dataDir = await runtimeFixture({ parent_pid: 4321 });
    await serviceFixture(dataDir);

    const attachment = await discoverRuntimeAttachment({
      dataDir,
      processIsAlive: (pid) => pid === 1234 || pid === 4321,
      probeIdentity: async () => ({
        status: "ok",
        service: "one-memory-core",
        version: "1.2.3",
        instance_id: "shared-runtime",
      }),
      platform: "linux",
      currentUid: process.getuid?.(),
    });

    expect(attachment?.instanceId).toBe("shared-runtime");
  });

  it("refuses a parent-owned Core with a mismatched Runtime service", async () => {
    const dataDir = await runtimeFixture({ parent_pid: 4321 });
    await serviceFixture(dataDir, { instance_id: "other-runtime" });

    await expect(
      discoverRuntimeAttachment({
        dataDir,
        processIsAlive: () => true,
        probeIdentity: vi.fn(),
        platform: "linux",
        currentUid: process.getuid?.(),
      }),
    ).rejects.toMatchObject({ code: "runtime_service_receipt_invalid" });
  });

  it.each([
    ["non-loopback receipt", { host: "0.0.0.0" }, "runtime_receipt_invalid"],
    ["mismatched identity", {}, "runtime_identity_mismatch"],
  ])("fails closed for a live %s", async (_label, changes, code) => {
    const dataDir = await runtimeFixture(changes);
    await expect(
      discoverRuntimeAttachment({
        dataDir,
        processIsAlive: () => true,
        probeIdentity: async () => ({
          status: "ok",
          service: "one-memory-core",
          version: "1.2.3",
          instance_id: "someone-else",
        }),
        platform: "linux",
        currentUid: process.getuid?.(),
      }),
    ).rejects.toMatchObject({ code });
  });

  it("rejects a token readable by other users", async () => {
    const dataDir = await runtimeFixture();
    await chmod(path.join(dataDir, "runtime-token"), 0o644);

    await expect(
      discoverRuntimeAttachment({
        dataDir,
        processIsAlive: () => true,
        probeIdentity: vi.fn(),
        platform: "linux",
        currentUid: process.getuid?.(),
      }),
    ).rejects.toMatchObject({
      code: "runtime_token_unavailable",
    });
  });
});
