import { describe, it, expect } from "vitest";
import { makeEnvelope, parseEnvelope, validateEnvelope } from "../src/index.js";
import type { ApprovalDecisionPayload, ApprovalRequestPayload, TaskEventPayload } from "../src/index.js";

describe("approval frames validation", () => {
  it("accepts a well-formed approval_request", () => {
    const env = makeEnvelope<ApprovalRequestPayload>("approval_request", "gateway", "room1", 1, 0, {
      approval_id: "a1",
      task_id: "t1",
      requester: "user",
      assignee: "echo",
      title: "写日报",
      expires_at_ms: 1700000000000,
    });
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("rejects approval_request with empty approval_id and non-integer expires_at_ms", () => {
    const env = makeEnvelope<ApprovalRequestPayload>("approval_request", "gateway", "room1", 1, 0, {
      approval_id: "",
      task_id: "t1",
      requester: "user",
      assignee: "echo",
      title: "写日报",
      expires_at_ms: 1.5,
    });
    const errs = validateEnvelope(env);
    expect(errs.some((e) => e.includes("approval_id"))).toBe(true);
    expect(errs.some((e) => e.includes("expires_at_ms"))).toBe(true);
  });

  it("accepts approval_decision approve/reject and rejects other decisions", () => {
    const ok = makeEnvelope<ApprovalDecisionPayload>("approval_decision", "user", "room1", 1, 0, {
      approval_id: "a1",
      decision: "approve",
    });
    expect(validateEnvelope(ok)).toEqual([]);
    const bad = makeEnvelope<ApprovalDecisionPayload>("approval_decision", "user", "room1", 1, 0, {
      approval_id: "a1",
      decision: "maybe" as never,
    });
    expect(validateEnvelope(bad).some((e) => e.includes("decision"))).toBe(true);
  });

  it("accepts task_event with status pending_approval", () => {
    const env = makeEnvelope<TaskEventPayload>("task_event", "gateway", "room1", 1, 0, {
      task_id: "t1",
      status: "pending_approval",
      assignee: "echo",
      title: "写日报",
    });
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("round-trips approval_request through JSON", () => {
    const env = makeEnvelope<ApprovalRequestPayload>("approval_request", "gateway", "room1", 3, 0, {
      approval_id: "a9",
      task_id: "t9",
      requester: "user",
      assignee: "echo",
      title: "x",
      expires_at_ms: 42,
    });
    const parsed = parseEnvelope(JSON.stringify(env));
    expect(parsed.type).toBe("approval_request");
    expect(validateEnvelope(parsed)).toEqual([]);
  });
});
