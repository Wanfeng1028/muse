// codec 单元测试：makeEnvelope/parseEnvelope 往返、解析错误、validateEnvelope 结构校验。
import { describe, it, expect } from "vitest";
import {
  makeEnvelope,
  parseEnvelope,
  validateEnvelope,
} from "../src/index.js";
import type {
  Envelope,
  MessagePayload,
  StreamPayload,
  GapPayload,
  CapabilityUpdatePayload,
} from "../src/index.js";

const TS = 1700000000000;

describe("codec makeEnvelope/parseEnvelope", () => {
  it("往返后字段全等", () => {
    const payload: MessagePayload = {
      msg_id: "m1",
      text: "hello",
      mentions: ["a"],
      intent: "chat",
    };
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      payload,
      TS,
    );
    const json = JSON.stringify(env);
    const parsed = parseEnvelope(json);
    expect(parsed).toEqual(env);
    expect(parsed.v).toBe(1);
    expect(parsed.type).toBe("message");
    expect(parsed.sender).toBe("alice");
    expect(parsed.room).toBe("room1");
    expect(parsed.seq).toBe(1);
    expect(parsed.ack).toBe(0);
    expect(parsed.ts).toBe(TS);
    expect(parsed.payload).toEqual(payload);
  });

  it("非法 JSON 抛 SyntaxError", () => {
    expect(() => parseEnvelope("{not json")).toThrow(SyntaxError);
  });

  it("缺 sender 抛 TypeError 且消息含 sender", () => {
    const bad = JSON.stringify({
      v: 1,
      type: "message",
      seq: 1,
      ack: 0,
      room: "room1",
      ts: TS,
      payload: {
        msg_id: "m1",
        text: "hi",
        mentions: [],
        intent: "chat",
      },
    });
    let err: unknown;
    try {
      parseEnvelope(bad);
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(TypeError);
    expect((err as TypeError).message).toContain("sender");
  });
});

describe("codec validateEnvelope", () => {
  it("合法 message 返回空数组", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      { msg_id: "m1", text: "hi", mentions: [], intent: "chat" },
      TS,
    );
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("v=2 返回非空", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      { msg_id: "m1", text: "hi", mentions: [], intent: "chat" },
      TS,
    );
    const bad: Envelope = { ...env, v: 2 };
    expect(validateEnvelope(bad).length).toBeGreaterThan(0);
  });

  it("seq=0 返回非空", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      { msg_id: "m1", text: "hi", mentions: [], intent: "chat" },
      TS,
    );
    const bad: Envelope = { ...env, seq: 0 };
    expect(validateEnvelope(bad).length).toBeGreaterThan(0);
  });

  it("intent=task 缺 task_id 返回非空", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      { msg_id: "m1", text: "do", mentions: [], intent: "task" },
      TS,
    );
    expect(validateEnvelope(env).length).toBeGreaterThan(0);
  });

  it("intent=task 带 task_id 合法", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      {
        msg_id: "m1",
        text: "do",
        mentions: [],
        intent: "task",
        task_id: "t1",
      },
      TS,
    );
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("stream error=true 缺 reason 返回非空", () => {
    const env = makeEnvelope<StreamPayload>(
      "stream",
      "alice",
      "room1",
      1,
      0,
      {
        stream_id: "s1",
        chunk_index: 0,
        final: true,
        delta: "",
        error: true,
      },
      TS,
    );
    expect(validateEnvelope(env).length).toBeGreaterThan(0);
  });

  it("gap from_seq>to_seq 返回非空", () => {
    const env = makeEnvelope<GapPayload>(
      "gap",
      "alice",
      "room1",
      1,
      0,
      { from_seq: 5, to_seq: 2 },
      TS,
    );
    expect(validateEnvelope(env).length).toBeGreaterThan(0);
  });

  it("capability_update version=0 返回非空", () => {
    const env = makeEnvelope<CapabilityUpdatePayload>(
      "capability_update",
      "alice",
      "room1",
      1,
      0,
      { version: 0, capabilities: { intents: ["chat"] } },
      TS,
    );
    expect(validateEnvelope(env).length).toBeGreaterThan(0);
  });

  it("gseq=7 合法", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      { msg_id: "m1", text: "hi", mentions: [], intent: "chat" },
      TS,
    );
    const withGseq: Envelope = { ...env, gseq: 7 };
    const errs = validateEnvelope(withGseq).filter((e) => e.startsWith("gseq"));
    expect(errs).toEqual([]);
  });

  it("不带 gseq 合法", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      { msg_id: "m1", text: "hi", mentions: [], intent: "chat" },
      TS,
    );
    expect(validateEnvelope(env)).toEqual([]);
  });

  it("gseq=0 非法", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      { msg_id: "m1", text: "hi", mentions: [], intent: "chat" },
      TS,
    );
    const withGseq: Envelope = { ...env, gseq: 0 };
    expect(validateEnvelope(withGseq)).toContain("gseq: must be a positive integer");
  });

  it("gseq=1.5 非法", () => {
    const env = makeEnvelope<MessagePayload>(
      "message",
      "alice",
      "room1",
      1,
      0,
      { msg_id: "m1", text: "hi", mentions: [], intent: "chat" },
      TS,
    );
    const withGseq: Envelope = { ...env, gseq: 1.5 };
    expect(validateEnvelope(withGseq)).toContain("gseq: must be a positive integer");
  });
});
