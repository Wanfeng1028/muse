#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const { readReleaseContract } = require("./release-contract.cjs");
const releaseContract = readReleaseContract(root);

const SEMVER =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;
const SHA256 = /^[a-f0-9]{64}$/;
const COMMIT = /^[0-9a-f]{40}$/;
const REDIRECTS = new Set([301, 302, 303, 307, 308]);
const MAX_MANIFEST_BYTES = 1024 * 1024;

export async function verifyPublishedRelease(options) {
  const manifestUrl = trustedUrl(options.manifestUrl);
  const expectedVersion = semver(options.version, "release_version_invalid");
  const expectedCommit = commit(options.gitCommit);
  const channel = releaseChannel(options.channel);
  const platform = releasePlatform(options.platform);
  const arch = releaseArch(options.arch);
  const kind = releaseKind(options.kind ?? "runtime");
  if (kind === "desktop" && platform !== "darwin") {
    throw new Error("release_desktop_platform_unsupported");
  }
  const allowedHosts = new Set(
    [manifestUrl.hostname, ...(options.allowedHosts ?? [])].map(normalizedHost),
  );
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? 5 * 60_000;
  const maxRedirects = options.maxRedirects ?? 3;

  const manifestBytes = await fetchBody(manifestUrl, {
    allowedHosts,
    fetchImpl,
    timeoutMs: Math.min(timeoutMs, 30_000),
    maxRedirects,
    maxBytes: MAX_MANIFEST_BYTES,
  });
  let value;
  try {
    value = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(manifestBytes),
    );
  } catch {
    throw new Error("release_manifest_invalid");
  }
  const release = parseManifest(value);
  if (release.version !== expectedVersion)
    throw new Error("release_version_mismatch");
  if (release.git_commit !== expectedCommit)
    throw new Error("release_commit_mismatch");
  if (release.channel !== channel) throw new Error("release_channel_mismatch");
  const artifact = release.artifacts.find(
    (candidate) =>
      candidate.kind === kind &&
      candidate.platform === platform &&
      candidate.arch === arch,
  );
  if (!artifact) throw new Error("release_artifact_unavailable");

  const artifactUrl = trustedUrl(artifact.url);
  if (!allowedHosts.has(normalizedHost(artifactUrl.hostname))) {
    throw new Error("release_url_untrusted");
  }
  const digest = createHash("sha256");
  let total = 0;
  await consumeResponse(artifactUrl, {
    allowedHosts,
    fetchImpl,
    timeoutMs,
    maxRedirects,
    consume: async (response) => {
      const declared = contentLength(response.headers);
      if (declared !== null && declared !== artifact.bytes) {
        throw new Error("release_artifact_size_mismatch");
      }
      if (!response.body) throw new Error("release_response_body_missing");
      for await (const chunk of response.body) {
        const bytes =
          chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk);
        total += bytes.byteLength;
        if (total > artifact.bytes)
          throw new Error("release_artifact_size_mismatch");
        digest.update(bytes);
      }
    },
  });
  if (total !== artifact.bytes)
    throw new Error("release_artifact_size_mismatch");
  const actualSha256 = digest.digest("hex");
  if (actualSha256 !== artifact.sha256) {
    throw new Error("release_artifact_hash_mismatch");
  }
  return {
    schema_version: 1,
    product: "memhub-published-release-verification",
    manifest_url: manifestUrl.href,
    version: release.version,
    build_number: release.build_number,
    git_commit: release.git_commit,
    channel: release.channel,
    kind,
    platform,
    arch,
    artifact_url: artifactUrl.href,
    filename: artifact.filename,
    bytes: total,
    sha256: actualSha256,
    verified_at: new Date().toISOString(),
  };
}

async function fetchBody(initial, options) {
  const chunks = [];
  let total = 0;
  await consumeResponse(initial, {
    ...options,
    consume: async (response) => {
      const declared = contentLength(response.headers);
      if (declared !== null && declared > options.maxBytes) {
        throw new Error("release_response_too_large");
      }
      if (!response.body) throw new Error("release_response_body_missing");
      for await (const chunk of response.body) {
        const bytes =
          chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk);
        total += bytes.byteLength;
        if (total > options.maxBytes)
          throw new Error("release_response_too_large");
        chunks.push(bytes);
      }
    },
  });
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

async function consumeResponse(initial, options) {
  let current = initial;
  for (let redirect = 0; ; redirect += 1) {
    if (!options.allowedHosts.has(normalizedHost(current.hostname))) {
      throw new Error("release_url_untrusted");
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs);
    try {
      const response = await options.fetchImpl(current.href, {
        method: "GET",
        redirect: "manual",
        signal: controller.signal,
        headers: {
          accept: "application/json, application/octet-stream;q=0.9, */*;q=0.1",
        },
      });
      if (REDIRECTS.has(response.status)) {
        if (redirect >= options.maxRedirects)
          throw new Error("release_redirect_limit");
        const location = response.headers.get("location");
        if (!location) throw new Error("release_redirect_invalid");
        current = trustedUrl(new URL(location, current).href);
        continue;
      }
      if (response.status !== 200)
        throw new Error(`release_http_status_${response.status}`);
      await options.consume(response);
      return;
    } catch (error) {
      if (controller.signal.aborted)
        throw new Error("release_download_timeout");
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }
}

function parseManifest(value) {
  if (
    !object(value) ||
    !Array.isArray(value.artifacts) ||
    value.artifacts.length === 0
  ) {
    throw new Error("release_manifest_invalid");
  }
  if (
    value.schema_version !== 1 ||
    value.product !== "memhub-release" ||
    typeof value.version !== "string" ||
    !SEMVER.test(value.version) ||
    !Number.isSafeInteger(value.build_number) ||
    value.build_number < 0 ||
    typeof value.git_commit !== "string" ||
    !COMMIT.test(value.git_commit) ||
    value.cli_protocol !== releaseContract.cliProtocol ||
    value.supported_runtime_protocol?.min !==
      releaseContract.cliSupportedRuntimeProtocol.min ||
    value.supported_runtime_protocol?.max !==
      releaseContract.cliSupportedRuntimeProtocol.max ||
    value.runtime_protocol !== releaseContract.runtimeProtocol ||
    value.supported_cli_protocol?.min !==
      releaseContract.runtimeSupportedCliProtocol.min ||
    value.supported_cli_protocol?.max !==
      releaseContract.runtimeSupportedCliProtocol.max ||
    !["stable", "prerelease"].includes(value.channel) ||
    typeof value.published_at !== "string" ||
    Number.isNaN(Date.parse(value.published_at))
  ) {
    throw new Error("release_manifest_invalid");
  }
  const identities = new Set();
  const artifacts = value.artifacts.map((artifact) => {
    if (object(artifact) && artifact.kind === "desktop") {
      if (
        artifact.platform !== "darwin" ||
        !["x64", "arm64"].includes(artifact.arch) ||
        artifact.format !== "dmg" ||
        typeof artifact.filename !== "string" ||
        !/^[0-9A-Za-z][0-9A-Za-z._-]{0,255}$/.test(artifact.filename) ||
        typeof artifact.url !== "string" ||
        !Number.isSafeInteger(artifact.bytes) ||
        artifact.bytes <= 0 ||
        typeof artifact.sha256 !== "string" ||
        !SHA256.test(artifact.sha256) ||
        typeof artifact.minimum_system_version !== "string" ||
        !/^\d+\.\d+$/.test(artifact.minimum_system_version)
      ) {
        throw new Error("release_manifest_invalid");
      }
      trustedUrl(artifact.url);
      const identity = `desktop/${artifact.platform}/${artifact.arch}`;
      if (identities.has(identity)) throw new Error("release_manifest_invalid");
      identities.add(identity);
      return artifact;
    }
    if (object(artifact) && artifact.kind === "metadata") {
      if (
        !["sbom", "notices"].includes(artifact.role) ||
        !["spdx-json", "markdown"].includes(artifact.format) ||
        typeof artifact.filename !== "string" ||
        !/^[0-9A-Za-z][0-9A-Za-z._-]{0,255}$/.test(artifact.filename) ||
        typeof artifact.url !== "string" ||
        !Number.isSafeInteger(artifact.bytes) ||
        artifact.bytes <= 0 ||
        typeof artifact.sha256 !== "string" ||
        !SHA256.test(artifact.sha256)
      ) {
        throw new Error("release_manifest_invalid");
      }
      trustedUrl(artifact.url);
      const identity = `metadata/${artifact.role}`;
      if (identities.has(identity)) throw new Error("release_manifest_invalid");
      identities.add(identity);
      return artifact;
    }
    if (
      !object(artifact) ||
      artifact.kind !== "runtime" ||
      !["darwin", "linux"].includes(artifact.platform) ||
      !["x64", "arm64"].includes(artifact.arch) ||
      artifact.format !== "tar.gz" ||
      typeof artifact.filename !== "string" ||
      !/^[0-9A-Za-z][0-9A-Za-z._-]{0,255}$/.test(artifact.filename) ||
      typeof artifact.url !== "string" ||
      !Number.isSafeInteger(artifact.bytes) ||
      artifact.bytes <= 0 ||
      !Number.isSafeInteger(artifact.unpacked_bytes) ||
      artifact.unpacked_bytes <= 0 ||
      typeof artifact.sha256 !== "string" ||
      !SHA256.test(artifact.sha256) ||
      artifact.runtime_manifest_schema !== 1
    ) {
      throw new Error("release_manifest_invalid");
    }
    trustedUrl(artifact.url);
    const identity = `runtime/${artifact.platform}/${artifact.arch}`;
    if (identities.has(identity)) throw new Error("release_manifest_invalid");
    identities.add(identity);
    return artifact;
  });
  return { ...value, artifacts };
}

function parseArgs(arguments_) {
  const options = { allowedHosts: [], kind: "runtime" };
  for (let index = 0; index < arguments_.length; index += 1) {
    const flag = arguments_[index];
    const value = arguments_[++index];
    if (!value) throw new Error(`missing value for ${flag}`);
    if (flag === "--manifest-url" && options.manifestUrl === undefined)
      options.manifestUrl = value;
    else if (flag === "--version" && options.version === undefined)
      options.version = value;
    else if (flag === "--channel" && options.channel === undefined)
      options.channel = value;
    else if (flag === "--git-commit" && options.gitCommit === undefined)
      options.gitCommit = value;
    else if (flag === "--platform" && options.platform === undefined)
      options.platform = value;
    else if (flag === "--arch" && options.arch === undefined)
      options.arch = value;
    else if (flag === "--kind") options.kind = value;
    else if (flag === "--allowed-host") options.allowedHosts.push(value);
    else throw new Error(`invalid argument: ${flag}`);
  }
  if (
    !options.manifestUrl ||
    !options.version ||
    !options.gitCommit ||
    !options.channel ||
    !options.platform ||
    !options.arch
  ) {
    throw new Error(
      "usage: verify-published-release.mjs --manifest-url <https-url> --version <SemVer> --git-commit <sha> --channel <stable|prerelease> --platform <darwin|linux> --arch <x64|arm64> [--kind <runtime|desktop>] [--allowed-host <hostname>]",
    );
  }
  return options;
}

function trustedUrl(raw) {
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("release_url_invalid");
  }
  if (url.protocol !== "https:" || url.username || url.password || url.hash) {
    throw new Error("release_url_invalid");
  }
  return url;
}

function contentLength(headers) {
  const raw = headers.get("content-length");
  if (raw === null) return null;
  if (!/^\d+$/.test(raw)) throw new Error("release_content_length_invalid");
  const value = Number(raw);
  if (!Number.isSafeInteger(value))
    throw new Error("release_content_length_invalid");
  return value;
}

function semver(value, error) {
  if (typeof value !== "string" || !SEMVER.test(value)) throw new Error(error);
  return value;
}

function commit(value) {
  if (typeof value !== "string" || !COMMIT.test(value)) {
    throw new Error("release_commit_invalid");
  }
  return value;
}

function releaseChannel(value) {
  if (value !== "stable" && value !== "prerelease")
    throw new Error("release_channel_invalid");
  return value;
}

function releasePlatform(value) {
  if (value !== "darwin" && value !== "linux")
    throw new Error("release_platform_unsupported");
  return value;
}

function releaseArch(value) {
  if (value !== "x64" && value !== "arm64")
    throw new Error("release_arch_unsupported");
  return value;
}

function releaseKind(value) {
  if (value !== "runtime" && value !== "desktop") {
    throw new Error("release_artifact_kind_invalid");
  }
  return value;
}

function normalizedHost(value) {
  return value.trim().toLowerCase();
}

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

async function main() {
  const receipt = await verifyPublishedRelease(
    parseArgs(process.argv.slice(2)),
  );
  process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : error}\n`);
    process.exitCode = 1;
  });
}
