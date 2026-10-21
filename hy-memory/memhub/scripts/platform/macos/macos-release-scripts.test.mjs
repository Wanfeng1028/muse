import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  detachMountedDmgVolumes,
  parseDmgMounts,
} from "./notarize-macos-release.mjs";

const build = await readFile(
  new URL("./build-macos-release.mjs", import.meta.url),
  "utf8",
);
const notarize = await readFile(
  new URL("./notarize-macos-release.mjs", import.meta.url),
  "utf8",
);

test("macOS release build is native, same-origin and contract-driven", () => {
  for (const marker of [
    "process.arch !== options.arch",
    "macos_min_version",
    'appUpdate !== "manual"',
    "MEMHUB_PUBLIC_BUNDLE_ID",
    "CSC_NAME",
    "CSC_KEYCHAIN",
    "electronBuilderIdentity",
    "Developer ID Application:",
    "-c.mac.identity=",
    "-c.forceCodeSigning=true",
    "MACOSX_DEPLOYMENT_TARGET",
    'run("sbom", "pnpm", ["run", "sbom"]',
    "build_runtime_distribution.cjs",
    "sameOriginRuntimeChecks",
    "synchronizeSignedAppRuntime",
    "synchronizeRuntimeBackToApp",
    "signStandaloneRuntimeMachOs",
    "treeCodeBundles",
    "resignPackagedApp",
    "rewriteDistributionManifest",
    "verifyRuntimeMachOSignatures",
    "entitlements.mac.inherit.plist",
    "readAppIdentity",
    "canonicalMacosVersion",
    "macos_release_minimum_system_version_invalid",
    "macos_release_app_identity_mismatch",
    "codesignTeamIdentifier",
    "macos_release_team_id_mismatch",
    "codesign-verify",
  ])
    assert.ok(build.includes(marker), marker);
  assert.match(build, /minimumSystemVersion !== "13\.0"/);
  assert.match(build, /const info = await lstat\(target\)/);
  assert.match(build, /!info\.isFile\(\) \|\| info\.isSymbolicLink\(\)/);
  assert.match(build, /const missing = declared\.filter/);
  assert.match(build, /_CodeSignature/);
  assert.doesNotMatch(
    build,
    /relative !== "bin\/node" && !relative\.startsWith\("lib\/"\)/,
  );
  assert.match(build, /result\.error\?\.message \|\| result\.stderr/);
});

test("macOS public packaging notarizes and staples App and DMG", () => {
  for (const marker of [
    "APPLE_NOTARY_KEY_PATH",
    "CSC_KEYCHAIN",
    "notarytool",
    "stapler",
    "hdiutil",
    "detachMountedDmgVolumes",
    "parseDmgMounts",
    "publicGateReport",
    "public_gate_dmg_gatekeeper_accepts",
    "public_gate_dmg_codesign_verify",
    "public_gate_dmg_notarization_ticket",
    "macos_public_gate_failed",
  ])
    assert.ok(notarize.includes(marker), marker);
  assert.match(notarize, /document\.status !== "Accepted"/);
});

test("parses only MemHub disk-image mounts", () => {
  const mounts = parseDmgMounts(
    [
      "/dev/disk4\tGUID_partition_scheme\t",
      "/dev/disk4s1\t48465300-0000-11AA-AA11-00306543ECAC\t/Volumes/MemHub",
      "/dev/disk5s1\t48465300-0000-11AA-AA11-00306543ECAC\t/Volumes/MemHub 1",
      "/dev/disk6s1\t48465300-0000-11AA-AA11-00306543ECAC\t/Volumes/MemHub Backup",
      "/dev/disk7s1\t48465300-0000-11AA-AA11-00306543ECAC\t/Volumes/Other",
    ].join("\n"),
    "MemHub",
  );
  assert.deepEqual(mounts, [
    { device: "/dev/disk4s1", mountPoint: "/Volumes/MemHub" },
    { device: "/dev/disk5s1", mountPoint: "/Volumes/MemHub 1" },
  ]);
});

test("detaches stale MemHub images and verifies they are gone", () => {
  const calls = [];
  let infoReads = 0;
  const fakeRun = (command, args) => {
    calls.push([command, ...args]);
    if (args[0] === "info") {
      infoReads += 1;
      return {
        code: 0,
        stdout:
          infoReads === 1
            ? "/dev/disk4s1\tApple_HFS\t/Volumes/MemHub\n/dev/disk5s1\tApple_HFS\t/Volumes/MemHub 1\n"
            : "",
        stderr: "",
      };
    }
    return { code: 0, stdout: "", stderr: "" };
  };

  assert.equal(detachMountedDmgVolumes("MemHub", true, fakeRun).length, 2);
  assert.deepEqual(calls, [
    ["hdiutil", "info"],
    ["hdiutil", "detach", "/Volumes/MemHub", "-force"],
    ["hdiutil", "detach", "/Volumes/MemHub 1", "-force"],
    ["hdiutil", "info"],
  ]);
});
