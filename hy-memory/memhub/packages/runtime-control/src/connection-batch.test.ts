import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type BatchAdapters,
  type BatchJournal,
  type BatchLedger,
  type BatchOwner,
  ConnectionBatch,
  type ConnectionItem,
  type ConnectionPlan,
  connectionPlanDigest,
  type ItemContext,
  type ItemReceipt,
} from "./connection-batch.js";

const hash = "a".repeat(64);
const owner: BatchOwner = { userId: "local", runtimeId: "home-one" };
const source = {
  sourceId: "cursor",
  rootId: "root-cursor",
  rootPath: "/fixture/cursor",
  grantRevision: 2,
};
const host = {
  hostId: "cursor",
  layoutDigest: hash,
  installationId: null,
  permissionRevision: 0,
  installationDigest: null,
};
const install: ConnectionItem = {
  id: "install",
  kind: "install",
  sources: [source],
  host,
  previewFingerprint: hash,
};
const grant: ConnectionItem = {
  id: "grant",
  kind: "readGrant",
  sources: [source],
  host,
  installItemId: "install",
  allowedTools: ["om_recall"],
  allowedScopes: ["all-apps"],
};
function plan(items: ConnectionItem[] = [install, grant]): ConnectionPlan {
  return {
    schemaVersion: 1,
    ...owner,
    operationId: "batch-one",
    items: structuredClone(items),
  };
}
class MemoryLedger implements BatchLedger {
  durability = "process" as const;
  entries = new Map<string, BatchJournal>();
  commits = 0;
  private tail = Promise.resolve();
  async exclusive<T>(_owner: BatchOwner, run: () => Promise<T>): Promise<T> {
    const previous = this.tail;
    let release!: () => void;
    this.tail = new Promise<void>((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      return await run();
    } finally {
      release();
    }
  }
  async load(_owner: BatchOwner, id: string) {
    return structuredClone(this.entries.get(id) ?? null);
  }
  async commit(
    _owner: BatchOwner,
    id: string,
    expected: number | null,
    next: BatchJournal,
  ) {
    if ((this.entries.get(id)?.revision ?? null) !== expected)
      throw Error("CAS");
    this.commits++;
    this.entries.set(id, structuredClone(next));
  }
}
function receipt(item: ConnectionItem, context: ItemContext): ItemReceipt {
  const binding = {
    ...owner,
    operationId: context.operationId,
    itemId: item.id,
    intentDigest: context.intentDigest,
  };
  const identity = context.host ?? item.host;
  const installed = {
    ...identity,
    installationId: identity.installationId ?? "installation-one",
    permissionRevision:
      item.kind === "install" ? 1 : identity.permissionRevision + 1,
    installationDigest: "b".repeat(64),
  };
  return item.kind === "install"
    ? { ...binding, kind: "install", host: installed }
    : {
        ...binding,
        kind: "readGrant",
        host: { ...installed, installationDigest: identity.installationDigest },
        allowedTools: item.allowedTools,
        allowedScopes: item.allowedScopes,
      };
}
function fixture(ledger: BatchLedger | undefined = new MemoryLedger()) {
  const adapters: BatchAdapters = {
    inspect: vi.fn(async (item, context) => ({
      status: "ready" as const,
      sources: item.sources,
      host: context.host ?? item.host,
      previewFingerprint:
        item.kind === "install" ? item.previewFingerprint : null,
    })),
    install: {
      apply: vi.fn(async (item, context) => ({
        status: "succeeded" as const,
        receipt: receipt(item, context),
      })),
      reconcile: vi.fn(async () => ({ status: "unknown" as const })),
    },
    readGrant: {
      apply: vi.fn(async (item, context) => ({
        status: "succeeded" as const,
        receipt: receipt(item, context),
      })),
      reconcile: vi.fn(async () => ({ status: "unknown" as const })),
    },
  };
  return {
    ledger: ledger as MemoryLedger,
    adapters,
    batch: new ConnectionBatch(owner, adapters, ledger),
  };
}
const execute = (batch: ConnectionBatch, p = plan(), signal?: AbortSignal) =>
  batch.run(p, {
    mode: "execute",
    userConfirmed: true,
    planDigest: connectionPlanDigest(p),
    signal,
  });

describe("connection batch authorization and recovery", () => {
  it("can retry read-only preflight failure but cannot turn unknown effects into a fresh apply", async () => {
    const { batch, adapters } = fixture();
    vi.mocked(adapters.inspect).mockRejectedValueOnce(Error("offline"));
    expect((await execute(batch, plan([install]))).items[0].state).toBe(
      "unavailable",
    );
    expect(adapters.install.apply).not.toHaveBeenCalled();
    vi.mocked(adapters.install.apply).mockRejectedValueOnce(Error("timeout"));
    expect((await execute(batch, plan([install]))).items[0].state).toBe(
      "unknown",
    );
    vi.mocked(adapters.inspect).mockRejectedValueOnce(Error("offline"));
    expect((await execute(batch, plan([install]))).items[0].state).toBe(
      "unknown",
    );
    await execute(batch, plan([install]));
    expect(adapters.install.apply).toHaveBeenCalledOnce();
    expect(adapters.install.reconcile).toHaveBeenCalledOnce();
  });
  it("refuses unsupported scopes and a grant not bound to a planned relink", async () => {
    const { batch, ledger } = fixture();
    const existingHost = {
      ...host,
      installationId: "old",
      permissionRevision: 2,
      installationDigest: hash,
    };
    for (const p of [
      plan([{ ...grant, allowedScopes: ["anything"] }]),
      plan([
        { ...install, host: existingHost },
        { ...grant, host: existingHost, installItemId: undefined },
      ]),
    ]) {
      await expect(
        batch.run(p, {
          mode: "execute",
          userConfirmed: true,
          planDigest: hash,
        }),
      ).rejects.toThrow();
    }
    expect(ledger.commits).toBe(0);
  });
  it("prevents identity drift during reconciliation from authorizing dependent work", async () => {
    const { batch, adapters } = fixture();
    vi.mocked(adapters.install.apply).mockRejectedValue(Error("timeout"));
    await execute(batch);
    vi.mocked(adapters.inspect).mockImplementation(async (item) => ({
      status: "ready",
      sources: item.sources,
      host: { ...item.host, layoutDigest: "c".repeat(64) },
      previewFingerprint: hash,
    }));
    const result = await execute(batch);
    expect(result.items[0].state).toBe("changed");
    expect(adapters.install.reconcile).not.toHaveBeenCalled();
    expect(adapters.readGrant.apply).not.toHaveBeenCalled();
  });
  it("performs no effect when creating or saving intent fails", async () => {
    const { batch, adapters, ledger } = fixture();
    vi.spyOn(ledger, "commit").mockRejectedValue(Error("disk"));
    await expect(execute(batch)).rejects.toThrow("ledger_unavailable");
    expect(adapters.install.apply).not.toHaveBeenCalled();
  });
  it("does not persist arbitrary adapter metadata even in a success receipt", async () => {
    const { batch, adapters, ledger } = fixture();
    vi.mocked(adapters.install.apply).mockImplementation(
      async (item, context) => ({
        status: "succeeded",
        receipt: {
          ...receipt(item, context),
          token: "secret-value",
        } as unknown as ItemReceipt,
      }),
    );
    const result = await execute(batch, plan([install]));
    expect(result.items[0].state).toBe("unknown");
    expect(JSON.stringify(ledger.entries.get("batch-one"))).not.toContain(
      "secret-value",
    );
  });
  it("defaults to preview with no ledger or adapter writes", async () => {
    const { batch, adapters, ledger } = fixture();
    const result = await batch.run(plan());
    expect(result.mode).toBe("preview");
    expect(result.planDigest).toBe(connectionPlanDigest(plan()));
    expect(ledger.commits).toBe(0);
    for (const kind of ["install", "readGrant"] as const)
      expect(adapters[kind].apply).not.toHaveBeenCalled();
  });
  it("requires explicit confirmation, exact digest and injected ledger", async () => {
    const { batch, adapters } = fixture();
    await expect(
      batch.run(plan(), {
        mode: "execute",
        userConfirmed: false,
        planDigest: connectionPlanDigest(plan()),
      }),
    ).rejects.toThrow("confirmation_required");
    await expect(
      batch.run(plan(), {
        mode: "execute",
        userConfirmed: true,
        planDigest: "0".repeat(64),
      }),
    ).rejects.toThrow("plan_changed");
    const noLedger = new ConnectionBatch(owner, adapters);
    await expect(execute(noLedger)).rejects.toThrow("ledger_required");
    expect(adapters.install.apply).not.toHaveBeenCalled();
  });
  it("rejects cross-user/runtime input, duplicate targets, unsafe extra fields before ledger use", async () => {
    const { batch, ledger } = fixture();
    for (const p of [
      { ...plan(), userId: "other" },
      { ...plan(), runtimeId: "other" },
      plan([install, { ...install, id: "again" }]),
      { ...plan(), apiKey: "secret" },
    ]) {
      await expect(
        batch.run(p, {
          mode: "execute",
          userConfirmed: true,
          planDigest: hash,
        }),
      ).rejects.toThrow();
    }
    expect(ledger.commits).toBe(0);
  });
  it("writes intent before effect, binds new install identity and keeps all actions independent", async () => {
    const { batch, adapters, ledger } = fixture();
    vi.mocked(adapters.install.apply).mockImplementation(
      async (item, context) => {
        expect(ledger.entries.get(context.operationId)?.items[0].state).toBe(
          "in_flight",
        );
        return { status: "succeeded", receipt: receipt(item, context) };
      },
    );
    const result = await execute(batch);
    expect(result.state).toBe("completed");
    expect(adapters.install.apply).toHaveBeenCalledOnce();
    expect(adapters.readGrant.apply).toHaveBeenCalledWith(
      expect.objectContaining({ allowedTools: ["om_recall"] }),
      expect.objectContaining({
        host: expect.objectContaining({
          installationId: "installation-one",
          permissionRevision: 1,
        }),
      }),
    );
    expect(result.recovery).toBe("process");
  });
  it("install alone never creates a read grant", async () => {
    const { batch, adapters } = fixture();
    await execute(batch, plan([install]));
    expect(adapters.readGrant.apply).not.toHaveBeenCalled();
  });
  it("never repeats successful items on replay or a new executor with the same ledger", async () => {
    const { batch, adapters, ledger } = fixture();
    await execute(batch);
    await execute(new ConnectionBatch(owner, adapters, ledger));
    for (const kind of ["install", "readGrant"] as const)
      expect(adapters[kind].apply).toHaveBeenCalledOnce();
  });
  it("unknown result reconciles first and never reapplies, even when reconciliation says not applied", async () => {
    const { batch, adapters, ledger } = fixture();
    vi.mocked(adapters.install.apply).mockRejectedValue(
      Error("secret network body"),
    );
    const first = await execute(batch);
    expect(first.items.find((item) => item.id === "install")?.state).toBe(
      "unknown",
    );
    expect(first.items.find((item) => item.id === "grant")?.state).toBe(
      "dependency_blocked",
    );
    vi.mocked(adapters.install.reconcile).mockResolvedValue({
      status: "not_applied",
    });
    const recovered = await execute(
      new ConnectionBatch(owner, adapters, ledger),
    );
    expect(recovered.items.find((item) => item.id === "install")?.state).toBe(
      "not_applied",
    );
    expect(adapters.install.reconcile).toHaveBeenCalledOnce();
    expect(adapters.install.apply).toHaveBeenCalledOnce();
    expect(JSON.stringify(ledger.entries.get("batch-one"))).not.toContain(
      "secret network body",
    );
  });
  it("recovered install permits only the explicitly planned separate grant", async () => {
    const { batch, adapters } = fixture();
    vi.mocked(adapters.install.apply).mockRejectedValue(Error("timeout"));
    await execute(batch);
    vi.mocked(adapters.install.reconcile).mockImplementation(
      async (item, context) => ({
        status: "succeeded",
        receipt: receipt(item, context),
      }),
    );
    expect((await execute(batch)).state).toBe("completed");
    expect(adapters.install.apply).toHaveBeenCalledOnce();
    expect(adapters.readGrant.apply).toHaveBeenCalledOnce();
  });
  it("source identity drift blocks install and its dependent grant", async () => {
    const { batch, adapters } = fixture();
    vi.mocked(adapters.inspect).mockImplementation(async (item, context) => ({
      status: "ready",
      sources: [{ ...source, rootId: "changed" }],
      host: context.host ?? item.host,
      previewFingerprint: item.kind === "install" ? hash : null,
    }));
    const result = await execute(batch);
    expect(result.state).toBe("partial");
    expect(result.items[0].state).toBe("changed");
    expect(result.items[1].state).toBe("dependency_blocked");
    expect(adapters.install.apply).not.toHaveBeenCalled();
    expect(adapters.readGrant.apply).not.toHaveBeenCalled();
  });
  it("denied installation cannot fall through to grant", async () => {
    const { batch, adapters } = fixture();
    vi.mocked(adapters.install.apply).mockResolvedValue({ status: "rejected" });
    const result = await execute(batch);
    expect(result.items[0].state).toBe("rejected");
    expect(result.items[1].state).toBe("dependency_blocked");
    expect(adapters.readGrant.apply).not.toHaveBeenCalled();
    await execute(batch);
    expect(adapters.install.apply).toHaveBeenCalledOnce();
  });
  it("malformed/broadened grant receipt is unknown, never success", async () => {
    const { batch, adapters } = fixture();
    vi.mocked(adapters.readGrant.apply).mockImplementation(
      async (item, context) => ({
        status: "succeeded",
        receipt: {
          ...receipt(item, context),
          allowedScopes: ["all-apps", "source:unapproved"],
        } as ItemReceipt,
      }),
    );
    expect((await execute(batch)).items[1].state).toBe("unknown");
  });
  it("aborting stops subsequent items without cancelling an in-flight operation", async () => {
    const { batch, adapters } = fixture();
    const controller = new AbortController();
    vi.mocked(adapters.install.apply).mockImplementation(
      async (item, context) => {
        controller.abort();
        return { status: "succeeded", receipt: receipt(item, context) };
      },
    );
    const result = await execute(batch, plan(), controller.signal);
    expect(result.cancelled).toBe(true);
    expect(result.items[0].state).toBe("succeeded");
    expect(adapters.readGrant.apply).not.toHaveBeenCalled();
  });
  it("serializes concurrent executors through ledger ownership", async () => {
    const { batch, adapters, ledger } = fixture();
    await Promise.all([
      execute(batch),
      execute(new ConnectionBatch(owner, adapters, ledger)),
    ]);
    expect(adapters.install.apply).toHaveBeenCalledOnce();
    expect(adapters.readGrant.apply).toHaveBeenCalledOnce();
  });
  it("freezes the plan before async reads; caller mutation cannot change confirmed scope", async () => {
    const { batch, adapters } = fixture();
    const p = plan();
    const work = execute(batch, p);
    (p.items[1] as typeof grant).allowedScopes = ["all-apps", "source:other"];
    await work;
    expect(adapters.readGrant.apply).toHaveBeenCalledWith(
      expect.objectContaining({ allowedScopes: ["all-apps"] }),
      expect.anything(),
    );
  });
  it("stops writes if intent journal fails and reconciles if success journal was lost", async () => {
    const ledger = new MemoryLedger(),
      { batch, adapters } = fixture(ledger);
    const original = ledger.commit.bind(ledger);
    vi.spyOn(ledger, "commit").mockImplementation(
      async (owner, id, expected, next) => {
        if (next.items[0].state === "succeeded") throw Error("disk full");
        await original(owner, id, expected, next);
      },
    );
    await expect(execute(batch)).rejects.toThrow("ledger_unavailable");
    expect(ledger.entries.get("batch-one")?.items[0].state).toBe("in_flight");
    expect(adapters.install.apply).toHaveBeenCalledOnce();
    expect(adapters.readGrant.apply).not.toHaveBeenCalled();
    vi.mocked(ledger.commit).mockImplementation(original);
    await execute(batch);
    expect(adapters.install.reconcile).toHaveBeenCalledOnce();
    expect(adapters.install.apply).toHaveBeenCalledOnce();
  });
  it("rejects reuse of operation id with another digest and corrupted journals", async () => {
    const { batch, ledger } = fixture();
    await execute(batch);
    await expect(execute(batch, plan([install]))).rejects.toThrow(
      "operation_conflict",
    );
    const journal = ledger.entries.get("batch-one") as BatchJournal;
    ledger.entries.set("batch-one", { ...journal, userId: "other" });
    await expect(execute(batch)).rejects.toThrow("journal_invalid");
  });
});

// Test-only persistence fixture. Production filesystem/ACL implementation is an
// explicit Main integration dependency, not provided by this in-memory executor.
const directories: string[] = [];
afterEach(async () => {
  for (const directory of directories.splice(0))
    await rm(directory, { recursive: true, force: true });
});
it("recovers only through an injected ledger persisted by its owner", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "connection-batch-"));
  directories.push(directory);
  const file = path.join(directory, "journal.json");
  const ledger = new MemoryLedger();
  const commit = ledger.commit.bind(ledger);
  ledger.commit = async (owner, id, expected, next) => {
    await commit(owner, id, expected, next);
    await writeFile(file, JSON.stringify(next), { mode: 0o600 });
  };
  const { batch, adapters } = fixture(ledger);
  await execute(batch);
  const restored = new MemoryLedger();
  restored.entries.set("batch-one", JSON.parse(await readFile(file, "utf8")));
  await execute(new ConnectionBatch(owner, adapters, restored));
  expect(adapters.install.apply).toHaveBeenCalledOnce();
  expect(adapters.readGrant.apply).toHaveBeenCalledOnce();
  expect(JSON.parse(await readFile(file, "utf8")).planDigest).toBe(
    connectionPlanDigest(plan()),
  );
});
