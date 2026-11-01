import { useEffect, useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { loadChart } from '../../lib/chart';
import { fortuneToday, palaceByName, palaceScore } from '../../lib/fortune';
import type { ZiweiChart } from '../../engine/types';
import { Ambient, AmbientLight, Card, Disclaimer, EmptyState } from '../../components/ui';
import { useTheme } from '../../lib/theme';
import '../../styles/portal.scss';

// 今日运势详情：综合分与四维分的完整拆解，公式全文写在页内与
// PORTAL.md 中；无盘时诚实空态，不造数。
export default function Fortune() {
  const [theme] = useTheme();
  const [chart, setChart] = useState<ZiweiChart | null>(null);
  useEffect(() => { setChart(loadChart()); }, []);

  if (!chart) {
    return (
      <View className={'page page-light theme-' + theme}>
        {theme === 'light' ? <AmbientLight /> : <Ambient />}
        <Card light title='今日运势'>
          <EmptyState title='还没有命盘' hint='今日运势由你的命盘实算，排盘后这里会显示综合分与四项分。' actionLabel='去排盘' onAction={() => Taro.navigateTo({ url: '/pages/birth/index' })} />
        </Card>
      </View>
    );
  }

  const f = fortuneToday(chart);
  const dims = [
    { label: '爱情', palace: '夫妻', v: f.love },
    { label: '财富', palace: '财帛', v: f.wealth },
    { label: '事业', palace: '官禄', v: f.career },
    { label: '学习', palace: '父母', v: f.study },
  ];

  return (
    <View className={'page page-light theme-' + theme}>
      {theme === 'light' ? <AmbientLight /> : <Ambient />}
      <Card light title={`今日运势 · ${f.dateLabel} ${f.weekday}`}>
        <Text className='muted'>{f.lunarLabel} · 今日地支落{f.dayPalaceName}宫</Text>
        <Text className='tool-big' style={{ display: 'block', marginTop: '12px' }}>{f.total}</Text>
        <Text className='muted' style={{ display: 'block' }}>综合分（{f.band}）</Text>
        <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{f.oneLiner}</Text>
        {dims.map((d) => {
          const p = palaceByName(chart, d.palace);
          const majors = p ? p.stars.filter((s) => s.type === 'major').map((s) => `${s.name}${s.brightnessRaw ?? ''}`).join(' ') : '';
          return (
            <View key={d.label}>
              <View className='bar-row'>
                <Text className='bar-row-label'>{d.label} · {d.palace}</Text>
                <View className='bar-row-track'><View className='bar-row-fill' style={{ width: d.v + '%' }} /></View>
                <Text className='bar-row-val'>{d.v}</Text>
              </View>
              <Text className='caption' style={{ display: 'block', marginTop: '4px' }}>
                宫分 {palaceScore(p)} · 主星 {majors || '无主星'}
              </Text>
            </View>
          );
        })}
        <Text className='caption' style={{ display: 'block', marginTop: '16px' }}>
          公式：单维分 = 60 + 宫分，夹在 35 与 95 之间。宫分 = 主星亮度（庙 8、旺 6、得 4、利 2、平 0、不 -2、闲 -1、陷 -6、地 -4）
          + 吉星每颗 +2（上限 +6）+ 煞星每颗 -3（下限 -9）+ 四化（禄 +5、权 +3、科 +3、忌 -8）。
          综合 = 四维均值 + 日支修正（今日地支落宫有吉星无煞星 +4，有煞星无吉星 -4，否则 0），再夹在 35 与 95 之间。
          分数仅供娱乐参考，不构成决策建议。
        </Text>
      </Card>
      <Disclaimer />
    </View>
  );
}
