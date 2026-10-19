import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import {
  isSubjectKey,
  type Mistake,
  type CreateMistakeInput,
  type UpdateMistakeInput,
  type MistakeSummary,
  type ExamRecord,
} from '@kaoyan/shared';

import { nowIso } from '../db';

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
}
