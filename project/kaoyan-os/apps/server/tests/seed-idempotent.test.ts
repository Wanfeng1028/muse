import { describe, it, expect } from 'vitest';
import { createDb, todayStr } from '../src/db';
import { seedIfEmpty } from '../src/seed';
import { DEFAULT_SETTINGS } from '@kaoyan/shared';

function count(db: ReturnType<typeof createDb>, table: string): number {
  const row = db.prepare(`SELECT COUNT(*) AS c FROM ${table}`).get() as { c: number };
  return row.c;
}

describe('seedIfEmpty 全新空库首次种子', () => {
  it('settings 写入 4 行且值与 DEFAULT_SETTINGS 一致', () => {
    const db = createDb(':memory:');
    seedIfEmpty(db);

    expect(count(db, 'settings')).toBe(4);

    const rows = db
      .prepare('SELECT key, value FROM settings ORDER BY key')
      .all() as Array<{ key: string; value: string }>;
    const map = new Map(rows.map((r) => [r.key, r.value]));

    expect([...map.keys()].sort()).toEqual([
      'break_minutes',
      'daily_goal_minutes',
      'exam_date',
      'pomodoro_minutes',
    ]);
    expect(map.get('exam_date')).toBe(DEFAULT_SETTINGS.examDate);
    expect(map.get('daily_goal_minutes')).toBe(String(DEFAULT_SETTINGS.dailyGoalMinutes));
    expect(map.get('pomodoro_minutes')).toBe(String(DEFAULT_SETTINGS.pomodoroMinutes));
    expect(map.get('break_minutes')).toBe(String(DEFAULT_SETTINGS.breakMinutes));
  });

  it('words 24 行且 source 全为 builtin，srs_state 24 行且初始状态正确', () => {
    const db = createDb(':memory:');
    seedIfEmpty(db);

    expect(count(db, 'words')).toBe(24);
    const sources = db.prepare('SELECT DISTINCT source FROM words').all() as Array<{ source: string }>;
    expect(sources.map((s) => s.source)).toEqual(['builtin']);

    expect(count(db, 'srs_state')).toBe(24);
    const states = db
      .prepare('SELECT ease, interval_days, repetitions, due_date FROM srs_state')
      .all() as Array<{ ease: number; interval_days: number; repetitions: number; due_date: string }>;
    expect(states).toHaveLength(24);
    for (const s of states) {
      expect(s.ease).toBe(2.5);
      expect(s.interval_days).toBe(0);
      expect(s.repetitions).toBe(0);
      expect(s.due_date).toBe(todayStr());
    }
  });

  it('plans/mistakes/exam_records/focus_sessions 行数与日期正确', () => {
    const db = createDb(':memory:');
    seedIfEmpty(db);

    expect(count(db, 'plans')).toBe(6);
    const planDates = db.prepare('SELECT DISTINCT date FROM plans').all() as Array<{ date: string }>;
    expect(planDates.map((d) => d.date)).toEqual([todayStr()]);

    expect(count(db, 'mistakes')).toBe(3);
    expect(count(db, 'exam_records')).toBe(2);
    expect(count(db, 'focus_sessions')).toBe(8);
  });
});

describe('seedIfEmpty 幂等性与部分状态', () => {
  it('连续跑两次后 7 张表行数不变（words 不会变 48）', () => {
    const db = createDb(':memory:');
    seedIfEmpty(db);
    const tables = ['settings', 'words', 'srs_state', 'plans', 'mistakes', 'exam_records', 'focus_sessions'];
    const before = tables.map((t) => count(db, t));

    seedIfEmpty(db);

    const after = tables.map((t) => count(db, t));
    expect(after).toEqual(before);
    expect(count(db, 'words')).toBe(24);
    expect(count(db, 'srs_state')).toBe(24);
    expect(count(db, 'settings')).toBe(4);
    expect(count(db, 'plans')).toBe(6);
    expect(count(db, 'mistakes')).toBe(3);
    expect(count(db, 'exam_records')).toBe(2);
    expect(count(db, 'focus_sessions')).toBe(8);
  });

  it('words 表已有 1 行时不再补种，但 plans 为空仍被种出 6 行', () => {
    const db = createDb(':memory:');
    const uid1 = (db.prepare("SELECT id FROM users WHERE username = 'local'").get() as { id: number }).id;
    db.prepare('INSERT INTO words (user_id, word, source) VALUES (?, ?, ?)').run(uid1, 'custom', 'manual');
    expect(count(db, 'words')).toBe(1);

    seedIfEmpty(db);

    expect(count(db, 'words')).toBe(1);
    const rows = db.prepare('SELECT word FROM words').all() as Array<{ word: string }>;
    expect(rows.map((r) => r.word)).toEqual(['custom']);
    expect(count(db, 'srs_state')).toBe(0);
    expect(count(db, 'plans')).toBe(6);
  });

  it('settings 表已有 1 行时不再补默认 4 行', () => {
    const db = createDb(':memory:');
    const uid2 = (db.prepare("SELECT id FROM users WHERE username = 'local'").get() as { id: number }).id;
    db.prepare('INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)').run(uid2, 'exam_date', '2099-01-01');

    seedIfEmpty(db);

    expect(count(db, 'settings')).toBe(1);
    const row = db.prepare('SELECT value FROM settings WHERE key = ?').get('exam_date') as {
      value: string;
    };
    expect(row.value).toBe('2099-01-01');
  });
});