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
import { parseCsv, normalizeHeader, buildHeaderIndex, cellAt } from './backup';

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
      if (!/^-?\d+$/.test(req.query.limit)) {
        return reply.code(400).send({ error: "limit 参数无效" });
      }
      if (parsed > 0) {
        limit = Math.min(parsed, 500);
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
      const str = String(req.query.days);
      if (!/^-?\d+$/.test(str)) {
        return reply.code(400).send({ error: "days 参数无效" });
      }
      const parsed = Number(str);
      if (parsed < 1 || parsed > 31) {
        return reply.code(400).send({ error: "days 参数无效" });
      }
      days = parsed;
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
  // 可选 ?days=N：只统计最近 N 天（含今天），N 越界（不在 1~31）返回 400；
  // 不传时统计全部历史，非法 days 返回 400
  app.get<{ Querystring: StatsQuery }>('/api/focus/summary/by-subject', (req, reply) => {
    let startDate: string | undefined;
    if (req.query.days !== undefined) {
      if (!/^-?\d+$/.test(req.query.days)) {
        return reply.code(400).send({ error: "days 参数无效" });
      }
      const parsed = Number(req.query.days);
      if (parsed < 1 || parsed > 31) {
        return reply.code(400).send({ error: "days 参数无效" });
      }
      startDate = addDays(todayStr(), -(parsed - 1));
    }
    const rows = db
      .prepare(
        'SELECT subject, COUNT(*) AS sessions, COALESCE(SUM(minutes), 0) AS totalMinutes ' +
          'FROM focus_sessions WHERE user_id = ? ' +
          (startDate ? 'AND substr(started_at, 1, 10) >= ? ' : '') +
          'GROUP BY subject'
      )
      .all(
        ...(startDate ? [req.user!.id, startDate] : [req.user!.id])
      ) as Array<{ subject: string; sessions: number; totalMinutes: number }>;

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

  app.get('/api/focus/export', async (req, reply) => {
    const subject = (req.query as { subject?: string }).subject;
    if (subject !== undefined && !isSubjectKey(subject)) {
      reply.code(400).send({ error: 'subject 非法' });
      return;
    }

    const sql = subject
      ? 'SELECT id, subject, minutes, started_at, note, plan_id FROM focus_sessions WHERE user_id = ? AND subject = ? ORDER BY started_at ASC, id ASC'
      : 'SELECT id, subject, minutes, started_at, note, plan_id FROM focus_sessions WHERE user_id = ? ORDER BY started_at ASC, id ASC';
    const params = subject ? [req.user!.id, subject] : [req.user!.id];
    const rows = db.prepare(sql).all(...params) as unknown as FocusRow[];

    const escapeCsvCell = (value: string): string => {
      if (/[",\r\n]/.test(value)) {
        return `"${value.replace(/"/g, '""')}"`;
      }
      return value;
    };

    const lines: string[] = ['id,subject,subject_name,minutes,started_at,note,plan_id'];
    for (const row of rows) {
      const subjectName =
        SUBJECTS.find((s) => s.key === row.subject)?.name ?? row.subject;
      lines.push(
        [
          escapeCsvCell(String(row.id)),
          escapeCsvCell(row.subject),
          escapeCsvCell(subjectName),
          escapeCsvCell(String(row.minutes)),
          escapeCsvCell(row.started_at),
          escapeCsvCell(row.note ?? ''),
          escapeCsvCell(row.plan_id == null ? '' : String(row.plan_id)),
        ].join(','),
      );
    }

    const csv = '\uFEFF' + lines.join('\n') + '\n';
    const filename = subject ? `kaoyan-focus-${subject}.csv` : 'kaoyan-focus.csv';
    reply.header('Content-Type', 'text/csv; charset=utf-8');
    reply.header('Content-Disposition', `attachment; filename="${filename}"`);
    reply.send(csv);
  });


app.post('/api/import/focus', { bodyLimit: 5 * 1024 * 1024 }, async (req, reply) => {
  const body = (typeof req.body === 'object' && req.body !== null ? req.body : {}) as Record<string, unknown>;
  const csv = typeof body.csv === 'string' ? body.csv : '';
  if (csv.trim() === '') {
    return reply.code(400).send({ error: 'csv 不能为空' });
  }

  const rows = parseCsv(csv);
  let headerIdx = 0;
  while (headerIdx < rows.length && rows[headerIdx].every((cell) => cell.trim() === '')) headerIdx++;
  const headerIndex = buildHeaderIndex(normalizeHeader(rows[headerIdx] ?? []));
  if (!headerIndex.has('subject') || !headerIndex.has('minutes') || !headerIndex.has('started_at')) {
    return reply.code(400).send({ error: '缺少必需列：subject / minutes / started_at' });
  }

  const userId = req.user!.id;
  const planExistsStmt = db.prepare('SELECT id FROM plans WHERE id = ? AND user_id = ?');
  const insertStmt = db.prepare(
    'INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note, plan_id) VALUES (?, ?, ?, ?, ?, ?)'
  );
  const getCell = (row: string[], name: string): string => {
    const idx = headerIndex.get(name);
    return idx === undefined ? '' : (cellAt(row, idx) ?? '').trim();
  };

  const errors: { row: number; message: string }[] = [];
  let errorRows = 0;
  let imported = 0;

  for (let i = headerIdx + 1; i < rows.length; i++) {
    const row = rows[i];
    if (row.every((cell) => cell.trim() === '')) continue;
    const rowNo = i + 1;

    const rowErrors: string[] = [];

    const subject = getCell(row, 'subject');
    if (!isSubjectKey(subject)) {
      rowErrors.push('subject 非法');
    }

    const minutes = Math.floor(Number(getCell(row, 'minutes')));
    if (!Number.isFinite(minutes) || minutes < 1 || minutes > 1440) {
      rowErrors.push('minutes 须为 1 到 1440 之间的整数');
    }

    const startedAt = getCell(row, 'started_at');
    const startedAtOk =
      startedAt.length >= 10 &&
      startedAt.length <= 40 &&
      /^\d{4}-\d{2}-\d{2}/.test(startedAt) &&
      !Number.isNaN(Date.parse(startedAt));
    if (!startedAtOk) {
      rowErrors.push('started_at 格式非法');
    }

    let note: string | null = null;
    const noteCell = getCell(row, 'note');
    if (noteCell !== '') {
      if (noteCell.length > 500) {
        rowErrors.push('note 超过 500 字');
      } else {
        note = noteCell;
      }
    }

    let planId: number | null = null;
    const planIdCell = getCell(row, 'plan_id');
    if (planIdCell !== '') {
      const parsedPlanId = Number(planIdCell);
      if (!Number.isInteger(parsedPlanId) || parsedPlanId <= 0) {
        rowErrors.push('plan_id 须为正整数');
      } else if (!planExistsStmt.get(parsedPlanId, userId)) {
        rowErrors.push('plan_id 不存在');
      } else {
        planId = parsedPlanId;
      }
    }

    if (rowErrors.length > 0) {
      errorRows++;
      for (const message of rowErrors) {
        if (errors.length >= 50) break;
        errors.push({ row: rowNo, message });
      }
      continue;
    }

    insertStmt.run(userId, subject, minutes, startedAt, note, planId);
    imported++;
  }

  return reply.code(200).send({ imported, errors, errorRows });
});
}
