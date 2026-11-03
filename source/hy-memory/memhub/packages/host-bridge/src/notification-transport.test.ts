import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import { createServer, type Server } from "node:http";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readHostCredentialFile } from "./broker-client.js";
import { writeDiscovery } from "./discovery.js";
import {
  capability,
  createNotificationTransport,
} from "./notification-transport.js";

const roots: string[] = [];
const servers: Server[] = [];
afterEach(async () => {
  vi.useRealTimers();
  for (const server of servers.splice(0)) {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
  for (const root of roots.splice(0))
    await rm(root, { recursive: true, force: true });
});
const payload = {
  version: 1 as const,
  event_id: "a".repeat(64),
  session_id: "s1",
  event_kind: "source-changed" as const,
};
async function fixture() {
  const root = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "d37-notify-")),
  );
  roots.push(root);
  const privateDir = path.join(root, "private");
  await mkdir(privateDir, { mode: 0o700 });
  await chmod(privateDir, 0o700);
  const credentialFile = path.join(privateDir, "credential");
  await writeFile(credentialFile, `omhg_v1_${"a".repeat(43)}`, { mode: 0o600 });
  const requests: Array<{
    url: string;
    authorization?: string;
    body: unknown;
  }> = [];
  let healthInstance = "instance-one";
  let status = 200;
  let responseBody = JSON.stringify({ accepted: true });
  let contentType = "application/json";
  let hang = false;
  const server = createServer(async (request, response) => {
    let raw = "";
    for await (const chunk of request) raw += chunk;
    requests.push({
      url: request.url ?? "",
      authorization: request.headers.authorization,
      body: raw ? JSON.parse(raw) : null,
    });
    if (request.url === "/health") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(
        JSON.stringify({
          status: "ok",
          service: "one-memory-recall-broker",
          instance_id: healthInstance,
        }),
      );
      return;
    }
    if (hang) return;
    response.writeHead(status, {
      "content-type": contentType,
      location: "/redirect-target",
    });
    response.end(responseBody);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  servers.push(server);
  const address = server.address();
  if (!address || typeof address === "string")
    throw Error("address_unavailable");
  const discoveryPath = path.join(root, "discovery.json");
  const discovery = {
    schema_version: 1 as const,
    service: "one-memory-recall-broker" as const,
    status: "running" as const,
    host: "127.0.0.1" as const,
    port: address.port,
    instance_id: "instance-one",
    pid: process.pid,
    updated_at: new Date().toISOString(),
  };
  await writeDiscovery(discoveryPath, discovery);
  const config = {
    schemaVersion: 1 as const,
    mode: "sync-only" as const,
    installationId: "00000000-0000-4000-8000-000000000001",
    discoveryPath,
    credentialFile,
    stateDirectory: path.join(root, "state"),
  };
  const notify = createNotificationTransport({
    config,
    credentialProvider: () => readHostCredentialFile(credentialFile),
  });
  return {
    root,
    requests,
    discovery,
    discoveryPath,
    credentialFile,
    config,
    notify,
    setResponse: (
      code: number,
      body = "private path /secret omhg_v1_never_leak",
      type = "application/json",
    ) => {
      status = code;
      responseBody = body;
      contentType = type;
    },
    mismatch: () => {
      healthInstance = "wrong-instance";
    },
    hang: () => {
      hang = true;
    },
  };
}

describe("production source-change transport", () => {
  it("exports the real capability and sends exactly the fixed wire after identity check", async () => {
    const f = await fixture();
    expect(capability).toBe("source-change-v1");
    expect(await f.notify(payload)).toEqual({ accepted: true });
    expect(f.requests.map((r) => r.url)).toEqual([
      "/health",
      "/source-changed",
    ]);
    expect(f.requests[0].authorization).toBeUndefined();
    expect(f.requests[1]).toMatchObject({
      body: payload,
      authorization: `Bearer omhg_v1_${"a".repeat(43)}`,
    });
    await writeFile(f.credentialFile, `omhg_v1_${"b".repeat(43)}`, {
      mode: 0o600,
    });
    await f.notify(payload);
    expect(f.requests[3].authorization).toBe(
      `Bearer omhg_v1_${"b".repeat(43)}`,
    );
  });
  it("rejects extra payload fields before any request", async () => {
    const f = await fixture();
    await expect(
      f.notify({ ...payload, path: "/private" } as never),
    ).rejects.toMatchObject({ code: "invalid_notification" });
    expect(f.requests).toEqual([]);
  });
  it("never sends credentials or events to mismatched or non-loopback discovery", async () => {
    const f = await fixture();
    f.mismatch();
    await expect(f.notify(payload)).rejects.toMatchObject({
      code: "notification_unavailable",
    });
    expect(f.requests.map((r) => r.url)).toEqual(["/health"]);
    await writeFile(
      f.discoveryPath,
      JSON.stringify({ ...f.discovery, host: "example.com" }),
    );
    await expect(f.notify(payload)).rejects.toMatchObject({
      code: "notification_unavailable",
    });
    expect(f.requests).toHaveLength(1);
  });
  it.each([
    [400, "invalid_notification"],
    [401, "host_authorization_required"],
    [403, "source_not_authorized"],
    [409, "source_work_unavailable"],
    [429, "source_notification_rate_limited"],
    [503, "notification_unavailable"],
    [302, "notification_unavailable"],
  ])("sanitizes %i and never retries or redirects", async (status, code) => {
    const f = await fixture();
    f.setResponse(Number(status));
    const error = await f.notify(payload).catch((error) => error);
    expect(error).toMatchObject({ code });
    expect(String(error)).not.toMatch(/private|secret|omhg_v1_/);
    expect(error.cause).toBeUndefined();
    expect(f.requests.map((r) => r.url)).toEqual([
      "/health",
      "/source-changed",
    ]);
  });
  it.each([
    ["not json", "application/json"],
    ['{"accepted":true,"body":"private"}', "application/json"],
    ['{"accepted":true}', "text/html"],
    ['{"accepted":false}', "application/json"],
  ])("rejects malformed success %s", async (body, type) => {
    const f = await fixture();
    f.setResponse(200, body, type);
    await expect(f.notify(payload)).rejects.toMatchObject({
      code: "notification_unavailable",
    });
    expect(f.requests).toHaveLength(2);
  });
  it("fails closed for a missing credential without sending a notification", async () => {
    const f = await fixture();
    await rm(f.credentialFile);
    await expect(f.notify(payload)).rejects.toMatchObject({
      code: "host_credential_unavailable",
    });
    expect(f.requests.filter((r) => r.url === "/source-changed")).toEqual([]);
  });
  it("bounds a stalled service with the single 25-second deadline and no retry", async () => {
    const f = await fixture();
    f.hang();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const pending = f.notify(payload).catch((error) => error);
    await vi.waitFor(() => expect(f.requests).toHaveLength(2));
    await vi.advanceTimersByTimeAsync(25_001);
    expect(await pending).toMatchObject({ code: "notification_unavailable" });
    expect(f.requests.map((r) => r.url)).toEqual([
      "/health",
      "/source-changed",
    ]);
  }, 8000);
  it("expires slow credential lookup under the same deadline and forbids a late POST", async () => {
    const f = await fixture();
    let finish!: (value: string) => void;
    const credentialProvider = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          finish = resolve;
        }),
    );
    const notify = createNotificationTransport({
      config: f.config,
      credentialProvider,
    });
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    let result: unknown;
    const pending = notify(payload).then(
      (value) => {
        result = value;
      },
      (error) => {
        result = error;
      },
    );
    await vi.waitFor(() => expect(credentialProvider).toHaveBeenCalledOnce());
    await vi.advanceTimersByTimeAsync(25_001);
    try {
      expect(result).toMatchObject({ code: "notification_unavailable" });
    } finally {
      finish(`omhg_v1_${"a".repeat(43)}`);
      await pending;
    }
    expect(f.requests.map((r) => r.url)).toEqual(["/health"]);
  });
  it("does not ship a test route or configurable endpoint", async () => {
    const source = await readFile(
      new URL("./notification-transport.ts", import.meta.url),
      "utf8",
    );
    expect(source).not.toContain("/test-source-changed");
    expect(source).not.toContain("process.env");
  });
});
