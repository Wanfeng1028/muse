import {
  mkdir,
  mkdtemp,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";

import {
  installUserService,
  parseDisabledOverride,
  parseLaunchctlPlistPath,
  restartUserService,
  uninstallUserService,
} from "./service-install.js";
import {
  planUserService,
  priorLaunchAgentDeclarations,
  runtimeInstallLayout,
} from "./service-plan.js";

const installManagedService = installUserService;

describe("user service installation", () => {
  it("reads the plist path launchctl actually prints, quoted or not", () => {
    expect(
      parseLaunchctlPlistPath(
        [
          "gui/501/com.tencent.onememory.runtime = {",
          "\tactive count = 1",
          "\tpath = /private/var/folders/xy/Library/LaunchAgents/one.plist",
          "\ttype = LaunchAgent",
        ].join("\n"),
      ),
    ).toBe("/private/var/folders/xy/Library/LaunchAgents/one.plist");
    expect(parseLaunchctlPlistPath('path = "/Users/A B/x.plist"')).toBe(
      "/Users/A B/x.plist",
    );
    expect(parseLaunchctlPlistPath("gui/501/x = {\n\tactive count = 0")).toBe(
      null,
    );
  });

  it("reads the durable launchctl disable override", () => {
    const table = [
      "",
      "\tdisabled services = {",
      '\t\t"com.docker.helper" => enabled',
      '\t\t"com.tencent.onememory.runtime.abc123" => disabled',
      "\t}",
    ].join("\n");
    expect(
      parseDisabledOverride(table, "com.tencent.onememory.runtime.abc123"),
    ).toBe(true);
    expect(parseDisabledOverride(table, "com.docker.helper")).toBe(false);
    // No entry means no override at all, which is not the same as disabled.
    expect(
      parseDisabledOverride(table, "com.tencent.onememory.runtime.missing"),
    ).toBe(false);
    expect(parseDisabledOverride("", "com.tencent.onememory.runtime")).toBe(
      false,
    );
  });

  it("reuses an already registered managed LaunchAgent without bootstrapping", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const plan = planUserService(layout, { uid: 501 });
    await mkdir(path.dirname(plan.service_file?.path as string), {
      recursive: true,
      mode: 0o700,
    });
    await writeFile(
      plan.service_file?.path as string,
      plan.service_file?.content as string,
      { mode: 0o600 },
    );
    const commands: string[][] = [];

    await installManagedService(layout, {
      uid: 501,
      platform: "darwin",
      inspectRegistration: async () => "managed",
      runCommand: async (command) => {
        commands.push([...command]);
      },
    });

    expect(commands).toEqual(plan.commands.restart);
    expect(await readFile(plan.service_file?.path as string, "utf8")).toBe(
      plan.service_file?.content,
    );
  });

  it("repairs a missing declaration for an already registered managed LaunchAgent", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const plan = planUserService(layout, { uid: 501 });
    const commands: string[][] = [];

    await installManagedService(layout, {
      uid: 501,
      platform: "darwin",
      inspectRegistration: async () => "managed",
      runCommand: async (command) => {
        commands.push([...command]);
      },
    });

    expect(commands).toEqual(plan.commands.restart);
    expect(await readFile(plan.service_file?.path as string, "utf8")).toBe(
      plan.service_file?.content,
    );
  });

  it("prepares owner-only launchd log files before bootstrapping", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
      dataDir: path.join(home, "Private Memory"),
    });
    await writeRuntimeFiles(layout);
    const commands: string[][] = [];

    const plan = await installManagedService(layout, {
      uid: 501,
      platform: "darwin",
      inspectRegistration: async () => "absent",
      runCommand: async (command) => {
        commands.push([...command]);
      },
    });

    // launchd will not create the redirect parent, and a login start must not be
    // able to silently fall back to a default home.
    expect(plan.log_directory).toBe(path.join(layout.dataDir, "logs"));
    expect((await stat(plan.log_directory as string)).mode & 0o777).toBe(0o700);
    for (const name of ["service.log", "service-error.log"]) {
      const log = await stat(path.join(plan.log_directory as string, name));
      expect(log.isFile()).toBe(true);
      expect(log.mode & 0o777).toBe(0o600);
    }
    expect(commands).toEqual(plan.commands.install);
  });

  it("does not create log artifacts when the label belongs to someone else", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);

    await expect(
      installManagedService(layout, {
        uid: 501,
        platform: "darwin",
        inspectRegistration: async () => "conflict",
        runCommand: vi.fn(),
      }),
    ).rejects.toThrow("runtime_service_label_conflict");

    await expect(
      readFile(path.join(layout.dataDir, "logs", "service.log")),
    ).rejects.toThrow();
  });

  it("refuses to install over a system- or user-disabled service", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const commands = vi.fn();

    // launchctl disable is a durable override; bootstrapping over it fails with
    // exit 5 and would silently undo the user's or the system's decision.
    await expect(
      installManagedService(layout, {
        uid: 501,
        platform: "darwin",
        inspectRegistration: async () => "disabled",
        runCommand: commands,
      }),
    ).rejects.toThrow("runtime_service_disabled_by_system");

    expect(commands).not.toHaveBeenCalled();
    const plan = planUserService(layout, { uid: 501 });
    await expect(readFile(plan.service_file?.path as string)).rejects.toThrow();
    await expect(
      readFile(path.join(layout.dataDir, "logs", "service.log")),
    ).rejects.toThrow();
  });

  it("probes the real print-disabled table before treating a label as installable", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-service-probe-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const plan = planUserService(layout, { uid: 501 });
    const bin = path.join(home, "fake-bin");
    await mkdir(bin, { recursive: true, mode: 0o700 });
    const fakeLaunchctl = path.join(bin, "launchctl");
    await writeFile(
      fakeLaunchctl,
      [
        "#!/bin/sh",
        'if [ "$1" = "print-disabled" ]; then',
        "  printf '\\t\\t\"%s\" => disabled\\n' " +
          JSON.stringify(plan.service_id),
        "  exit 0",
        "fi",
        "exit 113",
        "",
      ].join("\n"),
      { mode: 0o755 },
    );
    const previousPath = process.env.PATH;
    const commands = vi.fn();
    process.env.PATH = `${bin}:${previousPath ?? ""}`;
    try {
      // No inspectRegistration stub here: this must go through the real
      // `inspectLaunchAgentRegistration` -> `launchctl print-disabled` probe.
      await expect(
        installManagedService(layout, {
          uid: 501,
          platform: "darwin",
          runCommand: commands,
        }),
      ).rejects.toThrow("runtime_service_disabled_by_system");
    } finally {
      process.env.PATH = previousPath;
    }
    expect(commands).not.toHaveBeenCalled();
  });

  it("upgrades a managed LaunchAgent written before log redirects existed", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const plan = planUserService(layout, { uid: 501 });
    // Index 1 is the redirect-carrying shape -- what a user who installed from
    // a package actually has on disk, and the one this migration exists for.
    // (Index 0 already equals the current content, so it needs no migration.)
    const legacy = priorLaunchAgentDeclarations(layout)[1] as string;
    await mkdir(path.dirname(plan.service_file?.path as string), {
      recursive: true,
      mode: 0o700,
    });
    await writeFile(plan.service_file?.path as string, legacy, { mode: 0o600 });
    const commands: string[][] = [];

    await installManagedService(layout, {
      uid: 501,
      platform: "darwin",
      inspectRegistration: async () => "managed",
      runCommand: async (command) => {
        commands.push([...command]);
      },
    });

    expect(await readFile(plan.service_file?.path as string, "utf8")).toBe(
      plan.service_file?.content,
    );
    // A changed declaration only takes effect after launchd reboots the job:
    // bootout (allowed to fail), then bootstrap, which reloads and starts.
    expect(commands).toEqual([...plan.commands.stop, ...plan.commands.install]);
  });

  it("rejects an unknown same-label LaunchAgent with a distinct error", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const commands = vi.fn();

    await expect(
      installManagedService(layout, {
        uid: 501,
        platform: "darwin",
        inspectRegistration: async () => "conflict",
        runCommand: commands,
      }),
    ).rejects.toThrow("runtime_service_label_conflict");

    expect(commands).not.toHaveBeenCalled();
    const plan = planUserService(layout, { uid: 501 });
    await expect(readFile(plan.service_file?.path as string)).rejects.toThrow();
  });

  it("preserves an existing managed LaunchAgent declaration when restart fails", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const plan = planUserService(layout, { uid: 501 });
    await mkdir(path.dirname(plan.service_file?.path as string), {
      recursive: true,
      mode: 0o700,
    });
    await writeFile(
      plan.service_file?.path as string,
      plan.service_file?.content as string,
      { mode: 0o600 },
    );
    const dataMarker = path.join(layout.dataDir, "existing-data");
    await mkdir(layout.dataDir, { recursive: true });
    await writeFile(dataMarker, "keep existing data");

    await expect(
      installManagedService(layout, {
        uid: 501,
        platform: "darwin",
        inspectRegistration: async () => "managed",
        runCommand: async () => {
          throw new Error("restart failed");
        },
      }),
    ).rejects.toThrow("runtime_service_command_failed");

    expect(await readFile(plan.service_file?.path as string, "utf8")).toBe(
      plan.service_file?.content,
    );
    expect(await readFile(layout.runtimeEntry, "utf8")).toBe("fixture");
    expect(await readFile(dataMarker, "utf8")).toBe("keep existing data");
  });

  it("sanitizes LaunchAgent inspection failures", async () => {
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);

    const error = await installManagedService(layout, {
      uid: 501,
      platform: "darwin",
      inspectRegistration: async () => {
        throw new Error("SECRET_LAUNCHCTL_OUTPUT");
      },
      runCommand: vi.fn(),
    }).catch((reason: unknown) => reason);

    expect(error).toEqual(new Error("runtime_service_inspection_failed"));
    expect(error).not.toHaveProperty("cause");
  });

  it("writes a new Linux user unit before executing exact argv", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: process.platform === "darwin" ? "darwin" : "linux",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const commands: readonly string[][] = [];
    const plan = await installManagedService(layout, {
      uid: process.getuid?.(),
      xdgConfigHome: path.join(home, ".config"),
      inspectRegistration: async () => "absent",
      runCommand: async (command) => {
        (commands as string[][]).push([...command]);
      },
    });

    expect(await readFile(plan.service_file?.path as string, "utf8")).toBe(
      plan.service_file?.content,
    );
    expect(commands).toEqual(plan.commands.install);
  });

  it("rolls back the newly written service file when activation fails", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: process.platform === "darwin" ? "darwin" : "linux",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    let calls = 0;

    await expect(
      installManagedService(layout, {
        uid: process.getuid?.(),
        xdgConfigHome: path.join(home, ".config"),
        inspectRegistration: async () => "absent",
        runCommand: async () => {
          calls += 1;
          if (calls === 1) throw new Error("activation failed");
        },
      }),
    ).rejects.toThrow("runtime_service_command_failed");

    const plan = planFor(layout, home);
    await expect(readFile(plan.service_file?.path as string)).rejects.toThrow();
    expect(calls).toBe(1);
  });

  it("does not overwrite an existing service file", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: process.platform === "darwin" ? "darwin" : "linux",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const plan = planFor(layout, home);
    const { mkdir, writeFile } = await import("node:fs/promises");
    await mkdir(path.dirname(plan.service_file?.path as string), {
      recursive: true,
    });
    await writeFile(plan.service_file?.path as string, "unmanaged");

    await expect(
      installManagedService(layout, {
        uid: process.getuid?.(),
        xdgConfigHome: path.join(home, ".config"),
        inspectRegistration: async () => "absent",
        runCommand: vi.fn(),
      }),
    ).rejects.toThrow("runtime_service_file_exists");
    expect(await readFile(plan.service_file?.path as string, "utf8")).toBe(
      "unmanaged",
    );
  });

  it("does not write or run commands for an incomplete Runtime install", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-service-install-"));
    const layout = runtimeInstallLayout({
      platform: process.platform === "darwin" ? "darwin" : "linux",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    await rm(layout.runtimeEntry);
    const commands = vi.fn();

    await expect(
      installManagedService(layout, {
        uid: process.getuid?.(),
        xdgConfigHome: path.join(home, ".config"),
        runCommand: commands,
      }),
    ).rejects.toThrow("runtime_service_install_root_not_ready");
    expect(commands).not.toHaveBeenCalled();
    const plan = planFor(layout, home);
    await expect(readFile(plan.service_file?.path as string)).rejects.toThrow();
  });

  it("uninstalls a disabled, not-loaded service without forcing it back on", async () => {
    if (process.platform !== "darwin") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-service-disabled-un-"));
    const layout = runtimeInstallLayout({
      platform: "darwin",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const plan = planUserService(layout, { uid: 501 });
    await mkdir(path.dirname(plan.service_file?.path as string), {
      recursive: true,
      mode: 0o700,
    });
    await writeFile(
      plan.service_file?.path as string,
      plan.service_file?.content as string,
      { mode: 0o600 },
    );
    const dataMarker = path.join(layout.dataDir, "keep-me");
    await mkdir(layout.dataDir, { recursive: true });
    await writeFile(dataMarker, "user data");
    const commands: string[][] = [];

    // launchctl bootout reports exit 5 for a disabled, unloaded label. The
    // only trusted probe here is the real launchctl print, which reports 113
    // ("not loaded") in this throwaway HOME because the label is scoped to a
    // temp install root.
    await expect(
      uninstallUserService(layout, {
        uid: 501,
        platform: "darwin",
        runCommand: async (command) => {
          commands.push([...command]);
          throw new Error("Boot-out failed: 5: Input/output error");
        },
      }),
    ).resolves.toBe("removed");

    expect(commands).toEqual(plan.commands.uninstall);
    await expect(readFile(plan.service_file?.path as string)).rejects.toThrow();
    expect(await readFile(dataMarker, "utf8")).toBe("user data");
  });

  it("uninstalls only the exact managed service file and preserves Runtime data", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-service-uninstall-"));
    const layout = runtimeInstallLayout({
      platform: process.platform === "darwin" ? "darwin" : "linux",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const dataMarker = path.join(layout.dataDir, "keep-me");
    await mkdir(layout.dataDir, { recursive: true });
    await writeFile(dataMarker, "user data");
    const commands: string[][] = [];
    const options = {
      uid: process.getuid?.(),
      xdgConfigHome: path.join(home, ".config"),
      inspectRegistration: async () => "absent" as const,
      runCommand: async (command: readonly string[]) => {
        commands.push([...command]);
      },
    };
    const plan = await installManagedService(layout, options);

    await expect(uninstallUserService(layout, options)).resolves.toBe(
      "removed",
    );

    await expect(readFile(plan.service_file?.path as string)).rejects.toThrow();
    expect(commands).toEqual([
      ...plan.commands.install,
      ...plan.commands.uninstall,
    ]);
    expect(await readFile(layout.runtimeEntry, "utf8")).toBe("fixture");
    expect(await readFile(dataMarker, "utf8")).toBe("user data");
  });

  it("accepts a failed Linux disable only after systemd reports disabled and inactive", async () => {
    if (process.platform !== "linux") return;
    const home = await mkdtemp(
      path.join(tmpdir(), "om-service-linux-uninstall-"),
    );
    const layout = runtimeInstallLayout({
      platform: "linux",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const options = {
      uid: process.getuid?.(),
      xdgConfigHome: path.join(home, ".config"),
      runCommand: async (command: readonly string[]) => {
        if (command.includes("disable")) throw new Error("systemctl exit 1");
      },
    };
    const plan = await installManagedService(layout, {
      ...options,
      runCommand: async () => undefined,
    });
    await expect(
      uninstallUserService(layout, {
        ...options,
        inspectLinuxState: async () => ({
          code: 0,
          stdout: "LoadState=not-found\nUnitFileState=\nActiveState=inactive\n",
        }),
      }),
    ).resolves.toBe("removed");
    await expect(readFile(plan.service_file?.path as string)).rejects.toThrow();
  });

  it("preserves the Linux unit when a failed disable still reports active", async () => {
    if (process.platform !== "linux") return;
    const home = await mkdtemp(
      path.join(tmpdir(), "om-service-linux-uninstall-"),
    );
    const layout = runtimeInstallLayout({
      platform: "linux",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const plan = await installManagedService(layout, {
      uid: process.getuid?.(),
      xdgConfigHome: path.join(home, ".config"),
      runCommand: async () => undefined,
    });
    await expect(
      uninstallUserService(layout, {
        uid: process.getuid?.(),
        xdgConfigHome: path.join(home, ".config"),
        runCommand: async (command) => {
          if (command.includes("disable")) {
            throw new Error("systemctl exit 1");
          }
        },
        inspectLinuxState: async () => ({
          code: 0,
          stdout:
            "LoadState=loaded\nUnitFileState=disabled\nActiveState=active\n",
        }),
      }),
    ).rejects.toThrow("systemctl exit 1");
    await expect(
      readFile(plan.service_file?.path as string, "utf8"),
    ).resolves.toBe(plan.service_file?.content);
  });

  it("refuses to uninstall a modified service file", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-service-uninstall-"));
    const layout = runtimeInstallLayout({
      platform: process.platform === "darwin" ? "darwin" : "linux",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const options = {
      uid: process.getuid?.(),
      xdgConfigHome: path.join(home, ".config"),
      inspectRegistration: async () => "absent" as const,
      runCommand: async () => undefined,
    };
    const plan = await installManagedService(layout, options);
    await (await import("node:fs/promises")).writeFile(
      plan.service_file?.path as string,
      "user modified",
    );

    await expect(uninstallUserService(layout, options)).rejects.toThrow(
      "runtime_service_file_modified",
    );
    expect(await readFile(plan.service_file?.path as string, "utf8")).toBe(
      "user modified",
    );
  });

  it("restarts only an exact managed service file", async () => {
    if (process.platform === "win32") return;
    const home = await mkdtemp(path.join(tmpdir(), "om-service-restart-"));
    const layout = runtimeInstallLayout({
      platform: process.platform === "darwin" ? "darwin" : "linux",
      home,
      installRoot: path.join(home, "runtime"),
    });
    await writeRuntimeFiles(layout);
    const commands: string[][] = [];
    const options = {
      uid: process.getuid?.(),
      xdgConfigHome: path.join(home, ".config"),
      inspectRegistration: async () => "absent" as const,
      runCommand: async (command: readonly string[]) => {
        commands.push([...command]);
      },
    };
    const plan = await installManagedService(layout, options);
    commands.length = 0;

    await restartUserService(layout, options);

    expect(commands).toEqual(plan.commands.restart);
  });
});

async function writeRuntimeFiles(
  layout: ReturnType<typeof runtimeInstallLayout>,
) {
  for (const file of [
    layout.nodeCommand,
    layout.runtimeEntry,
    layout.coreCommand,
    layout.mcpEntryPath,
    layout.recallCliPath,
    path.join(layout.syncHookAssetsDirectory, "manifest.json"),
  ]) {
    const { mkdir, writeFile } = await import("node:fs/promises");
    await mkdir(path.dirname(file), { recursive: true });
    await writeFile(file, "fixture");
  }
}

function planFor(
  layout: ReturnType<typeof runtimeInstallLayout>,
  home: string,
) {
  return planUserService(layout, {
    uid: process.getuid?.(),
    xdgConfigHome: path.join(home, ".config"),
  });
}
