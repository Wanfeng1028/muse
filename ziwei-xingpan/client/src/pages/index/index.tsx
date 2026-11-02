import { useEffect } from 'react';
import { View, Text, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import lamp from '../../assets/ref-home/lamp.jpg';
import icoTarget from '../../assets/ref-home/ico-target.png';
import icoBell from '../../assets/ref-home/ico-bell.png';
import icoBattery from '../../assets/ref-home/ico-battery.png';
import icoBulb from '../../assets/ref-home/ico-bulb.png';
import icoLock from '../../assets/ref-home/ico-lock.png';
import icoMic from '../../assets/ref-home/ico-mic.png';
import icoWifi from '../../assets/ref-home/ico-wifi.png';
import icoPower from '../../assets/ref-home/ico-power.png';
import icoHome from '../../assets/ref-home/ico-home.png';
import icoDoc from '../../assets/ref-home/ico-doc.png';
import icoSparkles from '../../assets/ref-home/ico-sparkles.png';
import icoRefresh from '../../assets/ref-home/ico-refresh.png';
import icoSettings from '../../assets/ref-home/ico-settings.png';
import './index.scss';

// Home page, reference pass 2026-11-02 16:04 (user order: pull the
// miniappdesign Smart Home dashboard over first, with our Taro stack,
// content verbatim, our own adaptation afterwards). This is a port of
// miniappdesign LivingDashboard: sizes are that file's CSS px times
// 750/390, colors/weights/copy/icons are verbatim (icon PNGs in
// assets/ref-home/ are rendered from miniappdesign's own SVG paths;
// the lamp photo is miniappdesign's lamp.webp converted to JPG).
// Deliberately NOT this product's home yet: no chart anchor, no 运限，
// no interpretations — those live in git history (the previous
// index.tsx/index.scss) and come back when the user orders adaptation.
// Temporary for this pass: the native tabBar is hidden on mount so the
// reproduced tab bar reads exactly like the reference (restored on
// unmount); the reproduced tabs are visual-only, no actions, exactly
// as in the original. The welcome cold-start guard is unchanged
// (mount-only navigate to welcome, never a loop).
const TABS = [
  { icon: icoHome, active: true, label: 'home' },
  { icon: icoDoc, active: false, label: 'doc' },
  { icon: icoSparkles, active: false, label: 'sparkles' },
  { icon: icoRefresh, active: false, label: 'refresh' },
  { icon: icoSettings, active: false, label: 'settings' },
];

export default function Index() {
  useEffect(() => {
    // Automatic (not user-tapped) navigation: if the stack cannot take
    // it, stay on home instead of surfacing an unhandled rejection.
    Taro.navigateTo({ url: '/pages/welcome/index' }).catch(() => {});
  }, []);
  useEffect(() => {
    Taro.hideTabBar({}).catch(() => {});
    return () => { Taro.showTabBar({}).catch(() => {}); };
  }, []);

  return (
    <View className='home-ref'>
      <View className='home-ref-header'>
        <View className='home-ref-avatar'>JC</View>
        <View className='home-ref-who'>
          <Text className='home-ref-name'>James Carter</Text>
          <View className='home-ref-loc'>
            <Image className='home-ref-loc-ico' src={icoTarget} mode='aspectFit' />
            <Text>New York City</Text>
          </View>
        </View>
        <View className='home-ref-bell'>
          <Image className='home-ref-bell-ico' src={icoBell} mode='aspectFit' />
        </View>
      </View>

      <View className='home-ref-section-head'>
        <Text className='home-ref-section-title'>Favourites</Text>
        <Text className='home-ref-see-all'>See all</Text>
      </View>

      <View className='home-ref-hero'>
        <View className='home-ref-stats'>
          <View className='home-ref-stat'>
            <Text className='home-ref-stat-value'>98%</Text>
            <View className='home-ref-stat-label'>
              <Image className='home-ref-stat-ico' src={icoBattery} mode='aspectFit' />
              <Text>battery</Text>
            </View>
          </View>
          <View className='home-ref-stat'>
            <Text className='home-ref-stat-value'>On</Text>
            <View className='home-ref-stat-label'>
              <Image className='home-ref-stat-ico' src={icoBulb} mode='aspectFit' />
              <Text>light</Text>
            </View>
          </View>
        </View>
        <Image className='home-ref-photo' src={lamp} mode='aspectFill' />
        <View className='home-ref-photo-fade' />
        <View className='home-ref-control'>
          <View className='home-ref-ctl-btn'>
            <Image className='home-ref-ctl-ico' src={icoLock} mode='aspectFit' />
          </View>
          <View className='home-ref-step'>
            <Text>›</Text>
            <Text>›</Text>
            <Text>›</Text>
          </View>
          <View className='home-ref-ctl-btn'>
            <Image className='home-ref-ctl-ico' src={icoLock} mode='aspectFit' />
          </View>
        </View>
      </View>

      <View className='home-ref-tiles'>
        <View className='home-ref-tile'>
          <View className='home-ref-tile-top'>
            <View className='home-ref-glyph'>
              <Image className='home-ref-glyph-ico' src={icoMic} mode='aspectFit' />
            </View>
            <View className='home-ref-power'>
              <Image className='home-ref-power-ico' src={icoPower} mode='aspectFit' />
              <View className='home-ref-power-slash' />
            </View>
          </View>
          <View>
            <Text className='home-ref-tile-name'>Assistant</Text>
            <View className='home-ref-tile-meta'>
              <Image className='home-ref-meta-ico' src={icoBattery} mode='aspectFit' />
              <Text>80%</Text>
            </View>
          </View>
        </View>
        <View className='home-ref-tile'>
          <View className='home-ref-tile-top'>
            <View className='home-ref-glyph'>
              <Image className='home-ref-glyph-ico' src={icoWifi} mode='aspectFit' />
            </View>
            <View className='home-ref-power'>
              <Image className='home-ref-power-ico' src={icoPower} mode='aspectFit' />
              <View className='home-ref-power-slash' />
            </View>
          </View>
          <View>
            <Text className='home-ref-tile-name'>Hus Bridge</Text>
            <View className='home-ref-tile-meta'>
              <Image className='home-ref-meta-ico' src={icoBattery} mode='aspectFit' />
              <Text>76%</Text>
            </View>
          </View>
        </View>
      </View>

      <View className='home-ref-ghost-row'>
        <View className='home-ref-ghost-btn'>Reorder</View>
        <View className='home-ref-ghost-btn'>Edit</View>
      </View>

      <View className='home-ref-tabbar'>
        {TABS.map((tab) => (
          <View key={tab.label} className={'home-ref-tab-btn' + (tab.active ? ' is-active' : '')}>
            <Image className='home-ref-tab-ico' src={tab.icon} mode='aspectFit' />
          </View>
        ))}
      </View>
    </View>
  );
}
