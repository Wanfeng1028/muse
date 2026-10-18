import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerStatsRoutes } from '../src/routes/stats';
import { todayStr, addDays } from '../src/db';

function createDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:');
  db.exec(`
    CREATE TABLE focus_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, minutes INTEGER NOT NULL, started_at TEXT NOT NULL);
    CREATE TABLE plans (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE words (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL);
    CREATE TABLE srs_state (word_id INTEGER PRIMARY KEY, repetitions INTEGER NOT NULL DEFAULT 0, due_date TEXT NOT NULL);
    CREATE TABLE mistakes (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, mastered INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE exam_records (id INTEGER PRIMARY KEY AUTOINCREMENT, taken_at TEXT NOT NULL);
  `);
  return db;
}

async function buildApp(db: DatabaseSync): Promise<FastifyInstance> {
  const app = Fastify();
  registerStatsRoutes(app, db);
  await app.ready();
  return app;
}

// 本周一（本地时区，与 stats.ts 中算法一致）
function thisMonday(): string {
  const dow = (new Date().getDay() + 6) % 7;
  return addDays(todayStr(), -dow);
}

describe('stats r3 深测', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;

  beforeAll(async () => {
    db = createDb();
    app = await buildApp(db);
  });

  afterAll(async () => {
    await app.close();
    db.close();
  });

  beforeEach(() => {
    db.exec('DELETE FROM focus_sessions');
    db.exec('DELETE FROM plans');
    db.exec('DELETE FROM words');
    db.exec('DELETE FROM srs_state');
    db.exec('DELETE FROM mistakes');
    db.exec('DELETE FROM exam_records');
  });

  it('weekly start 参数校验：格式不符返回 400，日历不存在日期按源码语义透传', async () => {

    const r1 = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=2024-1-1' });
    expect(r1.statusCode).toBe(400);
    expect(r1.json().error).toBe('start 日期格式无效');

    const r2 = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=2024-13-01' });
    expect(r2.statusCode).toBe(400);
    expect(r2.json().error).toBe('start 日期无效');

    // '2024-02-30' 能通过正则且 new Date 不返回 NaN（JS 自动进位到 2024-03-01），故接口返回 200
    // 这是源码当前行为（只拒绝 NaN），测试如实记录
    const r3 = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=2024-02-30' });
    expect(r3.statusCode).toBe(200);
    expect(r3.json().weekStart).toBe('2024-02-30');

  });

  it('weekly 周区间开闭语义：[weekStart, weekEnd) 左闭右开，weekEndDate 23:59 计入', async () => {
    const weekStart = '2024-03-04'; // 周一
    const weekEnd = addDays(weekStart, 7); // 2024-03-11 周一 00:00
    const weekEndDate = addDays(weekStart, 6); // 2024-03-10 周日

    db.prepare(`INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`).run(
      'math', 60, `${weekEnd} 00:00:00`
    );
    db.prepare(`INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`).run(
      'math', 30, `${weekEndDate} 23:59:00`
    );
    // 边界前一刻：weekStart 当天 00:00:00 应计入
    db.prepare(`INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`).run(
      'english', 15, `${weekStart} 00:00:00`
    );

    const res = await app.inject({ method: 'GET', url: `/api/stats/weekly?start=${weekStart}` });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.weekStart).toBe(weekStart);
    expect(body.weekEnd).toBe(weekEnd);
    // weekEnd 的记录不计入；weekStart 00:00 与 weekEndDate 23:59 均计入
    expect(body.focusMinutes).toBe(45);
    expect(body.focusBySubject.math).toBe(30);
    expect(body.focusBySubject.english).toBe(15);
  });

  it('weekly focusBySubject：非法科目记录计入总数但不落入四个合法科目', async () => {
    const weekStart = thisMonday();
    db.prepare(`INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`).run(
      'art', 25, `${weekStart} 10:00:00`
    );
    db.prepare(`INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`).run(
      'math', 40, `${weekStart} 11:00:00`
    );

    const res = await app.inject({ method: 'GET', url: `/api/stats/weekly?start=${weekStart}` });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.focusMinutes).toBe(65);
    expect(body.focusBySubject.math).toBe(40);
    expect(body.focusBySubject.english).toBe(0);
    expect(body.focusBySubject.politics).toBe(0);
    expect(body.focusBySubject.major).toBe(0);
    // art 不应出现在 focusBySubject 的任何键上
    expect(Object.keys(body.focusBySubject).sort()).toEqual(['english', 'major', 'math', 'politics']);
  });

  it('weekly plans 跨周边界：[weekStart, weekEndDate] 闭区间', async () => {
    const weekStart = '2024-03-04';
    const weekEndDate = addDays(weekStart, 6); // 2024-03-10
    const before = addDays(weekStart, -1); // 2024-03-03

    db.prepare(`INSERT INTO plans (date, done) VALUES (?, ?)`).run(before, 1);
    db.prepare(`INSERT INTO plans (date, done) VALUES (?, ?)`).run(weekStart, 1);
    db.prepare(`INSERT INTO plans (date, done) VALUES (?, ?)`).run(weekEndDate, 0);
    // weekEnd（下周一）的计划不计入
    db.prepare(`INSERT INTO plans (date, done) VALUES (?, ?)`).run(addDays(weekStart, 7), 1);

    const res = await app.inject({ method: 'GET', url: `/api/stats/weekly?start=${weekStart}` });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.plansTotal).toBe(2);
    expect(body.plansDone).toBe(1);
  });

  it('weekly wordsDue/wordsLearned：due_date<=today 计入 due，repetitions>0 才计入 learned', async () => {
    const today = todayStr();
    const tomorrow = addDays(today, 1);

    db.prepare(`INSERT INTO words (text) VALUES (?)`).run('w1');
    db.prepare(`INSERT INTO words (text) VALUES (?)`).run('w2');
    db.prepare(`INSERT INTO words (text) VALUES (?)`).run('w3');

    // 今天到期，已学过
    db.prepare(`INSERT INTO srs_state (word_id, repetitions, due_date) VALUES (?, ?, ?)`).run(1, 3, today);
    // 明天到期，已学过 → 不计入 due
    db.prepare(`INSERT INTO srs_state (word_id, repetitions, due_date) VALUES (?, ?, ?)`).run(2, 1, tomorrow);
    // 今天到期，但 repetitions=0 → 不计入 learned
    db.prepare(`INSERT INTO srs_state (word_id, repetitions, due_date) VALUES (?, ?, ?)`).run(3, 0, today);

    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.wordsTotal).toBe(3);
    expect(body.wordsLearned).toBe(2); // word 1 和 2
    expect(body.wordsDue).toBe(2); // word 1 和 3
  });

  it('weekly mistakesNew 只计 created_at>=weekStart；mistakesUnmastered 计全库 mastered=0', async () => {
    const weekStart = '2024-03-04';
    const before = addDays(weekStart, -1);

    // 上周创建的未掌握错题：不计入 mistakesNew，但计入 mistakesUnmastered
    db.prepare(`INSERT INTO mistakes (created_at, mastered) VALUES (?, ?)`).run(`${before} 12:00:00`, 0);
    // 本周创建、已掌握：计入 mistakesNew，不计入 unmastered
    db.prepare(`INSERT INTO mistakes (created_at, mastered) VALUES (?, ?)`).run(`${weekStart} 00:00:00`, 1);
    // 本周创建、未掌握：两处都计入
    db.prepare(`INSERT INTO mistakes (created_at, mastered) VALUES (?, ?)`).run(`${addDays(weekStart, 3)} 08:00:00`, 0);

    const res = await app.inject({ method: 'GET', url: `/api/stats/weekly?start=${weekStart}` });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.mistakesNew).toBe(2);
    expect(body.mistakesUnmastered).toBe(2);
  });

  it('weekly currentStreak：今天无记录时从昨天起算，补今天后含今天', async () => {
    const today = todayStr();
    const yesterday = addDays(today, -1);
    const twoDaysAgo = addDays(today, -2);

    // 前天、昨天有记录，今天无
    db.prepare(`INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`).run('math', 10, `${twoDaysAgo} 10:00:00`);
    db.prepare(`INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`).run('math', 10, `${yesterday} 10:00:00`);

    const res1 = await app.inject({ method: 'GET', url: '/api/stats/weekly' });
    expect(res1.statusCode).toBe(200);
    expect(res1.json().currentStreak).toBe(2);

    // 补今天一条
    db.prepare(`INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`).run('math', 10, `${today} 09:00:00`);
    const res2 = await app.inject({ method: 'GET', url: '/api/stats/weekly' });
    expect(res2.statusCode).toBe(200);
    expect(res2.json().currentStreak).toBe(3);
  });

  it('heatmap months 参数：合法值决定窗口长度，越界与非法值返回 400，缺省为 3 个月', async () => {
    const today = todayStr();

    const r6 = await app.inject({ method: 'GET', url: '/api/stats/heatmap?months=6' });
    expect(r6.statusCode).toBe(200);
    const b6 = r6.json();
    expect(b6.months).toBe(6);
    expect(b6.days.length).toBe(186);
    expect(b6.endDate).toBe(today);
    expect(b6.startDate).toBe(addDays(today, -185));
    expect(b6.days[0].date).toBe(addDays(today, -185));
    expect(b6.days[185].date).toBe(today);

    for (const bad of ['0', '7', 'abc', '2.5']) {
      const r = await app.inject({ method: 'GET', url: `/api/stats/heatmap?months=${bad}` });
      expect(r.statusCode).toBe(400);
      expect(r.json().error).toBe('months 参数无效');
    }

    const rDef = await app.inject({ method: 'GET', url: '/api/stats/heatmap' });
    expect(rDef.statusCode).toBe(200);
    const bDef = rDef.json();
    expect(bDef.months).toBe(3);
    expect(bDef.days.length).toBe(93);
    expect(bDef.startDate).toBe(addDays(today, -92));
  });

  it('heatmap streak 口径：窗口内 5 连 + 断 1 天 + 2 连，bestStreak=5、currentStreak=2、activeDays=7', async () => {
    const today = todayStr();
    // 让 2 连的结尾正好落在今天
    const d0 = today;          // 今天
    const d1 = addDays(today, -1); // 昨天
    const d2 = addDays(today, -2); // 断点（无记录）
    const d3 = addDays(today, -3); // 5 连末尾
    const d4 = addDays(today, -4);
    const d5 = addDays(today, -5);
    const d6 = addDays(today, -6);
    const d7 = addDays(today, -7); // 5 连开头

    const insert = db.prepare(`INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`);
    for (const d of [d0, d1, d3, d4, d5, d6, d7]) {
      insert.run('math', 5, `${d} 12:00:00`);
    }
    // d2 无记录，形成断裂

    const res = await app.inject({ method: 'GET', url: '/api/stats/heatmap?months=3' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.bestStreak).toBe(5);
    expect(body.currentStreak).toBe(2);
    expect(body.activeDays).toBe(7);
  });

  it('heatmap 多源归集：同一天 focus/plans/mistakes/exam 各一，字段精确，其余天为 0', async () => {
    const today = todayStr();

    db.prepare(`INSERT INTO focus_sessions (subject, minutes, started_at) VALUES (?, ?, ?)`).run('math', 42, `${today} 08:00:00`);
    db.prepare(`INSERT INTO plans (date, done) VALUES (?, ?)`).run(today, 1);
    db.prepare(`INSERT INTO mistakes (created_at, mastered) VALUES (?, ?)`).run(`${today} 09:00:00`, 0);
    db.prepare(`INSERT INTO exam_records (taken_at) VALUES (?)`).run(`${today} 14:00:00`);

    const res = await app.inject({ method: 'GET', url: '/api/stats/heatmap?months=3' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    const day = body.days.find((d: { date: string }) => d.date === today);
    expect(day).toBeTruthy();
    expect(day.focusMinutes).toBe(42);
    expect(day.plansTotal).toBe(1);
    expect(day.plansDone).toBe(1);
    expect(day.mistakesNew).toBe(1);
    expect(day.examsTaken).toBe(1);

    const yesterday = addDays(today, -1);
    const y = body.days.find((d: { date: string }) => d.date === yesterday);
    expect(y.focusMinutes).toBe(0);
    expect(y.plansTotal).toBe(0);
    expect(y.plansDone).toBe(0);
    expect(y.mistakesNew).toBe(0);
    expect(y.examsTaken).toBe(0);

    // 窗口最后一天应为今天
    expect(body.days[body.days.length - 1].date).toBe(today);
  });

  it('weekly examsTaken 只计 taken_at 落在 [weekStart, weekEnd) 的模考记录', async () => {
    const weekStart = '2024-03-04';
    const weekEnd = addDays(weekStart, 7); // 2024-03-11
    const weekEndDate = addDays(weekStart, 6); // 2024-03-10

    const ins = db.prepare(`INSERT INTO exam_records (taken_at) VALUES (?)`);
    ins.run(`${addDays(weekStart, -1)} 23:59:00`); // 上周日：不计
    ins.run(`${weekStart} 00:00:00`);              // 本周起点：计
    ins.run(`${weekEndDate} 23:59:00`);            // 本周日末：计
    ins.run(`${weekEnd} 00:00:00`);                // 下周一 00:00：不计

    const res = await app.inject({ method: 'GET', url: `/api/stats/weekly?start=${weekStart}` });
    expect(res.statusCode).toBe(200);
    expect(res.json().examsTaken).toBe(2);
  });
});
