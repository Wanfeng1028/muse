import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, expect, it } from "vitest";

import { readPublishedCorePort } from "./discovery.js";

let dataDir: string;

beforeEach(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "one-memory-core-port-"));
});

afterEach(async () => {
  await rm(dataDir, { recursive: true, force: true });
});

async function writeReceipt(value: unknown): Promise<void> {
  await writeFile(
    path.join(dataDir, "runtime-service.json"),
    JSON.stringify(value),
  );
}

const base = {
  schema_version: 1,
  service: "one-memory-runtime",
  instance_id: "fixture-runtime",
  pid: 4321,
  status: "running",
};

it("returns the port a running Runtime published", async () => {
  await writeReceipt({ ...base, core_port: 9423 });
  await expect(readPublishedCorePort(dataDir)).resolves.toBe(9423);
});

it("publishes no port when the Runtime is not running yet", async () => {
  await writeReceipt({ ...base, status: "starting", core_port: 9423 });
  await expect(readPublishedCorePort(dataDir)).resolves.toBeNull();
});

it("publishes null instead of guessing when the receipt is absent", async () => {
  // A missing receipt must never be read as "the default port": the caller
  // keeps its own fallback rather than silently pointing at 8765.
  await expect(readPublishedCorePort(dataDir)).resolves.toBeNull();
});

it("publishes null rather than a port from a malformed receipt", async () => {
  await writeReceipt({ ...base, core_port: 80 });
  await expect(readPublishedCorePort(dataDir)).resolves.toBeNull();
});
