import type { GovernedMemory } from "@one-memory/contracts";

/** How many live memories carry each topic tag, most used first.
 *
 * Deleted and superseded memories do not count. A tag is only established by
 * memories that are still standing; letting a deleted one hold a tag up
 * would keep a topic alive that nothing is about any more.
 */
export function tagCounts(memories: GovernedMemory[]): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const memory of memories) {
    if (memory.status !== "confirmed") continue;
    for (const tag of memory.tags) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }
  return [...counts].sort(
    (left, right) => right[1] - left[1] || left[0].localeCompare(right[0]),
  );
}

/** Tags that exist on exactly one memory.
 *
 * This is the measurement, not a verdict. HY seeds its extract prompt with
 * the tags already in the library so the model reuses them, but nothing
 * forbids a new one, and the products that left that unconstrained ended up
 * with `Goals` beside `goal`. A tag used once is either a topic that has only
 * come up once — perfectly fine — or the first half of that split. Which one
 * it is cannot be told apart by counting, so this counts and says so, and no
 * threshold here decides anything on the reader's behalf.
 */
export function singletonTags(memories: GovernedMemory[]): string[] {
  return tagCounts(memories)
    .filter(([, count]) => count === 1)
    .map(([tag]) => tag);
}
