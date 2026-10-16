import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import type { SubjectKey, WeeklyStats } from '@kaoyan/shared';
import { todayStr, addDays } from '../db';

export function registerStatsRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // GET /api/stats/weekly?start=YYYY-MM-DD（可选，缺省为本周一）
  app.get<{ Querystring: { start?: string } }>('/api/stats/weekly', async (request, reply) => {
    let weekStart: string;
    const q = request.query.start;
    if (q === undefined) {
      const dow = (new Date().getDay() + 6) % 7; // 周一=0
      weekStart = addDays(todayStr(), -dow);
    } else {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(q)) return reply.code(400).send({ error: 'start 日期格式无效' });
      const dt = new Date(q + 'T00:00:00');
      if (Number.isNaN(dt.getTime())) return reply.code(400).send({ error: 'start 日期无效' });
      weekStart = q;
    }
    const weekEnd = addDays(weekStart, 7);
    const weekEndDate = addDays(weekStart, 6);
    const today = todayStr();

    // 专注：按科目汇总
    const focusRows = db.prepare(
      `SELECT subject, SUM(minutes) AS minutes FROM focus_sessions WHERE started_at >= ? AND started_at < ? GROUP BY subject`
    ).all(weekStart, weekEnd) as Array<{ subject: string; minutes: number }>;
    const focusBySubject: Record<SubjectKey, number> = { math: 0, english: 0, politics: 0, major: 0 };
    let focusMinutes = 0;
    for (const r of focusRows) {
      const m = r.minutes ?? 0;
      focusMinutes += m;
      if (r.subject === 'math' || r.subject === 'english' || r.subject === 'politics' || r.subject === 'major') {
        focusBySubject[r.subject] = m;
      }
    }

    // 计划
    const planRow = db.prepare(
      `SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done FROM plans WHERE date >= ? AND date <= ?`
    ).get(weekStart, weekEndDate) as { total: number; done: number };

    // 单词
    const wordsTotal = (db.prepare(`SELECT COUNT(*) AS c FROM words`).get() as { c: number }).c;
    const wordsLearned = (db.prepare(`SELECT COUNT(*) AS c FROM srs_state WHERE repetitions > 0`).get() as { c: number }).c;
    const wordsDue = (db.prepare(`SELECT COUNT(*) AS c FROM srs_state WHERE due_date <= ?`).get(today) as { c: number }).c;

    // 错题
    const mistakesNew = (db.prepare(`SELECT COUNT(*) AS c FROM mistakes WHERE created_at >= ?`).get(weekStart) as { c: number }).c;
    const mistakesUnmastered = (db.prepare(`SELECT COUNT(*) AS c FROM mistakes WHERE mastered = 0`).get() as { c: number }).c;

    // 模考
    const examsTaken = (db.prepare(`SELECT COUNT(*) AS c FROM exam_records WHERE taken_at >= ? AND taken_at < ?`).get(weekStart, weekEnd) as { c: number }).c;

    const stats: WeeklyStats = {
      weekStart, weekEnd, focusMinutes, focusBySubject,
      plansTotal: planRow.total, plansDone: planRow.done,
      wordsTotal, wordsLearned, wordsDue,
      mistakesNew, mistakesUnmastered, examsTaken,
    };
    return reply.send(stats);
  });
}
