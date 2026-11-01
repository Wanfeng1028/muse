// Share: read-only chart sharing. A share link carries profile id +
// version and the chart page renders it without writing zw_chart_v1 and
// without a save button, so a viewer can never modify the original
// profile. Points for sharing (+5/day) are granted ONLY on a successful
// share: the weapp shareAppMessage success callback, or the H5
// copy-link confirmation. Callers pass an earn function, or use
// defaultShareEarn (cloud points earn share / local ledger).

import Taro from '@tarojs/taro';
import { callFn, cloudConfigured, deviceFingerprint } from './cloud';
import { recordShareEarn } from './pricing';

export interface ShareTarget {
  profileId: string;
  version: number;
  name: string;
}

export function buildSharePath(target: ShareTarget): string {
  return '/pages/chart/index?share=1&readonly=1&profile=' + encodeURIComponent(target.profileId) + '&v=' + target.version;
}

export interface ShareParams {
  share: boolean;
  readonly: boolean;
  profileId: string | null;
  version: number | null;
}

// Pure parser: the page passes its own router params (no Taro import
// inside the parser, so the rule stays unit-testable by inspection).
export function parseShareParams(params: Record<string, string | undefined>): ShareParams {
  const version = params.v !== undefined ? parseInt(params.v, 10) : NaN;
  return {
    share: params.share === '1',
    readonly: params.readonly === '1',
    profileId: params.profile || null,
    version: Number.isNaN(version) ? null : version,
  };
}

export type EarnFn = () => Promise<{ ok: boolean; granted?: number; reason?: string }>;

// Default earn callback for a successful share: cloud points earn
// share (with the local device fingerprint, same as the mine page) or
// the local ledger when unconfigured. Used by PosterCard and the
// profiles detail share button alike.
export async function defaultShareEarn(): Promise<{ ok: boolean; granted?: number; reason?: string }> {
  if (cloudConfigured()) {
    const r = await callFn<{ delta: number; balance: number }>('points', { action: 'earn', rule: 'share', deviceFingerprint: deviceFingerprint() });
    return { ok: r.ok, granted: r.ok ? r.data.delta : undefined, reason: r.ok ? undefined : r.code };
  }
  const r = recordShareEarn();
  return { ok: r.ok, granted: 'granted' in r ? r.granted : undefined, reason: 'reason' in r ? r.reason : undefined };
}

export async function shareChart(target: ShareTarget, earn: EarnFn): Promise<{ shared: boolean; granted: number; note: string }> {
  const path = buildSharePath(target);
  const title = '「' + target.name + '」的命盘 · 星命盘';
  const env = Taro.getEnv();
  if (env === Taro.ENV_TYPE.WEB) {
    // H5 has no share sheet: copy the share path and treat a confirmed
    // copy as a successful share (same rule as the weapp success path).
    try {
      await Taro.setClipboardData({ data: path });
      const res = await earn();
      return {
        shared: true,
        granted: res.ok ? (res.granted || 0) : 0,
        note: res.ok ? '链接已复制，分享积分已到账（+' + (res.granted || 0) + '）。' : '链接已复制（今日分享积分已领过）。',
      };
    } catch {
      return { shared: false, granted: 0, note: '复制链接失败，请重试。' };
    }
  }
  const shareAppMessage = (Taro as any).shareAppMessage;
  if (typeof shareAppMessage !== 'function') {
    return { shared: false, granted: 0, note: '当前环境不支持微信分享。' };
  }
  try {
    await shareAppMessage({ title: title, path: path });
    const res = await earn();
    return {
      shared: true,
      granted: res.ok ? (res.granted || 0) : 0,
      note: res.ok ? '分享成功，积分已到账（+' + (res.granted || 0) + '）。' : '分享成功（今日分享积分已领过）。',
    };
  } catch {
    return { shared: false, granted: 0, note: '分享未完成，未发放积分。' };
  }
}
