import {
  buildSourceSyncRequest,
  hasSourceSyncTarget,
  SourceSyncInputError,
} from "@one-memory/operations";
import type { CoreReader } from "./core-client.js";
import type { CoreOperations } from "./core-operations.js";
import { validateSources } from "./core-responses.js";
import { PRODUCT } from "./version.js";

export type SyncAction = "pause" | "resume";

export type SourceSyncFlowDocument =
  | {
      schema_version: 1;
      product: string;
      state: "committed";
      source_id: string;
      sync_enabled: boolean;
    }
  | {
      schema_version: 1;
      product: string;
      state: "invalid" | "rejected" | "unknown";
      code: string;
    };

function failure(
  state: "invalid" | "rejected" | "unknown",
  code: string,
): SourceSyncFlowDocument {
  return { schema_version: 1, product: PRODUCT, state, code };
}

async function current(
  reader: CoreReader,
  sourceId: string,
): Promise<
  | {
      state: "ok";
      source: NonNullable<ReturnType<typeof validateSources>>[number];
    }
  | { state: "invalid" | "unknown"; code: string }
> {
  const outcome = await reader<unknown>("/api/v1/sources");
  if (outcome.state !== "ok") {
    return {
      state: outcome.state === "unavailable" ? "unknown" : "invalid",
      code: outcome.code ?? "core_read_failed",
    };
  }
  const sources = validateSources(outcome.data);
  if (!sources) return { state: "invalid", code: "sources_response_invalid" };
  const source = sources.find((item) => item.source_id === sourceId);
  return source
    ? { state: "ok", source }
    : { state: "invalid", code: "source_not_found" };
}

export async function setSourceSync(
  reader: CoreReader,
  operations: CoreOperations,
  request: { sourceId: string; action: SyncAction },
): Promise<SourceSyncFlowDocument> {
  if (!/^[A-Za-z0-9][\w.-]{0,127}$/.test(request.sourceId))
    return failure("invalid", "invalid_source_id");
  const enabled = request.action === "resume";
  const before = await current(reader, request.sourceId);
  if (before.state !== "ok") return failure(before.state, before.code);
  if (!before.source.authorized)
    return failure("rejected", "source_not_authorized");
  if (!hasSourceSyncTarget(before.source))
    return failure("rejected", "live_sync_unavailable");
  if (before.source.sync_enabled === enabled) {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "committed",
      source_id: request.sourceId,
      sync_enabled: enabled,
    };
  }

  let wire: ReturnType<typeof buildSourceSyncRequest>;
  try {
    wire = buildSourceSyncRequest(before.source, enabled);
  } catch (error) {
    if (error instanceof SourceSyncInputError)
      return failure("invalid", error.message);
    throw error;
  }
  const outcome = await operations.post<unknown>(wire.path, wire.body);
  if (outcome.state === "committed") {
    const value = outcome.data as Record<string, unknown>;
    if (
      value?.source_id !== request.sourceId ||
      value?.sync_enabled !== enabled
    )
      return failure("unknown", "sync_response_invalid");
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "committed",
      source_id: request.sourceId,
      sync_enabled: enabled,
    };
  }
  if (outcome.state === "rejected") {
    return failure(
      outcome.http_status === 409 ? "rejected" : "unknown",
      outcome.code,
    );
  }

  const observed = await current(reader, request.sourceId);
  if (observed.state === "ok" && observed.source.sync_enabled === enabled) {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "committed",
      source_id: request.sourceId,
      sync_enabled: enabled,
    };
  }
  return failure("unknown", "sync_outcome_unknown");
}

export function sourceSyncExitCode(document: SourceSyncFlowDocument): number {
  if (document.state === "committed") return 0;
  if (document.state === "invalid") return 2;
  return 1;
}

export function renderSourceSyncText(document: SourceSyncFlowDocument): string {
  if (document.state === "committed") {
    return `${
      document.sync_enabled ? "已恢复" : "已暂停"
    }来源 ${document.source_id} 的持续同步。\n`;
  }
  return `未变更：${document.code}\n`;
}
