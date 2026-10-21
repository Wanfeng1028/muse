import {
  chmod,
  lstat,
  mkdir,
  mkdtemp,
  symlink,
  unlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

import {
  applyLinuxUninstall,
  buildLinuxUninstallPlan,
  verifyLinuxUninstallPlan,
} from "./linux-uninstall.js";

async function home() {
  return mkdtemp(path.join(tmpdir(), "linux-uninstall-"));
}

const HOME = home();
const INSTALL_ROOT = HOME.then((value) => path.join(value, "install"));
const DATA_DIR = HOME.then((value) => path.join(value, "One Memory Data"));
const UNIT_PATH = HOME.then((value) =>
  path.join(value, "systemd/user/one-memory.service"),
);
const UNIT_CONTENT = "[Service]\nExecStart=old\n";
const CLI_LINK = HOME.then((value) => path.join(value, "bin/one-memory"));

async function fixture() {
  const homeDir = await HOME;
  await mkdir(path.join(await INSTALL_ROOT, "versions/0.0.0-linux-arm64/bin"), {
    recursive: true,
  });
  await writeFile(
    path.join(await INSTALL_ROOT, "versions/0.0.0-linux-arm64/bin/one-memory"),
    "program",
  );
  await mkdir(path.join(await INSTALL_ROOT, "unknown"), { recursive: true });
  await writeFile(path.join(await INSTALL_ROOT, "unknown/stray"), "stray");
  await symlink(
    "versions/0.0.0-linux-arm64",
    path.join(await INSTALL_ROOT, "current"),
    "dir",
  );
  await mkdir(path.dirname(await UNIT_PATH), { recursive: true });
  await writeFile(await UNIT_PATH, UNIT_CONTENT);
  await chmod(await UNIT_PATH, 0o600);
  await mkdir(path.dirname(await CLI_LINK), { recursive: true });
  await symlink(
    path.join(await INSTALL_ROOT, "current/bin/one-memory"),
    await CLI_LINK,
    "file",
  );
  await mkdir(await DATA_DIR, { recursive: true });
  await writeFile(path.join(await DATA_DIR, "data"), "keep");
}

describe("Linux product uninstall", () => {
  beforeEach(fixture);

  it("keeps data, unknown files, and a modified unit", async () => {
    const plan = await buildLinuxUninstallPlan({
      installRoot: await INSTALL_ROOT,
      home: await HOME,
      dataDir: await DATA_DIR,
      cliLinkPath: await CLI_LINK,
      stopsService: true,
      unitPath: await UNIT_PATH,
      unitContent: "[Service]\nExecStart=old\n",
    });
    expect(plan.preserved_data_dir).toBe(await DATA_DIR);
    expect(plan.stops_service).toBe(true);
    const receipt = await applyLinuxUninstall(plan);
    expect(receipt.removed_version_directories).toHaveLength(1);
    await expect(
      lstat(path.join(await DATA_DIR, "data")),
    ).resolves.toBeTruthy();
    await expect(
      lstat(path.join(await INSTALL_ROOT, "unknown/stray")),
    ).resolves.toBeTruthy();
    await expect(lstat(await UNIT_PATH)).resolves.toBeTruthy();
    await expect(lstat(await CLI_LINK)).rejects.toThrow();
  });

  it("removes only the exact managed current, version, and CLI link", async () => {
    const plan = await buildLinuxUninstallPlan({
      installRoot: await INSTALL_ROOT,
      home: await HOME,
      dataDir: await DATA_DIR,
      cliLinkPath: await CLI_LINK,
      stopsService: true,
      unitPath: await UNIT_PATH,
      unitContent: UNIT_CONTENT,
    });
    await verifyLinuxUninstallPlan(plan);
    const receipt = await applyLinuxUninstall(plan);
    expect(receipt.removed_current_link).toBe(true);
    expect(receipt.removed_cli_link).toBe(true);
    await expect(lstat(await CLI_LINK)).rejects.toThrow();
    await expect(lstat(await UNIT_PATH)).resolves.toBeTruthy();
    await expect(
      lstat(path.join(await DATA_DIR, "data")),
    ).resolves.toBeTruthy();
    await expect(
      lstat(path.join(await INSTALL_ROOT, "unknown/stray")),
    ).resolves.toBeTruthy();
  });

  it("preserves a link that points outside the managed installation", async () => {
    const plan = await buildLinuxUninstallPlan({
      installRoot: await INSTALL_ROOT,
      home: await HOME,
      dataDir: await DATA_DIR,
      cliLinkPath: await CLI_LINK,
      stopsService: false,
      unitPath: await UNIT_PATH,
      unitContent: UNIT_CONTENT,
    });
    await unlink(await CLI_LINK);
    await symlink("/usr/bin/true", await CLI_LINK, "file");
    await expect(verifyLinuxUninstallPlan(plan)).rejects.toThrow(
      "linux_cli_link_unmanaged",
    );
  });
});
