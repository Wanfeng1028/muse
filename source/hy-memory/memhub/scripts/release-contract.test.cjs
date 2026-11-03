const assert = require("node:assert/strict");
const { mkdtemp, rm, writeFile } = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  protocolIncludes,
  protocolRange,
  readReleaseContract,
} = require("./release-contract.cjs");

const VALID_RELEASE = {
  runtime_manifest_schema: 1,
  cli_protocol: 2,
  cli_supported_runtime_protocol: { min: 1, max: 3 },
  runtime_protocol: 3,
  runtime_supported_cli_protocol: { min: 2, max: 4 },
};

async function fixture(t, release = VALID_RELEASE) {
  const root = await mkdtemp(
    path.join(os.tmpdir(), "memhub-release-contract-"),
  );
  t.after(async () => {
    await rm(root, { recursive: true, force: true });
  });
  await writeFile(
    path.join(root, "package.json"),
    `${JSON.stringify({ release })}\n`,
  );
  return root;
}

test("reads and freezes the root release protocol contract", async (t) => {
  const contract = readReleaseContract(await fixture(t));
  assert.deepEqual(contract, {
    runtimeManifestSchema: 1,
    cliProtocol: 2,
    cliSupportedRuntimeProtocol: { min: 1, max: 3 },
    runtimeProtocol: 3,
    runtimeSupportedCliProtocol: { min: 2, max: 4 },
  });
  assert.equal(Object.isFrozen(contract), true);
  assert.equal(Object.isFrozen(contract.cliSupportedRuntimeProtocol), true);
  assert.equal(Object.isFrozen(contract.runtimeSupportedCliProtocol), true);
});

test("reads the repository's canonical release contract", () => {
  assert.deepEqual(readReleaseContract(), {
    runtimeManifestSchema: 1,
    cliProtocol: 1,
    cliSupportedRuntimeProtocol: { min: 1, max: 1 },
    runtimeProtocol: 1,
    runtimeSupportedCliProtocol: { min: 1, max: 1 },
  });
});

test("rejects missing and malformed protocol values", async (t) => {
  for (const [field, value] of [
    ["runtime_manifest_schema", 0],
    ["cli_protocol", 1.5],
    ["runtime_protocol", "1"],
    ["cli_supported_runtime_protocol", { min: 2, max: 1 }],
    ["runtime_supported_cli_protocol", null],
  ]) {
    const root = await fixture(t, { ...VALID_RELEASE, [field]: value });
    assert.throws(() => readReleaseContract(root), /release\.|compatibility/);
  }
});

test("rejects mutually incompatible CLI and runtime protocols", async (t) => {
  const cliRejectsRuntime = await fixture(t, {
    ...VALID_RELEASE,
    cli_supported_runtime_protocol: { min: 1, max: 2 },
  });
  assert.throws(
    () => readReleaseContract(cliRejectsRuntime),
    /CLI compatibility range/,
  );

  const runtimeRejectsCli = await fixture(t, {
    ...VALID_RELEASE,
    runtime_supported_cli_protocol: { min: 3, max: 4 },
  });
  assert.throws(
    () => readReleaseContract(runtimeRejectsCli),
    /runtime compatibility range/,
  );
});

test("protocol helpers reject malformed ranges and test inclusion", () => {
  const range = protocolRange({ min: 2, max: 4 }, "fixture");
  assert.equal(protocolIncludes(range, 1), false);
  assert.equal(protocolIncludes(range, 2), true);
  assert.equal(protocolIncludes(range, 4), true);
  assert.equal(protocolIncludes(range, 5), false);
  assert.throws(() => protocolRange({ min: 0, max: 1 }, "fixture"));
  assert.throws(() => protocolRange([], "fixture"));
});
