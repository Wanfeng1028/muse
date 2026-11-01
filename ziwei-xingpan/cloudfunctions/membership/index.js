'use strict';

// membership: read membership status / cancel auto-renew.
// Actions:
//   status {} -> { tier (effective), rawTier, expiresAt, autoRenew }
//   cancelAutoRenew {} -> autoRenew=false; tier stays until expiresAt,
//     then drops to free (see shared/membership.js effectiveTier).
// Granting / extending memberships happens in order (paid) and invite
// (tier rewards) and points (pro7d/pro30d redemption), never here.

const cloud = require('wx-server-sdk');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { getMembership } = require('./shared/db-helpers');
const { effectiveTier } = require('./shared/membership');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

exports.main = async (event, context) => {
  try {
    const wxContext = cloud.getWXContext();
    const openid = requireOpenid(wxContext);
    if (!openid) {
      return fail('NOT_LOGGED_IN', '无法获取微信登录态，请先调用 login');
    }
    const action = event.action || 'status';
    if (action === 'status') {
      const membership = await getMembership(db, openid);
      return ok({
        tier: effectiveTier(membership),
        rawTier: membership ? membership.tier : 'free',
        expiresAt: membership ? membership.expiresAt : null,
        autoRenew: membership ? !!membership.autoRenew : false
      });
    }
    if (action === 'cancelAutoRenew') {
      const membership = await getMembership(db, openid);
      if (!membership) {
        return fail('NO_MEMBERSHIP', '当前无会员记录');
      }
      await db.collection('memberships').doc(openid).update({
        data: { autoRenew: false, updatedAt: new Date() }
      });
      return ok({
        tier: effectiveTier(membership),
        rawTier: membership.tier,
        expiresAt: membership.expiresAt,
        autoRenew: false,
        note: '取消续费已生效，当前周期到期后降回普通。'
      });
    }
    return fail('UNKNOWN_ACTION', '未知 action: ' + String(action));
  } catch (e) {
    console.error('membership failed', e);
    return fail('MEMBERSHIP_FAILED', e.message || '会员查询失败');
  }
};
