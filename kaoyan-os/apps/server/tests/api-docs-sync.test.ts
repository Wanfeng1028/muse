import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import fs from 'node:fs';
import path from 'node:path';
import { createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerPlansRoutes } from '../src/routes/plans';
import { registerFocusRoutes } from '../src/routes/focus';
import { registerMistakesRoutes } from '../src/routes/mistakes';
import { registerWordsRoutes } from '../src/routes/words';
import { registerExamsRoutes } from '../src/routes/exams';
import { registerSettingsRoutes } from '../src/routes/settings';
import { registerBackupRoutes } from '../src/routes/backup';
import { registerStatsRoutes } from '../src/routes/stats';

describe('API 文档同步', () => {
  let app: FastifyInstance;
  let doc: string;
  const seen: Array<{ method: string; url: string }> = [];

  beforeAll(async () => {
    const db = createDb(':memory:');
    app = Fastify();

    app.addHook('onRoute', (route) => {
      const m = (route as { method?: unknown }).method;
      const u = (route as { url?: unknown }).url;
      const methods = Array.isArray(m) ? m : [m];
      for (const mm of methods) {
        if (typeof mm === 'string' && typeof u === 'string') {
          seen.push({ method: mm, url: u });
        }
      }
    });

    app.get('/api/health', async () => ({ ok: true }));

    applyAuthHook(app, db);
    registerAuthRoutes(app, db);
    registerPlansRoutes(app, db);
    registerFocusRoutes(app, db);
    registerMistakesRoutes(app, db);
    registerWordsRoutes(app, db);
    registerExamsRoutes(app, db);
    registerSettingsRoutes(app, db);
    registerBackupRoutes(app, db);
    registerStatsRoutes(app, db);

    await app.ready();

    doc = fs.readFileSync(
      path.resolve(__dirname, '../../../docs/API.md'),
      'utf-8',
    );
  });

  afterAll(async () => {
    await app.close();
  });

  it('文档包含全部已注册路由的精确标题', () => {
    const uniq = new Map<string, { method: string; url: string }>();
    for (const r of seen) {
      if (r.method === 'HEAD') continue;
      uniq.set(`${r.method} ${r.url}`, r);
    }
    const routes = Array.from(uniq.values()).sort((a, b) => {
      const ka = `${a.method} ${a.url}`;
      const kb = `${b.method} ${b.url}`;
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });

    const missing: string[] = [];
    for (const r of routes) {
      const needle = '`' + r.method + ' ' + r.url + '`';
      if (!doc.includes(needle)) {
        missing.push(needle);
      }
    }

    expect(missing, `以下路由未在 docs/API.md 中找到对应标题:\n${missing.join('\n')}`).toEqual([]);
  });

  it('路由总数 >= 40', () => {
    const uniq = new Set<string>();
    for (const r of seen) {
      if (r.method === 'HEAD') continue;
      uniq.add(`${r.method} ${r.url}`);
    }
    expect(uniq.size).toBeGreaterThanOrEqual(40);
  });

  it('文档包含错误码速查附录', () => {
    expect(doc).toContain('## 附录 A');
  });
});
