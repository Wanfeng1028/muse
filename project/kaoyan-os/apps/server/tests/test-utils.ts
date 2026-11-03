
import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';

// 注册一个测试用户并登录，返回可直接放进 inject headers 的 cookie 字符串（形如 kaoyan_session=xxx）。
// 注册失败（非 201）或登录失败（非 200）或拿不到 kaoyan_session cookie 时抛错。
export async function registerAndLogin(
  app: FastifyInstance,
  username: string,
  password = 'test-password-123',
): Promise<string> {
  const reg = await app.inject({
    method: 'POST',
    url: '/api/auth/register',
    payload: { username, password },
  });
  if (reg.statusCode !== 201) {
    throw new Error(`register failed: ${reg.statusCode} ${reg.body}`);
  }
  const login = await app.inject({
    method: 'POST',
    url: '/api/auth/login',
    payload: { username, password },
  });
  if (login.statusCode !== 200) {
    throw new Error(`login failed: ${login.statusCode} ${login.body}`);
  }
  const setCookie = login.headers['set-cookie'];
  const first = Array.isArray(setCookie) ? setCookie[0] : String(setCookie ?? '');
  const cookie = first.split(';')[0].trim();
  if (!cookie.startsWith('kaoyan_session=')) {
    throw new Error(`no session cookie in: ${first}`);
  }
  return cookie;
}

// 把 cookie 包成 inject 可用的 headers 对象
export function authHeaders(cookie: string): Record<string, string> {
  return { cookie };
}

// 注册并登录测试用户后，把 local 用户名下的种子数据复制一份给新用户（新 id），
// 让需要种子数据的旧测试能继续断言。
export async function createSeededUser(
  db: DatabaseSync,
  app: FastifyInstance,
  username: string,
  password = 'test-password-123',
): Promise<{ cookie: string; userId: number }> {
  const cookie = await registerAndLogin(app, username, password);

  const newUser = db
    .prepare('SELECT id FROM users WHERE username = ?')
    .get(username) as { id: number } | undefined;
  if (!newUser) {
    throw new Error(`seeded user not found: ${username}`);
  }
  const userId = newUser.id;

  const localUser = db
    .prepare('SELECT id FROM users WHERE username = ?')
    .get('local') as { id: number } | undefined;
  if (!localUser) {
    throw new Error('local seed user not found');
  }
  const localId = localUser.id;

  db.prepare(
    `INSERT INTO plans (user_id, date, subject, title, planned_minutes, done, created_at)
     SELECT ?, date, subject, title, planned_minutes, done, created_at FROM plans WHERE user_id = ?`,
  ).run(userId, localId);

  db.prepare(
    `INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note)
     SELECT ?, subject, minutes, started_at, note FROM focus_sessions WHERE user_id = ?`,
  ).run(userId, localId);

  db.prepare(
    `INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at)
     SELECT ?, subject, title, content, analysis, mastered, created_at FROM mistakes WHERE user_id = ?`,
  ).run(userId, localId);

  db.prepare(
    `INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at)
     SELECT ?, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE user_id = ?`,
  ).run(userId, localId);

  db.prepare(
    `INSERT INTO words (user_id, word, phonetic, meaning, example, source, memory_tip)
     SELECT ?, word, phonetic, meaning, example, source, memory_tip FROM words WHERE user_id = ?`,
  ).run(userId, localId);

  const localWords = db
    .prepare('SELECT id, word FROM words WHERE user_id = ?')
    .all(localId) as Array<{ id: number; word: string }>;
  const findNewWord = db.prepare('SELECT id FROM words WHERE user_id = ? AND word = ?');
  const findOldSrs = db.prepare(
    'SELECT ease, interval_days, repetitions, due_date FROM srs_state WHERE word_id = ?',
  );
  const insertSrs = db.prepare(
    `INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date)
     VALUES (?, ?, ?, ?, ?)`,
  );
  for (const oldWord of localWords) {
    const newWord = findNewWord.get(userId, oldWord.word) as { id: number } | undefined;
    if (!newWord) continue;
    const srs = findOldSrs.get(oldWord.id) as
      | { ease: number; interval_days: number; repetitions: number; due_date: string }
      | undefined;
    if (!srs) continue;
    insertSrs.run(newWord.id, srs.ease, srs.interval_days, srs.repetitions, srs.due_date);
  }

  db.prepare(
    `INSERT INTO settings (user_id, key, value)
     SELECT ?, key, value FROM settings WHERE user_id = ?`,
  ).run(userId, localId);

  return { cookie, userId };
}
