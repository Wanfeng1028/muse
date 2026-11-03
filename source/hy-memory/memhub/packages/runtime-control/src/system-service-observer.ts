import { execFile } from "node:child_process";
import os from "node:os";
import path from "node:path";

export type SystemEligibility =
  | "registered"
  | "requires_approval"
  | "not_registered"
  | "unknown";

export interface SystemServiceObservation {
  schemaVersion: 1;
  systemEligibility: SystemEligibility;
  code: string;
}

/** Eligibility only: not loaded-job identity, runtime health or operation proof.
 * helperPath must come from the caller's verified, immutable artifact registry.
 */
export async function observeSystemService(options: {
  helperPath: string;
  home: string;
  uid: number;
}): Promise<SystemServiceObservation> {
  if (process.platform !== "darwin")
    return unknown("system_observer_unsupported");
  const { helperPath, home, uid } = options;
  try {
    const account = os.userInfo();
    if (
      !Number.isSafeInteger(uid) ||
      uid <= 0 ||
      process.getuid?.() !== uid ||
      process.geteuid?.() !== uid ||
      account.uid !== uid ||
      !safeAbsolute(home) ||
      !home.startsWith("/Users/") ||
      home !== os.homedir() ||
      home !== account.homedir
    ) {
      return unknown("system_observer_identity_mismatch");
    }
  } catch {
    return unknown("system_observer_identity_mismatch");
  }
  if (!safeAbsolute(helperPath))
    return unknown("system_observer_helper_invalid");
  let response: { stdout: string; stderr: string };
  try {
    response = await new Promise((resolve, reject) => {
      execFile(
        helperPath,
        ["--status"],
        {
          encoding: "utf8",
          timeout: 2000,
          maxBuffer: 4096,
          killSignal: "SIGKILL",
          shell: false,
          env: { HOME: home, PATH: "/usr/bin:/bin", LANG: "C", LC_ALL: "C" },
        },
        (error, stdout, stderr) => {
          if (error) reject(error);
          else resolve({ stdout, stderr });
        },
      );
    });
  } catch {
    return unknown("system_observer_unavailable");
  }
  try {
    if (
      typeof response.stdout !== "string" ||
      typeof response.stderr !== "string" ||
      response.stderr !== "" ||
      Buffer.byteLength(response.stdout) > 4096
    ) {
      return unknown("system_observer_invalid_response");
    }
    const value: unknown = JSON.parse(response.stdout);
    if (
      !value ||
      typeof value !== "object" ||
      Array.isArray(value) ||
      Object.keys(value).length !== 2 ||
      !Object.hasOwn(value, "schemaVersion") ||
      !Object.hasOwn(value, "systemEligibility")
    )
      return unknown("system_observer_invalid_response");
    const item = value as Record<string, unknown>;
    if (item.schemaVersion !== 1 || !isEligibility(item.systemEligibility)) {
      return unknown("system_observer_invalid_response");
    }
    // The helper has a canonical two-field wire format; this also rejects duplicate keys.
    if (
      response.stdout.trim() !==
      JSON.stringify({
        schemaVersion: 1,
        systemEligibility: item.systemEligibility,
      })
    ) {
      return unknown("system_observer_invalid_response");
    }
    return {
      schemaVersion: 1,
      systemEligibility: item.systemEligibility,
      code:
        item.systemEligibility === "unknown"
          ? "system_eligibility_unknown"
          : "system_eligibility_observed",
    };
  } catch {
    return unknown("system_observer_invalid_response");
  }
}

function isEligibility(value: unknown): value is SystemEligibility {
  return (
    value === "registered" ||
    value === "requires_approval" ||
    value === "not_registered" ||
    value === "unknown"
  );
}

function safeAbsolute(value: string): boolean {
  return (
    typeof value === "string" &&
    path.isAbsolute(value) &&
    path.normalize(value) === value &&
    value !== "/" &&
    !value.endsWith("/") &&
    !/[\0\r\n]/.test(value)
  );
}

function unknown(code: string): SystemServiceObservation {
  return { schemaVersion: 1, systemEligibility: "unknown", code };
}
