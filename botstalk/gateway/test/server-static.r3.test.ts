import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { request as httpRequest } from "node:http";
import { openDb } from "../src/db.js";
import { startServer } from "../src/server.js";
import type { AddressInfo } from "node:net";
import type { GatewayConfig } from "../src/config.js";

function rawGet(port: number, path: string): Promise<{ status: number; headers: Record<string, string | undefined>; body: string }> {
  return new Promise((resolve, reject) => {
    const req = httpRequest({ host: "127.0.0.1", port, path, method: "GET" }, (res) => {
      const chunks: Buffer[] = [];
      res.on("data", (c) => chunks.push(Buffer.isBuffer(c) ? c : Buffer.from(c)));
      res.on("end", () => resolve({ status: res.statusCode ?? 0, headers: res.headers as Record<string, string | undefined>, body: Buffer.concat(chunks).toString("utf8") }));
    });
    req.on("error", reject);
    req.end();
  });
}

describe("server-static.r3", () => {
  let tmpDir: string;
  let db: ReturnType<typeof openDb>;
  let server: ReturnType<typeof startServer>;
  let publicDir: string | undefined;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "server-static-r3-"));
    db = openDb(join(tmpDir, "test.db"));
    publicDir = undefined;
  });

  afterEach(async () => {
    if (server) {
      await server.close();
    }
    try {
      db.close();
    } catch {
      // ignore
    }
    rmSync(tmpDir, { recursive: true, force: true });
  });

  async function boot(): Promise<number> {
    const config: GatewayConfig = {
      port: 0,
      dataDir: tmpDir,
      roomMaxMembersWorkroom: 50,
      roomMaxMembersPlayroom: 200,
      gameBroadcastThrottleMs: 500,
      publicDir,
    } as GatewayConfig;
    server = startServer(config, db);
    const addr = server.httpServer.address() as AddressInfo;
    return addr.port;
  }

  it("publicDir 未配置时 GET / 返回 404", async () => {
    publicDir = undefined;
    const port = await boot();
    const res = await rawGet(port, "/");
    expect(res.status).toBe(404);
  });

  it("publicDir 目录不存在时 GET / 返回 404", async () => {
    publicDir = join(tmpDir, "no-such-public-dir");
    const port = await boot();
    const res = await rawGet(port, "/");
    expect(res.status).toBe(404);
  });

  it("GET / 返回 index.html 内容与 text/html content-type", async () => {
    publicDir = join(tmpDir, "public");
    mkdirSync(publicDir, { recursive: true });
    writeFileSync(join(publicDir, "index.html"), "<h1>hi</h1>");
    const port = await boot();
    const res = await rawGet(port, "/");
    expect(res.status).toBe(200);
    expect(res.body).toBe("<h1>hi</h1>");
    expect(res.headers["content-type"]).toBe("text/html; charset=utf-8");
  });

  it("GET /app.js 返回 js 内容与 text/javascript content-type", async () => {
    publicDir = join(tmpDir, "public");
    mkdirSync(publicDir, { recursive: true });
    writeFileSync(join(publicDir, "app.js"), "console.log(1)");
    const port = await boot();
    const res = await rawGet(port, "/app.js");
    expect(res.status).toBe(200);
    expect(res.body).toBe("console.log(1)");
    expect(res.headers["content-type"]).toBe("text/javascript; charset=utf-8");
  });

  it("不存在的路径 SPA 回退返回 index.html", async () => {
    publicDir = join(tmpDir, "public");
    mkdirSync(publicDir, { recursive: true });
    writeFileSync(join(publicDir, "index.html"), "<h1>hi</h1>");
    const port = await boot();
    const res = await rawGet(port, "/nope/route");
    expect(res.status).toBe(200);
    expect(res.body).toBe("<h1>hi</h1>");
  });

  it("无扩展名文件走 application/octet-stream", async () => {
    publicDir = join(tmpDir, "public");
    mkdirSync(publicDir, { recursive: true });
    writeFileSync(join(publicDir, "LICENSE"), "MIT");
    const port = await boot();
    const res = await rawGet(port, "/LICENSE");
    expect(res.status).toBe(200);
    expect(res.body).toBe("MIT");
    expect(res.headers["content-type"]).toBe("application/octet-stream");
  });

  it("路径穿越 %2e%2e 被 URL 规范化中和：落到 SPA 回退，不逃逸", async () => {
    publicDir = join(tmpDir, "public");
    mkdirSync(publicDir, { recursive: true });
    writeFileSync(join(publicDir, "index.html"), "<h1>hi</h1>");
    const port = await boot();
    const res = await rawGet(port, "/%2e%2e/%2e%2e/etc/passwd");
    // WHATWG URL 解析把 %2e%2e 当 .. 做 dot-segment 规范化，pathname 变成 /etc/passwd，
    // resolve 后仍在 base 内 → 文件不存在 → SPA 回退 index.html。关键：body 是 index.html 而非 /etc/passwd 内容
    expect(res.status).toBe(200);
    expect(res.body).toBe("<h1>hi</h1>");
  });

  it("/healthz 不受静态文件影响返回探针 JSON", async () => {
    publicDir = join(tmpDir, "public");
    mkdirSync(publicDir, { recursive: true });
    writeFileSync(join(publicDir, "index.html"), "<h1>hi</h1>");
    const port = await boot();
    const res = await rawGet(port, "/healthz");
    expect(res.status).toBe(200);
    expect(res.body).toBe('{"ok":true}');
    expect(res.headers["content-type"]).toBe("application/json");
  });
});