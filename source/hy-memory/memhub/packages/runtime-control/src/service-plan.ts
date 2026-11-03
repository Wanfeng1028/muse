import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import path from "node:path";
import {
  runtimeServiceEnableMarkerPath,
  runtimeServiceOwnerPath,
} from "./service-ownership.js";

export type RuntimePlatform = "darwin" | "linux" | "win32";
export const RUNTIME_SERVICE_ID = "com.tencent.onememory.runtime";
/** The everyday install's Core port. Never changes: host configs and the
 *  renderer's default assume it, and it is the only port the daily install may
 *  use. */
export const DEFAULT_CORE_PORT = 8765;

export interface RuntimeInstallLayout {
  platform: RuntimePlatform;
  home: string;
  installRoot: string;
  dataDir: string;
  nodeCommand: string;
  runtimeEntry: string;
  coreCommand: string;
  mcpEntryPath: string;
  recallCliPath: string;
  syncHookAssetsDirectory: string;
  /**
   * Present only for an isolated hourly install. It carries the same two
   * markers the desktop already uses to decide the isolated install root. The
   * daily install leaves it undefined.
   */
  hourlyIsolation?: {
    instanceId: string;
    packageId: string;
  };
  /**
   * Set for every NON-default install root. Two custom roots share one machine
   * and would otherwise both bind the fixed 8765, so each gets its own stable
   * port. The daily root leaves this undefined and keeps 8765.
   */
  corePortOverride?: number;
  /** Optional stable Broker port for isolated/custom service instances. */
  brokerPortOverride?: number;
}

/** The two markers plus the port an isolated hourly install may carry.
 *
 * `isIsolatedHourlyDesktop` (apps/desktop) and C7's `isIsolatedHourlyRuntime`
 * use the same shape: a v4 UUID instance id and a package id
 * `One-Memory-H*-c7-isolated`. Keeping one predicate here means an install
 * cannot be "isolated" for the data dir but not for the plist.
 */
export function isIsolatedHourlyInstall(input: {
  instanceId?: unknown;
  packageId?: unknown;
}): input is { instanceId: string; packageId: string } {
  const { instanceId, packageId } = input;
  return (
    typeof instanceId === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      instanceId,
    ) &&
    typeof packageId === "string" &&
    packageId.startsWith("One-Memory-H") &&
    packageId.endsWith("-c7-isolated")
  );
}

/** The two hourly markers as they appear in a process environment.
 *
 * The installer (CLI `install`/`service-*`, the packaged App) is launched with
 * `ONE_MEMORY_HOURLY_INSTANCE_ID` / `ONE_MEMORY_HOURLY_PACKAGE_ID` already set
 * by the release entry point. Every `runtimeInstallLayout` caller must forward
 * them, or the LaunchAgent plist it writes carries neither the markers nor the
 * derived `ONE_MEMORY_CORE_PORT` and the installed Runtime falls back to the
 * daily port/root. Returning an empty object for a partial or malformed pair
 * keeps the daily install byte-identical to before.
 */
export function hourlyIsolationFromEnvironment(
  environment: NodeJS.ProcessEnv,
): { hourlyInstanceId?: string; hourlyPackageId?: string } {
  const instanceId = environment.ONE_MEMORY_HOURLY_INSTANCE_ID;
  const packageId = environment.ONE_MEMORY_HOURLY_PACKAGE_ID;
  if (!isIsolatedHourlyInstall({ instanceId, packageId })) return {};
  return { hourlyInstanceId: instanceId, hourlyPackageId: packageId };
}

/** The data root a management surface must use, from the environment alone.
 *
 * Standalone CLI and probe processes are launched from inside an hourly
 * package, so they carry `ONE_MEMORY_HOURLY_PACKAGE_ID` /
 * `ONE_MEMORY_HOURLY_INSTANCE_ID` (baked into the App's `LSEnvironment`, or set
 * by the release launcher) but *not* the plist's `ONE_MEMORY_DATA_DIR`, which
 * only launchd rewrites for the installed service. Defaulting to `~/.one-memory`
 * in that situation silently points management commands at the daily database
 * (EXEC-1914-CLI-STANDALONE-DAILY-DEFAULT). This derives the isolated root from
 * the same markers everything else keys on.
 *
 * Returns `null` when no hourly markers are present, so a genuine daily CLI run
 * still resolves `~/.one-memory`; an explicit `ONE_MEMORY_DATA_DIR` always wins.
 */
export function hourlyManagedDataDirFromEnvironment(
  environment: NodeJS.ProcessEnv,
  home: string,
): string | null {
  const explicit = environment.ONE_MEMORY_DATA_DIR;
  // An explicit value (even an invalid one) always wins, so the caller's
  // validation still reports `runtime_service_data_directory_invalid` rather
  // than silently substituting a derived root.
  if (explicit !== undefined) return explicit;
  const isolation = hourlyIsolationFromEnvironment(environment);
  if (isolation.hourlyPackageId === undefined) return null;
  const paths = process.platform === "win32" ? path.win32 : path.posix;
  return paths.join(
    home,
    ".one-memory-hourly",
    safePackageSegment(isolation.hourlyPackageId),
  );
}

export interface RuntimeServicePlan {
  schema_version: 1;
  platform: RuntimePlatform;
  scope: "user";
  service_id: string;
  status: "ready" | "blocked";
  blocked_reason: string | null;
  /**
   * The Core port this layout will bind. It is the one authority a probe or
   * the renderer can read without re-deriving `stableCorePort` from the install
   * root, so an isolated install can be probed on its real (non-canonical)
   * port. `null` only where no port applies (Windows has no user service yet).
   */
  core_port: number | null;
  service_file: { path: string; mode: 0o600; content: string } | null;
  /**
   * LaunchAgent stdout/stderr destination. `launchd` can only write where the
   * directory already exists, so the installer owns creating this at 0700 with
   * owner-only log files before `bootstrap`. Null for platforms whose service
   * manager does not need a preparsed path (systemd/windows).
   */
  log_directory: string | null;
  commands: {
    install: string[][];
    start: string[][];
    restart: string[][];
    stop: string[][];
    uninstall: string[][];
  };
}

/** Parent of the `current` link. Same places the CLI uses as its default install root. */
export function defaultManagedInstallRoot(
  platform: RuntimePlatform,
  home: string,
  localAppData?: string,
  isolated = false,
  hourlyPackageId?: string,
): string {
  const paths = platform === "win32" ? path.win32 : path.posix;
  if (platform === "darwin") {
    return isolated
      ? // Two hourly packages must not share one install root: they would fight
        // over the same `current` link, derive the same LaunchAgent label, and
        // overwrite each other's runtime token. Partition by package id so each
        // package owns its own root. The package id is `One-Memory-H*-...` with
        // no path separators, and `safePackageSegment` rejects anything else.
        paths.join(
          home,
          "Library",
          "Application Support",
          "One Memory Hourly",
          ...(hourlyPackageId === undefined
            ? ["managed-runtime"]
            : [safePackageSegment(hourlyPackageId), "managed-runtime"]),
        )
      : paths.join(home, "Library", "Application Support", "One Memory");
  }
  if (platform === "win32") {
    return localAppData
      ? paths.join(localAppData, "One Memory")
      : paths.join(home, "AppData", "Local", "One Memory");
  }
  return paths.join(home, ".local", "share", "one-memory");
}

/** The path host installs must name. It stays put while `current` flips versions. */
export function stableRuntimeInstallRoot(
  platform: RuntimePlatform,
  home: string,
  localAppData?: string,
  isolated = false,
  hourlyPackageId?: string,
): string {
  const paths = platform === "win32" ? path.win32 : path.posix;
  return paths.join(
    defaultManagedInstallRoot(
      platform,
      home,
      localAppData,
      isolated,
      hourlyPackageId,
    ),
    "current",
  );
}

/** A package id is used as a single path segment, so refuse anything that could
 *  escape it. The id is already `One-Memory-H*-c7-isolated`, but the marker
 *  comes from an environment variable, so validate rather than trust it. */
function safePackageSegment(packageId: string): string {
  if (
    packageId === "." ||
    packageId === ".." ||
    /[/\\\0\r\n]/.test(packageId)
  ) {
    throw new Error("runtime_service_hourly_package_id_invalid");
  }
  return packageId;
}

/** The default data directory for an install.
 *
 * The daily install keeps `<home>/.one-memory`. An isolated hourly install gets
 * its own root *per package id*, so two hourly packages stop sharing
 * `runtime-token` / `runtime.json` / the Core database. Without the package id
 * an isolated install falls back to the older shared `~/.one-memory-hourly`
 * shape, which keeps every previously shipped layout resolvable.
 */
function defaultManagedDataDir(
  paths: typeof path.posix,
  home: string,
  isolated: boolean,
  hourlyPackageId: string | undefined,
): string {
  if (!isolated) return paths.join(home, ".one-memory");
  return hourlyPackageId === undefined
    ? paths.join(home, ".one-memory-hourly")
    : paths.join(
        home,
        ".one-memory-hourly",
        safePackageSegment(hourlyPackageId),
      );
}

/** One physical macOS install root must always map to one `current` spelling.
 *
 * macOS exposes `/tmp` through the `/private/tmp` symlink. Planning often runs
 * before the selected install root exists, so canonicalize the nearest existing
 * ancestor and append the missing suffix. This keeps Desktop, CLI, upgrade and
 * uninstall on one scoped LaunchAgent label before and after installation.
 */
export function canonicalManagedServiceRoot(
  platform: RuntimePlatform,
  installRoot: string,
): string {
  const paths = platform === "win32" ? path.win32 : path.posix;
  const resolved = paths.resolve(installRoot);
  const root =
    paths.basename(resolved) === "current" ? paths.dirname(resolved) : resolved;
  let canonicalRoot = root;
  if (platform === "darwin" && process.platform === "darwin") {
    const suffix: string[] = [];
    let existing = root;
    while (true) {
      try {
        canonicalRoot = paths.join(realpathSync.native(existing), ...suffix);
        break;
      } catch {
        const parent = paths.dirname(existing);
        if (parent === existing) break;
        suffix.unshift(paths.basename(existing));
        existing = parent;
      }
    }
  }
  return paths.join(canonicalRoot, "current");
}

export function runtimeInstallLayout(input: {
  platform: RuntimePlatform;
  home: string;
  installRoot: string;
  dataDir?: string;
  localAppData?: string;
  hourlyInstanceId?: string;
  hourlyPackageId?: string;
  corePort?: number;
  brokerPort?: number;
}): RuntimeInstallLayout {
  const paths = input.platform === "win32" ? path.win32 : path.posix;
  const home = paths.resolve(input.home);
  // Every stable install path must end at the `current` link. Callers are not
  // consistent about naming the root or that link (install passes `current`,
  // uninstall/upgrade pass the root), and the on-disk service file and the
  // scoped label must not depend on which spelling was used. Normalize here so
  // preview, install, upgrade, uninstall and doctor agree on one layout.
  const installRoot = canonicalManagedServiceRoot(
    input.platform,
    input.installRoot,
  );
  if (
    input.dataDir !== undefined &&
    (!paths.isAbsolute(input.dataDir) || /[\0\r\n]/.test(input.dataDir))
  ) {
    throw new Error("runtime_service_data_directory_invalid");
  }
  const executable =
    input.platform === "win32" ? "one-memory.exe" : "one-memory";
  const node = input.platform === "win32" ? "node.exe" : "node";
  const isolated = isIsolatedHourlyInstall({
    instanceId: input.hourlyInstanceId,
    packageId: input.hourlyPackageId,
  });
  if (input.corePort !== undefined) {
    if (
      !Number.isInteger(input.corePort) ||
      input.corePort < 1024 ||
      input.corePort > 65_535
    ) {
      throw new Error("runtime_service_core_port_invalid");
    }
  }
  if (input.brokerPort !== undefined) {
    if (
      !Number.isInteger(input.brokerPort) ||
      input.brokerPort < 1024 ||
      input.brokerPort > 65_535 ||
      input.brokerPort === (input.corePort ?? DEFAULT_CORE_PORT)
    ) {
      throw new Error("runtime_service_broker_port_invalid");
    }
  }
  return Object.freeze({
    platform: input.platform,
    home,
    installRoot,
    dataDir:
      input.dataDir === undefined
        ? defaultManagedDataDir(paths, home, isolated, input.hourlyPackageId)
        : paths.normalize(input.dataDir),
    nodeCommand: paths.join(installRoot, "bin", node),
    runtimeEntry: paths.join(installRoot, "runtime", "runtime.cjs"),
    coreCommand: paths.join(installRoot, "core", executable),
    mcpEntryPath: paths.join(installRoot, "host-bridge", "mcp.cjs"),
    recallCliPath: paths.join(installRoot, "host-bridge", "recall-cli.cjs"),
    syncHookAssetsDirectory: paths.join(
      installRoot,
      "host-bridge",
      "sync-hook",
    ),
    ...(isolated
      ? {
          hourlyIsolation: {
            instanceId: input.hourlyInstanceId as string,
            packageId: input.hourlyPackageId as string,
          },
        }
      : {}),
    ...(input.brokerPort === undefined
      ? {}
      : { brokerPortOverride: input.brokerPort }),
    ...(() => {
      // A non-default install root shares the machine with the daily install
      // and with other custom roots, so it must not fall back to the fixed
      // 8765: two roots would collide and the second Runtime dies with
      // EADDRINUSE. The daily root gets no override at all.
      const defaultRoot = paths.dirname(
        canonicalManagedServiceRoot(
          input.platform,
          defaultManagedInstallRoot(input.platform, home, input.localAppData),
        ),
      );
      const normalizedRoot = paths.dirname(installRoot);
      if (normalizedRoot === defaultRoot) return {};
      return {
        corePortOverride: input.corePort ?? stableCorePort(normalizedRoot),
      };
    })(),
  });
}

/** A stable Core port for one non-default install root.
 *
 * Derived from the root path, so every command that looks at the same root
 * (preview, install, upgrade, uninstall, doctor) agrees without extra state,
 * and a reinstall keeps the same port. Kept below 10000 so it does not collide
 * with the ephemeral range a development run may pick.
 */
export function stableCorePort(installRoot: string): number {
  const digest = createHash("sha256")
    .update(`one-memory-core-port\0${installRoot}`)
    .digest();
  return 9200 + (digest.readUInt32BE(0) % 700);
}

export function planUserService(
  layout: RuntimeInstallLayout,
  options: { uid?: number; xdgConfigHome?: string } = {},
): RuntimeServicePlan {
  if (layout.platform === "win32") {
    return {
      schema_version: 1,
      platform: "win32",
      scope: "user",
      service_id: "One Memory Runtime",
      status: "blocked",
      blocked_reason: "windows_acl_and_user_service_not_verified",
      core_port: null,
      service_file: null,
      log_directory: null,
      commands: {
        install: [],
        start: [],
        restart: [],
        stop: [],
        uninstall: [],
      },
    };
  }
  return layout.platform === "darwin"
    ? launchAgentPlan(layout, options.uid)
    : systemdPlan(layout, options.xdgConfigHome);
}

/** One canonical label owns the daily install; other roots get a distinct label.
 *
 * A user-level LaunchAgent is single-instance per label. The daily install root
 * must keep the stable label host configs already name, so a reinstall is an
 * idempotent upgrade rather than a second conflicting registration. An isolated
 * or hourly install root is a different product instance on the same machine;
 * it is scoped to its own label so the two never collide, and so the daily
 * install stays untouched. The label is derived deterministically from the
 * root, so preview, apply and uninstall all agree without extra state.
 */
function serviceLabelFor(layout: RuntimeInstallLayout): string {
  const paths = layout.platform === "win32" ? path.win32 : path.posix;
  // Callers are not consistent about naming the install root or its `current`
  // link: `install` passes `current`, while `uninstall`/`upgrade` pass the
  // root. The label must not depend on that, or a service installed under one
  // spelling would not be found under the other. Normalize by dropping a
  // single trailing `current` segment.
  const resolved = paths.resolve(layout.installRoot);
  const installRoot =
    paths.basename(resolved) === "current" ? paths.dirname(resolved) : resolved;
  const dailyRoot = paths.dirname(
    canonicalManagedServiceRoot(
      layout.platform,
      defaultManagedInstallRoot(layout.platform, layout.home),
    ),
  );
  if (installRoot === dailyRoot) {
    return RUNTIME_SERVICE_ID;
  }
  const digest = createHash("sha256")
    .update(`one-memory-service-root\0${layout.platform}\0${installRoot}`)
    .digest("hex")
    .slice(0, 16);
  return `${RUNTIME_SERVICE_ID}.${digest}`;
}

function launchAgentPlan(
  layout: RuntimeInstallLayout,
  uid: number | undefined,
): RuntimeServicePlan {
  if (!Number.isSafeInteger(uid) || (uid ?? 0) < 1) {
    return blocked(layout, "macos_user_id_required", RUNTIME_SERVICE_ID);
  }
  const serviceId = serviceLabelFor(layout);
  const target = path.posix.join(
    layout.home,
    "Library",
    "LaunchAgents",
    `${serviceId}.plist`,
  );
  const domain = `gui/${uid}`;
  // `launchd` will not create the redirect's parent, and it writes as the
  // logged-in user. Keep service logs inside the data dir so uninstall
  // preserves them with the rest of the user's data, and so a custom data
  // instance keeps its own logs instead of sharing the daily home.
  const logDirectory = path.posix.join(layout.dataDir, "logs");
  const content = launchAgentDeclaration(layout, serviceId, target);
  return ready(layout, serviceId, target, content, logDirectory, {
    install: [["launchctl", "bootstrap", domain, target]],
    start: [["launchctl", "bootstrap", domain, target]],
    restart: [["launchctl", "kickstart", "-k", `${domain}/${serviceId}`]],
    stop: [["launchctl", "bootout", domain, target]],
    uninstall: [["launchctl", "bootout", domain, target]],
  });
}

function launchAgentDeclaration(
  layout: RuntimeInstallLayout,
  serviceId: string,
  serviceFile: string,
): string {
  // Deliberately NO StandardOutPath/StandardErrorPath. launchd would hold that
  // descriptor, and a descriptor launchd holds cannot be rotated: renaming the
  // file leaves launchd writing to the renamed inode, and truncating loses data
  // without bound. Measured: the redirect grew a login-start daemon's log by
  // ~654 bytes per `status` call, uncapped. The Runtime instead captures its own
  // stdout/stderr into bounded rotating files under <dataDir>/logs.
  const redirects = "";
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>${serviceId}</string>
<key>ProgramArguments</key><array><string>${xml(layout.nodeCommand)}</string><string>${xml(layout.runtimeEntry)}</string><string>serve</string></array>
<key>EnvironmentVariables</key><dict>${environmentEntries(layout, xml, serviceFile)}</dict>
<key>KeepAlive</key><dict><key>PathState</key><dict><key>${xml(runtimeServiceEnableMarkerPath(layout.dataDir))}</key><true/></dict></dict><key>ProcessType</key><string>Interactive</string>
${redirects}</dict></plist>
`;
}

/**
 * Exact prior declarations that a managed LaunchAgent may legitimately have on
 * disk. The redirect lines were added after the first shipped hourly packages,
 * so an existing managed registration is recognized by byte-for-byte match with
 * one of these shapes and upgraded, instead of being reported as
 * `runtime_service_file_modified`. Anything else is a user edit and is refused.
 */
export function priorLaunchAgentDeclarations(
  layout: RuntimeInstallLayout,
): string[] {
  if (layout.platform !== "darwin") return [];
  // Two shipped shapes must migrate, not be refused as "user modified":
  //   1. no redirect at all (the original declaration), and
  //   2. the shape that carried StandardOutPath/StandardErrorPath -- shipped
  //      while launchd still owned the log descriptor. That shape is exactly
  //      what the H34 ruling removes, so every installed-from-package user has
  //      it and must be migrated rather than locked out.
  const serviceId = serviceLabelFor(layout);
  const serviceFile = path.posix.join(
    layout.home,
    "Library",
    "LaunchAgents",
    `${serviceId}.plist`,
  );
  const current = launchAgentDeclaration(layout, serviceId, serviceFile);
  const legacy = legacyLaunchAgentDeclaration(layout, serviceId);
  // Shape 2: the same declaration plus the two redirect keys launchd used to
  // own. Built by inserting the keys rather than re-deriving, so it stays
  // byte-exact even as the legacy shape changes.
  const logs = path.posix.join(layout.dataDir, "logs");
  const withRedirects = legacy.replace(
    "</dict></plist>",
    `<key>StandardOutPath</key><string>${xml(path.posix.join(logs, "service.log"))}</string>
<key>StandardErrorPath</key><string>${xml(path.posix.join(logs, "service-error.log"))}</string>
</dict></plist>`,
  );
  return [current, legacy, withRedirects];
}

function legacyLaunchAgentDeclaration(
  layout: RuntimeInstallLayout,
  serviceId: string,
): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>${serviceId}</string>
<key>ProgramArguments</key><array><string>${xml(layout.nodeCommand)}</string><string>${xml(layout.runtimeEntry)}</string><string>serve</string></array>
<key>EnvironmentVariables</key><dict>${Object.entries(
    legacyRuntimeEnvironment(layout),
  )
    .map(([key, value]) => `<key>${key}</key><string>${xml(value)}</string>`)
    .join("")}</dict>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ProcessType</key><string>Interactive</string>
</dict></plist>
`;
}

function systemdPlan(
  layout: RuntimeInstallLayout,
  xdgConfigHome: string | undefined,
): RuntimeServicePlan {
  const config = path.posix.resolve(
    xdgConfigHome?.trim() || path.posix.join(layout.home, ".config"),
  );
  const target = path.posix.join(
    config,
    "systemd",
    "user",
    "one-memory.service",
  );
  const content = `[Unit]
Description=One Memory Runtime

[Service]
Type=simple
UMask=0077
ExecStart=${systemdWord(layout.nodeCommand)} ${systemdWord(layout.runtimeEntry)} serve
${environmentLines(layout)}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
`;
  return ready(layout, "one-memory.service", target, content, null, {
    install: [
      ["systemctl", "--user", "daemon-reload"],
      ["systemctl", "--user", "enable", "--now", target],
    ],
    start: [["systemctl", "--user", "start", "one-memory.service"]],
    restart: [["systemctl", "--user", "restart", "one-memory.service"]],
    stop: [["systemctl", "--user", "stop", "one-memory.service"]],
    uninstall: [
      ["systemctl", "--user", "disable", "--now", "one-memory.service"],
      ["systemctl", "--user", "daemon-reload"],
    ],
  });
}

function runtimeEnvironment(layout: RuntimeInstallLayout) {
  return {
    HOME: layout.home,
    ...legacyRuntimeEnvironment(layout),
    ONE_MEMORY_HOST_HOME: layout.home,
    ONE_MEMORY_SERVICE_OWNER_FILE: runtimeServiceOwnerPath(layout.dataDir),
    ONE_MEMORY_SERVICE_ENABLE_MARKER: runtimeServiceEnableMarkerPath(
      layout.dataDir,
    ),
  };
}

function legacyRuntimeEnvironment(layout: RuntimeInstallLayout) {
  return {
    ONE_MEMORY_RUNTIME_ENTRY: layout.runtimeEntry,
    ONE_MEMORY_DATA_DIR: layout.dataDir,
    ONE_MEMORY_CORE_COMMAND: layout.coreCommand,
    ONE_MEMORY_MCP_ENTRY: layout.mcpEntryPath,
    ONE_MEMORY_RECALL_CLI: layout.recallCliPath,
    ONE_MEMORY_SYNC_HOOK_ASSETS: layout.syncHookAssetsDirectory,
    ONE_MEMORY_NODE_COMMAND: layout.nodeCommand,
    // launchd starts the Runtime, so the port override only works if these keys
    // are in the plist. The daily install has no `hourlyIsolation`, so its plist
    // keeps exactly the seven keys above and still uses 8765.
    ...(layout.hourlyIsolation
      ? {
          ONE_MEMORY_HOURLY_INSTANCE_ID: layout.hourlyIsolation.instanceId,
          ONE_MEMORY_HOURLY_PACKAGE_ID: layout.hourlyIsolation.packageId,
        }
      : {}),
    ...(layout.corePortOverride === undefined
      ? {}
      : { ONE_MEMORY_CORE_PORT: String(layout.corePortOverride) }),
    ...(layout.brokerPortOverride === undefined
      ? {}
      : { ONE_MEMORY_BROKER_PORT: String(layout.brokerPortOverride) }),
  };
}

function environmentEntries(
  layout: RuntimeInstallLayout,
  escapeValue: (value: string) => string,
  serviceFile: string,
): string {
  return Object.entries({
    ...runtimeEnvironment(layout),
    ONE_MEMORY_SERVICE_FILE: serviceFile,
  })
    .map(
      ([key, value]) =>
        `<key>${key}</key><string>${escapeValue(value)}</string>`,
    )
    .join("");
}

function environmentLines(layout: RuntimeInstallLayout): string {
  return Object.entries(runtimeEnvironment(layout))
    .map(([key, value]) => `Environment=${systemdWord(`${key}=${value}`)}`)
    .join("\n");
}

function systemdWord(value: string): string {
  if (/\0|\r|\n/.test(value)) throw new Error("runtime_service_path_invalid");
  return `"${value.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

function xml(value: string): string {
  if (/\0/.test(value)) throw new Error("runtime_service_path_invalid");
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function ready(
  layout: RuntimeInstallLayout,
  serviceId: string,
  target: string,
  content: string,
  logDirectory: string | null,
  commands: RuntimeServicePlan["commands"],
): RuntimeServicePlan {
  return {
    schema_version: 1,
    platform: layout.platform,
    scope: "user",
    service_id: serviceId,
    status: "ready",
    blocked_reason: null,
    core_port: layout.corePortOverride ?? DEFAULT_CORE_PORT,
    service_file: { path: target, mode: 0o600, content },
    log_directory: logDirectory,
    commands,
  };
}

function blocked(
  layout: RuntimeInstallLayout,
  reason: string,
  serviceId: string,
): RuntimeServicePlan {
  return {
    schema_version: 1,
    platform: layout.platform,
    scope: "user",
    service_id: serviceId,
    status: "blocked",
    blocked_reason: reason,
    core_port: layout.corePortOverride ?? DEFAULT_CORE_PORT,
    service_file: null,
    log_directory: null,
    commands: { install: [], start: [], restart: [], stop: [], uninstall: [] },
  };
}
