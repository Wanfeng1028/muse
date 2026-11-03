import { mkdir, mkdtemp, readdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  applyRecallInstall,
  mcpConfigPath,
  planRecallInstall,
  rollbackRecallInstall,
  verifyRecallInstall,
  workbuddyScatteredLayout,
} from "./recall-installer.js";

/** The shape recall used to be installed into WorkBuddy in.
 *
 * Nothing installs it any more — `workbuddyLayout` is a plugin now — but these
 * stay because machines carry this shape and the plugin install has to be able
 * to take it down. Installing it is how a test can produce one to migrate.
 */
describe("WorkBuddy scattered recall installer", () => {
  it("installs the Skill and the MCP entry", async () => {
    const { layout, configPath } = await fixture();

    const plan = await planRecallInstall(layout, runtime());
    await applyRecallInstall(plan);
    await verifyRecallInstall(layout);

    expect(plan.actions).toEqual(["create-mcp", "create-skill"]);
    expect(await readFile(String(layout.skillPath), "utf8")).toContain(
      "MemHub_recall",
    );
    const installed = JSON.parse(await readFile(configPath, "utf8"));
    expect(installed.mcpServers["one-memory"]).toBeDefined();
  });

  it("merges into the user file and leaves connector files alone", async () => {
    const { layout, workbuddyDir, configPath } = await fixture();
    // A real machine has both: an empty user-level mcp.json, and per-connector
    // files whose entries are marketplace-managed and prefixed `connector:`.
    await writeFile(configPath, JSON.stringify({ mcpServers: {} }));
    const connectorPath = path.join(
      workbuddyDir,
      "connectors",
      "default",
      "mcp.json",
    );
    await mkdir(path.dirname(connectorPath), { recursive: true });
    const connector = JSON.stringify({
      mcpServers: {
        "connector:tdx-connector": {
          url: "https://example.invalid",
          disabled: true,
        },
      },
    });
    await writeFile(connectorPath, connector);

    await applyRecallInstall(await planRecallInstall(layout, runtime()));

    expect(
      JSON.parse(await readFile(configPath, "utf8")).mcpServers["one-memory"],
    ).toBeDefined();
    // Writing into a connector's file would put our entry in a namespace the
    // marketplace rewrites, so the install would vanish on the next sync.
    expect(await readFile(connectorPath, "utf8")).toBe(connector);
  });

  it("leaves no empty skill directory behind after uninstall", async () => {
    const { layout, workbuddyDir } = await fixture();
    const skills = path.join(workbuddyDir, "skills");
    await mkdir(skills, { recursive: true });
    // A neighbouring skill the user installed: it must survive untouched.
    await mkdir(path.join(skills, "their-skill"), { recursive: true });
    await writeFile(path.join(skills, "their-skill", "SKILL.md"), "theirs\n");

    await applyRecallInstall(await planRecallInstall(layout, runtime()));
    await rollbackRecallInstall(layout);

    // Hosts enumerate skills/*/SKILL.md, so an empty directory of ours reads
    // as a skill that failed to load.
    expect(await readdir(skills)).toEqual(["their-skill"]);
  });

  it("leaves an empty server map exactly as it found it", async () => {
    const { layout, configPath } = await fixture();
    // This is the real shape on this machine: WorkBuddy ships mcp.json with an
    // empty mcpServers object. Uninstalling has to give that back rather than
    // a synthesised `{}`, which would drop a key we never owned.
    const original = { mcpServers: {} };
    await writeFile(configPath, JSON.stringify(original, null, 2));

    await applyRecallInstall(await planRecallInstall(layout, runtime()));
    await rollbackRecallInstall(layout);

    expect(JSON.parse(await readFile(configPath, "utf8"))).toEqual(original);
  });

  it("restores a config already in our own formatting unchanged", async () => {
    const { layout, configPath } = await fixture();
    const original = `${JSON.stringify(
      {
        mcpServers: { "connector:keep-me": { url: "https://example.invalid" } },
      },
      null,
      2,
    )}\n`;
    await writeFile(configPath, original);

    await applyRecallInstall(await planRecallInstall(layout, runtime()));
    await rollbackRecallInstall(layout);

    expect(await readFile(configPath, "utf8")).toBe(original);
  });
});

async function fixture() {
  const workbuddyDir = await mkdtemp(path.join(os.tmpdir(), "om-workbuddy-"));
  const layout = workbuddyScatteredLayout(workbuddyDir);
  return { layout, workbuddyDir, configPath: mcpConfigPath(layout) };
}

function runtime() {
  return {
    runtimeCommand: "/opt/one-memory/bin/one-memory",
    mcpEntryPath: "/opt/one-memory/mcp/entry.mjs",
    discoveryPath: "/opt/one-memory/runtime.json",
  };
}
