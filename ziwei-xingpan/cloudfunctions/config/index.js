'use strict';

// config: publish client configuration. The client must never hardcode
// ad unit ids, prices or points rules; it reads them from here.
// Actions:
//   get {} -> { ads, pricing, pointsRules, ai, disclaimer, fromSeed }
// fromSeed: true means the `configs` collection has not been seeded yet
// and the values come from the seed module (see shared/config-seed.js).
// Seed the collection from the cloud console before launch.

const cloud = require('wx-server-sdk');
const { ok, fail, requireOpenid } = require('./shared/errors');
const { getConfigDoc } = require('./shared/db-helpers');
const { SEED_CONFIGS, DISCLAIMER } = require('./shared/config-seed');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

exports.main = async (event, context) => {
  try {
    const wxContext = cloud.getWXContext();
    const openid = requireOpenid(wxContext);
    if (!openid) {
      return fail('NOT_LOGGED_IN', '无法获取微信登录态，请先调用 login');
    }
    const action = event.action || 'get';
    if (action !== 'get') {
      return fail('UNKNOWN_ACTION', '未知 action: ' + String(action));
    }
    const ads = await getConfigDoc(db, 'ads', SEED_CONFIGS);
    const pricing = await getConfigDoc(db, 'pricing', SEED_CONFIGS);
    const pointsRules = await getConfigDoc(db, 'pointsRules', SEED_CONFIGS);
    const ai = await getConfigDoc(db, 'ai', SEED_CONFIGS);
    const fromSeed = ads.fromSeed || pricing.fromSeed || pointsRules.fromSeed || ai.fromSeed;
    const aiDoc = ai.doc || {};
    return ok({
      ads: ads.doc,
      pricing: pricing.doc,
      pointsRules: pointsRules.doc,
      ai: {
        // Only publish non-sensitive AI settings. Model names are public
        // config; keys are never included here or anywhere in code.
        cloudbaseChatModel: aiDoc.cloudbaseChatModel,
        cloudbaseImageModel: aiDoc.cloudbaseImageModel,
        botsrouterChatModel: aiDoc.botsrouterChatModel,
        proMonthlyAiLimit: aiDoc.proMonthlyAiLimit
      },
      disclaimer: DISCLAIMER,
      fromSeed: fromSeed
    });
  } catch (e) {
    console.error('config failed', e);
    return fail('CONFIG_FAILED', e.message || '配置下发失败');
  }
};
