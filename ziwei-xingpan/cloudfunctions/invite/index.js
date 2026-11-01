'use strict';

// invite: invite codes, binding, success settlement, poster QR placeholder.
// Actions:
//   info {} -> { inviteCode, successCount, nextTier, grantedTiers }
//   bind { code } -> bind the caller to an inviter (once, never self,
//     never same device as the inviter); grants the invitee +50 at bind.
//   settle {} -> for each pending invite of this inviter, if the invitee
//     now has at least one chart in `charts`, mark it successful, grant
//     the inviter +100, and grant newly reached tiers (3->7d Pro,
//     10->30d Pro, 30->30d Max). Idempotent via flags on the invite doc.
//   qrcode {} -> real wxacode.getUnlimited attempt; on failure returns
//     a placeholder status (never a fake fileID). The client draws the
//     poster with the returned fileID, or shows the placeholder note.
// Success rule (per brief): an invite only counts once the invitee has
// completed a real chart. Same WeChat account / same device counts once:
// bind is rejected for self and same-device pairs, and re-binding is
// rejected once invitedBy is set.

const cloud = require('wx-server-sdk');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { getUser, appendLedger, getMembership, upsertMembership } = require('./shared/db-helpers');
const { dayKey, EARN_RULES } = require('./shared/points');
const { newlyEarnedTiers, nextTier } = require('./shared/invite');
const { grantTier } = require('./shared/membership');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

async function countSuccess(inviterOpenid) {
  const res = await db.collection('invites')
    .where({ inviterOpenid: inviterOpenid, status: 'success' }).count();
  return res.total || 0;
}

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
    if (action === 'info') {
      const successCount = await countSuccess(openid);
      const granted = user.grantedInviteTiers || [];
      return ok({
        inviteCode: user.inviteCode || '',
        successCount: successCount,
        nextTier: nextTier(successCount),
        grantedTiers: granted
      });
    }
    if (action === 'bind') {
      const code = String(event.code || '').trim().toUpperCase();
      if (!code) {
        return fail('INVALID_PARAMS', '邀请码必填');
      }
      if (user.invitedBy) {
        return fail('ALREADY_BOUND', '已绑定过邀请人，不可重复绑定');
      }
      if (user.inviteCode === code) {
        return fail('SELF_INVITE', '不能绑定自己的邀请码');
      }
      const inviterRes = await db.collection('users').where({ inviteCode: code }).limit(1).get();
      if (!inviterRes.data || inviterRes.data.length === 0) {
        return fail('INVITE_CODE_NOT_FOUND', '邀请码不存在');
      }
      const inviter = inviterRes.data[0];
      if (user.deviceFingerprint && inviter.deviceFingerprint &&
        user.deviceFingerprint === inviter.deviceFingerprint) {
        return fail('SAME_DEVICE', '同一设备只计一次邀请');
      }
      const now = new Date();
      await db.collection('invites').add({
        data: {
          inviterOpenid: inviter.openid, inviteeOpenid: openid,
          inviteCode: code, status: 'pending',
          inviteeBonusGranted: false, inviterRewardGranted: false,
          tiersGranted: [], createdAt: now, updatedAt: now
        }
      });
      await db.collection('users').doc(openid).update({
        data: { invitedBy: inviter.openid, updatedAt: now }
      });
      // Invitee +50 at bind (registration); inviter rewards wait for success.
      await appendLedger(db, {
        openid: openid, type: 'earn', rule: 'inviteeBonus',
        delta: EARN_RULES.inviteeBonus.delta, dayKey: dayKey(),
        deviceFingerprint: user.deviceFingerprint || ''
      });
      await db.collection('invites').where({ inviteeOpenid: openid, status: 'pending' })
        .update({ data: { inviteeBonusGranted: true, updatedAt: new Date() } });
      return ok({ inviterOpenid: inviter.openid, inviteeBonus: 50 });
    }
    if (action === 'settle') {
      const pending = await db.collection('invites')
        .where({ inviterOpenid: openid, status: 'pending' }).get();
      let newlySuccess = 0;
      for (const inv of pending.data) {
        const charts = await db.collection('charts')
          .where({ openid: inv.inviteeOpenid }).limit(1).get();
        if (!charts.data || charts.data.length === 0) {
          continue;
        }
        newlySuccess++;
        await db.collection('invites').doc(inv._id).update({
          data: { status: 'success', updatedAt: new Date() }
        });
        if (!inv.inviterRewardGranted) {
          await appendLedger(db, {
            openid: openid, type: 'earn', rule: 'invite',
            delta: EARN_RULES.invite.delta, dayKey: dayKey(),
            deviceFingerprint: user.deviceFingerprint || ''
          });
          await db.collection('invites').doc(inv._id).update({
            data: { inviterRewardGranted: true, updatedAt: new Date() }
          });
        }
      }
      const successCount = await countSuccess(openid);
      // Grant tiers not yet granted, recorded on the inviter's user doc
      // via a marker list kept on the newest success docs is fragile, so
      // tiers are tracked on the inviter user record itself.
      const grantedBefore = user.grantedInviteTiers || [];
      const fresh = newlyEarnedTiers(successCount, grantedBefore);
      const grantedNow = [];
      for (const tier of fresh) {
        const existing = await getMembership(db, openid);
        // No-downgrade rule (see shared/membership.js grantTier): a Pro
        // reward never knocks an active Max membership down to Pro.
        const granted = grantTier(existing, tier.tier, tier.days);
        await upsertMembership(db, openid, granted.tier, granted.expiresAt, false);
        grantedNow.push(tier);
      }
      if (fresh.length > 0) {
        const allGranted = grantedBefore.concat(fresh.map(function (t) { return t.count; }));
        await db.collection('users').doc(openid).update({
          data: { grantedInviteTiers: allGranted, updatedAt: new Date() }
        });
      }
      return ok({
        newlySuccess: newlySuccess, successCount: successCount,
        tiersGrantedNow: grantedNow, nextTier: nextTier(successCount)
      });
    }
    if (action === 'qrcode') {
      try {
        const result = await cloud.openapi.wxacode.getUnlimited({
          scene: 'i=' + openid,
          page: 'pages/index/index',
          width: 430,
          checkPath: false
        });
        const upload = await cloud.uploadFile({
          cloudPath: 'invite-qrcode/' + openid + '-' + Date.now() + '.jpg',
          fileContent: result.buffer
        });
        return ok({ fileID: upload.fileID, placeholder: false });
      } catch (e) {
        return ok({
          placeholder: true,
          message: '小程序码接口暂不可用（待 AppID / 环境配置就绪后重试），未返回真实 fileID。',
          error: e.message
        });
      }
    }
    return fail('UNKNOWN_ACTION', '未知 action: ' + String(action));
  } catch (e) {
    console.error('invite failed', e);
    return fail('INVITE_FAILED', e.message || '邀请操作失败');
  }
};
