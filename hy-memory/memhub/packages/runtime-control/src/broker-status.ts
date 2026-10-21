import { constants, type Stats } from "node:fs";
import { lstat, open } from "node:fs/promises";
import path from "node:path";
import type { BrokerDiscovery } from "@one-memory/host-bridge";
import axios from "axios";

const MAX_BYTES = 16 * 1024;
const SERVICE = "one-memory-recall-broker";

export interface RecallBrokerStatus {
  state: "running" | "stopped" | "unhealthy" | "untrusted";
  code: string;
  instanceId?: string;
  host?: string;
  port?: number;
}

export interface RecallBrokerStatusOptions {
  dataDir: string;
  expectedInstanceId: string;
  processIsAlive?: (pid: number) => boolean;
  /** Return the health body, not an axios response or a success-only signal. */
  probeBroker?: (discovery: Readonly<BrokerDiscovery>) => Promise<unknown>;
}

interface Snapshot {
  discovery: Readonly<BrokerDiscovery>;
  raw: Buffer;
  metadata: Stats;
}

class DiscoveryError extends Error {
  constructor(readonly code: string) {
    super(code);
  }
}

/** Inspect only the caller-selected Runtime home; never start or repair services. */
export async function inspectRecallBrokerStatus(
  options: RecallBrokerStatusOptions,
): Promise<RecallBrokerStatus> {
  if (!validInstanceId(options.expectedInstanceId)) {
    return { state: "untrusted", code: "broker_expected_instance_invalid" };
  }
  let snapshot: Snapshot | null;
  try {
    snapshot = await readSnapshot(options.dataDir);
  } catch (error) {
    return {
      state: "untrusted",
      code:
        error instanceof DiscoveryError
          ? error.code
          : "broker_discovery_unreadable",
    };
  }
  if (!snapshot) return { state: "stopped", code: "broker_discovery_missing" };
  const discovery = snapshot.discovery;
  if (discovery.instance_id !== options.expectedInstanceId) {
    return { state: "untrusted", code: "broker_instance_mismatch" };
  }
  if (discovery.status === "stopped") {
    return { state: "stopped", code: "broker_stopped" };
  }
  const alive = options.processIsAlive ?? processIsAlive;
  const processStatus = inspectProcess(alive, discovery.pid);
  if (processStatus) return processStatus;
  let health: unknown;
  try {
    health = await (options.probeBroker ?? probeBroker)(discovery);
  } catch {
    return { state: "unhealthy", code: "broker_identity_unavailable" };
  }
  if (!isBrokerHealth(health, discovery.instance_id)) {
    return { state: "untrusted", code: "broker_identity_mismatch" };
  }
  // A late probe cannot attest a replaced, removed or permission-changed receipt.
  try {
    const current = await readSnapshot(options.dataDir);
    if (
      !current ||
      !sameFile(snapshot.metadata, current.metadata) ||
      !snapshot.raw.equals(current.raw)
    ) {
      return { state: "untrusted", code: "broker_discovery_changed" };
    }
  } catch {
    return { state: "untrusted", code: "broker_discovery_changed" };
  }
  const finalProcessStatus = inspectProcess(alive, discovery.pid);
  if (finalProcessStatus) return finalProcessStatus;
  return {
    state: "running",
    code: "broker_verified",
    instanceId: discovery.instance_id,
    host: discovery.host,
    port: discovery.port as number,
  };
}

async function readSnapshot(dataDir: string): Promise<Snapshot | null> {
  const directory = path.join(dataDir, "integrations");
  const target = path.join(directory, "cursor-broker.json");
  let parent: Stats;
  let metadata: Stats;
  try {
    parent = await lstat(directory);
    if (!parent.isDirectory() || parent.isSymbolicLink()) {
      throw new DiscoveryError("broker_discovery_unsafe");
    }
    metadata = await lstat(target);
  } catch (error) {
    if (errorCode(error) === "ENOENT") return null;
    throw error;
  }
  assertSafeFile(metadata);
  // NOFOLLOW closes the final-component symlink race; NONBLOCK avoids FIFO hangs.
  const handle = await open(
    target,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
  );
  try {
    const opened = await handle.stat();
    assertSafeFile(opened);
    if (!sameFile(metadata, opened))
      throw new DiscoveryError("broker_discovery_changed");
    const buffer = Buffer.alloc(MAX_BYTES + 1);
    let length = 0;
    while (length < buffer.length) {
      const { bytesRead } = await handle.read(
        buffer,
        length,
        buffer.length - length,
        length,
      );
      if (bytesRead === 0) break;
      length += bytesRead;
    }
    if (length > MAX_BYTES) throw new DiscoveryError("broker_discovery_unsafe");
    const after = await handle.stat();
    assertSafeFile(after);
    const named = await lstat(target);
    const currentParent = await lstat(directory);
    if (
      !sameFile(opened, after) ||
      !sameFile(after, named) ||
      parent.dev !== currentParent.dev ||
      parent.ino !== currentParent.ino ||
      parent.ctimeMs !== currentParent.ctimeMs ||
      currentParent.isSymbolicLink()
    ) {
      throw new DiscoveryError("broker_discovery_changed");
    }
    const raw = buffer.subarray(0, length);
    let value: unknown;
    try {
      value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(raw));
    } catch {
      throw new DiscoveryError("broker_discovery_invalid");
    }
    return { discovery: parseDiscovery(value), raw, metadata: after };
  } finally {
    await handle.close();
  }
}

function assertSafeFile(metadata: Stats): void {
  if (
    process.platform === "win32" ||
    typeof process.getuid !== "function" ||
    !metadata.isFile() ||
    metadata.isSymbolicLink() ||
    metadata.nlink !== 1 ||
    metadata.uid !== process.getuid() ||
    (metadata.mode & 0o077) !== 0 ||
    (metadata.mode & 0o400) === 0 ||
    metadata.size > MAX_BYTES
  ) {
    throw new DiscoveryError("broker_discovery_unsafe");
  }
}

function sameFile(left: Stats, right: Stats): boolean {
  return (
    left.dev === right.dev &&
    left.ino === right.ino &&
    left.size === right.size &&
    left.mode === right.mode &&
    left.uid === right.uid &&
    left.nlink === right.nlink &&
    left.mtimeMs === right.mtimeMs &&
    left.ctimeMs === right.ctimeMs
  );
}

function parseDiscovery(value: unknown): Readonly<BrokerDiscovery> {
  if (
    !isRecord(value) ||
    value.schema_version !== 1 ||
    value.service !== SERVICE ||
    (value.status !== "running" && value.status !== "stopped") ||
    value.host !== "127.0.0.1" ||
    !validInstanceId(value.instance_id) ||
    typeof value.pid !== "number" ||
    !Number.isSafeInteger(value.pid) ||
    value.pid <= 1 ||
    value.pid > 2_147_483_647 ||
    typeof value.updated_at !== "string" ||
    !Number.isFinite(Date.parse(value.updated_at)) ||
    (value.status === "stopped"
      ? value.port !== null
      : typeof value.port !== "number" ||
        !Number.isInteger(value.port) ||
        value.port < 1 ||
        value.port > 65_535)
  ) {
    throw new DiscoveryError("broker_discovery_invalid");
  }
  // Project known fields so even injected probes cannot receive incidental secrets.
  return Object.freeze({
    schema_version: 1,
    service: SERVICE,
    status: value.status,
    host: "127.0.0.1",
    port: value.port as number | null,
    instance_id: value.instance_id,
    pid: value.pid,
    updated_at: value.updated_at,
  });
}

function validInstanceId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 256 &&
    value.trim() === value &&
    ![...value].some((character) => {
      const code = character.charCodeAt(0);
      return code < 32 || code === 127;
    })
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isBrokerHealth(value: unknown, instanceId: string): boolean {
  return (
    isRecord(value) &&
    value.status === "ok" &&
    value.service === SERVICE &&
    value.instance_id === instanceId
  );
}

async function probeBroker(
  discovery: Readonly<BrokerDiscovery>,
): Promise<unknown> {
  const response = await axios.get<unknown>(
    `http://127.0.0.1:${discovery.port}/health`,
    {
      timeout: 1_000,
      proxy: false,
      maxRedirects: 0,
      maxContentLength: MAX_BYTES,
    },
  );
  return response.data;
}

function inspectProcess(
  alive: (pid: number) => boolean,
  pid: number,
): RecallBrokerStatus | null {
  try {
    return alive(pid)
      ? null
      : { state: "stopped", code: "broker_process_dead" };
  } catch {
    return { state: "untrusted", code: "broker_process_unverifiable" };
  }
}

function processIsAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (errorCode(error) === "ESRCH") return false;
    if (errorCode(error) === "EPERM") return true;
    throw error;
  }
}

function errorCode(error: unknown): unknown {
  return isRecord(error) ? error.code : undefined;
}
