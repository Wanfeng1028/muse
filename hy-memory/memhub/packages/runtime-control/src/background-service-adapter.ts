import { verifyBackgroundArtifact } from "./background-artifact.js";
import type { BackgroundOperationAdapter } from "./background-controller.js";
import {
  type BackgroundHealth,
  inspectBackgroundHealth,
} from "./background-health.js";
import type { BackgroundIntent } from "./background-operation.js";
import type {
  BackgroundPlanRegistry,
  TrustedBackgroundPlan,
} from "./background-plan.js";
import type { BackgroundRegistrationStatus } from "./background-status.js";
import { installUserService, uninstallUserService } from "./service-install.js";
import type {
  RuntimeInstallLayout,
  RuntimeServicePlan,
} from "./service-plan.js";

interface Options {
  registration(
    plan: TrustedBackgroundPlan,
  ): Promise<BackgroundRegistrationStatus>;
  verifyArtifact?: (
    layout: RuntimeInstallLayout,
  ) => Promise<{ digest: string; root: string; version: string }>;
  health?: (options: { dataDir: string }) => Promise<BackgroundHealth>;
  install?: (
    layout: RuntimeInstallLayout,
    options: { uid: number },
  ) => Promise<RuntimeServicePlan>;
  uninstall?: (
    layout: RuntimeInstallLayout,
    options: { uid: number },
  ) => Promise<"removed" | "not-installed">;
}

/** Internal guarded wiring to the existing installer, not a public mutation API.
 * Requires trusted OS observation; unknown is never treated as absent. Full
 * loaded-job provenance is not yet available, so inspect never attests applied.
 * Do not expose this adapter as enabled UI until that remaining gate is resolved.
 */
export class BackgroundServiceAdapter implements BackgroundOperationAdapter {
  constructor(
    private readonly plans: BackgroundPlanRegistry,
    private readonly options: Options,
  ) {}
  async check(intent: Readonly<BackgroundIntent>): Promise<boolean> {
    try {
      const plan = this.plans.resolve(intent);
      const artifact = await (
        this.options.verifyArtifact ?? verifyBackgroundArtifact
      )(plan.layout);
      if (
        artifact.digest !== intent.artifactDigest ||
        artifact.root !== plan.artifact.root ||
        artifact.version !== plan.artifact.version
      )
        return false;
      const status = await this.options.registration(plan);
      if (
        status.serviceId !== plan.service.service_id ||
        status.reason !== null
      )
        return false;
      if (intent.action === "disable")
        return (
          status.file === "managed" && status.registration === "registered"
        );
      if (status.file !== "absent" || status.registration !== "absent")
        return false;
      const health = await (this.options.health ?? inspectBackgroundHealth)({
        dataDir: plan.layout.dataDir,
      });
      return health.state === "stopped" && health.core === "stopped";
    } catch {
      return false;
    }
  }
  async apply(intent: Readonly<BackgroundIntent>): Promise<void> {
    // Resolve first preserves consumed/expired diagnostics instead of reducing
    // an attempted repeat to a misleading change of plan.
    const plan = this.plans.resolve(intent);
    if (!(await this.check(intent))) throw Error("background_plan_changed");
    this.plans.markApplying(intent);
    if (intent.action === "enable") {
      await (this.options.install ?? installUserService)(plan.layout, {
        uid: plan.uid,
      });
    } else {
      await (this.options.uninstall ?? uninstallUserService)(plan.layout, {
        uid: plan.uid,
      });
    }
  }
  async inspect(
    intent: Readonly<BackgroundIntent>,
  ): Promise<"unknown" | "conflict"> {
    const plan = this.plans.inspect(intent);
    if (!plan) return "unknown";
    try {
      const artifact = await (
        this.options.verifyArtifact ?? verifyBackgroundArtifact
      )(plan.layout);
      if (
        artifact.digest !== intent.artifactDigest ||
        artifact.root !== plan.artifact.root ||
        artifact.version !== plan.artifact.version
      )
        return "conflict";
      const registration = await this.options.registration(plan);
      if (
        registration.file === "conflict" ||
        registration.registration === "conflict"
      )
        return "conflict";
      // SM eligibility + healthy detached Runtime is not evidence that launchd
      // loaded this exact operation. Absence cannot prove no earlier effect.
      return "unknown";
    } catch {
      return "unknown";
    }
  }
}
