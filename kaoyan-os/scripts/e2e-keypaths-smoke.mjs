#!/usr/bin/env node
// 覆盖口径：7 步关键路径冒烟：注册登录、备份导出、备份合并导入、非法备份导入、单词播种幂等、热力图、周报。
import assert from 'node:assert/strict';

const BASE = process.env.E2E_BASE || 'http://127.0.0.1:3123';

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
    try { data = JSON.parse(text); } catch { data = text; }
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
  try { fn(); } catch (e) {
    let actual;
    try { actual = actualFn ? actualFn() : undefined; } catch { actual = '<unavailable>'; }
    fail(step, expected, actual);
  }
}

async function main() {
  try {
    const username = `e2e_${Date.now().toString(36)}`;
    const reg = await req('POST', '/api/auth/register', { username, password: 'e2ePassw0rd!' });
    safeAssert(
      'step1 register',
      () => assert.equal(reg.status, 201),
      201,
      () => reg.status,
    );

    const login = await req('POST', '/api/auth/login', { username, password: 'e2ePassw0rd!' });
    safeAssert(
      'step1 login',
      () => assert.equal(login.status, 200),
      200,
      () => login.status,
    );

    const cookie = (login.headers.get('set-cookie') || '').split(';')[0].trim();
    safeAssert(
      'step1 cookie',
      () => assert.match(cookie, /^kaoyan_session=.+$/),
      'kaoyan_session=xxx',
      () => cookie,
    );
    pass('step1 register/login');

    const backup = await req('GET', '/api/backup/export', undefined, cookie);
    safeAssert(
      'step2 backup export status',
      () => assert.equal(backup.status, 200),
      200,
      () => backup.status,
    );
    safeAssert(
      'step2 backup export format',
      () => assert.equal(backup.data?.format, 'kaoyan-backup'),
      'kaoyan-backup',
      () => backup.data?.format,
    );
    safeAssert(
      'step2 backup export tables',
      () => {
        assert.ok(backup.data && typeof backup.data.tables === 'object');
        assert.ok(backup.data.tables !== null);
        assert.ok(!Array.isArray(backup.data.tables));
        assert.ok(Object.keys(backup.data.tables).length >= 7);
      },
      'object with at least 7 keys',
      () => backup.data?.tables,
    );
    pass('step2 backup export');

    const merge = await req('POST', '/api/backup/import', { data: backup.data, mode: 'merge' }, cookie);
    safeAssert(
      'step3 backup import merge',
      () => assert.equal(merge.status, 200),
      200,
      () => merge.status,
    );
    pass('step3 backup import merge');

    const invalid = await req('POST', '/api/backup/import', { data: { format: 'x' }, mode: 'merge' }, cookie);
    safeAssert(
      'step4 backup import invalid',
      () => assert.equal(invalid.status, 400),
      400,
      () => invalid.status,
    );
    pass('step4 backup import invalid');

    const firstSeed = await req('POST', '/api/words/seed-vocab', undefined, cookie);
    safeAssert(
      'step5 words seed first status',
      () => assert.equal(firstSeed.status, 200),
      200,
      () => firstSeed.status,
    );
    safeAssert(
      'step5 words seed first imported',
      () => {
        assert.equal(typeof firstSeed.data?.imported, 'number');
        assert.ok(firstSeed.data.imported > 0);
      },
      'number greater than 0',
      () => firstSeed.data?.imported,
    );

    const secondSeed = await req('POST', '/api/words/seed-vocab', undefined, cookie);
    safeAssert(
      'step5 words seed second status',
      () => assert.equal(secondSeed.status, 200),
      200,
      () => secondSeed.status,
    );
    safeAssert(
      'step5 words seed second imported',
      () => assert.equal(secondSeed.data?.imported, 0),
      0,
      () => secondSeed.data?.imported,
    );
    pass('step5 words seed idempotent');

    const heatmap = await req('GET', '/api/stats/heatmap?months=1', undefined, cookie);
    safeAssert(
      'step6 heatmap status',
      () => assert.equal(heatmap.status, 200),
      200,
      () => heatmap.status,
    );
    safeAssert(
      'step6 heatmap days',
      () => {
        assert.ok(Array.isArray(heatmap.data?.days));
        assert.equal(heatmap.data.days.length, 31);
      },
      'array with 31 days',
      () => heatmap.data?.days,
    );
    safeAssert(
      'step6 heatmap current streak',
      () => assert.equal(typeof heatmap.data?.currentStreak, 'number'),
      'number',
      () => heatmap.data?.currentStreak,
    );
    pass('step6 heatmap');

    const weekly = await req('GET', '/api/stats/weekly', undefined, cookie);
    safeAssert(
      'step7 weekly status',
      () => assert.equal(weekly.status, 200),
      200,
      () => weekly.status,
    );
    safeAssert(
      'step7 weekly data',
      () => assert.ok(weekly.data && typeof weekly.data === 'object' && !Array.isArray(weekly.data)),
      'object',
      () => weekly.data,
    );
    pass('step7 weekly');

    console.log('KEYPATHS E2E OK');
  } catch (err) {
    console.error(`[${err.step}] ${err.message}`);
    process.exit(1);
  }
}

main();
