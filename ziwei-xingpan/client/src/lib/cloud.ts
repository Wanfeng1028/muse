import Taro from '@tarojs/taro';
import type { ZiweiChart } from '../engine/types';

// Cloud function client layer for 星命盘.
// Rules:
// - No AppID, merchant id, ad unit id or price is hardcoded here. Prices,
//   points rules and ad unit ids come from the `config` cloud function.
// - No fake data: when the cloud env is not configured (CLOUD_ENV_ID is
//   still the empty placeholder because the user has not provided an
//   envId), every call returns { ok: false, code: 'CLOUD_NOT_CONFIGURED' }
//   and the UI shows the honest "not configured" empty state.
// - Session uses the cloud native openid: wx.login is called first for the
//   session check, then the `login` cloud function creates/updates the
//   user record. No JWT is invented on the client.
// - The rewarded-video / share earn calls are client-attested (the ad
//   close callback / the share action happens on the client); the server
//   still enforces the daily caps and the device check, so a forged call
//   cannot exceed the caps.

// Cloud env placeholder: the user has not provided a real envId yet.
// Fill this in (in the developer tools cloud console, not from any secret)
// once the cloud environment is opened. Empty = cloud features disabled.
export const CLOUD_ENV_ID = '';

const DEVICE_FP_KEY = 'zw_device_fp_v1';

let cloudInitDone = false;

// Flat result shape (not a discriminated union): this project's tsconfig
// runs with strict:false, under which TS does not narrow `ok: true/false`
// unions, so a union shape breaks every error-branch access. Callers test
// `res.ok` first; `data` is null and `code`/`message` are set on failure.
export type CloudResult<T> =
  { ok: boolean; data: T | null; code: string; message: string };

export function cloudConfigured(): boolean {
  return CLOUD_ENV_ID !== '';
}

function anyTaro(): any {
  return Taro as any;
}

export function deviceFingerprint(): string {
  try {
    const existing = Taro.getStorageSync(DEVICE_FP_KEY) as string;
    if (existing) return existing;
    const fp =
      'fp-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
    Taro.setStorageSync(DEVICE_FP_KEY, fp);
    return fp;
  } catch {
    return 'fp-unknown';
  }
}

function ensureCloud(): CloudResult<null> | null {
  if (!cloudConfigured()) {
    return { ok: false, data: null, code: 'CLOUD_NOT_CONFIGURED', message: '云开发未配置：需提供云开发环境 ID 后开通' };
  }
  const cloud = anyTaro().cloud;
  if (!cloud || typeof cloud.init !== 'function' || typeof cloud.callFunction !== 'function') {
    return { ok: false, data: null, code: 'CLOUD_SDK_UNAVAILABLE', message: '当前运行环境不支持云开发调用' };
  }
  if (!cloudInitDone) {
    try {
      cloud.init({ env: CLOUD_ENV_ID, traceUser: true });
      cloudInitDone = true;
    } catch (e) {
      return { ok: false, data: null, code: 'CLOUD_INIT_FAILED', message: '云开发初始化失败：' + (e as Error).message };
    }
  }
  return null;
}

export async function callFn<T>(name: string, data: Record<string, unknown>): Promise<CloudResult<T>> {
  const blocked = ensureCloud();
  if (blocked) return blocked as CloudResult<T>;
  try {
    const res = await anyTaro().cloud.callFunction({ name, data });
    const result = res && res.result;
    if (result && result.code === 0) {
      return { ok: true, data: result.data as T, code: '', message: '' };
    }
    return {
      ok: false,
      data: null,
      code: (result && result.code) || 'CLOUD_CALL_FAILED',
      message: (result && result.message) || '云函数调用失败',
    };
  } catch (e) {
    return { ok: false, data: null, code: 'CLOUD_CALL_FAILED', message: '云函数调用失败：' + (e as Error).message };
  }
}

// wx.login session check, then the login cloud function. The login code
// itself is not sent to any server: cloud functions read OPENID from the
// call context. A failed wx.login does not block the cloud login attempt,
// but a missing cloud env does (honest unconfigured state, not a fake user).
export async function loginFlow(profile: {
  nickname?: string;
  avatarUrl?: string;
  gender?: number;
  birthYear?: number;
  isMinor?: boolean;
}): Promise<CloudResult<{ openid: string; isNew: boolean; user: CloudUser }>> {
  try {
    await Taro.login();
  } catch {
    // Session check failed; the cloud call below still decides by openid.
  }
  return callFn('login', {
    nickname: profile.nickname || '',
    avatarUrl: profile.avatarUrl || '',
    gender: profile.gender || 0,
    birthYear: profile.birthYear || 0,
    isMinor: profile.isMinor || false,
    deviceFingerprint: deviceFingerprint(),
  });
}

export interface CloudUser {
  openid: string;
  nickname?: string;
  avatarUrl?: string;
  gender?: number;
  birthYear?: number | null;
  minor?: boolean;
  inviteCode?: string;
  invitedBy?: string;
  pointsBalance?: number;
  profileBonusClaimed?: boolean;
  deviceFingerprint?: string;
}

export interface MembershipStatus {
  tier: string;
  rawTier: string;
  expiresAt: string | null;
  autoRenew: boolean;
}

export interface OrderDoc {
  _id: string;
  plan: string;
  tier: string;
  days: number;
  continuous: boolean;
  amountFen: number;
  outTradeNo: string;
  status: string;
  createdAt: string;
}

export interface LedgerEntry {
  _id?: string;
  rule: string;
  type: string;
  delta: number;
  dayKey?: string;
  createdAt: string;
}

export interface InviteInfo {
  inviteCode: string;
  successCount: number;
  nextTier: { count: number; tier: string; days: number } | null;
  grantedTiers: number[];
}

export interface SavedChart {
  _id: string;
  name: string;
  birthParams: Record<string, unknown>;
  chartData: ZiweiChart;
  chartHash: string;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AiResult {
  text: string;
  cached: boolean;
  provider: string;
  degraded: boolean;
  degradedReason?: string | null;
  quotaUsedToday?: number;
  quotaBudget?: number;
  chargedPoints?: number;
  disclaimer: string;
}

export interface AiImageResult {
  fileID: string;
  cached: boolean;
  provider: string;
  degraded: boolean;
  degradedReason?: string | null;
  chargedPoints?: number;
}
export interface AppConfig {
  ads: {
    bannerHome: string;
    bannerInterpret: string;
    rewardedVideo: string;
    interstitial: string;
    enabled: boolean;
  };
  pricing: {
    tiers: Record<string, { name: string; pointsGrant: number; noBannerAds: boolean; noInterstitialAds: boolean; noAllAds: boolean; hdExportFree: boolean; annualFortuneFree: boolean; earlyAccess: boolean }>;
    plans: Record<string, { tier: string; days: number; fen: number; pointsGrant: number; billingCycle: string; continuous: boolean }>;
    recharge: { pointsPerYuan: number; minYuan: number };
    cancelNote: string;
  };
  pointsRules: {
    earn: Record<string, { delta: number; dailyLimit?: number; once?: boolean }>;
    spend: Record<string, { delta: number }>;
    neverExpires: boolean;
  };
  ai: { proMonthlyAiLimit: number };
  disclaimer: string;
  fromSeed: boolean;
}

export const RULE_LABELS: Record<string, string> = {
  signin: '每日签到',
  video: '激励视频',
  invite: '邀请好友',
  profile: '完善资料',
  share: '分享海报',
  inviteeBonus: '被邀奖励',
  membership: '会员赠送积分',
  recharge: '积分充值',
  refund: '失败退款',
  chatOverage: '对话超额',
  advancedInterpret: '高级解读',
  aiInterpret: 'AI 解读',
  dimInterpret: '维度解读',
  compare: '合盘对照',
  chatImage: '对话内生图',
  posterBg: '海报背景 AI 生成',
  hdExport: '高清命盘图导出',
  annualFortune: '年度运势',
  aiPersona: 'AI 定制形象',
  pro7d: '7 天 Pro',
  pro30d: '30 天 Pro',
};

export const PLAN_NAMES: Record<string, string> = {
  plusMonthly: 'Plus 月付',
  proMonthly: 'Pro 月付',
  maxMonthly: 'Max 月付',
  recharge: '积分充值',
};

export const ORDER_STATUS_NAMES: Record<string, string> = {
  pending: '待支付',
  paid: '已支付',
  failed: '支付失败',
  closed: '已关闭',
};

export function formatYuan(fen: number): string {
  return '¥' + (fen / 100).toFixed(0);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    const p = (v: number) => String(v).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  } catch {
    return String(value);
  }
}

export function isPlaceholderAdUnit(id: string | undefined): boolean {
  return !id || id.indexOf('PLACEHOLDER') === 0;
}

// Resolve a cloud fileID to a temporary URL for display. Returns null when
// the cloud is unconfigured or the lookup fails; the caller shows the
// honest placeholder note instead of a broken image.
export async function tempFileURL(fileID: string): Promise<string | null> {
  const blocked = ensureCloud();
  if (blocked) return null;
  try {
    const res = await anyTaro().cloud.getTempFileURL({ fileList: [fileID] });
    const item = res && res.fileList && res.fileList[0];
    if (item && item.tempFileURL) return item.tempFileURL as string;
    return null;
  } catch {
    return null;
  }
}
