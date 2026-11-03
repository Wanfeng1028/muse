import { verifyBackgroundArtifact } from "./background-artifact.js";
import type {
  BackgroundOperationLedger,
  BackgroundOwner,
} from "./background-operation.js";
import {
  validateBackgroundOwner,
  validateBackgroundSnapshot,
} from "./background-operation.js";
import {
  BackgroundPlanRegistry,
  type BackgroundPreview,
} from "./background-plan.js";
import type { RuntimeInstallLayout } from "./service-plan.js";

/** Preview is read-only: no ledger initialization, OS registration or model use. */
export class BackgroundPreviewService {
  readonly plans: BackgroundPlanRegistry;
  private readonly owner: BackgroundOwner;
  private readonly layout: RuntimeInstallLayout;
  constructor(
    owner: BackgroundOwner,
    layout: RuntimeInstallLayout,
    uid: number,
    private readonly ledger: Pick<BackgroundOperationLedger, "load">,
    private readonly verify: typeof verifyBackgroundArtifact = verifyBackgroundArtifact,
  ) {
    validateBackgroundOwner(owner);
    this.owner = Object.freeze({ ...owner });
    this.layout = Object.freeze({ ...layout });
    this.plans = new BackgroundPlanRegistry(this.owner, this.layout, uid);
  }
  async preview(input: unknown): Promise<BackgroundPreview> {
    if (
      !input ||
      typeof input !== "object" ||
      Array.isArray(input) ||
      Object.keys(input).length !== 1 ||
      !Object.hasOwn(input, "startAtLogin") ||
      typeof (input as { startAtLogin: unknown }).startAtLogin !== "boolean"
    ) {
      throw Error("background_preview_invalid");
    }
    const startAtLogin = (input as { startAtLogin: boolean }).startAtLogin;
    const before = await this.read();
    if (
      before &&
      !["committed", "rejected"].includes(
        before.operations[before.operations.length - 1].state,
      )
    )
      throw Error("background_operation_pending");
    const artifact = await this.verify(this.layout);
    const after = await this.read();
    if ((before?.revision ?? 0) !== (after?.revision ?? 0))
      throw Error("background_revision_changed");
    return this.plans.create(
      startAtLogin ? "enable" : "disable",
      after?.revision ?? 0,
      artifact,
    );
  }
  private async read() {
    const snapshot = await this.ledger.load(this.owner);
    return snapshot ? validateBackgroundSnapshot(snapshot, this.owner) : null;
  }
}
