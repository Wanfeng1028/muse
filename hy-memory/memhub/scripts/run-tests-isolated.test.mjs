import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import test from "node:test";
import { promisify } from "node:util";

const run = promisify(execFile);

test("isolated test runner removes its run root and reuses one Corepack cache", async () => {
  const { stdout } = await run("bash", [
    "scripts/run-tests-isolated.sh",
    "self-test",
  ]);
  const home = stdout.match(/HOME=([^\s]+)/)?.[1];
  const corepackHome = stdout.match(/COREPACK_HOME=([^\s]+)/)?.[1];
  assert.ok(home, "self-test must report its temporary HOME");
  assert.ok(corepackHome, "self-test must report the shared Corepack cache");
  assert.equal(existsSync(home), false);
  assert.equal(corepackHome.startsWith(home), false);
});
