const { readFileSync } = require("node:fs");
const path = require("node:path");

const SEMVER =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;

function repositoryRoot(from = __dirname) {
  return path.resolve(from, "..");
}

function assertSemver(value, label = "release version") {
  if (typeof value !== "string" || !SEMVER.test(value)) {
    throw new Error(`${label} is not valid SemVer: ${String(value)}`);
  }
  return value;
}

function readReleaseVersion(root = repositoryRoot()) {
  const pkg = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8"));
  return assertSemver(pkg.version, "root package version");
}

function readReleaseBuildNumber(root = repositoryRoot()) {
  const pkg = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8"));
  const value = pkg.release?.build_number;
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`root release build number is invalid: ${String(value)}`);
  }
  return value;
}

function resolveBuildVersion(
  environment = process.env,
  root = repositoryRoot(),
) {
  const canonical = readReleaseVersion(root);
  const supplied = environment.ONE_MEMORY_VERSION?.trim();
  if (supplied === undefined || supplied === "") return canonical;
  assertSemver(supplied, "ONE_MEMORY_VERSION");
  if (supplied !== canonical) {
    throw new Error(
      `release version mismatch: root=${canonical} ONE_MEMORY_VERSION=${supplied}`,
    );
  }
  return canonical;
}

function resolveBuildNumber(
  environment = process.env,
  root = repositoryRoot(),
) {
  const canonical = readReleaseBuildNumber(root);
  const supplied = environment.ONE_MEMORY_BUILD_NUMBER?.trim();
  if (supplied === undefined || supplied === "") return canonical;
  if (!/^\d+$/.test(supplied) || !Number.isSafeInteger(Number(supplied))) {
    throw new Error(`invalid ONE_MEMORY_BUILD_NUMBER: ${supplied}`);
  }
  const value = Number(supplied);
  if (value !== canonical) {
    throw new Error(
      `release build number mismatch: root=${canonical} ONE_MEMORY_BUILD_NUMBER=${value}`,
    );
  }
  return canonical;
}

function isPrerelease(version) {
  assertSemver(version);
  return version.split("+", 1)[0].includes("-");
}

/** Map the product SemVer to Python's PEP 440 package metadata.
 *
 * Product/runtime identity always stays the original SemVer. Python only uses
 * this value while resolving the editable Core package. Standard alpha/beta/rc
 * identifiers map to their PEP 440 equivalents; an internal train such as
 * `0.1.0-internal.1` maps deterministically to `0.1.0.dev1+internal`.
 */
function pythonPackageVersion(version) {
  assertSemver(version);
  const [withoutBuild, build = ""] = version.split("+", 2);
  const dash = withoutBuild.indexOf("-");
  const base = dash === -1 ? withoutBuild : withoutBuild.slice(0, dash);
  const prerelease = dash === -1 ? "" : withoutBuild.slice(dash + 1);
  let pep = base;
  let local = "";
  if (prerelease) {
    const parts = prerelease.split(".");
    const label = parts[0].toLowerCase();
    const number =
      parts.length === 2 && /^\d+$/.test(parts[1]) ? parts[1] : null;
    if (number !== null && ["a", "alpha"].includes(label))
      pep = `${base}a${number}`;
    else if (number !== null && ["b", "beta"].includes(label))
      pep = `${base}b${number}`;
    else if (number !== null && label === "rc") pep = `${base}rc${number}`;
    else {
      const trailing = parts.at(-1);
      const dev =
        trailing !== undefined && /^\d+$/.test(trailing) ? trailing : "0";
      pep = `${base}.dev${dev}`;
      local =
        parts.slice(0, trailing === dev ? -1 : undefined).join(".") ||
        "prerelease";
    }
  }
  const localParts = [local, build]
    .filter(Boolean)
    .join(".")
    .toLowerCase()
    .replace(/[^a-z0-9.]+/g, ".")
    .replace(/^\.+|\.+$/g, "");
  return localParts ? `${pep}+${localParts}` : pep;
}

module.exports = {
  SEMVER,
  assertSemver,
  isPrerelease,
  pythonPackageVersion,
  readReleaseBuildNumber,
  readReleaseVersion,
  repositoryRoot,
  resolveBuildNumber,
  resolveBuildVersion,
};
