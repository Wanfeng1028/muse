export interface BackgroundOwner {
  userId: string;
  runtimeId: string;
}

export interface BackgroundIntent {
  operationId: string;
  expectedRevision: number;
  action: "enable" | "disable";
  planDigest: string;
  artifactDigest: string;
}

export interface BackgroundOperation extends BackgroundIntent {
  state: "prepared" | "applying" | "committed" | "rejected" | "unknown";
  code: string | null;
}

export interface BackgroundOperationSnapshot {
  schemaVersion: 1;
  userId: string;
  runtimeId: string;
  revision: number;
  operations: readonly BackgroundOperation[];
}

export interface BackgroundOperationLedger {
  exclusive<T>(owner: BackgroundOwner, run: () => Promise<T>): Promise<T>;
  load(owner: BackgroundOwner): Promise<BackgroundOperationSnapshot | null>;
  commit(
    owner: BackgroundOwner,
    expectedRevision: number | null,
    next: BackgroundOperationSnapshot,
  ): Promise<void>;
}

export function validateBackgroundOwner(owner: BackgroundOwner): void {
  exact(owner, ["userId", "runtimeId"]);
  for (const value of [owner.userId, owner.runtimeId]) {
    if (
      typeof value !== "string" ||
      !/^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$/.test(value)
    )
      fail();
  }
}

export function validateBackgroundIntent(intent: BackgroundIntent): void {
  exact(intent, [
    "operationId",
    "expectedRevision",
    "action",
    "planDigest",
    "artifactDigest",
  ]);
  if (
    typeof intent.operationId !== "string" ||
    !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(
      intent.operationId,
    )
  )
    fail();
  if (
    !Number.isSafeInteger(intent.expectedRevision) ||
    intent.expectedRevision < 0 ||
    intent.expectedRevision >= Number.MAX_SAFE_INTEGER
  )
    fail();
  if (intent.action !== "enable" && intent.action !== "disable") fail();
  for (const hash of [intent.planDigest, intent.artifactDigest]) {
    if (typeof hash !== "string" || !/^[a-f0-9]{64}$/.test(hash)) fail();
  }
}

export function validateBackgroundSnapshot(
  value: unknown,
  owner: BackgroundOwner,
): BackgroundOperationSnapshot {
  validateBackgroundOwner(owner);
  exact(value, [
    "schemaVersion",
    "userId",
    "runtimeId",
    "revision",
    "operations",
  ]);
  const snapshot = value as BackgroundOperationSnapshot;
  if (
    snapshot.schemaVersion !== 1 ||
    snapshot.userId !== owner.userId ||
    snapshot.runtimeId !== owner.runtimeId ||
    !Number.isSafeInteger(snapshot.revision) ||
    snapshot.revision < 1 ||
    snapshot.revision >= Number.MAX_SAFE_INTEGER ||
    !Array.isArray(snapshot.operations) ||
    snapshot.operations.length < 1 ||
    snapshot.operations.length > 32
  )
    fail();
  const ids = new Set<string>();
  let previous = -1;
  for (const [index, operation] of snapshot.operations.entries()) {
    exact(operation, [
      "operationId",
      "expectedRevision",
      "action",
      "planDigest",
      "artifactDigest",
      "state",
      "code",
    ]);
    const { state, code, ...intent } = operation;
    validateBackgroundIntent(intent);
    if (
      ids.has(intent.operationId) ||
      intent.expectedRevision <= previous ||
      intent.expectedRevision >= snapshot.revision
    )
      fail();
    previous = intent.expectedRevision;
    ids.add(intent.operationId);
    if (
      !["prepared", "applying", "committed", "rejected", "unknown"].includes(
        state,
      )
    )
      fail();
    if (
      code !== null &&
      (typeof code !== "string" || !/^[a-z][a-z0-9_]{0,95}$/.test(code))
    )
      fail();
    if (
      index < snapshot.operations.length - 1 &&
      state !== "committed" &&
      state !== "rejected"
    )
      fail();
  }
  return structuredClone(snapshot);
}

export function validateBackgroundTransition(
  previous: BackgroundOperationSnapshot | null,
  next: BackgroundOperationSnapshot,
  owner: BackgroundOwner,
): void {
  validateBackgroundSnapshot(next, owner);
  if (previous) validateBackgroundSnapshot(previous, owner);
  if (next.revision !== (previous?.revision ?? 0) + 1) fail();
  if (!previous) {
    if (
      next.operations.length !== 1 ||
      next.operations[0].expectedRevision !== 0 ||
      next.operations[0].state !== "prepared" ||
      next.operations[0].code !== null
    )
      fail();
    return;
  }
  const last = previous.operations[previous.operations.length - 1];
  const current = next.operations[next.operations.length - 1];
  if (current.operationId !== last.operationId) {
    if (
      !["committed", "rejected"].includes(last.state) ||
      current.state !== "prepared" ||
      current.code !== null ||
      current.expectedRevision !== previous.revision ||
      previous.operations.some((op) => op.operationId === current.operationId)
    )
      fail();
    if (
      operationValues(next.operations) !==
      operationValues([...previous.operations.slice(-31), current])
    )
      fail();
    return;
  }
  if (
    next.operations.length !== previous.operations.length ||
    operationValues(next.operations.slice(0, -1)) !==
      operationValues(previous.operations.slice(0, -1))
  )
    fail();
  const oldState = last.state,
    state = current.state;
  if (
    operationValues([{ ...last, state, code: current.code }]) !==
    operationValues([current])
  )
    fail();
  const allowed: Record<BackgroundOperation["state"], readonly string[]> = {
    prepared: ["applying", "rejected"],
    applying: ["committed", "unknown"],
    unknown: ["committed", "rejected"],
    committed: [],
    rejected: [],
  };
  if (!allowed[oldState].includes(state)) fail();
}

function operationValues(operations: readonly BackgroundOperation[]): string {
  return JSON.stringify(
    operations.map((item) => [
      item.operationId,
      item.expectedRevision,
      item.action,
      item.planDigest,
      item.artifactDigest,
      item.state,
      item.code,
    ]),
  );
}

function exact(value: unknown, keys: readonly string[]): void {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.getPrototypeOf(value) !== Object.prototype ||
    Object.keys(value).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(value, key))
  )
    fail();
}
function fail(): never {
  throw Error("background_operation_invalid");
}
