const assert = require("node:assert/strict");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");
const { options, verdict, check } = require("./verify_login_autorun.cjs");

test("a phase name and a receipt are both required", () => {
  assert.equal(options([]), null);
  assert.equal(options(["arm"]), null);
  assert.equal(options(["nonsense", "--receipt", "/tmp/r.json"]), null);
  assert.equal(options(["arm", "--receipt"]), null);
  assert.equal(options(["arm", "--receipt", "--data-dir"]), null);
});

test("the data directory defaults to the one the service would use", () => {
  const parsed = options(["after-login", "--receipt", "/tmp/r.json"]);
  assert.equal(parsed.phase, "after-login");
  assert.equal(parsed.receipt, "/tmp/r.json");
  assert.equal(parsed.dataDir, path.join(os.homedir(), ".one-memory"));
});

test("an explicit data directory and runtime entry win", () => {
  const parsed = options([
    "arm",
    "--receipt",
    "r.json",
    "--data-dir",
    "/tmp/sandbox",
    "--runtime",
    "/opt/one-memory/runtime/runtime.cjs",
  ]);
  assert.equal(parsed.dataDir, "/tmp/sandbox");
  assert.equal(parsed.runtime, "/opt/one-memory/runtime/runtime.cjs");
  assert.equal(parsed.receipt, path.resolve("r.json"));
});

test("only every check passing is a pass", () => {
  assert.equal(verdict([check("a", "pass", "")]), 0);
  assert.equal(verdict([check("a", "pass", ""), check("b", "manual", "")]), 0);
  assert.equal(verdict([check("a", "pass", ""), check("b", "fail", "")]), 4);
  assert.equal(
    verdict([check("a", "pass", ""), check("b", "not_implemented", "")]),
    5,
  );
  assert.equal(verdict([check("a", "unknown", "")]), 2);
});

test("a failure outranks an unimplemented step, which outranks not knowing", () => {
  assert.equal(
    verdict([
      check("a", "unknown", ""),
      check("b", "not_implemented", ""),
      check("c", "fail", ""),
    ]),
    4,
  );
  assert.equal(
    verdict([check("a", "unknown", ""), check("b", "not_implemented", "")]),
    5,
  );
});
