import { access, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  applyRecallInstall,
  cursorLayout,
  piLayout,
  planRecallInstall,
  type RecallHostLayout,
  rollbackRecallInstall,
  verifyRecallInstall,
} from "./recall-installer.js";

const runtime = {
  runtimeCommand: "/Applications/MemHub.app/Contents/MacOS/MemHub",
  mcpEntryPath:
    "/Applications/MemHub.app/Contents/Resources/host-bridge/mcp.cjs",
  recallCliPath:
    "/Applications/MemHub.app/Contents/Resources/host-bridge/recall.cjs",
  discoveryPath: "/tmp/om-skill-rename/cursor-broker.json",
};

describe("recall skill is named for MemHub", () => {
  it("installs under memhub-recall with a matching name", async () => {
    const dir = await cursorDir();
    await applyRecallInstall(
      await planRecallInstall(cursorLayout(dir), runtime),
    );

    const skill = await readFile(newSkill(dir), "utf8");
    expect(skill).toMatch(/^---\nname: memhub-recall\n/);
    expect(await exists(legacySkill(dir))).toBe(false);
  });

  it("moves a pre-rename install to the new directory on upgrade", async () => {
    const dir = await cursorDir();
    await installAtLegacyPath(cursorLayout(dir));
    expect(await exists(legacySkill(dir))).toBe(true);

    await applyRecallInstall(
      await planRecallInstall(cursorLayout(dir), runtime),
    );
    await verifyRecallInstall(cursorLayout(dir));

    expect(await exists(newSkill(dir))).toBe(true);
    expect(await exists(path.dirname(legacySkill(dir)))).toBe(false);

    await rollbackRecallInstall(cursorLayout(dir));
    expect(await exists(newSkill(dir))).toBe(false);
    const mcp = JSON.parse(await readFile(path.join(dir, "mcp.json"), "utf8"));
    expect(mcp.mcpServers["one-memory"]).toBeUndefined();
    expect(mcp.mcpServers.keepMe).toBeDefined();
  });

  it("still uninstalls a pre-rename install that was never upgraded", async () => {
    const dir = await cursorDir();
    await installAtLegacyPath(cursorLayout(dir));

    await rollbackRecallInstall(cursorLayout(dir));

    expect(await exists(legacySkill(dir))).toBe(false);
    const mcp = JSON.parse(await readFile(path.join(dir, "mcp.json"), "utf8"));
    expect(mcp.mcpServers["one-memory"]).toBeUndefined();
    expect(mcp.mcpServers.keepMe).toBeDefined();
  });

  it("keeps a pre-rename skill the user edited", async () => {
    const dir = await cursorDir();
    await installAtLegacyPath(cursorLayout(dir));
    const edited = `${await readFile(legacySkill(dir), "utf8")}\nmy own note\n`;
    await writeFile(legacySkill(dir), edited);

    await applyRecallInstall(
      await planRecallInstall(cursorLayout(dir), runtime),
    );

    expect(await readFile(legacySkill(dir), "utf8")).toBe(edited);
    expect(await exists(newSkill(dir))).toBe(true);
  });

  it("moves a skill-only host too, where the skill is the whole install", async () => {
    const dir = await hostDir(path.join(".pi", "agent"));
    await installAtLegacyPath(piLayout(dir));

    await applyRecallInstall(await planRecallInstall(piLayout(dir), runtime));
    expect(await exists(path.dirname(legacySkill(dir)))).toBe(false);

    await rollbackRecallInstall(piLayout(dir));
    expect(await exists(newSkill(dir))).toBe(false);
  });
});

/** What an install made before the rename left on disk. */
async function installAtLegacyPath(layout: RecallHostLayout): Promise<void> {
  const legacy: RecallHostLayout = {
    ...layout,
    skillPath: legacySkill(layout.containmentRoot),
    legacySkillPath: undefined,
  };
  await applyRecallInstall(await planRecallInstall(legacy, runtime));
}

function newSkill(dir: string): string {
  return path.join(dir, "skills", "memhub-recall", "SKILL.md");
}

function legacySkill(dir: string): string {
  return path.join(dir, "skills", "one-memory-recall", "SKILL.md");
}

async function cursorDir(): Promise<string> {
  const dir = await hostDir(".cursor");
  await writeFile(
    path.join(dir, "mcp.json"),
    JSON.stringify({ mcpServers: { keepMe: { command: "theirs" } } }),
  );
  return dir;
}

async function hostDir(name: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-skill-rename-"));
  const dir = path.join(root, name);
  await mkdir(dir, { recursive: true });
  return dir;
}

async function exists(target: string): Promise<boolean> {
  return access(target).then(
    () => true,
    () => false,
  );
}
