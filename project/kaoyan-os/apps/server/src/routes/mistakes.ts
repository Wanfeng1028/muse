import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import {
  isSubjectKey,
  SUBJECTS,
  type Mistake,
  type CreateMistakeInput,
  type UpdateMistakeInput,
  type MistakeSummary,
  type MistakeSubjectSummary,
  type MistakesBySubjectResponse,
  type ExamRecord,
  type QuizItem,
  type QuizGradeResult,
} from '@kaoyan/shared';

import { nowIso } from '../db';

// 严格日期校验 YYYY-MM-DD（含闰年/月份合法性）
function isValidDate(s: unknown): s is string {
  if (typeof s !== 'string') return false;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const [y, m, day] = s.split('-').map(Number);
  const d = new Date(s + 'T00:00:00');
  if (Number.isNaN(d.getTime())) return false;
  return d.getFullYear() === y && d.getMonth() + 1 === m && d.getDate() === day;
}

// 数据库行结构
interface MistakeRow {
  id: number;
  subject: string;
  title: string;
  content: string;
  analysis: string;
  mastered: number;
  created_at: string;
}

// 行 -> 契约对象
function rowToMistake(row: MistakeRow): Mistake {
  return {
    id: row.id,
    subject: row.subject as Mistake['subject'],
    title: row.title,
    content: row.content,
    analysis: row.analysis,
    mastered: row.mastered === 1,
    createdAt: row.created_at,
  };
}

export function registerMistakesRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // 错题掌握率：可选 subject 过滤
  app.get('/api/mistakes/summary', async (request, reply) => {
    const query = request.query as { subject?: string };
    const subject = query.subject;

    if (subject !== undefined && !isSubjectKey(subject)) {
      return reply.code(400).send({ error: '无效的 subject 参数' });
    }

    const rows = subject
      ? (db
          .prepare('SELECT mastered FROM mistakes WHERE user_id = ? AND subject = ?')
          .all(request.user!.id, subject) as Array<{ mastered: number }>)
      : (db.prepare('SELECT mastered FROM mistakes WHERE user_id = ?').all(request.user!.id) as Array<{
          mastered: number;
        }>);

    const total = rows.length;
    let mastered = 0;
    for (const row of rows) {
      if (row.mastered === 1) {
        mastered += 1;
      }
    }
    const unmastered = total - mastered;
    const masteredRate =
      total === 0 ? 0 : Math.round((mastered / total) * 10000) / 10000;

    const result: MistakeSummary = {
      subject: subject ?? null,
      total,
      mastered,
      unmastered,
      masteredRate,
    };
    return reply.send(result);
  });

  // 错题分科掌握率：仅返回有错题的科目，按 SUBJECTS 顺序排列
  app.get('/api/mistakes/summary/by-subject', async (request, reply) => {
    const rows = db
      .prepare(
        'SELECT subject, COUNT(*) AS total, COALESCE(SUM(mastered), 0) AS mastered FROM mistakes WHERE user_id = ? GROUP BY subject',
      )
      .all(request.user!.id) as Array<{ subject: string; total: number; mastered: number }>;

    const subjectMap = new Map(rows.map((r) => [r.subject, r]));

    const subjects: MistakeSubjectSummary[] = [];
    for (const s of SUBJECTS) {
      const row = subjectMap.get(s.key);
      if (row && row.total > 0) {
        const { total, mastered } = row;
        const unmastered = total - mastered;
        const masteredRate = total === 0 ? 0 : Math.round((mastered / total) * 10000) / 10000;
        subjects.push({ subject: s.key, total, mastered, unmastered, masteredRate });
      }
    }

    const result: MistakesBySubjectResponse = { subjects };
    return reply.send(result);
  });

  // GET /api/mistakes/export - 导出错题为 CSV（同真题导出口径：BOM + RFC4180 转义）
app.get('/api/mistakes/export', async (request, reply) => {
  const { subject } = request.query as { subject?: string };
  if (subject && !isSubjectKey(subject)) {
    return reply.code(400).send({ error: '无效的 subject' });
  }

  const escapeField = (value: unknown): string => {
    const str = value == null ? '' : String(value);
    if (/[",\r\n]/.test(str)) {
      return '"' + str.replace(/"/g, '""') + '"';
    }
    return str;
  };

  const params: Array<string | number> = [request.user!.id];
  let sql =
    'SELECT id, subject, title, content, analysis, mastered, created_at FROM mistakes WHERE user_id = ?';
  if (subject) {
    sql += ' AND subject = ?';
    params.push(subject);
  }
  sql += ' ORDER BY created_at ASC, id ASC';

  const rows = db.prepare(sql).all(...params) as unknown as MistakeRow[];

  const lines = ['id,subject,subject_name,title,content,analysis,mastered,created_at'];
  for (const row of rows) {
    const subjectName = SUBJECTS.find((s) => s.key === row.subject)?.name ?? row.subject;
    lines.push(
      [
        escapeField(row.id),
        escapeField(row.subject),
        escapeField(subjectName),
        escapeField(row.title),
        escapeField(row.content),
        escapeField(row.analysis),
        escapeField(row.mastered ? 1 : 0),
        escapeField(row.created_at),
      ].join(','),
    );
  }

  const csv = '\ufeff' + lines.join('\n') + '\n';
  const filename = subject ? `kaoyan-mistakes-${subject}.csv` : 'kaoyan-mistakes.csv';

  reply
    .header('Content-Type', 'text/csv; charset=utf-8')
    .header('Content-Disposition', 'attachment; filename="' + filename + '"');
  return reply.send(csv);
});

  // 列表：可选 subject、mastered、q
  app.get('/api/mistakes', async (request, reply) => {

    const query = request.query as {
      subject?: string;
      mastered?: string;
      q?: string;
    };

    const conditions: string[] = ['user_id = ?'];
    const params: (string | number)[] = [request.user!.id];

    if (query.subject !== undefined && query.subject !== '') {
      if (!isSubjectKey(query.subject)) {
        return reply.code(400).send({ error: '无效的 subject' });
      }
      conditions.push('subject = ?');
      params.push(query.subject);
    }

    if (query.mastered !== undefined && query.mastered !== '') {
      if (query.mastered !== '0' && query.mastered !== '1') {
        return reply.code(400).send({ error: 'mastered 必须为 0 或 1' });
      }
      conditions.push('mastered = ?');
      params.push(query.mastered === '1' ? 1 : 0);
    }

    if (query.q !== undefined && query.q !== '') {
      const like = `%${query.q}%`;
      conditions.push('(title LIKE ? OR content LIKE ?)');
      params.push(like, like);
    }

    const where = ` WHERE ${conditions.join(' AND ')}`;
    const rows = db
      .prepare(`SELECT * FROM mistakes${where} ORDER BY id DESC`)
      .all(...params) as unknown as MistakeRow[];


    return reply.send(rows.map(rowToMistake));
  });

  // 创建
  app.post('/api/mistakes', async (request, reply) => {
    const body = request.body as Partial<CreateMistakeInput> | undefined;
    if (!body || typeof body !== 'object') {
      return reply.code(400).send({ error: '请求体无效' });
    }

    if (!isSubjectKey(body.subject)) {
      return reply.code(400).send({ error: 'subject 非法' });
    }
    if (typeof body.title !== 'string' || body.title.trim() === '') {
      return reply.code(400).send({ error: 'title 不能为空' });
    }

    const title = body.title.trim();
    const content = typeof body.content === 'string' ? body.content : '';
    const analysis = typeof body.analysis === 'string' ? body.analysis : '';
    const createdAt = nowIso();

    const result = db
      .prepare(
        `INSERT INTO mistakes (user_id, subject, title, content, analysis, mastered, created_at)
         VALUES (?, ?, ?, ?, ?, 0, ?)`
      )
      .run(request.user!.id, body.subject, title, content, analysis, createdAt);

    const id = Number(result.lastInsertRowid);
    const row = db
      .prepare('SELECT * FROM mistakes WHERE id = ? AND user_id = ?')
      .get(id, request.user!.id) as unknown as MistakeRow;

    return reply.code(201).send(rowToMistake(row));
  });

  // 更新（逐字段可选）
  app.patch('/api/mistakes/:id', async (request, reply) => {
    const params = request.params as { id: string };
    const id = Number(params.id);
    if (!Number.isInteger(id) || id <= 0) {
      return reply.code(400).send({ error: 'id 非法' });
    }

    const existing = db
      .prepare('SELECT * FROM mistakes WHERE id = ? AND user_id = ?')
      .get(id, request.user!.id) as unknown as MistakeRow | undefined;
    if (!existing) {
      return reply.code(404).send({ error: '错题不存在' });
    }

    const body = request.body as Partial<UpdateMistakeInput> | undefined;
    if (!body || typeof body !== 'object') {
      return reply.code(400).send({ error: '请求体无效' });
    }

    const sets: string[] = [];
    const values: (string | number)[] = [];

    if (body.subject !== undefined) {
      if (!isSubjectKey(body.subject)) {
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
      values.push(body.title.trim());
    }

    if (body.content !== undefined) {
      if (typeof body.content !== 'string') {
        return reply.code(400).send({ error: 'content 非法' });
      }
      sets.push('content = ?');
      values.push(body.content);
    }

    if (body.analysis !== undefined) {
      if (typeof body.analysis !== 'string') {
        return reply.code(400).send({ error: 'analysis 非法' });
      }
      sets.push('analysis = ?');
      values.push(body.analysis);
    }

    if (body.mastered !== undefined) {
      if (typeof body.mastered !== 'boolean') {
        return reply.code(400).send({ error: 'mastered 非法' });
      }
      sets.push('mastered = ?');
      values.push(body.mastered ? 1 : 0);
    }

    if (sets.length > 0) {
      values.push(id);
      values.push(request.user!.id);
      db.prepare(`UPDATE mistakes SET ${sets.join(', ')} WHERE id = ? AND user_id = ?`).run(...values);
    }

    const updated = db
      .prepare('SELECT * FROM mistakes WHERE id = ? AND user_id = ?')
      .get(id, request.user!.id) as unknown as MistakeRow;

    return reply.send(rowToMistake(updated));
  });

  // 删除
  app.delete('/api/mistakes/:id', async (request, reply) => {
    const params = request.params as { id: string };
    const id = Number(params.id);
    if (!Number.isInteger(id) || id <= 0) {
      return reply.code(400).send({ error: 'id 非法' });
    }

    const existing = db
      .prepare('SELECT id FROM mistakes WHERE id = ? AND user_id = ?')
      .get(id, request.user!.id);
    if (!existing) {
      return reply.code(404).send({ error: '错题不存在' });
    }

    db.prepare('DELETE FROM mistakes WHERE id = ? AND user_id = ?').run(id, request.user!.id);
    return reply.send({ ok: true });
  });
  app.get('/api/mistakes/:id/source-exams', async (request, reply) => {
      const rawId = (request.params as { id: string }).id;
      const id = Number(rawId);
      if (!Number.isInteger(id) || id <= 0) {
        return reply.code(400).send({ error: 'id 非法' });
      }

      const rawWindow = (request.query as { windowDays?: string }).windowDays;
      let windowDays = 7;
      if (rawWindow !== undefined) {
        if (!/^-?\d+$/.test(rawWindow)) {
          return reply.code(400).send({ error: 'windowDays 非法' });
        }
        const parsed = Number(rawWindow);
        if (!Number.isInteger(parsed) || parsed < 0 || parsed > 90) {
          return reply.code(400).send({ error: 'windowDays 非法' });
        }
        windowDays = parsed;
      }

      const userId = request.user!.id;
      const mistake = db
      .prepare('SELECT id, user_id, subject, title, content, analysis, mastered, created_at FROM mistakes WHERE id = ? AND user_id = ?')
      .get(id, userId) as MistakeRow | undefined;
      if (!mistake) {
        return reply.code(404).send({ error: '错题不存在' });
      }

      const mistakeDate = mistake.created_at.slice(0, 10);
      const mParts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(mistakeDate);
      if (!mParts) {
        return reply.send([]);
      }
      const mUtc = Date.UTC(Number(mParts[1]), Number(mParts[2]) - 1, Number(mParts[3]));

      const rows = db
      .prepare(
        'SELECT id, user_id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE user_id = ? AND subject = ? ORDER BY taken_at DESC, id DESC',
        )
      .all(userId, mistake.subject) as Array<{
        id: number;
        user_id: number;
        subject: string;
        paper: string;
        score: number;
        total_score: number;
        duration_minutes: number;
        taken_at: string;
      }>;

      const result: ExamRecord[] = [];
      for (const row of rows) {
        const tParts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(row.taken_at);
        if (!tParts) {
          continue;
        }
        const tUtc = Date.UTC(Number(tParts[1]), Number(tParts[2]) - 1, Number(tParts[3]));
        const diffDays = Math.round(Math.abs(tUtc - mUtc) / 86400000);
        if (diffDays > windowDays) {
          continue;
        }
        result.push({
            id: row.id,
            subject: row.subject as ExamRecord['subject'],
            paper: row.paper,
            score: row.score,
            totalScore: row.total_score,
            durationMinutes: row.duration_minutes,
            takenAt: row.taken_at,
          });
      }

      return reply.send(result);
    });

  // 一键组卷：按条件抽取错题（隐藏 analysis）
  app.post('/api/mistakes/quiz/generate', async (request, reply) => {
    const body = request.body as {
      subject?: unknown;
      unmasteredOnly?: unknown;
      from?: unknown;
      to?: unknown;
      limit?: unknown;
    } | undefined;

    if (!body || typeof body !== 'object') {
      return reply.code(400).send({ error: '请求体无效' });
    }

    let subject: string | undefined;
    if (body.subject !== undefined) {
      if (typeof body.subject !== 'string' || !isSubjectKey(body.subject)) {
        return reply.code(400).send({ error: 'subject 非法' });
      }
      subject = body.subject;
    }

    let unmasteredOnly = true;
    if (body.unmasteredOnly !== undefined) {
      if (typeof body.unmasteredOnly !== 'boolean') {
        return reply.code(400).send({ error: 'unmasteredOnly 非法' });
      }
      unmasteredOnly = body.unmasteredOnly;
    }

    let from: string | undefined;
    if (body.from !== undefined) {
      if (!isValidDate(body.from)) {
        return reply.code(400).send({ error: 'from/to 格式非法，应为 YYYY-MM-DD' });
      }
      from = body.from;
    }
    let to: string | undefined;
    if (body.to !== undefined) {
      if (!isValidDate(body.to)) {
        return reply.code(400).send({ error: 'from/to 格式非法，应为 YYYY-MM-DD' });
      }
      to = body.to;
    }
    if (from !== undefined && to !== undefined && from > to) {
      return reply.code(400).send({ error: 'from 不能晚于 to' });
    }

    let limit = 20;
    if (body.limit !== undefined) {
      if (
        typeof body.limit !== 'number' ||
        !Number.isInteger(body.limit) ||
        body.limit < 1 ||
        body.limit > 100
      ) {
        return reply.code(400).send({ error: 'limit 非法' });
      }
      limit = body.limit;
    }

    const conditions: string[] = ['user_id = ?'];
    const params: (string | number)[] = [request.user!.id];

    if (subject !== undefined) {
      conditions.push('subject = ?');
      params.push(subject);
    }
    if (unmasteredOnly) {
      conditions.push('mastered = 0');
    }
    if (from !== undefined) {
      conditions.push('substr(created_at, 1, 10) >= ?');
      params.push(from);
    }
    if (to !== undefined) {
      conditions.push('substr(created_at, 1, 10) <= ?');
      params.push(to);
    }

    params.push(limit);

    const where = ` WHERE ${conditions.join(' AND ')}`;
    const rows = db
      .prepare(
        `SELECT id, subject, title, content, created_at FROM mistakes${where} ORDER BY mastered ASC, id ASC LIMIT ?`
      )
      .all(...params) as unknown as Array<{
        id: number;
        subject: string;
        title: string;
        content: string;
        created_at: string;
      }>;

    const result: QuizItem[] = rows.map((row) => ({
      id: row.id,
      subject: row.subject as QuizItem['subject'],
      title: row.title,
      content: row.content,
      createdAt: row.created_at,
    }));

    return reply.send(result);
  });

  // 批改：回写 mastered，全部校验通过后统一更新
  app.post('/api/mistakes/quiz/grade', async (request, reply) => {
    const body = request.body as { results?: unknown } | undefined;

    if (!body || typeof body !== 'object') {
      return reply.code(400).send({ error: '请求体无效' });
    }

    const rawResults = body.results;
    if (!Array.isArray(rawResults) || rawResults.length === 0) {
      return reply.code(400).send({ error: 'results 不能为空' });
    }
    if (rawResults.length > 200) {
      return reply.code(400).send({ error: 'results 不能超过 200 条' });
    }

    const seen = new Set<number>();
    const items: Array<{ mistakeId: number; correct: boolean }> = [];
    for (const entry of rawResults) {
      if (!entry || typeof entry !== 'object') {
        return reply.code(400).send({ error: 'results 项非法' });
      }
      const item = entry as { mistakeId?: unknown; correct?: unknown };
      if (
        typeof item.mistakeId !== 'number' ||
        !Number.isInteger(item.mistakeId) ||
        item.mistakeId <= 0 ||
        typeof item.correct !== 'boolean'
      ) {
        return reply.code(400).send({ error: 'results 项非法' });
      }
      if (seen.has(item.mistakeId)) {
        return reply.code(400).send({ error: 'mistakeId 不能重复' });
      }
      seen.add(item.mistakeId);
      items.push({ mistakeId: item.mistakeId, correct: item.correct });
    }

    const userId = request.user!.id;
    const existing = new Map<number, number>();
    for (const item of items) {
      const row = db
        .prepare('SELECT id, mastered FROM mistakes WHERE id = ? AND user_id = ?')
        .get(item.mistakeId, userId) as { id: number; mastered: number } | undefined;
      if (!row) {
        return reply.code(404).send({ error: '错题不存在' });
      }
      existing.set(item.mistakeId, row.mastered);
    }

    const updatedIds: number[] = [];
    let correct = 0;
    let wrong = 0;

    for (const item of items) {
      if (item.correct) {
        correct += 1;
      } else {
        wrong += 1;
      }
      const target = item.correct ? 1 : 0;
      const prev = existing.get(item.mistakeId)!;
      if (prev !== target) {
        updatedIds.push(item.mistakeId);
      }
    }

    for (const item of items) {
      const target = item.correct ? 1 : 0;
      db.prepare('UPDATE mistakes SET mastered = ? WHERE id = ? AND user_id = ?').run(
        target,
        item.mistakeId,
        userId
      );
    }

    updatedIds.sort((a, b) => a - b);

    const result: QuizGradeResult = {
      total: items.length,
      correct,
      wrong,
      updatedIds,
    };

    return reply.send(result);
  });
}
