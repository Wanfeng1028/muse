import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  planUserService,
  type RuntimeInstallLayout,
  type RuntimeServicePlan,
} from "../../service-plan.js";

export type LinuxCapabilityStatus = "available" | "unavailable" | "unknown";

export interface LinuxHostCapabilities {
  systemd: boolean;
  portables: boolean;
  tmpfilesD: boolean;
}

export interface LinuxRuntimeControlPlan {
  schema_version: 1;
  platform: "linux";
  capabilities: {
    systemd_user: LinuxCapabilityStatus;
    portable_service: LinuxCapabilityStatus;
    tmpfiles_d: LinuxCapabilityStatus;
  };
  blocked_reason: string | null;
  systemd: {
    serviceId: string;
    ownedTarget: string;
    plan: RuntimeServicePlan;
    migrate: boolean;
    legacyCanonicalDigest: string | null;
    upgradeCommands: readonly (readonly string[])[];
  } | null;
}

const LEGACY_CANONICAL_DIGEST = "b6c22afdd859760050cac9a4f621e67b38e0eaca";
const RESTART_BACKOFF_HEADER = `
Restart=on-failure
RestartSec=2s
StartLimitIntervalSec=60
StartLimitBurst=5`;

function canonicalUnit(value: string): string {
  return value
    .replace(/\r/g, "")
    .split("\n")
    .map((line) => line.replace(/\s+/g, " ").trimEnd())
    .filter((line) => line.length > 0)
    .join("\n")
    .trim();
}

function sha1(value: string): string {
  return createHash("sha1").update(value, "utf8").digest("hex");
}

function addBackoff(content: string): string {
  if (
    content.includes("RestartSec=") &&
    content.includes("StartLimitIntervalSec=")
  )
    return content;
  return content.replace(/Restart=on-failure\n?/, RESTART_BACKOFF_HEADER);
}

export function planLinuxRuntimeControl(input: {
  layout: RuntimeInstallLayout;
  host: LinuxHostCapabilities;
  currentUnit?: string | null;
}): LinuxRuntimeControlPlan {
  if (input.layout.platform !== "linux")
    throw new Error("linux_plan_platform_mismatch");

  if (!input.host.systemd) {
    return {
      schema_version: 1,
      platform: "linux",
      capabilities: {
        systemd_user: "unavailable",
        portable_service: input.host.portables ? "available" : "unavailable",
        tmpfiles_d: input.host.tmpfilesD ? "available" : "unavailable",
      },
      blocked_reason: "linux_systemd_user_unavailable",
      systemd: null,
    };
  }

  const plan = planUserService(input.layout);
  if (plan.status !== "ready" || plan.service_file === null)
    throw new Error(plan.blocked_reason ?? "linux_service_plan_blocked");
  plan.service_file.content = addBackoff(plan.service_file.content);

  const current = input.currentUnit ?? null;
  const same =
    current !== null &&
    canonicalUnit(current) === canonicalUnit(plan.service_file.content);
  const legacy =
    current !== null &&
    !same &&
    sha1(canonicalUnit(current)) === LEGACY_CANONICAL_DIGEST;
  const upgradeCommands = same
    ? []
    : legacy
      ? [
          ["systemctl", "--user", "stop", "one-memory.service"] as const,
          [
            "systemctl",
            "--user",
            "enable",
            "--now",
            "one-memory.service",
          ] as const,
        ]
      : [];

  return {
    schema_version: 1,
    platform: "linux",
    capabilities: {
      systemd_user: "available",
      portable_service: input.host.portables ? "available" : "unavailable",
      tmpfiles_d: input.host.tmpfilesD ? "available" : "unavailable",
      ...(input.host.systemd ? {} : {}),
    },
    blocked_reason: null,
    systemd: {
      serviceId: "one-memory.service",
      ownedTarget: "one-memory.service",
      plan,
      migrate: legacy,
      legacyCanonicalDigest: current === null ? null : LEGACY_CANONICAL_DIGEST,
      upgradeCommands,
    },
  };
}

export async function inspectLinuxRuntimeControl(input: {
  layout: RuntimeInstallLayout;
  host: LinuxHostCapabilities;
  unitPath?: string;
}): Promise<LinuxRuntimeControlPlan> {
  let unit: string | null = null;
  if (input.unitPath) {
    try {
      unit = await readFile(input.unitPath, "utf8");
    } catch {
      unit = null;
    }
  }
  return planLinuxRuntimeControl({
    layout: input.layout,
    host: input.host,
    currentUnit: unit,
  });
}

export type { RuntimeInstallLayout };
