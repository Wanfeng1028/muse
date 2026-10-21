import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import {
  access,
  lstat,
  readdir,
  readFile,
  readlink,
  realpath,
} from "node:fs/promises";
import path from "node:path";
import {
  defaultManagedInstallRoot,
  type RuntimeLaunch,
  type RuntimePlatform,
  runtimeInstallLayout,
  stableRuntimeInstallRoot,
} from "@one-memory/runtime-control";

export const HOST_RUNTIME_ATTESTATION_ENV =
  "ONE_MEMORY_HOST_RUNTIME_ATTESTATION";
export const HOST_RUNTIME_ERROR_ENV = "ONE_MEMORY_HOST_RUNTIME_ERROR";
export type HostRuntimeErrorCode =
  | "host_runtime_current_unavailable"
  | "host_runtime_app_location_unsafe"
  | "host_runtime_current_unsafe"
  | "host_runtime_current_changed"
  | "host_runtime_identity_mismatch"
  | "host_runtime_component_mismatch";
export interface VerifiedHostRuntime {
  schemaVersion: 1;
  managedInstallRoot: string;
  selectedVersionRoot: string;
  selectedRelativeTarget: string;
  appMarker: string;
  manifestPackageId: string;
  buildNumber: number;
  platform: RuntimePlatform;
  arch: string;
  manifestSha256: string;
  componentDigests: Record<string, string>;
  runtimeCommand: string;
  mcpEntryPath: string;
  recallCliPath: string;
  captureCommand: string;
  cliEntryPath: string;
  webDirectory: string;
  syncHookAssetsDirectory: string;
}
export type HostRuntimeSelection =
  | { state: "verified"; value: VerifiedHostRuntime }
  | { state: "blocked"; code: HostRuntimeErrorCode };

export {
  type CoreLaunch,
  CoreSupervisor,
  type CoreSupervisorOptions,
  ensureRuntimeProcess,
  findAvailablePort,
  isOwnedHealth,
  processIsAlive,
} from "@one-memory/runtime-control";

export function resolveCoreDataDir(
  appName: string,
  home: string,
  override?: string,
  isolated = false,
  hourlyPackageId?: string,
): string {
  return (
    override ??
    path.join(
      home,
      isolated
        ? hourlyPackageId === undefined
          ? ".one-memory-hourly"
          : // One data root per hourly package: two packages must not share the
            // Core database, `runtime-token` or `runtime.json`. The package id
            // is already path-safe (`One-Memory-H*-...`), but normalize anyway.
            path.join(".one-memory-hourly", safeSegment(hourlyPackageId))
        : appName === "One Memory Preview" || appName === "MemHub Preview"
          ? ".one-memory-preview"
          : ".one-memory",
    )
  );
}

/** Where an isolated hourly package keeps its Electron `userData`.
 *
 * Electron's single-instance lock lives under `userData`; if an isolated App
 * shares the daily App's directory its `requestSingleInstanceLock()` finds the
 * daily instance's `SingletonLock`, returns false, and the App exits with no
 * window whenever the daily App is running. Partition by package id, the same
 * discriminator the Core data/install roots use, under the platform's appData
 * directory (the daily root's parent).
 */
export function resolveCoreUserDataDir(
  appName: string,
  appData: string,
  hourlyPackageId: string,
): string {
  return path.join(
    appData,
    `${sanitizeDisplaySegment(appName)} ${safeSegment(hourlyPackageId)}`,
  );
}

/** Turn a display/app name into one path-safe directory segment.
 *
 * Electron's `app.getName()` is not path-safe: a packaged App without an
 * explicit `productName` returns the package.json `name`, which for this repo
 * is the scoped `@one-memory/desktop`. Passing that through the strict package
 * guard threw `hourly_package_id_invalid`, so `app.setPath("userData", ...)`
 * never ran and the isolated App kept the daily userData and its
 * single-instance lock (EXEC-1914-R5.1-USERDATA-NAME-REJECTED). This segment is
 * a human-readable prefix, not a trust boundary, so sanitize it instead of
 * rejecting; the package id below stays strictly validated. */
export function sanitizeDisplaySegment(value: string): string {
  const slug = value.trim().replace(/[/\\\0\r\n]+/g, "-");
  if (slug === "" || slug === "." || slug === "..") return "App";
  return slug;
}

/** Reject a package id that could escape its parent directory. */
function safeSegment(value: string): string {
  if (value === "." || value === ".." || /[/\\\0\r\n]/.test(value)) {
    throw new Error("hourly_package_id_invalid");
  }
  return value;
}

export function resolveCoreLaunch(options: {
  packaged: boolean;
  appPath: string;
  resourcesPath: string;
  platform: NodeJS.Platform;
}) {
  if (options.packaged) {
    const executable =
      options.platform === "win32" ? "one-memory.exe" : "one-memory";
    return {
      command: path.join(options.resourcesPath, "core", executable),
      args: [],
    };
  }

  const repositoryRoot = path.resolve(options.appPath, "../..");
  return {
    command: "uv",
    args: [
      "run",
      "--directory",
      path.join(repositoryRoot, "apps", "core"),
      "one-memory",
    ],
    cwd: repositoryRoot,
  };
}

function runtimePlatform(platform: NodeJS.Platform): RuntimePlatform {
  if (platform === "darwin" || platform === "linux" || platform === "win32") {
    return platform;
  }
  throw new Error("runtime_platform_unsupported");
}

export function stableRecallPaths(options: {
  home: string;
  dataDir: string;
  platform?: NodeJS.Platform;
  localAppData?: string;
  isolated?: boolean;
  hourlyPackageId?: string;
}): {
  runtimeCommand: string;
  mcpEntryPath: string;
  recallCliPath: string;
  captureCommand: string;
  syncHookAssetsDirectory: string;
  corePortOverride?: number;
} {
  const platform = runtimePlatform(options.platform ?? process.platform);
  const stable = runtimeInstallLayout({
    platform,
    home: options.home,
    installRoot: stableRuntimeInstallRoot(
      platform,
      options.home,
      options.localAppData,
      options.isolated,
      options.hourlyPackageId,
    ),
    dataDir: options.dataDir,
  });
  return {
    runtimeCommand: stable.nodeCommand,
    mcpEntryPath: stable.mcpEntryPath,
    recallCliPath: stable.recallCliPath,
    captureCommand: stable.coreCommand,
    syncHookAssetsDirectory: stable.syncHookAssetsDirectory,
    ...(stable.corePortOverride === undefined
      ? {}
      : { corePortOverride: stable.corePortOverride }),
  };
}

export type PackagedHostPaths = {
  runtimeCommand: string;
  mcpEntryPath: string;
  recallCliPath: string;
  captureCommand: string;
  syncHookAssetsDirectory: string;
};

/** Resolve host commands from the bundle that is actually running.
 *
 * Host configuration needs a path that survives ejecting a disk image,
 * deleting a download, or cleaning a QA directory. On macOS only an app
 * installed directly under /Applications is such a target. Tests may provide
 * an isolated Applications root; production never does.
 */
export async function resolveRunningPackagedHostPaths(options: {
  runtimeCommand: string;
  resourcesPath: string;
  platform?: NodeJS.Platform;
  applicationsRoot?: string;
}): Promise<
  | { state: "verified"; value: PackagedHostPaths }
  | { state: "blocked"; code: "host_runtime_app_location_unsafe" }
> {
  const platform = options.platform ?? process.platform;
  const unsafe = (value: string) =>
    value.startsWith(`/Volumes${path.sep}`) ||
    value.includes(`${path.sep}AppTranslocation${path.sep}`);
  if (
    platform === "darwin" &&
    (unsafe(options.runtimeCommand) || unsafe(options.resourcesPath))
  ) {
    return { state: "blocked", code: "host_runtime_app_location_unsafe" };
  }
  try {
    const runtimeCommand = await realpath(options.runtimeCommand);
    const resourcesPath = await realpath(options.resourcesPath);
    if (platform === "darwin") {
      if (unsafe(runtimeCommand) || unsafe(resourcesPath))
        return { state: "blocked", code: "host_runtime_app_location_unsafe" };
      const marker = `${path.sep}Contents${path.sep}MacOS${path.sep}`;
      const boundary = runtimeCommand.lastIndexOf(marker);
      if (boundary < 1 || !runtimeCommand.slice(0, boundary).endsWith(".app"))
        return { state: "blocked", code: "host_runtime_app_location_unsafe" };
      const bundle = runtimeCommand.slice(0, boundary);
      const applicationsRoot = await realpath(
        options.applicationsRoot ?? "/Applications",
      ).catch(() => path.resolve(options.applicationsRoot ?? "/Applications"));
      if (path.dirname(bundle) !== applicationsRoot)
        return { state: "blocked", code: "host_runtime_app_location_unsafe" };
      const contents = path.join(bundle, "Contents");
      if (resourcesPath !== path.join(contents, "Resources"))
        return { state: "blocked", code: "host_runtime_app_location_unsafe" };
    }
    return {
      state: "verified",
      value: {
        runtimeCommand,
        mcpEntryPath: path.join(resourcesPath, "host-bridge", "mcp.cjs"),
        recallCliPath: path.join(
          resourcesPath,
          "host-bridge",
          "recall-cli.cjs",
        ),
        captureCommand: path.join(
          resourcesPath,
          "core",
          platform === "win32" ? "one-memory.exe" : "one-memory",
        ),
        syncHookAssetsDirectory: path.join(
          resourcesPath,
          "host-bridge",
          "sync-hook",
        ),
      },
    };
  } catch {
    return { state: "blocked", code: "host_runtime_app_location_unsafe" };
  }
}

const HOST_COMPONENTS = [
  ["core/one-memory", "core/one-memory"],
  ["runtime/runtime.cjs", "runtime/runtime.cjs"],
  ["host-bridge/mcp.cjs", "host-bridge/mcp.cjs"],
  ["host-bridge/recall-cli.cjs", "host-bridge/recall-cli.cjs"],
  ["cli/one-memory.cjs", "bin/one-memory.cjs"],
] as const;

export async function resolveVerifiedHostRuntime(options: {
  resourcesPath: string;
  appMarker?: string;
  buildNumber?: number;
  home: string;
  platform?: NodeJS.Platform;
  arch?: string;
  localAppData?: string;
}): Promise<HostRuntimeSelection> {
  try {
    const appMarker = options.appMarker;
    const family = appMarker?.match(
      /^One-Memory-H(APP1R[0-9]+(?:\.[0-9]+)*-[0-9a-f]{8})-c7-isolated$/,
    )?.[1];
    if (!family || options.buildNumber === undefined)
      throw hostError("host_runtime_identity_mismatch");
    const platform = runtimePlatform(options.platform ?? process.platform);
    const arch = options.arch ?? process.arch;
    const root = defaultManagedInstallRoot(
      platform,
      options.home,
      options.localAppData,
      false,
    );
    const versions = path.join(root, "versions");
    const current = path.join(root, "current");
    const ancestors = await captureDirs([
      options.home,
      path.join(options.home, "Library"),
      path.join(options.home, "Library", "Application Support"),
      root,
      versions,
    ]);
    const linkInfo = await lstat(current).catch(() => null);
    if (!linkInfo?.isSymbolicLink())
      throw hostError("host_runtime_current_unavailable");
    const relative = await readlink(current);
    if (!/^versions\/[0-9A-Za-z][0-9A-Za-z._-]{0,127}$/.test(relative))
      throw hostError("host_runtime_current_unsafe");
    const selected = await realpath(path.join(root, relative));
    if (path.dirname(selected) !== (await realpath(versions)))
      throw hostError("host_runtime_current_unsafe");
    const selectedIdentity = await captureDirs([selected]);
    await recheck(ancestors, current, linkInfo, relative);
    const manifest = await verifiedManifest(selected, platform, arch);
    if (
      manifest.build_number !== options.buildNumber ||
      manifest.package_id !== `One-Memory-${family}-candidate`
    )
      throw hostError("host_runtime_identity_mismatch");
    const digests: Record<string, string> = {};
    for (const [from, to] of HOST_COMPONENTS)
      await compare(
        options.resourcesPath,
        from,
        selected,
        to,
        manifest,
        digests,
      );
    const appWeb = path.join(options.resourcesPath, "web");
    const selectedWeb = path.join(selected, "web");
    const appFiles = await treeFiles(appWeb);
    if (
      JSON.stringify(appFiles) !== JSON.stringify(await treeFiles(selectedWeb))
    )
      throw hostError("host_runtime_component_mismatch");
    for (const file of appFiles)
      await compare(
        appWeb,
        file,
        selectedWeb,
        file,
        manifest,
        digests,
        `web/${file}`,
      );
    const appHook = path.join(
      options.resourcesPath,
      "host-bridge",
      "sync-hook",
    );
    const selectedHook = path.join(selected, "host-bridge", "sync-hook");
    const hookFiles = await treeFiles(appHook);
    if (
      JSON.stringify(hookFiles) !==
      JSON.stringify(await treeFiles(selectedHook))
    )
      throw hostError("host_runtime_component_mismatch");
    for (const file of hookFiles)
      await compare(
        appHook,
        file,
        selectedHook,
        file,
        manifest,
        digests,
        `host-bridge/sync-hook/${file}`,
      );
    const node = path.join(selected, "bin", "node");
    const nodeInfo = await lstat(node).catch(() => null);
    if (
      !nodeInfo?.isFile() ||
      nodeInfo.isSymbolicLink() ||
      !(nodeInfo.mode & 0o111)
    )
      throw hostError("host_runtime_component_mismatch");
    await access(node, 1);
    await recheck(
      [...ancestors, ...selectedIdentity],
      current,
      linkInfo,
      relative,
    );
    return {
      state: "verified",
      value: Object.freeze({
        schemaVersion: 1,
        managedInstallRoot: root,
        selectedVersionRoot: selected,
        selectedRelativeTarget: relative,
        appMarker,
        manifestPackageId: manifest.package_id,
        buildNumber: options.buildNumber,
        platform,
        arch,
        manifestSha256: await hash(path.join(selected, "manifest.json")),
        componentDigests: Object.freeze(digests),
        runtimeCommand: node,
        mcpEntryPath: path.join(selected, "host-bridge/mcp.cjs"),
        recallCliPath: path.join(selected, "host-bridge/recall-cli.cjs"),
        captureCommand: path.join(selected, "core/one-memory"),
        cliEntryPath: path.join(selected, "bin/one-memory.cjs"),
        webDirectory: selectedWeb,
        syncHookAssetsDirectory: selectedHook,
      }),
    };
  } catch (error) {
    return {
      state: "blocked",
      code:
        error instanceof HostRuntimeFailure
          ? error.code
          : "host_runtime_current_unavailable",
    };
  }
}

class HostRuntimeFailure extends Error {
  constructor(readonly code: HostRuntimeErrorCode) {
    super(code);
  }
}
const hostError = (code: HostRuntimeErrorCode) => new HostRuntimeFailure(code);
type Identity = {
  path: string;
  dev: number;
  ino: number;
  mode: number;
  uid: number;
};
async function captureDirs(paths: string[]): Promise<Identity[]> {
  const result: Identity[] = [];
  for (const target of paths) {
    const info = await lstat(target).catch(() => null);
    if (
      !info?.isDirectory() ||
      info.isSymbolicLink() ||
      info.mode & 0o022 ||
      (process.getuid && info.uid !== process.getuid())
    )
      throw hostError("host_runtime_current_unsafe");
    result.push({
      path: target,
      dev: info.dev,
      ino: info.ino,
      mode: info.mode,
      uid: info.uid,
    });
  }
  return result;
}
async function recheck(
  ids: Identity[],
  current: string,
  link: Awaited<ReturnType<typeof lstat>>,
  relative: string,
) {
  for (const id of ids) {
    const now = await lstat(id.path).catch(() => null);
    if (
      !now?.isDirectory() ||
      now.isSymbolicLink() ||
      now.dev !== id.dev ||
      now.ino !== id.ino ||
      now.mode !== id.mode ||
      now.uid !== id.uid
    )
      throw hostError("host_runtime_current_changed");
  }
  const now = await lstat(current).catch(() => null);
  if (
    !now?.isSymbolicLink() ||
    now.dev !== link.dev ||
    now.ino !== link.ino ||
    (await readlink(current)) !== relative
  )
    throw hostError("host_runtime_current_changed");
}
async function treeFiles(root: string, current = root): Promise<string[]> {
  const files: string[] = [];
  for (const entry of (await readdir(current, { withFileTypes: true })).sort(
    (a, b) => a.name.localeCompare(b.name),
  )) {
    const target = path.join(current, entry.name);
    if (entry.isSymbolicLink())
      throw hostError("host_runtime_component_mismatch");
    if (entry.isDirectory()) files.push(...(await treeFiles(root, target)));
    else if (entry.isFile()) files.push(path.relative(root, target));
    else throw hostError("host_runtime_component_mismatch");
  }
  return files.sort();
}
async function compare(
  aRoot: string,
  aRel: string,
  bRoot: string,
  bRel: string,
  manifest: CheckedManifest,
  digests: Record<string, string>,
  manifestRel = bRel,
) {
  const a = path.join(aRoot, aRel),
    b = path.join(bRoot, bRel);
  const [ai, bi] = await Promise.all([
    lstat(a).catch(() => null),
    lstat(b).catch(() => null),
  ]);
  if (
    !ai?.isFile() ||
    ai.isSymbolicLink() ||
    !bi?.isFile() ||
    bi.isSymbolicLink()
  )
    throw hostError("host_runtime_component_mismatch");
  const [ah, bh] = await Promise.all([hash(a), hash(b)]);
  if (ah !== bh || manifest.files[manifestRel] !== bh)
    throw hostError("host_runtime_component_mismatch");
  digests[manifestRel] = bh;
}
async function hash(file: string): Promise<string> {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(file)) digest.update(chunk);
  return digest.digest("hex");
}

type CheckedManifest = {
  schema_version: 1;
  product: "one-memory-runtime";
  version: string;
  build_number?: number;
  package_id?: unknown;
  platform: RuntimePlatform;
  arch: string;
  files: Record<string, string>;
};

async function verifiedManifest(
  root: string,
  platform: RuntimePlatform,
  arch: string,
): Promise<CheckedManifest> {
  let value: unknown;
  try {
    value = JSON.parse(
      await readFile(path.join(root, "manifest.json"), "utf8"),
    );
  } catch {
    throw hostError("host_runtime_identity_mismatch");
  }
  const manifest = value as Partial<CheckedManifest>;
  if (
    manifest.schema_version !== 1 ||
    manifest.product !== "one-memory-runtime" ||
    typeof manifest.version !== "string" ||
    manifest.platform !== platform ||
    manifest.arch !== arch ||
    !manifest.files ||
    typeof manifest.files !== "object"
  )
    throw hostError("host_runtime_identity_mismatch");
  const actual = await manifestTreeFiles(root);
  const expected = [...Object.keys(manifest.files), "manifest.json"].sort();
  if (JSON.stringify(actual) !== JSON.stringify(expected))
    throw hostError("host_runtime_component_mismatch");
  for (const [relative, digest] of Object.entries(manifest.files)) {
    if (
      !/^[a-f0-9]{64}$/.test(digest) ||
      path.isAbsolute(relative) ||
      relative.split(/[\\/]/).includes("..") ||
      (await hash(path.join(root, relative))) !== digest
    )
      throw hostError("host_runtime_component_mismatch");
  }
  return manifest as CheckedManifest;
}

async function manifestTreeFiles(
  root: string,
  current = root,
): Promise<string[]> {
  const files: string[] = [];
  for (const entry of (await readdir(current, { withFileTypes: true })).sort(
    (a, b) => a.name.localeCompare(b.name),
  )) {
    const target = path.join(current, entry.name);
    if (entry.isDirectory())
      files.push(...(await manifestTreeFiles(root, target)));
    else if (entry.isFile() || entry.isSymbolicLink())
      files.push(path.relative(root, target));
    else throw hostError("host_runtime_component_mismatch");
  }
  return files.sort();
}

export function resolvePackagedRuntimeLaunch(options: {
  resourcesPath: string;
  dataDir: string;
  runtimeCommand: string;
  home: string;
  platform?: NodeJS.Platform;
  localAppData?: string;
  isolated?: boolean;
  hourlyPackageId?: string;
  hostRuntimeSelection?: HostRuntimeSelection;
  corePortOverride?: number;
  buildNumber?: number;
  commit?: string;
  packagedHostPaths?: {
    runtimeCommand: string;
    mcpEntryPath: string;
    recallCliPath: string;
    captureCommand: string;
    syncHookAssetsDirectory: string;
  };
}): RuntimeLaunch {
  const platform = runtimePlatform(options.platform ?? process.platform);
  const coreExecutable = platform === "win32" ? "one-memory.exe" : "one-memory";
  // The process still starts from the bundle it was packaged in. The paths
  // handed to other apps are the stable install: `current` does not move
  // when this bundle is replaced.
  const isolatedLayout = stableRecallPaths(options);
  const stable =
    options.hostRuntimeSelection?.state === "verified"
      ? options.hostRuntimeSelection.value
      : (options.packagedHostPaths ?? isolatedLayout);
  const hostRuntimeEnvironment =
    options.hostRuntimeSelection?.state === "verified"
      ? {
          [HOST_RUNTIME_ATTESTATION_ENV]: JSON.stringify(
            options.hostRuntimeSelection.value,
          ),
        }
      : options.hostRuntimeSelection?.state === "blocked"
        ? { [HOST_RUNTIME_ERROR_ENV]: options.hostRuntimeSelection.code }
        : {};
  return {
    command: options.runtimeCommand,
    args: [path.join(options.resourcesPath, "runtime", "runtime.cjs"), "serve"],
    env: {
      ELECTRON_RUN_AS_NODE: "1",
      ...(options.isolated ? { ONE_MEMORY_DESKTOP_RUNTIME_ISOLATED: "1" } : {}),
      ONE_MEMORY_DATA_DIR: options.dataDir,
      ONE_MEMORY_CORE_COMMAND: path.join(
        options.resourcesPath,
        "core",
        coreExecutable,
      ),
      ONE_MEMORY_MCP_ENTRY: stable.mcpEntryPath,
      ONE_MEMORY_RECALL_CLI: stable.recallCliPath,
      ONE_MEMORY_SYNC_HOOK_ASSETS: stable.syncHookAssetsDirectory,
      ONE_MEMORY_NODE_COMMAND: stable.runtimeCommand,
      ...(options.buildNumber === undefined
        ? {}
        : { ONE_MEMORY_BUILD_NUMBER: String(options.buildNumber) }),
      ...(options.commit === undefined
        ? {}
        : { ONE_MEMORY_COMMIT: options.commit }),
      ...hostRuntimeEnvironment,
      // The Runtime is spawned directly by the App (`ensureRuntimeProcess`),
      // not by an installed LaunchAgent, so it never sees the plist that would
      // have carried `ONE_MEMORY_CORE_PORT`. Without this the child's
      // `resolveCorePort` falls back to 8765 and an isolated package collides
      // with the daily Core. The layout already derives a stable per-root port
      // for every non-default install root and leaves the daily root without
      // one, so forwarding it keeps the daily path on 8765.
      ...(options.corePortOverride === undefined &&
      isolatedLayout.corePortOverride === undefined
        ? {}
        : {
            ONE_MEMORY_CORE_PORT: String(
              options.corePortOverride ?? isolatedLayout.corePortOverride,
            ),
          }),
    },
  };
}
