import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import { DatabaseSync } from 'node:sqlite';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

let db: DatabaseSync;
let app: FastifyInstance;

beforeEach(async () => {
  db = createRealDb(':memory:');
  app = Fastify();
  registerPlansRoutes(app, db);
  applyAuthHook(app, db);
  registerAuthRoutes(app, db);
  await app.ready();
});

afterAll(async () => {
  await app.close();
});

function randName(prefix: string): string {
  return prefix + Math.random().toString(36).slice(2, 10);
}

interface AutoScheduleResponse {
  created: number;
  skipped: number;
  discarded: number;
  items: Array<{
    id: number;
    date: string;
    subject: string;
    title: string;
    plannedMinutes: number;
    done: boolean;
    createdAt: string;
  }>;
}

describe('POST /api/plans/auto-schedule 深度边界', () => {
  it('复习节点恰好落在 examDate 当天时保留', async () => {
    const username = randName('deep');
    const cookie = await registerAndLogin(app, username);

    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 600,
        examDate: '2026-12-19',
        startDate: '2026-12-18',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as AutoScheduleResponse;

    // 新学1 在 12-18，复习 +1 天落在 12-19（等于 examDate 保留）；
    // +3/+7/+15/+30 全部超过 examDate 各丢弃一次，共 4 次；
    // 第 2 课 D=12-20 超过 examDate，停止推进，所以只有 2 条落库。
    expect(body.created).toBe(2);
    expect(body.discarded).toBe(4);

    const new1 = body.items.find((i) => i.title === '智能排期·数学 新学1');
    expect(new1).toBeDefined();
    expect(new1!.date).toBe('2026-12-18');

    const review1 = body.items.find((i) => i.title === '智能排期·数学 复习1-1天');
    expect(review1).toBeDefined();
    expect(review1!.date).toBe('2026-12-19');

    for (const item of body.items) {
      expect(item.date <= '2026-12-19').toBe(true);
    }
  });

  it('30 天偏移的保留/丢弃分界', async () => {
    const nameA = randName('deep');
    const cookieA = await registerAndLogin(app, nameA);

    // startDate 2026-10-20，新学1 在 10-20，+30 天 = 11-19，恰好等于 examDate 保留
    const resA = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieA },
      payload: {
        subjects: ['math'],
        dailyMinutes: 600,
        startDate: '2026-10-20',
        examDate: '2026-11-19',
      },
    });
    expect(resA.statusCode).toBe(200);
    const bodyA = resA.json() as AutoScheduleResponse;
    const review30A = bodyA.items.find((i) => i.title === '智能排期·数学 复习1-30天');
    expect(review30A).toBeDefined();
    expect(review30A!.date).toBe('2026-11-19');

    // 换新用户，examDate 提前一天到 11-18，+30 天超过 examDate 被丢弃
    const nameB = randName('deep');
    const cookieB = await registerAndLogin(app, nameB);

    const resB = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieB },
      payload: {
        subjects: ['math'],
        dailyMinutes: 600,
        startDate: '2026-10-20',
        examDate: '2026-11-18',
      },
    });
    expect(resB.statusCode).toBe(200);
    const bodyB = resB.json() as AutoScheduleResponse;

    const review30B = bodyB.items.find((i) => i.title === '智能排期·数学 复习1-30天');
    expect(review30B).toBeUndefined();
    expect(bodyB.discarded).toBeGreaterThanOrEqual(1);
    for (const item of bodyB.items) {
      expect(item.date <= '2026-11-18').toBe(true);
    }
  });

  it('新学推进节奏：每 2 天一课，科目之间错开', async () => {
    const nameA = randName('deep');
    const cookieA = await registerAndLogin(app, nameA);

    const resA = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieA },
      payload: {
        subjects: ['math'],
        dailyMinutes: 600,
        startDate: '2026-10-20',
        examDate: '2026-12-19',
      },
    });
    expect(resA.statusCode).toBe(200);
    const bodyA = resA.json() as AutoScheduleResponse;

    const n1 = bodyA.items.find((i) => i.title === '智能排期·数学 新学1');
    const n2 = bodyA.items.find((i) => i.title === '智能排期·数学 新学2');
    const n3 = bodyA.items.find((i) => i.title === '智能排期·数学 新学3');
    expect(n1).toBeDefined();
    expect(n2).toBeDefined();
    expect(n3).toBeDefined();
    expect(n1!.date).toBe('2026-10-20');
    expect(n2!.date).toBe('2026-10-22');
    expect(n3!.date).toBe('2026-10-24');

    // 两个科目：math 是 si=0，english 是 si=1，english 新学1 往后错开 1 天
    const nameB = randName('deep');
    const cookieB = await registerAndLogin(app, nameB);

    const resB = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieB },
      payload: {
        subjects: ['math', 'english'],
        dailyMinutes: 600,
        startDate: '2026-10-20',
        examDate: '2026-12-19',
      },
    });
    expect(resB.statusCode).toBe(200);
    const bodyB = resB.json() as AutoScheduleResponse;

    const mathNew1 = bodyB.items.find((i) => i.title === '智能排期·数学 新学1');
    const englishNew1 = bodyB.items.find((i) => i.title === '智能排期·英语 新学1');
    expect(mathNew1).toBeDefined();
    expect(englishNew1).toBeDefined();
    expect(mathNew1!.date).toBe('2026-10-20');
    expect(englishNew1!.date).toBe('2026-10-21');
  });

  it('单日分钟超限时顺延到后面可放下的日期', async () => {
    const username = randName('deep');
    const cookie = await registerAndLogin(app, username);

    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math', 'english'],
        dailyMinutes: 60,
        startDate: '2026-10-20',
        examDate: '2026-12-19',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as AutoScheduleResponse;

    // 10-21 那天 english 新学1（60 分钟）是新学，排在复习前面先放；
    // math 复习1-1天 也是 10-21，30 分钟放不下，往后挪到 10-22。
    const englishNew1 = body.items.find((i) => i.title === '智能排期·英语 新学1');
    expect(englishNew1).toBeDefined();
    expect(englishNew1!.date).toBe('2026-10-21');

    const mathReview1 = body.items.find((i) => i.title === '智能排期·数学 复习1-1天');
    expect(mathReview1).toBeDefined();
    expect(mathReview1!.date).toBe('2026-10-22');

    // 不变量：任意一天放置的总分钟不超过 dailyMinutes
    const perDay = new Map<string, number>();
    for (const item of body.items) {
      perDay.set(item.date, (perDay.get(item.date) ?? 0) + item.plannedMinutes);
    }
    for (const total of perDay.values()) {
      expect(total <= 60).toBe(true);
    }
  });

  it('连续多日超限的链式顺延落点', async () => {
    const username = randName('deep');
    const cookie = await registerAndLogin(app, username);

    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math', 'english'],
        dailyMinutes: 60,
        startDate: '2026-10-20',
        examDate: '2026-12-19',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as AutoScheduleResponse;

    // 推演：buildSchedule 先把 raw 条目按 (date, 新学优先) 排序，再逐条贪心放置，
    // 单日已用分钟 + 本条 > dailyMinutes 就往后挪一天，直到放得下。
    // 10-20 math 新学1(60) 放满。
    // 10-21 英语 新学1(60)（新学优先于同日的 math 复习1-1天）放满；
    //   math 复习1-1天(30) 被挤到 10-22。
    // 10-22 math 复习1-1天(30) 已占 30；math 新学2(60) 放不下 → 挪到 10-23；
    //   英语 复习1-1天(30) 与 10-22 的 30 相加正好 60 放下。
    // 10-23 math 新学2(60) 占满；英语 新学2(60) 放不下 → 挪到 10-24；
    //   math 复习1-3天(30)、math 复习2-1天(30) 依次尝试 → 10-24 已被英语 新学2 占满 → 10-25。
    // 10-24 英语 新学2(60) 放满。
    // 10-25 math 复习1-3天(30) 与 math 复习2-1天(30) 相加正好 60 放下。
    // 10-26 math 新学3(60) 放满。
    // 10-27 英语 复习1-3天(30) 与 英语 复习2-1天(30) 相加正好 60 放下。
    const englishNew2 = body.items.find((i) => i.title === '智能排期·英语 新学2');
    expect(englishNew2).toBeDefined();
    expect(englishNew2!.date).toBe('2026-10-24');

    const mathReview13 = body.items.find((i) => i.title === '智能排期·数学 复习1-3天');
    expect(mathReview13).toBeDefined();
    expect(mathReview13!.date).toBe('2026-10-25');

    const mathReview21 = body.items.find((i) => i.title === '智能排期·数学 复习2-1天');
    expect(mathReview21).toBeDefined();
    expect(mathReview21!.date).toBe('2026-10-25');

    const minutesByDate = new Map<string, number>();
    for (const item of body.items) {
      minutesByDate.set(item.date, (minutesByDate.get(item.date) ?? 0) + item.plannedMinutes);
    }
    for (const [date, minutes] of minutesByDate) {
      expect(minutes, `date=${date} 放置分钟数超限`).toBeLessThanOrEqual(60);
    }
  });

  it('用户隔离：B 名下不出现 A 的科目计划', async () => {
    const nameA = randName('deep');
    const nameB = randName('deep');
    const cookieA = await registerAndLogin(app, nameA);
    const cookieB = await registerAndLogin(app, nameB);

    const resA = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieA },
      payload: {
        subjects: ['math'],
        dailyMinutes: 600,
        examDate: '2026-12-19',
        startDate: '2026-10-20',
      },
    });
    expect(resA.statusCode).toBe(200);
    expect((resA.json() as AutoScheduleResponse).created).toBeGreaterThan(0);

    const listB = await app.inject({
      method: 'GET',
      url: '/api/plans',
      headers: { cookie: cookieB },
    });
    expect(listB.statusCode).toBe(200);
    expect(listB.json()).toEqual([]);

    const resB = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie: cookieB },
      payload: {
        subjects: ['english'],
        dailyMinutes: 600,
        examDate: '2026-12-19',
        startDate: '2026-10-20',
      },
    });
    expect(resB.statusCode).toBe(200);
    const bodyB = resB.json() as AutoScheduleResponse;
    const mathItem = bodyB.items.find((i) => i.subject === 'math');
    expect(mathItem).toBeUndefined();
  }, 30000);
});
