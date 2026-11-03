// Central pricing for 星命盘 (pure-points model, user-set 2026-11-01).
// Single adjustable point on the client; the cloud `configs` pricing /
// pointsRules docs override these constants when configured (see
// resolvePricing). The cloud seed is cloudfunctions/_shared/config-seed.js;
// keep the numbers in sync when the user changes them.
//
// Current truth (19:40 + 19:41 + 19:42 corrections; the 19:30 table with
// 1 yuan = 100 points and Pro 18 / Max 38 is void):
// - Standalone recharge: 1 yuan = 50 points, min 1 yuan.
// - Tiers (monthly fee; points granted once per payment, renewal pays
//   again and grants again; billingCycle is a config field, 'monthly'):
//   Plus 19.9 -> 1000 points + no banner ads;
//   Pro 34.9 -> 2000 points + no banner + no interstitial + early access;
//   Max 69.9 -> 4000 points + no ads at all + HD export free +
//   annual fortune free + early access.
// - Earn: signin +10/day; rewarded video +20 (max 5/day; banner and
//   interstitial ads never grant points); share +5/day (only on a
//   successful share); invite +100 (invitee must fill the invite code
//   and finish a first chart); invitee +50; profile +30 once.
//   Ladder: 3 invitees -> 7-day Pro; 10 -> 30-day Pro; 30 -> Max month.
//   Same WeChat/device counted once (anti-brush, server side).
// - Redeem identity (no points bundle): 300 -> 7-day Pro; 1500 -> 30-day Pro.
// - Free: brief chart reading (chart + chart map + short interpretation:
//   main palace star + one sentence + pattern name, no points).
// - Chat text: 2,000,000 tokens free per user per natural day (chat text
//   only, not image generation). Overage: 10 points per 1,000,000 tokens,
//   settled on actual usage, rounded up to whole points. Per-round
//   context packing cap + daily call cap are configurable.
// - Feature prices (19:48: doubled from the first draft; the list
//   below is the live table): single-dim full interpretation 20 (same
//   chart + dim unlocked stays free forever); full 13-dim + pattern
//   detail 100; compare 60; in-chat image 40; poster-bg AI generation
//   40 (base vector background free); HD chart export 40 (Max free);
//   annual fortune 100 (Max free); AI persona image 100 (19:49 correction).
// - Interruption: insufficient points stops the task (already-generated
//   part kept) + insufficient-balance prompt + earn paths; no overdraft;
//   failed answers are not charged (charged amounts roll back).
// - Ads: banner/interstitial are the interruptive slots gated by tier.
//   Rewarded video stays available to every tier because it is an
//   opt-in points-earning action, not an interruption.

import type { AppConfig } from './cloud';

export type Tier = 'free' | 'plus' | 'pro' | 'max';

export const TIER_RANK: Record<Tier, number> = { free: 0, plus: 1, pro: 2, max: 3 };

export const TIER_NAMES: Record<Tier, string> = {
  free: '普通',
  plus: 'Plus',
  pro: 'Pro',
  max: 'Max',
};

export interface TierBenefits {
  pointsGrant: number;
  noBannerAds: boolean;
  noInterstitialAds: boolean;
  noAllAds: boolean;
  hdExportFree: boolean;
  annualFortuneFree: boolean;
  earlyAccess: boolean;
}

export interface PlanDef {
  tier: Tier;
  days: number;
  fen: number;
  pointsGrant: number;
  billingCycle: string;
}

export interface ChatPricing {
  dailyTokenQuota: number;
  dailyCallCap: number;
  historyRounds: number;
  maxOutputTokens: number;
  pointsPerMillionTokens: number;
}

export interface Pricing {
  tiers: Record<Tier, TierBenefits>;
  plans: Record<string, PlanDef>;
  planOrder: string[];
  recharge: { pointsPerYuan: number; minYuan: number };
  earn: Record<string, { delta: number; dailyLimit?: number; once?: boolean }>;
  spend: Record<string, { delta: number }>;
  redeem: Record<string, { delta: number; tier: Tier; days: number }>;
  chat: ChatPricing;
}

export const PRICING: Pricing = {
  tiers: {
    free: { pointsGrant: 0, noBannerAds: false, noInterstitialAds: false, noAllAds: false, hdExportFree: false, annualFortuneFree: false, earlyAccess: false },
    plus: { pointsGrant: 1000, noBannerAds: true, noInterstitialAds: false, noAllAds: false, hdExportFree: false, annualFortuneFree: false, earlyAccess: false },
    pro: { pointsGrant: 2000, noBannerAds: true, noInterstitialAds: true, noAllAds: false, hdExportFree: false, annualFortuneFree: false, earlyAccess: true },
    max: { pointsGrant: 4000, noBannerAds: true, noInterstitialAds: true, noAllAds: true, hdExportFree: true, annualFortuneFree: true, earlyAccess: true },
  },
  plans: {
    plusMonthly: { tier: 'plus', days: 30, fen: 1990, pointsGrant: 1000, billingCycle: 'monthly' },
    proMonthly: { tier: 'pro', days: 30, fen: 3490, pointsGrant: 2000, billingCycle: 'monthly' },
    maxMonthly: { tier: 'max', days: 30, fen: 6990, pointsGrant: 4000, billingCycle: 'monthly' },
  },
  planOrder: ['plusMonthly', 'proMonthly', 'maxMonthly'],
  recharge: { pointsPerYuan: 50, minYuan: 1 },
  earn: {
    signin: { delta: 10, dailyLimit: 1 },
    video: { delta: 20, dailyLimit: 5 },
    share: { delta: 5, dailyLimit: 1 },
    invite: { delta: 100 },
    inviteeBonus: { delta: 50 },
    profile: { delta: 30, once: true },
  },
  spend: {
    dimInterpret: { delta: -20 },
    advancedInterpret: { delta: -100 },
    compare: { delta: -60 },
    chatImage: { delta: -40 },
    posterBg: { delta: -40 },
    hdExport: { delta: -40 },
    annualFortune: { delta: -100 },
    aiPersona: { delta: -100 },
  },
  redeem: {
    pro7d: { delta: -300, tier: 'pro', days: 7 },
    pro30d: { delta: -1500, tier: 'pro', days: 30 },
  },
  chat: {
    dailyTokenQuota: 2000000,
    dailyCallCap: 100,
    historyRounds: 10,
    maxOutputTokens: 2000,
    pointsPerMillionTokens: 10,
  },
};

// Cloud config overrides local constants when present. The cloud pricing
// doc carries tiers/plans/recharge; pointsRules carries earn/spend.
// Unknown cloud fields are ignored; missing ones fall back to local.
export function resolvePricing(config: AppConfig | null): Pricing {
  if (!config || !config.pricing) return PRICING;
  const out: Pricing = JSON.parse(JSON.stringify(PRICING));
  const p = config.pricing as any;
  if (p.tiers) {
    (Object.keys(p.tiers) as Tier[]).forEach((t) => {
      if (out.tiers[t]) out.tiers[t] = Object.assign({}, out.tiers[t], p.tiers[t]);
    });
  }
  if (p.plans) {
    Object.keys(p.plans).forEach((k) => {
      const plan = p.plans[k];
      if (plan && typeof plan.fen === 'number') {
        out.plans[k] = {
          tier: plan.tier || 'free',
          days: plan.days || 30,
          fen: plan.fen,
          pointsGrant: plan.pointsGrant || 0,
          billingCycle: plan.billingCycle || 'monthly',
        };
      }
    });
    out.planOrder = PRICING.planOrder.filter((k) => !!out.plans[k]);
    Object.keys(out.plans).forEach((k) => {
      if (out.planOrder.indexOf(k) < 0) out.planOrder.push(k);
    });
  }
  if (p.recharge) {
    if (typeof p.recharge.pointsPerYuan === 'number') out.recharge.pointsPerYuan = p.recharge.pointsPerYuan;
    if (typeof p.recharge.minYuan === 'number') out.recharge.minYuan = p.recharge.minYuan;
  }
  const rules = (config as any).pointsRules;
  if (rules) {
    if (rules.earn) {
      Object.keys(rules.earn).forEach((k) => {
        if (rules.earn[k] && typeof rules.earn[k].delta === 'number') out.earn[k] = rules.earn[k];
      });
    }
    if (rules.spend) {
      Object.keys(rules.spend).forEach((k) => {
        if (rules.spend[k] && typeof rules.spend[k].delta === 'number') out.spend[k] = rules.spend[k];
      });
    }
  }
  return out;
}

// Chat overage: 10 points per 1,000,000 tokens, rounded up to whole
// points. 1 point therefore covers 100,000 tokens of overage.
export function chatTokensToPoints(tokens: number, chat: ChatPricing): number {
  if (tokens <= 0) return 0;
  return Math.ceil((tokens * chat.pointsPerMillionTokens) / 1000000);
}

// Purchase-page value label (19:42: label the value point directly,
// no qualifier sentence). Example: 1000 points -> "约 1 亿 tokens 对话".
export function chatTokenValueLabel(points: number, chat: ChatPricing): string {
  const tokens = Math.floor((points * 1000000) / chat.pointsPerMillionTokens);
  if (tokens >= 100000000) {
    const yi = tokens / 100000000;
    const text = Number.isInteger(yi) ? String(yi) : yi.toFixed(1).replace(/\.0$/, '');
    return '约 ' + text + ' 亿 tokens 对话';
  }
  if (tokens >= 10000) {
    const wan = tokens / 10000;
    const text = Number.isInteger(wan) ? String(wan) : wan.toFixed(1).replace(/\.0$/, '');
    return '约 ' + text + ' 万 tokens 对话';
  }
  return '约 ' + tokens + ' tokens 对话';
}

// ---- Local ledger (used only when cloud is not configured) ----
// Keys live in localStorage on H5 and Taro storage on weapp; the helpers
// below use Taro storage so both targets share the code path.

import Taro from '@tarojs/taro';

const BALANCE_KEY = 'zw_points_balance_v1';
const LEDGER_KEY = 'zw_points_ledger_v1';
const DAILY_KEY = 'zw_points_daily_v1';
const ONCE_KEY = 'zw_points_once_v1';
const TIER_KEY = 'zw_local_tier_v1';
const UNLOCK_DIM_KEY = 'zw_unlock_dim_v1';
const UNLOCK_ALL_KEY = 'zw_unlock_all_v1';

function storageGet(key: string, fallback: any): any {
  try {
    const v = Taro.getStorageSync(key);
    return v === undefined || v === null || v === '' ? fallback : v;
  } catch {
    return fallback;
  }
}

function storageSet(key: string, value: any): void {
  try {
    Taro.setStorageSync(key, value);
  } catch {
    // Storage failure must not crash the page; the in-memory balance
    // below is still returned to the caller.
  }
}

export interface LocalTier {
  tier: Tier;
  expiresAt: number | null;
}

export function localTier(): LocalTier {
  const raw = storageGet(TIER_KEY, null);
  if (raw && raw.tier && TIER_RANK[raw.tier as Tier] !== undefined) {
    if (!raw.expiresAt || raw.expiresAt > Date.now()) return raw as LocalTier;
  }
  return { tier: 'free', expiresAt: null };
}

// No-downgrade mirror of cloudfunctions/_shared/membership.js grantTier.
export function localGrantTier(tier: Tier, days: number): LocalTier {
  const current = localTier();
  const keep = TIER_RANK[current.tier] > TIER_RANK[tier];
  const base = current.expiresAt && current.expiresAt > Date.now() ? current.expiresAt : Date.now();
  const next: LocalTier = {
    tier: keep ? current.tier : tier,
    expiresAt: base + days * 24 * 60 * 60 * 1000,
  };
  storageSet(TIER_KEY, next);
  return next;
}

export function localBalance(): number {
  const v = storageGet(BALANCE_KEY, 0);
  return typeof v === 'number' ? v : 0;
}

function appendLocalLedger(rule: string, delta: number): void {
  const list = storageGet(LEDGER_KEY, []) as Array<{ rule: string; delta: number; at: number }>;
  list.unshift({ rule: rule, delta: delta, at: Date.now() });
  storageSet(LEDGER_KEY, list.slice(0, 200));
  storageSet(BALANCE_KEY, localBalance() + delta);
}

function todayKey(): string {
  const d = new Date();
  return d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
}

function dailyCounts(): Record<string, number> {
  const raw = storageGet(DAILY_KEY, null);
  if (raw && raw.date === todayKey()) return raw.counts || {};
  return {};
}

function bumpDaily(rule: string): void {
  const counts = dailyCounts();
  counts[rule] = (counts[rule] || 0) + 1;
  storageSet(DAILY_KEY, { date: todayKey(), counts: counts });
}

export type EarnResult =
  | { ok: true; granted: number }
  | { ok: false; reason: 'DAILY_LIMIT' | 'ALREADY_CLAIMED' | 'UNKNOWN_RULE' };

export function localEarn(rule: string, pricing: Pricing = PRICING): EarnResult {
  const def = pricing.earn[rule];
  if (!def) return { ok: false, reason: 'UNKNOWN_RULE' };
  if (def.once) {
    const once = storageGet(ONCE_KEY, {}) as Record<string, boolean>;
    if (once[rule]) return { ok: false, reason: 'ALREADY_CLAIMED' };
    once[rule] = true;
    storageSet(ONCE_KEY, once);
  }
  if (def.dailyLimit !== undefined) {
    if ((dailyCounts()[rule] || 0) >= def.dailyLimit) return { ok: false, reason: 'DAILY_LIMIT' };
    bumpDaily(rule);
  }
  appendLocalLedger(rule, def.delta);
  return { ok: true, granted: def.delta };
}

export type SpendResult =
  | { ok: true; charged: number }
  | { ok: false; reason: 'INSUFFICIENT_POINTS' | 'UNKNOWN_RULE'; need: number; balance: number };

export function localSpend(rule: string, pricing: Pricing = PRICING, tier: Tier = 'free'): SpendResult {
  const def = pricing.spend[rule];
  if (!def) return { ok: false, reason: 'UNKNOWN_RULE', need: 0, balance: localBalance() };
  let cost = -def.delta;
  if (rule === 'hdExport' && pricing.tiers[tier] && pricing.tiers[tier].hdExportFree) cost = 0;
  if (rule === 'annualFortune' && pricing.tiers[tier] && pricing.tiers[tier].annualFortuneFree) cost = 0;
  if (cost === 0) return { ok: true, charged: 0 };
  const balance = localBalance();
  if (balance < cost) return { ok: false, reason: 'INSUFFICIENT_POINTS', need: cost, balance: balance };
  appendLocalLedger(rule, -cost);
  return { ok: true, charged: cost };
}

// Credit back a previously charged local spend (delivery-failure
// flows only). Ledger rule is 'refund'; the original rule is not
// recoverable from the local ledger shape, so callers must only use
// this immediately after a failed delivery of the same charge.
export function localRefund(amount: number): void {
  if (amount > 0) appendLocalLedger('refund', amount);
}

// Share earn: call ONLY after a successful share (shareAppMessage
// success callback or H5 copy-link confirmation). Cloud mode goes
// through the points function; local mode uses the local ledger.
export function recordShareEarn(pricing: Pricing = PRICING): EarnResult {
  return localEarn('share', pricing);
}

// Tier-gated ad slots (interruptive slots only; rewarded video is an
// opt-in earn action and stays available to every tier).
export function hideBanner(tier: Tier, pricing: Pricing = PRICING): boolean {
  return !!pricing.tiers[tier] && pricing.tiers[tier].noBannerAds;
}

export function hideInterstitial(tier: Tier, pricing: Pricing = PRICING): boolean {
  return !!pricing.tiers[tier] && (pricing.tiers[tier].noInterstitialAds || pricing.tiers[tier].noAllAds);
}

export function hdExportCost(tier: Tier, pricing: Pricing = PRICING): number {
  if (pricing.tiers[tier] && pricing.tiers[tier].hdExportFree) return 0;
  return -(pricing.spend.hdExport ? pricing.spend.hdExport.delta : -40);
}

export function annualFortuneCost(tier: Tier, pricing: Pricing = PRICING): number {
  if (pricing.tiers[tier] && pricing.tiers[tier].annualFortuneFree) return 0;
  return -(pricing.spend.annualFortune ? pricing.spend.annualFortune.delta : -100);
}

// Unlock sets: dim key = chartKey + '|' + dimId; all key = chartKey.
export function chartKeyForUnlock(input: { date: string; clockHour: number; clockMinute: number; province: string; city: string; longitude: number; gender: string; corrections: string }): string {
  return [input.date, input.clockHour, input.clockMinute, input.province, input.city, input.longitude, input.gender, input.corrections].join('|');
}

export function isDimUnlocked(chartKey: string, dimId: string): boolean {
  const set = storageGet(UNLOCK_DIM_KEY, {}) as Record<string, boolean>;
  return !!set[chartKey + '|' + dimId];
}

export function unlockDimLocal(chartKey: string, dimId: string): void {
  const set = storageGet(UNLOCK_DIM_KEY, {}) as Record<string, boolean>;
  set[chartKey + '|' + dimId] = true;
  storageSet(UNLOCK_DIM_KEY, set);
}

export function isAllUnlocked(chartKey: string): boolean {
  const set = storageGet(UNLOCK_ALL_KEY, {}) as Record<string, boolean>;
  return !!set[chartKey];
}

export function unlockAllLocal(chartKey: string): void {
  const set = storageGet(UNLOCK_ALL_KEY, {}) as Record<string, boolean>;
  set[chartKey] = true;
  storageSet(UNLOCK_ALL_KEY, set);
}

// Insufficient-balance guidance shown everywhere a spend can fail.
// Order matches the earn paths the user named: signin / video /
// share / invite / recharge.
export const EARN_GUIDE = '积分不足：可通过每日签到（+10）、激励视频（+20/次，每日上限 5 次）、分享（+5/日）、邀请好友（+100/人，需填邀请码）或充值（1 元 = 50 积分）获得积分。';
