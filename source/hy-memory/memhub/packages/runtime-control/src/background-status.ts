import { constants } from "node:fs";
import { lstat, open } from "node:fs/promises";
import path from "node:path";
import {
  planUserService,
  RUNTIME_SERVICE_ID,
  type RuntimeInstallLayout,
} from "./service-plan.js";

export type BackgroundRegistration =
  | "absent"
  | "registered"
  | "requires_approval"
  | "disabled_by_system"
  | "conflict"
  | "unknown";
export type LegacyBackgroundRegistration =
  | "not_registered"
  | "enabled"
  | "requires_approval"
  | "disabled_by_system"
  | "unknown";

export interface BackgroundRegistrationStatus {
  serviceId: string;
  file: "absent" | "managed" | "conflict" | "unknown";
  registration: BackgroundRegistration;
  runtime: "not_checked";
  reason: string | null;
}

/** Read-only declaration/registration projection; never installs or starts.
 * OS observation must come from the trusted control layer, not renderer input.
 * A managed plist is not proof of OS registration, Core/Broker health or consent.
 */
export async function inspectBackgroundRegistration(
  layout: RuntimeInstallLayout,
  options: {
    uid?: number;
    legacy?: LegacyBackgroundRegistration;
    observe?: (serviceId: string) => Promise<BackgroundRegistration>;
  } = {},
): Promise<BackgroundRegistrationStatus> {
  const base: BackgroundRegistrationStatus = {
    serviceId: RUNTIME_SERVICE_ID,
    file: "unknown",
    registration: "unknown",
    runtime: "not_checked",
    reason: null,
  };
  if (layout.platform !== "darwin")
    return { ...base, reason: "background_platform_unverified" };
  const plan = planUserService(layout, { uid: options.uid });
  if (!plan.service_file || plan.status !== "ready") {
    return { ...base, reason: plan.blocked_reason };
  }
  // The label is derived from the install root, so observe the one this plan
  // actually declares rather than the canonical daily label.
  const serviceId = plan.service_id;
  const before = await declarationStamp(plan.service_file.path);
  const file = await inspectDeclaration(
    plan.service_file.path,
    plan.service_file.content,
  );
  if (file === "conflict")
    return {
      ...base,
      file,
      registration: "conflict",
      reason: "service_declaration_conflict",
    };
  if (file === "unknown")
    return { ...base, file, reason: "service_declaration_unavailable" };
  if (options.legacy === undefined || options.legacy === "unknown") {
    return { ...base, file, reason: "legacy_registration_unknown" };
  }
  if (options.legacy !== "not_registered") {
    return {
      ...base,
      file,
      registration: "conflict",
      reason: "legacy_registration_conflict",
    };
  }
  if (!options.observe)
    return { ...base, file, reason: "system_registration_not_checked" };
  try {
    const registration = await options.observe(serviceId);
    const after = await declarationStamp(plan.service_file.path);
    if (before === undefined || after === undefined || before !== after) {
      return {
        ...base,
        serviceId,
        file: "unknown",
        reason: "service_declaration_changed",
      };
    }
    if (
      ![
        "absent",
        "registered",
        "requires_approval",
        "disabled_by_system",
        "conflict",
        "unknown",
      ].includes(registration)
    ) {
      return { ...base, file, reason: "system_registration_unavailable" };
    }
    if (
      file === "absent" &&
      registration !== "absent" &&
      registration !== "unknown"
    ) {
      return {
        ...base,
        serviceId,
        file,
        registration: "conflict",
        reason: "system_registration_without_declaration",
      };
    }
    return { ...base, serviceId, file, registration };
  } catch {
    return {
      ...base,
      serviceId,
      file,
      reason: "system_registration_unavailable",
    };
  }
}

async function inspectDeclaration(
  target: string,
  expected: string,
): Promise<BackgroundRegistrationStatus["file"]> {
  try {
    const metadata = await lstat(target);
    const parent = await lstat(path.dirname(target));
    const uid = process.getuid?.();
    if (
      !metadata.isFile() ||
      metadata.isSymbolicLink() ||
      metadata.nlink !== 1 ||
      metadata.size > 65536 ||
      (metadata.mode & 0o077) !== 0 ||
      (uid !== undefined && metadata.uid !== uid) ||
      !parent.isDirectory() ||
      parent.isSymbolicLink() ||
      (parent.mode & 0o022) !== 0 ||
      (uid !== undefined && parent.uid !== uid)
    )
      return "conflict";
    const handle = await open(
      target,
      constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
    );
    try {
      const opened = await handle.stat();
      if (
        !opened.isFile() ||
        opened.nlink !== 1 ||
        opened.mode !== metadata.mode ||
        opened.uid !== metadata.uid ||
        opened.ino !== metadata.ino ||
        opened.dev !== metadata.dev
      )
        return "unknown";
      const buffer = Buffer.alloc(65537);
      let total = 0;
      while (total < buffer.length) {
        const { bytesRead } = await handle.read(
          buffer,
          total,
          buffer.length - total,
          total,
        );
        if (!bytesRead) break;
        total += bytesRead;
      }
      if (total !== metadata.size || total > 65536) return "unknown";
      const text = new TextDecoder("utf-8", { fatal: true }).decode(
        buffer.subarray(0, total),
      );
      const current = await lstat(target);
      if (
        current.ino !== metadata.ino ||
        current.dev !== metadata.dev ||
        current.size !== metadata.size ||
        current.mtimeMs !== metadata.mtimeMs ||
        current.ctimeMs !== metadata.ctimeMs ||
        current.mode !== metadata.mode ||
        current.uid !== metadata.uid ||
        current.nlink !== 1
      )
        return "unknown";
      return text === expected ? "managed" : "conflict";
    } finally {
      await handle.close();
    }
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") return "absent";
    if (code === "ELOOP") return "conflict";
    return "unknown";
  }
}

async function declarationStamp(
  target: string,
): Promise<string | null | undefined> {
  try {
    const info = await lstat(target);
    return JSON.stringify([
      info.dev,
      info.ino,
      info.mode,
      info.uid,
      info.nlink,
      info.size,
      info.mtimeMs,
      info.ctimeMs,
    ]);
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "ENOENT"
      ? null
      : undefined;
  }
}
