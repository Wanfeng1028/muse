'use strict';

// login: create or update the users record for the caller's OPENID.
// Session uses the CloudBase native openid; this function invents no JWT.
// Input event: { nickname, avatarUrl, gender, deviceFingerprint, inviteCode?,
//   birthYear?, isMinor? }
//   inviteCode here is the inviter's code when the user arrived via invite;
//   binding itself is done by the invite function (see invite/index.js).
//   birthYear / isMinor feed the minor gate (see shared/minor.js):
//   declaring isMinor sticks until an adult birthYear is provided.
// Output: { code: 0, data: { openid, isNew, user } }

const cloud = require('wx-server-sdk');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { inviteCodeFromOpenid } = require('./shared/hash');
const { resolveMinor } = require('./shared/minor');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

function cleanString(value, maxLen) {
  if (typeof value !== 'string') {
    return '';
  }
  return value.slice(0, maxLen);
}

exports.main = async (event, context) => {
  try {
    const wxContext = cloud.getWXContext();
    const openid = requireOpenid(wxContext);
    if (!openid) {
      return fail('NOT_LOGGED_IN', '无法获取微信登录态，请先在小程序内登录');
    }
    const now = new Date();
    const existing = await db.collection('users').doc(openid).get()
      .catch(function () { return null; });
    const profile = {
      nickname: cleanString(event.nickname, 64),
      avatarUrl: cleanString(event.avatarUrl, 512),
      gender: [0, 1, 2].indexOf(event.gender) !== -1 ? event.gender : 0,
      deviceFingerprint: cleanString(event.deviceFingerprint, 128),
      updatedAt: now,
      lastLoginAt: now
    };
    if (existing && existing.data) {
      const patch = {};
      if (profile.nickname) { patch.nickname = profile.nickname; }
      if (profile.avatarUrl) { patch.avatarUrl = profile.avatarUrl; }
      if (profile.gender) { patch.gender = profile.gender; }
      if (profile.deviceFingerprint) { patch.deviceFingerprint = profile.deviceFingerprint; }
      // Minor gate: only a valid birthYear or an explicit isMinor=true
      // declaration touches the stored flag; anything else keeps it.
      const resolved = resolveMinor(existing.data, { birthYear: event.birthYear, isMinor: event.isMinor });
      if (resolved.birthYear !== (existing.data.birthYear || null) || resolved.minor !== !!existing.data.minor) {
        patch.birthYear = resolved.birthYear;
        patch.minor = resolved.minor;
      }
      patch.updatedAt = now;
      patch.lastLoginAt = now;
      await db.collection('users').doc(openid).update({ data: patch });
      const after = await db.collection('users').doc(openid).get();
      return ok({ openid: openid, isNew: false, user: after.data });
    }
    // New user: assign a deterministic invite code, retrying on collision.
    let ownCode = '';
    for (let attempt = 0; attempt < 5; attempt++) {
      const candidate = inviteCodeFromOpenid(openid, attempt);
      const clash = await db.collection('users').where({ inviteCode: candidate }).limit(1).get();
      if (!clash.data || clash.data.length === 0) {
        ownCode = candidate;
        break;
      }
    }
    if (!ownCode) {
      return fail('INVITE_CODE_COLLISION', '邀请码生成冲突，请重试');
    }
    const resolvedNew = resolveMinor(null, { birthYear: event.birthYear, isMinor: event.isMinor });
    const doc = Object.assign({
      _id: openid,
      openid: openid,
      inviteCode: ownCode,
      invitedBy: '',
      pointsBalance: 0,
      profileBonusClaimed: false,
      birthYear: resolvedNew.birthYear,
      minor: resolvedNew.minor,
      createdAt: now
    }, profile);
    if (!doc.nickname) { doc.nickname = '星盘用户'; }
    await db.collection('users').add({ data: doc });
    return ok({ openid: openid, isNew: true, user: doc });
  } catch (e) {
    console.error('login failed', e);
    return fail('LOGIN_FAILED', e.message || '登录失败');
  }
};
