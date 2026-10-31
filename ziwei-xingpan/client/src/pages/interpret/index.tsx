import { useEffect, useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { loadChart } from '../../lib/chart';
import { buildDimensions } from '../../lib/interpret';
import { detectPatterns } from '../../engine/patterns';
import type { ZiweiChart } from '../../engine/types';
import { Card, Disclaimer } from '../../components/ui';

export default function Interpret() {
  const [chart, setChart] = useState<ZiweiChart | null>(null);
  useEffect(() => { setChart(loadChart()); }, []);
  if (!chart) {
    return (
      <View className='page'>
        <Card title='还没有命盘'>
          <Text className='muted'>请先在首页排盘，解读会基于该盘生成。</Text>
          <View className='btn' style={{ marginTop: '12px' }} onClick={() => Taro.switchTab({ url: '/pages/index/index' })}>去首页排盘</View>
        </Card>
      </View>
    );
  }
  const dims = buildDimensions(chart);
  const patterns = detectPatterns(chart);
  return (
    <View className='page'>
      <Card title='格局判断'>
        {patterns.length === 0 ? (
          <Text className='muted'>本盘未触发格局库中的常见组合，仍宜以各宫主星与三方四正综合看。</Text>
        ) : patterns.map((p) => (
          <View key={p.name} style={{ marginBottom: '10px' }}>
            <Text style={{ fontWeight: 600 }}>{p.name}</Text>
            <Text className='muted' style={{ display: 'block', marginTop: '4px' }}>{p.description}</Text>
            <Text className='caption' style={{ display: 'block' }}>涉及：{p.palaces.join('、')}</Text>
          </View>
        ))}
        <Disclaimer />
      </Card>
      {dims.map((d) => (
        <Card key={d.id} title={`${d.title}（${d.palaceName}）`}>
          <Text className='muted' style={{ lineHeight: 1.7 }}>{d.body}</Text>
          <Disclaimer />
        </Card>
      ))}
    </View>
  );
}
