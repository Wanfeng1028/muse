/** Shared trusted sync-hook asset handling for Desktop and Runtime installers. */
import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { lstat, open } from "node:fs/promises";
import path from "node:path";
import {
  type ClaudeInstallPlan,
  verifiedAssets,
} from "@one-memory/host-bridge";

export interface SyncHookStatus {
  hostId: string;
  state:
    | "unsupported"
    | "connection-required"
    | "not-installed"
    | "installed"
    | "modified"
    | "unavailable";
  reason: string | null;
}
export interface SyncHookPreview {
  hostId: string;
  operation: "install" | "uninstall";
  installationId: string;
  revision: number;
  fingerprint: string;
  files: Array<{
    path: string;
    action: "create" | "update" | "remove";
    owner: "host" | "one-memory";
  }>;
}
export interface ApplySyncHookInput {
  operation: "install" | "uninstall";
  installationId: string;
  revision: number;
  fingerprint: string;
  userConfirmed: true;
}
const digest = (value: string | Buffer) =>
  createHash("sha256").update(value).digest("hex");
const object = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v);
const keys = (v: Record<string, unknown>, names: string[]) =>
  Object.keys(v).length === names.length &&
  names.every((k) => Object.hasOwn(v, k));

async function readAsset(file: string, limit: number): Promise<string> {
  const handle = await open(
    file,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
  );
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.size > limit)
      throw new Error("invalid_asset");
    const buffer = Buffer.alloc(limit + 1);
    let length = 0;
    while (length < buffer.length) {
      const r = await handle.read(
        buffer,
        length,
        buffer.length - length,
        length,
      );
      if (!r.bytesRead) break;
      length += r.bytesRead;
    }
    if (length > limit) throw new Error("invalid_asset");
    return new TextDecoder("utf-8", { fatal: true }).decode(
      buffer.subarray(0, length),
    );
  } finally {
    await handle.close();
  }
}
export async function loadSyncHookAssets(directory: string) {
  try {
    if (!path.isAbsolute(directory)) throw new Error("invalid_asset");
    const info = await lstat(directory);
    if (!info.isDirectory() || info.isSymbolicLink())
      throw new Error("invalid_asset");
    const manifest: unknown = JSON.parse(
      await readAsset(path.join(directory, "manifest.json"), 8192),
    );
    if (
      !object(manifest) ||
      !keys(manifest, [
        "schemaVersion",
        "runtimeCapability",
        "notificationCapability",
        "runtimeTarget",
        "files",
      ]) ||
      manifest.schemaVersion !== 1 ||
      manifest.runtimeCapability !== "mh-c01-runtime-v1" ||
      manifest.notificationCapability !== "source-change-v1" ||
      manifest.runtimeTarget !== "node24" ||
      !object(manifest.files) ||
      !keys(manifest.files, ["runtime.mjs", "notification.mjs"])
    )
      throw new Error("invalid_asset");
    const contents: Record<string, string> = {};
    for (const name of ["runtime.mjs", "notification.mjs"]) {
      const meta = manifest.files[name];
      if (
        !object(meta) ||
        !keys(meta, ["sha256", "bytes"]) ||
        typeof meta.sha256 !== "string" ||
        !/^[a-f0-9]{64}$/.test(meta.sha256) ||
        !Number.isSafeInteger(meta.bytes) ||
        Number(meta.bytes) <= 0 ||
        Number(meta.bytes) > 2 * 1024 * 1024
      )
        throw new Error("invalid_asset");
      const value = await readAsset(
        path.join(directory, name),
        2 * 1024 * 1024,
      );
      if (
        Buffer.byteLength(value) !== meta.bytes ||
        digest(value) !== meta.sha256
      )
        throw new Error("invalid_asset");
      contents[name] = value;
    }
    return verifiedAssets({
      runtime: contents["runtime.mjs"],
      notification: contents["notification.mjs"],
      proof: {
        runtimeSha256: digest(contents["runtime.mjs"]),
        notificationSha256: digest(contents["notification.mjs"]),
        integrationTestsPassed: true,
      },
    });
  } catch {
    throw new Error("sync_hook_assets_unavailable");
  }
}

export async function hasSyncHookArtifacts(root: string): Promise<boolean> {
  for (const name of [
    "install.json",
    "hook.mjs",
    "runtime.mjs",
    "notification.mjs",
    "config.json",
    "LICENSE.memmy",
  ]) {
    try {
      await lstat(path.join(root, ".one-memory/mh-c01", name));
      return true;
    } catch (error) {
      if (!object(error) || error.code !== "ENOENT") throw error;
    }
  }
  return false;
}

/** Identity for removing hook artifacts that outlived their installation record.
 *
 * A host directory can keep `.one-memory/mh-c01` after the record behind it is
 * gone: the data directory was reset, or the artifacts came from an earlier
 * build. Those files still block re-linking, and removal used to require the
 * missing record to build a preview, so the host could never be repaired.
 *
 * The identity is derived from the host directory so that preview and apply
 * agree without involving the grant store. Nothing is authorized through an
 * orphaned hook, and the only operation it can carry is a removal, so there is
 * no right to bind to an installation here.
 */
export function orphanSyncHookIdentity(root: string): {
  installationId: string;
  revision: number;
  credentialDigest: string;
} {
  const seed = digest(`one-memory-orphan-sync-hook:${path.resolve(root)}`);
  return {
    installationId: [
      seed.slice(0, 8),
      seed.slice(8, 12),
      `4${seed.slice(13, 16)}`,
      `8${seed.slice(17, 20)}`,
      seed.slice(20, 32),
    ].join("-"),
    revision: 1,
    credentialDigest: seed,
  };
}

export function syncHookPreview(
  root: string,
  plan: ClaudeInstallPlan,
  identity: {
    installationId: string;
    revision: number;
    credentialDigest: string;
  },
): SyncHookPreview {
  return {
    hostId: "claude-code",
    operation: plan.operation,
    installationId: identity.installationId,
    revision: identity.revision,
    fingerprint: digest(
      JSON.stringify([
        root,
        plan.fingerprint,
        identity.installationId,
        identity.revision,
        identity.credentialDigest,
      ]),
    ),
    files: plan.files
      .filter((file) => file.content !== file.after)
      .map((file) => ({
        path: path.join(root, file.path),
        action:
          file.after === null
            ? "remove"
            : file.content === null
              ? "create"
              : "update",
        owner:
          file.path === "settings.json" || file.path === "CLAUDE.md"
            ? "host"
            : "one-memory",
      })),
  };
}

export function syncHookInput(value: unknown): ApplySyncHookInput {
  if (
    !object(value) ||
    !keys(value, [
      "operation",
      "installationId",
      "revision",
      "fingerprint",
      "userConfirmed",
    ]) ||
    (value.operation !== "install" && value.operation !== "uninstall") ||
    value.userConfirmed !== true ||
    typeof value.installationId !== "string" ||
    !/^[a-f0-9-]{36}$/.test(value.installationId) ||
    !Number.isSafeInteger(value.revision) ||
    Number(value.revision) < 1 ||
    typeof value.fingerprint !== "string" ||
    !/^[a-f0-9]{64}$/.test(value.fingerprint)
  )
    throw new Error("sync_hook_confirmation_required");
  return value as unknown as ApplySyncHookInput;
}
