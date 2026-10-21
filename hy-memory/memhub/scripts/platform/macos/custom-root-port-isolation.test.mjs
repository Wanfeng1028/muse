import assert from "node:assert/strict";
import test from "node:test";

import {
  defaultManagedInstallRoot,
  planUserService,
  runtimeInstallLayout,
} from "../../../packages/runtime-control/src/service-plan.ts";

/**
 * C7 macOS: two non-default install roots must not share the fixed Core port.
 *
 * Regression this pins (C0 H86 BLOCK
 * `[BLOCK C0 -> C7] a refused uninstall leaves the Runtime holding 8765`):
 *
 *   1. install root A -> its LaunchAgent Runtime binds 8765;
 *   2. a refused uninstall for A (foreign PATH entry) never reaches service
 *      teardown, so A's Runtime keeps holding 8765;
 *   3. install root B -> its Runtime also tries 8765, gets EADDRINUSE, and the
 *      CLI reports `install_runtime_not_ready`.
 *
 * The harness already isolates the *label* per root (scoped hash), so two roots
 * are distinct services. What they are NOT isolated on is the port: the plist
 * carries no `ONE_MEMORY_CORE_PORT`, so `runtimeEnvironment()` leaves both at the
 * fixed default 8765.
 *
 * This file states the contract independently of the implementation: a
 * non-default install root must carry a distinct, explicit Core port in its
 * LaunchAgent declaration. It is expected to FAIL today and turn green when the
 * port-override atomic group (runtime-cli + service-plan allowlist +
 * service-install migration + desktop main) lands.
 *
 * Daily installs are deliberately NOT covered here: they must keep the fixed
 * default port, so the assertion is scoped to roots outside the default root.
 */

const HOME = "/Users/example";
const DEFAULT_ROOT = defaultManagedInstallRoot("darwin", HOME);

function planFor(installRoot, dataDir) {
  const layout = runtimeInstallLayout({
    platform: "darwin",
    home: HOME,
    installRoot,
    dataDir,
  });
  return planUserService(layout, { uid: 501 });
}

function declaredCorePort(plan) {
  const match = plan.service_file?.content.match(
    /<key>ONE_MEMORY_CORE_PORT<\/key><string>(\d+)<\/string>/,
  );
  return match ? Number(match[1]) : null;
}

test("two non-default install roots get distinct scoped labels", () => {
  const a = planFor("/Users/example/custom-A", "/Users/example/da");
  const b = planFor("/Users/example/custom-B", "/Users/example/db");
  assert.equal(a.status, "ready");
  assert.equal(b.status, "ready");
  assert.notEqual(a.service_id, b.service_id, "labels must be scoped per root");
});

test("two non-default install roots must not both fall back to the fixed port", () => {
  const a = planFor("/Users/example/custom-A", "/Users/example/da");
  const b = planFor("/Users/example/custom-B", "/Users/example/db");

  const portA = declaredCorePort(a);
  const portB = declaredCorePort(b);

  // RED today: both are null, which means both Runtimes bind the fixed 8765 and
  // the second one dies with EADDRINUSE.
  assert.notEqual(
    portA,
    null,
    "a non-default install root must declare an explicit Core port in its plist",
  );
  assert.notEqual(
    portB,
    null,
    "a non-default install root must declare an explicit Core port in its plist",
  );
  assert.notEqual(
    portA,
    portB,
    "two custom roots must not share one Core port",
  );
});

test("the daily (default) install root keeps the fixed port and no override key", () => {
  // Guard the other direction: the port override must never widen the everyday
  // path. The daily root stays on the default 8765 with no override variable.
  const daily = planFor(DEFAULT_ROOT, "/Users/example/.one-memory");
  assert.equal(daily.status, "ready");
  assert.equal(
    declaredCorePort(daily),
    null,
    "the daily install root must not carry an override port",
  );
});
