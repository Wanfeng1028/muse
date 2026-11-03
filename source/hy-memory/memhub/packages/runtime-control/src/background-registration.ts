import { lstat } from "node:fs/promises";
import path from "node:path";
import { verifyBackgroundArtifact } from "./background-artifact.js";
import type { TrustedBackgroundPlan } from "./background-plan.js";
import {
  type BackgroundRegistrationStatus,
  inspectBackgroundRegistration,
  type LegacyBackgroundRegistration,
} from "./background-status.js";
import {
  observeSystemService,
  type SystemServiceObservation,
} from "./system-service-observer.js";

interface Options {
  legacy: LegacyBackgroundRegistration;
  verifyArtifact?: typeof verifyBackgroundArtifact;
  observe?: typeof observeSystemService;
  inspectDeclaration?: typeof inspectBackgroundRegistration;
}

/** Public OS eligibility is separate from proof of a loaded operation. */
export async function inspectPlannedBackgroundRegistration(
  plan: TrustedBackgroundPlan,
  options: Options,
): Promise<BackgroundRegistrationStatus> {
  const unknown: BackgroundRegistrationStatus = {
    serviceId: plan.service.service_id,
    file: "unknown",
    registration: "unknown",
    runtime: "not_checked",
    reason: "system_registration_unavailable",
  };
  const verify = options.verifyArtifact ?? verifyBackgroundArtifact;
  const inspect = options.inspectDeclaration ?? inspectBackgroundRegistration;
  try {
    const before = await verify(plan.layout);
    if (!matches(before, plan))
      return { ...unknown, reason: "background_artifact_changed" };
    const helperPath = path.join(before.root, "runtime/service-observer");
    const helper = await lstat(helperPath);
    if (
      !helper.isFile() ||
      helper.isSymbolicLink() ||
      helper.nlink !== 1 ||
      (helper.mode & 0o111) === 0 ||
      (helper.mode & 0o022) !== 0 ||
      helper.uid !== process.getuid?.()
    )
      return unknown;
    let observation: SystemServiceObservation | undefined;
    const first = await inspect(plan.layout, {
      uid: plan.uid,
      legacy: options.legacy,
      observe: async () => {
        observation = await (options.observe ?? observeSystemService)({
          helperPath,
          home: plan.layout.home,
          uid: plan.uid,
        });
        const status = observation.systemEligibility;
        return status === "not_registered" ? "absent" : status;
      },
    });
    if (!observation) return first;
    // Re-read the declaration around the native URL-based check. The API takes
    // a URL, not a descriptor, so changes invalidate this observed snapshot.
    const last = await inspect(plan.layout, {
      uid: plan.uid,
      legacy: options.legacy,
      observe: async () => first.registration,
    });
    const after = await verify(plan.layout);
    if (!matches(after, plan) || JSON.stringify(first) !== JSON.stringify(last))
      return { ...unknown, reason: "background_registration_changed" };
    return first;
  } catch {
    return unknown;
  }
}

function matches(
  value: { digest: string; root: string; version: string },
  plan: TrustedBackgroundPlan,
): boolean {
  return (
    value.digest === plan.intent.artifactDigest &&
    value.root === plan.artifact.root &&
    value.version === plan.artifact.version
  );
}
