import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import * as fs from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, expect, it, vi } from "vitest";
import type { BackgroundOperationSnapshot } from "./background-operation.js";
import { PersistentBackgroundOperationLedger } from "./background-operation-ledger.js";

vi.mock("node:fs/promises", async (original) => {
  const actual = await original<typeof import("node:fs/promises")>();
  return {
    ...actual,
    open: vi.fn(actual.open),
    link: vi.fn(actual.link),
    rename: vi.fn(actual.rename),
  };
});
const owner = { userId: "local", runtimeId: "stable-data-instance" };
const roots: string[] = [];
function snapshot(
  revision = 1,
  state: BackgroundOperationSnapshot["operations"][number]["state"] = "prepared",
): BackgroundOperationSnapshot {
  return {
    schemaVersion: 1,
    ...owner,
    revision,
    operations: [
      {
        operationId: "19e60957-ccfe-4d79-8d6b-c109c0b5f3fa",
        expectedRevision: 0,
        action: "enable",
        planDigest: "a".repeat(64),
        artifactDigest: "b".repeat(64),
        state,
        code: state === "unknown" ? "interrupted" : null,
      },
    ],
  };
}
async function root() {
  const value = await fs.realpath(
    await fs.mkdtemp(path.join(tmpdir(), "background-ledger-test-")),
  );
  roots.push(value);
  await fs.chmod(value, 0o700);
  return value;
}
async function fixture() {
  const dataDir = await root();
  const ledger = await PersistentBackgroundOperationLedger.initialize(
    dataDir,
    owner,
  );
  return {
    dataDir,
    ledger,
    directory: path.join(dataDir, "background-operations"),
    file: path.join(dataDir, "background-operations", "state.json"),
  };
}
async function create(ledger: PersistentBackgroundOperationLedger) {
  await ledger.exclusive(owner, () => ledger.commit(owner, null, snapshot()));
}
afterEach(async () => {
  vi.restoreAllMocks();
  await Promise.all(
    roots
      .splice(0)
      .map((value) => fs.rm(value, { recursive: true, force: true })),
  );
});

it("open does not initialize and initialize does not reset an existing store", async () => {
  const dataDir = await root();
  await expect(
    PersistentBackgroundOperationLedger.open(dataDir, owner),
  ).rejects.toThrow();
  expect(await fs.readdir(dataDir)).toEqual([]);
  await PersistentBackgroundOperationLedger.initialize(dataDir, owner);
  await expect(
    PersistentBackgroundOperationLedger.initialize(dataDir, owner),
  ).rejects.toThrow();
  await fs.unlink(path.join(dataDir, "background-operations", "owner.json"));
  await expect(
    PersistentBackgroundOperationLedger.open(dataDir, owner),
  ).rejects.toThrow();
});

it("persists owner and CAS state privately and reopens without writes", async () => {
  const f = await fixture();
  expect(await f.ledger.load(owner)).toBeNull();
  expect(await fs.readdir(f.directory)).toEqual(["owner.json"]);
  await create(f.ledger);
  expect((await fs.stat(f.directory)).mode & 0o7777).toBe(0o700);
  for (const name of ["owner.json", "state.json"]) {
    const info = await fs.lstat(path.join(f.directory, name));
    expect(info.mode & 0o7777).toBe(0o600);
    expect(info.nlink).toBe(1);
  }
  const before = await fs.readFile(f.file, "utf8");
  const reopened = await PersistentBackgroundOperationLedger.open(
    f.dataDir,
    owner,
  );
  expect(await reopened.load(owner)).toEqual(snapshot());
  expect(await fs.readFile(f.file, "utf8")).toBe(before);
  expect((await fs.readdir(f.directory)).sort()).toEqual([
    "owner.json",
    "state.json",
  ]);
});

it("requires the stable owner and an active exclusive lease for commits", async () => {
  const f = await fixture();
  const wrong = { ...owner, runtimeId: "process-instance-is-not-owner" };
  await expect(f.ledger.commit(owner, null, snapshot())).rejects.toThrow(
    "lock_required",
  );
  await expect(f.ledger.load(wrong)).rejects.toThrow();
  await expect(f.ledger.exclusive(wrong, async () => {})).rejects.toThrow();
  await expect(
    PersistentBackgroundOperationLedger.open(f.dataDir, wrong),
  ).rejects.toThrow();
  await create(f.ledger);
  await f.ledger.exclusive(owner, async () => {
    await expect(f.ledger.commit(owner, null, snapshot())).rejects.toThrow(
      "revision_conflict",
    );
    await f.ledger.commit(owner, 1, snapshot(2, "applying"));
    await expect(
      f.ledger.commit(owner, 1, snapshot(2, "applying")),
    ).rejects.toThrow("revision_conflict");
  });
});

it("delegates invalid metadata and unsafe transition rejection to the frozen model", async () => {
  const f = await fixture();
  await f.ledger.exclusive(owner, async () => {
    await expect(
      f.ledger.commit(owner, null, {
        ...snapshot(),
        secret: "DO_NOT_PERSIST",
      } as BackgroundOperationSnapshot),
    ).rejects.toThrow();
    await f.ledger.commit(owner, null, snapshot());
    await expect(
      f.ledger.commit(owner, 1, snapshot(2, "committed")),
    ).rejects.toThrow();
    await f.ledger.commit(owner, 1, snapshot(2, "applying"));
    await f.ledger.commit(owner, 2, snapshot(3, "unknown"));
    await expect(
      f.ledger.commit(owner, 3, snapshot(4, "applying")),
    ).rejects.toThrow();
  });
  expect((await f.ledger.load(owner))?.operations[0].state).toBe("unknown");
  expect(await fs.readFile(f.file, "utf8")).not.toContain("DO_NOT_PERSIST");
});

it("cannot append past an unresolved operation or silently change its intent", async () => {
  const f = await fixture();
  await create(f.ledger);
  await f.ledger.exclusive(owner, async () => {
    const first = snapshot().operations[0];
    await expect(
      f.ledger.commit(owner, 1, {
        ...snapshot(2),
        operations: [
          first,
          {
            ...first,
            operationId: "f60fc8eb-8e2e-4944-b177-38d58698d42e",
            expectedRevision: 1,
          },
        ],
      }),
    ).rejects.toThrow();
    await expect(
      f.ledger.commit(owner, 1, {
        ...snapshot(2, "applying"),
        operations: [
          { ...first, state: "applying", artifactDigest: "c".repeat(64) },
        ],
      }),
    ).rejects.toThrow();
  });
});

it("serializes concurrent CAS writes within one lease", async () => {
  const f = await fixture();
  await create(f.ledger);
  await f.ledger.exclusive(owner, async () => {
    const results = await Promise.allSettled([
      f.ledger.commit(owner, 1, snapshot(2, "applying")),
      f.ledger.commit(owner, 1, snapshot(2, "applying")),
    ]);
    expect(results.map((result) => result.status).sort()).toEqual([
      "fulfilled",
      "rejected",
    ]);
  });
  expect((await f.ledger.load(owner))?.revision).toBe(2);
});

it("retains the latest 32 operations and cannot evict the unresolved tail", async () => {
  const f = await fixture();
  let current: BackgroundOperationSnapshot | null = null;
  await f.ledger.exclusive(owner, async () => {
    for (let index = 0; index < 33; index++) {
      const previous: BackgroundOperationSnapshot | null = current;
      const revision: number = previous?.revision ?? 0;
      const next: BackgroundOperationSnapshot = {
        ...snapshot(revision + 1),
        operations: [
          ...(previous?.operations.slice(-31) ?? []),
          {
            ...snapshot().operations[0],
            operationId: randomUUID(),
            expectedRevision: revision,
          },
        ],
      };
      await f.ledger.commit(owner, previous?.revision ?? null, next);
      current = next;
      if (index < 32) {
        current = {
          ...next,
          revision: next.revision + 1,
          operations: next.operations.map((entry, i) =>
            i === next.operations.length - 1
              ? { ...entry, state: "rejected" as const }
              : entry,
          ),
        };
        await f.ledger.commit(owner, next.revision, current);
      }
    }
  });
  const actual = await f.ledger.load(owner);
  expect(actual?.operations).toHaveLength(32);
  expect(actual?.operations[0].expectedRevision).toBe(2);
  expect(actual?.operations.at(-1)?.state).toBe("prepared");
  if (!actual) throw new Error("Missing state");
  await f.ledger.exclusive(owner, async () => {
    await expect(
      f.ledger.commit(owner, actual.revision, {
        ...actual,
        revision: actual.revision + 1,
        operations: [
          ...actual.operations.slice(1, -1),
          {
            ...snapshot().operations[0],
            operationId: randomUUID(),
            expectedRevision: actual.revision,
          },
        ],
      }),
    ).rejects.toThrow();
  });
  expect(await f.ledger.load(owner)).toEqual(actual);
});

it("rejects unsafe or symlink data roots without creating a ledger", async () => {
  const dataDir = await root();
  await fs.chmod(dataDir, 0o755);
  await expect(
    PersistentBackgroundOperationLedger.initialize(dataDir, owner),
  ).rejects.toThrow("directory_unsafe");
  expect(await fs.readdir(dataDir)).toEqual([]);
  await fs.chmod(dataDir, 0o700);
  const container = await root();
  const alias = path.join(container, "alias");
  await fs.symlink(dataDir, alias);
  await expect(
    PersistentBackgroundOperationLedger.initialize(alias, owner),
  ).rejects.toThrow("directory_unsafe");
  expect(await fs.readdir(dataDir)).toEqual([]);
});

it("snapshots input before awaits and rejects detached writes after the callback ends", async () => {
  const f = await fixture();
  let detached!: () => Promise<void>;
  await f.ledger.exclusive(owner, async () => {
    const value = snapshot();
    const pending = f.ledger.commit(owner, null, value);
    value.operations[0].planDigest = "c".repeat(64);
    await pending;
    detached = () => f.ledger.commit(owner, 1, snapshot(2, "applying"));
  });
  expect(await f.ledger.load(owner)).toEqual(snapshot());
  await expect(detached()).rejects.toThrow("lock_required");
});

it("excludes a second handle and releases a clean lease on callback failure", async () => {
  const f = await fixture();
  const other = await PersistentBackgroundOperationLedger.open(
    f.dataDir,
    owner,
  );
  await expect(
    f.ledger.exclusive(owner, async () => {
      await expect(other.exclusive(owner, async () => {})).rejects.toThrow(
        "recovery_required",
      );
      throw new Error("synthetic callback failure");
    }),
  ).rejects.toThrow("synthetic callback failure");
  await other.exclusive(owner, async () => {});
});

it("never takes over a stale or malformed lock", async () => {
  const f = await fixture();
  const lock = path.join(f.directory, "execution.lock");
  await fs.mkdir(lock, { mode: 0o700 });
  const text = JSON.stringify({
    ...owner,
    pid: 2147483647,
    nonce: "dead-process",
  });
  await fs.writeFile(path.join(lock, "owner.json"), text, { mode: 0o600 });
  await expect(f.ledger.exclusive(owner, async () => {})).rejects.toThrow(
    "recovery_required",
  );
  expect(await fs.readFile(path.join(lock, "owner.json"), "utf8")).toBe(text);
});

it.each(["owner", "root", "directory"])(
  "rejects replaced %s identity",
  async (kind) => {
    const f = await fixture();
    if (kind === "owner")
      await fs.writeFile(path.join(f.directory, "owner.json"), "{}", {
        mode: 0o600,
      });
    else if (kind === "directory") {
      await fs.rename(f.directory, `${f.directory}.old`);
      await fs.mkdir(f.directory, { mode: 0o700 });
      await fs.copyFile(
        path.join(`${f.directory}.old`, "owner.json"),
        path.join(f.directory, "owner.json"),
      );
    } else {
      await fs.rename(f.dataDir, `${f.dataDir}.old`);
      roots.push(`${f.dataDir}.old`);
      await fs.mkdir(f.dataDir, { mode: 0o700 });
      await fs.mkdir(f.directory, { mode: 0o700 });
      await fs.copyFile(
        path.join(`${f.dataDir}.old`, "background-operations", "owner.json"),
        path.join(f.directory, "owner.json"),
      );
    }
    await expect(f.ledger.load(owner)).rejects.toThrow();
    if (kind === "root")
      await expect(
        PersistentBackgroundOperationLedger.open(f.dataDir, owner),
      ).rejects.toThrow();
  },
);

it.each(["corrupt", "oversize", "symlink", "hardlink", "permissions"])(
  "refuses %s state without repair",
  async (kind) => {
    const f = await fixture();
    await create(f.ledger);
    if (kind === "corrupt") await fs.writeFile(f.file, "{bad");
    if (kind === "oversize")
      await fs.writeFile(f.file, " ".repeat(256 * 1024 + 1));
    if (kind === "permissions") await fs.chmod(f.file, 0o644);
    if (kind === "hardlink") await fs.link(f.file, `${f.file}.alias`);
    if (kind === "symlink") {
      await fs.rename(f.file, `${f.file}.old`);
      await fs.symlink(`${f.file}.old`, f.file);
    }
    await expect(f.ledger.load(owner)).rejects.toThrow();
    expect(await fs.lstat(f.file)).toBeTruthy();
  },
);

it("initial publication never replaces a competing state", async () => {
  const f = await fixture();
  const real = await vi.importActual<typeof fs>("node:fs/promises");
  vi.mocked(fs.link).mockImplementationOnce(async (from, to) => {
    await real.writeFile(to, "competitor", { flag: "wx", mode: 0o600 });
    await real.link(from, to);
  });
  await expect(create(f.ledger)).rejects.toThrow();
  expect(await fs.readFile(f.file, "utf8")).toBe("competitor");
});

it("pre-publication failure preserves the prior state and releases the lock", async () => {
  const f = await fixture();
  await create(f.ledger);
  vi.mocked(fs.rename).mockRejectedValueOnce(
    new Error("synthetic rename failure"),
  );
  await expect(
    f.ledger.exclusive(owner, () =>
      f.ledger.commit(owner, 1, snapshot(2, "applying")),
    ),
  ).rejects.toThrow();
  expect(await f.ledger.load(owner)).toEqual(snapshot());
  await f.ledger.exclusive(owner, async () => {});
});

it("post-publication fsync failure preserves state and poisons the lease across reopen", async () => {
  const f = await fixture();
  await create(f.ledger);
  const real = await vi.importActual<typeof fs>("node:fs/promises");
  vi.mocked(fs.open).mockImplementation(async (...args) => {
    const handle = await real.open(...args);
    if (args[0] === f.directory) {
      const sync = handle.sync.bind(handle);
      handle.sync = async () => {
        if (JSON.parse(await real.readFile(f.file, "utf8")).revision === 2)
          throw new Error("synthetic fsync failure");
        await sync();
      };
    }
    return handle;
  });
  await expect(
    f.ledger.exclusive(owner, () =>
      f.ledger.commit(owner, 1, snapshot(2, "applying")),
    ),
  ).rejects.toThrow("recovery_required");
  vi.mocked(fs.open).mockImplementation(real.open);
  const reopened = await PersistentBackgroundOperationLedger.open(
    f.dataDir,
    owner,
  );
  expect((await reopened.load(owner))?.revision).toBe(2);
  await expect(reopened.exclusive(owner, async () => {})).rejects.toThrow(
    "recovery_required",
  );
});

it("a separate Node process cannot enter the same data-directory lease", async () => {
  const f = await fixture();
  const source = path.dirname(fileURLToPath(import.meta.url));
  // Temporary source copies allow Node's TS loader to resolve the model import
  // without changing the repository or installing a loader.
  const module = path.join(f.dataDir, "ledger.ts");
  const text = await fs.readFile(
    path.join(source, "background-operation-ledger.ts"),
    "utf8",
  );
  await fs.writeFile(
    module,
    text.replaceAll('"./background-operation.js"', '"./model.ts"'),
  );
  await fs.copyFile(
    path.join(source, "background-operation.ts"),
    path.join(f.dataDir, "model.ts"),
  );
  await f.ledger.exclusive(owner, async () => {
    const child = spawn(
      process.execPath,
      [
        "--experimental-transform-types",
        "--input-type=module",
        "-e",
        `
      import {PersistentBackgroundOperationLedger} from ${JSON.stringify(module)};
      const owner=${JSON.stringify(owner)};
      const ledger=await PersistentBackgroundOperationLedger.open(${JSON.stringify(f.dataDir)},owner);
      try { await ledger.exclusive(owner,async()=>console.log('BAD_EFFECT')); }
      catch(error) { console.log(error.message); }
    `,
      ],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let out = "",
      err = "";
    child.stdout.on("data", (data) => {
      out += data;
    });
    child.stderr.on("data", (data) => {
      err += data;
    });
    const code = await new Promise<number | null>((resolve, reject) => {
      child.once("exit", resolve);
      child.once("error", reject);
    });
    expect(code, err).toBe(0);
    expect(out.trim()).toBe("background_operation_ledger_recovery_required");
  });
});
