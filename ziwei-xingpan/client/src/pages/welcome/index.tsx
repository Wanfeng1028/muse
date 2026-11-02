import { View, Text, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import starMark from '../../assets/logo/star-mark.png';
import wireImg from '../../assets/ref-home/wire-pale.png';
import eyeWhite from '../../assets/lucide/png/eye-white.png';
import bookWhite from '../../assets/lucide/png/book-open-white.png';
import './index.scss';

// Welcome (splash) page, adaptation round 2026-11-02 16:24 (user
// order: content to our text, Get Started capsule to our color
// scheme, icons to ours; tech stack already Taro, no rewrite needed).
// Structure stays the photo-27 / LivingOnboarding skeleton (logo
// square + split-curve wire + summary card + tilted chips + label
// pill + big bold headline + centered copy + bottom capsule); only
// the content layer is swapped to this product's own: star brand,
// 命盘摘要 card (line + feature lines), 年度运势 peek, 免费看盘 /
// 十三维解读 chips, 紫微斗数 pill, 你的命盘，一眼看懂。 headline,
// Get Started capsule in the Gemini blue gradient (text stays
// English per the 2026-11-02 15:59 order). The reference card head's
// arrow/tools row is dropped: a back arrow on an entry splash is
// fake chrome with no function in this product. The right chip is
// moved down to the feature-lines height: at title height it would
// cover our (longer) card line. Tech stack note: this page is Taro
// (View/Text/Image + Taro.navigateTo, builds to weapp) — the
// reproduction was ported to our stack, never pasted as web code.
// Button target unchanged: Get Started goes to this product's chat
// page. Entry rule unchanged: first launch, no local login marker
// (mount-only home guard, never a loop).
export default function Welcome() {
  return (
    <View className='welcome-ref'>
      <View className='welcome-ref-glow' />
      <View className='welcome-ref-body'>
        <View className='welcome-ref-logo'>
          <Image className='welcome-ref-logo-img' src={starMark} mode='aspectFit' />
        </View>
        <Image className='welcome-ref-lines' src={wireImg} mode='aspectFit' />
        <View className='welcome-ref-card'>
          <Text className='welcome-ref-card-title'>命盘摘要</Text>
          <Text className='welcome-ref-card-line'>输入出生信息，一次排盘，看懂整张命盘。</Text>
          <View className='welcome-ref-feat'>
            <Text className='welcome-ref-feat-item'>十三维解读，随盘解锁</Text>
            <Text className='welcome-ref-feat-item'>对话每日 2M tokens 免费</Text>
          </View>
        </View>
        <View className='welcome-ref-better'>
          <Text className='welcome-ref-better-title'>年度运势</Text>
          <Text className='welcome-ref-better-line'>流年四化与大限，100 积分/次</Text>
        </View>
        <View className='welcome-ref-chip welcome-ref-chip-left'>
          <View className='welcome-ref-chip-dot'>
            <Image className='welcome-ref-chip-ico' src={eyeWhite} mode='aspectFit' />
          </View>
          免费看盘
        </View>
        <View className='welcome-ref-chip welcome-ref-chip-right'>
          <View className='welcome-ref-chip-dot'>
            <Image className='welcome-ref-chip-ico' src={bookWhite} mode='aspectFit' />
          </View>
          十三维解读
        </View>
        <View className='welcome-ref-pill'>
          <Image className='welcome-ref-pill-ico' src={starMark} mode='aspectFit' />
          紫微斗数
        </View>
        <View className='welcome-ref-title'>
          <Text className='welcome-ref-title-line'>你的命盘一看就懂</Text>
        </View>
        <Text className='welcome-ref-copy'>本地排盘，十三维解读，对话随时问。积分规则公开透明。</Text>
        <View className='welcome-ref-cta' onClick={() => Taro.navigateTo({ url: '/pages/chat/index' })}>Get Started</View>
      </View>
    </View>
  );
}
