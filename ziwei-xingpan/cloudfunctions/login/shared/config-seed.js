'use strict';

// Seed documents for the `configs` collection. These are DATA, not logic:
// the order/config/membership functions read the live `configs` documents
// first and only fall back to this seed when the collection has not been
// seeded yet (in which case responses carry fromSeed: true so operations
// can see the database still needs seeding). Insert these documents into
// the `configs` collection from the cloud console before launch; do not
// put any real key, AppID, merchant id or ad unit id here.
// Prices are in fen (1 yuan = 100 fen) because cloudPay totalFee is in fen.

const DISCLAIMER = '内容源自传统紫微斗数文化，仅供学习与娱乐参考，不构成人生决策建议。';

const SEED_CONFIGS = [
  {
    _id: 'pricing',
    // 2026-11-01 pure-points model (user-set numbers 19:40; the 19:30
    // 1 yuan = 100 points table and Pro 18 / Max 38 prices are void).
    // Prices in fen (1 yuan = 100 fen) because cloudPay totalFee is fen.
    // Points are a separate currency, credited once per payment:
    // - standalone recharge: 1 yuan = 50 points, min 1 yuan, variable
    //   amount (order plan 'recharge' + yuan; rule 'recharge').
    // - membership payment: pointsGrant once per payment; paying again
    //   (renewal) grants again.
    // billingCycle is a config field only: 'monthly' now. If the user
    // later switches a plan to buyout, only this field changes; the
    // order/membership code does not need a refactor.
    // Tier benefits: noBannerAds / noInterstitialAds / noAllAds gate
    // the interruptive ad slots only. Rewarded video stays available
    // to every tier because it is an opt-in points-earning action,
    // not an interruption (see pricing.ts for the client mirror).
    tiers: {
      free: { name: '普通', pointsGrant: 0, noBannerAds: false, noInterstitialAds: false, noAllAds: false, hdExportFree: false, annualFortuneFree: false, earlyAccess: false },
      plus: { name: 'Plus', pointsGrant: 1000, noBannerAds: true, noInterstitialAds: false, noAllAds: false, hdExportFree: false, annualFortuneFree: false, earlyAccess: false },
      pro: { name: 'Pro', pointsGrant: 2000, noBannerAds: true, noInterstitialAds: true, noAllAds: false, hdExportFree: false, annualFortuneFree: false, earlyAccess: true },
      max: { name: 'Max', pointsGrant: 4000, noBannerAds: true, noInterstitialAds: true, noAllAds: true, hdExportFree: true, annualFortuneFree: true, earlyAccess: true }
    },
    // Plan keys the order function accepts: plusMonthly, proMonthly,
    // maxMonthly. Each maps to a tier + 30-day term + fen price.
    // Chat-token equivalence shown on the purchase page (19:42):
    // pointsGrant / 10 points per million tokens = grant tokens.
    // Plus 1000 -> about 100 million tokens; Pro 2000 -> 200M;
    // Max 4000 -> 400M. The page labels the value point directly.
    plans: {
      plusMonthly: { tier: 'plus', days: 30, fen: 1990, pointsGrant: 1000, billingCycle: 'monthly', continuous: false },
      proMonthly: { tier: 'pro', days: 30, fen: 3490, pointsGrant: 2000, billingCycle: 'monthly', continuous: false },
      maxMonthly: { tier: 'max', days: 30, fen: 6990, pointsGrant: 4000, billingCycle: 'monthly', continuous: false }
    },
    recharge: { pointsPerYuan: 50, minYuan: 1 },
    cancelNote: '取消续费随时生效，当前周期到期后降回普通。'
  },
  {
    _id: 'ads',
    // Placeholder ad unit ids. Real ids come from the traffic-master
    // console after UV >= 1000; the client must never hardcode them.
    bannerHome: 'PLACEHOLDER_ADUNIT_BANNER_HOME',
    bannerInterpret: 'PLACEHOLDER_ADUNIT_BANNER_INTERPRET',
    rewardedVideo: 'PLACEHOLDER_ADUNIT_REWARDED_VIDEO',
    interstitial: 'PLACEHOLDER_ADUNIT_INTERSTITIAL',
    enabled: false
  },
  {
    _id: 'pointsRules',
    earn: {
      signin: { delta: 10, dailyLimit: 1 },
      video: { delta: 20, dailyLimit: 5 },
      invite: { delta: 100 },
      profile: { delta: 30, once: true },
      share: { delta: 5, dailyLimit: 1 },
      inviteeBonus: { delta: 50 }
    },
    spend: {
      // Mirrors cloudfunctions/_shared/points.js SPEND_RULES exactly.
      // Chat text has NO flat rule: daily token quota first, then
      // 10 points per 1,000,000 tokens (see the 'chat' doc below).
      advancedInterpret: { delta: -100 },
      aiInterpret: { delta: -30 },
      pro7d: { delta: -300 },
      pro30d: { delta: -1500 },
      dimInterpret: { delta: -20 },
      aiPersona: { delta: -100 },
      compare: { delta: -60 },
      chatImage: { delta: -40 },
      posterBg: { delta: -40 },
      hdExport: { delta: -40 },
      annualFortune: { delta: -100 }
    },
    neverExpires: true
  },
  {
    _id: 'ai',
    // Primary: CloudBase built-in models (console-enabled, resource points).
    cloudbaseChatModel: 'deepseek-v4-flash',
    cloudbaseImageModel: 'HY-Image-3.0-Plus-4090-Tob-v1.0',
    // Fallback: BotsRouter, OpenAI-compatible. Key only from the cloud
    // function environment config BOTSROUTER_API_KEY, never from code.
    botsrouterChatModel: 'deepseek-v4.1-flash',
    botsrouterImageModel: '',
    proMonthlyAiLimit: 20,
    disclaimer: DISCLAIMER
  },
  {
    _id: 'quota',
    dailyTokenBudget: 1000000,
    thresholdPercent: 85
  },
  {
    _id: 'chat',
    // Lightweight pure chat (19:30 correction: no multi-step tool loop).
    // Chat text only; image generation is charged separately
    // (chatImage 20/image). Token quota resets each natural day.
    // Overage billing (19:41 correction): 10 points per 1,000,000
    // tokens, settled on actual usage, rounded up to whole points.
    // (1 point therefore covers 100,000 tokens of overage.)
    dailyTokenQuota: 2000000,
    dailyCallCap: 100,
    historyRounds: 10,
    maxOutputTokens: 2000,
    pointsPerMillionTokens: 10
  }
];

module.exports = { SEED_CONFIGS: SEED_CONFIGS, DISCLAIMER: DISCLAIMER };
