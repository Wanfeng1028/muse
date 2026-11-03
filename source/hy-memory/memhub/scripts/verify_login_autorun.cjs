#!/usr/bin/env node
/** Login auto-run acceptance for a real Mac, in phases a human can span.
 *
 * A single process cannot observe a logout, so the run is split: `arm` records
 * what must survive, `after-login` is run before opening the App on the next
 * login, `resilience` kills each service in turn, `disarm` puts the machine
 * back. Every phase appends to one receipt so the phases cannot be claimed out
 * of order or without the machine having actually restarted.
 *
 * Usage:
 *   node scripts/verify_login_autorun.cjs <phase> --receipt <path> [--data-dir <path>]
 *     [--runtime <path to runtime.cjs>]
 *
 * Phases: arm | after-login | resilience | disarm
 *
 * Exit codes: 0 pass, 4 a check failed, 5 the product does not implement the
 * step yet, 2 the script could not tell. 5 and 2 are never pass.
 */
const assert = require("node:assert/strict");
const { execFile } = require("node:child_process");
const { readFile, writeFile, stat } = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { promisify } = require("node:util");

const execute = promisify(execFile);
const root = path.resolve(__dirname, "..");
const PHASES = new Set(["arm", "after-login", "resilience", "disarm"]);
// Matches RUNTIME_SERVICE_ID in packages/runtime-control/src/service-plan.ts.
// The launched service is `one-memory-runtime`, labelled with this prefix.
const SERVICE_LABEL = "com.tencent.onememory.runtime";
const LEGACY_PLIST = "one-memory-background.plist";

function options(argv) {
  const [phase, ...rest] = argv;
  const values = new Map();
  for (let index = 0; index < rest.length; index += 2) {
    const name = (rest[index] ?? "").replace(/^--/, "");
    const value = rest[index + 1];
    if (!name || !value || value.startsWith("--")) return null;
    values.set(name, value);
  }
  if (!PHASES.has(phase) || !values.get("receipt")) return null;
  return {
    phase,
    receipt: path.resolve(values.get("receipt")),
    dataDir: values.get("data-dir") ?? path.join(os.homedir(), ".one-memory"),
    runtime:
      values.get("runtime") ??
      path.join(root, "packages/runtime-control/dist/runtime.cjs"),
  };
}

async function shell(command, args, extra = {}) {
  try {
    const { stdout, stderr } = await execute(command, args, {
      timeout: 120_000,
      ...extra,
    });
    return { code: 0, stdout, stderr };
  } catch (error) {
    return {
      code: typeof error.code === "number" ? error.code : 1,
      stdout: error.stdout ?? "",
      stderr: error.stderr ?? String(error.message ?? error),
    };
  }
}

/** The product's own read-only view, not this script's opinion of it. */
async function status(config) {
  const result = await shell(process.execPath, [
    config.runtime,
    "status",
    "--data-dir",
    config.dataDir,
  ]);
  let parsed = null;
  try {
    parsed = JSON.parse(result.stdout);
  } catch {
    parsed = null;
  }
  return {
    exit: result.code,
    health: parsed,
    stderr: result.stderr.slice(0, 400),
  };
}

async function bootUptime() {
  const result = await shell("sysctl", ["-n", "kern.boottime"]);
  return result.stdout.trim();
}

async function launchctlPrint(label) {
  const uid = process.getuid();
  return shell("launchctl", ["print", `gui/${uid}/${label}`]);
}

/** launchd prints the label only when the job is actually loaded.
 *
 * It exits 113 when the service is absent. Matching the label inside stdout
 * keeps this honest: an empty or error-only body is never "registered", and a
 * different loaded job whose banner merely mentions the label cannot pass.
 */
function isRegistered(result, label) {
  if (result.code !== 0) return false;
  const banner = `gui/${process.getuid()}/${label}`;
  return result.stdout
    .split(/\r?\n/)
    .some((line) => line.trimStart().startsWith(`${banner} = {`));
}

async function absent(target) {
  try {
    await stat(target);
    return false;
  } catch {
    return true;
  }
}

async function readReceipt(file) {
  try {
    return JSON.parse(await readFile(file, "utf8"));
  } catch {
    return { phases: [] };
  }
}

async function record(config, phase, checks) {
  const receipt = await readReceipt(config.receipt);
  receipt.phases = (receipt.phases ?? []).filter(
    (entry) => entry.phase !== phase,
  );
  receipt.phases.push({
    phase,
    at: new Date().toISOString(),
    boot: await bootUptime(),
    platform: `${process.platform} ${os.release()}`,
    data_dir: config.dataDir,
    checks,
  });
  await writeFile(config.receipt, `${JSON.stringify(receipt, null, 2)}\n`, {
    mode: 0o600,
  });
  return receipt;
}

function verdict(checks) {
  if (checks.some((check) => check.result === "fail")) return 4;
  if (checks.some((check) => check.result === "not_implemented")) return 5;
  if (checks.some((check) => check.result === "unknown")) return 2;
  return 0;
}

function check(name, result, evidence) {
  return { name, result, evidence };
}

/** Phase arm: register login start through the product and record the identity
 * that must survive the logout. Registration itself is deliberately NOT done
 * by this script: if the product cannot do it, that is the finding. */
async function arm(config) {
  const checks = [];
  const before = await status(config);
  checks.push(
    check(
      "runtime_status_before_login_registration",
      before.health ? "observed" : "unknown",
      before.health ?? before.stderr,
    ),
  );
  const service = await launchctlPrint(SERVICE_LABEL);
  checks.push(
    check(
      "managed_runtime_service_registered",
      isRegistered(service, SERVICE_LABEL) ? "pass" : "not_implemented",
      isRegistered(service, SERVICE_LABEL)
        ? `gui/${process.getuid()}/${SERVICE_LABEL} present`
        : "no managed one-memory-runtime user service; login start is currently the Electron app's own SMAppService item",
    ),
  );
  const legacy = await launchctlPrint(LEGACY_PLIST.replace(/\.plist$/, ""));
  checks.push(
    check(
      "no_double_registration_with_the_legacy_plist",
      isRegistered(legacy, LEGACY_PLIST.replace(/\.plist$/, ""))
        ? "fail"
        : "pass",
      isRegistered(legacy, LEGACY_PLIST.replace(/\.plist$/, ""))
        ? "legacy background plist is still loaded"
        : "absent",
    ),
  );
  checks.push(
    check(
      "login_item_state_from_the_os",
      "manual",
      "open System Settings > General > Login Items and record One Memory's state verbatim",
    ),
  );
  checks.push(
    check(
      "operator_action_required",
      "manual",
      "enable login start in One Memory's settings, quit the App, then log out and log back in without opening the App",
    ),
  );
  await record(config, "arm", checks);
  return verdict(checks);
}

/** Phase after-login: run in a fresh session BEFORE opening the App. */
async function afterLogin(config) {
  const receipt = await readReceipt(config.receipt);
  const armed = (receipt.phases ?? []).find((entry) => entry.phase === "arm");
  const checks = [];
  if (!armed) {
    checks.push(check("arm_phase_present", "fail", "run the arm phase first"));
    await record(config, "after-login", checks);
    return verdict(checks);
  }
  const boot = await bootUptime();
  checks.push(
    check(
      "machine_actually_restarted_or_relogged",
      boot === armed.boot ? "unknown" : "pass",
      { armed: armed.boot, now: boot },
    ),
  );
  const health = await status(config);
  checks.push(
    check(
      "runtime_core_broker_healthy_without_opening_the_app",
      health.health?.state === "healthy" ? "pass" : "fail",
      health.health ?? health.stderr,
    ),
  );
  checks.push(
    check(
      "same_instance_as_the_service_receipt",
      health.health?.instanceId ? "pass" : "fail",
      health.health?.instanceId
        ? `instance ${health.health.instanceId}`
        : "no verified instance id; a live process is not evidence",
    ),
  );
  const windows = await shell("osascript", [
    "-e",
    'tell application "System Events" to count (every process whose name is "MemHub" or name is "One Memory")',
  ]);
  checks.push(
    check(
      "no_main_window_was_opened_by_login_start",
      windows.code === 0
        ? windows.stdout.trim() === "0"
          ? "pass"
          : "fail"
        : "unknown",
      windows.stdout.trim() || windows.stderr,
    ),
  );
  checks.push(
    check(
      "host_recall_without_the_app",
      "manual",
      "in a new WorkBuddy or Cursor session, ask a natural question whose answer you did not put in the query, and record the tool call and the returned ids",
    ),
  );
  await record(config, "after-login", checks);
  return verdict(checks);
}

/** Phase resilience: kill each service and require recovery or an honest
 * degraded report. A healthy answer from a stale receipt is a failure. */
async function resilience(config) {
  const checks = [];
  for (const target of ["one-memory", "mcp.cjs", "runtime.cjs"]) {
    const killed = await shell("pkill", ["-f", target]);
    if (killed.code > 1) {
      checks.push(check(`kill_${target}`, "unknown", killed.stderr));
      continue;
    }
    let observed = null;
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      observed = await status(config);
      if (observed.health?.state === "healthy") break;
    }
    const state = observed?.health?.state;
    checks.push(
      check(
        `recovers_or_reports_degraded_after_killing_${target}`,
        state === "healthy" || state === "degraded" || state === "stopped"
          ? "pass"
          : "fail",
        observed?.health ?? observed?.stderr,
      ),
    );
  }
  await record(config, "resilience", checks);
  return verdict(checks);
}

/** Phase disarm: turn login start off and prove it stays off. */
async function disarm(config) {
  const checks = [];
  checks.push(
    check(
      "operator_action_required",
      "manual",
      "turn login start off in One Memory's settings, then log out and back in",
    ),
  );
  const service = await launchctlPrint(SERVICE_LABEL);
  checks.push(
    check(
      "service_unregistered_after_turning_login_start_off",
      isRegistered(service, SERVICE_LABEL) ? "fail" : "pass",
      isRegistered(service, SERVICE_LABEL)
        ? "service is still registered"
        : "absent",
    ),
  );
  const health = await status(config);
  checks.push(
    check(
      "nothing_running_after_login_without_the_app",
      health.health?.state === "healthy" ? "fail" : "pass",
      health.health ?? health.stderr,
    ),
  );
  checks.push(
    check(
      "data_survived_the_service_removal",
      (await absent(path.join(config.dataDir, "one-memory.sqlite3")))
        ? "fail"
        : "pass",
      path.join(config.dataDir, "one-memory.sqlite3"),
    ),
  );
  await record(config, "disarm", checks);
  return verdict(checks);
}

async function main() {
  const config = options(process.argv.slice(2));
  if (!config) {
    process.stderr.write(
      "Usage: verify_login_autorun.cjs <arm|after-login|resilience|disarm> --receipt <path> [--data-dir <path>] [--runtime <path>]\n",
    );
    return 2;
  }
  if (process.platform !== "darwin") {
    process.stderr.write(
      "login auto-run acceptance is macOS only; Linux and Windows stay unverified\n",
    );
    return 2;
  }
  assert(path.isAbsolute(config.dataDir));
  const run = { arm, "after-login": afterLogin, resilience, disarm }[
    config.phase
  ];
  const code = await run(config);
  const receipt = await readReceipt(config.receipt);
  const current = receipt.phases.find((entry) => entry.phase === config.phase);
  for (const entry of current.checks) {
    process.stdout.write(
      `${entry.result.toUpperCase().padEnd(16)} ${entry.name}\n`,
    );
  }
  process.stdout.write(`receipt: ${config.receipt}\n`);
  return code;
}

if (require.main === module) {
  main().then(
    (code) => process.exit(code),
    (error) => {
      process.stderr.write(`${error?.stack ?? error}\n`);
      process.exit(2);
    },
  );
}

module.exports = { options, verdict, check, PHASES };
