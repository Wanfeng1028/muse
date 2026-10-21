import { spawn } from "node:child_process";
import * as fs from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, expect, it, vi } from "vitest";
import {
  type BatchAdapters,
  type BatchJournal,
  ConnectionBatch,
  type ConnectionPlan,
  connectionPlanDigest,
} from "./connection-batch.js";
import { PersistentBatchLedger } from "./connection-batch-ledger.js";

vi.mock("node:fs/promises", async (original) => {
  const actual = await original<typeof import("node:fs/promises")>();
  return { ...actual, rename: vi.fn(actual.rename), open: vi.fn(actual.open) };
});

const owner = { userId: "local", runtimeId: "verified-data-instance" };
const roots: string[] = [];
const digest = "a".repeat(64);
const source = {
  sourceId: "cursor",
  rootId: "root",
  rootPath: "/fixture",
  grantRevision: 1,
};
const host = {
  hostId: "cursor",
  layoutDigest: digest,
  installationId: null,
  permissionRevision: 0,
  installationDigest: null,
};
function journal(revision = 1): BatchJournal {
  return {
    schemaVersion: 1,
    ...owner,
    operationId: "operation-one",
    planDigest: digest,
    revision,
    items: [
      {
        id: "install",
        kind: "install",
        intentDigest: digest,
        state: "pending",
        receipt: null,
      },
    ],
  };
}
async function fixture() {
  const root = await fs.realpath(
    await fs.mkdtemp(path.join(tmpdir(), "batch-ledger-")),
  );
  roots.push(root);
  await fs.chmod(root, 0o700);
  const ledger = await PersistentBatchLedger.initialize(root, owner);
  return { root, ledger, directory: path.join(root, "connection-batches") };
}
async function create(ledger: PersistentBatchLedger) {
  await ledger.exclusive(owner, () =>
    ledger.commit(owner, "operation-one", null, journal()),
  );
}
async function journalPath(directory: string) {
  const names = await fs.readdir(directory);
  return path.join(
    directory,
    names.find((n) => /^[a-f0-9]{64}\.json$/.test(n)) ?? "missing",
  );
}
afterEach(async () => {
  vi.restoreAllMocks();
  await Promise.all(
    roots
      .splice(0)
      .map((root) => fs.rm(root, { recursive: true, force: true })),
  );
});
it("persists private journals, reloads stable owner, and enforces create/update CAS", async () => {
  const { root, ledger, directory } = await fixture();
  expect(await ledger.load(owner, "operation-one")).toBeNull();
  await create(ledger);
  expect((await fs.stat(directory)).mode & 0o777).toBe(0o700);
  expect((await fs.stat(await journalPath(directory))).mode & 0o777).toBe(
    0o600,
  );
  const reopened = await PersistentBatchLedger.open(root, owner);
  expect(await reopened.load(owner, "operation-one")).toEqual(journal());
  await expect(
    reopened.exclusive(owner, () =>
      reopened.commit(owner, "operation-one", null, journal()),
    ),
  ).rejects.toThrow("revision_conflict");
  await reopened.exclusive(owner, () =>
    reopened.commit(owner, "operation-one", 1, journal(2)),
  );
  await expect(
    ledger.exclusive(owner, () =>
      ledger.commit(owner, "operation-one", 1, journal(2)),
    ),
  ).rejects.toThrow("revision_conflict");
  expect((await ledger.load(owner, "operation-one"))?.revision).toBe(2);
});
it("excludes separate executors across all operations, and releases after failure", async () => {
  const { root, ledger } = await fixture();
  const other = await PersistentBatchLedger.open(root, owner);
  let release!: () => void;
  let entered!: () => void;
  const ready = new Promise<void>((r) => {
    entered = r;
  });
  const effect = vi.fn();
  const held = ledger.exclusive(owner, async () => {
    entered();
    await new Promise<void>((r) => {
      release = r;
    });
  });
  await ready;
  await expect(
    other.exclusive(owner, async () => {
      effect();
    }),
  ).rejects.toThrow("recovery_required");
  expect(effect).not.toHaveBeenCalled();
  release();
  await held;
  await expect(
    ledger.exclusive(owner, async () => {
      throw Error("effect failure");
    }),
  ).rejects.toThrow("effect failure");
  await other.exclusive(owner, async () => {
    effect();
  });
  expect(effect).toHaveBeenCalledTimes(1);
});
it("requires explicit initialization and exact owner; owner loss is not a fresh store", async () => {
  const { root, directory, ledger } = await fixture();
  await expect(
    PersistentBatchLedger.open(root, { ...owner, runtimeId: "different" }),
  ).rejects.toThrow("owner_mismatch");
  await expect(
    ledger.load({ ...owner, userId: "other" }, "operation-one"),
  ).rejects.toThrow("owner_mismatch");
  await fs.unlink(path.join(directory, "owner.json"));
  await expect(PersistentBatchLedger.open(root, owner)).rejects.toThrow();
  await expect(PersistentBatchLedger.initialize(root, owner)).rejects.toThrow();
});
it("rejects caller paths, extra fields, bad digest/revision, and preserves successful history", async () => {
  const { ledger } = await fixture();
  await expect(ledger.load(owner, "../../outside")).rejects.toThrow();
  await ledger.exclusive(owner, async () => {
    await expect(
      ledger.commit(owner, "operation-one", null, {
        ...journal(),
        secret: "x",
      } as BatchJournal),
    ).rejects.toThrow();
    await ledger.commit(owner, "operation-one", null, journal());
    await expect(
      ledger.commit(owner, "operation-one", 1, {
        ...journal(2),
        planDigest: "b".repeat(64),
      }),
    ).rejects.toThrow("operation_conflict");
    const succeeded = journal(2);
    succeeded.items[0] = {
      ...succeeded.items[0],
      state: "succeeded",
      receipt: {
        ...owner,
        operationId: "operation-one",
        itemId: "install",
        intentDigest: digest,
        kind: "install",
        host: {
          ...host,
          installationId: "installation-one",
          permissionRevision: 1,
          installationDigest: "b".repeat(64),
        },
      },
    };
    await ledger.commit(owner, "operation-one", 1, succeeded);
    await expect(
      ledger.commit(owner, "operation-one", 2, journal(3)),
    ).rejects.toThrow("history_conflict");
  });
});
it.each(["corrupt", "wide", "symlink", "hardlink", "oversized"])(
  "rejects %s journal instead of replacing it",
  async (kind) => {
    const { ledger, directory } = await fixture();
    await create(ledger);
    const file = await journalPath(directory);
    if (kind === "corrupt") await fs.writeFile(file, "{");
    if (kind === "wide") await fs.chmod(file, 0o644);
    if (kind === "oversized") await fs.writeFile(file, "x".repeat(600000));
    if (kind === "hardlink")
      await fs.link(file, path.join(directory, "linked"));
    if (kind === "symlink") {
      await fs.rename(file, `${file}.old`);
      await fs.symlink(`${file}.old`, file);
    }
    await expect(ledger.load(owner, "operation-one")).rejects.toThrow();
    await expect(
      ledger.exclusive(owner, () =>
        ledger.commit(owner, "operation-one", 1, journal(2)),
      ),
    ).rejects.toThrow();
  },
);
it("refuses directory inode replacement and never steals stale/malformed lock", async () => {
  const { root, ledger, directory } = await fixture();
  await fs.mkdir(path.join(directory, "execution.lock"), { mode: 0o700 });
  await expect(ledger.exclusive(owner, async () => {})).rejects.toThrow(
    "recovery_required",
  );
  await fs.rmdir(path.join(directory, "execution.lock"));
  await fs.rename(directory, `${directory}.old`);
  await fs.mkdir(directory, { mode: 0o700 });
  await expect(ledger.load(owner, "operation-one")).rejects.toThrow(
    "directory_changed",
  );
  expect(await fs.readdir(directory)).toEqual([]);
  await expect(PersistentBatchLedger.open(root, owner)).rejects.toThrow();
});
it("failure before publish preserves old bytes and allows safe reload", async () => {
  const { root, ledger, directory } = await fixture();
  await create(ledger);
  const file = await journalPath(directory),
    before = await fs.readFile(file);
  vi.spyOn(fs, "rename").mockRejectedValueOnce(new Error("injected IO"));
  await expect(
    ledger.exclusive(owner, () =>
      ledger.commit(owner, "operation-one", 1, journal(2)),
    ),
  ).rejects.toThrow();
  expect(await fs.readFile(file)).toEqual(before);
  expect(
    await (await PersistentBatchLedger.open(root, owner)).load(
      owner,
      "operation-one",
    ),
  ).toEqual(journal());
});
it("does not permit unlocked commits or mutate journals supplied by callers during awaits", async () => {
  const { ledger } = await fixture();
  await expect(
    ledger.commit(owner, "operation-one", null, journal()),
  ).rejects.toThrow("lock_required");
  await ledger.exclusive(owner, async () => {
    const value = journal();
    const commit = ledger.commit(owner, "operation-one", null, value);
    value.planDigest = "b".repeat(64);
    await commit;
  });
  expect((await ledger.load(owner, "operation-one"))?.planDigest).toBe(digest);
});

it.each([
  "root-mode",
  "store-mode",
  "owner-mode",
  "owner-link",
  "owner-corrupt",
  "store-link",
])("fails closed for %s without fixing user files", async (kind) => {
  const { root, ledger, directory } = await fixture();
  const file = path.join(directory, "owner.json");
  if (kind === "root-mode") await fs.chmod(root, 0o755);
  if (kind === "store-mode") await fs.chmod(directory, 0o755);
  if (kind === "owner-mode") await fs.chmod(file, 0o644);
  if (kind === "owner-corrupt") await fs.writeFile(file, "{}");
  if (kind === "owner-link") await fs.link(file, path.join(directory, "alias"));
  if (kind === "store-link") {
    await fs.rename(directory, `${directory}.old`);
    await fs.symlink(`${directory}.old`, directory);
  }
  await expect(ledger.load(owner, "operation-one")).rejects.toThrow();
  await expect(PersistentBatchLedger.open(root, owner)).rejects.toThrow();
});

it("recovers a real install executor without repeating its external effect", async () => {
  const { root, ledger } = await fixture();
  const plan: ConnectionPlan = {
    schemaVersion: 1,
    ...owner,
    operationId: "effect",
    items: [
      {
        id: "install",
        kind: "install",
        sources: [source],
        host,
        previewFingerprint: digest,
      },
    ],
  };
  const apply = vi.fn(async (_item, context) => ({
    status: "succeeded" as const,
    receipt: {
      userId: context.userId,
      runtimeId: context.runtimeId,
      operationId: context.operationId,
      itemId: context.itemId,
      intentDigest: context.intentDigest,
      kind: "install" as const,
      host: {
        ...host,
        installationId: "installation-one",
        permissionRevision: 1,
        installationDigest: "b".repeat(64),
      },
    },
  }));
  const adapters: BatchAdapters = {
    inspect: async () => ({
      status: "ready",
      sources: [source],
      host,
      previewFingerprint: digest,
    }),
    install: {
      apply,
      reconcile: async () => ({ status: "unknown" }),
    },
    readGrant: {
      apply: async () => ({ status: "unknown" }),
      reconcile: async () => ({ status: "unknown" }),
    },
  };
  const options = {
    mode: "execute" as const,
    userConfirmed: true,
    planDigest: connectionPlanDigest(plan),
  };
  expect(
    (await new ConnectionBatch(owner, adapters, ledger).run(plan, options))
      .state,
  ).toBe("completed");
  const reopened = await PersistentBatchLedger.open(root, owner);
  expect(
    (await new ConnectionBatch(owner, adapters, reopened).run(plan, options))
      .state,
  ).toBe("completed");
  expect(apply).toHaveBeenCalledTimes(1);
});

it("serializes concurrent commits inside the same admitted lease", async () => {
  const { ledger } = await fixture();
  await create(ledger);
  await ledger.exclusive(owner, async () => {
    const results = await Promise.allSettled([
      ledger.commit(owner, "operation-one", 1, journal(2)),
      ledger.commit(owner, "operation-one", 1, journal(2)),
    ]);
    expect(results.map((r) => r.status)).toEqual(["fulfilled", "rejected"]);
  });
  expect((await ledger.load(owner, "operation-one"))?.revision).toBe(2);
});

it("a separate Node process cannot execute while the data-instance lease is held", async () => {
  const { root, ledger } = await fixture();
  const module = fileURLToPath(
    new URL("./connection-batch-ledger.ts", import.meta.url),
  );
  await ledger.exclusive(owner, async () => {
    const child = spawn(
      process.execPath,
      [
        "--experimental-transform-types",
        "--input-type=module",
        "-e",
        `
      import {PersistentBatchLedger} from ${JSON.stringify(module)};
      const owner=${JSON.stringify(owner)};
      const ledger=await PersistentBatchLedger.open(${JSON.stringify(root)},owner);
      try { await ledger.exclusive(owner,async()=>{console.log('BAD_EFFECT')}); }
      catch(error){console.log(error.message);}
    `,
      ],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let stdout = "",
      stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    const code = await new Promise<number | null>((resolve, reject) => {
      child.once("exit", resolve);
      child.once("error", reject);
    });
    expect(code, stderr).toBe(0);
    expect(stdout.trim()).toBe("connection_batch_ledger_recovery_required");
  });
});

it("rejects receipt payload extras and unknown grant scopes without replacing a journal", async () => {
  const { ledger } = await fixture();
  await create(ledger);
  const next = journal(2);
  next.items[0] = {
    ...next.items[0],
    state: "succeeded",
    receipt: {
      ...owner,
      operationId: "operation-one",
      itemId: "install",
      intentDigest: digest,
      kind: "install",
      host: {
        ...host,
        installationId: "installation-one",
        permissionRevision: 1,
        installationDigest: "b".repeat(64),
      },
      credential: "MUST_NOT_STORE",
    } as never,
  };
  await expect(
    ledger.exclusive(owner, () =>
      ledger.commit(owner, "operation-one", 1, next),
    ),
  ).rejects.toThrow();
  expect(await ledger.load(owner, "operation-one")).toEqual(journal());
});

it("a known dead PID lock is still recovery-required, never age-based stolen", async () => {
  const { ledger, directory } = await fixture();
  const lock = path.join(directory, "execution.lock");
  await fs.mkdir(lock, { mode: 0o700 });
  await fs.writeFile(
    path.join(lock, "owner.json"),
    JSON.stringify({ ...owner, pid: 2147483647, nonce: "old" }),
    { mode: 0o600 },
  );
  const effect = vi.fn();
  await expect(
    ledger.exclusive(owner, async () => {
      effect();
    }),
  ).rejects.toThrow("recovery_required");
  expect(effect).not.toHaveBeenCalled();
  expect(
    JSON.parse(await fs.readFile(path.join(lock, "owner.json"), "utf8")).nonce,
  ).toBe("old");
});

it("post-publication directory fsync failure preserves published journal and fences further execution", async () => {
  const { root, ledger, directory } = await fixture();
  await create(ledger);
  const file = await journalPath(directory);
  const actual =
    await vi.importActual<typeof import("node:fs/promises")>(
      "node:fs/promises",
    );
  vi.mocked(fs.open).mockImplementation(async (...args) => {
    const handle = await actual.open(...args);
    if (args[0] === directory) {
      const sync = handle.sync.bind(handle);
      handle.sync = async () => {
        if (JSON.parse(await actual.readFile(file, "utf8")).revision === 2)
          throw Error("injected fsync failure");
        await sync();
      };
    }
    return handle;
  });
  await expect(
    ledger.exclusive(owner, () =>
      ledger.commit(owner, "operation-one", 1, journal(2)),
    ),
  ).rejects.toThrow("recovery_required");
  expect(JSON.parse(await actual.readFile(file, "utf8")).revision).toBe(2);
  vi.mocked(fs.open).mockImplementation(actual.open);
  const reopened = await PersistentBatchLedger.open(root, owner);
  expect((await reopened.load(owner, "operation-one"))?.revision).toBe(2);
  await expect(reopened.exclusive(owner, async () => {})).rejects.toThrow(
    "recovery_required",
  );
});
