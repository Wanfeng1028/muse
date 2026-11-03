const SEMVER =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;

/** A side-effect-free packaged-App probe used by the public signing gate.
 *
 * It runs before Desktop lifecycle startup, so checking that the signed App
 * can load Electron's Framework never creates a window, starts Runtime, writes
 * user data or registers a service.
 */
export function desktopVersionOutput(
  arguments_: readonly string[],
  embeddedVersion: unknown,
): string | null {
  const tokens = arguments_.slice(1);
  if (tokens.length !== 1 || tokens[0] !== "--memhub-version") {
    return null;
  }
  const version =
    typeof embeddedVersion === "string" && SEMVER.test(embeddedVersion.trim())
      ? embeddedVersion.trim()
      : "development";
  return `MemHub ${version}\n`;
}
