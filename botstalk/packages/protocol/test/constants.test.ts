// constants 单元测试：常量契约值与 backoffDelay 计算/封顶。
import { describe, it, expect } from "vitest";
import {
  PROTOCOL_VERSION,
  HEARTBEAT_MS,
  OFFLINE_AFTER_MS,
  ZOMBIE_SWEEP_MS,
  DEDUP_WINDOW,
  RESEND_MAX_MSGS,
  RESEND_MAX_BYTES,
  STREAM_DANGLING_MS,
  GAP_RESEND_MS,
  UPLOAD_URL_WINDOW_MS,
  backoffDelay,
} from "../src/index.js";

describe("常量契约", () => {
  it("值与契约一致", () => {
    expect(PROTOCOL_VERSION).toBe(1);
    expect(HEARTBEAT_MS).toBe(20000);
    expect(OFFLINE_AFTER_MS).toBe(45000);
    expect(ZOMBIE_SWEEP_MS).toBe(15000);
    expect(DEDUP_WINDOW).toBe(500);
    expect(RESEND_MAX_MSGS).toBe(200);
    expect(RESEND_MAX_BYTES).toBe(65536);
    expect(STREAM_DANGLING_MS).toBe(60000);
    expect(GAP_RESEND_MS).toBe(5000);
    expect(UPLOAD_URL_WINDOW_MS).toBe(300000);
  });
});

describe("backoffDelay", () => {
  it("attempt=0 为 1000，attempt=5/10 封顶 30000", () => {
    expect(backoffDelay(0)).toBe(1000);
    expect(backoffDelay(5)).toBe(30000);
    expect(backoffDelay(10)).toBe(30000);
  });
});
