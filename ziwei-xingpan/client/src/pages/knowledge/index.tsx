import { useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { STAR_ENTRIES, PALACE_ENTRIES, SIHUA_ENTRIES, PATTERN_ENTRIES } from '../../lib/knowledge';
import { AmbientLight, Card, Cover } from '../../components/ui';
import CustomTabBar from '../../custom-tab-bar';
import './index.scss';

const TABS = [
  { id: 'star', label: '星曜', entries: STAR_ENTRIES, coverTitle: '星曜', coverSub: '十四主星与辅星、吉星、煞星的性格、亮度与看法。' },
  { id: 'palace', label: '宫位', entries: PALACE_ENTRIES, coverTitle: '十二宫', coverSub: '命、兄、夫、子、财、疾、迁、友、官、田、福、父各自主掌的面向。' },
  { id: 'sihua', label: '四化', entries: SIHUA_ENTRIES, coverTitle: '四化', coverSub: '禄、权、科、忌随天干而动的引动与变化。' },
  { id: 'pattern', label: '格局', entries: PATTERN_ENTRIES, coverTitle: '格局', coverSub: '常见组合的成格条件与看法，仅作学习参考。' },
] as const;

export default function Knowledge() {
  const [tab, setTab] = useState<string>('star');
  const current = TABS.find((t) => t.id === tab) ?? TABS[0];
  return (
    <View className='page page-light'>
      <AmbientLight />
      <View className='seg'>
        {TABS.map((t) => (
          <View key={t.id} className={t.id === tab ? `seg-tab seg-tab-${t.id} seg-tab-active` : `seg-tab seg-tab-${t.id}`} onClick={() => setTab(t.id)}>
            {t.label}
          </View>
        ))}
      </View>
      <Cover kind={current.id} title={current.coverTitle} sub={current.coverSub} />
      {current.entries.map((e) => (
        <View key={e.title} className={`know-cat-${current.id}`}>
          <Card light title={e.title}>
            <Text className='know-body'>{e.body}</Text>
          </Card>
        </View>
      ))}
      {/* H5 fallback mount (weapp injects the custom tabBar natively). */}
      {Taro.getEnv() === Taro.ENV_TYPE.WEB ? <CustomTabBar /> : null}
    </View>
  );
}
