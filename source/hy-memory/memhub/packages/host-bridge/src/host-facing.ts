/** What a host's model is allowed to see of a recall result.
 *
 * D100, narrowed to the part that is not in dispute: evidence UUIDs.
 *
 * A returned `evidence_ids` array is how a model came to recite
 * `c866a180-…` to the person. It means nothing outside our own store, and
 * anything that needs to trace a memory back to its source reads the
 * diagnostics, not the tool result.
 *
 * Deliberately left alone here: the result's own state fields. Collapsing
 * them to four sentences is the larger half of D100 and it contradicts
 * existing tests — notably the ones asserting a truncated result must not be
 * relabelled complete. That half waits for the wording to be settled, rather
 * than being done here and quietly weakening those guards.
 */

/** Drop the fields that exist only for our own tracing.
 *
 * Only `evidence_ids` today. Written as a list so the next one has an
 * obvious place, and so the rest of the receipt survives untouched — the
 * caller's own assertions, and the tests that guard them, keep working.
 */
const INTERNAL_HIT_FIELDS = ["evidence_ids"] as const;

export function recallForHost(receipt: unknown): unknown {
  const source = (receipt ?? {}) as Record<string, unknown>;
  if (!Array.isArray(source.hits)) return receipt;
  const sourceHits = source.hits;
  const hits = sourceHits.map((hit) => {
    if (hit === null || typeof hit !== "object") return hit;
    const item = hit as Record<string, unknown>;
    if (!INTERNAL_HIT_FIELDS.some((field) => field in item)) return hit;
    const stripped = { ...item };
    for (const field of INTERNAL_HIT_FIELDS) delete stripped[field];
    return stripped;
  });
  // Nothing to strip means nothing to rebuild: the caller keeps its own
  // object, so identity-based assertions elsewhere still hold.
  if (hits.every((hit, index) => hit === sourceHits[index])) return receipt;
  return { ...source, hits };
}
