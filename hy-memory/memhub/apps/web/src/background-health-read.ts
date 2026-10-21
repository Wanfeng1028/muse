type Health = Awaited<
  ReturnType<
    NonNullable<NonNullable<Window["oneMemory"]>["getBackgroundHealth"]>
  >
>;
export type BackgroundSnapshot = Pick<Health, "state" | "core" | "broker">;

/** Only the trusted Desktop bridge observes Runtime ownership; Core health alone cannot. */
export async function readBackgroundHealth(): Promise<
  BackgroundSnapshot | "no-bridge"
> {
  const bridge = window.oneMemory;
  if (typeof bridge?.getBackgroundHealth !== "function") return "no-bridge";
  const value: unknown = await bridge.getBackgroundHealth();
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  const result = value as Record<string, unknown>;
  if (
    !member(result.state, [
      "healthy",
      "stopped",
      "degraded",
      "untrusted",
      "unknown",
    ]) ||
    !member(result.core, [
      "running",
      "stopped",
      "unhealthy",
      "untrusted",
      "unknown",
    ]) ||
    !member(result.broker, [
      "running",
      "stopped",
      "unhealthy",
      "untrusted",
      "not_checked",
    ])
  )
    fail();
  const { state, core, broker } = result;
  const consistent =
    state === "healthy"
      ? core === "running" &&
        broker === "running" &&
        result.code === "background_verified" &&
        typeof result.instanceId === "string" &&
        /^[a-zA-Z0-9_.:-]{1,128}$/.test(result.instanceId)
      : state === "stopped"
        ? core === "stopped" && broker === "not_checked"
        : state === "degraded"
          ? (core === "unhealthy" && broker === "not_checked") ||
            (core === "running" &&
              (broker === "stopped" || broker === "unhealthy"))
          : state === "untrusted"
            ? (core === "untrusted" && broker === "not_checked") ||
              (core === "running" && broker === "untrusted")
            : broker === "not_checked";
  if (!consistent) fail();
  return { state, core, broker } as BackgroundSnapshot;
}

function member(value: unknown, values: readonly string[]): value is string {
  return typeof value === "string" && values.includes(value);
}
function fail(): never {
  throw Error("background_health_invalid_response");
}
