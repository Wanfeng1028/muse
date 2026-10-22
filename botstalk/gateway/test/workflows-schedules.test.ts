import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb } from "../src/db.js";
import {
  createScheduledTask, listScheduledTasks, getScheduledTask, updateScheduledTask, deleteScheduledTask,
  claimDueScheduledTasks, validateScheduledTaskInput,
} from "../src/workflows.js";
import type { Db } from "../src/db.js";

let dir: string;
let db: Db;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "wf-")); db = openDb(dir); });
afterEach(() => { db.close(); rmSync(dir, { recursive: true, force: true }); });

describe("定时任务 CRUD", () => {
  it("创建后能取到全部字段", () => {
    const t = createScheduledTask(db, { room: "r1", name: "早报", interval_sec: 3600, prompt: "生成早报内容", owner: "u1" });
    expect(t.id.length).toBeGreaterThan(0);
    expect(t.room).toBe("r1");
    expect(t.enabled).toBe(1);
    expect(t.agent_id).toBeNull();
    const got = getScheduledTask(db, t.id);
    expect(got?.name).toBe("早报");
    expect(got?.prompt).toBe("生成早报内容");
    expect(got?.next_run_ms).toBeGreaterThan(Date.now() + 3590 * 1000);
  });
  it("task_title 为空时取 prompt 前 40 字", () => {
    const t = createScheduledTask(db, { room: "r1", name: "t", interval_sec: 3600, prompt: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ", owner: "u" });
    expect(t.task_title).toBe("abcdefghijklmnopqrstuvwxyz0123456789ABCD");
  });
  it("list 按 room 过滤并按创建时间升序", () => {
    createScheduledTask(db, { room: "r1", name: "a", interval_sec: 3600, prompt: "p", owner: "u" });
    createScheduledTask(db, { room: "r2", name: "b", interval_sec: 3600, prompt: "p", owner: "u" });
    createScheduledTask(db, { room: "r1", name: "c", interval_sec: 3600, prompt: "p", owner: "u" });
    const list = listScheduledTasks(db, "r1");
    expect(list.map((x) => x.name)).toEqual(["a", "c"]);
  });
  it("update 改名与禁用", () => {
    const t = createScheduledTask(db, { room: "r1", name: "old", interval_sec: 3600, prompt: "p", owner: "u" });
    const u = updateScheduledTask(db, t.id, { name: "new", enabled: false });
    expect(u?.name).toBe("new");
    expect(u?.enabled).toBe(0);
  });
  it("update 改 interval_sec 重算 next_run_ms", () => {
    const t = createScheduledTask(db, { room: "r1", name: "t", interval_sec: 3600, prompt: "p", owner: "u" });
    const u = updateScheduledTask(db, t.id, { interval_sec: 7200 });
    expect(u?.interval_sec).toBe(7200);
    expect(u?.next_run_ms ?? 0).toBeGreaterThan(Date.now() + 7190 * 1000);
  });
  it("update/delete 不存在的 id", () => {
    expect(updateScheduledTask(db, "nope", { name: "x" })).toBeUndefined();
    expect(deleteScheduledTask(db, "nope")).toBe(false);
  });
  it("delete 后 get 为 undefined", () => {
    const t = createScheduledTask(db, { room: "r1", name: "t", interval_sec: 3600, prompt: "p", owner: "u" });
    expect(deleteScheduledTask(db, t.id)).toBe(true);
    expect(getScheduledTask(db, t.id)).toBeUndefined();
  });
});

describe("定时任务校验", () => {
  it("name 空", () => { expect(validateScheduledTaskInput({ name: "  ", interval_sec: 60, prompt: "p" })).toBe("名称不能为空"); });
  it("interval_sec 太小", () => { expect(validateScheduledTaskInput({ name: "n", interval_sec: 30, prompt: "p" })).toContain("间隔秒数"); });
  it("interval_sec 非整数", () => { expect(validateScheduledTaskInput({ name: "n", interval_sec: 61.5, prompt: "p" })).toContain("间隔秒数"); });
  it("prompt 空", () => { expect(validateScheduledTaskInput({ name: "n", interval_sec: 60, prompt: "" })).toBe("任务内容不能为空"); });
  it("合法通过", () => { expect(validateScheduledTaskInput({ name: "n", interval_sec: 60, prompt: "p" })).toBeNull(); });
});

describe("claimDueScheduledTasks", () => {
  it("领取到期任务并推进 next_run_ms", () => {
    const a = createScheduledTask(db, { room: "r1", name: "a", interval_sec: 3600, prompt: "p", owner: "u" });
    const b = createScheduledTask(db, { room: "r1", name: "b", interval_sec: 1800, prompt: "p", owner: "u" });
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id IN (?,?)").run(Date.now() - 1000, a.id, b.id);
    const claimed = claimDueScheduledTasks(db, Date.now());
    expect(claimed.map((x) => x.id).sort()).toEqual([a.id, b.id].sort());
    for (const c of claimed) expect(c.next_run_ms).toBeGreaterThan(Date.now());
    expect(claimDueScheduledTasks(db, Date.now())).toEqual([]);
  });
  it("禁用的任务不被领取", () => {
    const t = createScheduledTask(db, { room: "r1", name: "t", interval_sec: 3600, prompt: "p", owner: "u" });
    updateScheduledTask(db, t.id, { enabled: false });
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(Date.now() - 1000, t.id);
    expect(claimDueScheduledTasks(db, Date.now())).toEqual([]);
  });
});