import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";

import { verifyReleaseVersion } from "./verify-release-version.mjs";

const require = createRequire(import.meta.url);
const { pythonPackageVersion } = require("./release-version.cjs");
const rootPackage = JSON.parse(
  await readFile(new URL("../package.json", import.meta.url), "utf8"),
);
const currentVersion = rootPackage.version;
const currentBuildNumber = rootPackage.release.build_number;
const currentPythonVersion = pythonPackageVersion(currentVersion);

test("development accepts the synchronized source version", async () => {
  const receipt = await verifyReleaseVersion(["--channel", "development"], {});
  assert.equal(receipt.version, currentVersion);
  assert.equal(receipt.build_number, currentBuildNumber);
  for (const [file, version] of Object.entries(receipt.files)) {
    assert.equal(
      version,
      file.startsWith("apps/core/") ? currentPythonVersion : currentVersion,
    );
  }
});

test("stable accepts the exact tag and build number", async () => {
  const receipt = await verifyReleaseVersion(
    [
      "--channel",
      "stable",
      "--tag",
      `v${currentVersion}`,
      "--build-number",
      String(currentBuildNumber),
    ],
    {},
  );
  assert.equal(receipt.version, currentVersion);
  assert.equal(receipt.build_number, currentBuildNumber);
});

test("prerelease rejects a stable source version", async () => {
  await assert.rejects(
    verifyReleaseVersion(
      [
        "--channel",
        "prerelease",
        "--tag",
        `v${currentVersion}`,
        "--build-number",
        String(currentBuildNumber),
      ],
      {},
    ),
    /prerelease channel requires a SemVer prerelease/,
  );
});

test("an environment override cannot drift from the source version", async () => {
  await assert.rejects(
    verifyReleaseVersion(["--channel", "development"], {
      ONE_MEMORY_VERSION: "1.2.3",
    }),
    /does not match root|release version mismatch/,
  );
});

test("a build number override cannot drift from the release contract", async () => {
  await assert.rejects(
    verifyReleaseVersion(["--channel", "development"], {
      ONE_MEMORY_BUILD_NUMBER: String(currentBuildNumber + 1),
    }),
    /release build number mismatch/,
  );
});

test("the verifier source checks every release-bearing manifest", async () => {
  const source = await readFile(
    new URL("./verify-release-version.mjs", import.meta.url),
    "utf8",
  );
  for (const file of [
    "apps/cli/package.json",
    "apps/desktop/package.json",
    "packages/runtime-control/package.json",
    "apps/core/pyproject.toml",
  ]) {
    assert.match(source, new RegExp(file.replaceAll("/", "\\/")));
  }
});
