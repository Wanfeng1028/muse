import { useEffect, useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { loadChart } from '../../lib/chart';
import { baziOf } from '../../lib/fortune';
import type { ZiweiChart } from '../../engine/types';
import { Ambient, AmbientLight, Card, Disclaimer, EmptyState } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import '../../styles/portal.scss';

// 八字运势：四柱取引擎 lunarInfo（节气四柱优先），五行按天干地支
// 映射计数；无盘时诚实空态。
const PILLAR_LABELS = ['年柱', '月柱', '日柱', '时柱'];
const ELEMENTS = ['金', '木', '水', '火', '土'];

export default function Bazi() {
  const [theme] = useTheme();
  const [chart, setChart] = useState<ZiweiChart | null>(null);
  useEffect(() => { setChart(loadChart()); }, []);

  if (!chart) {
    return (
      <View className={'page page-light theme-' + theme}>
        {theme === 'light' ? <AmbientLight /> : <Ambient />}
        <Card light title='八字运势'>
          <EmptyState title='还没有命盘' hint='八字四柱由你的命盘生成，排盘后这里会显示四柱与五行分布。' actionLabel='去排盘' onAction={() => Taro.navigateTo({ url: '/pages/birth/index' })} />
        </Card>
      </View>
    );
  }

  const bazi = baziOf(chart);
  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title='八字四柱'>
        {bazi.pillars.length === 4 ? (
          <View style={{ display: 'flex', gap: '12px' }}>
            {bazi.pillars.map((p, i) => (
              <View key={i} style={{ flex: 1, textAlign: 'center' }}>
                <Text className='tool-mid' style={{ display: 'block' }}>{p}</Text>
                <Text className='caption'>{PILLAR_LABELS[i]}</Text>
              </View>
            ))}
          </View>
        ) : (
          <Text className='muted'>本盘未带出四柱数据，请重新排盘。</Text>
        )}
        <Text className='muted' style={{ display: 'block', marginTop: '12px' }}>
          日主 {bazi.dayMaster || '—'}（{bazi.dayMasterElement || '—'}）· {chart.wuxingJuName} · 命主 {chart.mingZhu} · 身主 {chart.shenZhu}
        </Text>
      </Card>
      <Card light title='五行分布（四柱八字共 8 字计数）'>
        {ELEMENTS.map((el) => (
          <View key={el} className='bar-row'>
            <Text className='bar-row-label'>{el}</Text>
            <View className='bar-row-track'><View className='bar-row-fill' style={{ width: (bazi.counts[el] / 8 * 100) + '%' }} /></View>
            <Text className='bar-row-val'>{bazi.counts[el]} 字</Text>
          </View>
        ))}
        <Text className='caption' style={{ display: 'block', marginTop: '12px' }}>
          映射：甲乙属木、丙丁属火、戊己属土、庚辛属金、壬癸属水；子亥属水、寅卯属木、巳午属火、申酉属金、辰戌丑未属土。
          五行分布只反映四柱字面构成，不作吉凶断言。
        </Text>
      </Card>
      <Disclaimer />
    </View>
  );
}
