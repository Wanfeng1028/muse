import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("./verify-linux-upgrade-rollback.mjs", import.meta.url),
  "utf8",
);

test("Linux upgrade matrix proves N-1 to N and crash rollback separately", () => {
  for (const marker of [
    "upgrade_n_minus_one_to_n",
    "makeFailingDistribution",
    "upgrade_health_check_failed",
    "selection_not_restored",
    "failed_version_retained",
    "recalled_after_rollback",
    "database_file_changed_during_failed_upgrade",
    "uninstall_preserve_data",
    "inactive-before-uninstall",
  ]) {
    assert.ok(source.includes(marker), marker);
  }
  assert.match(source, /currentDistribution\.manifest\.build_number <=/);
  assert.match(source, /manifest\.files\["core\/one-memory"\]/);
  assert.match(source, /crashingExecutable = "\/bin\/false"/);
  const crashUpgrade = source.slice(
    source.indexOf("const failedUpgrade = run("),
    source.indexOf("if (failedUpgrade.status !== 1)"),
  );
  assert.match(crashUpgrade, /"upgrade-to-crashing-build"/);
  assert.match(crashUpgrade, /\[1\]/);
  assert.match(
    crashUpgrade,
    /180_000/,
    "the outer crash-upgrade timeout must cover failure detection and rollback readiness",
  );
  const statusWait = source.slice(
    source.indexOf("async function waitForRunningStatus"),
    source.indexOf("async function waitForRecall"),
  );
  assert.match(statusWait, /\[0, 1, 3\]/);
  assert.match(statusWait, /if \(result\.status === 0\)/);
  assert.match(source, /recalled_after_rollback/);
  assert.match(
    source,
    /databaseAfterUninstall\.sha256 !== databaseBeforeUninstall\.sha256/,
  );
});
