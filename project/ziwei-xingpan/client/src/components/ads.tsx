import { View } from '@tarojs/components';
import { Ad } from '@tarojs/components';

// Banner ad slot. Renders nothing when the unit id is missing or a
// placeholder: an unopened traffic-master slot must never render a fake
// ad frame. The caller decides visibility by membership tier (Pro/Max
// hide banners) and passes only a live id.
export function BannerAd({ unitId }: { unitId: string | null }) {
  if (!unitId) return null;
  return (
    <View style={{ marginTop: '12px' }}>
      <Ad unitId={unitId} />
    </View>
  );
}
