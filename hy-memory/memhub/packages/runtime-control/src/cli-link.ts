import { access, lstat, mkdir, readlink, rm, symlink } from "node:fs/promises";
import path from "node:path";

export interface CliLinkPlan {
  schema_version: 1;
  platform: NodeJS.Platform;
  home: string;
  install_root: string;
  bin_directory: string;
  status: "create" | "present" | "blocked";
  blocked_reason: string | null;
  link_path: string;
  target_path: string;
  compat_link_path?: string;
  compat_target_path?: string;
}

export interface CliLinkReceipt extends CliLinkPlan {
  created: boolean;
  compat_created?: boolean;
}

export async function planCliLink(options: {
  home: string;
  installRoot: string;
  binDirectory?: string;
  platform?: NodeJS.Platform;
  includeCompatibilityAlias?: boolean;
}): Promise<CliLinkPlan> {
  const platform = options.platform ?? process.platform;
  const paths = platform === "win32" ? path.win32 : path.posix;
  const home = paths.resolve(options.home);
  const installRoot = paths.resolve(options.installRoot);
  const binDirectory = paths.resolve(
    options.binDirectory ?? paths.join(home, ".local", "bin"),
  );
  const executableName = platform === "win32" ? "one-memory.cmd" : "one-memory";
  const linkPath = paths.join(
    binDirectory,
    platform === "win32" ? "memhub.cmd" : "memhub",
  );
  const targetPath = paths.join(installRoot, "current", "bin", executableName);
  const compatLinkPath =
    options.includeCompatibilityAlias === false
      ? undefined
      : paths.join(binDirectory, executableName);
  const compatTargetPath =
    compatLinkPath === undefined ? undefined : targetPath;
  if (platform === "win32") {
    return blocked(
      platform,
      home,
      installRoot,
      binDirectory,
      linkPath,
      targetPath,
      compatLinkPath,
      compatTargetPath,
      "windows_path_install_not_verified",
    );
  }
  const primary = await inspect(linkPath, targetPath);
  const compat =
    compatLinkPath === undefined || compatTargetPath === undefined
      ? "present"
      : await inspect(compatLinkPath, compatTargetPath);
  if (primary === "unmanaged" || compat === "unmanaged") {
    return blocked(
      platform,
      home,
      installRoot,
      binDirectory,
      linkPath,
      targetPath,
      compatLinkPath,
      compatTargetPath,
      "cli_link_unmanaged",
    );
  }
  if (primary === "present" && compat === "present") {
    return ready(
      "present",
      platform,
      home,
      installRoot,
      binDirectory,
      linkPath,
      targetPath,
      compatLinkPath,
      compatTargetPath,
    );
  }
  return ready(
    "create",
    platform,
    home,
    installRoot,
    binDirectory,
    linkPath,
    targetPath,
    compatLinkPath,
    compatTargetPath,
  );
}

export async function installCliLink(
  plan: CliLinkPlan,
): Promise<CliLinkReceipt> {
  return installCliLinkInternal(plan);
}

/** Internal safety harness for the future managed release implementation. */
export async function installCliLinkInternal(
  plan: CliLinkPlan,
): Promise<CliLinkReceipt> {
  if (plan.status === "blocked") {
    throw new Error(plan.blocked_reason ?? "cli_link_blocked");
  }
  const refreshed = await planCliLink({
    home: plan.home,
    installRoot: plan.install_root,
    binDirectory: plan.bin_directory,
    platform: plan.platform,
    includeCompatibilityAlias: plan.compat_link_path !== undefined,
  });
  if (
    refreshed.link_path !== plan.link_path ||
    refreshed.target_path !== plan.target_path ||
    refreshed.compat_link_path !== plan.compat_link_path ||
    refreshed.compat_target_path !== plan.compat_target_path ||
    refreshed.status !== plan.status
  ) {
    throw new Error("cli_link_plan_stale");
  }
  if (plan.status === "present") {
    return { ...plan, created: false, compat_created: false };
  }
  await access(plan.target_path).catch(() => {
    throw new Error("cli_link_target_missing");
  });
  const existed = await lstat(plan.bin_directory).catch(() => null);
  await mkdir(plan.bin_directory, { recursive: true, mode: 0o700 });
  if (!existed)
    await (await import("node:fs/promises")).chmod(plan.bin_directory, 0o700);
  const directory = await lstat(plan.bin_directory);
  if (
    !directory.isDirectory() ||
    directory.isSymbolicLink() ||
    (directory.mode & 0o022) !== 0 ||
    (typeof process.getuid === "function" && directory.uid !== process.getuid())
  ) {
    throw new Error("cli_link_directory_unsafe");
  }
  let created = false;
  let compatCreated = false;
  try {
    const primary = await inspect(plan.link_path, plan.target_path);
    if (primary === "missing") {
      await symlink(plan.target_path, plan.link_path, "file");
      created = true;
    }
    if (plan.compat_link_path && plan.compat_target_path) {
      const compat = await inspect(
        plan.compat_link_path,
        plan.compat_target_path,
      );
      if (compat === "missing") {
        await symlink(plan.compat_target_path, plan.compat_link_path, "file");
        compatCreated = true;
      }
    }
  } catch (error) {
    if (created) await rm(plan.link_path, { force: true });
    if (compatCreated && plan.compat_link_path)
      await rm(plan.compat_link_path, { force: true });
    throw error;
  }
  return { ...plan, created, compat_created: compatCreated };
}

export async function rollbackCliLink(receipt: CliLinkReceipt): Promise<void> {
  if (receipt.created)
    await removeOwnedLink(receipt.link_path, receipt.target_path);
  if (
    receipt.compat_created &&
    receipt.compat_link_path &&
    receipt.compat_target_path
  ) {
    await removeOwnedLink(receipt.compat_link_path, receipt.compat_target_path);
  }
}

async function inspect(
  linkPath: string,
  targetPath: string,
): Promise<"missing" | "present" | "unmanaged"> {
  const current = await lstat(linkPath).catch(() => null);
  if (!current) return "missing";
  if (!current.isSymbolicLink()) return "unmanaged";
  const actual = path.resolve(path.dirname(linkPath), await readlink(linkPath));
  return actual === targetPath ? "present" : "unmanaged";
}

async function removeOwnedLink(
  linkPath: string,
  targetPath: string,
): Promise<void> {
  const info = await lstat(linkPath).catch(() => null);
  if (!info?.isSymbolicLink()) return;
  const target = path.resolve(path.dirname(linkPath), await readlink(linkPath));
  if (target === targetPath) await rm(linkPath);
}

function ready(
  status: "create" | "present",
  platform: NodeJS.Platform,
  home: string,
  installRoot: string,
  binDirectory: string,
  linkPath: string,
  targetPath: string,
  compatLinkPath?: string,
  compatTargetPath?: string,
): CliLinkPlan {
  return {
    schema_version: 1,
    platform,
    home,
    install_root: installRoot,
    bin_directory: binDirectory,
    status,
    blocked_reason: null,
    link_path: linkPath,
    target_path: targetPath,
    compat_link_path: compatLinkPath,
    compat_target_path: compatTargetPath,
  };
}

function blocked(
  platform: NodeJS.Platform,
  home: string,
  installRoot: string,
  binDirectory: string,
  linkPath: string,
  targetPath: string,
  compatLinkPath: string | undefined,
  compatTargetPath: string | undefined,
  reason: string,
): CliLinkPlan {
  return {
    schema_version: 1,
    platform,
    home,
    install_root: installRoot,
    bin_directory: binDirectory,
    status: "blocked",
    blocked_reason: reason,
    link_path: linkPath,
    target_path: targetPath,
    compat_link_path: compatLinkPath,
    compat_target_path: compatTargetPath,
  };
}
