/** The idempotent source-sync request shared by every client surface. */
import type { SourceResponse } from "@one-memory/contracts";

export interface SourceSyncRequest {
  path: string;
  body: {
    enabled: boolean;
  };
}

export class SourceSyncInputError extends Error {}

/**
 * Build the final-state request shared by every client.
 */
export function buildSourceSyncRequest(
  source: Pick<SourceResponse, "source_id">,
  enabled: boolean,
): SourceSyncRequest {
  if (!source.source_id?.trim())
    throw new SourceSyncInputError("source_id_required");
  return {
    path: `/api/v1/sources/${encodeURIComponent(source.source_id)}/sync-permission`,
    body: { enabled },
  };
}

/** Core validates the live grant; clients only need an authorized source. */
export function hasSourceSyncTarget(source: SourceResponse): boolean {
  return (
    source.authorized === true &&
    source.capabilities.live_sync === "implemented"
  );
}
