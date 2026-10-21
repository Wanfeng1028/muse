import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("./verify-fake-release-bootstrap.mjs", import.meta.url),
  "utf8",
);

test("fake Release smoke keeps the real downloader and install transaction", () => {
  for (const marker of [
    "buildReleaseAssets",
    "https.createServer",
    "const child = spawn(command",
    "NODE_EXTRA_CA_CERTS",
    "MEMHUB_DEFAULT_RELEASE_MANIFEST_URL_TEMPLATE",
    "sourceRoot",
    "preview_manifest_only",
    "remote_download_install",
    "download_cleanup",
    "doctor_core_version",
    "npm_uninstall_preserve_runtime_data",
    "uninstall_preserve_data",
    "npmInstallSpec",
    "expectedCliSha256",
    "fake_release_registry_cli_digest_mismatch",
    "--release-manifest-url",
  ]) {
    assert.ok(source.includes(marker), marker);
  }
  assert.match(source, /previewDocument\?\.apply !== false/);
  assert.match(source, /afterApply\.artifact !== beforeApply\.artifact \+ 1/);
  assert.match(source, /servedArtifact\.bytes_sent !== artifact\.bytes/);
  assert.match(source, /databaseAfter\.sha256 !== databaseBefore\.sha256/);
  assert.match(source, /active-after-npm-uninstall/);
  assert.match(source, /doctor-after-npm-uninstall/);
  assert.doesNotMatch(source, /http:\/\//);
});
