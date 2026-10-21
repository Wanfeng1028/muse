import { describe, expect, it } from "vitest";
import {
  blockReasonLabel,
  modelBlock,
  retryingBlockLabel,
  splitBlockedStages,
  worthNamingBlock,
} from "./memory-processing-labels";

describe("oversized conversation processing label", () => {
  const oversized = {
    kind: "extract",
    reason: "hy_memory_input_exceeds_window",
    count: 1,
  };

  it("explains retained originals without asserting other work is running", () => {
    expect(blockReasonLabel(oversized.reason)).toBe(
      "这段对话含过长原文，暂未整理；原文已保留",
    );
  });

  it("does not classify the oversized conversation as a missing model", () => {
    expect(modelBlock([oversized])).toBeNull();
  });

  it("still identifies a separate missing-model block", () => {
    const missingModel = {
      kind: "extract",
      reason: "model_profile_not_active",
      count: 2,
    };
    expect(modelBlock([oversized, missingModel])).toBe(missingModel);
    expect(blockReasonLabel(missingModel.reason)).toBe("还没有启用生成模型");
  });
});

it.each([
  "hy_memory_model_authentication_failed",
  "hy_memory_model_payment_required",
  "hy_memory_model_access_denied",
  "hy_memory_model_request_incompatible",
  "secure_storage_unavailable",
])("makes %s actionable only for a positive blocked count", (reason) => {
  const block = { kind: "extract", reason, count: 1 };
  expect(modelBlock([block])).toBe(block);
  expect(modelBlock([{ ...block, count: 0 }])).toBeNull();
  expect(blockReasonLabel(reason)).not.toBe(reason);
});

describe("pipeline codes stay out of the reader's way", () => {
  it.each([
    "hy_memory_write_verification_clause_incomplete",
    "hy_memory_write_verification_failed",
    "hy_memory_write_verification_quote_invalid",
    "some_code_this_build_has_never_seen",
  ])("describes %s without repeating it", (reason) => {
    const label = blockReasonLabel(reason);
    expect(label).not.toBe(reason);
    expect(label).not.toContain("hy_memory");
    expect(label).not.toMatch(/[a-z]+_[a-z]/);
  });

  it("separates what the reader owes attention from what Core retries", () => {
    const stages = splitBlockedStages([
      { kind: "extract", reason: "model_api_key_missing", count: 3 },
      {
        kind: "extract",
        reason: "hy_memory_write_verification_failed",
        count: 1,
      },
      {
        kind: "extract",
        reason: "hy_memory_write_verification_clause_incomplete",
        count: 1,
      },
      { kind: "extract", reason: "model_profile_not_active", count: 0 },
    ]);

    expect(stages.named).toEqual([
      { kind: "extract", reason: "model_api_key_missing", count: 3 },
    ]);
    expect(stages.retrying).toBe(2);
    expect(retryingBlockLabel(stages.retrying)).toBe(
      "2 条这次没能整理成功，正在重试",
    );
  });

  it("sums retries rather than listing them", () => {
    // Both are the same internal guard tripping twice; a reader counting
    // them apart learns nothing the total does not already say.
    expect(
      splitBlockedStages([
        {
          kind: "extract",
          reason: "hy_memory_write_verification_failed",
          count: 2,
        },
        { kind: "extract", reason: "failed", count: 5 },
      ]),
    ).toEqual({ named: [], retrying: 7 });
  });

  it("names the oversized stall, which Core never retries", () => {
    expect(worthNamingBlock("hy_memory_input_exceeds_window")).toBe(true);
    expect(
      splitBlockedStages([
        { kind: "extract", reason: "hy_memory_input_exceeds_window", count: 1 },
      ]),
    ).toEqual({
      named: [
        { kind: "extract", reason: "hy_memory_input_exceeds_window", count: 1 },
      ],
      retrying: 0,
    });
  });

  it("folds a code it cannot explain into the total, not into the line", () => {
    // A reason this build has never seen is still one Core picks up again
    // (`_guard_task` excludes only the oversized case), so "still working" is
    // the honest thing to say and the code is not.
    expect(worthNamingBlock("some_future_code")).toBe(false);
    expect(
      splitBlockedStages([
        { kind: "extract", reason: "model_profile_not_active", count: 1 },
        { kind: "extract", reason: "some_future_code", count: 4 },
      ]),
    ).toEqual({
      named: [
        { kind: "extract", reason: "model_profile_not_active", count: 1 },
      ],
      retrying: 4,
    });
  });
});

describe("keychain failure wording", () => {
  it("tells the reader to authorize when macOS is asking for permission", () => {
    expect(blockReasonLabel("secure_storage_authorization_required")).toBe(
      "需要授权访问本机钥匙串。请重新打开 App 并完成一次授权",
    );
  });

  it("asks for a re-save when the keychain read timed out", () => {
    expect(blockReasonLabel("secure_storage_read_timeout")).toBe(
      "读取本机钥匙串超时。重新保存一遍模型配置即可恢复",
    );
  });

  it("asks for a re-save when the keychain write timed out", () => {
    expect(blockReasonLabel("secure_storage_write_timeout")).toBe(
      "写入本机钥匙串超时。重新保存一遍模型配置即可恢复",
    );
  });

  it("does not claim a missing model for a keychain failure", () => {
    expect(modelBlock([])).toBeNull();
    expect(
      blockReasonLabel("secure_storage_authorization_required"),
    ).not.toContain("生成模型");
  });
});
