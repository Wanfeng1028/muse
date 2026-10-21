const { readFileSync } = require("node:fs");
const path = require("node:path");

function repositoryRoot(from = __dirname) {
  return path.resolve(from, "..");
}

function positiveSafeInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new Error(
      `${label} must be a positive safe integer: ${String(value)}`,
    );
  }
  return value;
}

function protocolRange(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object with integer min/max`);
  }
  const min = positiveSafeInteger(value.min, `${label}.min`);
  const max = positiveSafeInteger(value.max, `${label}.max`);
  if (max < min) {
    throw new Error(`${label}.max must be greater than or equal to min`);
  }
  return Object.freeze({ min, max });
}

function protocolIncludes(range, version) {
  return version >= range.min && version <= range.max;
}

function readReleaseContract(root = repositoryRoot()) {
  const packagePath = path.join(root, "package.json");
  const pkg = JSON.parse(readFileSync(packagePath, "utf8"));
  const release = pkg.release;
  if (
    release === null ||
    typeof release !== "object" ||
    Array.isArray(release)
  ) {
    throw new Error("root package release contract is missing or invalid");
  }

  const contract = {
    runtimeManifestSchema: positiveSafeInteger(
      release.runtime_manifest_schema,
      "release.runtime_manifest_schema",
    ),
    cliProtocol: positiveSafeInteger(
      release.cli_protocol,
      "release.cli_protocol",
    ),
    cliSupportedRuntimeProtocol: protocolRange(
      release.cli_supported_runtime_protocol,
      "release.cli_supported_runtime_protocol",
    ),
    runtimeProtocol: positiveSafeInteger(
      release.runtime_protocol,
      "release.runtime_protocol",
    ),
    runtimeSupportedCliProtocol: protocolRange(
      release.runtime_supported_cli_protocol,
      "release.runtime_supported_cli_protocol",
    ),
  };

  if (
    !protocolIncludes(
      contract.cliSupportedRuntimeProtocol,
      contract.runtimeProtocol,
    )
  ) {
    throw new Error(
      "release CLI compatibility range does not include the runtime protocol",
    );
  }
  if (
    !protocolIncludes(
      contract.runtimeSupportedCliProtocol,
      contract.cliProtocol,
    )
  ) {
    throw new Error(
      "release runtime compatibility range does not include the CLI protocol",
    );
  }
  return Object.freeze(contract);
}

module.exports = {
  protocolIncludes,
  protocolRange,
  readReleaseContract,
  repositoryRoot,
};
