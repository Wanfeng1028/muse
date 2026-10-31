import { View, Text } from '@tarojs/components';
import type { ReactNode } from 'react';
import { DISCLAIMER } from '../lib/chart';
import './ui.scss';

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <View className='card'>
      {title ? <View className='card-title'>{title}</View> : null}
      {children}
    </View>
  );
}

export function Pill({ text, accent }: { text: string; accent?: boolean }) {
  return <Text className={accent ? 'chip chip-accent' : 'chip'}>{text}</Text>;
}

export function Disclaimer() {
  return <View className='disclaimer'>{DISCLAIMER}</View>;
}
