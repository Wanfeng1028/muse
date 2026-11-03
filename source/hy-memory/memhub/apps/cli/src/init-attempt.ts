import path from "node:path";

/** Where the interactive `init` wizard keeps its durable attempt fence.
 *
 * The wizard originally passed a CWD-relative singleton (`init`) to
 * `claimPlanAttempt`. That shared one fence across unrelated runs and let a
 * stale `init.one-memory-attempt` in the working directory turn every later
 * wizard run into "交互计划无效 / exit 2". Keep the fence under the Runtime's
 * data dir, keyed by the operation id, exactly like `init --source --import`.
 */
export function interactiveInitAttemptPath(
  dataDir: string,
  operationId: string,
): string {
  return path.join(dataDir, `.cli-init-attempt-${operationId}`);
}
