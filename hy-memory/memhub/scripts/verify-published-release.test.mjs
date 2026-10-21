import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import { verifyPublishedRelease } from "./verify-published-release.mjs";

const artifact = new TextEncoder().encode("verified runtime artifact\n");
const digest = createHash("sha256").update(artifact).digest("hex");
const desktopArtifact = new TextEncoder().encode("verified desktop dmg\n");
const desktopDigest = createHash("sha256")
  .update(desktopArtifact)
  .digest("hex");

function manifest(overrides = {}) {
  return {
    schema_version: 1,
    product: "memhub-release",
    version: "0.1.0-internal.1",
    build_number: 1,
    git_commit: "a".repeat(40),
    channel: "prerelease",
    cli_protocol: 1,
    supported_runtime_protocol: { min: 1, max: 1 },
    runtime_protocol: 1,
    supported_cli_protocol: { min: 1, max: 1 },
    published_at: "2026-10-13T00:00:00Z",
    artifacts: [
      {
        kind: "runtime",
        platform: "linux",
        arch: "x64",
        format: "tar.gz",
        filename: "memhub-runtime-v0.1.0-internal.1-linux-x64.tar.gz",
        url: "https://releases.example.test/runtime.tar.gz",
        bytes: artifact.byteLength,
        unpacked_bytes: 100,
        sha256: digest,
        runtime_manifest_schema: 1,
      },
      {
        kind: "desktop",
        platform: "darwin",
        arch: "arm64",
        format: "dmg",
        filename: "MemHub-v0.1.0-internal.1-macos-arm64.dmg",
        url: "https://releases.example.test/MemHub.dmg",
        bytes: desktopArtifact.byteLength,
        sha256: desktopDigest,
        minimum_system_version: "13.0",
      },
      {
        kind: "metadata",
        role: "sbom",
        format: "spdx-json",
        filename: "SBOM.spdx.json",
        url: "https://releases.example.test/SBOM.spdx.json",
        bytes: 10,
        sha256: "e".repeat(64),
      },
    ],
    ...overrides,
  };
}

function response(body, options = {}) {
  return new Response(body, {
    status: options.status ?? 200,
    headers: {
      "content-length": String(body?.byteLength ?? 0),
      ...(options.headers ?? {}),
    },
  });
}

function fetcher(release = manifest(), artifactBody = artifact) {
  return async (url) => {
    if (url === "https://releases.example.test/release-manifest.json") {
      return response(new TextEncoder().encode(JSON.stringify(release)));
    }
    if (url === "https://releases.example.test/runtime.tar.gz") {
      return response(artifactBody);
    }
    if (url === "https://releases.example.test/MemHub.dmg") {
      return response(desktopArtifact);
    }
    return response(new Uint8Array(), { status: 404 });
  };
}

const base = {
  manifestUrl: "https://releases.example.test/release-manifest.json",
  version: "0.1.0-internal.1",
  gitCommit: "a".repeat(40),
  channel: "prerelease",
  platform: "linux",
  arch: "x64",
};

test("verifies the remotely served manifest and complete artifact", async () => {
  const receipt = await verifyPublishedRelease({
    ...base,
    fetchImpl: fetcher(),
  });
  assert.equal(receipt.version, "0.1.0-internal.1");
  assert.equal(receipt.bytes, artifact.byteLength);
  assert.equal(receipt.sha256, digest);
});

test("verifies a Desktop DMG without confusing it with the Runtime", async () => {
  const receipt = await verifyPublishedRelease({
    ...base,
    kind: "desktop",
    platform: "darwin",
    arch: "arm64",
    fetchImpl: fetcher(),
  });
  assert.equal(receipt.kind, "desktop");
  assert.equal(receipt.filename, "MemHub-v0.1.0-internal.1-macos-arm64.dmg");
  assert.equal(receipt.bytes, desktopArtifact.byteLength);
  assert.equal(receipt.sha256, desktopDigest);
});

test("rejects version drift before accepting the artifact", async () => {
  await assert.rejects(
    verifyPublishedRelease({
      ...base,
      version: "0.1.0-internal.2",
      fetchImpl: fetcher(),
    }),
    /release_version_mismatch/,
  );
});

test("rejects a Release from a different tag commit", async () => {
  await assert.rejects(
    verifyPublishedRelease({
      ...base,
      gitCommit: "b".repeat(40),
      fetchImpl: fetcher(),
    }),
    /release_commit_mismatch/,
  );
});

test("rejects a redirect to a host outside the allow-list", async () => {
  const fetchImpl = async (url) => {
    if (url.endsWith("release-manifest.json")) {
      return new Response(null, {
        status: 302,
        headers: {
          location: "https://objects.example.test/release-manifest.json",
        },
      });
    }
    throw new Error("unexpected request");
  };
  await assert.rejects(
    verifyPublishedRelease({ ...base, fetchImpl }),
    /release_url_untrusted/,
  );
});

test("rejects an artifact whose bytes do not match the manifest digest", async () => {
  await assert.rejects(
    verifyPublishedRelease({
      ...base,
      fetchImpl: fetcher(
        manifest(),
        new TextEncoder().encode("different artifact bytes\n"),
      ),
    }),
    /release_artifact_size_mismatch|release_artifact_hash_mismatch/,
  );
});
