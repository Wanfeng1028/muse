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
    tiers: {
      free: { monthlyFen: 0, continuousFen: 0, name: '普通' },
      pro: { monthlyFen: 1800, continuousFen: 1500, name: 'Pro' },
      max: { monthlyFen: 3800, continuousFen: 3200, name: 'Max' }
    },
    // Plan keys the order function accepts: proMonthly, proContinuous,
    // maxMonthly, maxContinuous. Each maps to a tier + billing mode.
    plans: {
      proMonthly: { tier: 'pro', days: 30, fen: 1800, continuous: false },
      proContinuous: { tier: 'pro', days: 30, fen: 1500, continuous: true },
      maxMonthly: { tier: 'max', days: 30, fen: 3800, continuous: false },
      maxContinuous: { tier: 'max', days: 30, fen: 3200, continuous: true }
    },
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
      advancedInterpret: { delta: -50 },
      aiInterpret: { delta: -30 },
      pro7d: { delta: -300 },
      pro30d: { delta: -1500 }
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
  }
];

module.exports = { SEED_CONFIGS: SEED_CONFIGS, DISCLAIMER: DISCLAIMER };
