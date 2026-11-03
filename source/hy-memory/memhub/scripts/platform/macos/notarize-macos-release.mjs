#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { publicGateReport } from "./service-lifecycle.mjs";

export async function notarizeMacosRelease(options) {
  if (process.platform !== "darwin") {
    throw new Error("macos_notarization_requires_darwin");
  }
  const app = path.resolve(options.app);
  const dmg = path.resolve(options.dmg);
  const receiptPath = path.resolve(options.receipt);
  const key = process.env.APPLE_NOTARY_KEY_PATH?.trim();
  const keyId = process.env.APPLE_API_KEY_ID?.trim();
  const issuer = process.env.APPLE_API_ISSUER?.trim();
  const identity = process.env.CSC_NAME?.trim();
  const keychain = process.env.CSC_KEYCHAIN?.trim();
  if (!key || !keyId || !issuer || !identity || !keychain) {
    throw new Error("macos_notarization_credentials_required");
  }
  await mkdir(path.dirname(dmg), { recursive: true, mode: 0o700 });
  await mkdir(path.dirname(receiptPath), { recursive: true, mode: 0o700 });
  const temporary = await mkdtemp(path.join(os.tmpdir(), "memhub-notarize-"));
  const zip = path.join(temporary, "MemHub.app.zip");
  try {
    detachMountedDmgVolumes("MemHub");
    run("ditto", ["-c", "-k", "--keepParent", app, zip]);
    const appSubmission = submit(zip, { key, keyId, issuer });
    run("xcrun", ["stapler", "staple", app]);
    run("xcrun", ["stapler", "validate", app]);
    run("hdiutil", [
      "create",
      "-volname",
      "MemHub",
      "-srcfolder",
      app,
      "-ov",
      "-format",
      "UDZO",
      dmg,
    ]);
    run("codesign", [
      "--force",
      "--timestamp",
      "--sign",
      identity,
      "--keychain",
      keychain,
      dmg,
    ]);
    run("codesign", ["--verify", "--strict", dmg]);
    const dmgSubmission = submit(dmg, { key, keyId, issuer });
    run("xcrun", ["stapler", "staple", dmg]);
    run("xcrun", ["stapler", "validate", dmg]);
    const checks = await publicGateReport(app);
    const dmgSpctl = run(
      "spctl",
      [
        "-a",
        "-vvv",
        "-t",
        "open",
        "--context",
        "context:primary-signature",
        dmg,
      ],
      false,
    );
    const dmgStapler = run("xcrun", ["stapler", "validate", dmg], false);
    const dmgCodesign = run("codesign", ["--verify", "--strict", dmg], false);
    checks.push({
      name: "public_gate_dmg_codesign_verify",
      result: dmgCodesign.code === 0 ? "pass" : "fail",
      status: dmgCodesign.code === 0 ? "pass" : "fail",
      evidence: `codesign --verify --strict exit ${dmgCodesign.code}`,
    });
    checks.push({
      name: "public_gate_dmg_gatekeeper_accepts",
      result: dmgSpctl.code === 0 ? "pass" : "fail",
      status: dmgSpctl.code === 0 ? "pass" : "fail",
      evidence:
        dmgSpctl.code === 0 ? "spctl accepted DMG" : "spctl rejected DMG",
    });
    checks.push({
      name: "public_gate_dmg_notarization_ticket",
      result: dmgStapler.code === 0 ? "pass" : "fail",
      status: dmgStapler.code === 0 ? "pass" : "fail",
      evidence:
        dmgStapler.code === 0
          ? "notarization ticket stapled to DMG"
          : "DMG notarization ticket missing",
    });
    // `verify_public_release_ready.py` consumes `status`; service-lifecycle's
    // native check records `result`. Carry both without weakening either API.
    const normalized = checks.map((check) => ({
      ...check,
      status: check.status ?? check.result,
    }));
    if (normalized.some((check) => check.status !== "pass")) {
      throw new Error("macos_public_gate_failed");
    }
    const receipt = {
      schema_version: 1,
      product: "memhub-macos-public-gate",
      platform: "darwin",
      arch: process.arch,
      app,
      dmg,
      app_submission_id: appSubmission.id,
      dmg_submission_id: dmgSubmission.id,
      checks: normalized,
      result: "passed",
    };
    await writeFile(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`);
    return receipt;
  } finally {
    detachMountedDmgVolumes("MemHub", false);
    await rm(temporary, { recursive: true, force: true });
  }
}

/** Detach stale copies of the product DMG before creating another one.
 *
 * Finder and failed packaging runs can leave `/Volumes/MemHub` mounted. A
 * later `hdiutil create -volname MemHub` then fails with EPERM while trying to
 * stage `MemHub.app`. Only mounts reported by `hdiutil info` are considered,
 * so an unrelated physical volume is never detached merely because it has a
 * similar path. Suffixed mounts (`MemHub 1`, `MemHub 2`, ...) are cleaned too
 * so build workers do not accumulate old images indefinitely.
 */
export function detachMountedDmgVolumes(
  volumeName,
  required = true,
  runCommand = run,
) {
  const info = runCommand("hdiutil", ["info"], required);
  if (info.code !== 0) return [];
  const mounts = parseDmgMounts(info.stdout, volumeName);
  for (const mount of mounts) {
    runCommand("hdiutil", ["detach", mount.mountPoint, "-force"], required);
  }
  if (required) {
    const remaining = parseDmgMounts(
      runCommand("hdiutil", ["info"], true).stdout,
      volumeName,
    );
    if (remaining.length > 0) {
      throw new Error(
        `macos_dmg_volume_cleanup_failed:${remaining
          .map((mount) => mount.mountPoint)
          .join(",")}`,
      );
    }
  }
  return mounts;
}

export function parseDmgMounts(stdout, volumeName) {
  const escaped = volumeName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const accepted = new RegExp(`^/Volumes/${escaped}(?: \\d+)?$`);
  const mounts = [];
  for (const line of stdout.split(/\r?\n/)) {
    if (!line.startsWith("/dev/disk")) continue;
    const columns = line.split("\t").filter(Boolean);
    const device = columns[0];
    const mountPoint = columns.at(-1);
    if (!device || !mountPoint || !accepted.test(mountPoint)) continue;
    mounts.push({ device, mountPoint });
  }
  return mounts.sort((left, right) =>
    left.mountPoint.localeCompare(right.mountPoint),
  );
}

function submit(file, credentials) {
  const result = run("xcrun", [
    "notarytool",
    "submit",
    file,
    "--key",
    credentials.key,
    "--key-id",
    credentials.keyId,
    "--issuer",
    credentials.issuer,
    "--wait",
    "--output-format",
    "json",
  ]);
  let document;
  try {
    document = JSON.parse(result.stdout);
  } catch {
    throw new Error("macos_notarization_response_invalid");
  }
  if (document.status !== "Accepted" || typeof document.id !== "string") {
    throw new Error("macos_notarization_rejected");
  }
  return document;
}

function run(command, arguments_, required = true) {
  const result = spawnSync(command, arguments_, {
    encoding: "utf8",
    timeout: 30 * 60_000,
  });
  if (required && result.status !== 0) {
    throw new Error(`${command} failed: ${result.stderr || result.stdout}`);
  }
  return { code: result.status, stdout: result.stdout, stderr: result.stderr };
}

function parseArguments(arguments_) {
  const options = {};
  for (let index = 0; index < arguments_.length; index += 1) {
    const flag = arguments_[index];
    const value = arguments_[++index];
    if (!value) throw new Error(`missing value for ${flag}`);
    if (flag === "--app") options.app = value;
    else if (flag === "--dmg") options.dmg = value;
    else if (flag === "--receipt") options.receipt = value;
    else throw new Error(`invalid argument: ${flag}`);
  }
  if (!options.app || !options.dmg || !options.receipt) {
    throw new Error(
      "usage: notarize-macos-release.mjs --app <MemHub.app> --dmg <output.dmg> --receipt <json>",
    );
  }
  return options;
}

async function main() {
  const receipt = await notarizeMacosRelease(
    parseArguments(process.argv.slice(2)),
  );
  process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : error}\n`);
    process.exitCode = 1;
  });
}
