import { describe, it, expect } from "vitest";
import { makeEnvelope, parseEnvelope, validateEnvelope } from "../src/index.js";
import type { Envelope, MessagePayload, StreamPayload, PresencePayload, HelloPayload, CapabilityUpdatePayload } from "../src/index.js";

const TS = 1700000000000;
function baseMsg(): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", "alice", "room1", 1, 0, { msg_id: "m1", text: "hi", mentions: [], intent: "chat" }, TS);
}

describe("codec.r3 未覆盖分支", () => {
  it("parseEnvelope 收到数组 JSON 应抛 TypeError，消息为 field envelope: expected object", () => {
    expect(() => parseEnvelope("[1,2]")).toThrow(TypeError);
    expect(() => parseEnvelope("[1,2]")).toThrow("field envelope: expected object");
  });

  it("parseEnvelope 缺失 v 字段应抛错，消息含 field v: missing", () => {
    expect(() => parseEnvelope(JSON.stringify({ type: "message" }))).toThrow("field v: missing");
  });

  it("parseEnvelope 遇到非法 type 应抛错，消息为 field type: invalid frame type", () => {
    const raw = JSON.stringify({ v: 1, type: "bogus", seq: 1, ack: 0, sender: "a", room: "r", ts: 1, payload: {} });
    expect(() => parseEnvelope(raw)).toThrow("field type: invalid frame type");
  });

  it("parseEnvelope 缺失 payload 字段应抛错，消息为 field payload: missing", () => {
    const raw = JSON.stringify({ v: 1, type: "message", seq: 1, ack: 0, sender: "a", room: "r", ts: 1 });
    expect(() => parseEnvelope(raw)).toThrow("field payload: missing");
  });

  it("validateEnvelope 非对象输入应返回 envelope: expected object", () => {
    const result = validateEnvelope("nope" as unknown as Envelope);
    expect(result).toEqual(["envelope: expected object"]);
  });

  it("validateEnvelope 非法 type 应提前返回，仅含 type: invalid frame type 而不校验 payload", () => {
    const e = { ...baseMsg(), type: "bogus" as unknown as "message" };
    const result = validateEnvelope(e);
    expect(result.length).toBe(1);
    expect(result[0]).toBe("type: invalid frame type");
  });

  it("validateEnvelope presence 非法 status 应报 payload.status 错误", () => {
    const e = makeEnvelope<PresencePayload>("presence", "a", "r", 1, 0, { adapter_id: "a", status: "bogus" } as unknown as PresencePayload, TS) as Envelope;
    expect(validateEnvelope(e)).toContain("payload.status: must be 'online', 'thinking' or 'offline'");
  });

  it("validateEnvelope stream chunk_index 为负数应报 payload.chunk_index 错误", () => {
    const e = makeEnvelope<StreamPayload>("stream", "a", "r", 1, 0, { stream_id: "s", chunk_index: -1, final: false, delta: "x" }, TS) as Envelope;
    expect(validateEnvelope(e)).toContain("payload.chunk_index: must be an integer >= 0");
  });

  it("validateEnvelope message 非法 intent 与 task_status 应同时报两条错误", () => {
    const e = makeEnvelope<MessagePayload>("message", "a", "r", 1, 0, { msg_id: "m", text: "t", mentions: [], intent: "bogus", task_status: "bogus" } as unknown as MessagePayload, TS) as Envelope;
    const result = validateEnvelope(e);
    expect(result).toContain("payload.intent: must be 'chat' or 'task'");
    expect(result).toContain("payload.task_status: must be 'running' | 'done' | 'failed' | 'unsupported'");
  });

  it("parseEnvelope 允许 sender 为空串，而 validateEnvelope 判定其非法", () => {
    const e = { ...baseMsg(), sender: "" };
    expect(() => parseEnvelope(JSON.stringify(e))).not.toThrow();
    expect(validateEnvelope(e)).toContain("sender: must be a non-empty string");
  });
});