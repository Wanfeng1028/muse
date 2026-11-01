import { useState } from 'react';
import { View, Text } from '@tarojs/components';
import { rollDice } from '../../lib/tools';
import { Ambient, AmbientLight, Card, Disclaimer } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import '../../styles/portal.scss';

// 星座骰子：行星 × 星座 × 宫位三颗骰子随机组合，句式本站新写。
// 纯随机趣味工具，结果由随机数生成，不作断言。
export default function Dice() {
  const [theme] = useTheme();
  const [result, setResult] = useState<ReturnType<typeof rollDice> | null>(null);

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='星座骰子'>
        <Text className='muted'>掷三颗骰子：行星、星座、宫位各一颗，组合成一句话。结果纯随机，仅供娱乐。</Text>
        <View className='btn-medley btn-medley-dark' hoverClass='btn-press' style={{ marginTop: '12px' }} onClick={() => setResult(rollDice())}>掷骰子</View>
        {result ? (
          <View style={{ marginTop: '16px' }}>
            <View style={{ display: 'flex', gap: '12px' }}>
              <View className='tool-full-card' style={{ flex: 1, textAlign: 'center' }}>
                <Text className='tool-mid'>{result.planet}</Text>
                <Text className='caption' style={{ display: 'block' }}>行星</Text>
              </View>
              <View className='tool-full-card' style={{ flex: 1, textAlign: 'center' }}>
                <Text className='tool-mid'>{result.sign}</Text>
                <Text className='caption' style={{ display: 'block' }}>星座</Text>
              </View>
              <View className='tool-full-card' style={{ flex: 1, textAlign: 'center' }}>
                <Text className='tool-mid'>{result.house}</Text>
                <Text className='caption' style={{ display: 'block' }}>宫位</Text>
              </View>
            </View>
            <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>{result.line}</Text>
          </View>
        ) : null}
      </Card>
      <Disclaimer />
    </View>
  );
}
