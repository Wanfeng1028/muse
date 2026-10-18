import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, savePendingFrame, loadPendingFrames, prunePendingFrames } from "../src/db.js";

let dir: string;
let db: ReturnType<typeof openDb>;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "botstalk-pending-")); db = openDb(dir); });
afterEach(() => { try { (db as unknown as { close?: () => void }).close?.(); } catch {} try { rmSync(dir, { recursive: true, force: true }); } catch {} });

describe("db-pending-frames.r3", () => {
  it("save 一条后 load 应取回该条且 gseq 与 envelope 字段一致", () => {
    savePendingFrame(db, "a", 5, '{"t":1}');
    const rows = loadPendingFrames(db, "a");
    expect(rows.length).toBe(1);
    expect(rows[0].gseq).toBe(5);
    expect(rows[0].envelope).toBe('{"t":1}');
  });

  it("乱序 save gseq 9、3、7 后 load 应按 gseq 升序返回 [3,7,9]", () => {
    savePendingFrame(db, "a", 9, '{"g":9}');
    savePendingFrame(db, "a", 3, '{"g":3}');
    savePendingFrame(db, "a", 7, '{"g":7}');
    const rows = loadPendingFrames(db, "a");
    expect(rows.map((r) => r.gseq)).toEqual([3, 7, 9]);
  });

  it("load 不存在的 adapter 应返回空数组", () => {
    const rows = loadPendingFrames(db, "ghost");
    expect(rows).toEqual([]);
  });

  it("save gseq 1..5 后 prune keepMax=2 应仅保留最新两条 gseq 4 与 5", () => {
    savePendingFrame(db, "a", 1, '{"g":1}');
    savePendingFrame(db, "a", 2, '{"g":2}');
    savePendingFrame(db, "a", 3, '{"g":3}');
    savePendingFrame(db, "a", 4, '{"g":4}');
    savePendingFrame(db, "a", 5, '{"g":5}');
    prunePendingFrames(db, "a", 2);
    const rows = loadPendingFrames(db, "a");
    expect(rows.map((r) => r.gseq)).toEqual([4, 5]);
  });

  it("save 两条后 prune keepMax=0 应删除全部记录 load 返回空数组", () => {
    savePendingFrame(db, "a", 1, '{"g":1}');
    savePendingFrame(db, "a", 2, '{"g":2}');
    prunePendingFrames(db, "a", 0);
    const rows = loadPendingFrames(db, "a");
    expect(rows).toEqual([]);
  });

  it("prune adapter a 时不应影响 adapter b 的记录", () => {
    savePendingFrame(db, "a", 1, '{"a":1}');
    savePendingFrame(db, "a", 2, '{"a":2}');
    savePendingFrame(db, "a", 3, '{"a":3}');
    savePendingFrame(db, "b", 1, '{"b":1}');
    savePendingFrame(db, "b", 2, '{"b":2}');
    prunePendingFrames(db, "a", 1);
    const rowsA = loadPendingFrames(db, "a");
    const rowsB = loadPendingFrames(db, "b");
    expect(rowsA.map((r) => r.gseq)).toEqual([3]);
    expect(rowsB.map((r) => r.gseq)).toEqual([1, 2]);
  });

  it("prune 不存在的 adapter 应不抛错且后续 load 仍为空", () => {
    expect(() => prunePendingFrames(db, "ghost", 5)).not.toThrow();
    expect(loadPendingFrames(db, "ghost")).toEqual([]);
  });

  it("envelope 为 5000 个 x 的大文本应原样存取逐字相等", () => {
    const big = "x".repeat(5000);
    savePendingFrame(db, "a", 1, big);
    const rows = loadPendingFrames(db, "a");
    expect(rows.length).toBe(1);
    expect(rows[0].envelope).toBe(big);
    expect(rows[0].envelope.length).toBe(5000);
  });
});