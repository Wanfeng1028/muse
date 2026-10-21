import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";

import {
  type CommandResult,
  inspectLaunchdService,
  restartManagedService,
  type ServiceCommandRunner,
  startManagedService,
  stopManagedService,
} from "./service-session.js";

const SERVICE_ID = "com.tencent.onememory.runtime";
const UID = 501;

function running(pid: number, plist = "/tmp/h/Library/LaunchAgents/x.plist") {
  return {
    code: 0,
    stdout: `gui/501/${SERVICE_ID} = {\n\tpath = ${plist}\n\tstate = running\n\tpid = ${pid}\n}\n`,
    stderr: "",
  } satisfies CommandResult;
}

function absent() {
  return {
    code: 113,
    stdout: "",
    stderr: `Could not find service "${SERVICE_ID}" in domain for user`,
  } satisfies CommandResult;
}

describe("service-aware launchd session", () => {
  it("reports running with the launchd pid and plist", async () => {
    const run = vi.fn<ServiceCommandRunner>(async () => running(84237));
    await expect(
      inspectLaunchdService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
      }),
    ).resolves.toEqual({
      state: "running",
      pid: 84237,
      plistPath: "/tmp/h/Library/LaunchAgents/x.plist",
    });
  });

  it("treats 'could not find service' as absent", async () => {
    const run = vi.fn<ServiceCommandRunner>(async () => absent());
    await expect(
      inspectLaunchdService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
      }),
    ).resolves.toEqual({ state: "absent" });
  });

  it("fails closed on an unexpected launchctl error", async () => {
    const run = vi.fn<ServiceCommandRunner>(async () => ({
      code: 1,
      stdout: "",
      stderr: "Input/output error",
    }));
    await expect(
      inspectLaunchdService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
      }),
    ).resolves.toEqual({ state: "unknown", code: "launchd_inspection_failed" });
  });

  it("stops by booting the service out and only reports stopped once gone", async () => {
    const calls: string[][] = [];
    let state: CommandResult = running(84237);
    const run = vi.fn<ServiceCommandRunner>(async (command) => {
      calls.push([...command]);
      if (command[1] === "bootout") {
        state = absent();
        return { code: 0, stdout: "", stderr: "" };
      }
      return state;
    });

    await expect(
      stopManagedService({ serviceId: SERVICE_ID, uid: UID, runCaptured: run }),
    ).resolves.toBe("stopped");
    // The real停用 is a launchctl bootout, not a signal to a receipt pid.
    expect(calls.some((c) => c[0] === "launchctl" && c[1] === "bootout")).toBe(
      true,
    );
  });

  it("refuses to claim stopped when launchd keeps the service running", async () => {
    const run = vi.fn<ServiceCommandRunner>(async (command) => {
      if (command[1] === "bootout") return { code: 0, stdout: "", stderr: "" };
      // KeepAlive instantly restarts it: print still reports running.
      return running(99999);
    });
    await expect(
      stopManagedService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
        timeoutMs: 300,
      }),
    ).resolves.toBe("still-running");
  });

  // Real-machine finding (2026-09-29 cleanup): after `bootout`, macOS launchd
  // re-loads the plist from ~/Library/LaunchAgents, so the label comes back.
  // The old code returned "stopped" on the *first* absent sample and reported
  // success while the service was running again — the exact red line A8 exists
  // to prevent. "Stopped" must mean sustained absence, not one absent sample.
  it("does not report stopped on a single absent sample that then returns", async () => {
    let prints = 0;
    const run = vi.fn<ServiceCommandRunner>(async (command) => {
      if (command[1] === "bootout") return { code: 0, stdout: "", stderr: "" };
      prints += 1;
      // print #1 (before) running; #2 (after bootout) briefly absent because
      // launchd is re-loading; #3+ running again.
      if (prints === 2) return absent();
      return running(50000 + prints);
    });
    await expect(
      stopManagedService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
        timeoutMs: 1_200,
        pollMs: 50,
      }),
    ).resolves.toBe("still-running");
  });

  it("start reports not-running state as absent so the caller can spawn", async () => {
    // Absent AND no managed plist on disk -> nothing to bootstrap; caller spawns.
    const run = vi.fn<ServiceCommandRunner>(async () => absent());
    await expect(
      startManagedService({
        serviceId: SERVICE_ID,
        uid: UID,
        home: "/nonexistent/home",
        runCaptured: run,
      }),
    ).resolves.toBe("absent");
  });

  it("start kickstarts a registered service instead of spawning a rival", async () => {
    const calls: string[][] = [];
    // First print: loaded but not running -> start must kickstart.
    let printed = 0;
    const run = vi.fn<ServiceCommandRunner>(async (command) => {
      calls.push([...command]);
      if (command[1] === "print") {
        printed += 1;
        return printed === 1
          ? {
              code: 0,
              stdout: `path = /tmp/x.plist\nstate = not running\n`,
              stderr: "",
            }
          : running(84237);
      }
      return running(84237);
    });
    await expect(
      startManagedService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
      }),
    ).resolves.toBe("started");
    expect(calls).toContainEqual([
      "launchctl",
      "kickstart",
      "-k",
      `gui/${UID}/${SERVICE_ID}`,
    ]);
  });

  it("start is idempotent when the service is already running", async () => {
    const calls: string[][] = [];
    const run = vi.fn<ServiceCommandRunner>(async (command) => {
      calls.push([...command]);
      return running(84237);
    });
    await expect(
      startManagedService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
      }),
    ).resolves.toBe("started");
    // Already running -> no kickstart needed.
    expect(calls.some((c) => c[1] === "kickstart")).toBe(false);
  });

  it("start bootstraps the managed plist after a bootout", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "memhub-la-"));
    const agents = path.join(home, "Library", "LaunchAgents");
    await mkdir(agents, { recursive: true });
    const plist = path.join(agents, `${SERVICE_ID}.plist`);
    await writeFile(plist, "<plist/>");
    const calls: string[][] = [];
    let printed = 0;
    const run = vi.fn<ServiceCommandRunner>(async (command) => {
      calls.push([...command]);
      if (command[1] === "print") {
        printed += 1;
        return printed === 1 ? absent() : running(555);
      }
      return { code: 0, stdout: "", stderr: "" };
    });
    await expect(
      startManagedService({
        serviceId: SERVICE_ID,
        uid: UID,
        home,
        runCaptured: run,
      }),
    ).resolves.toBe("started");
    expect(calls).toContainEqual([
      "launchctl",
      "bootstrap",
      `gui/${UID}`,
      plist,
    ]);
  });

  it("treats a loaded service with no pid as loaded, not absent", async () => {
    const run = vi.fn<ServiceCommandRunner>(async () => ({
      code: 0,
      stdout: `path = /tmp/x.plist\nstate = not running\n`,
      stderr: "",
    }));
    await expect(
      inspectLaunchdService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
      }),
    ).resolves.toEqual({ state: "loaded", plistPath: "/tmp/x.plist" });
  });

  it("restart kickstarts in place and keeps the registration", async () => {
    const calls: string[][] = [];
    const run = vi.fn<ServiceCommandRunner>(async (command) => {
      calls.push([...command]);
      return running(101);
    });
    await expect(
      restartManagedService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
      }),
    ).resolves.toBe("restarted");
    expect(calls).toContainEqual([
      "launchctl",
      "kickstart",
      "-k",
      `gui/${UID}/${SERVICE_ID}`,
    ]);
    // Restart must never bootout (that would unregister the service).
    expect(calls.some((c) => c[1] === "bootout")).toBe(false);
  });

  // C8 P1 (2026-09-29): `status`/`stop`/`start` treated *any* running
  // `com.tencent.onememory.runtime` label as this data dir's Runtime. The label
  // is global per user, so a second install (or a test with an injected data
  // dir) saw a stranger's service reported as its own. Identity must come from
  // the plist's OWN_MEMORY_DATA_DIR, not the label name alone.
  it("does not claim a running label whose plist binds another data dir", async () => {
    const run = vi.fn<ServiceCommandRunner>(async (command) => {
      if (command[0] === "launchctl") {
        return {
          code: 0,
          stdout: `\tpath = /tmp/h/Library/LaunchAgents/x.plist\n\tstate = running\n\tpid = 42\n`,
          stderr: "",
        };
      }
      // plutil: this plist belongs to a different data dir.
      return {
        code: 0,
        stdout: JSON.stringify({
          Label: SERVICE_ID,
          ProgramArguments: ["/tmp/node", "/tmp/runtime.cjs", "serve"],
          EnvironmentVariables: { ONE_MEMORY_DATA_DIR: "/somewhere/else" },
        }),
        stderr: "",
      };
    });
    await expect(
      inspectLaunchdService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
        dataDir: "/tmp/this-install/data",
      }),
    ).resolves.toMatchObject({ state: "foreign" });
  });

  it("claims a running label whose plist binds this exact data dir", async () => {
    const run = vi.fn<ServiceCommandRunner>(async (command) => {
      if (command[0] === "launchctl") {
        return {
          code: 0,
          stdout: `\tpath = /tmp/h/Library/LaunchAgents/x.plist\n\tstate = running\n\tpid = 42\n`,
          stderr: "",
        };
      }
      return {
        code: 0,
        stdout: JSON.stringify({
          Label: SERVICE_ID,
          ProgramArguments: ["/tmp/node", "/tmp/runtime.cjs", "serve"],
          EnvironmentVariables: {
            ONE_MEMORY_DATA_DIR: "/tmp/this-install/data",
          },
        }),
        stderr: "",
      };
    });
    await expect(
      inspectLaunchdService({
        serviceId: SERVICE_ID,
        uid: UID,
        runCaptured: run,
        dataDir: "/tmp/this-install/data",
      }),
    ).resolves.toMatchObject({ state: "running", pid: 42 });
  });
});
