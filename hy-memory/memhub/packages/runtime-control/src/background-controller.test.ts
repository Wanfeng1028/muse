import { randomUUID } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import { BackgroundController } from "./background-controller.js";
import {
  type BackgroundOperationLedger,
  type BackgroundOperationSnapshot,
  validateBackgroundTransition,
} from "./background-operation.js";

const owner = { userId: "local", runtimeId: "stable-data" };
function setup() {
  let state: BackgroundOperationSnapshot | null = null;
  const ledger: BackgroundOperationLedger = {
    exclusive: async (_owner, run) => run(),
    load: async () => state && structuredClone(state),
    commit: async (_owner, expected, next) => {
      expect(state?.revision ?? null).toBe(expected);
      validateBackgroundTransition(state, next, owner);
      state = structuredClone(next);
    },
  };
  const inspect = vi.fn(
    async () => "applied" as "applied" | "not_applied" | "unknown" | "conflict",
  );
  const check = vi.fn(async () => true),
    apply = vi.fn(async () => {});
  const adapter = { check, apply, inspect };
  const controller = new BackgroundController(owner, ledger, adapter);
  const intent = {
    operationId: randomUUID(),
    expectedRevision: 0,
    action: "enable" as const,
    planDigest: "a".repeat(64),
    artifactDigest: "b".repeat(64),
  };
  return { controller, ledger, adapter, intent, state: () => state };
}
describe("background operation controller", () => {
  it("failure to persist final receipt leaves applying and never repeats the side effect", async () => {
    const f = setup();
    const commit = f.ledger.commit;
    f.ledger.commit = async (owner, revision, next) => {
      if (next.operations.at(-1)?.state === "committed")
        throw Error("disk full after effect");
      await commit(owner, revision, next);
    };
    await expect(f.controller.execute(f.intent, true)).rejects.toThrow(
      "disk full",
    );
    expect(f.state()?.operations.at(-1)?.state).toBe("applying");
    expect((await f.controller.execute(f.intent, true)).state).toBe("applying");
    f.ledger.commit = commit;
    expect((await f.controller.reconcile(f.intent.operationId))?.state).toBe(
      "committed",
    );
    expect(f.adapter.apply).toHaveBeenCalledTimes(1);
  });
  it("explicitly cancels only a persisted prepared operation, without calling adapter", async () => {
    const f = setup();
    const prepared: BackgroundOperationSnapshot = {
      schemaVersion: 1,
      ...owner,
      revision: 1,
      operations: [{ ...f.intent, state: "prepared", code: null }],
    };
    await f.ledger.commit(owner, null, prepared);
    await expect(
      f.controller.cancelPrepared(f.intent.operationId, 0, true),
    ).rejects.toThrow("revision");
    expect(
      (await f.controller.cancelPrepared(f.intent.operationId, 1, true)).state,
    ).toBe("rejected");
    expect(f.adapter.apply).not.toHaveBeenCalled();
    expect(f.adapter.inspect).not.toHaveBeenCalled();
    expect((await f.controller.execute(f.intent, true)).code).toBe(
      "background_cancelled_before_apply",
    );
  });
  it("cannot cancel an unknown side effect or start a new operation with stale revision", async () => {
    const f = setup();
    f.adapter.apply.mockRejectedValueOnce(Error("lost"));
    await f.controller.execute(f.intent, true);
    await expect(
      f.controller.cancelPrepared(
        f.intent.operationId,
        f.state()?.revision ?? -1,
        true,
      ),
    ).rejects.toThrow("not_safe");
    await f.controller.reconcile(f.intent.operationId);
    await expect(
      f.controller.execute({ ...f.intent, operationId: randomUUID() }, true),
    ).rejects.toThrow("revision");
    expect(f.adapter.apply).toHaveBeenCalledTimes(1);
  });
  it("records applying before actual side effect and repeat never applies again", async () => {
    const f = setup();
    f.adapter.apply.mockImplementation(async () => {
      expect(f.state()?.operations[0].state).toBe("applying");
    });
    expect((await f.controller.execute(f.intent, true)).state).toBe(
      "committed",
    );
    expect((await f.controller.execute(f.intent, true)).state).toBe(
      "committed",
    );
    expect(f.adapter.apply).toHaveBeenCalledTimes(1);
  });
  it("requires explicit confirmation before any ledger or adapter action", async () => {
    const f = setup();
    await expect(f.controller.execute(f.intent, false)).rejects.toThrow(
      "confirmation",
    );
    expect(f.state()).toBeNull();
    expect(f.adapter.check).not.toHaveBeenCalled();
  });
  it("lost apply response stays unknown and reconciliation is read-only", async () => {
    const f = setup();
    f.adapter.apply.mockRejectedValueOnce(Error("secret model text"));
    const first = await f.controller.execute(f.intent, true);
    expect(first.state).toBe("unknown");
    expect(JSON.stringify(first)).not.toContain("secret");
    expect((await f.controller.execute(f.intent, true)).state).toBe("unknown");
    expect((await f.controller.reconcile(f.intent.operationId))?.state).toBe(
      "committed",
    );
    expect(f.adapter.apply).toHaveBeenCalledTimes(1);
  });
  it("blocks fresh intent while prior outcome is unknown", async () => {
    const f = setup();
    f.adapter.inspect.mockResolvedValue("unknown");
    await f.controller.execute(f.intent, true);
    await expect(
      f.controller.execute(
        {
          ...f.intent,
          operationId: randomUUID(),
          expectedRevision: f.state()?.revision ?? -1,
        },
        true,
      ),
    ).rejects.toThrow("pending");
    expect(f.adapter.apply).toHaveBeenCalledTimes(1);
  });
  it("rejects stale plans without calling apply", async () => {
    const f = setup();
    f.adapter.check.mockResolvedValue(false);
    expect((await f.controller.execute(f.intent, true)).state).toBe("rejected");
    expect(f.adapter.apply).not.toHaveBeenCalled();
  });
  it("not-found reconcile is not permission to retry", async () => {
    const f = setup();
    expect(await f.controller.reconcile(randomUUID())).toBeNull();
    expect(f.adapter.apply).not.toHaveBeenCalled();
  });
  it("storage failure before applying causes zero side effects", async () => {
    const f = setup();
    f.ledger.commit = async () => {
      throw Error("disk unavailable");
    };
    await expect(f.controller.execute(f.intent, true)).rejects.toThrow();
    expect(f.adapter.apply).not.toHaveBeenCalled();
  });
  it("reuses persisted operation after controller recreation", async () => {
    const f = setup();
    f.adapter.inspect.mockResolvedValueOnce("unknown");
    await f.controller.execute(f.intent, true);
    const reopened = new BackgroundController(owner, f.ledger, f.adapter);
    expect((await reopened.reconcile(f.intent.operationId))?.state).toBe(
      "committed",
    );
    expect(f.adapter.apply).toHaveBeenCalledTimes(1);
  });
});
