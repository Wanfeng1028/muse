import { randomUUID } from "node:crypto";
import { chmod, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

export interface BrokerDiscovery {
  schema_version: 1;
  service: "one-memory-recall-broker";
  status: "running" | "stopped";
  host: "127.0.0.1";
  port: number | null;
  instance_id: string;
  pid: number;
  updated_at: string;
}

export async function writeDiscovery(
  targetPath: string,
  discovery: BrokerDiscovery,
): Promise<void> {
  await mkdir(path.dirname(targetPath), { recursive: true, mode: 0o700 });
  const temporaryPath = `${targetPath}.${randomUUID()}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(discovery, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600,
    flag: "wx",
  });
  await chmod(temporaryPath, 0o600);
  await rename(temporaryPath, targetPath);
  await chmod(targetPath, 0o600);
}

export async function readDiscovery(
  targetPath: string,
): Promise<BrokerDiscovery> {
  let raw: string;
  try {
    raw = await readFile(targetPath, "utf8");
  } catch (error) {
    throw new Error("MemHub is not running (broker discovery is unavailable)", {
      cause: error,
    });
  }

  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch (error) {
    throw new Error("MemHub broker discovery is invalid", {
      cause: error,
    });
  }
  if (!isBrokerDiscovery(value)) {
    throw new Error("MemHub broker discovery is invalid");
  }
  return value;
}

function isBrokerDiscovery(value: unknown): value is BrokerDiscovery {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<BrokerDiscovery>;
  return (
    candidate.schema_version === 1 &&
    candidate.service === "one-memory-recall-broker" &&
    (candidate.status === "running" || candidate.status === "stopped") &&
    candidate.host === "127.0.0.1" &&
    (candidate.port === null ||
      (Number.isInteger(candidate.port) &&
        (candidate.port ?? 0) > 0 &&
        (candidate.port ?? 0) <= 65_535)) &&
    typeof candidate.instance_id === "string" &&
    typeof candidate.pid === "number" &&
    typeof candidate.updated_at === "string"
  );
}
