import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { expectRestrictedFileMode } from "./expect-restricted-mode.js";
import {
  applyRecallInstall,
  claudeCodeLayout,
  planRecallInstall,
  previewRecallInstall,
  rollbackRecallInstall,
  verifyRecallInstall,
} from "./recall-installer.js";

describe("Claude Code recall installer", () => {
  it("merges into the real config shape, verifies, and rolls back", async () => {
    const { layout, configPath } = await fixture();
    // Claude Code keeps unrelated state in the same file, so an install that
    // rewrites it wholesale would silently drop the user's projects and
    // preferences.
    await writeFile(
      configPath,
      `${JSON.stringify(
        {
          installMethod: "native",
          autoUpdates: true,
          projects: { "/Users/someone/work": { allowedTools: [] } },
          mcpServers: { "fixture-existing-server": { command: "keep-me" } },
        },
        null,
        2,
      )}\n`,
    );

    const plan = await planRecallInstall(layout, runtime());
    await applyRecallInstall(plan);
    await verifyRecallInstall(layout);

    const installed = JSON.parse(await readFile(configPath, "utf8"));
    expect(installed.installMethod).toBe("native");
    expect(installed.projects["/Users/someone/work"]).toBeDefined();
    expect(installed.mcpServers["fixture-existing-server"]).toBeDefined();
    expect(installed.mcpServers["one-memory"].env).not.toHaveProperty(
      "ONE_MEMORY_API_TOKEN",
    );
    await expectRestrictedFileMode(layout.journalPath);
    // Claude Code has a skill mechanism, so this host must install one.
    expect(layout.skillPath).not.toBeNull();
    expect(await readFile(String(layout.skillPath), "utf8")).toContain(
      "memhub-recall",
    );

    await rollbackRecallInstall(layout);

    const rolledBack = JSON.parse(await readFile(configPath, "utf8"));
    expect(rolledBack.installMethod).toBe("native");
    expect(rolledBack.projects["/Users/someone/work"]).toBeDefined();
    expect(rolledBack.mcpServers["fixture-existing-server"]).toBeDefined();
    expect(rolledBack.mcpServers["one-memory"]).toBeUndefined();
  });

  it("installs into a config that does not exist yet", async () => {
    const { layout, configPath } = await fixture();

    const plan = await planRecallInstall(layout, runtime());
    expect(plan.actions).toContain("create-mcp");
    await applyRecallInstall(plan);
    await verifyRecallInstall(layout);

    expect(
      JSON.parse(await readFile(configPath, "utf8")).mcpServers["one-memory"],
    ).toBeDefined();

    await rollbackRecallInstall(layout);
    // The installer created the file, so rolling back leaves nothing behind.
    await expect(readFile(configPath, "utf8")).rejects.toThrow();
  });

  it("names Claude Code when refusing an unmanaged collision", async () => {
    const { layout, configPath } = await fixture();
    const original = JSON.stringify({
      mcpServers: { "one-memory": { command: "/somebody/else" } },
    });
    await writeFile(configPath, original);

    await expect(planRecallInstall(layout, runtime())).rejects.toThrow(
      /Claude Code already has an unmanaged MCP server/,
    );
    expect(await readFile(configPath, "utf8")).toBe(original);
  });

  it("refuses a skill path outside the host directory", async () => {
    const { layout } = await fixture();
    const escaping = {
      ...layout,
      skillPath: path.join(layout.containmentRoot, "..", "escaped", "SKILL.md"),
    };

    const plan = await planRecallInstall(escaping, runtime());
    await expect(applyRecallInstall(plan)).rejects.toThrow(
      /escapes Claude Code root/,
    );
  });
});

describe("Claude Code isolated config guard", () => {
  it("refuses an isolated host dir without an explicit config before any write", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "om-claude-isolation-"));
    try {
      const fakeHome = path.join(root, "home");
      const hostDir = path.join(fakeHome, "custom-claude");
      await mkdir(fakeHome, { recursive: true });
      await mkdir(hostDir, { recursive: true });
      const result = runInstallerCli(hostDir, root, fakeHome);
      expect(result.status).not.toBe(0);
      expect(result.stderr).toContain("isolated_claude_config_required");
      await expect(
        readFile(path.join(fakeHome, ".claude.json"), "utf8"),
      ).rejects.toThrow();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("requires an explicit opt-in for the default Claude host directory", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "om-claude-default-"));
    try {
      const fakeHome = path.join(root, "home");
      const hostDir = path.join(fakeHome, ".claude");
      await mkdir(hostDir, { recursive: true });
      const result = runInstallerCli(hostDir, root, fakeHome);
      expect(result.status).not.toBe(0);
      expect(result.stderr).toContain("isolated_claude_config_required");
      await expect(
        readFile(path.join(fakeHome, ".claude.json"), "utf8"),
      ).rejects.toThrow();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("previews the default config only with --allow-default-config", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "om-claude-allow-"));
    try {
      const fakeHome = path.join(root, "home");
      const hostDir = path.join(fakeHome, ".claude");
      await mkdir(hostDir, { recursive: true });
      const result = runInstallerCli(hostDir, root, fakeHome, [
        "--allow-default-config",
      ]);
      expect(result.status).toBe(0);
      expect(result.stderr).toBe("");
      expect(JSON.parse(result.stdout)).toMatchObject({
        ok: true,
        command: "preview",
      });
      await expect(
        readFile(path.join(fakeHome, ".claude.json"), "utf8"),
      ).rejects.toThrow();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("previews an isolated host dir with an explicit config", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "om-claude-explicit-"));
    try {
      const fakeHome = path.join(root, "home");
      const hostDir = path.join(fakeHome, "custom-claude");
      const configPath = path.join(root, "claude.json");
      await mkdir(hostDir, { recursive: true });
      await writeFile(
        configPath,
        JSON.stringify({
          mcpServers: { keep: { command: "keep" } },
          permissions: { allow: ["Read"] },
        }),
      );
      const result = runInstallerCli(hostDir, root, fakeHome, [
        "--config",
        configPath,
      ]);
      expect(result.status).toBe(0);
      expect(result.stderr).toBe("");
      expect(JSON.parse(result.stdout)).toMatchObject({
        ok: true,
        command: "preview",
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("accepts an explicit fresh config and preserves unrelated settings", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "om-claude-explicit-"));
    try {
      const hostDir = path.join(root, ".claude");
      const configPath = path.join(root, "claude.json");
      await mkdir(hostDir, { recursive: true });
      await writeFile(
        configPath,
        JSON.stringify({
          mcpServers: { keep: { command: "keep" } },
          permissions: { allow: ["Read"] },
        }),
      );
      const layout = claudeCodeLayout({ claudeDir: hostDir, configPath });
      const plan = await planRecallInstall(layout, {
        runtimeCommand: path.join(root, "runtime.cjs"),
        mcpEntryPath: path.join(root, "mcp.cjs"),
        discoveryPath: path.join(root, "discovery.json"),
      });
      const preview = await previewRecallInstall(plan);
      await applyRecallInstall(plan, preview.fingerprint);
      const installed = JSON.parse(await readFile(configPath, "utf8"));
      expect(installed.mcpServers.keep).toEqual({ command: "keep" });
      expect(installed.permissions).toEqual({ allow: ["Read"] });
      expect(installed.mcpServers["one-memory"]).toBeDefined();
      await rollbackRecallInstall(layout);
      const restored = JSON.parse(await readFile(configPath, "utf8"));
      expect(restored.mcpServers.keep).toEqual({ command: "keep" });
      expect(restored.permissions).toEqual({ allow: ["Read"] });
      expect(restored.mcpServers["one-memory"]).toBeUndefined();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});

function runInstallerCli(
  hostDir: string,
  root: string,
  fakeHome: string,
  extra: string[] = [],
) {
  return spawnSync(
    process.execPath,
    [
      path.join(process.cwd(), "dist/installer-cli.cjs"),
      "preview",
      "--host",
      "claude-code",
      "--host-dir",
      hostDir,
      "--runtime-command",
      process.execPath,
      "--mcp-entry",
      path.join(process.cwd(), "dist/mcp.cjs"),
      "--discovery",
      path.join(root, "discovery.json"),
      ...extra,
    ],
    {
      cwd: process.cwd(),
      encoding: "utf8",
      env: { ...process.env, HOME: fakeHome, USERPROFILE: fakeHome },
    },
  );
}

async function fixture(): Promise<{
  layout: ReturnType<typeof claudeCodeLayout>;
  configPath: string;
}> {
  const home = await mkdtemp(path.join(os.tmpdir(), "om-claude-fixture-"));
  const claudeDir = path.join(home, ".claude");
  await mkdir(claudeDir);
  const configPath = path.join(home, ".claude.json");
  return { layout: claudeCodeLayout({ claudeDir, configPath }), configPath };
}

function runtime() {
  return {
    runtimeCommand: "/Applications/MemHub.app/Contents/MacOS/MemHub",
    mcpEntryPath:
      "/Applications/MemHub.app/Contents/Resources/host-bridge/mcp.cjs",
    discoveryPath: path.join(
      os.homedir(),
      ".one-memory",
      "integrations",
      "cursor-broker.json",
    ),
  };
}
