import { EventEmitter } from "node:events";
import {
  mkdtemp,
  readdir,
  readFile,
  realpath,
  rm,
  unlink,
  writeFile,
} from "node:fs/promises";
import { createServer, type Server } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import type {
  ConnectionSetupJournal,
  ConnectionSetupPreview,
  SourceResponse,
} from "@one-memory/contracts";
import type { RecallHostLayout } from "@one-memory/host-bridge/installer";
import type { IpcMainInvokeEvent } from "electron";
import { afterEach, expect, it, vi } from "vitest";
import { PersistentBatchLedger } from "../../../packages/runtime-control/src/connection-batch-ledger.js";
import {
  connectionHostId,
  installConnectionSetupIpc,
} from "./connection-setup-ipc";
import type {
  RecallPermissionStatus,
  SetRecallPermissionInput,
} from "./host-permissions";

const roots: string[] = [];
const servers: Server[] = [];
const preload = vi.hoisted(() => ({ expose: vi.fn(), invoke: vi.fn() }));
vi.mock("electron", () => ({
  contextBridge: { exposeInMainWorld: preload.expose },
  ipcRenderer: { invoke: preload.invoke },
}));
afterEach(async () => {
  await Promise.all(
    servers
      .splice(0)
      .map(
        (s) => new Promise<void>((r, j) => s.close((e) => (e ? j(e) : r()))),
      ),
  );
  await Promise.all(
    roots.splice(0).map((r) => rm(r, { recursive: true, force: true })),
  );
});
async function fixture(
  withHost = false,
  disabledReason?: "noncanonical_data_dir" | "app_not_in_applications",
) {
  const dataDir = await realpath(
    await mkdtemp(path.join(tmpdir(), "setup-ipc-")),
  );
  roots.push(dataDir);
  const source: SourceResponse = {
    source_id: "cursor",
    display_name: "Cursor",
    storage_kinds: ["jsonl"],
    available: true,
    authorized: true,
    detected: true,
    root_label: "fixture",
    candidate_path: dataDir,
    candidate_kind: "default",
    root_id: "root",
    candidate_root_id: "root",
    grant_revision: 1,
    sync_enabled: false,
    location_state: "found",
    imported_messages: 1,
    imported_conversations: 1,
    sync_completeness: "additions_only",
    capabilities: {
      historical_import: "implemented",
      incremental_import: "implemented",
      live_sync: "implemented",
      recall: "implemented",
      installer: "implemented",
      verification: "fixture_only",
    },
  };
  const requests: Array<{
    method: string | undefined;
    url: string | undefined;
    authorization: string | undefined;
    body: unknown;
  }> = [];
  let respondSync: (() => Promise<void>) | null = null;
  let malformedSyncResponse = false;
  let identity = "core-one";
  let expectedIdentity = "core-one";
  const server = createServer(async (req, res) => {
    let body = "";
    for await (const c of req) body += c;
    requests.push({
      method: req.method,
      url: req.url,
      authorization: req.headers.authorization,
      body: body ? JSON.parse(body) : null,
    });
    res.setHeader("content-type", "application/json");
    if (req.headers.authorization !== "Bearer synthetic-token") {
      res.writeHead(401);
      res.end("{}");
      return;
    }
    if (req.url === "/api/v1/runtime/identity") {
      res.end(
        JSON.stringify({
          status: "ok",
          service: "one-memory-core",
          instance_id: identity,
        }),
      );
      return;
    }
    if (req.url === "/api/v1/sources") {
      res.end(JSON.stringify([source]));
      return;
    }
    if (req.url === "/api/v1/sources/cursor/sync-permission") {
      await respondSync?.();
      source.sync_enabled = true;
      res.end(
        JSON.stringify({
          source_id: "cursor",
          sync_enabled: true,
          ...(malformedSyncResponse ? { unexpected: true } : {}),
        }),
      );
      return;
    }
    res.writeHead(404);
    res.end("{}");
  });
  servers.push(server);
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const address = server.address();
  if (!address || typeof address === "string") throw Error("fixture");
  const handlers = new Map<
    string,
    (event: IpcMainInvokeEvent, ...args: unknown[]) => unknown
  >();
  const frame = { url: "one-memory://app/index.html" };
  const sender = Object.assign(new EventEmitter(), { mainFrame: frame });
  const window = Object.assign(new EventEmitter(), { webContents: sender });
  const event = { sender, senderFrame: frame } as unknown as IpcMainInvokeEvent;
  const trustedWindows = new Map([[event, window]]);
  const trusted = vi.fn((e: IpcMainInvokeEvent) => {
    const owned = trustedWindows.get(e);
    if (!owned || e.senderFrame?.url !== "one-memory://app/index.html")
      throw Error("UNTRUSTED_SECRET");
    return owned;
  });
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
          installationId: "install-one",
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
    setPermission: vi.fn(async (_layout: RecallHostLayout, input: unknown) => {
      const grant = input as SetRecallPermissionInput;
      permission = {
        hostId: "cursor",
        state: "approved",
        reason: null,
        receipt: {
          hostId: "cursor",
          installationId: grant.installationId,
          revision: grant.expectedRevision + 1,
          status: "approved",
          allowedTools: grant.allowedTools,
          allowedScopes: grant.allowedScopes,
        },
      };
      return structuredClone(permission);
    }),
  };
  const options: Parameters<typeof installConnectionSetupIpc>[0] = {
    ipc: {
      handle: (name, fn) => {
        handlers.set(name, fn);
      },
      removeHandler: (name) => {
        handlers.delete(name);
      },
    },
    dataDir,
    getCore: () => ({
      port: address.port,
      apiToken: "synthetic-token",
      instanceId: expectedIdentity,
    }),
    requireTrustedWindow: trusted,
    hostPermissions,
    hosts: withHost
      ? [
          {
            hostId: "cursor",
            label: "Cursor",
            presencePath: dataDir,
            layout: {
              hostId: "cursor",
              hostLabel: "Cursor",
              configPath: path.join(dataDir, "fixture-mcp.json"),
              format: "json",
              channel: "mcp",
              skillPath: null,
              journalPath: path.join(dataDir, "fixture-install.json"),
              containmentRoot: dataDir,
            },
          },
        ]
      : [],
    platform: "darwin",
    ...(disabledReason ? { disabledReason } : {}),
  };
  let bridge = installConnectionSetupIpc(options);
  const call = (name: string, ...args: unknown[]) => {
    const fn = handlers.get(`one-memory:connection-setup-${name}`);
    if (!fn) throw Error("missing handler");
    return Promise.resolve(fn(event, ...args));
  };
  return {
    dataDir,
    source,
    requests,
    get bridge() {
      return bridge;
    },
    handlers,
    event,
    window,
    frame,
    call,
    hostPermissions,
    async reopen() {
      const oldReceipt = handlers.get("one-memory:connection-setup-receipt");
      await bridge.drain();
      bridge.dispose();
      expect(handlers.size).toBe(0);
      expect(window.listenerCount("closed")).toBe(0);
      expect(sender.listenerCount("did-start-navigation")).toBe(0);
      bridge = installConnectionSetupIpc(options);
      expect(handlers.size).toBe(4);
      expect(handlers.get("one-memory:connection-setup-receipt")).not.toBe(
        oldReceipt,
      );
      return oldReceipt;
    },
    newWindow() {
      const frame = { url: "one-memory://app/index.html" };
      const sender = Object.assign(new EventEmitter(), { mainFrame: frame });
      const window = Object.assign(new EventEmitter(), { webContents: sender });
      const event = {
        sender,
        senderFrame: frame,
      } as unknown as IpcMainInvokeEvent;
      trustedWindows.set(event, window);
      return {
        window,
        event,
        call(name: string, ...args: unknown[]) {
          const handler = handlers.get(`one-memory:connection-setup-${name}`);
          if (!handler) throw Error("missing handler");
          return Promise.resolve(handler(event, ...args));
        },
      };
    },
    setSyncGate: (v: () => Promise<void>) => {
      respondSync = v;
    },
    malformedSyncResponse: () => {
      malformedSyncResponse = true;
    },
    changeIdentity: () => {
      identity = "another-core";
    },
    replaceVerifiedCoreSession: () => {
      identity = "core-session-two";
      expectedIdentity = identity;
    },
  };
}
it("capability is read-only; preview persists only control metadata; execute uses the simplified sync protocol", async () => {
  const f = await fixture();
  expect(await f.call("capability")).toMatchObject({ available: true });
  expect(await readdir(f.dataDir)).toEqual([]);
  const p = (await f.call("preview", {
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  })) as { planId: string; digest: string; operationId: string };
  expect(f.requests.filter((r) => r.body)).toEqual([]);
  expect(f.hostPermissions.install).not.toHaveBeenCalled();
  const result = await f.call("execute", {
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(result).toMatchObject({
    state: "completed",
    recovery: "none",
    items: [
      {
        id: "sync:cursor",
        kind: "sync",
        state: "succeeded",
        receipt: null,
      },
    ],
  });
  expect(f.requests.find((r) => r.body)?.body).toEqual({
    enabled: true,
  });
  expect(
    f.requests.every((r) => r.authorization === "Bearer synthetic-token"),
  ).toBe(true);
  expect(JSON.stringify(result)).not.toMatch(
    /synthetic-token|rootPath|runtimeId/,
  );
  expect(await f.call("receipt", p.operationId)).toBeNull();
  await f.bridge.drain();
  f.bridge.dispose();
  expect(f.handlers.size).toBe(0);
});
it("rejects untrusted windows, extra paths/tools/args before any metadata or HTTP work", async () => {
  const f = await fixture();
  for (const name of ["capability", "preview", "execute", "receipt"]) {
    const fn = f.handlers.get(`one-memory:connection-setup-${name}`);
    await expect(fn?.({} as IpcMainInvokeEvent)).rejects.toThrow(
      "connection_setup_untrusted_window",
    );
  }
  await expect(
    f.call("preview", {
      syncSourceIds: ["cursor"],
      hostSourceIds: [],
      tools: ["om_ask"],
    }),
  ).rejects.toThrow("invalid_input");
  await expect(f.call("capability", {})).rejects.toThrow("invalid_input");
  expect(f.requests).toHaveLength(0);
  expect(await readdir(f.dataDir)).toEqual([]);
  f.bridge.dispose();
});
it("closes admission, aborts later effects and drains admitted request before releasing executor lock", async () => {
  const f = await fixture();
  const p = (await f.call("preview", {
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  })) as { planId: string; digest: string };
  let release!: () => void;
  let started!: () => void;
  const ready = new Promise<void>((r) => {
    started = r;
  });
  f.setSyncGate(async () => {
    started();
    await new Promise<void>((r) => {
      release = r;
    });
  });
  const executing = f.call("execute", {
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  await ready;
  let drained = false;
  const drain = f.bridge.drain().then(() => {
    drained = true;
  });
  await new Promise((r) => setTimeout(r, 20));
  expect(drained).toBe(false);
  await expect(
    f.call("preview", { syncSourceIds: [], hostSourceIds: [] }),
  ).rejects.toThrow("closing");
  release();
  expect(await executing).toMatchObject({ cancelled: true });
  await drain;
  expect(drained).toBe(true);
  expect(
    await readdir(path.join(f.dataDir, "connection-batches")),
  ).not.toContain("execution.lock");
  f.bridge.dispose();
});
it("malformed sync response is resolved from the current final state", async () => {
  const f = await fixture();
  const p = (await f.call("preview", {
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  })) as { planId: string; digest: string };
  f.malformedSyncResponse();
  expect(
    await f.call("execute", {
      planId: p.planId,
      digest: p.digest,
      userConfirmed: true,
    }),
  ).toMatchObject({
    state: "completed",
    items: [{ kind: "sync", state: "succeeded", receipt: null }],
  });
  await f.bridge.drain();
  f.bridge.dispose();
});
it("receipt read does not initialize an absent ledger", async () => {
  const f = await fixture();
  expect(await f.call("receipt", "operation")).toBeNull();
  expect(await readdir(f.dataDir)).toEqual([]);
  f.bridge.dispose();
});

it("trusted layout creates separate install/grant receipts and sufficient grants return true skipped no-op", async () => {
  const f = await fixture(true);
  const p = (await f.call("preview", {
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  })) as { planId: string; digest: string };
  expect(f.hostPermissions.install).not.toHaveBeenCalled();
  const result = await f.call("execute", {
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  expect(result).toMatchObject({
    state: "completed",
    items: [
      { kind: "install", state: "succeeded" },
      { kind: "readGrant", state: "succeeded" },
    ],
  });
  const grant = f.hostPermissions.setPermission.mock
    .calls[0]?.[1] as SetRecallPermissionInput;
  expect(grant).toEqual({
    installationId: "install-one",
    expectedRevision: 1,
    allowedTools: ["om_recall", "om_conversations", "om_diagnostic_trace"],
    allowedScopes: ["all-apps", "source:cursor"],
    userConfirmed: true,
  });
  const next = (await f.call("preview", {
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  })) as { planId: string; digest: string };
  expect(
    await f.call("execute", {
      planId: next.planId,
      digest: next.digest,
      userConfirmed: true,
    }),
  ).toMatchObject({
    state: "completed",
    items: [],
    skipped: [{ state: "unchanged" }],
  });
  expect(f.hostPermissions.setPermission).toHaveBeenCalledTimes(1);
  const binding = JSON.parse(
    await readFile(
      path.join(f.dataDir, "connection-batches", "owner.json"),
      "utf8",
    ),
  );
  expect(binding.runtimeId).toMatch(/^[a-f0-9]{64}$/);
  expect(binding.runtimeId).not.toBe("core-one");
  expect(binding).not.toHaveProperty("pid");
  await f.bridge.drain();
  f.bridge.dispose();
});

it("changed runtime identity blocks capability and effects without exposing token", async () => {
  const f = await fixture();
  f.changeIdentity();
  expect(await f.call("capability")).toEqual({
    available: false,
    reason: "runtime_unavailable",
  });
  await expect(
    f.call("preview", { syncSourceIds: ["cursor"], hostSourceIds: [] }),
  ).rejects.toThrow("connection_setup_runtime_unavailable");
  expect(await readdir(f.dataDir)).toEqual([]);
  f.bridge.dispose();
});

it("closed renderer waits for admitted sync, rejects delivery and does not invent a persistent receipt", async () => {
  const f = await fixture();
  const p = (await f.call("preview", {
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  })) as { planId: string; digest: string; operationId: string };
  let release!: () => void;
  let started!: () => void;
  const ready = new Promise<void>((r) => {
    started = r;
  });
  f.setSyncGate(async () => {
    started();
    await new Promise<void>((r) => {
      release = r;
    });
  });
  const pending = f.call("execute", {
    planId: p.planId,
    digest: p.digest,
    userConfirmed: true,
  });
  const rejected = expect(pending).rejects.toThrow("context_changed");
  await ready;
  f.window.emit("closed");
  release();
  await rejected;
  expect(await f.call("receipt", p.operationId)).toBeNull();
  expect(f.window.listenerCount("closed")).toBe(0);
  expect(f.window.webContents.listenerCount("did-start-navigation")).toBe(0);
  await f.bridge.drain();
  f.bridge.dispose();
});

it("maps every exact one-click host and keeps profile-based Harness out", () => {
  for (const id of [
    "cursor",
    "claude-code",
    "codex",
    "workbuddy",
    "opencode",
    "qwen-code",
    "hermes",
    "pi",
  ])
    expect(connectionHostId(id)).toBe(id);
  expect(connectionHostId("openclaw")).toBeNull();
  expect(connectionHostId("deepseek-harness")).toBeNull();
});

it("unmapped host IDs cannot reach native installers", async () => {
  const f = await fixture();
  await expect(
    f.call("preview", { syncSourceIds: [], hostSourceIds: ["unknown-host"] }),
  ).rejects.toThrow("connection_setup_unavailable");
  await expect(
    f.call("preview", { syncSourceIds: [], hostSourceIds: ["cursor"] }),
  ).rejects.toThrow("connection_setup_unavailable");
  expect(f.hostPermissions.install).not.toHaveBeenCalled();
  await f.bridge.drain();
  f.bridge.dispose();
});

it("capability reports corrupted existing metadata without repairing it", async () => {
  const f = await fixture();
  await f.call("preview", { syncSourceIds: ["cursor"], hostSourceIds: [] });
  const file = path.join(f.dataDir, "connection-batches", "owner.json");
  await writeFile(file, "{}");
  expect(await f.call("capability")).toEqual({
    available: false,
    reason: "storage_unavailable",
  });
  expect(await readFile(file, "utf8")).toBe("{}");
  f.bridge.dispose();
});

it("reports a noncanonical test data directory without opening storage", async () => {
  const f = await fixture(false, "noncanonical_data_dir");
  expect(await f.call("capability")).toEqual({
    available: false,
    reason: "noncanonical_data_dir",
  });
  expect(f.requests).toEqual([]);
  f.bridge.dispose();
});

it("reports a blocked app location as the reason connection setup is unavailable", async () => {
  const f = await fixture(false, "app_not_in_applications");
  expect(await f.call("capability")).toEqual({
    available: false,
    reason: "app_not_in_applications",
  });
  expect(f.requests).toEqual([]);
  f.bridge.dispose();
});

it("preload exposes only typed setup methods and exact invoke payloads", async () => {
  await import("./preload.js");
  const bridge = preload.expose.mock.calls[0]?.[1] as {
    getConnectionSetupCapability(): Promise<unknown>;
    previewConnectionSetup(input: unknown): Promise<unknown>;
    executeConnectionSetup(input: unknown): Promise<unknown>;
    getConnectionSetupReceipt(id: string): Promise<unknown>;
  };
  await bridge.getConnectionSetupCapability();
  await bridge.previewConnectionSetup({
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  });
  await bridge.executeConnectionSetup({
    planId: "p",
    digest: "a".repeat(64),
    userConfirmed: true,
  });
  await bridge.getConnectionSetupReceipt("op");
  expect(preload.invoke.mock.calls).toEqual([
    ["one-memory:connection-setup-capability"],
    [
      "one-memory:connection-setup-preview",
      { syncSourceIds: ["cursor"], hostSourceIds: [] },
    ],
    [
      "one-memory:connection-setup-execute",
      { planId: "p", digest: "a".repeat(64), userConfirmed: true },
    ],
    ["one-memory:connection-setup-receipt", "op"],
  ]);
});

async function controlFiles(dataDir: string) {
  const directory = path.join(dataDir, "connection-batches");
  const files = (await readdir(directory)).sort();
  return Object.fromEntries(
    await Promise.all(
      files.map(async (file) => [
        file,
        await readFile(path.join(directory, file), "utf8"),
      ]),
    ),
  );
}

function effectCounts(f: Awaited<ReturnType<typeof fixture>>) {
  return {
    sync: f.requests.filter((request) => request.method === "POST").length,
    install: f.hostPermissions.install.mock.calls.length,
    grant: f.hostPermissions.setPermission.mock.calls.length,
    hostReads: f.hostPermissions.getPermission.mock.calls.length,
    previews: f.hostPermissions.previewInstall.mock.calls.length,
  };
}

it("reopened controller reads committed journal from a new trusted window with GET-only recovery and rejects the old plan", async () => {
  const f = await fixture(true);
  const preview = (await f.call("preview", {
    syncSourceIds: ["cursor"],
    hostSourceIds: ["cursor"],
  })) as ConnectionSetupPreview;
  expect(
    await f.call("execute", {
      planId: preview.planId,
      digest: preview.digest,
      userConfirmed: true,
    }),
  ).toMatchObject({ state: "completed" });
  const expected = (await f.call(
    "receipt",
    preview.operationId,
  )) as ConnectionSetupJournal;
  expect(expected.items).toHaveLength(2);
  expect(expected.items.map((item) => item.kind)).toEqual([
    "install",
    "readGrant",
  ]);
  expect(effectCounts(f)).toMatchObject({ sync: 1, install: 1, grant: 1 });
  const files = await controlFiles(f.dataDir);
  const counts = effectCounts(f);
  const requestIndex = f.requests.length;
  // The trusted connection session may change; persisted ownership must not.
  f.replaceVerifiedCoreSession();
  const oldHandler = await f.reopen();
  await expect(oldHandler?.(f.event, preview.operationId)).rejects.toThrow(
    "connection_setup_closing",
  );
  const fresh = f.newWindow();
  expect(await fresh.call("receipt", preview.operationId)).toEqual(expected);
  await expect(
    fresh.call("execute", {
      planId: preview.planId,
      digest: preview.digest,
      userConfirmed: true,
    }),
  ).rejects.toThrow("connection_setup_plan_missing");
  const reads = f.requests.slice(requestIndex);
  expect(reads.length).toBeGreaterThan(0);
  expect(
    reads.every(
      (request) =>
        request.method === "GET" && request.url === "/api/v1/runtime/identity",
    ),
  ).toBe(true);
  expect(effectCounts(f)).toEqual(counts);
  expect(await controlFiles(f.dataDir)).toEqual(files);
  expect(fresh.window.listenerCount("closed")).toBe(0);
  expect(fresh.window.webContents.listenerCount("did-start-navigation")).toBe(
    0,
  );
  await f.bridge.drain();
  f.bridge.dispose();
  expect(f.handlers.size).toBe(0);
});

it("direct sync status is never reconstructed as a persistent receipt", async () => {
  const f = await fixture();
  const p = (await f.call("preview", {
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  })) as ConnectionSetupPreview;
  f.malformedSyncResponse();
  expect(
    await f.call("execute", {
      planId: p.planId,
      digest: p.digest,
      userConfirmed: true,
    }),
  ).toMatchObject({
    state: "completed",
    items: [{ state: "succeeded", receipt: null }],
  });
  expect(f.source.sync_enabled).toBe(true);
  const counts = effectCounts(f),
    files = await controlFiles(f.dataDir);
  expect(await f.call("receipt", p.operationId)).toBeNull();
  await f.reopen();
  expect(await f.call("receipt", p.operationId)).toBeNull();
  expect(effectCounts(f)).toEqual(counts);
  expect(await controlFiles(f.dataDir)).toEqual(files);
  await f.bridge.drain();
  f.bridge.dispose();
});

it("reopened in_flight install journal is read as partial without reconcile or effect execution", async () => {
  const f = await fixture();
  await f.call("preview", { syncSourceIds: ["cursor"], hostSourceIds: [] });
  const binding = JSON.parse(
    await readFile(
      path.join(f.dataDir, "connection-batches", "owner.json"),
      "utf8",
    ),
  );
  const owner = {
    userId: binding.userId as string,
    runtimeId: binding.runtimeId as string,
  };
  const ledger = await PersistentBatchLedger.open(f.dataDir, owner);
  const operationId = "interrupted-operation";
  await ledger.exclusive(owner, () =>
    ledger.commit(owner, operationId, null, {
      schemaVersion: 1,
      ...owner,
      operationId,
      planDigest: "a".repeat(64),
      revision: 1,
      items: [
        {
          id: "install:cursor",
          kind: "install",
          intentDigest: "b".repeat(64),
          state: "in_flight",
          receipt: null,
        },
      ],
    }),
  );
  const files = await controlFiles(f.dataDir),
    counts = effectCounts(f);
  await f.reopen();
  expect(await f.newWindow().call("receipt", operationId)).toEqual({
    operationId,
    planDigest: "a".repeat(64),
    revision: 1,
    state: "partial",
    items: [
      {
        id: "install:cursor",
        kind: "install",
        state: "in_flight",
        receipt: null,
      },
    ],
  });
  expect(effectCounts(f)).toEqual(counts);
  expect(await controlFiles(f.dataDir)).toEqual(files);
  await f.bridge.drain();
  f.bridge.dispose();
});

it.each([
  "journal-corrupt",
  "binding-corrupt",
  "owner-mismatch",
  "journal-owner-mismatch",
  "binding-missing",
])(
  "reopened receipt rejects %s without repairing storage or writing effects",
  async (kind) => {
    const f = await fixture(true);
    const p = (await f.call("preview", {
      syncSourceIds: [],
      hostSourceIds: ["cursor"],
    })) as ConnectionSetupPreview;
    await f.call("execute", {
      planId: p.planId,
      digest: p.digest,
      userConfirmed: true,
    });
    const directory = path.join(f.dataDir, "connection-batches");
    const names = await readdir(directory);
    const journal = names.find((name) => /^[a-f0-9]{64}\.json$/.test(name));
    if (!journal) throw Error("missing positive journal");
    const file = path.join(
      directory,
      kind.startsWith("journal") ? journal : "owner.json",
    );
    const data = JSON.parse(await readFile(file, "utf8"));
    if (kind === "binding-missing") await unlink(file);
    else
      await writeFile(
        file,
        kind.endsWith("corrupt")
          ? "{"
          : JSON.stringify({ ...data, runtimeId: "other-owner" }),
      );
    const before = await controlFiles(f.dataDir),
      counts = effectCounts(f);
    await f.reopen();
    await expect(f.newWindow().call("receipt", p.operationId)).rejects.toThrow(
      "connection_setup_unavailable",
    );
    expect(await controlFiles(f.dataDir)).toEqual(before);
    expect(effectCounts(f)).toEqual(counts);
    await f.bridge.drain();
    f.bridge.dispose();
  },
);

it("reopened missing operation never initializes absent Ledger or creates a journal in an existing one", async () => {
  const f = await fixture();
  await f.reopen();
  expect(await f.newWindow().call("receipt", "missing")).toBeNull();
  expect(await readdir(f.dataDir)).toEqual([]);
  await f.call("preview", { syncSourceIds: ["cursor"], hostSourceIds: [] });
  const before = await controlFiles(f.dataDir);
  expect(Object.keys(before)).toEqual(["owner.json"]);
  await f.reopen();
  expect(await f.call("receipt", "missing")).toBeNull();
  expect(await controlFiles(f.dataDir)).toEqual(before);
  expect(effectCounts(f)).toMatchObject({ sync: 0, install: 0, grant: 0 });
  await f.bridge.drain();
  f.bridge.dispose();
});

it("no-op-only completion has no mutation journal after reopen and is not reconstructed as success", async () => {
  const f = await fixture(true);
  const first = (await f.call("preview", {
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  })) as ConnectionSetupPreview;
  await f.call("execute", {
    planId: first.planId,
    digest: first.digest,
    userConfirmed: true,
  });
  const noop = (await f.call("preview", {
    syncSourceIds: [],
    hostSourceIds: ["cursor"],
  })) as ConnectionSetupPreview;
  expect(
    await f.call("execute", {
      planId: noop.planId,
      digest: noop.digest,
      userConfirmed: true,
    }),
  ).toMatchObject({
    state: "completed",
    items: [],
    skipped: [{ state: "unchanged" }],
  });
  const before = await controlFiles(f.dataDir),
    counts = effectCounts(f);
  await f.reopen();
  expect(await f.call("receipt", noop.operationId)).toBeNull();
  expect(await f.call("receipt", first.operationId)).toMatchObject({
    state: "completed",
  });
  expect(await controlFiles(f.dataDir)).toEqual(before);
  expect(effectCounts(f)).toEqual(counts);
  await f.bridge.drain();
  f.bridge.dispose();
});
