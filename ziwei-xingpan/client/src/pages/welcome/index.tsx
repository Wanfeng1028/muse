import { View, Text, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { useTheme } from '../../lib/theme';
import starMark from '../../assets/logo/star-mark.png';
import './index.scss';

// Welcome (splash) page, 2026-11-02 user order: layout borrowed from the
// Smart Home splash in photo-24 (brand card on top, one summary card,
// big title, sub copy, bottom Get Started capsule) — layout ONLY.
// All copy is this product's own: no Smart Home wording, no invented
// features, no copied numbers. Get Started goes to the existing
// login/register page; auth logic itself is untouched.
// Entry rule (home mount-only guard): this page shows on first launch
// when no local login marker exists. There is NO such marker yet —
// loginFlow stores nothing locally — so until cloud联调 adds a local
// session marker, this page shows on every cold start, once per
// session (the guard is mount-only, never useDidShow, so pressing back
// from here lands on the already-mounted home and never re-bounces).
export default function Welcome() {
  const [theme] = useTheme();
  return (
    <View className={'page page-light theme-' + theme}>
      <View className='welcome-brand'>
        <Image className='welcome-mark' src={starMark} mode='aspectFit' />
        <Text className='welcome-brand-name'>星命盘</Text>
      </View>
      <View className='welcome-card'>
        <Text className='welcome-card-words'>排盘 · 解读 · 对话 · 积分</Text>
        <Text className='welcome-card-line'>一次排盘，看懂命盘、读懂解读、随时对话，积分规则公开透明。</Text>
      </View>
      <View className='welcome-title'>
        <Text className='welcome-title-line'>你的命盘，</Text>
        <Text className='welcome-title-line'>一眼看懂。</Text>
      </View>
      <Text className='welcome-sub'>本地排盘，十三维解读，对话随时问——先看盘，再决定要不要登录。</Text>
      <View className='welcome-foot'>
        <View className='welcome-cta' onClick={() => Taro.navigateTo({ url: '/pages/auth/index' })}>Get Started</View>
      </View>
    </View>
  );
}
