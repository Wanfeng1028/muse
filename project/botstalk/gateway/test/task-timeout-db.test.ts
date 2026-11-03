import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, upsertTaskDispatch, getTask, recordTaskProgress, getTaskProgress, listExpiredTasks, markTaskTimedOut } from "../src/db.js";

let dir: string;
let db: ReturnType<typeof openDb>;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "botstalk-taskdb-"));
  db = openDb(dir);
});

afterEach(() => {
  try { (db as unknown as { close?: () => void }).close?.(); } catch {}
  try { rmSync(dir, { recursive: true, force: true }); } catch {}
});

describe("task-timeout-db", () => {
  it("新任务默认值", () => {
    upsertTaskDispatch(db, { task_id: "t1", room: "r1", owner: "o1", assignee: "a1", title: "title1", status: "dispatched" });
    const task = getTask(db, "t1");
    expect(task).toBeDefined();
    expect(task!.deadline_ms).toBeNull();
    expect(task!.error).toBeNull();
    expect(task!.progress_count).toBe(0);
  });

  it("upsert 带 deadline_ms 落库", () => {
    upsertTaskDispatch(db, { task_id: "t2", room: "r2", owner: "o2", assignee: "a2", title: "title2", status: "dispatched", deadline_ms: 12345 });
    const task = getTask(db, "t2");
    expect(task).toBeDefined();
    expect(task!.deadline_ms).toBe(12345);
  });

  it("重派发刷新 deadline", () => {
    upsertTaskDispatch(db, { task_id: "t3", room: "r3", owner: "o3", assignee: "a3", title: "title3", status: "dispatched", deadline_ms: 100 });
    upsertTaskDispatch(db, { task_id: "t3", room: "r3", owner: "o3", assignee: "a3", title: "title3", status: "dispatched", deadline_ms: 200 });
    const task = getTask(db, "t3");
    expect(task).toBeDefined();
    expect(task!.deadline_ms).toBe(200);
  });

  it("recordTaskProgress seq 从 1 递增", () => {
    upsertTaskDispatch(db, { task_id: "t4", room: "r4", owner: "o4", assignee: "a4", title: "title4", status: "running" });
    const seq1 = recordTaskProgress(db, "t4", "reporter1", "msg1", null);
    const seq2 = recordTaskProgress(db, "t4", "reporter2", "msg2", '{"key":"value"}');
    const seq3 = recordTaskProgress(db, "t4", "reporter3", "msg3", null);
    expect(seq1).toBe(1);
    expect(seq2).toBe(2);
    expect(seq3).toBe(3);
    const task = getTask(db, "t4");
    expect(task!.progress_count).toBe(3);
    const progress = getTaskProgress(db, "t4");
    expect(progress[0].data_json).toBeNull();
    expect(progress[1].data_json).toEqual('{"key":"value"}');
  });

  it("getTaskProgress 按 seq 升序返回 message 序列正确", () => {
    upsertTaskDispatch(db, { task_id: "t5", room: "r5", owner: "o5", assignee: "a5", title: "title5", status: "running" });
    recordTaskProgress(db, "t5", "r", "alpha", null);
    recordTaskProgress(db, "t5", "r", "beta", null);
    recordTaskProgress(db, "t5", "r", "gamma", null);
    const progress = getTaskProgress(db, "t5");
    expect(progress.map(p => p.message)).toEqual(["alpha", "beta", "gamma"]);
  });

  it("listExpiredTasks 不返回已 done 的过期任务", () => {
    upsertTaskDispatch(db, { task_id: "t6", room: "r6", owner: "o6", assignee: "a6", title: "title6", status: "done", deadline_ms: 50 });
    const expired = listExpiredTasks(db, 100);
    expect(expired.find(t => t.task_id === "t6")).toBeUndefined();
  });

  it("listExpiredTasks 不返回 deadline_ms 为 null 的任务", () => {
    upsertTaskDispatch(db, { task_id: "t7", room: "r7", owner: "o7", assignee: "a7", title: "title7", status: "dispatched" });
    const expired = listExpiredTasks(db, 100);
    expect(expired.find(t => t.task_id === "t7")).toBeUndefined();
  });

  it("边界：deadline_ms 恰等于 nowMs 时不返回（严格小于）", () => {
    upsertTaskDispatch(db, { task_id: "t8", room: "r8", owner: "o8", assignee: "a8", title: "title8", status: "dispatched", deadline_ms: 100 });
    const expired = listExpiredTasks(db, 100);
    expect(expired.find(t => t.task_id === "t8")).toBeUndefined();
  });

  it("边界：deadline_ms = nowMs-1 时返回", () => {
    upsertTaskDispatch(db, { task_id: "t9", room: "r9", owner: "o9", assignee: "a9", title: "title9", status: "dispatched", deadline_ms: 99 });
    const expired = listExpiredTasks(db, 100);
    expect(expired.find(t => t.task_id === "t9")).toBeDefined();
  });

  it("markTaskTimedOut：dispatched 任务变为 timed_out，error 写入 'Task timed out'，返回 true", () => {
    upsertTaskDispatch(db, { task_id: "t10", room: "r10", owner: "o10", assignee: "a10", title: "title10", status: "dispatched", deadline_ms: 50 });
    const result = markTaskTimedOut(db, "t10", "Task timed out", 100);
    expect(result).toBe(true);
    const task = getTask(db, "t10");
    expect(task!.status).toBe("timed_out");
    expect(task!.error).toBe("Task timed out");
  });

  it("markTaskTimedOut 对 done 任务返回 false 且状态保持 done", () => {
    upsertTaskDispatch(db, { task_id: "t11", room: "r11", owner: "o11", assignee: "a11", title: "title11", status: "done" });
    const result = markTaskTimedOut(db, "t11", "Task timed out", 100);
    expect(result).toBe(false);
    const task = getTask(db, "t11");
    expect(task!.status).toBe("done");
  });

  it("幂等：同一任务连调两次 markTaskTimedOut，第一次 true 第二次 false", () => {
    upsertTaskDispatch(db, { task_id: "t12", room: "r12", owner: "o12", assignee: "a12", title: "title12", status: "dispatched" });
    const res1 = markTaskTimedOut(db, "t12", "Task timed out", 100);
    expect(res1).toBe(true);
    const res2 = markTaskTimedOut(db, "t12", "Task timed out", 100);
    expect(res2).toBe(false);
  });

  it("老库迁移幂等：同一目录 openDb 两次不抛错（先 close 第一个再 open 第二个）", () => {
    (db as unknown as { close?: () => void }).close?.();
    const db2 = openDb(dir);
    expect(db2).toBeDefined();
    (db2 as unknown as { close?: () => void }).close?.();
  });
});