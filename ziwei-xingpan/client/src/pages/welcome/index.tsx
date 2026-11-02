import { View, Text, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { useTheme } from '../../lib/theme';
import starMark from '../../assets/logo/star-mark.png';
import wireImg from '../../assets/welcome-wire.png';
import eyeWhite from '../../assets/lucide/png/eye-white.png';
import bookWhite from '../../assets/lucide/png/book-open-white.png';
import './index.scss';

// Welcome (splash) page, rebuilt 2026-11-02 15:47 to faithfully
// reproduce the photo-24 Smart Home splash (photo-27 re-shot,
// miniappdesign LivingOnboarding as the measured reference): full-bleed
// Gemini blue gradient top, white rounded-square brand mark centered,
// the split-curve wire (same curve geometry as the reference) down to
// layered overlapping summary cards with two tilted feature stickers,
// a small centered label pill, a big bold centered headline, gray
// centered sub copy, and a full-width bottom capsule. Layout and visual
// weight follow the reference; parameters are this product's own:
// Gemini blue (not the reference blue-purple), star brand mark, Chinese
// copy, and the button reads Get Started in English (2026-11-02 15:59
// user order: Get Started stays English no matter what) and goes to
// this product's chat page. Card lines are real product facts, no
// invented data.
// This page is a user-specified exception to the 2026-11-02 nine rules:
// the gradient top, the wire image, and the big bold headline are
// allowed here. Entry rule (home mount-only guard): this page shows on
// first launch when no local login marker exists. There is NO such
// marker yet — loginFlow stores nothing locally — so until cloud联调
// adds a local session marker, this page shows on every cold start,
// once per session (the guard is mount-only, never useDidShow, so
// pressing back from here lands on the already-mounted home and never
// re-bounces).
export default function Welcome() {
  const [theme] = useTheme();
  return (
    <View className={'page theme-' + theme + ' welcome-page'}>
      <View className='welcome-glow' />
      <View className='welcome-logo-sq'>
        <Image className='welcome-logo-img' src={starMark} mode='aspectFit' />
      </View>
      <Text className='welcome-hero-name'>星命盘</Text>
      <Image className='welcome-wire-img' src={wireImg} mode='aspectFit' />
      <View className='welcome-stack'>
        <View className='welcome-badge welcome-badge-a'>
          <View className='welcome-badge-dot'>
            <Image className='welcome-badge-ico' src={eyeWhite} mode='aspectFit' />
          </View>
          免费看盘
        </View>
        <View className='welcome-card-main'>
          <Text className='welcome-card-kicker'>命盘摘要</Text>
          <Text className='welcome-card-line'>输入出生信息，一次排盘，看懂整张命盘。</Text>
          <View className='welcome-feat'>
            <Text className='welcome-feat-item'>十三维解读，随盘解锁</Text>
            <Text className='welcome-feat-item'>对话每日 2M tokens 免费</Text>
          </View>
          <View className='welcome-badge welcome-badge-b'>
            <View className='welcome-badge-dot'>
              <Image className='welcome-badge-ico' src={bookWhite} mode='aspectFit' />
            </View>
            十三维解读
          </View>
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
        <View className='welcome-cta' onClick={() => Taro.navigateTo({ url: '/pages/chat/index' })}>Get Started</View>
      </View>
    </View>
  );
}
