import {
  chmod,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { inspectRuntimeStatus } from "./runtime-status.js";

let dataDir: string;
const core = {
  schema_version: 1,
  service: "one-memory-core",
  instance_id: "fixture-runtime",
  pid: 1234,
  parent_pid: 4321,
  host: "127.0.0.1",
  port: 8765,
};
const service = {
  schema_version: 1,
  service: "one-memory-runtime",
  instance_id: core.instance_id,
  pid: 4321,
  status: "running",
  core_port: 8765,
};
const healthy = {
  status: "ok" as const,
  service: "one-memory-core" as const,
  instance_id: core.instance_id,
  version: "test-version",
};
async function fixture() {
  await writeFile(path.join(dataDir, "runtime.json"), JSON.stringify(core));
  await writeFile(
    path.join(dataDir, "runtime-service.json"),
    JSON.stringify(service),
  );
  await writeFile(path.join(dataDir, "runtime-token"), "synthetic-token", {
    mode: 0o600,
  });
  await chmod(path.join(dataDir, "runtime-token"), 0o600);
}
const options = () => ({
  dataDir,
  requireServiceReceipt: true,
  processIsAlive: vi.fn(() => true),
  probeIdentity: vi.fn(async () => healthy),
});
beforeEach(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "runtime-status-fixture-"));
});
afterEach(async () => {
  await rm(dataDir, { recursive: true, force: true });
});

it("reports absent Core as stopped without creating files or probing", async () => {
  const input = options();
  expect(await inspectRuntimeStatus(input)).toEqual({
    state: "stopped",
    code: "runtime_not_running",
  });
  expect(await readdir(dataDir)).toEqual([]);
  expect(input.probeIdentity).not.toHaveBeenCalled();
});

it("reports a dead Core as stopped without probing a stale receipt", async () => {
  await fixture();
  const input = options();
  input.processIsAlive.mockReturnValue(false);
  expect(await inspectRuntimeStatus(input)).toEqual({
    state: "stopped",
    code: "runtime_not_running",
  });
  expect(input.probeIdentity).not.toHaveBeenCalled();
});

it("maps a live Core with missing required service receipt to untrusted", async () => {
  await writeFile(path.join(dataDir, "runtime.json"), JSON.stringify(core));
  const input = options();
  expect(await inspectRuntimeStatus(input)).toEqual({
    state: "untrusted",
    code: "runtime_service_not_ready",
  });
  expect(await readdir(dataDir)).toEqual(["runtime.json"]);
  expect(input.probeIdentity).not.toHaveBeenCalled();
});

it.each([
  ["runtime.json", "runtime_receipt_unavailable"],
  ["runtime-service.json", "runtime_service_receipt_unavailable"],
])(
  "maps real receipt I/O failure at %s to untrusted, not stopped",
  async (file, code) => {
    await fixture();
    await rm(path.join(dataDir, file));
    await mkdir(path.join(dataDir, file));
    const input = options();
    expect(await inspectRuntimeStatus(input)).toEqual({
      state: "untrusted",
      code,
    });
    expect(input.probeIdentity).not.toHaveBeenCalled();
    expect(await readdir(path.join(dataDir, file))).toEqual([]);
  },
);

it.each([
  ["runtime.json", "runtime_receipt_invalid"],
  ["runtime-service.json", "runtime_service_receipt_invalid"],
])(
  "preserves malformed %s unchanged and reports untrusted",
  async (file, code) => {
    await fixture();
    const raw = "{DO_NOT_EXPOSE";
    await writeFile(path.join(dataDir, file), raw);
    const input = options();
    expect(await inspectRuntimeStatus(input)).toEqual({
      state: "untrusted",
      code,
    });
    expect(await readFile(path.join(dataDir, file), "utf8")).toBe(raw);
    expect(input.probeIdentity).not.toHaveBeenCalled();
  },
);

it("reports unreachable Core identity as unhealthy and strips underlying error details", async () => {
  await fixture();
  const input = options();
  input.probeIdentity.mockRejectedValue(
    new Error("DO_NOT_EXPOSE synthetic-token"),
  );
  expect(await inspectRuntimeStatus(input)).toEqual({
    state: "unhealthy",
    code: "runtime_identity_unavailable",
  });
});

it("reports a mismatched Core identity as untrusted", async () => {
  await fixture();
  const input = options();
  input.probeIdentity.mockResolvedValue({ ...healthy, instance_id: "other" });
  expect(await inspectRuntimeStatus(input)).toEqual({
    state: "untrusted",
    code: "runtime_identity_mismatch",
  });
});

it("returns only public Core/Runtime status and leaves all receipt bytes unchanged", async () => {
  await fixture();
  const names = await readdir(dataDir);
  const before = await Promise.all(
    names.map((name) => readFile(path.join(dataDir, name), "utf8")),
  );
  expect(await inspectRuntimeStatus(options())).toEqual({
    state: "running",
    code: "runtime_verified",
    instanceId: core.instance_id,
    host: core.host,
    port: core.port,
    version: healthy.version,
  });
  expect(await readdir(dataDir)).toEqual(names);
  expect(
    await Promise.all(
      names.map((name) => readFile(path.join(dataDir, name), "utf8")),
    ),
  ).toEqual(before);
});

it("reports degraded, not stopped, when the service is alive but its Core died", async () => {
  await fixture();
  const input = options();
  // The Core pid (1234) is gone; the Runtime service pid (4321) is still alive.
  input.processIsAlive.mockImplementation((pid?: number) => pid === 4321);
  expect(await inspectRuntimeStatus(input)).toEqual({
    state: "degraded",
    code: "runtime_core_exited",
  });
  expect(input.probeIdentity).not.toHaveBeenCalled();
});

it("stays stopped when both the service and its Core are gone", async () => {
  await fixture();
  const input = options();
  input.processIsAlive.mockReturnValue(false);
  expect(await inspectRuntimeStatus(input)).toEqual({
    state: "stopped",
    code: "runtime_not_running",
  });
});
