import { lstat, readFile, readlink } from "node:fs/promises";
import path from "node:path";

import {
  type LocalUninstallPlan,
  type LocalUninstallReceipt,
  planLocalUninstall,
} from "../../local-install.js";

export type WindowsUninstallPlan = LocalUninstallPlan;
export type WindowsUninstallReceipt = LocalUninstallReceipt;

/**
 * Windows cannot execute this transaction yet, but planning must be able to
 * name what would be removed and what must stay. On a real machine the data
 * directory, Credential Manager entries, and SID/DACL-secured files are
 * preserved unless the user explicitly asks for a data-destroying operation.
 */
export async function planWindowsUninstall(options: {
  installRoot: string;
  home: string;
  dataDir: string | null;
  cliLinkPath: string | null;
  stopsService: boolean;
}): Promise<WindowsUninstallPlan> {
  const basePlan = await planLocalUninstall(options);
  if (basePlan.cli_link) {
    await assertManagedWindowsCliLink(basePlan.cli_link, basePlan.install_root);
  }
  return basePlan;
}

async function assertManagedWindowsCliLink(
  cliLinkPath: string,
  installRoot: string,
): Promise<void> {
  const info = await lstat(cliLinkPath).catch(() => null);
  if (info === null) return;
  if (info.isSymbolicLink()) {
    const target = await readlink(cliLinkPath);
    const resolved = path.win32.resolve(
      path.win32.dirname(cliLinkPath),
      target,
    );
    const expected = path.win32.join(
      installRoot,
      "current",
      "bin",
      "one-memory.cmd",
    );
    if (resolved.toLowerCase() !== expected.toLowerCase()) {
      throw new Error("windows_cli_link_unmanaged");
    }
    return;
  }
  if (!info.isFile()) throw new Error("windows_cli_link_unmanaged");
  const actual = await readFile(cliLinkPath, "utf8");
  if (!actual.includes("one-memory.cjs")) {
    throw new Error("windows_cli_link_unmanaged");
  }
}
