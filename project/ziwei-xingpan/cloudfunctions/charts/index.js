'use strict';

// charts: CRUD for the user's chart history + set-default + delete.
// The backend only stores charts: the client casts the chart and uploads
// the result. The server computes chartHash from the normalized birth
// parameters so AI cache keys are stable regardless of key order.
// Actions:
//   list   {} -> user's charts, default first, newest first
//   get    { chartId }
//   create { name, birthParams, chartData } -> chart (chartHash computed)
//   update { chartId, name?, birthParams?, chartData? }
//   remove { chartId }
//   setDefault { chartId }
// Ownership is enforced on every action: doc.openid must equal OPENID.

const cloud = require('wx-server-sdk');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { chartHash } = require('./shared/hash');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();
const _ = db.command;

async function loadOwned(openid, chartId) {
  if (!chartId) {
    return null;
  }
  const res = await db.collection('charts').doc(String(chartId)).get()
    .catch(function () { return null; });
  if (!res || !res.data || res.data.openid !== openid) {
    return null;
  }
  return res.data;
}

exports.main = async (event, context) => {
  try {
    const wxContext = cloud.getWXContext();
    const openid = requireOpenid(wxContext);
    if (!openid) {
      return fail('NOT_LOGGED_IN', '无法获取微信登录态，请先调用 login');
    }
    const action = event.action;
    if (action === 'list') {
      const res = await db.collection('charts').where({ openid: openid })
        .orderBy('isDefault', 'desc').orderBy('updatedAt', 'desc').limit(100).get();
      return ok({ charts: res.data });
    }
    if (action === 'get') {
      const chart = await loadOwned(openid, event.chartId);
      if (!chart) {
        return fail('CHART_NOT_FOUND', '命盘不存在或不属于当前用户');
      }
      return ok({ chart: chart });
    }
    if (action === 'create') {
      if (!event.birthParams || typeof event.birthParams !== 'object' || !event.chartData) {
        return fail('INVALID_PARAMS', 'birthParams 与 chartData 均为必填');
      }
      const now = new Date();
      const doc = {
        openid: openid,
        name: typeof event.name === 'string' ? event.name.slice(0, 64) : '我的命盘',
        birthParams: event.birthParams,
        chartData: event.chartData,
        chartHash: chartHash(event.birthParams),
        isDefault: false,
        createdAt: now,
        updatedAt: now
      };
      const added = await db.collection('charts').add({ data: doc });
      return ok({ chartId: added._id, chart: Object.assign({ _id: added._id }, doc) });
    }
    if (action === 'update') {
      const chart = await loadOwned(openid, event.chartId);
      if (!chart) {
        return fail('CHART_NOT_FOUND', '命盘不存在或不属于当前用户');
      }
      const patch = { updatedAt: new Date() };
      if (typeof event.name === 'string') { patch.name = event.name.slice(0, 64); }
      if (event.birthParams && typeof event.birthParams === 'object') {
        patch.birthParams = event.birthParams;
        patch.chartHash = chartHash(event.birthParams);
      }
      if (event.chartData) { patch.chartData = event.chartData; }
      await db.collection('charts').doc(String(event.chartId)).update({ data: patch });
      return ok({ chartId: event.chartId });
    }
    if (action === 'remove') {
      const chart = await loadOwned(openid, event.chartId);
      if (!chart) {
        return fail('CHART_NOT_FOUND', '命盘不存在或不属于当前用户');
      }
      await db.collection('charts').doc(String(event.chartId)).remove();
      return ok({ chartId: event.chartId, removed: true });
    }
    if (action === 'setDefault') {
      const chart = await loadOwned(openid, event.chartId);
      if (!chart) {
        return fail('CHART_NOT_FOUND', '命盘不存在或不属于当前用户');
      }
      const defaults = await db.collection('charts')
        .where({ openid: openid, isDefault: true }).get();
      for (const item of defaults.data) {
        if (item._id !== String(event.chartId)) {
          await db.collection('charts').doc(item._id).update({
            data: { isDefault: false, updatedAt: new Date() }
          });
        }
      }
      await db.collection('charts').doc(String(event.chartId)).update({
        data: { isDefault: true, updatedAt: new Date() }
      });
      return ok({ chartId: event.chartId, isDefault: true });
    }
    return fail('UNKNOWN_ACTION', '未知 action: ' + String(action));
  } catch (e) {
    console.error('charts failed', e);
    return fail('CHARTS_FAILED', e.message || '命盘操作失败');
  }
};
