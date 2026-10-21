/** Skill-only hosts: no MCP config file exists to edit.
 *
 * Pi was the first such host. These tests deliberately do not call `piLayout`,
 * so the installer cannot claim the capability only for one named product.
 */

import {
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  applyRecallInstall,
  applyRecallUninstall,
  planRecallInstall,
  planRecallUninstall,
  type RecallHostLayout,
  type RecallRuntime,
  rollbackRecallInstall,
  verifyRecallInstall,
} from "./recall-installer.js";

/** A generic skill-only layout — the shape A-2 requires of the installer. */
function skillOnlyLayout(hostDir: string): RecallHostLayout {
  const root = path.resolve(hostDir);
  return {
    hostId: "skill-only-fixture",
    hostLabel: "Skill-Only Fixture",
    configPath: null,
    format: "none",
    channel: "cli",
    skillPath: path.join(root, "skills", "one-memory-recall", "SKILL.md"),
    journalPath: path.join(root, ".one-memory", "recall-install.json"),
    containmentRoot: root,
  };
}

let root: string;
let layout: RecallHostLayout;
let runtime: RecallRuntime;

beforeEach(async () => {
  root = await mkdtemp(path.join(tmpdir(), "one-memory-skill-only-"));
  await mkdir(path.join(root, "skills"), { recursive: true });
  layout = skillOnlyLayout(root);
  runtime = {
    runtimeCommand: path.join(root, "MemHub.app", "MacOS", "MemHub"),
    mcpEntryPath: path.join(root, "bridge", "mcp.cjs"),
    discoveryPath: path.join(root, "discovery.json"),
    recallCliPath: path.join(root, "bridge", "recall-cli.cjs"),
  };
});

afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

async function listRelativeFiles(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true, recursive: true });
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => path.relative(dir, path.join(entry.parentPath, entry.name)))
    .sort();
}

describe("installer support for skill-only hosts (A-2)", () => {
  it("plans and applies without inventing an MCP config file", async () => {
    const plan = await planRecallInstall(layout, runtime);
    expect(plan.paths.mcp).toBeNull();
    expect(plan.next.server).toBeNull();
    expect(plan.actions).toEqual(["create-skill"]);

    await applyRecallInstall(plan);

    const files = await listRelativeFiles(root);
    expect(files).toContain("skills/one-memory-recall/SKILL.md");
    expect(files).toContain(".one-memory/recall-install.json");
    expect(files.every((file) => !file.includes("mcp"))).toBe(true);
    await expect(stat(path.join(root, "mcp.json"))).rejects.toThrow();
  });

  it("writes a CLI skill that names the command, not om_recall", async () => {
    await applyRecallInstall(await planRecallInstall(layout, runtime));
    const skill = await readFile(layout.skillPath as string, "utf8");
    expect(skill).not.toContain("om_recall");
    expect(skill).toContain(runtime.recallCliPath as string);
    expect(skill).toContain('--workspace-path "$PWD"');
  });

  it("verifies, rolls back, and uninstalls without touching an MCP path", async () => {
    const plan = await planRecallInstall(layout, runtime);
    await applyRecallInstall(plan);
    await expect(verifyRecallInstall(layout)).resolves.toMatchObject({
      hostId: "skill-only-fixture",
      discoveryPath: runtime.discoveryPath,
    });

    await rollbackRecallInstall(layout);
    await expect(stat(layout.skillPath as string)).rejects.toThrow();

    await applyRecallInstall(await planRecallInstall(layout, runtime));
    const uninstall = await planRecallUninstall(layout);
    await applyRecallUninstall(uninstall);
    await expect(stat(layout.skillPath as string)).rejects.toThrow();
    expect(
      await listRelativeFiles(root).then((files) =>
        files.filter((file) => file.toLowerCase().includes("mcp")),
      ),
    ).toEqual([]);
  });

  it("refuses a skill-only layout that still claims the mcp channel", async () => {
    await expect(
      planRecallInstall({ ...layout, channel: "mcp" }, runtime),
    ).rejects.toThrow(/channel cannot be "mcp"/);
  });

  it("refuses to overwrite a skill it does not own", async () => {
    await mkdir(path.dirname(layout.skillPath as string), { recursive: true });
    await writeFile(layout.skillPath as string, "# hand-written\n");
    await expect(planRecallInstall(layout, runtime)).rejects.toThrow(
      /unmanaged/i,
    );
    expect(await readFile(layout.skillPath as string, "utf8")).toBe(
      "# hand-written\n",
    );
  });
});
