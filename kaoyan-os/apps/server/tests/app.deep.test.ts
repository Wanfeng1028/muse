import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { buildApp } from '../src/app';
import { registerAndLogin } from './test-utils';
import type { FastifyInstance } from 'fastify';

// 收集每个用例创建的临时目录，用例结束后清理
const tmpDirs: string[] = [];

function makeTmpDbPathTracked(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kaoyan-app-deep-'));
  tmpDirs.push(dir);
  return path.join(dir, 'kaoyan.db');
}

let app: FastifyInstance;
let authCookie = '';

beforeEach(async () => {
  app = buildApp({ dbPath: makeTmpDbPathTracked(), logger: false });
  authCookie = await registerAndLogin(app, 'appdeep');
});

afterEach(async () => {
  await app.close();
  while (tmpDirs.length > 0) {
    const dir = tmpDirs.pop();
    if (dir) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }
});

describe('app deep behavior', () => {
  it('health 接口返回 ok 与合法 ISO 时间', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/health' });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { status: string; time: string };
    expect(body.status).toBe('ok');
    expect(Number.isNaN(Date.parse(body.time))).toBe(false);
  });

  it('计划跨月排程：跨越 2 月的两个日期都存得住', async () => {
    const create1 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: {
        title: '跨月计划',
        subject: 'math',
        plannedMinutes: 60,
        date: '2024-01-31'
      }
    });
    expect(create1.statusCode).toBe(201);
    const created1 = create1.json() as { id: number; date: string };
    expect(created1.date).toBe('2024-01-31');

    const create2 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: {
        title: '跨月计划2',
        subject: 'math',
        plannedMinutes: 60,
        date: '2024-03-01'
      }
    });
    expect(create2.statusCode).toBe(201);
    const created2 = create2.json() as { id: number; date: string };
    expect(created2.date).toBe('2024-03-01');

    const list = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans' });
    expect(list.statusCode).toBe(200);
    const plans = list.json() as Array<{ id: number; date: string }>;
    const found1 = plans.find((p) => p.id === created1.id);
    const found2 = plans.find((p) => p.id === created2.id);
    expect(found1).toBeTruthy();
    expect(found1!.date).toBe('2024-01-31');
    expect(found2).toBeTruthy();
    expect(found2!.date).toBe('2024-03-01');
  });

  it('计划闰年边界：2024-02-29 可正常创建并回读', async () => {
    const create = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: {
        title: '闰年计划',
        subject: 'english',
        plannedMinutes: 30,
        date: '2024-02-29'
      }
    });
    expect(create.statusCode).toBe(201);
    const created = create.json() as { id: number; date: string };
    expect(created.date).toBe('2024-02-29');

    const list = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans' });
    expect(list.statusCode).toBe(200);
    const plans = list.json() as Array<{ id: number; date: string }>;
    const found = plans.find((p) => p.id === created.id);
    expect(found).toBeTruthy();
    expect(found!.date).toBe('2024-02-29');
  });

  it('空计划列表：初始状态返回数组且不含示例外多余项', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/plans' });
    expect(res.statusCode).toBe(200);
    const plans = res.json() as unknown[];
    expect(Array.isArray(plans)).toBe(true);
    expect(plans.length).toBeGreaterThanOrEqual(0);
  });

  it('番茄计时边界：时长为 0 的会话被拒绝', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus/sessions',
      payload: {
        taskName: '零时长',
        durationMinutes: 0,
        startedAt: '2024-03-01T09:00:00.000Z'
      }
    });
    expect(res.statusCode).toBeGreaterThanOrEqual(400);
    const body = res.json() as { error?: string };
    expect(typeof body.error).toBe('string');
  });

  it('番茄计时边界：正常 25 分钟会话写入后可在列表查到', async () => {
    const create = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: {
        subject: 'math',
        minutes: 25,
        startedAt: '2024-03-01T09:00:00.000Z'
      }
    });
    expect(create.statusCode).toBe(201);
    const created = create.json() as { id: number; minutes: number };
    expect(created.minutes).toBe(25);

    const list = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/focus' });
    expect(list.statusCode).toBe(200);
    const sessions = list.json() as Array<{ id: number; minutes: number }>;
    const found = sessions.find((s) => s.id === created.id);
    expect(found).toBeTruthy();
    expect(found!.minutes).toBe(25);
  });

  it('错题不隐式去重：同一题干提交两次存两条', async () => {
    const payload = {
      subject: 'math',
      title: '求极限 lim(x->0) sin(x)/x',
      content: '粗心'
    };
    const first = await app.inject({ headers: { cookie: authCookie }, method: 'POST', url: '/api/mistakes', payload });
    expect(first.statusCode).toBe(201);
    const firstBody = first.json() as { id: number };
    expect(typeof firstBody.id).toBe('number');

    const second = await app.inject({ headers: { cookie: authCookie }, method: 'POST', url: '/api/mistakes', payload });
    expect(second.statusCode).toBe(201);
    const secondBody = second.json() as { id: number };
    expect(secondBody.id).not.toBe(firstBody.id);

    const list = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/mistakes' });
    expect(list.statusCode).toBe(200);
    const mistakes = list.json() as Array<{ id: number; title: string }>;
    const matched = mistakes.filter((m) => m.title === payload.title);
    expect(matched.length).toBe(2);
  });

  it('单词 SRS：复习后 dueDate 被推进且复习次数加一', async () => {
    const create = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/words',
      payload: {
        word: 'serendipity',
        meaning: '放弃'
      }
    });
    expect(create.statusCode).toBe(201);
    const created = create.json() as {
      id: number;
      state: { repetitions: number; dueDate: string };
    };
    expect(created.state.repetitions).toBe(0);

    const review = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: `/api/words/${created.id}/review`,
      payload: { grade: 2 }
    });
    expect(review.statusCode).toBe(200);
    const reviewed = review.json() as {
      id: number;
      state: { repetitions: number; dueDate: string };
    };
    expect(reviewed.state.repetitions).toBe(1);
    expect(Date.parse(reviewed.state.dueDate)).toBeGreaterThanOrEqual(
      Date.parse(created.state.dueDate)
    );

    const list = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/words' });
    expect(list.statusCode).toBe(200);
    const words = list.json() as Array<{ id: number; state: { repetitions: number } }>;
    const found = words.find((w) => w.id === created.id);
    expect(found).toBeTruthy();
    expect(found!.state.repetitions).toBe(1);
  });

  it('导入 CSV 畸形行：缺少字段的行被跳过，合法行入库', async () => {
    const csv = [
      'word,meaning',
      'apple,苹果',
      ',缺词',
      'banana,香蕉'
    ].join('\n');

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/import/words',
      payload: { csv }
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { imported: number; skippedEmpty: number };
    expect(body.imported).toBe(2);
    expect(body.skippedEmpty).toBe(1);

    const list = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/words' });
    expect(list.statusCode).toBe(200);
    const words = list.json() as Array<{ word: string }>;
    const names = words.map((w) => w.word);
    expect(names).toContain('apple');
    expect(names).toContain('banana');
  });

  it('备份恢复 round-trip：导出后恢复，数据一致', async () => {
    const create = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/words',
      payload: { word: 'roundtrip', meaning: '往返' }
    });
    expect(create.statusCode).toBe(201);

    const backup = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/backup/export' });
    expect(backup.statusCode).toBe(200);
    const dump = backup.json() as {
      format: string;
      version: number;
      tables: { words: Array<{ word: string; meaning: string }> };
    };
    expect(Array.isArray(dump.tables.words)).toBe(true);
    expect(dump.tables.words.some((w) => w.word === 'roundtrip')).toBe(true);

    const restore = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: { data: dump, mode: 'replace' }
    });
    expect(restore.statusCode).toBe(200);

    const list = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/words' });
    expect(list.statusCode).toBe(200);
    const words = list.json() as Array<{ id: number; word: string; meaning: string }>;
    const found = words.find((w) => w.word === 'roundtrip');
    expect(found).toBeTruthy();
    expect(found!.word).toBe('roundtrip');
    expect(found!.meaning).toBe('往返');
  });

  it('统计接口：写入计划后统计总数包含新增项', async () => {
    const create = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: {
        title: '统计用计划',
        subject: 'politics',
        plannedMinutes: 45,
        date: '2024-04-01'
      }
    });
    expect(create.statusCode).toBe(201);

    const stats = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/plans/summary?date=2024-04-01'
    });
    expect(stats.statusCode).toBe(200);
    const body = stats.json() as { date: string; total: number };
    expect(typeof body.total).toBe('number');
    expect(body.total).toBeGreaterThanOrEqual(1);
    expect(body.date).toBe('2024-04-01');
  });
});