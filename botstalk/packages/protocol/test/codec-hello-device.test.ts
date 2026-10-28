import { describe, it, expect } from "vitest";
import { makeEnvelope, validateEnvelope } from "../src/index.js";
import type { HelloPayload } from "../src/index.js";

function helloEnv(extra: Record<string, unknown> = {}) {
  return makeEnvelope<HelloPayload>("hello", "adapter-1", "room-a", 1, 0, { adapter_id: "adapter-1", protocol_version: "1.3", last_seen_seq: 0, ...extra });
}

describe("codec hello device fields", () => {
  // 用例1：验证没有设备字段时校验通过
  it("passes without device fields", () => {
    expect(validateEnvelope(helloEnv())).toEqual([]);
  });

  // 用例2：验证同时具有设备ID和设备密钥时校验通过
  it("passes with both device fields", () => {
    const extra = { device_id: "phone-1", device_key: "0123456789abcdef" };
    expect(validateEnvelope(helloEnv(extra))).toEqual([]);
  });

  // 用例3：验证 device_id 为空字符串时校验报错
  it("rejects empty device_id", () => {
    const extra = { device_id: "" };
    expect(validateEnvelope(helloEnv(extra))).toContain("payload.device_id: must be a non-empty string");
  });

  // 用例4：验证 device_key 为非字符串类型时校验报错
  it("rejects non-string device_key", () => {
    const extra = { device_key: 123 };
    expect(validateEnvelope(helloEnv(extra))).toContain("payload.device_key: must be a non-empty string");
  });

  // 用例5：验证仅有单个设备字段时在编解码层不报错（字段成对性由网关层负责校验）
  it("does not reject a lone device field at codec level", () => {
    const extra = { device_id: "phone-1" };
    expect(validateEnvelope(helloEnv(extra))).toEqual([]);
  });
});