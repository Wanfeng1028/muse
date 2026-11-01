import { View, Text, Image } from '@tarojs/components';
import type { ReactNode } from 'react';
import { DISCLAIMER } from '../lib/chart';
import arrowUp from '../assets/arrow-up.png';
import './ui.scss';

// v3 ambient layers (gap 1 / gap 4 light half). Pure background Views:
// no handlers, no text, no layout effect beyond the fixed layer itself.
export function Ambient({ welcome }: { welcome?: boolean }) {
  return <View className={welcome ? 'ambient ambient-welcome' : 'ambient'} />;
}

export function AmbientLight() {
  return <View className='ambient-light' />;
}

export function Card({ title, children, light }: { title?: string; children: ReactNode; light?: boolean }) {
  return (
    <View className={light ? 'card card-light' : 'card'}>
      {title ? <View className='card-title'>{title}</View> : null}
      {children}
    </View>
  );
}

// Medley InputBar single (composer): 56 bar + 36 send circle.
// The home submit action lives here, not in a full-width white button.
export function ComposerBar({ label, onClick, light }: { label: string; onClick: () => void; light?: boolean }) {
  return (
    <View className={light ? 'composer composer-light' : 'composer'} onClick={onClick}>
      <Text className='composer-label'>{label}</Text>
      <View className='composer-send'>
        <Image className='composer-send-img' src={arrowUp} mode='aspectFit' />
      </View>
    </View>
  );
}

export function Pill({ text, accent }: { text: string; accent?: boolean }) {
  return <Text className={accent ? 'chip chip-accent' : 'chip'}>{text}</Text>;
}

export function Disclaimer() {
  return <View className='disclaimer'>{DISCLAIMER}</View>;
}
