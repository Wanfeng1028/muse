/** Keep the managed bin directory on the user's PATH.
 *
 * The product requirement is "装完即短指令可用": after `memhub install` the
 * user must be able to type `memhub ...` without exporting anything. The
 * installer already creates the `memhub`/`one-memory` links in `binDir`; this
 * module makes `binDir` reachable from a NEW shell.
 *
 * Design rules, deliberately conservative:
 *   - Only a marked, single block is ever written. We never rewrite or reorder
 *     the user's existing profile content.
 *   - Idempotent: re-running installs the same block once.
 *   - Removable: uninstall removes exactly the block we wrote, and only if it
 *     still matches byte-for-byte.
 *   - A profile that already puts binDir on PATH is left completely alone.
 *   - Reject path escapes: binDir must be absolute and newline-free, and the
 *     profile must live in the user's home.
 */

import { mkdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const BEGIN = "# >>> memhub PATH >>>";
const END = "# <<< memhub PATH <<<";

export interface ShellPathPlan {
  schema_version: 1;
  status: "present" | "create" | "blocked";
  blocked_reason: string | null;
  bin_directory: string;
  profile_path: string;
  /** The exact block this tool owns, or null when there is nothing to write. */
  block: string | null;
  /** True when the caller explicitly opted out of profile edits. Recorded so
   * apply can re-verify the same plan instead of re-planning into a write. */
  disabled?: boolean;
}

export interface ShellPathReceipt extends ShellPathPlan {
  created: boolean;
}

/** The profile a login shell on this platform will read for `PATH`.
 *
 * macOS defaults to zsh, so `~/.zprofile` is the login-shell file; Linux (and
 * unknown POSIX) use `~/.profile`, which is the portable choice. Windows has no
 * POSIX profile and stays blocked until a real PATH story is verified.
 */
function defaultProfilePath(
  platform: NodeJS.Platform,
  home: string,
): string | null {
  if (platform === "darwin") return path.join(home, ".zprofile");
  if (platform === "linux") return path.join(home, ".profile");
  return null;
}

function blockFor(binDirectory: string): string {
  return [
    BEGIN,
    `# Added by memhub install. Remove with: memhub uninstall --yes`,
    `case ":$PATH:" in`,
    `  *":${binDirectory}:"*) ;;`,
    `  *) PATH="${binDirectory}:$PATH" ;;`,
    `esac`,
    `export PATH`,
    END,
    "",
  ].join("\n");
}

/** The block plus the separator that positions it, so removing it restores the
 * original file byte-for-byte regardless of the original's trailing newline. */
function ownedBlock(existing: string | null, binDirectory: string): string {
  const separator =
    existing === null || existing === "" || existing.endsWith("\n") ? "" : "\n";
  return `${separator}${blockFor(binDirectory)}`;
}

export async function planShellPath(options: {
  binDirectory: string;
  home: string;
  platform?: NodeJS.Platform;
  profilePath?: string;
  /** Opt out of profile edits entirely (isolated installs, CI, scripted
   * installs that manage PATH themselves). Reported as `present` with no block
   * so no caller is tempted to write one later. */
  disabled?: boolean;
}): Promise<ShellPathPlan> {
  const platform = options.platform ?? process.platform;
  const paths = platform === "win32" ? path.win32 : path.posix;
  const binDirectory = options.binDirectory;
  const profilePath =
    options.profilePath ?? defaultProfilePath(platform, options.home);
  if (options.disabled === true) {
    return {
      schema_version: 1,
      status: "present",
      blocked_reason: null,
      bin_directory: binDirectory,
      profile_path: profilePath ?? "",
      block: null,
      disabled: true,
    };
  }
  const blocked = (reason: string, target: string): ShellPathPlan => ({
    schema_version: 1,
    status: "blocked",
    blocked_reason: reason,
    bin_directory: target,
    profile_path: profilePath ?? "",
    block: null,
  });
  if (
    !paths.isAbsolute(binDirectory) ||
    binDirectory.includes("\0") ||
    /[\r\n]/.test(binDirectory)
  ) {
    return blocked("bin_directory_unusable", binDirectory);
  }
  if (profilePath === null) {
    return blocked("shell_path_not_verified", binDirectory);
  }
  const home = paths.resolve(options.home);
  const resolvedProfile = paths.resolve(profilePath);
  // Never write outside the user's own profile directory.
  if (paths.dirname(resolvedProfile) !== home) {
    return blocked("profile_outside_home", binDirectory);
  }
  const existing = await readProfile(resolvedProfile);
  const block = ownedBlock(existing, binDirectory);
  if (existing === null) {
    return {
      schema_version: 1,
      status: "create",
      blocked_reason: null,
      bin_directory: binDirectory,
      profile_path: resolvedProfile,
      block,
    };
  }
  if (existing.includes(block)) {
    return {
      schema_version: 1,
      status: "present",
      blocked_reason: null,
      bin_directory: binDirectory,
      profile_path: resolvedProfile,
      block,
    };
  }
  // A different-but-equivalent membership already exists (user manages PATH).
  if (profileExportsDirectory(existing, binDirectory)) {
    return {
      schema_version: 1,
      status: "present",
      blocked_reason: null,
      bin_directory: binDirectory,
      profile_path: resolvedProfile,
      block: null,
    };
  }
  return {
    schema_version: 1,
    status: "create",
    blocked_reason: null,
    bin_directory: binDirectory,
    profile_path: resolvedProfile,
    block,
  };
}

export async function applyShellPath(
  plan: ShellPathPlan,
): Promise<ShellPathReceipt> {
  if (plan.status === "blocked") {
    throw new Error(plan.blocked_reason ?? "shell_path_blocked");
  }
  const refreshed = await planShellPath({
    binDirectory: plan.bin_directory,
    home: path.dirname(plan.profile_path),
    profilePath: plan.profile_path,
    ...(plan.disabled ? { disabled: true } : {}),
  });
  if (refreshed.status !== plan.status || refreshed.block !== plan.block) {
    throw new Error("shell_path_plan_stale");
  }
  if (plan.status === "present") {
    return { ...plan, created: false };
  }
  const existing = (await readProfile(plan.profile_path)) ?? "";
  const block = plan.block ?? ownedBlock(existing, plan.bin_directory);
  await writeProfileAtomically(plan.profile_path, `${existing}${block}`);
  return { ...plan, created: true };
}

export async function removeShellPath(
  plan: ShellPathPlan,
): Promise<"removed" | "not-present"> {
  const existing = await readProfile(plan.profile_path);
  if (existing === null) return "not-present";
  const marker = plan.block ?? ownedBlock(existing, plan.bin_directory);
  const index = existing.indexOf(marker);
  if (index === -1) return "not-present";
  const before = existing.slice(0, index);
  const after = existing.slice(index + marker.length);
  await writeProfileAtomically(plan.profile_path, `${before}${after}`);
  return "removed";
}

async function readProfile(profilePath: string): Promise<string | null> {
  try {
    const info = await stat(profilePath);
    if (!info.isFile()) return null;
    return await readFile(profilePath, "utf8");
  } catch {
    return null;
  }
}

async function writeProfileAtomically(
  profilePath: string,
  content: string,
): Promise<void> {
  // A fresh `--home` may not exist yet; create it (owner-only) before writing
  // the temp profile, otherwise the write fails with a raw ENOENT. Surface a
  // structured code for any other failure.
  await mkdir(path.dirname(profilePath), {
    recursive: true,
    mode: 0o700,
  }).catch(() => {
    throw new Error("shell_path_home_unwritable");
  });
  const temporary = `${profilePath}.memhub.${process.pid}.tmp`;
  try {
    await writeFile(temporary, content, { encoding: "utf8", mode: 0o644 });
    await rename(temporary, profilePath);
  } catch (error) {
    await rm(temporary, { force: true });
    throw error;
  }
}

/** True when the profile already exports `directory` on PATH in some form. */
function profileExportsDirectory(content: string, directory: string): boolean {
  for (const raw of content.split("\n")) {
    const line = raw.trim();
    if (line === "" || line.startsWith("#")) continue;
    if (!/\bPATH\b/.test(line) && !/\bpath\b/.test(line)) continue;
    // Tokens are split on the separators that can appear inside a PATH
    // assignment; the directory counts only as a whole `:`-delimited element,
    // so `/x/bin-extra` never matches `/x/bin`.
    const tokens = line.split(/[:\s="']+/);
    if (tokens.includes(directory)) return true;
  }
  return false;
}

export function renderShellPathPlan(plan: ShellPathPlan): string {
  if (plan.status === "blocked") {
    return `PATH 未配置：${plan.blocked_reason}\n`;
  }
  if (plan.status === "present") {
    return `PATH 已包含 ${plan.bin_directory}（${plan.profile_path}）\n`;
  }
  return `将在 ${plan.profile_path} 添加 PATH 条目：${plan.bin_directory}\n`;
}
