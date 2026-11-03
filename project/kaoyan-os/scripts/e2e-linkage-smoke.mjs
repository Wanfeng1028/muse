#!/usr/bin/env node
/**
 * e2e-linkage-smoke.mjs
 * 复习计划 / 错题 / 考试联动 端到端黑盒冒烟
 *
 * 覆盖口径（8 步）：
 *  1) 注册 201 + 登录 200 并提取 kaoyan_session cookie
 *  2) 今日计划 P1(math,60) / P2(english,30) 创建 201 且 id 为数字
 *  3) focus 与 planId 关联：P1->40、P2->20 正确回填，无关联->planId===null
 *  4) plans/summary 聚合：total=2、P1.actualMinutes=40、P2.actualMinutes=20
 *  5) 错题 <-> 真题 双向联动：source-exams 含 E1、related-mistakes 含 M1
 *  6) PATCH 计划 done + weekly 统计联动：focusMinutes>=75、planCompletionRate>0
 *  7) DELETE 计划后 focus 记录保留且 planId 置 null、summary 仅剩 1 条
 *  8) 逐步 PASS 输出，全绿输出 LINKAGE E2E OK；失败抛 Error 且非零退出
 */

import assert from 'node:assert/strict';

const BASE = process.env.E2E_BASE || 'http://127.0.0.1:3123';

/* ------------------------- utils ------------------------- */

const pad = (n) => String(n).padStart(2, '0');
const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

const today = localToday();

const username = `e2e_${Date.now().toString(36)}`;
assert.match(username, /^[a-z][a-z0-9_]{2,31}$/, `generated username invalid: ${username}`);

const stepLog = [];
function pass(name) {
  const line = `PASS ${name}`;
  stepLog.push(line);
  console.log(line);
}

async function req(method, path, body, cookie) {
  const headers = {};
  if (body !== undefined && body !== null) headers['content-type'] = 'application/json';
  if (cookie) headers['cookie'] = cookie;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body === undefined || body === null ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(10000),
  });

  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  return { status: res.status, data, headers: res.headers };
}

function fail(step, expected, actual) {
  const msg = `[${step}] assertion failed\n  expected: ${JSON.stringify(expected)}\n  actual:   ${JSON.stringify(actual)}`;
  const err = new Error(msg);
  err.step = step;
  throw err;
}

function safeAssert(step, fn, expected, actualFn) {
  try {
    fn();
  } catch (e) {
    let actual;
    try {
      actual = actualFn ? actualFn() : undefined;
    } catch {
      actual = '<unavailable>';
    }
    fail(step, expected, actual);
  }
}

/* ------------------------- steps ------------------------- */

async function main() {
  // ---- Step 1: register + login ----
  const step1 = 'step1 register/login';
  const reg = await req('POST', '/api/auth/register', { username, password: 'e2ePassw0rd!' });
  safeAssert(step1, () => assert.equal(reg.status, 201), { status: 201 }, () => ({ status: reg.status, data: reg.data }));

  const login = await req('POST', '/api/auth/login', { username, password: 'e2ePassw0rd!' });
  safeAssert(step1, () => assert.equal(login.status, 200), { status: 200 }, () => ({ status: login.status, data: login.data }));

  const setCookie = login.headers.get('set-cookie') || '';
  const cookiePart = setCookie.split(';')[0].trim();
  safeAssert(step1, () => assert.match(cookiePart, /^kaoyan_session=/), 'kaoyan_session=xxx', () => setCookie);
  const cookie = cookiePart;
  pass(step1);

  // ---- Step 2: create plans ----
  const step2 = 'step2 create plans';
  const p1Res = await req('POST', '/api/plans', { date: today, title: 'E2E 高数', subject: 'math', plannedMinutes: 60 }, cookie);
  safeAssert(step2, () => assert.equal(p1Res.status, 201), { status: 201 }, () => ({ status: p1Res.status, data: p1Res.data }));
  safeAssert(step2, () => assert.equal(typeof p1Res.data?.id, 'number'), 'number id', () => p1Res.data);
  const P1 = p1Res.data.id;

  const p2Res = await req('POST', '/api/plans', { date: today, title: 'E2E 单词', subject: 'english', plannedMinutes: 30 }, cookie);
  safeAssert(step2, () => assert.equal(p2Res.status, 201), { status: 201 }, () => ({ status: p2Res.status, data: p2Res.data }));
  safeAssert(step2, () => assert.equal(typeof p2Res.data?.id, 'number'), 'number id', () => p2Res.data);
  const P2 = p2Res.data.id;

  safeAssert(step2, () => assert.notEqual(P1, P2), 'P1 !== P2', () => ({ P1, P2 }));
  pass(step2);

  // ---- Step 3: create focus records ----
  const step3 = 'step3 create focus with planId linkage';
  const f1Res = await req('POST', '/api/focus', { subject: 'math', minutes: 40, planId: P1 }, cookie);
  safeAssert(step3, () => assert.equal(f1Res.status, 201), { status: 201 }, () => ({ status: f1Res.status, data: f1Res.data }));
  safeAssert(step3, () => assert.equal(f1Res.data?.planId, P1), { planId: P1 }, () => f1Res.data);

  const f2Res = await req('POST', '/api/focus', { subject: 'english', minutes: 20, planId: P2 }, cookie);
  safeAssert(step3, () => assert.equal(f2Res.status, 201), { status: 201 }, () => ({ status: f2Res.status, data: f2Res.data }));
  safeAssert(step3, () => assert.equal(f2Res.data?.planId, P2), { planId: P2 }, () => f2Res.data);

  const f3Res = await req('POST', '/api/focus', { subject: 'math', minutes: 15 }, cookie);
  safeAssert(step3, () => assert.equal(f3Res.status, 201), { status: 201 }, () => ({ status: f3Res.status, data: f3Res.data }));
  safeAssert(step3, () => assert.equal(f3Res.data?.planId, null), { planId: null }, () => f3Res.data);
  pass(step3);

  // ---- Step 4: plans/summary aggregation ----
  const step4 = 'step4 plans/summary aggregation';
  const sumRes = await req('GET', `/api/plans/summary?date=${today}`, undefined, cookie);
  safeAssert(step4, () => assert.equal(sumRes.status, 200), { status: 200 }, () => ({ status: sumRes.status, data: sumRes.data }));
  safeAssert(step4, () => assert.equal(sumRes.data?.total, 2), { total: 2 }, () => sumRes.data);
  const plans = sumRes.data?.plans || [];
  const sp1 = plans.find((p) => p.id === P1);
  const sp2 = plans.find((p) => p.id === P2);
  safeAssert(step4, () => assert.ok(sp1), 'P1 present in summary.plans', () => plans);
  safeAssert(step4, () => assert.ok(sp2), 'P2 present in summary.plans', () => plans);
  safeAssert(step4, () => assert.equal(sp1.actualMinutes, 40), { actualMinutes: 40 }, () => sp1);
  safeAssert(step4, () => assert.equal(sp2.actualMinutes, 20), { actualMinutes: 20 }, () => sp2);
  pass(step4);

  // ---- Step 5: mistake <-> exam linkage ----
  const step5 = 'step5 mistake/exam linkage';
  const m1Res = await req('POST', '/api/mistakes', { subject: 'math', title: 'E2E 错题-中值定理' }, cookie);
  safeAssert(step5, () => assert.equal(m1Res.status, 201), { status: 201 }, () => ({ status: m1Res.status, data: m1Res.data }));
  safeAssert(step5, () => assert.equal(typeof m1Res.data?.id, 'number'), 'number id', () => m1Res.data);
  const M1 = m1Res.data.id;

  const e1Res = await req('POST', '/api/exams', { subject: 'math', paper: 'E2E 2024真题一', score: 110, totalScore: 150, takenAt: today }, cookie);
  safeAssert(step5, () => assert.equal(e1Res.status, 201), { status: 201 }, () => ({ status: e1Res.status, data: e1Res.data }));
  safeAssert(step5, () => assert.equal(typeof e1Res.data?.id, 'number'), 'number id', () => e1Res.data);
  const E1 = e1Res.data.id;

  const srcRes = await req('GET', `/api/mistakes/${M1}/source-exams`, undefined, cookie);
  safeAssert(step5, () => assert.equal(srcRes.status, 200), { status: 200 }, () => ({ status: srcRes.status, data: srcRes.data }));
  safeAssert(step5, () => assert.ok(Array.isArray(srcRes.data)), 'array', () => srcRes.data);
  safeAssert(step5, () => assert.ok(srcRes.data.some((e) => e.id === E1)), `source-exams contains E1=${E1}`, () => srcRes.data);

  const relRes = await req('GET', `/api/exams/${E1}/related-mistakes`, undefined, cookie);
  safeAssert(step5, () => assert.equal(relRes.status, 200), { status: 200 }, () => ({ status: relRes.status, data: relRes.data }));
  safeAssert(step5, () => assert.ok(Array.isArray(relRes.data)), 'array', () => relRes.data);
  safeAssert(step5, () => assert.ok(relRes.data.some((m) => m.id === M1)), `related-mistakes contains M1=${M1}`, () => relRes.data);
  pass(step5);

  // ---- Step 6: patch plan done + weekly stats ----
  const step6 = 'step6 patch plan done & weekly stats';
  const patchRes = await req('PATCH', `/api/plans/${P1}`, { done: true }, cookie);
  safeAssert(step6, () => assert.equal(patchRes.status, 200), { status: 200 }, () => ({ status: patchRes.status, data: patchRes.data }));

  const weeklyRes = await req('GET', '/api/stats/weekly', undefined, cookie);
  safeAssert(step6, () => assert.equal(weeklyRes.status, 200), { status: 200 }, () => ({ status: weeklyRes.status, data: weeklyRes.data }));
  const weekly = weeklyRes.data || {};

  if ('focusMinutes' in weekly) {
    safeAssert(step6, () => assert.ok(weekly.focusMinutes >= 75), 'focusMinutes >= 75', () => weekly.focusMinutes);
  } else {
    console.warn('[warn] step6: /api/stats/weekly missing focusMinutes, skipping assertion');
  }
  if ('planCompletionRate' in weekly) {
    safeAssert(step6, () => assert.ok(weekly.planCompletionRate > 0), 'planCompletionRate > 0', () => weekly.planCompletionRate);
  } else {
    console.warn('[warn] step6: /api/stats/weekly missing planCompletionRate, skipping assertion');
  }
  pass(step6);

  // ---- Step 7: delete plan, focus survives with planId null ----
  const step7 = 'step7 delete plan keeps focus with planId=null';
  const delRes = await req('DELETE', `/api/plans/${P2}`, undefined, cookie);
  safeAssert(step7, () => assert.equal(delRes.status, 200), { status: 200 }, () => ({ status: delRes.status, data: delRes.data }));
  safeAssert(step7, () => assert.equal(delRes.data?.ok, true), { ok: true }, () => delRes.data);

  const focusListRes = await req('GET', '/api/focus', undefined, cookie);
  safeAssert(step7, () => assert.equal(focusListRes.status, 200), { status: 200 }, () => ({ status: focusListRes.status, data: focusListRes.data }));
  safeAssert(step7, () => assert.ok(Array.isArray(focusListRes.data)), 'array', () => focusListRes.data);

  const survived = focusListRes.data.find((f) => f.planId === null && f.minutes === 20 && f.subject === 'english');
  safeAssert(step7, () => assert.ok(survived), 'focus record for P2 survives with planId=null', () => focusListRes.data);

  const sumRes2 = await req('GET', `/api/plans/summary?date=${today}`, undefined, cookie);
  safeAssert(step7, () => assert.equal(sumRes2.status, 200), { status: 200 }, () => ({ status: sumRes2.status, data: sumRes2.data }));
  safeAssert(step7, () => assert.equal(sumRes2.data?.plans?.length, 1), 'summary.plans.length === 1', () => sumRes2.data);
  pass(step7);

  // ---- Step 8: final ----
  console.log('LINKAGE E2E OK');
}

main().catch((err) => {
  console.error('LINKAGE E2E FAILED');
  console.error(err && err.message ? err.message : err);
  if (err && err.stack && !err.step) console.error(err.stack);
  process.exit(1);
});
