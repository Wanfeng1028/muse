import { randomUUID } from "node:crypto";
import { chmod, mkdtemp, readFile, realpath, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { expect, it, vi } from "vitest";
import { BackgroundController } from "./background-controller.js";
import { PersistentBackgroundOperationLedger } from "./background-operation-ledger.js";

it("reopens the persisted unknown operation and verifies without reapplying", async () => {
  const directory = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "om-bg-controller-")),
  );
  await chmod(directory, 0o700);
  const owner = { userId: "local", runtimeId: "synthetic-stable-data" };
  const intent = {
    operationId: randomUUID(),
    expectedRevision: 0,
    action: "enable" as const,
    planDigest: "a".repeat(64),
    artifactDigest: "b".repeat(64),
  };
  const apply = vi.fn(async () => {
    throw Error("lost after actual effect");
  });
  const adapter = {
    check: async () => true,
    apply,
    inspect: async () => "applied" as const,
  };
  try {
    const ledger = await PersistentBackgroundOperationLedger.initialize(
      directory,
      owner,
    );
    expect(
      (
        await new BackgroundController(owner, ledger, adapter).execute(
          intent,
          true,
        )
      ).state,
    ).toBe("unknown");
    const reopened = await PersistentBackgroundOperationLedger.open(
      directory,
      owner,
    );
    const controller = new BackgroundController(owner, reopened, adapter);
    expect((await controller.reconcile(intent.operationId))?.state).toBe(
      "committed",
    );
    expect((await controller.execute(intent, true)).state).toBe("committed");
    expect(apply).toHaveBeenCalledTimes(1);
    const stored = await readFile(
      path.join(directory, "background-operations/state.json"),
      "utf8",
    );
    expect(stored).not.toContain("lost after actual effect");
    expect(JSON.parse(stored).revision).toBe(4);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
