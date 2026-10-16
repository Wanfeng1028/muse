import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import type { SubjectKey, WeeklyStats, HeatmapDay, HeatmapResponse } from '@kaoyan/shared';

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

  // 本周每日专注分钟
  const dayRows = db.prepare(
    `SELECT substr(started_at, 1, 10) AS d, SUM(minutes) AS m FROM focus_sessions WHERE substr(started_at, 1, 10) >= ? AND substr(started_at, 1, 10) < ? GROUP BY d`
  ).all(weekStart, weekEnd) as { d: string; m: number | null }[];
  const dayMap = new Map<string, number>();
  for (const row of dayRows) {
    dayMap.set(row.d, Number(row.m ?? 0));
  }
  const focusMinutesByDay: number[] = [0, 1, 2, 3, 4, 5, 6].map(
    (i) => dayMap.get(addDays(weekStart, i)) ?? 0
  );

  // 连续打卡（与热力图口径一致）
  const streakRows = db.prepare(
    `SELECT substr(started_at, 1, 10) AS d, SUM(minutes) AS m FROM focus_sessions WHERE substr(started_at, 1, 10) >= ? GROUP BY d`
  ).all(addDays(today, -365)) as { d: string; m: number | null }[];
  const activeDays = new Set<string>();
  for (const row of streakRows) {
    if (Number(row.m ?? 0) > 0) activeDays.add(row.d);
  }
  let cursor = activeDays.has(today) ? today : addDays(today, -1);
  let currentStreak = 0;
  while (activeDays.has(cursor)) {
    currentStreak += 1;
    cursor = addDays(cursor, -1);
  }

  // 模考
  const examsTaken = (db.prepare(`SELECT COUNT(*) AS c FROM exam_records WHERE taken_at >= ? AND taken_at < ?`).get(weekStart, weekEnd) as { c: number }).c;

  const stats: WeeklyStats = {
    weekStart, weekEnd, focusMinutes, focusBySubject,
    focusMinutesByDay, currentStreak,
    plansTotal: planRow.total, plansDone: planRow.done,
    wordsTotal, wordsLearned, wordsDue,
    mistakesNew, mistakesUnmastered, examsTaken,
  };
  return reply.send(stats);
  });

  app.get('/api/stats/heatmap', async (request, reply) => {
    const q = (request.query ?? {}) as { months?: string };
    let months = 3;
    if (q.months !== undefined) {
      const n = Number(q.months);
      if (!Number.isInteger(n) || n < 1 || n > 6) {
        return reply.status(400).send({ error: 'months 参数无效' });
      }
      months = n;
    }

    const endDate = todayStr();
    const startDate = addDays(endDate, -(months * 31 - 1));

    const focusRows = db
      .prepare(
        `SELECT substr(started_at, 1, 10) AS d, SUM(minutes) AS m
         FROM focus_sessions
         WHERE substr(started_at, 1, 10) >= ? AND substr(started_at, 1, 10) <= ?
         GROUP BY d`
      )
      .all(startDate, endDate) as { d: string; m: number }[];

    const planRows = db
      .prepare(
        `SELECT date AS d, COUNT(*) AS total, SUM(CASE WHEN done = 1 THEN 1 ELSE 0 END) AS doneCnt
         FROM plans
         WHERE date >= ? AND date <= ?
         GROUP BY d`
      )
      .all(startDate, endDate) as { d: string; total: number; doneCnt: number }[];

    const mistakeRows = db
      .prepare(
        `SELECT substr(created_at, 1, 10) AS d, COUNT(*) AS c
         FROM mistakes
         WHERE substr(created_at, 1, 10) >= ? AND substr(created_at, 1, 10) <= ?
         GROUP BY d`
      )
      .all(startDate, endDate) as { d: string; c: number }[];

    const examRows = db
      .prepare(
        `SELECT substr(taken_at, 1, 10) AS d, COUNT(*) AS c
         FROM exam_records
         WHERE substr(taken_at, 1, 10) >= ? AND substr(taken_at, 1, 10) <= ?
         GROUP BY d`
      )
      .all(startDate, endDate) as { d: string; c: number }[];

    const focusMap = new Map<string, number>();
    for (const r of focusRows) focusMap.set(r.d, Number(r.m ?? 0));
    const planTotalMap = new Map<string, number>();
    const planDoneMap = new Map<string, number>();
    for (const r of planRows) {
      planTotalMap.set(r.d, Number(r.total ?? 0));
      planDoneMap.set(r.d, Number(r.doneCnt ?? 0));
    }
    const mistakeMap = new Map<string, number>();
    for (const r of mistakeRows) mistakeMap.set(r.d, Number(r.c ?? 0));
    const examMap = new Map<string, number>();
    for (const r of examRows) examMap.set(r.d, Number(r.c ?? 0));

    const days: HeatmapDay[] = [];
    const totalDays = months * 31;
    for (let i = 0; i < totalDays; i++) {
      const date = addDays(startDate, i);
      days.push({
        date,
        focusMinutes: focusMap.get(date) ?? 0,
        plansTotal: planTotalMap.get(date) ?? 0,
        plansDone: planDoneMap.get(date) ?? 0,
        mistakesNew: mistakeMap.get(date) ?? 0,
        examsTaken: examMap.get(date) ?? 0,
      });
    }

    const activeDays = days.filter((d) => d.focusMinutes > 0).length;

    let currentStreak = 0;
    {
      const todayIdx = days.length - 1;
      let i = todayIdx;
      if (i >= 0 && days[i].focusMinutes <= 0) i--;
      while (i >= 0 && days[i].focusMinutes > 0) {
        currentStreak++;
        i--;
      }
    }

    let bestStreak = 0;
    {
      let run = 0;
      for (const d of days) {
        if (d.focusMinutes > 0) {
          run++;
          if (run > bestStreak) bestStreak = run;
        } else {
          run = 0;
        }
      }
    }

    const resp: HeatmapResponse = {
      months,
      startDate,
      endDate,
      days,
      currentStreak,
      bestStreak,
      activeDays,
    };
    return reply.send(resp);
  });
}

