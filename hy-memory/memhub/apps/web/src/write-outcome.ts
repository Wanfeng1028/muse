/** Did Core definitely refuse this write, or might it still have landed?
 *
 * A 4xx (except 408) means the request was answered and refused. A 5xx, a
 * timeout, or a transport failure with no response means the outcome is
 * *unknown*: the write may have been applied before the answer was lost.
 *
 * This distinction has to be made once and shared, because the failure mode it
 * guards against is subtle: the code catches a thrown error, closes the trace
 * with `failed`, and shows the user copy that says the result is *unconfirmed*.
 * The log then contradicts the screen, and the log is what a later reader
 * trusts. Worse, calling an unknown outcome "failed" invites a retry that can
 * double-apply a write.
 */

/** True only when Core answered with a definite refusal. */
export function isDefiniteRefusal(reason: unknown): boolean {
  // A wrapper that already classified the transport error wins: by the time a
  // caller sees it the original axios error (and its status) is gone.
  if (reason && typeof reason === "object" && "definiteRefusal" in reason)
    return (reason as { definiteRefusal?: unknown }).definiteRefusal === true;
  if (!reason || typeof reason !== "object" || !("response" in reason))
    return false;
  const response = (reason as { response?: unknown }).response;
  if (!response || typeof response !== "object" || !("status" in response))
    return false;
  const status = (response as { status?: unknown }).status;
  return (
    typeof status === "number" &&
    status >= 400 &&
    status < 500 &&
    status !== 408
  );
}

/** The trace outcome that matches whether the write was refused or is unknown. */
export function writeTraceStatus(reason: unknown): "failed" | "unknown" {
  return isDefiniteRefusal(reason) ? "failed" : "unknown";
}
