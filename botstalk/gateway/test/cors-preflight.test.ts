import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb } from "../src/db.js";
import { startServer } from "../src/server.js";

describe("CORS 预检 OPTIONS", () => {
  let dataDir: string;
  let db: Awaited<ReturnType<typeof openDb>>;
  let server: Awaited<ReturnType<typeof startServer>>;
  let baseUrl: string;

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), "cors-preflight-test-"));
    db = await openDb(join(dataDir, "dbdir"));
    server = await startServer(
      {
        port: 0,
        dataDir: join(dataDir, "dbdir"),
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      },
      db,
    );
    const address = server.httpServer.address();
    const port = typeof address === "object" && address !== null ? address.port : 0;
    baseUrl = `http://127.0.0.1:${port}`;
  });

  afterEach(async () => {
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  it("OPTIONS 分享链接路径返回 204 与预检头", async () => {
    const res = await fetch(baseUrl + "/api/rooms/any-room/share-links", {
      method: "OPTIONS",
      headers: {
        origin: "http://localhost:4173",
        "access-control-request-method": "POST",
        "access-control-request-headers": "content-type",
      },
    });
    expect(res.status).toBe(204);
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
    expect(res.headers.get("access-control-allow-methods")).toContain("POST");
    expect(res.headers.get("access-control-allow-methods")).toContain("DELETE");
    expect(res.headers.get("access-control-allow-headers")).toContain("content-type");
  });

  it("OPTIONS 未知路径同样返回 204（全局预检，不走路由）", async () => {
    const res = await fetch(baseUrl + "/api/no-such-thing", { method: "OPTIONS" });
    expect(res.status).toBe(204);
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
  });
});
