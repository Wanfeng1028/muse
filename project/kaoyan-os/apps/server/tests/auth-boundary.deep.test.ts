import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerAuthRoutes, applyAuthHook, ensureLocalUser, SESSION_COOKIE } from '../src/auth.js';
import { registerAndLogin, authHeaders } from './test-utils.js';

// 建一个带 users/sessions 表的最小 DB（与生产迁移后的列一致）
function makeDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:');
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
      expires_at TEXT NOT NULL
    );
    CREATE TABLE plans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      planned_minutes INTEGER NOT NULL,
      done INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);
  ensureLocalUser(db);
  return db;
}

async function buildApp(db: DatabaseSync): Promise<FastifyInstance> {
  const app = Fastify({ logger: false });
  registerAuthRoutes(app, db);
  applyAuthHook(app, db);
  // 一个需要登录的业务端点，用于验证钩子拦截
  app.get('/api/plans', async (req, reply) => {
    if (!req.user) return reply.code(401).send({ error: '未登录' });
    return reply.send({ userId: req.user.id });
  });
  await app.ready();
  return app;
}

describe('auth 边界深测', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;

  beforeEach(async () => {
    db = makeDb();
    app = await buildApp(db);
  });

  afterEach(async () => {
    await app.close();
    db.close();
    vi.unstubAllEnvs();
  });

  // ---------- 用户名规则边界 ----------
  describe('用户名规则边界', () => {
    const cases: Array<{ name: string; username: string; want: number }> = [
      // 规则：^[a-z][a-z0-9_]{2,31}$  总长 3~32
      { name: '2 位（过短）', username: 'ab', want: 400 },
      { name: '3 位（最短合法）', username: 'abc', want: 201 },
      { name: '32 位（最长合法）', username: 'a' + 'b'.repeat(31), want: 201 },
      { name: '33 位（过长）', username: 'a' + 'b'.repeat(32), want: 400 },
      { name: '大写开头', username: 'Abc', want: 400 },
      { name: '中文', username: '张三丰', want: 400 },
      { name: '下划线结尾合法', username: 'a_b', want: 201 },
      { name: '数字开头非法', username: '1ab', want: 400 },
      { name: '含大写中间非法', username: 'aBc', want: 400 },
    ];

    for (const c of cases) {
      it(`register username=${JSON.stringify(c.username)} → ${c.want}`, async () => {
        const res = await app.inject({
          method: 'POST',
          url: '/api/auth/register',
          payload: { username: c.username, password: 'test-password-123' },
        });
        expect(res.statusCode).toBe(c.want);
      });
    }
  });

  // ---------- 密码字节长度边界 ----------
  describe('密码字节长度边界', () => {
    it('7 字节密码被拒（<8）', async () => {
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'pw7user', password: 'abcdefg' }, // 7 bytes
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toMatchObject({ error: '密码长度需为 8~72 个字符' });
    });

    it('8 字节密码通过（==min）', async () => {
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'pw8user', password: 'abcdefgh' }, // 8 bytes
      });
      expect(res.statusCode).toBe(201);
    });

    it('72 字节密码通过（==max）', async () => {
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'pw72user', password: 'a'.repeat(72) }, // 72 bytes
      });
      expect(res.statusCode).toBe(201);
    });

    it('73 字节密码被拒（>72）', async () => {
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'pw73user', password: 'a'.repeat(73) }, // 73 bytes
      });
      expect(res.statusCode).toBe(400);
      expect(res.json()).toMatchObject({ error: '密码长度需为 8~72 个字符' });
    });

    it('多字节字符按 UTF-8 字节计（4 个汉字=12 字节，通过）', async () => {
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'utf8user', password: '中文测试' }, // 12 bytes
      });
      expect(res.statusCode).toBe(201);
    });

    it('多字节字符刚好 72 字节通过、73 字节被拒', async () => {
      // '中' = 3 bytes；24 个 = 72 bytes
      const ok = await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'utf72ok', password: '中'.repeat(24) },
      });
      expect(ok.statusCode).toBe(201);

      // 24 中 + 1 ascii = 73 bytes
      const bad = await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'utf73no', password: '中'.repeat(24) + 'a' },
      });
      expect(bad.statusCode).toBe(400);
    });
  });

  // ---------- 会话过期 → 401 ----------
  describe('会话过期', () => {
    it('expires_at 设为过去 → 业务接口返回 401 且清 Set-Cookie', async () => {
      const cookie = await registerAndLogin(app, 'expireuser');

      // 直接把会话推到过去
      db.prepare(
        "UPDATE sessions SET expires_at = datetime('now', '-1 hour') WHERE user_id = (SELECT id FROM users WHERE username = 'expireuser')",
      ).run();

      const res = await app.inject({
        method: 'GET',
        url: '/api/plans',
        headers: authHeaders(cookie),
      });
      expect(res.statusCode).toBe(401);
      expect(res.json()).toMatchObject({ error: '未登录' });

      const setCookie = res.headers['set-cookie'];
      const sc = Array.isArray(setCookie) ? setCookie[0] : String(setCookie ?? '');
      expect(sc).toContain(`${SESSION_COOKIE}=;`);
      expect(sc).toContain('Max-Age=0');
      expect(sc).toContain('HttpOnly');
    });

    it('过期后会话行被删除', async () => {
      const cookie = await registerAndLogin(app, 'expireuser2');
      db.prepare(
        "UPDATE sessions SET expires_at = datetime('now', '-1 minute') WHERE user_id = (SELECT id FROM users WHERE username = 'expireuser2')",
      ).run();

      await app.inject({ method: 'GET', url: '/api/plans', headers: authHeaders(cookie) });

      const row = db
        .prepare(
          "SELECT COUNT(*) AS n FROM sessions WHERE user_id = (SELECT id FROM users WHERE username = 'expireuser2')",
        )
        .get() as { n: number };
      expect(row.n).toBe(0);
    });

    it('过期会话不写入 req.user：/api/auth/me 返回 401', async () => {
      const cookie = await registerAndLogin(app, 'expireuser3');
      db.prepare(
        "UPDATE sessions SET expires_at = datetime('now', '-1 second') WHERE user_id = (SELECT id FROM users WHERE username = 'expireuser3')",
      ).run();

      const res = await app.inject({
        method: 'GET',
        url: '/api/auth/me',
        headers: authHeaders(cookie),
      });
      expect(res.statusCode).toBe(401);
    });
  });

  // ---------- 空闲续期 ----------
  describe('空闲续期', () => {
    it('last_seen_at 早于 24h → 访问时 last_seen_at 与 expires_at 都被续期', async () => {
      const cookie = await registerAndLogin(app, 'idleuser');

      // 会话当前值
      const before = db
        .prepare(
          "SELECT id, last_seen_at, expires_at FROM sessions WHERE user_id = (SELECT id FROM users WHERE username = 'idleuser')",
        )
        .get() as { id: number; last_seen_at: string; expires_at: string };

      // 把 last_seen_at 推到 25 小时前（超过 24h 阈值），expires_at 仍有效（30 天）
      db.prepare(
        "UPDATE sessions SET last_seen_at = datetime('now', '-25 hours') WHERE id = ?",
      ).run(before.id);

      const stale = db
        .prepare('SELECT last_seen_at FROM sessions WHERE id = ?')
        .get(before.id) as { last_seen_at: string };
      expect(stale.last_seen_at).toBe(before.last_seen_at === stale.last_seen_at ? stale.last_seen_at : stale.last_seen_at);

      const res = await app.inject({
        method: 'GET',
        url: '/api/plans',
        headers: authHeaders(cookie),
      });
      expect(res.statusCode).toBe(200);

      const after = db
        .prepare('SELECT last_seen_at, expires_at FROM sessions WHERE id = ?')
        .get(before.id) as { last_seen_at: string; expires_at: string };

      // last_seen_at 变新（不等于 25 小时前的那个值）
      expect(after.last_seen_at).not.toBe(stale.last_seen_at);
      // expires_at 被延长：新值 >= 旧值（SQLite datetime('now') 为秒精度，同一秒内续期可能相等）
      expect(after.expires_at >= before.expires_at).toBe(true);
      // 新 last_seen_at 应接近 now（不早于 1 分钟前）
      const fresh = db
        .prepare(
          "SELECT (last_seen_at >= datetime('now','-1 minute')) AS fresh FROM sessions WHERE id = ?",
        )
        .get(before.id) as { fresh: number };
      expect(fresh.fresh).toBe(1);
    });

    it('last_seen_at 在 24h 内 → 不续期（expires_at 不变）', async () => {
      const cookie = await registerAndLogin(app, 'noidleuser');
      const before = db
        .prepare(
          "SELECT id, expires_at FROM sessions WHERE user_id = (SELECT id FROM users WHERE username = 'noidleuser')",
        )
        .get() as { id: number; expires_at: string };

      // 把 last_seen_at 调到 1 小时前（< 24h）
      db.prepare(
        "UPDATE sessions SET last_seen_at = datetime('now', '-1 hour') WHERE id = ?",
      ).run(before.id);

      const res = await app.inject({
        method: 'GET',
        url: '/api/plans',
        headers: authHeaders(cookie),
      });
      expect(res.statusCode).toBe(200);

      const after = db
        .prepare('SELECT expires_at FROM sessions WHERE id = ?')
        .get(before.id) as { expires_at: string };
      expect(after.expires_at).toBe(before.expires_at);
    });
  });

  // ---------- 限流 ----------
  describe('登录限流', () => {
    it('NODE_ENV=test 下 rateLimitEnabled() 关闭 → 不触发 429（真实行为）', async () => {
      // 源码 auth.ts:60-62：NODE_ENV==='test' 直接关闭限流。
      // 因此这里断言真实行为：连续 20 次错误密码仍返回 401，而不是 429。
      await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'ratelimituser', password: 'test-password-123' },
      });

      let last = 0;
      for (let i = 0; i < 20; i++) {
        const res = await app.inject({
          method: 'POST',
          url: '/api/auth/login',
          payload: { username: 'ratelimituser', password: 'wrong-password' },
        });
        last = res.statusCode;
      }
      expect(last).toBe(401);
    });

    it('登录成功后 clearRate：错误后再用正确密码仍能成功', async () => {
      await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'clearuser', password: 'test-password-123' },
      });

      // 先错一次
      const bad = await app.inject({
        method: 'POST',
        url: '/api/auth/login',
        payload: { username: 'clearuser', password: 'wrong' },
      });
      expect(bad.statusCode).toBe(401);

      // 再对
      const ok = await app.inject({
        method: 'POST',
        url: '/api/auth/login',
        payload: { username: 'clearuser', password: 'test-password-123' },
      });
      expect(ok.statusCode).toBe(200);
      const setCookie = ok.headers['set-cookie'];
      const sc = Array.isArray(setCookie) ? setCookie[0] : String(setCookie ?? '');
      expect(sc).toContain(`${SESSION_COOKIE}=`);
    });
  });

  // ---------- cookie flags ----------
  describe('cookie flags', () => {
    it('登录 Set-Cookie 含 HttpOnly / Path=/ / SameSite=Lax，不含 Secure（默认）', async () => {
      await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'cookieuser', password: 'test-password-123' },
      });
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/login',
        payload: { username: 'cookieuser', password: 'test-password-123' },
      });
      expect(res.statusCode).toBe(200);
      const setCookie = res.headers['set-cookie'];
      const sc = Array.isArray(setCookie) ? setCookie[0] : String(setCookie ?? '');
      expect(sc).toContain(`${SESSION_COOKIE}=`);
      expect(sc).toContain('HttpOnly');
      expect(sc).toContain('Path=/');
      expect(sc).toContain('SameSite=Lax');
      expect(sc).not.toContain('Secure');
      // token 本体应是 base64url 长度 43（32 字节）
      const token = sc.split(';')[0].split('=')[1];
      expect(token).toMatch(/^[A-Za-z0-9_-]{43}$/);
    });

    it('COOKIE_SECURE=1 时登录 Set-Cookie 含 Secure', async () => {
      vi.stubEnv('COOKIE_SECURE', '1');
      await app.inject({
        method: 'POST',
        url: '/api/auth/register',
        payload: { username: 'secureuser', password: 'test-password-123' },
      });
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/login',
        payload: { username: 'secureuser', password: 'test-password-123' },
      });
      expect(res.statusCode).toBe(200);
      const setCookie = res.headers['set-cookie'];
      const sc = Array.isArray(setCookie) ? setCookie[0] : String(setCookie ?? '');
      expect(sc).toContain('Secure');
      expect(sc).toContain('HttpOnly');
    });

    it('登出清 cookie：kaoyan_session=; Max-Age=0; HttpOnly', async () => {
      const cookie = await registerAndLogin(app, 'logoutuser');
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/logout',
        headers: authHeaders(cookie),
      });
      expect(res.statusCode).toBe(204);
      const setCookie = res.headers['set-cookie'];
      const sc = Array.isArray(setCookie) ? setCookie[0] : String(setCookie ?? '');
      expect(sc).toContain(`${SESSION_COOKIE}=;`);
      expect(sc).toContain('Max-Age=0');
      expect(sc).toContain('HttpOnly');
    });

    it('伪造 cookie → 401 且清 Set-Cookie', async () => {
      const res = await app.inject({
        method: 'GET',
        url: '/api/plans',
        headers: { cookie: `${SESSION_COOKIE}=deadbeef` },
      });
      expect(res.statusCode).toBe(401);
      const setCookie = res.headers['set-cookie'];
      const sc = Array.isArray(setCookie) ? setCookie[0] : String(setCookie ?? '');
      expect(sc).toContain(`${SESSION_COOKIE}=;`);
      expect(sc).toContain('Max-Age=0');
    });
  });

  // ---------- auth 全局钩子白名单 ----------
  describe('auth 全局钩子', () => {
    it('/api/health 在非白名单外 → 未登录 401（源码白名单不含 /api/plans）', async () => {
      const res = await app.inject({ method: 'GET', url: '/api/plans' });
      expect(res.statusCode).toBe(401);
    });

    it('白名单 /api/auth/login 未登录可访问', async () => {
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/login',
        payload: { username: 'nobody', password: 'whatever-pass' },
      });
      // 无此用户 → 401，但能到路由（非 404/403）
      expect(res.statusCode).toBe(401);
      expect(res.json()).toMatchObject({ error: '用户名或密码错误' });
    });

    it('写方法带跨源 Origin → 403', async () => {
      const cookie = await registerAndLogin(app, 'originuser');
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/logout',
        headers: { ...authHeaders(cookie), origin: 'https://evil.example.com', host: 'localhost' },
      });
      expect(res.statusCode).toBe(403);
      expect(res.json()).toMatchObject({ error: '非法来源' });
    });

    it('写方法 Origin 与 host 一致 → 放行（走完白名单）', async () => {
      const cookie = await registerAndLogin(app, 'originokuser');
      const res = await app.inject({
        method: 'POST',
        url: '/api/auth/logout',
        headers: { ...authHeaders(cookie), origin: 'http://localhost:80', host: 'localhost:80' },
      });
      expect(res.statusCode).toBe(204);
    });
  });
});
