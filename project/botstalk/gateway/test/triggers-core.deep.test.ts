import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb } from "../src/db.js";
import {
  createTriggerRule, ruleMatches, renderTemplate, claimTriggerFire, updateTriggerRule,
  type TriggerRule,
} from "../src/workflows.js";
import { shouldSkipTriggerCheck } from "../src/triggers.js";
import type { Db } from "../src/db.js";

let dir: string;
let db: Db;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "wf-")); db = openDb(dir); });
afterEach(() => { db.close(); rmSync(dir, { recursive: true, force: true }); });

const baseRule: TriggerRule = {
  id: "rule-id",
  room: "room-a",
  name: "rule-name",
  enabled: 1,
  match_type: "keyword",
  pattern: "",
  agent_id: "agent-id",
  task_title: "task-title",
  prompt: "prompt",
  owner: "owner",
  cooldown_sec: 0,
  last_fired_ms: null,
  created_at_ms: 0,
  updated_at_ms: 0,
};

function makeRule(overrides: Partial<TriggerRule>): TriggerRule {
  return { ...baseRule, ...overrides } as TriggerRule;
}

describe("ruleMatches", () => {
  it("keyword 规则：pattern 命中 text 返回 true", () => {
    const rule = makeRule({ match_type: "keyword", pattern: "早报" });
    const result = ruleMatches(rule, {
      sender: "alice",
      payload: { intent: "chat", text: "今天的早报来了" },
    });
    expect(result).toBe(true);
  });

  it("keyword 规则：逗号分隔的多个关键词任一命中返回 true", () => {
    const rule = makeRule({ match_type: "keyword", pattern: "早报,日报" });
    const result = ruleMatches(rule, {
      sender: "alice",
      payload: { intent: "chat", text: "日报已出" },
    });
    expect(result).toBe(true);
  });

  it("keyword 规则：pattern 前后空格会被 trim", () => {
    const rule = makeRule({ match_type: "keyword", pattern: " 早报 , 晚报 " });
    const result = ruleMatches(rule, {
      sender: "alice",
      payload: { intent: "chat", text: "晚报时间" },
    });
    expect(result).toBe(true);
  });

  it("keyword 规则：intent=chat 但 text 缺失返回 false", () => {
    const rule = makeRule({ match_type: "keyword", pattern: "早报" });
    const result = ruleMatches(rule, {
      sender: "alice",
      payload: { intent: "chat" },
    });
    expect(result).toBe(false);
  });

  it("keyword 规则：intent=task 返回 false", () => {
    const rule = makeRule({ match_type: "keyword", pattern: "早报" });
    const result = ruleMatches(rule, {
      sender: "alice",
      payload: { intent: "task", task_status: "completed" },
    });
    expect(result).toBe(false);
  });

  it("sender 规则：完全相等返回 true，大小写不同返回 false", () => {
    const rule = makeRule({ match_type: "sender", pattern: "Alice" });
    expect(ruleMatches(rule, { sender: "Alice", payload: { intent: "chat", text: "hi" } })).toBe(true);
    expect(ruleMatches(rule, { sender: "alice", payload: { intent: "chat", text: "hi" } })).toBe(false);
  });

  it("event 规则：task_status 相等返回 true，缺失返回 false", () => {
    const rule = makeRule({ match_type: "event", pattern: "completed" });
    expect(ruleMatches(rule, {
      sender: "alice",
      payload: { intent: "task", task_status: "completed" },
    })).toBe(true);
    expect(ruleMatches(rule, {
      sender: "alice",
      payload: { intent: "task" },
    })).toBe(false);
  });

  it("未知 intent 返回 false", () => {
    const rule = makeRule({ match_type: "keyword", pattern: "早报" });
    const result = ruleMatches(rule, {
      sender: "alice",
      payload: { intent: "presence", text: "今天的早报来了" },
    });
    expect(result).toBe(false);
  });

  it("intent 缺失返回 false", () => {
    const rule = makeRule({ match_type: "keyword", pattern: "早报" });
    const result = ruleMatches(rule, {
      sender: "alice",
      payload: { text: "今天的早报来了" },
    });
    expect(result).toBe(false);
  });
});

describe("renderTemplate", () => {
  const vars = { text: "你好", sender: "alice", room: "lobby" };

  it("三个变量都正确替换", () => {
    expect(renderTemplate("{sender} 在 {room} 说：{text}", vars)).toBe("alice 在 lobby 说：你好");
  });

  it("同一变量出现两次都被替换", () => {
    expect(renderTemplate("{text} / {text}", vars)).toBe("你好 / 你好");
  });

  it("未知变量原样保留", () => {
    expect(renderTemplate("hello {foo}", vars)).toBe("hello {foo}");
  });

  it("空字符串变量替换为空", () => {
    expect(renderTemplate("[{text}]", { text: "", sender: "alice", room: "lobby" })).toBe("[]");
  });
});

describe("shouldSkipTriggerCheck", () => {
  it("sender=scheduler 返回 true", () => {
    expect(shouldSkipTriggerCheck({ sender: "scheduler", payload: {} } as never)).toBe(true);
  });

  it("sender 以 trigger: 开头返回 true", () => {
    expect(shouldSkipTriggerCheck({ sender: "trigger:abc123", payload: {} } as never)).toBe(true);
  });

  it("sender=gateway 返回 true", () => {
    expect(shouldSkipTriggerCheck({ sender: "gateway", payload: {} } as never)).toBe(true);
  });

  it("未知 intent 返回 true", () => {
    expect(shouldSkipTriggerCheck({ sender: "alice", payload: { intent: "presence" } } as never)).toBe(true);
  });

  it("intent=chat 与 intent 缺失返回 false", () => {
    expect(shouldSkipTriggerCheck({ sender: "alice", payload: { intent: "chat" } } as never)).toBe(false);
    expect(shouldSkipTriggerCheck({ sender: "alice", payload: {} } as never)).toBe(false);
  });
});

describe("claimTriggerFire", () => {
  it("新规则首次触发并写入 last_fired_ms", () => {
    const rule = createTriggerRule(db, {
      room: "room-a",
      name: "first-fire",
      match_type: "keyword",
      pattern: "早报",
      prompt: "prompt",
      owner: "owner",
      cooldown_sec: 300,
    });

    const fired = claimTriggerFire(db, rule.id, 1000);
    expect(fired).toBeDefined();
    expect(fired?.id).toBe(rule.id);
    expect(fired?.last_fired_ms).toBe(1000);

    const row = db
      .prepare("SELECT last_fired_ms FROM trigger_rules WHERE id = ?")
      .get(rule.id) as { last_fired_ms: number | null };
    expect(row.last_fired_ms).toBe(1000);
  });

  it("冷却期内再次触发返回 undefined", () => {
    const rule = createTriggerRule(db, {
      room: "room-a",
      name: "cooldown",
      match_type: "keyword",
      pattern: "早报",
      prompt: "prompt",
      owner: "owner",
      cooldown_sec: 300,
    });

    expect(claimTriggerFire(db, rule.id, 1000)?.last_fired_ms).toBe(1000);
    expect(claimTriggerFire(db, rule.id, 2000)).toBeUndefined();
  });

  it("冷却边界时可以触发", () => {
    const rule = createTriggerRule(db, {
      room: "room-a",
      name: "boundary",
      match_type: "keyword",
      pattern: "早报",
      prompt: "prompt",
      owner: "owner",
      cooldown_sec: 300,
    });

    expect(claimTriggerFire(db, rule.id, 1000)?.last_fired_ms).toBe(1000);
    const fired = claimTriggerFire(db, rule.id, 301000);
    expect(fired).toBeDefined();
    expect(fired?.last_fired_ms).toBe(301000);
  });

  it("禁用规则和不存在的 id 返回 undefined", () => {
    const rule = createTriggerRule(db, {
      room: "room-a",
      name: "disabled",
      match_type: "keyword",
      pattern: "早报",
      prompt: "prompt",
      owner: "owner",
      cooldown_sec: 300,
    });

    updateTriggerRule(db, rule.id, { enabled: false });
    expect(claimTriggerFire(db, rule.id, 1000)).toBeUndefined();
    expect(claimTriggerFire(db, "missing-rule-id", 1000)).toBeUndefined();
  });
});