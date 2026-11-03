import {
  chmod,
  lstat,
  mkdir,
  readFile,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import path from "node:path";

export type RuntimeServiceOwner =
  | {
      schema_version: 1;
      owner: "app";
      app_bundle: string;
      app_executable: string;
      start_at_login: boolean;
    }
  | {
      schema_version: 1;
      owner: "cli";
    };

export function runtimeServiceOwnerPath(dataDir: string): string {
  return path.join(dataDir, "runtime-service-owner.json");
}

export function runtimeServiceEnableMarkerPath(dataDir: string): string {
  return path.join(dataDir, "runtime-service.enabled");
}

export async function readRuntimeServiceOwner(
  dataDir: string,
): Promise<RuntimeServiceOwner | null> {
  try {
    const value = JSON.parse(
      await readFile(runtimeServiceOwnerPath(dataDir), "utf8"),
    ) as unknown;
    return validateRuntimeServiceOwner(value);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw new Error("runtime_service_owner_invalid", { cause: error });
  }
}

export async function writeRuntimeServiceOwner(
  dataDir: string,
  owner: RuntimeServiceOwner,
): Promise<void> {
  const value = validateRuntimeServiceOwner(owner);
  if (value === null) throw new Error("runtime_service_owner_invalid");
  await mkdir(dataDir, { recursive: true, mode: 0o700 });
  const temporary = `${runtimeServiceOwnerPath(dataDir)}.${process.pid}.tmp`;
  try {
    await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600,
      flag: "wx",
    });
    await chmod(temporary, 0o600);
    await rename(temporary, runtimeServiceOwnerPath(dataDir));
    await chmod(runtimeServiceOwnerPath(dataDir), 0o600);
  } finally {
    await rm(temporary, { force: true });
  }
}

export async function removeRuntimeServiceOwner(
  dataDir: string,
): Promise<void> {
  await rm(runtimeServiceOwnerPath(dataDir), { force: true });
}

export async function claimRuntimeServiceForApp(options: {
  dataDir: string;
  appBundle: string;
  appExecutable: string;
  startAtLogin?: boolean;
}): Promise<RuntimeServiceOwner> {
  const current = await readRuntimeServiceOwner(options.dataDir);
  if (current?.owner === "cli") return current;
  const owner: RuntimeServiceOwner = {
    schema_version: 1,
    owner: "app",
    app_bundle: safeApplicationPath(options.appBundle),
    app_executable: safeApplicationPath(options.appExecutable),
    start_at_login:
      options.startAtLogin ??
      (current?.owner === "app" ? current.start_at_login : true),
  };
  await writeRuntimeServiceOwner(options.dataDir, owner);
  return owner;
}

export async function setAppRuntimeStartAtLogin(
  dataDir: string,
  enabled: boolean,
): Promise<RuntimeServiceOwner> {
  const current = await readRuntimeServiceOwner(dataDir);
  if (current?.owner !== "app") {
    throw new Error("runtime_service_owner_not_app");
  }
  const next: RuntimeServiceOwner = {
    ...current,
    start_at_login: enabled,
  };
  await writeRuntimeServiceOwner(dataDir, next);
  return next;
}

export async function claimRuntimeServiceForCli(
  dataDir: string,
): Promise<RuntimeServiceOwner> {
  const owner: RuntimeServiceOwner = { schema_version: 1, owner: "cli" };
  await writeRuntimeServiceOwner(dataDir, owner);
  return owner;
}

export async function enableRuntimeService(dataDir: string): Promise<void> {
  await mkdir(dataDir, { recursive: true, mode: 0o700 });
  const marker = runtimeServiceEnableMarkerPath(dataDir);
  const info = await lstat(marker).catch(() => null);
  if (info !== null) {
    if (!info.isFile() || info.isSymbolicLink()) {
      throw new Error("runtime_service_enable_marker_unmanaged");
    }
    await chmod(marker, 0o600);
    return;
  }
  await writeFile(marker, "enabled\n", { encoding: "utf8", mode: 0o600 });
  await chmod(marker, 0o600);
}

export async function disableRuntimeService(dataDir: string): Promise<void> {
  await rm(runtimeServiceEnableMarkerPath(dataDir), { force: true });
}

export async function runtimeServiceEnabled(dataDir: string): Promise<boolean> {
  return pathExists(runtimeServiceEnableMarkerPath(dataDir));
}

export async function appOwnedRuntimeShouldStop(options: {
  dataDir: string;
  markerPath?: string;
  exists?: (target: string) => Promise<boolean>;
}): Promise<boolean> {
  const owner = await readRuntimeServiceOwner(options.dataDir);
  if (owner?.owner !== "app") return false;
  const exists = options.exists ?? pathExists;
  return (
    !(await exists(owner.app_bundle)) || !(await exists(owner.app_executable))
  );
}

function validateRuntimeServiceOwner(
  value: unknown,
): RuntimeServiceOwner | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  if (record.schema_version !== 1) return null;
  if (record.owner === "cli" && Object.keys(record).length === 2) {
    return { schema_version: 1, owner: "cli" };
  }
  if (
    record.owner === "app" &&
    Object.keys(record).length === 5 &&
    typeof record.app_bundle === "string" &&
    typeof record.app_executable === "string" &&
    typeof record.start_at_login === "boolean"
  ) {
    return {
      schema_version: 1,
      owner: "app",
      app_bundle: safeApplicationPath(record.app_bundle),
      app_executable: safeApplicationPath(record.app_executable),
      start_at_login: record.start_at_login,
    };
  }
  return null;
}

function safeApplicationPath(value: string): string {
  const resolved = path.resolve(value);
  if (
    !resolved.startsWith("/Applications/") ||
    /[\0\r\n]/.test(resolved) ||
    (!resolved.includes(".app/") && !resolved.endsWith(".app"))
  ) {
    throw new Error("runtime_service_app_path_invalid");
  }
  return resolved;
}

async function pathExists(target: string): Promise<boolean> {
  return lstat(target).then(
    () => true,
    (error: NodeJS.ErrnoException) => {
      if (error.code === "ENOENT") return false;
      throw error;
    },
  );
}
