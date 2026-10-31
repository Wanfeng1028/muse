import { useState } from 'react';
import { View, Text } from '@tarojs/components';
import { STAR_ENTRIES, PALACE_ENTRIES, SIHUA_ENTRIES, PATTERN_ENTRIES } from '../../lib/knowledge';
import { Card } from '../../components/ui';

const TABS = [
  { id: 'star', label: '星曜', entries: STAR_ENTRIES },
  { id: 'palace', label: '宫位', entries: PALACE_ENTRIES },
  { id: 'sihua', label: '四化', entries: SIHUA_ENTRIES },
  { id: 'pattern', label: '格局', entries: PATTERN_ENTRIES },
] as const;

export default function Knowledge() {
  const [tab, setTab] = useState<string>('star');
  const current = TABS.find((t) => t.id === tab) ?? TABS[0];
  return (
    <View className='page'>
      <View style={{ display: 'flex', marginBottom: '12px' }}>
        {TABS.map((t) => (
          <View key={t.id} className={t.id === tab ? 'chip chip-accent' : 'chip'} onClick={() => setTab(t.id)}>
            {t.label}
          </View>
        ))}
      </View>
      {current.entries.map((e) => (
        <Card key={e.title} title={e.title}>
          <Text className='muted' style={{ lineHeight: 1.7 }}>{e.body}</Text>
        </Card>
      ))}
    </View>
  );
}
