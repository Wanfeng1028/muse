import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import {
  type Plan,
  type CreatePlanInput,
  type UpdatePlanInput,
  type PlanSummary,
  type PlanProgress,
  type PlanSubjectSummary,
  type PlansBySubjectResponse,
  type AutoScheduleItem,
  type SubjectKey,
  isSubjectKey,
  SUBJECTS,
} from '@kaoyan/shared';
import { todayStr, addDays } from '../db';
import { computeDayLoads } from '../schedule-stats';

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
  const [y, m, day] = s.split('-').map(Number);
  const d = new Date(s + 'T00:00:00');
  if (Number.isNaN(d.getTime())) return false;
  return d.getFullYear() === y && d.getMonth() + 1 === m && d.getDate() === day;
}

const REVIEW_OFFSETS = [1, 3, 7, 15, 30];
const NEW_MINUTES = 60;
const REVIEW_MINUTES = 30;

function buildSchedule(
  subjects: Plan['subject'][],
  dailyMinutes: number,
  examDate: string,
  startDate: string,
): { items: AutoScheduleItem[]; discarded: number } {
  const raw: AutoScheduleItem[] = [];
  let discarded = 0;
  for (let si = 0; si < subjects.length; si++) {
    const key = subjects[si];
    const name = SUBJECTS.find((s) => s.key === key)?.name ?? key;
    let n = 1;
    while (true) {
      const D = addDays(startDate, si + (n - 1) * 2);
      if (D > examDate) break;
      raw.push({
        date: D,
        subject: key,
        title: `智能排期·${name} 新学${n}`,
        plannedMinutes: NEW_MINUTES,
        kind: 'new',
      });
      for (const offset of REVIEW_OFFSETS) {
        const R = addDays(D, offset);
        if (R > examDate) {
          discarded++;
          continue;
        }
        raw.push({
          date: R,
          subject: key,
          title: `智能排期·${name} 复习${n}-${offset}天`,
          plannedMinutes: REVIEW_MINUTES,
          kind: 'review',
        });
      }
      n++;
    }
  }

  raw.sort((a, b) => {
    if (a.date !== b.date) return a.date < b.date ? -1 : 1;
    const ka = a.kind === 'new' ? 0 : 1;
    const kb = b.kind === 'new' ? 0 : 1;
    return ka - kb;
  });

  const used: Record<string, number> = {};
  const placed: AutoScheduleItem[] = [];
  for (const item of raw) {
    let d = item.date;
    const minutes = item.plannedMinutes;
    if (minutes > dailyMinutes) {
      discarded++;
      continue;
    }
    while ((used[d] ?? 0) + minutes > dailyMinutes) {
      d = addDays(d, 1);
    }
    if (d > examDate) {
      discarded++;
      continue;
    }
    used[d] = (used[d] ?? 0) + minutes;
    placed.push({
      date: d,
      subject: item.subject,
      title: item.title,
      plannedMinutes: minutes,
      kind: item.kind,
    });
  }

  placed.sort((a, b) => {
    if (a.date !== b.date) return a.date < b.date ? -1 : 1;
    const ka = a.kind === 'new' ? 0 : 1;
    const kb = b.kind === 'new' ? 0 : 1;
    return ka - kb;
  });

  return { items: placed, discarded };
}

export function registerPlansRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // 查询列表：可选 date / subject 过滤
  app.get('/api/plans', async (req, reply) => {
    const userId = req.user!.id;
    const q = req.query as Record<string, unknown>;
    const where: string[] = ['user_id = ?'];
    const params: unknown[] = [userId];

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
      ' WHERE ' + where.join(' AND ') +
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
        'SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done FROM plans WHERE date = ? AND user_id = ?',
      )
      .get(date, req.user!.id) as unknown as { total: number; done: number };

    const total = Number(row?.total ?? 0);
    const done = Number(row?.done ?? 0);
    const completionRate = total === 0 ? 0 : Number((done / total).toFixed(4));

    const summary: PlanSummary = { date, total, done, completionRate, plans: [] };

    const planRows = db
      .prepare(
        'SELECT p.id AS id, p.title AS title, p.subject AS subject, ' +
          'p.planned_minutes AS planned_minutes, p.done AS done, ' +
          'COALESCE(SUM(f.minutes), 0) AS actual_minutes ' +
          'FROM plans p LEFT JOIN focus_sessions f ON f.plan_id = p.id AND f.user_id = p.user_id ' +
          'WHERE p.date = ? AND p.user_id = ? GROUP BY p.id ORDER BY p.id ASC',
      )
      .all(date, req.user!.id) as unknown as Array<{
      id: number;
      title: string;
      subject: string;
      planned_minutes: number;
      done: number;
      actual_minutes: number;
    }>;

    summary.plans = planRows.map(
      (r): PlanProgress => ({
        id: r.id,
        title: r.title,
        subject: r.subject as SubjectKey,
        plannedMinutes: Number(r.planned_minutes),
        actualMinutes: Number(r.actual_minutes),
        done: r.done === 1,
      }),
    );

    return reply.send(summary);
  });

  // 计划分科汇总：仅返回有计划的科目，按 SUBJECTS 顺序排列
  app.get('/api/plans/summary/by-subject', async (req, reply) => {
    const planRows = db
      .prepare(
        'SELECT subject, COUNT(*) AS total, COALESCE(SUM(done), 0) AS done, ' +
          'COALESCE(SUM(planned_minutes), 0) AS planned_minutes ' +
          'FROM plans WHERE user_id = ? GROUP BY subject',
      )
      .all(req.user!.id) as unknown as Array<{
      subject: string;
      total: number;
      done: number;
      planned_minutes: number;
    }>;
    const focusRows = db
      .prepare(
        'SELECT p.subject AS subject, COALESCE(SUM(f.minutes), 0) AS actual_minutes ' +
          'FROM plans p LEFT JOIN focus_sessions f ON f.plan_id = p.id AND f.user_id = p.user_id ' +
          'WHERE p.user_id = ? GROUP BY p.subject',
      )
      .all(req.user!.id) as unknown as Array<{ subject: string; actual_minutes: number }>;
    const planMap = new Map(planRows.map((r) => [r.subject, r]));
    const focusMap = new Map(focusRows.map((r) => [r.subject, Number(r.actual_minutes)]));
    const subjects: PlanSubjectSummary[] = [];
    for (const s of SUBJECTS) {
      const row = planMap.get(s.key);
      if (!row || Number(row.total) === 0) continue;
      const total = Number(row.total);
      const done = Number(row.done);
      subjects.push({
        subject: s.key,
        total,
        done,
        completionRate: total === 0 ? 0 : Number((done / total).toFixed(4)),
        plannedMinutes: Number(row.planned_minutes),
        actualMinutes: focusMap.get(s.key) ?? 0,
      });
    }
    const result: PlansBySubjectResponse = { subjects };
    return reply.send(result);
  });

  // 逾期未完成计划：date 小于今天且未完成，按 date 升序、id 升序
  app.get('/api/plans/overdue', async (req, reply) => {
    const today = todayStr();
    const rows = db
      .prepare(
        'SELECT id, date, subject, title, planned_minutes, done, created_at FROM plans WHERE user_id = ? AND date < ? AND done = 0 ORDER BY date ASC, id ASC',
      )
      .all(req.user!.id, today) as unknown as PlanRow[];
    return reply.send({ date: today, count: rows.length, plans: rows.map(mapPlan) });
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
        'INSERT INTO plans (user_id, date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)',
      )
      .run(req.user!.id, date, body.subject, body.title, body.plannedMinutes, createdAt);

    const id = Number(info.lastInsertRowid);
    const row = db
      .prepare(
        'SELECT id, date, subject, title, planned_minutes, done, created_at FROM plans WHERE id = ? AND user_id = ?',
      )
      .get(id, req.user!.id) as unknown as PlanRow;

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
      .prepare('SELECT id FROM plans WHERE id = ? AND user_id = ?')
      .get(id, req.user!.id) as unknown as { id: number } | undefined;
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
      values.push(req.user!.id);
      db.prepare(`UPDATE plans SET ${sets.join(', ')} WHERE id = ? AND user_id = ?`).run(
        ...(values as never[]),
      );
    }

    const row = db
      .prepare(
        'SELECT id, date, subject, title, planned_minutes, done, created_at FROM plans WHERE id = ? AND user_id = ?',
      )
      .get(id, req.user!.id) as unknown as PlanRow;

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
      .prepare('SELECT id FROM plans WHERE id = ? AND user_id = ?')
      .get(id, req.user!.id) as unknown as { id: number } | undefined;
    if (!existing) {
      return reply.code(404).send({ error: '计划不存在' });
    }

    // 删计划不断专注链：关联的专注记录 plan_id 置空
    db.prepare('UPDATE focus_sessions SET plan_id = NULL WHERE plan_id = ? AND user_id = ?').run(
      id,
      req.user!.id,
    );
    db.prepare('DELETE FROM plans WHERE id = ? AND user_id = ?').run(id, req.user!.id);
    return reply.send({ ok: true });
  });
  app.get('/api/plans/auto-schedule/preview', async (request, reply) => {
    const q = request.query as Record<string, unknown>;

    const subjectsRaw = q.subjects;
    if (typeof subjectsRaw !== 'string' || subjectsRaw.trim() === '') {
      return reply.code(400).send({ error: 'subjects 不能为空' });
    }
    const keys = subjectsRaw.split(',').map((s) => s.trim()).filter((s) => s.length > 0);
    if (keys.length === 0) {
      return reply.code(400).send({ error: 'subjects 不能为空' });
    }
    for (const k of keys) {
      if (!isSubjectKey(k)) {
        return reply.code(400).send({ error: 'subject 非法' });
      }
    }

    const dailyMinutesRaw = q.dailyMinutes;
    const dailyMinutes = typeof dailyMinutesRaw === 'string' ? Number(dailyMinutesRaw) : NaN;
    if (
      !Number.isInteger(dailyMinutes) ||
      dailyMinutes < 30 ||
      dailyMinutes > 1440
    ) {
      return reply.code(400).send({ error: 'dailyMinutes 非法' });
    }

    const examDate = q.examDate;
    if (!isValidDate(examDate)) {
      return reply.code(400).send({ error: 'examDate 非法' });
    }

    let startDate: string;
    if (q.startDate === undefined || q.startDate === null || q.startDate === '') {
      startDate = todayStr();
    } else if (isValidDate(q.startDate)) {
      startDate = q.startDate;
    } else {
      return reply.code(400).send({ error: 'startDate 非法' });
    }

    if (examDate < startDate) {
      return reply.code(400).send({ error: 'examDate 不能早于 startDate' });
    }

    const { items } = buildSchedule(keys as Plan['subject'][], dailyMinutes, examDate, startDate);
    return reply.send({ items });
  });

  app.post('/api/plans/auto-schedule', async (request, reply) => {
    const body = (request.body ?? {}) as Record<string, unknown>;

    const subjectsRaw = body.subjects;
    if (!Array.isArray(subjectsRaw) || subjectsRaw.length === 0) {
      return reply.code(400).send({ error: 'subjects 不能为空' });
    }
    for (const k of subjectsRaw) {
      if (!isSubjectKey(k)) {
        return reply.code(400).send({ error: 'subject 非法' });
      }
    }
    const subjects = subjectsRaw as Plan['subject'][];

    const dailyMinutes = body.dailyMinutes;
    if (
      typeof dailyMinutes !== 'number' ||
      !Number.isInteger(dailyMinutes) ||
      dailyMinutes < 30 ||
      dailyMinutes > 1440
    ) {
      return reply.code(400).send({ error: 'dailyMinutes 非法' });
    }

    const examDate = body.examDate;
    if (!isValidDate(examDate)) {
      return reply.code(400).send({ error: 'examDate 非法' });
    }

    let startDate: string;
    if (body.startDate === undefined || body.startDate === null || body.startDate === '') {
      startDate = todayStr();
    } else if (isValidDate(body.startDate)) {
      startDate = body.startDate;
    } else {
      return reply.code(400).send({ error: 'startDate 非法' });
    }

    if (examDate < startDate) {
      return reply.code(400).send({ error: 'examDate 不能早于 startDate' });
    }

    const userId = request.user!.id;
    const { items: scheduled, discarded } = buildSchedule(subjects, dailyMinutes, examDate, startDate);

    let created = 0;
    let skipped = 0;
    const items: Plan[] = [];

    for (const item of scheduled) {
      const existing = db
        .prepare(
          'SELECT id FROM plans WHERE user_id = ? AND date = ? AND subject = ? AND title = ?',
        )
        .get(userId, item.date, item.subject, item.title) as { id: number } | undefined;
      if (existing) {
        skipped++;
        continue;
      }
      const createdAt = new Date().toISOString();
      const result = db
        .prepare(
          'INSERT INTO plans (user_id, date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
        )
        .run(
          userId,
          item.date,
          item.subject,
          item.title,
          item.plannedMinutes,
          0,
          createdAt,
        );
      const row = db
        .prepare('SELECT * FROM plans WHERE id = ?')
        .get(Number(result.lastInsertRowid)) as unknown as PlanRow;
      items.push(mapPlan(row));
      created++;
    }

    return reply.send({ created, skipped, discarded, items });
  });

  // 区间查询：from/to（含），最多 62 天
  app.get('/api/plans/range', async (req, reply) => {
    const userId = req.user!.id;
    const q = req.query as Record<string, unknown>;

    if (!isValidDate(q.from) || !isValidDate(q.to)) {
      return reply.code(400).send({ error: 'from/to 格式非法，应为 YYYY-MM-DD' });
    }
    const from = q.from;
    const to = q.to;

    if (from > to) {
      return reply.code(400).send({ error: 'from 不能晚于 to' });
    }

    // 计算天数（含端点）
    const [fy, fm, fd] = from.split('-').map(Number);
    const [ty, tm, td] = to.split('-').map(Number);
    const fromUtc = Date.UTC(fy, fm - 1, fd);
    const toUtc = Date.UTC(ty, tm - 1, td);
    const days = Math.round((toUtc - fromUtc) / 86400000) + 1;
    if (days > 62) {
      return reply.code(400).send({ error: '区间不能超过 62 天' });
    }

    const rows = db
      .prepare(
        'SELECT id, date, subject, title, planned_minutes, done, created_at FROM plans' +
          ' WHERE user_id = ? AND date >= ? AND date <= ?' +
          ' ORDER BY date ASC, id ASC',
      )
      .all(userId, from, to) as unknown as PlanRow[];

    return reply.send(rows.map(mapPlan));
  });

  // 单日负荷预警：weekStart + dailyMinutes，返回 7 天 DayLoad
  app.get('/api/plans/overload', async (req, reply) => {
    const userId = req.user!.id;
    const q = req.query as Record<string, unknown>;

    if (!isValidDate(q.weekStart)) {
      return reply.code(400).send({ error: 'weekStart 格式非法，应为 YYYY-MM-DD' });
    }
    const weekStart = q.weekStart;

    const dailyMinutesRaw = q.dailyMinutes;
    const dailyMinutes =
      typeof dailyMinutesRaw === 'string'
        ? Number(dailyMinutesRaw)
        : typeof dailyMinutesRaw === 'number'
          ? dailyMinutesRaw
          : NaN;
    if (
      !Number.isInteger(dailyMinutes) ||
      dailyMinutes < 30 ||
      dailyMinutes > 1440
    ) {
      return reply.code(400).send({ error: 'dailyMinutes 非法' });
    }

    const weekEnd = addDays(weekStart, 6);

    const rows = db
      .prepare(
        'SELECT id, date, subject, title, planned_minutes, done, created_at FROM plans' +
          ' WHERE user_id = ? AND date >= ? AND date <= ?' +
          ' ORDER BY date ASC, id ASC',
      )
      .all(userId, weekStart, weekEnd) as unknown as PlanRow[];

    const plansForStats = rows.map((r) => ({
      id: r.id,
      date: r.date,
      subject: r.subject as SubjectKey,
      title: r.title,
      plannedMinutes: r.planned_minutes,
      done: r.done === 1,
    }));

    const days = computeDayLoads(plansForStats, dailyMinutes, weekStart, 7);
    const overloadedDays = days.filter((d) => d.overloaded).length;

    return reply.send({
      weekStart,
      weekEnd,
      dailyMinutes,
      overloadedDays,
      days,
    });
  });
}
