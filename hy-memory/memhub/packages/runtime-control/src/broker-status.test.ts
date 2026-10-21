import * as fs from "node:fs/promises";
import {
  chmod,
  link,
  lstat,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  rename,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { BrokerDiscovery } from "@one-memory/host-bridge";
import axios from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { inspectRecallBrokerStatus } from "./broker-status.js";

vi.mock("node:fs/promises", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs/promises")>();
  return { ...actual, open: vi.fn(actual.open) };
});

const receipt: BrokerDiscovery = {
  schema_version: 1,
  service: "one-memory-recall-broker",
  status: "running",
  host: "127.0.0.1",
  port: 18765,
  instance_id: "test-runtime",
  pid: 4321,
  updated_at: "2026-09-19T01:00:00.000Z",
};
const health = {
  status: "ok",
  service: "one-memory-recall-broker",
  instance_id: receipt.instance_id,
};

describe("inspectRecallBrokerStatus", () => {
  let root: string;
  let dataDir: string;
  let target: string;
  const alive = vi.fn(() => true);
  const probe = vi.fn(async (): Promise<unknown> => ({ ...health }));

  beforeEach(async () => {
    root = await mkdtemp(path.join(os.tmpdir(), "om-broker-status-"));
    dataDir = path.join(root, "selected-home");
    target = path.join(dataDir, "integrations", "cursor-broker.json");
    alive.mockReset().mockReturnValue(true);
    probe.mockReset().mockResolvedValue({ ...health });
    // An accidental use of the default transport must never reach a real service.
    vi.spyOn(axios, "get").mockRejectedValue(new Error("unexpected network"));
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    vi.mocked(fs.open).mockReset();
    await rm(root, { recursive: true, force: true });
  });

  async function put(value: unknown = receipt) {
    await mkdir(path.dirname(target), { recursive: true, mode: 0o700 });
    await writeFile(target, JSON.stringify(value), { mode: 0o600 });
  }

  function inspect(expectedInstanceId = receipt.instance_id) {
    return inspectRecallBrokerStatus({
      dataDir,
      expectedInstanceId,
      processIsAlive: alive,
      probeBroker: probe,
    });
  }

  it("verifies the real protocol and leaves files/metadata unchanged", async () => {
    await put();
    const before = await lstat(target);
    const bytes = await readFile(target);
    expect(await inspect()).toEqual({
      state: "running",
      code: "broker_verified",
      instanceId: receipt.instance_id,
      host: "127.0.0.1",
      port: 18765,
    });
    expect(alive).toHaveBeenCalledWith(4321);
    expect(probe).toHaveBeenCalledWith(receipt);
    expect(await readFile(target)).toEqual(bytes);
    const after = await lstat(target);
    expect([after.ino, after.mode, after.mtimeMs, after.ctimeMs]).toEqual([
      before.ino,
      before.mode,
      before.mtimeMs,
      before.ctimeMs,
    ]);
    expect(await readdir(path.dirname(target))).toEqual(["cursor-broker.json"]);
    expect(axios.get).not.toHaveBeenCalled();
  });

  it("does not create an absent home or search a different discovery path", async () => {
    expect(await inspect()).toEqual({
      state: "stopped",
      code: "broker_discovery_missing",
    });
    expect(await readdir(root)).toEqual([]);
    await mkdir(dataDir);
    await writeFile(path.join(dataDir, "broker.json"), JSON.stringify(receipt));
    expect(await inspect()).toEqual({
      state: "stopped",
      code: "broker_discovery_missing",
    });
    expect(await readdir(dataDir)).toEqual(["broker.json"]);
    expect(alive).not.toHaveBeenCalled();
    expect(probe).not.toHaveBeenCalled();
  });

  it("reports a valid stopped receipt without checking PID or probing", async () => {
    await put({ ...receipt, status: "stopped", port: null });
    expect(await inspect()).toEqual({
      state: "stopped",
      code: "broker_stopped",
    });
    expect(alive).not.toHaveBeenCalled();
    expect(probe).not.toHaveBeenCalled();
  });

  it("reports a validated dead PID as stopped without probing", async () => {
    await put();
    alive.mockReturnValue(false);
    expect(await inspect()).toEqual({
      state: "stopped",
      code: "broker_process_dead",
    });
    expect(probe).not.toHaveBeenCalled();
  });

  it.each(["running", "stopped"])(
    "rejects wrong instance before %s/PID checks",
    async (status) => {
      await put({
        ...receipt,
        status,
        port: status === "stopped" ? null : receipt.port,
      });
      alive.mockReturnValue(false);
      expect(await inspect("other-runtime")).toEqual({
        state: "untrusted",
        code: "broker_instance_mismatch",
      });
      expect(alive).not.toHaveBeenCalled();
      expect(probe).not.toHaveBeenCalled();
    },
  );

  it.each(["", " ", "test\nsecret"])(
    "rejects invalid expected identity %j",
    async (identity) => {
      expect(await inspect(identity)).toEqual({
        state: "untrusted",
        code: "broker_expected_instance_invalid",
      });
      expect(probe).not.toHaveBeenCalled();
    },
  );

  it.each([
    { schema_version: 2 },
    { service: "one-memory-core" },
    { host: "localhost" },
    { host: "::1" },
    { host: "127.0.0.2" },
    { host: "https://example.invalid" },
    { port: null },
    { port: 0 },
    { port: -1 },
    { port: 65536 },
    { port: 12.5 },
    { port: "18765" },
    { pid: 0 },
    { pid: 1 },
    { pid: -4321 },
    { pid: 2.5 },
    { pid: "4321" },
    { pid: Number.MAX_SAFE_INTEGER },
    { instance_id: "" },
    { instance_id: " test-runtime " },
    { updated_at: "" },
    { updated_at: "invalid" },
    { status: "starting" },
    { status: "stopped", port: 18765 },
  ])(
    "rejects malformed identity %j without PID or HTTP calls",
    async (change) => {
      await put({ ...receipt, ...change });
      expect(await inspect()).toEqual({
        state: "untrusted",
        code: "broker_discovery_invalid",
      });
      expect(alive).not.toHaveBeenCalled();
      expect(probe).not.toHaveBeenCalled();
    },
  );

  it.each([null, [], {}, "secret"])(
    "rejects non-receipt JSON %j",
    async (value) => {
      await put(value);
      expect(await inspect()).toEqual({
        state: "untrusted",
        code: "broker_discovery_invalid",
      });
    },
  );

  it("rejects partial JSON without disclosing the document", async () => {
    await put();
    await writeFile(target, '{"token":"private-marker"');
    expect(await inspect()).toEqual({
      state: "untrusted",
      code: "broker_discovery_invalid",
    });
    expect(probe).not.toHaveBeenCalled();
  });

  it("accepts 16KiB but refuses any extra byte before probing", async () => {
    await put();
    await writeFile(target, JSON.stringify(receipt).padEnd(16 * 1024, " "));
    expect((await inspect()).state).toBe("running");
    probe.mockClear();
    await writeFile(target, JSON.stringify(receipt).padEnd(16 * 1024 + 1, " "));
    expect(await inspect()).toEqual({
      state: "untrusted",
      code: "broker_discovery_unsafe",
    });
    expect(probe).not.toHaveBeenCalled();
  });

  it.each([0o644, 0o620, 0o601, 0o000])(
    "refuses insecure/unreadable file mode %s",
    async (mode) => {
      await put();
      await chmod(target, mode);
      expect(await inspect()).toEqual({
        state: "untrusted",
        code: "broker_discovery_unsafe",
      });
      expect(probe).not.toHaveBeenCalled();
    },
  );

  it("refuses a different owner without changing real file ownership", async () => {
    await put();
    const uid = process.getuid?.();
    if (uid === undefined) throw new Error("POSIX test requires getuid");
    vi.spyOn(process, "getuid").mockReturnValue(uid + 1);
    expect(await inspect()).toEqual({
      state: "untrusted",
      code: "broker_discovery_unsafe",
    });
    expect(probe).not.toHaveBeenCalled();
  });

  it.each([false, true])(
    "refuses a discovery symlink, including dangling=%s",
    async (dangling) => {
      await put();
      const other = path.join(root, "other.json");
      await rename(target, other);
      if (dangling) await rm(other);
      await symlink(other, target);
      expect(await inspect()).toEqual({
        state: "untrusted",
        code: "broker_discovery_unsafe",
      });
      expect(probe).not.toHaveBeenCalled();
    },
  );

  it("refuses a hard-linked file", async () => {
    await put();
    await link(target, path.join(root, "alias.json"));
    expect(await inspect()).toEqual({
      state: "untrusted",
      code: "broker_discovery_unsafe",
    });
    expect(probe).not.toHaveBeenCalled();
  });

  it("refuses a directory at the discovery path", async () => {
    await mkdir(target, { recursive: true });
    expect(await inspect()).toEqual({
      state: "untrusted",
      code: "broker_discovery_unsafe",
    });
  });

  it("does not follow an integrations symlink to another home", async () => {
    await put();
    const other = path.join(root, "other-integrations");
    await rename(path.dirname(target), other);
    await symlink(other, path.dirname(target));
    expect(await inspect()).toEqual({
      state: "untrusted",
      code: "broker_discovery_unsafe",
    });
    expect(probe).not.toHaveBeenCalled();
  });

  it("does not classify ENOTDIR as missing", async () => {
    await mkdir(dataDir);
    await writeFile(path.dirname(target), "not a directory");
    expect((await inspect()).state).toBe("untrusted");
    expect(probe).not.toHaveBeenCalled();
  });

  it("sanitizes PID inspection failure, never treating it as dead", async () => {
    await put();
    alive.mockImplementation(() => {
      throw new Error("private PID detail");
    });
    expect(await inspect()).toEqual({
      state: "untrusted",
      code: "broker_process_unverifiable",
    });
    expect(probe).not.toHaveBeenCalled();
  });

  it("sanitizes probe failure as unhealthy", async () => {
    await put();
    probe.mockRejectedValue(new Error("token=private-marker"));
    expect(await inspect()).toEqual({
      state: "unhealthy",
      code: "broker_identity_unavailable",
    });
  });

  it.each([
    undefined,
    null,
    {},
    [],
    { ...health, status: "failed" },
    { ...health, service: "one-memory-core" },
    { ...health, instance_id: "another-runtime" },
  ])("never trusts an invalid health body %j", async (body) => {
    await put();
    probe.mockResolvedValue(body);
    expect(await inspect()).toEqual({
      state: "untrusted",
      code: "broker_identity_mismatch",
    });
  });

  it("returns only public fields and passes no unknown receipt fields to the probe", async () => {
    await put({
      ...receipt,
      token: "private-marker",
      arbitrary: "private-value",
    });
    probe.mockResolvedValue({ ...health, token: "another-private-marker" });
    expect(await inspect()).toEqual({
      state: "running",
      code: "broker_verified",
      instanceId: receipt.instance_id,
      host: receipt.host,
      port: receipt.port,
    });
    expect(probe).toHaveBeenCalledWith(receipt);
  });

  it("uses bounded loopback axios without redirects/proxy and validates its body", async () => {
    await put();
    vi.mocked(axios.get).mockResolvedValue({ data: health });
    expect(
      (
        await inspectRecallBrokerStatus({
          dataDir,
          expectedInstanceId: receipt.instance_id,
          processIsAlive: alive,
        })
      ).state,
    ).toBe("running");
    expect(axios.get).toHaveBeenCalledWith(
      "http://127.0.0.1:18765/health",
      expect.objectContaining({
        timeout: 1000,
        maxRedirects: 0,
        proxy: false,
        maxContentLength: 16 * 1024,
      }),
    );
    vi.mocked(axios.get).mockResolvedValue({
      data: { ...health, service: "fake" },
    });
    expect(
      (
        await inspectRecallBrokerStatus({
          dataDir,
          expectedInstanceId: receipt.instance_id,
          processIsAlive: alive,
        })
      ).state,
    ).toBe("untrusted");
  });

  it.each(["replace", "remove", "chmod"])(
    "fails closed if discovery changes during probe: %s",
    async (change) => {
      await put();
      probe.mockImplementation(async () => {
        if (change === "remove") await rm(target);
        else if (change === "chmod") await chmod(target, 0o644);
        else {
          await rm(target);
          await put({ ...receipt, instance_id: "replacement" });
        }
        return health;
      });
      expect(await inspect()).toEqual({
        state: "untrusted",
        code: "broker_discovery_changed",
      });
    },
  );

  it("does not report running if the PID dies during the probe", async () => {
    await put();
    alive.mockReturnValueOnce(true).mockReturnValue(false);
    expect(await inspect()).toEqual({
      state: "stopped",
      code: "broker_process_dead",
    });
  });

  it.each(["EACCES", "EIO", "EMFILE"])(
    "sanitizes file-open error %s without probing",
    async (code) => {
      await put();
      vi.mocked(fs.open).mockRejectedValueOnce(
        Object.assign(new Error("private path/body"), { code }),
      );
      expect(await inspect()).toEqual({
        state: "untrusted",
        code: "broker_discovery_unreadable",
      });
      expect(probe).not.toHaveBeenCalled();
    },
  );

  it.each(["ESRCH", "EPERM", "EIO"])(
    "default PID checker distinguishes %s with signal zero only",
    async (code) => {
      await put();
      const signal = vi.spyOn(process, "kill").mockImplementation(() => {
        throw Object.assign(new Error("private process detail"), { code });
      });
      const result = await inspectRecallBrokerStatus({
        dataDir,
        expectedInstanceId: receipt.instance_id,
        probeBroker: probe,
      });
      expect(result.state).toBe(
        code === "ESRCH"
          ? "stopped"
          : code === "EPERM"
            ? "running"
            : "untrusted",
      );
      expect(signal).toHaveBeenCalledWith(4321, 0);
      expect(signal.mock.calls.every((call) => call[1] === 0)).toBe(true);
      if (code !== "EPERM") expect(probe).not.toHaveBeenCalled();
    },
  );

  it("fails closed without a verified POSIX ownership implementation", async () => {
    await put();
    vi.spyOn(process, "getuid").mockReturnValue(undefined as unknown as number);
    expect(await inspect()).toEqual({
      state: "untrusted",
      code: "broker_discovery_unsafe",
    });
    expect(probe).not.toHaveBeenCalled();
  });
});
