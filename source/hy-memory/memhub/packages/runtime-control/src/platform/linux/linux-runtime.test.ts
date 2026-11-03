import path from "node:path";
import { describe, expect, it } from "vitest";
import { planLinuxRuntimeControl } from "./linux-runtime.js";

function layout(home: string) {
  return {
    platform: "linux" as const,
    home,
    installRoot: `${home}/.local/share/one-memory/current`,
    dataDir: `${home}/.one-memory`,
    nodeCommand: `${home}/.local/share/one-memory/current/bin/node`,
    runtimeEntry: `${home}/.local/share/one-memory/current/runtime/runtime.cjs`,
    coreCommand: `${home}/.local/share/one-memory/current/core/one-memory`,
    mcpEntryPath: `${home}/.local/share/one-memory/current/host-bridge/mcp.cjs`,
    recallCliPath: `${home}/.local/share/one-memory/current/host-bridge/recall-cli.cjs`,
    syncHookAssetsDirectory: path.join(
      home,
      ".local/share/one-memory/current/host-bridge/sync-hook",
    ),
  };
}

describe("Linux runtime control matrix", () => {
  it("blocks systemd before the OS reports a real user manager", () => {
    const plan = planLinuxRuntimeControl({
      layout: layout("/home/example"),
      host: {
        systemd: false,
        portables: false,
        tmpfilesD: false,
      },
    });
    expect(plan.capabilities).toMatchObject({
      systemd_user: "unavailable",
      portable_service: "unavailable",
      tmpfiles_d: "unavailable",
    });
    expect(plan.systemd).toBeNull();
    expect(plan.blocked_reason).toBe("linux_systemd_user_unavailable");
  });

  it("upgrades a legacy Memmy-style unit without losing the wanted-by target", () => {
    const plan = planLinuxRuntimeControl({
      layout: layout("/home/example"),
      host: { systemd: true, portables: true, tmpfilesD: true },
      currentUnit: [
        "[Unit]",
        "Description=Old Service",
        "",
        "[Service]",
        "Type=simple",
        "UMask=0077",
        'ExecStart="/usr/bin/node" "/opt/old/runtime.cjs" serve',
        "Restart=on-failure",
        "",
        "[Install]",
        "WantedBy=default.target",
      ].join("\n"),
    });
    const service = plan.systemd;
    expect(service).not.toBeNull();
    expect(service?.ownedTarget.toLowerCase()).toBe("one-memory.service");
    expect(service?.plan).toMatchObject({
      status: "ready",
      service_id: "one-memory.service",
    });
    expect(service?.legacyCanonicalDigest).toBe(
      "b6c22afdd859760050cac9a4f621e67b38e0eaca",
    );
    expect(service?.migrate).toBe(true);
    expect(service?.upgradeCommands).toEqual([
      ["systemctl", "--user", "stop", "one-memory.service"],
      ["systemctl", "--user", "enable", "--now", "one-memory.service"],
    ]);
    expect(service?.plan.service_file?.content).toContain(
      "WantedBy=default.target",
    );
  });

  it("does not overwrite a unit whose only difference is upstream hardening", () => {
    const plan = planLinuxRuntimeControl({
      layout: layout("/home/example"),
      host: { systemd: true, portables: true, tmpfilesD: true },
      currentUnit: [
        "[Unit]",
        "Description=One Memory Runtime",
        "",
        "[Service]",
        "Type=simple",
        "UMask=0077",
        'ExecStart="/home/example/.local/share/one-memory/current/bin/node" "/home/example/.local/share/one-memory/current/runtime/runtime.cjs" serve',
        'Environment="ONE_MEMORY_RUNTIME_ENTRY=/home/example/.local/share/one-memory/current/runtime/runtime.cjs"',
        'Environment="ONE_MEMORY_DATA_DIR=/home/example/.one-memory"',
        'Environment="ONE_MEMORY_CORE_COMMAND=/home/example/.local/share/one-memory/current/core/one-memory"',
        'Environment="ONE_MEMORY_MCP_ENTRY=/home/example/.local/share/one-memory/current/host-bridge/mcp.cjs"',
        'Environment="ONE_MEMORY_RECALL_CLI=/home/example/.local/share/one-memory/current/host-bridge/recall-cli.cjs"',
        'Environment="ONE_MEMORY_SYNC_HOOK_ASSETS=/home/example/.local/share/one-memory/current/host-bridge/sync-hook"',
        'Environment="ONE_MEMORY_NODE_COMMAND=/home/example/.local/share/one-memory/current/bin/node"',
        "Restart=on-failure",
        "RestartSec=2s",
        "StartLimitIntervalSec=60",
        "StartLimitBurst=5",
        "",
        "[Install]",
        "WantedBy=default.target",
      ].join("\n"),
    });
    expect(plan.systemd?.upgradeCommands).toEqual([]);
  });

  it("repairs missing RestartSec/StartLimit so a broken service cannot restart-storm", () => {
    const plan = planLinuxRuntimeControl({
      layout: layout("/home/example"),
      host: { systemd: true, portables: true, tmpfilesD: true },
      currentUnit: [
        "[Unit]",
        "Description=Old Service",
        "",
        "[Service]",
        "Type=simple",
        "UMask=0077",
        'ExecStart="/usr/bin/node" "/opt/old/runtime.cjs" serve',
        "Restart=on-failure",
        "",
        "[Install]",
        "WantedBy=default.target",
      ].join("\n"),
    });
    const content = plan.systemd?.plan.service_file?.content ?? "";
    expect(content).toContain("RestartSec=2s");
    expect(content).toContain("StartLimitIntervalSec=60");
    expect(content).toContain("StartLimitBurst=5");
  });
});
