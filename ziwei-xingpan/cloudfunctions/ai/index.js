'use strict';

// ai: AI chart interpretation and chart Q&A.
// Actions:
//   interpret { chartId, interpretType }
//     Cache: aiCache keyed by sha256(normalized birth params + type).
//     Cache hit returns the stored text with cached: true and charges
//     nothing. Cache miss goes through the quota gate, then the adapter
//     (CloudBase primary, BotsRouter fallback), then stores aiCache.
//   ask { chartId, question, history? }
//     No cache (questions vary). Same quota gate and gating as interpret.
// Gating (per PLAN): Max = unlimited free; Pro = 20 free AI uses per
// calendar month, then the AI解读 points price applies; other tiers pay
// the AI解读 price (30 points) per use. Insufficient points -> error,
// never a silent free result.
// Quota gate: today's CloudBase usage (quotaLogs, provider cloudbase)
// vs the quota config budget. At >= threshold (default 85%) the call is
// forced to the BotsRouter fallback and the response says so
// (degraded: true, provider: 'botsrouter'); it never fails silently.
// Every response carries the disclaimer text.

const cloud = require('wx-server-sdk');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { getUser, getConfigDoc, appendLedger, logQuota } = require('./shared/db-helpers');
const { aiCacheKey } = require('./shared/hash');
const { dayKey, SPEND_RULES } = require('./shared/points');
const { effectiveTier } = require('./shared/membership');
const { shouldDegrade } = require('./shared/quota');
const { SEED_CONFIGS, DISCLAIMER } = require('./shared/config-seed');
const adapter = require('./shared/ai-adapter');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

const SYSTEM_PROMPT = '你是紫微斗数文化解读助手。只做传统文化学习与娱乐参考解读，'
  + '不做确定性断言，不提供改运、化解、法事建议，不构成人生决策建议。'
  + '语言简洁，分点说明，最后附上免责声明。';

async function loadChart(openid, chartId) {
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

async function monthAiUses(openid, monthKey) {
  const res = await db.collection('quotaLogs')
    .where({ openid: openid, kind: 'ai', monthKey: monthKey }).count();
  return res.total || 0;
}

async function todayCloudbaseTokens() {
  const today = dayKey();
  const res = await db.collection('quotaLogs')
    .where({ provider: 'cloudbase', dayKey: today }).get();
  let total = 0;
  res.data.forEach(function (d) { total += (d.totalTokens || 0); });
  return total;
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
    if (action !== 'interpret' && action !== 'ask') {
      return fail('UNKNOWN_ACTION', '未知 action: ' + String(action));
    }
    const chart = await loadChart(openid, event.chartId);
    if (!chart) {
      return fail('CHART_NOT_FOUND', '命盘不存在或不属于当前用户');
    }
    const aiCfg = await getConfigDoc(db, 'ai', SEED_CONFIGS);
    const quotaCfg = await getConfigDoc(db, 'quota', SEED_CONFIGS);
    const interpretType = action === 'interpret'
      ? String(event.interpretType || 'full') : 'ask';
    // Cache only for interpretations, never for open Q&A.
    if (action === 'interpret') {
      const key = aiCacheKey(chart.birthParams, interpretType);
      const hit = await db.collection('aiCache').where({ cacheKey: key }).limit(1).get();
      if (hit.data && hit.data.length > 0) {
        return ok({
          text: hit.data[0].text, cached: true, provider: hit.data[0].provider || 'cache',
          degraded: false, disclaimer: DISCLAIMER
        });
      }
    }
    // Gating.
    const membership = await db.collection('memberships').doc(openid).get()
      .catch(function () { return null; });
    const tier = effectiveTier(membership ? membership.data : null);
    const monthKey = dayKey().slice(0, 7);
    let chargePoints = false;
    if (tier === 'max') {
      chargePoints = false;
    } else if (tier === 'pro') {
      const uses = await monthAiUses(openid, monthKey);
      const limit = (aiCfg.doc && aiCfg.doc.proMonthlyAiLimit) || 20;
      chargePoints = uses >= limit;
    } else {
      chargePoints = true;
    }
    if (chargePoints) {
      const balance = user.pointsBalance || 0;
      if (balance + SPEND_RULES.aiInterpret.delta < 0) {
        return fail('INSUFFICIENT_POINTS', '积分不足：AI 解读需 30 积分');
      }
    }
    // Quota gate.
    const budget = (quotaCfg.doc && quotaCfg.doc.dailyTokenBudget) || 0;
    const threshold = (quotaCfg.doc && quotaCfg.doc.thresholdPercent) || 85;
    const usedToday = await todayCloudbaseTokens();
    const forceFallback = shouldDegrade(usedToday, budget, threshold);
    // Build messages.
    const chartSummary = JSON.stringify(chart.chartData || {}).slice(0, 6000);
    const userContent = action === 'interpret'
      ? '请解读下面这张紫微命盘（解读类型：' + interpretType + '）。命盘数据：' + chartSummary
      : '就下面这张紫微命盘回答问题。问题：' + String(event.question || '') + '。命盘数据：' + chartSummary;
    if (action === 'ask' && !event.question) {
      return fail('INVALID_PARAMS', 'ask 需要 question');
    }
    const messages = [
      { role: 'system', content: SYSTEM_PROMPT },
      { role: 'user', content: userContent }
    ];
    let result;
    try {
      result = await adapter.generateTextWithFallback({
        messages: messages,
        cloudbaseModel: (aiCfg.doc && aiCfg.doc.cloudbaseChatModel) || 'deepseek-v4-flash',
        botsrouterApiKey: process.env.BOTSROUTER_API_KEY || '',
        botsrouterBaseUrl: process.env.BOTSROUTER_BASE_URL || '',
        botsrouterModel: (aiCfg.doc && aiCfg.doc.botsrouterChatModel) || 'deepseek-v4.1-flash',
        forceFallback: forceFallback
      });
    } catch (e) {
      return fail(e.code || 'AI_UNAVAILABLE',
        'AI 服务暂不可用（主备均失败），请稍后重试。原因：' + (e.causes ? e.causes.join(' | ') : e.message),
        { degraded: true, provider: null });
    }
    const usage = result.usage || {};
    const totalTokens = usage.total_tokens || ((usage.prompt_tokens || 0) + (usage.completion_tokens || 0));
    await logQuota(db, {
      openid: openid, kind: 'ai', provider: result.provider,
      model: result.provider === 'cloudbase'
        ? ((aiCfg.doc && aiCfg.doc.cloudbaseChatModel) || 'deepseek-v4-flash')
        : ((aiCfg.doc && aiCfg.doc.botsrouterChatModel) || 'deepseek-v4.1-flash'),
      promptTokens: usage.prompt_tokens || 0,
      completionTokens: usage.completion_tokens || 0,
      totalTokens: totalTokens, dayKey: dayKey(), monthKey: monthKey,
      degraded: !!result.degraded, chartId: chart._id
    });
    if (chargePoints) {
      await appendLedger(db, {
        openid: openid, type: 'spend', rule: 'aiInterpret',
        delta: SPEND_RULES.aiInterpret.delta, dayKey: dayKey(),
        deviceFingerprint: user.deviceFingerprint || '', chartId: chart._id
      });
    }
    if (action === 'interpret') {
      const key = aiCacheKey(chart.birthParams, interpretType);
      await db.collection('aiCache').add({
        data: {
          cacheKey: key, openid: openid, chartId: chart._id,
          interpretType: interpretType, text: result.text,
          provider: result.provider, createdAt: new Date()
        }
      });
    }
    return ok({
      text: result.text, cached: false, provider: result.provider,
      degraded: !!result.degraded,
      degradedReason: result.degraded ? (result.reason || (forceFallback ? 'quota-threshold-reached' : '')) : null,
      quotaUsedToday: usedToday, quotaBudget: budget,
      chargedPoints: chargePoints ? 30 : 0,
      disclaimer: DISCLAIMER
    });
  } catch (e) {
    console.error('ai failed', e);
    return fail('AI_FAILED', e.message || 'AI 调用失败');
  }
};
