import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../src/app';
import { registerAndLogin } from './test-utils';
import type { FastifyInstance } from 'fastify';

interface AutoScheduleItem {
  date: string;
  subject: string;
  title: string;
  plannedMinutes: number;
  kind: 'new' | 'review';
}

interface AutoScheduleResponse {
  created: number;
  skipped: number;
  discarded: number;
  items: AutoScheduleItem[];
}

describe('plans auto-schedule cross month deep4', () => {
  let app: FastifyInstance;

  beforeEach(async () => {
    app = await buildApp({ dbPath: ':memory:' });
  });

  afterEach(async () => {
    await app.close();
  });

  it('跨月排期返回 discarded=23 且 items.length=25', async () => {
    const cookie = await registerAndLogin(app, `as_cm_counts_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`);

    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2026-02-12',
        startDate: '2026-01-29',
      },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as AutoScheduleResponse;
    expect(body.discarded).toBe(23);
    expect(body.items.length).toBe(25);
  });

  it('跨月排期的新学日期为 8 个精确序列', async () => {
    const cookie = await registerAndLogin(app, `as_cm_newdates_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`);

    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2026-02-12',
        startDate: '2026-01-29',
      },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as AutoScheduleResponse;

    const newDates = body.items
      .filter((it) => it.title.includes('新学'))
      .map((it) => it.date)
      .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

    expect(newDates).toEqual([
      '2026-01-29',
      '2026-01-31',
      '2026-02-02',
      '2026-02-04',
      '2026-02-06',
      '2026-02-08',
      '2026-02-10',
      '2026-02-12',
    ]);
  });

  it('2026-02-01 当天恰好 2 条复习记录', async () => {
    const cookie = await registerAndLogin(app, `as_cm_feb01_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`);

    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2026-02-12',
        startDate: '2026-01-29',
      },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as AutoScheduleResponse;

    const onFeb01 = body.items.filter((it) => it.date === '2026-02-01');
    expect(onFeb01.length).toBe(2);

    const titles = onFeb01.map((it) => it.title).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    expect(titles).toEqual([
      '智能排期·数学 复习1-3天',
      '智能排期·数学 复习2-1天',
    ]);
  });

  it('所有 items 日期为合法日历日期且不晚于 2026-02-12 并按 date 升序', async () => {
    const cookie = await registerAndLogin(app, `as_cm_dates_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`);

    const res = await app.inject({
      method: 'POST',
      url: '/api/plans/auto-schedule',
      headers: { cookie },
      payload: {
        subjects: ['math'],
        dailyMinutes: 480,
        examDate: '2026-02-12',
        startDate: '2026-01-29',
      },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json() as AutoScheduleResponse;

    for (const item of body.items) {
      expect(item.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      const [y, m, d] = item.date.split('-').map(Number);
      const parsed = new Date(item.date + 'T00:00:00');
      expect(Number.isNaN(parsed.getTime())).toBe(false);
      expect(parsed.getFullYear()).toBe(y);
      expect(parsed.getMonth() + 1).toBe(m);
      expect(parsed.getDate()).toBe(d);
      expect(item.date <= '2026-02-12').toBe(true);
    }

    for (let i = 1; i < body.items.length; i++) {
      expect(body.items[i - 1].date <= body.items[i].date).toBe(true);
    }
  });
});
