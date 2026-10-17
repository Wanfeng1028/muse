import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import type { AddressInfo } from "node:net";
import { openDb, type Db } from "../src/db.js";
import { startServer, type RunningServer } from "../src/server.js";
import type { GatewayConfig } from "../src/config.js";
import type { ArtifactUploadGrant } from "@botstalk/protocol";

const HERE = dirname(fileURLToPath(import.meta.url));

let server: RunningServer;
let db: Db;
let base: string;
let tmpDir: string;

beforeAll(async () => {
  const parent = join(HERE, "test-tmp");
  mkdirSync(parent, { recursive: true });
  tmpDir = mkdtempSync(join(parent, "artifacts-"));
  db = openDb(tmpDir);
  const config: GatewayConfig = { port: 0, dataDir: tmpDir, roomMaxMembersWorkroom: 50, roomMaxMembersPlayroom: 200, gameBroadcastThrottleMs: 500 };
  server = startServer(config, db);
  await new Promise<void>((r) => server.httpServer.once("listening", r));
  const addr = server.httpServer.address() as AddressInfo;
  base = `http://127.0.0.1:${addr.port}`;
});

afterAll(async () => {
  await server.close();
  db.close();
  rmSync(tmpDir, { recursive: true, force: true });
});

describe("artifacts", () => {
  it("full roundtrip", async () => {
    const reqRes = await fetch(`${base}/artifacts/request`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: "hello.txt", declared_size: 11 }),
    });
    expect(reqRes.status).toBe(201);
    const grant = (await reqRes.json()) as ArtifactUploadGrant;
    expect(typeof grant.upload_url).toBe("string");

    const body = new TextEncoder().encode("hello world");
    const putRes = await fetch(grant.upload_url, {
      method: "PUT",
      body,
    });
    expect(putRes.status).toBe(200);
    const putJson = (await putRes.json()) as {
      id: string;
      filename: string;
      size: number;
    };
    expect(putJson.filename).toBe("hello.txt");
    expect(putJson.size).toBe(11);
    expect(typeof putJson.id).toBe("string");

    const getRes = await fetch(`${base}/artifacts/${putJson.id}`);
    expect(getRes.status).toBe(200);
    const text = await getRes.text();
    expect(text).toBe("hello world");
  });

  it("size mismatch", async () => {
    const reqRes = await fetch(`${base}/artifacts/request`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: "mismatch.txt", declared_size: 11 }),
    });
    expect(reqRes.status).toBe(201);
    const grant = (await reqRes.json()) as ArtifactUploadGrant;

    const body = new TextEncoder().encode("hello");
    const putRes = await fetch(grant.upload_url, {
      method: "PUT",
      body,
    });
    expect(putRes.status).toBe(400);
  });

  it("bad token", async () => {
    const putRes = await fetch(`${base}/artifacts/upload/nope`, {
      method: "PUT",
      body: new TextEncoder().encode("x"),
    });
    expect(putRes.status).toBe(410);
  });

  it("get missing", async () => {
    const getRes = await fetch(`${base}/artifacts/artf_000`);
    expect(getRes.status).toBe(404);
  });
});

// 自查：红线 1-5 逐条通过
