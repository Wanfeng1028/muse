import { describe, it, expect } from "vitest";
import { makeEnvelope, validateEnvelope, parseEnvelope, TASK_PROGRESS_MESSAGE_MAX, validateTaskProgress } from "../src/index.js";

describe("taskprogress", () => {
  it("progress 事件合法（含 progress+progress_count=3）→[]", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t1",
      status: "progress",
      progress: { message: "working" },
      progress_count: 3
    });
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("timed_out 事件→[]", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t2",
      status: "timed_out"
    });
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("progress 事件缺 progress→错误非空", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t3",
      status: "progress"
    });
    const errors = validateEnvelope(env);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("progress 的 message 为空→错误非空", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t4",
      status: "progress",
      progress: { message: "" }
    });
    const errors = validateEnvelope(env);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("progress 的 message 超 2000 字符→错误非空", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t5",
      status: "progress",
      progress: { message: "a".repeat(2001) }
    });
    const errors = validateEnvelope(env);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("progress 的 message 恰 2000 字符→[]", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t6",
      status: "progress",
      progress: { message: "b".repeat(2000) }
    });
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("progress_count 为 -1→错误非空", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t7",
      status: "progress",
      progress: { message: "working" },
      progress_count: -1
    });
    const errors = validateEnvelope(env);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("progress_count 为 1.5→错误非空", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t8",
      status: "progress",
      progress: { message: "working" },
      progress_count: 1.5
    });
    const errors = validateEnvelope(env);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("done 状态带 progress 字段→错误非空", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t9",
      status: "done",
      progress: { message: "completed" }
    });
    const errors = validateEnvelope(env);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("message 帧 task_progress 合法→[]", () => {
    const env = makeEnvelope("message", "bot-a", "room1", 1, 0, {
      msg_id: "m1",
      text: "t",
      mentions: [],
      intent: "task",
      task_id: "t1",
      task_progress: { task_id: "t1", message: "50%" }
    });
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("message 帧 task_progress 的 message 为空→错误非空", () => {
    const env = makeEnvelope("message", "bot-a", "room1", 1, 0, {
      msg_id: "m2",
      text: "t",
      mentions: [],
      intent: "task",
      task_id: "t1",
      task_progress: { task_id: "t1", message: "" }
    });
    const errors = validateEnvelope(env);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("message 帧 task_progress 缺 task_id→错误非空", () => {
    const env = makeEnvelope("message", "bot-a", "room1", 1, 0, {
      msg_id: "m3",
      text: "t",
      mentions: [],
      intent: "task",
      task_id: "t1",
      task_progress: { message: "50%" } as any
    });
    const errors = validateEnvelope(env);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("progress 事件序列化→parseEnvelope→validateEnvelope 为[]", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t13",
      status: "progress",
      progress: { message: "syncing" }
    });
    const parsed = parseEnvelope(JSON.stringify(env));
    expect(validateEnvelope(parsed)).toEqual([]);
  });

  it("TASK_PROGRESS_MESSAGE_MAX===2000 且 validateTaskProgress(123) 返回非空数组、validateTaskProgress({message:\"ok\"}) 返回[]", () => {
    expect(TASK_PROGRESS_MESSAGE_MAX).toBe(2000);
    expect(validateTaskProgress(123).length).toBeGreaterThan(0);
    expect(validateTaskProgress({ message: "ok" })).toEqual([]);
  });
});