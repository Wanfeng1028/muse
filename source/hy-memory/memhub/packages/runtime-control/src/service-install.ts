import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { constants, type Stats } from "node:fs";
import {
  access,
  type FileHandle,
  link,
  lstat,
  mkdir,
  open,
  realpath,
  rename,
  unlink,
} from "node:fs/promises";
import path from "node:path";
import {
  disableRuntimeService,
  enableRuntimeService,
  readRuntimeServiceOwner,
  runtimeServiceEnableMarkerPath,
} from "./service-ownership.js";
import type {
  RuntimeInstallLayout,
  RuntimeServicePlan,
} from "./service-plan.js";
import {
  planUserService,
  priorLaunchAgentDeclarations,
} from "./service-plan.js";

export type ServiceCommandRunner = (
  command: readonly string[],
) => Promise<void>;

/**
 * `disabled` is a distinct, durable OS state: `launchctl disable` records a
 * persistent override, after which `bootstrap` of the same label fails with
 * exit 5 and the job never loads (verified on macOS 15.1). It is NOT `absent`,
 * because installing over it would silently undo the user's or the system's
 * decision. Nothing here ever calls `launchctl enable`.
 */
export type ServiceRegistrationState =
  | "absent"
  | "managed"
  | "conflict"
  | "disabled";

export type ServiceRegistrationInspector = (
  plan: RuntimeServicePlan,
) => Promise<ServiceRegistrationState>;

interface ServiceOptions {
  uid?: number;
  xdgConfigHome?: string;
  runCommand?: ServiceCommandRunner;
  inspectRegistration?: ServiceRegistrationInspector;
  inspectLinuxState?: (
    serviceId: string,
  ) => Promise<{ code: number | null; stdout: string }>;
  platform?: NodeJS.Platform;
}

export async function installUserService(
  layout: RuntimeInstallLayout,
  options: ServiceOptions = {},
): Promise<RuntimeServicePlan> {
  return installUserServiceInternal(layout, options);
}

/** Internal safety harness for the future managed release implementation. */
export async function installUserServiceInternal(
  layout: RuntimeInstallLayout,
  options: ServiceOptions = {},
): Promise<RuntimeServicePlan> {
  const plan = planUserService(layout, options);
  if (plan.status !== "ready" || plan.service_file === null) {
    throw new Error(plan.blocked_reason ?? "runtime_service_plan_blocked");
  }
  if (layout.platform !== (options.platform ?? process.platform)) {
    throw new Error("runtime_service_platform_mismatch");
  }
  for (const required of [
    layout.nodeCommand,
    layout.runtimeEntry,
    layout.coreCommand,
    layout.mcpEntryPath,
    layout.recallCliPath,
    path.join(layout.syncHookAssetsDirectory, "manifest.json"),
  ]) {
    await access(required).catch(() => {
      throw new Error("runtime_service_install_root_not_ready");
    });
  }
  const target = plan.service_file.path;
  const parent = path.dirname(target);
  await mkdir(parent, { recursive: true, mode: 0o700 });
  const directory = await assertSafeParent(parent);
  const existing = await statIfPresent(target);
  const registration =
    layout.platform === "darwin"
      ? await inspectRegistration(
          plan,
          options.inspectRegistration ?? inspectLaunchAgentRegistration,
        )
      : "absent";
  if (registration === "conflict") {
    throw new Error("runtime_service_label_conflict");
  }
  // A disabled service must not be silently re-enabled. `bootstrap` would fail
  // with exit 5 anyway, but that generic error hides the real cause and invites
  // a caller to "fix" it by re-enabling, which is exactly what the product
  // forbids. Report the durable OS state instead.
  if (registration === "disabled") {
    throw new Error("runtime_service_disabled_by_system");
  }
  // The LaunchAgent redirects stdout/stderr into this directory; launchd will
  // not create it. Only do this once the label is known not to be a foreign
  // registration, so a conflict never leaves new artifacts behind.
  await prepareServiceLogDirectory(plan);
  const markerExisted = await statIfPresent(
    runtimeServiceEnableMarkerPath(layout.dataDir),
  );
  const run = options.runCommand ?? runServiceCommand;
  const content = plan.service_file.content;
  if (existing) {
    if (layout.platform !== "darwin") {
      throw new Error("runtime_service_file_exists");
    }
    if (registration === "absent") {
      const owner = await readRuntimeServiceOwner(layout.dataDir).catch(
        () => null,
      );
      if (owner === null) throw new Error("runtime_service_file_exists");
      await verifyFile(target, content, existing);
      await enableRuntimeService(layout.dataDir);
      try {
        await activateManagedDeclaration(
          target,
          content,
          parent,
          directory,
          run,
          plan.commands.install,
        );
      } catch (error) {
        if (markerExisted === null) {
          await disableRuntimeService(layout.dataDir).catch(() => undefined);
        }
        throw error;
      }
      return plan;
    }
    if (registration !== "managed") {
      throw new Error("runtime_service_file_exists");
    }
    try {
      await verifyFile(target, content, existing);
    } catch (currentError) {
      // A managed registration may still hold an earlier shipped declaration
      // (e.g. the LaunchAgent before stdout/stderr redirects existed). Migrate
      // it exactly; anything else is a user edit and must fail closed.
      const legacy = priorLaunchAgentDeclarations(layout);
      try {
        await verifyFileOneOf(target, legacy, existing);
      } catch {
        throw currentError;
      }
      await rewriteManagedDeclaration(
        target,
        content,
        legacy,
        existing,
        parent,
        directory,
      );
      await enableRuntimeService(layout.dataDir);
      try {
        // launchd keeps serving the declaration it loaded, so a changed plist is
        // only picked up by booting the job out and bootstrapping again.
        // `bootout` is allowed to fail because the label may not be loaded yet.
        // `enable` is deliberately not called: a system or user disable must
        // survive an upgrade instead of being silently undone.
        for (const command of plan.commands.stop) {
          await assertSafeParent(parent, directory);
          await runAllowedToFail(run, command);
          await assertSafeParent(parent, directory);
          await verifyFile(target, content, await lstat(target));
        }
        await activateManagedDeclaration(
          target,
          content,
          parent,
          directory,
          run,
          plan.commands.install,
        );
      } catch (error) {
        if (markerExisted === null) {
          await disableRuntimeService(layout.dataDir).catch(() => undefined);
        }
        throw error;
      }
      return plan;
    }
    await enableRuntimeService(layout.dataDir);
    try {
      for (const command of plan.commands.restart) {
        await assertSafeParent(parent, directory);
        await verifyFile(target, content, existing);
        await runCheckedCommand(run, command);
        await assertSafeParent(parent, directory);
        await verifyFile(target, content, existing);
      }
    } catch (error) {
      if (markerExisted === null) {
        await disableRuntimeService(layout.dataDir).catch(() => undefined);
      }
      throw error;
    }
    return plan;
  }
  const temporary = `${target}.${randomUUID()}.tmp`;
  const commands =
    registration === "managed" ? plan.commands.restart : plan.commands.install;
  let handle: FileHandle | undefined;
  let owned: Stats | undefined;
  let prepared = false;
  let published = false;
  let temporaryPresent = false;
  let markerEnabled = false;
  try {
    await assertSafeParent(parent, directory);
    handle = await open(
      temporary,
      constants.O_CREAT |
        constants.O_EXCL |
        constants.O_WRONLY |
        constants.O_NOFOLLOW,
      0o600,
    );
    temporaryPresent = true;
    await handle.chmod(0o600);
    owned = await handle.stat();
    await handle.writeFile(content, "utf8");
    await handle.sync();
    prepared = true;
    await assertSafeParent(parent, directory);
    await verifyFile(temporary, content, owned, 1);
    // Hard-link publication is atomic NOREPLACE; rename would overwrite a racer.
    await link(temporary, target);
    published = true;
    await assertSafeParent(parent, directory);
    await verifyFile(target, content, owned, 2);
    await verifyFile(temporary, content, owned, 2);
    await unlink(temporary);
    temporaryPresent = false;
    // Keep the post-publication handle state as the stable snapshot. The
    // pre-write/pre-link stat cannot prove that later commands left this exact
    // declaration untouched, while path metadata may still be stale on CephFS.
    owned = await handle.stat();
    await syncDirectory(parent, directory);
    await enableRuntimeService(layout.dataDir);
    markerEnabled = true;
    for (const command of commands) {
      await assertSafeParent(parent, directory);
      await verifyPublishedFile(target, content, handle, owned);
      await runCheckedCommand(run, command);
      await assertSafeParent(parent, directory);
      await verifyPublishedFile(target, content, handle, owned);
    }
    return plan;
  } catch (error) {
    // Unknown directory durability is not rollback success. Never uninstall an
    // OS service here: a failed command may have affected a pre-existing label.
    if (
      error instanceof Error &&
      error.message === "runtime_service_durability_unknown"
    )
      throw error;
    if (owned && prepared && handle) {
      await assertSafeParent(parent, directory);
      if (published) {
        if (temporaryPresent) {
          await verifyFile(target, content, owned, 2);
        } else {
          await verifyPublishedFile(target, content, handle, owned);
        }
        if (temporaryPresent) await verifyFile(temporary, content, owned, 2);
        await unlink(target);
      }
      if (temporaryPresent) {
        await verifyFile(temporary, content, owned);
        await unlink(temporary);
      }
      await syncDirectory(parent, directory);
    }
    if (markerEnabled && markerExisted === null) {
      await disableRuntimeService(layout.dataDir).catch(() => undefined);
    }
    throw error;
  } finally {
    await handle?.close();
  }
}

export async function uninstallUserService(
  layout: RuntimeInstallLayout,
  options: ServiceOptions = {},
): Promise<"removed" | "not-installed"> {
  const plan = planUserService(layout, options);
  if (plan.status !== "ready" || plan.service_file === null) {
    throw new Error(plan.blocked_reason ?? "runtime_service_plan_blocked");
  }
  if (layout.platform !== (options.platform ?? process.platform)) {
    throw new Error("runtime_service_platform_mismatch");
  }
  const target = plan.service_file.path;
  const info = await statIfPresent(target);
  if (info === null) {
    await disableRuntimeService(layout.dataDir);
    return "not-installed";
  }
  const parent = path.dirname(target);
  const directory = await assertSafeParent(parent);
  await verifyFile(target, plan.service_file.content, info);
  const run = options.runCommand ?? runServiceCommand;
  const marker = runtimeServiceEnableMarkerPath(layout.dataDir);
  const markerExisted = await statIfPresent(marker);
  await disableRuntimeService(layout.dataDir);
  try {
    for (const command of plan.commands.uninstall) {
      await assertSafeParent(parent, directory);
      await verifyFile(target, plan.service_file.content, info);
      // `launchctl bootout` fails with exit 5 for a label that is not currently
      // loaded (e.g. the user disabled the service, or it was already stopped and
      // booted out; verified on macOS 15.1). That is "already stopped", not a
      // failed uninstall. Tolerate it only when the job really is not loaded;
      // otherwise surface the failure instead of silently leaving a live job and
      // deleting its declaration.
      await uninstallBootout(run, command, plan, options.inspectLinuxState);
      await assertSafeParent(parent, directory);
      await verifyFile(target, plan.service_file.content, info);
    }
  } catch (error) {
    if (markerExisted !== null) {
      await enableRuntimeService(layout.dataDir).catch(() => undefined);
    }
    throw error;
  }
  await unlink(target);
  await syncDirectory(parent, directory);
  return "removed";
}

export async function restartUserService(
  layout: RuntimeInstallLayout,
  options: ServiceOptions = {},
): Promise<RuntimeServicePlan> {
  const plan = planUserService(layout, options);
  if (plan.status !== "ready" || plan.service_file === null) {
    throw new Error(plan.blocked_reason ?? "runtime_service_plan_blocked");
  }
  if (layout.platform !== (options.platform ?? process.platform)) {
    throw new Error("runtime_service_platform_mismatch");
  }
  const info = await statIfPresent(plan.service_file.path);
  if (!info?.isFile() || info.isSymbolicLink()) {
    throw new Error("runtime_service_not_installed");
  }
  const parent = path.dirname(plan.service_file.path);
  const directory = await assertSafeParent(parent);
  await verifyFile(plan.service_file.path, plan.service_file.content, info);
  const run = options.runCommand ?? runServiceCommand;
  for (const command of plan.commands.restart) {
    await assertSafeParent(parent, directory);
    await verifyFile(plan.service_file.path, plan.service_file.content, info);
    await runCheckedCommand(run, command);
    await assertSafeParent(parent, directory);
    await verifyFile(plan.service_file.path, plan.service_file.content, info);
  }
  return plan;
}

function sameIdentity(left: Stats, right: Stats): boolean {
  return (
    left.dev === right.dev &&
    left.ino === right.ino &&
    left.mode === right.mode &&
    left.uid === right.uid &&
    left.gid === right.gid
  );
}

async function statIfPresent(target: string): Promise<Stats | null> {
  try {
    return await lstat(target);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

/**
 * Atomically replace a managed declaration whose exact prior bytes are already
 * known, then re-check identity. Used only for an in-place migration of the
 * LaunchAgent to the current declaration shape.
 */
async function rewriteManagedDeclaration(
  target: string,
  content: string,
  accepted: readonly string[],
  before: Stats,
  parent: string,
  directory: Stats,
): Promise<void> {
  await assertSafeParent(parent, directory);
  await verifyFileOneOf(target, accepted, before);
  const temporary = `${target}.${randomUUID()}.migrate`;
  const handle = await open(
    temporary,
    constants.O_CREAT |
      constants.O_EXCL |
      constants.O_WRONLY |
      constants.O_NOFOLLOW,
    0o600,
  );
  let owned: Stats | undefined;
  try {
    await handle.chmod(0o600);
    owned = await handle.stat();
    await handle.writeFile(content, "utf8");
    await handle.sync();
  } finally {
    await handle.close();
  }
  try {
    await assertSafeParent(parent, directory);
    await verifyFile(temporary, content, owned, 1);
    await rename(temporary, target);
  } catch (error) {
    await lstat(temporary)
      .then((info) => (info.isFile() ? unlink(temporary) : undefined))
      .catch(() => undefined);
    throw error;
  }
  await assertSafeParent(parent, directory);
  await verifyFile(target, content, owned, 1);
  await syncDirectory(parent, directory);
}

async function activateManagedDeclaration(
  target: string,
  content: string,
  parent: string,
  directory: Stats,
  run: ServiceCommandRunner,
  commands: readonly string[][],
): Promise<void> {
  for (const command of commands) {
    await assertSafeParent(parent, directory);
    const info = await lstat(target);
    await verifyFile(target, content, info);
    await runCheckedCommand(run, command);
    await assertSafeParent(parent, directory);
    const after = await lstat(target);
    await verifyFile(target, content, after);
  }
}

/**
 * launchd refuses to start a LaunchAgent whose StandardOutPath/StandardErrorPath
 * parent does not exist, and it will not create the file itself. Prepare an
 * owner-only directory plus both files so a login start always has somewhere to
 * write, and so the redirect can never downgrade to a world-writable path.
 */
async function prepareServiceLogDirectory(
  plan: RuntimeServicePlan,
): Promise<void> {
  if (plan.log_directory === null) return;
  await mkdir(plan.log_directory, { recursive: true, mode: 0o700 });
  await assertSafeParent(plan.log_directory);
  for (const name of ["service.log", "service-error.log"]) {
    const target = path.join(plan.log_directory, name);
    try {
      const handle = await open(
        target,
        constants.O_CREAT |
          constants.O_EXCL |
          constants.O_WRONLY |
          constants.O_NOFOLLOW,
        0o600,
      );
      try {
        await handle.chmod(0o600);
      } finally {
        await handle.close();
      }
    } catch (error) {
      // A concurrent install may have created the file between our check and
      // the exclusive open; validate whatever is there instead of failing.
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    }
    const info = await statIfPresent(target);
    if (
      info === null ||
      !info.isFile() ||
      info.isSymbolicLink() ||
      (info.mode & 0o7777) !== 0o600 ||
      (typeof process.getuid === "function" && info.uid !== process.getuid())
    ) {
      throw new Error("runtime_service_log_unmanaged");
    }
  }
}

async function assertSafeParent(
  target: string,
  expected?: Stats,
): Promise<Stats> {
  const info = await lstat(target);
  if (
    !info.isDirectory() ||
    info.isSymbolicLink() ||
    (expected !== undefined && !sameIdentity(info, expected)) ||
    (process.platform !== "win32" &&
      ((info.mode & 0o022) !== 0 ||
        (typeof process.getuid === "function" &&
          info.uid !== process.getuid())))
  ) {
    throw new Error("runtime_service_directory_unsafe");
  }
  return info;
}

async function verifyFile(
  target: string,
  content: string,
  expected: Stats,
  links = 1,
): Promise<void> {
  await verifyFileOneOf(target, [content], expected, links);
}

/**
 * Accept any of several exact declarations. Used for the LaunchAgent, where a
 * managed registration may still hold a prior shipped declaration shape; the
 * installer then rewrites it. A declaration matching none of the accepted
 * shapes is a user edit and fails closed.
 */
async function verifyFileOneOf(
  target: string,
  contents: readonly string[],
  expected: Stats,
  links = 1,
): Promise<void> {
  const before = await lstat(target);
  if (
    !before.isFile() ||
    before.isSymbolicLink() ||
    (before.mode & 0o7777) !== 0o600 ||
    before.nlink !== links ||
    !sameIdentity(before, expected) ||
    (process.getuid && before.uid !== process.getuid())
  ) {
    throw new Error("runtime_service_file_unmanaged");
  }
  const file = await open(
    target,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
  );
  try {
    const opened = await file.stat();
    if (!opened.isFile() || !sameFileState(opened, before))
      throw new Error("runtime_service_file_unmanaged");
    const expectedBytes = contents.map((content) =>
      Buffer.from(content, "utf8"),
    );
    if (!expectedBytes.some((bytes) => bytes.length === opened.size))
      throw new Error("runtime_service_file_modified");
    const readLimit =
      Math.max(...expectedBytes.map((bytes) => bytes.length)) + 1;
    const bytes = Buffer.alloc(readLimit);
    let total = 0;
    while (total < bytes.length) {
      const { bytesRead } = await file.read({
        buffer: bytes,
        offset: total,
        length: bytes.length - total,
        position: total,
      });
      if (bytesRead === 0) break;
      total += bytesRead;
    }
    const finished = await file.stat();
    const after = await lstat(target);
    if (!sameFileState(finished, opened) || !sameFileState(after, opened))
      throw new Error("runtime_service_file_unmanaged");
    if (
      !expectedBytes.some(
        (candidate) =>
          total === candidate.length &&
          bytes.subarray(0, total).equals(candidate),
      )
    )
      throw new Error("runtime_service_file_modified");
  } finally {
    await file.close();
  }
}

/** Verify a declaration published from a file handle this process still owns.
 *
 * CephFS may briefly return stale link-count and ctime data from `lstat(path)`
 * after the temporary hard link is removed, even though `fstat(handle)` already
 * reports the authoritative single-link state. The open handle is stronger
 * identity evidence than path timestamps: while it remains open, a replacement
 * inode cannot reuse its dev/inode pair. Keep the path checks for type,
 * ownership, permissions and exact bytes, but take identity and link count from
 * the retained handle instead of guessing how quickly path metadata converges.
 */
async function verifyPublishedFile(
  target: string,
  content: string,
  ownedHandle: FileHandle,
  expected: Stats,
): Promise<void> {
  const authoritative = await ownedHandle.stat();
  if (
    !authoritative.isFile() ||
    authoritative.nlink !== 1 ||
    !sameFileState(authoritative, expected) ||
    (authoritative.mode & 0o7777) !== 0o600 ||
    (process.getuid && authoritative.uid !== process.getuid())
  ) {
    throw new Error("runtime_service_file_unmanaged");
  }
  const before = await lstat(target);
  if (
    !before.isFile() ||
    before.isSymbolicLink() ||
    !sameIdentity(before, authoritative) ||
    (before.mode & 0o7777) !== 0o600 ||
    (process.getuid && before.uid !== process.getuid())
  ) {
    throw new Error("runtime_service_file_unmanaged");
  }
  const file = await open(
    target,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
  );
  try {
    const opened = await file.stat();
    if (!opened.isFile() || !sameIdentity(opened, authoritative)) {
      throw new Error("runtime_service_file_unmanaged");
    }
    const expectedBytes = Buffer.from(content, "utf8");
    if (opened.size !== expectedBytes.length) {
      throw new Error("runtime_service_file_modified");
    }
    const bytes = Buffer.alloc(expectedBytes.length + 1);
    let total = 0;
    while (total < bytes.length) {
      const { bytesRead } = await file.read({
        buffer: bytes,
        offset: total,
        length: bytes.length - total,
        position: total,
      });
      if (bytesRead === 0) break;
      total += bytesRead;
    }
    const finished = await file.stat();
    const after = await lstat(target);
    const finalAuthoritative = await ownedHandle.stat();
    if (
      !sameIdentity(finished, authoritative) ||
      !sameIdentity(after, authoritative) ||
      !sameFileState(finalAuthoritative, authoritative) ||
      finalAuthoritative.nlink !== 1
    ) {
      throw new Error("runtime_service_file_unmanaged");
    }
    if (
      total !== expectedBytes.length ||
      !bytes.subarray(0, total).equals(expectedBytes)
    ) {
      throw new Error("runtime_service_file_modified");
    }
  } finally {
    await file.close();
  }
}

function sameFileState(left: Stats, right: Stats): boolean {
  return (
    sameIdentity(left, right) &&
    left.nlink === right.nlink &&
    left.size === right.size &&
    left.mtimeMs === right.mtimeMs &&
    left.ctimeMs === right.ctimeMs
  );
}

async function runCheckedCommand(
  run: ServiceCommandRunner,
  command: readonly string[],
): Promise<void> {
  try {
    await run(command);
  } catch {
    throw new Error("runtime_service_command_failed");
  }
}

/**
 * A bootout for a label that is not currently loaded is a no-op failure, not a
 * lost update. Callers must have already verified the declaration on disk.
 */
async function runAllowedToFail(
  run: ServiceCommandRunner,
  command: readonly string[],
): Promise<void> {
  try {
    await run(command);
  } catch {
    // Intentionally ignored: absence of the label is acceptable here.
  }
}

/** Run `bootout`, treating "not currently loaded" as success but never a
 * genuine failure. Only the exact managed declaration reaches this point.
 *
 * The re-probe asks the OS directly whether the job is loaded. A job that is
 * `disable`d but not loaded is the common case here (the user turned the
 * service off), and `bootout` reports that as exit 5. A job that is still
 * loaded after a failed `bootout` is a real failure and must surface.
 */
async function uninstallBootout(
  run: ServiceCommandRunner,
  command: readonly string[],
  plan: RuntimeServicePlan,
  inspectLinuxState?: (
    serviceId: string,
  ) => Promise<{ code: number | null; stdout: string }>,
): Promise<void> {
  try {
    await run(command);
    return;
  } catch (error) {
    if (
      plan.platform === "linux" &&
      command[0] === "systemctl" &&
      command.includes("disable") &&
      (await linuxServiceDisabledAndStopped(
        plan.service_id,
        inspectLinuxState ?? inspectLinuxServiceState,
      ))
    ) {
      return;
    }
    const domain = plan.commands.install[0]?.[2];
    if (plan.platform !== "darwin" || !domain) throw error;
    const probe = await runServiceProbe([
      "launchctl",
      "print",
      `${domain}/${plan.service_id}`,
    ]).catch(() => null);
    // 113 means the label is not loaded: nothing left to stop.
    if (probe?.code === 113) return;
    throw error;
  }
}

/** A failed `systemctl disable --now` may still have reached its exact target.
 *
 * systemd returns non-zero when the unit became absent while the command was
 * stopping/disabling it. Treat that as idempotent success only after two
 * independent probes agree that the unit is no longer enabled and no process
 * is active. Any enabled/active/unparseable state remains a hard failure, so a
 * live service declaration is never deleted on the strength of an exit code.
 */
async function linuxServiceDisabledAndStopped(
  serviceId: string,
  inspect: (
    serviceId: string,
  ) => Promise<{ code: number | null; stdout: string }>,
): Promise<boolean> {
  const state = await inspect(serviceId).catch(() => null);
  if (state?.code !== 0) return false;
  const properties = Object.fromEntries(
    state.stdout
      .split(/\r?\n/)
      .map((line) => line.split("=", 2))
      .filter((entry) => entry.length === 2),
  );
  const load = properties.LoadState?.toLowerCase();
  const unitFile = properties.UnitFileState?.toLowerCase();
  const active = properties.ActiveState?.toLowerCase();
  const disabled =
    load === "not-found" ||
    ["disabled", "masked", "not-found"].includes(unitFile ?? "");
  const stopped = ["inactive", "failed"].includes(active ?? "");
  return disabled && stopped;
}

async function inspectLinuxServiceState(
  serviceId: string,
): Promise<{ code: number | null; stdout: string }> {
  return runServiceProbe([
    "systemctl",
    "--user",
    "show",
    serviceId,
    "--property=LoadState",
    "--property=UnitFileState",
    "--property=ActiveState",
    "--no-pager",
  ]);
}

async function inspectLaunchAgentRegistration(
  plan: RuntimeServicePlan,
): Promise<ServiceRegistrationState> {
  if (plan.platform !== "darwin" || plan.service_file === null) return "absent";
  const domain = plan.commands.install[0]?.[2];
  if (!domain) throw new Error("runtime_service_inspection_failed");
  // A persistent `launchctl disable` override must be detected before we treat
  // the label as installable. `print` returns 113 for a disabled-but-unloaded
  // job, which would otherwise look exactly like `absent`; bootstrapping it
  // then fails with exit 5. Read the override table first so a disabled service
  // is never silently re-enabled or misreported as a fresh install.
  if (await launchAgentIsDisabled(domain, plan.service_id)) return "disabled";
  const result = await runServiceProbe([
    "launchctl",
    "print",
    `${domain}/${plan.service_id}`,
  ]);
  if (result.code === 113) return "absent";
  if (result.code !== 0) throw new Error("runtime_service_inspection_failed");
  // launchd reports the resolved plist path, which can differ textually from
  // the user-facing one (e.g. /private/var vs /var, symlinked HOME). Compare
  // real paths so a genuine managed registration is never misread as conflict.
  const wanted = await resolvedPath(plan.service_file.path);
  const declared = parseLaunchctlPlistPath(result.stdout);
  if (declared === null) return "conflict";
  return (await resolvedPath(declared)) === wanted ? "managed" : "conflict";
}

/** True when launchd currently records a `disable` override for this label.
 *
 * `launchctl print-disabled <domain>` exits 0 and lists every override as
 * `"<label>" => disabled|enabled`. Any failure to read the table is reported as
 * "not disabled" so the caller keeps its existing fail-closed behavior on the
 * subsequent `print`/`bootstrap` rather than inventing a state.
 */
async function launchAgentIsDisabled(
  domain: string,
  serviceId: string,
): Promise<boolean> {
  const result = await runServiceProbe(["launchctl", "print-disabled", domain]);
  if (result.code !== 0) return false;
  return parseDisabledOverride(result.stdout, serviceId);
}

/** Parse `launchctl print-disabled <domain>` output for one label.
 * A label absent from the table has no override and is treated as not disabled.
 */
export function parseDisabledOverride(
  stdout: string,
  serviceId: string,
): boolean {
  const quoted = `"${serviceId}"`;
  for (const line of stdout.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith(quoted)) continue;
    const value = trimmed
      .slice(quoted.length)
      .replace(/^\s*=>\s*/, "")
      .trim();
    return value === "disabled";
  }
  return false;
}

/** Extract the `path = ...` line launchctl prints for a loaded job. */
export function parseLaunchctlPlistPath(stdout: string): string | null {
  for (const line of stdout.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("path = ")) continue;
    const value = trimmed.slice("path = ".length).trim();
    const unquoted =
      value.length >= 2 && value.startsWith('"') && value.endsWith('"')
        ? value.slice(1, -1)
        : value;
    if (unquoted.startsWith("/")) return unquoted;
  }
  return null;
}

async function resolvedPath(target: string): Promise<string> {
  return realpath(target).catch(() => target);
}

async function inspectRegistration(
  plan: RuntimeServicePlan,
  inspect: ServiceRegistrationInspector,
): Promise<ServiceRegistrationState> {
  try {
    const state = await inspect(plan);
    if (
      state === "absent" ||
      state === "managed" ||
      state === "conflict" ||
      state === "disabled"
    ) {
      return state;
    }
  } catch {
    // Registration probing is a trust boundary; never expose launchctl output.
  }
  throw new Error("runtime_service_inspection_failed");
}

async function runServiceProbe(
  command: readonly string[],
): Promise<{ code: number | null; stdout: string }> {
  const [program, ...args] = command;
  if (!program) throw new Error("runtime_service_inspection_failed");
  return new Promise((resolve, reject) => {
    const child = spawn(program, args, {
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "ignore"],
    });
    const chunks: Buffer[] = [];
    let size = 0;
    child.stdout.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > 64 * 1024) {
        child.kill();
        return;
      }
      chunks.push(chunk);
    });
    child.once("error", () =>
      reject(new Error("runtime_service_inspection_failed")),
    );
    child.once("close", (code) => {
      if (size > 64 * 1024) {
        reject(new Error("runtime_service_inspection_failed"));
        return;
      }
      resolve({ code, stdout: Buffer.concat(chunks).toString("utf8") });
    });
  });
}

async function syncDirectory(target: string, expected: Stats): Promise<void> {
  await assertSafeParent(target, expected);
  let directory: FileHandle;
  try {
    directory = await open(
      target,
      constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW,
    );
  } catch {
    throw new Error("runtime_service_durability_unknown");
  }
  try {
    if (!sameIdentity(await directory.stat(), expected))
      throw new Error("runtime_service_directory_unsafe");
    try {
      await directory.sync();
    } catch {
      throw new Error("runtime_service_durability_unknown");
    }
    await assertSafeParent(target, expected);
  } finally {
    await directory.close();
  }
}

async function runServiceCommand(command: readonly string[]): Promise<void> {
  const [program, ...args] = command;
  if (!program) throw new Error("runtime_service_command_invalid");
  await new Promise<void>((resolve, reject) => {
    const child = spawn(program, args, {
      shell: false,
      windowsHide: true,
      stdio: "ignore",
    });
    child.once("error", () =>
      reject(new Error("runtime_service_command_failed")),
    );
    child.once("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error("runtime_service_command_failed"));
    });
  });
}
