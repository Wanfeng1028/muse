// task 单元测试：task intent 路由、unsupported 回执、本体执行回执、capability_update 合法性。
import { describe, it, expect } from "vitest";
import { makeEnvelope, validateEnvelope } from "../src/index.js";
import type {
  MessagePayload,
  CapabilityUpdatePayload,
} from "../src/index.js";

const TS = 1700000000000;

describe("task intent 路由", () => {
  it("intent=task 带 task_id 合法", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      {
        msg_id: "m1",
        text: "do it",
        mentions: [],
        intent: "task",
        task_id: "t1",
      },
      TS,
    );
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("纯 API adapter 能力不足回执合法且 task_status=unsupported", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      2,
      1,
      {
        msg_id: "m2",
        text: "unsupported",
        mentions: [],
        intent: "task",
        task_id: "t1",
        task_status: "unsupported",
      },
      TS,
    );
    expect(validateEnvelope(env)).toEqual([]);
    expect(env.payload.task_status).toBe("unsupported");
  });
});

describe("本体执行回执", () => {
  it("running→done 两帧都合法", () => {
    const running = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      3,
      1,
      {
        msg_id: "m3",
        text: "running",
        mentions: [],
        intent: "task",
        task_id: "t1",
        task_status: "running",
      },
      TS,
    );
    const done = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      4,
      1,
      {
        msg_id: "m4",
        text: "done",
        mentions: [],
        intent: "task",
        task_id: "t1",
        task_status: "done",
      },
      TS,
    );
    expect(validateEnvelope(running)).toEqual([]);
    expect(validateEnvelope(done)).toEqual([]);
    expect(running.payload.task_status).toBe("running");
    expect(done.payload.task_status).toBe("done");
  });
});

describe("capability_update", () => {
  it("version 递增两帧都合法，intents=[chat] 合法", () => {
    const v1 = makeEnvelope<CapabilityUpdatePayload>(
      "capability_update",
      "alice",
      "room1",
      5,
      0,
      { version: 1, capabilities: { intents: ["chat"] } },
      TS,
    );
    const v2 = makeEnvelope<CapabilityUpdatePayload>(
      "capability_update",
      "alice",
      "room1",
      6,
      0,
      { version: 2, capabilities: { intents: ["chat"] } },
      TS,
    );
    expect(validateEnvelope(v1)).toEqual([]);
    expect(validateEnvelope(v2)).toEqual([]);
    expect(v2.payload.version).toBeGreaterThan(v1.payload.version);
    expect(v1.payload.capabilities.intents).toEqual(["chat"]);
  });
});
