import { useEffect, useState } from 'react';
import { View, Text, Input, Image } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { Icon } from '../../components/icons';
import icListRed from '../../assets/lucide/png/ref/list-red.png';
import icChatGreen from '../../assets/lucide/png/ref/message-square-green.png';
import icCalAmber from '../../assets/lucide/png/ref/calendar-amber.png';
import icArrowDark from '../../assets/lucide/png/ref/arrow-dark.png';
import { hasLoginFlag } from '../../lib/session';
import { setHomeQuestion } from '../../lib/nav';
import './index.scss';

// 首页第一步（2026-11-02 用户定）：把用户已复现好的 HealthChat
// （miniappdesign/src/screens/HealthAI.tsx）原样移植到本站首页，
// 不改内容、不改尺寸、不改颜色。StatusBar/HomeBar 是手机壳 chrome，
// 小程序有原生导航栏与 tabBar，不移植。图标一律 Lucide（本站铁律）：
// 复现稿的 user/users/list/chat/calendar/mic/arrow-up 对应本站图标库，
// 其中红/绿/黄三色芯片图标与深色发送箭头是复现稿原色，放在
// assets/lucide/ref/（仅复现稿用，不进图标库）；蓝芯片用库里的蓝图标。
// 复现稿只有浅色，主题切换在第二步适配时接；本页目前固定浅色。
// 芯片与输入框不是摆设：芯片点进对话页，输入框可打字、发送带问题进对话页。
const CHIPS = [
  { label: 'Check Symptoms', tone: 'blue', icon: 'user' as const, ref: null as string | null },
  { label: 'Check Available Doctor', tone: 'blue', icon: 'users' as const, ref: null },
  { label: 'Today my Report', tone: 'red', icon: null, ref: icListRed },
  { label: 'Chat With Ai', tone: 'green', icon: null, ref: icChatGreen },
  { label: 'Your Upcoming Appointment', tone: 'amber', icon: null, ref: icCalAmber },
];

export default function Home() {
  const [question, setQuestion] = useState('');

  // 登录守夜（2026-11-02 用户定：登录后进首页）:只有未登录才推欢迎页，
  // 已登录直接留首页。mount-only：tab 页常驻，切换 tab 不重挂载，
  // 不会反复推欢迎页。原生 tabBar 本页可见。
  useEffect(() => {
    if (!hasLoginFlag()) {
      Taro.navigateTo({ url: '/pages/welcome/index' }).catch(() => {});
    }
  }, []);

  const goChat = (q?: string) => {
    if (q && q.trim()) setHomeQuestion(q.trim());
    Taro.navigateTo({ url: '/pages/chat/index' }).catch(() => {});
  };

  return (
    <View className='page home-root theme-light'>
      <View className='hl-chat__sky' />
      <View className='hl-chat__body'>
        <View className='hl-orb'>
          <View className='hl-orb-ring' />
        </View>
        <View className='hl-chat__title'>
          <Text className='hl-title-line'>Hi ALex</Text>
          <Text className='hl-title-line'>How Can I Help You?</Text>
        </View>
        <Text className='hl-chat__sub'>Your smart Your smart Your smart</Text>
        <View className='hl-chips'>
          {CHIPS.map((chip) => (
            <View key={chip.label} className={'hl-chip hl-chip--' + chip.tone} onClick={() => goChat()}>
              {chip.icon ? (
                <Icon name={chip.icon} tone='blue' size='15px' />
              ) : (
                <Image className='lucide-icon' style={{ width: '15px', height: '15px' }} src={chip.ref as string} mode='aspectFit' />
              )}
              <Text>{chip.label}</Text>
            </View>
          ))}
        </View>
      </View>
      <View className='hl-composer'>
        <View className='hl-input'>
          <Input
            className='hl-input-field'
            placeholder='Write your message...'
            placeholderClass='hl-input-ph'
            value={question}
            onInput={(e) => setQuestion(e.detail.value)}
            confirmType='send'
            onConfirm={() => goChat(question)}
          />
          <Icon name='mic' tone='gray' size='17px' />
        </View>
        <View className='hl-send' onClick={() => goChat(question)}>
          <Image className='lucide-icon' style={{ width: '18px', height: '18px' }} src={icArrowDark} mode='aspectFit' />
        </View>
      </View>
    </View>
  );
}
