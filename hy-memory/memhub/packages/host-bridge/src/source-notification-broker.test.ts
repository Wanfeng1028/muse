import { mkdtemp, rm } from "node:fs/promises";
import { createServer, request as httpRequest } from "node:http";
import type { AddressInfo } from "node:net";
import os from "node:os";
import path from "node:path";
import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { recallThroughBroker } from "./broker-client.js";
import { HostGrantStore } from "./host-grants.js";
import { McpSession } from "./mcp-session.js";
import { RecallBroker, type RecallBrokerOptions } from "./recall-broker.js";
import { SourceNotificationError } from "./source-notifications.js";

const roots: string[] = [];
const closers: Array<() => Promise<void>> = [];
afterEach(async () => {
  for (const close of closers.splice(0).reverse()) await close();
  for (const root of roots.splice(0))
    await rm(root, { recursive: true, force: true });
});
const event = {
  version: 1,
  event_id: "a".repeat(64),
  session_id: "synthetic-session",
  event_kind: "source-changed",
};
async function fixture(
  options: {
    noStore?: boolean;
    noHandler?: boolean;
    coreWait?: Promise<void>;
    diagnostics?: RecallBrokerOptions["diagnostics"];
  } = {},
) {
  const root = await mkdtemp(path.join(os.tmpdir(), "om-source-broker-"));
  roots.push(root);
  const store = await HostGrantStore.initialize(path.join(root, "grants"));
  const issued = await store.createInstallation({ hostId: "claude-code" });
  const coreCalls: string[] = [];
  const core = createServer((request, response) => {
    coreCalls.push(request.url ?? "");
    request.resume();
    response.setHeader("content-type", "application/json");
    void Promise.resolve(options.coreWait).then(() =>
      response.end(
        JSON.stringify({
          state: "empty",
          query: "synthetic",
          scope: "all-apps",
          hits: [],
          used_characters: 0,
          truncated: false,
        }),
      ),
    );
  });
  await new Promise<void>((resolve) => core.listen(0, "127.0.0.1", resolve));
  closers.push(
    () =>
      new Promise<void>((resolve, reject) => {
        core.closeAllConnections();
        core.close((error) => (error ? reject(error) : resolve()));
      }),
  );
  const checkSource = vi.fn(async (_sourceId: string) => {});
  const synchronize = vi.fn(
    async (_sourceId: string, _signal: AbortSignal) => {},
  );
  const broker = new RecallBroker({
    coreBaseUrl: `http://127.0.0.1:${(core.address() as AddressInfo).port}`,
    coreApiToken: "synthetic-core-token",
    discoveryPath: path.join(root, "discovery.json"),
    instanceId: "synthetic-broker",
    preferredPort: 0,
    ...(!options.noStore ? { hostGrantStore: store } : {}),
    ...(!options.noHandler
      ? { sourceNotificationHandler: { checkSource, synchronize } }
      : {}),
    ...(options.diagnostics ? { diagnostics: options.diagnostics } : {}),
  });
  await broker.start();
  closers.push(() => broker.stop());
  const url = `http://127.0.0.1:${broker.port}`;
  const post = (
    route = "source-changed",
    data: unknown = event,
    secret: string | null = issued.secret,
  ) =>
    axios.post(`${url}/${route}`, data, {
      headers: {
        "content-type": "application/json",
        ...(secret ? { Authorization: `Bearer ${secret}` } : {}),
      },
      proxy: false,
      timeout: 3000,
      validateStatus: () => true,
    });
  return {
    root,
    store,
    issued,
    broker,
    url,
    post,
    coreCalls,
    checkSource,
    synchronize,
    discoveryPath: path.join(root, "discovery.json"),
  };
}

describe.skipIf(process.platform === "win32")(
  "source-changed HTTP boundary",
  () => {
    it("allows install-only notification but not recall, then preserves approved recall", async () => {
      const f = await fixture();
      const notified = await f.post();
      expect(notified.status).toBe(200);
      expect(notified.data).toEqual({ accepted: true });
      expect(notified.headers["cache-control"]).toBe("no-store");
      expect(f.synchronize).toHaveBeenCalledExactlyOnceWith(
        "claude-code",
        expect.any(AbortSignal),
      );
      expect((await f.post("recall", { query: "synthetic" })).status).toBe(403);
      expect(f.coreCalls).toEqual([]);
      await f.store.approveGrants({
        installationId: f.issued.receipt.installationId,
        expectedRevision: 1,
        allowedTools: ["om_recall"],
        allowedScopes: ["all-apps"],
      });
      expect((await f.post("recall", { query: "synthetic" })).status).toBe(200);
      expect(f.coreCalls).toEqual(["/api/v1/recall"]);
    });

    it("answers a completed sync without waiting for a slow diagnostic write", async () => {
      const events: string[] = [];
      const f = await fixture({
        diagnostics: (value) => {
          events.push(value.event);
          return new Promise(() => undefined);
        },
      });
      const notified = await f.post();
      expect(notified.status).toBe(200);
      expect(f.synchronize).toHaveBeenCalledOnce();
      expect(events).toContain("host_hook.completed");
    });

    it.each([{ noHandler: true }, { noStore: true }])(
      "fails closed without required dependency %j",
      async (options) => {
        const f = await fixture(options);
        const response = await f.post();
        expect(response.status).toBe(503);
        expect(response.data).toEqual({
          error: "source_notification_unavailable",
        });
        expect(f.synchronize).not.toHaveBeenCalled();
        expect(f.coreCalls).toEqual([]);
      },
    );

    it("rejects missing/forged credentials and extra payload fields without echoing them", async () => {
      const f = await fixture();
      for (const token of [null, "not-a-credential"])
        expect((await f.post("source-changed", event, token)).status).toBe(401);
      for (const extra of [
        { source_id: "cursor" },
        { path: f.root },
        { token: f.issued.secret },
        { body: "private" },
      ]) {
        const response = await f.post("source-changed", { ...event, ...extra });
        expect(response.status).toBe(400);
        expect(response.data).toEqual({ error: "source_notification_invalid" });
      }
      expect(f.checkSource).not.toHaveBeenCalled();
      expect(f.coreCalls).toEqual([]);
    });

    it("rejects duplicate Authorization headers rather than accepting Node's first value", async () => {
      const f = await fixture();
      const rawPost = (duplicate: boolean) =>
        new Promise<{ status?: number; body: string }>((resolve, reject) => {
          const data = JSON.stringify(event);
          const request = httpRequest(
            `${f.url}/source-changed`,
            {
              method: "POST",
              headers: [
                "Host",
                new URL(f.url).host,
                "Content-Type",
                "application/json",
                "Content-Length",
                String(Buffer.byteLength(data)),
                "Authorization",
                `Bearer ${f.issued.secret}`,
                ...(duplicate
                  ? ["Authorization", `Bearer ${f.issued.secret}`]
                  : []),
              ],
            },
            (result) => {
              let body = "";
              result.on("data", (part) => {
                body += part;
              });
              result.on("end", () =>
                resolve({ status: result.statusCode, body }),
              );
            },
          );
          request.on("error", reject);
          request.end(data);
        });
      expect((await rawPost(false)).status).toBe(200);
      expect(f.synchronize).toHaveBeenCalledOnce();
      f.synchronize.mockClear();
      const response = await rawPost(true);
      expect(response.status, response.body).toBe(401);
      expect(response.body).not.toContain(f.issued.secret);
      expect(f.synchronize).not.toHaveBeenCalled();
    });

    it.each([400, 403, 409, 429, 503])(
      "returns only fixed public failure for status %i",
      async (status) => {
        const f = await fixture();
        const codes = {
          400: "source_notification_invalid",
          403: "source_not_authorized",
          409: "source_work_unavailable",
          429: "source_notification_capacity",
          503: "source_notification_unavailable",
        } as const;
        const code = codes[status as keyof typeof codes];
        f.checkSource.mockRejectedValueOnce(
          new SourceNotificationError(
            code,
            status as 400 | 403 | 409 | 429 | 503,
          ),
        );
        const response = await f.post();
        expect(response.status).toBe(status);
        expect(response.data).toEqual({ error: code });
        expect(f.synchronize).not.toHaveBeenCalled();
      },
    );

    it("sanitizes unexpected handler errors and does not retry", async () => {
      const f = await fixture();
      f.synchronize.mockRejectedValueOnce(
        new Error(`${f.root} ${f.issued.secret}`),
      );
      const response = await f.post();
      expect(response.status).toBe(503);
      expect(response.data).toEqual({
        error: "source_notification_unavailable",
      });
      expect(f.synchronize).toHaveBeenCalledOnce();
    });

    it("does not return accepted after revocation during real HTTP work", async () => {
      const f = await fixture();
      f.synchronize.mockImplementationOnce(async () => {
        await f.store.revoke({
          installationId: f.issued.receipt.installationId,
          expectedRevision: 1,
        });
      });
      const response = await f.post();
      expect(response.status).toBe(401);
      expect(response.data).toEqual({
        error: "host_grant_authentication_failed",
      });
      expect(f.synchronize).toHaveBeenCalledOnce();
    });

    it("drains notifications without stranding a concurrent MCP recall and rejects new notifications during stop", async () => {
      let finishRecall!: () => void;
      const coreWait = new Promise<void>((resolve) => {
        finishRecall = resolve;
      });
      let finishSync!: () => void;
      const syncWait = new Promise<void>((resolve) => {
        finishSync = resolve;
      });
      const f = await fixture({ coreWait });
      await f.store.approveGrants({
        installationId: f.issued.receipt.installationId,
        expectedRevision: 1,
        allowedTools: ["om_recall"],
        allowedScopes: ["all-apps"],
      });
      f.synchronize.mockImplementationOnce(() => syncWait);
      const session = new McpSession(f.discoveryPath, (discovery, request) =>
        recallThroughBroker(discovery, request, {
          credentialProvider: () => f.issued.secret,
        }),
      );
      const recall = session.handle({
        jsonrpc: "2.0",
        id: 1,
        method: "tools/call",
        params: { name: "om_recall", arguments: { query: "synthetic" } },
      });
      const notification = f.post();
      let stopping: Promise<void> | undefined;
      try {
        await vi.waitFor(() => expect(f.coreCalls).toEqual(["/api/v1/recall"]));
        await vi.waitFor(() => expect(f.synchronize).toHaveBeenCalledOnce());
        let stopped = false;
        stopping = f.broker.stop().then(() => {
          stopped = true;
        });
        expect(f.synchronize.mock.calls[0][1].aborted).toBe(true);
        expect(stopped).toBe(false);
        const extra = await f.post("source-changed", {
          ...event,
          event_id: "b".repeat(64),
        });
        expect(extra.status).toBe(503);
        expect(extra.data).toEqual({
          error: "source_notification_unavailable",
        });
        expect(f.synchronize).toHaveBeenCalledOnce();
        finishRecall();
        const result = await recall;
        expect(result).toMatchObject({
          id: 1,
          result: { content: [{ type: "text" }] },
        });
        expect(result?.result).not.toHaveProperty("isError", true);
        expect(JSON.stringify(result)).toContain('\\"state\\":\\"empty\\"');
        expect(stopped).toBe(false);
        finishSync();
        expect((await notification).status).toBe(503);
        await stopping;
        expect(stopped).toBe(true);
        const after = await session.handle({
          jsonrpc: "2.0",
          id: 2,
          method: "tools/call",
          params: { name: "om_recall", arguments: { query: "synthetic" } },
        });
        expect(after?.result).toHaveProperty("isError", true);
        expect(f.coreCalls).toHaveLength(1);
      } finally {
        finishRecall();
        finishSync();
        await Promise.allSettled([
          recall,
          notification,
          ...(stopping ? [stopping] : []),
        ]);
      }
    });
  },
);
