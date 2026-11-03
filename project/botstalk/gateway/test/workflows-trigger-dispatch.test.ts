import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb } from "../src/db.js";
import { createTriggerRule } from "../src/workflows.js";
import { checkTriggers, shouldSkipTriggerCheck } from "../src/triggers.js";
import { makeEnvelope } from "@botstalk/protocol";
import type { Envelope, MessagePayload } from "@botstalk/protocol";
import type { Db } from "../src/db.js";
import type { Hub } from "../src/hub.js";

class FakeHub {
  sent: Array<{ to: string; env: Envelope<MessagePayload> }> = [];
  private seq = 0;
  constructor(private adapters: string[]) {}
  getOnlineAdapters(): string[] { return [...this.adapters]; }
  getConn(id: string): { capabilities: { intents: string[] } } | undefined {
    return this.adapters.includes(id) ? { capabilities: { intents: ["task", "chat"] } } : undefined;
  }
  sendTo(to: string, env: Envelope<MessagePayload>): boolean { this.sent.push({ to, env }); return true; }
  broadcast(_room: string, _env: Envelope<MessagePayload>): void {}
  broadcastTaskEvent(_room: string, _payload: Record<string, unknown>): void {}
  nextSeq(): number { return ++this.seq; }
}

let dir: string;
let db: Db;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "wf-")); db = openDb(dir); });
afterEach(() => { db.close(); rmSync(dir, { recursive: true, force: true }); });

function chatEnv(sender: string, text: string): Envelope<MessagePayload> {
  return makeEnvelope<MessagePayload>("message", sender, "r1", 1, 0, { msg_id: "m1", text, mentions: [], intent: "chat" });
}

describe("shouldSkipTriggerCheck", () => {
  it("系统帧跳过", () => {
    expect(shouldSkipTriggerCheck(chatEnv("scheduler", "hi"))).toBe(true);
    expect(shouldSkipTriggerCheck(chatEnv("trigger:abc", "hi"))).toBe(true);
    expect(shouldSkipTriggerCheck(chatEnv("gateway", "hi"))).toBe(true);
  });
  it("正常聊天不跳过", () => {
    expect(shouldSkipTriggerCheck(chatEnv("alice", "hi"))).toBe(false);
  });
});

describe("checkTriggers 关键词触发", () => {
  it("命中关键词派发任务并渲染模板", () => {
    const rule = createTriggerRule(db, { room: "r1", name: "kw", match_type: "keyword", pattern: "早报", prompt: "{sender} 提到 {text}", owner: "u", agent_id: "agent1" });
    const hub = new FakeHub(["agent1"]);
    checkTriggers(hub as unknown as Hub, db, chatEnv("alice", "早报来了"));
    expect(hub.sent).toHaveLength(1);
    expect(hub.sent[0].to).toBe("agent1");
    expect(hub.sent[0].env.sender).toBe("trigger:" + rule.id);
    expect(hub.sent[0].env.payload.text).toBe("alice 提到 早报来了");
  });
  it("未命中不派发", () => {
    createTriggerRule(db, { room: "r1", name: "kw", match_type: "keyword", pattern: "早报", prompt: "p", owner: "u", agent_id: "agent1" });
    const hub = new FakeHub(["agent1"]);
    checkTriggers(hub as unknown as Hub, db, chatEnv("alice", "今天天气不错"));
    expect(hub.sent).toHaveLength(0);
  });
  it("冷却期内不重复触发", () => {
    createTriggerRule(db, { room: "r1", name: "kw", match_type: "keyword", pattern: "早报", prompt: "p", owner: "u", agent_id: "agent1", cooldown_sec: 3600 });
    const hub = new FakeHub(["agent1"]);
    checkTriggers(hub as unknown as Hub, db, chatEnv("alice", "早报"));
    checkTriggers(hub as unknown as Hub, db, chatEnv("alice", "早报来了"));
    expect(hub.sent).toHaveLength(1);
  });
  it("禁用的规则不触发", () => {
    const rule = createTriggerRule(db, { room: "r1", name: "kw", match_type: "keyword", pattern: "早报", prompt: "p", owner: "u", agent_id: "agent1" });
    db.prepare("UPDATE trigger_rules SET enabled=0 WHERE id=?").run(rule.id);
    const hub = new FakeHub(["agent1"]);
    checkTriggers(hub as unknown as Hub, db, chatEnv("alice", "早报"));
    expect(hub.sent).toHaveLength(0);
  });
  it("self-guard：scheduler 发的消息不触发", () => {
    createTriggerRule(db, { room: "r1", name: "kw", match_type: "keyword", pattern: "早报", prompt: "p", owner: "u", agent_id: "agent1" });
    const hub = new FakeHub(["agent1"]);
    checkTriggers(hub as unknown as Hub, db, chatEnv("scheduler", "早报"));
    expect(hub.sent).toHaveLength(0);
  });
});

describe("checkTriggers 事件触发", () => {
  it("任务回执 done 触发", () => {
    createTriggerRule(db, { room: "r1", name: "ev", match_type: "event", pattern: "done", prompt: "任务完成了", owner: "u", agent_id: "agent1" });
    const hub = new FakeHub(["agent1"]);
    const env = makeEnvelope<MessagePayload>("message", "agent1", "r1", 2, 0, { msg_id: "m2", text: "", mentions: [], intent: "task", task_id: "t1", task_status: "done" });
    checkTriggers(hub as unknown as Hub, db, env);
    expect(hub.sent).toHaveLength(1);
    expect(hub.sent[0].to).toBe("agent1");
  });
});