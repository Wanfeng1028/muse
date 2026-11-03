
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb } from "../src/db.js";
import { startServer } from "../src/server.js";
import type { AddressInfo } from "node:net";
import type { GatewayConfig } from "../src/config.js";

const tmpDir = mkdtempSync(join(tmpdir(), "artifacts-r2-"));
const config: GatewayConfig = {
  port: 0,
  dataDir: tmpDir,
  roomMaxMembersWorkroom: 50,
  roomMaxMembersPlayroom: 200,
  gameBroadcastThrottleMs: 500,
};

let server: ReturnType<typeof startServer>;
let base: string;

beforeAll(async () => {
  const db = openDb(join(tmpDir, "test.db"));
  server = startServer(config, db);
  const addr = server.httpServer.address() as AddressInfo;
  base = `http://127.0.0.1:${addr.port}`;
});

afterAll(async () => {
  await server.close();
});

async function requestGrant(body: unknown, rawBody?: string): Promise<Response> {
  return fetch(`${base}/artifacts/request`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: rawBody !== undefined ? rawBody : JSON.stringify(body),
  });
}

async function uploadRaw(token: string, buf: Uint8Array<ArrayBuffer>): Promise<Response> {
  return fetch(`${base}/artifacts/upload/${token}`, {
    method: "PUT",
    headers: { "content-length": String(buf.length) },
    body: buf,
  });
}

describe("artifacts.r2", () => {
  it("1.1 request body 非 JSON → 400 invalid_json", async () => {
    const res = await requestGrant(null, "not-json{{{");
    expect(res.status).toBe(400);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("invalid_json");
  });

  it("1.2 filename 为空字符串 → 400 invalid_filename", async () => {
    const res = await requestGrant({ filename: "", declared_size: 10 });
    expect(res.status).toBe(400);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("invalid_filename");
  });

  it("1.3 declared_size 为 0 → 400 invalid_size", async () => {
    const res = await requestGrant({ filename: "a.bin", declared_size: 0 });
    expect(res.status).toBe(400);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("invalid_size");
  });

  it("1.4 declared_size 为 1.5 → 400 invalid_size", async () => {
    const res = await requestGrant({ filename: "a.bin", declared_size: 1.5 });
    expect(res.status).toBe(400);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("invalid_size");
  });

  it("1.5 mime 为数字 → 400 invalid_mime", async () => {
    const res = await requestGrant({ filename: "a.bin", declared_size: 10, mime: 123 });
    expect(res.status).toBe(400);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("invalid_mime");
  });

  it("2. declared_size 为负数 → 400 invalid_size", async () => {
    const res = await requestGrant({ filename: "a.bin", declared_size: -5 });
    expect(res.status).toBe(400);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("invalid_size");
  });

  it("3. PUT 未知 token → 410 gone", async () => {
    const res = await uploadRaw("nonexistent-token-abc", new TextEncoder().encode("hello"));
    expect(res.status).toBe(410);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("gone");
  });

  it("4. size_mismatch 后 pending 清除，同 token 复用 → 410 gone", async () => {
    const grantRes = await requestGrant({ filename: "mismatch.bin", declared_size: 10 });
    expect(grantRes.status).toBe(201);
    const grant = (await grantRes.json()) as { upload_url: string; expires_at_ms: number };
    expect(typeof grant.upload_url).toBe("string");
    expect(typeof grant.expires_at_ms).toBe("number");
    const token = grant.upload_url.split("/").pop() as string;

    const putRes = await uploadRaw(token, new TextEncoder().encode("12345"));
    expect(putRes.status).toBe(400);
    const putJson = (await putRes.json()) as { error: string };
    expect(putJson.error).toBe("size_mismatch");

    const reuseRes = await uploadRaw(token, new TextEncoder().encode("1234567890"));
    expect(reuseRes.status).toBe(410);
    const reuseJson = (await reuseRes.json()) as { error: string };
    expect(reuseJson.error).toBe("gone");
  });

  it("5. 成功上传后 token 复用 → 410 gone", async () => {
    const payload = new TextEncoder().encode("token-once-payload");
    const grantRes = await requestGrant({ filename: "once.bin", declared_size: payload.length });
    expect(grantRes.status).toBe(201);
    const grant = (await grantRes.json()) as { upload_url: string };
    const token = grant.upload_url.split("/").pop() as string;

    const first = await uploadRaw(token, payload);
    expect(first.status).toBe(200);
    const firstJson = (await first.json()) as { id: string; filename: string; size: number };
    expect(firstJson.filename).toBe("once.bin");
    expect(firstJson.size).toBe(payload.length);
    expect(firstJson.id).toMatch(/^artf_[0-9a-f]{16}$/);

    const second = await uploadRaw(token, payload);
    expect(second.status).toBe(410);
    const secondJson = (await second.json()) as { error: string };
    expect(secondJson.error).toBe("gone");
  });

  it("6. 两个 grant 并发上传互不干扰，各自内容正确", async () => {
    const payloadA = new TextEncoder().encode("AAAA-concurrent-a");
    const payloadB = new TextEncoder().encode("BBBB-concurrent-bbbb");

    const grantARes = await requestGrant({ filename: "a.txt", declared_size: payloadA.length, mime: "text/plain" });
    const grantBRes = await requestGrant({ filename: "b.txt", declared_size: payloadB.length, mime: "text/plain" });
    expect(grantARes.status).toBe(201);
    expect(grantBRes.status).toBe(201);
    const grantA = (await grantARes.json()) as { upload_url: string };
    const grantB = (await grantBRes.json()) as { upload_url: string };
    const tokenA = grantA.upload_url.split("/").pop() as string;
    const tokenB = grantB.upload_url.split("/").pop() as string;

    const [resA, resB] = await Promise.all([
      uploadRaw(tokenA, payloadA),
      uploadRaw(tokenB, payloadB),
    ]);
    expect(resA.status).toBe(200);
    expect(resB.status).toBe(200);
    const jsonA = (await resA.json()) as { id: string };
    const jsonB = (await resB.json()) as { id: string };
    expect(jsonA.id).not.toBe(jsonB.id);
    expect(jsonA.id).toMatch(/^artf_[0-9a-f]{16}$/);
    expect(jsonB.id).toMatch(/^artf_[0-9a-f]{16}$/);

    const dlA = await fetch(`${base}/artifacts/${jsonA.id}`);
    expect(dlA.status).toBe(200);
    const bufA = Buffer.from(await dlA.arrayBuffer());
    expect(bufA.equals(payloadA)).toBe(true);

    const dlB = await fetch(`${base}/artifacts/${jsonB.id}`);
    expect(dlB.status).toBe(200);
    const bufB = Buffer.from(await dlB.arrayBuffer());
    expect(bufB.equals(payloadB)).toBe(true);
  });

  it("7. 下载不存在的 id → 404 not_found", async () => {
    const res = await fetch(`${base}/artifacts/artf_0000000000000000`);
    expect(res.status).toBe(404);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("not_found");
  });

  it("8.1 下载成功 mime 登记为 text/plain 时头正确且 body 一致", async () => {
    const payload = new TextEncoder().encode("plain-text-body-001");
    const grantRes = await requestGrant({ filename: "note.txt", declared_size: payload.length, mime: "text/plain" });
    expect(grantRes.status).toBe(201);
    const grant = (await grantRes.json()) as { upload_url: string };
    const token = grant.upload_url.split("/").pop() as string;

    const upRes = await uploadRaw(token, payload);
    expect(upRes.status).toBe(200);
    const upJson = (await upRes.json()) as { id: string; filename: string; size: number };
    expect(upJson.size).toBe(payload.length);

    const dlRes = await fetch(`${base}/artifacts/${upJson.id}`);
    expect(dlRes.status).toBe(200);
    expect(dlRes.headers.get("content-type")).toBe("text/plain");
    expect(dlRes.headers.get("content-length")).toBe(String(payload.length));
    const got = Buffer.from(await dlRes.arrayBuffer());
    expect(got.equals(payload)).toBe(true);
  });

  it("8.2 未登记 mime 时下载 content-type 为 application/octet-stream 且 body 一致", async () => {
    const payload = new Uint8Array([0x00, 0x01, 0x02, 0xff, 0xfe]);
    const grantRes = await requestGrant({ filename: "raw.bin", declared_size: payload.length });
    expect(grantRes.status).toBe(201);
    const grant = (await grantRes.json()) as { upload_url: string };
    const token = grant.upload_url.split("/").pop() as string;

    const upRes = await uploadRaw(token, payload);
    expect(upRes.status).toBe(200);
    const upJson = (await upRes.json()) as { id: string };
    expect(upJson.id).toMatch(/^artf_[0-9a-f]{16}$/);

    const dlRes = await fetch(`${base}/artifacts/${upJson.id}`);
    expect(dlRes.status).toBe(200);
    expect(dlRes.headers.get("content-type")).toBe("application/octet-stream");
    expect(dlRes.headers.get("content-length")).toBe(String(payload.length));
    const got = Buffer.from(await dlRes.arrayBuffer());
    expect(got.equals(payload)).toBe(true);
  });

  it("9. filename 含路径分隔符时仅做元数据登记，返回 filename 与请求一致", async () => {
    const weirdName = "../../x";
    const payload = new TextEncoder().encode("path-traversal-meta");
    const grantRes = await requestGrant({ filename: weirdName, declared_size: payload.length });
    expect(grantRes.status).toBe(201);
    const grant = (await grantRes.json()) as { upload_url: string };
    const token = grant.upload_url.split("/").pop() as string;

    const upRes = await uploadRaw(token, payload);
    expect(upRes.status).toBe(200);
    const upJson = (await upRes.json()) as { id: string; filename: string; size: number };
    expect(upJson.filename).toBe(weirdName);
    expect(upJson.size).toBe(payload.length);
    expect(upJson.id).toMatch(/^artf_[0-9a-f]{16}$/);

    const dlRes = await fetch(`${base}/artifacts/${upJson.id}`);
    expect(dlRes.status).toBe(200);
    const got = Buffer.from(await dlRes.arrayBuffer());
    expect(got.equals(payload)).toBe(true);
  });
});
