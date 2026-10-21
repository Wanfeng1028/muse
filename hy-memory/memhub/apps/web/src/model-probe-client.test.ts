// @vitest-environment jsdom
import type { ModelProbeOperationReceipt } from "@one-memory/contracts";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { recoverableProbe } from "./model-probe-client";
import {
  readPendingModelProbe,
  savePendingModelProbe,
} from "./pending-model-probe";

const ID = "11111111-1111-4111-8111-111111111111";
const PROFILE = "22222222-2222-4222-8222-222222222222";
const OTHER = "33333333-3333-4333-8333-333333333333";
const pending = { operationId: ID, profileId: PROFILE, inputRevision: 1 };
const KEY = "one-memory.pending-model-probe.v1";
function absent(): ModelProbeOperationReceipt {
  return {
    schema_version: 1,
    operation_id: ID,
    profile_id: null,
    expected_profile_revision: null,
    state: "not_found",
    result: null,
    code: null,
    stale: null,
  };
}
function completed(): ModelProbeOperationReceipt {
  return {
    schema_version: 1,
    operation_id: ID,
    profile_id: PROFILE,
    expected_profile_revision: 1,
    state: "completed",
    code: null,
    stale: false,
    result: {
      profile_id: PROFILE,
      input_profile_revision: 1,
      profile_revision: 2,
      stages: [{ stage: "model", ok: true, code: "ok", latency_ms: 1 }],
      capabilities: {
        endpoint_reachable: true,
        model_available: true,
        structured_output: true,
        embedding_available: true,
      },
    },
  };
}
function transport() {
  return {
    lookup: vi.fn(async (_id: string) => absent()),
    probe: vi.fn(async (_id: string, _request: unknown) => completed()),
  };
}
beforeEach(() => {
  window.localStorage.clear();
  vi.spyOn(crypto, "randomUUID").mockReturnValue(ID);
});
afterEach(() => vi.restoreAllMocks());

it("checks capability, saves/readbacks metadata before exactly one POST, clears confirmed result", async () => {
  const t = transport();
  t.probe.mockImplementation(async (id, request) => {
    expect(id).toBe(PROFILE);
    expect(request).toEqual({ operation_id: ID, expected_profile_revision: 1 });
    expect(readPendingModelProbe()).toEqual(pending);
    return completed();
  });
  expect(await recoverableProbe(PROFILE, 1, t)).toEqual(completed().result);
  expect(t.lookup).toHaveBeenCalledExactlyOnceWith(ID);
  expect(t.probe).toHaveBeenCalledOnce();
  expect(readPendingModelProbe()).toBeNull();
});

it("after lost POST response the next click only GETs the original operation", async () => {
  const t = transport();
  t.probe.mockRejectedValueOnce(Error("SECRET response body"));
  await expect(recoverableProbe(PROFILE, 1, t)).rejects.toThrow(
    "model_probe_operation_pending",
  );
  expect(readPendingModelProbe()).toEqual(pending);
  t.lookup.mockResolvedValue(completed());
  expect(await recoverableProbe(PROFILE, 2, t)).toEqual(completed().result);
  expect(t.probe).toHaveBeenCalledOnce();
  expect(readPendingModelProbe()).toBeNull();
});

it("reopened module recovers matching profile by stored input revision", async () => {
  savePendingModelProbe(pending);
  const t = transport();
  t.lookup.mockResolvedValue(completed());
  vi.resetModules();
  const fresh = await import("./model-probe-client");
  await fresh.recoverableProbe(PROFILE, 2, t);
  expect(t.probe).not.toHaveBeenCalled();
  expect(crypto.randomUUID).not.toHaveBeenCalled();
});

it("another profile cannot overwrite pending or make any request", async () => {
  savePendingModelProbe(pending);
  const t = transport();
  await expect(recoverableProbe(OTHER, 1, t)).rejects.toThrow(
    "model_probe_other_profile_pending",
  );
  expect(t.lookup).not.toHaveBeenCalled();
  expect(t.probe).not.toHaveBeenCalled();
  expect(readPendingModelProbe()).toEqual(pending);
});

it.each(["404", "network", "invalid", "not-absent", "wrong-id"])(
  "fresh capability failure %s never saves or POSTs",
  async (kind) => {
    const t = transport();
    if (kind === "404" || kind === "network")
      t.lookup.mockRejectedValue(Error(`private ${kind}`));
    else
      t.lookup.mockResolvedValue(
        kind === "not-absent"
          ? completed()
          : kind === "wrong-id"
            ? { ...absent(), operation_id: OTHER }
            : ({} as ModelProbeOperationReceipt),
      );
    await expect(recoverableProbe(PROFILE, 1, t)).rejects.toThrow(
      "model_probe_capability_unavailable",
    );
    expect(readPendingModelProbe()).toBeNull();
    expect(t.probe).not.toHaveBeenCalled();
  },
);

it.each(["pending", "not_found", "disconnect"])(
  "recovery %s retains pending without POST",
  async (state) => {
    savePendingModelProbe(pending);
    const t = transport();
    if (state === "disconnect") t.lookup.mockRejectedValue(Error("secret"));
    else
      t.lookup.mockResolvedValue(
        state === "not_found"
          ? absent()
          : {
              ...completed(),
              state: "pending",
              result: null,
            },
      );
    await expect(recoverableProbe(PROFILE, 1, t)).rejects.toThrow(
      "model_probe_operation_pending",
    );
    expect(readPendingModelProbe()).toEqual(pending);
    expect(t.probe).not.toHaveBeenCalled();
  },
);

it.each(["failed", "stale"])(
  "matching terminal %s clears but does not retry",
  async (kind) => {
    savePendingModelProbe(pending);
    const t = transport();
    t.lookup.mockResolvedValue(
      kind === "stale"
        ? { ...completed(), stale: true }
        : {
            ...completed(),
            state: "failed",
            result: null,
            code: "model_probe_profile_changed",
            stale: true,
          },
    );
    await expect(recoverableProbe(PROFILE, 1, t)).rejects.toThrow(
      kind === "stale"
        ? "model_probe_operation_stale"
        : "model_probe_operation_stale",
    );
    expect(readPendingModelProbe()).toBeNull();
    expect(t.probe).not.toHaveBeenCalled();
  },
);

it.each([
  { operation_id: OTHER },
  { profile_id: OTHER },
  { expected_profile_revision: 2 },
  { schema_version: 2 },
  { code: "arbitrary secret" },
  { stale: null },
  { result: null },
  { secret: "extra" },
])("invalid receipt metadata %# retains pending", async (patch) => {
  savePendingModelProbe(pending);
  const t = transport();
  t.lookup.mockResolvedValue({
    ...completed(),
    ...patch,
  } as ModelProbeOperationReceipt);
  await expect(recoverableProbe(PROFILE, 1, t)).rejects.toThrow(
    "model_probe_operation_unavailable",
  );
  expect(readPendingModelProbe()).toEqual(pending);
  expect(t.probe).not.toHaveBeenCalled();
});

it.each([
  { profile_id: OTHER },
  { input_profile_revision: 2 },
  { profile_revision: 3 },
  { profile_revision: 1.5 },
  { stages: [] },
  { stages: [{ stage: "unknown", ok: true, code: "ok", latency_ms: 0 }] },
  { stages: [{ stage: "model", ok: "true", code: "ok", latency_ms: 0 }] },
  { stages: [{ stage: "model", ok: true, code: "secret", latency_ms: 0 }] },
  { stages: [{ stage: "model", ok: true, code: "ok", latency_ms: -1 }] },
  { capabilities: { model_available: true } },
  { extra: "private" },
])("invalid result shape %# cannot clear pending", async (patch) => {
  savePendingModelProbe(pending);
  const t = transport();
  t.lookup.mockResolvedValue({
    ...completed(),
    result: { ...completed().result, ...patch },
  } as ModelProbeOperationReceipt);
  await expect(recoverableProbe(PROFILE, 1, t)).rejects.toThrow(
    "model_probe_operation_unavailable",
  );
  expect(readPendingModelProbe()).toEqual(pending);
});

it("negative completed result is returned without pretending capabilities passed", async () => {
  const t = transport();
  const result = completed();
  if (!result.result) throw Error("fixture");
  result.result.capabilities.model_available = false;
  result.result.stages = [
    { stage: "model", ok: false, code: "unauthorized", latency_ms: 0 },
  ];
  t.probe.mockResolvedValue(result);
  expect(
    (await recoverableProbe(PROFILE, 1, t)).capabilities.model_available,
  ).toBe(false);
  expect(readPendingModelProbe()).toBeNull();
});

it.each(["corrupt", "unwritable", "readback"])(
  "storage %s blocks POST",
  async (kind) => {
    const t = transport();
    if (kind === "corrupt") window.localStorage.setItem(KEY, "{");
    else
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        if (kind === "unwritable") throw Error("private");
      });
    await expect(recoverableProbe(PROFILE, 1, t)).rejects.toThrow(
      "pending_model_probe_failed",
    );
    expect(t.probe).not.toHaveBeenCalled();
    if (kind === "corrupt") expect(t.lookup).not.toHaveBeenCalled();
  },
);

it("competing pending installed during capability check blocks our save/POST", async () => {
  const t = transport();
  t.lookup.mockImplementation(async () => {
    savePendingModelProbe({ ...pending, operationId: OTHER });
    return absent();
  });
  await expect(recoverableProbe(PROFILE, 1, t)).rejects.toThrow(
    "pending_model_probe_failed",
  );
  expect(t.probe).not.toHaveBeenCalled();
  expect(readPendingModelProbe()?.operationId).toBe(OTHER);
});

it("failed clear cannot return success or delete competing pending", async () => {
  savePendingModelProbe(pending);
  const t = transport();
  t.lookup.mockImplementation(async () => {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({
        schemaVersion: 1,
        value: { ...pending, operationId: OTHER },
      }),
    );
    return completed();
  });
  await expect(recoverableProbe(PROFILE, 1, t)).rejects.toThrow(
    "pending_model_probe_failed",
  );
  expect(readPendingModelProbe()?.operationId).toBe(OTHER);
});

it("concurrent clicks cannot dispatch two fresh operations in this module", async () => {
  const t = transport();
  let release!: (value: ModelProbeOperationReceipt) => void;
  t.lookup.mockImplementation(
    () =>
      new Promise((resolve) => {
        release = resolve;
      }),
  );
  const first = recoverableProbe(PROFILE, 1, t);
  try {
    await expect(recoverableProbe(PROFILE, 1, t)).rejects.toThrow(
      "model_probe_in_flight",
    );
  } finally {
    release(absent());
    await first;
  }
  expect(t.probe).toHaveBeenCalledOnce();
});

it("accepts the native result's nullable/measured embedding dimensions", async () => {
  const t = transport();
  const result = completed();
  if (!result.result) throw Error("fixture");
  Object.assign(result.result.stages[0], { embedding_dimensions: null });
  result.result.stages.push({
    stage: "embedding",
    ok: true,
    code: "ok",
    latency_ms: 2,
    ...{ embedding_dimensions: 512 },
  });
  t.probe.mockResolvedValue(result);
  expect(await recoverableProbe(PROFILE, 1, t)).toEqual(result.result);
  expect(readPendingModelProbe()).toBeNull();
});

it.each([
  ["invalid", 1],
  [PROFILE, 0],
  [PROFILE, Number.MAX_SAFE_INTEGER + 1],
])(
  "invalid input never queries or dispatches (%#)",
  async (profileId, inputRevision) => {
    const t = transport();
    await expect(
      recoverableProbe(profileId as string, inputRevision as number, t),
    ).rejects.toThrow("model_probe_input_invalid");
    expect(t.lookup).not.toHaveBeenCalled();
    expect(t.probe).not.toHaveBeenCalled();
    expect(readPendingModelProbe()).toBeNull();
  },
);
