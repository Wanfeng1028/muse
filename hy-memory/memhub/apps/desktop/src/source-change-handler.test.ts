import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, describe, expect, it } from "vitest";
import { createSourceChangeHandler } from "./source-change-handler";

const closers: Array<() => Promise<void>> = [];
const coreToken = "synthetic-desktop-held-core-token";
const rootId = `root:v2:${"a".repeat(64)}`;

afterEach(async () => {
  for (const close of closers.splice(0).reverse()) await close();
});

async function fixture() {
  const source = {
    source_id: "claude-code",
    authorized: true,
    sync_enabled: true,
    root_id: rootId,
    candidate_root_id: rootId,
    grant_revision: 1,
    sync_completeness: "additions_only",
    capabilities: { live_sync: "implemented" },
  };
  const state = {
    source,
    instanceId: "test-source-notifications",
    status: 200,
    job: {
      source_id: "claude-code",
      operation: "sync",
      status: "completed",
      errors: 0,
    },
    afterSync: () => {},
    redirect: "",
  };
  const requests: Array<{
    path?: string;
    method?: string;
    body: string;
    authorization?: string;
  }> = [];
  const server = createServer((request, response) => {
    void (async () => {
      let body = "";
      for await (const part of request) body += part.toString();
      requests.push({
        path: request.url,
        method: request.method,
        body,
        authorization: request.headers.authorization,
      });
      response.setHeader("Content-Type", "application/json");
      if (request.url === "/api/v1/health") {
        response.end(
          JSON.stringify({
            status: "ok",
            service: "one-memory-core",
            instance_id: state.instanceId,
          }),
        );
      } else if (request.url === "/api/v1/sources") {
        response.end(JSON.stringify([state.source]));
      } else if (request.url === "/api/v1/sources/claude-code/sync") {
        state.afterSync();
        if (state.redirect) {
          response.writeHead(307, { Location: state.redirect });
          response.end("must not follow");
        } else {
          response.statusCode = state.status;
          response.end(JSON.stringify(state.job));
        }
      } else {
        response.statusCode = 404;
        response.end("{}");
      }
    })();
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  closers.push(async () => {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });
  const baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  return {
    state,
    requests,
    baseUrl,
    handler: createSourceChangeHandler({
      coreBaseUrl: baseUrl,
      coreApiToken: coreToken,
      instanceId: state.instanceId,
    }),
  };
}

describe("Desktop source-change handler", () => {
  it("uses the current Core sync route with no hook body and returns no source content", async () => {
    const f = await fixture();
    await expect(f.handler.checkSource("claude-code")).resolves.toBeUndefined();
    await expect(
      f.handler.synchronize("claude-code", new AbortController().signal),
    ).resolves.toBeUndefined();
    const writes = f.requests.filter((r) => r.method === "POST");
    expect(writes).toEqual([
      {
        path: "/api/v1/sources/claude-code/sync",
        method: "POST",
        body: "",
        authorization: `Bearer ${coreToken}`,
      },
    ]);
    expect(
      f.requests.every((r) => r.authorization === `Bearer ${coreToken}`),
    ).toBe(true);
    expect(
      f.requests.every((r) => !/model|memories|grants/.test(r.path ?? "")),
    ).toBe(true);
  });

  it.each(["read", "sync", "root", "revision"])(
    "refuses invalid %s permission before dispatch",
    async (condition) => {
      const f = await fixture();
      if (condition === "read") f.state.source.authorized = false;
      if (condition === "sync") f.state.source.sync_enabled = false;
      if (condition === "root")
        f.state.source.candidate_root_id = `root:v2:${"b".repeat(64)}`;
      if (condition === "revision") f.state.source.grant_revision = 0;
      await expect(
        f.handler.synchronize("claude-code", new AbortController().signal),
      ).rejects.toMatchObject({ status: 403 });
      expect(f.requests.filter((r) => r.method === "POST")).toHaveLength(0);
    },
  );

  it.each(["openclaw", "cursor", "../claude-code", "CLAUDE-CODE"])(
    "does not derive a source URL from unrecognized host %s",
    async (source) => {
      const f = await fixture();
      await expect(f.handler.checkSource(source)).rejects.toMatchObject({
        status: 403,
      });
      expect(f.requests).toHaveLength(0);
    },
  );

  it("refuses a different Core process at the same address", async () => {
    const f = await fixture();
    f.state.instanceId = "another-core";
    await expect(
      f.handler.synchronize("claude-code", new AbortController().signal),
    ).rejects.toMatchObject({ status: 503 });
    expect(f.requests.map((r) => r.path)).toEqual(["/api/v1/health"]);
  });

  it.each(["paused", "interrupted", "pending", "failed", "cancelled"])(
    "does not mark %s source work accepted",
    async (status) => {
      const f = await fixture();
      f.state.job.status = status;
      await expect(
        f.handler.synchronize("claude-code", new AbortController().signal),
      ).rejects.toMatchObject({ status: 409 });
    },
  );

  it.each(["source", "operation", "errors"])(
    "checks the returned job %s",
    async (field) => {
      const f = await fixture();
      if (field === "source") f.state.job.source_id = "cursor";
      if (field === "operation") f.state.job.operation = "history";
      if (field === "errors") f.state.job.errors = 1;
      await expect(
        f.handler.synchronize("claude-code", new AbortController().signal),
      ).rejects.toMatchObject({ status: 409 });
    },
  );

  it.each(["read", "sync", "root", "revision"])(
    "rechecks %s after the sync response",
    async (field) => {
      const f = await fixture();
      f.state.afterSync = () => {
        if (field === "read") f.state.source.authorized = false;
        if (field === "sync") f.state.source.sync_enabled = false;
        if (field === "root") {
          f.state.source.root_id = `root:v2:${"b".repeat(64)}`;
          f.state.source.candidate_root_id = f.state.source.root_id;
        }
        if (field === "revision") f.state.source.grant_revision++;
      };
      await expect(
        f.handler.synchronize("claude-code", new AbortController().signal),
      ).rejects.toMatchObject({ status: 403 });
      expect(f.requests.filter((r) => r.method === "POST")).toHaveLength(1);
    },
  );

  it("does not follow a Core redirect or expose its internal token", async () => {
    const f = await fixture();
    f.state.redirect = `${f.baseUrl}/secret-leak`;
    const error = await f.handler
      .synchronize("claude-code", new AbortController().signal)
      .catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 503 });
    expect(String(error)).not.toContain(coreToken);
    expect(error).not.toHaveProperty("cause");
    expect(f.requests.some((r) => r.path === "/secret-leak")).toBe(false);
  });

  it("respects cancellation before any request", async () => {
    const f = await fixture();
    const control = new AbortController();
    control.abort();
    await expect(
      f.handler.synchronize("claude-code", control.signal),
    ).rejects.toMatchObject({ status: 409 });
    expect(f.requests).toHaveLength(0);
  });

  it.each([
    "https://127.0.0.1:8765",
    "http://example.com:8765",
    "http://user@127.0.0.1:8765",
    "http://127.0.0.1:8765/api",
    "http://127.0.0.1:8765?x=1",
  ])("rejects an unexpected Core address %s", (coreBaseUrl) => {
    expect(() =>
      createSourceChangeHandler({
        coreBaseUrl,
        coreApiToken: coreToken,
        instanceId: "fixed",
      }),
    ).toThrow();
  });
});
