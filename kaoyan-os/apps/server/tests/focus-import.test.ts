import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerFocusRoutes } from '../src/routes/focus';
import { registerAndLogin } from './test-utils';

type ImportResult = {
  imported: number;
  errors: Array<{ row: number; message: string }>;
  errorRows: number;
};

type FocusListItem = {
  subject: string;
  minutes: number;
  startedAt: string;
  note: string | null;
  planId: number | null;
};

describe('POST /api/import/focus', () => {
  let app: FastifyInstance;
  let db: ReturnType<typeof createDb>;
  let cookie: string;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerFocusRoutes(app, db);
    await app.ready();
    cookie = await registerAndLogin(app, 'focuscsv');
  });

  afterEach(async () => {
    await app.close();
    db.close();
  });

  const postImport = (csv: string) =>
    app.inject({
      method: 'POST',
      url: '/api/import/focus',
      headers: { cookie },
      payload: { csv },
    });

  const getFocusList = async (): Promise<FocusListItem[]> => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus',
      headers: { cookie },
    });
    expect(res.statusCode).toBe(200);
    return res.json() as FocusListItem[];
  };

  it('空 csv 返回 400', async () => {
    const empty = await postImport('');
    expect(empty.statusCode).toBe(400);
    expect(empty.json()).toEqual({ error: 'csv 不能为空' });

    const blank = await postImport('   \n\t');
    expect(blank.statusCode).toBe(400);
    expect(blank.json()).toEqual({ error: 'csv 不能为空' });
  });

  it('缺少必需列返回 400', async () => {
    const res = await postImport('subject,minutes\nmath,30');
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '缺少必需列：subject / minutes / started_at' });
  });

  it('两行合法加一行非法 minutes：合法行入库、非法行记错且行号正确', async () => {
    const csv = [
      'subject,minutes,started_at',
      'math,30,2024-05-01',
      'english,45,2024-05-02',
      'math,0,2024-05-03',
    ].join('\n');

    const res = await postImport(csv);
    expect(res.statusCode).toBe(200);
    const body = res.json() as ImportResult;
    expect(body.imported).toBe(2);
    expect(body.errorRows).toBe(1);
    expect(body.errors).toHaveLength(1);
    expect(body.errors[0].row).toBe(4);
    expect(typeof body.errors[0].message).toBe('string');

    const list = await getFocusList();
    expect(list).toHaveLength(2);
  });

  it('note 缺省为 null 且 plan_id 缺省为 null', async () => {
    const csv = ['subject,minutes,started_at', 'math,30,2024-05-01'].join('\n');

    const res = await postImport(csv);
    expect(res.statusCode).toBe(200);
    expect((res.json() as ImportResult).imported).toBe(1);

    const list = await getFocusList();
    expect(list).toHaveLength(1);
    expect(list[0]).toMatchObject({
      subject: 'math',
      minutes: 30,
      note: null,
      planId: null,
    });
    expect(list[0]).toHaveProperty('startedAt');
  });

  it('非法 subject 记错且不入库', async () => {
    const csv = ['subject,minutes,started_at', '数学,30,2024-05-01'].join('\n');

    const res = await postImport(csv);
    expect(res.statusCode).toBe(200);
    const body = res.json() as ImportResult;
    expect(body.imported).toBe(0);
    expect(body.errorRows).toBe(1);
    expect(body.errors).toHaveLength(1);
    expect(body.errors[0].row).toBe(2);

    const list = await getFocusList();
    expect(list).toHaveLength(0);
  });

  it('未登录返回 401', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/focus',
      payload: { csv: 'subject,minutes,started_at\nmath,30,2024-05-01' },
    });
    expect(res.statusCode).toBe(401);
  });
});
