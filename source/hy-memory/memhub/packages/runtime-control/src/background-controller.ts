import {
  type BackgroundIntent,
  type BackgroundOperation,
  type BackgroundOperationLedger,
  type BackgroundOperationSnapshot,
  type BackgroundOwner,
  validateBackgroundIntent,
  validateBackgroundOwner,
  validateBackgroundSnapshot,
} from "./background-operation.js";

export interface BackgroundOperationAdapter {
  /** Trusted control adapter verifies current plan/artifact/owner, not renderer assertions. */
  check(intent: Readonly<BackgroundIntent>): Promise<boolean>;
  apply(intent: Readonly<BackgroundIntent>): Promise<void>;
  /** applied means exact intended registration/identity verified; exit0 is insufficient. */
  inspect(
    intent: Readonly<BackgroundIntent>,
  ): Promise<"applied" | "not_applied" | "unknown" | "conflict">;
}

/** Coordinates an explicit operation; no default OS adapter or automatic replay.
 * Cross-process admission and crash fences belong to the supplied persistent ledger.
 */
export class BackgroundController {
  private readonly owner: BackgroundOwner;
  constructor(
    owner: BackgroundOwner,
    private readonly ledger: BackgroundOperationLedger,
    private readonly adapter: BackgroundOperationAdapter,
  ) {
    validateBackgroundOwner(owner);
    this.owner = Object.freeze({ ...owner });
  }

  async execute(
    input: BackgroundIntent,
    confirmed: boolean,
  ): Promise<BackgroundOperation> {
    if (confirmed !== true) throw Error("background_confirmation_required");
    validateBackgroundIntent(input);
    const intent = Object.freeze({ ...input });
    return this.ledger.exclusive(this.owner, async () => {
      let snapshot = await this.load();
      const previous = snapshot?.operations.find(
        (op) => op.operationId === intent.operationId,
      );
      if (previous) {
        if (!sameIntent(previous, intent))
          throw Error("background_operation_conflict");
        return { ...previous };
      }
      if (
        snapshot &&
        !terminal(snapshot.operations[snapshot.operations.length - 1])
      )
        throw Error("background_operation_pending");
      if ((snapshot?.revision ?? 0) !== intent.expectedRevision)
        throw Error("background_revision_conflict");
      snapshot = await this.save(snapshot, [
        ...(snapshot?.operations ?? []).slice(-31),
        { ...intent, state: "prepared", code: null },
      ]);
      let valid = false;
      try {
        valid = await this.adapter.check(intent);
      } catch {
        valid = false;
      }
      if (!valid)
        return this.finish(snapshot, "rejected", "background_plan_changed");
      snapshot = await this.advance(snapshot, "applying", null);
      let observation: Awaited<
        ReturnType<BackgroundOperationAdapter["inspect"]>
      > = "unknown";
      try {
        await this.adapter.apply(intent);
        observation = await this.adapter.inspect(intent);
      } catch {
        /* Any exception after applying is an uncertain side effect. */
      }
      return this.finish(
        snapshot,
        observation === "applied" ? "committed" : "unknown",
        observation === "applied" ? null : "background_result_unknown",
      );
    });
  }

  async reconcile(operationId: string): Promise<BackgroundOperation | null> {
    return this.ledger.exclusive(this.owner, async () => {
      let snapshot = await this.load();
      const previous = snapshot?.operations.find(
        (op) => op.operationId === operationId,
      );
      if (!snapshot || !previous) return null;
      if (terminal(previous) || previous.state === "prepared")
        return { ...previous };
      // A persisted applying state after a lost response is never replayed.
      if (previous.state === "applying")
        snapshot = await this.advance(
          snapshot,
          "unknown",
          "background_result_unknown",
        );
      let observation: Awaited<
        ReturnType<BackgroundOperationAdapter["inspect"]>
      > = "unknown";
      try {
        observation = await this.adapter.inspect(intentOf(previous));
      } catch {
        /* Remain unknown. */
      }
      if (observation === "applied")
        return this.finish(snapshot, "committed", null);
      if (observation === "not_applied")
        return this.finish(snapshot, "rejected", "background_not_applied");
      return { ...snapshot.operations[snapshot.operations.length - 1] };
    });
  }

  async cancelPrepared(
    operationId: string,
    expectedRevision: number,
    confirmed: boolean,
  ): Promise<BackgroundOperation> {
    if (confirmed !== true) throw Error("background_confirmation_required");
    return this.ledger.exclusive(this.owner, async () => {
      const snapshot = await this.load();
      if (!snapshot || snapshot.revision !== expectedRevision)
        throw Error("background_revision_conflict");
      const current = snapshot.operations[snapshot.operations.length - 1];
      if (current.operationId !== operationId || current.state !== "prepared")
        throw Error("background_cancel_not_safe");
      // Applying is committed before the adapter call. A healthy ledger that
      // still contains prepared therefore proves this operation was not sent.
      return this.finish(
        snapshot,
        "rejected",
        "background_cancelled_before_apply",
      );
    });
  }

  private async load() {
    const snapshot = await this.ledger.load(this.owner);
    return snapshot ? validateBackgroundSnapshot(snapshot, this.owner) : null;
  }
  private async save(
    previous: BackgroundOperationSnapshot | null,
    operations: readonly BackgroundOperation[],
  ) {
    const next: BackgroundOperationSnapshot = {
      schemaVersion: 1,
      ...this.owner,
      revision: (previous?.revision ?? 0) + 1,
      operations,
    };
    await this.ledger.commit(this.owner, previous?.revision ?? null, next);
    return next;
  }
  private async advance(
    snapshot: BackgroundOperationSnapshot,
    state: BackgroundOperation["state"],
    code: string | null,
  ) {
    const current = snapshot.operations[snapshot.operations.length - 1];
    return this.save(snapshot, [
      ...snapshot.operations.slice(0, -1),
      { ...current, state, code },
    ]);
  }
  private async finish(
    snapshot: BackgroundOperationSnapshot,
    state: BackgroundOperation["state"],
    code: string | null,
  ) {
    const next = await this.advance(snapshot, state, code);
    return { ...next.operations[next.operations.length - 1] };
  }
}

function terminal(operation: BackgroundOperation): boolean {
  return operation.state === "committed" || operation.state === "rejected";
}
function intentOf(operation: BackgroundOperation): Readonly<BackgroundIntent> {
  const { state: _state, code: _code, ...intent } = operation;
  return Object.freeze(intent);
}
function sameIntent(
  operation: BackgroundOperation,
  intent: BackgroundIntent,
): boolean {
  return (
    operation.expectedRevision === intent.expectedRevision &&
    operation.action === intent.action &&
    operation.planDigest === intent.planDigest &&
    operation.artifactDigest === intent.artifactDigest
  );
}
