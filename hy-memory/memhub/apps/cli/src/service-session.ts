/** Service-aware start/stop/status for the launchd-managed Runtime.
 *
 * `start`/`stop`/`status` used to be purely receipt-based: they looked at
 * `runtime.json`/`runtime-service.json`. When the Runtime is managed by the
 * launchd KeepAlive service, those receipts can disappear while the daemon is
 * still alive, so `stop` reported "stopped" (exit 0) with the daemon running,
 * and `start` then failed with "exited before ready" because the service was
 * already holding the data directory. This module makes the three commands
 * consult the real launchd state and act on it:
 *   - `stop` boots the service out (真正停用) and verifies it is gone;
 *   - `start` kickstarts an already-registered service instead of spawning a
 *     competing process;
 *   - `status` can report the service as running even without a receipt.
 *
 * All launchctl interaction goes through an injectable runner so the logic is
 * testable without touching the host's launchd.
 */

import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import path from "node:path";

export interface CommandResult {
  code: number;
  stdout: string;
  stderr: string;
}

export type ServiceCommandRunner = (
  command: readonly string[],
) => Promise<CommandResult>;

export type LaunchdServiceState =
  | { state: "running"; pid: number; plistPath: string | null }
  /** Loaded by launchd but with no live pid right now (e.g. throttled, or
   * between KeepAlive restarts). Still a registered service. */
  | { state: "loaded"; plistPath: string | null }
  /** A `com.tencent.onememory.runtime` label is running, but its plist binds a
   * different data dir. The label is global per user, so a second install must
   * not be mistaken for this one. */
  | { state: "foreign"; plistPath: string | null }
  | { state: "absent" }
  | { state: "unknown"; code: string };

function launchdDomain(uid: number): string {
  return `gui/${uid}`;
}

/** Deterministic location of the managed LaunchAgent plist. Needed because
 * after `bootout` launchd no longer reports a path, yet `start` must be able to
 * bootstrap the very same service back. */
export function defaultLaunchAgentPath(
  home: string,
  serviceId: string,
): string {
  return path.posix.join(home, "Library", "LaunchAgents", `${serviceId}.plist`);
}

async function fileExists(target: string): Promise<boolean> {
  return access(target).then(
    () => true,
    () => false,
  );
}

/** Inspect the launchd label for this product. `launchctl print` succeeds with
 * `state = running` / `pid = N` while loaded; a non-zero exit that mentions the
 * service is missing means absent; anything else is unknown (fail-closed). */
export async function inspectLaunchdService(options: {
  serviceId: string;
  uid: number;
  runCaptured: ServiceCommandRunner;
  /** When given, a running/loaded label is only claimed for this data dir:
   * the plist's `ONE_MEMORY_DATA_DIR` must match it. The label name alone is
   * not identity — it is global per user, so a second install would otherwise
   * be reported as this one. Omit only where the caller already knows it owns
   * the label (e.g. bootstrapping the exact plist it just wrote). */
  dataDir?: string;
}): Promise<LaunchdServiceState> {
  const result = await options.runCaptured([
    "launchctl",
    "print",
    `${launchdDomain(options.uid)}/${options.serviceId}`,
  ]);
  if (result.code !== 0) {
    if (/could not find service|service not found/i.test(result.stderr)) {
      return { state: "absent" };
    }
    return { state: "unknown", code: "launchd_inspection_failed" };
  }
  const pid = /^\s*pid\s*=\s*(\d+)\s*$/m.exec(result.stdout);
  const plist = /^\s*path\s*=\s*(.+?)\s*$/m.exec(result.stdout);
  const plistPath = plist?.[1] ?? null;
  if (options.dataDir !== undefined && plistPath !== null) {
    const bound = await readPlistDataDir(plistPath, options.runCaptured).catch(
      () => undefined,
    );
    // Fail closed: an unreadable plist or a missing/mismatched data dir is not
    // proof that this label belongs to us.
    if (bound !== options.dataDir) return { state: "foreign", plistPath };
  }
  if (!pid || Number(pid[1]) < 1) return { state: "loaded", plistPath };
  return {
    state: "running",
    pid: Number(pid[1]),
    plistPath,
  };
}

/** The `ONE_MEMORY_DATA_DIR` a managed plist was written with, or undefined if
 * it cannot be read. Used only to attribute a global launchd label to a data
 * dir; never to trust the label name on its own. */
async function readPlistDataDir(
  plistPath: string,
  runCaptured: ServiceCommandRunner,
): Promise<string | undefined> {
  const result = await runCaptured([
    "/usr/bin/plutil",
    "-convert",
    "json",
    "-o",
    "-",
    plistPath,
  ]);
  if (result.code !== 0) return undefined;
  try {
    const document = JSON.parse(result.stdout) as {
      EnvironmentVariables?: Record<string, unknown>;
    };
    const value = document.EnvironmentVariables?.ONE_MEMORY_DATA_DIR;
    return typeof value === "string" ? value : undefined;
  } catch {
    return undefined;
  }
}

async function delay(milliseconds: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, milliseconds));
}

/** Stop the managed service for real. Returns "stopped" only after the label is
 * verifiably gone; returning early would reproduce the exact false success this
 * module exists to prevent. */
export async function stopManagedService(options: {
  serviceId: string;
  uid: number;
  runCaptured: ServiceCommandRunner;
  /** Attribution: only a label bound to this data dir may be stopped. */
  dataDir?: string;
  timeoutMs?: number;
  /** Consecutive absent samples required before "stopped" is returned. */
  sustainedAbsentSamples?: number;
  /** Delay between absence samples. */
  pollMs?: number;
}): Promise<"stopped" | "not-running" | "still-running"> {
  const before = await inspectLaunchdService(options);
  // `foreign`: another install's daemon holds this (global) label. Not ours to
  // stop or report on — let the caller fall through to its own receipt path.
  if (before.state === "absent" || before.state === "foreign")
    return "not-running";
  if (before.state === "unknown") throw new Error(before.code);
  const domain = launchdDomain(options.uid);
  // Prefer the plist path launchd itself reports; fall back to the label.
  const target = before.plistPath
    ? (["launchctl", "bootout", domain, before.plistPath] as const)
    : (["launchctl", "bootout", `${domain}/${options.serviceId}`] as const);
  const result = await options.runCaptured([...target]);
  if (
    result.code !== 0 &&
    !/could not find service|service not found/i.test(result.stderr)
  ) {
    throw new Error("launchd_bootout_failed");
  }
  // "Stopped" must mean the label stays gone, not that we saw it gone once.
  // macOS launchd re-loads plists from ~/Library/LaunchAgents, so a single
  // absent sample right after bootout can be followed by the service coming
  // back with a new pid. Require N consecutive absent samples spaced out, and
  // treat any reappearance as "still-running" so the caller reports non-zero
  // instead of the false success A8 exists to prevent.
  // ~5s of consecutive absence (20 × 250ms). A 1.5s window was observed to be
  // too short: a crash-looping service (`state = spawn scheduled`) came back
  // with a new pid a few seconds after bootout, and the CLI had already
  // reported success. 5s matches the acceptance criterion the verifier used
  // ("label 连续 5s 计数 0").
  const requiredAbsentSamples = options.sustainedAbsentSamples ?? 20;
  const pollMs = options.pollMs ?? 250;
  const deadline = Date.now() + (options.timeoutMs ?? 10_000);
  let consecutiveAbsent = 0;
  while (Date.now() < deadline) {
    const now = await inspectLaunchdService(options);
    if (now.state === "absent") {
      consecutiveAbsent += 1;
      if (consecutiveAbsent >= requiredAbsentSamples) return "stopped";
    } else {
      consecutiveAbsent = 0;
    }
    await delay(pollMs);
  }
  return "still-running";
}

/** Start (or restart) the managed service if it is registered; report whether a
 * kickstart was used so the caller can avoid spawning a second process. */
export async function startManagedService(options: {
  serviceId: string;
  uid: number;
  /** Home whose LaunchAgents dir holds the managed plist; required to
   * bootstrap a service that was previously booted out. */
  home?: string;
  runCaptured: ServiceCommandRunner;
  /** Attribution: a label bound to another data dir must not be kickstarted. */
  dataDir?: string;
  timeoutMs?: number;
}): Promise<"started" | "absent" | "not-ready"> {
  const before = await inspectLaunchdService(options);
  if (before.state === "unknown") throw new Error(before.code);
  // A stranger's daemon owns this label; do not kickstart or claim it.
  if (before.state === "foreign") return "absent";
  if (before.state === "running") return "started";
  const domain = launchdDomain(options.uid);
  if (before.state === "absent") {
    // Not loaded: bootstrap the managed plist if it exists; otherwise there is
    // nothing service-backed to start and the caller spawns instead.
    const plist = options.home
      ? defaultLaunchAgentPath(options.home, options.serviceId)
      : null;
    if (plist === null || !(await fileExists(plist))) return "absent";
    const boot = await options.runCaptured([
      "launchctl",
      "bootstrap",
      domain,
      plist,
    ]);
    if (boot.code !== 0) throw new Error("launchd_bootstrap_failed");
  } else {
    const result = await options.runCaptured([
      "launchctl",
      "kickstart",
      "-k",
      `${domain}/${options.serviceId}`,
    ]);
    if (result.code !== 0) throw new Error("launchd_kickstart_failed");
  }
  const deadline = Date.now() + (options.timeoutMs ?? 15_000);
  while (Date.now() < deadline) {
    const now = await inspectLaunchdService(options);
    if (now.state === "running") return "started";
    await delay(150);
  }
  return "not-ready";
}

/** Restart a registered service in place with `kickstart -k`, which keeps the
 * launchd registration. `absent` means the caller should fall back to the
 * receipt/spawn path. */
export async function restartManagedService(options: {
  serviceId: string;
  uid: number;
  runCaptured: ServiceCommandRunner;
  /** Attribution: never kickstart a label bound to another data dir. */
  dataDir?: string;
  timeoutMs?: number;
}): Promise<"restarted" | "absent" | "not-ready"> {
  const before = await inspectLaunchdService(options);
  if (before.state === "absent" || before.state === "foreign") return "absent";
  if (before.state === "unknown") throw new Error(before.code);
  const domain = launchdDomain(options.uid);
  const result = await options.runCaptured([
    "launchctl",
    "kickstart",
    "-k",
    `${domain}/${options.serviceId}`,
  ]);
  if (result.code !== 0) throw new Error("launchd_kickstart_failed");
  const deadline = Date.now() + (options.timeoutMs ?? 15_000);
  while (Date.now() < deadline) {
    const now = await inspectLaunchdService(options);
    if (now.state === "running") return "restarted";
    await delay(150);
  }
  return "not-ready";
}

export async function runLaunchctlCaptured(
  command: readonly string[],
): Promise<CommandResult> {
  const [program, ...args] = command;
  if (!program) throw new Error("launchd_command_invalid");
  return new Promise((resolve, reject) => {
    const child = spawn(program, args, {
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr?.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.once("error", () => reject(new Error("launchd_command_failed")));
    child.once("close", (code) => resolve({ code: code ?? 1, stdout, stderr }));
  });
}

/** Run launchctl for a teardown step and tolerate an already-gone target.
 *
 * `launchctl bootout` exits non-zero ("Boot-out failed: 3: No such process")
 * when the label is not loaded. That is the desired end state, not a failure.
 * The managed-service uninstaller otherwise aborts before unlinking the plist,
 * leaving a stale file that makes every later `install --yes` refuse with
 * `runtime_service_file_exists`. This is exactly the sequence `memhub stop`
 * (bootout) followed by `memhub uninstall --yes` produces. */
export function createTolerantLaunchctlRunner(
  runCaptured: ServiceCommandRunner,
): (command: readonly string[]) => Promise<void> {
  return async (command) => {
    const result = await runCaptured(command);
    if (result.code === 0) return;
    // Only launchctl gets this leniency; a non-launchctl teardown failure is a
    // real failure. Keeping it scoped also keeps Linux `systemctl` behaviour
    // exactly as the shared package defines it.
    if (command[0] === "launchctl" && isAlreadyGone(result.stderr)) return;
    throw new Error("runtime_service_command_failed");
  };
}

function isAlreadyGone(stderr: string): boolean {
  return /could not find service|service not found|no such process|boot-out failed|not loaded/i.test(
    stderr,
  );
}
