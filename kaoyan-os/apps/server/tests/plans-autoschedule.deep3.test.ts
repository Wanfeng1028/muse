// tests/plans-autoschedule.deep3.test.ts
//
// Deep round 3 for /api/plans/auto-schedule. These 8 cases are deliberately
// chosen to NOT overlap with plans-autoschedule.test.ts / plans-autoschedule.deep2.test.ts:
//   - deep2 already covers: review node landing exactly on examDate kept,
//     the 30-day-offset boundary, "every 2 days one lesson" cadence,
//     single-day overflow deferral, chained deferral landing points, and
//     "no A-subject titles under B's account".
//   - this file covers instead:
//       1. single-day window (examDate == startDate) exact counts
//       2. tight-window discarded precise accounting (raw total = 12)
//       3. dailyMinutes=30 => all new-lessons dropped, review-only output
//       4. two-subject deferral pushing reviews past examDate (no review kept)
//       5. multi-user idempotency isolation (A vs B, incl. direct db counts)
//       6. preview vs POST four-tuple exact equality + write count
//       7. duplicate subjects are day-shifted, not deduped (created=3, skipped=0, discarded=9)
//       8. POST validation 400 coverage for every illegal field
//
// All dates are fixed string literals; no todayStr() is ever used as an
// assertion baseline. Every `it` registers its own fresh user (randName)
// and the in-memory db is rebuilt in beforeEach.

import './bcrypt-test-env';
import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import Fastify, { type FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import { registerPlansRoutes } from '../src/routes/plans';
import { createDb as createRealDb } from '../src/db';
import { applyAuthHook, registerAuthRoutes } from '../src/auth';
import { registerAndLogin } from './test-utils';

let app: FastifyInstance;
let db: DatabaseSync;

let userSeq = 0;
function randName(prefix = 'deep3'): string {
  userSeq += 1;
  return `${prefix}_${Date.now().toString(36)}_${userSeq}_${Math.random().toString(36).slice(2, 8)}`;
}

// POST /api/plans/auto-schedule 返回的 items 是 Plan[]，没有 kind 字段（只有 preview 有）。
// 从 title 反推：`智能排期·数学 新学1` -> new，`智能排期·数学 复习1-1天` -> review。
function kindOfTitle(title: string): 'new' | 'review' {
  return title.includes('复习') ? 'review' : 'new';
}

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

type Item = {
  date: string;
  subject: string;
  title: string;
  plannedMinutes: number;
  kind: 'new' | 'review';
};

type AutoScheduleBody = {
  subjects: string[];
  dailyMinutes: number;
  examDate: string;
  startDate?: string;
};

async function postAutoSchedule(cookie: string, payload: AutoScheduleBody) {
  const res = await app.inject({
    method: 'POST',
    url: '/api/plans/auto-schedule',
    headers: { cookie },
    payload,
  });
  return res;
}

async function getPreview(cookie: string, query: Record<string, string | number>) {
  const qs = new URLSearchParams(
    Object.entries(query).map(([k, v]) => [k, String(v)]),
  ).toString();
  const res = await app.inject({
    method: 'GET',
    url: `/api/plans/auto-schedule/preview?${qs}`,
    headers: { cookie },
  });
  return res;
}

async function getPlans(cookie: string) {
  const res = await app.inject({
    method: 'GET',
    url: '/api/plans',
    headers: { cookie },
  });
  return res;
}

function userIdOf(username: string): number {
  const row = db
    .prepare('SELECT id FROM users WHERE username = ?')
    .get(username) as { id: number } | undefined;
  if (!row) throw new Error(`user not found: ${username}`);
  return row.id;
}

function planCountForUser(userId: number): number {
  const row = db
    .prepare('SELECT COUNT(*) AS c FROM plans WHERE user_id = ?')
    .get(userId) as { c: number };
  return row.c;
}

describe('plans/auto-schedule deep3', () => {
  it('1. single-day window examDate==startDate: only the first new lesson survives', async () => {
    const username = randName();
    const cookie = await registerAndLogin(app, username);

    const res = await postAutoSchedule(cookie, {
      subjects: ['math'],
      dailyMinutes: 600,
      startDate: '2026-12-19',
      examDate: '2026-12-19',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      created: number;
      skipped: number;
      discarded: number;
      items: Item[];
    };

    // math: n=1 -> D=2026-12-19 (== examDate, not > so kept).
    //   new(60) on D.
    //   reviews: R=D+1=12-20 > examDate -> discard; +3, +7, +15, +30 all > too.
    //   => 1 new generated, 5 reviews discarded.
    // n=2 -> D=2026-12-21 > examDate -> break.
    // raw = [new@12-19(60)]
    // greedy: used[12-19]=0; 60 <= 600; while(0+60 > 600)? no -> place.
    // created=1, skipped=0, discarded=5.
    expect(body.created).toBe(1);
    expect(body.skipped).toBe(0);
    expect(body.discarded).toBe(5);
    expect(body.items.length).toBe(1);
    expect(body.items[0].date).toBe('2026-12-19');
    expect(kindOfTitle(body.items[0].title)).toBe('new');
  });

  it('2. tight window 12-01..12-03: raw total is exactly 12, precise discarded', async () => {
    const username = randName();
    const cookie = await registerAndLogin(app, username);

    const res = await postAutoSchedule(cookie, {
      subjects: ['math'],
      dailyMinutes: 600,
      startDate: '2026-12-01',
      examDate: '2026-12-03',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      created: number;
      skipped: number;
      discarded: number;
      items: Item[];
    };

    // math:
    //   n=1 -> D=2026-12-01. new(60). reviews: 12-02(1),12-04(3)>exam,12-08(7)>,
    //          12-16(15)>,12-31(30)> => only offset=1 kept.
    //   n=2 -> D=2026-12-03. new(60). reviews: 12-04(1)>exam, rest > => 0 kept.
    //   n=3 -> D=2026-12-05 > examDate -> break.
    // raw generated (before sort): new@12-01, review@12-02, new@12-03 => 3 generated.
    // discarded during generation (R>examDate): offset 3,7,15,30 for n=1 (4)
    //                                        + offsets 1,3,7,15,30 for n=2 (5) = 9.
    // raw count = 3 generated + 9 discarded = 12.
    // greedy on dailyMinutes=600 (all single items 60/30 <= 600, no deferral):
    //   sorted by (date asc, new before review):
    //     12-01 new math (60)
    //     12-02 review math (30)
    //     12-03 new math (60)
    //   all placed. created=3, discarded stays 9.
    expect(body.created).toBe(3);
    expect(body.discarded).toBe(9);
    expect(body.created + body.discarded).toBe(12);
    expect(body.items.map((i) => i.date)).toEqual([
      '2026-12-01',
      '2026-12-02',
      '2026-12-03',
    ]);
    expect(body.items.map((i) => kindOfTitle(i.title))).toEqual(['new', 'review', 'new']);
  });

  it('3. dailyMinutes=30: every new lesson dropped, review-only output', async () => {
    const username = randName();
    const cookie = await registerAndLogin(app, username);

    const res = await postAutoSchedule(cookie, {
      subjects: ['math'],
      dailyMinutes: 30,
      startDate: '2026-12-01',
      examDate: '2026-12-10',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      created: number;
      skipped: number;
      discarded: number;
      items: Item[];
    };

    // math, window 12-01..12-10 (inclusive).
    // n=1 -> D=12-01. new(60) generated. reviews: offset1=12-02 kept(<=12-10),
    //   offset3=12-04 kept, offset7=12-08 kept, offset15=12-16>exam disc,
    //   offset30=12-31>exam disc. => gen new + 3 reviews, 2 disc.
    // n=2 -> D=12-03. new(60). reviews: 12-04 kept, 12-06 kept, 12-10 kept,
    //   12-18> disc, 12-33> disc. => gen new + 3 reviews, 2 disc.
    // n=3 -> D=12-05. new(60). reviews: 12-06 kept, 12-08 kept, 12-12> disc,
    //   12-20> disc, 12-35> disc. => gen new + 2 reviews, 3 disc.
    // n=4 -> D=12-07. new(60). reviews: 12-08 kept, 12-10 kept, 12-14> disc,
    //   12-22> disc, 12-37> disc. => gen new + 2 reviews, 3 disc.
    // n=5 -> D=12-09. new(60). reviews: 12-10 kept, 12-12> disc, 12-16> disc,
    //   12-24> disc, 12-39> disc. => gen new + 1 review, 4 disc.
    // n=6 -> D=12-11 > examDate -> break.
    //
    // generated news = 5, generated reviews = 3+3+2+2+1 = 11.
    // generation-time discards = 2+2+3+3+4 = 14.
    //
    // raw = 5 news + 11 reviews = 16 raw entries (sorted).
    // greedy, dailyMinutes=30:
    //   each new is 60 > 30 -> discarded immediately (5 discards).
    //   each review is 30:
    //     sort order (date asc, new before review):
    //       12-01 new(disc), 12-02 review, 12-03 new(disc), 12-04 review,
    //       12-04 review(n=2 offset1), 12-05 new(disc), 12-06 review(n=2 o3),
    //       12-06 review(n=3 o1), 12-07 new(disc), 12-08 review(n=1 o7),
    //       12-08 review(n=3 o3), 12-08 review(n=4 o1), 12-09 new(disc),
    //       12-10 review(n=2 o7), 12-10 review(n=4 o3), 12-10 review(n=5 o1)
    //   reviews placed:
    //     12-02: used=0, 30<=30, place. used[12-02]=30.
    //     12-04: 30 <= 30 place. used[12-04]=30.
    //     12-04 (2nd): used=30, 30+30>30 -> d=12-05: used=0, place. used[12-05]=30.
    //     12-06: place. used[12-06]=30.
    //     12-06 (2nd): d=12-07: place. used[12-07]=30.
    //     12-08: place. used[12-08]=30.
    //     12-08 (2nd): d=12-09: place. used[12-09]=30.
    //     12-08 (3rd): d=12-09 used=30 -> d=12-10: place. used[12-10]=30.
    //     12-10: used=30 -> d=12-11 > exam -> discarded.
    //     12-10 (2nd): discarded.
    //     12-10 (3rd): discarded.
    //   => placed reviews = 8, deferred-off examDate discards = 3.
    //
    // total discarded = 14 (gen) + 5 (news too big) + 3 (deferred off) = 22.
    // created = 8.
    expect(body.created).toBe(8);
    expect(body.discarded).toBe(22);
    expect(body.items.length).toBe(8);
    for (const it of body.items) {
      expect(kindOfTitle(it.title)).toBe('review');
      expect(it.plannedMinutes).toBe(30);
      expect(it.date <= '2026-12-10').toBe(true);
    }
    const perDay = new Map<string, number>();
    for (const it of body.items) {
      perDay.set(it.date, (perDay.get(it.date) ?? 0) + it.plannedMinutes);
    }
    for (const mins of perDay.values()) {
      expect(mins <= 30).toBe(true);
    }
  });

  it('4. two-subject deferral pushes math reviews past examDate -> none kept', async () => {
    const username = randName();
    const cookie = await registerAndLogin(app, username);

    const res = await postAutoSchedule(cookie, {
      subjects: ['math', 'english'],
      dailyMinutes: 60,
      startDate: '2026-12-18',
      examDate: '2026-12-19',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      created: number;
      skipped: number;
      discarded: number;
      items: Item[];
    };

    // si=0 math:
    //   n=1 -> D=12-18. new(60). reviews: offset1=12-19 kept, offset3=12-21>,
    //     offset7=12-25>, offset15=01-02>, offset30=01-17> => 1 kept, 4 disc.
    //   n=2 -> D=12-20 > examDate -> break.
    // si=1 english:
    //   n=1 -> D=addDays(12-18, 1) = 12-19. new(60). reviews: offset1=12-20> ...
    //     all 5 offsets > examDate => 5 disc.
    //   n=2 -> D=12-21 > examDate -> break.
    //
    // generated = math new@12-18, math review@12-19, english new@12-19.
    // gen discards = 4 (math reviews) + 5 (english reviews) = 9.
    // raw sorted (date asc, new before review):
    //   12-18 math new(60)
    //   12-19 math review(30)
    //   12-19 english new(60)
    // greedy, dailyMinutes=60:
    //   12-18 math new: used=0, 60<=60, place. used[12-18]=60.
    //   12-19 math review: used=0, 30<=60, place. used[12-19]=30.
    //   12-19 english new: used=30, 30+60>60 -> d=12-20 > examDate -> discard.
    // created=2, discarded = 9 + 1 = 10.
    expect(body.created).toBe(2);
    expect(body.discarded).toBe(10);
    expect(body.items.length).toBe(2);
    for (const it of body.items) {
      expect(kindOfTitle(it.title)).not.toBe('review');
    }
    const subjects = new Set(body.items.map((i) => i.subject));
    expect(subjects.has('math')).toBe(true);
    expect(subjects.has('english')).toBe(true);
  });

  it('5. multi-user idempotency isolation', async () => {
    const nameA = randName('isoa');
    const nameB = randName('isob');
    const cookieA = await registerAndLogin(app, nameA);
    const cookieB = await registerAndLogin(app, nameB);

    const payload: AutoScheduleBody = {
      subjects: ['math'],
      dailyMinutes: 600,
      startDate: '2026-12-01',
      examDate: '2026-12-05',
    };

    const resA1 = await postAutoSchedule(cookieA, payload);
    expect(resA1.statusCode).toBe(200);
    const bodyA1 = resA1.json() as { created: number; skipped: number; discarded: number };
    const createdA = bodyA1.created;
    expect(createdA).toBeGreaterThan(0);

    const resB1 = await postAutoSchedule(cookieB, payload);
    expect(resB1.statusCode).toBe(200);
    const bodyB1 = resB1.json() as { created: number; skipped: number; discarded: number };
    const createdB = bodyB1.created;
    expect(createdB).toBe(createdA);

    const resA2 = await postAutoSchedule(cookieA, payload);
    expect(resA2.statusCode).toBe(200);
    const bodyA2 = resA2.json() as { created: number; skipped: number; discarded: number };
    expect(bodyA2.created).toBe(0);
    expect(bodyA2.skipped).toBe(createdA);

    const resB2 = await postAutoSchedule(cookieB, payload);
    expect(resB2.statusCode).toBe(200);
    const bodyB2 = resB2.json() as { created: number; skipped: number; discarded: number };
    expect(bodyB2.created).toBe(0);
    expect(bodyB2.skipped).toBe(createdB);

    const plansA = await getPlans(cookieA);
    expect(plansA.statusCode).toBe(200);
    const itemsA = plansA.json() as unknown[];
    expect(itemsA.length).toBe(createdA);

    const plansB = await getPlans(cookieB);
    expect(plansB.statusCode).toBe(200);
    const itemsB = plansB.json() as unknown[];
    expect(itemsB.length).toBe(createdB);

    const idA = userIdOf(nameA);
    const idB = userIdOf(nameB);
    expect(planCountForUser(idA)).toBe(createdA);
    expect(planCountForUser(idB)).toBe(createdB);
  });

  it('6. preview and POST produce identical four-tuples in the same order', async () => {
    const username = randName();
    const cookie = await registerAndLogin(app, username);

    const params: AutoScheduleBody = {
      subjects: ['english'],
      dailyMinutes: 600,
      startDate: '2026-12-01',
      examDate: '2026-12-08',
    };

    const previewRes = await getPreview(cookie, {
      subjects: 'english',
      dailyMinutes: 600,
      startDate: '2026-12-01',
      examDate: '2026-12-08',
    });
    expect(previewRes.statusCode).toBe(200);
    const previewBody = previewRes.json() as { items: Item[] };

    const postRes = await postAutoSchedule(cookie, params);
    expect(postRes.statusCode).toBe(200);
    const postBody = postRes.json() as { created: number; items: Item[] };

    // 注意：POST 返回的 items 是 Plan[]，没有 kind 字段；只比较四元组。
    const fourTuple = (i: Item) =>
      [i.date, i.subject, i.title, i.plannedMinutes] as const;

    expect(previewBody.items.length).toBe(postBody.items.length);
    expect(previewBody.items.map(fourTuple)).toEqual(postBody.items.map(fourTuple));

    const plansRes = await getPlans(cookie);
    expect(plansRes.statusCode).toBe(200);
    const plans = plansRes.json() as unknown[];
    expect(plans.length).toBe(postBody.created);
  });

  it('7. duplicate subjects are day-shifted, not deduped (created=3, discarded=9)', async () => {
    const username = randName();
    const cookie = await registerAndLogin(app, username);

    const res = await postAutoSchedule(cookie, {
      subjects: ['math', 'math'],
      dailyMinutes: 600,
      startDate: '2026-12-18',
      examDate: '2026-12-19',
    });
    expect(res.statusCode).toBe(200);
    const body = res.json() as {
      created: number;
      skipped: number;
      discarded: number;
      items: Item[];
    };

    // 按源码逐行重算（si=1 的科目起始日 = startDate+1）：
    //   si=0: n=1 -> D=12-18 新学1(60)；复习 offset=1 -> 12-19 保留(30)，
    //     offset=3/7/15/30 -> 12-21/12-25/01-02/01-17 超 examDate -> 4 discarded；
    //     n=2 -> D=12-20 > examDate 终止。
    //   si=1: n=1 -> D=12-19 新学1(60)；5 个复习节点 R>=12-20 全超 examDate -> 5 discarded；
    //     n=2 -> D=12-21 > examDate 终止。
    // raw=3 条，生成期 discarded=9；放置（600 分钟/天）3 条全放下；
    // 幂等键 (user_id,date,subject,title) 三条互不相同，无去重。
    // 结论：重复科目不会触发去重——si 偏移使第二套计划整体后移一天；
    // (date,subject,title) 去重只发生在同一用户重复 POST 同一参数时。
    expect(body.created).toBe(3);
    expect(body.skipped).toBe(0);
    expect(body.discarded).toBe(9);
    expect(body.items.length).toBe(3);
  });

  it('8. POST validation returns 400 for every illegal field', async () => {
    const username = randName();
    const cookie = await registerAndLogin(app, username);

    const valid: AutoScheduleBody = {
      subjects: ['math'],
      dailyMinutes: 60,
      startDate: '2026-12-01',
      examDate: '2026-12-10',
    };

    // subjects = []
    {
      const r = await postAutoSchedule(cookie, { ...valid, subjects: [] });
      expect(r.statusCode).toBe(400);
    }

    // subjects = ['nope']
    {
      const r = await postAutoSchedule(cookie, { ...valid, subjects: ['nope'] });
      expect(r.statusCode).toBe(400);
    }

    // dailyMinutes = 29
    {
      const r = await postAutoSchedule(cookie, { ...valid, dailyMinutes: 29 });
      expect(r.statusCode).toBe(400);
    }

    // dailyMinutes = 1441
    {
      const r = await postAutoSchedule(cookie, { ...valid, dailyMinutes: 1441 });
      expect(r.statusCode).toBe(400);
    }

    // dailyMinutes = 60.5 (non-integer)
    {
      const r = await postAutoSchedule(cookie, { ...valid, dailyMinutes: 60.5 });
      expect(r.statusCode).toBe(400);
    }

    // examDate = '2026-13-01' (invalid month)
    {
      const r = await postAutoSchedule(cookie, { ...valid, examDate: '2026-13-01' });
      expect(r.statusCode).toBe(400);
    }

    // examDate earlier than startDate
    {
      const r = await postAutoSchedule(cookie, {
        ...valid,
        startDate: '2026-12-10',
        examDate: '2026-12-01',
      });
      expect(r.statusCode).toBe(400);
    }

    // startDate = 'not-a-date'
    {
      const r = await postAutoSchedule(cookie, { ...valid, startDate: 'not-a-date' });
      expect(r.statusCode).toBe(400);
    }
  });
});
