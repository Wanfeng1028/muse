// PersonaCard: base persona image, rendered locally from a star preset.
// Gradient card + Lucide star glyph + star name + title + motif + note.
// The "形象仅为装饰" footnote is always present; the card never makes
// fate claims. AI custom image is a separate button owned by the page
// (it needs cloud + 100 points); this component only renders the base.
// Compact mode is a 64px mini badge (star + star name only): the full
// motif/note text would wrap one character per line and overflow a
// 64px container, so it is omitted here by design.

import { View, Text } from '@tarojs/components';
import { Icon } from './icons';
import type { PersonaPreset } from '../lib/persona';

export default function PersonaCard({ preset, compact }: { preset: PersonaPreset; compact?: boolean }) {
  const gradient = 'linear-gradient(135deg, ' + preset.colors[0] + ', ' + preset.colors[1] + ')';
  if (compact) {
    return (
      <View className='persona-card' style={{ background: gradient, padding: '8px 4px', overflow: 'hidden' }}>
        <View className='persona-star'>
          <Icon name='star' tone='white' size='44px' />
        </View>
        <Text className='persona-name' style={{ display: 'block', fontSize: '13px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{preset.star}</Text>
      </View>
    );
  }
  return (
    <View className='persona-card' style={{ background: gradient }}>
      <View className='persona-star'>
        <Icon name='star' tone='white' size={compact ? '64px' : '96px'} />
      </View>
      <Text className='persona-name'>{preset.star}</Text>
      <Text className='persona-title'>{preset.title}</Text>
      <Text className='persona-motif'>{preset.motif}</Text>
      <Text className='persona-note'>{preset.note}</Text>
      <Text className='persona-foot'>形象仅为装饰</Text>
    </View>
  );
}
