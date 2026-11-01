'use strict';

// feedback: user feedback inbox (in-app "意见反馈" writes here).
// Actions:
//   create { content, contact? } -> feedback doc, status 'open'
//   list   {} -> the caller's own feedbacks, newest first, max 50
// No admin reply path in this phase: replies are handled by the operator
// in the cloud console / by contacting the user via `contact` when given.
// The client never fabricates a reply; an unanswered item stays 'open'.

const cloud = require('wx-server-sdk');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { getUser } = require('./shared/db-helpers');

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
    if (action === 'create') {
      const content = typeof event.content === 'string' ? event.content.trim() : '';
      if (!content || content.length > 1000) {
        return fail('INVALID_PARAMS', '反馈内容必填，且不超过 1000 字');
      }
      const contact = typeof event.contact === 'string' ? event.contact.slice(0, 128) : '';
      const now = new Date();
      const added = await db.collection('feedbacks').add({
        data: { openid: openid, content: content, contact: contact, status: 'open', createdAt: now, updatedAt: now }
      });
      return ok({ feedbackId: added._id, status: 'open' });
    }
    if (action === 'list') {
      const res = await db.collection('feedbacks').where({ openid: openid })
        .orderBy('createdAt', 'desc').limit(50).get();
      return ok({ feedbacks: res.data });
    }
    return fail('UNKNOWN_ACTION', '未知 action: ' + String(action));
  } catch (e) {
    console.error('feedback failed', e);
    return fail('FEEDBACK_FAILED', e.message || '反馈提交失败');
  }
};
