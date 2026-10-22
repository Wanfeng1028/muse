import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb } from "../src/db.js";
import {
  createScheduledTask, claimDueScheduledTasks, deleteScheduledTask, updateScheduledTask,
} from "../src/workflows.js";
import type { Db } from "../src/db.js";

let dir: string;
let db: Db;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "wf-")); db = openDb(dir); });
afterEach(() => { db.close(); rmSync(dir, { recursive: true, force: true }); });

describe("claimDueScheduledTasks", () => {
  const now = 1_700_000_000_000;

  it("未到期的任务不被 claim", () => {
    const task = createScheduledTask(db, {
      room: "room-a",
      name: "future-task",
      interval_sec: 3600,
      prompt: "prompt",
      owner: "owner",
    });
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now + 60000, task.id);

    const claimed = claimDueScheduledTasks(db, now);

    expect(claimed).toEqual([]);
    const row = db.prepare("SELECT next_run_ms FROM scheduled_tasks WHERE id = ?").get(task.id) as unknown as { next_run_ms: number };
    expect(row.next_run_ms).toBe(now + 60000);
  });

  it("三个到期任务按 next_run_ms 升序被 claim", () => {
    const early = createScheduledTask(db, {
      room: "room-a",
      name: "early",
      interval_sec: 3600,
      prompt: "prompt",
      owner: "owner",
    });
    const middle = createScheduledTask(db, {
      room: "room-a",
      name: "middle",
      interval_sec: 3600,
      prompt: "prompt",
      owner: "owner",
    });
    const late = createScheduledTask(db, {
      room: "room-a",
      name: "late",
      interval_sec: 3600,
      prompt: "prompt",
      owner: "owner",
    });

    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now - 3000, early.id);
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now - 2000, middle.id);
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now - 1000, late.id);

    const claimed = claimDueScheduledTasks(db, now);

    expect(claimed).toHaveLength(3);
    expect(claimed.map((task) => task.id)).toEqual([early.id, middle.id, late.id]);
  });

  it("claim 成功后更新 next_run_ms 和 last_run_ms", () => {
    const task = createScheduledTask(db, {
      room: "room-a",
      name: "due-task",
      interval_sec: 3600,
      prompt: "prompt",
      owner: "owner",
    });
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now - 1000, task.id);

    const claimed = claimDueScheduledTasks(db, now);

    expect(claimed).toHaveLength(1);
    expect(claimed[0].id).toBe(task.id);
    expect(claimed[0].next_run_ms).toBe(now + task.interval_sec * 1000);
    expect(claimed[0].last_run_ms).toBe(now);

    const row = db.prepare("SELECT next_run_ms, last_run_ms FROM scheduled_tasks WHERE id = ?").get(task.id) as unknown as { next_run_ms: number; last_run_ms: number };
    expect(row.next_run_ms).toBe(now + task.interval_sec * 1000);
    expect(row.last_run_ms).toBe(now);
  });

  it("同一 nowMs 立刻再次 claim 返回空数组", () => {
    const task = createScheduledTask(db, {
      room: "room-a",
      name: "idempotent-task",
      interval_sec: 60,
      prompt: "prompt",
      owner: "owner",
    });
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now - 1000, task.id);

    const firstClaim = claimDueScheduledTasks(db, now);
    const secondClaim = claimDueScheduledTasks(db, now);

    expect(firstClaim).toHaveLength(1);
    expect(secondClaim).toEqual([]);
  });

  it("enabled=0 的到期任务不被 claim", () => {
    const task = createScheduledTask(db, {
      room: "room-a",
      name: "disabled-task",
      interval_sec: 3600,
      prompt: "prompt",
      owner: "owner",
    });
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now - 1000, task.id);
    updateScheduledTask(db, task.id, { enabled: false });

    const claimed = claimDueScheduledTasks(db, now);

    expect(claimed).toEqual([]);
    const row = db.prepare("SELECT next_run_ms FROM scheduled_tasks WHERE id = ?").get(task.id) as unknown as { next_run_ms: number };
    expect(row.next_run_ms).toBe(now - 1000);
  });

  it("interval_sec=60 的任务到期可正常 claim", () => {
    const task = createScheduledTask(db, {
      room: "room-a",
      name: "min-interval-task",
      interval_sec: 60,
      prompt: "prompt",
      owner: "owner",
    });
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now - 1000, task.id);

    const claimed = claimDueScheduledTasks(db, now);

    expect(claimed).toHaveLength(1);
    expect(claimed[0].id).toBe(task.id);
    expect(claimed[0].next_run_ms).toBe(now + 60 * 1000);
    expect(claimed[0].last_run_ms).toBe(now);
  });

  it("跨 room 的到期任务都会被 claim", () => {
    const roomATask = createScheduledTask(db, {
      room: "room-a",
      name: "room-a-task",
      interval_sec: 3600,
      prompt: "prompt",
      owner: "owner",
    });
    const roomBTask = createScheduledTask(db, {
      room: "room-b",
      name: "room-b-task",
      interval_sec: 3600,
      prompt: "prompt",
      owner: "owner",
    });
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now - 3000, roomATask.id);
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now - 2000, roomBTask.id);

    const claimed = claimDueScheduledTasks(db, now);

    expect(claimed).toHaveLength(2);
    expect(claimed.map((task) => task.id)).toEqual([roomATask.id, roomBTask.id]);
    expect(claimed.map((task) => task.room)).toEqual(["room-a", "room-b"]);
  });

  it("删除任务后不再被 claim", () => {
    const task = createScheduledTask(db, {
      room: "room-a",
      name: "deleted-task",
      interval_sec: 3600,
      prompt: "prompt",
      owner: "owner",
    });
    db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(now - 1000, task.id);
    deleteScheduledTask(db, task.id);

    const claimed = claimDueScheduledTasks(db, now);

    expect(claimed).toEqual([]);
  });
});