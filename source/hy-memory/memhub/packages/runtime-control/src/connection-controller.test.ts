import { mkdtemp, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import type { SourceResponse } from "@one-memory/contracts";
import type { RecallHostLayout } from "@one-memory/host-bridge/installer";
import { afterEach, expect, it, vi } from "vitest";
import { PersistentBatchLedger } from "./connection-batch-ledger.js";
import { ConnectionController } from "./connection-controller.js";
import type { RecallPermissionStatus } from "./host-permissions.js";

const roots: string[] = [];

it("does not evict an active execute reference while other previews roll over", async () => {
  const f = await fixture();
  const selection = { syncSourceIds: ["cursor"], hostSourceIds: [] };
  const first = await f.controller.preview(selection);
  let release!: () => void;
  let entered!: () => void;
  const hold = new Promise<void>((resolve) => {
    release = resolve;
  });
  const admission = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const original = PersistentBatchLedger.prototype.exclusive;
  // Pause only admission, before a journal exists; keep actual locking and effects real.
  const exclusive = vi
    .spyOn(PersistentBatchLedger.prototype, "exclusive")
    .mockImplementationOnce(async function (
      this: PersistentBatchLedger,
      owner,
      operation,
    ) {
      entered();
      await hold;
      return original.call(this, owner, operation);
    });
  const input = {
    planId: first.planId,
    digest: first.digest,
    userConfirmed: true as const,
  };
  const work = f.controller.execute(input);
  try {
    await admission;
    for (let index = 0; index < 70; index++)
      await f.controller.preview(selection);
  } finally {
    release();
    await work;
    exclusive.mockRestore();
  }
  await f.controller.execute(input);
  expect(f.trusted.setSourceSync).toHaveBeenCalledTimes(1);
});

it("evicts oldest previews after 64 without replaying an achieved sync state", async () => {
  const f = await fixture();
  const selection = { syncSourceIds: ["cursor"], hostSourceIds: [] };
  const oldest = await f.controller.preview(selection);
  const execute = {
    planId: oldest.planId,
    digest: oldest.digest,
    userConfirmed: true as const,
  };
  await f.controller.execute(execute);
  await f.controller.execute(execute);
  expect(f.trusted.setSourceSync).toHaveBeenCalledTimes(1);
  let newest = oldest;
  for (let index = 0; index < 70; index++)
    newest = await f.controller.preview(selection);
  await expect(f.controller.execute(execute)).rejects.toThrow("plan_missing");
  expect(await f.controller.receipt(oldest.operationId)).toBeNull();
  const latest = {
    planId: newest.planId,
    digest: newest.digest,
    userConfirmed: true as const,
  };
  await f.controller.execute(latest);
  await f.controller.execute(latest);
  expect(f.trusted.setSourceSync).toHaveBeenCalledTimes(1);
});

it("a failed direct sync remains retryable after cache rollover", async () => {
  const f = await fixture();
  const selection = { syncSourceIds: ["cursor"], hostSourceIds: [] };
  let plan = await f.controller.preview(selection);
  for (let index = 0; index < 65; index++)
    plan = await f.controller.preview(selection);
  f.trusted.setSourceSync.mockRejectedValueOnce(Error("lost"));
  const input = {
    planId: plan.planId,
    digest: plan.digest,
    userConfirmed: true as const,
  };
  expect((await f.controller.execute(input)).items[0].state).toBe("unknown");
  await expect(f.controller.preview(selection)).resolves.toBeDefined();
  expect((await f.controller.execute(input)).items[0].state).toBe("succeeded");
  expect(f.trusted.setSourceSync).toHaveBeenCalledTimes(2);
});
afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((r) => rm(r, { recursive: true, force: true })),
  );
});
async function fixture() {
  const dataDir = await realpath(
    await mkdtemp(path.join(tmpdir(), "connection-control-")),
  );
  roots.push(dataDir);
  const source = {
    source_id: "cursor",
    display_name: "Cursor",
    authorized: true,
    available: true,
    root_id: "root",
    candidate_root_id: "root",
    candidate_path: path.join(dataDir, "cursor"),
    grant_revision: 2,
    sync_enabled: false,
    location_state: "found",
    capabilities: {
      live_sync: "implemented",
      installer: "implemented",
      recall: "implemented",
    },
  } as SourceResponse;
  const layout: RecallHostLayout = {
    hostId: "cursor",
    hostLabel: "Cursor",
    configPath: path.join(dataDir, "mcp.json"),
    format: "json",
    channel: "mcp",
    skillPath: null,
    journalPath: path.join(dataDir, "install.json"),
    containmentRoot: dataDir,
  };
  let permission: RecallPermissionStatus = {
    hostId: "cursor",
    state: "not-installed",
    reason: null,
    receipt: null,
  };
  const hostPermissions = {
    getPermission: vi.fn(async () => structuredClone(permission)),
    previewInstall: vi.fn(async () => ({
      hostId: "cursor",
      hostLabel: "Cursor",
      files: [],
      supersedes: null,
      fingerprint: "a".repeat(64),
    })),
    install: vi.fn(async () => {
      permission = {
        hostId: "cursor",
        state: "install-only",
        reason: null,
        receipt: {
          hostId: "cursor",
          installationId: "install-1",
          revision: 1,
          status: "install-only",
          allowedTools: [],
          allowedScopes: [],
        },
      };
      return {
        hostId: "cursor",
        installed: true,
        permission: structuredClone(permission),
      };
    }),
    setPermission: vi.fn(async (_layout, input) => {
      permission = {
        hostId: "cursor",
        state: "approved",
        reason: null,
        receipt: {
          hostId: "cursor",
          installationId: input.installationId,
          revision: input.expectedRevision + 1,
          status: "approved",
          allowedTools: input.allowedTools,
          allowedScopes: input.allowedScopes,
        },
      };
      return structuredClone(permission);
    }),
  };
  const trusted = {
    dataDir,
    stableOwner: { userId: "local", runtimeId: "stable-data" },
    hostPermissions,
    resolveHostLayout: vi.fn(() => layout),
    getSources: vi.fn(async () => [structuredClone(source)]),
    setSourceSync: vi.fn(async (s: SourceResponse, enabled: boolean) => {
      source.sync_enabled = enabled;
      return {
        source_id: s.source_id,
        sync_enabled: enabled,
      };
    }),
  };
  const controller = await ConnectionController.initialize(trusted);
  return {
    controller,
    trusted,
    source,
    layout,
    hostPermissions,
    setPermission: (p: RecallPermissionStatus) => {
      permission = p;
    },
  };
}
it("previews IDs only with separate install/grant then executes exact receipts once", async () => {
  const f = await fixture();
  const p = await f.controller.preview({
    syncSourceIds: ["cursor"],
    hostSourceIds: ["cursor"],
  });
  expect(f.hostPermissions.install).not.toHaveBeenCalled();
  expect(f.trusted.setSourceSync).not.toHaveBeenCalled();
  expect(p.items.map((i) => i.kind)).toEqual(["sync", "install", "readGrant"]);
  expect(p.items.at(-1)?.allowedTools).toEqual([
    "om_recall",
    "om_conversations",
    "om_diagnostic_trace",
  ]);
  expect(p.items.at(-1)?.allowedScopes).toEqual(["all-apps", "source:cursor"]);
  const input = {
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true as const,
  };
  const result = await f.controller.execute(input);
  expect(result.state).toBe("completed");
  expect(f.hostPermissions.setPermission.mock.calls[0]?.[1]).toMatchObject({
    installationId: "install-1",
    expectedRevision: 1,
    userConfirmed: true,
  });
  await f.controller.execute(input);
  expect(f.hostPermissions.install).toHaveBeenCalledTimes(1);
  expect(f.trusted.setSourceSync).toHaveBeenCalledTimes(1);
  expect(
    (await f.controller.receipt(p.operationId))?.items.every(
      (i) => i.state === "succeeded",
    ),
  ).toBe(true);
});
it("rejects arbitrary paths/tools, unknown sources, missing confirmation and tampered digest", async () => {
  const f = await fixture();
  await expect(
    f.controller.preview({
      syncSourceIds: [],
      hostSourceIds: ["cursor"],
      allowedTools: ["om_ask"],
    } as never),
  ).rejects.toThrow();
  await expect(
    f.controller.preview({
      syncSourceIds: ["../../outside"],
      hostSourceIds: [],
    }),
  ).rejects.toThrow();
  await expect(
    f.controller.preview({ syncSourceIds: ["missing"], hostSourceIds: [] }),
  ).rejects.toThrow();
  const p = await f.controller.preview({
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  });
  await expect(
    f.controller.execute({
      planId: p.planId,
      digest: p.digest,
      userConfirmed: false,
    } as never),
  ).rejects.toThrow();
  await expect(
    f.controller.execute({
      planId: p.planId,
      digest: "b".repeat(64),
      userConfirmed: true,
    }),
  ).rejects.toThrow();
  expect(f.trusted.setSourceSync).not.toHaveBeenCalled();
});
it("invalid current source blocks both frozen host writes and direct sync", async () => {
  const f = await fixture();
  const p = await f.controller.preview({
    syncSourceIds: ["cursor"],
    hostSourceIds: ["cursor"],
  });
  f.source.root_id = "changed";
  const result = await f.controller.execute({
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(result.state).toBe("partial");
  expect(f.hostPermissions.install).not.toHaveBeenCalled();
  expect(f.trusted.setSourceSync).not.toHaveBeenCalled();
  expect(result.items.at(-1)).toMatchObject({
    kind: "sync",
    state: "unknown",
    receipt: null,
  });
});
it("revoked existing installation is explicitly summarized and never restored by preview", async () => {
  const f = await fixture();
  f.setPermission({
    hostId: "cursor",
    state: "revoked",
    reason: null,
    receipt: {
      hostId: "cursor",
      installationId: "old",
      revision: 4,
      status: "revoked",
      allowedTools: [],
      allowedScopes: [],
    },
  });
  const p = await f.controller.preview({
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  });
  expect(p.items[0].restoresRevoked).toBe(true);
  expect(f.hostPermissions.setPermission).not.toHaveBeenCalled();
  await f.controller.execute({
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(f.hostPermissions.install).not.toHaveBeenCalled();
  expect(
    f.hostPermissions.setPermission.mock.calls[0]?.[1].expectedRevision,
  ).toBe(4);
});
it("a lost direct-sync response is resolved immediately from final state", async () => {
  const f = await fixture();
  f.trusted.setSourceSync.mockImplementationOnce(async (source, enabled) => {
    f.source.sync_enabled = enabled;
    throw new Error(`lost result for ${source.source_id}`);
  });
  const p = await f.controller.preview({
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  });
  const input = {
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true as const,
  };
  expect((await f.controller.execute(input)).items[0].state).toBe("succeeded");
  expect(f.trusted.setSourceSync).toHaveBeenCalledTimes(1);
  const reopened = await ConnectionController.open(f.trusted);
  await expect(reopened.execute(input)).rejects.toThrow("plan_missing");
  await expect(
    reopened.preview({ syncSourceIds: ["cursor"], hostSourceIds: ["cursor"] }),
  ).resolves.toBeDefined();
  expect(await reopened.receipt(p.operationId)).toBeNull();
});
it("cancelled host execution skips the following direct sync", async () => {
  const f = await fixture();
  const abort = new AbortController();
  const original = f.hostPermissions.install.getMockImplementation();
  if (!original) throw Error("missing fixture implementation");
  f.hostPermissions.install.mockImplementation(async (...args) => {
    const r = await original(...args);
    abort.abort();
    return r;
  });
  const p = await f.controller.preview({
    syncSourceIds: ["cursor"],
    hostSourceIds: ["cursor"],
  });
  const r = await f.controller.execute(
    { planId: p.planId, digest: p.digest, userConfirmed: true },
    abort.signal,
  );
  expect(r.cancelled).toBe(true);
  expect(r.items[0].state).toBe("succeeded");
  expect(f.hostPermissions.setPermission).not.toHaveBeenCalled();
  expect(f.trusted.setSourceSync).not.toHaveBeenCalled();
});

it("existing approval retains om_ask/workspace rights when adding the requested grant", async () => {
  const f = await fixture();
  f.setPermission({
    hostId: "cursor",
    state: "approved",
    reason: null,
    receipt: {
      hostId: "cursor",
      installationId: "old",
      revision: 3,
      status: "approved",
      allowedTools: ["om_ask"],
      allowedScopes: [`workspace:v1:${"b".repeat(64)}`],
    },
  });
  const p = await f.controller.preview({
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  });
  expect(p.items[0].allowedTools).toEqual([
    "om_ask",
    "om_recall",
    "om_conversations",
    "om_diagnostic_trace",
  ]);
  expect(p.items[0].allowedScopes).toEqual([
    `workspace:v1:${"b".repeat(64)}`,
    "all-apps",
    "source:cursor",
  ]);
  await f.controller.execute({
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(
    f.hostPermissions.setPermission.mock.calls[0]?.[1].allowedTools,
  ).toContain("om_ask");
});

it("partial install failure blocks only dependent grant and still applies direct sync", async () => {
  const f = await fixture();
  const p = await f.controller.preview({
    syncSourceIds: ["cursor"],
    hostSourceIds: ["cursor"],
  });
  f.hostPermissions.install.mockRejectedValueOnce(new Error("private failure"));
  const result = await f.controller.execute({
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(result.items.map((item) => item.state)).toEqual([
    "unknown",
    "dependency_blocked",
    "succeeded",
  ]);
  expect(f.hostPermissions.setPermission).not.toHaveBeenCalled();
  expect(JSON.stringify(result)).not.toContain("private failure");
});

it("changed layout and live managed-config drift refuse existing grant writes", async () => {
  const f = await fixture();
  f.setPermission({
    hostId: "cursor",
    state: "install-only",
    reason: null,
    receipt: {
      hostId: "cursor",
      installationId: "old",
      revision: 1,
      status: "install-only",
      allowedTools: [],
      allowedScopes: [],
    },
  });
  const p = await f.controller.preview({
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  });
  f.layout.skillPath = path.join(f.trusted.dataDir, "changed-skill");
  const changed = await f.controller.execute({
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(changed.items[0].state).toBe("changed");
  expect(f.hostPermissions.setPermission).not.toHaveBeenCalled();
});

it("direct sync uses the current authorized source instead of a preview CAS", async () => {
  const f = await fixture();
  const p = await f.controller.preview({
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  });
  f.source.grant_revision = 3;
  expect(
    (
      await f.controller.execute({
        planId: p.planId,
        digest: p.digest,
        userConfirmed: true,
      })
    ).items[0].state,
  ).toBe("succeeded");
  expect(f.trusted.setSourceSync).toHaveBeenCalledOnce();
});

it("a set response alone cannot claim sync success without final source state", async () => {
  const f = await fixture();
  const p = await f.controller.preview({
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  });
  f.trusted.setSourceSync.mockResolvedValueOnce({
    source_id: "cursor",
    sync_enabled: true,
  });
  expect(
    (
      await f.controller.execute({
        planId: p.planId,
        digest: p.digest,
        userConfirmed: true,
      })
    ).items[0].state,
  ).toBe("unknown");
});

it("one failed sync does not suppress an independent install and explicit read grant", async () => {
  const f = await fixture();
  f.trusted.setSourceSync.mockRejectedValueOnce(new Error("transport lost"));
  const p = await f.controller.preview({
    syncSourceIds: ["cursor"],
    hostSourceIds: ["cursor"],
  });
  const result = await f.controller.execute({
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(result.items.map((item) => item.state)).toEqual([
    "succeeded",
    "succeeded",
    "unknown",
  ]);
  expect(f.hostPermissions.setPermission).toHaveBeenCalledTimes(1);
});

it("restarting loses plans but permits a new preview after only successful history", async () => {
  const f = await fixture();
  const p = await f.controller.preview({
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  });
  await f.controller.execute({
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  const reopened = await ConnectionController.open(f.trusted);
  await expect(
    reopened.execute({
      planId: p.planId,
      digest: p.digest,
      userConfirmed: true,
    }),
  ).rejects.toThrow("plan_missing");
  const next = await reopened.preview({
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  });
  expect(next.operationId).not.toBe(p.operationId);
  expect(next.items.map((item) => item.kind)).toEqual(["readGrant"]);
  expect(next.items[0].action).toBe("unchanged");
});

it("richer sufficient approval is a real no-op with no grant revision bump", async () => {
  const f = await fixture();
  f.setPermission({
    hostId: "cursor",
    state: "approved",
    reason: null,
    receipt: {
      hostId: "cursor",
      installationId: "old",
      revision: 5,
      status: "approved",
      allowedTools: [
        "om_ask",
        "om_recall",
        "om_conversations",
        "om_diagnostic_trace",
      ],
      allowedScopes: [
        "all-apps",
        "source:cursor",
        `workspace:v1:${"c".repeat(64)}`,
      ],
    },
  });
  const p = await f.controller.preview({
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  });
  expect(p.items[0].action).toBe("unchanged");
  const r = await f.controller.execute({
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(r.state).toBe("completed");
  expect(r.skipped[0].state).toBe("unchanged");
  expect(f.hostPermissions.setPermission).not.toHaveBeenCalled();
  expect(f.hostPermissions.install).not.toHaveBeenCalled();
});

it("unfreezable existing source rights require attention instead of silent downgrade", async () => {
  const f = await fixture();
  f.setPermission({
    hostId: "cursor",
    state: "approved",
    reason: null,
    receipt: {
      hostId: "cursor",
      installationId: "old",
      revision: 5,
      status: "approved",
      allowedTools: ["om_ask"],
      allowedScopes: ["source:revoked"],
    },
  });
  await expect(
    f.controller.preview({ syncSourceIds: [], hostSourceIds: ["cursor"] }),
  ).rejects.toThrow("needs_attention");
  expect(f.hostPermissions.setPermission).not.toHaveBeenCalled();
});

it.each(["install", "grant", "sync"])(
  "source revoked during %s cannot produce a successful receipt",
  async (kind) => {
    const f = await fixture();
    const fn =
      kind === "install"
        ? f.hostPermissions.install
        : kind === "grant"
          ? f.hostPermissions.setPermission
          : f.trusted.setSourceSync;
    const original = fn.getMockImplementation();
    if (!original) throw Error("fixture");
    (
      fn as unknown as {
        mockImplementationOnce(
          implementation: (...args: unknown[]) => Promise<unknown>,
        ): unknown;
      }
    ).mockImplementationOnce(async (...args: unknown[]) => {
      const result = await (
        original as (...args: unknown[]) => Promise<unknown>
      )(...args);
      f.source.authorized = false;
      return result as never;
    });
    const p = await f.controller.preview({
      syncSourceIds: kind === "sync" ? ["cursor"] : [],
      hostSourceIds: kind === "sync" ? [] : ["cursor"],
    });
    const r = await f.controller.execute({
      planId: p.planId,
      digest: p.digest,
      userConfirmed: true,
    });
    expect(r.state).toBe("partial");
    expect(
      r.items.find(
        (item) => item.kind === (kind === "grant" ? "readGrant" : kind),
      )?.state,
    ).toBe("unknown");
    expect(f.source.authorized).toBe(false);
  },
);

it("retains and freezes additional existing source scopes instead of dropping them", async () => {
  const f = await fixture();
  const other = {
    ...f.source,
    source_id: "other",
    root_id: "other-root",
    candidate_root_id: "other-root",
  };
  f.trusted.getSources.mockImplementation(async () => [
    structuredClone(f.source),
    structuredClone(other),
  ]);
  f.setPermission({
    hostId: "cursor",
    state: "approved",
    reason: null,
    receipt: {
      hostId: "cursor",
      installationId: "old",
      revision: 3,
      status: "approved",
      allowedTools: ["om_ask"],
      allowedScopes: ["source:other"],
    },
  });
  const p = await f.controller.preview({
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  });
  expect(p.items[0].sourceIds).toEqual(["cursor", "other"]);
  expect(p.items[0].allowedScopes).toContain("source:other");
  other.authorized = false;
  const result = await f.controller.execute({
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(result.state).toBe("partial");
  expect(f.hostPermissions.setPermission).not.toHaveBeenCalled();
});

it("no-op is revalidated on execute rather than trusting preview", async () => {
  const f = await fixture();
  f.setPermission({
    hostId: "cursor",
    state: "approved",
    reason: null,
    receipt: {
      hostId: "cursor",
      installationId: "old",
      revision: 3,
      status: "approved",
      allowedTools: ["om_recall", "om_conversations", "om_diagnostic_trace"],
      allowedScopes: ["all-apps", "source:cursor"],
    },
  });
  const p = await f.controller.preview({
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  });
  f.source.authorized = false;
  const result = await f.controller.execute({
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(result.state).toBe("partial");
  expect(result.skipped[0].state).toBe("changed");
  expect(f.hostPermissions.setPermission).not.toHaveBeenCalled();
});
