import './bcrypt-test-env';
import { describe, it, expect } from 'vitest';
import { DatabaseSync } from 'node:sqlite';
import Fastify, { FastifyInstance } from 'fastify';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import * as path from 'node:path';
import { createDb, initSchema, migrateToMultiUser, todayStr } from '../src/db';
import { registerPlansRoutes } from '../src/routes/plans';
import { registerFocusRoutes } from '../src/routes/focus';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin, authHeaders } from './test-utils';

function makeLegacyTables(db: DatabaseSync): void {
  db.exec(`
    CREATE TABLE plans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT NOT NULL,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      planned_minutes INTEGER NOT NULL DEFAULT 0,
      done INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE focus_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      minutes INTEGER NOT NULL DEFAULT 0,
      started_at TEXT NOT NULL,
      note TEXT NULL
    );
    CREATE TABLE mistakes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      content TEXT NOT NULL DEFAULT '',
      analysis TEXT NOT NULL DEFAULT '',
      mastered INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE words (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      word TEXT NOT NULL UNIQUE,
      phonetic TEXT NOT NULL DEFAULT '',
      meaning TEXT NOT NULL DEFAULT '',
      example TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'manual',
      memory_tip TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE srs_state (
      word_id INTEGER PRIMARY KEY,
      ease REAL NOT NULL DEFAULT 2.5,
      interval_days INTEGER NOT NULL DEFAULT 0,
      repetitions INTEGER NOT NULL DEFAULT 0,
      due_date TEXT NOT NULL,
      FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
    );
    CREATE TABLE exam_records (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      paper TEXT NOT NULL,
      score REAL NOT NULL DEFAULT 0,
      total_score REAL NOT NULL DEFAULT 0,
      duration_minutes INTEGER NOT NULL DEFAULT 0,
      taken_at TEXT NOT NULL
    );
    CREATE TABLE settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
  `);
}

describe('plans_focus_diff deep regression', () => {
  it('老库经 initSchema 迁移后加 plan_id 列、保留老数据、planId 全链路可用', async () => {
    const tmpDir = mkdtempSync(path.join(tmpdir(), 'kaoyan-diffplanid-'));
    const dbPath = path.join(tmpDir, 'legacy-upgrade.db');
    let app: FastifyInstance | undefined;
    let db: DatabaseSync | undefined;
    try {
      const legacy = new DatabaseSync(dbPath);
      legacy.exec('PRAGMA foreign_keys = ON');
      makeLegacyTables(legacy);
      legacy
        .prepare(
          "INSERT INTO plans (date, subject, title, planned_minutes, done) VALUES ('2026-10-01', 'math', 'OldPlan', 60, 0)",
        )
        .run();
      legacy
        .prepare(
          "INSERT INTO focus_sessions (subject, minutes, started_at, note) VALUES ('math', 30, '2026-10-01T10:00:00', 'old note 1')",
        )
        .run();
      legacy
        .prepare(
          "INSERT INTO focus_sessions (subject, minutes, started_at, note) VALUES ('english', 20, '2026-10-02T11:00:00', NULL)",
        )
        .run();
      legacy.close();

      db = createDb(dbPath);

      const focusCols = db.prepare('PRAGMA table_info(focus_sessions)').all() as Array<{ name: string }>;
      expect(focusCols.some((c) => c.name === 'plan_id')).toBe(true);

      const old1 = db
        .prepare('SELECT subject, minutes, started_at, note FROM focus_sessions WHERE id = 1')
        .get() as { subject: string; minutes: number; started_at: string; note: string | null };
      expect(old1.subject).toBe('math');
      expect(old1.minutes).toBe(30);
      expect(old1.started_at).toBe('2026-10-01T10:00:00');
      expect(old1.note).toBe('old note 1');

      const old2 = db
        .prepare('SELECT subject, minutes, started_at, note FROM focus_sessions WHERE id = 2')
        .get() as { subject: string; minutes: number; started_at: string; note: string | null };
      expect(old2.subject).toBe('english');
      expect(old2.minutes).toBe(20);
      expect(old2.started_at).toBe('2026-10-02T11:00:00');
      expect(old2.note).toBeNull();

      const localRow = db.prepare("SELECT id FROM users WHERE username = 'local'").get() as { id: number };
      const oldPlan = db
        .prepare("SELECT user_id, title FROM plans WHERE title = 'OldPlan'")
        .get() as { user_id: number; title: string };
      expect(oldPlan.user_id).toBe(localRow.id);
      expect(oldPlan.title).toBe('OldPlan');

      expect(() => initSchema(db as DatabaseSync)).not.toThrow();

      app = Fastify();
      registerPlansRoutes(app, db);
      registerFocusRoutes(app, db);
      applyAuthHook(app, db);
      registerAuthRoutes(app, db);
      await app.ready();

      const cookie = await registerAndLogin(app, 'diffplan_u1');
      const headers = authHeaders(cookie);

      const planRes = await app.inject({
        method: 'POST',
        url: '/api/plans',
        headers,
        payload: { date: todayStr(), title: 'NewPlan', subject: 'math', plannedMinutes: 60 },
      });
      expect(planRes.statusCode).toBe(201);
      const createdPlan = planRes.json() as { id: number };
      const planId = createdPlan.id;

      const focusRes = await app.inject({
        method: 'POST',
        url: '/api/focus',
        headers,
        payload: { subject: 'math', minutes: 25, planId },
      });
      expect(focusRes.statusCode).toBe(201);
      const focusBody = focusRes.json() as { planId: number };
      expect(focusBody.planId).toBe(planId);

      const summaryRes = await app.inject({
        method: 'GET',
        url: `/api/plans/summary?date=${todayStr()}`,
        headers,
      });
      expect(summaryRes.statusCode).toBe(200);
      const summaryBody = summaryRes.json() as {
        plans: Array<{ id: number; actualMinutes: number }>;
      };
      const found = summaryBody.plans.find((p) => p.id === planId);
      expect(found).toBeDefined();
      expect(found!.actualMinutes).toBe(25);
    } finally {
      if (app) await app.close();
      if (db) db.close();
      rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('migrateToMultiUser 重建 focus_sessions 时 plan_id 数据原样保留', () => {
    const tmpDir2 = mkdtempSync(path.join(tmpdir(), 'kaoyan-diffplanid-'));
    const dbPath2 = path.join(tmpDir2, 'keep-planid.db');
    let db: DatabaseSync | undefined;
    try {
      db = new DatabaseSync(dbPath2);
      db.exec('PRAGMA foreign_keys = ON');
      db.exec(`
        CREATE TABLE users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          token_hash TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
          expires_at TEXT NOT NULL,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
      `);
      makeLegacyTables(db);

      db.exec('ALTER TABLE focus_sessions ADD COLUMN plan_id INTEGER NULL');

      db.prepare(
        "INSERT INTO plans (date, subject, title, planned_minutes, done) VALUES ('2026-10-03', 'math', 'KeepPlan', 45, 0)",
      ).run();
      const keepPlanRow = db
        .prepare("SELECT id FROM plans WHERE title = 'KeepPlan'")
        .get() as { id: number };
      const keepPlanId = keepPlanRow.id;

      db.prepare(
        "INSERT INTO focus_sessions (subject, minutes, started_at, note, plan_id) VALUES ('math', 50, '2026-10-03T09:00:00', 'linked', ?)",
      ).run(keepPlanId);
      db.prepare(
        "INSERT INTO focus_sessions (subject, minutes, started_at, note, plan_id) VALUES ('english', 15, '2026-10-03T10:00:00', NULL, NULL)",
      ).run();

      migrateToMultiUser(db);

      const cols = db.prepare('PRAGMA table_info(focus_sessions)').all() as Array<{ name: string }>;
      expect(cols.some((c) => c.name === 'user_id')).toBe(true);
      expect(cols.some((c) => c.name === 'plan_id')).toBe(true);

      const localRow = db.prepare("SELECT id FROM users WHERE username = 'local'").get() as { id: number };

      const rows = db
        .prepare('SELECT id, plan_id, user_id, subject, minutes, note FROM focus_sessions ORDER BY id')
        .all() as Array<{
        id: number;
        plan_id: number | null;
        user_id: number;
        subject: string;
        minutes: number;
        note: string | null;
      }>;
      expect(rows.length).toBe(2);

      expect(rows[0].plan_id).toBe(keepPlanId);
      expect(rows[0].user_id).toBe(localRow.id);
      expect(rows[0].subject).toBe('math');
      expect(rows[0].minutes).toBe(50);
      expect(rows[0].note).toBe('linked');

      expect(rows[1].plan_id).toBeNull();
      expect(rows[1].user_id).toBe(localRow.id);
      expect(rows[1].subject).toBe('english');
      expect(rows[1].minutes).toBe(15);
      expect(rows[1].note).toBeNull();

      const planRow = db
        .prepare("SELECT user_id, title, planned_minutes FROM plans WHERE id = ?")
        .get(keepPlanId) as { user_id: number; title: string; planned_minutes: number };
      expect(planRow.user_id).toBe(localRow.id);
      expect(planRow.title).toBe('KeepPlan');
      expect(planRow.planned_minutes).toBe(45);
    } finally {
      if (db) db.close();
      rmSync(tmpDir2, { recursive: true, force: true });
    }
  });
});