import { useState } from 'react';
import { View, Text } from '@tarojs/components';
import { drawTarot } from '../../lib/tools';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import '../../styles/portal.scss';

// 塔罗牌：22 张大阿卡纳，牌意本站新写；抽牌随机、不放回。
// 趣味工具，不作断言。
export default function Tarot() {
  const [theme] = useTheme();
  const [drawn, setDrawn] = useState<ReturnType<typeof drawTarot>>([]);

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='塔罗牌'>
        <Text className='muted'>从 22 张大阿卡纳中随机抽牌（不放回），牌意为本站新写，仅供娱乐参考。</Text>
        <View className='btn-row' style={{ marginTop: '12px' }}>
          <View className='btn-medley btn-medley-dark' hoverClass='btn-press' onClick={() => setDrawn(drawTarot(1))}>抽 1 张</View>
          <View className='btn-medley btn-medley-outline-light' onClick={() => setDrawn(drawTarot(3))}>抽 3 张</View>
        </View>
        {drawn.map((d, i) => (
          <View key={i} className='tool-full-card' style={{ marginTop: '12px' }}>
            <Text className='tool-mid'>{d.card.name} · {d.reversed ? '逆位' : '正位'}</Text>
            <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{d.reversed ? d.card.rev : d.card.up}</Text>
          </View>
        ))}
      </Card>
      <Disclaimer />
    </View>
  );
}
