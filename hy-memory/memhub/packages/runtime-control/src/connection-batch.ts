import { createHash } from "node:crypto";
import type { HostReadTool } from "@one-memory/host-bridge";

export interface BatchOwner {
  userId: string;
  runtimeId: string;
}
export interface SourceIdentity {
  sourceId: string;
  rootId: string;
  rootPath: string;
  grantRevision: number;
}
/** layoutDigest covers the COMPLETE trusted RecallHostLayout, including paths,
 * plugin/supersedes/channel. It is not a host label or a renderer-chosen path. */
export interface HostIdentity {
  hostId: string;
  layoutDigest: string;
  installationId: string | null;
  permissionRevision: number;
  /** Hash of nonsecret managed-file/layout state; NEVER a credential digest. */
  installationDigest: string | null;
}
export type ConnectionItem =
  | {
      id: string;
      kind: "install";
      sources: SourceIdentity[];
      host: HostIdentity;
      previewFingerprint: string;
    }
  | {
      id: string;
      kind: "readGrant";
      sources: SourceIdentity[];
      host: HostIdentity;
      installItemId?: string;
      allowedTools: readonly HostReadTool[];
      allowedScopes: readonly string[];
    };
export interface ConnectionPlan extends BatchOwner {
  schemaVersion: 1;
  operationId: string;
  items: ConnectionItem[];
}
interface ReceiptBinding extends BatchOwner {
  operationId: string;
  itemId: string;
  intentDigest: string;
}
export type ItemReceipt = ReceiptBinding &
  (
    | { kind: "install"; host: HostIdentity }
    | {
        kind: "readGrant";
        host: HostIdentity;
        allowedTools: readonly HostReadTool[];
        allowedScopes: readonly string[];
      }
  );
export interface ItemContext extends ReceiptBinding {
  /** Receipt of this batch's completed install, or the exact original identity. */
  host: HostIdentity | null;
}
export type Inspection =
  | { status: "denied" | "unavailable" }
  | {
      status: "ready";
      sources: SourceIdentity[];
      host: HostIdentity | null;
      previewFingerprint: string | null;
    };
export type AdapterResult =
  | { status: "succeeded"; receipt: ItemReceipt }
  | { status: "unknown" | "rejected" | "changed" | "not_applied" };
export interface ItemAdapter {
  /** Must atomically recheck supplied identities/fingerprints with the effect.
   * Rejected means authoritative refusal, not an arbitrary transport exception. */
  apply(
    item: Readonly<ConnectionItem>,
    context: Readonly<ItemContext>,
  ): Promise<AdapterResult>;
  /** READ ONLY. Correlate operation/intent to authority receipts. Mere presence
   * of an installation or enabled flag does not prove this operation succeeded. */
  reconcile(
    item: Readonly<ConnectionItem>,
    context: Readonly<ItemContext>,
  ): Promise<AdapterResult>;
}
export interface BatchAdapters {
  inspect(
    item: Readonly<ConnectionItem>,
    context: Readonly<ItemContext>,
  ): Promise<Inspection>;
  install: ItemAdapter;
  readGrant: ItemAdapter;
}
export type ItemState =
  | "pending"
  | "in_flight"
  | "succeeded"
  | "unknown"
  | "rejected"
  | "changed"
  | "not_applied"
  | "unavailable"
  | "dependency_blocked";
export interface ItemJournal {
  id: string;
  kind: ConnectionItem["kind"];
  intentDigest: string;
  state: ItemState;
  receipt: ItemReceipt | null;
}
/** Nonsecret operation summary only, not permission authority or host config. */
export interface BatchJournal extends BatchOwner {
  schemaVersion: 1;
  operationId: string;
  planDigest: string;
  revision: number;
  items: ItemJournal[];
}
export interface BatchLedger {
  durability: "process" | "persistent";
  /** Runtime-wide exclusive execution across all batches/instances for this
   * owner, held until in-flight calls settle. Persistent implementations must
   * fence process owners; timeout alone may not steal a live executor's lock. */
  exclusive<T>(owner: BatchOwner, operation: () => Promise<T>): Promise<T>;
  load(owner: BatchOwner, operationId: string): Promise<BatchJournal | null>;
  /** Atomic durable CAS; create expected=null must refuse existing files. A
   * successful return must survive restart before any adapter effect starts. */
  commit(
    owner: BatchOwner,
    operationId: string,
    expectedRevision: number | null,
    next: BatchJournal,
  ): Promise<void>;
}
export interface BatchOptions {
  mode?: "preview" | "execute";
  userConfirmed?: boolean;
  planDigest?: string;
  signal?: AbortSignal;
}
export interface BatchResult {
  mode: "preview" | "execute";
  operationId: string;
  planDigest: string;
  state: "preview" | "completed" | "partial";
  recovery: "none" | "process" | "persistent";
  cancelled: boolean;
  items: ItemJournal[];
}

/** Only trusted Runtime control callers may instantiate this module. Digest is
 * confirmation integrity, NOT authentication. Nothing here accesses files or
 * credentials; the injected ledger/adapters own those established boundaries. */
export class ConnectionBatch {
  private readonly owner: BatchOwner;
  constructor(
    owner: BatchOwner,
    private readonly adapters: BatchAdapters,
    private readonly ledger?: BatchLedger,
  ) {
    this.owner = freeze(clone(owner));
    exact(this.owner, ["userId", "runtimeId"]);
    identifier(this.owner.userId);
    identifier(this.owner.runtimeId);
  }

  async run(
    input: ConnectionPlan,
    options: BatchOptions = {},
  ): Promise<BatchResult> {
    const plan = checkedPlan(input);
    if (
      plan.userId !== this.owner.userId ||
      plan.runtimeId !== this.owner.runtimeId
    )
      fail("owner_mismatch");
    const digest = connectionPlanDigest(plan);
    if (
      options.mode !== undefined &&
      options.mode !== "preview" &&
      options.mode !== "execute"
    )
      fail("invalid_input");
    const confirmed = options.userConfirmed === true;
    const approvedDigest = options.planDigest;
    const signal = options.signal;
    const initial: BatchJournal = {
      schemaVersion: 1,
      ...this.owner,
      operationId: plan.operationId,
      planDigest: digest,
      revision: 1,
      items: plan.items.map((item) => ({
        id: item.id,
        kind: item.kind,
        intentDigest: itemDigest(item),
        state: "pending",
        receipt: null,
      })),
    };
    if (options.mode !== "execute") {
      for (const [index, item] of plan.items.entries()) {
        if (signal?.aborted) break;
        const context = this.context(plan, item, initial);
        initial.items[index].state = context
          ? await this.inspect(item, context)
          : "dependency_blocked";
      }
      return this.result(initial, "preview", signal?.aborted === true);
    }
    if (!confirmed) fail("confirmation_required");
    if (approvedDigest !== digest) fail("plan_changed");
    const ledger = this.ledger;
    if (!ledger) fail("ledger_required");
    if (!["process", "persistent"].includes(ledger.durability))
      fail("ledger_invalid");
    return ledger
      .exclusive(this.owner, async () => {
        let saved: BatchJournal | null;
        try {
          saved = await ledger.load(this.owner, plan.operationId);
        } catch {
          fail("ledger_unavailable");
        }
        let journal = initial;
        if (saved !== null) {
          journal = this.validateJournal(saved, plan, digest);
        } else if (!signal?.aborted) {
          await this.commit(ledger, null, journal);
        } else return this.result(journal, "execute", true);
        const persist = async (
          index: number,
          state: ItemState,
          receipt: ItemReceipt | null = null,
        ) => {
          const next = clone(journal);
          next.revision++;
          next.items[index] = { ...next.items[index], state, receipt };
          await this.commit(ledger, journal.revision, next);
          journal = next;
        };
        for (const [index, item] of plan.items.entries()) {
          if (signal?.aborted) break;
          const previous = journal.items[index];
          if (
            ["succeeded", "rejected", "changed", "not_applied"].includes(
              previous.state,
            )
          )
            continue;
          const context = this.context(plan, item, journal);
          if (!context) {
            if (previous.state !== "dependency_blocked")
              await persist(index, "dependency_blocked");
            continue;
          }
          const adapter = this.adapters[item.kind];
          if (previous.state === "unknown" || previous.state === "in_flight") {
            // Effect may have committed before connection/ledger loss. No retry
            // is permitted, even if reconciliation reports definitively absent.
            const recoveryIdentity = await this.recoveryIdentity(item, context);
            if (recoveryIdentity !== "pending") {
              await persist(index, recoveryIdentity);
              continue;
            }
            const resolved = await this.effect(
              adapter,
              "reconcile",
              item,
              context,
            );
            await persist(index, resolved.state, resolved.receipt);
            continue;
          }
          const inspection = await this.inspect(item, context);
          if (signal?.aborted) break;
          if (inspection !== "pending") {
            await persist(index, inspection);
            continue;
          }
          // Journal I/O is deliberately outside effect catch: a failed save
          // stops the batch and preserves in_flight for later reconciliation.
          await persist(index, "in_flight");
          if (signal?.aborted) {
            await persist(index, "not_applied");
            break;
          }
          const outcome = await this.effect(adapter, "apply", item, context);
          await persist(index, outcome.state, outcome.receipt);
        }
        return this.result(journal, "execute", signal?.aborted === true);
      })
      .catch((error: unknown) => {
        if (
          error instanceof Error &&
          [
            "connection_batch_operation_conflict",
            "connection_batch_journal_invalid",
            "connection_batch_ledger_unavailable",
          ].includes(error.message)
        )
          throw error;
        fail("ledger_unavailable");
      });
  }

  private context(
    plan: ConnectionPlan,
    item: ConnectionItem,
    journal: BatchJournal,
  ): Readonly<ItemContext> | null {
    let host = item.host;
    if (item.kind === "readGrant" && item.installItemId) {
      const dependency = journal.items.find(
        (row) => row.id === item.installItemId,
      );
      if (
        dependency?.state !== "succeeded" ||
        dependency.receipt?.kind !== "install"
      )
        return null;
      host = dependency.receipt.host;
    }
    return freeze(
      clone({
        ...this.owner,
        operationId: plan.operationId,
        itemId: item.id,
        intentDigest: itemDigest(item),
        host,
      }),
    );
  }

  private async inspect(
    item: ConnectionItem,
    context: Readonly<ItemContext>,
  ): Promise<ItemState> {
    try {
      const value = await this.adapters.inspect(item, context);
      if (value.status === "denied") return "rejected";
      if (value.status !== "ready") return "unavailable";
      if (canonical(value.sources) !== canonical(item.sources))
        return "changed";
      if (canonical(value.host) !== canonical(context.host)) return "changed";
      if (
        item.kind === "install" &&
        value.previewFingerprint !== item.previewFingerprint
      )
        return "changed";
      return "pending";
    } catch {
      return "unavailable";
    }
  }

  private async recoveryIdentity(
    item: ConnectionItem,
    context: Readonly<ItemContext>,
  ): Promise<"pending" | "changed" | "unknown" | "rejected"> {
    try {
      const current = await this.adapters.inspect(item, context);
      if (current.status === "denied") return "rejected";
      if (current.status !== "ready") return "unknown";
      if (canonical(current.sources) !== canonical(item.sources))
        return "changed";
      // The write itself may have changed revision/fingerprint. Reconciliation
      // must prove that exact transition, but never across another layout/root.
      return current.host?.hostId === item.host.hostId &&
        current.host.layoutDigest === item.host.layoutDigest
        ? "pending"
        : "changed";
    } catch {
      return "unknown";
    }
  }

  private async effect(
    adapter: ItemAdapter,
    method: "apply" | "reconcile",
    item: ConnectionItem,
    context: Readonly<ItemContext>,
  ): Promise<{ state: ItemState; receipt: ItemReceipt | null }> {
    try {
      const result = await adapter[method](item, context);
      if (result.status === "succeeded")
        return {
          state: "succeeded",
          receipt: validatedReceipt(result.receipt, item, context),
        };
      if (["rejected", "changed", "not_applied"].includes(result.status))
        return { state: result.status as ItemState, receipt: null };
    } catch {
      /* Transport and malformed receipt errors must never leak secrets. */
    }
    return { state: "unknown", receipt: null };
  }

  private async commit(
    ledger: BatchLedger,
    expected: number | null,
    next: BatchJournal,
  ) {
    try {
      await ledger.commit(
        this.owner,
        next.operationId,
        expected,
        freeze(clone(next)),
      );
    } catch {
      fail("ledger_unavailable");
    }
  }

  private validateJournal(
    value: BatchJournal,
    plan: ConnectionPlan,
    digest: string,
  ): BatchJournal {
    try {
      exact(value, [
        "schemaVersion",
        "userId",
        "runtimeId",
        "operationId",
        "planDigest",
        "revision",
        "items",
      ]);
      if (
        value.schemaVersion !== 1 ||
        value.userId !== this.owner.userId ||
        value.runtimeId !== this.owner.runtimeId ||
        value.operationId !== plan.operationId
      )
        fail("journal_invalid");
      integer(value.revision, 1);
      hash(value.planDigest);
      if (value.planDigest !== digest) fail("operation_conflict");
      if (
        !Array.isArray(value.items) ||
        value.items.length !== plan.items.length
      )
        fail("journal_invalid");
      const journal = clone(value);
      for (const [index, row] of journal.items.entries()) {
        const item = plan.items[index];
        exact(row, ["id", "kind", "intentDigest", "state", "receipt"]);
        if (
          row.id !== item.id ||
          row.kind !== item.kind ||
          row.intentDigest !== itemDigest(item) ||
          ![
            "pending",
            "in_flight",
            "succeeded",
            "unknown",
            "rejected",
            "changed",
            "not_applied",
            "dependency_blocked",
            "unavailable",
          ].includes(row.state)
        )
          fail("journal_invalid");
        if (row.state === "succeeded") {
          const context = this.context(plan, item, journal);
          if (!context || !row.receipt) fail("journal_invalid");
          row.receipt = validatedReceipt(row.receipt, item, context);
        } else if (row.receipt !== null) fail("journal_invalid");
      }
      return journal;
    } catch (error) {
      if (
        error instanceof Error &&
        error.message === "connection_batch_operation_conflict"
      )
        throw error;
      fail("journal_invalid");
    }
  }

  private result(
    journal: BatchJournal,
    mode: "preview" | "execute",
    cancelled: boolean,
  ): BatchResult {
    return clone({
      mode,
      operationId: journal.operationId,
      planDigest: journal.planDigest,
      state:
        mode === "preview"
          ? "preview"
          : journal.items.every((item) => item.state === "succeeded")
            ? "completed"
            : "partial",
      recovery:
        mode === "preview" ? "none" : (this.ledger?.durability ?? "none"),
      cancelled,
      items: journal.items,
    });
  }
}

export function connectionPlanDigest(plan: ConnectionPlan): string {
  return createHash("sha256")
    .update(`one-memory:connection-batch:v1\n${canonical(checkedPlan(plan))}`)
    .digest("hex");
}
function itemDigest(item: ConnectionItem) {
  return createHash("sha256").update(canonical(item)).digest("hex");
}
function checkedPlan(input: ConnectionPlan): ConnectionPlan {
  let plan: ConnectionPlan;
  try {
    plan = clone(input);
  } catch {
    fail("invalid_input");
  }
  exact(plan, ["schemaVersion", "userId", "runtimeId", "operationId", "items"]);
  if (plan.schemaVersion !== 1) fail("invalid_input");
  identifier(plan.userId);
  identifier(plan.runtimeId);
  identifier(plan.operationId);
  if (
    !Array.isArray(plan.items) ||
    plan.items.length > 96 ||
    plan.items.length === 0
  )
    fail("invalid_input");
  const ids = new Set<string>(),
    targets = new Set<string>();
  for (const item of plan.items) {
    identifier(item.id);
    if (ids.has(item.id)) fail("invalid_input");
    if (item.kind === "install" || item.kind === "readGrant") {
      exact(item, [
        "id",
        "kind",
        "sources",
        "host",
        ...(item.kind === "install"
          ? ["previewFingerprint"]
          : [
              "allowedTools",
              "allowedScopes",
              ...(Object.hasOwn(item, "installItemId")
                ? ["installItemId"]
                : []),
            ]),
      ]);
      hostIdentity(item.host);
      if (!Array.isArray(item.sources) || item.sources.length > 32)
        fail("invalid_input");
      item.sources.forEach(sourceIdentity);
      if (
        new Set(item.sources.map((source) => source.sourceId)).size !==
        item.sources.length
      )
        fail("invalid_input");
      if (item.kind === "install") hash(item.previewFingerprint);
      else {
        stringSet(item.allowedTools, 5);
        stringSet(item.allowedScopes, 64);
        if (
          !item.allowedTools.every((tool) =>
            [
              "om_recall",
              "om_ask",
              "om_conversations",
              "om_matters",
              "om_diagnostic_trace",
            ].includes(tool),
          )
        )
          fail("invalid_input");
        for (const scope of item.allowedScopes) {
          if (
            !(
              scope === "all-apps" ||
              /^workspace:v1:[a-f0-9]{64}$/.test(scope) ||
              /^source:[a-z0-9][a-z0-9-]{0,127}$/.test(scope)
            )
          )
            fail("invalid_input");
          if (
            scope.startsWith("source:") &&
            !item.sources.some(
              (source) => scope === `source:${source.sourceId}`,
            )
          )
            fail("invalid_input");
        }
        if (item.installItemId !== undefined) {
          identifier(item.installItemId);
          const prior = plan.items.find(
            (candidate) => candidate.id === item.installItemId,
          );
          if (
            !ids.has(item.installItemId) ||
            prior?.kind !== "install" ||
            canonical(prior.host) !== canonical(item.host) ||
            canonical(prior.sources) !== canonical(item.sources)
          )
            fail("invalid_input");
        } else if (
          item.host.installationId === null ||
          plan.items.some(
            (candidate) =>
              candidate.kind === "install" &&
              candidate.host.hostId === item.host.hostId,
          )
        )
          fail("invalid_input");
      }
    } else fail("invalid_input");
    const target = `${item.kind}:${item.host.hostId}`;
    if (targets.has(target)) fail("invalid_input");
    ids.add(item.id);
    targets.add(target);
  }
  return freeze(plan);
}
function validatedReceipt(
  input: ItemReceipt,
  item: ConnectionItem,
  context: ItemContext,
): ItemReceipt {
  const value = clone(input);
  const base = [
    "userId",
    "runtimeId",
    "operationId",
    "itemId",
    "intentDigest",
    "kind",
  ];
  if (
    !value ||
    value.kind !== item.kind ||
    value.userId !== context.userId ||
    value.runtimeId !== context.runtimeId ||
    value.operationId !== context.operationId ||
    value.itemId !== context.itemId ||
    value.intentDigest !== context.intentDigest
  )
    fail("receipt_invalid");
  exact(value, [
    ...base,
    "host",
    ...(value.kind === "readGrant" ? ["allowedTools", "allowedScopes"] : []),
  ]);
  hostIdentity(value.host);
  if (
    !context.host ||
    value.host.hostId !== context.host.hostId ||
    value.host.layoutDigest !== context.host.layoutDigest ||
    !value.host.installationId ||
    !value.host.installationDigest
  )
    fail("receipt_invalid");
  if (value.kind === "install") {
    if (
      value.host.permissionRevision !== 1 ||
      value.host.installationId === context.host.installationId
    )
      fail("receipt_invalid");
  } else if (item.kind === "readGrant") {
    if (
      value.host.installationId !== context.host.installationId ||
      value.host.installationDigest !== context.host.installationDigest ||
      value.host.permissionRevision !== context.host.permissionRevision + 1 ||
      canonical(value.allowedTools) !== canonical(item.allowedTools) ||
      canonical(value.allowedScopes) !== canonical(item.allowedScopes)
    )
      fail("receipt_invalid");
  }
  return value;
}
function sourceIdentity(source: SourceIdentity) {
  exact(source, ["sourceId", "rootId", "rootPath", "grantRevision"]);
  identifier(source.sourceId);
  identifier(source.rootId);
  text(source.rootPath);
  integer(source.grantRevision, 1);
}
function hostIdentity(host: HostIdentity) {
  exact(host, [
    "hostId",
    "layoutDigest",
    "installationId",
    "permissionRevision",
    "installationDigest",
  ]);
  identifier(host.hostId);
  hash(host.layoutDigest);
  integer(host.permissionRevision, 0);
  if (host.installationId === null) {
    if (host.permissionRevision !== 0 || host.installationDigest !== null)
      fail("invalid_input");
  } else {
    identifier(host.installationId);
    hash(host.installationDigest);
    if (host.permissionRevision < 1) fail("invalid_input");
  }
}
function exact(value: unknown, keys: string[]) {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.keys(value).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(value, key))
  )
    fail("invalid_input");
}
function identifier(value: unknown) {
  if (
    typeof value !== "string" ||
    !/^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$/.test(value)
  )
    fail("invalid_input");
}
function text(value: unknown) {
  if (
    typeof value !== "string" ||
    value.length < 1 ||
    value.length > 4096 ||
    [...value].some(
      (character) =>
        character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127,
    )
  )
    fail("invalid_input");
}
function hash(value: unknown) {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value))
    fail("invalid_input");
}
function integer(value: unknown, minimum: number) {
  if (
    !Number.isSafeInteger(value) ||
    (value as number) < minimum ||
    (value as number) >= Number.MAX_SAFE_INTEGER
  )
    fail("invalid_input");
}
function stringSet(values: readonly string[], max: number) {
  if (
    !Array.isArray(values) ||
    values.length < 1 ||
    values.length > max ||
    new Set(values).size !== values.length
  )
    fail("invalid_input");
  values.forEach(text);
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object")
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`,
      )
      .join(",")}}`;
  return JSON.stringify(value);
}
function clone<T>(value: T): T {
  return structuredClone(value);
}
function freeze<T>(value: T): T {
  if (value && typeof value === "object") {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}
function fail(code: string): never {
  throw new Error(`connection_batch_${code}`);
}
