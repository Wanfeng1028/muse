import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, stat, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  appBundleChecks,
  CANONICAL_LABEL,
  judgeLeftovers,
  parseLaunchctlJobCommand,
  parsePsRows,
  safeRemoveWork,
  sameOriginRuntimeChecks,
  scopedLabel,
  sharedDaemonVerdict,
} from "./service-lifecycle.mjs";

test("flags a bundled RunAtLoad login agent and reports signing honestly", async () => {
  const app = await mkdtemp(path.join(os.tmpdir(), "om-app-bundle-"));
  const agentsDir = path.join(app, "Contents", "Library", "LaunchAgents");
  await mkdir(agentsDir, { recursive: true });
  await writeFile(
    path.join(agentsDir, "one-memory-background.plist"),
    [
      "<plist><dict>",
      "<key>Label</key><string>com.example.background</string>",
      "<key>RunAtLoad</key><true/>",
      "</dict></plist>",
    ].join("\n"),
  );
  const checks = await appBundleChecks(app);
  const registration = checks.find((c) =>
    c.name.includes("run_at_load_login_agent"),
  );
  assert.equal(registration.result, "fail");
  assert.match(registration.evidence, /one-memory-background\.plist/);
  await rm(app, { recursive: true, force: true });
});

test("passes the login-registration check for a bundle with no LaunchAgents", async () => {
  const app = await mkdtemp(path.join(os.tmpdir(), "om-app-clean-"));
  await mkdir(path.join(app, "Contents"), { recursive: true });
  const checks = await appBundleChecks(app);
  const registration = checks.find((c) =>
    c.name.includes("run_at_load_login_agent"),
  );
  assert.equal(registration.result, "pass");
  await rm(app, { recursive: true, force: true });
});

test("reads the exact program and arguments launchd reports for a job", () => {
  const job = parseLaunchctlJobCommand(
    [
      "gui/501/com.tencent.onememory.runtime = {",
      "\tactive count = 1",
      "\tpath = /tmp/home/Library/LaunchAgents/com.tencent.onememory.runtime.plist",
      "\tprogram = /tmp/home/.local/share/one-memory/current/bin/node",
      "\targuments = {",
      "\t\t/tmp/home/.local/share/one-memory/current/bin/node",
      "\t\t/tmp/home/.local/share/one-memory/current/runtime/runtime.cjs",
      "\t\tserve",
      "\t}",
      "}",
    ].join("\n"),
  );
  assert.deepEqual(job, {
    program: "/tmp/home/.local/share/one-memory/current/bin/node",
    args: [
      "/tmp/home/.local/share/one-memory/current/bin/node",
      "/tmp/home/.local/share/one-memory/current/runtime/runtime.cjs",
      "serve",
    ],
  });
});

test("reports no command when launchd output has no program line", () => {
  assert.equal(parseLaunchctlJobCommand("\tactive count = 0\n"), null);
  assert.equal(parseLaunchctlJobCommand(""), null);
});

/** Build a throwaway App bundle + distribution pair for the same-origin test.
 * `mismatch` optionally makes one component's App copy differ by one byte. */
/** Mirrors the REAL on-disk layout, which is not symmetric:
 *    core/runtime/host-bridge -> directories on both sides;
 *    the CLI                  -> `dist/bin/one-memory.cjs` (a FILE) in the
 *                                distribution, `Resources/cli/` (a DIRECTORY)
 *                                in the App bundle.
 * The previous fixture gave the distribution a `cli/` directory that does not
 * exist in a real distribution, which hid the false `dist=missing` failure.
 */
async function sameOriginFixture({ mismatch = null } = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-same-origin-"));
  const dist = path.join(root, "runtime-dist");
  const app = path.join(root, "MemHub.app");
  const resources = path.join(app, "Contents", "Resources");
  for (const component of ["core", "runtime", "host-bridge", "web"]) {
    for (const base of [
      path.join(dist, component),
      path.join(resources, component),
    ]) {
      await mkdir(base, { recursive: true });
      await writeFile(
        path.join(base, `${component}-file`),
        component === mismatch && base.startsWith(resources)
          ? "drifted"
          : "identical",
      );
    }
  }
  // Distribution: a single CLI file under bin/.
  await mkdir(path.join(dist, "bin"), { recursive: true });
  await writeFile(
    path.join(dist, "bin", "one-memory.cjs"),
    mismatch === "cli" ? "drifted" : "identical",
  );
  // App bundle: the CLI as a directory with the same file name inside.
  await mkdir(path.join(resources, "cli"), { recursive: true });
  await writeFile(
    path.join(resources, "cli", "one-memory.cjs"),
    mismatch === "cli" ? "drifted" : "identical",
  );
  return { root, dist, app };
}

const HOME = "/Users/example";
const ROOT =
  "/Users/example/Library/Application Support/One Memory Hourly/managed-runtime";
const DAILY = `${HOME}/Library/Application Support/One Memory`;

test("the daily install root keeps the canonical label", () => {
  assert.equal(scopedLabel("darwin", DAILY, DAILY), CANONICAL_LABEL);
  assert.equal(
    scopedLabel("darwin", `${DAILY}/current`, DAILY),
    CANONICAL_LABEL,
  );
});

test("an isolated root gets its own scoped label, never the canonical one", () => {
  const label = scopedLabel("darwin", ROOT, DAILY);
  assert.match(label, /^com\.tencent\.onememory\.runtime\.[a-f0-9]{16}$/);
  assert.notEqual(label, CANONICAL_LABEL);
});

test("root and its current link resolve to the same label", () => {
  // install passes `<root>/current`; uninstall/upgrade pass `<root>`. If these
  // disagreed, an install would be invisible to its own uninstall.
  assert.equal(
    scopedLabel("darwin", ROOT, DAILY),
    scopedLabel("darwin", `${ROOT}/current`, DAILY),
  );
});

test("the label is stable for one root and different across roots", () => {
  assert.equal(
    scopedLabel("darwin", ROOT, DAILY),
    scopedLabel("darwin", ROOT, DAILY),
  );
  assert.notEqual(
    scopedLabel("darwin", ROOT, DAILY),
    scopedLabel("darwin", `${ROOT}-other`, DAILY),
  );
});

test("a root with spaces and non-ASCII characters still yields a valid label", () => {
  // Real users install under paths like `/Users/张三/Library/Application Support/…`.
  // The label must stay an ASCII bundle-id-shaped token, not echo the path.
  const root = "/Users/张三/Application Support/One Memory Hourly/运行目录";
  const label = scopedLabel("darwin", `${root}/current`, DAILY);
  assert.match(label, /^com\.tencent\.onememory\.runtime\.[a-f0-9]{16}$/);
  assert.equal(label, scopedLabel("darwin", root, DAILY));
  assert.notEqual(label, scopedLabel("darwin", `${root} 2`, DAILY));
});

test("same-origin check passes when App and distribution match byte for byte", async () => {
  const f = await sameOriginFixture();
  try {
    const checks = await sameOriginRuntimeChecks(f.dist, f.app);
    assert.equal(checks.length, 5);
    assert.deepEqual(
      checks.map((c) => c.result),
      ["pass", "pass", "pass", "pass", "pass"],
    );
  } finally {
    await rm(f.root, { recursive: true, force: true });
  }
});

test("same-origin check fails when the App embeds a drifted component", async () => {
  const f = await sameOriginFixture({ mismatch: "runtime" });
  try {
    const checks = await sameOriginRuntimeChecks(f.dist, f.app);
    const runtime = checks.find((c) => c.name.includes("runtime"));
    assert.equal(runtime.result, "fail");
    // The other components must still pass: the check is per-component, not global.
    assert.equal(checks.filter((c) => c.result === "pass").length, 4);
  } finally {
    await rm(f.root, { recursive: true, force: true });
  }
});

test("same-origin check fails, not skips, when a side is missing", async () => {
  const f = await sameOriginFixture();
  try {
    await rm(
      path.join(f.app, "Contents", "Resources", "cli", "one-memory.cjs"),
      { force: true },
    );
    const checks = await sameOriginRuntimeChecks(f.dist, f.app);
    const cli = checks.find((c) => c.name.includes("cli"));
    assert.equal(cli.result, "fail");
    assert.match(cli.evidence, /app=missing/);
  } finally {
    await rm(f.root, { recursive: true, force: true });
  }
});

test("safe cleanup removes an idle throwaway tree", async () => {
  const work = await mkdtemp(path.join(os.tmpdir(), "om-cleanup-ok-"));
  await mkdir(path.join(work, "home"), { recursive: true });
  const result = await safeRemoveWork(
    work,
    "com.tencent.onememory.runtime.0000000000000000",
    false,
  );
  assert.equal(result.removed, true);
  assert.equal(result.reason, "cleaned");
  await assert.rejects(stat(work));
});

test("safe cleanup accepts a /tmp work path whose realpath is /private/tmp", async () => {
  // The harness may be handed `--work /tmp/...` while os.tmpdir() points at
  // /var/folders. macOS resolves both to /private/*, so a naive prefix check
  // against os.tmpdir() would refuse to clean a directory it owns forever.
  const work = await mkdtemp("/tmp/om-cleanup-realpath-");
  await writeFile(path.join(work, "keep"), "x");
  const result = await safeRemoveWork(
    work,
    "com.tencent.onememory.runtime.0000000000000000",
    false,
  );
  assert.equal(result.removed, true, result.reason);
  assert.equal(result.reason, "cleaned");
  await assert.rejects(stat(work));
});

test("safe cleanup refuses a directory a live process still references", async () => {
  // Hold the path in a real child process command line so `pgrep -fl` finds a
  // live holder, making the refusal deterministic rather than incidental.
  const work = await mkdtemp(path.join(os.tmpdir(), "om-cleanup-live-"));
  await writeFile(path.join(work, "keep"), "x");
  const { spawn } = await import("node:child_process");
  // Keep the path in a live process's argv that does NOT re-exec itself:
  // `node -e 'setTimeout(()=>{},30000)' <path>` leaves the path in argv, so
  // `pgrep -fl` matches it for the lifetime of the holder.
  const holder = spawn(
    process.execPath,
    ["-e", "setTimeout(()=>{}, 30000)", work],
    { stdio: "ignore" },
  );
  try {
    // Wait until the holder is visible with the path in argv.
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const probe = spawn("/usr/bin/pgrep", ["-fl", work], {
        stdio: ["ignore", "pipe", "ignore"],
      });
      let out = "";
      probe.stdout.on("data", (c) => (out += c));
      await new Promise((r) => probe.once("close", r));
      if (out.trim() !== "") break;
      await new Promise((r) => setTimeout(r, 100));
    }
    const result = await safeRemoveWork(
      work,
      "com.tencent.onememory.runtime.0000000000000000",
      false,
    );
    assert.equal(result.removed, false);
    assert.match(result.reason, /live-process/);
    await stat(path.join(work, "keep"));
  } finally {
    if (holder.exitCode === null && holder.signalCode === null) {
      const closed = new Promise((r) => holder.once("close", r));
      holder.kill("SIGKILL");
      await closed;
    }
    await rm(work, { recursive: true, force: true });
  }
});

test("safe cleanup refuses a registered service's tree", async () => {
  const work = await mkdtemp(path.join(os.tmpdir(), "om-cleanup-svc-"));
  await writeFile(path.join(work, "keep"), "x");
  const result = await safeRemoveWork(
    work,
    "com.tencent.onememory.runtime.0000000000000000",
    true,
  );
  assert.equal(result.removed, false);
  assert.equal(result.reason, "service-still-registered");
  await stat(path.join(work, "keep"));
  await rm(work, { recursive: true, force: true });
});

test("safe cleanup refuses a symlinked work path", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-cleanup-sym-"));
  const real = path.join(root, "real");
  const link = path.join(root, "link");
  await mkdir(real, { recursive: true });
  await writeFile(path.join(real, "keep"), "x");
  await symlink(real, link, "dir");
  try {
    const result = await safeRemoveWork(
      link,
      "com.tencent.onememory.runtime.0000000000000000",
      false,
    );
    assert.equal(result.removed, false);
    assert.equal(result.reason, "not-a-real-directory");
    // The target must survive: a symlinked path is never followed and removed.
    await stat(path.join(real, "keep"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("parses ps rows into pid/ppid/state/command and drops unparseable lines", () => {
  const rows = parsePsRows(
    [
      "    1     0 Ss   /sbin/launchd",
      " 4242  4241 Z    <defunct>",
      "  900   899 S    /tmp/root/current/bin/node /tmp/root/current/runtime.cjs serve",
      "", // blank line ignored
      "not-a-ps-line", // dropped
    ].join("\n"),
  );
  assert.equal(rows.length, 3);
  assert.deepEqual(rows[2], {
    pid: 900,
    ppid: 899,
    state: "S",
    command: "/tmp/root/current/bin/node /tmp/root/current/runtime.cjs serve",
  });
  assert.equal(rows[1].state, "Z");
});

test("a Z-state row is reported as a zombie even with no command (pgrep cannot see it)", () => {
  // A real zombie has no argv; `pgrep -fl <path>` misses it entirely. This is
  // the C8 mutation target: if `zombies` is emptied, this test must go red.
  const rows = parsePsRows(" 4242  4241 Z    <defunct>");
  const { zombies, liveLeftovers } = judgeLeftovers(rows, "/tmp/some-root");
  assert.equal(zombies.length, 1, "a Z-state process must count as a zombie");
  assert.equal(zombies[0].pid, 4242);
  assert.equal(liveLeftovers.length, 0, "a zombie is not a live leftover");
});

test("a live process still referencing the removed root is a leftover", () => {
  const rows = parsePsRows(
    "  900   899 S /tmp/one-memory-current/bin/node /tmp/one-memory-root/x",
  );
  const { zombies, liveLeftovers } = judgeLeftovers(
    rows,
    "/tmp/one-memory-root",
  );
  assert.equal(zombies.length, 0);
  assert.equal(liveLeftovers.length, 1);
});

test("clean ps output yields neither zombies nor leftovers", () => {
  const rows = parsePsRows("    1     0 Ss /sbin/launchd");
  const { zombies, liveLeftovers } = judgeLeftovers(rows, "/tmp/whatever");
  assert.equal(zombies.length, 0);
  assert.equal(liveLeftovers.length, 0);
});

test("every Z-state row across the table is collected, not just the first", () => {
  // Guards against a filter that only reports one zombie or drops later rows.
  const rows = parsePsRows(
    [" 111 1 Z <defunct>", " 222 1 Z <defunct>", " 333 1 S /bin/sh"].join("\n"),
  );
  const { zombies } = judgeLeftovers(rows, "/tmp/root");
  assert.equal(zombies.length, 2);
});

test("uninstall ignores unrelated pre-existing zombies", () => {
  const rows = parsePsRows(
    [
      " 111 1 Z <defunct>",
      " 222 1 Z <defunct>",
      " 333 1 S /tmp/root/current/bin/node /tmp/root/runtime.cjs serve",
    ].join("\n"),
  );
  const { zombies, liveLeftovers } = judgeLeftovers(
    rows,
    "/tmp/root",
    new Set([222, 333]),
  );
  assert.deepEqual(
    zombies.map((row) => row.pid),
    [222],
  );
  assert.deepEqual(
    liveLeftovers.map((row) => row.pid),
    [333],
  );
});

test("shared-daemon verdict: same job + CLI sees it -> pass", () => {
  assert.equal(
    sharedDaemonVerdict({ sameJob: true, cliSeesRunning: true, healthy: true }),
    "pass",
  );
});

test("shared-daemon verdict: same job, CLI cannot see a healthy runtime -> fail", () => {
  // The C8-class mutation target: dropping the CLI observation must not be able
  // to keep this green.
  assert.equal(
    sharedDaemonVerdict({
      sameJob: true,
      cliSeesRunning: false,
      healthy: true,
    }),
    "fail",
  );
});

test("shared-daemon verdict: job moved -> unknown, not a fake pass", () => {
  assert.equal(
    sharedDaemonVerdict({
      sameJob: false,
      cliSeesRunning: false,
      healthy: true,
    }),
    "unknown",
  );
});

test("shared-daemon verdict: no health baseline -> unknown, not fail", () => {
  assert.equal(
    sharedDaemonVerdict({
      sameJob: true,
      cliSeesRunning: false,
      healthy: false,
    }),
    "unknown",
  );
});
