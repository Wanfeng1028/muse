import { View, Text, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import googleG from '../../assets/ref-home/google-g.png';
import wireImg from '../../assets/ref-home/wire-pale.png';
import icoArrow from '../../assets/ref-home/ico-arrow.png';
import icoSparkles from '../../assets/ref-home/ico-sparkles-dk.png';
import icoMore from '../../assets/ref-home/ico-more.png';
import icoBulbW from '../../assets/ref-home/ico-bulb-w.png';
import icoMicW from '../../assets/ref-home/ico-mic-w.png';
import icoHomeBlue from '../../assets/ref-home/ico-home-blue.png';
import './index.scss';

// Welcome (splash) page, reference pass 2026-11-02 16:14 (user order:
// bring the reproduced code over directly, disregard our own content
// for this pass). This is miniappdesign LivingOnboarding ported to
// this project's Taro stack, verbatim: sizes are that file's CSS px
// times 750/390, colors/weights/copy/icons verbatim (icon PNGs in
// assets/ref-home/ rendered from miniappdesign's own SVG paths; the
// wire is that file's split-curve path at its original stroke).
// Three places where the code disagrees with the photo it reproduces
// (photo-27) are resolved in favor of the photo, because the user
// judges by the photo: (1) the card head is two rows in the photo
// (arrow row, then title row), not the code's one row; (2) the chips
// sit tilted on the card's top edge (left) and right edge at title
// height (right) in the photo — the code's positions would cover the
// head's arrow and first letters; (3) Better Insight peeks out below
// the main card, shifted right, in the photo — the code keeps it
// inside. Everything else is verbatim.
// The previous welcome versions (our adaptation: Gemini gradient,
// star brand, Chinese copy, 要开始/Get Started routing copy) are in
// git history, not deleted from the repo. The only behavior kept from
// this product is the button target: Get Started goes to this
// product's chat page (the original button has no action; a dead end
// here would strand the user on the splash). Entry rule unchanged:
// this page shows on first launch when no local login marker exists
// (mount-only home guard, never a loop).
export default function Welcome() {
  return (
    <View className='welcome-ref'>
      <View className='welcome-ref-glow' />
      <View className='welcome-ref-body'>
        <View className='welcome-ref-logo'>
          <Image className='welcome-ref-logo-img' src={googleG} mode='aspectFit' />
        </View>
        <Image className='welcome-ref-lines' src={wireImg} mode='aspectFit' />
        <View className='welcome-ref-card'>
          <View className='welcome-ref-card-head-row'>
            <Image className='welcome-ref-head-ico' src={icoArrow} mode='aspectFit' />
            <View className='welcome-ref-head-tools'>
              <Image className='welcome-ref-head-ico' src={icoSparkles} mode='aspectFit' />
              <Image className='welcome-ref-head-ico' src={icoMore} mode='aspectFit' />
            </View>
          </View>
          <Text className='welcome-ref-card-title'>Smart Home Summary</Text>
          <View className='welcome-ref-skeleton'>
            <View className='welcome-ref-bar' style={{ width: '76%' }} />
            <View className='welcome-ref-bar' style={{ width: '56%' }} />
            <View className='welcome-ref-bar' style={{ width: '82%' }} />
            <View className='welcome-ref-bar' style={{ width: '44%' }} />
          </View>
          <View className='welcome-ref-progress'>
            <View className='welcome-ref-progress-fill' />
          </View>
          <View className='welcome-ref-skeleton welcome-ref-skeleton-short'>
            <View className='welcome-ref-bar' style={{ width: '38%' }} />
            <View className='welcome-ref-bar' style={{ width: '52%' }} />
          </View>
        </View>
        <View className='welcome-ref-better'>
          <Text className='welcome-ref-better-title'>Better Insight</Text>
          <View className='welcome-ref-skeleton welcome-ref-skeleton-inside'>
            <View className='welcome-ref-bar' style={{ width: '70%' }} />
            <View className='welcome-ref-bar' style={{ width: '46%' }} />
          </View>
        </View>
        <View className='welcome-ref-chip welcome-ref-chip-left'>
          <View className='welcome-ref-chip-dot welcome-ref-chip-dot-blue'>
            <Image className='welcome-ref-chip-ico' src={icoBulbW} mode='aspectFit' />
          </View>
          Auto Lights
        </View>
        <View className='welcome-ref-chip welcome-ref-chip-right'>
          <View className='welcome-ref-chip-dot welcome-ref-chip-dot-violet'>
            <Image className='welcome-ref-chip-ico' src={icoMicW} mode='aspectFit' />
          </View>
          Voice Control
        </View>
        <View className='welcome-ref-pill'>
          <Image className='welcome-ref-pill-ico' src={icoHomeBlue} mode='aspectFit' />
          Smart Control
        </View>
        <View className='welcome-ref-title'>
          <Text className='welcome-ref-title-line'>Experience Smarter</Text>
          <Text className='welcome-ref-title-line'>Living Every Day</Text>
        </View>
        <Text className='welcome-ref-copy'>Control devices, automate routines, and enjoy seamless comfort tailored to your lifestyle.</Text>
        <View className='welcome-ref-cta' onClick={() => Taro.navigateTo({ url: '/pages/chat/index' })}>Get Started</View>
      </View>
    </View>
  );
}
