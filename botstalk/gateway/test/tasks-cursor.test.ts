import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { openDb, upsertTaskDispatch, listTasks, type Db } from "../src/db.js";

const TEST_TMP_ROOT = join(import.meta.dirname ?? __dirname, "test-tmp");
mkdirSync(TEST_TMP_ROOT, { recursive: true });

describe("listTasks cursor pagination", () => {
  let dir: string;
  let db: Db;

  beforeEach(() => {
    dir = mkdtempSync(join(TEST_TMP_ROOT, "tasks-cursor-"));
    db = openDb(join(dir, "test.db"));
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  function seed(): void {
    upsertTaskDispatch(db, { task_id: "t1", room: "r", owner: "o", assignee: "a", title: "T1", status: "pending" });
    upsertTaskDispatch(db, { task_id: "t2", room: "r", owner: "o", assignee: "a", title: "T2", status: "pending" });
    upsertTaskDispatch(db, { task_id: "t3", room: "r", owner: "o", assignee: "a", title: "T3", status: "pending" });
    upsertTaskDispatch(db, { task_id: "t4", room: "r", owner: "o", assignee: "a", title: "T4", status: "pending" });
    upsertTaskDispatch(db, { task_id: "t5", room: "r", owner: "o", assignee: "a", title: "T5", status: "pending" });
    const upd = db.prepare("UPDATE tasks SET updated_at_ms = ? WHERE task_id = ?");
    upd.run(3000, "t1");
    upd.run(1000, "t2");
    upd.run(1000, "t3");
    upd.run(1000, "t4");
    upd.run(500, "t5");
  }

  it("pages through all tasks with cursor, no dup no miss", () => {
    seed();
    const page1 = listTasks(db, { limit: 2 });
    expect(page1.map((r) => r.task_id)).toEqual(["t1", "t2"]);

    const last1 = page1[page1.length - 1];
    const page2 = listTasks(db, {
      limit: 2,
      before_updated_ms: last1.updated_at_ms,
      before_task_id: last1.task_id,
    });
    expect(page2.map((r) => r.task_id)).toEqual(["t3", "t4"]);

    const last2 = page2[page2.length - 1];
    const page3 = listTasks(db, {
      limit: 2,
      before_updated_ms: last2.updated_at_ms,
      before_task_id: last2.task_id,
    });
    expect(page3.map((r) => r.task_id)).toEqual(["t5"]);

    const last3 = page3[page3.length - 1];
    const page4 = listTasks(db, {
      limit: 2,
      before_updated_ms: last3.updated_at_ms,
      before_task_id: last3.task_id,
    });
    expect(page4.map((r) => r.task_id)).toEqual([]);

    const all = [...page1, ...page2, ...page3].map((r) => r.task_id);
    expect(all).toEqual(["t1", "t2", "t3", "t4", "t5"]);
    expect(new Set(all).size).toBe(5);
  });

  it("ignores cursor when only before_updated_ms is provided", () => {
    seed();
    const page1 = listTasks(db, { limit: 2 });
    const partial = listTasks(db, { limit: 2, before_updated_ms: 1000 });
    expect(partial.map((r) => r.task_id)).toEqual(page1.map((r) => r.task_id));
  });

  it("ignores cursor when only before_task_id is provided", () => {
    seed();
    const page1 = listTasks(db, { limit: 2 });
    const partial = listTasks(db, { limit: 2, before_task_id: "t2" });
    expect(partial.map((r) => r.task_id)).toEqual(page1.map((r) => r.task_id));
  });
});
