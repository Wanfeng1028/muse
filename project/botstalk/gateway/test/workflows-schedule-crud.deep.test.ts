import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb } from "../src/db.js";
import {
  createScheduledTask, listScheduledTasks, getScheduledTask, updateScheduledTask, deleteScheduledTask,
} from "../src/workflows.js";
import type { Db } from "../src/db.js";

let dir: string;
let db: Db;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "wf-")); db = openDb(dir); });
afterEach(() => { db.close(); rmSync(dir, { recursive: true, force: true }); });

describe("scheduled task CRUD", () => {
  it("创建后 next_run_ms 约等于 now + interval_sec*1000，且 DB 读回值与返回值一致", () => {
    const before = Date.now();
    const created = createScheduledTask(db, {
      room: "roomA",
      name: "task-1",
      interval_sec: 60,
      prompt: "do something",
      owner: "tester",
    });
    const after = Date.now();
    const intervalMs = 60 * 1000;

    expect(created.next_run_ms).toBeGreaterThanOrEqual(before + intervalMs);
    expect(created.next_run_ms).toBeLessThanOrEqual(after + intervalMs);
    expect(getScheduledTask(db, created.id)).toEqual(created);
  });

  it("未传 task_title 时，超长 prompt 默认 title 为 prompt.trim().slice(0,40).trimEnd()", () => {
    const prompt = "x".repeat(100);
    const created = createScheduledTask(db, {
      room: "roomA",
      name: "long-prompt",
      interval_sec: 30,
      prompt,
      owner: "tester",
    });

    expect(created.task_title).toBe(prompt.trim().slice(0, 40).trimEnd());
  });

  it("prompt 带前后空格时默认 title 已 trim", () => {
    const prompt = "   scheduled prompt with spaces   ";
    const created = createScheduledTask(db, {
      room: "roomA",
      name: "trim-prompt",
      interval_sec: 30,
      prompt,
      owner: "tester",
    });

    expect(created.task_title).toBe(prompt.trim().slice(0, 40).trimEnd());
  });

  it("显式传入 task_title 时不被 prompt 覆盖", () => {
    const created = createScheduledTask(db, {
      room: "roomA",
      name: "explicit-title",
      interval_sec: 30,
      task_title: "explicit task title",
      prompt: "this prompt should not be used as title",
      owner: "tester",
    });

    expect(created.task_title).toBe("explicit task title");
  });

  it("update 变更 interval_sec：next_run_ms 重排，last_run_ms 保持原值", () => {
    const created = createScheduledTask(db, {
      room: "roomA",
      name: "interval-update",
      interval_sec: 60,
      prompt: "update interval",
      owner: "tester",
    });

    const oldLastRun = created.created_at_ms - 1234;
    db.prepare("UPDATE scheduled_tasks SET last_run_ms = ? WHERE id = ?").run(oldLastRun, created.id);

    const before = Date.now();
    const updated = updateScheduledTask(db, created.id, { interval_sec: 30 });
    const after = Date.now();
    const newIntervalMs = 30 * 1000;

    expect(updated).toBeDefined();
    if (!updated) throw new Error("updateScheduledTask should return the updated task");

    expect(updated.last_run_ms).toBe(oldLastRun);
    expect(updated.next_run_ms).toBeGreaterThanOrEqual(before + newIntervalMs);
    expect(updated.next_run_ms).toBeLessThanOrEqual(after + newIntervalMs);
  });

  it("update 传空 patch {}：返回对象且 updated_at_ms 与原值完全相同", () => {
    const created = createScheduledTask(db, {
      room: "roomA",
      name: "empty-patch",
      interval_sec: 30,
      prompt: "empty patch",
      owner: "tester",
    });

    const updated = updateScheduledTask(db, created.id, {});

    expect(updated).toBeDefined();
    if (!updated) throw new Error("updateScheduledTask should return the original task");

    expect(updated.updated_at_ms).toBe(created.updated_at_ms);
    expect(getScheduledTask(db, created.id)).toEqual(created);
  });

  it("update 不存在的 id：返回 undefined", () => {
    const updated = updateScheduledTask(db, "missing-id", {
      name: "new-name",
    });

    expect(updated).toBeUndefined();
  });

  it("delete 不存在的 id 返回 false；删除已有任务后 get 返回 undefined", () => {
    expect(deleteScheduledTask(db, "missing-id")).toBe(false);

    const created = createScheduledTask(db, {
      room: "roomA",
      name: "to-delete",
      interval_sec: 30,
      prompt: "delete me",
      owner: "tester",
    });

    expect(deleteScheduledTask(db, created.id)).toBe(true);
    expect(getScheduledTask(db, created.id)).toBeUndefined();
  });

  it("room 隔离：roomA 建 2 个、roomB 建 1 个，listScheduledTasks(db,\"roomA\") 只返回 2 个", () => {
    createScheduledTask(db, {
      room: "roomA",
      name: "roomA-task-1",
      interval_sec: 30,
      prompt: "roomA 1",
      owner: "tester",
    });
    createScheduledTask(db, {
      room: "roomA",
      name: "roomA-task-2",
      interval_sec: 30,
      prompt: "roomA 2",
      owner: "tester",
    });
    createScheduledTask(db, {
      room: "roomB",
      name: "roomB-task-1",
      interval_sec: 30,
      prompt: "roomB 1",
      owner: "tester",
    });

    const roomATasks = listScheduledTasks(db, "roomA");

    expect(roomATasks).toHaveLength(2);
    expect(roomATasks.every((task) => task.room === "roomA")).toBe(true);
  });

  it("getScheduledTask 按 id 可取到其他 room 的任务", () => {
    const roomBTask = createScheduledTask(db, {
      room: "roomB",
      name: "other-room-task",
      interval_sec: 30,
      prompt: "other room",
      owner: "tester",
    });

    const fetched = getScheduledTask(db, roomBTask.id);

    expect(fetched).toEqual(roomBTask);
    expect(fetched?.room).toBe("roomB");
  });

  it("创建 3 个任务，list 返回顺序按 created_at_ms 升序", async () => {
    const first = createScheduledTask(db, {
      room: "roomA",
      name: "first",
      interval_sec: 30,
      prompt: "first",
      owner: "tester",
    });
    await new Promise<void>((resolve) => setTimeout(resolve, 20));

    const second = createScheduledTask(db, {
      room: "roomA",
      name: "second",
      interval_sec: 30,
      prompt: "second",
      owner: "tester",
    });
    await new Promise<void>((resolve) => setTimeout(resolve, 20));

    const third = createScheduledTask(db, {
      room: "roomA",
      name: "third",
      interval_sec: 30,
      prompt: "third",
      owner: "tester",
    });

    const listed = listScheduledTasks(db, "roomA");

    expect(listed.map((task) => task.id)).toEqual([first.id, second.id, third.id]);

    const times = listed.map((task) => task.created_at_ms);
    for (let i = 1; i < times.length; i++) {
      expect(times[i]).toBeGreaterThanOrEqual(times[i - 1]);
    }
  });

  it("未传 agent_id 时创建结果 agent_id 为 null", () => {
    const created = createScheduledTask(db, {
      room: "roomA",
      name: "no-agent",
      interval_sec: 30,
      prompt: "no agent",
      owner: "tester",
    });

    expect(created.agent_id).toBeNull();
    expect(getScheduledTask(db, created.id)?.agent_id).toBeNull();
  });
});