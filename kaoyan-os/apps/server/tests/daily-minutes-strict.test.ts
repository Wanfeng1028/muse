import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { createDb } from '../src/db';
import { registerPlansRoutes } from '../src/routes/plans';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

describe('dailyMinutes 纯数字正则校验（两路 GET 接口）', () => {
  let app: FastifyInstance;
  let cookie: string;

  beforeEach(async () => {
    const db = createDb(':memory:');
    app = Fastify();
    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerPlansRoutes(app, db);
    await app.ready();
    cookie = await registerAndLogin(app, 'dmstrict');
  });

  afterEach(async () => {
    await app.close();
  });

  describe('preview 路 /api/plans/auto-schedule/preview', () => {
    const base = '/api/plans/auto-schedule/preview?subjects=math&examDate=2026-12-19&startDate=2026-10-20';

    it('dailyMinutes=60.0 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('60.0')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'dailyMinutes 非法' });
    });

    it('dailyMinutes=0x3c 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('0x3c')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'dailyMinutes 非法' });
    });

    it('dailyMinutes=+60 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('+60')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'dailyMinutes 非法' });
    });

    it('dailyMinutes=带空格的 60 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent(' 60 ')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'dailyMinutes 非法' });
    });

    it('dailyMinutes=空串返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'dailyMinutes 非法' });
    });

    it('dailyMinutes=060 返回 200', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('060')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(200);
    });

    it('dailyMinutes=60 返回 200', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('60')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(200);
    });
  });

  describe('overload 路 /api/plans/overload', () => {
    const base = '/api/plans/overload?weekStart=2026-10-21';

    it('dailyMinutes=60.0 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('60.0')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'dailyMinutes 非法' });
    });

    it('dailyMinutes=0x3c 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('0x3c')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'dailyMinutes 非法' });
    });

    it('dailyMinutes=+60 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('+60')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'dailyMinutes 非法' });
    });

    it('dailyMinutes=带空格的 60 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent(' 60 ')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toEqual({ error: 'dailyMinutes 非法' });
    });

    it('dailyMinutes=060 返回 200，回显 60', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('060')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(200);
      expect(res.json().dailyMinutes).toBe(60);
    });

    it('dailyMinutes=240 返回 200，回显 240', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${base}&dailyMinutes=${encodeURIComponent('240')}`,
        headers: { cookie },
      });
      expect(res.statusCode).toBe(200);
      expect(res.json().dailyMinutes).toBe(240);
    });
  });
});