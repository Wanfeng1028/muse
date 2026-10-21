import { lstat, readFile } from "node:fs/promises";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  discoverRuntimeAttachment,
  RuntimeDiscoveryError,
} from "./discovery.js";
import { ensureRuntimeProcess } from "./runtime-launcher.js";

vi.mock("node:fs/promises", () => ({ lstat: vi.fn(), readFile: vi.fn() }));

const core = {
  schema_version: 1,
  service: "one-memory-core",
  instance_id: "fixture-runtime",
  pid: 1234,
  parent_pid: null as number | null,
  host: "127.0.0.1",
  port: 8765,
};
const service = {
  schema_version: 1,
  service: "one-memory-runtime",
  instance_id: core.instance_id,
  pid: 4321,
  status: "running",
  core_port: core.port,
};
const options = () => ({
  dataDir: "/synthetic/discovery-no-real-io",
  processIsAlive: vi.fn(() => true),
  probeIdentity: vi.fn(async () => ({
    status: "ok" as const,
    service: "one-memory-core" as const,
    instance_id: core.instance_id,
    version: "fixture-version",
  })),
  platform: "linux" as const,
  currentUid: 501,
});
function files(overrides: Record<string, string | Error> = {}) {
  const values: Record<string, string | Error> = {
    "runtime.json": JSON.stringify(core),
    "runtime-service.json": JSON.stringify(service),
    "runtime-token": "synthetic-token",
    ...overrides,
  };
  vi.mocked(readFile).mockImplementation(async (file) => {
    const value = values[path.basename(String(file))];
    if (value === undefined) throw new Error("unexpected_fixture_read");
    if (value instanceof Error) throw value;
    return value;
  });
}
const ioError = (code: string) =>
  Object.assign(new Error("DO_NOT_EXPOSE/private/path"), { code });
beforeEach(() => {
  vi.resetAllMocks();
  files();
  vi.mocked(lstat).mockResolvedValue({
    isFile: () => true,
    isSymbolicLink: () => false,
    mode: 0o600,
    uid: 501,
  } as Awaited<ReturnType<typeof lstat>>);
});

describe("receipt read errors", () => {
  it.each([
    ["runtime.json", "EACCES", "runtime_receipt_unavailable"],
    ["runtime-service.json", "EIO", "runtime_service_receipt_unavailable"],
    ["runtime-service.json", "ENOENT", "runtime_service_not_ready"],
  ])(
    "launcher never spawns a replacement for %s %s",
    async (file, errno, code) => {
      files({ [file]: ioError(errno) });
      const spawnProcess = vi.fn();
      await expect(
        ensureRuntimeProcess({
          ...options(),
          launch: { command: "/synthetic/not-executed", args: [] },
          spawnProcess,
        }),
      ).rejects.toMatchObject({ code });
      expect(spawnProcess).not.toHaveBeenCalled();
    },
  );

  it.each(["EACCES", "EPERM", "EIO", "ENOTDIR"])(
    "does not turn Core receipt %s into absence",
    async (code) => {
      files({ "runtime.json": ioError(code) });
      const input = options();
      const error = await discoverRuntimeAttachment(input).catch(
        (reason: unknown) => reason,
      );
      expect(error).toBeInstanceOf(RuntimeDiscoveryError);
      expect(error).toMatchObject({
        code: "runtime_receipt_unavailable",
        message: "runtime_receipt_unavailable",
      });
      expect(error).not.toHaveProperty("cause");
      expect(input.processIsAlive).not.toHaveBeenCalled();
      expect(input.probeIdentity).not.toHaveBeenCalled();
      expect(lstat).not.toHaveBeenCalled();
    },
  );

  it.each(["EACCES", "EPERM", "EIO", "ENOTDIR"])(
    "does not turn required service receipt %s into absence",
    async (code) => {
      files({ "runtime-service.json": ioError(code) });
      const input = { ...options(), requireServiceReceipt: true };
      const error = await discoverRuntimeAttachment(input).catch(
        (reason: unknown) => reason,
      );
      expect(error).toBeInstanceOf(RuntimeDiscoveryError);
      expect(error).toMatchObject({
        code: "runtime_service_receipt_unavailable",
        message: "runtime_service_receipt_unavailable",
      });
      expect(error).not.toHaveProperty("cause");
      expect(input.probeIdentity).not.toHaveBeenCalled();
      expect(lstat).not.toHaveBeenCalled();
    },
  );

  it("does not classify an error without errno as missing", async () => {
    files({ "runtime.json": new Error("DO_NOT_EXPOSE") });
    await expect(discoverRuntimeAttachment(options())).rejects.toMatchObject({
      code: "runtime_receipt_unavailable",
    });
  });

  it("only Core ENOENT reports absence without probing", async () => {
    files({ "runtime.json": ioError("ENOENT") });
    const input = { ...options(), requireServiceReceipt: true };
    await expect(discoverRuntimeAttachment(input)).resolves.toBeNull();
    expect(input.processIsAlive).not.toHaveBeenCalled();
    expect(input.probeIdentity).not.toHaveBeenCalled();
    expect(readFile).toHaveBeenCalledTimes(1);
  });

  it.each([null, 4321])(
    "live Core parent=%s without required service receipt is not absent",
    async (parentPid) => {
      files({
        "runtime.json": JSON.stringify({ ...core, parent_pid: parentPid }),
        "runtime-service.json": ioError("ENOENT"),
      });
      const input = { ...options(), requireServiceReceipt: true };
      await expect(discoverRuntimeAttachment(input)).rejects.toMatchObject({
        code: "runtime_service_not_ready",
      });
      expect(input.probeIdentity).not.toHaveBeenCalled();
      expect(lstat).not.toHaveBeenCalled();
    },
  );

  it("preserves non-strict parent-owned absence for the caller's ownership path", async () => {
    files({
      "runtime.json": JSON.stringify({ ...core, parent_pid: 4321 }),
      "runtime-service.json": ioError("ENOENT"),
    });
    const input = options();
    await expect(discoverRuntimeAttachment(input)).resolves.toBeNull();
    expect(input.probeIdentity).not.toHaveBeenCalled();
  });

  it("still rejects unreadable service receipts on the non-strict parent-owned path", async () => {
    files({
      "runtime.json": JSON.stringify({ ...core, parent_pid: 4321 }),
      "runtime-service.json": ioError("EACCES"),
    });
    await expect(discoverRuntimeAttachment(options())).rejects.toMatchObject({
      code: "runtime_service_receipt_unavailable",
    });
  });

  it("preserves legacy and dead-Core caller paths without reading service/token", async () => {
    files({ "runtime.json": JSON.stringify({ pid: 1234, parent_pid: null }) });
    const input = options();
    await expect(discoverRuntimeAttachment(input)).resolves.toBeNull();
    expect(readFile).toHaveBeenCalledTimes(1);
    vi.mocked(readFile).mockClear();
    files();
    input.processIsAlive.mockReturnValue(false);
    await expect(
      discoverRuntimeAttachment({ ...input, requireServiceReceipt: true }),
    ).resolves.toBeNull();
    expect(readFile).toHaveBeenCalledTimes(1);
    expect(input.probeIdentity).not.toHaveBeenCalled();
  });

  it.each([
    ["runtime.json", "runtime_receipt_invalid"],
    ["runtime-service.json", "runtime_service_receipt_invalid"],
  ])(
    "malformed JSON in %s remains invalid rather than absent",
    async (file, code) => {
      files({ [file]: "{DO_NOT_EXPOSE" });
      const input = { ...options(), requireServiceReceipt: true };
      await expect(discoverRuntimeAttachment(input)).rejects.toMatchObject({
        code,
        message: code,
      });
      expect(input.probeIdentity).not.toHaveBeenCalled();
    },
  );

  it("can attach on a later read after the required service receipt appears", async () => {
    files({ "runtime-service.json": ioError("ENOENT") });
    const input = { ...options(), requireServiceReceipt: true };
    await expect(discoverRuntimeAttachment(input)).rejects.toMatchObject({
      code: "runtime_service_not_ready",
    });
    files();
    await expect(discoverRuntimeAttachment(input)).resolves.toMatchObject({
      instanceId: core.instance_id,
      servicePid: service.pid,
    });
    expect(input.probeIdentity).toHaveBeenCalledExactlyOnceWith(
      core.port,
      "synthetic-token",
    );
  });
});
