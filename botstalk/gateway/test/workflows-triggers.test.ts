import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb } from "../src/db.js";
import {
  createTriggerRule, listTriggerRules, getTriggerRule, updateTriggerRule, deleteTriggerRule,
  claimTriggerFire, validateTriggerRuleInput, renderTemplate, ruleMatches,
} from "../src/workflows.js";
import type { Db } from "../src/db.js";

let dir: string;
let db: Db;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "wf-")); db = openDb(dir); });
afterEach(() => { db.close(); rmSync(dir, { recursive: true, force: true }); });

describe("触发规则 CRUD", () => {
  it("创建后能取到全部字段", () => {
    const r = createTriggerRule(db, { room: "r1", name: "kw", match_type: "keyword", pattern: "早报,日报", prompt: "hi", owner: "u1" });
    expect(r.enabled).toBe(1);
    expect(r.cooldown_sec).toBe(300);
    expect(r.last_fired_ms).toBeNull();
    const got = getTriggerRule(db, r.id);
    expect(got?.pattern).toBe("早报,日报");
    expect(got?.room).toBe("r1");
  });
  it("list 按 room 过滤", () => {
    createTriggerRule(db, { room: "r1", name: "a", match_type: "sender", pattern: "alice", prompt: "p", owner: "u" });
    createTriggerRule(db, { room: "r2", name: "b", match_type: "sender", pattern: "bob", prompt: "p", owner: "u" });
    expect(listTriggerRules(db, "r1").map((x) => x.name)).toEqual(["a"]);
  });
  it("update 改 pattern 与 cooldown", () => {
    const r = createTriggerRule(db, { room: "r1", name: "a", match_type: "keyword", pattern: "a", prompt: "p", owner: "u" });
    const u = updateTriggerRule(db, r.id, { pattern: "b,c", cooldown_sec: 60 });
    expect(u?.pattern).toBe("b,c");
    expect(u?.cooldown_sec).toBe(60);
  });
  it("update/delete 不存在的 id", () => {
    expect(updateTriggerRule(db, "nope", { name: "x" })).toBeUndefined();
    expect(deleteTriggerRule(db, "nope")).toBe(false);
  });
});

describe("触发规则校验", () => {
  it("match_type 非法", () => {
    expect(validateTriggerRuleInput({ name: "n", match_type: "regex", pattern: "a", prompt: "p" })).toContain("匹配类型");
  });
  it("keyword 的 pattern 全空", () => {
    expect(validateTriggerRuleInput({ name: "n", match_type: "keyword", pattern: " , ", prompt: "p" })).toContain("关键词");
  });
  it("cooldown 负数", () => {
    expect(validateTriggerRuleInput({ name: "n", match_type: "sender", pattern: "a", prompt: "p", cooldown_sec: -1 })).toContain("冷却");
  });
  it("合法通过", () => {
    expect(validateTriggerRuleInput({ name: "n", match_type: "event", pattern: "done", prompt: "p", cooldown_sec: 0 })).toBeNull();
  });
});

describe("renderTemplate", () => {
  it("替换全部占位符", () => {
    expect(renderTemplate("{sender} 说了 {text}（{room}）", { text: "你好", sender: "alice", room: "r1" })).toBe("alice 说了 你好（r1）");
  });
  it("未知占位符保留", () => {
    expect(renderTemplate("hi {foo}", { text: "t", sender: "s", room: "r" })).toBe("hi {foo}");
  });
});

describe("ruleMatches", () => {
  it("keyword 命中与未命中", () => {
    const chat = { sender: "alice", payload: { intent: "chat", text: "今天的早报来了" } };
    expect(ruleMatches({ pattern: "早报,日报", match_type: "keyword" } as never, chat as never)).toBe(true);
    expect(ruleMatches({ pattern: "周报", match_type: "keyword" } as never, chat as never)).toBe(false);
  });
  it("keyword 大小写不敏感", () => {
    const chat = { sender: "a", payload: { intent: "chat", text: "early news" } };
    expect(ruleMatches({ pattern: "EARLY", match_type: "keyword" } as never, chat as never)).toBe(true);
  });
  it("keyword 不匹配非 chat", () => {
    const task = { sender: "a", payload: { intent: "task", text: "早报" } };
    expect(ruleMatches({ pattern: "早报", match_type: "keyword" } as never, task as never)).toBe(false);
  });
  it("sender 精确匹配", () => {
    const chat = { sender: "alice", payload: { intent: "chat", text: "hi" } };
    expect(ruleMatches({ pattern: "alice", match_type: "sender" } as never, chat as never)).toBe(true);
    expect(ruleMatches({ pattern: "ali", match_type: "sender" } as never, chat as never)).toBe(false);
  });
  it("event 匹配任务回执状态", () => {
    const done = { sender: "a", payload: { intent: "task", task_status: "done" } };
    expect(ruleMatches({ pattern: "done", match_type: "event" } as never, done as never)).toBe(true);
    expect(ruleMatches({ pattern: "failed", match_type: "event" } as never, done as never)).toBe(false);
  });
});

describe("claimTriggerFire 冷却", () => {
  it("首次触发成功、冷却期内再次触发被拒", () => {
    const r = createTriggerRule(db, { room: "r1", name: "a", match_type: "keyword", pattern: "a", prompt: "p", owner: "u", cooldown_sec: 3600 });
    const first = claimTriggerFire(db, r.id, Date.now());
    expect(first?.last_fired_ms).toBeGreaterThan(0);
    expect(claimTriggerFire(db, r.id, Date.now())).toBeUndefined();
  });
  it("冷却过期后可再次触发", () => {
    const r = createTriggerRule(db, { room: "r1", name: "a", match_type: "keyword", pattern: "a", prompt: "p", owner: "u", cooldown_sec: 60 });
    claimTriggerFire(db, r.id, Date.now());
    db.prepare("UPDATE trigger_rules SET last_fired_ms=? WHERE id=?").run(Date.now() - 61 * 1000, r.id);
    expect(claimTriggerFire(db, r.id, Date.now())).not.toBeUndefined();
  });
});