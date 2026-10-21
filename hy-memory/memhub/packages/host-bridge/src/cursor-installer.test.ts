import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  applyCursorInstall,
  planCursorInstall,
  rollbackCursorInstall,
  verifyCursorInstall,
} from "./cursor-installer.js";
import { expectRestrictedFileMode } from "./expect-restricted-mode.js";

describe("Cursor recall installer", () => {
  it("merges without replacing existing MCP servers, verifies, and rolls back", async () => {
    const cursorDir = await fixtureDir();
    const mcpPath = path.join(cursorDir, "mcp.json");
    await writeFile(
      mcpPath,
      await readFile(
        path.join(process.cwd(), "fixtures", "cursor", "mcp.json"),
        "utf8",
      ),
    );
    const plan = await planCursorInstall(options(cursorDir));
    await applyCursorInstall(plan);
    await verifyCursorInstall(cursorDir);

    const installed = JSON.parse(await readFile(mcpPath, "utf8"));
    expect(installed.mcpServers["fixture-existing-server"]).toBeDefined();
    expect(installed.fixtureSetting).toBe("must-survive-one-memory-install");
    expect(installed.mcpServers["one-memory"].env).not.toHaveProperty(
      "ONE_MEMORY_API_TOKEN",
    );
    await expectRestrictedFileMode(
      path.join(cursorDir, ".one-memory", "recall-install.json"),
    );

    installed.mcpServers.addedAfterInstall = { command: "later" };
    await writeFile(mcpPath, `${JSON.stringify(installed, null, 2)}\n`);
    await rollbackCursorInstall(cursorDir);

    const rolledBack = JSON.parse(await readFile(mcpPath, "utf8"));
    expect(rolledBack.mcpServers["fixture-existing-server"]).toBeDefined();
    expect(rolledBack.mcpServers.addedAfterInstall).toBeDefined();
    expect(rolledBack.mcpServers["one-memory"]).toBeUndefined();
  });

  it("still uninstalls cleanly after being installed twice", async () => {
    const cursorDir = await fixtureDir();
    const mcpPath = path.join(cursorDir, "mcp.json");
    await writeFile(
      mcpPath,
      JSON.stringify({ mcpServers: { keepMe: { command: "theirs" } } }),
    );

    await applyCursorInstall(await planCursorInstall(options(cursorDir)));
    // Re-running install must not let us become our own "previous" entry,
    // or uninstall would restore us instead of removing us.
    await applyCursorInstall(await planCursorInstall(options(cursorDir)));
    await rollbackCursorInstall(cursorDir);

    const rolledBack = JSON.parse(await readFile(mcpPath, "utf8"));
    expect(rolledBack.mcpServers["one-memory"]).toBeUndefined();
    expect(rolledBack.mcpServers.keepMe).toBeDefined();
  });

  it("updates a managed one-memory server in place and does not add a memhub key", async () => {
    const cursorDir = await fixtureDir();
    const mcpPath = path.join(cursorDir, "mcp.json");
    await writeFile(
      mcpPath,
      JSON.stringify({
        mcpServers: {
          "one-memory": {
            command: "/old",
            args: ["/old/mcp.cjs"],
            env: {
              ELECTRON_RUN_AS_NODE: "1",
              ONE_MEMORY_MANAGED_BY: "one-memory",
            },
          },
          "someone-else": { command: "/somebody/else" },
        },
      }),
    );

    await applyCursorInstall(await planCursorInstall(options(cursorDir)));

    const installed = JSON.parse(await readFile(mcpPath, "utf8"));
    expect(installed.mcpServers.memhub).toBeUndefined();
    expect(installed.mcpServers["one-memory"].env.ONE_MEMORY_MANAGED_BY).toBe(
      "one-memory",
    );
    expect(installed.mcpServers["one-memory"].command).not.toBe("/old");
    expect(installed.mcpServers["someone-else"].command).toBe("/somebody/else");
  });

  it("refuses unmanaged name collisions without changing files", async () => {
    const cursorDir = await fixtureDir();
    const mcpPath = path.join(cursorDir, "mcp.json");
    const original = JSON.stringify({
      mcpServers: {
        "one-memory": { command: "/somebody/else" },
      },
    });
    await writeFile(mcpPath, original);

    await expect(planCursorInstall(options(cursorDir))).rejects.toThrow(
      "unmanaged MCP server",
    );
    expect(await readFile(mcpPath, "utf8")).toBe(original);
  });

  it("refuses apply when configuration changed after plan", async () => {
    const cursorDir = await fixtureDir();
    const mcpPath = path.join(cursorDir, "mcp.json");
    await writeFile(mcpPath, JSON.stringify({ mcpServers: {} }));
    const plan = await planCursorInstall(options(cursorDir));
    await writeFile(
      mcpPath,
      JSON.stringify({ mcpServers: { userAdded: { command: "new" } } }),
    );

    await expect(applyCursorInstall(plan)).rejects.toThrow(
      "changed after plan",
    );
  });

  it("refuses rollback when an installed owned file was edited", async () => {
    const cursorDir = await fixtureDir();
    const plan = await planCursorInstall(options(cursorDir));
    await applyCursorInstall(plan);
    await writeFile(
      path.join(cursorDir, "skills", "memhub-recall", "SKILL.md"),
      "<!-- one-memory-managed:v1 -->\nuser edit\n",
    );

    await expect(rollbackCursorInstall(cursorDir)).rejects.toThrow(
      "rollback refused",
    );
  });

  it("refuses to overwrite a Skill of the same name it does not own", async () => {
    const cursorDir = await fixtureDir();
    const skillPath = path.join(
      cursorDir,
      "skills",
      "memhub-recall",
      "SKILL.md",
    );
    await mkdir(path.dirname(skillPath), { recursive: true });
    // Same name, no managed marker: someone wrote their own recall Skill.
    const original = "---\nname: memhub-recall\n---\n\nmy own notes\n";
    await writeFile(skillPath, original);

    await expect(planCursorInstall(options(cursorDir))).rejects.toThrow(
      "unmanaged memhub-recall Skill",
    );
    expect(await readFile(skillPath, "utf8")).toBe(original);
  });

  it("refuses a journal written by a schema it does not understand", async () => {
    const cursorDir = await fixtureDir();
    await applyCursorInstall(await planCursorInstall(options(cursorDir)));
    const journalPath = path.join(
      cursorDir,
      ".one-memory",
      "recall-install.json",
    );
    const journal = JSON.parse(await readFile(journalPath, "utf8"));

    // A journal from a newer build may mean fields we would misread. Guessing
    // risks restoring the wrong thing over the user's real configuration.
    await writeFile(
      journalPath,
      JSON.stringify({ ...journal, schema_version: 2 }, null, 2),
    );

    await expect(rollbackCursorInstall(cursorDir)).rejects.toThrow(
      "journal is invalid",
    );
  });

  it("refuses to reinstall over an unreadable journal", async () => {
    const cursorDir = await fixtureDir();
    const mcpPath = path.join(cursorDir, "mcp.json");
    await writeFile(
      mcpPath,
      JSON.stringify({ mcpServers: { keepMe: { command: "theirs" } } }),
    );
    await applyCursorInstall(await planCursorInstall(options(cursorDir)));
    await writeFile(
      path.join(cursorDir, ".one-memory", "recall-install.json"),
      "{ truncated",
    );

    // The journal holds the only record of what the host looked like before
    // us. Treating a damaged one as "nothing to restore" would quietly make
    // the takeover permanent, so a reinstall has to stop here.
    await expect(planCursorInstall(options(cursorDir))).rejects.toThrow();
    expect(
      JSON.parse(await readFile(mcpPath, "utf8")).mcpServers.keepMe,
    ).toBeDefined();
  });
});

async function fixtureDir(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-cursor-fixture-"));
  const cursorDir = path.join(root, ".cursor");
  await mkdir(cursorDir);
  return cursorDir;
}

function options(cursorDir: string) {
  return {
    cursorDir,
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
