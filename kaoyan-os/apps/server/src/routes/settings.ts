import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { DEFAULT_SETTINGS, type Settings } from '@kaoyan/shared';

// settings 表 key <-> Settings 字段 映射
const KEY_MAP: Array<[keyof Settings, string]> = [
  ['examDate', 'exam_date'],
  ['dailyGoalMinutes', 'daily_goal_minutes'],
  ['pomodoroMinutes', 'pomodoro_minutes'],
  ['breakMinutes', 'break_minutes'],
];

// 数字字段上限校验
const NUMBER_LIMITS: Record<'dailyGoalMinutes' | 'pomodoroMinutes' | 'breakMinutes', number> = {
  dailyGoalMinutes: 1440,
  pomodoroMinutes: 180,
  breakMinutes: 60,
};

// 从数据库读取全部 settings，并与默认值合并
function readSettings(db: DatabaseSync): Settings {
  const rows = db.prepare('SELECT key, value FROM settings').all() as Array<{
    key: string;
    value: string;
  }>;
  const map = new Map<string, string>();
  for (const row of rows) map.set(row.key, row.value);

  const result: Settings = { ...DEFAULT_SETTINGS };
  for (const [field, dbKey] of KEY_MAP) {
    const raw = map.get(dbKey);
    if (raw === undefined) continue;
    if (field === 'examDate') {
      result.examDate = raw;
    } else {
      const n = parseInt(raw, 10);
      if (!Number.isNaN(n)) result[field] = n;
    }
  }
  return result;
}

// 校验单个字段，返回规范化后的值或 null 表示非法
function validateField(
  field: keyof Settings,
  value: unknown
): { ok: true; value: string } | { ok: false } {
  if (field === 'examDate') {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return { ok: false };
    return { ok: true, value };
  }
  // 数字字段
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return { ok: false };
  const limit = NUMBER_LIMITS[field as keyof typeof NUMBER_LIMITS];
  if (limit !== undefined && value > limit) return { ok: false };
  return { ok: true, value: String(Math.floor(value)) };
}

export function registerSettingsRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // 获取设置
  app.get('/api/settings', async (_req, reply) => {
    const settings = readSettings(db);
    return reply.send(settings);
  });

  // 更新设置
  app.put('/api/settings', async (req, reply) => {
    const body = (req.body ?? {}) as Partial<Settings>;
    const updates: Array<[string, string]> = [];

    for (const [field, dbKey] of KEY_MAP) {
      if (!(field in body)) continue; // 未提供的字段保持不变
      const check = validateField(field, (body as Record<string, unknown>)[field]);
      if (!check.ok) {
        return reply.status(400).send({ error: `invalid field: ${field}` });
      }
      updates.push([dbKey, check.value]);
    }

    // upsert 合法字段
    const stmt = db.prepare(
      'INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value'
    );
    for (const [key, value] of updates) {
      stmt.run(key, value);
    }

    return reply.send(readSettings(db));
  });
}
