import Taro from '@tarojs/taro';
import type { AppConfig } from './cloud';
import { isPlaceholderAdUnit } from './cloud';

// Ad helpers. Every ad slot comes from the `config` cloud function; a
// placeholder id or enabled=false means the slot is NOT live (traffic
// master UV < 1000) and the client renders nothing for it, never a fake ad.
// - Banner: home bottom + interpret bottom, removed for Pro/Max (the
//   caller checks membership tier before rendering).
// - Rewarded video: points center + advanced unlocks; the caller only
//   grants points after onClose reports isEnded.
// - Interstitial: at most once per session, closable (the mini-program
//   interstitial ad is closable by design); a failed show still counts as
//   the session's one attempt so a retry loop cannot spam the user.

export function adSlotLive(config: AppConfig | null, slot: 'bannerHome' | 'bannerInterpret' | 'rewardedVideo' | 'interstitial'): string | null {
  if (!config || !config.ads.enabled) return null;
  const id = config.ads[slot];
  if (isPlaceholderAdUnit(id)) return null;
  return id;
}

let interstitialShownThisSession = false;

export async function showInterstitialOnce(config: AppConfig | null): Promise<boolean> {
  const adUnitId = adSlotLive(config, 'interstitial');
  if (!adUnitId || interstitialShownThisSession) return false;
  interstitialShownThisSession = true;
  const createAd = (Taro as any).createInterstitialAd;
  if (typeof createAd !== 'function') return false;
  try {
    const ad = createAd({ adUnitId });
    await ad.show();
    return true;
  } catch {
    return false;
  }
}

export async function showRewardedVideo(config: AppConfig | null): Promise<'ended' | 'not-ended' | 'unavailable'> {
  const adUnitId = adSlotLive(config, 'rewardedVideo');
  if (!adUnitId) return 'unavailable';
  const createAd = (Taro as any).createRewardedVideoAd;
  if (typeof createAd !== 'function') return 'unavailable';
  try {
    const ad = createAd({ adUnitId });
    const result = await new Promise<'ended' | 'not-ended'>((resolve) => {
      ad.onClose((r: { isEnded: boolean }) => resolve(r && r.isEnded ? 'ended' : 'not-ended'));
      ad.show().catch(() => resolve('not-ended'));
    });
    return result;
  } catch {
    return 'unavailable';
  }
}
