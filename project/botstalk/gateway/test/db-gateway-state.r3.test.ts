import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, getGatewayState, setGatewayState } from "../src/db.js";

let dir: string;
let db: ReturnType<typeof openDb>;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "botstalk-gwstate-")); db = openDb(dir); });
afterEach(() => { try { (db as unknown as { close?: () => void }).close?.(); } catch {} try { rmSync(dir, { recursive: true, force: true }); } catch {} });

describe("db-gateway-state.r3", () => {
  it("未设置的 key：getGatewayState 查询无匹配行时返回 undefined", () => {
    expect(getGatewayState(db, "nope")).toBeUndefined();
  });

  it("set 后 get：setGatewayState 写入的值能被 getGatewayState 原样取回", () => {
    setGatewayState(db, "k1", "v1");
    expect(getGatewayState(db, "k1")).toBe("v1");
  });

  it("同 key 覆盖更新：二次 set 触发 ON CONFLICT DO UPDATE，get 返回最新值", () => {
    setGatewayState(db, "k", "a");
    setGatewayState(db, "k", "b");
    expect(getGatewayState(db, "k")).toBe("b");
  });

  it("多 key 互不干扰：不同 key 各自 INSERT 独立行，取值各归各", () => {
    setGatewayState(db, "a", "1");
    setGatewayState(db, "b", "2");
    expect(getGatewayState(db, "a")).toBe("1");
    expect(getGatewayState(db, "b")).toBe("2");
  });

  it("空串值可存取：value 为空字符串时 get 返回空字符串而非 undefined", () => {
    setGatewayState(db, "e", "");
    expect(getGatewayState(db, "e")).toBe("");
  });

  it("空串 key 可存取：key 为空字符串时按参数匹配取回对应值", () => {
    setGatewayState(db, "", "v");
    expect(getGatewayState(db, "")).toBe("v");
  });

  it("值含特殊字符原样存取：含引号与花括号的 JSON 文本逐字相等", () => {
    const raw = '{"a":1,"b":"x"}';
    setGatewayState(db, "j", raw);
    expect(getGatewayState(db, "j")).toBe(raw);
  });

  it("set 返回 undefined 且不抛错：setGatewayState 声明 void 并正常执行", () => {
    expect(setGatewayState(db, "x", "y")).toBeUndefined();
  });
});