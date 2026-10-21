/** Model-profile operations shared with the CLI.
 *
 * The one non-obvious case is delete. The CLI
 * (`core-client.ts:297-323`) treats HTTP 404 and 409 as *refusals that are
 * properties of the profile* — unknown id, still-active profile — and returns
 * `false`; anything else non-2xx is a transport failure and throws. The
 * renderer previously had no equivalent and turned every non-2xx into a thrown
 * error, so a confirmed "it is already gone / it is active" was indistinguishable
 * from "we don't know whether it was deleted". That distinction changes what a
 * person should do next, so it is preserved here.
 *
 * Dependency-free so it can move into a shared package once C0 picks a spot.
 */

/** The three outcomes a profile delete can have. */
export type ModelRemoveOutcome =
  | { state: "removed" }
  | {
      state: "refused";
      code: "model_profile_not_found" | "active_model_profile";
    }
  | { state: "unknown"; code: string };

/** Map an HTTP status (and Core's stable detail when present) to the outcome.
 *
 * Core returns 404 `model_profile_not_found` and 409 `active_model_profile`;
 * the body `detail` is preferred so a future rename of the status code cannot
 * silently change meaning, with the status used as the fallback.
 */
export function classifyModelRemove(
  status: number,
  detail?: unknown,
): ModelRemoveOutcome {
  const code = typeof detail === "string" ? detail : null;
  // Core's stable `detail` is the authority; the status is only a fallback so
  // that a future status change cannot silently reclassify a known code.
  if (code === "model_profile_not_found" || (code === null && status === 404))
    return { state: "refused", code: "model_profile_not_found" };
  if (code === "active_model_profile" || (code === null && status === 409))
    return { state: "refused", code: "active_model_profile" };
  if (status >= 200 && status < 300) return { state: "removed" };
  return { state: "unknown", code: code ?? `http_${status}` };
}

/** Activate is a plain write: Core's 404/422 are rejections, not unknowns. */
export function classifyModelActivate(
  status: number,
  detail?: unknown,
):
  | { state: "activated" }
  | { state: "rejected"; code: string }
  | { state: "unknown"; code: string } {
  const code = typeof detail === "string" ? detail : null;
  if (status >= 200 && status < 300) return { state: "activated" };
  if (status >= 400 && status < 500)
    return { state: "rejected", code: code ?? `http_${status}` };
  return { state: "unknown", code: code ?? `http_${status}` };
}
