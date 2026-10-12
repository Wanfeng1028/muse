import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import {
  type Plan,
  type CreatePlanInput,
  type UpdatePlanInput,
  type PlanSummary,
  isSubjectKey,
} from '@kaoyan/shared';
import { todayStr } from '../db';

// 数据库行类型（snake_case）
interface PlanRow {
  id: number;
  date: string;
  subject: string;
  title: string;
  planned_minutes: number;
  done: number;
  created_at: string;
}

// 行映射：snake_case -> Plan（done 转 boolean）
function mapPlan(row: PlanRow): Plan {
  return {
    id: row.id,
    date: row.date,
    subject: row.subject as Plan['subject'],
    title: row.title,
    plannedMinutes: row.planned_minutes,
    done: row.done === 1,
    createdAt: row.created_at,
  };
}

// 校验日期格式 YYYY-MM-DD
function isValidDate(s: unknown): s is string {
  if (typeof s !== 'string') return false;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const d = new Date(s + 'T00:00:00');
  return !Number.isNaN(d.getTime());
}

export function registerPlansRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // 查询列表：可选 date / subject 过滤
  app.get('/api/plans', async (req, reply) => {
    const q = req.query as Record<string, unknown>;
    const where: string[] = [];
    const params: unknown[] = [];

    if (q.date !== undefined) {
      if (!isValidDate(q.date)) {
        return reply.code(400).send({ error: 'date 格式非法，应为 YYYY-MM-DD' });
      }
      where.push('date = ?');
      params.push(q.date);
    }
    if (q.subject !== undefined) {
      if (typeof q.subject !== 'string' || !isSubjectKey(q.subject)) {
        return reply.code(400).send({ error: 'subject 非法' });
      }
      where.push('subject = ?');
      params.push(q.subject);
    }

    const sql =
      'SELECT id, date, subject, title, planned_minutes, done, created_at FROM plans' +
      (where.length ? ' WHERE ' + where.join(' AND ') : '') +
      ' ORDER BY date ASC, id ASC';

    const rows = db.prepare(sql).all(...(params as never[])) as unknown as PlanRow[];
    return reply.send(rows.map(mapPlan));
  });

  // 计划汇总统计
  app.get('/api/plans/summary', async (req, reply) => {
    const q = req.query as Record<string, unknown>;
    let date: string;
    if (q.date === undefined) {
      date = todayStr();
    } else {
      if (!isValidDate(q.date)) {
        return reply.code(400).send({ error: 'date 格式非法，应为 YYYY-MM-DD' });
      }
      date = q.date;
    }

    const row = db
      .prepare(
        'SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done FROM plans WHERE date = ?',
      )
      .get(date) as unknown as { total: number; done: number };

    const total = Number(row?.total ?? 0);
    const done = Number(row?.done ?? 0);
    const completionRate = total === 0 ? 0 : Number((done / total).toFixed(4));

    const summary: PlanSummary = { date, total, done, completionRate };
    return reply.send(summary);
  });

  // 新建计划
  app.post('/api/plans', async (req, reply) => {
    const body = (req.body ?? {}) as Partial<CreatePlanInput>;

    // 校验 title
    if (typeof body.title !== 'string' || body.title.trim() === '') {
      return reply.code(400).send({ error: 'title 不能为空' });
    }
    // 校验 subject
    if (typeof body.subject !== 'string' || !isSubjectKey(body.subject)) {
      return reply.code(400).send({ error: 'subject 非法' });
    }
    // 校验 plannedMinutes
    if (
      typeof body.plannedMinutes !== 'number' ||
      !Number.isFinite(body.plannedMinutes) ||
      body.plannedMinutes < 1 ||
      body.plannedMinutes > 1440
    ) {
      return reply.code(400).send({ error: 'plannedMinutes 必须为 1~1440 的数字' });
    }
    // 校验 date（缺省今天）
    let date: string;
    if (body.date === undefined) {
      date = todayStr();
    } else if (!isValidDate(body.date)) {
      return reply.code(400).send({ error: 'date 格式非法，应为 YYYY-MM-DD' });
    } else {
      date = body.date;
    }

    const createdAt = new Date().toISOString();
    const info = db
      .prepare(
        'INSERT INTO plans (date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, ?, ?, 0, ?)',
      )
      .run(date, body.subject, body.title, body.plannedMinutes, createdAt);

    const id = Number(info.lastInsertRowid);
    const row = db
      .prepare(
        'SELECT id, date, subject, title, planned_minutes, done, created_at FROM plans WHERE id = ?',
      )
      .get(id) as unknown as PlanRow;

    return reply.code(201).send(mapPlan(row));
  });

  // 更新计划（逐字段可选）
  app.patch('/api/plans/:id', async (req, reply) => {
    const params = req.params as { id: string };
    const id = Number(params.id);
    if (!Number.isInteger(id) || id <= 0) {
      return reply.code(400).send({ error: 'id 非法' });
    }

    const existing = db
      .prepare('SELECT id FROM plans WHERE id = ?')
      .get(id) as unknown as { id: number } | undefined;
    if (!existing) {
      return reply.code(404).send({ error: '计划不存在' });
    }

    const body = (req.body ?? {}) as UpdatePlanInput;
    const sets: string[] = [];
    const values: unknown[] = [];

    if (body.date !== undefined) {
      if (!isValidDate(body.date)) {
        return reply.code(400).send({ error: 'date 格式非法，应为 YYYY-MM-DD' });
      }
      sets.push('date = ?');
      values.push(body.date);
    }
    if (body.subject !== undefined) {
      if (typeof body.subject !== 'string' || !isSubjectKey(body.subject)) {
        return reply.code(400).send({ error: 'subject 非法' });
      }
      sets.push('subject = ?');
      values.push(body.subject);
    }
    if (body.title !== undefined) {
      if (typeof body.title !== 'string' || body.title.trim() === '') {
        return reply.code(400).send({ error: 'title 不能为空' });
      }
      sets.push('title = ?');
      values.push(body.title);
    }
    if (body.plannedMinutes !== undefined) {
      if (
        typeof body.plannedMinutes !== 'number' ||
        !Number.isFinite(body.plannedMinutes) ||
        body.plannedMinutes < 1 ||
        body.plannedMinutes > 1440
      ) {
        return reply.code(400).send({ error: 'plannedMinutes 必须为 1~1440 的数字' });
      }
      sets.push('planned_minutes = ?');
      values.push(body.plannedMinutes);
    }
    if (body.done !== undefined) {
      if (typeof body.done !== 'boolean') {
        return reply.code(400).send({ error: 'done 必须为布尔值' });
      }
      sets.push('done = ?');
      values.push(body.done ? 1 : 0);
    }

    if (sets.length > 0) {
      values.push(id);
      db.prepare(`UPDATE plans SET ${sets.join(', ')} WHERE id = ?`).run(
        ...(values as never[]),
      );
    }

    const row = db
      .prepare(
        'SELECT id, date, subject, title, planned_minutes, done, created_at FROM plans WHERE id = ?',
      )
      .get(id) as unknown as PlanRow;

    return reply.send(mapPlan(row));
  });

  // 删除计划
  app.delete('/api/plans/:id', async (req, reply) => {
    const params = req.params as { id: string };
    const id = Number(params.id);
    if (!Number.isInteger(id) || id <= 0) {
      return reply.code(400).send({ error: 'id 非法' });
    }

    const existing = db
      .prepare('SELECT id FROM plans WHERE id = ?')
      .get(id) as unknown as { id: number } | undefined;
    if (!existing) {
      return reply.code(404).send({ error: '计划不存在' });
    }

    db.prepare('DELETE FROM plans WHERE id = ?').run(id);
    return reply.send({ ok: true });
  });
}
