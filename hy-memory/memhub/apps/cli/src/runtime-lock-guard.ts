import { readFile } from "node:fs/promises";
import path from "node:path";

/** Refuse a destructive operation while a Runtime service lease names a live
 * process.
 *
 * `inspectRuntimeStatus` deliberately treats a missing `runtime.json` as
 * stopped, but the service lease can still name the process that owns the
 * database. A destructive command must not interpret "receipt missing" as
 * proof that no Runtime exists.
 *
 * The guard is deliberately conservative: an unreadable or malformed lease is
 * `unknown` (refuse), not `clear`.
 */
export type RuntimeLockState = "clear" | "live" | "unknown";

export async function inspectRuntimeServiceLock(
  dataDir: string,
  processIsAlive: (pid: number) => boolean = defaultProcessIsAlive,
): Promise<RuntimeLockState> {
  const ownerPath = path.join(dataDir, "runtime-service.lock", "owner.json");
  let raw: string;
  try {
    raw = await readFile(ownerPath, "utf8");
  } catch (error) {
    // No lock directory is the normal stopped state. Any other read failure is
    // not evidence that the data directory is safe to replace.
    return (error as NodeJS.ErrnoException).code === "ENOENT"
      ? "clear"
      : "unknown";
  }
  let owner: unknown;
  try {
    owner = JSON.parse(raw);
  } catch {
    return "unknown";
  }
  if (owner === null || typeof owner !== "object" || Array.isArray(owner)) {
    return "unknown";
  }
  const pid = (owner as { pid?: unknown }).pid;
  if (typeof pid !== "number" || !Number.isInteger(pid) || pid <= 1) {
    return "unknown";
  }
  return processIsAlive(pid) ? "live" : "clear";
}

function defaultProcessIsAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}
