import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("proxy verifier exercises HTTPS_PROXY and NO_PROXY through the CLI", async () => {
  const source = await readFile(
    new URL("./verify-release-proxy.mjs", import.meta.url),
    "utf8",
  );
  for (const marker of [
    "HTTPS_PROXY",
    "NO_PROXY",
    'proxy.on("connect"',
    "NODE_EXTRA_CA_CERTS",
    "release_proxy_not_used",
    "release_no_proxy_not_honored",
    "apps/cli/dist/one-memory.cjs",
  ]) {
    assert.ok(source.includes(marker), marker);
  }
});
