import { createHash } from "node:crypto";
import {
  chmod,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  realpath,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { createServer, type ServerResponse } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import type { SourceResponse } from "@one-memory/contracts";
import type { ConnectionControlRequest } from "@one-memory/host-bridge";
import { afterEach, expect, it, vi } from "vitest";
import type { BatchResult } from "./connection-batch.js";
import { createConnectionControlService } from "./connection-control-service.js";
import type { ConnectionControllerPreview } from "./connection-controller.js";
import type { HostPermissions } from "./host-permissions.js";

const INSTANCE = "11111111-1111-4111-8111-111111111111";
const cleanup: Array<() => Promise<void>> = [];
afterEach(async () => {
  for (const close of cleanup.splice(0).reverse()) await close();
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function send(response: ServerResponse, value: unknown, status = 200) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(value));
}
async function fixture() {
  const parent = await realpath(
    await mkdtemp(path.join(tmpdir(), "d06-service-")),
  );
  const dataDir = path.join(parent, "data");
  await mkdir(dataDir, { mode: 0o700 });
  await chmod(dataDir, 0o700);
  cleanup.push(() => rm(parent, { recursive: true, force: true }));
  const source = {
    source_id: "cursor",
    display_name: "Cursor",
    authorized: true,
    available: true,
    detected: true,
    candidate_kind: "default",
    imported_messages: 0,
    imported_conversations: 0,
    storage_kinds: [],
    sync_completeness: "full_dynamic",
    root_id: "fixture-root",
    root_label: "Synthetic source",
    candidate_root_id: "fixture-root",
    candidate_path: path.join(parent, "source"),
    grant_revision: 2,
    sync_enabled: false,
    location_state: "found",
    capabilities: {
      historical_import: "implemented",
      incremental_import: "implemented",
      verification: "fixture_only",
      live_sync: "implemented",
      installer: "implemented",
      recall: "implemented",
    },
  } as SourceResponse;
  const posts: unknown[] = [];
  const reads: string[] = [];
  const failures: string[] = [];
  let coreInstance = INSTANCE;
  let loseResponse = false;
  let badReceipt = false;
  let gate: ReturnType<typeof deferred<void>> | null = null;
  const admitted = deferred<void>();
  const server = createServer(async (request, response) => {
    try {
      if (request.headers.authorization !== "Bearer fixture-token") {
        failures.push("missing authentication");
        send(response, {}, 401);
        return;
      }
      if (request.url === "/api/v1/runtime/identity") {
        reads.push("identity");
        send(response, {
          status: "ok",
          service: "one-memory-core",
          instance_id: coreInstance,
        });
      } else if (request.url === "/api/v1/sources") {
        reads.push("sources");
        send(response, [source]);
      } else if (
        request.url === "/api/v1/sources/cursor/sync-permission" &&
        request.method === "POST"
      ) {
        let body = "";
        for await (const chunk of request) body += chunk;
        const input = JSON.parse(body);
        posts.push(input);
        if (input.enabled !== true) {
          failures.push("invalid final state");
          send(response, { detail: "conflict" }, 409);
          return;
        }
        source.sync_enabled = true;
        admitted.resolve();
        if (gate) await gate.promise;
        if (loseResponse) {
          response.destroy();
          return;
        }
        send(response, {
          source_id: badReceipt ? "wrong" : "cursor",
          sync_enabled: true,
        });
      } else {
        failures.push(`unexpected route ${request.url}`);
        send(response, {}, 404);
      }
    } catch {
      if (!response.destroyed) send(response, {}, 500);
    }
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  cleanup.push(async () => {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
    expect(failures).toEqual([]);
  });
  const address = server.address();
  if (!address || typeof address === "string") throw Error("fixture address");
  const permissions = {
    getPermission: vi.fn(),
    previewInstall: vi.fn(),
    install: vi.fn(),
    setPermission: vi.fn(),
  };
  const options = {
    dataDir,
    connection: {
      instanceId: INSTANCE,
      coreApiToken: "fixture-token",
      coreBaseUrl: `http://127.0.0.1:${address.port}`,
    },
    permissions: permissions as unknown as HostPermissions,
    layouts: new Map(),
  };
  function service() {
    const value = createConnectionControlService(options);
    cleanup.push(async () => {
      gate?.resolve();
      await value.stop();
    });
    return value;
  }
  return {
    parent,
    dataDir,
    source,
    posts,
    reads,
    permissions,
    service,
    setInstance(value: string) {
      coreInstance = value;
    },
    lose() {
      loseResponse = true;
    },
    bad() {
      badReceipt = true;
    },
    hold() {
      gate = deferred<void>();
      return { entered: admitted.promise, release: () => gate?.resolve() };
    },
  };
}
function request(
  action: ConnectionControlRequest["action"],
  input: Record<string, unknown> = {},
): ConnectionControlRequest {
  return { schema_version: 1, instance_id: INSTANCE, action, input };
}
async function preview(
  service: ReturnType<typeof createConnectionControlService>,
) {
  return (await service.handle(
    request("preview", { syncSourceIds: ["cursor"], hostSourceIds: [] }),
  )) as ConnectionControllerPreview;
}
function execute(plan: ConnectionControllerPreview) {
  return request("execute", {
    planId: plan.planId,
    digest: plan.digest,
    userConfirmed: true,
  });
}

it("capability and absent receipt only read Core and never create a ledger", async () => {
  const f = await fixture();
  const service = f.service();
  expect(await service.handle(request("capability"))).toEqual({
    available: true,
  });
  expect(
    await service.handle(request("receipt", { operationId: "missing" })),
  ).toBeNull();
  expect(await readdir(f.dataDir)).toEqual([]);
  expect(f.posts).toEqual([]);
  expect(f.reads.every((read) => read === "identity")).toBe(true);
  for (const method of Object.values(f.permissions))
    expect(method).not.toHaveBeenCalled();
});

it("real preview applies direct final-state sync with no operation receipt", async () => {
  const f = await fixture();
  const service = f.service();
  const plan = await preview(service);
  expect(plan.items).toEqual([
    {
      id: "sync:cursor",
      kind: "sync",
      sourceIds: ["cursor"],
      restoresRevoked: false,
    },
  ]);
  expect(JSON.stringify(plan)).not.toContain(f.parent);
  expect(f.posts).toEqual([]);
  const result = (await service.handle(execute(plan))) as BatchResult;
  expect(result.state).toBe("completed");
  expect(result.items[0].state).toBe("succeeded");
  await service.handle(execute(plan));
  expect(f.posts).toEqual([{ enabled: true }]);
  expect(
    await service.handle(request("receipt", { operationId: plan.operationId })),
  ).toBeNull();
  await service.stop();
  const reopened = f.service();
  expect(
    await reopened.handle(
      request("receipt", { operationId: plan.operationId }),
    ),
  ).toBeNull();
  await expect(reopened.handle(execute(plan))).rejects.toThrow("plan_missing");
  expect(f.posts).toHaveLength(1);
});

it.each(["request", "core"])(
  "invalid %s instance never creates ledger or dispatches CAS",
  async (kind) => {
    const f = await fixture();
    const service = f.service();
    if (kind === "core") f.setInstance("other");
    const input = request("preview", {
      syncSourceIds: ["cursor"],
      hostSourceIds: [],
    });
    if (kind === "request") input.instance_id = "other";
    await expect(service.handle(input)).rejects.toThrow(
      "connection_control_unavailable",
    );
    expect(await readdir(f.dataDir)).toEqual([]);
    expect(f.posts).toEqual([]);
  },
);

it("data root inode replacement after preview rejects execute without creating replacement ledger", async () => {
  const f = await fixture();
  const service = f.service();
  const plan = await preview(service);
  await rename(f.dataDir, path.join(f.parent, "old"));
  await mkdir(f.dataDir, { mode: 0o700 });
  await expect(service.handle(execute(plan))).rejects.toThrow(
    "connection_control_unavailable",
  );
  expect(f.posts).toEqual([]);
  expect(await readdir(f.dataDir)).toEqual([]);
});

it.each(["root", "revocation"])(
  "source %s change after preview prevents sync mutation",
  async (kind) => {
    const f = await fixture();
    const service = f.service();
    const plan = await preview(service);
    if (kind === "root") {
      f.source.root_id = "new";
      f.source.candidate_root_id = "new";
    } else f.source.authorized = false;
    const result = (await service.handle(execute(plan))) as BatchResult;
    expect(result.state).toBe(kind === "root" ? "completed" : "partial");
    expect(f.posts).toEqual(kind === "root" ? [{ enabled: true }] : []);
  },
);

it.each(["lost-response", "bad-response"])(
  "%s is resolved immediately from the current final state without a ledger",
  async (kind) => {
    const f = await fixture();
    const service = f.service();
    const plan = await preview(service);
    if (kind === "lost-response") f.lose();
    else f.bad();
    const first = (await service.handle(execute(plan))) as BatchResult;
    expect(first.items[0].state).toBe("succeeded");
    expect(f.posts).toHaveLength(1);
    expect(f.source.sync_enabled).toBe(true);
    await service.stop();
    const reopened = f.service();
    expect(
      await reopened.handle(
        request("receipt", { operationId: plan.operationId }),
      ),
    ).toBeNull();
    await expect(preview(reopened)).resolves.toBeDefined();
    expect(f.posts).toHaveLength(1);
  },
);

it("stop waits for admitted direct sync and leaves no operation receipt", async () => {
  const f = await fixture();
  const service = f.service();
  const plan = await preview(service);
  const hold = f.hold();
  const work = service.handle(execute(plan)).then(
    () => "success",
    () => "rejected",
  );
  await hold.entered;
  let drained = false;
  const stopping = service.stop().then(() => {
    drained = true;
  });
  await Promise.resolve();
  expect(drained).toBe(false);
  await expect(service.handle(request("capability"))).rejects.toThrow(
    "connection_control_busy",
  );
  hold.release();
  expect(await work).toBe("rejected");
  await stopping;
  expect(drained).toBe(true);
  expect(f.posts).toHaveLength(1);
  expect(
    await f
      .service()
      .handle(request("receipt", { operationId: plan.operationId })),
  ).toBeNull();
});

it("queues refresh behind an admitted write without replaying or rejecting normal contention", async () => {
  const f = await fixture();
  const service = f.service();
  const plan = await preview(service);
  const hold = f.hold();
  const work = service.handle(execute(plan));
  await hold.entered;
  let refreshed = false;
  const refresh = service.handle(request("capability")).then((result) => {
    refreshed = true;
    return result;
  });
  await Promise.resolve();
  expect(refreshed).toBe(false);
  hold.release();
  expect(((await work) as BatchResult).state).toBe("completed");
  expect(await refresh).toEqual({ available: true });
  expect(f.posts).toHaveLength(1);
});

it("unsafe data directory permissions fail closed before creating a ledger", async () => {
  const f = await fixture();
  await chmod(f.dataDir, 0o755);
  await expect(f.service().handle(request("capability"))).rejects.toThrow(
    "connection_control_unavailable",
  );
  expect(await readdir(f.dataDir)).toEqual([]);
  expect(f.posts).toEqual([]);
});

it("Core identity changing after direct sync rejects the call without a receipt", async () => {
  const f = await fixture();
  const service = f.service();
  const plan = await preview(service);
  const hold = f.hold();
  const work = service.handle(execute(plan)).then(
    () => "success",
    () => "rejected",
  );
  await hold.entered;
  f.setInstance("replacement-core");
  hold.release();
  expect(await work).toBe("rejected");
  expect(f.posts).toHaveLength(1);
  f.setInstance(INSTANCE);
  expect(
    await f
      .service()
      .handle(request("receipt", { operationId: plan.operationId })),
  ).toBeNull();
  expect(f.posts).toHaveLength(1);
});

it("corrupt external-operation journal is not reported absent or repaired", async () => {
  const f = await fixture();
  const service = f.service();
  const plan = await preview(service);
  const directory = path.join(f.dataDir, "connection-batches");
  const owner = JSON.parse(
    await readFile(path.join(directory, "owner.json"), "utf8"),
  ) as { userId: string; runtimeId: string };
  const operationId = "external-operation";
  const name =
    createHash("sha256")
      .update(JSON.stringify([owner.userId, owner.runtimeId, operationId]))
      .digest("hex") + ".json";
  const file = path.join(directory, name);
  await writeFile(file, "{", { mode: 0o600 });
  await expect(
    f.service().handle(request("receipt", { operationId })),
  ).rejects.toThrow();
  expect(await readFile(file, "utf8")).toBe("{");
  expect((await readdir(directory)).sort()).toContain(name);
  expect(f.posts).toHaveLength(0);
});
