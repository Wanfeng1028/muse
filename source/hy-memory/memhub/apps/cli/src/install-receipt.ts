/** Managed installation receipt for the CLI's chosen data directory.
 *
 * `memhub install --data-dir <path>` binds the user service and the Runtime to
 * that path. The installed CLI binary, however, is the same for every install
 * and only knows the default `~/.one-memory`. Without a receipt, a new login
 * shell with no environment variables would attach to the default directory
 * and report a running Runtime as stopped — the exact opposite of the product
 * requirement "装完即短指令可用".
 *
 * The receipt lives next to the data directory's parent home so that:
 *   - it is per-user and never shared across installs;
 *   - uninstall can remove it without touching data;
 *   - a caller can always override it with `--data-dir` or
 *     `ONE_MEMORY_DATA_DIR`.
 */

import { mkdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";

export interface InstallReceipt {
  schema_version: 1;
  data_dir: string;
  install_root: string;
  home: string;
  created_at: string;
}

export function defaultInstallReceiptPath(home: string): string {
  return path.join(path.resolve(home), ".one-memory", "cli-install.json");
}

/** The install-time data dir, when the caller did not name one explicitly.
 *
 * Precedence is `ONE_MEMORY_DATA_DIR` > managed install receipt > undefined.
 * Only consults the receipt when `HOME` is explicitly present: tests and
 * embedders pass `{}`, and falling back to `os.homedir()` there would make them
 * read (and later write) the developer's real `~/.one-memory`.
 */
export async function resolveInstalledDataDir(
  environment: NodeJS.ProcessEnv,
): Promise<string | undefined> {
  if (environment.ONE_MEMORY_DATA_DIR !== undefined) {
    return environment.ONE_MEMORY_DATA_DIR;
  }
  const home = environment.HOME;
  if (home === undefined) return undefined;
  const receipt = await readInstallReceipt(defaultInstallReceiptPath(home));
  return receipt?.data_dir;
}

function explicitDataDirFlag(arguments_: readonly string[]): string | null {
  let value: string | undefined;
  for (let index = 0; index < arguments_.length; index += 1) {
    if (arguments_[index] !== "--data-dir") continue;
    if (value !== undefined) return null; // duplicate flag: refuse, do not guess
    const next = arguments_[index + 1];
    if (next === undefined || next.startsWith("--")) return null;
    value = next;
    index += 1;
  }
  if (value === undefined) return null;
  if (!path.isAbsolute(value) || /[\0\r\n]/.test(value)) return null;
  return path.normalize(value);
}

/** The data dir the diagnostics logger must use, or null when the caller named
 * a data dir that is unusable.
 *
 * Precedence mirrors `run()` exactly so entry-level logging and command
 * behaviour cannot diverge: explicit `--data-dir` > `ONE_MEMORY_DATA_DIR` >
 * install receipt > undefined (and the runtime-control default applies).
 * Returns null when an explicit flag is present but invalid: that is a usage
 * error, never a reason to silently fall back to a different data dir.
 */
export async function resolveDiagnosticsDataDir(
  arguments_: readonly string[],
  environment: NodeJS.ProcessEnv,
): Promise<string | null> {
  if (arguments_.includes("--data-dir")) {
    return explicitDataDirFlag(arguments_);
  }
  return (await resolveInstalledDataDir(environment)) ?? null;
}

export async function readInstallReceipt(
  receiptPath: string,
): Promise<InstallReceipt | null> {
  try {
    const info = await stat(receiptPath);
    if (!info.isFile()) return null;
    const raw = JSON.parse(await readFile(receiptPath, "utf8")) as unknown;
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      return null;
    }
    const record = raw as Record<string, unknown>;
    if (
      record.schema_version !== 1 ||
      typeof record.data_dir !== "string" ||
      typeof record.install_root !== "string" ||
      typeof record.home !== "string" ||
      typeof record.created_at !== "string" ||
      !path.isAbsolute(record.data_dir) ||
      /[\0\r\n]/.test(record.data_dir) ||
      !path.isAbsolute(record.install_root) ||
      !path.isAbsolute(record.home)
    ) {
      return null;
    }
    return {
      schema_version: 1,
      data_dir: path.normalize(record.data_dir),
      install_root: path.normalize(record.install_root),
      home: path.normalize(record.home),
      created_at: record.created_at,
    };
  } catch {
    return null;
  }
}

export async function writeInstallReceipt(options: {
  path: string;
  dataDir: string;
  installRoot: string;
  home: string;
  now?: string;
}): Promise<InstallReceipt> {
  if (
    !path.isAbsolute(options.dataDir) ||
    /[\0\r\n]/.test(options.dataDir) ||
    options.dataDir === ""
  ) {
    throw new Error("install_receipt_data_dir_invalid");
  }
  if (!path.isAbsolute(options.installRoot)) {
    throw new Error("install_receipt_install_root_invalid");
  }
  const receipt: InstallReceipt = {
    schema_version: 1,
    data_dir: path.normalize(options.dataDir),
    install_root: path.normalize(options.installRoot),
    home: path.normalize(path.resolve(options.home)),
    created_at: options.now ?? new Date().toISOString(),
  };
  const directory = path.dirname(path.resolve(options.path));
  await mkdir(directory, { recursive: true, mode: 0o700 }).catch(() => {
    throw new Error("install_receipt_home_unwritable");
  });
  const temporary = `${options.path}.memhub.${process.pid}.tmp`;
  try {
    await writeFile(temporary, `${JSON.stringify(receipt, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600,
    });
    await rename(temporary, options.path);
  } catch (error) {
    await rm(temporary, { force: true });
    throw error;
  }
  return receipt;
}

export async function removeInstallReceipt(
  receiptPath: string,
): Promise<"removed" | "not-present"> {
  try {
    await rm(receiptPath);
    return "removed";
  } catch (error) {
    if (
      error !== null &&
      typeof error === "object" &&
      "code" in error &&
      (error as { code?: string }).code === "ENOENT"
    ) {
      return "not-present";
    }
    throw error;
  }
}
