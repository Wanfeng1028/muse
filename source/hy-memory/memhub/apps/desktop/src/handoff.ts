/** Opening another AI app with the memories already in its input box.
 *
 * The renderer never supplies a URL. It names a host and passes text, and the
 * link is assembled here against the table below. A renderer that could hand
 * `shell.openExternal` an arbitrary string would be handing it every scheme
 * the machine has a handler for, which is a much larger thing than "start a
 * chat somewhere else".
 */

/** Only Cursor's prefill handler has been inspected and exercised in its
 * native input box. Other hosts keep the complete clipboard fallback. */
const BUILDERS: Record<string, (prompt: string, home: string) => string> = {
  cursor: (prompt) =>
    `cursor://anysphere.cursor-deeplink/prompt?text=${encodeURIComponent(prompt)}&mode=ask`,
};

/** Hosts One Memory can reach, but not with the text already typed.
 *
 * Kept apart from `BUILDERS` so the interface can say so instead of opening
 * an empty window and letting the user work out that nothing came along.
 */
export const HANDOFF_WITHOUT_PROMPT = new Set([
  "workbuddy",
  "claude-code",
  "codex",
  "opencode",
]);

export function canHandOff(hostId: string): boolean {
  return hostId in BUILDERS;
}

/** Null when this host cannot be started with a prompt, so the caller has to
 * decide what to do about it rather than opening something empty. */
export function handoffUrl(
  hostId: string,
  prompt: string,
  home: string,
): string | null {
  const build = BUILDERS[hostId];
  if (!build) return null;
  if (!prompt.trim()) return null;
  const url = build(prompt, home);
  return url.length <= 7000 ? url : null;
}
