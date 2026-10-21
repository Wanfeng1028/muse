import {
  chmod,
  lstat,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import { createServer, type ServerResponse } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import type { SourceResponse } from "@one-memory/contracts";
import { RecallBroker } from "@one-memory/host-bridge";
import axios from "axios";
import { afterEach, expect, it } from "vitest";
import { createConnectionClient } from "./connection-client.js";
import { createConnectionControlService } from "./connection-control-service.js";
import { HostPermissions } from "./host-permissions.js";

const INSTANCE = "11111111-1111-4111-8111-111111111111";
const TOKEN = "synthetic-management-token";
const cleanups: Array<() => Promise<void>> = [];
afterEach(async () => {
  const failures: unknown[] = [];
  for (const close of cleanups.splice(0).reverse()) {
    try {
      await close();
    } catch (error) {
      failures.push(error);
    }
  }
  expect(failures).toEqual([]);
});

function send(response: ServerResponse, value: unknown, status = 200) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(value));
}

// Core alone is synthetic. No discovery, transport, Broker, controller or ledger mocks.
async function fixture() {
  const parent = await realpath(
    await mkdtemp(path.join(tmpdir(), "d06-wire-")),
  );
  cleanups.push(() => rm(parent, { recursive: true, force: true }));
  const dataDir = path.join(parent, "data");
  await mkdir(dataDir, { mode: 0o700 });
  await chmod(dataDir, 0o700);
  const discoveryPath = path.join(
    dataDir,
    "integrations",
    "cursor-broker.json",
  );
  const source = {
    source_id: "cursor",
    display_name: "Synthetic Cursor",
    authorized: true,
    available: true,
    detected: true,
    candidate_kind: "default",
    root_label: "Synthetic Cursor",
    imported_messages: 0,
    imported_conversations: 0,
    storage_kinds: [],
    sync_completeness: "full_dynamic",
    root_id: "fixture-root",
    candidate_root_id: "fixture-root",
    candidate_path: path.join(parent, "unused-source"),
    grant_revision: 2,
    sync_enabled: false,
    location_state: "found",
    capabilities: {
      historical_import: "implemented",
      incremental_import: "implemented",
      live_sync: "implemented",
      installer: "implemented",
      recall: "implemented",
      verification: "fixture_only",
    },
  } as SourceResponse;
  const posts: unknown[] = [];
  const reads: string[] = [];
  const dispatched: string[] = [];
  const unexpected: string[] = [];
  let coreInstance = INSTANCE;
  let outcome: "success" | "lost-core-response" | "identity-change" = "success";
  const core = createServer(async (request, response) => {
    try {
      if (request.headers.authorization !== `Bearer ${TOKEN}`) {
        unexpected.push("unauthenticated synthetic Core request");
        send(response, {}, 401);
        return;
      }
      if (
        request.method === "GET" &&
        request.url === "/api/v1/runtime/identity"
      ) {
        reads.push("identity");
        send(response, {
          status: "ok",
          service: "one-memory-core",
          version: "synthetic",
          instance_id: coreInstance,
        });
      } else if (
        request.method === "GET" &&
        request.url === "/api/v1/sources"
      ) {
        reads.push("sources");
        send(response, [source]);
      } else if (
        request.method === "POST" &&
        request.url === "/api/v1/sources/cursor/sync-permission"
      ) {
        let raw = "";
        for await (const part of request) raw += part;
        const input = JSON.parse(raw);
        posts.push(input);
        if (input.enabled !== true) {
          unexpected.push("synthetic sync final-state mismatch");
          send(response, { detail: "conflict" }, 409);
          return;
        }
        source.sync_enabled = true;
        if (outcome === "lost-core-response") {
          response.destroy();
          return;
        }
        if (outcome === "identity-change")
          coreInstance = "replacement-instance";
        send(response, {
          source_id: source.source_id,
          sync_enabled: true,
        });
      } else {
        unexpected.push(`${request.method} ${request.url}`);
        send(response, {}, 404);
      }
    } catch {
      unexpected.push("synthetic server handler failure");
      if (!response.destroyed) send(response, {}, 500);
    }
  });
  await new Promise<void>((resolve) => core.listen(0, "127.0.0.1", resolve));
  cleanups.push(async () => {
    core.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      core.close((error) => (error ? reject(error) : resolve())),
    );
    expect(unexpected).toEqual([]);
  });
  const address = core.address();
  if (!address || typeof address === "string")
    throw Error("synthetic port unavailable");
  const coreBaseUrl = `http://127.0.0.1:${address.port}`;
  async function privateJson(name: string, value: unknown) {
    const target = path.join(dataDir, name);
    await writeFile(target, JSON.stringify(value), { mode: 0o600 });
    await chmod(target, 0o600);
  }
  await privateJson("runtime.json", {
    schema_version: 1,
    service: "one-memory-core",
    instance_id: INSTANCE,
    pid: process.pid,
    parent_pid: process.pid,
    host: "127.0.0.1",
    port: address.port,
    started_at: new Date().toISOString(),
  });
  const serviceReceipt = {
    schema_version: 1,
    service: "one-memory-runtime",
    instance_id: INSTANCE,
    pid: process.pid,
    status: "running",
    core_port: address.port,
  };
  await privateJson("runtime-service.json", serviceReceipt);
  await writeFile(path.join(dataDir, "runtime-token"), TOKEN, { mode: 0o600 });
  await chmod(path.join(dataDir, "runtime-token"), 0o600);
  const permissions = await HostPermissions.open(dataDir, {
    runtimeCommand: process.execPath,
    mcpEntryPath: path.join(parent, "unused-mcp.cjs"),
    discoveryPath,
  });
  const options = {
    dataDir,
    connection: { instanceId: INSTANCE, coreApiToken: TOKEN, coreBaseUrl },
    permissions,
    layouts: new Map(),
  };
  let service = createConnectionControlService(options);
  const broker = new RecallBroker({
    coreBaseUrl,
    coreApiToken: TOKEN,
    discoveryPath,
    instanceId: INSTANCE,
    preferredPort: 0,
    hostGrantStore: permissions.hostGrantStore,
    connectionControl(request) {
      dispatched.push(request.action);
      return service.handle(request);
    },
  });
  await broker.start();
  cleanups.push(async () => {
    await service.stop();
    await broker.stop();
  });
  return {
    parent,
    dataDir,
    discoveryPath,
    source,
    posts,
    reads,
    dispatched,
    broker,
    client: () => createConnectionClient({ dataDir }),
    loseCoreResponse() {
      outcome = "lost-core-response";
    },
    changeIdentityOnCommit() {
      outcome = "identity-change";
    },
    setCoreIdentity(value: string) {
      coreInstance = value;
    },
    async reopenService() {
      await service.stop();
      service = createConnectionControlService(options);
    },
    async corruptServiceIdentity() {
      await privateJson("runtime-service.json", {
        ...serviceReceipt,
        instance_id: "wrong-instance",
      });
    },
    async corruptBrokerPid() {
      const discovery = JSON.parse(await readFile(discoveryPath, "utf8"));
      await privateJson("integrations/cursor-broker.json", {
        ...discovery,
        pid: process.ppid,
      });
    },
  };
}

async function noLedger(dataDir: string) {
  expect(await readdir(dataDir)).not.toContain("connection-batches");
}

it("capability and missing receipt cross real discovery and Broker without initializing ledger", async () => {
  const f = await fixture();
  await noLedger(f.dataDir);
  const before = (await readdir(f.dataDir)).sort();
  const client = f.client();
  expect(f.dispatched).toEqual([]);
  expect(await client.capability()).toEqual({ available: true });
  expect(await client.receipt("missing-operation")).toBeNull();
  expect(f.dispatched).toEqual(["capability", "receipt"]);
  expect(f.posts).toEqual([]);
  expect(f.reads.length).toBeGreaterThan(0);
  expect(f.reads.every((route) => route === "identity")).toBe(true);
  expect((await readdir(f.dataDir)).sort()).toEqual(before);
  await noLedger(f.dataDir);
  for (const name of [
    "runtime.json",
    "runtime-service.json",
    "runtime-token",
    "integrations/cursor-broker.json",
  ])
    expect((await lstat(path.join(f.dataDir, name))).mode & 0o777).toBe(0o600);
});

it("preview and execute apply direct final-state sync with no receipt", async () => {
  const f = await fixture();
  const client = f.client();
  const plan = await client.preview({
    syncSourceIds: ["cursor"],
    hostSourceIds: [],
  });
  expect(plan.items).toEqual([
    {
      id: "sync:cursor",
      kind: "sync",
      sourceIds: ["cursor"],
      restoresRevoked: false,
    },
  ]);
  expect(f.posts).toEqual([]);
  const input = {
    planId: plan.planId,
    digest: plan.digest,
    userConfirmed: true as const,
  };
  const result = await client.execute(input);
  expect(result.state).toBe("completed");
  expect(result.items[0]).toMatchObject({
    state: "succeeded",
    receipt: null,
  });
  expect(f.posts).toEqual([{ enabled: true }]);
  const before = await client.receipt(plan.operationId);
  expect(before).toBeNull();
  await f.reopenService();
  const reopened = f.client();
  expect(await reopened.receipt(plan.operationId)).toEqual(before);
  await expect(reopened.execute(input)).rejects.toThrow(
    "connection_client_plan_missing",
  );
  await expect(client.execute(input)).rejects.toThrow(
    "connection_client_operation_unknown",
  );
  expect(f.dispatched.filter((action) => action === "execute")).toHaveLength(1);
  expect(f.posts).toHaveLength(1);
  expect(JSON.stringify({ plan, result, before })).not.toContain(f.parent);
  expect(JSON.stringify({ plan, result, before })).not.toContain(TOKEN);
  const ledger = path.join(f.dataDir, "connection-batches");
  const journals = (await readdir(ledger)).filter((name) =>
    /^[a-f0-9]{64}\.json$/.test(name),
  );
  expect(journals).toHaveLength(0);
});

it.each(["core-response-lost", "identity-changed-after-commit"])(
  "%s is resolved by a new preview reading final state, without a receipt",
  async (mode) => {
    const f = await fixture();
    const client = f.client();
    const plan = await client.preview({
      syncSourceIds: ["cursor"],
      hostSourceIds: [],
    });
    const input = {
      planId: plan.planId,
      digest: plan.digest,
      userConfirmed: true as const,
    };
    if (mode === "core-response-lost") f.loseCoreResponse();
    else f.changeIdentityOnCommit();
    if (mode === "core-response-lost") {
      const result = await client.execute(input);
      expect(result.state).toBe("completed");
      expect(result.items[0]).toMatchObject({
        state: "succeeded",
        receipt: null,
      });
    } else {
      await expect(client.execute(input)).rejects.toThrow(
        "connection_client_operation_unknown",
      );
      f.setCoreIdentity(INSTANCE);
    }
    await expect(client.execute(input)).rejects.toThrow(
      "connection_client_operation_unknown",
    );
    expect(f.source.sync_enabled).toBe(true);
    expect(f.posts).toHaveLength(1);
    await f.reopenService();
    const reopened = f.client();
    expect(await reopened.receipt(plan.operationId)).toBeNull();
    await expect(reopened.execute(input)).rejects.toThrow(
      "connection_client_plan_missing",
    );
    const retry = await reopened.preview({
      syncSourceIds: ["cursor"],
      hostSourceIds: [],
    });
    expect(
      (
        await reopened.execute({
          planId: retry.planId,
          digest: retry.digest,
          userConfirmed: true,
        })
      ).items[0].state,
    ).toBe("succeeded");
    expect(f.posts).toHaveLength(1);
    expect(f.dispatched.filter((action) => action === "execute")).toHaveLength(
      2,
    );
  },
);

it.each(["core", "service", "broker-pid", "token-mode"])(
  "invalid %s identity rejects before control dispatch or ledger creation",
  async (kind) => {
    const f = await fixture();
    expect(await f.client().capability()).toEqual({ available: true });
    const before = [...f.dispatched];
    if (kind === "core") f.setCoreIdentity("other-core");
    else if (kind === "service") await f.corruptServiceIdentity();
    else if (kind === "broker-pid") await f.corruptBrokerPid();
    else await chmod(path.join(f.dataDir, "runtime-token"), 0o644);
    await expect(
      f.client().preview({ syncSourceIds: ["cursor"], hostSourceIds: [] }),
    ).rejects.toThrow("connection_client_runtime_unavailable");
    expect(f.dispatched).toEqual(before);
    expect(f.posts).toEqual([]);
    await noLedger(f.dataDir);
  },
);

it("real Broker rejects wrong management token and request instance before service admission", async () => {
  const f = await fixture();
  for (const [token, instance, status] of [
    ["wrong-token", INSTANCE, 403],
    [TOKEN, "wrong-instance", 400],
  ] as const) {
    const response = await axios.post(
      `http://127.0.0.1:${f.broker.port}/control/connections`,
      {
        schema_version: 1,
        instance_id: instance,
        action: "capability",
        input: {},
      },
      {
        headers: { Authorization: `Bearer ${token}` },
        proxy: false,
        maxRedirects: 0,
        timeout: 2000,
        validateStatus: () => true,
      },
    );
    expect(response.status).toBe(status);
  }
  expect(f.dispatched).toEqual([]);
  expect(f.posts).toEqual([]);
  await noLedger(f.dataDir);
});
