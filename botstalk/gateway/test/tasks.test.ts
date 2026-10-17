import { describe, it, expect } from "vitest";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import {
  openDb,
  upsertTaskDispatch,
  updateTaskStatus,
  getTask,
  listTasks,
  countTasksByStatus,
} from "../src/db";

function newDb() {
  return openDb(join(tmpdir(), `botstalk-tasks-${randomUUID()}.db`));
}

describe("tasks", () => {
  it("dispatch 登记后 getTask 字段齐全", () => {
    const db = newDb();
    upsertTaskDispatch(db, {
      task_id: "t1",
      room: "r1",
      owner: "alice",
      assignee: "bob",
      title: "hello",
      status: "dispatched",
    });
    const row = getTask(db, "t1");
    expect(row).toBeDefined();
    expect(row!.task_id).toBe("t1");
    expect(row!.room).toBe("r1");
    expect(row!.owner).toBe("alice");
    expect(row!.assignee).toBe("bob");
    expect(row!.title).toBe("hello");
    expect(row!.status).toBe("dispatched");
    expect(typeof row!.created_at_ms).toBe("number");
    expect(typeof row!.updated_at_ms).toBe("number");
  });

  it("重复 task_id 幂等更新（状态与 assignee 被覆盖，created_at_ms 不变）", async () => {
    const db = newDb();
    upsertTaskDispatch(db, {
      task_id: "t1",
      room: "r1",
      owner: "alice",
      assignee: "bob",
      title: "hello",
      status: "dispatched",
    });
    const before = getTask(db, "t1")!;
    await new Promise((r) => setTimeout(r, 5));
    upsertTaskDispatch(db, {
      task_id: "t1",
      room: "r1",
      owner: "alice",
      assignee: "carol",
      title: "hello",
      status: "running",
    });
    const after = getTask(db, "t1")!;
    expect(after.status).toBe("running");
    expect(after.assignee).toBe("carol");
    expect(after.created_at_ms).toBe(before.created_at_ms);
    expect(after.updated_at_ms).toBeGreaterThanOrEqual(before.updated_at_ms);
  });

  it("updateTaskStatus 流转 running→done", () => {
    const db = newDb();
    upsertTaskDispatch(db, {
      task_id: "t1",
      room: "r1",
      owner: "alice",
      assignee: null,
      title: "hello",
      status: "dispatched",
    });
    expect(updateTaskStatus(db, "t1", "running")).toBe(true);
    expect(getTask(db, "t1")!.status).toBe("running");
    expect(updateTaskStatus(db, "t1", "done")).toBe(true);
    expect(getTask(db, "t1")!.status).toBe("done");
  });

  it("不存在的 task_id 返回 false", () => {
    const db = newDb();
    expect(updateTaskStatus(db, "nope", "done")).toBe(false);
  });

  it("listTasks 按 room/status 过滤与倒序", async () => {
    const db = newDb();
    upsertTaskDispatch(db, { task_id: "a", room: "r1", owner: "o", assignee: null, title: "a", status: "dispatched" });
    await new Promise((r) => setTimeout(r, 5));
    upsertTaskDispatch(db, { task_id: "b", room: "r1", owner: "o", assignee: null, title: "b", status: "running" });
    await new Promise((r) => setTimeout(r, 5));
    upsertTaskDispatch(db, { task_id: "c", room: "r2", owner: "o", assignee: null, title: "c", status: "running" });

    const all = listTasks(db, {});
    expect(all.length).toBe(3);
    expect(all[0].task_id).toBe("c");
    expect(all[1].task_id).toBe("b");
    expect(all[2].task_id).toBe("a");

    const r1 = listTasks(db, { room: "r1" });
    expect(r1.map((x) => x.task_id)).toEqual(["b", "a"]);

    const running = listTasks(db, { status: "running" });
    expect(running.map((x) => x.task_id)).toEqual(["c", "b"]);

    const r1running = listTasks(db, { room: "r1", status: "running" });
    expect(r1running.map((x) => x.task_id)).toEqual(["b"]);
  });

  it("countTasksByStatus 计数正确", () => {
    const db = newDb();
    upsertTaskDispatch(db, { task_id: "a", room: "r1", owner: "o", assignee: null, title: "a", status: "dispatched" });
    upsertTaskDispatch(db, { task_id: "b", room: "r1", owner: "o", assignee: null, title: "b", status: "running" });
    upsertTaskDispatch(db, { task_id: "c", room: "r2", owner: "o", assignee: null, title: "c", status: "running" });
    upsertTaskDispatch(db, { task_id: "d", room: "r2", owner: "o", assignee: null, title: "d", status: "done" });

    const all = countTasksByStatus(db);
    expect(all).toEqual({ dispatched: 1, running: 2, done: 1 });

    const r1 = countTasksByStatus(db, "r1");
    expect(r1).toEqual({ dispatched: 1, running: 1 });

    const r2 = countTasksByStatus(db, "r2");
    expect(r2).toEqual({ running: 1, done: 1 });
  });

  it("limit 上限 200（传 500 只回 200）", () => {
    const db = newDb();
    for (let i = 0; i < 250; i++) {
      upsertTaskDispatch(db, {
        task_id: `t${String(i).padStart(4, "0")}`,
        room: "r1",
        owner: "o",
        assignee: null,
        title: "x",
        status: "dispatched",
      });
    }
    const rows = listTasks(db, { limit: 500 });
    expect(rows.length).toBe(200);
  });
});
