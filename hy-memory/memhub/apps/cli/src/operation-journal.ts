import { constants } from "node:fs";
import { type FileHandle, open } from "node:fs/promises";
import { readBoundedJson } from "./bounded-file.js";

export type PlanAttempt = {
  schema_version: 1;
  operation_id: string;
  plan_digest: string;
};

/**
 * Durable client fence written before a mutating request. Once present, the
 * same plan may only query its operation receipt; it is never blindly posted
 * again after an unknown result.
 */
export async function claimPlanAttempt(
  planFile: string,
  attempt: PlanAttempt,
): Promise<"first" | "prior" | "invalid"> {
  const journal = `${planFile}.one-memory-attempt`;
  let handle: FileHandle;
  try {
    handle = await open(
      journal,
      constants.O_WRONLY |
        constants.O_CREAT |
        constants.O_EXCL |
        (constants.O_NOFOLLOW ?? 0),
      0o600,
    );
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") return "invalid";
    const current = await readBoundedJson(journal, 1024);
    return sameAttempt(current, attempt) ? "prior" : "invalid";
  }
  try {
    await handle.writeFile(`${JSON.stringify(attempt)}\n`, "utf8");
    await handle.sync();
    return "first";
  } catch {
    return "invalid";
  } finally {
    await handle.close().catch(() => undefined);
  }
}

function sameAttempt(value: unknown, expected: PlanAttempt): boolean {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    (value as Record<string, unknown>).schema_version === 1 &&
    (value as Record<string, unknown>).operation_id === expected.operation_id &&
    (value as Record<string, unknown>).plan_digest === expected.plan_digest &&
    Object.keys(value).length === 3
  );
}
