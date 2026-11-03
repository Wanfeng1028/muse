const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");
const {
  buildServiceObserver,
  parseArguments,
  SOURCE,
  DEFAULT_OUTPUT,
} = require("./build_service_observer.cjs");

test("fixed source and output, only optional output argument", () => {
  assert(
    SOURCE.endsWith("/packages/runtime-control/native/service-observer.m"),
  );
  assert(
    DEFAULT_OUTPUT.endsWith("/packages/runtime-control/dist/service-observer"),
  );
  assert.deepEqual(parseArguments([]), { output: DEFAULT_OUTPUT });
  assert.deepEqual(parseArguments(["--output", "/tmp/fixture/helper"]), {
    output: "/tmp/fixture/helper",
  });
  for (const argv of [
    ["--source", "/tmp/fake.m"],
    ["--output"],
    ["--output", "relative"],
    ["--status"],
    ["--output", "/tmp/a", "--output", "/tmp/b"],
  ])
    assert.throws(() => parseArguments(argv));
});

test("builds with fixed frameworks and never executes output", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "om-observer-build-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const output = path.join(root, "resources", "service-observer");
  const calls = [];
  await buildServiceObserver({
    output,
    platform: "darwin",
    arch: "arm64",
    run: async (command, args, options) => {
      calls.push({ command, args, options });
      await fs.writeFile(args[args.indexOf("-o") + 1], "fake compiled bytes", {
        mode: 0o755,
      });
    },
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].command, "/usr/bin/xcrun");
  assert(calls[0].args.includes(SOURCE));
  assert(calls[0].args.includes("-mmacosx-version-min=13.0"));
  assert(calls[0].args.includes("Foundation"));
  assert(calls[0].args.includes("ServiceManagement"));
  assert.equal(await fs.readFile(output, "utf8"), "fake compiled bytes");
  await assert.rejects(
    buildServiceObserver({
      output,
      platform: "darwin",
      arch: "arm64",
      run: () => {
        throw Error("must not run");
      },
    }),
  );
  assert.equal(await fs.readFile(output, "utf8"), "fake compiled bytes");
});

test("failed compilation leaves no published binary", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "om-observer-failure-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const output = path.join(root, "service-observer");
  await assert.rejects(
    buildServiceObserver({
      output,
      platform: "darwin",
      arch: "arm64",
      run: async () => {
        throw Error("compiler failed");
      },
    }),
  );
  assert.deepEqual(await fs.readdir(root), []);
});

test("rejects unsupported platform before compilation", async () => {
  await assert.rejects(
    buildServiceObserver({
      platform: "linux",
      run: () => {
        throw Error("must not run");
      },
    }),
    /unsupported/,
  );
});

test("native source admits only --status and fixes the legacy URL", async () => {
  const source = await fs.readFile(SOURCE, "utf8");
  assert(source.includes('strcmp(argv[1], "--status")'));
  assert(source.indexOf("argc != 2") < source.indexOf("NSHomeDirectory()"));
  assert(source.includes("com.tencent.onememory.runtime.plist"));
  assert(source.includes("statusForLegacyURL:"));
  assert(
    !/registerAndReturnError|unregisterAndReturnError|launchctl|--test|--fake/.test(
      source,
    ),
  );
  for (const [status, result] of [
    ["Enabled", "registered"],
    ["RequiresApproval", "requires_approval"],
    ["NotRegistered", "not_registered"],
    ["NotFound", "unknown"],
  ]) {
    assert(
      source.includes(
        `case SMAppServiceStatus${status}: eligibility = @"${result}"; break;`,
      ),
    );
  }
});

test("a competing output cannot be overwritten by publication", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "om-observer-race-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const output = path.join(root, "service-observer");
  await assert.rejects(
    buildServiceObserver({
      output,
      platform: "darwin",
      arch: "arm64",
      run: async (_command, args) => {
        await fs.writeFile(args[args.indexOf("-o") + 1], "our compiled bytes");
        await fs.writeFile(output, "competitor");
      },
    }),
    { code: "EEXIST" },
  );
  assert.equal(await fs.readFile(output, "utf8"), "competitor");
  assert.deepEqual(await fs.readdir(root), ["service-observer"]);
});

test("successful compiler exit without binary is not a successful build", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "om-observer-empty-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  await assert.rejects(
    buildServiceObserver({
      output: path.join(root, "service-observer"),
      platform: "darwin",
      arch: "arm64",
      run: async () => {},
    }),
  );
  assert.deepEqual(await fs.readdir(root), []);
});
