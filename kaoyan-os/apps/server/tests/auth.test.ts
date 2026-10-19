import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerAuthRoutes, applyAuthHook, SESSION_COOKIE } from '../src/auth.js';
import { registerAndLogin, authHeaders } from './test-utils.js';

// 必须存在的最小业务表，用于“未登录访问业务接口”断言；与源码其他模块共用同一批表名。
function bootstrapSchema(db: DatabaseSync): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      token_hash TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
      expires_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS plans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      planned_minutes INTEGER NOT NULL DEFAULT 0,
      done INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);
}

// 构造一个仅挂载 auth 路由 + auth 钩子的最小 app；/api/plans 用轻量 stub 代表业务接口。
function buildApp(db: DatabaseSync): FastifyInstance {
  const app = Fastify({ logger: false });
  registerAuthRoutes(app, db);
  applyAuthHook(app, db);
  app.get('/api/plans', async (req, reply) => {
    if (!req.user) return reply.code(401).send({ error: '未登录' });
    return reply.code(200).send({ items: [] });
  });
  return app;
}

// 从 inject 响应头解析 Set-Cookie 中指定 cookie 值（不存在返回 null）
function readCookie(res: { headers: Record<string, unknown> }, name: string): string | null {
  const raw = res.headers['set-cookie'];
  if (!raw) return null;
  const list = Array.isArray(raw) ? raw : [String(raw)];
  for (const line of list) {
    const head = line.split(';')[0].trim();
    const eq = head.indexOf('=');
    if (eq < 0) continue;
    if (head.slice(0, eq).trim() === name) {
      return head.slice(eq + 1).trim();
    }
  }
  return null;
}

let db: DatabaseSync;
let app: FastifyInstance;

beforeEach(async () => {
  db = new DatabaseSync(':memory:');
  bootstrapSchema(db);
  app = buildApp(db);
  await app.ready();
});

afterEach(async () => {
  await app.close();
  db.close();
});

describe('POST /api/auth/register', () => {
  it('合法用户名+合法密码 → 201 且返回 id/username/created_at，且不落会话', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'alice', password: 'p@ssw0rd-1' },
    });
    expect(res.statusCode).toBe(201);
    const body = res.json() as { id: number; username: string; created_at: string };
    expect(body.username).toBe('alice');
    expect(typeof body.id).toBe('number');
    expect(body.created_at).toMatch(/^\d{4}-\d{2}-\d{2}/);
    // 注册不应种会话
    expect(readCookie(res, SESSION_COOKIE)).toBeNull();
    // 用户已落库，密码不是明文
    const row = db
      .prepare('SELECT password_hash FROM users WHERE username = ?')
      .get('alice') as { password_hash: string };
    expect(row.password_hash).not.toBe('p@ssw0rd-1');
    expect(row.password_hash.startsWith('$2')).toBe(true);
    // 无会话行
    const sessions = db.prepare('SELECT COUNT(*) AS c FROM sessions').get() as { c: number };
    expect(sessions.c).toBe(0);
  });

  it('重名 → 409，且不新增用户', async () => {
    const first = await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'bob', password: 'p@ssw0rd-1' },
    });
    expect(first.statusCode).toBe(201);

    const dup = await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'bob', password: 'another-pass-1' },
    });
    expect(dup.statusCode).toBe(409);
    expect(dup.json()).toEqual({ error: '用户名已存在' });

    const count = db
      .prepare('SELECT COUNT(*) AS c FROM users WHERE username = ?')
      .get('bob') as { c: number };
    expect(count.c).toBe(1);
  });

  it.each([
    ['大写开头', 'Alice'],
    ['数字开头', '1alice'],
    ['下划线开头', '_alice'],
    ['过短', 'ab'],
    ['过长', 'a'.repeat(33)],
    ['含非法字符', 'alice-bob'],
    ['非字符串', 12345 as unknown],
  ])('非法用户名（%s）→ 400', async (_label, username) => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username, password: 'p@ssw0rd-1' },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '用户名格式不合法' });
  });

  it.each([
    ['过短', 'short'],
    ['恰好 7 字节', '1234567'],
    ['超 72 字节', 'x'.repeat(73)],
    ['非字符串', 12345678 as unknown],
  ])('弱密码（%s）→ 400', async (_label, password) => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'weakpw', password },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual({ error: '密码长度需为 8~72 个字符' });
  });

  it('边界：8 字节与 72 字节密码均通过', async () => {
    const ok8 = await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'edge8', password: '12345678' },
    });
    expect(ok8.statusCode).toBe(201);

    const ok72 = await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'edge72', password: 'x'.repeat(72) },
    });
    expect(ok72.statusCode).toBe(201);
  });
});

describe('POST /api/auth/login', () => {
  it('成功 → 200 + Set-Cookie 含 kaoyan_session 且 HttpOnly，并落 sessions 行', async () => {
    await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'carol', password: 'p@ssw0rd-1' },
    });

    const res = await app.inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { username: 'carol', password: 'p@ssw0rd-1' },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ id: expect.any(Number), username: 'carol' });

    const raw = res.headers['set-cookie'];
    expect(raw).toBeTruthy();
    const line = Array.isArray(raw) ? raw[0] : String(raw);
    expect(line).toContain(`${SESSION_COOKIE}=`);
    expect(line).toContain('HttpOnly');
    expect(line).toContain('SameSite=Lax');
    expect(line).toContain('Path=/');

    const token = readCookie(res, SESSION_COOKIE);
    expect(token).toBeTruthy();
    // 落库为 sha256 而非明文
    const rows = db.prepare('SELECT token_hash FROM sessions').all() as Array<{ token_hash: string }>;
    expect(rows.length).toBe(1);
    expect(rows[0].token_hash).not.toBe(token);
    expect(rows[0].token_hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it('错密码 → 401 且不种会话', async () => {
    await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'dave', password: 'p@ssw0rd-1' },
    });
    const res = await app.inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { username: 'dave', password: 'wrong-password' },
    });
    expect(res.statusCode).toBe(401);
    expect(res.json()).toEqual({ error: '用户名或密码错误' });
    expect(readCookie(res, SESSION_COOKIE)).toBeNull();
    const c = db.prepare('SELECT COUNT(*) AS c FROM sessions').get() as { c: number };
    expect(c.c).toBe(0);
  });

  it('不存在用户 → 401，且耗时与错密码路径同数量级（时序均衡）', async () => {
    await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'erin', password: 'p@ssw0rd-1' },
    });

    // 预热，避免首次 bcrypt 初始化影响
    await app.inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { username: 'erin', password: 'wrong-password' },
    });
    await app.inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { username: 'nobody_here', password: 'wrong-password' },
    });

    const t0 = performance.now();
    const wrongPw = await app.inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { username: 'erin', password: 'wrong-password' },
    });
    const t1 = performance.now();
    const unknown = await app.inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { username: 'nobody_here', password: 'wrong-password' },
    });
    const t2 = performance.now();

    expect(wrongPw.statusCode).toBe(401);
    expect(unknown.statusCode).toBe(401);
    expect(unknown.json()).toEqual({ error: '用户名或密码错误' });

    const dtExist = t1 - t0;
    const dtUnknown = t2 - t1;
    // 宽松区间：未知用户不应比存在用户快太多（避免用户枚举）；也不应慢出一个数量级
    const ratio = dtUnknown / Math.max(dtExist, 1);
    expect(ratio).toBeGreaterThan(0.3);
    // 仅在成本参数一致（生产默认 12）时比较上界；BCRYPT_COST=4 时未知用户仍走 cost=12 的 DUMMY_HASH，ratio 会异常放大
    if (process.env.BCRYPT_COST === '12' || process.env.BCRYPT_COST === undefined) {
      expect(ratio).toBeLessThan(3);
    }
  });
});

describe('POST /api/auth/logout', () => {
  it('带会话 → 204，删 sessions 行并清 cookie', async () => {
    const cookie = await registerAndLogin(app, 'frank');
    const before = db.prepare('SELECT COUNT(*) AS c FROM sessions').get() as { c: number };
    expect(before.c).toBe(1);

    const res = await app.inject({
      method: 'POST',
      url: '/api/auth/logout',
      headers: authHeaders(cookie),
    });
    expect(res.statusCode).toBe(204);

    const raw = res.headers['set-cookie'];
    const line = Array.isArray(raw) ? raw[0] : String(raw ?? '');
    expect(line).toContain(`${SESSION_COOKIE}=;`);
    expect(line).toContain('Max-Age=0');

    const after = db.prepare('SELECT COUNT(*) AS c FROM sessions').get() as { c: number };
    expect(after.c).toBe(0);
  });

  it('无 cookie 也返回 204 且不报错', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/auth/logout' });
    expect(res.statusCode).toBe(204);
  });

  it('登出后旧 cookie 再访问 /api/auth/me → 401', async () => {
    const cookie = await registerAndLogin(app, 'grace');
    const me1 = await app.inject({
      method: 'GET',
      url: '/api/auth/me',
      headers: authHeaders(cookie),
    });
    expect(me1.statusCode).toBe(200);
    expect(me1.json()).toEqual({ id: expect.any(Number), username: 'grace' });

    await app.inject({
      method: 'POST',
      url: '/api/auth/logout',
      headers: authHeaders(cookie),
    });

    const me2 = await app.inject({
      method: 'GET',
      url: '/api/auth/me',
      headers: authHeaders(cookie),
    });
    expect(me2.statusCode).toBe(401);
  });
});

describe('GET /api/auth/me', () => {
  it('已登录 → 200 且返回 id/username', async () => {
    const cookie = await registerAndLogin(app, 'henry');
    const res = await app.inject({
      method: 'GET',
      url: '/api/auth/me',
      headers: authHeaders(cookie),
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as { id: number; username: string };
    expect(body.username).toBe('henry');
    const dbUser = db
      .prepare('SELECT id FROM users WHERE username = ?')
      .get('henry') as { id: number };
    expect(body.id).toBe(dbUser.id);
  });

  it('未登录 → 401，白名单允许匿名进入', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/auth/me' });
    expect(res.statusCode).toBe(401);
    expect(res.json()).toEqual({ error: '未登录' });
  });

  it('伪造 cookie → 401', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/auth/me',
      headers: { cookie: `${SESSION_COOKIE}=forged-token-not-in-db` },
    });
    expect(res.statusCode).toBe(401);
  });
});

describe('全局 auth 钩子', () => {
  it('未登录访问业务接口 → 401', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/plans' });
    expect(res.statusCode).toBe(401);
    expect(res.json()).toEqual({ error: '未登录' });
  });

  it('已登录访问业务接口 → 200', async () => {
    const cookie = await registerAndLogin(app, 'ivan');
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: authHeaders(cookie),
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ items: [] });
  });

  it('非 /api/* 路径不被拦截', async () => {
    // 未注册的路由，Fastify 返回 404 而不是 401，说明钩子未拦
    const res = await app.inject({ method: 'GET', url: '/whatever' });
    expect(res.statusCode).toBe(404);
  });

  it('白名单 /api/auth/register 可匿名访问', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'judy', password: 'p@ssw0rd-1' },
    });
    expect(res.statusCode).toBe(201);
  });

  it('白名单 /api/auth/login 可匿名访问', async () => {
    await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'kate', password: 'p@ssw0rd-1' },
    });
    const res = await app.inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { username: 'kate', password: 'p@ssw0rd-1' },
    });
    expect(res.statusCode).toBe(200);
  });

  it('已过期会话 → 401 且清除会话行', async () => {
    const cookie = await registerAndLogin(app, 'leo');
    const token = cookie.split('=')[1];
    // 直接把 expires_at 改到过去
    db.prepare(
      "UPDATE sessions SET expires_at = datetime('now', '-1 day') WHERE token_hash = ?",
    ).run(require('node:crypto').createHash('sha256').update(token).digest('hex'));

    const res = await app.inject({
      method: 'GET',
      url: '/api/auth/me',
      headers: authHeaders(cookie),
    });
    expect(res.statusCode).toBe(401);
    const c = db.prepare('SELECT COUNT(*) AS c FROM sessions').get() as { c: number };
    expect(c.c).toBe(0);
  });
});
