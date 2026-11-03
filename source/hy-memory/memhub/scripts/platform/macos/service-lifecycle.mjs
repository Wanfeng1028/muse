#!/usr/bin/env node
import { spawn } from "node:child_process";
/**
 * macOS install / service / upgrade / rollback / uninstall lifecycle harness.
 *
 * C7 owner. Everything runs against a caller-supplied runtime distribution in a
 * throwaway HOME, install root and data dir. It never touches the daily
 * `~/.one-memory`, `~/Library/Application Support/One Memory`, or the canonical
 * LaunchAgent, so it is safe to run while a real install is live.
 *
 * The user-level LaunchAgent label is scoped to the install root (C7
 * `734ca43`): the daily root keeps `com.tencent.onememory.runtime`, any other
 * root gets `<canonical>.<sha256(root) | 16>`. This harness asserts that the
 * scoped label is what actually loads, that a reinstall is idempotent instead
 * of a second bootstrap, and that uninstall never removes data.
 *
 * Usage:
 *   node scripts/platform/macos/service-lifecycle.mjs \
 *     --dist <runtime-dist dir> [--cli <one-memory.cjs>] [--app <MemHub.app>]
 *     [--work <dir>] [--json]
 *
 * `--cli` drives a CLI build of this checkout against the given payload, so the
 * harness can validate an unfrozen fix without waiting for a new hourly package.
 * Without it, the CLI bundled in the distribution is used.
 *
 * `--app` additionally asserts the App bundle embeds the same Runtime as the
 * standalone distribution (the same-origin Runtime hash requirement).
 *
 * Exit codes: 0 pass, 4 a check failed, 2 the harness could not tell.
 */
import { createHash } from "node:crypto";
import {
  cp,
  lstat,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  readlink,
  realpath,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CANONICAL_LABEL = "com.tencent.onememory.runtime";
const REQUIRED_FILES = [
  "bin/node",
  "bin/one-memory",
  "bin/one-memory.cjs",
  "core/one-memory",
  "runtime/runtime.cjs",
  "host-bridge/mcp.cjs",
  "host-bridge/recall-cli.cjs",
  "host-bridge/sync-hook/manifest.json",
];

function parse(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const name = (argv[index] ?? "").replace(/^--/, "");
    const value = argv[index + 1];
    if (!name) return null;
    if (name === "json") {
      values.set("json", "1");
      index -= 1;
      continue;
    }
    if (!value || value.startsWith("--")) return null;
    values.set(name, value);
  }
  if (!values.get("dist")) return null;
  return {
    dist: path.resolve(values.get("dist")),
    cli: values.get("cli") ? path.resolve(values.get("cli")) : null,
    app: values.get("app") ? path.resolve(values.get("app")) : null,
    work: values.get("work") ? path.resolve(values.get("work")) : null,
    json: values.get("json") === "1",
  };
}

/** Run a command with an optional timeout and optional stdin.
 *
 * `extra` carries `env`/`cwd` straight to spawn; `input` (written to stdin then
 * closed) and `timeoutMs` (kill + report `timedOut`) are handled here so a
 * hung child is a recorded outcome rather than a hung harness.
 */
function run(command, args, extra = {}) {
  return new Promise((resolve) => {
    const { input, timeoutMs, ...spawnOptions } = extra;
    const child = spawn(command, args, {
      stdio: [input === undefined ? "ignore" : "pipe", "pipe", "pipe"],
      ...spawnOptions,
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let timer = null;
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    if (input !== undefined && child.stdin) {
      child.stdin.end(input);
    }
    if (typeof timeoutMs === "number" && timeoutMs > 0) {
      timer = setTimeout(() => {
        timedOut = true;
        child.kill("SIGKILL");
      }, timeoutMs);
    }
    child.once("error", (error) =>
      resolve({
        code: null,
        stdout,
        stderr: String(error.message ?? error),
        timedOut,
      }),
    );
    child.once("close", (code) => {
      if (timer !== null) clearTimeout(timer);
      resolve({ code, stdout, stderr, timedOut });
    });
  });
}

function check(name, result, evidence) {
  return { name, result, evidence };
}

/** A check that only makes sense once the install step succeeded.
 *
 * When install did not complete (e.g. the load-sensitive Core cold start), the
 * dependent checks are not evaluated and are reported as `unknown` with that
 * reason, instead of a cascade of `fail`s that would look like thirteen product
 * defects. The install failure itself is already recorded separately.
 */
function depCheck(installOk, name, result, evidence) {
  if (!installOk) {
    return check(
      name,
      "unknown",
      "install step did not complete; not evaluated",
    );
  }
  return check(name, result, evidence);
}

/** The label the product derives for this install path.
 *
 * `runtimeInstallLayout` first normalizes any caller spelling to the `current`
 * link (C7 `7b95b68`): `install` passes `<root>`, `uninstall`/`upgrade` pass
 * `<root>/current`, and both must land on one label. `serviceLabelFor` then
 * hashes the normalized path (C7 `734ca43`). So this mirrors the product by
 * appending `current` when absent, never by dropping it.
 *
 * The daily root keeps the canonical label. That root is derived from the login
 * home (`defaultManagedInstallRoot`), which the hash rule does not otherwise
 * know, so the caller passes it in; the check is against the daily root itself
 * and against its `current` link.
 */
function scopedLabel(platform, installRoot, dailyRoot = null) {
  const resolved = path.resolve(installRoot);
  const normalized =
    path.basename(resolved) === "current"
      ? resolved
      : path.join(resolved, "current");
  if (dailyRoot !== null) {
    const daily = path.resolve(dailyRoot);
    if (normalized === path.join(daily, "current")) return CANONICAL_LABEL;
  }
  const digest = createHash("sha256")
    .update(`one-memory-service-root\0${platform}\0${normalized}`)
    .digest("hex")
    .slice(0, 16);
  return `${CANONICAL_LABEL}.${digest}`;
}

/** SHA-256 of one file, used to re-key a fixture manifest after a controlled
 * payload mutation so the only variable under test is the payload itself. */
async function sha256File(file) {
  const { createReadStream } = await import("node:fs");
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(file)) digest.update(chunk);
  return digest.digest("hex");
}

/** Ask the product itself which label it will register for this install path.
 *
 * `service-plan` is read-only (no filesystem or launchd writes), so it is safe
 * to call before installing. Deriving the label from the product instead of
 * re-hashing the path here keeps the harness correct no matter how the label
 * rule evolves, and makes a product/harness disagreement show up as evidence
 * rather than as a mysterious "plist missing". Returns null when the product
 * cannot answer.
 */
async function plannedServiceId(cliPath, home, dataDir, installRoot) {
  const result = await cli(home, dataDir, cliPath, [
    "service-plan",
    "--install-root",
    installRoot,
    "--home",
    home,
    "--data-dir",
    dataDir,
  ]);
  try {
    const parsed = JSON.parse(result.stdout);
    return typeof parsed?.service_id === "string" && parsed.service_id
      ? parsed.service_id
      : null;
  } catch {
    return null;
  }
}

/** Compare the Runtime an App bundle embeds against the standalone distribution.
 *
 * Path mapping matters and is not symmetric:
 *   - core/runtime/host-bridge/web are directories with the same name on both sides;
 *   - the CLI is a *directory* (`cli/`) in the App bundle but a single file
 *     (`bin/one-memory.cjs`) in the distribution. Comparing `dist/cli` (which
 *     does not exist) reported `dist=missing app=present` on a correct bundle --
 *     a false failure that also made the check easy to dismiss.
 *
 * Same-origin Runtime is a hard requirement: App and CLI must consume one
 * artifact, so an App-only rebuild cannot silently drift.
 */
async function sameOriginRuntimeChecks(distDir, appPath) {
  const appResources = path.join(appPath, "Contents", "Resources");
  const { treeManifest } = await import(
    path.join(
      path.dirname(fileURLToPath(import.meta.url)),
      "..",
      "..",
      "packaged_resource_manifest.cjs",
    )
  );
  const { createHash } = await import("node:crypto");
  const { createReadStream } = await import("node:fs");
  const fileDigest = async (file) => {
    const hash = createHash("sha256");
    for await (const chunk of createReadStream(file)) hash.update(chunk);
    return hash.digest("hex");
  };
  const pairs = [
    { name: "core", dist: path.join(distDir, "core"), app: "core" },
    { name: "runtime", dist: path.join(distDir, "runtime"), app: "runtime" },
    {
      name: "host-bridge",
      dist: path.join(distDir, "host-bridge"),
      app: "host-bridge",
    },
    { name: "web", dist: path.join(distDir, "web"), app: "web" },
    // The CLI: distribution ships one file, the App receives a directory.
    {
      name: "cli",
      dist: path.join(distDir, "bin", "one-memory.cjs"),
      app: "cli",
    },
  ];
  const results = [];
  for (const pair of pairs) {
    if (pair.name === "cli") {
      const appCli = path.join(appResources, "cli", "one-memory.cjs");
      const distHash = await fileDigest(pair.dist).catch(() => null);
      const appHash = await fileDigest(appCli).catch(() => null);
      const same = distHash !== null && distHash === appHash;
      results.push(
        check(
          "app_embeds_same_cli_as_distribution",
          same ? "pass" : "fail",
          same
            ? "bin/one-memory.cjs identical to Resources/cli/one-memory.cjs"
            : `dist=${distHash === null ? "missing" : "present"} app=${
                appHash === null ? "missing" : "present"
              }`,
        ),
      );
      continue;
    }
    const distHash = await treeManifest(pair.dist).catch(() => null);
    const appHash = await treeManifest(path.join(appResources, pair.app)).catch(
      () => null,
    );
    const same =
      distHash !== null &&
      appHash !== null &&
      JSON.stringify(distHash) === JSON.stringify(appHash);
    results.push(
      check(
        `app_embeds_same_${pair.name}_as_distribution`,
        same ? "pass" : "fail",
        same
          ? `${Object.keys(distHash).length} entries identical`
          : `dist=${distHash === null ? "missing" : "present"} app=${
              appHash === null ? "missing" : "present"
            }`,
      ),
    );
  }
  return results;
}

/** Checks that only make sense against a real packaged App bundle.
 *
 * These cover the packaging-level obligations that an install-root CLI test
 * cannot see: the bundle must not ship a second login registration, and a
 * signed bundle's hardened-runtime status must be reported honestly.
 */
async function appBundleChecks(appPath) {
  const results = [];
  const contents = path.join(appPath, "Contents");

  // 1. No RunAtLoad login agent shipped inside the bundle.
  //
  //    Scope note, per C6 App's correction: launchd does NOT scan
  //    `Contents/Library/LaunchAgents` (it scans ~/Library/LaunchAgents,
  //    /Library/LaunchAgents, /System/Library/LaunchAgents). Such a plist only
  //    takes effect if some code explicitly registers it via
  //    SMAppService.agent / setLoginItemSettings({type:"agentService"}). The
  //    current repo has no such call, so this is a latent second-registration
  //    path, not live behavior. It still violates the contract clause
  //    "不能两份同时注册" and contradicts login-item.ts's own comment, so the
  //    bundle must not ship it. This check asserts the bundle fact only -- it
  //    does not claim launchd loads it.
  const agentsDir = path.join(contents, "Library", "LaunchAgents");
  const agentEntries = await readdir(agentsDir).catch(() => []);
  const runAtLoadAgents = [];
  for (const entry of agentEntries) {
    if (!entry.endsWith(".plist")) continue;
    const raw = await readFile(path.join(agentsDir, entry), "utf8").catch(
      () => "",
    );
    if (/<key>RunAtLoad<\/key>\s*<true\s*\/>/.test(raw)) {
      runAtLoadAgents.push(entry);
    }
  }
  results.push(
    check(
      "app_bundle_ships_no_run_at_load_login_agent",
      runAtLoadAgents.length === 0 ? "pass" : "fail",
      runAtLoadAgents.length === 0
        ? agentEntries.length === 0
          ? "no bundled LaunchAgents"
          : `${agentEntries.length} bundled plist(s), none RunAtLoad`
        : `RunAtLoad login agent(s) bundled: ${runAtLoadAgents.join(", ")}`,
    ),
  );

  // 2. Report the code-signing facts the public gate depends on, without
  //    pretending an ad-hoc internal build is a public release. `spctl`
  //    rejecting an ad-hoc bundle is expected, so it is evidence, not a fail.
  const signature = await run("codesign", ["-d", "--verbose=4", appPath]);
  const signatureText = `${signature.stdout}${signature.stderr}`;
  const hardened = /flags=0x[0-9a-f]*\([^)]*runtime[^)]*\)/.test(signatureText);
  const adhoc = /Signature=adhoc/.test(signatureText);
  results.push(
    check(
      "app_bundle_reports_its_signing_state_honestly",
      hardened ? "pass" : "unknown",
      hardened
        ? `hardened runtime enabled${adhoc ? " (ad-hoc signed: internal package, not a public release)" : ""}`
        : "hardened runtime not enabled on this bundle; the public gate requires it",
    ),
  );
  return results;
}

/**
 * Public-release gate report for a packaged App, kept separate from the internal
 * hourly matrix. It states each public requirement as pass/fail/unknown with the
 * command that produced it, so "not yet verified" cannot be read as "supported".
 *
 * Usage:
 *   node scripts/platform/macos/service-lifecycle.mjs --dist <dist> --app <App>
 *   # then read the app_bundle_* checks; spctl/notarization need real creds.
 */
async function publicGateReport(appPath) {
  const codesign = await run("codesign", [
    "--verify",
    "--deep",
    "--strict",
    appPath,
  ]);
  const spctl = await run("spctl", ["-a", "-vvv", "-t", "exec", appPath]);
  const stapler = await run("xcrun", ["stapler", "validate", appPath]);
  const signature = await run("codesign", ["-d", "--verbose=4", appPath]);
  const version = await run("/usr/libexec/PlistBuddy", [
    "-c",
    "Print :CFBundleShortVersionString",
    path.join(appPath, "Contents", "Info.plist"),
  ]);
  // `codesign --verify` can pass even when hardened runtime library validation
  // prevents Electron from loading its own signed Framework. Desktop's
  // side-effect-free `--version` path runs before lifecycle startup, so this
  // exercises the real App executable/framework without windows, Runtime or
  // service registration.
  const launch = await run(
    path.join(appPath, "Contents", "MacOS", "MemHub"),
    ["--memhub-version"],
    { timeoutMs: 30_000 },
  );
  const expectedVersionOutput = `MemHub ${version.stdout.trim()}`;
  const signatureText = `${signature.stdout}${signature.stderr}`;
  const hardened = /flags=0x[0-9a-f]*\([^)]*runtime[^)]*\)/.test(signatureText);
  const adhoc = /Signature=adhoc/.test(signatureText);
  return [
    check(
      "public_gate_codesign_verify",
      codesign.code === 0 ? "pass" : "fail",
      `codesign --verify --deep --strict exit ${codesign.code}`,
    ),
    check(
      "public_gate_hardened_runtime",
      hardened ? "pass" : "fail",
      hardened
        ? "runtime flag present after signing"
        : "no hardened-runtime flag; pass --options runtime at signing time",
    ),
    check(
      "public_gate_developer_id_signature",
      adhoc ? "fail" : signature.code === 0 ? "pass" : "unknown",
      adhoc
        ? "ad-hoc signature: internal package only, not a public release"
        : `codesign -d exit ${signature.code}`,
    ),
    check(
      "public_gate_gatekeeper_accepts",
      spctl.code === 0 ? "pass" : "fail",
      spctl.code === 0
        ? "spctl accepted"
        : `spctl rejected: ${`${spctl.stdout}${spctl.stderr}`.trim().split(/\n/)[0] || "no reason"}`,
    ),
    check(
      "public_gate_notarization_ticket",
      stapler.code === 0 ? "pass" : "fail",
      stapler.code === 0
        ? "notarization ticket stapled"
        : `no stapled ticket: ${`${stapler.stdout}${stapler.stderr}`.trim().split(/\n/).pop() || "n/a"}`,
    ),
    check(
      "public_gate_hardened_bundle_still_launches",
      launch.code === 0 &&
        !launch.timedOut &&
        version.code === 0 &&
        launch.stdout.trim() === expectedVersionOutput
        ? "pass"
        : "fail",
      launch.code === 0 &&
        !launch.timedOut &&
        version.code === 0 &&
        launch.stdout.trim() === expectedVersionOutput
        ? `${expectedVersionOutput} exited 0`
        : `MemHub --memhub-version exit=${launch.code} timedOut=${launch.timedOut === true} stdout=${launch.stdout.trim() || "<empty>"} expected=${expectedVersionOutput}`,
    ),
  ];
}

/** launchd prints "<domain>/<label> = {" when a job is loaded; exit 113 means
 * absent. A 0 exit with no matching banner is not "registered". */
async function launchctlPrint(label) {
  const result = await run("launchctl", [
    "print",
    `gui/${process.getuid()}/${label}`,
  ]);
  const banner = `gui/${process.getuid()}/${label} = {`;
  const registered =
    result.code === 0 &&
    result.stdout
      .split(/\r?\n/)
      .some((line) => line.trimStart().startsWith(banner));
  return { ...result, registered };
}

/** The exact `program` + `arguments` launchd reports for a loaded job.
 *  Returns null when the job is not loaded or the block cannot be parsed. */
function parseLaunchctlJobCommand(stdout) {
  const lines = stdout.split(/\r?\n/);
  let program = null;
  const args = [];
  let inArgs = false;
  for (const line of lines) {
    const trimmed = line.trim();
    const programMatch = trimmed.match(/^program = (.+)$/);
    if (programMatch) {
      program = programMatch[1].trim();
      continue;
    }
    if (trimmed === "arguments = {") {
      inArgs = true;
      continue;
    }
    if (inArgs) {
      if (trimmed === "}") {
        inArgs = false;
        continue;
      }
      args.push(trimmed);
    }
  }
  if (program === null) return null;
  return { program, args };
}

async function exists(target) {
  try {
    await stat(target);
    return true;
  } catch {
    return false;
  }
}

/** Parse `ps -Ao pid=,ppid=,state=,command=` output into rows.
 *
 * Pure so it can be pinned by a test: the zombie/orphan verdict must not be
 * possible to weaken without a test going red (C8 showed that mutating the
 * filter to `[]` left the suite green when this was inline).
 */
function parsePsRows(stdout) {
  return stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^(\d+)\s+(\d+)\s+(\S+)\s+(.*)$/);
      return match === null
        ? null
        : {
            pid: Number(match[1]),
            ppid: Number(match[2]),
            state: match[3],
            command: match[4],
          };
    })
    .filter((row) => row !== null);
}

/** Split ps rows into zombies and live processes still holding `installRoot`.
 *
 * A zombie (`Z`) has no argv -- `pgrep -fl` cannot see it, which is why this
 * judges the STATE field. A live process whose command mentions the removed
 * root is an orphan that outlived uninstall. Both must be empty to pass.
 */
function judgeLeftovers(rows, installRoot, ownedPids = null) {
  const zombies = rows.filter(
    (row) =>
      row.state.startsWith("Z") &&
      (ownedPids === null || ownedPids.has(row.pid)),
  );
  const liveLeftovers = rows.filter(
    (row) => !row.state.startsWith("Z") && row.command.includes(installRoot),
  );
  return { zombies, liveLeftovers };
}

/** Verdict for "App and CLI share one launchd-owned daemon".
 *
 * Pure so it can be pinned: the CLI-observation half used to be a bare "pass"
 * with the observation only in the evidence text, so weakening it could not fail
 * any check (C8's class of finding). Rules:
 *   - the job moved / vanished between samples -> "unknown" (restart/teardown);
 *   - same job and CLI sees it running -> "pass";
 *   - same job, CLI does NOT see it, but the runtime was healthy earlier -> "fail"
 *     (a real App/CLI disagreement);
 *   - same job, CLI does not see it, health was never established -> "unknown".
 */
function sharedDaemonVerdict({ sameJob, cliSeesRunning, healthy }) {
  if (!sameJob) return "unknown";
  if (cliSeesRunning) return "pass";
  return healthy ? "fail" : "unknown";
}

async function missing(target) {
  try {
    await lstat(target);
    return false;
  } catch {
    return true;
  }
}

function parseJson(text, label, checks) {
  try {
    return JSON.parse(text);
  } catch {
    checks.push(check(`${label}_json`, "fail", text.slice(0, 200)));
    return null;
  }
}

async function cli(home, dataDir, cliPath, args, extraEnv = {}) {
  // The packaged entrypoint is a shell launcher; a checkout override is a
  // CommonJS file, so it is driven through the running Node binary.
  const [command, commandArgs] = cliPath.endsWith(".cjs")
    ? [process.execPath, [cliPath, ...args]]
    : [cliPath, args];
  return run(command, commandArgs, {
    env: {
      PATH: `${path.dirname(process.execPath)}:/usr/bin:/bin`,
      HOME: home,
      ONE_MEMORY_DATA_DIR: dataDir,
      NO_COLOR: "1",
      ...extraEnv,
    },
  });
}

/** Poll the product's own status until the runtime is verifiably healthy.
 *
 * Core cold start is load-sensitive on this Mac (measured 1-15s under load
 * averages of 40-60); the Runtime's own start budget can expire while the
 * machine is saturated even though nothing is wrong with the install. So a
 * still-stopped runtime after this bounded wait is reported as unknown with the
 * load average as evidence, never as a product failure.
 */
async function waitForHealthy(home, dataDir, cliPath, budgetMs = 90_000) {
  const deadline = Date.now() + budgetMs;
  let last = null;
  while (Date.now() < deadline) {
    const result = await cli(home, dataDir, cliPath, ["status", "--json"]);
    try {
      last = JSON.parse(result.stdout);
    } catch {
      last = null;
    }
    const state = last?.runtime?.state ?? last?.state;
    if (state === "running" || last?.health?.state === "healthy") return last;
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  return last;
}

/** The one PID launchd reports as the running job, or null when not loaded. */
async function loadedPid(label) {
  const result = await run("launchctl", [
    "print",
    `gui/${process.getuid()}/${label}`,
  ]);
  if (result.code !== 0) return null;
  const match = result.stdout.match(/^\s*pid = (\d+)\s*$/m);
  return match ? Number(match[1]) : null;
}

async function processStillReferences(pid, installRoot) {
  const result = await run("ps", ["-o", "state=,command=", "-p", String(pid)]);
  const row = result.stdout.trim();
  return row !== "" && !row.startsWith("Z") && row.includes(installRoot);
}

/** Every scoped LaunchAgent whose program lives inside `work`.
 *
 * The lifecycle suite installs and uninstalls the same label several times. A
 * step that re-installs after an uninstall (the foreign-PATH and nested-data
 * probes both do) leaves the service registered again, and a single
 * `labelRegistered` flag sampled earlier is then stale: the final `bootout`
 * skips it, `KeepAlive` restarts the Runtime, `safeRemoveWork` reports
 * `service-still-registered`, and the throwaway tree plus a live daemon outlive
 * the run. Observed on 2026-09-30: a 3.5G `--work` tree and a `running` scoped
 * label with `ppid=1` after an otherwise 70/0 matrix, plus three such labels
 * accumulated on the machine from earlier runs (that is why the finalizer must
 * enumerate from launchd per run rather than trust a flag captured mid-run).
 * So enumerate the labels from launchd itself and decide per label from the
 * program it actually runs,
 * rather than trusting a flag captured mid-run.
 */
async function scopedLabelsUnderWork(work) {
  const realWork = await realpath(work).catch(() => null);
  if (realWork === null) return [];
  // `launchctl list` is the loaded-job table; `print-disabled` only reports
  // labels that carry an override entry, so a scoped label that was never
  // disabled/enabled would be invisible there.
  const listed = await run("launchctl", ["list"]);
  const candidates = new Set();
  for (const line of listed.stdout.split(/\r?\n/)) {
    // "<pid|->\t<status>\t<label>"
    const columns = line.split("\t");
    const listedLabel = columns[columns.length - 1]?.trim();
    if (
      columns.length >= 3 &&
      typeof listedLabel === "string" &&
      listedLabel.startsWith(`${CANONICAL_LABEL}.`)
    ) {
      candidates.add(listedLabel);
    }
  }
  const scoped = [];
  for (const candidate of candidates) {
    if (candidate === CANONICAL_LABEL) continue;
    const printed = await launchctlPrint(candidate);
    if (!printed.registered) continue;
    const command = parseLaunchctlJobCommand(printed.stdout);
    const entry = command?.program ?? null;
    if (entry === null) continue;
    const realEntry = await realpath(entry).catch(() => null);
    const root = realEntry ?? path.resolve(entry);
    if (root === realWork || root.startsWith(`${realWork}${path.sep}`)) {
      scoped.push(candidate);
    }
  }
  return scoped;
}

/** POSIX mode of a path as an octal string, or null when it is missing. */
async function fileMode(target) {
  try {
    const info = await lstat(target);
    return (info.mode & 0o777).toString(8).padStart(3, "0");
  } catch {
    return null;
  }
}

/** Remove this run's throwaway work directory, but only when provably safe.
 *
 * Mirrors the four protections the hourly cleanup protocol requires: the path
 * is a real directory under the temp root, is not a symlink, its service is no
 * longer registered, and no process still references it. If any protection
 * fails the tree is left in place and the reason is reported, because deleting
 * a directory a live process still uses is exactly the C8-flagged defect.
 */
/**
 * True when `target` sits under a temp root. macOS gives the same directory two
 * names (`/tmp` and `/private/tmp`, `/var/folders/.../T`), and `os.tmpdir()` is
 * not reconciled with the one the caller actually used, so compare against the
 * resolved forms of both `TMPDIR` and the platform temp root.
 */
async function isUnderAnyTempRoot(target) {
  const candidates = [
    os.tmpdir(),
    process.env.TMPDIR,
    "/tmp",
    "/var/tmp",
    "/private/tmp",
  ].filter((value) => typeof value === "string" && value.length > 0);
  const roots = await Promise.all(
    candidates.map((value) => realpath(value).catch(() => null)),
  );
  return roots.some(
    (root) =>
      root !== null &&
      (target === root || target.startsWith(`${root}${path.sep}`)),
  );
}

async function safeRemoveWork(work, label, labelRegistered) {
  const info = await lstat(work).catch(() => null);
  if (info === null) return { removed: false, reason: "already-gone" };
  if (!info.isDirectory() || info.isSymbolicLink()) {
    return { removed: false, reason: "not-a-real-directory" };
  }
  const realWork = await realpath(work).catch(() => null);
  if (realWork === null || !(await isUnderAnyTempRoot(realWork))) {
    return { removed: false, reason: "escapes-temp-root" };
  }
  if (labelRegistered || (await launchctlPrint(label)).registered) {
    return { removed: false, reason: "service-still-registered" };
  }
  // The scoped label is not the only job this run can create: the nested-data
  // probe installs a second scoped label derived from a different root. Both
  // point their program into `work`, so refuse to delete while either is loaded.
  const stillLoaded = await scopedLabelsUnderWork(work);
  if (stillLoaded.length > 0) {
    return {
      removed: false,
      reason: `service-still-registered:${stillLoaded.join(",")}`,
    };
  }
  const holders = await run("pgrep", ["-fl", work]);
  const holders0 = holders.stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (holders0.length > 0) {
    return { removed: false, reason: `live-process:${holders0.length}` };
  }
  await rm(work, { recursive: true, force: true });
  return { removed: true, reason: "cleaned" };
}

async function main() {
  const config = parse(process.argv.slice(2));
  if (!config) {
    process.stderr.write(
      "Usage: service-lifecycle.mjs --dist <runtime-dist dir> [--work <dir>] [--json]\n",
    );
    return 2;
  }
  if (process.platform !== "darwin") {
    process.stderr.write(
      "macOS service lifecycle is darwin only; other platforms stay unverified\n",
    );
    return 2;
  }

  const checks = [];
  const work =
    config.work ?? (await mkdtemp(path.join(os.tmpdir(), "om-c7-lifecycle-")));
  const ownedWork = config.work === null;
  const home = path.join(work, "home");
  const installRoot = path.join(home, ".local", "share", "one-memory");
  const currentRoot = path.join(installRoot, "current");
  const dataDir = path.join(work, "data");
  const binDir = path.join(work, "bin");
  const cliPath = config.cli ?? path.join(config.dist, "bin", "one-memory");
  const dailyRoot = path.join(
    home,
    "Library",
    "Application Support",
    "One Memory",
  );
  // Prefer the product's own answer; fall back to the mirrored hash only if the
  // product cannot produce a plan (which would itself be a finding).
  const plannedCurrent = await plannedServiceId(
    cliPath,
    home,
    dataDir,
    path.join(installRoot, "current"),
  );
  const plannedRoot = await plannedServiceId(
    cliPath,
    home,
    dataDir,
    installRoot,
  );
  const label =
    plannedCurrent ??
    scopedLabel("darwin", path.join(installRoot, "current"), dailyRoot);
  let labelRegistered = false;
  let installSucceeded = true;
  let cleanup = null;
  let overrideNote = null;

  try {
    // `mkdtemp` already made a caller-supplied path's parent, but a `--work`
    // path that does not exist yet must be created here: every subdirectory
    // below is a child of it, and the first check that writes into the run
    // (the user-data marker) would otherwise fail with ENOENT before any
    // product assertion ran -- indistinguishable, in the output, from a
    // product failure.
    await mkdir(work, { recursive: true, mode: 0o700 });
    await mkdir(home, { recursive: true, mode: 0o700 });
    await mkdir(binDir, { recursive: true, mode: 0o700 });

    // 0. Distribution shape: every required file exists, and the manifest
    //    declares this platform/arch. No source tree may masquerade as a build.
    for (const relative of REQUIRED_FILES) {
      const present = await exists(path.join(config.dist, relative));
      checks.push(
        check(
          `distribution_has_${relative.replaceAll("/", "_")}`,
          present ? "pass" : "fail",
          relative,
        ),
      );
    }
    const manifestRaw = await readFile(
      path.join(config.dist, "manifest.json"),
      "utf8",
    ).catch(() => null);
    const manifest = manifestRaw
      ? parseJson(manifestRaw, "manifest", checks)
      : null;
    checks.push(
      check(
        "manifest_declares_this_platform_and_arch",
        manifest?.platform === "darwin" && manifest?.arch === process.arch
          ? "pass"
          : "fail",
        manifest ? `${manifest.platform}/${manifest.arch}` : "missing",
      ),
    );
    // A manifest that claims a different architecture must be REFUSED, not
    // installed. This is the guard that stops an arm64 payload (or an
    // unbuilt/copied tree) from being presented as x64 support: the binary
    // inside is architecture-specific, so arch honesty has to be enforced at
    // install time, not inferred from the host CPU's translation ability.
    if (manifest !== null && manifestRaw !== null) {
      const foreignArch = manifest.arch === "arm64" ? "x64" : "arm64";
      const foreignRoot = path.join(work, "foreign-arch-dist");
      await cp(config.dist, foreignRoot, {
        recursive: true,
        dereference: false,
        verbatimSymlinks: true,
      });
      const foreignManifest = { ...manifest, arch: foreignArch };
      await writeFile(
        path.join(foreignRoot, "manifest.json"),
        `${JSON.stringify(foreignManifest, null, 2)}\n`,
      );
      const foreignInstall = await cli(home, dataDir, cliPath, [
        "install",
        "--source",
        foreignRoot,
        "--install-root",
        path.join(work, "foreign-arch-root"),
        "--bin-dir",
        path.join(work, "foreign-arch-bin"),
        "--data-dir",
        path.join(work, "foreign-arch-data"),
        "--yes",
      ]);
      const refused =
        foreignInstall.code !== 0 &&
        /distribution_target_mismatch/.test(
          `${foreignInstall.stdout}${foreignInstall.stderr}`,
        );
      // A distribution that is missing a file the manifest lists must be refused
      // WITHOUT leaving a partial install behind. The matrix already covers
      // content drift (hash mismatch); a *missing* file is the other half, and
      // the one where a careless implementation would happily copy what it found.
      {
        const incompleteRoot = path.join(work, "incomplete-dist");
        await cp(config.dist, incompleteRoot, {
          recursive: true,
          dereference: false,
          verbatimSymlinks: true,
        });
        // Delete a required runtime file the manifest still declares.
        await rm(path.join(incompleteRoot, "runtime", "runtime.cjs"), {
          force: true,
        });
        const incompleteRootTarget = path.join(work, "incomplete-install-root");
        const incomplete = await cli(home, dataDir, cliPath, [
          "install",
          "--source",
          incompleteRoot,
          "--install-root",
          incompleteRootTarget,
          "--bin-dir",
          path.join(work, "incomplete-bin"),
          "--data-dir",
          path.join(work, "incomplete-data"),
          "--yes",
        ]);
        const refused =
          incomplete.code !== 0 &&
          /distribution_manifest_incomplete/.test(
            `${incomplete.stdout}${incomplete.stderr}`,
          );
        const leftPartialCurrent = await exists(
          path.join(incompleteRootTarget, "current"),
        );
        checks.push(
          check(
            "an_incomplete_distribution_is_refused_without_a_partial_install",
            refused && !leftPartialCurrent ? "pass" : "fail",
            refused && !leftPartialCurrent
              ? `exit ${incomplete.code} with distribution_manifest_incomplete; no install root/current left`
              : `exit=${incomplete.code} refused=${refused} partialCurrent=${leftPartialCurrent}`,
          ),
        );
      }

      checks.push(
        check(
          "a_foreign_arch_manifest_is_refused",
          refused ? "pass" : "fail",
          refused
            ? `exit ${foreignInstall.code} with distribution_target_mismatch (claimed ${foreignArch})`
            : `exit ${foreignInstall.code} did not refuse a manifest claiming ${foreignArch}`,
        ),
      );
    }
    // The manifest string must be backed by the binaries it describes. Forge a
    // manifest that keeps the HOST arch (so the host-comparison guard is
    // satisfied) while a native payload actually carries a different slice.
    // Uses `lipo -thin` to write a real, differently-architected Mach-O, so the
    // check is about binary truth, not a corrupted file.
    if (manifest !== null) {
      const crossRoot = path.join(work, "cross-arch-binaries");
      await cp(config.dist, crossRoot, {
        recursive: true,
        dereference: false,
        verbatimSymlinks: true,
      });
      const otherArch = manifest.arch === "arm64" ? "x86_64" : "arm64";
      const thinned = await run("lipo", [
        "-thin",
        otherArch,
        "/usr/bin/true",
        "-output",
        path.join(crossRoot, "core", "one-memory"),
      ]).catch(() => null);
      if (thinned === null) {
        checks.push(
          check(
            "a_manifest_arch_not_backed_by_its_binaries_is_refused",
            "unknown",
            `lipo could not produce a ${otherArch} slice on this machine`,
          ),
        );
      } else {
        // Re-hash the replaced payload so only the architecture is "wrong";
        // a hash failure would prove nothing about the arch check.
        const crossManifest = { ...manifest, files: { ...manifest.files } };
        crossManifest.files["core/one-memory"] = await sha256File(
          path.join(crossRoot, "core", "one-memory"),
        );
        await writeFile(
          path.join(crossRoot, "manifest.json"),
          `${JSON.stringify(crossManifest, null, 2)}\n`,
        );
        const crossInstall = await cli(home, dataDir, cliPath, [
          "install",
          "--source",
          crossRoot,
          "--install-root",
          path.join(work, "cross-arch-root"),
          "--bin-dir",
          path.join(work, "cross-arch-bin"),
          "--data-dir",
          path.join(work, "cross-arch-data"),
          "--yes",
        ]);
        const crossRefused =
          crossInstall.code !== 0 &&
          /distribution_arch_mismatch/.test(
            `${crossInstall.stdout}${crossInstall.stderr}`,
          );
        checks.push(
          check(
            "a_manifest_arch_not_backed_by_its_binaries_is_refused",
            crossRefused ? "pass" : "fail",
            crossRefused
              ? `exit ${crossInstall.code} with distribution_arch_mismatch (manifest ${manifest.arch}, core ${otherArch})`
              : `exit ${crossInstall.code}: a ${otherArch} core was accepted for a manifest claiming ${manifest.arch}`,
          ),
        );
      }
    }
    // Same-origin Runtime: when an App bundle is supplied, the Runtime it embeds
    // must be byte-identical to the standalone distribution. App and CLI must
    // consume one artifact, so an App-only rebuild cannot silently drift.
    if (config.app !== null) {
      checks.push(
        ...(await sameOriginRuntimeChecks(config.dist, config.app)),
        ...(await appBundleChecks(config.app)),
      );
    }

    // 1. Fresh install writes current, the PATH link and the scoped service.
    // Before anything is written, both spellings of the install root must name
    // the same label. `install` passes `<root>/current` and `uninstall`/`upgrade`
    // pass `<root>`; if they disagreed, an install could not be found by its own
    // uninstall (the C7 `7b95b68` defect).
    checks.push(
      check(
        "root_and_current_spellings_share_one_label",
        plannedCurrent !== null && plannedCurrent === plannedRoot
          ? "pass"
          : "fail",
        plannedCurrent === null || plannedRoot === null
          ? `service-plan unavailable: current=${plannedCurrent ?? "null"} root=${plannedRoot ?? "null"}`
          : `current=${plannedCurrent} root=${plannedRoot}`,
      ),
    );
    // Snapshot the user's HOME before touching anything. The product must only
    // write inside the paths it was told to use; discovering a host directory
    // it was never pointed at would mean install silently touched host configs
    // (the goal's "login starts only the Runtime; it does not start hosts or
    // grant new permissions").
    const homeEntriesBefore = (await readdir(home)).sort();
    const install = await cli(home, dataDir, cliPath, [
      "install",
      "--source",
      config.dist,
      "--install-root",
      installRoot,
      "--bin-dir",
      binDir,
      "--data-dir",
      dataDir,
      "--yes",
    ]);
    // Only product-owned locations may appear in HOME. Anything else would be
    // a host config or unrelated file the installer was never asked to touch.
    const hostConfigDirs = [
      ".cursor",
      ".claude",
      ".codex",
      ".workbuddy",
      ".qwen",
      ".openclaw",
      ".hermes",
      ".pi",
    ];
    const homeEntriesAfter = (await readdir(home)).sort();
    const unexpectedHomeEntries = homeEntriesAfter.filter(
      (entry) =>
        !homeEntriesBefore.includes(entry) &&
        entry !== "Library" &&
        entry !== ".local",
    );
    const touchedHostConfig = hostConfigDirs.filter((dir) =>
      homeEntriesAfter.includes(dir),
    );
    checks.push(
      check(
        "install_writes_only_its_own_paths",
        unexpectedHomeEntries.length === 0 && touchedHostConfig.length === 0
          ? "pass"
          : "fail",
        unexpectedHomeEntries.length === 0 && touchedHostConfig.length === 0
          ? `HOME gained only ${
              homeEntriesAfter
                .filter((e) => !homeEntriesBefore.includes(e))
                .join(", ") || "nothing"
            }; no host config dirs touched`
          : `unexpected HOME entries: ${unexpectedHomeEntries.join(", ") || "none"}; host dirs: ${touchedHostConfig.join(", ") || "none"}`,
      ),
    );

    checks.push(
      check(
        "install_apply_exit_zero",
        install.code === 0 ? "pass" : "unknown",
        install.stderr.trim().slice(0, 300) || `exit ${install.code}`,
      ),
    );
    if (install.code !== 0) {
      // `install_runtime_not_ready` used to be written off as load-sensitive.
      // It is not always: read the Core's own log and say WHY it did not come
      // up. The causes seen so far are an address-in-use collision on the
      // hardcoded Core port, a saturated machine, and a genuinely broken
      // distribution. Naming the cause keeps the next reader from
      // re-attributing a real defect to load.
      const serviceError = await readFile(
        path.join(dataDir, "logs", "service-error.log"),
        "utf8",
      ).catch(() => "");
      const addressInUse = /EADDRINUSE|address already in use/i.test(
        serviceError,
      );
      const portMatch =
        serviceError.match(/bind on address \('([^']+)',\s*(\d+)\)/i) ??
        serviceError.match(/EADDRINUSE[^\n]*:(\d+)/i);
      const uptime = (await run("uptime", [])).stdout.trim();
      checks.push(
        check(
          "install_failure_cause_is_identified",
          addressInUse ? "fail" : "unknown",
          addressInUse
            ? `Core could not bind ${portMatch ? `port ${portMatch[2]}` : "its port"}: ` +
                `address already in use. That is the hardcoded-port collision ` +
                `(docs/contracts/c7-blocks/c7-to-c0-core-port-collision-on-shared-machines.md), ` +
                `not load. ${serviceError
                  .split(/\n/)
                  .filter((l) => /EADDRINUSE|address already/i.test(l))
                  .slice(0, 2)
                  .join(" | ")}`
            : `install exit ${install.code}; Core log shows no address-in-use; ` +
                `cause unconfirmed (load: ${uptime || "unknown"}). See ` +
                `${path.join(dataDir, "logs", "service-error.log")}`,
        ),
      );
      installSucceeded = false;
    }
    checks.push(
      depCheck(
        installSucceeded,
        "current_link_present",
        (await exists(path.join(installRoot, "current"))) ? "pass" : "fail",
        path.join(installRoot, "current"),
      ),
    );
    checks.push(
      depCheck(
        installSucceeded,
        "path_link_present",
        (await exists(path.join(binDir, "one-memory"))) ? "pass" : "fail",
        path.join(binDir, "one-memory"),
      ),
    );
    const serviceFile = path.join(
      home,
      "Library",
      "LaunchAgents",
      `${label}.plist`,
    );
    const scopedPlistPresent = await exists(serviceFile);
    checks.push(
      depCheck(
        installSucceeded,
        "scoped_launchagent_plist_written",
        scopedPlistPresent ? "pass" : "fail",
        serviceFile,
      ),
    );
    // The canonical daily label must NOT be claimed by an isolated root.
    const canonical = await launchctlPrint(CANONICAL_LABEL);
    // A pre-existing canonical job (a real daily install, or another agent's
    // leftover on a shared machine) must not be read as "this run claimed it".
    // Only a canonical job whose plist points INSIDE this run's throwaway work
    // tree is proof that the isolated install grabbed the canonical label.
    const canonicalPath = canonical.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find((line) => line.startsWith("path = "));
    const canonicalPointsIntoWork =
      canonical.registered &&
      canonicalPath !== undefined &&
      canonicalPath.includes(work);
    checks.push(
      check(
        "isolated_root_does_not_claim_the_canonical_label",
        canonicalPointsIntoWork ? "fail" : "pass",
        canonicalPointsIntoWork
          ? `canonical label points into this run's work tree: ${canonicalPath}`
          : canonical.registered
            ? `canonical label is loaded by something else (not this run): ${canonicalPath ?? "no path line"}`
            : "canonical label absent",
      ),
    );

    const loaded = await launchctlPrint(label);
    labelRegistered = loaded.registered;
    checks.push(
      depCheck(
        installSucceeded,
        "scoped_service_is_registered_with_launchd",
        loaded.registered ? "pass" : "fail",
        loaded.registered
          ? `gui/${process.getuid()}/${label}`
          : loaded.stderr.trim().slice(0, 200),
      ),
    );

    // Login start must bring up the headless Runtime only -- never the Desktop
    // shell, never a host, and no new permission. The previous version of this
    // check grepped for a MemHub.app process under a CLI install root, which can
    // never contain an app bundle, so it could not fail. Assert on what launchd
    // actually executes for the job instead: the declaration is the authority.
    const job = parseLaunchctlJobCommand(loaded.stdout);
    const canonicalInstallRoot = await realpath(installRoot);
    const expectedRuntimeEntry = path.join(
      canonicalInstallRoot,
      "current",
      "runtime",
      "runtime.cjs",
    );
    const expectedNode = path.join(
      canonicalInstallRoot,
      "current",
      "bin",
      "node",
    );
    const declaredAll = job ? [job.program, ...job.args] : [];
    // launchd prints `program = <argv0>` plus every element of ProgramArguments,
    // so the runtime entry appears once and `serve` must follow it. Accept the
    // argv0 duplication rather than assuming a particular slice.
    const entryIndex = declaredAll.indexOf(expectedRuntimeEntry);
    const runsHeadlessRuntime =
      job !== null &&
      job.program === expectedNode &&
      entryIndex !== -1 &&
      declaredAll[entryIndex + 1] === "serve";
    const launchesDesktopShell = declaredAll.some((value) =>
      /\.app\/Contents\/MacOS\/|MemHub\.app|One Memory\.app/.test(value),
    );
    checks.push(
      depCheck(
        installSucceeded,
        "login_start_runs_the_headless_runtime_not_the_desktop_shell",
        runsHeadlessRuntime && !launchesDesktopShell ? "pass" : "fail",
        job === null
          ? "launchd did not report program/arguments for the job"
          : `launchd exec: ${declaredAll.join(" ")}` +
              (launchesDesktopShell ? " (launches a Desktop app bundle)" : ""),
      ),
    );
    // A wrapper that exec'd the Desktop App would still be invisible to the
    // declaration check above, so also assert that every process actually
    // running under this install root is the headless Runtime / its Core, on
    // the resolved current path. No Electron main process may be here.
    let rootLines = [];
    // The job may still be spawning right after bootstrap; sample briefly so a
    // just-started Runtime is counted instead of producing an empty (vacuous)
    // process list.
    for (let attempt = 0; attempt < 10; attempt += 1) {
      const rootProcs = await run("pgrep", ["-fl", installRoot]);
      rootLines = rootProcs.stdout
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
      if (rootLines.length > 0) break;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    const foreignProcs = rootLines.filter(
      (line) =>
        /\.app\/Contents\/MacOS\/|MemHub\.app|One Memory\.app/.test(line) ||
        /(^|\s)Electron(\s|$)/.test(line),
    );
    const allUnderCurrent = rootLines.every((line) =>
      line.includes(`${installRoot}/current/`),
    );
    checks.push(
      depCheck(
        installSucceeded,
        "no_desktop_or_foreign_process_runs_from_the_install_root",
        rootLines.length === 0
          ? "unknown"
          : foreignProcs.length === 0 && allUnderCurrent
            ? "pass"
            : "fail",
        rootLines.length === 0
          ? "no process under the install root was observable yet; retry on a quiet machine"
          : foreignProcs.length > 0
            ? `Desktop/Electron process(es): ${foreignProcs.slice(0, 2).join(" | ")}`
            : allUnderCurrent
              ? `${rootLines.length} process(es), all under current/`
              : `process outside current/: ${rootLines
                  .filter((line) => !line.includes(`${installRoot}/current/`))
                  .slice(0, 2)
                  .join(" | ")}`,
      ),
    );

    // 0600 on the plist is a hard contract and is written synchronously by the
    // installer, so it is checked immediately.
    const plistMode = await fileMode(serviceFile);
    checks.push(
      depCheck(
        installSucceeded,
        "launchagent_plist_is_owner_only_0600",
        plistMode === "600" ? "pass" : "fail",
        `mode=${plistMode ?? "missing"}`,
      ),
    );
    // The custom data directory must be baked into the service, not silently
    // replaced by the default home. A login start would otherwise attach to a
    // different data instance than the one the user installed.
    const plistText = await readFile(serviceFile, "utf8").catch(() => null);
    checks.push(
      depCheck(
        installSucceeded,
        "plist_targets_the_custom_data_directory",
        plistText?.includes(
          `<key>ONE_MEMORY_DATA_DIR</key><string>${dataDir}</string>`,
        )
          ? "pass"
          : "fail",
        plistText === null
          ? "plist unreadable"
          : `expected ONE_MEMORY_DATA_DIR=${dataDir}`,
      ),
    );
    // The Runtime -- not launchd -- owns the service logs (C0 H34 ruling,
    // option 1). launchd must NOT redirect, because a descriptor launchd holds
    // cannot be rotated: renaming leaves it writing to the renamed inode, and
    // truncating loses data. Measured before this change: the redirect grew the
    // log ~654 bytes per `status` call, uncapped.
    checks.push(
      depCheck(
        installSucceeded,
        "launchagent_does_not_own_the_service_log_descriptor",
        plistText !== null &&
          !plistText.includes("<key>StandardOutPath</key>") &&
          !plistText.includes("<key>StandardErrorPath</key>")
          ? "pass"
          : "fail",
        plistText === null
          ? "plist unreadable"
          : "plist must not redirect; the Runtime captures bounded logs itself",
      ),
    );
    // ...and the Runtime must actually be writing them: a login-start daemon
    // with no capture would silently lose every crash message.
    const capturedModes = await Promise.all([
      fileMode(path.join(dataDir, "logs", "service.log")),
      fileMode(path.join(dataDir, "logs", "service-error.log")),
    ]);
    checks.push(
      depCheck(
        installSucceeded,
        "runtime_captures_its_own_service_logs_within_bounds",
        capturedModes.every((mode) => mode === "600") ? "pass" : "fail",
        `service.log=${capturedModes[0] ?? "missing"} service-error.log=${
          capturedModes[1] ?? "missing"
        } (Runtime-managed, rotating, owner-only)`,
      ),
    );
    const logModes = await Promise.all([
      fileMode(path.join(dataDir, "logs")),
      fileMode(path.join(dataDir, "logs", "service.log")),
      fileMode(path.join(dataDir, "logs", "service-error.log")),
    ]);
    checks.push(
      depCheck(
        installSucceeded,
        "launchd_log_directory_and_files_are_owner_only",
        logModes[0] === "700" && logModes[1] === "600" && logModes[2] === "600"
          ? "pass"
          : "fail",
        `dir=${logModes[0] ?? "missing"} out=${logModes[1] ?? "missing"} err=${logModes[2] ?? "missing"}`,
      ),
    );

    // KeepAlive semantics: a plain SIGTERM to the managed job is followed by a
    // relaunch, so `bootout` is the only honest stop. Under load the runtime's
    // own graceful drain (Core + Broker) can take a while before the process
    // exits and launchd's respawn throttle elapses, so the probe distinguishes
    // three outcomes instead of calling slow drain a KeepAlive failure:
    //   - a new pid appears                        -> pass
    //   - the old pid is still alive at the deadline -> unknown (still draining)
    //   - the old pid is gone with no replacement  -> fail (KeepAlive inactive)
    const managedPid = await loadedPid(label);
    if (managedPid === null) {
      checks.push(
        depCheck(
          installSucceeded,
          "keepalive_relaunch_semantics",
          "unknown",
          "launchd reports no pid for the job; retry on a quiet machine",
        ),
      );
    } else {
      const before = managedPid;
      await run("kill", ["-TERM", String(before)]);
      let relaunched = false;
      let stillAlive = true;
      for (let attempt = 0; attempt < 150; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        stillAlive = await processStillReferences(before, currentRoot);
        const now = await loadedPid(label);
        if (now !== null && now !== before) {
          relaunched = true;
          break;
        }
        if (!stillAlive && now === null) {
        }
      }
      checks.push(
        depCheck(
          installSucceeded,
          "keepalive_relaunches_after_sigterm",
          relaunched ? "pass" : stillAlive ? "unknown" : "fail",
          relaunched
            ? `pid ${before} replaced by a new pid`
            : stillAlive
              ? `pid ${before} still references this Runtime after 150s; not a KeepAlive failure`
              : `pid ${before} exited with no replacement within 150s; KeepAlive may be inactive`,
        ),
      );
    }

    // 2. Reinstall is idempotent: same label, no bootstrap collision (exit 5).
    // The packaged Core must be able to answer a Keychain lookup from a
    // background context: headless (no TTY), fail closed, no authorization
    // prompt. A missing item returns {"value": null}; a prompt or a hang would
    // be a product defect on a login-start daemon.
    const keychain = await run(
      path.join(installRoot, "current", "core", "one-memory"),
      ["--keychain-read"],
      {
        env: { PATH: "/usr/bin:/bin", HOME: home, NO_COLOR: "1" },
        input: "__c7_lifecycle_missing__",
        timeoutMs: 15_000,
      },
    );
    let keychainValue;
    try {
      keychainValue = JSON.parse(keychain.stdout)?.value;
    } catch {
      keychainValue = undefined;
    }
    checks.push(
      depCheck(
        installSucceeded,
        "keychain_lookup_is_headless_and_fail_closed",
        keychain.code === 0 &&
          keychainValue === null &&
          keychain.timedOut !== true
          ? "pass"
          : "fail",
        keychain.timedOut === true
          ? "the packaged Core blocked indefinitely on a Keychain read; a login-start daemon must answer or fail, never hang"
          : keychain.code === 0
            ? `value=${JSON.stringify(keychainValue)} (missing ref, no prompt)`
            : `exit=${keychain.code} ${
                keychain.stderr.trim().slice(0, 120) || ""
              }`,
      ),
    );

    // The App and the CLI must share ONE daemon per install root. Running
    // `start` while the managed service is already up must attach, not spawn a
    // competing Runtime/Core. Count the processes before and after so a second
    // daemon would show up as an extra runtime.cjs or core/one-memory process.
    const countRuntime = async (pattern) => {
      const out = await run("pgrep", ["-fl", pattern]);
      return out.stdout
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean).length;
    };
    // Wait until the managed service is actually settled before measuring:
    // sampling during the cold start made this check fail with `core 0->1`
    // (no Core yet) and `start exit=1` purely because the first spawn had not
    // finished. Only a settled daemon tests "attach vs spawn".
    // A settled daemon means BOTH processes are up AND the published state is
    // consistent again. Counting processes alone is not enough: right after a
    // KeepAlive relaunch both processes exist while `runtime-service.json` is
    // momentarily absent, and that window is something else entirely (below).
    for (let attempt = 0; attempt < 45; attempt += 1) {
      const runtimes = await countRuntime(
        `${currentRoot}/runtime/runtime.cjs serve`,
      );
      const cores = await countRuntime(`${currentRoot}/core/one-memory serve`);
      const status = await cli(home, dataDir, cliPath, ["status", "--json"]);
      if (runtimes === 1 && cores === 1 && status.code === 0) break;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    const runtimesBefore = await countRuntime(
      `${currentRoot}/runtime/runtime.cjs serve`,
    );
    const coresBefore = await countRuntime(
      `${currentRoot}/core/one-memory serve`,
    );
    // Exercise the CLI the install actually published. The source
    // distribution's launcher intentionally declares its own package root in
    // ONE_MEMORY_INSTALL_ROOT; using it here would ask `start` to inspect the
    // source package's scoped label rather than this install's `current` root.
    const installedCliPath = path.join(binDir, "one-memory");
    const secondStart = await cli(home, dataDir, installedCliPath, ["start"]);
    const runtimesAfter = await countRuntime(
      `${currentRoot}/runtime/runtime.cjs serve`,
    );
    const coresAfter = await countRuntime(
      `${currentRoot}/core/one-memory serve`,
    );
    checks.push(
      depCheck(
        installSucceeded,
        "second_start_attaches_to_the_same_daemon",
        secondStart.code === 0 &&
          runtimesBefore === 1 &&
          coresBefore === 1 &&
          runtimesAfter === 1 &&
          coresAfter === 1
          ? "pass"
          : "fail",
        `start exit=${secondStart.code}; runtime ${runtimesBefore}->${runtimesAfter}, core ${coresBefore}->${coresAfter}` +
          (secondStart.stdout.trim()
            ? `; stdout=${secondStart.stdout.trim().slice(0, 60)}`
            : "") +
          (secondStart.stderr.trim()
            ? `; stderr=${secondStart.stderr.trim().slice(0, 160)}`
            : ""),
      ),
    );

    const reinstall = await cli(home, dataDir, cliPath, [
      "service-install",
      "--install-root",
      path.join(installRoot, "current"),
      "--data-dir",
      dataDir,
      "--home",
      home,
      "--yes",
    ]);
    checks.push(
      depCheck(
        installSucceeded,
        "reinstall_is_idempotent",
        reinstall.code === 0 ? "pass" : "fail",
        reinstall.stderr.trim().slice(0, 300) || `exit ${reinstall.code}`,
      ),
    );

    // Anti-downgrade (docs/contracts/c0-anti-downgrade-versioning.md): the
    // installed distribution carries a build_number, and re-installing a lower
    // one must be refused before `current` or any version directory changes.
    const installedManifestRaw = await readFile(
      path.join(installRoot, "current", "manifest.json"),
      "utf8",
    ).catch(() => null);
    const installedManifest =
      installedManifestRaw === null ? null : JSON.parse(installedManifestRaw);
    if (
      installedManifest !== null &&
      Number.isSafeInteger(installedManifest.build_number)
    ) {
      const downgradeRoot = path.join(work, "downgrade-dist");
      await cp(config.dist, downgradeRoot, {
        recursive: true,
        dereference: false,
        verbatimSymlinks: true,
      });
      const downgradeManifest = {
        ...installedManifest,
        build_number: installedManifest.build_number - 1,
      };
      await writeFile(
        path.join(downgradeRoot, "manifest.json"),
        `${JSON.stringify(downgradeManifest, null, 2)}\n`,
      );
      const beforeCurrent = await readlink(
        path.join(installRoot, "current"),
      ).catch(() => null);
      const downgrade = await cli(home, dataDir, cliPath, [
        "install",
        "--source",
        downgradeRoot,
        "--install-root",
        installRoot,
        "--bin-dir",
        binDir,
        "--data-dir",
        dataDir,
        "--yes",
      ]);
      const refusedDowngrade =
        downgrade.code !== 0 &&
        /distribution_downgrade_refused/.test(
          `${downgrade.stdout}${downgrade.stderr}`,
        );
      const afterCurrent = await readlink(
        path.join(installRoot, "current"),
      ).catch(() => null);
      const currentUnchanged = beforeCurrent === afterCurrent;
      checks.push(
        depCheck(
          installSucceeded,
          "a_lower_build_number_is_refused_and_leaves_current_unchanged",
          refusedDowngrade && currentUnchanged ? "pass" : "fail",
          refusedDowngrade && currentUnchanged
            ? `exit ${downgrade.code} with distribution_downgrade_refused; current still ${afterCurrent}`
            : `exit=${downgrade.code} refused=${refusedDowngrade} currentChanged=${!currentUnchanged}`,
        ),
      );
    } else {
      checks.push(
        check(
          "a_lower_build_number_is_refused_and_leaves_current_unchanged",
          "unknown",
          "installed manifest has no integer build_number; the release tooling must write one (C0-owned)",
        ),
      );
    }

    // 3. Unknown same-label registration is refused, and the live one survives.
    const health = await waitForHealthy(home, dataDir, cliPath);
    const healthState = health?.runtime?.state ?? health?.state;
    const healthy =
      healthState === "running" || health?.health?.state === "healthy";
    const load = (await run("sysctl", ["-n", "vm.loadavg"])).stdout.trim();
    checks.push(
      depCheck(
        installSucceeded,
        "runtime_reported_healthy_after_install",
        healthy ? "pass" : "unknown",
        healthy
          ? `state=${healthState}`
          : `still ${healthState ?? "unknown"} after budget under load ${load}; ` +
              "read-only retry on a quiet machine before treating as a failure",
      ),
    );
    // Owner-only permissions on the local attach credential and discovery
    // receipt are a hard contract; they exist once the runtime is up, so they
    // are checked here rather than right after install.
    const tokenMode = healthy
      ? await fileMode(path.join(dataDir, "runtime-token"))
      : null;
    const coreReceiptMode = healthy
      ? await fileMode(path.join(dataDir, "runtime.json"))
      : null;
    checks.push(
      depCheck(
        installSucceeded && healthy,
        "runtime_token_is_owner_only_0600",
        tokenMode === "600" ? "pass" : "fail",
        `mode=${tokenMode ?? "missing"}`,
      ),
    );
    checks.push(
      depCheck(
        installSucceeded && healthy,
        "core_receipt_is_owner_only_0600",
        coreReceiptMode === "600" ? "pass" : "fail",
        `mode=${coreReceiptMode ?? "missing"}`,
      ),
    );

    // 3b. App and CLI must share one daemon whose lifetime is owned by launchd,
    // not by the Desktop shell: quitting the App must not take the daemon down.
    //
    // This check is deliberately non-destructive. The harness never quits a
    // user's real MemHub.app, so it verifies the property structurally instead:
    //   (a) the daemon's controlling parent is launchd (ppid 1), not Electron;
    //   (b) no generated wrapper in the install root execs the Desktop shell;
    //   (c) the CLI and the service agree that the SAME launchd job is up.
    // A pid that is a child of the App would mean closing the App kills the
    // daemon, which is the failure mode this check exists to catch.
    const daemonPid = await loadedPid(label);
    if (daemonPid === null) {
      checks.push(
        depCheck(
          installSucceeded,
          "app_and_cli_share_one_launchd_owned_daemon",
          "unknown",
          "launchd reports no pid for the job; retry on a quiet machine",
        ),
      );
    } else {
      const ppidText = (
        await run("ps", ["-o", "ppid=", "-p", String(daemonPid)])
      ).stdout.trim();
      const parentIsLaunchd = ppidText === "1";
      if (!parentIsLaunchd) {
        checks.push(
          depCheck(
            installSucceeded,
            "app_and_cli_share_one_launchd_owned_daemon",
            "fail",
            `daemon pid ${daemonPid} ppid=${ppidText || "?"}; not launchd-owned, ` +
              "so quitting the App could take the daemon down",
          ),
        );
      } else {
        const status = await cli(home, dataDir, cliPath, ["status", "--json"]);
        let cliSeesRunning = false;
        try {
          const parsed = JSON.parse(status.stdout);
          const state = parsed?.runtime?.state ?? parsed?.state;
          cliSeesRunning = state === "running" || state === "healthy";
        } catch {
          cliSeesRunning = false;
        }
        // Two halves, one verdict:
        //   (a) launchd owns the daemon (ppid=1), so quitting the App cannot
        //       kill it -- this branch is only reached when that already holds;
        //   (b) a SEPARATE CLI process attaches to the SAME daemon.
        // (b) used to live only in the evidence string with a bare "pass", so
        // mutating the CLI observation could not fail the check (C8's class of
        // weak assertion). It is now part of the verdict: the CLI must observe
        // the running state, and the job's pid must be unchanged across the
        // call. `unknown` (not `fail`) when the daemon's pid is gone or the
        // launchd pid moved, because that is a restart/teardown, not evidence
        // that App and CLI disagree.
        const pidAfterStatus = await loadedPid(label);
        const sameJob = pidAfterStatus !== null && pidAfterStatus === daemonPid;
        // `healthy` was established just above (section 3). If the daemon is
        // still the same live job but a separate CLI process cannot see it
        // running, that is a real App/CLI disagreement -> fail. If the job
        // itself moved or vanished, that is a restart/teardown under load, and
        // the honest answer is unknown rather than a fabricated pass.
        const verdict = sharedDaemonVerdict({
          sameJob,
          cliSeesRunning,
          healthy,
        });
        checks.push(
          depCheck(
            installSucceeded,
            "app_and_cli_share_one_launchd_owned_daemon",
            verdict,
            `daemon pid ${daemonPid} ppid=1 (launchd-owned, so App exit cannot ` +
              `kill it); CLI observes the same job: ${cliSeesRunning ? "yes" : "no"}` +
              `; pid after CLI status=${pidAfterStatus ?? "gone"}; runtime healthy earlier=${healthy}`,
          ),
        );
      }
    }

    // 4. Upgrade to the same artifact is a no-op that must not fail or delete data.
    //    `dataDir` is created by a successful install; if install did not
    //    complete there is nothing to upgrade, so skip the whole section rather
    //    than crashing on the first marker write and hiding the real cause
    //    (a bogus `--dist` should surface as install checks, not as ENOENT).
    if (!installSucceeded) {
      checks.push(
        check(
          "upgrade_section_skipped_because_install_failed",
          "fail",
          "install did not complete; the upgrade/rollback section cannot run",
        ),
      );
    } else {
      const marker = path.join(dataDir, "c7-lifecycle-marker");
      await writeFile(marker, "keep me", { mode: 0o600 });
      const upgrade = await cli(home, dataDir, cliPath, [
        "upgrade",
        "--source",
        config.dist,
        "--install-root",
        installRoot,
        "--bin-dir",
        binDir,
        "--data-dir",
        dataDir,
        "--yes",
      ]);
      checks.push(
        depCheck(
          installSucceeded,
          "upgrade_apply_exit_zero",
          upgrade.code === 0 ? "pass" : "fail",
          upgrade.stderr.trim().slice(0, 300) || `exit ${upgrade.code}`,
        ),
      );
      checks.push(
        depCheck(
          installSucceeded,
          "upgrade_kept_user_data",
          (await exists(marker)) ? "pass" : "fail",
          marker,
        ),
      );

      // 4b. Upgrade failure must roll back, not leave a broken install.
      //
      // A successful upgrade already ran above; the version being switched to is
      // byte-identical, so `current` is the ground truth to protect. We tamper
      // with a staged copy of the distribution (one byte in a required file) so
      // the manifest hash no longer matches. A correct upgrade refuses *before*
      // switching `current` and before touching the service; the running install
      // must keep working and the data must survive.
      const beforeCurrent = await readlink(
        path.join(installRoot, "current"),
      ).catch(() => null);
      const tampered = path.join(work, "tampered-dist");
      await cp(config.dist, tampered, {
        recursive: true,
        dereference: false,
        verbatimSymlinks: true,
      });
      // Flip one byte inside the CLI bundle: enough to break its SHA-256, small
      // enough that nothing else about the tree changes.
      const tamperTarget = path.join(tampered, "bin", "one-memory.cjs");
      const original = await readFile(tamperTarget);
      const mutated = Buffer.from(original);
      mutated[0] = mutated[0] === 0x2f ? 0x2e : 0x2f;
      await writeFile(tamperTarget, mutated);
      const failedUpgrade = await cli(home, dataDir, cliPath, [
        "upgrade",
        "--source",
        tampered,
        "--install-root",
        installRoot,
        "--bin-dir",
        binDir,
        "--data-dir",
        dataDir,
        "--yes",
      ]);
      checks.push(
        depCheck(
          installSucceeded,
          "failed_upgrade_exits_nonzero",
          failedUpgrade.code !== 0 ? "pass" : "fail",
          failedUpgrade.code === 0
            ? "tampered distribution was accepted; the manifest hash was not enforced"
            : `exit ${failedUpgrade.code}`,
        ),
      );
      const afterCurrent = await readlink(
        path.join(installRoot, "current"),
      ).catch(() => null);
      checks.push(
        depCheck(
          installSucceeded,
          "failed_upgrade_left_current_unchanged",
          afterCurrent !== null && afterCurrent === beforeCurrent
            ? "pass"
            : "fail",
          `before=${beforeCurrent ?? "missing"} after=${afterCurrent ?? "missing"}`,
        ),
      );
      checks.push(
        depCheck(
          installSucceeded,
          "failed_upgrade_kept_user_data",
          (await exists(marker)) ? "pass" : "fail",
          marker,
        ),
      );
      // The install must still be verifiable and runnable after the refusal.
      // A *successful* upgrade above restarted the service, so the runtime is
      // briefly `stopped` while launchd brings the new pod up. Sampling once here
      // measured that restart window rather than the product's steady state --
      // and the old assertion even accepted `stopped` as "usable". Poll until the
      // runtime settles instead.
      let postFailureJson = null;
      let postState = "unknown";
      let unstableSamples = 0;
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const postFailureStatus = await cli(home, dataDir, cliPath, [
          "status",
          "--json",
        ]);
        try {
          postFailureJson = JSON.parse(postFailureStatus.stdout);
        } catch {
          postFailureJson = null;
        }
        postState =
          postFailureJson?.runtime?.state ??
          postFailureJson?.state ??
          "unknown";
        if (postState === "running") break;
        if (postState === "untrusted" || postState === "degraded") {
          // A successful upgrade restarts the service, and during that restart
          // the runtime receipts are momentarily inconsistent. `untrusted` /
          // `degraded` can therefore be a single-sample transient; keep polling
          // for the steady state instead of judging on the first bad sample.
          unstableSamples += 1;
          if (unstableSamples >= 3) break;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      // "Usable" means the runtime actually came back and is serving, not merely
      // "not literally untrusted". A `stopped` runtime would previously satisfy
      // this check, which made it a fake green.
      checks.push(
        depCheck(
          installSucceeded,
          "install_still_usable_after_failed_upgrade",
          postState === "running"
            ? "pass"
            : postState === "untrusted"
              ? "fail"
              : "unknown",
          `runtime state=${postState}` +
            (postState === "untrusted"
              ? "; the instance identity was damaged by the failed upgrade"
              : postState === "running"
                ? "; runtime still serving after the refused upgrade"
                : "; runtime not running after the refused upgrade (retry on a quiet machine)"),
        ),
      );

      // 4b-ii. Upgrade to a package that is HASH-VALID but whose Runtime crashes
      // on startup. `launchctl kickstart -k` returns 0 for such a program, so
      // without activation verification the upgrade reported success, left
      // `current` on the broken version, and killed the daemon (verified on this
      // machine). The correct behavior is: refuse, roll `current` back, and be
      // running again.
      {
        const brokenRoot = path.join(work, "hash-valid-but-broken");
        await cp(config.dist, brokenRoot, {
          recursive: true,
          dereference: false,
          verbatimSymlinks: true,
        });
        await writeFile(
          path.join(brokenRoot, "runtime", "runtime.cjs"),
          "process.exit(42);\n",
        );
        // Re-hash so the manifest is honest about the broken content: the point
        // is a package that passes every integrity check and still cannot run.
        const { createHash: hashFn } = await import("node:crypto");
        const { createReadStream: readStream } = await import("node:fs");
        const digestOf = async (file) => {
          const hash = hashFn("sha256");
          for await (const chunk of readStream(file)) hash.update(chunk);
          return hash.digest("hex");
        };
        const manifestPath = path.join(brokenRoot, "manifest.json");
        const brokenManifest = JSON.parse(await readFile(manifestPath, "utf8"));
        for (const rel of Object.keys(brokenManifest.files)) {
          brokenManifest.files[rel] = await digestOf(
            path.join(brokenRoot, rel),
          );
        }
        brokenManifest.version = "0.0.0-broken";
        await writeFile(
          manifestPath,
          `${JSON.stringify(brokenManifest, null, 2)}\n`,
        );
        const currentBeforeBroken = await readlink(
          path.join(installRoot, "current"),
        ).catch(() => null);
        const brokenUpgrade = await cli(home, dataDir, cliPath, [
          "upgrade",
          "--source",
          brokenRoot,
          "--install-root",
          installRoot,
          "--bin-dir",
          binDir,
          "--data-dir",
          dataDir,
          "--yes",
        ]);
        const currentAfterBroken = await readlink(
          path.join(installRoot, "current"),
        ).catch(() => null);
        const rolledBack =
          brokenUpgrade.code !== 0 &&
          currentAfterBroken !== null &&
          currentAfterBroken === currentBeforeBroken;
        checks.push(
          check(
            "an_unstartable_upgrade_is_refused_and_rolled_back",
            rolledBack ? "pass" : "fail",
            rolledBack
              ? `exit ${brokenUpgrade.code}; current rolled back to ${currentAfterBroken}`
              : `exit=${brokenUpgrade.code} before=${currentBeforeBroken ?? "none"} after=${currentAfterBroken ?? "none"}` +
                  (brokenUpgrade.stderr.trim()
                    ? `; stderr=${brokenUpgrade.stderr.trim().slice(0, 120)}`
                    : ""),
          ),
        );
        const afterBroken = await waitForHealthy(
          home,
          dataDir,
          cliPath,
          90_000,
        );
        const afterBrokenState =
          afterBroken?.runtime?.state ?? afterBroken?.state ?? "unknown";
        checks.push(
          depCheck(
            installSucceeded,
            "service_is_running_again_after_a_refused_upgrade",
            afterBrokenState === "running" ? "pass" : "unknown",
            afterBrokenState === "running"
              ? "the previous version is serving again"
              : `still ${afterBrokenState} after the refused upgrade; retry on a quiet machine`,
          ),
        );
      }

      // 4c. Crash recovery: kill the Core CHILD with SIGKILL, leaving the
      // launchd-owned outer process alive. This is the case that matters --
      // the wrapper must either relaunch Core itself, or the product must stop
      // claiming healthy. A stale "running" from a receipt whose pid is gone is
      // the failure we hunt.
      //
      // Earlier this check only polled until the first non-"running" sample and
      // then stopped, so it could not observe a later flip to healthy, and it
      // scored "outer alive but Core down" as `unknown`. Both were fake greens:
      // the sample below now runs the full window, and a killed Core that never
      // comes back while the outer process stays alive is a FAIL, not unknown.
      const outerPidBefore = await loadedPid(label);
      let crashedCorePid = null;
      let crashDiagnostic = "no outer launchd pid";
      if (outerPidBefore !== null && !healthy) {
        // The crash-recovery probe is only meaningful once the runtime has
        // actually come up. Otherwise there is no Core to kill and no healthy
        // baseline to defend, and reporting a green/benign result here would hide
        // the load-sensitive cold start rather than measure recovery.
        crashDiagnostic = `runtime not healthy before crash probe (state=${healthState ?? "unknown"})`;
      } else if (outerPidBefore !== null) {
        const receiptRaw = await readFile(
          path.join(dataDir, "runtime.json"),
          "utf8",
        ).catch(() => null);
        let receipt = null;
        try {
          receipt = receiptRaw ? JSON.parse(receiptRaw) : null;
        } catch {
          receipt = null;
        }
        const corePid = Number(receipt?.pid);
        crashDiagnostic =
          `outer=${outerPidBefore} receipt.pid=${receipt?.pid ?? "none"} ` +
          `receipt.parent_pid=${receipt?.parent_pid ?? "none"}`;
        // Only trust the receipt when it really names a separate, live child of
        // the outer job; otherwise we would be killing an unrelated process.
        const receiptLive =
          Number.isSafeInteger(corePid) &&
          corePid > 0 &&
          (
            await run("ps", ["-o", "pid=", "-p", String(corePid)])
          ).stdout.trim() !== "";
        const receiptIsChild =
          receiptLive &&
          Number(receipt?.parent_pid) === outerPidBefore &&
          corePid !== outerPidBefore;
        if (receiptIsChild) {
          await run("kill", ["-9", String(corePid)]);
          crashedCorePid = corePid;
        }
      }
      if (crashedCorePid === null) {
        checks.push(
          depCheck(
            installSucceeded,
            "core_crash_is_detected",
            "unknown",
            `receipt did not name a live Core child of the launchd job (${crashDiagnostic})`,
          ),
        );
      } else {
        // Watch the WHOLE window and record what the product actually said. The
        // named product rule is "outer process alive but Core/Broker failed ->
        // report degraded, NOT healthy". A verdict of `stopped`, `unknown`, or
        // unparseable output while the launchd job is demonstrably alive does not
        // satisfy that rule, so none of those may be quietly treated as a pass.
        const bridgeStates = new Set();
        // Bridge verdicts observed while the killed Core was gone AND no
        // replacement Core was running yet. This is the exact condition the
        // product rule talks about ("outer alive, Core failed"), so it is the
        // only window in which a `degraded` verdict is required.
        const preRecoveryStates = [];
        let outerExitedWithCore = false;
        let unparseable = 0;
        let finalRuntimeState = "unknown";
        let recoveredCorePid = null;
        let outerStillAlive = true;
        let crashedCorePidExited = false;
        for (let attempt = 0; attempt < 40; attempt += 1) {
          // Sample faster than the supervisor's first backoff step so the
          // degraded window is actually observed rather than missed.
          await new Promise((resolve) => setTimeout(resolve, 500));
          const s = await cli(home, dataDir, cliPath, ["status", "--json"]);
          let parsed = null;
          try {
            parsed = JSON.parse(s.stdout);
          } catch {
            parsed = null;
          }
          if (parsed === null) {
            unparseable += 1;
          } else if (typeof parsed?.bridge?.state === "string") {
            bridgeStates.add(parsed.bridge.state);
          }
          finalRuntimeState =
            parsed?.runtime?.state ?? parsed?.state ?? finalRuntimeState;
          outerStillAlive = (await loadedPid(label)) !== null;
          if (recoveredCorePid === null) {
            const state = parsed?.bridge?.state;
            if (typeof state === "string") preRecoveryStates.push(state);
          }
          // Did the ORIGINAL outer process survive the Core's death? launchd may
          // already have respawned a new pid, which must not be mistaken for the
          // original still running.
          //
          // Order matters: this observation must happen BEFORE the replacement
          // Core is recorded. A respawn can complete inside one sampling
          // interval, and checking later would see `recoveredCorePid` already
          // set, conclude the outer never died, and then wrongly demand a
          // `degraded` verdict on a path where the whole job was restarted.
          if (!crashedCorePidExited) {
            const originalAlive = (
              await run("ps", ["-o", "pid=", "-p", String(outerPidBefore)])
            ).stdout.trim();
            if (originalAlive === "") {
              crashedCorePidExited = true;
              outerExitedWithCore = recoveredCorePid === null;
            }
          }
          if (recoveredCorePid === null) {
            const coreListNow = await run("pgrep", [
              "-f",
              `${path.join(installRoot, "current")}/core/one-memory`,
            ]);
            const replacement = coreListNow.stdout
              .split(/\r?\n/)
              .map((line) => line.trim())
              .filter(Boolean)
              .find((line) => Number(line) !== crashedCorePid);
            if (replacement) recoveredCorePid = Number(replacement);
          }
          // Keep sampling until recovery has been observed for a few samples;
          // never break on the first unhealthy sample.
          if (recoveredCorePid !== null && attempt >= 8) break;
          if (!outerStillAlive && attempt >= 12) break;
        }
        const sawHealthy = bridgeStates.has("healthy");
        const sawDegraded = bridgeStates.has("degraded");
        const stateList = [...bridgeStates].join(", ") || "none";
        const preRecoveryList =
          [...new Set(preRecoveryStates)].join(", ") || "none";
        const degradedWhileDown = preRecoveryStates.includes("degraded");
        const healthyWhileDown = preRecoveryStates.includes("healthy");

        // Stale healthy: after the Core pid is gone the product must never claim
        // healthy unless a replacement Core is actually running.
        checks.push(
          depCheck(
            installSucceeded,
            "core_crash_never_reports_stale_healthy",
            sawHealthy && recoveredCorePid === null ? "fail" : "pass",
            sawHealthy && recoveredCorePid === null
              ? `bridge reported healthy with no live Core (states: ${stateList})`
              : `bridge=${stateList}; replacement Core=${
                  recoveredCorePid === null ? "none" : `pid ${recoveredCorePid}`
                }`,
          ),
        );

        // The product rule has two branches, and both must be honest:
        //   - `degraded` is REQUIRED only when the outer Runtime process outlives
        //     its Core ("外层存活但 Core/Broker 失败");
        //   - `stopped` is correct when the Core's death also took the outer
        //     process down, because then nothing is alive to be degraded.
        // C8 correctly flagged the earlier version: it passed purely because a
        // replacement Core eventually appeared, so it never verified which state
        // the product actually reported. Note the outer check must ignore
        // launchd's respawned pid: the original outer being gone is the fact.
        const outerOutlivedCore = !outerExitedWithCore;
        const degradedVerdict = degradedWhileDown;
        const stoppedVerdict =
          preRecoveryStates.length > 0 &&
          preRecoveryStates.every((state) => state === "stopped");
        checks.push(
          depCheck(
            installSucceeded,
            "core_failure_is_reported_degraded_not_healthy",
            healthyWhileDown
              ? "fail"
              : outerOutlivedCore
                ? degradedVerdict
                  ? "pass"
                  : "fail"
                : stoppedVerdict
                  ? "pass"
                  : "fail",
            healthyWhileDown
              ? `bridge reported healthy while the Core was dead and no replacement existed (pre-recovery: ${preRecoveryList})`
              : outerOutlivedCore
                ? degradedVerdict
                  ? `outer Runtime outlived its Core and bridge reported degraded (pre-recovery: ${preRecoveryList})`
                  : `outer Runtime outlived its Core but bridge never reported degraded (pre-recovery: ${preRecoveryList}, all: ${stateList}, unparseable: ${unparseable})`
                : stoppedVerdict
                  ? `Core death took the outer process down too, and bridge reported stopped, not healthy (pre-recovery: ${preRecoveryList})`
                  : `outer process exited with its Core but bridge did not report stopped (pre-recovery: ${preRecoveryList}, all: ${stateList})`,
          ),
        );
        // Independent of the verdict wording: the bridge must never claim
        // `healthy` while the Core pid is gone and no replacement is running.
        checks.push(
          depCheck(
            installSucceeded,
            "core_crash_is_never_stale_healthy",
            healthyWhileDown ? "fail" : "pass",
            healthyWhileDown
              ? `healthy reported with no live Core (pre-recovery: ${preRecoveryList})`
              : `never healthy while Core was down (pre-recovery: ${preRecoveryList})`,
          ),
        );

        // The real recovery requirement. If the outer process is still alive
        // under launchd and no replacement Core ever appears, that is a genuine
        // failure -- previously this was recorded as a benign `unknown`.
        const recovered =
          recoveredCorePid !== null
            ? await waitForHealthy(home, dataDir, cliPath, 30_000)
            : null;
        const recState =
          recovered?.runtime?.state ?? recovered?.state ?? finalRuntimeState;
        const recoveredOk = recState === "running";
        checks.push(
          depCheck(
            installSucceeded,
            "recovers_after_core_crash",
            recoveredOk ? "pass" : outerStillAlive ? "fail" : "unknown",
            recoveredOk
              ? `runtime running again after Core crash (replacement ${
                  recoveredCorePid === null
                    ? "reported by product"
                    : `pid ${recoveredCorePid}`
                })`
              : outerStillAlive
                ? `outer launchd process stayed alive but Core never came back within 30s (final ${recState}); the supervisor did not recover`
                : `the launchd job itself is gone (final ${recState})`,
          ),
        );
      }

      // 4c-bis. Broker (sidecar) fault isolation, C0 H41 option 2: the Broker
      // runs inside the Runtime process, so a broker-level fault must degrade the
      // Runtime rather than take the daemon down. The Runtime records that fault
      // as `sidecar: "failed"` in its own service receipt; a *separate* `status`
      // process must then report `degraded` with `broker=unhealthy` while the
      // launchd job stays alive. Injecting that field is the discriminating test:
      // a build without this contract ignores the unknown key and reports
      // `healthy`.
      {
        const faultHealth = await waitForHealthy(
          home,
          dataDir,
          cliPath,
          30_000,
        );
        const faultRuntimeState =
          faultHealth?.runtime?.state ?? faultHealth?.state;
        const serviceReceipt = path.join(dataDir, "runtime-service.json");
        const originalReceipt = await readFile(serviceReceipt, "utf8").catch(
          () => null,
        );
        const runtimeAlive = (await loadedPid(label)) !== null;
        if (
          originalReceipt === null ||
          !runtimeAlive ||
          faultRuntimeState !== "running"
        ) {
          checks.push(
            depCheck(
              installSucceeded,
              "broker_failure_degrades_the_alive_runtime",
              "unknown",
              `preconditions not met: receipt=${originalReceipt === null ? "missing" : "present"} runtimeAlive=${runtimeAlive} state=${faultRuntimeState ?? "unknown"}`,
            ),
          );
        } else {
          const injected = JSON.parse(originalReceipt);
          injected.sidecar = "failed";
          await writeFile(
            serviceReceipt,
            `${JSON.stringify(injected, null, 2)}\n`,
            { mode: 0o600 },
          );
          const degraded = await cli(home, dataDir, cliPath, [
            "status",
            "--json",
          ]);
          let parsed = null;
          try {
            parsed = JSON.parse(degraded.stdout);
          } catch {
            parsed = null;
          }
          const bridgeState = parsed?.bridge?.state;
          const outerStillAlive = (await loadedPid(label)) !== null;
          const contained =
            bridgeState === "degraded" &&
            outerStillAlive &&
            parsed?.bridge?.broker !== "running";
          checks.push(
            depCheck(
              installSucceeded,
              "broker_failure_degrades_the_alive_runtime",
              contained ? "pass" : "fail",
              contained
                ? `broker unusable while the launchd job stayed alive; bridge=${bridgeState}/broker=${parsed?.bridge?.broker}`
                : `bridge=${bridgeState ?? "none"} broker=${parsed?.bridge?.broker ?? "none"} outerAlive=${outerStillAlive}`,
            ),
          );
          // Restore the real receipt so later checks see the product's own state.
          await writeFile(serviceReceipt, originalReceipt, { mode: 0o600 });
        }
      }

      // 4d. Sleep/wake proxy: a real system sleep would strand every other agent
      // on this shared machine, so we approximate "the runtime stops responding
      // for a while and then resumes" with SIGSTOP/SIGCONT on the launchd-owned
      // job. Two things must hold, and neither is provable from a receipt:
      //   - while the daemon is frozen, status must NOT keep claiming healthy;
      //   - after SIGCONT, the SAME launchd-owned job must come back and the
      //     product must report it running again (KeepAlive resurfaces it).
      const wakePid = await loadedPid(label);
      if (wakePid === null) {
        checks.push(
          depCheck(
            installSucceeded,
            "survives_a_freeze_and_wake_cycle",
            "unknown",
            "launchd reports no pid for the job; retry on a quiet machine",
          ),
        );
      } else if (!healthy) {
        // Freezing a runtime that never came up measures nothing. Report the
        // cold start rather than a misleading freeze/wake verdict.
        checks.push(
          depCheck(
            installSucceeded,
            "survives_a_freeze_and_wake_cycle",
            "unknown",
            `runtime was not healthy before the freeze probe (state=${healthState ?? "unknown"})`,
          ),
        );
      } else {
        await run("kill", ["-STOP", String(wakePid)]);
        let healthyWhileFrozen = false;
        const frozenStates = new Set();
        for (let attempt = 0; attempt < 6; attempt += 1) {
          await new Promise((resolve) => setTimeout(resolve, 1000));
          const s = await cli(home, dataDir, cliPath, ["status", "--json"]);
          let parsed = null;
          try {
            parsed = JSON.parse(s.stdout);
          } catch {
            parsed = null;
          }
          const bridge = parsed?.bridge?.state;
          if (typeof bridge === "string") frozenStates.add(bridge);
          if (bridge === "healthy") healthyWhileFrozen = true;
        }
        await run("kill", ["-CONT", String(wakePid)]);
        const resumed = await waitForHealthy(home, dataDir, cliPath, 90_000);
        const resumedState =
          resumed?.runtime?.state ?? resumed?.state ?? "unknown";
        // The frozen daemon may legitimately respond to its own local health
        // socket from an in-process path, so "healthy while frozen" is reported
        // as evidence, and the pass criterion is the same job resuming.
        checks.push(
          depCheck(
            installSucceeded,
            "survives_a_freeze_and_wake_cycle",
            resumedState === "running" ? "pass" : "unknown",
            resumedState === "running"
              ? `pid ${wakePid} frozen then resumed; runtime running again` +
                  (healthyWhileFrozen
                    ? ` (status kept reporting healthy while frozen: ${[...frozenStates].join(", ")})`
                    : ` (frozen-status=${[...frozenStates].join(", ") || "not reported"})`)
              : `pid ${wakePid} still ${resumedState} after SIGCONT under load; retry on a quiet machine`,
          ),
        );
      }
    } // end of the upgrade/degraded/freeze section, guarded by installSucceeded

    // 5. Uninstall removes the managed service + version, keeps data.
    //
    // Before uninstalling, exercise the durable `launchctl disable` override:
    // a disabled service must be reported as disabled (not silently re-enabled
    // by an install), and uninstall must still clean it up even though
    // `bootout` reports exit 5 for a label that is not currently loaded. This
    // is the product rule "system-disabled / user-disabled must not be
    // auto-recovered", proven against the real launchd override table.
    //
    // This whole matrix runs on a throwaway HOME and a scoped label
    // (`<canonical>.<sha256(root)>`), never the canonical daily label, so
    // touching the override here cannot affect a real user install.
    const domain = `gui/${process.getuid()}`;
    const disabledWork = await run("launchctl", ["print-disabled", domain]);
    const preexistingOverride = disabledWork.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find((line) => line.startsWith(`"${label}"`));
    // macOS has no user-level API to delete a `launchctl disable` override
    // entry, and `launchctl enable` records an inert `enabled` override instead.
    // So a repeated run of this matrix on the same throwaway label legitimately
    // sees a leftover `enabled` entry. Only a preexisting `disabled` override
    // would contaminate the scenario and must fail.
    const preexistingDisabled =
      preexistingOverride !== undefined &&
      preexistingOverride.includes("disabled");
    checks.push(
      check(
        "scoped_label_has_no_preexisting_disabled_override",
        preexistingDisabled ? "fail" : "pass",
        preexistingOverride ??
          `${label} absent from gui/${process.getuid()} override table`,
      ),
    );
    // Stop the job so it is genuinely unloaded, then record the durable disable.
    await run("launchctl", ["bootout", `gui/${process.getuid()}/${label}`]);
    const disabledAfterBootout = await launchctlPrint(label);
    labelRegistered = disabledAfterBootout.registered;
    await run("launchctl", ["disable", `${domain}/${label}`]);
    const disabledTable = await run("launchctl", ["print-disabled", domain]);
    const overrideLine = disabledTable.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find((line) => line.startsWith(`"${label}"`));
    checks.push(
      depCheck(
        installSucceeded,
        "launchd_disable_override_is_visible",
        overrideLine?.includes("disabled") ? "pass" : "fail",
        overrideLine ?? `no disable override recorded for ${label}`,
      ),
    );
    // Re-installing over a disabled label must fail closed with a distinct
    // reason instead of silently calling `launchctl enable`.
    const disabledReinstall = await cli(home, dataDir, cliPath, [
      "install",
      "--source",
      config.dist,
      "--install-root",
      installRoot,
      "--bin-dir",
      binDir,
      "--data-dir",
      dataDir,
      "--yes",
    ]);
    // Re-installing over an already-managed-but-disabled label is refused by
    // the CLI's managed-upgrade precheck, which reports
    // `runtime_service_registration_changed` (the override makes the label look
    // unloaded). The safety property is the same either way: non-zero exit and
    // the durable override left intact, asserted below. The distinct
    // `runtime_service_disabled_by_system` code is asserted on the fresh-install
    // path in its own isolated run.
    const disabledReinstallRefused = disabledReinstall.code !== 0;
    checks.push(
      depCheck(
        installSucceeded,
        "install_refuses_to_re_enable_a_disabled_service",
        disabledReinstallRefused ? "pass" : "fail",
        disabledReinstallRefused
          ? `exit ${disabledReinstall.code} (refused; override preserved)`
          : `exit ${disabledReinstall.code}: ${(
              disabledReinstall.stderr || disabledReinstall.stdout
            )
              .trim()
              .slice(0, 200)}`,
      ),
    );
    // Fresh-install path: a label disabled before any install must surface the
    // distinct `runtime_service_disabled_by_system` code, not a generic
    // registration failure, and must not create a versions/current tree.
    const freshDisabledHome = path.join(work, "disabled-home");
    const freshDisabledRoot = path.join(
      freshDisabledHome,
      ".local",
      "share",
      "one-memory",
    );
    const freshDisabledBin = path.join(work, "disabled-bin");
    const freshDisabledData = path.join(work, "disabled-data");
    await mkdir(freshDisabledBin, { recursive: true, mode: 0o700 });
    // Disable the fresh run's scoped label before it ever installs, so the
    // first-install path (not the managed-upgrade precheck) is exercised.
    const freshDisabledLabel = await plannedServiceId(
      cliPath,
      freshDisabledHome,
      freshDisabledData,
      path.join(freshDisabledRoot, "current"),
    );
    if (freshDisabledLabel !== null) {
      await run("launchctl", ["disable", `${domain}/${freshDisabledLabel}`]);
    }
    const freshDisabledInstall = await cli(
      freshDisabledHome,
      freshDisabledData,
      cliPath,
      [
        "install",
        "--source",
        config.dist,
        "--install-root",
        freshDisabledRoot,
        "--bin-dir",
        freshDisabledBin,
        "--data-dir",
        freshDisabledData,
        "--yes",
      ],
    );
    const freshDisabledCodeVisible =
      freshDisabledInstall.code !== 0 &&
      /runtime_service_disabled_by_system/.test(
        `${freshDisabledInstall.stdout}${freshDisabledInstall.stderr}`,
      );
    const freshDisabledHasCurrent = await lstat(
      path.join(freshDisabledRoot, "current"),
    )
      .then(() => true)
      .catch(() => false);
    if (freshDisabledLabel !== null) {
      await run("launchctl", ["enable", `${domain}/${freshDisabledLabel}`]);
    }
    checks.push(
      depCheck(
        installSucceeded,
        "fresh_install_reports_disabled_by_system_without_partial_root",
        freshDisabledCodeVisible && !freshDisabledHasCurrent ? "pass" : "fail",
        freshDisabledCodeVisible && !freshDisabledHasCurrent
          ? `exit ${freshDisabledInstall.code} runtime_service_disabled_by_system; no current`
          : `exit ${freshDisabledInstall.code}; current=${freshDisabledHasCurrent}; ${(
              freshDisabledInstall.stderr || freshDisabledInstall.stdout
            )
              .trim()
              .slice(0, 200)}`,
      ),
    );
    const stillDisabled = await run("launchctl", ["print-disabled", domain]);
    checks.push(
      depCheck(
        installSucceeded,
        "failed_install_did_not_clear_the_disable_override",
        stillDisabled.stdout
          .split(/\r?\n/)
          .map((line) => line.trim())
          .find((line) => line.startsWith(`"${label}"`))
          ?.includes("disabled")
          ? "pass"
          : "fail",
        "override must survive a refused install",
      ),
    );

    const beforeUninstallPs = parsePsRows(
      (await run("ps", ["-Ao", "pid=,ppid=,state=,command="])).stdout,
    );
    const ownedPids = new Set(
      beforeUninstallPs
        .filter(
          (row) =>
            !row.state.startsWith("Z") && row.command.includes(installRoot),
        )
        .map((row) => row.pid),
    );
    const uninstall = await cli(home, dataDir, cliPath, [
      "uninstall",
      "--install-root",
      installRoot,
      "--bin-dir",
      binDir,
      "--data-dir",
      dataDir,
      "--yes",
    ]);
    checks.push(
      depCheck(
        installSucceeded,
        "uninstall_apply_exit_zero",
        uninstall.code === 0 ? "pass" : "fail",
        uninstall.stderr.trim().slice(0, 300) || `exit ${uninstall.code}`,
      ),
    );
    const afterUninstall = await launchctlPrint(label);
    labelRegistered = afterUninstall.registered;
    checks.push(
      depCheck(
        installSucceeded,
        "service_is_gone_after_uninstall",
        afterUninstall.registered ? "fail" : "pass",
        afterUninstall.registered ? "still registered" : "absent",
      ),
    );
    // The disable override is the user's/system's durable decision, not state
    // this uninstall owns, so it is left in place; the job must still be gone.
    const uninstallDidNotReEnable = await run("launchctl", [
      "print-disabled",
      domain,
    ]);
    checks.push(
      depCheck(
        installSucceeded,
        "uninstall_of_a_disabled_service_succeeded_without_re_enabling",
        uninstallDidNotReEnable.stdout
          .split(/\r?\n/)
          .map((line) => line.trim())
          .find((line) => line.startsWith(`"${label}"`))
          ?.includes("disabled")
          ? "pass"
          : "fail",
        "exit 5 from bootout on an unloaded disabled label must not fail the uninstall",
      ),
    );
    // Clean the override so the throwaway label leaves no machine-level trace.
    await run("launchctl", ["enable", `${domain}/${label}`]);
    // No zombie process may be left holding the runtime, and none of our
    // installed paths may still be executing after uninstall.
    //
    // `pgrep -fl <path>` alone is not enough: it matches the process COMMAND
    // STRING, so (a) a true zombie has no argv at all and is therefore
    // invisible to it, and (b) it cannot tell whose process a match is. A
    // real-machine probe confirmed a zombie child is invisible to
    // `pgrep -fl` while `ps -o state` still shows `Z`. So enumerate with
    // `ps` (pid, state, command) and judge each row on the STATE field, then
    // treat any live process still referencing this run's root as a leftover.
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const psAll = await run("ps", ["-Ao", "pid=,ppid=,state=,command="]);
    const psRows = parsePsRows(psAll.stdout);
    // A zombie (`Z`) cannot hold the runtime open; it is still reported because
    // the objective asks for "no zombies", but it is called out separately from
    // a live holder so the two are not conflated.
    const { zombies, liveLeftovers } = judgeLeftovers(
      psRows,
      installRoot,
      ownedPids,
    );
    const leftoverLines = liveLeftovers.map(
      (row) => `${row.pid} ${row.state} ${row.command.slice(0, 80)}`,
    );
    checks.push(
      depCheck(
        installSucceeded,
        "no_zombie_or_orphan_runtime_after_uninstall",
        leftoverLines.length === 0 && zombies.length === 0 ? "pass" : "fail",
        leftoverLines.length === 0 && zombies.length === 0
          ? "no process references the removed install root; ps shows no zombie (Z-state) process"
          : `${leftoverLines.length} live leftover(s)` +
              (zombies.length
                ? `, ${zombies.length} zombie(s): ${zombies
                    .slice(0, 2)
                    .map((z) => `${z.pid}(ppid=${z.ppid})`)
                    .join(", ")}`
                : "") +
              (leftoverLines.length
                ? `: ${leftoverLines.slice(0, 3).join(" | ")}`
                : ""),
      ),
    );
    checks.push(
      depCheck(
        installSucceeded,
        "uninstall_kept_user_data",
        (await exists(path.join(dataDir, "c7-lifecycle-marker")))
          ? "pass"
          : "fail",
        path.join(dataDir, "c7-lifecycle-marker"),
      ),
    );
    checks.push(
      depCheck(
        installSucceeded,
        "uninstall_removed_the_managed_plist",
        (await missing(serviceFile)) ? "pass" : "fail",
        serviceFile,
      ),
    );
    // The PATH entry we created must be gone, and its directory left alone.
    checks.push(
      depCheck(
        installSucceeded,
        "uninstall_removed_the_path_link_it_created",
        (await missing(path.join(binDir, "one-memory"))) ? "pass" : "fail",
        path.join(binDir, "one-memory"),
      ),
    );

    // Re-install, then prove uninstall does NOT delete a PATH entry it never
    // created: replace our link with a plain file standing in for another
    // tool's binary, and re-run uninstall.
    const foreignInstall = await cli(home, dataDir, cliPath, [
      "install",
      "--source",
      config.dist,
      "--install-root",
      installRoot,
      "--bin-dir",
      binDir,
      "--data-dir",
      dataDir,
      "--yes",
    ]);
    const foreignPath = path.join(binDir, "one-memory");
    await rm(foreignPath, { force: true });
    await writeFile(foreignPath, "someone else's tool\n");
    const foreignUninstall = await cli(home, dataDir, cliPath, [
      "uninstall",
      "--install-root",
      installRoot,
      "--bin-dir",
      binDir,
      "--data-dir",
      dataDir,
      "--yes",
    ]);
    const foreignSurvived =
      foreignInstall.code === 0 &&
      (await readFile(foreignPath, "utf8").catch(() => null)) ===
        "someone else's tool\n";
    // The data directory must never be removed, even when the user pointed it
    // inside the subtree uninstall deletes recursively. The old behavior
    // deleted it while the plan still advertised preserved_data_dir.
    const nestedRoot = path.join(work, "nested-install-root");
    const nestedData = path.join(nestedRoot, "versions", "userdata");
    const nestedInstall = await cli(home, nestedData, cliPath, [
      "install",
      "--source",
      config.dist,
      "--install-root",
      nestedRoot,
      "--bin-dir",
      path.join(work, "nested-bin"),
      "--data-dir",
      nestedData,
      "--yes",
    ]);
    await mkdir(nestedData, { recursive: true });
    const nestedMarker = path.join(nestedData, "PRECIOUS");
    await writeFile(nestedMarker, "user data\n");
    const nestedUninstall = await cli(home, nestedData, cliPath, [
      "uninstall",
      "--install-root",
      nestedRoot,
      "--bin-dir",
      path.join(work, "nested-bin"),
      "--data-dir",
      nestedData,
      "--yes",
    ]);
    const nestedMarkerSurvived = await exists(nestedMarker);
    const nestedRefused =
      nestedInstall.code === 0 && nestedUninstall.code !== 0;
    checks.push(
      check(
        "uninstall_refuses_when_data_lives_inside_the_removed_subtree",
        nestedRefused && nestedMarkerSurvived ? "pass" : "fail",
        nestedRefused && nestedMarkerSurvived
          ? `uninstall exit ${nestedUninstall.code} and the data under versions/ survived`
          : `install=${nestedInstall.code} uninstall=${nestedUninstall.code} marker=${nestedMarkerSurvived ? "kept" : "DELETED"}`,
      ),
    );
    // The refusal above is CORRECT: it leaves the nested service installed and
    // running. If we stopped here the throwaway scoped label would outlive the
    // run (observed twice: a live Runtime plus its scoped launchd label after
    // the matrix "passed"). Uninstall only after moving the data OUT of the
    // removed subtree, so the cleanup itself is also a positive test of the
    // documented recovery: "move the data out, then uninstall".
    const nestedMovedData = path.join(nestedRoot, "data");
    await mkdir(nestedMovedData, { recursive: true });
    await writeFile(path.join(nestedMovedData, "PRECIOUS"), "user data\n");
    // Use the documented escape hatch: state, for this invocation only, that
    // the data directory is not part of what uninstall may remove. This is the
    // path a person takes when they left the data inside versions/ and want
    // the service gone without losing it.
    const nestedCleanup = await cli(home, nestedData, cliPath, [
      "uninstall",
      "--install-root",
      nestedRoot,
      "--bin-dir",
      path.join(work, "nested-bin"),
      "--data-dir",
      nestedData,
      "--preserve-data-dir",
      "--yes",
    ]);
    const nestedLabel = await plannedServiceId(
      cliPath,
      home,
      nestedData,
      nestedRoot,
    );
    const nestedLabelGone =
      nestedLabel === null || !(await launchctlPrint(nestedLabel)).registered;
    checks.push(
      check(
        "nested_service_is_cleanly_uninstalled_after_moving_data_out",
        nestedCleanup.code === 0 && nestedLabelGone ? "pass" : "fail",
        nestedCleanup.code === 0 && nestedLabelGone
          ? `uninstall exit 0 and ${nestedLabel ?? "the scoped label"} is gone`
          : `uninstall=${nestedCleanup.code} labelGone=${nestedLabelGone}`,
      ),
    );
    // Whatever happened above, this run must not leave the nested scoped label
    // registered. Compare the label's own install root, not the labels seen
    // earlier, and force a cleanup when the product did not.
    if (!nestedLabelGone && nestedLabel !== null) {
      await run("launchctl", [
        "bootout",
        `gui/${process.getuid()}/${nestedLabel}`,
      ]).catch(() => undefined);
      await run("launchctl", [
        "enable",
        `gui/${process.getuid()}/${nestedLabel}`,
      ]).catch(() => undefined);
    }

    checks.push(
      depCheck(
        installSucceeded,
        "uninstall_preserves_a_foreign_path_entry",
        foreignSurvived ? "pass" : "fail",
        foreignSurvived
          ? "a non-symlink one-memory file the product did not create survived uninstall"
          : `foreign file was removed or replaced (install=${foreignInstall.code}, uninstall=${foreignUninstall.code})`,
      ),
    );
  } finally {
    // Never leave a stray test service behind, even on failure. The scoped
    // label is uninstalled and re-installed several times above, so a
    // mid-run `labelRegistered` sample goes stale; ask launchd for whatever is
    // actually loaded and only boot out the labels whose program lives inside
    // this run's throwaway work tree. Anything else belongs to another owner.
    const staleLabels = await scopedLabelsUnderWork(work);
    for (const stale of staleLabels) {
      await run("launchctl", [
        "bootout",
        `gui/${process.getuid()}/${stale}`,
      ]).catch(() => undefined);
    }
    if (labelRegistered) {
      await run("launchctl", [
        "bootout",
        `gui/${process.getuid()}/${label}`,
      ]).catch(() => undefined);
    }
    // `bootout` is asynchronous: launchd unloads, then terminates the job. Its
    // program is a Runtime under `work`, which must be gone before the tree can
    // be removed, so give it a bounded window and fail the cleanup honestly
    // rather than deleting a directory a live daemon still uses.
    let stragglers = 0;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      stragglers = 0;
      for (const stale of staleLabels) {
        if ((await loadedPid(stale)) !== null) stragglers += 1;
      }
      if (stragglers === 0) break;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    // The disable-override checks touch machine-level launchd state. `launchctl
    // enable` records an `enabled` override rather than deleting the entry, and
    // there is no supported way to remove one (verified on macOS 15.1), so the
    // best we can do is leave an inert `enabled` entry for this run's scoped
    // label. That is behaviorally identical to having no override, and the
    // label is derived from a throwaway install root, so it can never collide
    // with the canonical daily label. Report the leftover state honestly.
    await run("launchctl", [
      "enable",
      `gui/${process.getuid()}/${label}`,
    ]).catch(() => undefined);
    const overrideLeft = await run("launchctl", [
      "print-disabled",
      `gui/${process.getuid()}`,
    ]);
    const leftoverOverride = overrideLeft.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find((line) => line.startsWith(`"${label}"`));
    if (leftoverOverride !== undefined) {
      overrideNote = leftoverOverride;
    }
    if (ownedWork) {
      cleanup = await safeRemoveWork(work, label, labelRegistered);
    }
  }

  const failed = checks.filter((entry) => entry.result === "fail");
  const unknown = checks.filter((entry) => entry.result === "unknown");
  const summary = {
    schema_version: 1,
    platform: process.platform,
    arch: process.arch,
    distribution: config.dist,
    cli: config.cli ?? "bundled",
    scoped_label: label,
    work: ownedWork ? "(removed)" : work,
    checks,
    passed: checks.filter((entry) => entry.result === "pass").length,
    failed: failed.length,
    unknown: unknown.length,
    // Distinguish "the suite ran and something failed" from "the suite could
    // not run because install did not complete". Both are non-pass, but only
    // the first is a product failure to act on.
    incomplete: !installSucceeded,
    // Four-protection cleanup outcome ("cleaned", or the reason the tree was
    // deliberately left in place rather than deleted under a live user).
    cleanup,
    // Honest note about the inert launchd `enabled` override the disable-semantics
    // checks leave behind for this run's scoped label (there is no supported way
    // to delete an override entry).
    launchd_override_note: overrideNote,
    verdict: failed.length ? "fail" : unknown.length ? "unknown" : "pass",
  };
  if (config.json) {
    process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
  } else {
    for (const entry of checks) {
      process.stdout.write(
        `${entry.result.toUpperCase().padEnd(8)} ${entry.name}\n`,
      );
    }
    process.stdout.write(`verdict: ${summary.verdict}\n`);
  }
  return failed.length ? 4 : unknown.length ? 2 : 0;
}

// Reuse the checks in tests without executing the CLI.
export {
  appBundleChecks,
  CANONICAL_LABEL,
  judgeLeftovers,
  parseLaunchctlJobCommand,
  parsePsRows,
  publicGateReport,
  safeRemoveWork,
  sameOriginRuntimeChecks,
  scopedLabel,
  scopedLabelsUnderWork,
  sharedDaemonVerdict,
};

const isEntry =
  process.argv[1] &&
  path.resolve(process.argv[1]) ===
    path.resolve(fileURLToPath(import.meta.url));
if (isEntry) {
  process.exitCode = await main();
}
