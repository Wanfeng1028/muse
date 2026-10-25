import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import {
  SUBJECTS,
  type CreateFocusInput,
  type FocusBySubjectResponse,
  type FocusSession,
  type FocusStats,
  type FocusSubjectSummary,
  type SubjectKey,
  isSubjectKey,
} from '@kaoyan/shared';
import { todayStr, addDays, nowIso } from '../db';

// 查询参数类型
interface FocusQuery {
  limit?: string;
}

interface StatsQuery {
  days?: string;
}

// 数据库行类型
interface FocusRow {
  id: number;
  subject: string;
  minutes: number;
  started_at: string;
  note: string | null;
  plan_id: number | null;
}

interface DaySumRow {
  day: string;
  minutes: number;
}

// 将数据库行映射为 FocusSession
function mapFocus(row: FocusRow): FocusSession {
  return {
    id: row.id,
    subject: row.subject as SubjectKey,
    minutes: row.minutes,
    startedAt: row.started_at,
    note: row.note === null ? null : row.note,
    planId: row.plan_id ?? null,
  };
}

export function registerFocusRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // GET /api/focus —— 按 started_at 降序返回专注记录
  app.get<{ Querystring: FocusQuery }>('/api/focus', (req, reply) => {
    let limit = 50;
    if (req.query.limit !== undefined) {
      const parsed = Number(req.query.limit);
      if (Number.isFinite(parsed) && parsed > 0) {
        limit = Math.min(Math.floor(parsed), 500);
      }
    }
    const rows = db
      .prepare(
        'SELECT id, subject, minutes, started_at, note, plan_id FROM focus_sessions WHERE user_id = ? ORDER BY started_at DESC LIMIT ?'
      )
      .all(req.user!.id, limit) as unknown as FocusRow[];
    return reply.send(rows.map(mapFocus));
  });

  // POST /api/focus —— 新增一条专注记录
  app.post<{ Body: CreateFocusInput }>('/api/focus', (req, reply) => {
    const body = req.body ?? ({} as CreateFocusInput);
    const { subject, minutes, startedAt, note } = body;

    // 校验 subject
    if (!isSubjectKey(subject)) {
      return reply.code(400).send({ error: 'invalid subject' });
    }
    // 校验 minutes 为 1~1440 整数
    if (
      typeof minutes !== 'number' ||
      !Number.isInteger(minutes) ||
      minutes < 1 ||
      minutes > 1440
    ) {
      return reply.code(400).send({ error: 'minutes must be an integer between 1 and 1440' });
    }

    // 校验 startedAt：提供时必须为合法的 ISO 8601 日期时间字符串，且可解析
    // 强约束：以 YYYY-MM-DD 开头（保证 substr(1,10) 正确），长度 10~40，Date.parse 可解析
    let finalStartedAt: string;
    if (startedAt !== undefined && startedAt !== null) {
      if (typeof startedAt !== 'string') {
        return reply.code(400).send({ error: 'startedAt must be a valid date string' });
      }
      const trimmed = startedAt.trim();
      if (
        !/^\d{4}-\d{2}-\d{2}/.test(trimmed) ||
        trimmed.length < 10 ||
        trimmed.length > 40 ||
        Number.isNaN(Date.parse(trimmed))
      ) {
        return reply.code(400).send({ error: 'startedAt must be a valid date string' });
      }
      finalStartedAt = trimmed;
    } else {
      finalStartedAt = nowIso();
    }

    // 校验 note：可选，若提供必须是字符串且长度 <= 500
    let finalNote: string | null;
    if (note === undefined || note === null) {
      finalNote = null;
    } else if (typeof note !== 'string' || note.length > 500) {
      return reply.code(400).send({ error: 'note must be a string up to 500 chars' });
    } else {
      finalNote = note;
    }

    // 校验 planId：可选；提供时必须为正整数且为当前用户的计划
    let finalPlanId: number | null = null;
    if (body.planId !== undefined) {
      if (!Number.isInteger(body.planId) || (body.planId as number) <= 0) {
        return reply.code(400).send({ error: 'planId 非法' });
      }
      const plan = db
        .prepare('SELECT id FROM plans WHERE id = ? AND user_id = ?')
        .get(body.planId, req.user!.id) as unknown as { id: number } | undefined;
      if (!plan) {
        return reply.code(404).send({ error: '计划不存在' });
      }
      finalPlanId = body.planId;
    }

    const result = db
      .prepare(
        'INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note, plan_id) VALUES (?, ?, ?, ?, ?, ?)'
      )
      .run(req.user!.id, subject, minutes, finalStartedAt, finalNote, finalPlanId);

    const id = Number(result.lastInsertRowid);
    const session: FocusSession = {
      id,
      subject,
      minutes,
      startedAt: finalStartedAt,
      note: finalNote,
      planId: finalPlanId,
    };

    return reply.code(201).send(session);
  });

  // GET /api/focus/stats —— 返回专注统计
  app.get<{ Querystring: StatsQuery }>('/api/focus/stats', (req, reply) => {
    let days = 7;
    if (req.query.days !== undefined) {
      const parsed = Number(req.query.days);
      if (Number.isFinite(parsed)) {
        days = Math.min(Math.max(Math.floor(parsed), 1), 31);
      }
    }

    const today = todayStr();
    const startDate = addDays(today, -(days - 1));

    // 按日期分组统计（使用 started_at 前 10 位）
    const dayRows = db
      .prepare(
        "SELECT substr(started_at, 1, 10) AS day, SUM(minutes) AS minutes " +
          'FROM focus_sessions WHERE user_id = ? AND substr(started_at, 1, 10) >= ? ' +
          'GROUP BY day'
      )
      .all(req.user!.id, startDate) as unknown as DaySumRow[];

    const dayMap = new Map<string, number>();
    for (const r of dayRows) {
      dayMap.set(r.day, Number(r.minutes));
    }

    // 组装最近 days 天（含今天）按日期升序
    const daysArr: { date: string; minutes: number }[] = [];
    for (let i = 0; i < days; i++) {
      const date = addDays(startDate, i);
      daysArr.push({ date, minutes: dayMap.get(date) ?? 0 });
    }

    const todayMinutes = dayMap.get(today) ?? 0;
    const weekMinutes = daysArr.reduce((sum, d) => sum + d.minutes, 0);

    // 全部历史总和
    const totalRow = db
      .prepare('SELECT COALESCE(SUM(minutes), 0) AS total FROM focus_sessions WHERE user_id = ?')
      .get(req.user!.id) as unknown as { total: number };
    const totalMinutes = Number(totalRow.total);

    const stats: FocusStats = {
      days: daysArr,
      todayMinutes,
      weekMinutes,
      totalMinutes,
    };
    return reply.send(stats);
  });

  // GET /api/focus/summary/by-subject —— 分科汇总专注时长：仅返回有记录的科目，按 SUBJECTS 顺序排列
  app.get('/api/focus/summary/by-subject', (req, reply) => {
    const rows = db
      .prepare(
        'SELECT subject, COUNT(*) AS sessions, COALESCE(SUM(minutes), 0) AS totalMinutes ' +
          'FROM focus_sessions WHERE user_id = ? GROUP BY subject'
      )
      .all(req.user!.id) as Array<{ subject: string; sessions: number; totalMinutes: number }>;

    const subjectMap = new Map(rows.map((r) => [r.subject, r]));

    const subjects: FocusSubjectSummary[] = [];
    for (const s of SUBJECTS) {
      const row = subjectMap.get(s.key);
      if (row && row.sessions > 0) {
        subjects.push({
          subject: s.key,
          sessions: Number(row.sessions),
          totalMinutes: Number(row.totalMinutes),
        });
      }
    }

    const result: FocusBySubjectResponse = { subjects };
    return reply.send(result);
  });
}
