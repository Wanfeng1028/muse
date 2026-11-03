import { readlink } from "node:fs/promises";
import path from "node:path";

import {
  applyLocalUninstall,
  type LocalUninstallPlan,
  type LocalUninstallReceipt,
  planLocalUninstall,
} from "../../local-install.js";

export interface LinuxUninstallPlan extends LocalUninstallPlan {}
export type LinuxUninstallReceipt = LocalUninstallReceipt;

export async function buildLinuxUninstallPlan(options: {
  installRoot: string;
  home: string;
  dataDir: string | null;
  cliLinkPath: string | null;
  stopsService: boolean;
  unitPath?: string;
  unitContent?: string;
}): Promise<LinuxUninstallPlan> {
  if (
    options.stopsService &&
    options.unitPath &&
    options.unitContent !== undefined
  ) {
    const existing = await readlinkSafe(options.unitPath);
    if (existing === null) {
      const { readFile } = await import("node:fs/promises");
      const actual = await readFile(options.unitPath, "utf8");
      if (actual !== options.unitContent) {
        throw new Error("linux_service_file_modified");
      }
    } else {
      throw new Error("linux_service_file_unmanaged");
    }
  }
  const basePlan = await planLocalUninstall(options);
  return basePlan;
}

export async function verifyLinuxUninstallPlan(
  plan: LinuxUninstallPlan,
): Promise<void> {
  if (plan.cli_link) {
    const link = await readlinkSafe(plan.cli_link);
    if (link === null) {
      const { lstat, readFile } = await import("node:fs/promises");
      const info = await lstat(plan.cli_link);
      if (!info.isFile() || info.isSymbolicLink()) {
        throw new Error("linux_cli_link_unmanaged");
      }
      const actual = await readFile(plan.cli_link, "utf8");
      const expected = `#!/bin/sh\nexec "${plan.cli_link}"\n`;
      if (actual !== expected) throw new Error("linux_cli_link_unmanaged");
    } else {
      const target = path.resolve(path.dirname(plan.cli_link), link);
      const expected = path.join(
        plan.install_root,
        "current",
        "bin",
        "one-memory",
      );
      if (target !== expected) throw new Error("linux_cli_link_unmanaged");
    }
  }
}

export async function applyLinuxUninstall(
  plan: LinuxUninstallPlan,
): Promise<LinuxUninstallReceipt> {
  await verifyLinuxUninstallPlan(plan);
  return applyLocalUninstall(plan);
}

async function readlinkSafe(target: string): Promise<string | null> {
  try {
    return await readlink(target);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "EINVAL") return null;
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}
