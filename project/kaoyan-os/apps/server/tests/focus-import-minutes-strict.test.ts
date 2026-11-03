import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify from 'fastify';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerFocusRoutes } from '../src/routes/focus';
import { registerAndLogin } from './test-utils';

describe('POST /api/import/focus - minutes strict validation', () => {
  let app: Fastify.FastifyInstance;
  let db: ReturnType<typeof createDb>;
  let cookie: string;

  beforeEach(async () => {
    db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerFocusRoutes(app, db);
    await app.ready();
    cookie = await registerAndLogin(app, 'focusimportminutes');
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

  const getFocusList = () =>
    app.inject({
      method: 'GET',
      url: '/api/focus',
      headers: { cookie },
    });

  it('minutes=60.5 is an error row, not imported', async () => {
    const csv = 'subject,minutes,started_at\nmath,60.5,2026-02-01';
    const res = await postImport(csv);
    expect(res.statusCode).toBe(200);
    const body = await res.json();
    expect(body.imported).toBe(0);
    expect(body.errorRows).toBe(1);
    expect(body.errors).toHaveLength(1);
    expect(body.errors[0].row).toBe(2);
    expect(body.errors[0].message).toBe('minutes 须为 1 到 1440 之间的整数');
    const listRes = await getFocusList();
    expect(listRes.statusCode).toBe(200);
    const listBody = await listRes.json();
    expect(listBody).toHaveLength(0);
  });

  it('minutes=0x3c is an error row, not imported', async () => {
    const csv = 'subject,minutes,started_at\nmath,0x3c,2026-02-01';
    const res = await postImport(csv);
    expect(res.statusCode).toBe(200);
    const body = await res.json();
    expect(body.imported).toBe(0);
    expect(body.errorRows).toBe(1);
    expect(body.errors).toHaveLength(1);
    expect(body.errors[0].row).toBe(2);
    expect(body.errors[0].message).toBe('minutes 须为 1 到 1440 之间的整数');
    const listRes = await getFocusList();
    expect(listRes.statusCode).toBe(200);
    const listBody = await listRes.json();
    expect(listBody).toHaveLength(0);
  });

  it('minutes=1e2 is an error row, not imported', async () => {
    const csv = 'subject,minutes,started_at\nmath,1e2,2026-02-01';
    const res = await postImport(csv);
    expect(res.statusCode).toBe(200);
    const body = await res.json();
    expect(body.imported).toBe(0);
    expect(body.errorRows).toBe(1);
    expect(body.errors).toHaveLength(1);
    expect(body.errors[0].row).toBe(2);
    expect(body.errors[0].message).toBe('minutes 须为 1 到 1440 之间的整数');
    const listRes = await getFocusList();
    expect(listRes.statusCode).toBe(200);
    const listBody = await listRes.json();
    expect(listBody).toHaveLength(0);
  });

  it('minutes=+60 is an error row, not imported', async () => {
    const csv = 'subject,minutes,started_at\nmath,+60,2026-02-01';
    const res = await postImport(csv);
    expect(res.statusCode).toBe(200);
    const body = await res.json();
    expect(body.imported).toBe(0);
    expect(body.errorRows).toBe(1);
    expect(body.errors).toHaveLength(1);
    expect(body.errors[0].row).toBe(2);
    expect(body.errors[0].message).toBe('minutes 须为 1 到 1440 之间的整数');
    const listRes = await getFocusList();
    expect(listRes.statusCode).toBe(200);
    const listBody = await listRes.json();
    expect(listBody).toHaveLength(0);
  });

  it('minutes=060 is valid and imports as 60', async () => {
    const csv = 'subject,minutes,started_at\nmath,060,2026-02-01';
    const res = await postImport(csv);
    expect(res.statusCode).toBe(200);
    const body = await res.json();
    expect(body.imported).toBe(1);
    expect(body.errorRows).toBe(0);
    const listRes = await getFocusList();
    expect(listRes.statusCode).toBe(200);
    const listBody = await listRes.json();
    expect(listBody).toHaveLength(1);
    expect(listBody[0].minutes).toBe(60);
  });

  it('valid rows import, one 60.5 row errors with correct row number', async () => {
    const csv = 'subject,minutes,started_at\nmath,30,2026-02-01\nenglish,45,2026-02-01\nmajor,60.5,2026-02-01';
    const res = await postImport(csv);
    expect(res.statusCode).toBe(200);
    const body = await res.json();
    expect(body.imported).toBe(2);
    expect(body.errorRows).toBe(1);
    expect(body.errors[0].row).toBe(4);
    const listRes = await getFocusList();
    expect(listRes.statusCode).toBe(200);
    const listBody = await listRes.json();
    expect(listBody).toHaveLength(2);
  });

  it('boundary values', async () => {
    const csv = 'subject,minutes,started_at\nmath,1,2026-02-01\nenglish,1440,2026-02-01\nmajor,0,2026-02-01\npolitics,-5,2026-02-01\nmath,1441,2026-02-01';
    const res = await postImport(csv);
    expect(res.statusCode).toBe(200);
    const body = await res.json();
    expect(body.imported).toBe(2);
    expect(body.errorRows).toBe(3);
    expect(body.errors[0].row).toBe(4);
    expect(body.errors[1].row).toBe(5);
    expect(body.errors[2].row).toBe(6);
    const listRes = await getFocusList();
    expect(listRes.statusCode).toBe(200);
    const listBody = await listRes.json();
    expect(listBody).toHaveLength(2);
    const minutes = listBody.map((item: { minutes: number }) => item.minutes);
    expect([...minutes].sort((a, b) => a - b)).toEqual([1, 1440]);
  });
});
