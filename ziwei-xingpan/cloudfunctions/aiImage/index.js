'use strict';

// aiImage: generate poster-background / daily-fortune images.
// Cache: imageCache keyed by prompt hash, or by date + chart hash for
// daily-fortune images. A hit returns the stored cloud fileID directly.
// Primary: CloudBase Hunyuan image model (see shared/ai-adapter.js for
// the documented call shape). The model returns a 24h URL, so a hit is
// downloaded and re-uploaded to cloud storage and the fileID is cached;
// the raw URL is never returned as the durable result.
// Fallback: BotsRouter image model, only when a BotsRouter image model
// is configured (the seed leaves it empty rather than inventing one).
// If both fail, the error is returned with degraded status, never a
// fabricated fileID. Download uses Node https only (no extra dependency).

const cloud = require('wx-server-sdk');
const https = require('https');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { getUser, getConfigDoc, logQuota } = require('./shared/db-helpers');
const { imageCacheKey } = require('./shared/hash');
const { dayKey } = require('./shared/points');
const { shouldDegrade } = require('./shared/quota');
const { SEED_CONFIGS } = require('./shared/config-seed');
const adapter = require('./shared/ai-adapter');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

function downloadBuffer(url) {
  return new Promise(function (resolve, reject) {
    https.get(url, { timeout: 120000 }, function (res) {
      if (res.statusCode < 200 || res.statusCode >= 300) {
        reject(new Error('IMAGE_DOWNLOAD_HTTP_' + res.statusCode));
        return;
      }
      const parts = [];
      res.on('data', function (c) { parts.push(c); });
      res.on('end', function () { resolve(Buffer.concat(parts)); });
    }).on('error', reject);
  });
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
    const prompt = String(event.prompt || '').trim();
    if (!prompt && !event.chartId) {
      return fail('INVALID_PARAMS', 'prompt 与 chartId 至少提供一个');
    }
    let chart = null;
    if (event.chartId) {
      const res = await db.collection('charts').doc(String(event.chartId)).get()
        .catch(function () { return null; });
      if (!res || !res.data || res.data.openid !== openid) {
        return fail('CHART_NOT_FOUND', '命盘不存在或不属于当前用户');
      }
      chart = res.data;
    }
    const aiCfg = await getConfigDoc(db, 'ai', SEED_CONFIGS);
    const quotaCfg = await getConfigDoc(db, 'quota', SEED_CONFIGS);
    const kind = event.kind === 'daily' ? 'daily' : 'poster';
    const finalPrompt = prompt || ('紫微命盘每日运势配图，中国风，简洁留白，适配海报背景。命盘：'
      + JSON.stringify(chart ? chart.birthParams : {}));
    const key = kind === 'daily' && chart
      ? imageCacheKey({ chartParams: chart.birthParams, dateKey: dayKey() })
      : imageCacheKey({ prompt: finalPrompt });
    const hit = await db.collection('imageCache').where({ cacheKey: key }).limit(1).get();
    if (hit.data && hit.data.length > 0) {
      return ok({
        fileID: hit.data[0].fileID, cached: true,
        provider: hit.data[0].provider || 'cache', degraded: false
      });
    }
    const budget = (quotaCfg.doc && quotaCfg.doc.dailyTokenBudget) || 0;
    const threshold = (quotaCfg.doc && quotaCfg.doc.thresholdPercent) || 85;
    const todayRes = await db.collection('quotaLogs')
      .where({ provider: 'cloudbase', dayKey: dayKey() }).get();
    let usedToday = 0;
    todayRes.data.forEach(function (d) { usedToday += (d.totalTokens || 0); });
    const forceFallback = shouldDegrade(usedToday, budget, threshold);
    let result;
    try {
      result = await adapter.generateImageWithFallback({
        prompt: finalPrompt,
        cloudbaseModel: (aiCfg.doc && aiCfg.doc.cloudbaseImageModel) || 'HY-Image-3.0-Plus-4090-Tob-v1.0',
        size: event.size || '1024x1024',
        botsrouterApiKey: process.env.BOTSROUTER_API_KEY || '',
        botsrouterBaseUrl: process.env.BOTSROUTER_BASE_URL || '',
        botsrouterModel: (aiCfg.doc && aiCfg.doc.botsrouterImageModel) || '',
        forceFallback: forceFallback
      });
    } catch (e) {
      return fail(e.code || 'AI_IMAGE_UNAVAILABLE',
        '生图服务暂不可用（主备均失败），请稍后重试。原因：' + (e.causes ? e.causes.join(' | ') : e.message),
        { degraded: true, provider: null });
    }
    const buffer = await downloadBuffer(result.url);
    const upload = await cloud.uploadFile({
      cloudPath: 'ai-images/' + openid + '-' + Date.now() + '.jpg',
      fileContent: buffer
    });
    await db.collection('imageCache').add({
      data: {
        cacheKey: key, openid: openid, kind: kind, prompt: finalPrompt,
        fileID: upload.fileID, provider: result.provider, createdAt: new Date()
      }
    });
    await logQuota(db, {
      openid: openid, kind: 'image', provider: result.provider,
      model: result.provider === 'cloudbase'
        ? ((aiCfg.doc && aiCfg.doc.cloudbaseImageModel) || 'HY-Image-3.0-Plus-4090-Tob-v1.0')
        : ((aiCfg.doc && aiCfg.doc.botsrouterImageModel) || ''),
      promptTokens: 0, completionTokens: 0, totalTokens: 0,
      dayKey: dayKey(), monthKey: dayKey().slice(0, 7),
      degraded: !!result.degraded, chartId: chart ? chart._id : ''
    });
    return ok({
      fileID: upload.fileID, cached: false, provider: result.provider,
      degraded: !!result.degraded,
      degradedReason: result.degraded ? (result.reason || (forceFallback ? 'quota-threshold-reached' : '')) : null
    });
  } catch (e) {
    console.error('aiImage failed', e);
    return fail('AI_IMAGE_FAILED', e.message || '生图失败');
  }
};
