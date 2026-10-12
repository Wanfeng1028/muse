import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import {
  isSubjectKey,
  type CreateExamInput,
  type ExamRecord,
  type ExamTrendPoint,
} from '@kaoyan/shared';
import { todayStr } from '../db';

// 数据库行类型
interface ExamRow {
  id: number;
  subject: string;
  paper: string;
  score: number;
  total_score: number;
  duration_minutes: number;
  taken_at: string;
}

// 将数据库行映射为 ExamRecord
function mapExam(row: ExamRow): ExamRecord {
  return {
    id: row.id,
    subject: row.subject as ExamRecord['subject'],
    paper: row.paper,
    score: row.score,
    totalScore: row.total_score,
    durationMinutes: row.duration_minutes,
    takenAt: row.taken_at,
  };
}

export function registerExamsRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // GET /api/exams - 按 taken_at 降序、id 降序返回考试记录
  app.get('/api/exams', async (req, reply) => {
    const query = req.query as { subject?: string };
    const params: string[] = [];
    let sql = 'SELECT id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records';

    if (query.subject !== undefined) {
      if (!isSubjectKey(query.subject)) {
        return reply.code(400).send({ error: '无效的 subject 参数' });
      }
      sql += ' WHERE subject = ?';
      params.push(query.subject);
    }

    sql += ' ORDER BY taken_at DESC, id DESC';
    const rows = db.prepare(sql).all(...params) as unknown as ExamRow[];
    return rows.map(mapExam);
  });

  // GET /api/exams/trend - 按 taken_at 升序返回趋势点
  app.get('/api/exams/trend', async (req, reply) => {
    const query = req.query as { subject?: string };
    const params: string[] = [];
    let sql = 'SELECT id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records';

    if (query.subject !== undefined) {
      if (!isSubjectKey(query.subject)) {
        return reply.code(400).send({ error: '无效的 subject 参数' });
      }
      sql += ' WHERE subject = ?';
      params.push(query.subject);
    }

    sql += ' ORDER BY taken_at ASC, id ASC';
    const rows = db.prepare(sql).all(...params) as unknown as ExamRow[];

    const points: ExamTrendPoint[] = rows.map((row) => {
      const rate =
        row.total_score > 0
          ? Math.round((row.score / row.total_score) * 10000) / 10000
          : 0;
      return {
        takenAt: row.taken_at,
        paper: row.paper,
        score: row.score,
        totalScore: row.total_score,
        rate,
      };
    });

    return points;
  });

  // POST /api/exams - 创建考试记录
  app.post('/api/exams', async (req, reply) => {
    const body = req.body as Partial<CreateExamInput> | undefined;

    if (!body || typeof body !== 'object') {
      return reply.code(400).send({ error: '请求体不能为空' });
    }

    const { subject, paper, score, totalScore, durationMinutes, takenAt } = body;

    if (!isSubjectKey(subject)) {
      return reply.code(400).send({ error: '无效的 subject' });
    }

    if (typeof paper !== 'string' || paper.trim() === '') {
      return reply.code(400).send({ error: 'paper 不能为空' });
    }

    if (typeof totalScore !== 'number' || !Number.isFinite(totalScore) || totalScore <= 0) {
      return reply.code(400).send({ error: 'totalScore 必须大于 0' });
    }

    if (
      typeof score !== 'number' ||
      !Number.isFinite(score) ||
      score < 0 ||
      score > totalScore
    ) {
      return reply.code(400).send({ error: 'score 必须在 0 到 totalScore 之间' });
    }

    let duration = 0;
    if (durationMinutes !== undefined && durationMinutes !== null) {
      if (
        typeof durationMinutes !== 'number' ||
        !Number.isFinite(durationMinutes) ||
        durationMinutes < 0
      ) {
        return reply.code(400).send({ error: 'durationMinutes 必须大于等于 0' });
      }
      duration = Math.floor(durationMinutes);
    }

    let taken = todayStr();
    if (takenAt !== undefined && takenAt !== null) {
      if (typeof takenAt !== 'string' || takenAt.trim() === '') {
        return reply.code(400).send({ error: 'takenAt 无效' });
      }
      taken = takenAt;
    }

    const result = db
      .prepare(
        'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
      )
      .run(subject, paper, score, totalScore, duration, taken);

    const id = Number(result.lastInsertRowid);

    const row = db
      .prepare(
        'SELECT id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE id = ?'
      )
      .get(id) as unknown as ExamRow | undefined;

    if (!row) {
      return reply.code(500).send({ error: '创建失败' });
    }

    return reply.code(201).send(mapExam(row));
  });

  // DELETE /api/exams/:id - 删除考试记录
  app.delete('/api/exams/:id', async (req, reply) => {
    const params = req.params as { id: string };
    const id = Number(params.id);

    if (!Number.isInteger(id) || id <= 0) {
      return reply.code(400).send({ error: '无效的 id' });
    }

    const existing = db
      .prepare('SELECT id FROM exam_records WHERE id = ?')
      .get(id) as unknown as { id: number } | undefined;

    if (!existing) {
      return reply.code(404).send({ error: '记录不存在' });
    }

    db.prepare('DELETE FROM exam_records WHERE id = ?').run(id);

    return reply.send({ ok: true });
  });
}
