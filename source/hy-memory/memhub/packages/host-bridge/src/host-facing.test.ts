import { describe, expect, it } from "vitest";

import { recallForHost } from "./host-facing.js";

const HIT = {
  memory_id: "m1",
  content: "用户偏好本地优先",
  kind: "chat",
  scopes: ["all-apps"],
  evidence_ids: ["c866a180-0000-4000-8000-000000000000"],
  updated_at: "2026-10-09T00:00:00Z",
  score: 0.9,
};

describe("a recall result as a host sees it", () => {
  it("leaves no evidence id for the model to read aloud", () => {
    const seen = recallForHost({ state: "ok", hits: [HIT] });

    // A UUID in the tool result is what got recited to the person.
    expect(JSON.stringify(seen)).not.toContain("c866a180");
    expect(seen).toMatchObject({
      state: "ok",
      hits: [{ memory_id: "m1", content: "用户偏好本地优先" }],
    });
  });

  it("keeps everything the caller already relies on", () => {
    // The narrow point of this change: remove the ids, not the meaning. A
    // truncated result must still read as truncated.
    const seen = recallForHost({
      state: "partial",
      hits: [HIT],
      truncated: true,
      truncated_by: ["count_budget"],
      unexamined_count: 4,
    }) as Record<string, unknown>;

    expect(seen.state).toBe("partial");
    expect(seen.truncated).toBe(true);
    expect(seen.truncated_by).toEqual(["count_budget"]);
    expect(seen.unexamined_count).toBe(4);
  });

  it("passes a result with no hits through unchanged", () => {
    const receipt = { state: "empty", hits: [] };
    expect(recallForHost(receipt)).toBe(receipt);
    expect(recallForHost(null)).toBe(null);
  });
});
