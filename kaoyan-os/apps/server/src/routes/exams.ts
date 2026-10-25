import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import {
  SUBJECTS,
  isSubjectKey,
  type CreateExamInput,
  type ExamRecord,
  type ExamTrendPoint,
  type ExamSummary,
  type ExamSubjectSummary,
  type ExamsBySubjectResponse,
  type Mistake,
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
    const params: (string | number)[] = [req.user!.id];
    let sql = 'SELECT id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE user_id = ?';

    if (query.subject !== undefined) {
      if (!isSubjectKey(query.subject)) {
        return reply.code(400).send({ error: '无效的 subject 参数' });
      }
      sql += ' AND subject = ?';
      params.push(query.subject);
    }

    sql += ' ORDER BY taken_at DESC, id DESC';
    const rows = db.prepare(sql).all(...params) as unknown as ExamRow[];
    return rows.map(mapExam);
  });

  // GET /api/exams/trend - 按 taken_at 升序返回趋势点
  app.get('/api/exams/trend', async (req, reply) => {
    const query = req.query as { subject?: string };
    const params: (string | number)[] = [req.user!.id];
    let sql = 'SELECT id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE user_id = ?';

    if (query.subject !== undefined) {
      if (!isSubjectKey(query.subject)) {
        return reply.code(400).send({ error: '无效的 subject 参数' });
      }
      sql += ' AND subject = ?';
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
    const query = req.query as { subject?: string };
    const params: (string | number)[] = [req.user!.id];
    let sql = 'SELECT id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE user_id = ?';

    if (query.subject !== undefined) {
      if (!isSubjectKey(query.subject)) {
        return reply.code(400).send({ error: '无效的 subject 参数' });
      }
      sql += ' AND subject = ?';
      params.push(query.subject);
    }

    sql += ' ORDER BY taken_at ASC, id ASC';
    const rows = db.prepare(sql).all(...params) as unknown as ExamRow[];

    const subject = query.subject !== undefined ? query.subject : null;

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
    // avgRate 为“加权得分率”（总分之和 / 满分之和），与单场 rate 含义不同
    const avgRate = totalFullSum > 0 ? Math.round((totalScoreSum / totalFullSum) * 10000) / 10000 : 0;

    // 最高分：rows 已按 taken_at ASC, id ASC 排序，保留第一个达到最大分的即为“并列取最早”
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


  // GET /api/exams/summary/by-subject - 真题分科汇总：仅返回有记录的科目，按 SUBJECTS 顺序排列
  app.get('/api/exams/summary/by-subject', async (req, reply) => {
    const rows = db.prepare('SELECT id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE user_id = ? ORDER BY taken_at ASC, id ASC').all(req.user!.id) as unknown as ExamRow[];

    const grouped = new Map<string, ExamRow[]>();
    for (const row of rows) {
      const arr = grouped.get(row.subject);
      if (arr) {
        arr.push(row);
      } else {
        grouped.set(row.subject, [row]);
      }
    }

    const subjects: ExamSubjectSummary[] = [];
    for (const s of SUBJECTS) {
      const group = grouped.get(s.key);
      if (!group) continue;

      const count = group.length;
      const scoreSum = group.reduce((sum, r) => sum + r.score, 0);
      const totalScoreSum = group.reduce((sum, r) => sum + r.total_score, 0);
      const avgScore = Math.round((scoreSum / count) * 10) / 10;
      const avgRate = totalScoreSum > 0 ? Math.round((scoreSum / totalScoreSum) * 10000) / 10000 : 0;

      const first = group[0];
      const latest = group[count - 1];
      let best = group[0];
      for (let i = 1; i < count; i++) {
        if (group[i].score > best.score) {
          best = group[i];
        }
      }

      const improvement = count < 2 ? 0 : latest.score - first.score;

      subjects.push({
        subject: s.key,
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
      });
    }

    return reply.send({ subjects });
  });

  // GET /api/exams/export - 导出考试记录为 CSV
  app.get('/api/exams/export', async (req, reply) => {
    const query = req.query as { subject?: string };
    const params: (string | number)[] = [req.user!.id];
    let sql = 'SELECT id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE user_id = ?';

    if (query.subject !== undefined) {
      if (!isSubjectKey(query.subject)) {
        return reply.code(400).send({ error: '无效的 subject 参数' });
      }
      sql += ' AND subject = ?';
      params.push(query.subject);
    }

    sql += ' ORDER BY taken_at ASC, id ASC';
    const rows = db.prepare(sql).all(...params) as unknown as ExamRow[];

    const escapeField = (value: string): string => {
      if (/[",\r\n]/.test(value)) {
        return '"' + value.replace(/"/g, '""') + '"';
      }
      return value;
    };

    const lines: string[] = [];
    lines.push(
      ['id', 'subject', 'subject_name', 'paper', 'score', 'total_score', 'rate', 'duration_minutes', 'taken_at'].join(',')
    );

    for (const row of rows) {
      const rate =
        row.total_score > 0
          ? Math.round((row.score / row.total_score) * 10000) / 10000
          : 0;
      const subjectName =
        SUBJECTS.find((s) => s.key === row.subject)?.name ?? row.subject;
      const fields = [
        String(row.id),
        row.subject,
        subjectName,
        row.paper,
        String(row.score),
        String(row.total_score),
        String(rate),
        String(row.duration_minutes),
        row.taken_at,
      ];
      lines.push(fields.map(escapeField).join(','));
    }

    const csv = '\ufeff' + lines.join('\n') + '\n';

    const filename = query.subject !== undefined
      ? `kaoyan-exams-${query.subject}.csv`
      : 'kaoyan-exams.csv';
    reply
      .header('Content-Type', 'text/csv; charset=utf-8')
      .header('Content-Disposition', `attachment; filename="${filename}"`);


    return reply.send(csv);
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
        'INSERT INTO exam_records (user_id, subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
      )
      .run(req.user!.id, subject, paper, score, totalScore, duration, taken);

    const id = Number(result.lastInsertRowid);

    const row = db
      .prepare(
        'SELECT id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE id = ? AND user_id = ?'
      )
      .get(id, req.user!.id) as unknown as ExamRow | undefined;

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

    const result = db
      .prepare('DELETE FROM exam_records WHERE id = ? AND user_id = ?')
      .run(id, req.user!.id);

    if (Number(result.changes) === 0) {
      return reply.code(404).send({ error: '记录不存在' });
    }

    return reply.send({ ok: true });
  });
  app.get('/api/exams/:id/related-mistakes', async (request, reply) => {
      const rawId = (request.params as { id: string }).id;
      const id = Number(rawId);
      if (!Number.isInteger(id) || id <= 0) {
        return reply.code(400).send({ error: '无效的 id' });
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
      const exam = db
      .prepare('SELECT id, user_id, subject, paper, score, total_score, duration_minutes, taken_at FROM exam_records WHERE id = ? AND user_id = ?')
      .get(id, userId) as ExamRow | undefined;
      if (!exam) {
        return reply.code(404).send({ error: '记录不存在' });
      }

      const eParts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(exam.taken_at);
      if (!eParts) {
        return reply.code(400).send({ error: 'takenAt 非法' });
      }
      const eUtc = Date.UTC(Number(eParts[1]), Number(eParts[2]) - 1, Number(eParts[3]));

      const rows = db
      .prepare('SELECT id, user_id, subject, title, content, analysis, mastered, created_at FROM mistakes WHERE user_id = ? AND subject = ? ORDER BY created_at DESC, id DESC')
      .all(userId, exam.subject) as Array<{
        id: number;
        user_id: number;
        subject: string;
        title: string;
        content: string;
        analysis: string;
        mastered: number;
        created_at: string;
      }>;

      const result: Mistake[] = [];
      for (const row of rows) {
        const cDate = row.created_at.slice(0, 10);
        const cParts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(cDate);
        if (!cParts) {
          continue;
        }
        const cUtc = Date.UTC(Number(cParts[1]), Number(cParts[2]) - 1, Number(cParts[3]));
        const diffDays = Math.round(Math.abs(cUtc - eUtc) / 86400000);
        if (diffDays > windowDays) {
          continue;
        }
        result.push({
            id: row.id,
            subject: row.subject as Mistake['subject'],
            title: row.title,
            content: row.content,
            analysis: row.analysis,
            mastered: row.mastered === 1,
            createdAt: row.created_at,
          });
      }

      return reply.send(result);
    });
}
