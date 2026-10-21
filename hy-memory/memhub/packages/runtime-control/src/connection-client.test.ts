import { mkdir, mkdtemp, readdir, rename, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import axios, { type AxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { inspectRecallBrokerStatus } from "./broker-status.js";
import { createConnectionClient } from "./connection-client.js";
import { discoverRuntimeAttachment } from "./discovery.js";

vi.mock("./discovery.js", () => ({ discoverRuntimeAttachment: vi.fn() }));
vi.mock("./broker-status.js", () => ({ inspectRecallBrokerStatus: vi.fn() }));
const instanceId = "test-instance";
const preview = {
  planId: "plan-1",
  operationId: "operation-1",
  digest: "a".repeat(64),
  items: [
    {
      id: "sync:cursor",
      kind: "sync",
      sourceIds: ["cursor"],
      restoresRevoked: false,
    },
  ],
};
let root: string;
let request: ReturnType<typeof vi.spyOn>;

beforeEach(async () => {
  root = await mkdtemp(path.join(os.tmpdir(), "connection-client-"));
  vi.mocked(discoverRuntimeAttachment).mockResolvedValue({
    instanceId,
    apiToken: "test-management-secret",
    host: "127.0.0.1",
    port: 8100,
    servicePid: 12345,
    health: {
      status: "ok",
      service: "one-memory-core",
      version: "test",
      instance_id: instanceId,
    },
  });
  vi.mocked(inspectRecallBrokerStatus).mockResolvedValue({
    state: "running",
    code: "broker_verified",
    instanceId,
    host: "127.0.0.1",
    port: 8101,
  });
  request = vi.spyOn(axios, "request").mockImplementation(async (config) => {
    const body = config.data as { action: string };
    return {
      status: 200,
      data: {
        schema_version: 1,
        instance_id: instanceId,
        action: body.action,
        result:
          body.action === "capability"
            ? { available: true }
            : body.action === "preview"
              ? preview
              : null,
      },
    };
  });
});
afterEach(async () => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  await rm(root, { recursive: true, force: true });
});

describe("Runtime connection client", () => {
  it("preserves the fixed remove-hook instruction but never arbitrary server errors", async () => {
    const client = createConnectionClient({ dataDir: root });
    request.mockRejectedValueOnce({
      response: { status: 503, data: { error: "sync_hook_remove_first" } },
    });
    await expect(
      client.host?.({
        hostId: "claude-code",
        operation: "previewInstall",
        args: [],
      }),
    ).rejects.toThrow("sync_hook_remove_first");
    request.mockRejectedValueOnce({
      response: {
        status: 503,
        data: { error: "sync_hook_remove_first: SECRET" },
      },
    });
    await expect(
      client.host?.({
        hostId: "claude-code",
        operation: "previewInstall",
        args: [],
      }),
    ).rejects.toThrow("connection_client_unavailable");
  });
  it("checks cancellation after async identity verification and before the write is dispatched", async () => {
    const client = createConnectionClient({ dataDir: root });
    await client.preview({ syncSourceIds: ["cursor"], hostSourceIds: [] });
    const abort = new AbortController();
    const prior = vi.mocked(discoverRuntimeAttachment).getMockImplementation();
    vi.mocked(discoverRuntimeAttachment).mockImplementationOnce(
      async (options) => {
        abort.abort();
        return (await prior?.(options)) ?? null;
      },
    );
    await expect(
      client.execute(
        { planId: preview.planId, digest: preview.digest, userConfirmed: true },
        abort.signal,
      ),
    ).rejects.toThrow("connection_client_cancelled");
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("bounds preview cache without requiring a Runtime restart after 64 previews", async () => {
    let sequence = 0;
    request.mockImplementation(
      async (config: AxiosRequestConfig<{ action: string }>) => ({
        status: 200,
        data: {
          schema_version: 1,
          instance_id: instanceId,
          action: config.data?.action,
          result: {
            ...preview,
            planId: `plan-${++sequence}`,
            operationId: `operation-${sequence}`,
          },
        },
      }),
    );
    const client = createConnectionClient({ dataDir: root });
    for (let index = 0; index < 65; index++) {
      await client.preview({ syncSourceIds: ["cursor"], hostSourceIds: [] });
    }
    await expect(
      client.execute({
        planId: "plan-1",
        digest: preview.digest,
        userConfirmed: true,
      }),
    ).rejects.toThrow("connection_client_plan_missing");
    expect(request).toHaveBeenCalledTimes(65);
  });
  it("requires Broker PID to belong to the verified Runtime before probing", async () => {
    const get = vi.spyOn(axios, "get");
    vi.mocked(inspectRecallBrokerStatus).mockImplementationOnce(
      async (options) => {
        await options.probeBroker?.({
          schema_version: 1,
          service: "one-memory-recall-broker",
          instance_id: instanceId,
          pid: 99999,
          host: "127.0.0.1",
          port: 8101,
          status: "running",
          updated_at: new Date().toISOString(),
        });
        throw Error("unexpected success");
      },
    );
    await expect(
      createConnectionClient({ dataDir: root }).capability(),
    ).rejects.toThrow("connection_client_runtime_unavailable");
    expect(get).not.toHaveBeenCalled();
    expect(request).not.toHaveBeenCalled();
  });
  it("accepts successful direct sync without exposing paths or a receipt", async () => {
    const item = {
      id: "sync:cursor",
      kind: "sync",
      intentDigest: "b".repeat(64),
      state: "succeeded",
      receipt: null,
    };
    const client = createConnectionClient({ dataDir: root });
    await client.preview({ syncSourceIds: ["cursor"], hostSourceIds: [] });
    request.mockResolvedValueOnce({
      status: 200,
      data: {
        schema_version: 1,
        instance_id: instanceId,
        action: "execute",
        result: {
          mode: "execute",
          operationId: preview.operationId,
          planDigest: preview.digest,
          state: "completed",
          recovery: "persistent",
          cancelled: false,
          items: [item],
          skipped: [],
        },
      },
    });
    expect(
      (
        await client.execute({
          planId: preview.planId,
          digest: preview.digest,
          userConfirmed: true,
        })
      ).state,
    ).toBe("completed");
    request.mockResolvedValueOnce({
      status: 200,
      data: {
        schema_version: 1,
        instance_id: instanceId,
        action: "receipt",
        result: null,
      },
    });
    expect(await client.receipt(preview.operationId)).toBeNull();
  });
  it("rejects malformed successful execute and fences later attempts", async () => {
    const client = createConnectionClient({ dataDir: root });
    await client.preview({ syncSourceIds: ["cursor"], hostSourceIds: [] });
    request.mockResolvedValueOnce({
      status: 200,
      data: {
        schema_version: 1,
        instance_id: instanceId,
        action: "execute",
        result: { state: "completed", token: "secret" },
      },
    });
    const input = {
      planId: preview.planId,
      digest: preview.digest,
      userConfirmed: true as const,
    };
    await expect(client.execute(input)).rejects.toThrow(
      "connection_client_operation_unknown",
    );
    await expect(client.execute(input)).rejects.toThrow(
      "connection_client_operation_unknown",
    );
    expect(request).toHaveBeenCalledTimes(2);
  });
  it("rejects a live Core without the outer Runtime identity", async () => {
    const runtime = await vi
      .mocked(discoverRuntimeAttachment)
      .getMockImplementation()?.({} as never);
    vi.mocked(discoverRuntimeAttachment).mockResolvedValueOnce(
      runtime ? { ...runtime, servicePid: null } : null,
    );
    await expect(
      createConnectionClient({ dataDir: root }).capability(),
    ).rejects.toThrow("connection_client_runtime_unavailable");
    expect(request).not.toHaveBeenCalled();
  });
  it("construction and receipt do not create a local ledger or grants", async () => {
    const client = createConnectionClient({ dataDir: root });
    expect(request).not.toHaveBeenCalled();
    expect(await client.receipt("operation-1")).toBeNull();
    expect(await readdir(root)).toEqual([]);
    expect(discoverRuntimeAttachment).toHaveBeenCalledTimes(2);
    expect(discoverRuntimeAttachment).toHaveBeenCalledWith(
      expect.objectContaining({ requireServiceReceipt: true }),
    );
    expect(request).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "POST",
        url: "http://127.0.0.1:8101/control/connections",
        timeout: 30000,
        proxy: false,
        maxRedirects: 0,
        maxBodyLength: 65536,
        maxContentLength: 1048576,
        headers: {
          Authorization: "Bearer test-management-secret",
          "Content-Type": "application/json",
        },
        data: {
          schema_version: 1,
          instance_id: instanceId,
          action: "receipt",
          input: { operationId: "operation-1" },
        },
      }),
    );
  });
  it("rejects caller paths and invalid input before discovery", async () => {
    const client = createConnectionClient({ dataDir: root });
    await expect(
      client.preview({ syncSourceIds: [], hostSourceIds: ["../host"] }),
    ).rejects.toThrow("connection_client_invalid_input");
    expect(discoverRuntimeAttachment).not.toHaveBeenCalled();
    expect(() =>
      createConnectionClient({ dataDir: root, home: root } as never),
    ).toThrow("connection_client_invalid_input");
  });
  it("requires standalone Runtime and same-instance Broker", async () => {
    vi.mocked(discoverRuntimeAttachment).mockResolvedValueOnce(null);
    await expect(
      createConnectionClient({ dataDir: root }).capability(),
    ).rejects.toThrow("connection_client_runtime_unavailable");
    vi.mocked(inspectRecallBrokerStatus).mockResolvedValueOnce({
      state: "running",
      code: "broker_verified",
      instanceId: "wrong",
      host: "127.0.0.1",
      port: 8101,
    });
    await expect(
      createConnectionClient({ dataDir: root }).capability(),
    ).rejects.toThrow("connection_client_runtime_unavailable");
    expect(request).not.toHaveBeenCalled();
  });
  it("maps old-server 404 and raw error to fixed codes without secrets", async () => {
    request.mockRejectedValueOnce({
      response: { status: 404 },
      message: "test-management-secret",
    });
    await expect(
      createConnectionClient({ dataDir: root }).capability(),
    ).rejects.toThrow("connection_client_capability_unavailable");
    request.mockRejectedValueOnce(Error("test-management-secret"));
    await expect(
      createConnectionClient({ dataDir: root }).receipt("operation-1"),
    ).rejects.toThrow("connection_client_unavailable");
  });
  it("does not replay execute after transport failure; receipt remains available", async () => {
    const client = createConnectionClient({ dataDir: root });
    await client.preview({ syncSourceIds: ["cursor"], hostSourceIds: [] });
    request.mockRejectedValueOnce(Error("dropped response"));
    const input = {
      planId: preview.planId,
      digest: preview.digest,
      userConfirmed: true as const,
    };
    await expect(client.execute(input)).rejects.toThrow(
      "connection_client_operation_unknown",
    );
    await expect(client.execute(input)).rejects.toThrow(
      "connection_client_operation_unknown",
    );
    expect(request).toHaveBeenCalledTimes(2);
    expect(await client.receipt(preview.operationId)).toBeNull();
  });
  it("rejects response identity drift and extra result fields", async () => {
    request.mockResolvedValueOnce({
      status: 200,
      data: {
        schema_version: 1,
        instance_id: "wrong",
        action: "capability",
        result: { available: true },
      },
    });
    await expect(
      createConnectionClient({ dataDir: root }).capability(),
    ).rejects.toThrow("connection_client_invalid_response");
    request.mockResolvedValueOnce({
      status: 200,
      data: {
        schema_version: 1,
        instance_id: instanceId,
        action: "capability",
        result: { available: true, token: "bad" },
      },
    });
    await expect(
      createConnectionClient({ dataDir: root }).capability(),
    ).rejects.toThrow("connection_client_invalid_response");
  });
  it("rejects Runtime replacement after a successful response", async () => {
    const attachment = {
      instanceId,
      apiToken: "test-management-secret",
      host: "127.0.0.1" as const,
      port: 8100,
      servicePid: 12345,
      health: {
        status: "ok" as const,
        service: "one-memory-core" as const,
        version: "test",
        instance_id: instanceId,
      },
    };
    vi.mocked(discoverRuntimeAttachment)
      .mockResolvedValueOnce(attachment)
      .mockResolvedValueOnce({ ...attachment, apiToken: "replacement-secret" });
    await expect(
      createConnectionClient({ dataDir: root }).capability(),
    ).rejects.toThrow("connection_client_runtime_unavailable");
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("rejects data root replacement during an action", async () => {
    request.mockImplementationOnce(
      async (config: AxiosRequestConfig<{ action: string }>) => {
        await rename(root, `${root}-old`);
        await mkdir(root, { mode: 0o700 });
        await rm(`${root}-old`, { recursive: true });
        return {
          status: 200,
          data: {
            schema_version: 1,
            instance_id: instanceId,
            action: config.data?.action,
            result: { available: true },
          },
        };
      },
    );
    await expect(
      createConnectionClient({ dataDir: root }).capability(),
    ).rejects.toThrow("connection_client_storage_unavailable");
  });
});
