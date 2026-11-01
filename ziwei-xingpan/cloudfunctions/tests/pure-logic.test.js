'use strict';

// Pure-logic tests for the cloud backend. No wx-server-sdk, no network,
// no database: only the shared rule modules. Run:
//   node cloudfunctions/tests/pure-logic.test.js
// Exit code 0 = all pass, 1 = any failure.

const assert = require('assert');
const hash = require('../_shared/hash');
const points = require('../_shared/points');
const invite = require('../_shared/invite');
const membership = require('../_shared/membership');
const quota = require('../_shared/quota');
const minor = require('../_shared/minor');
const botsrouter = require('../_shared/botsrouter');
const seed = require('../_shared/config-seed');

let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed++;
    console.log('PASS ' + name);
  } catch (e) {
    console.error('FAIL ' + name + ': ' + e.message);
    process.exitCode = 1;
  }
}

// --- chart hash: key order must not change the hash ---
check('chartHash is key-order independent', function () {
  const a = hash.chartHash({ year: 1998, month: 5, hour: '午时', gender: 1 });
  const b = hash.chartHash({ gender: 1, hour: '午时', month: 5, year: 1998 });
  assert.strictEqual(a, b);
  assert.strictEqual(a.length, 64);
});

// --- AI cache key: same chart + type hits, different type misses ---
check('aiCacheKey varies by interpret type only', function () {
  const params = { year: 1998, month: 5 };
  assert.strictEqual(hash.aiCacheKey(params, 'full'), hash.aiCacheKey(params, 'full'));
  assert.notStrictEqual(hash.aiCacheKey(params, 'full'), hash.aiCacheKey(params, 'wealth'));
  assert.notStrictEqual(hash.aiCacheKey(params, 'full'), hash.aiCacheKey({ year: 1999, month: 5 }, 'full'));
});

// --- image cache key: prompt hash vs daily date+chart ---
check('imageCacheKey prompt vs daily differ', function () {
  const p = hash.imageCacheKey({ prompt: 'poster bg' });
  const d = hash.imageCacheKey({ chartParams: { year: 1998 }, dateKey: '2026-11-01' });
  assert.notStrictEqual(p, d);
  assert.strictEqual(d, hash.imageCacheKey({ chartParams: { year: 1998 }, dateKey: '2026-11-01' }));
  assert.notStrictEqual(d, hash.imageCacheKey({ chartParams: { year: 1998 }, dateKey: '2026-11-02' }));
});

// --- points: daily caps ---
check('points signin capped at 1 per day', function () {
  const today = points.dayKey(new Date('2026-11-01T02:00:00Z'));
  const entries = [{ rule: 'signin', dayKey: today }];
  assert.strictEqual(points.canEarn('signin', { today: today, todayEntries: entries }).allowed, false);
  assert.strictEqual(points.canEarn('signin', { today: today, todayEntries: [] }).allowed, true);
});
check('points video capped at 5 per day', function () {
  const today = '2026-11-01';
  const four = [1, 2, 3, 4].map(function () { return { rule: 'video', dayKey: today }; });
  const five = [1, 2, 3, 4, 5].map(function () { return { rule: 'video', dayKey: today }; });
  assert.strictEqual(points.canEarn('video', { today: today, todayEntries: four }).allowed, true);
  assert.strictEqual(points.canEarn('video', { today: today, todayEntries: five }).allowed, false);
});
check('points profile is once only', function () {
  assert.strictEqual(points.canEarn('profile', { alreadyClaimed: true }).allowed, false);
  assert.strictEqual(points.canEarn('profile', { alreadyClaimed: false }).allowed, true);
});
check('points spend rejects insufficient balance', function () {
  assert.strictEqual(points.canSpend('aiInterpret', 29).allowed, false);
  assert.strictEqual(points.canSpend('aiInterpret', 30).allowed, true);
  assert.strictEqual(points.canSpend('pro30d', 1499).allowed, false);
  assert.strictEqual(points.canSpend('pro30d', 1500).allowed, true);
});

// --- invite tiers ---
check('invite tiers fire at 3 / 10 / 30 and never twice', function () {
  assert.deepStrictEqual(invite.newlyEarnedTiers(2, []), []);
  assert.deepStrictEqual(invite.newlyEarnedTiers(3, []), [{ count: 3, tier: 'pro', days: 7 }]);
  assert.deepStrictEqual(invite.newlyEarnedTiers(10, [3]), [{ count: 10, tier: 'pro', days: 30 }]);
  assert.deepStrictEqual(invite.newlyEarnedTiers(30, [3, 10]), [{ count: 30, tier: 'max', days: 30 }]);
  assert.deepStrictEqual(invite.newlyEarnedTiers(30, [3, 10, 30]), []);
  assert.deepStrictEqual(invite.nextTier(9), { count: 10, tier: 'pro', days: 30 });
  assert.strictEqual(invite.nextTier(30), null);
});

// --- membership: expiry and extension ---
check('membership effective tier drops to free after expiry', function () {
  const now = new Date('2026-11-01T00:00:00Z');
  assert.strictEqual(membership.effectiveTier({ tier: 'pro', expiresAt: new Date('2026-10-31T00:00:00Z') }, now), 'free');
  assert.strictEqual(membership.effectiveTier({ tier: 'pro', expiresAt: new Date('2026-11-02T00:00:00Z') }, now), 'pro');
  assert.strictEqual(membership.effectiveTier(null, now), 'free');
});
check('membership extension builds on active expiry, else on now', function () {
  const now = new Date('2026-11-01T00:00:00Z');
  const active = membership.extendedExpiry({ expiresAt: new Date('2026-11-10T00:00:00Z') }, 7, now);
  assert.strictEqual(active.toISOString(), '2026-11-17T00:00:00.000Z');
  const expired = membership.extendedExpiry({ expiresAt: new Date('2026-10-01T00:00:00Z') }, 7, now);
  assert.strictEqual(expired.toISOString(), '2026-11-08T00:00:00.000Z');
});

// --- membership: grantTier never downgrades a higher active tier ---
check('grantTier keeps Max when granting Pro, extends expiry', function () {
  const now = new Date('2026-11-01T00:00:00Z');
  const max = { tier: 'max', expiresAt: new Date('2026-11-10T00:00:00Z') };
  const g = membership.grantTier(max, 'pro', 7, now);
  assert.strictEqual(g.tier, 'max');
  assert.strictEqual(g.keptHigherTier, true);
  assert.strictEqual(g.expiresAt.toISOString(), '2026-11-17T00:00:00.000Z');
});
check('grantTier upgrades Pro to Max', function () {
  const now = new Date('2026-11-01T00:00:00Z');
  const pro = { tier: 'pro', expiresAt: new Date('2026-11-10T00:00:00Z') };
  const g = membership.grantTier(pro, 'max', 30, now);
  assert.strictEqual(g.tier, 'max');
  assert.strictEqual(g.keptHigherTier, false);
  assert.strictEqual(g.expiresAt.toISOString(), '2026-12-10T00:00:00.000Z');
});
check('grantTier on expired membership grants fresh', function () {
  const now = new Date('2026-11-01T00:00:00Z');
  const expired = { tier: 'max', expiresAt: new Date('2026-10-01T00:00:00Z') };
  const g = membership.grantTier(expired, 'pro', 7, now);
  assert.strictEqual(g.tier, 'pro');
  assert.strictEqual(g.expiresAt.toISOString(), '2026-11-08T00:00:00.000Z');
});
// --- minor gate: resolveMinor ---
check('minor gate: birthYear implies minor under 18', function () {
  const now = new Date('2026-11-01T00:00:00Z');
  assert.strictEqual(minor.resolveMinor(null, { birthYear: 2010 }, now).minor, true);
  assert.strictEqual(minor.resolveMinor(null, { birthYear: 2008 }, now).minor, false);
  assert.strictEqual(minor.resolveMinor(null, { birthYear: 2009 }, now).minor, true);
});
check('minor gate: explicit isMinor sticks over adult birthYear', function () {
  const now = new Date('2026-11-01T00:00:00Z');
  assert.strictEqual(minor.resolveMinor(null, { birthYear: 1990, isMinor: true }, now).minor, true);
});
check('minor gate: adult birthYear clears a stored minor flag, silence keeps it', function () {
  const now = new Date('2026-11-01T00:00:00Z');
  const stored = { minor: true, birthYear: 2010 };
  assert.strictEqual(minor.resolveMinor(stored, { birthYear: 1990 }, now).minor, false);
  assert.strictEqual(minor.resolveMinor(stored, {}, now).minor, true);
  assert.strictEqual(minor.resolveMinor(null, {}, now).minor, false);
});
check('minor gate: invalid birthYear is ignored', function () {
  const now = new Date('2026-11-01T00:00:00Z');
  assert.strictEqual(minor.resolveMinor(null, { birthYear: 1800 }, now).birthYear, null);
  assert.strictEqual(minor.resolveMinor(null, { birthYear: '2010' }, now).birthYear, null);
  assert.strictEqual(minor.isMinorByBirthYear(2010, 2026), true);
  assert.strictEqual(minor.isMinorByBirthYear(1800, 2026), null);
});

check('quota degrades at 85 percent by default', function () {
  assert.strictEqual(quota.shouldDegrade(850000, 1000000), true);
  assert.strictEqual(quota.shouldDegrade(849999, 1000000), false);
  assert.strictEqual(quota.shouldDegrade(900000, 1000000, 95), false);
  assert.strictEqual(quota.shouldDegrade(0, 0), false);
});

// --- botsrouter request shape (no network call) ---
check('botsrouter chat request shape', function () {
  const req = botsrouter.buildChatRequest('deepseek-v4.1-flash', [{ role: 'user', content: 'hi' }]);
  assert.strictEqual(req.model, 'deepseek-v4.1-flash');
  assert.strictEqual(req.messages[0].content, 'hi');
  const parsed = botsrouter.parseChatResponse({
    choices: [{ message: { content: 'hello' } }],
    usage: { total_tokens: 42 }, model: 'deepseek-v4.1-flash'
  });
  assert.strictEqual(parsed.text, 'hello');
  assert.strictEqual(parsed.usage.total_tokens, 42);
});

// --- config seed integrity: prices match PLAN, no real secrets ---
check('config seed prices match PLAN and contain only placeholders', function () {
  const pricing = seed.SEED_CONFIGS.find(function (d) { return d._id === 'pricing'; });
  assert.strictEqual(pricing.plans.proMonthly.fen, 1800);
  assert.strictEqual(pricing.plans.proContinuous.fen, 1500);
  assert.strictEqual(pricing.plans.maxMonthly.fen, 3800);
  assert.strictEqual(pricing.plans.maxContinuous.fen, 3200);
  const ads = seed.SEED_CONFIGS.find(function (d) { return d._id === 'ads'; });
  Object.keys(ads).forEach(function (k) {
    if (typeof ads[k] === 'string' && k !== '_id') {
      assert.ok(ads[k].indexOf('PLACEHOLDER') === 0, 'ad unit ' + k + ' must be a placeholder');
    }
  });
  const ai = seed.SEED_CONFIGS.find(function (d) { return d._id === 'ai'; });
  assert.strictEqual(ai.botsrouterChatModel, 'deepseek-v4.1-flash');
  assert.strictEqual(ai.cloudbaseChatModel, 'deepseek-v4-flash');
  const dump = JSON.stringify(seed.SEED_CONFIGS);
  assert.ok(dump.indexOf('sk-') === -1, 'seed must not contain any API key');
});

console.log(passed + ' pure-logic checks passed');
