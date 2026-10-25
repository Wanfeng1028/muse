import './bcrypt-test-env';
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '../src/app';

function normalize(url: string): string {
  let u = url.split('${qs')[0];
  u = u.replace(/\$\{[^}]+\}/g, ':p');
  return '/api' + u;
}

describe('api route parity deep5', () => {
  let app: FastifyInstance;
  let pairs: Array<{ method: string; url: string }>;
  const EXPECTED: string[] = [
    'DELETE /api/exams/:p',
    'DELETE /api/mistakes/:p',
    'DELETE /api/plans/:p',
    'DELETE /api/words/:p',
    'GET /api/auth/me',
    'GET /api/backup/export',
    'GET /api/exams',
    'GET /api/exams/:p/related-mistakes',
    'GET /api/exams/export',
    'GET /api/exams/summary',
    'GET /api/exams/trend',
    'GET /api/focus',
    'GET /api/focus/stats',
    'GET /api/health',
    'GET /api/mistakes',
    'GET /api/mistakes/:p/source-exams',
    'GET /api/mistakes/summary',
    'GET /api/mistakes/summary/by-subject',
    'GET /api/plans',
    'GET /api/plans/auto-schedule/preview',
  'GET /api/plans/overdue',
    'GET /api/plans/overload',
    'GET /api/plans/range',
    'GET /api/plans/summary',
    'GET /api/settings',
    'GET /api/stats/heatmap',
    'GET /api/stats/weekly',
    'GET /api/words',
    'GET /api/words/due',
    'GET /api/words/vocab-status',
    'PATCH /api/mistakes/:p',
    'PATCH /api/plans/:p',
    'POST /api/auth/login',
    'POST /api/auth/logout',
    'POST /api/auth/register',
    'POST /api/backup/import',
    'POST /api/exams',
    'POST /api/focus',
    'POST /api/import/mistakes',
    'POST /api/import/words',
    'POST /api/mistakes',
    'POST /api/mistakes/quiz/generate',
    'POST /api/mistakes/quiz/grade',
    'POST /api/plans',
    'POST /api/plans/auto-schedule',
    'POST /api/words',
    'POST /api/words/import',
    'POST /api/words/:p/review',
    'POST /api/words/seed-vocab',
    'PUT /api/settings',
  ];

  beforeAll(async () => {
    app = buildApp({ dbPath: ':memory:', logger: false });
    await app.ready();
    const apiSrc = fs.readFileSync(fileURLToPath(new URL('../../web/src/api.ts', import.meta.url)), 'utf-8');
    pairs = [];

    const reqRe = /request<[\s\S]*?>\(\s*[`'"]([^`'"]+)[`'"](\s*,\s*\{\s*method\s*:\s*['"]([A-Z]+)['"])?/g;
    const fetchRe = /fetch\(\s*BASE\s*\+\s*`([^`]+)`/g;

    let m: RegExpExecArray | null;
    while ((m = reqRe.exec(apiSrc)) !== null) {
      const url = m[1];
      const method = m[3] || 'GET';
      pairs.push({ method, url: normalize(url) });
    }
    while ((m = fetchRe.exec(apiSrc)) !== null) {
      const url = m[1];
      pairs.push({ method: 'GET', url: normalize(url) });
    }
  });

  afterAll(async () => {
    await app.close();
  });

  it('解析出 50 个前端 api 调用（数量快照）', () => {
    expect(pairs.length).toBe(50);
  });

  it('解析结果与 EXPECTED 快照完全一致', () => {
    const got = pairs.map(p => `${p.method} ${p.url}`).sort();
    expect(got).toEqual([...EXPECTED].sort());
  });

  it('每个前端调用在后端都有同名同方法路由（防 P0 类 404/405 漏网）', () => {
    for (const p of pairs) {
      const ok = app.hasRoute({ method: p.method as any, url: p.url });
      expect(ok, `missing route: ${p.method} ${p.url}`).toBe(true);
    }
  });

  it('P0-1 回归：PATCH /api/settings 不存在、PUT /api/settings 存在', () => {
    expect(app.hasRoute({ method: 'PATCH', url: '/api/settings' })).toBe(false);
    expect(app.hasRoute({ method: 'PUT', url: '/api/settings' })).toBe(true);
  });

  it('hasRoute 歧视器自检：未知路径返回 false', () => {
    expect(app.hasRoute({ method: 'GET', url: '/api/this-route-does-not-exist' })).toBe(false);
  });
});