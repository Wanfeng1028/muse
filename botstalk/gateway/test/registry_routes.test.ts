import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb } from "../src/db.js";
import { startServer } from "../src/server.js";

describe("GET /api/registry/agents", () => {
  let dataDir: string;
  let db: ReturnType<typeof openDb>;
  let server: any;

  beforeEach(() => {
    dataDir = mkdtempSync(join(tmpdir(), "botstalk-server-"));
    db = openDb(join(dataDir, "test.db"));
    server = startServer(
      {
        port: 0,
        dataDir,
        roomMaxMembersWorkroom: 50,
        roomMaxMembersPlayroom: 200,
        gameBroadcastThrottleMs: 500,
      },
      db,
    );
  });

  afterEach(async () => {
    await server.close();
    rmSync(dataDir, { recursive: true, force: true });
  });

  const getPort = () => {
    const address = server.httpServer.address();
    if (!address || typeof address === "string") {
      throw new Error("无法获取测试服务器端口");
    }
    return address.port;
  };

  it("GET /api/registry/agents 返回 22 条白名单记录", async () => {
    const res = await fetch(`http://127.0.0.1:${getPort()}/api/registry/agents`);
    expect(res.status).toBe(200);

    const body = await res.json();
    expect(body.agents).toHaveLength(22);
    expect(body.agents[0].name).toBe("claude");

    // 每条记录都应只暴露白名单字段
    for (const agent of body.agents) {
      expect(agent).toHaveProperty("name");
      expect(agent).toHaveProperty("label");
      expect(agent).toHaveProperty("binary");

      expect(agent).not.toHaveProperty("check_ready");
      expect(agent).not.toHaveProperty("launch");
      expect(agent).not.toHaveProperty("probe");
      expect(agent).not.toHaveProperty("env_config");
      expect(agent).not.toHaveProperty("resolve_env");
    }
  });

  it("GET /api/registry/agents/:name 返回单项", async () => {
    const res = await fetch(`http://127.0.0.1:${getPort()}/api/registry/agents/codex`);
    expect(res.status).toBe(200);

    const body = await res.json();
    expect(body.agent.name).toBe("codex");
    expect(body.agent.label).toBe("OpenAI Codex CLI");
  });

  it("不存在的 agent 返回 404", async () => {
    const res = await fetch(`http://127.0.0.1:${getPort()}/api/registry/agents/nonexist`);
    expect(res.status).toBe(404);

    const body = await res.json();
    expect(body.error).toBeDefined();
    expect(String(body.error).toLowerCase()).toContain("not found");
  });

  it("响应带 CORS 头", async () => {
    const res = await fetch(`http://127.0.0.1:${getPort()}/api/registry/agents`);
    expect(res.status).toBe(200);
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
  });
});
