import {
  mkdir,
  mkdtemp,
  readlink,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { planWindowsUninstall } from "./windows-uninstall.js";

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true, force: true })),
  );
});

async function fixture() {
  const root = await mkdtemp(path.join(tmpdir(), "om-windows-uninstall-"));
  roots.push(root);
  const installRoot = path.join(root, "One Memory");
  const versions = path.join(installRoot, "versions");
  const versionDirectory = path.join(versions, "1.0.0-win32-x64");
  const bin = path.join(versionDirectory, "bin");
  await mkdir(bin, { recursive: true });
  await writeFile(path.join(bin, "one-memory.cjs"), "cli");
  const dataDir = path.join(root, "data");
  await mkdir(dataDir, { recursive: true });
  return { root, installRoot, versions, versionDirectory, dataDir };
}

describe("Windows uninstall planning", () => {
  it("names only managed program paths and always preserves the data directory", async () => {
    const f = await fixture();
    const plan = await planWindowsUninstall({
      installRoot: f.installRoot,
      home: f.root,
      dataDir: f.dataDir,
      cliLinkPath: null,
      stopsService: true,
    });
    expect(plan.version_directories).toEqual([f.versionDirectory]);
    expect(plan.preserved_data_dir).toBe(f.dataDir);
    expect(plan.cli_link).toBeNull();
  });

  it("refuses to remove a CLI link that One Memory did not create", async () => {
    const f = await fixture();
    const binDir = path.join(f.root, "bin");
    await mkdir(binDir, { recursive: true });
    const cliLink = path.join(binDir, "one-memory.cmd");
    await writeFile(cliLink, "@echo off\r\nsomeone else\r\n");
    await expect(
      planWindowsUninstall({
        installRoot: f.installRoot,
        home: f.root,
        dataDir: f.dataDir,
        cliLinkPath: cliLink,
        stopsService: true,
      }),
    ).rejects.toThrow("windows_cli_link_unmanaged");
  });
});
