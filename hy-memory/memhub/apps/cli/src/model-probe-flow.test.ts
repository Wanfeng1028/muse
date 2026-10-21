import { describe, expect, it, vi } from "vitest";

import type { CoreReader } from "./core-client.js";
import type { CoreOperations } from "./core-operations.js";
import {
  executeModelProbe,
  planModelProbe,
  readModelProbeReceipt,
} from "./model-probe-flow.js";

const PROFILE_ID = "22222222-2222-4222-8222-222222222222";

const PROFILE = {
  profile_id: PROFILE_ID,
  name: "Synthetic",
  provider_kind: "openai_compatible",
  base_url: "https://example.invalid/v1",
  model: "synthetic-model",
  embedding_model: null,
  embedding_provider_kind: null,
  embedding_base_url: null,
  embedding_dimensions: null,
  has_api_key: true,
  credential_state: "available",
  timeout_seconds: 30,
  max_concurrency: 1,
  context_window: null,
  disable_thinking: true,
  capabilities: {
    endpoint_reachable: false,
    model_available: false,
    structured_output: false,
    embedding_available: false,
  },
  revision: 3,
  is_active: false,
  created_at: "2026-09-19T00:00:00Z",
  updated_at: "2026-09-19T00:00:00Z",
};

function notFound(operationId: string) {
  return {
    schema_version: 1,
    operation_id: operationId,
    profile_id: null,
    expected_profile_revision: null,
    state: "not_found",
    result: null,
    code: null,
    stale: null,
  };
}

function completed(operationId: string) {
  return {
    schema_version: 1,
    operation_id: operationId,
    profile_id: PROFILE_ID,
    expected_profile_revision: 3,
    state: "completed",
    result: {
      profile_id: PROFILE_ID,
      profile_revision: 3,
      input_profile_revision: 3,
      stages: [
        {
          stage: "authentication",
          ok: false,
          code: "missing_api_key",
          latency_ms: 0,
          embedding_dimensions: null,
        },
      ],
      capabilities: {
        endpoint_reachable: false,
        model_available: false,
        structured_output: false,
        embedding_available: false,
      },
    },
    code: null,
    stale: false,
  };
}

describe("model probe operation flow", () => {
  it("plans against the exact current profile revision", async () => {
    const reader = vi.fn().mockResolvedValue({ state: "ok", data: [PROFILE] });
    const document = await planModelProbe(reader as CoreReader, PROFILE_ID);
    expect(document.state).toBe("preview");
    if (document.state !== "preview") throw new Error("expected preview");
    expect(document.plan).toMatchObject({
      kind: "model_profile_probe",
      profile_id: PROFILE_ID,
      expected_profile_revision: 3,
    });
    expect(document.plan.operation_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
    expect(document.plan.digest).toMatch(/^[0-9a-f]{64}$/);
  });

  it("proves operation support with schema-1 not_found before posting", async () => {
    const planned = await planModelProbe(
      vi.fn().mockResolvedValue({ state: "ok", data: [PROFILE] }) as CoreReader,
      PROFILE_ID,
    );
    if (planned.state !== "preview") throw new Error("expected preview");
    const operationId = planned.plan.operation_id;
    const reader = vi
      .fn()
      .mockResolvedValueOnce({ state: "ok", data: notFound(operationId) });
    const post = vi
      .fn()
      .mockResolvedValue({ state: "committed", data: completed(operationId) });

    const result = await executeModelProbe(
      planned.plan,
      reader as CoreReader,
      { post } as CoreOperations,
    );

    expect(result.state).toBe("completed");
    expect(reader).toHaveBeenCalledWith(
      `/api/v1/model-probe-operations/${operationId}`,
    );
    expect(post).toHaveBeenCalledWith(
      `/api/v1/model-profiles/${PROFILE_ID}/probe`,
      { operation_id: operationId, expected_profile_revision: 3 },
    );
  });

  it("does not post when the Core lacks the exact operation contract", async () => {
    const planned = await planModelProbe(
      vi.fn().mockResolvedValue({ state: "ok", data: [PROFILE] }) as CoreReader,
      PROFILE_ID,
    );
    if (planned.state !== "preview") throw new Error("expected preview");
    const post = vi.fn();
    const result = await executeModelProbe(
      planned.plan,
      vi.fn().mockResolvedValue({
        state: "not_found",
        code: "http_404",
      }) as CoreReader,
      { post } as CoreOperations,
    );
    expect(result).toMatchObject({
      state: "disabled",
      code: "model_probe_operations_unsupported",
    });
    expect(post).not.toHaveBeenCalled();
  });

  it("does not post when a legacy Core returns a non-operation body", async () => {
    const planned = await planModelProbe(
      vi.fn().mockResolvedValue({ state: "ok", data: [PROFILE] }) as CoreReader,
      PROFILE_ID,
    );
    if (planned.state !== "preview") throw new Error("expected preview");
    const post = vi.fn();
    const result = await executeModelProbe(
      planned.plan,
      vi.fn().mockResolvedValue({
        state: "ok",
        data: { detail: "legacy_route_shape" },
      }) as CoreReader,
      { post } as CoreOperations,
    );
    expect(result).toMatchObject({
      state: "disabled",
      code: "model_probe_operations_unsupported",
    });
    expect(post).not.toHaveBeenCalled();
  });

  it("reconciles an unknown POST by GET and never treats not_found as replay permission", async () => {
    const planned = await planModelProbe(
      vi.fn().mockResolvedValue({ state: "ok", data: [PROFILE] }) as CoreReader,
      PROFILE_ID,
    );
    if (planned.state !== "preview") throw new Error("expected preview");
    const operationId = planned.plan.operation_id;
    const reader = vi
      .fn()
      .mockResolvedValueOnce({ state: "ok", data: notFound(operationId) })
      .mockResolvedValueOnce({ state: "ok", data: notFound(operationId) });
    const post = vi.fn().mockResolvedValue({
      state: "unknown",
      code: "transport_result_unknown",
    });
    const result = await executeModelProbe(
      planned.plan,
      reader as CoreReader,
      { post } as CoreOperations,
    );
    expect(result).toMatchObject({
      state: "unknown",
      code: "model_probe_receipt_not_found_after_attempt",
    });
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("strictly rejects a receipt whose result revision is not bound to the input", async () => {
    const operationId = "11111111-1111-4111-8111-111111111111";
    const malformed = completed(operationId);
    malformed.result.profile_revision = 8;
    const result = await readModelProbeReceipt(
      vi.fn().mockResolvedValue({
        state: "ok",
        data: malformed,
      }) as CoreReader,
      operationId,
    );
    expect(result).toMatchObject({
      state: "unknown",
      code: "model_probe_receipt_invalid",
    });
  });
});
