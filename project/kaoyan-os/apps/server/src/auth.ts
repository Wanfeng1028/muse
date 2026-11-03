
import bcrypt from 'bcryptjs';
import crypto from 'node:crypto';
import type { FastifyInstance, FastifyRequest} from 'fastify';
import type { DatabaseSync} from 'node:sqlite';

declare module 'fastify' {
  interface FastifyRequest {
    user?: { id: number; username: string};
  }
}

// 会话 Cookie 名
export const SESSION_COOKIE = 'kaoyan_session';
// bcrypt cost（生产默认 12；测试可用 BCRYPT_COST=4 提速）
const BCRYPT_COST = (() => {
  const v = parseInt(process.env.BCRYPT_COST ?? '', 10);
  return Number.isInteger(v) && v >= 4 && v <= 14 ? v : 12;
})();
// 用户名规则：小写字母开头，允许小写字母/数字/下划线，长度 3~32
const USERNAME_RE = /^[a-z][a-z0-9_]{2,31}$/;
// 密码字节长度范围
const PASSWORD_MIN_BYTES = 8;
const PASSWORD_MAX_BYTES = 72;

// 用于未知用户均衡耗时的合法 bcrypt 常量（cost=12，与 BCRYPT_COST 对齐）
// 启动时用 bcrypt.hashSync 生成一次，避免硬编码串是否合法带来的等时漏洞
const DUMMY_HASH = bcrypt.hashSync('kaoyan-os-dummy-password', 12);

// 会话有效期（天）
const SESSION_DAYS = 30;
// 空闲续期阈值（毫秒）
const IDLE_REFRESH_MS = 24 * 60 * 60 * 1000;

type RateEntry = { count: number; resetAt: number};

const rateMap = new Map<string, RateEntry>();

// 每 10 分钟清理过期键，避免内存泄漏
const cleaner = setInterval(() => {
  const now = Date.now();
  for (const [k, v] of rateMap) {
    if (v.resetAt <= now) rateMap.delete(k);
  }
}, 10 * 60 * 1000);
if (typeof cleaner.unref === 'function') cleaner.unref();

// 返回 true 表示已超限（本次不计入）
function checkAndRecord(key: string, limit: number, windowMs: number): boolean {
  const now = Date.now();
  const entry = rateMap.get(key);
  if (!entry || entry.resetAt <= now) {
    rateMap.set(key, { count: 1, resetAt: now + windowMs});
    return false;
  }
  if (entry.count >= limit) {
    return true;
  }
  entry.count += 1;
  return false;
}

function clearRate(key: string): void {
  rateMap.delete(key);
}

// 测试环境（vitest 置 NODE_ENV=test）关闭限流：测试里每个用例都注册新用户，限流会误伤；生产行为不变
function rateLimitEnabled(): boolean {
  return process.env.NODE_ENV !== 'test';
}

// 从 req.headers.cookie 手工解析出指定 cookie
function parseCookies(req: FastifyRequest): Record<string, string> {
  const out: Record<string, string> = {};
  const raw = req.headers.cookie;
  if (!raw || typeof raw !== 'string') return out;
  const parts = raw.split(';');
  for (const part of parts) {
    const idx = part.indexOf('=');
    if (idx < 0) continue;
    const k = part.slice(0, idx).trim();
    const v = part.slice(idx + 1).trim();
    if (!k) continue;
    try {
      out[k] = decodeURIComponent(v);
    } catch {
      out[k] = v;
    }
  }
  return out;
}

function getSessionToken(req: FastifyRequest): string | null {
  const cookies = parseCookies(req);
  const t = cookies[SESSION_COOKIE];
  if (!t) return null;
  return t;
}

// 构建 Set-Cookie 头
// - 登录：显式 Max-Age = SESSION_DAYS*86400，保证跨浏览器重启仍有效
// - 登出/失效：Max-Age=0 立即清除
function buildSetCookie(token: string | null, secure: boolean): string {
  const base = `Path=/; HttpOnly; SameSite=Lax`;
  if (token) {
    const maxAge = SESSION_DAYS * 24 * 60 * 60;
    return `${SESSION_COOKIE}=${token}; ${base}; Max-Age=${maxAge}${
      secure ? '; Secure' : ''
    }`;
  }
  return `${SESSION_COOKIE}=; ${base}; Max-Age=0`;
}


function sha256Hex(input: string): string {
  return crypto.createHash('sha256').update(input).digest('hex');
}

function generateToken(): string {
  return crypto.randomBytes(32).toString('base64url');
}

function isSecure(): boolean {
  return process.env.COOKIE_SECURE === '1';
}

// 统一未认证失败体
function unauthorized(reply: any) {
  return reply.code(401).send({ error: '未登录'});
}

// 注册账号体系路由
export function registerAuthRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // POST /api/auth/register
  app.post('/api/auth/register', async (req, reply) => {
    const body = (req.body ?? {}) as { username?: unknown; password?: unknown};
    const username = typeof body.username === 'string' ? body.username : '';
    const password = typeof body.password === 'string' ? body.password : '';

    const ip = req.ip ?? 'unknown';
    if (rateLimitEnabled() && checkAndRecord(`register:ip:${ip}`, 5, 60 * 60 * 1000)) {
      return reply.code(429).send({ error: '请求过于频繁'});
    }

    if (!USERNAME_RE.test(username)) {
      return reply.code(400).send({ error: '用户名格式不合法'});
    }
    const pwBytes = Buffer.byteLength(password, 'utf8');
    if (pwBytes < PASSWORD_MIN_BYTES || pwBytes > PASSWORD_MAX_BYTES) {
      return reply.code(400).send({ error: '密码长度需为 8~72 个字符'});
    }

    const existing = db
      .prepare('SELECT id FROM users WHERE username = ?')
      .get(username) as { id: number} | undefined;
    if (existing) {
      return reply.code(409).send({ error: '用户名已存在'});
    }

    const hash = await bcrypt.hash(password, BCRYPT_COST);

    let info: { lastInsertRowid: number | bigint};
    try {
      info = db
        .prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)')
        .run(username, hash);
    } catch {
      // 并发插入时唯一约束兜底
      return reply.code(409).send({ error: '用户名已存在'});
    }

    const id = Number(info.lastInsertRowid);
    const row = db
      .prepare('SELECT id, username, created_at FROM users WHERE id = ?')
      .get(id) as { id: number; username: string; created_at: string};

    return reply.code(201).send({
      id: row.id,
      username: row.username,
      created_at: row.created_at,
    });
  });

  // POST /api/auth/login
  app.post('/api/auth/login', async (req, reply) => {
    const body = (req.body ?? {}) as { username?: unknown; password?: unknown};
    const username = typeof body.username === 'string' ? body.username : '';
    const password = typeof body.password === 'string' ? body.password : '';
    const ip = req.ip ?? 'unknown';


    // 用户维度键用归一化后的 username，避免大小写/空白变体绕过
    const normalizedUser = username.trim().toLowerCase();
    const userKey = `login:user:${normalizedUser}`;
    const ipKey = `login:ip:${ip}`;
    const windowMs = 15 * 60 * 1000;

    if (
      rateLimitEnabled() &&
      (checkAndRecord(userKey, 10, windowMs) ||
        checkAndRecord(ipKey, 10, windowMs))
    ) {
      return reply.code(429).send({ error: '请求过于频繁'});
    }

    const row = db
      .prepare('SELECT id, username, password_hash FROM users WHERE username = ?')
      .get(username) as
      | { id: number; username: string; password_hash: string}
      | undefined;

    let ok = false;
    if (!row) {
      // 未知用户名：对常量哈希做一次 compare，均衡耗时
      try {
        await bcrypt.compare(password, DUMMY_HASH);
      } catch {
        // ignore
      }
      ok = false;
    } else {
      try {
        ok = await bcrypt.compare(password, row.password_hash);
      } catch {
        // password_hash 非法（如 '!locked'）视为失败，不 500
        ok = false;
      }
    }

    if (!ok) {
      return reply.code(401).send({ error: '用户名或密码错误'});
    }

    // 仅清除用户维度，保留 IP 维度窗口，防止同一 IP 下攻击者用自己账号刷新配额
    clearRate(userKey);


    const token = generateToken();
    const tokenHash = sha256Hex(token);

    db.prepare(
      `INSERT INTO sessions (user_id, token_hash, expires_at)
       VALUES (?, ?, datetime('now', '+${SESSION_DAYS} days'))`
    ).run(row!.id, tokenHash);

    reply.header('Set-Cookie', buildSetCookie(token, isSecure()));
    return reply.code(200).send({ id: row!.id, username: row!.username});
  });

  // POST /api/auth/logout
  app.post('/api/auth/logout', async (req, reply) => {
    const token = getSessionToken(req);
    if (token) {
      const tokenHash = sha256Hex(token);
      db.prepare('DELETE FROM sessions WHERE token_hash = ?').run(tokenHash);
    }
    reply.header('Set-Cookie', buildSetCookie(null, isSecure()));
    return reply.code(204).send();
  });

  // GET /api/auth/me
  app.get('/api/auth/me', async (req, reply) => {
    if (!req.user) {
      return unauthorized(reply);
    }
    return reply.code(200).send({
      id: req.user.id,
      username: req.user.username,
    });
  });
}

// 认证钩子
export function applyAuthHook(app: FastifyInstance, db: DatabaseSync): void {
  const whitelist = new Set<string>([
    '/api/health',
    '/api/auth/register',
    '/api/auth/login',
    '/api/auth/logout',
  ]);

  app.addHook('onRequest', async (req, reply) => {
    const url = req.url.split('?')[0];

    // 非 /api/* 路径放行
    if (!url.startsWith('/api/')) {
      return;
    }

    // Origin 校验（写方法）
    const method = req.method.toUpperCase();
    if (
      method === 'POST' ||
      method === 'PUT' ||
      method === 'PATCH' ||
      method === 'DELETE'
    ) {
      const origin = req.headers.origin;
      if (typeof origin === 'string' && origin.length > 0) {
        const host = req.headers.host;
        const proto = (req.protocol ?? 'http').split(',')[0].trim();
        if (host) {
          const expected = `${proto}://${host}`;
          if (origin !== expected) {
            return reply.code(403).send({ error: '非法来源'});
          }
        }
      }
    }

    // 白名单放行
    if (whitelist.has(url)) {
      return;
    }

    // 认证流程
    const token = getSessionToken(req);
    if (!token) {
      return unauthorized(reply);
    }
    const tokenHash = sha256Hex(token);

    const row = db
      .prepare(
        `SELECT s.id AS session_id, s.last_seen_at AS last_seen_at,
                s.expires_at AS expires_at,
                u.id AS user_id, u.username AS username
         FROM sessions s
         JOIN users u ON u.id = s.user_id
         WHERE s.token_hash = ?`
      )
      .get(tokenHash) as
      | {
          session_id: number;
          last_seen_at: string;
          expires_at: string;
          user_id: number;
          username: string;
        }
      | undefined;

    if (!row) {
      reply.header('Set-Cookie', buildSetCookie(null, isSecure()));
      return unauthorized(reply);
    }

    // 过期判断（row 已存在；这里再查一次是为了按 SQLite 时间比较语义取过期标志）
    const expRow = db
      .prepare(
        "SELECT (expires_at <= datetime('now')) AS expired FROM sessions WHERE token_hash = ?"
      )
      .get(tokenHash) as { expired: number } | undefined;
    if (expRow && expRow.expired === 1) {
      db.prepare('DELETE FROM sessions WHERE token_hash = ?').run(tokenHash);
      reply.header('Set-Cookie', buildSetCookie(null, isSecure()));
      return unauthorized(reply);
    }

    req.user = { id: row.user_id, username: row.username};

    // 空闲续期：last_seen_at 早于 24 小时前，且当前未过期（避免与过期并发复活会话）
    db.prepare(
      `UPDATE sessions
       SET last_seen_at = datetime('now'),
           expires_at = datetime('now', '+${SESSION_DAYS} days')
       WHERE token_hash = ?
         AND expires_at > datetime('now')
         AND last_seen_at <= datetime('now', '-24 hours')`
    ).run(tokenHash);
  });
}

// 确保存在 local 保留用户，返回其 id
// 注意：password_hash 用 '!locked' 哨兵；login 里 compare 会抛错并被 catch 兜底，
// 因此 local 用户无法通过密码登录。但 compare 立即抛错会让耗时短于真实 bcrypt，
// 攻击者可据此探测 'local' 存在性——这是可接受的（local 是公开保留名）。
export function ensureLocalUser(db: DatabaseSync): number {
  db.prepare(
    `INSERT INTO users (username, password_hash)
     SELECT 'local', '!locked'
     WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'local')`
  ).run();
  const row = db
    .prepare("SELECT id FROM users WHERE username = 'local'")
    .get() as { id: number };
  return row.id;
}

