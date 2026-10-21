import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  applyRecallInstall,
  codexLayout,
  mcpConfigPath,
  planRecallInstall,
  rollbackRecallInstall,
  verifyRecallInstall,
} from "./recall-installer.js";

/** Shaped after a real `~/.codex/config.toml`, foreign entry included. */
const OCCUPIED = `personality = "pragmatic"

# MemHub 记忆 + 判决账本 + 项目图谱。
# Tutti 会把本文件复制进每个会话的 CODEX_HOME。
[mcp_servers.one-memory]
command = "node"
args = ["/Users/someone/one-memory-tutti/bin/mcp-server.mjs"]
enabled = true

[mcp_servers.screenpipe]
command = "/Applications/screenpipe.app/Contents/MacOS/bun"
args = ["x", "screenpipe-mcp@latest"]
enabled = true

[features]
hooks = true
`;

describe("Codex recall installer", () => {
  it("installs into a config that does not exist yet", async () => {
    const { layout, configPath } = await fixture();

    const plan = await planRecallInstall(layout, runtime());
    await applyRecallInstall(plan);
    await verifyRecallInstall(layout);

    // Codex reads ~/.codex/skills/<name>/SKILL.md like Cursor and Claude Code
    // do, so it gets the guidance file and not just the bare tool.
    expect(layout.skillPath).not.toBeNull();
    expect(plan.actions).toEqual(["create-mcp", "create-skill"]);
    const installed = await readFile(configPath, "utf8");
    expect(installed).toContain("[mcp_servers.one-memory]");
    expect(installed).toContain('ONE_MEMORY_MANAGED_BY = "one-memory"');
    expect(await readFile(String(layout.skillPath), "utf8")).toContain(
      "MemHub_recall",
    );

    await rollbackRecallInstall(layout);
    await expect(readFile(configPath, "utf8")).rejects.toThrow();
  });

  it("refuses a foreign same-named server unless takeover is asked for", async () => {
    const { layout, configPath } = await fixture();
    await writeFile(configPath, OCCUPIED);

    await expect(planRecallInstall(layout, runtime())).rejects.toThrow(
      /Codex already has an unmanaged MCP server named "one-memory"/,
    );
    // The refusal must not have touched the file.
    expect(await readFile(configPath, "utf8")).toBe(OCCUPIED);
  });

  it("takes over a foreign entry and restores it verbatim on rollback", async () => {
    const { layout, configPath } = await fixture();
    await writeFile(configPath, OCCUPIED);

    const plan = await planRecallInstall(layout, runtime(), {
      takeover: true,
    });
    expect(plan.actions).toContain("takeover-mcp");
    await applyRecallInstall(plan);
    await verifyRecallInstall(layout);

    const installed = await readFile(configPath, "utf8");
    expect(installed).not.toContain("one-memory-tutti");
    // The comment described the displaced entry, so it leaves with it rather
    // than staying behind to mislabel ours.
    expect(installed).not.toContain("Tutti");
    // Everything we do not own survives untouched.
    expect(installed).toContain('personality = "pragmatic"');
    expect(installed).toContain("screenpipe-mcp@latest");
    expect(installed).toContain("[features]");

    await rollbackRecallInstall(layout);

    // Taking over another tool's entry has to be fully reversible, comments
    // and position included, or it is data loss with extra steps.
    expect(await readFile(configPath, "utf8")).toBe(OCCUPIED);
  });

  it("keeps the displaced entry recoverable across a reinstall", async () => {
    const { layout, configPath } = await fixture();
    await writeFile(configPath, OCCUPIED);
    await applyRecallInstall(
      await planRecallInstall(layout, runtime(), { takeover: true }),
    );

    // A second install sees our own managed entry, not the foreign one. If it
    // recorded that as the state to restore, the only surviving copy of the
    // displaced entry would be gone and the takeover would become permanent.
    await applyRecallInstall(await planRecallInstall(layout, runtime()));
    await rollbackRecallInstall(layout);

    expect(await readFile(configPath, "utf8")).toBe(OCCUPIED);
  });

  it("refuses rollback after the installed entry was edited by hand", async () => {
    const { layout, configPath } = await fixture();
    await writeFile(configPath, OCCUPIED);
    await applyRecallInstall(
      await planRecallInstall(layout, runtime(), { takeover: true }),
    );

    const edited = (await readFile(configPath, "utf8")).replace(
      'ELECTRON_RUN_AS_NODE = "1"',
      'ELECTRON_RUN_AS_NODE = "0"',
    );
    await writeFile(configPath, edited);

    await expect(rollbackRecallInstall(layout)).rejects.toThrow(
      /changed after installation/,
    );
    await expect(verifyRecallInstall(layout)).rejects.toThrow();
  });

  it("leaves a malformed config alone instead of overwriting it", async () => {
    const { layout, configPath } = await fixture();
    // A half-written table: our reader must not treat this as "no server".
    const broken = "[mcp_servers.one-memory]\ncommand =\n";
    await writeFile(configPath, broken);

    await expect(planRecallInstall(layout, runtime())).rejects.toThrow(
      /unmanaged MCP server/,
    );
    expect(await readFile(configPath, "utf8")).toBe(broken);
  });
});

async function fixture() {
  const home = await mkdtemp(path.join(os.tmpdir(), "om-codex-"));
  const codexDir = path.join(home, ".codex");
  await mkdir(codexDir, { recursive: true });
  const layout = codexLayout(codexDir);
  return { layout, configPath: mcpConfigPath(layout) };
}

function runtime() {
  return {
    runtimeCommand: "/Applications/MemHub.app/Contents/MacOS/MemHub",
    mcpEntryPath: "/Applications/MemHub.app/Contents/Resources/mcp.cjs",
    discoveryPath: "/Users/someone/.one-memory/integrations/broker.json",
  };
}
