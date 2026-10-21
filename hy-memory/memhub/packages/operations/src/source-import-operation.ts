/** Source-import operation: the exact `POST /sources/connect` body.
 *
 * This is the operation the objective names as the step-2 acceptance example:
 * the same import started from the UI and from the CLI must reach the kernel
 * with identical parameters. The CLI builds it in
 * `headless-flows.ts:194-202` (and `batch-import-flow.ts:120-141`); the
 * renderer previously built a similar but not identical object inline in
 * `api.ts`. Keeping it here makes the field set and the coalescing rules
 * structural instead of two hand-maintained literals.
 *
 * Dependency-free on purpose so it can move into a shared package once C0
 * chooses the landing spot.
 */

export class SourceImportInputError extends Error {}

export interface SourceImportInput {
  sourceIds: readonly string[];
  /** Root identity per source. Always present, like the CLI's plan body. */
  sourceRoots?: Record<string, string>;
  sourceCandidateRevisions?: Record<string, number>;
  confirmEnvironmentOverrides?: boolean;
  fullRescan?: boolean;
  onboarding?: boolean;
  enableSync?: boolean;
  requestId?: string;
  importUploadId?: string;
}

/**
 * Build the connect body. Every field the CLI always sends is always present
 * here; the two purely-Web additions (`import_upload_id`) are added only when
 * a caller actually has one, which is how the CLI treats an optional upload.
 */
export function buildSourceImportRequest(
  input: SourceImportInput,
  newRequestId: () => string = () => crypto.randomUUID(),
): { path: "/api/v1/sources/connect"; body: Record<string, unknown> } {
  if (!Array.isArray(input.sourceIds) || input.sourceIds.length < 1)
    throw new SourceImportInputError("source_ids_required");
  if (input.sourceIds.length > 32)
    throw new SourceImportInputError("source_ids_too_many");
  const requestId = input.requestId ?? newRequestId();
  if (
    typeof requestId !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      requestId,
    )
  )
    throw new SourceImportInputError("request_id_invalid");
  const sourceIds = [...input.sourceIds];
  const roots = { ...(input.sourceRoots ?? {}) };
  const revisions = { ...(input.sourceCandidateRevisions ?? {}) };
  if (
    Object.keys(roots).some((id) => !sourceIds.includes(id)) ||
    Object.keys(revisions).some((id) => !sourceIds.includes(id))
  )
    throw new SourceImportInputError("source_metadata_unknown_source");
  return {
    path: "/api/v1/sources/connect",
    body: {
      source_ids: sourceIds,
      source_roots: roots,
      source_candidate_revisions: revisions,
      confirm_environment_overrides: input.confirmEnvironmentOverrides ?? false,
      full_rescan: input.fullRescan ?? false,
      onboarding: input.onboarding ?? false,
      enable_sync: input.enableSync ?? false,
      request_id: requestId,
      ...(input.importUploadId === undefined
        ? {}
        : { import_upload_id: input.importUploadId }),
    },
  };
}
