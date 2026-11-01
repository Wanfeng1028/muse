'use strict';

// points: append-only ledger (pointsLedger) + balance + redemption.
// pointsLedger is only ever added to, never updated or removed, in code
// and by the security rules the client must not write it directly.
// Actions:
//   balance {} -> { balance, ledger (latest 50) }
//   earn { rule, deviceFingerprint? }
//     rule: signin | video | share | profile
//     (invite / inviteeBonus are granted by the invite function only)
//   spend { rule, chartId? }
//     rule: advancedInterpret | aiInterpret | pro7d | pro30d
//     pro7d/pro30d also extend the membership (7 / 30 days of Pro).
// Anti-brush: signin/share/video are capped per openid per day
// (Asia/Shanghai day key); profile is once per user (flag on users);
// earn calls also require the caller device fingerprint to match the
// fingerprint recorded at login when both are present.

const cloud = require('wx-server-sdk');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { getUser, appendLedger, getMembership, upsertMembership } = require('./shared/db-helpers');
const { EARN_RULES, SPEND_RULES, dayKey, canEarn, canSpend } = require('./shared/points');
const { grantTier } = require('./shared/membership');
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

exports.main = async (event, context) => {
  try {
    const wxContext = cloud.getWXContext();
    const openid = requireOpenid(wxContext);
    if (!openid) {
      return fail('NOT_LOGGED_IN', '无法获取微信登录态，请先调用 login');
    }
    const user = await getUser(db, openid);
    if (!user) {
      return fail('USER_NOT_FOUND', '用户不存在，请先调用 login');
    }
    const action = event.action;
    if (action === 'balance') {
      const res = await db.collection('pointsLedger').where({ openid: openid })
        .orderBy('createdAt', 'desc').limit(50).get();
      return ok({ balance: user.pointsBalance || 0, ledger: res.data });
    }
    if (action === 'earn') {
      const rule = event.rule;
      const def = EARN_RULES[rule];
      if (!def || (rule === 'invite' || rule === 'inviteeBonus')) {
        return fail('INVALID_RULE', '该规则不接受客户端直接领取: ' + String(rule));
      }
      if (user.deviceFingerprint && event.deviceFingerprint &&
        user.deviceFingerprint !== event.deviceFingerprint) {
        return fail('DEVICE_MISMATCH', '设备指纹与登录设备不一致，拒绝领取');
      }
      const today = dayKey();
      let todayEntries = [];
      if (def.dailyLimit > 0) {
        const res = await db.collection('pointsLedger')
          .where({ openid: openid, rule: rule, dayKey: today }).get();
        todayEntries = res.data;
      }
      const check = canEarn(rule, {
        today: today, todayEntries: todayEntries,
        alreadyClaimed: rule === 'profile' ? !!user.profileBonusClaimed : false
      });
      if (!check.allowed) {
        return fail(check.reason, '无法领取: ' + check.reason);
      }
      const fingerprint = event.deviceFingerprint || user.deviceFingerprint || '';
      await appendLedger(db, {
        openid: openid, type: 'earn', rule: rule, delta: def.delta,
        dayKey: today, deviceFingerprint: fingerprint
      });
      if (rule === 'profile') {
        await db.collection('users').doc(openid).update({
          data: { profileBonusClaimed: true, updatedAt: new Date() }
        });
      }
      const after = await getUser(db, openid);
      return ok({ rule: rule, delta: def.delta, balance: after.pointsBalance || 0 });
    }
    if (action === 'spend') {
      const rule = event.rule;
      const def = SPEND_RULES[rule];
      if (!def) {
        return fail('INVALID_RULE', '未知消费规则: ' + String(rule));
      }
      const check = canSpend(rule, user.pointsBalance || 0);
      if (!check.allowed) {
        return fail(check.reason, '积分不足');
      }
      const today = dayKey();
      await appendLedger(db, {
        openid: openid, type: 'spend', rule: rule, delta: def.delta,
        dayKey: today, deviceFingerprint: user.deviceFingerprint || '',
        chartId: event.chartId || ''
      });
      let membership = null;
      if (rule === 'pro7d' || rule === 'pro30d') {
        const days = rule === 'pro7d' ? 7 : 30;
        const existing = await getMembership(db, openid);
        // No-downgrade rule: redeeming Pro while Max is active keeps Max
        // and only extends its expiry (see shared/membership.js grantTier).
        const granted = grantTier(existing, 'pro', days);
        membership = await upsertMembership(db, openid, granted.tier, granted.expiresAt, false);
      }
      const after = await getUser(db, openid);
      return ok({
        rule: rule, delta: def.delta, balance: after.pointsBalance || 0,
        membership: membership
      });
    }
    return fail('UNKNOWN_ACTION', '未知 action: ' + String(action));
  } catch (e) {
    console.error('points failed', e);
    return fail('POINTS_FAILED', e.message || '积分操作失败');
  }
};
