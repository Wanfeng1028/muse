import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("self-contained verifier poisons system build/runtime tools", async () => {
  const source = await readFile(
    new URL("./verify-self-contained-runtime.mjs", import.meta.url),
    "utf8",
  );
  for (const marker of [
    '"python"',
    '"python3"',
    '"sqlite3"',
    '"pnpm"',
    '"uv"',
    "PATH: `${poisonBin}:/usr/bin:/bin`",
    'child.kill("SIGTERM")',
    "no_system_python_sqlite_build_tools",
  ]) {
    assert.ok(source.includes(marker), marker);
  }
});
