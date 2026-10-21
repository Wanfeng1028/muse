import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import os from "node:os";
import path from "node:path";
import { expect, it } from "vitest";
import { inspectBackgroundHealth } from "./background-health.js";

async function listen(server: Server): Promise<number> {
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  return (server.address() as AddressInfo).port;
}
async function close(server: Server) {
  if (server.listening)
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
}

it("actual HTTP proves healthy to degraded transition without writing a receipt", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "om-health-integration-"),
  );
  const instance = "health-fixture-instance",
    token = "synthetic-health-token";
  let coreReads = 0,
    brokerReads = 0;
  const core = createServer((req, res) => {
    coreReads++;
    if (
      req.url !== "/api/v1/runtime/identity" ||
      req.headers.authorization !== `Bearer ${token}`
    ) {
      res.writeHead(401).end();
      return;
    }
    res.setHeader("Content-Type", "application/json");
    res.end(
      JSON.stringify({
        status: "ok",
        service: "one-memory-core",
        instance_id: instance,
        version: "fixture",
      }),
    );
  });
  const broker = createServer((req, res) => {
    brokerReads++;
    expect(req.headers.authorization).toBeUndefined();
    res.setHeader("Content-Type", "application/json");
    res.end(
      JSON.stringify({
        status: "ok",
        service: "one-memory-recall-broker",
        instance_id: instance,
      }),
    );
  });
  try {
    const corePort = await listen(core),
      brokerPort = await listen(broker);
    await mkdir(path.join(directory, "integrations"), { mode: 0o700 });
    const files: Record<string, string> = {
      "runtime-token": token,
      "runtime.json": JSON.stringify({
        schema_version: 1,
        service: "one-memory-core",
        instance_id: instance,
        pid: process.pid,
        parent_pid: process.pid,
        host: "127.0.0.1",
        port: corePort,
        started_at: new Date().toISOString(),
      }),
      "runtime-service.json": JSON.stringify({
        schema_version: 1,
        service: "one-memory-runtime",
        status: "running",
        instance_id: instance,
        pid: process.pid,
        core_port: corePort,
        started_at: new Date().toISOString(),
      }),
      "integrations/cursor-broker.json": JSON.stringify({
        schema_version: 1,
        service: "one-memory-recall-broker",
        status: "running",
        host: "127.0.0.1",
        port: brokerPort,
        instance_id: instance,
        pid: process.pid,
        updated_at: new Date().toISOString(),
      }),
    };
    for (const [name, text] of Object.entries(files))
      await writeFile(path.join(directory, name), text, { mode: 0o600 });
    expect(await inspectBackgroundHealth({ dataDir: directory })).toMatchObject(
      {
        state: "healthy",
        core: "running",
        broker: "running",
        instanceId: instance,
      },
    );
    expect(coreReads).toBe(2);
    expect(brokerReads).toBe(1);
    await close(broker);
    const unavailable = await inspectBackgroundHealth({ dataDir: directory });
    expect(unavailable).toMatchObject({
      state: "degraded",
      core: "running",
      broker: "unhealthy",
    });
    expect(JSON.stringify(unavailable)).not.toContain(token);
    for (const [name, text] of Object.entries(files))
      expect(await readFile(path.join(directory, name), "utf8")).toBe(text);
  } finally {
    await close(core);
    await close(broker);
    await rm(directory, { recursive: true, force: true });
  }
});
