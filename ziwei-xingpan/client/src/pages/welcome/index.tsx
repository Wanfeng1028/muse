import { View, Text, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { useTheme } from '../../lib/theme';
import starMark from '../../assets/logo/star-mark.png';
import './index.scss';

// Welcome (splash) page. 2026-11-02 12:03 user order: rebuild it to
// actually look like the photo-24 Smart Home splash (photo-27 re-shot):
// gradient hero panel on top, white rounded-square brand mark centered,
// a thin wire down to layered overlapping summary cards with two tilted
// feature stickers, a small centered section label, a big bold centered
// headline, gray centered sub copy, and a full-width Get Started capsule
// anchored at the bottom. Structure and visual weight follow the
// reference; colors are this product's own (Gemini blue panel, no
// copied blue-purple), copy is this product's own (no Smart Home
// wording, no invented data — card lines are real product facts).
// This page is a user-specified exception to the 2026-11-02 nine rules:
// the hero gradient panel and the big bold headline are allowed here.
// Get Started goes to the existing login/register page; auth logic
// itself is untouched. Entry rule (home mount-only guard): this page
// shows on first launch when no local login marker exists. There is NO
// such marker yet — loginFlow stores nothing locally — so until cloud
//联调 adds a local session marker, this page shows on every cold start,
// once per session (the guard is mount-only, never useDidShow, so
// pressing back from here lands on the already-mounted home and never
// re-bounces).
export default function Welcome() {
  const [theme] = useTheme();
  return (
    <View className={'page theme-' + theme + ' welcome-page'}>
      <View className='welcome-hero'>
        <View className='welcome-logo-sq'>
          <Image className='welcome-logo-img' src={starMark} mode='aspectFit' />
        </View>
        <Text className='welcome-hero-name'>星命盘</Text>
        <View className='welcome-wire' />
      </View>
      <View className='welcome-stack'>
        <View className='welcome-badge welcome-badge-a'>免费看盘</View>
        <View className='welcome-card-main'>
          <Text className='welcome-card-kicker'>命盘摘要</Text>
          <Text className='welcome-card-line'>输入出生信息，一次排盘，看懂整张命盘。</Text>
          <View className='welcome-feat'>
            <Text className='welcome-feat-item'>十三维解读，随盘解锁</Text>
            <Text className='welcome-feat-item'>对话每日 2M tokens 免费</Text>
          </View>
          <View className='welcome-badge welcome-badge-b'>十三维解读</View>
        </View>
        <View className='welcome-card-peek'>
          <Text className='welcome-peek-kicker'>年度运势</Text>
          <Text className='welcome-peek-line'>流年四化与大限，100 积分/次</Text>
        </View>
      </View>
      <View className='welcome-label'>
        <Image className='welcome-label-mark' src={starMark} mode='aspectFit' />
        <Text className='welcome-label-text'>紫微斗数</Text>
      </View>
      <View className='welcome-title'>
        <Text className='welcome-title-line'>你的命盘，</Text>
        <Text className='welcome-title-line'>一眼看懂。</Text>
      </View>
      <Text className='welcome-sub'>本地排盘，十三维解读，对话随时问。积分规则公开透明。</Text>
      <View className='welcome-foot'>
        <View className='welcome-cta' onClick={() => Taro.navigateTo({ url: '/pages/auth/index' })}>Get Started</View>
      </View>
    </View>
  );
}
