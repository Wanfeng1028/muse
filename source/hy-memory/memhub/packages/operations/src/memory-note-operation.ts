/** Memory-note write contract: the body shape and the receipt check.
 *
 * The CLI validates a note receipt in `ui-write-flows-extended.ts:321-340`
 * before accepting it — the evidence id must be a UUID and the state must be
 * one of the known states. The renderer previously stored whatever Core
 * returned straight into component state (`MemoryNoteComposer.remember`), so a
 * malformed 200 would be rendered as a real note. This mirrors the CLI's check.
 *
 * The save body is fixed too: Core takes exactly `request_id`, `text`, `scope`;
 * the CLI hard-codes `scope: "all-apps"` and so does the UI. Keeping it here
 * means both surfaces send the same three fields.
 *
 * Dependency-free (contracts types only) so it can move into a shared package.
 */
import type { MemoryNoteInput, MemoryNoteReceipt } from "@one-memory/contracts";

export class MemoryNoteInputError extends Error {}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const NOTE_STATES = [
  "waiting_for_model",
  "waiting_for_permission",
  "pending",
  "running",
  "failed",
  "ready",
  "no_memories",
] as const;

export interface MemoryNoteSaveRequest {
  path: "/api/v1/memory-notes";
  body: { request_id: string; text: string; scope: "all-apps" };
}

/** The exact three-field body Core accepts; scope is fixed, not caller-supplied. */
export function buildMemoryNoteSaveRequest(
  note: MemoryNoteInput,
): MemoryNoteSaveRequest {
  if (typeof note.request_id !== "string" || !UUID.test(note.request_id))
    throw new MemoryNoteInputError("request_id_invalid");
  if (typeof note.text !== "string" || note.text.trim().length === 0)
    throw new MemoryNoteInputError("text_required");
  return {
    path: "/api/v1/memory-notes",
    body: { request_id: note.request_id, text: note.text, scope: "all-apps" },
  };
}

/**
 * Validate a note receipt before it becomes UI state.
 *
 * Returns null for a malformed body; callers must treat that as an unknown
 * result rather than a saved note.
 */
export function parseMemoryNoteReceipt(
  value: unknown,
): MemoryNoteReceipt | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const receipt = value as Record<string, unknown>;
  if (
    typeof receipt.evidence_id !== "string" ||
    !UUID.test(receipt.evidence_id) ||
    typeof receipt.state !== "string" ||
    !(NOTE_STATES as readonly string[]).includes(receipt.state) ||
    receipt.scope !== "all-apps"
  )
    return null;
  if (
    !Array.isArray(receipt.memory_ids) ||
    receipt.memory_ids.some((id) => typeof id !== "string")
  )
    return null;
  return value as MemoryNoteReceipt;
}
