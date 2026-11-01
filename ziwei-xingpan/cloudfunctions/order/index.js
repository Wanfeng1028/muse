'use strict';

// order: create order records + return wx.requestPayment parameters via
// CloudBase cloudPay, and receive the payment callback.
// Actions (client calls):
//   create { plan }       -> order + payment (or PAY_NOT_CONFIGURED)
//   query  { orderId }    -> order + live cloudPay status when configured
//   close  { orderId }    -> close a pending order (cloudPay, >=5 min old)
//   list   {}             -> user's orders, newest first
// Pay callback (WeChat calls this function directly, NOT via the client):
//   the event carries returnCode/outTradeNo (see cloudPay docs). The
//   unifiedOrder call sets functionName='order' and envId from config, so
//   this same function receives the callback. It must return { errcode: 0 }
//   or WeChat keeps retrying for up to two days.
// Prices/plans come from the `configs` pricing doc, never from literals
// in this file's logic (the seed module is only the unseeded fallback).
// Missing merchant/env config -> explicit PAY_NOT_CONFIGURED, never fake.

const cloud = require('wx-server-sdk');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { getConfigDoc, getMembership, upsertMembership, getUser, appendLedger } = require('./shared/db-helpers');
const { grantTier } = require('./shared/membership');
const { SEED_CONFIGS } = require('./shared/config-seed');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

function payConfig() {
  return {
    subMchId: process.env.WECHAT_PAY_SUB_MCH_ID || '',
    envId: process.env.WECHAT_PAY_ENV_ID || '',
    callbackFunction: process.env.WECHAT_PAY_CALLBACK_FUNCTION || 'order'
  };
}

function outTradeNo() {
  const now = new Date();
  const stamp = now.toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);
  const rand = Math.floor(Math.random() * 1000000).toString().padStart(6, '0');
  return 'ZW' + stamp + rand;
}

async function grantMembership(openid, plan) {
  const existing = await getMembership(db, openid);
  // No-downgrade rule: buying Pro while Max is active keeps Max and only
  // extends its expiry (see shared/membership.js grantTier).
  const granted = grantTier(existing, plan.tier, plan.days);
  await upsertMembership(db, openid, granted.tier, granted.expiresAt, !!plan.continuous);
  return { tier: granted.tier, expiresAt: granted.expiresAt, autoRenew: !!plan.continuous };
}

// WeChat pay-callback path: event has no client action, it has returnCode.
async function handlePayCallback(event) {
  const returnCode = event.returnCode || event.return_code || '';
  const tradeNo = event.outTradeNo || event.out_trade_no || '';
  if (!tradeNo) {
    return { errcode: 0, errmsg: 'no outTradeNo' };
  }
  const found = await db.collection('orders').where({ outTradeNo: tradeNo }).limit(1).get();
  if (!found.data || found.data.length === 0) {
    return { errcode: 0, errmsg: 'order not found' };
  }
  const order = found.data[0];
  if (returnCode === 'SUCCESS' && order.status !== 'paid') {
    await db.collection('orders').doc(order._id).update({
      data: { status: 'paid', paidAt: new Date(), updatedAt: new Date() }
    });
    const pricing = await getConfigDoc(db, 'pricing', SEED_CONFIGS);
    // Points are locked at purchase time: the callback prefers the
    // order's stored pointsGrant (written by create) and only falls back
    // to the current pricing doc for orders created before that field
    // existed. Recomputing from the live doc would over/under-credit
    // the user if an admin changed prices between create and pay.
    if (order.plan === 'recharge') {
      const rate = (pricing.doc && pricing.doc.recharge && pricing.doc.recharge.pointsPerYuan) || 50;
      const points = typeof order.pointsGrant === 'number' ? order.pointsGrant : (order.yuan || 0) * rate;
      if (points > 0) {
        await appendLedger(db, { openid: order.openid, rule: 'recharge', delta: points, orderId: order._id, yuan: order.yuan });
      }
    } else {
      const plan = pricing.doc && pricing.doc.plans ? pricing.doc.plans[order.plan] : null;
      if (plan) {
        await grantMembership(order.openid, plan);
        const grant = typeof order.pointsGrant === 'number' ? order.pointsGrant : plan.pointsGrant;
        if (grant > 0) {
          await appendLedger(db, { openid: order.openid, rule: 'membership', delta: grant, plan: order.plan, orderId: order._id });
        }
      }
    }
  } else if (returnCode !== 'SUCCESS' && order.status === 'pending') {
    await db.collection('orders').doc(order._id).update({
      data: { status: 'failed', updatedAt: new Date() }
    });
  }
  return { errcode: 0, errmsg: '' };
}

exports.main = async (event, context) => {
  try {
    // Pay callback arrives without a client action; handle it first.
    if (event && !event.action && (event.outTradeNo || event.out_trade_no)) {
      return await handlePayCallback(event);
    }
    const wxContext = cloud.getWXContext();
    const openid = requireOpenid(wxContext);
    if (!openid) {
      return fail('NOT_LOGGED_IN', '无法获取微信登录态，请先调用 login');
    }
    const action = event.action;
    if (action === 'list') {
      const res = await db.collection('orders').where({ openid: openid })
        .orderBy('createdAt', 'desc').limit(50).get();
      return ok({ orders: res.data });
    }
    if (action === 'create') {
      // Minor gate: paid membership purchase is refused for minors.
      // The user record is required here (call login first, per API doc);
      // without it the gate cannot be evaluated, so the order is refused
      // rather than silently allowed.
      const buyer = await getUser(db, openid);
      if (!buyer) {
        return fail('USER_NOT_FOUND', '用户不存在，请先调用 login');
      }
      if (buyer.minor) {
        return fail('MINOR_PURCHASE_BLOCKED', '未成年人不可购买付费会员，免费功能仍可正常使用');
      }
      const pricing = await getConfigDoc(db, 'pricing', SEED_CONFIGS);
      // Plan 'recharge' is standalone points recharge: variable yuan
      // amount, min 1 yuan, points = yuan * recharge.pointsPerYuan.
      // It goes through the same minor gate above as membership plans.
      let plan;
      let yuan = 0;
      if (event.plan === 'recharge') {
        const rechargeCfg = (pricing.doc && pricing.doc.recharge) || { pointsPerYuan: 50, minYuan: 1 };
        yuan = Math.floor(Number(event.yuan) || 0);
        if (yuan < (rechargeCfg.minYuan || 1)) {
          return fail('INVALID_RECHARGE_AMOUNT', '充值金额须为 ' + (rechargeCfg.minYuan || 1) + ' 元起的整数元', { fromSeed: pricing.fromSeed });
        }
        plan = { tier: '', days: 0, fen: yuan * 100, pointsGrant: yuan * (rechargeCfg.pointsPerYuan || 50), billingCycle: 'recharge', continuous: false };
      } else {
        if (!pricing.doc || !pricing.doc.plans || !pricing.doc.plans[event.plan]) {
          return fail('UNKNOWN_PLAN', '未知套餐: ' + String(event.plan), { fromSeed: pricing.fromSeed });
        }
        plan = pricing.doc.plans[event.plan];
      }
      const tradeNo = outTradeNo();
      const now = new Date();
      const orderDoc = {
        openid: openid, plan: event.plan, tier: plan.tier,
        days: plan.days, continuous: !!plan.continuous,
        amountFen: plan.fen, outTradeNo: tradeNo,
        status: 'pending', createdAt: now, updatedAt: now
      };
      if (event.plan === 'recharge') {
        orderDoc.yuan = yuan;
      }
      // Stored for the pay callback: the granted points are locked at
      // purchase time, not recomputed from the live pricing doc at pay.
      orderDoc.pointsGrant = plan.pointsGrant;
      const added = await db.collection('orders').add({ data: orderDoc });
      const cfg = payConfig();
      if (!cfg.subMchId || !cfg.envId) {
        return fail('PAY_NOT_CONFIGURED',
          '微信支付未配置：请在云函数环境配置中设置 WECHAT_PAY_SUB_MCH_ID 与 WECHAT_PAY_ENV_ID 后重试，订单已创建为待支付状态。',
          { orderId: added._id, outTradeNo: tradeNo, amountFen: plan.fen, fromSeed: pricing.fromSeed });
      }
      const res = await cloud.cloudPay.unifiedOrder({
        body: event.plan === 'recharge' ? '星命盘-积分充值-' + yuan + '元' : '星命盘-' + plan.tier + '-' + plan.days + '天',
        outTradeNo: tradeNo,
        spbillCreateIp: '127.0.0.1',
        subMchId: cfg.subMchId,
        totalFee: plan.fen,
        envId: cfg.envId,
        functionName: cfg.callbackFunction
      });
      if (!res || !res.payment) {
        return fail('PAY_UNIFIED_ORDER_FAILED', '统一下单未返回支付参数，请稍后重试',
          { orderId: added._id, outTradeNo: tradeNo });
      }
      return ok({
        orderId: added._id, outTradeNo: tradeNo, amountFen: plan.fen,
        payment: res.payment, fromSeed: pricing.fromSeed
      });
    }
    if (action === 'query') {
      const order = await db.collection('orders').doc(String(event.orderId)).get()
        .catch(function () { return null; });
      if (!order || !order.data || order.data.openid !== openid) {
        return fail('ORDER_NOT_FOUND', '订单不存在或不属于当前用户');
      }
      const cfg = payConfig();
      let live = null;
      if (cfg.subMchId) {
        try {
          live = await cloud.cloudPay.queryOrder({ outTradeNo: order.data.outTradeNo });
        } catch (e) {
          live = { error: e.message };
        }
      }
      return ok({ order: order.data, live: live });
    }
    if (action === 'close') {
      const order = await db.collection('orders').doc(String(event.orderId)).get()
        .catch(function () { return null; });
      if (!order || !order.data || order.data.openid !== openid) {
        return fail('ORDER_NOT_FOUND', '订单不存在或不属于当前用户');
      }
      if (order.data.status !== 'pending') {
        return fail('ORDER_NOT_PENDING', '只有待支付订单可以关闭');
      }
      const cfg = payConfig();
      if (!cfg.subMchId) {
        return fail('PAY_NOT_CONFIGURED', '微信支付未配置，无法调用关闭订单');
      }
      await cloud.cloudPay.closeOrder({ outTradeNo: order.data.outTradeNo });
      await db.collection('orders').doc(String(event.orderId)).update({
        data: { status: 'closed', updatedAt: new Date() }
      });
      return ok({ orderId: event.orderId, status: 'closed' });
    }
    return fail('UNKNOWN_ACTION', '未知 action: ' + String(action));
  } catch (e) {
    console.error('order failed', e);
    return fail('ORDER_FAILED', e.message || '订单操作失败');
  }
};
