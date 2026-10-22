import { describe, expect, it } from "vitest";
import { PendingApprovals, type PendingApproval } from "../src/approvals.js";

function makeApproval(
  approvalId: string = "a1",
  overrides: Partial<PendingApproval> = {}
): PendingApproval {
  return {
    approval_id: approvalId,
    task_id: "t1",
    room: "r1",
    requester: "u1",
    assignee: "u2",
    title: "做早报",
    env: {
      kind: "message",
      sender: "u1",
      room: "r1",
      payload: {
        msg_id: "m1",
        text: "做早报",
        intent: "task",
        task_id: "t1",
      },
    } as never,
    expires_at_ms: 1000,
    ...overrides,
  };
}

describe("PendingApprovals", () => {
  it("put 后 get 能取回同一对象", () => {
    const approvals = new PendingApprovals();
    const approval = makeApproval("a1");
    approvals.put(approval);
    const got = approvals.get("a1");
    expect(got).toBe(approval);
    expect(got?.approval_id).toBe("a1");
    expect(got?.task_id).toBe("t1");
    expect(got?.room).toBe("r1");
    expect(got?.requester).toBe("u1");
    expect(got?.assignee).toBe("u2");
    expect(got?.title).toBe("做早报");
    expect(got?.expires_at_ms).toBe(1000);
  });

  it("get 不存在的 id 返回 undefined", () => {
    const approvals = new PendingApprovals();
    expect(approvals.get("nope")).toBeUndefined();
  });

  it("take 取出对象并从表中删除", () => {
    const approvals = new PendingApprovals();
    const approval = makeApproval("a1");
    approvals.put(approval);
    expect(approvals.size).toBe(1);
    const taken = approvals.take("a1");
    expect(taken).toBe(approval);
    expect(approvals.size).toBe(0);
    expect(approvals.get("a1")).toBeUndefined();
  });

  it("take 不存在的 id 返回 undefined 且 size 不变", () => {
    const approvals = new PendingApprovals();
    approvals.put(makeApproval("a1"));
    expect(approvals.take("nope")).toBeUndefined();
    expect(approvals.size).toBe(1);
  });

  it("同一 id take 两次：第一次返回对象，第二次返回 undefined", () => {
    const approvals = new PendingApprovals();
    const approval = makeApproval("a1");
    approvals.put(approval);
    const first = approvals.take("a1");
    const second = approvals.take("a1");
    expect(first).toBe(approval);
    expect(second).toBeUndefined();
  });

  it("sweepExpired 清除过期项并保留未过期项", () => {
    const approvals = new PendingApprovals();
    const expired1 = makeApproval("a1", { expires_at_ms: 100 });
    const expired2 = makeApproval("a2", { expires_at_ms: 200 });
    const active = makeApproval("a3", { expires_at_ms: 500 });
    approvals.put(expired1);
    approvals.put(expired2);
    approvals.put(active);
    const swept = approvals.sweepExpired(300);
    expect(swept.length).toBe(2);
    const sweptIds = swept.map((p) => p.approval_id);
    expect(sweptIds).toContain("a1");
    expect(sweptIds).toContain("a2");
    expect(approvals.size).toBe(1);
    expect(approvals.get("a3")).toBe(active);
    expect(approvals.get("a1")).toBeUndefined();
    expect(approvals.get("a2")).toBeUndefined();
  });

  it("sweepExpired 边界：expires_at_ms 恰好等于 now 的条目被清掉", () => {
    const approvals = new PendingApprovals();
    const boundary = makeApproval("a1", { expires_at_ms: 300 });
    approvals.put(boundary);
    const swept = approvals.sweepExpired(300);
    expect(swept.length).toBe(1);
    expect(swept[0]).toBe(boundary);
    expect(approvals.size).toBe(0);
    expect(approvals.get("a1")).toBeUndefined();
  });

  it("sweepExpired 空表返回空数组", () => {
    const approvals = new PendingApprovals();
    const swept = approvals.sweepExpired(1000);
    expect(swept).toEqual([]);
    expect(approvals.size).toBe(0);
  });

  it("put 同一 approval_id 两次：size 保持 1，get 取到第二次内容", () => {
    const approvals = new PendingApprovals();
    const first = makeApproval("a1", { title: "first" });
    const second = makeApproval("a1", { title: "second" });
    approvals.put(first);
    approvals.put(second);
    expect(approvals.size).toBe(1);
    const got = approvals.get("a1");
    expect(got).toBe(second);
    expect(got?.title).toBe("second");
  });

  it("list 返回数组快照：修改返回数组不影响 size，重新 list 才可见新条目", () => {
    const approvals = new PendingApprovals();
    approvals.put(makeApproval("a1"));
    const snapshot = approvals.list();
    snapshot.push(makeApproval("a2"));
    expect(approvals.size).toBe(1);
    const afterPush = approvals.list();
    expect(afterPush.length).toBe(1);
    expect(afterPush.map((p) => p.approval_id)).not.toContain("a2");
    approvals.put(makeApproval("a2"));
    const afterPut = approvals.list();
    expect(afterPut.length).toBe(2);
    expect(afterPut.map((p) => p.approval_id)).toContain("a2");
  });
});