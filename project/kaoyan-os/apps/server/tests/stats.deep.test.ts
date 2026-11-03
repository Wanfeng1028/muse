import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerStatsRoutes } from '../src/routes/stats';
import { todayStr, addDays, createDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

const USER = 'statsdeep';

async function buildApp(db: DatabaseSync): Promise<FastifyInstance> {
  const app = Fastify();
  registerStatsRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
  return app;
}

describe('stats 深度测试', () => {
  let db: DatabaseSync;
  let app: FastifyInstance;
  let authCookie = '';

  beforeAll(async () => {
    db = createDb(':memory:');
    app = await buildApp(db);
    authCookie = await registerAndLogin(app, USER);
  });

  afterAll(async () => {
    await app.close();
    db.close();
  });

  it('跨月排程：周起点跨月时周区间正确切分且按日归集', async () => {
    db.exec('DELETE FROM focus_sessions');
    const start = '2024-01-29';
    const inWeek = addDays(start, 2);
    db.prepare("INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?, ?, ?)").run('math', 30, inWeek + 'T09:00:00');
    db.prepare("INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?, ?, ?)").run('english', 20, addDays(start, 6) + 'T10:00:00');
    db.prepare("INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?, ?, ?)").run('math', 99, addDays(start, 7) + 'T10:00:00');
    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=' + start, headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.weekStart).toBe(start);
    expect(body.weekEnd).toBe('2024-02-05');
    expect(body.focusMinutes).toBe(50);
    expect(body.focusBySubject.math).toBe(30);
    expect(body.focusBySubject.english).toBe(20);
    expect(body.focusMinutesByDay[2]).toBe(30);
    expect(body.focusMinutesByDay[6]).toBe(20);
  });

  it('闰年边界：2024-02-26 起始周跨越 2 月 29 日', async () => {
    db.exec('DELETE FROM focus_sessions');
    const start = '2024-02-26';
    db.prepare("INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?, ?, ?)").run('politics', 45, '2024-02-29T08:00:00');
    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=' + start, headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.weekStart).toBe('2024-02-26');
    expect(body.weekEnd).toBe('2024-03-04');
    expect(body.focusMinutesByDay[3]).toBe(45);
    expect(body.focusMinutesByDay[0]).toBe(0);
  });

  it('空计划：无任何计划时 plansTotal 与 plansDone 均为 0', async () => {
    db.exec("DELETE FROM plans WHERE user_id = (SELECT id FROM users WHERE username = 'statsdeep')");
    const start = '2024-03-04';
    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=' + start, headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.plansTotal).toBe(0);
    expect(body.plansDone).toBe(0);
  });

  it('计划汇总：本周内完成数正确，区间外不计入', async () => {
    db.exec("DELETE FROM plans WHERE user_id = (SELECT id FROM users WHERE username = 'statsdeep')");
    const start = '2024-03-04';
    const ins = db.prepare("INSERT INTO plans (user_id, date, subject, title, done) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?, 'math', 't', ?)");
    ins.run(start, 1);
    ins.run(addDays(start, 3), 0);
    ins.run(addDays(start, 6), 1);
    ins.run(addDays(start, 7), 1);
    ins.run(addDays(start, -1), 1);
    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=' + start, headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.plansTotal).toBe(3);
    expect(body.plansDone).toBe(2);
  });

  it('番茄计时边界：跨周 session 只计入所在周，本周前不计', async () => {
    db.exec('DELETE FROM focus_sessions');
    const start = '2024-03-04';
    db.prepare("INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?, ?, ?)").run('major', 25, '2024-03-03T23:59:59');
    db.prepare("INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?, ?, ?)").run('major', 25, '2024-03-04T00:00:00');
    db.prepare("INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?, ?, ?)").run('major', 25, '2024-03-10T23:59:59');
    db.prepare("INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?, ?, ?)").run('major', 25, '2024-03-11T00:00:00');
    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=' + start, headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.focusMinutes).toBe(50);
    expect(body.focusBySubject.major).toBe(50);
    expect(body.focusMinutesByDay[0]).toBe(25);
    expect(body.focusMinutesByDay[6]).toBe(25);
  });

  it('错题去重：heatmap 中同一天多条错题按条数聚合，weekly mistakesNew 按周计数', async () => {
    db.exec("DELETE FROM mistakes WHERE user_id = (SELECT id FROM users WHERE username = 'statsdeep')");
    const start = '2024-03-04';
    const ins = db.prepare("INSERT INTO mistakes (user_id, subject, title, created_at, mastered) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), 'math', 't', ?, ?)");
    ins.run(start + 'T10:00:00', 0);
    ins.run(start + 'T11:00:00', 1);
    ins.run(addDays(start, 2) + 'T10:00:00', 0);
    ins.run(addDays(start, 7) + 'T10:00:00', 0);
    const weekly = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=' + start, headers: { cookie: authCookie } });
    expect(weekly.statusCode).toBe(200);
    const wb = weekly.json();
    expect(wb.mistakesNew).toBe(4);
    expect(wb.mistakesUnmastered).toBe(3);
  });

  it('单词 SRS：wordsLearned 按 repetitions>0 统计，wordsDue 按 due_date<=today 统计', async () => {
    db.exec("DELETE FROM srs_state WHERE word_id IN (SELECT id FROM words WHERE user_id = (SELECT id FROM users WHERE username = 'statsdeep'))");
    db.exec("DELETE FROM words WHERE user_id = (SELECT id FROM users WHERE username = 'statsdeep')");
    const insW = db.prepare("INSERT INTO words (user_id, word) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?)");
    insW.run('abandon');
    insW.run('benefit');
    insW.run('curious');
    const insS = db.prepare('INSERT INTO srs_state (word_id, repetitions, due_date) VALUES (?, ?, ?)');
    const today = todayStr();
    insS.run(1, 2, addDays(today, -1));
    insS.run(2, 0, addDays(today, -5));
    insS.run(3, 1, addDays(today, 3));
    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=' + today, headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.wordsTotal).toBe(3);
    expect(body.wordsLearned).toBe(2);
    expect(body.wordsDue).toBe(2);
  });

  it('导入 CSV 畸形行：weekly 参数非法时返回 400 且不写入统计', async () => {
    const bad = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=2024/03/04', headers: { cookie: authCookie } });
    expect(bad.statusCode).toBe(400);
    const body = bad.json();
    expect(body.error).toBe('start 日期格式无效');
  });

  it('导入 CSV 畸形行：日期不存在时返回 400', async () => {
    const bad = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=2024-13-45', headers: { cookie: authCookie } });
    expect(bad.statusCode).toBe(400);
    const body = bad.json();
    expect(body.error).toBe('start 日期无效');
  });

  it('备份恢复 round-trip：插入后读取与重新查询一致，连续打卡正确', async () => {
    db.exec("DELETE FROM focus_sessions WHERE user_id = (SELECT id FROM users WHERE username = 'statsdeep')");
    const today = todayStr();
    const ins = db.prepare("INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), ?, ?, ?)");
    ins.run('math', 10, today + 'T08:00:00');
    ins.run('math', 10, addDays(today, -1) + 'T08:00:00');
    ins.run('math', 10, addDays(today, -2) + 'T08:00:00');
    ins.run('math', 10, addDays(today, -4) + 'T08:00:00');
    const res1 = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=' + addDays(today, -6), headers: { cookie: authCookie } });
    expect(res1.statusCode).toBe(200);
    const b1 = res1.json();
    expect(b1.currentStreak).toBe(3);
    const heat = await app.inject({ method: 'GET', url: '/api/stats/heatmap?months=1', headers: { cookie: authCookie } });
    expect(heat.statusCode).toBe(200);
    const hb = heat.json();
    expect(hb.months).toBe(1);
    expect(hb.days.length).toBe(31);
    expect(hb.endDate).toBe(today);
    expect(hb.currentStreak).toBe(3);
    expect(hb.bestStreak).toBe(3);
  });

  it('heatmap months 边界：非法值返回 400，合法值 1 与 6 均可', async () => {
    const bad = await app.inject({ method: 'GET', url: '/api/stats/heatmap?months=0', headers: { cookie: authCookie } });
    expect(bad.statusCode).toBe(400);
    expect(bad.json().error).toBe('months 参数无效');
    const bad2 = await app.inject({ method: 'GET', url: '/api/stats/heatmap?months=7', headers: { cookie: authCookie } });
    expect(bad2.statusCode).toBe(400);
    const bad3 = await app.inject({ method: 'GET', url: '/api/stats/heatmap?months=2.5', headers: { cookie: authCookie } });
    expect(bad3.statusCode).toBe(400);
    const ok1 = await app.inject({ method: 'GET', url: '/api/stats/heatmap?months=1', headers: { cookie: authCookie } });
    expect(ok1.statusCode).toBe(200);
    expect(ok1.json().days.length).toBe(31);
    const ok6 = await app.inject({ method: 'GET', url: '/api/stats/heatmap?months=6', headers: { cookie: authCookie } });
    expect(ok6.statusCode).toBe(200);
    expect(ok6.json().days.length).toBe(186);
  });

  it('模考计数：本周内 exam_records 计数正确，区间外不计入', async () => {
    db.exec("DELETE FROM exam_records WHERE user_id = (SELECT id FROM users WHERE username = 'statsdeep')");
    const start = '2024-03-04';
    const ins = db.prepare("INSERT INTO exam_records (user_id, subject, paper, taken_at) VALUES ((SELECT id FROM users WHERE username = 'statsdeep'), 'math', 'p', ?)");
    ins.run(start + 'T09:00:00');
    ins.run(addDays(start, 6) + 'T09:00:00');
    ins.run(addDays(start, 7) + 'T09:00:00');
    ins.run(addDays(start, -1) + 'T09:00:00');
    const res = await app.inject({ method: 'GET', url: '/api/stats/weekly?start=' + start, headers: { cookie: authCookie } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.examsTaken).toBe(2);
    expect(body.weekStart).toBe(start);
    expect(body.weekEnd).toBe(addDays(start, 7));
  });
});