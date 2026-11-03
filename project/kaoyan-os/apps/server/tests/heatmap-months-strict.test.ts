import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '../src/app';
import { registerAndLogin } from './test-utils';

let app: FastifyInstance;
let authCookie = '';

beforeAll(async () => {
  app = await buildApp({ dbPath: ':memory:' });
  await app.ready();
  authCookie = await registerAndLogin(app, 'heatmapmonthsstrict');
});

afterAll(async () => {
  await app.close();
});

describe('GET /api/stats/heatmap months 严格校验', () => {
  it('非法串均返回 400', async () => {
    for (const bad of ['1.0', '0x2', '%202', '%2B2', '']) {
      const res = await app.inject({
        headers: { cookie: authCookie },
        method: 'GET',
        url: `/api/stats/heatmap?months=${bad}`,
      });
      expect(res.statusCode).toBe(400);
      expect(res.json().error).toBe('months 参数无效');
    }
  });

  it('合法值返回 200', async () => {
    const r02 = await app.inject({
      headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=02',
    });
    expect(r02.statusCode).toBe(200);
    expect(r02.json().months).toBe(2);
    expect(r02.json().days.length).toBe(62);

    const r2 = await app.inject({
      headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap?months=2',
    });
    expect(r2.statusCode).toBe(200);
    expect(r2.json().months).toBe(2);
    expect(r2.json().days.length).toBe(62);
  });

  it('缺省返回 3 个月', async () => {
    const res = await app.inject({
      headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/stats/heatmap',
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().months).toBe(3);
    expect(res.json().days.length).toBe(93);
  });
});
