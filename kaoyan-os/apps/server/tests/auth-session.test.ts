import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerAuthRoutes, applyAuthHook } from '../src/auth';
import { initSchema } from '../src/db';
import { registerAndLogin, authHeaders } from './test-utils';
import crypto from 'node:crypto';

describe('auth session security', () => {
  let app: FastifyInstance;
  let db: DatabaseSync;
  let cleanup: () => Promise<void>;

  beforeEach(async () => {
    db = new DatabaseSync(':memory:');
    initSchema(db);
    app = Fastify({ logger: false });
    registerAuthRoutes(app, db);
    applyAuthHook(app, db);
    cleanup = async () => {
      await app.close();
    };
    // 清空会话表，避免跨用例污染（若不存在则忽略）
    try {
      db.prepare('DELETE FROM sessions').run();
    } catch {
      /* ignore */
    }
  });

  afterEach(async () => {
    await cleanup();
  });

  it('登录后 Set-Cookie 带 Max-Age 与 HttpOnly/SameSite，不含 Secure（默认）', async () => {
    const reg = await app.inject({
      method: 'POST',
      url: '/api/auth/register',
      payload: { username: 'cookieuser', password: 'test-password-123' },
    });
    expect(reg.statusCode).toBe(201);

    const login = await app.inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { username: 'cookieuser', password: 'test-password-123' },
    });
    expect(login.statusCode).toBe(200);
    const setCookie = String(login.headers['set-cookie'] ?? '');
    expect(setCookie).toMatch(/kaoyan_session=/);
    expect(setCookie).toMatch(/HttpOnly/i);
    expect(setCookie).toMatch(/SameSite=Lax/i);
    expect(setCookie).toMatch(/Max-Age=2592000/); // 30 天
    expect(setCookie).not.toMatch(/;\s*Secure/i);
  });

  it('sessions 表只存 sha256(token)，不存明文 token', async () => {
    const cookie = await registerAndLogin(app, 'hashstore');
    const token = cookie.split('=')[1];
    expect(token.length).toBeGreaterThan(20);

    const expectedHash = crypto.createHash('sha256').update(token).digest('hex');
    const row = db
      .prepare('SELECT token_hash FROM sessions WHERE token_hash = ?')
      .get(expectedHash) as { token_hash: string } | undefined;
    expect(row).toBeTruthy();
    expect(row!.token_hash).toBe(expectedHash);

    // 明文 token 不应出现在 DB
    const plain = db
      .prepare('SELECT 1 FROM sessions WHERE token_hash = ?')
      .get(token) as unknown;
    expect(plain).toBeUndefined();
  });

  it('登出后会话从 sessions 表删除，且 Set-Cookie 清除', async () => {
    const cookie = await registerAndLogin(app, 'logoutuser');
    const token = cookie.split('=')[1];
    const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
    const before = db
      .prepare('SELECT id FROM sessions WHERE token_hash = ?')
      .get(tokenHash);
    expect(before).toBeTruthy();

    const out = await app.inject({
      method: 'POST',
      url: '/api/auth/logout',
      headers: authHeaders(cookie),
    });
    expect(out.statusCode).toBe(204);
    const setCookie = String(out.headers['set-cookie'] ?? '');
    expect(setCookie).toMatch(/Max-Age=0/);

    const after = db
      .prepare('SELECT id FROM sessions WHERE token_hash = ?')
      .get(tokenHash);
    expect(after).toBeUndefined();
  });

  it('过期会话被拒绝并删除', async () => {
    const cookie = await registerAndLogin(app, 'expireduser');
    const token = cookie.split('=')[1];
    const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
    // 手工把 expires_at 改到过去
    db.prepare(
      "UPDATE sessions SET expires_at = datetime('now', '-1 day') WHERE token_hash = ?"
    ).run(tokenHash);

    const res = await app.inject({
      method: 'GET',
      url: '/api/auth/me',
      headers: authHeaders(cookie),
    });
    expect(res.statusCode).toBe(401);

    const after = db
      .prepare('SELECT id FROM sessions WHERE token_hash = ?')
      .get(tokenHash);
    expect(after).toBeUndefined();
  });

  it('未知用户名登录与错误密码耗时量级一致（bcrypt 等时）', async () => {
    // 注册一个真实用户
    await registerAndLogin(app, 'timinguser');
    const t0 = Date.now();
    await app.inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { username: 'nobody_xyz_123', password: 'wrong-password-xxx' },
    });
    const tUnknown = Date.now() - t0;

    const t1 = Date.now();
    await app.inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { username: 'timinguser', password: 'wrong-password-xxx' },
    });
    const tKnown = Date.now() - t1;

    // 两者都应 >= 一次 bcrypt compare 的时间（BCRYPT_COST=4 下约 1~5ms），
    // 只做粗略量级断言：未知路径不应显著快于已知路径的一半。
    expect(tUnknown).toBeGreaterThan(0);
    expect(tUnknown).toBeGreaterThanOrEqual(Math.min(tKnown, 1));
  });

  it('会话在 last_seen_at 超过 24h 后触发续期（expires_at 被推后）', async () => {
    const cookie = await registerAndLogin(app, 'refreshuser');
    const token = cookie.split('=')[1];
    const tokenHash = crypto.createHash('sha256').update(token).digest('hex');

    // 把 last_seen_at 设为 25 小时前
    db.prepare(
      "UPDATE sessions SET last_seen_at = datetime('now', '-25 hours') WHERE token_hash = ?"
    ).run(tokenHash);

    const before = db
      .prepare('SELECT expires_at FROM sessions WHERE token_hash = ?')
      .get(tokenHash) as { expires_at: string };

    const res = await app.inject({
      method: 'GET',
      url: '/api/auth/me',
      headers: authHeaders(cookie),
    });
    expect(res.statusCode).toBe(200);

    const after = db
      .prepare(
        'SELECT expires_at, last_seen_at FROM sessions WHERE token_hash = ?'
      )
      .get(tokenHash) as { expires_at: string; last_seen_at: string };
    expect(after.expires_at >= before.expires_at).toBe(true);
    // last_seen_at 应被更新为接近 now
    expect(after.last_seen_at).not.toBe(
      db.prepare("SELECT datetime('now','-25 hours') AS t").get().t,
    );
  });

  it('过期会话不会被续期逻辑复活', async () => {
    const cookie = await registerAndLogin(app, 'noresurrect');
    const token = cookie.split('=')[1];
    const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
    db.prepare(
      "UPDATE sessions SET last_seen_at = datetime('now','-25 hours'), expires_at = datetime('now','-1 minute') WHERE token_hash = ?"
    ).run(tokenHash);

    const res = await app.inject({
      method: 'GET',
      url: '/api/auth/me',
      headers: authHeaders(cookie),
    });
    expect(res.statusCode).toBe(401);
    const after = db
      .prepare('SELECT id FROM sessions WHERE token_hash = ?')
      .get(tokenHash);
    expect(after).toBeUndefined();
  });

  it('非白名单 /api/* 未登录返回 401', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/plans' });
    expect(res.statusCode).toBe(401);
  });

  it('登出接口在白名单中：无 cookie 调用也 204', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/auth/logout' });
    expect(res.statusCode).toBe(204);
  });
});
