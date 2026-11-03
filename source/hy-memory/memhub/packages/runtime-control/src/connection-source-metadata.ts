import type { SourceResponse } from "@one-memory/contracts";

/** Validate Core source metadata and project only the existing connection contract. */
export function connectionSourceMetadata(value: unknown): SourceResponse[] {
  if (!Array.isArray(value) || value.length > 256) fail();
  const seen = new Set<string>();
  return value.map((input) => {
    const s = object(input);
    sourceId(s.source_id);
    if (seen.has(s.source_id as string)) fail();
    seen.add(s.source_id as string);
    for (const name of ["display_name", "candidate_path"]) text(s[name], 4096);
    for (const name of ["authorized", "available"])
      if (typeof s[name] !== "boolean") fail();
    if (s.detected !== null && typeof s.detected !== "boolean") fail();
    for (const name of ["grant_revision", "candidate_revision"])
      if (s[name] !== undefined) integer(s[name], 0);
    for (const name of ["imported_messages", "imported_conversations"])
      integer(s[name], 0);
    if (typeof s.sync_enabled !== "boolean") fail();
    for (const name of ["root_id", "candidate_root_id", "root_label"])
      if (s[name] != null) text(s[name], 4096);
    member(s.candidate_kind, [
      "default",
      "environment_override",
      "user_selected",
    ]);
    if (s.location_state !== undefined)
      member(s.location_state, [
        "found",
        "not_found",
        "inaccessible",
        "invalid",
      ]);
    member(s.sync_completeness, [
      "full_dynamic",
      "additions_only",
      "one_time_snapshot",
    ]);
    const caps = object(s.capabilities);
    exact(caps, [
      "historical_import",
      "incremental_import",
      "live_sync",
      "recall",
      "installer",
      "verification",
    ]);
    for (const key of [
      "historical_import",
      "incremental_import",
      "live_sync",
      "recall",
      "installer",
    ])
      member(caps[key], ["implemented", "not_implemented"]);
    member(caps.verification, ["fixture_only", "real_replayed"]);
    if (!Array.isArray(s.storage_kinds) || s.storage_kinds.length > 32) fail();
    s.storage_kinds.forEach((k) => {
      text(k, 64);
    });
    // Keep the Desktop projection: candidate_revision is validated, not exposed here.
    return {
      source_id: s.source_id,
      display_name: s.display_name,
      candidate_path: s.candidate_path,
      candidate_kind: s.candidate_kind,
      available: s.available,
      authorized: s.authorized,
      detected: s.detected,
      root_label: s.root_label ?? null,
      root_id: s.root_id,
      candidate_root_id: s.candidate_root_id,
      grant_revision: s.grant_revision,
      sync_enabled: s.sync_enabled,
      location_state: s.location_state,
      imported_messages: s.imported_messages,
      imported_conversations: s.imported_conversations,
      storage_kinds: s.storage_kinds,
      capabilities: caps,
      sync_completeness: s.sync_completeness,
    } as unknown as SourceResponse;
  });
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  return value as Record<string, unknown>;
}
function exact(value: Record<string, unknown>, keys: string[]) {
  if (
    Object.keys(value).length !== keys.length ||
    keys.some((k) => !Object.hasOwn(value, k))
  )
    fail();
}
function sourceId(value: unknown) {
  if (typeof value !== "string" || !/^[a-z0-9][a-z0-9-]{0,127}$/.test(value))
    fail();
}
function integer(value: unknown, min: number) {
  if (!Number.isSafeInteger(value) || (value as number) < min) fail();
}
function member(value: unknown, choices: readonly string[]) {
  if (typeof value !== "string" || !choices.includes(value)) fail();
}
function text(value: unknown, max: number) {
  if (
    typeof value !== "string" ||
    value.length > max ||
    [...value].some(
      (character) =>
        character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127,
    )
  )
    fail();
}
function fail(): never {
  throw Error("connection_setup_invalid_core_metadata");
}
