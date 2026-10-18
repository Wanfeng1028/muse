import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import {
isSubjectKey,
type CreateExamInput,
type ExamRecord,
type ExamTrendPoint,
type ExamSummary,
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

// GET /api/exams/summary - 真题汇总统计
app.get('/api/exams/summary', async (req, reply) => {
const query = req.query as { subject?: string};
const params: string[] = [];
let sql = 'SELECT id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records';

if (query.subject!== undefined) {
if (!isSubjectKey(query.subject)) {
return reply.code(400).send({ error: '无效的 subject 参数'});
}
sql += ' WHERE subject =?';
params.push(query.subject);
}

sql += ' ORDER BY taken_at ASC, id ASC';
const rows = db.prepare(sql).all(...params) as unknown as ExamRow[];

const subject = query.subject!== undefined ? query.subject : null;

if (rows.length === 0) {
const empty: ExamSummary = {
subject,
count: 0,
avgScore: 0,
avgRate: 0,
bestScore: 0,
bestTakenAt: '',
latestScore: 0,
latestTakenAt: '',
firstScore: 0,
firstTakenAt: '',
improvement: 0,
};
return empty;
}

const count = rows.length;
const totalScoreSum = rows.reduce((sum, row) => sum + row.score, 0);
const totalFullSum = rows.reduce((sum, row) => sum + row.total_score, 0);
const avgScore = Math.round((totalScoreSum / count) * 10) / 10;
const avgRate = totalFullSum > 0 ? Math.round((totalScoreSum / totalFullSum) * 10000) / 10000 : 0;

// 最高分：并列取最早的一场（taken_at 最早，并列取 id 最小）
let best = rows[0];
for (const row of rows) {
if (row.score > best.score) {
best = row;
}
}

// 最早一场：taken_at 最早，并列取 id 最小
let first = rows[0];
for (const row of rows) {
if (row.taken_at < first.taken_at || (row.taken_at === first.taken_at && row.id < first.id)) {
first = row;
}
}

// 最近一场：taken_at 最晚，并列取 id 最大
let latest = rows[0];
for (const row of rows) {
if (row.taken_at > latest.taken_at || (row.taken_at === latest.taken_at && row.id > latest.id)) {
latest = row;
}
}

const improvement = count < 2 ? 0 : latest.score - first.score;

const summary: ExamSummary = {
subject,
count,
avgScore,
avgRate,
bestScore: best.score,
bestTakenAt: best.taken_at,
latestScore: latest.score,
latestTakenAt: latest.taken_at,
firstScore: first.score,
firstTakenAt: first.taken_at,
improvement,
};

return summary;
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
