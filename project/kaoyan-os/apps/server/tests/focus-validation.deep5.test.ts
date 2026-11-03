import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerFocusRoutes } from '../src/routes/focus';
import { registerPlansRoutes } from '../src/routes/plans';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin, authHeaders } from './test-utils';
import type { DatabaseSync } from 'node:sqlite';

let db: DatabaseSync;
let app: FastifyInstance;

beforeEach(async () => {
  db = createDb(':memory:');
  app = Fastify();
  registerPlansRoutes(app, db);
  registerFocusRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

afterAll(async () => { await app.close(); });

interface ErrorBody { error: string; }

async function postFocus(headers: Record<string, string>, payload: unknown) {
  return app.inject({ method: 'POST', url: '/api/focus', headers, payload });
}

describe('focus validation deep5', () => {
  it('subject 大小写 Math 非法', async () => {
    const headers = authHeaders(await registerAndLogin(app, 'u_kw10'));
    const res = await postFocus(headers, { subject: 'Math', minutes: 30 });
    expect(res.statusCode).toBe(400);
    expect(res.json<ErrorBody>().error).toBe('invalid subject');
  });

  it('subject 空串非法', async () => {
    const headers = authHeaders(await registerAndLogin(app, 'u_kw11'));
    const res = await postFocus(headers, { subject: '', minutes: 30 });
    expect(res.statusCode).toBe(400);
    expect(res.json<ErrorBody>().error).toBe('invalid subject');
  });

  it('subject 带空格非法', async () => {
    const headers = authHeaders(await registerAndLogin(app, 'u_kw12'));
    const res = await postFocus(headers, { subject: ' math ', minutes: 30 });
    expect(res.statusCode).toBe(400);
    expect(res.json<ErrorBody>().error).toBe('invalid subject');
  });

  it('subject 数字非法', async () => {
    const headers = authHeaders(await registerAndLogin(app, 'u_kw13'));
    const res = await postFocus(headers, { subject: 123, minutes: 30 });
    expect(res.statusCode).toBe(400);
    expect(res.json<ErrorBody>().error).toBe('invalid subject');
  });

  it('minutes 字符串非法', async () => {
    const headers = authHeaders(await registerAndLogin(app, 'u_kw14'));
    const res = await postFocus(headers, { subject: 'math', minutes: '60' });
    expect(res.statusCode).toBe(400);
  });

  it('minutes 小数非法', async () => {
    const headers = authHeaders(await registerAndLogin(app, 'u_kw15'));
    const res = await postFocus(headers, { subject: 'math', minutes: 1.5 });
    expect(res.statusCode).toBe(400);
  });

  it('minutes 0 非法', async () => {
    const headers = authHeaders(await registerAndLogin(app, 'u_kw16'));
    const res = await postFocus(headers, { subject: 'math', minutes: 0 });
    expect(res.statusCode).toBe(400);
  });

  it('minutes 1441 非法', async () => {
    const headers = authHeaders(await registerAndLogin(app, 'u_kw17'));
    const res = await postFocus(headers, { subject: 'math', minutes: 1441 });
    expect(res.statusCode).toBe(400);
  });

  it('minutes 1 合法', async () => {
    const headers = authHeaders(await registerAndLogin(app, 'u_kw18'));
    const res = await postFocus(headers, { subject: 'math', minutes: 1 });
    expect(res.statusCode).toBe(201);
  });

  it('minutes 1440 合法', async () => {
    const headers = authHeaders(await registerAndLogin(app, 'u_kw19'));
    const res = await postFocus(headers, { subject: 'math', minutes: 1440 });
    expect(res.statusCode).toBe(201);
  });
});