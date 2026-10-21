import { AsyncLocalStorage } from "node:async_hooks";
import { createHash, randomUUID } from "node:crypto";
import { constants, type Stats } from "node:fs";
import * as fs from "node:fs/promises";
import path from "node:path";
import type {
  BatchJournal,
  BatchLedger,
  BatchOwner,
} from "./connection-batch.js";

const MAX_BYTES = 512 * 1024;
const READ = constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK;
const CREATE =
  constants.O_WRONLY |
  constants.O_CREAT |
  constants.O_EXCL |
  constants.O_NOFOLLOW;
type Identity = { dev: number; ino: number };
type Lease = {
  active: boolean;
  poisoned: boolean;
  tail: Promise<void>;
  identity: Identity;
  nonce: string;
};
type Binding = BatchOwner & {
  schemaVersion: 1;
  dataDev: number;
  dataIno: number;
};

/** Trusted control callers provide a stable, already-verified data-instance owner.
 * This store never derives identity from PID, creates grants or repairs unknown files. */
export class PersistentBatchLedger implements BatchLedger {
  readonly durability = "persistent" as const;
  private readonly context = new AsyncLocalStorage<Lease>();
  private readonly directory: string;
  private constructor(
    private readonly dataDir: string,
    private readonly binding: Binding,
    private readonly dataIdentity: Identity,
    private readonly directoryIdentity: Identity,
  ) {
    this.directory = path.join(dataDir, "connection-batches");
  }

  /** Explicit first creation only. Existing/incomplete stores must use open, never reset. */
  static async initialize(
    dataDir: string,
    owner: BatchOwner,
  ): Promise<PersistentBatchLedger> {
    const checked = checkedOwner(owner);
    const root = await checkedRoot(dataDir);
    const directory = path.join(dataDir, "connection-batches");
    await fs.mkdir(directory, { mode: 0o700 });
    const info = await fs.lstat(directory);
    privateDirectory(info);
    const binding: Binding = {
      schemaVersion: 1,
      ...checked,
      dataDev: root.dev,
      dataIno: root.ino,
    };
    const ledger = new PersistentBatchLedger(dataDir, binding, root, info);
    await ledger.checkDirectories();
    await writeNew(path.join(directory, "owner.json"), JSON.stringify(binding));
    await syncDirectory(directory);
    await syncDirectory(dataDir);
    await ledger.check();
    return ledger;
  }

  static async open(
    dataDir: string,
    owner: BatchOwner,
  ): Promise<PersistentBatchLedger> {
    const checked = checkedOwner(owner);
    const root = await checkedRoot(dataDir);
    const directory = path.join(dataDir, "connection-batches");
    const info = await fs.lstat(directory);
    privateDirectory(info);
    const value = record(
      await readJson(path.join(directory, "owner.json"), 2048),
    );
    exact(value, [
      "schemaVersion",
      "userId",
      "runtimeId",
      "dataDev",
      "dataIno",
    ]);
    if (
      value.schemaVersion !== 1 ||
      value.userId !== checked.userId ||
      value.runtimeId !== checked.runtimeId ||
      value.dataDev !== root.dev ||
      value.dataIno !== root.ino
    )
      fail("owner_mismatch");
    const ledger = new PersistentBatchLedger(
      dataDir,
      value as unknown as Binding,
      root,
      info,
    );
    await ledger.check();
    return ledger;
  }

  async exclusive<T>(
    owner: BatchOwner,
    operation: () => Promise<T>,
  ): Promise<T> {
    this.matchOwner(owner);
    await this.check();
    const lock = path.join(this.directory, "execution.lock");
    try {
      await fs.mkdir(lock, { mode: 0o700 });
    } catch (error) {
      // No age/PID-based takeover: even a dead process can have left an unknown effect.
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
    // Incomplete acquisition intentionally remains fenced if this durable owner write fails.
    await writeNew(
      path.join(lock, "owner.json"),
      JSON.stringify({ ...this.owner(), pid: process.pid, nonce: lease.nonce }),
    );
    await syncDirectory(lock);
    await syncDirectory(this.directory);
    await this.checkLease(lease);
    try {
      return await this.context.run(lease, operation);
    } finally {
      lease.active = false;
      await lease.tail;
      if (lease.poisoned) fail("recovery_required");
      await this.checkLease(lease);
      await fs.unlink(path.join(lock, "owner.json"));
      await fs.rmdir(lock);
      await syncDirectory(this.directory);
    }
  }

  async load(
    owner: BatchOwner,
    operationId: string,
  ): Promise<BatchJournal | null> {
    this.matchOwner(owner);
    identifier(operationId);
    await this.check();
    let value: unknown;
    try {
      value = await readJson(this.file(operationId), MAX_BYTES);
    } catch (error) {
      await this.check();
      if (hasCode(error, "ENOENT")) return null;
      throw error;
    }
    const result = checkedJournal(value, this.owner(), operationId);
    await this.check();
    return result;
  }

  async commit(
    owner: BatchOwner,
    operationId: string,
    expectedRevision: number | null,
    next: BatchJournal,
  ): Promise<void> {
    this.matchOwner(owner);
    identifier(operationId);
    const value = checkedJournal(
      structuredClone(next),
      this.owner(),
      operationId,
    );
    if (expectedRevision !== null) integer(expectedRevision, 1);
    if (value.revision !== (expectedRevision ?? 0) + 1)
      fail("revision_conflict");
    const lease = this.context.getStore();
    if (!lease?.active || lease.poisoned) fail("lock_required");
    const previous = lease.tail;
    const operation = previous.then(() =>
      this.publish(lease, operationId, expectedRevision, value),
    );
    lease.tail = operation.then(
      () => {},
      () => {},
    );
    return operation;
  }

  private async publish(
    lease: Lease,
    operationId: string,
    expected: number | null,
    next: BatchJournal,
  ) {
    if (lease.poisoned) fail("recovery_required");
    await this.checkLease(lease);
    const current = await this.load(this.owner(), operationId);
    if ((current?.revision ?? null) !== expected) fail("revision_conflict");
    if (current) {
      if (current.planDigest !== next.planDigest) fail("operation_conflict");
      if (current.items.length !== next.items.length) fail("history_conflict");
      for (const [index, item] of current.items.entries()) {
        const replacement = next.items[index];
        if (
          item.id !== replacement.id ||
          item.kind !== replacement.kind ||
          item.intentDigest !== replacement.intentDigest
        )
          fail("history_conflict");
        if (
          ["succeeded", "rejected", "changed", "not_applied"].includes(
            item.state,
          ) &&
          canonical(item) !== canonical(replacement)
        )
          fail("history_conflict");
        if (
          ["in_flight", "unknown"].includes(item.state) &&
          [
            "pending",
            "in_flight",
            "unavailable",
            "dependency_blocked",
          ].includes(replacement.state) &&
          item.state !== replacement.state
        )
          fail("history_conflict");
      }
    }
    const target = this.file(operationId);
    const original = current ? await fs.lstat(target) : null;
    const temporary = path.join(this.directory, `.pending-${randomUUID()}`);
    let temporaryIdentity: Identity | null = null;
    let published = false;
    try {
      temporaryIdentity = await writeNew(temporary, JSON.stringify(next));
      await this.checkLease(lease);
      if (original) {
        const latest = await fs.lstat(target);
        privateFile(latest);
        if (!same(original, latest)) fail("revision_conflict");
        await fs.rename(temporary, target);
      } else {
        // POSIX rename overwrites: hard-link publication is atomic NOREPLACE for create.
        await fs.link(temporary, target);
        published = true;
        await fs.unlink(temporary);
      }
      published = true;
      await syncDirectory(this.directory);
      await this.checkLease(lease);
      privateFile(await fs.lstat(target));
    } catch (error) {
      // After publication, an fsync error is unknown durability, never rollback success.
      if (published) lease.poisoned = true;
      throw error;
    } finally {
      if (temporaryIdentity) {
        await this.checkDirectories();
        const remaining = await fs.lstat(temporary).catch((error) => {
          if (hasCode(error, "ENOENT")) return null;
          throw error;
        });
        if (remaining && same(remaining, temporaryIdentity))
          await fs.unlink(temporary);
      }
    }
  }

  private owner(): BatchOwner {
    return { userId: this.binding.userId, runtimeId: this.binding.runtimeId };
  }
  private matchOwner(owner: BatchOwner) {
    const checked = checkedOwner(owner);
    if (
      checked.userId !== this.binding.userId ||
      checked.runtimeId !== this.binding.runtimeId
    )
      fail("owner_mismatch");
  }
  private file(operationId: string) {
    return path.join(
      this.directory,
      `${createHash("sha256")
        .update(
          JSON.stringify([
            this.binding.userId,
            this.binding.runtimeId,
            operationId,
          ]),
        )
        .digest("hex")}.json`,
    );
  }
  private async checkDirectories() {
    const root = await checkedRoot(this.dataDir);
    const directory = await fs.lstat(this.directory);
    privateDirectory(directory);
    if (
      !same(root, this.dataIdentity) ||
      !same(directory, this.directoryIdentity)
    )
      fail("directory_changed");
  }
  private async check() {
    await this.checkDirectories();
    const binding = await readJson(
      path.join(this.directory, "owner.json"),
      2048,
    );
    if (canonical(binding) !== canonical(this.binding)) fail("owner_mismatch");
    await this.checkDirectories();
  }
  private async checkLease(lease: Lease) {
    await this.check();
    const lock = path.join(this.directory, "execution.lock");
    const info = await fs.lstat(lock);
    privateDirectory(info);
    if (!same(info, lease.identity)) fail("recovery_required");
    const value = await readJson(path.join(lock, "owner.json"), 2048);
    if (
      canonical(value) !==
      canonical({ ...this.owner(), pid: process.pid, nonce: lease.nonce })
    )
      fail("recovery_required");
  }
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
    (info.mode & 0o777) !== 0o700
  )
    fail("directory_unsafe");
}
function privateFile(info: Stats) {
  if (
    !info.isFile() ||
    info.isSymbolicLink() ||
    info.nlink !== 1 ||
    info.uid !== process.getuid?.() ||
    (info.mode & 0o777) !== 0o600
  )
    fail("file_unsafe");
}
function same(a: Identity, b: Identity) {
  return a.dev === b.dev && a.ino === b.ino;
}
async function readJson(file: string, maximum: number): Promise<unknown> {
  const handle = await fs.open(file, READ);
  try {
    const before = await handle.stat();
    privateFile(before);
    if (before.size > maximum) fail("size_exceeded");
    const buffer = Buffer.alloc(maximum + 1);
    let length = 0;
    while (length < buffer.length) {
      const { bytesRead } = await handle.read(
        buffer,
        length,
        buffer.length - length,
        length,
      );
      if (!bytesRead) break;
      length += bytesRead;
    }
    const after = await handle.stat();
    privateFile(after);
    if (
      length > maximum ||
      before.size !== after.size ||
      before.mtimeMs !== after.mtimeMs ||
      before.ctimeMs !== after.ctimeMs
    )
      fail("file_changed");
    const value: unknown = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(
        buffer.subarray(0, length),
      ),
    );
    if (!same(after, await fs.lstat(file))) fail("file_changed");
    return value;
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
    return info;
  } finally {
    await handle.close();
  }
}
async function syncDirectory(directory: string) {
  const handle = await fs.open(
    directory,
    constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW,
  );
  try {
    privateDirectory(await handle.stat());
    await handle.sync();
  } finally {
    await handle.close();
  }
}
function checkedOwner(input: BatchOwner): BatchOwner {
  const value = record(input);
  exact(value, ["userId", "runtimeId"]);
  identifier(value.userId);
  identifier(value.runtimeId);
  return {
    userId: value.userId as string,
    runtimeId: value.runtimeId as string,
  };
}
function checkedJournal(
  input: unknown,
  owner: BatchOwner,
  operationId: string,
): BatchJournal {
  const value = record(input);
  exact(value, [
    "schemaVersion",
    "userId",
    "runtimeId",
    "operationId",
    "planDigest",
    "revision",
    "items",
  ]);
  if (
    value.schemaVersion !== 1 ||
    value.userId !== owner.userId ||
    value.runtimeId !== owner.runtimeId ||
    value.operationId !== operationId
  )
    fail("owner_mismatch");
  hash(value.planDigest);
  integer(value.revision, 1);
  if (
    !Array.isArray(value.items) ||
    !value.items.length ||
    value.items.length > 96
  )
    fail("journal_invalid");
  const ids = new Set<string>();
  for (const candidate of value.items) {
    const row = record(candidate);
    exact(row, ["id", "kind", "intentDigest", "state", "receipt"]);
    identifier(row.id);
    hash(row.intentDigest);
    if (ids.has(row.id as string)) fail("journal_invalid");
    ids.add(row.id as string);
    if (
      !["sync", "install", "readGrant"].includes(String(row.kind)) ||
      ![
        "pending",
        "in_flight",
        "succeeded",
        "unknown",
        "rejected",
        "changed",
        "not_applied",
        "unavailable",
        "dependency_blocked",
      ].includes(String(row.state))
    )
      fail("journal_invalid");
    if (row.state !== "succeeded") {
      if (row.receipt !== null) fail("journal_invalid");
      continue;
    }
    const receipt = record(row.receipt);
    const base = [
      "userId",
      "runtimeId",
      "operationId",
      "itemId",
      "intentDigest",
      "kind",
    ];
    if (
      receipt.userId !== owner.userId ||
      receipt.runtimeId !== owner.runtimeId ||
      receipt.operationId !== operationId ||
      receipt.itemId !== row.id ||
      receipt.intentDigest !== row.intentDigest ||
      receipt.kind !== row.kind
    )
      fail("journal_invalid");
    if (row.kind === "sync") {
      exact(receipt, [
        ...base,
        "sourceId",
        "rootId",
        "grantRevision",
        "syncRevision",
        "enabled",
      ]);
      identifier(receipt.sourceId);
      identifier(receipt.rootId);
      integer(receipt.grantRevision, 1);
      integer(receipt.syncRevision, 0);
      if (typeof receipt.enabled !== "boolean") fail("journal_invalid");
    } else {
      exact(receipt, [
        ...base,
        "host",
        ...(row.kind === "readGrant" ? ["allowedTools", "allowedScopes"] : []),
      ]);
      const host = record(receipt.host);
      exact(host, [
        "hostId",
        "layoutDigest",
        "installationId",
        "permissionRevision",
        "installationDigest",
      ]);
      identifier(host.hostId);
      identifier(host.installationId);
      hash(host.layoutDigest);
      hash(host.installationDigest);
      integer(host.permissionRevision, 1);
      if (row.kind === "readGrant") {
        stringSet(receipt.allowedTools, 5, (value) =>
          [
            "om_recall",
            "om_ask",
            "om_conversations",
            "om_matters",
            "om_diagnostic_trace",
          ].includes(value),
        );
        stringSet(
          receipt.allowedScopes,
          64,
          (value) =>
            value === "all-apps" ||
            /^workspace:v1:[a-f0-9]{64}$/.test(value) ||
            /^source:[a-z0-9][a-z0-9-]{0,127}$/.test(value),
        );
      }
    }
  }
  if (Buffer.byteLength(JSON.stringify(value)) > MAX_BYTES)
    fail("size_exceeded");
  return structuredClone(value) as unknown as BatchJournal;
}
function stringSet(
  value: unknown,
  maximum: number,
  allowed: (value: string) => boolean,
) {
  if (
    !Array.isArray(value) ||
    !value.length ||
    value.length > maximum ||
    new Set(value).size !== value.length ||
    value.some((item) => typeof item !== "string" || !allowed(item))
  )
    fail("journal_invalid");
}
function record(value: unknown): Record<string, unknown> {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.getPrototypeOf(value) !== Object.prototype
  )
    fail("journal_invalid");
  return value as Record<string, unknown>;
}
function exact(value: Record<string, unknown>, keys: string[]) {
  if (
    Object.keys(value).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(value, key))
  )
    fail("journal_invalid");
}
function identifier(value: unknown) {
  if (
    typeof value !== "string" ||
    !/^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$/.test(value)
  )
    fail("journal_invalid");
}
function hash(value: unknown) {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value))
    fail("journal_invalid");
}
function integer(value: unknown, minimum: number) {
  if (
    !Number.isSafeInteger(value) ||
    (value as number) < minimum ||
    (value as number) >= Number.MAX_SAFE_INTEGER
  )
    fail("journal_invalid");
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
  throw new Error(`connection_batch_ledger_${code}`);
}
