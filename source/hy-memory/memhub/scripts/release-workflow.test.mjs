import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflowUrl = new URL(
  "../../.github/workflows/release.yml",
  import.meta.url,
);

test("the optional full release workflow is manual and preserves ordering", async () => {
  const workflow = await readFile(workflowUrl, "utf8");

  assert.match(workflow, /workflow_dispatch:/);
  assert.doesNotMatch(workflow, /tags:\s*\n\s*- ["']v\*["']/);
  assert.match(workflow, /verify_public_release_ready\.py --json/);
  assert.match(workflow, /export_public_snapshot\.py/);
  assert.match(workflow, /verify_public_snapshot\.py/);
  assert.match(workflow, /verify-release-version\.mjs/);
  assert.match(workflow, /release\.build_number/);
  assert.match(workflow, /source_date_epoch=.*git show -s --format=%ct/);
  assert.match(
    workflow,
    /SOURCE_DATE_EPOCH: \$\{\{ needs\.contract\.outputs\.source_date_epoch \}\}/,
  );
  assert.match(workflow, /run: pnpm run sbom/);
  assert.doesNotMatch(workflow, /run: pnpm sbom/);
  assert.doesNotMatch(workflow, /github\.run_number/);
  assert.match(workflow, /ubuntu-24\.04-arm/);
  assert.match(workflow, /runner: macos-15\n\s+arch: arm64/);
  assert.match(workflow, /runner: macos-15-intel\n\s+arch: x64/);
  assert.match(workflow, /APPLE_CERTIFICATE_BASE64/);
  assert.match(workflow, /APPLE_API_KEY_P8_BASE64/);
  assert.match(workflow, /if: always\(\)/);
  assert.match(workflow, /security delete-keychain/);
  assert.match(workflow, /DeveloperIDG2CA\.cer/);
  assert.match(workflow, /AppleRootCA\.pem/);
  assert.match(workflow, /memhub-notary-key\.p8/);
  assert.match(workflow, /build-macos-release\.mjs/);
  assert.match(workflow, /notarize-macos-release\.mjs/);
  assert.match(workflow, /runtime-app-darwin-arm64/);
  assert.match(workflow, /runtime-app-darwin-x64/);
  assert.match(workflow, /--desktop "arm64=/);
  assert.match(workflow, /--desktop "x64=/);
  assert.match(workflow, /--kind "\$\{\{ matrix\.kind \}\}"/);
  assert.match(workflow, /--git-commit "\$GITHUB_SHA"/);
  assert.match(workflow, /verify-linux-lifecycle\.mjs/);
  assert.match(workflow, /verify-release-proxy\.mjs/);
  assert.match(workflow, /verify-self-contained-runtime\.mjs/);
  assert.match(workflow, /self-contained-runtime-receipt\.json/);
  assert.match(workflow, /release-proxy-receipt\.json/);
  assert.match(workflow, /if: matrix\.arch == 'x64'/);
  assert.match(workflow, /transport\.tar\.gz/);
  assert.match(workflow, /build-release-assets\.mjs/);
  assert.match(workflow, /attest-build-provenance@[a-f0-9]{40}/);
  assert.match(workflow, /gh release create/);
  assert.match(workflow, /verify-published-release\.mjs/);
  assert.match(workflow, /publish-cli-after-release\.mjs/);
  assert.match(
    workflow,
    /MEMHUB_DEFAULT_RELEASE_MANIFEST_URL_TEMPLATE: https:\/\/github\.com\//,
  );
  assert.match(workflow, /--provenance/);
  assert.match(workflow, /npm install --global/);
  assert.match(workflow, /Install the Runtime through the registry CLI/);
  assert.match(workflow, /core_port=.*node -e/);
  assert.match(workflow, /ONE_MEMORY_CORE_PORT=\$core_port/);
  assert.match(workflow, /GITHUB_ENV/);
  assert.match(
    workflow,
    /needs:\s*\n\s*- contract\s*\n\s*- verify-published-release/,
  );

  const uses = [...workflow.matchAll(/^\s*- uses:\s*([^\s]+)\s*$/gm)].map(
    (match) => match[1],
  );
  assert.ok(uses.length > 0);
  for (const action of uses) {
    assert.match(action, /@[a-f0-9]{40}$/, `action must be pinned: ${action}`);
  }
});
