import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";
import { constants, type Stats } from "node:fs";
import * as fs from "node:fs/promises";
import path from "node:path";
import {
  type BackgroundOperationLedger,
  type BackgroundOperationSnapshot,
  type BackgroundOwner,
  validateBackgroundOwner,
  validateBackgroundSnapshot,
  validateBackgroundTransition,
} from "./background-operation.js";

const MAX_BYTES = 256 * 1024;
const READ = constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK;
const CREATE =
  constants.O_WRONLY |
  constants.O_CREAT |
  constants.O_EXCL |
  constants.O_NOFOLLOW;
type Identity = { dev: number; ino: number };
type Binding = BackgroundOwner & {
  schemaVersion: 1;
  dataDev: number;
  dataIno: number;
};
type Lease = {
  active: boolean;
  poisoned: boolean;
  tail: Promise<void>;
  identity: Identity;
  nonce: string;
};

/** One stable data-instance owner; this module never performs service actions.
 * Lock directories are persistent fences, not age/PID-based takeover candidates.
 */
export class PersistentBackgroundOperationLedger
  implements BackgroundOperationLedger
{
  readonly durability = "persistent" as const;
  private readonly context = new AsyncLocalStorage<Lease>();
  private readonly directory: string;
  private constructor(
    private readonly dataDir: string,
    private readonly binding: Binding,
    private readonly rootIdentity: Identity,
    private readonly directoryIdentity: Identity,
  ) {
    this.directory = path.join(dataDir, "background-operations");
  }

  static async initialize(
    dataDir: string,
    owner: BackgroundOwner,
  ): Promise<PersistentBackgroundOperationLedger> {
    const checked = checkedOwner(owner);
    const root = await checkedRoot(dataDir);
    const directory = path.join(dataDir, "background-operations");
    await fs.mkdir(directory, { mode: 0o700 });
    const info = await fs.lstat(directory);
    privateDirectory(info);
    const binding: Binding = {
      schemaVersion: 1,
      ...checked,
      dataDev: root.dev,
      dataIno: root.ino,
    };
    const ledger = new PersistentBackgroundOperationLedger(
      dataDir,
      binding,
      root,
      info,
    );
    await ledger.checkDirectories();
    await writeNew(path.join(directory, "owner.json"), JSON.stringify(binding));
    await syncDirectory(directory, info);
    await syncDirectory(dataDir, root);
    await ledger.check();
    return ledger;
  }

  static async open(
    dataDir: string,
    owner: BackgroundOwner,
  ): Promise<PersistentBackgroundOperationLedger> {
    const checked = checkedOwner(owner);
    const root = await checkedRoot(dataDir);
    const directory = path.join(dataDir, "background-operations");
    const info = await fs.lstat(directory);
    privateDirectory(info);
    const { value } = await readJson(path.join(directory, "owner.json"), 2048);
    const expected: Binding = {
      schemaVersion: 1,
      ...checked,
      dataDev: root.dev,
      dataIno: root.ino,
    };
    if (canonical(value) !== canonical(expected)) fail("owner_mismatch");
    const ledger = new PersistentBackgroundOperationLedger(
      dataDir,
      expected,
      root,
      info,
    );
    await ledger.check();
    return ledger;
  }

  async exclusive<T>(
    owner: BackgroundOwner,
    run: () => Promise<T>,
  ): Promise<T> {
    this.matchOwner(owner);
    await this.check();
    const lock = path.join(this.directory, "execution.lock");
    try {
      await fs.mkdir(lock, { mode: 0o700 });
    } catch (error) {
      if (hasCode(error, "EEXIST")) fail("recovery_required");
      throw error;
    }
    const identity = await fs.lstat(lock);
    privateDirectory(identity);
    const lease: Lease = {
      active: true,
      poisoned: false,
      tail: Promise.resolve(),
      identity,
      nonce: randomUUID(),
    };
    // Failed acquisition stays fenced; do not clean an unverified/partially durable lock.
    await writeNew(
      path.join(lock, "owner.json"),
      JSON.stringify(this.lockOwner(lease)),
    );
    await syncDirectory(lock, identity);
    await syncDirectory(this.directory, this.directoryIdentity);
    await this.checkLease(lease);
    try {
      return await this.context.run(lease, run);
    } finally {
      lease.active = false;
      await lease.tail;
      if (lease.poisoned) fail("recovery_required");
      await this.checkLease(lease);
      await fs.unlink(path.join(lock, "owner.json"));
      await fs.rmdir(lock);
      await syncDirectory(this.directory, this.directoryIdentity);
    }
  }

  async load(
    owner: BackgroundOwner,
  ): Promise<BackgroundOperationSnapshot | null> {
    this.matchOwner(owner);
    return (await this.readState())?.snapshot ?? null;
  }

  async commit(
    owner: BackgroundOwner,
    expectedRevision: number | null,
    next: BackgroundOperationSnapshot,
  ): Promise<void> {
    this.matchOwner(owner);
    const value = validateBackgroundSnapshot(next, this.owner());
    if (
      expectedRevision !== null &&
      (!Number.isSafeInteger(expectedRevision) ||
        expectedRevision < 1 ||
        expectedRevision >= Number.MAX_SAFE_INTEGER)
    )
      fail("revision_conflict");
    if (value.revision !== (expectedRevision ?? 0) + 1)
      fail("revision_conflict");
    const lease = this.context.getStore();
    if (!lease?.active || lease.poisoned) fail("lock_required");
    const operation = lease.tail.then(() =>
      this.publish(lease, expectedRevision, value),
    );
    lease.tail = operation.then(
      () => {},
      () => {},
    );
    return operation;
  }

  private async readState(): Promise<{
    snapshot: BackgroundOperationSnapshot;
    identity: Stats;
  } | null> {
    await this.check();
    let entry: Awaited<ReturnType<typeof readJson>>;
    try {
      entry = await readJson(
        path.join(this.directory, "state.json"),
        MAX_BYTES,
      );
    } catch (error) {
      await this.check();
      if (hasCode(error, "ENOENT")) return null;
      throw error;
    }
    const snapshot = validateBackgroundSnapshot(entry.value, this.owner());
    await this.check();
    return { snapshot, identity: entry.identity };
  }

  private async publish(
    lease: Lease,
    expected: number | null,
    next: BackgroundOperationSnapshot,
  ): Promise<void> {
    if (lease.poisoned) fail("recovery_required");
    await this.checkLease(lease);
    const current = await this.readState();
    if ((current?.snapshot.revision ?? null) !== expected)
      fail("revision_conflict");
    validateBackgroundTransition(current?.snapshot ?? null, next, this.owner());
    const target = path.join(this.directory, "state.json");
    const temporary = path.join(this.directory, `.pending-${randomUUID()}`);
    let identity: Identity | null = null;
    let published = false;
    try {
      identity = await writeNew(temporary, JSON.stringify(next));
      await this.checkLease(lease);
      if (current) {
        const latest = await readJson(target, MAX_BYTES);
        if (
          !sameFile(latest.identity, current.identity) ||
          canonical(latest.value) !== canonical(current.snapshot)
        )
          fail("revision_conflict");
        await fs.rename(temporary, target);
      } else {
        await fs.link(temporary, target);
        published = true;
        await fs.unlink(temporary);
      }
      published = true;
      await syncDirectory(this.directory, this.directoryIdentity);
      await this.checkLease(lease);
      const stored = await readJson(target, MAX_BYTES);
      if (
        !same(identity, stored.identity) ||
        canonical(stored.value) !== canonical(next)
      )
        fail("publication_changed");
    } catch (error) {
      if (published) lease.poisoned = true;
      throw error;
    } finally {
      if (identity) {
        await this.checkDirectories();
        const remaining = await fs.lstat(temporary).catch((error) => {
          if (hasCode(error, "ENOENT")) return null;
          throw error;
        });
        if (remaining) {
          if (!same(remaining, identity)) fail("recovery_required");
          privateFile(remaining);
          await fs.unlink(temporary);
        }
      }
    }
  }

  private owner(): BackgroundOwner {
    return { userId: this.binding.userId, runtimeId: this.binding.runtimeId };
  }
  private lockOwner(lease: Lease) {
    return { ...this.owner(), pid: process.pid, nonce: lease.nonce };
  }
  private matchOwner(owner: BackgroundOwner) {
    const checked = checkedOwner(owner);
    if (
      checked.userId !== this.binding.userId ||
      checked.runtimeId !== this.binding.runtimeId
    )
      fail("owner_mismatch");
  }
  private async checkDirectories(): Promise<void> {
    const root = await checkedRoot(this.dataDir);
    const directory = await fs.lstat(this.directory);
    privateDirectory(directory);
    if (
      !same(root, this.rootIdentity) ||
      !same(directory, this.directoryIdentity)
    )
      fail("directory_changed");
  }
  private async check(): Promise<void> {
    await this.checkDirectories();
    const { value } = await readJson(
      path.join(this.directory, "owner.json"),
      2048,
    );
    if (canonical(value) !== canonical(this.binding)) fail("owner_mismatch");
    await this.checkDirectories();
  }
  private async checkLease(lease: Lease): Promise<void> {
    await this.check();
    const lock = path.join(this.directory, "execution.lock");
    const info = await fs.lstat(lock);
    privateDirectory(info);
    if (!same(info, lease.identity)) fail("recovery_required");
    const { value } = await readJson(path.join(lock, "owner.json"), 2048);
    if (canonical(value) !== canonical(this.lockOwner(lease)))
      fail("recovery_required");
  }
}

function checkedOwner(owner: BackgroundOwner): BackgroundOwner {
  validateBackgroundOwner(owner);
  return { userId: owner.userId, runtimeId: owner.runtimeId };
}
async function checkedRoot(dataDir: string): Promise<Stats> {
  if (process.platform === "win32" || typeof process.getuid !== "function")
    fail("platform_unsupported");
  if (
    !path.isAbsolute(dataDir) ||
    path.resolve(dataDir) !== dataDir ||
    (await fs.realpath(dataDir)) !== dataDir
  )
    fail("directory_unsafe");
  const info = await fs.lstat(dataDir);
  privateDirectory(info);
  return info;
}
function privateDirectory(info: Stats) {
  if (
    !info.isDirectory() ||
    info.isSymbolicLink() ||
    info.uid !== process.getuid?.() ||
    (info.mode & 0o7777) !== 0o700
  )
    fail("directory_unsafe");
}
function privateFile(info: Stats) {
  if (
    !info.isFile() ||
    info.isSymbolicLink() ||
    info.nlink !== 1 ||
    info.uid !== process.getuid?.() ||
    (info.mode & 0o7777) !== 0o600
  )
    fail("file_unsafe");
}
function same(a: Identity, b: Identity) {
  return a.dev === b.dev && a.ino === b.ino;
}
function sameFile(a: Stats, b: Stats) {
  return (
    same(a, b) &&
    a.mode === b.mode &&
    a.uid === b.uid &&
    a.gid === b.gid &&
    a.nlink === b.nlink &&
    a.size === b.size &&
    a.mtimeMs === b.mtimeMs &&
    a.ctimeMs === b.ctimeMs
  );
}
async function readJson(
  file: string,
  maximum: number,
): Promise<{ value: unknown; identity: Stats }> {
  const handle = await fs.open(file, READ);
  try {
    const before = await handle.stat();
    privateFile(before);
    if (before.size > maximum) fail("size_exceeded");
    const buffer = Buffer.alloc(maximum + 1);
    let length = 0;
    while (length < buffer.length) {
      const { bytesRead } = await handle.read({
        buffer,
        offset: length,
        length: buffer.length - length,
        position: length,
      });
      if (!bytesRead) break;
      length += bytesRead;
    }
    const after = await handle.stat();
    privateFile(after);
    const named = await fs.lstat(file);
    privateFile(named);
    if (
      length > maximum ||
      length !== after.size ||
      !sameFile(before, after) ||
      !sameFile(after, named)
    )
      fail("file_changed");
    let value: unknown;
    try {
      value = JSON.parse(
        new TextDecoder("utf-8", { fatal: true }).decode(
          buffer.subarray(0, length),
        ),
      );
    } catch {
      return fail("invalid_json");
    }
    return { value, identity: after };
  } finally {
    await handle.close();
  }
}
async function writeNew(file: string, text: string): Promise<Identity> {
  if (Buffer.byteLength(text) > MAX_BYTES) fail("size_exceeded");
  const handle = await fs.open(file, CREATE, 0o600);
  try {
    await handle.writeFile(text, "utf8");
    await handle.sync();
    const info = await handle.stat();
    privateFile(info);
    if (!sameFile(info, await fs.lstat(file))) fail("file_changed");
    return info;
  } finally {
    await handle.close();
  }
}
async function syncDirectory(
  directory: string,
  expected: Identity,
): Promise<void> {
  const handle = await fs.open(
    directory,
    constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW,
  );
  try {
    const info = await handle.stat();
    privateDirectory(info);
    if (!same(info, expected)) fail("directory_changed");
    await handle.sync();
    const named = await fs.lstat(directory);
    privateDirectory(named);
    if (!same(info, named)) fail("directory_changed");
  } finally {
    await handle.close();
  }
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object")
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`,
      )
      .join(",")}}`;
  return JSON.stringify(value);
}
function hasCode(error: unknown, code: string) {
  return (
    !!error &&
    typeof error === "object" &&
    "code" in error &&
    error.code === code
  );
}
function fail(code: string): never {
  throw new Error(`background_operation_ledger_${code}`);
}
