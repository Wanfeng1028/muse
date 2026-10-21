import { createHash, randomUUID } from "node:crypto";
import { constants } from "node:fs";
import { open, readdir } from "node:fs/promises";
import path from "node:path";
import type { SourceResponse, SourceSyncState } from "@one-memory/contracts";
import type { HostReadTool } from "@one-memory/host-bridge";
import type { RecallHostLayout } from "@one-memory/host-bridge/installer";
import {
  type AdapterResult,
  type BatchAdapters,
  type BatchOwner,
  type BatchResult,
  ConnectionBatch,
  type ConnectionItem,
  type ConnectionPlan,
  connectionPlanDigest,
  type HostIdentity,
  type Inspection,
  type ItemContext,
  type SourceIdentity,
} from "./connection-batch.js";
import { PersistentBatchLedger } from "./connection-batch-ledger.js";
import type {
  HostPermissions,
  RecallPermissionStatus,
} from "./host-permissions.js";

export interface ConnectionControllerTrusted {
  dataDir: string;
  stableOwner: BatchOwner;
  hostPermissions: Pick<
    HostPermissions,
    "getPermission" | "previewInstall" | "install" | "setPermission"
  >;
  /** Resolves a source ID to its reviewed host layout; null means unsupported. */
  resolveHostLayout(
    id: string,
  ): RecallHostLayout | null | Promise<RecallHostLayout | null>;
  getSources(): Promise<SourceResponse[]>;
  setSourceSync(
    source: SourceResponse,
    enabled: boolean,
  ): Promise<SourceSyncState>;
}
export interface ConnectionSelection {
  syncSourceIds: string[];
  hostSourceIds: string[];
}
export interface ConnectionControllerPreview {
  planId: string;
  operationId: string;
  digest: string;
  items: Array<{
    id: string;
    kind: ConnectionItem["kind"] | "sync";
    sourceIds: string[];
    hostId?: string;
    restoresRevoked: boolean;
    allowedTools?: readonly string[];
    allowedScopes?: readonly string[];
    action?: "unchanged" | "add-rights" | "grant";
    previousTools?: readonly string[];
    previousScopes?: readonly string[];
  }>;
}
type Cached = {
  plan: ConnectionPlan;
  preview: ConnectionControllerPreview;
  hostSources: Map<string, string>;
  noops: Array<Extract<ConnectionItem, { kind: "readGrant" }>>;
  syncSources: string[];
};

/** Control-plane adapter only. IPC authentication and stable owner derivation stay outside. */
export class ConnectionController {
  private readonly plans = new Map<string, Cached>();
  private readonly activePlans = new Map<string, number>();
  private readonly owner: BatchOwner;
  private constructor(
    private readonly trusted: ConnectionControllerTrusted,
    private readonly ledger: PersistentBatchLedger,
  ) {
    this.owner = Object.freeze({ ...trusted.stableOwner });
  }
  static async initialize(trusted: ConnectionControllerTrusted) {
    return new ConnectionController(
      trusted,
      await PersistentBatchLedger.initialize(
        trusted.dataDir,
        trusted.stableOwner,
      ),
    );
  }
  static async open(trusted: ConnectionControllerTrusted) {
    return new ConnectionController(
      trusted,
      await PersistentBatchLedger.open(trusted.dataDir, trusted.stableOwner),
    );
  }
  async preview(
    input: ConnectionSelection,
  ): Promise<ConnectionControllerPreview> {
    const selection = structuredClone(input);
    exact(selection, ["syncSourceIds", "hostSourceIds"]);
    ids(selection.syncSourceIds);
    ids(selection.hostSourceIds);
    if (!selection.syncSourceIds.length && !selection.hostSourceIds.length)
      fail("empty_selection");
    return this.ledger.exclusive(this.owner, async () => {
      await this.rejectUnknown();
      const sources = await this.trusted.getSources();
      const items: ConnectionItem[] = [];
      const summary: ConnectionControllerPreview["items"] = [];
      const hostSources = new Map<string, string>();
      const noops: Cached["noops"] = [];
      const selectedSources = [
        ...new Set([...selection.syncSourceIds, ...selection.hostSourceIds]),
      ].map((id) => sourceIdentity(requiredSource(sources, id)));
      for (const id of selection.syncSourceIds) {
        const source = requiredSource(sources, id);
        requireSync(source);
        summary.push({
          id: `sync:${id}`,
          kind: "sync",
          sourceIds: [id],
          restoresRevoked: false,
        });
      }
      for (const id of selection.hostSourceIds) {
        const source = requiredSource(sources, id);
        if (
          source.capabilities.installer !== "implemented" ||
          source.capabilities.recall !== "implemented"
        )
          fail("unsupported_host");
        const layout = await this.layout(id);
        if (hostSources.has(layout.hostId)) fail("duplicate_host");
        hostSources.set(layout.hostId, id);
        const permission =
          await this.trusted.hostPermissions.getPermission(layout);
        const host = hostIdentity(layout, permission);
        const restoresRevoked = permission.state === "revoked";
        let installItemId: string | undefined;
        if (
          permission.state === "not-installed" ||
          permission.state === "relink-required"
        ) {
          const install =
            await this.trusted.hostPermissions.previewInstall(layout);
          if (install.hostId !== layout.hostId || !isHash(install.fingerprint))
            fail("preview_invalid");
          installItemId = `install:${layout.hostId}`;
          items.push({
            id: installItemId,
            kind: "install",
            sources: selectedSources,
            host,
            previewFingerprint: install.fingerprint,
          });
          summary.push({
            id: installItemId,
            kind: "install",
            sourceIds: selectedSources.map((s) => s.sourceId),
            hostId: layout.hostId,
            restoresRevoked,
          });
        }
        const requiredTools: HostReadTool[] = [
          "om_recall",
          "om_conversations",
          "om_diagnostic_trace",
        ];
        const requiredScopes = [
          "all-apps",
          ...selectedSources.map((s) => `source:${s.sourceId}`),
        ];
        const previous =
          permission.receipt?.status === "approved" ? permission.receipt : null;
        const allowedTools = [
          ...new Set([...(previous?.allowedTools ?? []), ...requiredTools]),
        ];
        const allowedScopes = [
          ...new Set([...(previous?.allowedScopes ?? []), ...requiredScopes]),
        ];
        const frozenSources = [...selectedSources];
        try {
          for (const scope of previous?.allowedScopes ?? []) {
            if (
              scope.startsWith("source:") &&
              !frozenSources.some((s) => scope === `source:${s.sourceId}`)
            )
              frozenSources.push(
                sourceIdentity(requiredSource(sources, scope.slice(7))),
              );
          }
        } catch {
          fail("needs_attention");
        }
        const unchanged =
          permission.state === "approved" &&
          !!previous &&
          requiredTools.every((tool) => previous.allowedTools.includes(tool)) &&
          requiredScopes.every((scope) =>
            previous.allowedScopes.includes(scope),
          );
        const grant: Extract<ConnectionItem, { kind: "readGrant" }> = {
          id: `grant:${layout.hostId}`,
          kind: "readGrant",
          sources: frozenSources,
          host,
          ...(installItemId ? { installItemId } : {}),
          allowedTools,
          allowedScopes,
        };
        // Validate retained scopes with the existing plan validator, without changing it.
        try {
          connectionPlanDigest({
            schemaVersion: 1,
            ...this.owner,
            operationId: "validation",
            items: [...items, grant],
          });
        } catch {
          if (previous) fail("needs_attention");
          throw Error("connection_controller_preview_invalid");
        }
        if (unchanged) noops.push(grant);
        else items.push(grant);
        summary.push({
          id: `grant:${layout.hostId}`,
          kind: "readGrant",
          sourceIds: frozenSources.map((s) => s.sourceId),
          hostId: layout.hostId,
          restoresRevoked,
          allowedTools,
          allowedScopes,
          action: unchanged ? "unchanged" : previous ? "add-rights" : "grant",
          previousTools: previous?.allowedTools ?? [],
          previousScopes: previous?.allowedScopes ?? [],
        });
      }
      const plan: ConnectionPlan = {
        schemaVersion: 1,
        ...this.owner,
        operationId: randomUUID(),
        items,
      };
      const preview = {
        planId: randomUUID(),
        operationId: plan.operationId,
        digest: hash({ plan, noops }),
        items: summary,
      };
      if (this.plans.size >= 64) {
        const oldest = [...this.plans.keys()].find(
          (id) => !this.activePlans.has(id),
        );
        if (oldest === undefined) fail("plan_capacity");
        this.plans.delete(oldest);
      }
      this.plans.set(preview.planId, {
        plan: structuredClone(plan),
        preview: structuredClone(preview),
        hostSources,
        noops: structuredClone(noops),
        syncSources: [...selection.syncSourceIds],
      });
      return preview;
    });
  }
  async execute(
    input: { planId: string; digest: string; userConfirmed: true },
    signal?: AbortSignal,
  ) {
    exact(input, ["planId", "digest", "userConfirmed"]);
    if (input.userConfirmed !== true) fail("confirmation_required");
    const cached = this.plans.get(input.planId);
    if (!cached) fail("plan_missing");
    if (input.digest !== cached.preview.digest) fail("plan_changed");
    this.activePlans.set(
      input.planId,
      (this.activePlans.get(input.planId) ?? 0) + 1,
    );
    try {
      return await this.executeCached(cached, input.digest, signal);
    } finally {
      const remaining = (this.activePlans.get(input.planId) ?? 1) - 1;
      if (remaining) this.activePlans.set(input.planId, remaining);
      else this.activePlans.delete(input.planId);
    }
  }
  private async executeCached(
    cached: Cached,
    digest: string,
    signal?: AbortSignal,
  ) {
    const skipped: Array<{
      id: string;
      state: "unchanged" | "changed" | "unavailable";
    }> = [];
    const applySync = async () => {
      const results: Array<{
        id: string;
        kind: "sync";
        intentDigest: string;
        state: "succeeded" | "unknown";
        receipt: null;
      }> = [];
      for (const sourceId of cached.syncSources) {
        try {
          const before = requiredSource(
            await this.trusted.getSources(),
            sourceId,
          );
          requireSync(before);
          if (!before.sync_enabled) {
            try {
              await this.trusted.setSourceSync(before, true);
            } catch {
              // A lost response is resolved by the authoritative read below.
            }
          }
          const after = requiredSource(
            await this.trusted.getSources(),
            sourceId,
          );
          results.push({
            id: `sync:${sourceId}`,
            kind: "sync",
            intentDigest: hash({ sourceId, enabled: true }),
            state: after.sync_enabled ? "succeeded" : "unknown",
            receipt: null,
          });
        } catch {
          results.push({
            id: `sync:${sourceId}`,
            kind: "sync",
            intentDigest: hash({ sourceId, enabled: true }),
            state: "unknown",
            receipt: null,
          });
        }
      }
      return results;
    };
    const checkNoops = async () => {
      for (const item of cached.noops) {
        try {
          const current = await this.adapters(cached).inspect(item, {
            ...this.owner,
            operationId: cached.plan.operationId,
            itemId: item.id,
            intentDigest: hash(item),
            host: item.host,
          });
          skipped.push({
            id: item.id,
            state:
              current.status === "ready" &&
              canonical(current.sources) === canonical(item.sources) &&
              canonical(current.host) === canonical(item.host)
                ? "unchanged"
                : "changed",
          });
        } catch {
          skipped.push({ id: item.id, state: "unavailable" });
        }
      }
    };
    if (!cached.plan.items.length) {
      return this.ledger.exclusive(this.owner, async () => {
        await this.rejectUnknown(cached.plan.operationId);
        await checkNoops();
        const sync = signal?.aborted ? [] : await applySync();
        return {
          mode: "execute" as const,
          operationId: cached.plan.operationId,
          planDigest: digest,
          state:
            skipped.every((item) => item.state === "unchanged") &&
            sync.every((item) => item.state === "succeeded") &&
            !signal?.aborted
              ? ("completed" as const)
              : ("partial" as const),
          recovery: "none" as const,
          cancelled: signal?.aborted === true,
          items: sync,
          skipped,
        };
      });
    }
    const batch = new ConnectionBatch(this.owner, this.adapters(cached), {
      durability: "persistent",
      load: (owner, id) => this.ledger.load(owner, id),
      commit: (owner, id, expected, next) =>
        this.ledger.commit(owner, id, expected, next),
      exclusive: (owner, operation) =>
        this.ledger.exclusive(owner, async () => {
          await this.rejectUnknown(cached.plan.operationId);
          const result = await operation();
          await checkNoops();
          return result;
        }),
    });
    const result: BatchResult = await batch.run(cached.plan, {
      mode: "execute",
      userConfirmed: true,
      planDigest: connectionPlanDigest(cached.plan),
      signal,
    });
    const sync = signal?.aborted ? [] : await applySync();
    return {
      ...result,
      planDigest: digest,
      state:
        skipped.some((item) => item.state !== "unchanged") ||
        sync.some((item) => item.state !== "succeeded")
          ? ("partial" as const)
          : result.state,
      items: [...result.items, ...sync],
      skipped,
    };
  }
  receipt(operationId: string) {
    return this.ledger.load(this.owner, operationId);
  }

  private adapters(cached: Cached): BatchAdapters {
    const inspect = async (
      item: Readonly<ConnectionItem>,
    ): Promise<Inspection> => {
      const all = await this.trusted.getSources();
      let sources: SourceResponse[];
      try {
        sources = item.sources.map((s) => requiredSource(all, s.sourceId));
      } catch {
        return { status: "denied" };
      }
      const id = cached.hostSources.get(item.host.hostId);
      if (!id) fail("unsupported_host");
      const layout = await this.layout(id);
      const permission =
        await this.trusted.hostPermissions.getPermission(layout);
      if (
        item.kind === "readGrant" &&
        !["approved", "install-only", "revoked"].includes(permission.state)
      )
        return { status: "denied" };
      const host = hostIdentity(layout, permission);
      const preview =
        item.kind === "install"
          ? await this.trusted.hostPermissions.previewInstall(layout)
          : null;
      return {
        status: "ready",
        sources: sources.map(sourceIdentity),
        host,
        previewFingerprint: preview?.fingerprint ?? null,
      };
    };
    const apply = async (
      item: Readonly<ConnectionItem>,
      context: Readonly<ItemContext>,
    ): Promise<AdapterResult> => {
      // Repeat the frozen-state check directly before dispatching the guarded native method.
      const current = await inspect(item);
      if (current.status !== "ready")
        return { status: current.status === "denied" ? "rejected" : "unknown" };
      if (canonical(current.sources) !== canonical(item.sources))
        return { status: "changed" };
      const { host: _host, ...binding } = context;
      if (canonical(current.host) !== canonical(context.host))
        return { status: "changed" };
      const sourceId = cached.hostSources.get(item.host.hostId);
      if (!sourceId) fail("unsupported_host");
      const layout = await this.layout(sourceId);
      if (hash(layout) !== item.host.layoutDigest) return { status: "changed" };
      if (item.kind === "install") {
        if (current.previewFingerprint !== item.previewFingerprint)
          return { status: "changed" };
        const result = await this.trusted.hostPermissions
          .install(layout, item.previewFingerprint)
          .catch(async () => {
            await this.sourcesUnchanged(item.sources);
            fail("effect_unknown");
          });
        if (!(await this.sourcesUnchanged(item.sources)))
          return { status: "unknown" };
        if (!result.installed || result.hostId !== layout.hostId)
          return { status: "unknown" };
        return {
          status: "succeeded",
          receipt: {
            ...binding,
            kind: "install",
            host: hostIdentity(layout, result.permission),
          },
        };
      }
      if (!context.host?.installationId) return { status: "changed" };
      const result = await this.trusted.hostPermissions
        .setPermission(layout, {
          installationId: context.host.installationId,
          expectedRevision: context.host.permissionRevision,
          allowedTools: item.allowedTools,
          allowedScopes: item.allowedScopes,
          userConfirmed: true,
        })
        .catch(async () => {
          await this.sourcesUnchanged(item.sources);
          fail("effect_unknown");
        });
      if (!(await this.sourcesUnchanged(item.sources)))
        return { status: "unknown" };
      if (result.state !== "approved" || !result.receipt)
        return { status: "unknown" };
      return {
        status: "succeeded",
        receipt: {
          ...binding,
          kind: "readGrant",
          host: hostIdentity(layout, result),
          allowedTools: result.receipt.allowedTools,
          allowedScopes: result.receipt.allowedScopes,
        },
      };
    };
    const adapter = {
      apply,
      reconcile: async (): Promise<AdapterResult> => ({ status: "unknown" }),
    };
    return { inspect, install: adapter, readGrant: adapter };
  }
  private async layout(id: string) {
    const layout = await this.trusted.resolveHostLayout(id);
    if (!layout || layout.hostId === "openclaw") fail("unsupported_host");
    return structuredClone(layout);
  }
  private async sourcesUnchanged(identities: readonly SourceIdentity[]) {
    try {
      const sources = await this.trusted.getSources();
      return (
        canonical(
          identities.map((identity) =>
            sourceIdentity(requiredSource(sources, identity.sourceId)),
          ),
        ) === canonical(identities)
      );
    } catch {
      return false;
    }
  }
  private async rejectUnknown(except?: string) {
    // Read only bounded metadata, then let the ledger revalidate every owner/file/journal.
    await this.ledger.load(this.owner, "controller-validation");
    const directory = path.join(this.trusted.dataDir, "connection-batches");
    const entries = await readdir(directory);
    if (entries.length > 1024) fail("recovery_required");
    for (const name of entries) {
      if (!/^[a-f0-9]{64}\.json$/.test(name)) continue;
      const handle = await open(
        path.join(directory, name),
        constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
      );
      let operationId: unknown;
      try {
        const stat = await handle.stat();
        if (
          !stat.isFile() ||
          stat.nlink !== 1 ||
          stat.size > 512 * 1024 ||
          (stat.mode & 0o777) !== 0o600 ||
          stat.uid !== process.getuid?.()
        )
          fail("recovery_required");
        const buffer = Buffer.alloc(512 * 1024 + 1);
        const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
        if (bytesRead !== stat.size) fail("recovery_required");
        operationId = JSON.parse(
          buffer.subarray(0, bytesRead).toString("utf8"),
        ).operationId;
      } finally {
        await handle.close();
      }
      if (typeof operationId !== "string") fail("recovery_required");
      const expected = hash(
        [this.owner.userId, this.owner.runtimeId, operationId],
        false,
      );
      if (name !== `${expected}.json`) fail("recovery_required");
      const journal = await this.ledger.load(this.owner, operationId);
      if (!journal) fail("recovery_required");
      if (
        operationId !== except &&
        journal.items.some(
          (item) => item.state === "unknown" || item.state === "in_flight",
        )
      )
        fail("recovery_required");
    }
  }
}
function requiredSource(sources: SourceResponse[], id: string) {
  const found = sources.filter((s) => s.source_id === id);
  const source = found[0];
  if (
    found.length !== 1 ||
    !source.authorized ||
    !source.available ||
    source.location_state !== "found" ||
    !source.root_id ||
    source.root_id !== source.candidate_root_id ||
    !source.candidate_path ||
    !Number.isSafeInteger(source.grant_revision) ||
    (source.grant_revision ?? 0) < 1
  )
    fail("source_unavailable");
  return source;
}
function requireSync(source: SourceResponse) {
  if (
    source.capabilities.live_sync !== "implemented" ||
    typeof source.sync_enabled !== "boolean"
  )
    fail("unsupported_sync");
}
function sourceIdentity(source: SourceResponse): SourceIdentity {
  return {
    sourceId: source.source_id,
    rootId: source.root_id as string,
    rootPath: source.candidate_path,
    grantRevision: source.grant_revision as number,
  };
}
function hostIdentity(
  layout: RecallHostLayout,
  status: RecallPermissionStatus,
): HostIdentity {
  if (
    status.hostId !== layout.hostId ||
    status.state === "unsupported" ||
    status.state === "unavailable" ||
    status.reason === "installation_incomplete"
  )
    fail("host_unavailable");
  const receipt = status.receipt;
  if (receipt && receipt.hostId !== layout.hostId) fail("host_unavailable");
  return {
    hostId: layout.hostId,
    layoutDigest: hash(layout),
    installationId: receipt?.installationId ?? null,
    permissionRevision: receipt?.revision ?? 0,
    // Nonsecret binding identity only; getPermission verifies managed files live.
    installationDigest: receipt ? hash([layout, receipt.installationId]) : null,
  };
}
function ids(value: unknown) {
  if (
    !Array.isArray(value) ||
    value.length > 32 ||
    new Set(value).size !== value.length ||
    value.some(
      (id) => typeof id !== "string" || !/^[a-z0-9][a-z0-9-]{0,127}$/.test(id),
    )
  )
    fail("invalid_selection");
}
function exact(value: unknown, keys: string[]) {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.keys(value).length !== keys.length ||
    keys.some((k) => !Object.hasOwn(value, k))
  )
    fail("invalid_input");
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object")
    return `{${Object.keys(value)
      .sort()
      .map(
        (k) =>
          `${JSON.stringify(k)}:${canonical((value as Record<string, unknown>)[k])}`,
      )
      .join(",")}}`;
  return JSON.stringify(value);
}
function hash(value: unknown, canonicalize = true) {
  return createHash("sha256")
    .update(canonicalize ? canonical(value) : JSON.stringify(value))
    .digest("hex");
}
function isHash(value: unknown) {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}
function fail(code: string): never {
  throw Error(`connection_controller_${code}`);
}
