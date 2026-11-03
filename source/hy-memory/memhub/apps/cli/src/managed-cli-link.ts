import {
  access,
  chmod,
  lstat,
  mkdir,
  readlink,
  rm,
  symlink,
} from "node:fs/promises";
import path from "node:path";

import type { CliLinkPlan, CliLinkReceipt } from "@one-memory/runtime-control";

export async function planManagedCliAlias(
  compatibility: CliLinkPlan,
): Promise<CliLinkPlan> {
  return planManagedCliLink(compatibility, "memhub");
}

/** Plan a managed link with an explicit name.
 *
 * `runtime-control/cli-link.ts` owns the managed link names. Since its
 * `01eedd8` it creates `<bin>/memhub` (primary) plus `<bin>/one-memory`
 * (compat) itself; before that it created only `<bin>/one-memory`. This
 * primitive lets the CLI stay correct on either shape without editing that
 * package: create `memhub` when the package does not, and remove the
 * `one-memory` compat the package's uninstall leaves behind when it does.
 */
export async function planManagedCliLink(
  compatibility: CliLinkPlan,
  name: string,
): Promise<CliLinkPlan> {
  const paths = compatibility.platform === "win32" ? path.win32 : path.posix;
  if (!/^[a-z0-9][a-z0-9._-]*$/i.test(name)) {
    return {
      ...compatibility,
      status: "blocked",
      blocked_reason: "cli_alias_name_invalid",
      link_path: paths.join(compatibility.bin_directory, name),
    };
  }
  const linkPath = paths.join(
    compatibility.bin_directory,
    compatibility.platform === "win32" ? `${name}.cmd` : name,
  );
  if (compatibility.platform === "win32") {
    return {
      ...compatibility,
      status: "blocked",
      blocked_reason: "windows_path_install_not_verified",
      link_path: linkPath,
    };
  }
  const current = await lstat(linkPath).catch(() => null);
  if (!current) {
    return {
      ...compatibility,
      status: "create",
      blocked_reason: null,
      link_path: linkPath,
    };
  }
  if (!current.isSymbolicLink()) {
    return {
      ...compatibility,
      status: "blocked",
      blocked_reason: "cli_alias_unmanaged",
      link_path: linkPath,
    };
  }
  const actual = paths.resolve(
    paths.dirname(linkPath),
    await readlink(linkPath),
  );
  if (actual !== compatibility.target_path) {
    return {
      ...compatibility,
      status: "blocked",
      blocked_reason: "cli_alias_unmanaged",
      link_path: linkPath,
    };
  }
  // The link names our managed target. It may be dangling (the install tree was
  // already torn down), which is exactly the state during uninstall, so report
  // `present`: attribution is by link *target*, not by whether that target still
  // exists. Callers that only need the link to work can check existence.
  return {
    ...compatibility,
    status: "present",
    blocked_reason: null,
    link_path: linkPath,
  };
}

export async function installManagedCliAlias(
  plan: CliLinkPlan,
): Promise<CliLinkReceipt> {
  return installManagedCliLink(plan);
}

export async function installManagedCliLink(
  plan: CliLinkPlan,
): Promise<CliLinkReceipt> {
  if (plan.status === "blocked") {
    throw new Error(plan.blocked_reason ?? "cli_alias_blocked");
  }
  const linkName = path.posix.basename(plan.link_path).replace(/\.cmd$/i, "");
  const refreshed = await planManagedCliLink(plan, linkName);
  if (
    refreshed.link_path !== plan.link_path ||
    refreshed.target_path !== plan.target_path ||
    refreshed.status !== plan.status
  ) {
    throw new Error("cli_alias_plan_stale");
  }
  if (plan.status === "present") return { ...plan, created: false };
  await access(plan.target_path).catch(() => {
    throw new Error("cli_alias_target_missing");
  });
  const existed = await lstat(plan.bin_directory).catch(() => null);
  await mkdir(plan.bin_directory, { recursive: true, mode: 0o700 });
  if (!existed) await chmod(plan.bin_directory, 0o700);
  await assertSafeDirectory(plan.bin_directory);
  await symlink(plan.target_path, plan.link_path, "file").catch(() => {
    throw new Error("cli_alias_plan_stale");
  });
  return { ...plan, created: true };
}

export async function rollbackManagedCliAlias(
  receipt: CliLinkReceipt,
): Promise<void> {
  return rollbackManagedCliLink(receipt);
}

export async function rollbackManagedCliLink(
  receipt: CliLinkReceipt,
): Promise<void> {
  if (!receipt.created) return;
  await removeExactAlias(receipt, false);
}

export async function removeManagedCliAlias(
  plan: CliLinkPlan,
): Promise<"removed" | "not-installed"> {
  return removeManagedCliLink(plan);
}

export async function removeManagedCliLink(
  plan: CliLinkPlan,
): Promise<"removed" | "not-installed"> {
  const linkName = path.posix.basename(plan.link_path).replace(/\.cmd$/i, "");
  const refreshed = await planManagedCliLink(plan, linkName);
  if (refreshed.status === "create") return "not-installed";
  // A dangling symlink is reported as `blocked` because the plan resolves the
  // link target. That is exactly the state after `applyLocalUninstall` removes
  // `current/` but not the compat link, so a link that still *names* our
  // managed target must be removed. A link pointing anywhere else stays a
  // refusal — the CLI never deletes an entry it cannot attribute to us.
  await removeExactAlias({ ...refreshed, created: true }, true);
  return "removed";
}

async function removeExactAlias(
  receipt: CliLinkReceipt,
  strict: boolean,
): Promise<void> {
  const info = await lstat(receipt.link_path).catch(() => null);
  if (!info) return;
  if (!info.isSymbolicLink()) {
    if (strict) throw new Error("cli_alias_unmanaged");
    return;
  }
  const paths = receipt.platform === "win32" ? path.win32 : path.posix;
  const target = paths.resolve(
    paths.dirname(receipt.link_path),
    await readlink(receipt.link_path),
  );
  if (target !== receipt.target_path) {
    if (strict) throw new Error("cli_alias_unmanaged");
    return;
  }
  await assertSafeDirectory(receipt.bin_directory);
  await rm(receipt.link_path);
}

async function assertSafeDirectory(directory: string): Promise<void> {
  const info = await lstat(directory);
  if (
    !info.isDirectory() ||
    info.isSymbolicLink() ||
    (info.mode & 0o022) !== 0 ||
    (process.getuid && info.uid !== process.getuid())
  ) {
    throw new Error("cli_alias_directory_unsafe");
  }
}
