/**
 * Model-profile writes the Web console had but the CLI did not:
 * activate (`POST /model-profiles/{id}/activate`) and edit
 * (`PATCH /model-profiles/{id}`).
 *
 * Core owns the semantics. These flows reuse the same two-phase convention as
 * `models configure`: plan without `--confirm` (or produce a plan file), then
 * apply exactly that plan. The edit body mirrors the Web console's
 * `ModelProfilePatch`, including `expected_revision` as the compare-and-swap
 * guard Core requires.
 */

import { createHash, randomUUID } from "node:crypto";
import type { ModelProfile } from "@one-memory/contracts";
import {
  buildModelProfileUpdateRequest,
  ModelProfileInputError,
  parseModelProfileReceipt,
} from "@one-memory/operations";
import type { CoreOperations, CorePatchOperations } from "./core-operations.js";
import { PRODUCT } from "./version.js";

const PROFILE_ID = /^[A-Za-z0-9][\w.-]{0,127}$/;

export type ModelWritePlan =
  | {
      schema_version: 1;
      kind: "model_profile_activate";
      profile_id: string;
      digest: string;
    }
  | {
      schema_version: 1;
      kind: "model_profile_edit";
      profile_id: string;
      expected_revision: number;
      patch: Record<string, unknown>;
      digest: string;
    };

export type ModelWriteDocument =
  | {
      schema_version: 1;
      product: string;
      state: "preview";
      plan: ModelWritePlan;
    }
  | {
      schema_version: 1;
      product: string;
      state: "committed";
      operation_id: string;
      receipt: Record<string, unknown>;
    }
  | {
      schema_version: 1;
      product: string;
      state: "rejected" | "unknown" | "invalid";
      operation_id?: string;
      code: string;
    };

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  if (value === undefined) return "null";
  return JSON.stringify(value);
}

function digestOf(value: unknown): string {
  return createHash("sha256").update(canonical(value)).digest("hex");
}

function preview(
  plan:
    | Omit<
        Extract<ModelWritePlan, { kind: "model_profile_activate" }>,
        "digest"
      >
    | Omit<Extract<ModelWritePlan, { kind: "model_profile_edit" }>, "digest">,
): ModelWriteDocument {
  return {
    schema_version: 1,
    product: PRODUCT,
    state: "preview",
    plan: { ...plan, digest: digestOf(plan) } as ModelWritePlan,
  };
}

function invalid(code: string): ModelWriteDocument {
  return { schema_version: 1, product: PRODUCT, state: "invalid", code };
}

function committed(
  operationId: string,
  profile: ModelProfile,
): ModelWriteDocument {
  return {
    schema_version: 1,
    product: PRODUCT,
    state: "committed",
    operation_id: operationId,
    receipt: projectProfile(profile),
  };
}

function projectProfile(profile: ModelProfile): Record<string, unknown> {
  return {
    profile_id: profile.profile_id,
    name: profile.name,
    provider_kind: profile.provider_kind,
    model: profile.model,
    embedding_model: profile.embedding_model,
    credential_state: profile.credential_state,
    revision: profile.revision,
    is_active: profile.is_active,
  };
}

// --- activate -------------------------------------------------------------

/**
 * Activation has no request body, so the plan carries only the target. There
 * is deliberately no `expected_revision`: Core would never read one, and
 * recording a check it does not perform would be a fake guard.
 */
export function planModelProfileActivate(input: {
  profileId: string;
}): ModelWriteDocument {
  return PROFILE_ID.test(input.profileId)
    ? preview({
        schema_version: 1,
        kind: "model_profile_activate",
        profile_id: input.profileId,
      })
    : invalid("model_profile_activate_input_invalid");
}

export async function executeModelProfileActivate(
  plan: Extract<ModelWritePlan, { kind: "model_profile_activate" }>,
  operations: CoreOperations,
): Promise<ModelWriteDocument> {
  const result = await operations.post<unknown>(
    `/api/v1/model-profiles/${encodeURIComponent(plan.profile_id)}/activate`,
    {},
  );
  return modelProfileResult(plan.profile_id, result);
}

// --- edit -----------------------------------------------------------------

export function planModelProfileEdit(input: {
  profileId: string;
  patch: unknown;
}): ModelWriteDocument {
  // The shared builder owns patch validation (14-key allow-list,
  // expected_revision CAS, field bounds, api_key/clear_api_key exclusivity).
  // A rejected patch is `invalid`, never a plan the caller could confirm.
  let request: ReturnType<typeof buildModelProfileUpdateRequest>;
  try {
    request = buildModelProfileUpdateRequest(input.profileId, input.patch);
  } catch (error) {
    if (error instanceof ModelProfileInputError) {
      return invalid("model_profile_edit_input_invalid");
    }
    throw error;
  }
  const patch = request.body as Record<string, unknown>;
  if (!PROFILE_ID.test(input.profileId)) {
    return invalid("model_profile_edit_input_invalid");
  }
  return preview({
    schema_version: 1,
    kind: "model_profile_edit",
    profile_id: input.profileId,
    expected_revision: patch.expected_revision as number,
    // `api_key` is read from a controlled file at apply time, exactly like
    // `models configure`; the plan never carries the credential. The revision
    // is a top-level field, so it is stripped from the nested patch rather
    // than being duplicated in both places.
    patch: Object.fromEntries(
      Object.entries(patch).filter(
        ([key]) => key !== "api_key" && key !== "expected_revision",
      ),
    ),
  });
}

export async function executeModelProfileEdit(
  plan: Extract<ModelWritePlan, { kind: "model_profile_edit" }>,
  operations: CorePatchOperations,
  apiKey: string | undefined,
): Promise<ModelWriteDocument> {
  // Re-validate through the shared builder at apply time too, so a hand-edited
  // plan cannot smuggle an out-of-bounds patch past the write.
  let request: ReturnType<typeof buildModelProfileUpdateRequest>;
  try {
    request = buildModelProfileUpdateRequest(plan.profile_id, {
      ...plan.patch,
      expected_revision: plan.expected_revision,
      ...(apiKey === undefined ? {} : { api_key: apiKey }),
    });
  } catch (error) {
    if (error instanceof ModelProfileInputError) {
      return invalid("model_profile_edit_input_invalid");
    }
    throw error;
  }
  const result = await operations.patch<unknown>(request.path, request.body);
  return modelProfileResult(plan.profile_id, result);
}

function modelProfileResult(
  operationId: string,
  result:
    | Awaited<ReturnType<CoreOperations["post"]>>
    | Awaited<ReturnType<CorePatchOperations["patch"]>>,
): ModelWriteDocument {
  if (result.state === "rejected") {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "rejected",
      operation_id: operationId,
      code: result.code,
    };
  }
  if (result.state === "unknown") {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "unknown",
      operation_id: operationId,
      code: result.code,
    };
  }
  // The shared parser is the single judge of a model-profile receipt; null
  // means a malformed body, which must be `unknown`, never a committed write.
  const profile = parseModelProfileReceipt(result.data);
  if (!profile) {
    return {
      schema_version: 1,
      product: PRODUCT,
      state: "unknown",
      operation_id: operationId,
      code: "model_profile_receipt_invalid",
    };
  }
  return committed(operationId, profile);
}

export function validateModelWritePlan(value: unknown): ModelWritePlan | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  if (candidate.schema_version !== 1 || typeof candidate.kind !== "string") {
    return null;
  }
  const { digest, ...withoutDigest } = candidate;
  if (typeof digest !== "string" || digest !== digestOf(withoutDigest)) {
    return null;
  }
  switch (candidate.kind) {
    case "model_profile_activate":
      return typeof candidate.profile_id === "string" &&
        PROFILE_ID.test(candidate.profile_id) &&
        Object.keys(candidate).length === 3
        ? (candidate as unknown as ModelWritePlan)
        : null;
    case "model_profile_edit": {
      if (
        typeof candidate.profile_id !== "string" ||
        !PROFILE_ID.test(candidate.profile_id) ||
        !Number.isSafeInteger(candidate.expected_revision)
      ) {
        return null;
      }
      // The shared builder is the single judge of a patch body; the plan must
      // not carry `api_key` (that is read from a controlled file at apply).
      let built: ReturnType<typeof buildModelProfileUpdateRequest>;
      try {
        built = buildModelProfileUpdateRequest(candidate.profile_id, {
          ...(candidate.patch as Record<string, unknown>),
          expected_revision: candidate.expected_revision,
        });
      } catch {
        return null;
      }
      if ("api_key" in built.body) return null;
      return Object.keys(candidate).length === 6
        ? (candidate as unknown as ModelWritePlan)
        : null;
    }
    default:
      return null;
  }
}

export function modelWriteExitCode(document: ModelWriteDocument): number {
  return ["preview", "committed"].includes(document.state) ? 0 : 1;
}

export function renderModelWriteText(document: ModelWriteDocument): string {
  if (document.state === "preview") {
    const plan = document.plan;
    return [
      `预览：${plan.kind}`,
      `目标配置：${plan.profile_id}`,
      `确认摘要：${plan.digest}`,
      "未执行任何写操作。请把 --json 输出保存为 plan 文件，再用对应命令加 --confirm。",
      "",
    ].join("\n");
  }
  if (document.state === "committed") {
    return `已保存模型配置：${document.receipt.profile_id}\nrevision=${document.receipt.revision}\n`;
  }
  return `模型写操作未完成：${document.state}（${document.code}）\n`;
}
