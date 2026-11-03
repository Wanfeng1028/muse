import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createInterface } from "node:readline";
import type { MatterContext } from "@one-memory/contracts";
import axios from "axios";
import { expect, it } from "vitest";
import { RecallBroker } from "./recall-broker.js";

type RpcResult = {
  id: number;
  result: {
    tools: { name: string }[];
    structuredContent: { contexts: MatterContext[] };
  };
};

const runtimePath = process.env.ONE_MEMORY_DEMO_TEST_RUNTIME;

it.skipIf(!runtimePath)(
  "reads authorized live dossiers through the built MCP stdio process",
  async () => {
    const runtime = JSON.parse(await readFile(runtimePath as string, "utf8"));
    const client = axios.create({
      baseURL: runtime.core_url,
      headers: { Authorization: `Bearer ${runtime.token}` },
      proxy: false,
    });
    const all = (await client.get("/api/v1/matters")).data;
    const matter = all.find((item: { title: string }) =>
      item.title.includes("MemHub"),
    );
    expect(matter?.availability).toBe("ready");
    const directory = await mkdtemp(path.join(os.tmpdir(), "om-matter-mcp-"));
    const discovery = path.join(directory, "broker.json");
    const broker = new RecallBroker({
      coreBaseUrl: runtime.core_url,
      coreApiToken: runtime.token,
      discoveryPath: discovery,
      instanceId: "matter-live-test",
      preferredPort: 0,
    });
    await broker.start();
    const child = spawn(process.execPath, [path.resolve("dist/mcp.cjs")], {
      env: { ...process.env, ONE_MEMORY_BROKER_DISCOVERY: discovery },
      stdio: ["pipe", "pipe", "pipe"],
    });
    const lineReader = createInterface({ input: child.stdout });
    const pending = new Map<number, (value: RpcResult) => void>();
    lineReader.on("line", (line) => {
      const response = JSON.parse(line);
      pending.get(response.id)?.(response);
      pending.delete(response.id);
    });
    let nextId = 0;
    function rpc(method: string, params: unknown) {
      const id = ++nextId;
      return new Promise<RpcResult>((resolve, reject) => {
        const timer = setTimeout(() => {
          pending.delete(id);
          reject(new Error("MCP timeout"));
        }, 15000);
        pending.set(id, (value) => {
          clearTimeout(timer);
          resolve(value);
        });
        child.stdin.write(
          `${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`,
        );
      });
    }
    async function share(value: boolean) {
      const current = (await client.get(`/api/v1/matters/${matter.matter_id}`))
        .data;
      await client.patch(`/api/v1/matters/${matter.matter_id}`, {
        expected_version: current.version,
        agent_access: value,
      });
    }
    try {
      await rpc("initialize", {
        protocolVersion: "2025-03-26",
        clientInfo: { name: "one-memory-live-acceptance", version: "1" },
        capabilities: {},
      });
      const listed = await rpc("tools/list", {});
      expect(
        listed.result.tools.some(
          (tool: { name: string }) => tool.name === "MemHub_matters",
        ),
      ).toBe(true);
      await share(false);
      const denied = await rpc("tools/call", {
        name: "om_matters",
        arguments: { query: "MemHub" },
      });
      expect(denied.result.structuredContent.contexts).toEqual([]);
      await share(true);
      const allowed = await rpc("tools/call", {
        name: "om_matters",
        arguments: { query: "MemHub" },
      });
      const context = allowed.result.structuredContent.contexts.find(
        (item: { matter_id: string }) => item.matter_id === matter.matter_id,
      );
      if (!context)
        throw new Error("Authorized matter context was not returned");
      expect(context.instruction_policy).toBe("reference_only");
      expect(context.text).toContain("evidence=");
      expect(context.text).toContain("revision=");
      await share(false);
      const revoked = await rpc("tools/call", {
        name: "om_matters",
        arguments: { query: "MemHub" },
      });
      expect(revoked.result.structuredContent.contexts).toEqual([]);
    } finally {
      await share(matter.agent_access);
      child.stdin.end();
      child.kill("SIGTERM");
      lineReader.close();
      await broker.stop();
      await rm(directory, { recursive: true, force: true });
    }
  },
  60000,
);
