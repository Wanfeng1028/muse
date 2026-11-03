import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerBackupRoutes } from '../src/routes/backup';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

const TABLE_ORDER = [
  'plans',
  'focus_sessions',
  'mistakes',
  'words',
  'srs_state',
  'exam_records',
  'settings',
];

function emptyTables(): Record<string, unknown[]> {
  const t: Record<string, unknown[]> = {};
  for (const name of TABLE_ORDER) t[name] = [];
  return t;
}

function validPayload(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      format: 'kaoyan-backup',
      version: 1,
      tables: emptyTables(),
    },
    mode: 'replace',
    ...overrides,
  };
}

describe('POST /api/backup/import 校验分支边界', () => {
  let app: FastifyInstance;
  let authCookie = '';
  let db: ReturnType<typeof createDb>;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerBackupRoutes(app, db);
    await app.ready();
    authCookie = await registerAndLogin(app, 'backupboundary');
  });

  afterEach(async () => {
    await app.close();
    db.close();
  });

  function seedPlan(id: number, title: string): void {
    db.prepare(
      'INSERT INTO plans (user_id, id, date, subject, title) VALUES ((SELECT id FROM users WHERE username = \'backupboundary\'), ?, ?, ?, ?)'
    ).run(id, '2024-03-01', 'math', title);
  }

  function planCount(): number {
    return (db.prepare('SELECT COUNT(*) AS c FROM plans').get() as { c: number })
      .c;
  }

  it('version=2 → 400 version 无效', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({
        data: { format: 'kaoyan-backup', version: 2, tables: emptyTables() },
      }),
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'version 无效' });
  });

  it('data 为数组 → 400 data 无效', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({ data: [] }),
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'data 无效' });
  });

  it('data 为字符串 → 400 data 无效', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({ data: 'nope' }),
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'data 无效' });
  });

  it('data.tables 为字符串 → 400 tables 无效', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({
        data: { format: 'kaoyan-backup', version: 1, tables: 'x' },
      }),
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: 'tables 无效' });
  });

  it('整个 body 为数组 → 400 请求体无效', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: [] as unknown,
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '请求体无效' });
  });

  it('tables.plans 行非对象 → 400 含 表 plans 第 1 行不是对象', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({
        data: {
          format: 'kaoyan-backup',
          version: 1,
          tables: { ...emptyTables(), plans: ['not-an-object'] },
        },
      }),
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe('表 plans 第 1 行不是对象');
  });

  it('words 行缺 meaning → 400 含 表 words 第 1 行 与 meaning', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({
        data: {
          format: 'kaoyan-backup',
          version: 1,
          tables: { ...emptyTables(), words: [{ word: 'abandon' }] },
        },
      }),
    });
    expect(res.statusCode).toBe(400);
    const err = res.json().error as string;
    expect(err).toContain('表 words 第 1 行');
    expect(err).toContain('meaning');
    expect(err).toBe('表 words 第 1 行：meaning 缺失或类型不对');
  });

  it('srs_state 行 word_id 为字符串 → 400 含 表 srs_state 第 1 行', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({
        data: {
          format: 'kaoyan-backup',
          version: 1,
          tables: {
            ...emptyTables(),
            srs_state: [{ word_id: '1', due_date: '2024-03-01' }],
          },
        },
      }),
    });
    expect(res.statusCode).toBe(400);
    const err = res.json().error as string;
    expect(err).toContain('表 srs_state 第 1 行');
    expect(err).toBe('表 srs_state 第 1 行：word_id 缺失或类型不对');
  });

  it('exam_records 行缺 taken_at → 400 含 表 exam_records 第 1 行', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({
        data: {
          format: 'kaoyan-backup',
          version: 1,
          tables: {
            ...emptyTables(),
            exam_records: [{ subject: 'math', paper: '2023' }],
          },
        },
      }),
    });
    expect(res.statusCode).toBe(400);
    const err = res.json().error as string;
    expect(err).toContain('表 exam_records 第 1 行');
    expect(err).toBe('表 exam_records 第 1 行：taken_at 缺失或类型不对');
  });

  it('settings 行 value 为数字 → 400 含 表 settings 第 1 行', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({
        data: {
          format: 'kaoyan-backup',
          version: 1,
          tables: { ...emptyTables(), settings: [{ key: 'theme', value: 1 }] },
        },
      }),
    });
    expect(res.statusCode).toBe(400);
    const err = res.json().error as string;
    expect(err).toContain('表 settings 第 1 行');
    expect(err).toBe('表 settings 第 1 行：value 缺失或类型不对');
  });

  it('mode 缺省 → 默认 replace，清空旧数据仅保留导入', async () => {
    seedPlan(1, '旧计划');
    expect(planCount()).toBe(1);

    const payload = {
      data: {
        format: 'kaoyan-backup',
        version: 1,
        tables: {
          ...emptyTables(),
          plans: [{ date: '2024-05-01', subject: 'english', title: '新计划' }],
        },
      },
    };

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload,
    });
    expect(res.statusCode).toBe(200);
    expect(planCount()).toBe(1);
    const rows = db.prepare('SELECT * FROM plans ORDER BY id ASC').all() as Array<{
      title: string;
    }>;
    expect(rows).toHaveLength(1);
    expect(rows[0].title).toBe('新计划');
  });

  it('mode=merge → 追加保留已有 plan', async () => {
    seedPlan(1, '旧计划');

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({
        mode: 'merge',
        data: {
          format: 'kaoyan-backup',
          version: 1,
          tables: {
            ...emptyTables(),
            plans: [{ date: '2024-05-01', subject: 'english', title: '新计划' }],
          },
        },
      }),
    });
    expect(res.statusCode).toBe(200);
    expect(planCount()).toBe(2);
    const titles = (
      db.prepare('SELECT title FROM plans ORDER BY id ASC').all() as Array<{
        title: string;
      }>
    ).map((r) => r.title);
    expect(titles).toContain('旧计划');
    expect(titles).toContain('新计划');
  });

  it('原子性：合法行 + 第 2 行非法 → 400 且库不变', async () => {
    seedPlan(1, '旧计划');
    expect(planCount()).toBe(1);

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: validPayload({
        data: {
          format: 'kaoyan-backup',
          version: 1,
          tables: {
            ...emptyTables(),
            plans: [
              { date: '2024-05-01', subject: 'english', title: '合法行' },
              { date: '2024-05-02', subject: 'english' },
            ],
          },
        },
      }),
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toContain('表 plans 第 2 行');
    expect(planCount()).toBe(1);
    const rows = db.prepare('SELECT title FROM plans').all() as Array<{
      title: string;
    }>;
    expect(rows).toHaveLength(1);
    expect(rows[0].title).toBe('旧计划');
  });
});
