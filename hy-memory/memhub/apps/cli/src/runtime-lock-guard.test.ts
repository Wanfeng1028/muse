import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { inspectRuntimeServiceLock } from "./runtime-lock-guard.js";

const roots: string[] = [];

async function fixture(): Promise<string> {
  const root = await mkdtemp(path.join(tmpdir(), "memhub-lock-guard-"));
  roots.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true, force: true })),
  );
});

describe("runtime service lock guard", () => {
  it("is clear when no service lease exists", async () => {
    await expect(inspectRuntimeServiceLock(await fixture())).resolves.toBe(
      "clear",
    );
  });

  it("reports a live owner even when runtime.json is absent", async () => {
    const dataDir = await fixture();
    const lock = path.join(dataDir, "runtime-service.lock");
    await mkdir(lock, { mode: 0o700 });
    await writeFile(
      path.join(lock, "owner.json"),
      JSON.stringify({ pid: 4321 }),
      { mode: 0o600 },
    );
    await expect(
      inspectRuntimeServiceLock(dataDir, (pid) => pid === 4321),
    ).resolves.toBe("live");
  });

  it("reports a stopped owner as clear", async () => {
    const dataDir = await fixture();
    const lock = path.join(dataDir, "runtime-service.lock");
    await mkdir(lock, { mode: 0o700 });
    await writeFile(
      path.join(lock, "owner.json"),
      JSON.stringify({ pid: 4321 }),
      { mode: 0o600 },
    );
    await expect(inspectRuntimeServiceLock(dataDir, () => false)).resolves.toBe(
      "clear",
    );
  });

  it("fails closed on a malformed lease", async () => {
    const dataDir = await fixture();
    const lock = path.join(dataDir, "runtime-service.lock");
    await mkdir(lock, { mode: 0o700 });
    await writeFile(path.join(lock, "owner.json"), "{not-json", {
      mode: 0o600,
    });
    await expect(inspectRuntimeServiceLock(dataDir)).resolves.toBe("unknown");
  });
});
