import { createHash, randomUUID } from "node:crypto";
import path from "node:path";
import { performance } from "node:perf_hooks";
import {
  type BackgroundIntent,
  type BackgroundOwner,
  validateBackgroundIntent,
  validateBackgroundOwner,
} from "./background-operation.js";
import {
  planUserService,
  type RuntimeInstallLayout,
  type RuntimeServicePlan,
  runtimeInstallLayout,
} from "./service-plan.js";

interface ArtifactIdentity {
  digest: string;
  version: string;
  root: string;
}
export interface TrustedBackgroundPlan {
  intent: BackgroundIntent;
  layout: RuntimeInstallLayout;
  service: RuntimeServicePlan;
  artifact: ArtifactIdentity;
  owner: BackgroundOwner;
  uid: number;
}
export interface BackgroundPreview {
  intent: BackgroundIntent;
  version: string;
  startAtLogin: boolean;
}
interface Entry {
  plan: TrustedBackgroundPlan;
  expires: number;
  consumed: boolean;
}

/** Short-lived trusted plan registry; never accepts executable paths from renderer.
 * It does not attest artifact bytes or OS state; callers verify those separately.
 * Reopened-process recovery reconstructs plans from trusted installed artifacts,
 * not from public previews. No unverified preview can restore this registry.
 */
export class BackgroundPlanRegistry {
  private readonly entries = new Map<string, Entry>();
  private readonly owner: BackgroundOwner;
  private readonly layout: RuntimeInstallLayout;
  private lastTime = -Infinity;
  constructor(
    owner: BackgroundOwner,
    layout: RuntimeInstallLayout,
    private readonly uid: number,
    private readonly options: { clock?: () => number } = {},
  ) {
    validateBackgroundOwner(owner);
    if (layout.platform !== "darwin" || !Number.isSafeInteger(uid) || uid < 1)
      throw Error("background_plan_platform_unverified");
    if (!path.isAbsolute(layout.home) || !path.isAbsolute(layout.installRoot))
      throw Error("background_plan_layout_invalid");
    const expected = runtimeInstallLayout({
      platform: layout.platform,
      home: layout.home,
      installRoot: layout.installRoot,
      dataDir: layout.dataDir,
    });
    if (
      Object.keys(layout).length !== Object.keys(expected).length ||
      Object.entries(expected).some(
        ([key, value]) => layout[key as keyof RuntimeInstallLayout] !== value,
      )
    )
      throw Error("background_plan_layout_invalid");
    this.owner = Object.freeze({ ...owner });
    this.layout = Object.freeze({ ...layout });
  }
  create(
    action: BackgroundIntent["action"],
    expectedRevision: number,
    artifact: ArtifactIdentity,
  ): BackgroundPreview {
    const now = this.now();
    for (const [key, entry] of this.entries)
      if (entry.expires <= now) this.entries.delete(key);
    if (this.entries.size >= 16) throw Error("background_plan_capacity");
    if (
      !/^[a-f0-9]{64}$/.test(artifact.digest) ||
      !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/.test(artifact.version) ||
      !path.isAbsolute(artifact.root)
    )
      throw Error("background_plan_artifact_invalid");
    const service = planUserService(this.layout, { uid: this.uid });
    const planDigest = createHash("sha256")
      .update(
        JSON.stringify([
          "background-plan-v1",
          this.owner.userId,
          this.owner.runtimeId,
          this.uid,
          Object.keys(this.layout)
            .sort()
            .map((key) => [
              key,
              this.layout[key as keyof RuntimeInstallLayout],
            ]),
          service,
          action,
          artifact.digest,
          artifact.version,
          artifact.root,
        ]),
      )
      .digest("hex");
    const intent = {
      operationId: randomUUID(),
      expectedRevision,
      action,
      planDigest,
      artifactDigest: artifact.digest,
    };
    validateBackgroundIntent(intent);
    this.entries.set(intent.operationId, {
      plan: structuredClone({
        intent,
        layout: this.layout,
        service,
        artifact,
        owner: this.owner,
        uid: this.uid,
      }),
      expires: now + 300,
      consumed: false,
    });
    return {
      intent: { ...intent },
      version: artifact.version,
      startAtLogin: action === "enable",
    };
  }
  resolve(intent: BackgroundIntent): TrustedBackgroundPlan {
    const entry = this.entry(intent);
    if (entry.consumed) throw Error("background_plan_consumed");
    return structuredClone(entry.plan);
  }
  markApplying(intent: BackgroundIntent): void {
    const entry = this.entry(intent);
    if (entry.consumed) throw Error("background_plan_consumed");
    entry.consumed = true;
  }
  inspect(intent: BackgroundIntent): TrustedBackgroundPlan | null {
    try {
      return structuredClone(this.entry(intent).plan);
    } catch {
      return null;
    }
  }
  private entry(intent: BackgroundIntent): Entry {
    validateBackgroundIntent(intent);
    const now = this.now(),
      entry = this.entries.get(intent.operationId);
    if (!entry || entry.expires <= now) throw Error("background_plan_expired");
    const saved = entry.plan.intent;
    if (
      saved.action !== intent.action ||
      saved.expectedRevision !== intent.expectedRevision ||
      saved.planDigest !== intent.planDigest ||
      saved.artifactDigest !== intent.artifactDigest
    )
      throw Error("background_plan_changed");
    return entry;
  }
  private now(): number {
    const now = (this.options.clock ?? (() => performance.now() / 1000))();
    if (!Number.isFinite(now) || now < this.lastTime)
      throw Error("background_plan_clock_invalid");
    this.lastTime = now;
    return now;
  }
}
