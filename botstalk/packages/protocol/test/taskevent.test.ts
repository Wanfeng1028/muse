import { describe, it, expect } from "vitest";
import { makeEnvelope, validateEnvelope, parseEnvelope } from "../src/index.js";

describe("task_event", () => {
  it("dispatched 事件（带 assignee+title）→ []", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t1",
      status: "dispatched",
      assignee: "bot-a",
      title: "do thing",
    });
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("done 事件（不带可选字段）→ []", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 2, 0, {
      task_id: "t2",
      status: "done",
    });
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("缺 task_id → 错误非空", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 3, 0, {
      status: "running",
    });
    expect(validateEnvelope(env).length).toBeGreaterThan(0);
  });

  it('status="bogus" → 错误非空', () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 4, 0, {
      task_id: "t4",
      status: "bogus",
    });
    expect(validateEnvelope(env).length).toBeGreaterThan(0);
  });

  it("assignee=123（数字）→ 错误非空", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 5, 0, {
      task_id: "t5",
      status: "running",
      assignee: 123,
    });
    expect(validateEnvelope(env).length).toBeGreaterThan(0);
  });

  it("序列化再解析后校验通过", () => {
    const env = makeEnvelope("task_event", "gateway", "room1", 1, 0, {
      task_id: "t1",
      status: "running",
    });
    const wire = JSON.stringify(env);
    const parsed = parseEnvelope(wire);
    expect(validateEnvelope(parsed)).toEqual([]);
  });
});
