const { randomUUID } = require("node:crypto");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

/** Point an hourly package at its own install root, data dir and label.
 *
 * The App decides `isolatedHourly` from two environment variables that release
 * tooling is expected to inject (`apps/desktop/src/isolated-runtime.ts`). A
 * plain Finder double-click carries no environment, so without this the App
 * falls through to the daily install root and tries to claim the canonical
 * `com.tencent.onememory.runtime` label -- which collides with a real install
 * already on the machine. `LSEnvironment` is macOS's supported way to give a
 * bundle its own environment at launch, so bake the isolation in at pack time.
 *
 * The instance UUID is generated per build on purpose: it is the package's
 * identity, and a fixed one would make two copies of the same package look like
 * the same instance.
 *
 * Only internal hourly packages opt in (`ONE_MEMORY_HOURLY_PACKAGE=1` at pack
 * time). Preview and production builds must keep installing into the real
 * managed root and owning the canonical label, so for them this is a no-op.
 */
function writeHourlyIsolationEnvironment(plist, context) {
  if (process.env.ONE_MEMORY_HOURLY_PACKAGE !== "1") return;
  const version = context.packager?.appInfo?.version ?? "0.0.0";
  const packageId =
    process.env.ONE_MEMORY_HOURLY_PACKAGE_ID ??
    `One-Memory-H08-${version}-c7-isolated`;
  const instanceId = randomUUID();
  // Diagnostic identity for the four-level chain. The shipped dist launcher
  // stamps these, but a Finder-launched App spawns the Runtime itself and never
  // runs that launcher, so its legs carry no build/package/round and
  // `c6-ui-trace-report` reports `unknown:no-identity`. Bake the same values
  // here. `round` comes from the builder when it supplies one; never invented.
  const round =
    typeof process.env.ONE_MEMORY_ROUND === "string" &&
    process.env.ONE_MEMORY_ROUND.trim() !== ""
      ? process.env.ONE_MEMORY_ROUND.trim()
      : undefined;
  // `LSEnvironment` is a dict; `Add` fails if it already exists, so clear first.
  try {
    execFileSync("/usr/libexec/PlistBuddy", [
      "-c",
      "Delete :LSEnvironment",
      plist,
    ]);
  } catch {
    // Absent on a fresh pack; that is the normal case.
  }
  execFileSync("/usr/libexec/PlistBuddy", [
    "-c",
    "Add :LSEnvironment dict",
    "-c",
    `Add :LSEnvironment:ONE_MEMORY_HOURLY_INSTANCE_ID string ${instanceId}`,
    "-c",
    `Add :LSEnvironment:ONE_MEMORY_HOURLY_PACKAGE_ID string ${packageId}`,
    "-c",
    `Add :LSEnvironment:ONE_MEMORY_BUILD_ID string ${packageId}`,
    "-c",
    `Add :LSEnvironment:ONE_MEMORY_PACKAGE_ID string ${packageId}`,
    ...(round === undefined
      ? []
      : ["-c", `Add :LSEnvironment:ONE_MEMORY_ROUND string ${round}`]),
    plist,
  ]);
}

/** Stamp the monotonic install authority for every macOS package profile.
 *
 * Production App bundles must carry this even though they intentionally have
 * no hourly identity: otherwise Finder launch presents build 0 to the shared
 * installer and a valid installed current is rejected as a downgrade. Only
 * this key is replaced, preserving unrelated LSEnvironment entries.
 */
function releaseVersion(context) {
  const supplied = process.env.ONE_MEMORY_VERSION?.trim();
  const packaged = context.packager?.appInfo?.version?.trim();
  const version = supplied || packaged;
  return typeof version === "string" &&
    /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/.test(
      version,
    )
    ? version
    : undefined;
}

function writeReleaseIdentity(plist, context) {
  const version = releaseVersion(context);
  const buildNumber =
    typeof process.env.ONE_MEMORY_BUILD_NUMBER === "string" &&
    /^\d+$/.test(process.env.ONE_MEMORY_BUILD_NUMBER.trim())
      ? process.env.ONE_MEMORY_BUILD_NUMBER.trim()
      : undefined;
  try {
    execFileSync("/usr/libexec/PlistBuddy", [
      "-c",
      "Add :LSEnvironment dict",
      plist,
    ]);
  } catch {
    // Electron already creates this dictionary for production settings.
  }
  for (const key of ["ONE_MEMORY_VERSION", "ONE_MEMORY_BUILD_NUMBER"]) {
    try {
      execFileSync("/usr/libexec/PlistBuddy", [
        "-c",
        `Delete :LSEnvironment:${key}`,
        plist,
      ]);
    } catch {
      // Absent on a fresh package.
    }
  }
  if (version !== undefined) {
    execFileSync("/usr/libexec/PlistBuddy", [
      "-c",
      `Add :LSEnvironment:ONE_MEMORY_VERSION string ${version}`,
      plist,
    ]);
    execFileSync("/usr/libexec/PlistBuddy", [
      "-c",
      `Set :CFBundleShortVersionString ${version}`,
      plist,
    ]);
  }
  if (buildNumber !== undefined) {
    execFileSync("/usr/libexec/PlistBuddy", [
      "-c",
      `Add :LSEnvironment:ONE_MEMORY_BUILD_NUMBER string ${buildNumber}`,
      plist,
    ]);
    execFileSync("/usr/libexec/PlistBuddy", [
      "-c",
      `Set :CFBundleVersion ${buildNumber}`,
      plist,
    ]);
  }
  const commit = process.env.ONE_MEMORY_COMMIT?.trim();
  if (commit !== undefined && /^[0-9a-f]{40}$/.test(commit)) {
    execFileSync("/usr/libexec/PlistBuddy", [
      "-c",
      `Add :LSEnvironment:ONE_MEMORY_COMMIT string ${commit}`,
      plist,
    ]);
  }
}

const UNUSED_PERMISSION_KEYS = [
  ["NS", "BluetoothAlwaysUsageDescription"].join(""),
  ["NS", "BluetoothPeripheralUsageDescription"].join(""),
  ["NS", "CameraUsageDescription"].join(""),
  ["NS", "MicrophoneUsageDescription"].join(""),
  ["NS", "AudioCaptureUsageDescription"].join(""),
];

module.exports = async function removeUnusedMacPermissions(context) {
  if (context.electronPlatformName !== "darwin") return;

  const appBundle = path.join(
    context.appOutDir,
    `${context.packager.appInfo.productFilename}.app`,
  );
  const plist = path.join(appBundle, "Contents", "Info.plist");
  // Do this before codesigning so the seal covers the final Info.plist.
  writeHourlyIsolationEnvironment(plist, context);
  writeReleaseIdentity(plist, context);
  // The Runtime service (`SMAppService.mainAppService`, see login-item.ts) is
  // the only startup owner. This hook used to also write a bundled
  // `Contents/Library/LaunchAgents/one-memory-background.plist` with
  // `RunAtLoad`, which launchd never scans, so it registered nothing while
  // still shipping a second-looking startup definition. Do not reintroduce it.
  for (const key of UNUSED_PERMISSION_KEYS) {
    try {
      execFileSync("/usr/libexec/PlistBuddy", ["-c", `Delete :${key}`, plist]);
    } catch {
      // Electron versions do not all provide the same default usage strings.
    }
  }
  // Public packages are signed by electron-builder after this hook has made
  // its final plist changes. Ad-hoc signing here would replace or conflict
  // with the Developer ID identity and make notarization evidence dishonest.
  if (process.env.MEMHUB_MAC_SIGNING_MODE !== "public") {
    execFileSync("/usr/bin/codesign", [
      "--force",
      "--deep",
      "--sign",
      "-",
      appBundle,
    ]);
  }
};
