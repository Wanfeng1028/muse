import { describe, it, expect } from "vitest";
import { deriveThreadId, findReplyTarget, groupThreads, type ThreadItem } from "../src/thread.js";

describe("thread helpers", () => {
  it("derive: no reply_to => own msg_id", () => {
    expect(deriveThreadId("m1")).toBe("m1");
  });
  it("derive: reply flattens to target thread", () => {
    expect(deriveThreadId("m3", "m2", "m1")).toBe("m1");
    expect(deriveThreadId("m2", "m1")).toBe("m1");
  });
  it("findReplyTarget matches msg_id in payload JSON", () => {
    const rows = [
      { id: 1, room: "r", sender: "a", seq: 1, type: "message", payload: JSON.stringify({ msg_id: "m1", text: "hi" }), ts: 1 },
      { id: 2, room: "r", sender: "b", seq: 2, type: "message", payload: JSON.stringify({ msg_id: "m2", text: "yo" }), ts: 2 },
    ];
    expect(findReplyTarget(rows, "m2")?.id).toBe(2);
    expect(findReplyTarget(rows, "missing")).toBeUndefined();
    expect(findReplyTarget([{ ...rows[0], payload: "not-json" }], "m1")).toBeUndefined();
  });
  it("groupThreads: roots, replies sorted, orphans alone", () => {
    const items: ThreadItem[] = [
      { msgId: "m2", threadId: "m1", replyTo: "m1", ts: 3 },
      { msgId: "m1", threadId: "m1", ts: 1 },
      { msgId: "m3", threadId: "m1", replyTo: "m2", ts: 2 },
      { msgId: "orphan", threadId: "gone", ts: 4 },
    ];
    const groups = groupThreads(items);
    expect(groups.map((g) => g.root.msgId)).toEqual(["m1", "orphan"]);
    expect(groups[0].replies.map((r) => r.msgId)).toEqual(["m3", "m2"]);
    expect(groups[1].replies).toEqual([]);
  });
  it("groupThreads does not mutate input order", () => {
    const items: ThreadItem[] = [
      { msgId: "m2", threadId: "m1", ts: 3 },
      { msgId: "m1", threadId: "m1", ts: 1 },
    ];
    const before = [...items];
    groupThreads(items);
    expect(items).toEqual(before);
  });
});
