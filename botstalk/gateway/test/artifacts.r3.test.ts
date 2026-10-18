import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb } from "../src/db.js";
import { startServer } from "../src/server.js";
import { createArtifactService } from "../src/artifacts.js";
import type { AddressInfo } from "node:net";
import type { GatewayConfig } from "../src/config.js";
import type { IncomingMessage, ServerResponse } from "node:http";

const tmpDir = mkdtempSync(join(tmpdir(), "artifacts-r3-"));
const config: GatewayConfig = { port: 0, dataDir: tmpDir, roomMaxMembersWorkroom: 50, roomMaxMembersPlayroom: 200, gameBroadcastThrottleMs: 500 };
let server: ReturnType<typeof startServer>;
let base: string;
beforeAll(async () => { const db = openDb(join(tmpDir, "test.db")); server = startServer(config, db); const addr = server.httpServer.address() as AddressInfo; base = `http://127.0.0.1:${addr.port}`; });
afterAll(async () => { await server.close(); });

describe("artifacts.r3 未覆盖分支", () => {
  it("handle() 对非 artifact 路径、以及 method 与路径错配的请求均返回 false", () => {
    const svc = createArtifactService(openDb(join(tmpDir, "h.db")), config);
    const fakeRes = {} as unknown as ServerResponse;

    const req1 = { url: "/api/rooms/w1/history", method: "GET" } as unknown as IncomingMessage;
    expect(svc.handle(req1, fakeRes)).toBe(false);

    const req2 = { url: "/artifacts/request", method: "PUT" } as unknown as IncomingMessage;
    expect(svc.handle(req2, fakeRes)).toBe(false);

    const req3 = { url: "/other", method: "POST" } as unknown as IncomingMessage;
    expect(svc.handle(req3, fakeRes)).toBe(false);
  });

  it("POST body 为 null 时返回 400 invalid_request", async () => {
    const res = await fetch(`${base}/artifacts/request`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "null",
    });
    expect(res.status).toBe(400);
    const json = await res.json() as { error?: string };
    expect(json.error).toBe("invalid_request");
  });

  it("POST body 为数字时返回 400 invalid_request", async () => {
    const res = await fetch(`${base}/artifacts/request`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "123",
    });
    expect(res.status).toBe(400);
    const json = await res.json() as { error?: string };
    expect(json.error).toBe("invalid_request");
  });

  it("filename 为数字时返回 400 invalid_filename", async () => {
    const res = await fetch(`${base}/artifacts/request`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: 123, declared_size: 10 }),
    });
    expect(res.status).toBe(400);
    const json = await res.json() as { error?: string };
    expect(json.error).toBe("invalid_filename");
  });

  it("declared_size 为字符串时返回 400 invalid_size", async () => {
    const res = await fetch(`${base}/artifacts/request`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: "a.bin", declared_size: "10" }),
    });
    expect(res.status).toBe(400);
    const json = await res.json() as { error?: string };
    expect(json.error).toBe("invalid_size");
  });

  it("mime 为空串时被接受并原样透传为空 content-type", async () => {
    const grantRes = await fetch(`${base}/artifacts/request`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: "e.bin", declared_size: 3, mime: "" }),
    });
    expect(grantRes.status).toBe(201);
    const grant = await grantRes.json() as { upload_url: string };
    const token = grant.upload_url.slice(grant.upload_url.lastIndexOf("/") + 1);

    const putRes = await fetch(`${base}/artifacts/upload/${token}`, {
      method: "PUT",
      body: Buffer.from([1, 2, 3]),
    });
    expect(putRes.status).toBe(200);
    const putJson = await putRes.json() as { id: string };
    expect(typeof putJson.id).toBe("string");

    const dlRes = await fetch(`${base}/artifacts/${putJson.id}`);
    expect(dlRes.status).toBe(200);
    expect(dlRes.headers.get("content-type")).toBe("");
  });

  it("PUT 路径 token 含多余斜杠时整段作为 token 查不到 pending 返回 410 gone", async () => {
    const grantRes = await fetch(`${base}/artifacts/request`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: "s.bin", declared_size: 2 }),
    });
    expect(grantRes.status).toBe(201);
    const grant = await grantRes.json() as { upload_url: string };
    const token = grant.upload_url.slice(grant.upload_url.lastIndexOf("/") + 1);

    const putRes = await fetch(`${base}/artifacts/upload/${token}/extra`, {
      method: "PUT",
      body: Buffer.from([1, 2]),
    });
    expect(putRes.status).toBe(410);
    const json = await putRes.json() as { error?: string };
    expect(json.error).toBe("gone");
  });
});
